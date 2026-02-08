import os
import logging
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.storage import (
    add_subscription,
    get_subscriptions,
    remove_subscription,
    update_state,
    get_state_item,
)

logger = logging.getLogger(__name__)

router = Router()
BOT_CONFIG = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def register_handlers(dp, config):
    global BOT_CONFIG
    BOT_CONFIG = config
    dp.include_router(router)
    logger.info("Handlers зарегистрированы.")


# --- Middleware: admin-only (опционально) ---
@router.message.outer_middleware
async def admin_check_middleware(handler, event, data):
    """
    Если задан ADMIN_USER_ID — пускаем только его.
    Если не задан — бот публичный (пускаем всех).
    """
    admin_id = os.getenv("ADMIN_USER_ID")
    if not admin_id:
        return await handler(event, data)

    try:
        allowed = int(admin_id)
    except ValueError:
        logger.warning("ADMIN_USER_ID задан неверно: %s", admin_id)
        return await handler(event, data)

    user_id = getattr(getattr(event, "from_user", None), "id", None)
    if user_id == allowed:
        return await handler(event, data)

    # молча игнорируем (или можно ответить "нет доступа")
    return


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>Привет! Я бот для мониторинга цен Wildberries.</b>\n\n"
        "<b>Команды:</b>\n"
        "/add <code>артикул</code> <code>цель</code> — добавить товар\n"
        "/list — список подписок (с актуальной ценой)\n"
        "/del <code>артикул</code> — удалить товар\n"
        "/status — статус бота\n\n"
        "<i>Пример:</i> <code>/add 172638392 50.00</code>",
        parse_mode="HTML"
    )


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject):
    args = command.args
    if not args:
        await message.answer("⚠️ Формат: <code>/add артикул цена</code>", parse_mode="HTML")
        return

    try:
        parts = args.split()
        if len(parts) != 2:
            raise ValueError("Неверное число аргументов")

        article = parts[0].strip()
        target_price = float(parts[1].replace(",", "."))

        if not article.isdigit() or target_price <= 0:
            raise ValueError("Неверные значения")

        wait_msg = await message.answer(f"🔍 Ищу товар <code>{article}</code>...", parse_mode="HTML")

        settings = BOT_CONFIG["settings"]

        # 1) запрос
        data = await get_product_data(article, settings)
        if not data:
            await wait_msg.edit_text("❌ Товар не найден на WB или ошибка API.")
            return

        # 2) парс цены (валидация наличия)
        price_info = parse_card_data(data, settings["price_divider"])
        if not price_info:
            await wait_msg.edit_text("❌ Не удалось получить цену (возможно нет в наличии).")
            return

        # 3) имя товара (берём products[0].name — это “правильный” name)
        products = (data.get("data") or {}).get("products") or data.get("products") or []
        product_name = "Товар WB"
        if products and isinstance(products, list):
            product_name = products[0].get("name") or product_name

        current_price = float(price_info["total"])
        currency = settings["currency"].upper()

        # 4) сохраняем подписку
        add_subscription({
            "id": article,
            "target": target_price,
            "name": product_name,
        })

        # 5) заполняем кэш, чтобы /list сразу показал цену
        update_state(article, {
            "in_alert": False,
            "last_price": round(current_price, 2),
            "last_check_time": _now_iso(),
        })

        logger.info("ADD: user=%s article=%s target=%.2f", message.from_user.id, article, target_price)

        await wait_msg.edit_text(
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📦 {product_name}\n"
            f"🆔 <code>{article}</code>\n"
            f"💰 Текущая цена: <b>{current_price:.2f} {currency}</b>\n"
            f"🎯 Цель: <b>{target_price:.2f} {currency}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception("Ошибка /add: %s", e)
        await message.answer("⚠️ Ошибка. Пример: <code>/add 123456 50.5</code>", parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(message: Message):
    subs = get_subscriptions()
    if not subs:
        await message.answer("📭 Список отслеживания пуст.")
        return

    status_msg = await message.answer("⏳ Проверяю актуальность цен...")

    settings = BOT_CONFIG["settings"]
    currency = settings["currency"].upper()

    ttl_minutes = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
    ttl = timedelta(minutes=ttl_minutes)

    report_lines = []
    items_to_update = []

    now = datetime.now()

    # 1) Сначала строим список на основе кэша
    for item in subs:
        product_id = str(item["id"])
        state = get_state_item(product_id)

        last_price = state.get("last_price")
        last_check_str = state.get("last_check_time")
        last_check_dt = _parse_iso(last_check_str)

        is_stale = True
        if last_check_dt:
            try:
                if (now - last_check_dt) < ttl:
                    is_stale = False
            except Exception:
                is_stale = True

        if is_stale:
            items_to_update.append(product_id)
            price_display = "⏳ <i>обновляю...</i>"
        else:
            price_display = f"<b>{float(last_price):.2f} {currency}</b>" if last_price is not None else "—"

        report_lines.append({
            "name": item.get("name", "Товар"),
            "id": product_id,
            "target": float(item["target"]),
            "price_display": price_display,
        })

    # 2) Обновляем устаревшие (последовательно для MVP)
    if items_to_update:
        logger.info("/list: нужно обновить %d товаров", len(items_to_update))
        for line in report_lines:
            pid = line["id"]
            if pid not in items_to_update:
                continue

            new_price = None
            try:
                data = await get_product_data(pid, settings)
                if data:
                    p_info = parse_card_data(data, settings["price_divider"])
                    if p_info:
                        new_price = float(p_info["total"])
            except Exception as e:
                logger.warning("/list: ошибка обновления %s: %s", pid, e)

            if new_price is not None:
                update_state(pid, {
                    "last_price": round(new_price, 2),
                    "last_check_time": _now_iso(),
                })
                line["price_display"] = f"<b>{new_price:.2f} {currency}</b>"
            else:
                # если есть старый кэш — покажем его как “устар.”
                st = get_state_item(pid)
                old = st.get("last_price")
                if old is not None:
                    line["price_display"] = f"<b>{float(old):.2f} {currency}</b> <i>(устар.)</i>"
                else:
                    line["price_display"] = "⚠️ <i>ошибка</i>"

    # 3) Финальный вывод
    text = "📋 <b>Твои подписки:</b>\n\n"
    for line in report_lines:
        text += (
            f"🔹 <b>{line['name']}</b>\n"
            f"ID: <code>{line['id']}</code>\n"
            f"Цена: {line['price_display']}\n"
            f"Цель: {line['target']:.2f} {currency}\n\n"
        )

    await status_msg.edit_text(text, parse_mode="HTML")
    logger.info("/list: ответ сформирован (items=%d)", len(report_lines))


@router.message(Command("del", "delete"))
async def cmd_del(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("⚠️ Укажите артикул: <code>/del 123456</code>", parse_mode="HTML")
        return

    article = command.args.strip()
    remove_subscription(article)

    # (опционально) можно и state прибрать, но я бы пока оставил — не критично.
    logger.info("DEL: user=%s article=%s", message.from_user.id, article)

    await message.answer(f"🗑 Товар <code>{article}</code> удален из отслеживания.", parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    settings = BOT_CONFIG["settings"]
    ttl = os.getenv("CHECK_INTERVAL_MINUTES", "10")
    admin_id = os.getenv("ADMIN_USER_ID")

    subs = get_subscriptions()

    await message.answer(
        "⚙️ <b>Статус:</b>\n"
        f"Подписок: <b>{len(subs)}</b>\n"
        f"Интервал проверки: <b>{ttl} мин</b>\n"
        f"Регион (dest): <b>{settings.get('dest')}</b>\n"
        f"Валюта: <b>{settings.get('currency')}</b>\n"
        f"Режим доступа: <b>{'admin-only' if admin_id else 'public'}</b>",
        parse_mode="HTML"
    )
