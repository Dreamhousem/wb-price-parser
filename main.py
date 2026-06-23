# main.py
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, CHECK_INTERVAL_MINUTES, validate_config
from bot.handlers import router
from services.checker import check_prices

# ─── Logging ─────────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── Startup / Shutdown ──────────────────────────────────────────────────────

async def on_startup(bot: Bot):
    logger.info(f"Бот запущен. Интервал проверки: {CHECK_INTERVAL_MINUTES} мин.")
    await bot.send_message(ADMIN_ID, "✅ WB Price Tracker запущен")

async def on_shutdown(bot: Bot):
    await bot.send_message(ADMIN_ID, "🛑 WB Price Tracker остановлен")

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    validate_config()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[bot],
        id="price_check",
        replace_existing=True,
    )
    scheduler.start()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")
