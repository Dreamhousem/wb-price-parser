# handlers.py
import logging
from aiogram import Router, F
from aiogram.types import Message
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

# ─── Guards ─────────────────────────────────────────────────────────────────

def is_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_ID

# ─── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message):
        return

    await message.answer(
        "👋 <b>WB Price Tracker (BY)</b>\n\n"
        "Команды:\n"
        "/add — добавить товар\n"
        "/list — список товаров\n"
        "/delete — удалить товар\n"
        "/pause — приостановить/возобновить\n"
        "/history — история цен\n"
        "/check — проверить прямо сейчас",
        parse_mode="HTML"
    )

# ─── /add ────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if not is_admin(message):
        return

    await state.set_state(AddItem.waiting_for_sku)
    await message.answer("Введи артикул товара WB (только цифры):")

@router.message(AddItem.waiting_for_sku)
async def process_sku(message: Message, state: FSMContext):
    sku = message.text.strip()

    if not sku.isdigit():
        await message.answer("❌ Артикул должен состоять только из цифр. Попробуй ещё раз:")
        return

    # Проверяем товар через API
    msg = await message.answer(f"🔍 Ищу товар <code>{sku}</code>...", parse_mode="HTML")

    client = WBClient()
    item_data = client.get_item_data(sku)

    if not item_data:
        await msg.edit_text(
            f"❌ Товар <code>{sku}</code> не найден на WB.by\n"
            "Проверь артикул и попробуй снова /add",
            parse_mode="HTML"
        )
        await state.clear()
        return

    await state.update_data(sku=sku, name=item_data['name'], current_price=item_data['price_cents'])

    current_byn = item_data['price_cents'] / 100
    await msg.edit_text(
        f"✅ Нашёл: <b>{item_data['name']}</b>\n"
        f"💰 Текущая цена: <b>{current_byn:.2f} BYN</b>\n\n"
        "Введи целевую цену в BYN (например: <code>49.99</code>):",
        parse_mode="HTML"
    )
    await state.set_state(AddItem.waiting_for_price)

@router.message(AddItem.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")

    try:
        price_byn = float(text)
        if price_byn <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Некорректная цена. Введи число, например: <code>49.99</code>", parse_mode="HTML")
        return

    price_cents = int(round(price_byn * 100))
    data = await state.get_data()
    sku = data['sku']
    name = data['name']
    current_price = data['current_price']

    db = Database()
    db.add_item(sku=sku, name=name, target_price_cents=price_cents)

    current_byn = current_price / 100
    arrow = "🔽" if price_cents <= current_price else "🔼"

    await message.answer(
        f"✅ <b>Товар добавлен!</b>\n\n"
        f"📦 {name}\n"
        f"🆔 <code>{sku}</code>\n"
        f"💰 Сейчас: <b>{current_byn:.2f} BYN</b>\n"
        f"{arrow} Цель: <b>{price_byn:.2f} BYN</b>",
        parse_mode="HTML"
    )
    await state.clear()

# ─── /list ───────────────────────────────────────────────────────────────────

@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message):
        return

    db = Database()
    items = db.list_items()

    if not items:
        await message.answer("📭 Список пуст. Добавь товар через /add")
        return

    lines = []
    for item in items:
        status_icon = "▶️" if item['status'] == 'active' else "⏸"
        alert_icon = "🔔" if item['is_in_alert'] else ""
        current = f"{item['last_price_cents']/100:.2f}" if item['last_price_cents'] else "—"
        target = f"{item['target_price_cents']/100:.2f}"

        lines.append(
            f"{status_icon} {alert_icon} <b>{item['name'][:30]}</b>\n"
            f"   🆔 <code>{item['sku']}</code>\n"
            f"   💰 {current} / 🎯 {target} BYN"
        )

    await message.answer(
        f"📋 <b>Товары ({len(items)}):</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML"
    )

# ─── /delete ─────────────────────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: Message):
    if not is_admin(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /delete <артикул>\nНапример: <code>/delete 123456789</code>", parse_mode="HTML")
        return

    sku = args[1].strip()
    db = Database()
    item = db.get_item(sku)

    if not item:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    db.delete_item(sku)
    await message.answer(f"🗑 Удалён: <b>{item['name']}</b>", parse_mode="HTML")

# ─── /pause ──────────────────────────────────────────────────────────────────

@router.message(Command("pause"))
async def cmd_pause(message: Message):
    if not is_admin(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /pause <артикул>", parse_mode="HTML")
        return

    sku = args[1].strip()
    db = Database()
    item = db.get_item(sku)

    if not item:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    if item['status'] == 'active':
        db.set_status(sku, 'paused')
        await message.answer(f"⏸ Приостановлен: <b>{item['name']}</b>", parse_mode="HTML")
    else:
        db.set_status(sku, 'active')
        await message.answer(f"▶️ Возобновлён: <b>{item['name']}</b>", parse_mode="HTML")

# ─── /history ────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message):
    if not is_admin(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /history <артикул>", parse_mode="HTML")
        return

    sku = args[1].strip()
    db = Database()
    item = db.get_item(sku)

    if not item:
        await message.answer(f"❌ Товар <code>{sku}</code> не найден", parse_mode="HTML")
        return

    history = db.get_history(item['id'], limit=10)

    if not history:
        await message.answer("📭 История пуста")
        return

    lines = [f"📈 <b>История цен: {item['name'][:30]}</b>\n"]
    for record in history:
        price = f"{record['price_cents']/100:.2f}"
        lines.append(f"  {record['checked_at']}  →  <b>{price} BYN</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")

# ─── /check ──────────────────────────────────────────────────────────────────

@router.message(Command("check"))
async def cmd_check(message: Message):
    if not is_admin(message):
        return

    from services.checker import check_prices
    bot = message.bot

    msg = await message.answer("🔄 Запускаю проверку...")
    await check_prices(bot)
    await msg.edit_text("✅ Проверка завершена. Смотри /list")
