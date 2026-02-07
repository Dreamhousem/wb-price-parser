import requests

def get_product_data(article, settings):
    """Делает запрос к API WB и возвращает JSON или None"""
    url = (
        f"https://card.wb.ru/cards/v4/detail?"
        f"appType=1&"
        f"curr={settings['currency']}&"
        f"dest={settings['dest']}&"
        f"spp={settings['spp']}&"
        f"nm={article}"
    )
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    try:
        response = requests.get(url, headers=headers, timeout=settings['timeout_seconds'])
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[NETWORK] Ошибка запроса для {article}: {e}")
        return None
    except Exception as e:
        print(f"[UNKNOWN] Ошибка с {article}: {e}")
        return None