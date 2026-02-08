import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.storage import init_csv
from app.config import load_config
from app.handlers import register_handlers
from app.checker import check_prices_job

# -----------------------------
# Логирование
# -----------------------------
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def main():
    # 1) Конфиг
    config = load_config()
    token = (config.get("settings") or {}).get("tg_token")

    if not token:
        logger.error("Не найден TG токен. Проверь .env (TG_BOT_TOKEN) и загрузчик конфига.")
        return

    # 2) Инициализация CSV для аналитики
    init_csv()

    # 3) Бот и диспетчер
    bot = Bot(token=token)  # parse_mode можно задавать в send_message, как сейчас
    dp = Dispatcher()

    # 4) Планировщик
    scheduler = AsyncIOScheduler()
    interval = int(os.getenv("CHECK_INTERVAL_MINUTES", 10))

    # Важно: задаём ID джобы, чтобы потом уметь менять интервал
    job = scheduler.add_job(
        check_prices_job,
        trigger="interval",
        minutes=interval,
        args=[bot, config],
        id="check_prices",          # <- ключ для /interval
        replace_existing=True,      # <- если вдруг добавится повторно
        max_instances=1,            # <- защита от наложения запусков
        coalesce=True,              # <- если “проспал”, не догоняет пачкой
        misfire_grace_time=60,      # <- если задержка до 60с — всё ок
    )
    scheduler.start()

    # 5) Хэндлеры (передадим scheduler, чтобы команда /interval могла менять job)
    register_handlers(dp, config, scheduler)

    logger.info("Бот запущен. Интервал проверки: %s минут", interval)

    try:
        # не отвечать на старые сообщения, накопленные пока бот был выключен
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        # аккуратное завершение
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка по сигналу.")
