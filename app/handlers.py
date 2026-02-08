import os
from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.storage import add_subscription, get_subscriptions, remove_subscription, update_state

# Создаем роутер (группу хэндлеров)
router = Router()

# Глобальная переменная для конфига (простой способ передать настройки в хэндлеры)
BOT_CONFIG = None

def register_handlers(dp, config):
    """
    Эта функция вызывается из main.py.
    Она регистрирует роутер и сохраняет конфиг.
    """
    global BOT_CONFIG
    BOT_CONFIG = config
    
    # Регистрируем роутер в диспетчере
    dp.include_router(router)

# --- Фильтр "Только для владельца" ---
# Бот будет реагировать только на сообщения от allowed_user_id
@router.message.outer_middleware
async def admin_check_middleware(handler, event, data):
    # Получаем ID пользователя
    user_id = None
    if isinstance(event, Message):
        user_id = event.from_user.id
    
    # Проверяем доступ
    # Берем ID из конфига, который подтянулся из .env
    allowed_id = int(BOT_CONFIG['settings'].get('tg_chat_id', 0))
    
    if user_id and user_id == allowed_id:
        return await handler(event, data)
    else:
        # Если пишет чужой — можно игнорировать или ответить "Нет доступа"
        return

# --- Хэндлеры (Команды) ---

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>Привет! Я бот для мониторинга цен WB (BY).</b>\n\n"
        "<b>Мои команды:</b>\n"
        "/add <code>артикул</code> <code>цель</code> — добавить товар\n"
        "/list — список подписок\n"
        "/del <code>артикул</code> — удалить товар\n"
        "/status — проверить настройки\n\n"
        "<i>Пример добавления:</i>\n"
        "<code>/add 172638392 50.00</code>",
        parse_mode="HTML"
    )

@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject):
    """Добавить товар: /add 123456 55.5"""
    args = command.args
    if not args:
        await message.answer("⚠️ Ошибка. Формат: <code>/add артикул цена</code>")
        return

    try:
        parts = args.split()
        if len(parts) != 2:
            raise ValueError
        
        article = parts[0]
        target_price = float(parts[1].replace(',', '.'))
        
        # 1. Проверяем товар на WB (валидация)
        wait_msg = await message.answer(f"🔍 Ищу товар {article}...")
        
        settings = BOT_CONFIG['settings']
        data = await get_product_data(article, settings)
        
        if not data:
            await wait_msg.edit_text("❌ Товар не найден на WB или ошибка API.")
            return
            
        # 2. Парсим данные
        price_info = parse_card_data(data, settings['price_divider'])
        if not price_info:
            await wait_msg.edit_text("❌ Не удалось получить цену товара. Возможно, его нет в наличии.")
            return

        # # Название товара берем из JSON WB
        # # Структура может отличаться, пробуем найти имя
        # try:
        #     products = data.get('data', {}).get('products', [])
        #     product_name = products[0].get('name', 'Без названия')
        # except:
        #     product_name = "Товар WB"

        # Название товара берем из JSON WB (правильный путь: products[0].name)
        products = (data.get('data') or {}).get('products') or data.get('products') or []

        if not products:
            product_name = "Товар WB"
        else:
            product_name = products[0].get('name') or "Товар WB"


        # 3. Сохраняем в базу
        item = {
            'id': article,
            'target': target_price,
            'name': product_name
        }
        add_subscription(item)
        
        # Опционально: сразу сбрасываем стейт, чтобы уведомление пришло свежее
        update_state(article, {'in_alert': False})

        current_price = price_info['total']
        currency = settings['currency'].upper()
        
        await wait_msg.edit_text(
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📦 {product_name}\n"
            f"🆔 <code>{article}</code>\n"
            f"💰 Текущая цена: <b>{current_price} {currency}</b>\n"
            f"🎯 Цель: <b>{target_price} {currency}</b>",
            parse_mode="HTML"
        )

    except ValueError:
        await message.answer("⚠️ Ошибка в числах. Пример: <code>/add 123456 50.5</code>")
    except Exception as e:
        await message.answer(f"⚠️ Произошла ошибка: {e}")

@router.message(Command("list"))
async def cmd_list(message: Message):
    subs = get_subscriptions()
    if not subs:
        await message.answer("📭 Список отслеживания пуст.")
        return

    text = "📋 <b>Твои подписки:</b>\n\n"
    currency = BOT_CONFIG['settings']['currency'].upper()

    for item in subs:
        text += (
            f"🔹 <b>{item.get('name', 'Товар')}</b>\n"
            f"ID: <code>{item['id']}</code> | Цель: {item['target']} {currency}\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")

@router.message(Command("del", "delete"))
async def cmd_del(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("⚠️ Укажите артикул: <code>/del 123456</code>")
        return
    
    article = command.args.strip()
    remove_subscription(article)
    await message.answer(f"🗑 Товар {article} удален из отслеживания.")

@router.message(Command("status"))
async def cmd_status(message: Message):
    settings = BOT_CONFIG['settings']
    await message.answer(
        f"⚙️ <b>Статус бота:</b>\n"
        f"Интервал проверки: {os.getenv('CHECK_INTERVAL_MINUTES', '10')} мин\n"
        f"Регион (dest): {settings['dest']}\n"
        f"Валюта: {settings['currency']}",
        parse_mode="HTML"
    )