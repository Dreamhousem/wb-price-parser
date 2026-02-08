import json
import os
import logging

SUBS_FILE = 'data/subscriptions.json'
STATE_FILE = 'data/state.json'

logger = logging.getLogger(__name__)

def _load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения {filepath}: {e}")
        return default

def _save_json(filepath, data):
    os.makedirs('data', exist_ok=True)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка записи {filepath}: {e}")

# --- Публичные методы ---

def get_subscriptions():
    """Возвращает список товаров"""
    return _load_json(SUBS_FILE, [])

def add_subscription(item):
    """item = {'id': 123, 'target': 500, 'name': '...'}"""
    subs = get_subscriptions()
    # Проверка на дубликаты
    for sub in subs:
        if sub['id'] == item['id']:
            sub['target'] = item['target'] # Обновляем цель
            _save_json(SUBS_FILE, subs)
            return
    subs.append(item)
    _save_json(SUBS_FILE, subs)

def remove_subscription(product_id):
    subs = get_subscriptions()
    subs = [s for s in subs if str(s['id']) != str(product_id)]
    _save_json(SUBS_FILE, subs)
    # Также нужно чистить стейт, но это опционально для MVP

def get_state():
    return _load_json(STATE_FILE, {})

def update_state(product_id, state_data):
    """Обновляет in_alert и цены для конкретного товара"""
    current_state = get_state()
    current_state[str(product_id)] = state_data
    _save_json(STATE_FILE, current_state)