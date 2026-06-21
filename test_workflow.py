# test_workflow.py
import logging
from database.db_manager import Database
from parser.wb_client import WBClient

# Настройка простейшего логгера
logging.basicConfig(level=logging.INFO)

def run_test():
    # 1. Инициализация
    print("--- 1. Init DB ---")
    db = Database("data/test.db") # Используем тестовую БД
    client = WBClient()

    # 2. Добавление товара
    sku = "175789238" # Какой-то реальный товар
    target_rub = 500
    target_cents = target_rub * 100
    
    print(f"--- 2. Adding Item {sku} with target {target_rub} RUB ---")
    # Имя пока прочерк, парсер его обновит (в идеале, но пока мы передаем при создании)
    # В реальном коде мы сначала парсим, потом добавляем. Сделаем эмуляцию:
    item_data = client.get_item_data(sku)
    
    if not item_data:
        print("❌ Ошибка: Парсер не нашел товар, тест остановлен.")
        return

    db.add_item(sku, item_data['name'], target_cents)
    
    # Проверяем, что записалось
    item_in_db = db.get_item(sku)
    print(f"✅ Item in DB: ID={item_in_db['id']}, Name={item_in_db['name']}")

    # 3. Логирование цены (Эмуляция работы Checker'а)
    print(f"--- 3. Logging Price: {item_data['price_cents']} cents ---")
    db.log_price(item_in_db['id'], item_data['price_cents'])

    # 4. Проверка истории
    print("--- 4. Checking History ---")
    # Тут можно добавить метод get_history в db_manager, но пока проверим raw sql
    with db._connect() as conn:
        cursor = conn.execute("SELECT * FROM price_history WHERE item_id = ?", (item_in_db['id'],))
        history = cursor.fetchall()
        for row in history:
            print(f"   📜 History Record: Price={row['price_cents']} cents, Time={row['checked_at']}")

    # 5. Логика уведомления
    print("--- 5. Notification Logic ---")
    current_price = item_data['price_cents']
    target = item_in_db['target_price_cents']
    
    if current_price <= target:
        print(f"🔥 ALARM! Цена {current_price/100} <= Цели {target/100}")
        db.mark_notified(item_in_db['id'])
        print("   ✅ Mark notified called")
    else:
        print(f"❄️ Цена {current_price/100} выше цели {target/100}. Ждем.")

    print("\n🎉 TEST COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    run_test()