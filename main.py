import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import load_config
from app.handlers import register_handlers
from app.checker import check_prices_job

# Настройка логирования
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    # 1. Загрузка конфига
    config = load_config()
    token = config['settings']['tg_token']
    
    # 2. Инициализация бота
    bot = Bot(token=token)
    dp = Dispatcher()
    
    # 3. Регистрация хэндлеров (команд)
    register_handlers(dp, config)
    
    # 4. Запуск планировщика
    scheduler = AsyncIOScheduler()
    interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 10))
    
    scheduler.add_job(
        check_prices_job, 
        'interval', 
        minutes=interval, 
        args=[bot, config]
    )
    scheduler.start()
    
    logger.info("Бот запущен. Планировщик работает.")
    
    # 5. Старт поллинга (обработка сообщений)
    # Пропускаем старые апдейты, чтобы бот не ответил на все, что пришло пока он спал
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")