import json
import os
from dotenv import load_dotenv

# Загружаем переменные из .env в память
load_dotenv()

CONFIG_FILE = 'config.json'

def load_config():
    """Загружает JSON и добавляет секреты из ENV"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Подмешиваем секреты из переменных окружения
        # Если в .env есть TG_TOKEN, он попадет в settings
        config['settings']['tg_token'] = os.getenv('TG_BOT_TOKEN')
        config['settings']['tg_chat_id'] = os.getenv('TG_CHAT_ID')
        
        return config
    except FileNotFoundError:
        print(f"[SYSTEM] Ошибка: Файл {CONFIG_FILE} не найден.")
        exit(1)
    except json.JSONDecodeError:
        print(f"[SYSTEM] Ошибка: {CONFIG_FILE} битый.")
        exit(1)