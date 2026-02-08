import json
import os
import logging
from typing import Dict, Any, List

SUBS_FILE = "data/subscriptions.json"
STATE_FILE = "data/state.json"

logger = logging.getLogger(__name__)


def _load_json(filepath: str, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Ошибка чтения %s: %s", filepath, e)
        return default


def _save_json(filepath: str, data) -> None:
    """
    Сохраняет JSON атомарно (через tmp + replace),
    чтобы не получить "битый" файл при сбое.
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    tmp = filepath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)
    except Exception as e:
        logger.error("Ошибка записи %s: %s", filepath, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


# --- Subscriptions ---

def get_subscriptions() -> List[Dict[str, Any]]:
    subs = _load_json(SUBS_FILE, default=[])
    if not isinstance(subs, list):
        logger.warning("%s имеет неверный формат, ожидали list", SUBS_FILE)
        return []
    return subs


def add_subscription(item: Dict[str, Any]) -> None:
    """
    item: {id, target, name}
    Если товар уже есть — обновляем target и name.
    """
    subs = get_subscriptions()
    item_id = str(item.get("id"))

    updated = False
    for sub in subs:
        if str(sub.get("id")) == item_id:
            sub["target"] = item.get("target", sub.get("target"))
            sub["name"] = item.get("name", sub.get("name"))
            updated = True
            break

    if not updated:
        subs.append(item)

    _save_json(SUBS_FILE, subs)
    logger.info("Подписка сохранена: id=%s (updated=%s)", item_id, updated)


def remove_subscription(product_id: str) -> None:
    subs = get_subscriptions()
    pid = str(product_id)
    new_subs = [s for s in subs if str(s.get("id")) != pid]
    _save_json(SUBS_FILE, new_subs)
    logger.info("Подписка удалена: id=%s (было=%d стало=%d)", pid, len(subs), len(new_subs))


# --- State (prices + alerts) ---

def get_state_item(product_id: str) -> Dict[str, Any]:
    """
    Возвращает состояние конкретного товара:
    {in_alert, last_price, last_check_time, ...}
    """
    full_state = _load_json(STATE_FILE, default={})
    if not isinstance(full_state, dict):
        logger.warning("%s имеет неверный формат, ожидали dict", STATE_FILE)
        return {}

    return full_state.get(str(product_id), {})


def update_state(product_id: str, patch: Dict[str, Any]) -> None:
    """
    Patch-обновление: накладываем patch поверх текущего состояния товара,
    чтобы не затереть in_alert и другие флаги.
    """
    full_state = _load_json(STATE_FILE, default={})
    if not isinstance(full_state, dict):
        logger.warning("%s имеет неверный формат, пересоздаю как dict", STATE_FILE)
        full_state = {}

    pid = str(product_id)
    current = full_state.get(pid, {})
    if not isinstance(current, dict):
        current = {}

    current.update(patch)
    full_state[pid] = current

    _save_json(STATE_FILE, full_state)
    logger.debug("State updated: id=%s patch=%s", pid, patch)