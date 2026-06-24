# bot/handlers.py
import asyncio
import html
import logging

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db_manager import Database
from parser.wb_client import WBClient
from config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()


# ─── FSM ────────────────────────────────────────────────────────────────────

class AddItem(StatesGroup):
    waiting_for_sku = State()
    waiting_for_price = State()


# ─── Helpers ────────────────────────────────────────────────────────────────

def is_admin_message(message: Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID


def is_admin_callback(callback: CallbackQuery) -> bool:
    return callback.from_user and callback.from_user.id == ADMIN_ID


def product_url(sku: str) -> str:
    return f"https://www.wildberries.by/catalog/{sku}/detail.aspx"


def product_link(sku: str) -> str:
    return f"<a href='{product_url(sku)}'>ссылка</a>"


def safe_text(value, default: str = "—") -> str:
    if value is None:
        return default
    return html.escape(str(value))


def short_name(name, limit: int = 35) -> str:
    name = name or "Без названия"
    name = str(name)

    if len(name) > limit:
        name = name[:limit - 1] + "…"

    return html.escape(name)


def format_byn(cents) -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:.2f}"


def parse_price_to_cents(text: str) -> int | None:
    text = text.strip().replace(",", ".")

    try:
        price_byn = float(text)
        if price_byn <= 0:
            return None
        return int(round(price_byn * 100))
    except ValueError:
        return None


def target_line(current_price_cents: int, target_price_cents: int) -> str:
    if current_price_cents <= target_price_cents:
        return f"🎯 Цель достигнута: <b>{format_byn(target_price_cents)} BYN</b>"

    return f"🔽 Цель: <b>{format_byn(target_price_cents)} BYN</b>"


