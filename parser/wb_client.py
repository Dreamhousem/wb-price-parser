from curl_cffi import requests
import logging

class WBClient:
    def __init__(self):
        # BYN params: curr=byn, dest=-59246 (Минск/РБ)
        self.base_url = "https://card.wb.ru/cards/v1/detail?appType=1&curr=byn&dest=-59246&spp=30&nm={sku}"
    
    def get_item_data(self, sku: str):
        url = self.base_url.format(sku=sku)
        try:
            # impersonate="chrome110" важен для обхода защиты
            response = requests.get(url, impersonate="chrome110", timeout=10)
            
            if response.status_code != 200:
                logging.error(f"WB API error: {response.status_code}")
                return None
            
            data = response.json()
            products = data.get('data', {}).get('products', [])
            
            if not products:
                logging.warning(f"Товар {sku} не найден (возможно, нет в наличии в РБ)")
                return None
                
            product = products[0]
            name = product.get('name', 'No Name')
            
            # ВАЖНО: WB отдает цену в "копейках" валюты запроса.
            # Если запросили curr=byn, то salePriceU придет в белорусских копейках.
            price_cents = product.get('salePriceU') or product.get('priceU') or 0
                
            return {
                'sku': sku,
                'name': name,
                'price_cents': int(price_cents),
                'available': True
            }

        except Exception as e:
            logging.error(f"Ошибка парсинга {sku}: {e}")
            return None