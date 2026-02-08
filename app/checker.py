import os
import logging
from datetime import datetime

from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.storage import get_subscriptions, get_state_item, update_state

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    # MVP: локальное время, главное чтобы парсер /list тоже понимал fromisoformat()
    return datetime.now().isoformat(timespec="seconds")


async def check_prices_job(bot, config):
    """
    Функция, которую вызывает планировщик.
    Критически важно: всегда обновляет last_price/last_check_time,
    чтобы /list мог показывать актуальные цены без доп. запросов.
    """
    logger.info("=== Плановая проверка цен: START ===")

    settings = config["settings"]
    currency = settings["currency"].upper()

    # Пока single-user: отправляем владельцу
    chat_id = settings.get("tg_chat_id") or os.getenv("ADMIN_USER_ID")
    if not chat_id:
        logger.warning("TG chat_id не задан (settings.tg_chat_id / ADMIN_USER_ID). Уведомления отключены.")

    subs = get_subscriptions()
    if not subs:
        logger.info("Нет подписок для проверки.")
        return

    for item in subs:
        product_id = str(item["id"])
        target_price = float(item["target"])
        item_name = item.get("name", "Товар")

        # 1) Запрос
        try:
            data = await get_product_data(product_id, settings)
        except Exception as e:
            logger.warning("Ошибка WB запроса для %s: %s", product_id, e)
            continue

        if not data:
            logger.warning("WB вернул пустой ответ/ошибку для %s", product_id)
            continue

        # 2) Парсинг
        try:
            price_info = parse_card_data(data, settings["price_divider"])
        except Exception as e:
            logger.error("Парсинг сломался для %s: %s", product_id, e)
            continue

        if not price_info:
            logger.warning("Не удалось извлечь цену для %s (возможно нет в наличии)", product_id)
            continue

        current_price = float(price_info["total"])

        # 3) Всегда обновляем кэш (для /list)
        update_state(product_id, {
            "last_price": round(current_price, 2),
            "last_check_time": _now_iso(),
        })

        logger.info("Цена: %s (%s) = %.2f %s (цель %.2f)",
                    item_name, product_id, current_price, currency, target_price)

        # 4) Антиспам: in_alert
        item_state = get_state_item(product_id)
        is_in_alert = bool(item_state.get("in_alert", False))

        if current_price <= target_price:
            if not is_in_alert and chat_id:
                msg = (
                    f"🎯 <b>ЦЕНА НИЖЕ ЦЕЛИ!</b>\n\n"
                    f"📦 {item_name}\n"
                    f"🆔 <code>{product_id}</code>\n"
                    f"💰 <b>{current_price:.2f} {currency}</b>\n"
                    f"🎯 Цель: {target_price:.2f} {currency}\n"
                    f"🔗 <a href='https://www.wildberries.by/catalog/{product_id}/detail.aspx'>Открыть товар</a>"
                )
                try:
                    await bot.send_message(chat_id, msg, parse_mode="HTML", disable_web_page_preview=True)
                    update_state(product_id, {"in_alert": True})
                    logger.info("Уведомление отправлено (in_alert=True): %s", product_id)
                except Exception as e:
                    logger.error("Ошибка отправки TG для %s: %s", product_id, e)
        else:
            # Цена выше цели — снимаем флаг, чтобы при следующем падении снова алертить
            if is_in_alert:
                update_state(product_id, {"in_alert": False})
                logger.info("Сброс in_alert=False: %s", product_id)

    logger.info("=== Плановая проверка цен: END ===")
