import requests

def send_telegram(message, config):
    settings = config['settings']
    token = settings.get('tg_token')
    chat_id = settings.get('tg_chat_id')

    if not token or not chat_id:
        print("[SYSTEM] Телеграм не настроен (проверь .env)")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM] Сбой отправки: {e}")