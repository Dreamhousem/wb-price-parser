import logging
from datetime import datetime

from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.storage import (
    get_subscriptions,
    get_state_item,
    update_state,
    save_price_to_csv,
)

logger = logging.getLogger(__name__)


async def check_prices_job(bot, config):
    """
    Плановая проверка (вызывается scheduler'ом раз в N минут).

    Делает 3 вещи по каждому товару:
    1) История: пишет строку в prices.csv (всегда, если цена получена)
    2) Кэш: обновляет state.json (last_price/last_check_time) для /list
    3) Алерты: антиспам-уведомления по target_price (in_alert)
    """
    logger.info("=== Запуск плановой проверки цен ===")

    settings = config.get("settings", {})
    currency = str(settings.get("currency", "byn")).upper()
    chat_id = settings.get("tg_chat_id")

    if not chat_id:
        logger.error("tg_chat_id не задан. Проверь .env / config loader.")
        return

    subs = get_subscriptions()
    if not subs:
        logger.info("Подписок нет — проверять нечего.")
        return

    for item in subs:
        product_id = str(item.get("id"))
        target_price = item.get("target")
        item_name = item.get("name", "Товар WB")

        if not product_id:
            logger.warning("Пропускаю подписку без id: %s", item)
            continue

        try:
            # 1) Запрос к WB API
            data = await get_product_data(product_id, settings)
            if not data:
                logger.warning("WB API вернул пусто/ошибку: id=%s", product_id)
                continue

            # 2) Парсинг цены
            price_info = parse_card_data(data, settings.get("price_divider", 100))
            if not price_info:
                logger.warning("Не удалось извлечь цену: id=%s", product_id)
                continue

            current_price = float(price_info["total"])

            # --- [1] ИСТОРИЯ: CSV (для аналитики) ---
            # Важно: пишем всегда, если цену получили
            save_price_to_csv(
                item_id=product_id,
                item_name=item_name,
                price_dict=price_info,
                target_price=target_price,
            )

            # --- [2] КЭШ: state.json (для /list) ---
            update_state(product_id, {
                "last_price": current_price,
                "last_check_time": datetime.now().isoformat(),
            })

            # --- [3] АЛЕРТЫ: антиспам ---
            item_state = get_state_item(product_id)
            is_in_alert = bool(item_state.get("in_alert", False))

            # target_price может быть строкой/None — приведем аккуратно
            try:
                target_val = float(target_price) if target_price is not None else None
            except Exception:
                target_val = None

            if target_val is None:
                # Если цели нет — алерты не шлём, но историю и кэш ведём
                logger.info("Цель не задана: id=%s (история/кэш обновлены)", product_id)
                continue

            if current_price <= target_val:
                if not is_in_alert:
                    msg = (
                        f"🎯 <b>ЦЕНА НИЖЕ ЦЕЛИ!</b>\n\n"
                        f"📦 {item_name}\n"
                        f"🆔 <code>{product_id}</code>\n"
                        f"💰 <b>{current_price:.2f} {currency}</b>\n"
                        f"🎯 Цель: {target_val:.2f} {currency}\n"
                        f"🔗 <a href='https://www.wildberries.by/catalog/{product_id}/detail.aspx'>Купить</a>"
                    )
                    try:
                        await bot.send_message(chat_id, msg, parse_mode="HTML")
                        update_state(product_id, {"in_alert": True})
                        logger.info("Алерт отправлен: id=%s price=%.2f target=%.2f", product_id, current_price, target_val)
                    except Exception as e:
                        logger.error("Ошибка отправки TG (id=%s): %s", product_id, e)
                else:
                    logger.debug("Уже в алерте, не спамлю: id=%s", product_id)
            else:
                # Цена вернулась выше цели — сбрасываем флаг, чтобы следующее падение прислало алерт
                if is_in_alert:
                    update_state(product_id, {"in_alert": False})
                    logger.info("Сброс in_alert (цена выше цели): id=%s price=%.2f target=%.2f", product_id, current_price, target_val)

        except Exception as e:
            # Гарантия: один проблемный товар не валит всю задачу
            logger.exception("Неожиданная ошибка при проверке id=%s: %s", product_id, e)

    logger.info("=== Плановая проверка завершена ===")
