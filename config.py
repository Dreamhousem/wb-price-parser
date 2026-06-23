# config.py
import os
from dotenv import load_dotenv

load_dotenv()


def get_str_env(name: str, default: str = "") -> str:
    """
    Безопасно читает строковую переменную из .env.
    Если переменной нет — вернёт default.
    """
    return os.getenv(name, default).strip()


def get_int_env(name: str, default: int = 0) -> int:
    """
    Безопасно читает числовую переменную из .env.
    Если значение пустое — вернёт default.
    Если значение не число — выбросит понятную ошибку.
    """
    value = os.getenv(name, str(default)).strip()

    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} должен быть числом, сейчас: {value}")


# ─── Telegram ────────────────────────────────────────────────────────────────

BOT_TOKEN = get_str_env("BOT_TOKEN")
ADMIN_ID = get_int_env("ADMIN_ID")


# ─── Database ────────────────────────────────────────────────────────────────

DB_NAME = get_str_env("DB_NAME", "data/wb_price.db")


# ─── Scheduler ───────────────────────────────────────────────────────────────

CHECK_INTERVAL_MINUTES = get_int_env("CHECK_INTERVAL_MINUTES", 30)


# ─── Wildberries BY ──────────────────────────────────────────────────────────

WB_CURR = get_str_env("WB_CURR", "byn")
WB_DEST = get_str_env("WB_DEST", "-59246")
WB_SPP = get_str_env("WB_SPP", "30")
WB_WEB_BASE_URL = get_str_env("WB_WEB_BASE_URL", "https://www.wildberries.by")


# ─── Validation on startup ──────────────────────────────────────────────────

def validate_config():
    """
    Проверяет настройки при старте приложения.
    Если что-то не так — приложение не запустится молча, а покажет понятную ошибку.
    """
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не задан в .env")

    if ADMIN_ID <= 0:
        errors.append("ADMIN_ID не задан в .env или указан неверно")

    if CHECK_INTERVAL_MINUTES <= 0:
        errors.append("CHECK_INTERVAL_MINUTES должен быть больше 0")

    if not DB_NAME:
        errors.append("DB_NAME не задан")

    if not WB_CURR:
        errors.append("WB_CURR не задан")

    if not WB_DEST:
        errors.append("WB_DEST не задан")

    if not WB_SPP:
        errors.append("WB_SPP не задан")

    if errors:
        raise ValueError("Ошибки конфигурации:\n- " + "\n- ".join(errors))