def build_items_keyboard(items: list[dict]) -> InlineKeyboardMarkup | None:
    if not items:
        return None

    keyboard = []

    for item in items:
        sku = str(item["sku"])

        if item["status"] == "active":
            toggle_text = f"⏸ {sku}"
        else:
            toggle_text = f"▶️ {sku}"

        keyboard.append([
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=f"toggle:{sku}",
            ),
            InlineKeyboardButton(
                text=f"🗑 {sku}",
                callback_data=f"delete:{sku}",
            ),
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_items_text(items: list[dict]) -> str:
    if not items:
        return "📭 Список пуст. Добавь товар через /add"

    lines = [f"📋 <b>Товары ({len(items)}):</b>"]

    for item in items:
        sku = str(item["sku"])

        status_icon = "▶️" if item["status"] == "active" else "⏸"
        alert_icon = "🔔" if item.get("is_in_alert") else ""

        current = format_byn(item.get("last_price_cents"))
        target = format_byn(item.get("target_price_cents"))

        lines.append(
            f"\n{status_icon} {alert_icon} <b>{short_name(item.get('name'))}</b>\n"
            f"   🆔 <code>{html.escape(sku)}</code> ({product_link(sku)})\n"
            f"   💰 {current} / 🎯 {target} BYN"
        )

    return "\n".join(lines)


async def send_items_list(message: Message):
    db = Database()
    items = db.list_items()

    text = build_items_text(items)
    keyboard = build_items_keyboard(items)

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def edit_items_list(message: Message):
    db = Database()
    items = db.list_items()

    text = build_items_text(items)
    keyboard = build_items_keyboard(items)

    await message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def add_item_by_sku_and_price(
    message: Message,
    sku: str,
    price_text: str,
    state: FSMContext | None = None,
    item_data: dict | None = None,
):
    """
    Общая функция добавления товара.

    Используется в двух режимах:

    1. Быстрый режим:
       /add 846796617 6
       item_data отсутствует → идём на WB.

    2. Диалоговый режим:
       /add → ввёл SKU → бот уже нашёл товар → ввёл цену
       item_data уже есть из state → повторно на WB НЕ идём.
    """
    sku = sku.strip()

    if not sku.isdigit():
        await message.answer("❌ Артикул должен состоять только из цифр.")

        if state:
            await state.clear()

        return

    target_price_cents = parse_price_to_cents(price_text)

    if target_price_cents is None:
        await message.answer(
            "❌ Некорректная целевая цена.\n"
            "Пример: <code>/add 846796617 6</code>",
            parse_mode="HTML",
        )
        return

    msg = None

    # Если item_data не передали — это быстрый режим /add sku price.
    # Значит нужно сходить на WB.
    if item_data is None:
        msg = await message.answer(
            f"🔍 Ищу товар <code>{sku}</code> на WB.by...",
            parse_mode="HTML",
        )

        client = WBClient()

        # WBClient синхронный, поэтому уводим запрос в отдельный поток,
        # чтобы не подвешивать Telegram-бота.
        item_data = await asyncio.to_thread(client.get_item_data, sku)

        if not item_data:
            await msg.edit_text(
                f"❌ Товар <code>{sku}</code> не найден на WB.by\n"
                "Проверь артикул и попробуй снова.",
                parse_mode="HTML",
            )

            if state:
                await state.clear()

            return

    current_price_cents = item_data["price_cents"]
    name = item_data["name"]

    db = Database()
    db.add_item(
        sku=sku,
        name=name,
        target_price_cents=target_price_cents,
    )

    # Раз мы уже получили цену при добавлении, сразу сохраняем её в историю
    # и обновляем last_price_cents.
    item = db.get_item(sku)

    if item and current_price_cents > 0:
        db.log_price(
            item_id=item["id"],
            price_cents=current_price_cents,
        )

    result_text = (
        f"✅ <b>Товар добавлен!</b>\n\n"
        f"📦 {safe_text(name)}\n"
        f"🆔 <code>{sku}</code> ({product_link(sku)})\n"
        f"💰 Сейчас: <b>{format_byn(current_price_cents)} BYN</b>\n"
        f"{target_line(current_price_cents, target_price_cents)}"
    )

    # В быстром режиме есть сообщение "Ищу товар..." — редактируем его.
    # В диалоговом режиме такого сообщения на этом шаге нет — отправляем новое.
    if msg:
        await msg.edit_text(result_text, parse_mode="HTML")
    else:
        await message.answer(result_text, parse_mode="HTML")

    if state:
        await state.clear()


def toggle_item_status(db: Database, sku: str) -> tuple[bool, str, str]:
    """
    Переключает active ↔ paused.

    Возвращает:
        success, new_status, item_name
    """
    item = db.get_item(sku)

    if not item:
        return False, "", ""

    if item["status"] == "active":
        new_status = "paused"
    else:
        new_status = "active"

    db.set_status(sku, new_status)

    return True, new_status, item.get("name") or "Товар"


# ─── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin_message(message):
        return

    await message.answer(
        "👋 <b>WB Price Tracker (BY)</b>\n\n"
        "Я слежу за ценами WB.by и присылаю уведомление, "
        "когда цена товара становится меньше или равна целевой.\n\n"
        "Напиши /help, чтобы посмотреть команды.",
        parse_mode="HTML",
    )


# ─── /help ──────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin_message(message):
        return

    await message.answer(
        "ℹ️ <b>Команды WB Price Tracker</b>\n\n"

        "<b>Добавление товара</b>\n"
        "/add — добавить товар через диалог\n"
        "/add &lt;артикул&gt; &lt;цена&gt; — быстро добавить товар\n"
        "Пример: <code>/add 846796617 6</code>\n\n"

        "<b>Список и управление</b>\n"
        "/list — список товаров с кнопками управления\n"
        "/pause &lt;артикул&gt; — приостановить/возобновить отслеживание\n"
        "/delete &lt;артикул&gt; — удалить товар\n\n"

        "<b>Проверки и история</b>\n"
        "/check — проверить цены прямо сейчас\n"
        "/history &lt;артикул&gt; — последние 10 проверок товара\n\n"

        "<b>Подсказка</b>\n"
        "В /list рядом с каждым товаром есть кнопки:\n"
        "⏸ / ▶️ — переключить отслеживание\n"
        "🗑 — удалить товар",
        parse_mode="HTML",
    )


# ─── /add ───────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if not is_admin_message(message):
        return

    parts = message.text.split(maxsplit=2)

    # Быстрый режим:
    # /add 846796617 6
    if len(parts) == 3:
        sku = parts[1]
        price_text = parts[2]

        await add_item_by_sku_and_price(
            message=message,
            sku=sku,
            price_text=price_text,
            state=state,
        )
        return

    # Пользователь написал /add 846796617, но без цены
    if len(parts) == 2:
        await message.answer(
            "Ты указал артикул, но не указал целевую цену.\n\n"
            "Пример быстрого добавления:\n"
            "<code>/add 846796617 6</code>\n\n"
            "Или просто напиши /add и пройди добавление через диалог.",
            parse_mode="HTML",
        )
        return

    # Диалоговый режим
    await state.set_state(AddItem.waiting_for_sku)
    await message.answer("Введи артикул товара WB (только цифры):")


@router.message(AddItem.waiting_for_sku)
async def process_sku(message: Message, state: FSMContext):
    if not is_admin_message(message):
        return

    sku = message.text.strip()

    if not sku.isdigit():
        await message.answer("❌ Артикул должен состоять только из цифр. Попробуй ещё раз:")
        return

    msg = await message.answer(
        f"🔍 Ищу товар <code>{sku}</code> на WB.by...",
        parse_mode="HTML",
    )

    client = WBClient()
    item_data = await asyncio.to_thread(client.get_item_data, sku)

    if not item_data:
        await msg.edit_text(
            f"❌ Товар <code>{sku}</code> не найден на WB.by\n"
            "Проверь артикул и попробуй снова /add",
            parse_mode="HTML",
        )
        await state.clear()
        return

    await state.update_data(
        sku=sku,
        name=item_data["name"],
        current_price_cents=item_data["price_cents"],
    )

    current_byn = item_data["price_cents"] / 100

    await msg.edit_text(
        f"✅ Нашёл: <b>{safe_text(item_data['name'])}</b>\n"
        f"🆔 <code>{sku}</code> ({product_link(sku)})\n"
        f"💰 Текущая цена: <b>{current_byn:.2f} BYN</b>\n\n"
        "Введи целевую цену в BYN, например: <code>49.99</code>",
        parse_mode="HTML",
    )

    await state.set_state(AddItem.waiting_for_price)


@router.message(AddItem.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    if not is_admin_message(message):
        return

    data = await state.get_data()

    sku = data["sku"]
    price_text = message.text.strip()

    cached_item_data = {
        "sku": sku,
        "name": data["name"],
        "price_cents": data["current_price_cents"],
    }

    await add_item_by_sku_and_price(
        message=message,
        sku=sku,
        price_text=price_text,
        state=state,
        item_data=cached_item_data,
    )


# ─── /list ──────────────────────────────────────────────────────────────────

@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin_message(message):
        return

    await send_items_list(message)


# ─── /delete ────────────────────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: Message):
    if not is_admin_message(message):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "Использование: /delete &lt;артикул&gt;\n"
            "Например: <code>/delete 846796617</code>",
            parse_mode="HTML",
        )
        return

    sku = args[1].strip()

    db = Database()
    item = db.get_item(sku)

    if not item:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    db.delete_item(sku)

    await message.answer(
        f"🗑 Удалён: <b>{short_name(item.get('name'), limit=80)}</b>",
        parse_mode="HTML",
    )


# ─── /pause ─────────────────────────────────────────────────────────────────

@router.message(Command("pause"))
async def cmd_pause(message: Message):
    if not is_admin_message(message):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "Использование: /pause &lt;артикул&gt;\n"
            "Например: <code>/pause 846796617</code>",
            parse_mode="HTML",
        )
        return

    sku = args[1].strip()
    db = Database()

    success, new_status, item_name = toggle_item_status(db, sku)

    if not success:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    if new_status == "active":
        await message.answer(f"▶️ Возобновлён: <b>{safe_text(item_name)}</b>", parse_mode="HTML")
    else:
        await message.answer(f"⏸ Приостановлен: <b>{safe_text(item_name)}</b>", parse_mode="HTML")


