import logging
from datetime import datetime
from app.wb_api import get_product_data
from app.parser import parse_card_data
from app.storage import get_subscriptions, get_state, update_state

logger = logging.getLogger(__name__)

async def check_prices_job(bot, config):
    """Функция, которую вызывает планировщик"""
    logger.info("--- Запуск плановой проверки цен ---")
    
    settings = config['settings']
    chat_id = settings['tg_chat_id'] # ID владельца из .env
    
    subs = get_subscriptions()
    state = get_state()
    
    if not subs:
        logger.info("Нет подписок для проверки.")
        return

    for item in subs:
        product_id = item['id']
        target_price = item['target']
        item_name = item.get('name', 'Товар')
        
        # 1. Запрос
        data = await get_product_data(product_id, settings)
        if not data:
            continue
            
        # 2. Парсинг
        price_info = parse_card_data(data, settings['price_divider'])
        if not price_info:
            logger.warning(f"Не удалось извлечь цену для {product_id}")
            continue
            
        current_price = price_info['total']
        
        # 3. Логика уведомлений (State Machine)
        item_state = state.get(str(product_id), {'in_alert': False})
        is_in_alert = item_state.get('in_alert', False)
        
        # Сценарий А: Цена НИЖЕ или РАВНА цели
        if current_price <= target_price:
            if not is_in_alert:
                # ВХОД В АЛЕРТ -> Шлем уведомление
                msg = (
                    f"🎯 <b>ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА!</b>\n\n"
                    f"📦 {item_name}\n"
                    f"🆔 <code>{product_id}</code>\n"
                    f"💰 <b>{current_price:.2f} BYN</b> (Цель: {target_price:.2f})\n\n"
                    f"🔗 <a href='https://www.wildberries.by/catalog/{product_id}/detail.aspx'>Открыть на WB</a>"
                )
                try:
                    await bot.send_message(chat_id, msg, parse_mode="HTML")
                    logger.info(f"Уведомление отправлено для {product_id}")
                    
                    # Обновляем стейт
                    update_state(product_id, {
                        'in_alert': True,
                        'last_price': current_price,
                        'alert_ts': datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление: {e}")
            else:
                logger.info(f"{product_id}: Цена {current_price} все еще ниже цели. Тишина (антиспам).")

        # Сценарий Б: Цена ВЫШЕ цели
        else:
            if is_in_alert:
                # ВЫХОД ИЗ АЛЕРТА -> Сбрасываем флаг
                logger.info(f"{product_id}: Цена {current_price} поднялась выше цели. Сброс алерта.")
                update_state(product_id, {
                    'in_alert': False,
                    'last_price': current_price
                })