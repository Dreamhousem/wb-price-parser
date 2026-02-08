import csv
import json
import os
import logging
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# -----------------------------
# Пути к файлам данных
# -----------------------------
DATA_DIR = "data"
SUBS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
CSV_FILE = os.path.join(DATA_DIR, "prices.csv")

# -----------------------------
# Ротация CSV
# 5 МБ ≈ 50-70k строк (зависит от длины названий)
# -----------------------------
MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB


# -----------------------------
# Внутренние helpers
# -----------------------------
def _ensure_data_dir() -> None:
    """Гарантируем, что папка data существует."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(filepath: str, default):
    """
    Читаем JSON.
    default возвращаем если файла нет или он битый.
    """
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Ошибка чтения %s: %s", filepath, e)
        return default


def _save_json(filepath: str, data) -> None:
    """Пишем JSON. Папку data создаём при необходимости."""
    _ensure_data_dir()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Ошибка записи %s: %s", filepath, e)


# =========================================================
# 1) SUBSCRIPTIONS: список отслеживаемых товаров (MVP single-user)
# =========================================================
def get_subscriptions() -> List[Dict[str, Any]]:
    """
    Возвращает список подписок:
    [
      {"id": "123", "target": 55.0, "name": "..."}, ...
    ]
    """
    subs = _load_json(SUBS_FILE, default=[])
    if not isinstance(subs, list):
        logger.warning("Файл подписок %s имеет неожиданный формат. Сбрасываю в [].", SUBS_FILE)
        return []
    return subs


def add_subscription(item: Dict[str, Any]) -> None:
    """
    Добавляет или обновляет подписку по product_id.
    Важно: если товар уже есть — обновим target и (опционально) name.
    """
    subs = get_subscriptions()
    item_id = str(item.get("id"))

    if not item_id:
        logger.warning("Попытка добавить подписку без id: %s", item)
        return

    # Обновление существующей
    for sub in subs:
        if str(sub.get("id")) == item_id:
            sub["target"] = item.get("target", sub.get("target"))
            # имя обновляем, если пришло новое
            if item.get("name"):
                sub["name"] = item["name"]
            _save_json(SUBS_FILE, subs)
            logger.info("Подписка обновлена: id=%s target=%s", item_id, sub.get("target"))
            return

    # Добавление новой
    subs.append({
        "id": item_id,
        "target": item.get("target"),
        "name": item.get("name", "Товар WB"),
    })
    _save_json(SUBS_FILE, subs)
    logger.info("Подписка добавлена: id=%s target=%s", item_id, item.get("target"))


def remove_subscription(product_id: str) -> None:
    """Удаляет подписку по product_id."""
    subs = get_subscriptions()
    pid = str(product_id)
    new_subs = [s for s in subs if str(s.get("id")) != pid]

    _save_json(SUBS_FILE, new_subs)
    logger.info("Подписка удалена: id=%s (было=%d стало=%d)", pid, len(subs), len(new_subs))


# =========================================================
# 2) STATE: кэш для /list и флаг in_alert (антиспам)
# =========================================================
def get_state_item(product_id: str) -> Dict[str, Any]:
    """
    Возвращает состояние для одного товара, пример:
    {
      "last_price": 58.74,
      "last_check_time": "2026-02-08T15:45:00.123456",
      "in_alert": true
    }
    """
    full_state = _load_json(STATE_FILE, default={})
    if not isinstance(full_state, dict):
        logger.warning("Файл state %s имеет неожиданный формат. Сбрасываю в {}.", STATE_FILE)
        return {}
    return full_state.get(str(product_id), {}) or {}


def update_state(product_id: str, new_data: Dict[str, Any]) -> None:
    """
    Patch-обновление state по product_id.
    Важно: мы НЕ затираем весь объект, а накладываем поля поверх (update).
    """
    full_state = _load_json(STATE_FILE, default={})
    if not isinstance(full_state, dict):
        full_state = {}

    pid = str(product_id)
    current_item_state = full_state.get(pid, {}) or {}
    if not isinstance(current_item_state, dict):
        current_item_state = {}

    current_item_state.update(new_data)  # <-- ключевой момент: не теряем in_alert и др.
    full_state[pid] = current_item_state

    _save_json(STATE_FILE, full_state)


# =========================================================
# 3) CSV: история цен для аналитики + ротация
# =========================================================
def init_csv() -> None:
    """
    Создаёт папку data и prices.csv с заголовком, если файла нет.
    Можно вызывать при старте (в main.py).
    """
    _ensure_data_dir()
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        return

    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "timestamp",
                "id",
                "name",
                "product_price",
                "logistics",
                "return",
                "total_price",
                "target_price",
            ])
        logger.info("CSV инициализирован: %s", CSV_FILE)
    except Exception as e:
        logger.error("Ошибка инициализации CSV %s: %s", CSV_FILE, e)


def _rotate_csv_if_needed() -> None:
    """
    Если prices.csv больше MAX_CSV_SIZE, переименовываем его и начинаем новый.
    """
    if not os.path.exists(CSV_FILE):
        return

    try:
        file_size = os.path.getsize(CSV_FILE)
        if file_size >= MAX_CSV_SIZE:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = os.path.join(DATA_DIR, f"prices_{timestamp}.csv")
            shutil.move(CSV_FILE, new_name)
            logger.info("🔄 Ротация CSV: %s -> %s", CSV_FILE, new_name)
            # после ротации создадим новый файл с заголовком
            init_csv()
    except Exception as e:
        logger.error("Ошибка ротации CSV: %s", e)


def save_price_to_csv(
    item_id: str,
    item_name: str,
    price_dict: Dict[str, Any],
    target_price: Optional[float] = None
) -> None:
    """
    Пишет строку в CSV (история).
    price_dict ожидается: {'product': ..., 'logistics': ..., 'return': ..., 'total': ...}
    """
    _ensure_data_dir()

    # 1) Ротация (если файл разросся)
    _rotate_csv_if_needed()

    # 2) Если файл отсутствует/пустой — создадим заголовок
    if (not os.path.exists(CSV_FILE)) or os.path.getsize(CSV_FILE) == 0:
        init_csv()

    def fmt(num) -> str:
        """Формат для Excel: 2 знака, запятая вместо точки."""
        try:
            return f"{float(num):.2f}".replace(".", ",")
        except Exception:
            return "0,00"

    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(item_id),
                item_name or "Товар WB",
                fmt(price_dict.get("product", 0)),
                fmt(price_dict.get("logistics", 0)),
                fmt(price_dict.get("return", 0)),
                fmt(price_dict.get("total", 0)),
                fmt(target_price if target_price is not None else 0),
            ])
    except Exception as e:
        logger.error("Ошибка записи в CSV %s: %s", CSV_FILE, e)
