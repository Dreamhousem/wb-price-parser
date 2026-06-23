# parser/wb_client.py
import logging

from curl_cffi import requests

from config import WB_CURR, WB_DEST, WB_SPP

logger = logging.getLogger(__name__)


class WBClient:
    def __init__(self):
        # Это внутренний endpoint, который реально использует сайт wildberries.by
        self.base_url = "https://www.wildberries.by/__internal/u-card/cards/v4/detail"

    def get_item_data(self, sku: str):
        """
        Получает данные товара WB.by.

        Возвращает:
        {
            "sku": "756698415",
            "name": "Название товара",
            "price_cents": 6431,          # product + logistics
            "product_price_cents": 5787,  # цена товара
            "logistics_cents": 644,       # доставка/логистика
            "available": True
        }

        Или None, если товар не найден / ошибка запроса.
        """

        if not sku or not str(sku).isdigit():
            logger.warning(f"Invalid sku: {sku}")
            return None

        params = {
            "appType": "1",
            "curr": WB_CURR,          # byn
            "dest": WB_DEST,          # например -8139704
            "spp": WB_SPP,            # обычно 30
            "hide_vflags": "4294967296",
            "hide_dflags": "131072",
            "hide_dtype": "11;13;15",
            "mtype": "257",
            "lang": "ru",
            "ab_testing": "false",
            "nm": sku,
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                impersonate="chrome110",
                timeout=15,
            )

            if response.status_code != 200:
                logger.error(
                    f"WB API error: {response.status_code}, "
                    f"url={response.url}, "
                    f"body={response.text[:300]}"
                )
                return None

            data = response.json()

            products = data.get("products", [])
            if not products:
                logger.warning(f"Product not found: sku={sku}, url={response.url}")
                return None

            product = products[0]
            name = product.get("name") or "No Name"

            sizes = product.get("sizes", [])
            if not sizes:
                logger.warning(f"No sizes found for sku={sku}")
                return None

            # Берём первый размер/вариант, где есть цена.
            # Для товаров без размеров обычно всё равно есть один size.
            selected_size = None
            for size in sizes:
                price = size.get("price")
                if price:
                    selected_size = size
                    break

            if not selected_size:
                logger.warning(f"No price data found for sku={sku}")
                return None

            price_data = selected_size.get("price", {})

            product_price_cents = int(price_data.get("product") or 0)
            logistics_cents = int(price_data.get("logistics") or 0)

            # Цена, которую считаем целевой для мониторинга:
            # товар + логистика/доставка
            total_price_cents = product_price_cents + logistics_cents

            if total_price_cents <= 0:
                logger.warning(
                    f"Total price is empty for sku={sku}, price_data={price_data}"
                )
                return None

            total_quantity = int(product.get("totalQuantity") or 0)
            available = total_quantity > 0

            return {
                "sku": str(sku),
                "name": name,
                "price_cents": total_price_cents,
                "product_price_cents": product_price_cents,
                "logistics_cents": logistics_cents,
                "available": available,
            }

        except Exception as e:
            logger.exception(f"Error parsing sku={sku}: {e}")
            return None