# services/checker.py
import logging
import asyncio
from database.db_manager import Database
from parser.wb_client import WBClient
from config import ADMIN_ID 

logger = logging.getLogger(__name__)

async def check_prices(bot):
    """
    Основная функция проверки.
    Запускается из scheduler (main.py).
    """
    db = Database()
    client = WBClient()
    
    # 1. Получаем активные товары
    items = db.get_active_items()
    if not items:
        logger.info("Нет активных товаров для проверки.")
        return

    logger.info(f"Начинаем проверку {len(items)} товаров (Region: BY)...")

    for item in items:
        # item - это словарь из БД (id, sku, target_price_cents, is_in_alert, etc.)
        sku = item['sku']
        
        # 2. Парсим (синхронный вызов внутри асинхронной функции - для MVP ок)
        # Если будет много товаров, парсер лучше тоже сделать async
        item_data = client.get_item_data(sku)
        
        if not item_data:
            logger.warning(f"Не удалось получить данные для {sku}")
            continue

        current_price_cents = item_data['price_cents']
        target_price_cents = item['target_price_cents']
        is_in_alert = bool(item['is_in_alert']) # 1 или 0 из БД
        
        # 3. Пишем в историю (всегда!)
        db.log_price(item['id'], current_price_cents)
        
        # 4. Логика уведомлений (State Machine)
        
        # Сценарий А: Цена НИЖЕ или РАВНА цели
        if current_price_cents <= target_price_cents:
            if not is_in_alert:
                # ВХОД В АЛЕРТ -> Шлем уведомление
                price_byn = current_price_cents / 100
                target_byn = target_price_cents / 100
                
                msg = (
                    f"🇧🇾 <b>ЦЕЛЕВАЯ ЦЕНА (BYN)!</b>\n\n"
                    f"📦 {item['name']}\n"
                    f"🆔 <code>{sku}</code>\n"
                    f"💰 <b>{price_byn:.2f} BYN</b> (Цель: {target_byn:.2f})\n\n"
                    f"🔗 <a href='https://www.wildberries.by/catalog/{sku}/detail.aspx'>Открыть на WB</a>"
                )
                
                try:
                    # Отправляем сообщение админу
                    await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
                    
                    # Ставим флаг "Мы в алерте", обновляем время уведомления
                    db.set_alert_status(item['id'], True)
                    db.mark_notified(item['id'])
                    logger.info(f"Уведомление отправлено для {sku}")
                except Exception as e:
                    logger.error(f"Ошибка отправки Telegram для {sku}: {e}")
            else:
                # Уже в алерте, цена все еще низкая -> ТИШИНА
                logger.info(f"{sku}: Цена низкая, но уведомление уже было (Anti-Spam).")

        # Сценарий Б: Цена ВЫШЕ цели
        else:
            if is_in_alert:
                # ВЫХОД ИЗ АЛЕРТА -> Сбрасываем флаг
                logger.info(f"{sku}: Цена поднялась выше цели. Сброс алерта.")
                db.set_alert_status(item['id'], False)
            else:
                # Все спокойно
                pass