import time
from datetime import datetime

# Импортируем наши новые модули из папки app
from app.config import load_config
from app.storage import init_csv, save_price
from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.notify import send_telegram

def process_items(config):
    settings = config['settings']
    items = config['items']
    currency = settings['currency'].upper()
    
    print(f"--- Запуск проверки ({datetime.now().strftime('%H:%M:%S')}) ---")

    for item in items:
        article = item['id']
        name = item['name']
        
        # 1. Получаем сырые данные (сеть)
        json_data = get_product_data(article, settings)
        if not json_data:
            continue

        # 2. Вытаскиваем цены (логика)
        price_info = parse_card_data(json_data, settings['price_divider'])
        if not price_info:
            print(f"[DATA] Не найдена цена для {article}")
            continue
            
        total = price_info['total']

        # 3. Вывод и сохранение (хранилище)
        print(f"✅ {name} ({article}) -> {total:.2f} {currency}")
        save_price(article, name, price_info)

        # 4. Проверка цели и уведомление (уведомления)
        target = item.get('target_price')
        if target and round(total, 2) <= target:
            print(f"   🔥 ВНИМАНИЕ! Цена ниже {target}!")
            msg = (
                f"🔥 <b>Цена упала!</b>\n"
                f"Товар: {name}\n"
                f"Текущая: <b>{total:.2f} {currency}</b>\n"
                f"Цель: {target} {currency}\n"
                f"<a href='https://www.wildberries.by/catalog/{article}/detail.aspx'>Ссылка на товар</a>"
            )
            send_telegram(msg, config)

        time.sleep(settings['sleep_seconds'])

if __name__ == "__main__":
    init_csv() # Создаст папку data и файл, если нет
    cfg = load_config()
    process_items(cfg)