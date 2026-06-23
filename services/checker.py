# services/checker.py
import logging
import asyncio
from database.db_manager import Database
from parser.wb_client import WBClient
from config import ADMIN_ID

logger = logging.getLogger(__name__)


def _fetch_price(client: WBClient, sku: str):
    """Синхронная обёртка для запуска в отдельном потоке."""
    return client.get_item_data(sku)


async def _check_single_item(bot, db: Database, client: WBClient, item: dict):
    """
    Проверяет один товар. Изолирована, чтобы ошибка одного товара
    не ломала цикл остальных.
    """
    sku = item['sku']

    # FIX 1: WBClient синхронный — запускаем в отдельном потоке,
    # чтобы не блокировать event loop бота.
    try:
        item_data = await asyncio.to_thread(_fetch_price, client, sku)
    except Exception as e:
        logger.error(f"[{sku}] Ошибка запроса к WB: {e}")
        return

    if not item_data:
        logger.warning(f"[{sku}] WB вернул пустой ответ — пропускаем.")
        return

    current_price_cents = item_data.get('price_cents', 0)

    # FIX 2: Защита от цены 0 / None / отрицательной.
    # Такое бывает при глюках WB API — не считаем это реальной ценой.
    if not current_price_cents or current_price_cents <= 0:
        logger.warning(
            f"[{sku}] Получена подозрительная цена: {current_price_cents!r} — пропускаем, алерт не шлём."
        )
        return

    target_price_cents = item['target_price_cents']
    is_in_alert = bool(item['is_in_alert'])

    # 3. Пишем в историю (всегда, если цена валидная)
    db.log_price(item['id'], current_price_cents)

    price_byn = current_price_cents / 100
    target_byn = target_price_cents / 100
    logger.info(f"[{sku}] {price_byn:.2f} BYN (цель: {target_byn:.2f}, alert={is_in_alert})")

    # 4. State Machine уведомлений
    if current_price_cents <= target_price_cents:
        if not is_in_alert:
            # ВХОД В АЛЕРТ → шлём уведомление
            msg = (
                f"🇧🇾 <b>ЦЕЛЕВАЯ ЦЕНА (BYN)!</b>\n\n"
                f"📦 {item['name']}\n"
                f"🆔 <code>{sku}</code>\n"
                f"💰 <b>{price_byn:.2f} BYN</b> (Цель: {target_byn:.2f})\n\n"
                f"🔗 <a href='https://www.wildberries.by/catalog/{sku}/detail.aspx'>Открыть на WB</a>"
            )
            try:
                await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
                db.set_alert_status(item['id'], True)
                db.mark_notified(item['id'])
                logger.info(f"[{sku}] ✅ Уведомление отправлено.")
            except Exception as e:
                logger.error(f"[{sku}] Ошибка отправки в Telegram: {e}")
        else:
            logger.info(f"[{sku}] Цена низкая, но алерт уже активен — молчим (Anti-Spam).")

    else:
        if is_in_alert:
            # ВЫХОД ИЗ АЛЕРТА → сбрасываем флаг
            db.set_alert_status(item['id'], False)
            logger.info(f"[{sku}] Цена вернулась выше цели — алерт сброшен.")


async def check_prices(bot):
    """
    Главная функция проверки. Запускается из scheduler (main.py)
    и вручную через /check.
    """
    db = Database()
    client = WBClient()

    items = db.get_active_items()
    if not items:
        logger.info("Нет активных товаров для проверки.")
        return

    logger.info(f"▶ Проверка {len(items)} товар(ов) (Region: BY)...")

    # FIX 3: каждый товар проверяется независимо —
    # исключение в одном не остановит остальные.
    for item in items:
        try:
            await _check_single_item(bot, db, client, item)
        except Exception as e:
            logger.error(f"[{item['sku']}] Неожиданная ошибка: {e}", exc_info=True)

    logger.info("✅ Проверка завершена.")