# ─── /history ───────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message):
    if not is_admin_message(message):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "Использование: /history &lt;артикул&gt;\n"
            "Например: <code>/history 846796617</code>",
            parse_mode="HTML",
        )
        return

    sku = args[1].strip()

    db = Database()
    item = db.get_item(sku)

    if not item:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    history = db.get_history(item["id"], limit=10)

    if not history:
        await message.answer("📭 История пуста")
        return

    lines = [
        f"📈 <b>История цен: {short_name(item.get('name'), limit=60)}</b>",
        f"🆔 <code>{sku}</code> ({product_link(sku)})",
        "",
    ]

    for record in history:
        price = format_byn(record["price_cents"])
        lines.append(f"{record['checked_at']} → <b>{price} BYN</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── /check ─────────────────────────────────────────────────────────────────

@router.message(Command("check"))
async def cmd_check(message: Message):
    if not is_admin_message(message):
        return

    from services.checker import check_prices

    msg = await message.answer("🔄 Запускаю проверку...")
    await check_prices(message.bot)
    await msg.edit_text("✅ Проверка завершена. Смотри /list")


# ─── Inline buttons from /list ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("toggle:"))
async def callback_toggle_item(callback: CallbackQuery):
    if not is_admin_callback(callback):
        await callback.answer()
        return

    sku = callback.data.split(":", maxsplit=1)[1]

    db = Database()
    success, new_status, item_name = toggle_item_status(db, sku)

    if not success:
        await callback.answer("Товар не найден", show_alert=True)
        return

    if new_status == "active":
        await callback.answer("Отслеживание включено")
    else:
        await callback.answer("Отслеживание приостановлено")

    await edit_items_list(callback.message)


@router.callback_query(F.data.startswith("delete:"))
async def callback_delete_item(callback: CallbackQuery):
    if not is_admin_callback(callback):
        await callback.answer()
        return

    sku = callback.data.split(":", maxsplit=1)[1]

    db = Database()
    item = db.get_item(sku)

    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    db.delete_item(sku)

    await callback.answer("Товар удалён")
    await edit_items_list(callback.message)