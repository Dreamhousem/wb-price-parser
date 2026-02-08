import aiohttp
import logging

logger = logging.getLogger(__name__)

async def get_product_data(article, settings):
    """Асинхронный запрос к API WB"""
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
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=settings['timeout_seconds']) as response:
                response.raise_for_status()
                return await response.json()
    except Exception as e:
        logger.error(f"Ошибка API WB для {article}: {e}")
        return None