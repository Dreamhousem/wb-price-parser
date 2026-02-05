import requests
import json
import time
import csv
import os
from datetime import datetime

# --- КОНСТАНТЫ И НАСТРОЙКИ ---
CONFIG_FILE = 'config.json'
CSV_FILE = 'prices.csv'

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[SYSTEM] Ошибка: Файл {CONFIG_FILE} не найден.")
        exit(1)
    except json.JSONDecodeError:
        print(f"[SYSTEM] Ошибка: {CONFIG_FILE} содержит некорректный JSON.")
        exit(1)

def init_csv():
    """Создает файл и заголовки, если файла нет"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['timestamp', 'id', 'name', 'product_price', 'logistics', 'return', 'total_price'])

def save_to_csv(item_data):
    """Дописывает строку в CSV"""
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            item_data['id'],
            item_data['name'],
            f"{item_data['product']:.2f}".replace('.', ','), # Excel любит запятые
            f"{item_data['logistics']:.2f}".replace('.', ','),
            f"{item_data['return']:.2f}".replace('.', ','),
            f"{item_data['total']:.2f}".replace('.', ',')
        ])

def _find_price_block(product_obj):
    """
    Пытается найти блок с ценой в разных местах JSON.
    Возвращает словарь цены или None.
    """
    # 1. Пробуем первый размер (стандарт для сумок/штук)
    sizes = product_obj.get('sizes', [])
    if sizes and 'price' in sizes[0]:
        return sizes[0]['price']
    
    # 2. Если sizes[0] пуст, ищем в любом другом размере (редкий кейс)
    for size in sizes:
        if 'price' in size:
            return size['price']

    # 3. (Legacy) Иногда цена бывает в корне объекта (очень старый API, но вдруг)
    # Тут сложнее, так как структура разная, но для надежности вернем None,
    # чтобы выкинуть ошибку [DATA], а не гадать.
    return None

def process_items(config):
    settings = config['settings']
    items = config['items']
    
    # Заголовки как у браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    print(f"--- Запуск проверки ({datetime.now().strftime('%H:%M:%S')}) ---")

    for item in items:
        article = item['id']
        name = item['name']
        
        url = (
            f"https://card.wb.ru/cards/v4/detail?"
            f"appType=1&"
            f"curr={settings['currency']}&"
            f"dest={settings['dest']}&"
            f"spp={settings['spp']}&"
            f"nm={article}"
        )

        try:
            # 1. ЗАПРОС (с таймаутом)
            response = requests.get(
                url, 
                headers=headers, 
                timeout=settings['timeout_seconds']
            )
            
            # 2. ПРОВЕРКА HTTP СТАТУСА
            response.raise_for_status() # Выкинет ошибку, если статус 4xx или 5xx

            # 3. ПАРСИНГ JSON
            data = response.json()
            # products = data.get('data', {}).get('products', [])
            products = data.get('data', {}).get('products') or data.get('products') or []

            if not products:
                print(f"[DATA] Товар {article} не найден в ответе API.")
                continue

            product_obj = products[0]
            
            # 4. ПОИСК ЦЕНЫ
            price_data = _find_price_block(product_obj)
            
            if not price_data:
                print(f"[DATA] Не найдена цена для {article} (структура изменилась?)")
                continue

            # 5. РАСЧЕТЫ
            divider = settings['price_divider']
            p_val = price_data.get('product', 0) / divider
            l_val = price_data.get('logistics', 0) / divider
            r_val = price_data.get('return', 0) / divider
            total = p_val + l_val + r_val

            currency = settings['currency'].upper()

            # Вывод в консоль
            print(f"✅ {name} ({article}) -> {total:.2f} {currency}")
            
            # 6. СОХРАНЕНИЕ В CSV
            save_to_csv({
                'id': article,
                'name': name,
                'product': p_val,
                'logistics': l_val,
                'return': r_val,
                'total': total
            })

            # Проверка цели
            if item.get('target_price') and round(total, 2) <= item['target_price']: 
                print(f"   🔥 ВНИМАНИЕ! Цена ниже {item['target_price']}!")

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "NO_STATUS"
            print(f"[HTTP {status}] Ошибка для {article}: {e}")

            
        except requests.exceptions.ConnectionError:
            # Нет интернета или DNS
            print(f"[NETWORK] Ошибка подключения для {article}.")
            
        except requests.exceptions.Timeout:
            # Сервер думал дольше timeout_seconds
            print(f"[NETWORK] Таймаут ({settings['timeout_seconds']}с) для {article}.")
            
        except json.JSONDecodeError:
            # Вернулся HTML или мусор вместо JSON
            print(f"[PARSE] Сервер вернул не JSON для {article}.")
            
        except Exception as e:
            # Всё остальное
            print(f"[UNKNOWN] Неизвестная ошибка с {article}: {e}")

        # Пауза между товарами
        time.sleep(settings['sleep_seconds'])

if __name__ == "__main__":
    init_csv() # Создаем файл, если нет
    cfg = load_config()
    process_items(cfg)