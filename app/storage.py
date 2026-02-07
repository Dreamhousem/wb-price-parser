import csv
import os
from datetime import datetime

CSV_FILE = 'data/prices.csv' # Обрати внимание: теперь в папке data

def init_csv():
    """Создает папку data и файл CSV, если их нет"""
    os.makedirs('data', exist_ok=True)
    
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['timestamp', 'id', 'name', 'product_price', 'logistics', 'return', 'total_price'])

def save_price(item_id, item_name, price_dict):
    """Дописывает строку в CSV"""
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            item_id,
            item_name,
            f"{price_dict['product']:.2f}".replace('.', ','),
            f"{price_dict['logistics']:.2f}".replace('.', ','),
            f"{price_dict['return']:.2f}".replace('.', ','),
            f"{price_dict['total']:.2f}".replace('.', ',')
        ])