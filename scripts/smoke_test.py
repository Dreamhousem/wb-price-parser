"""
scripts/smoke_test.py

Запуск из корня проекта:
    python -m scripts.smoke_test

Проверяет:
  1. БД создаётся и товар добавляется
  2. Цикл checker: антиспам State Machine (4 шага)
  3. Защита от цены 0 — алерт не должен уйти
  4. Ошибка одного товара не ломает цикл остальных
"""

import asyncio
import sys
import os
import logging

# Чтобы импорты работали из корня проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import Database
from services.checker import _check_single_item

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("smoke_test")

# ─── Моки ────────────────────────────────────────────────────────────────────

class MockBot:
    """Имитирует bot.send_message — считает, сколько раз вызвали."""
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text})
        logger.info(f"  📨 MockBot: сообщение отправлено (всего: {len(self.sent)})")


class MockWBClient:
    """Возвращает цену, которую мы передаём через price_cents."""
    def __init__(self, price_cents: int):
        self.price_cents = price_cents

    def get_item_data(self, sku: str):
        if self.price_cents <= 0:
            return {"sku": sku, "name": "Test Item", "price_cents": self.price_cents, "available": True}
        return {"sku": sku, "name": "Test Item", "price_cents": self.price_cents, "available": True}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_item(db: Database, sku: str, target_cents: int) -> dict:
    db.add_item(sku=sku, name="Test Item", target_price_cents=target_cents)
    return db.get_item(sku)


def assert_eq(label: str, actual, expected):
    status = "✅" if actual == expected else "❌"
    print(f"  {status} {label}: ожидали={expected!r}, получили={actual!r}")
    if actual != expected:
        raise AssertionError(f"FAIL: {label}")


# ─── Тесты ───────────────────────────────────────────────────────────────────

async def test_antispam_state_machine(db: Database):
    """
    Шаг 1: цена ниже цели → уведомление отправлено, is_in_alert=1
    Шаг 2: цена всё ещё ниже цели → тишина (антиспам)
    Шаг 3: цена выше цели → is_in_alert сброшен в 0
    Шаг 4: цена снова ниже цели → уведомление снова отправлено
    """
    print("\n📋 Тест: антиспам State Machine")
    SKU = "ANTISPAM001"
    TARGET = 10000  # 100.00 BYN
    bot = MockBot()

    item = make_item(db, SKU, TARGET)

    # Шаг 1: цена ниже цели, алерта нет → ждём уведомление
    client = MockWBClient(price_cents=8000)  # 80.00 BYN
    await _check_single_item(bot, db, client, db.get_item(SKU))
    item = db.get_item(SKU)
    assert_eq("Шаг 1: is_in_alert", item['is_in_alert'], 1)
    assert_eq("Шаг 1: уведомлений отправлено", len(bot.sent), 1)

    # Шаг 2: цена всё ещё ниже, алерт уже есть → тишина
    await _check_single_item(bot, db, client, db.get_item(SKU))
    assert_eq("Шаг 2: is_in_alert", db.get_item(SKU)['is_in_alert'], 1)
    assert_eq("Шаг 2: уведомлений (без новых)", len(bot.sent), 1)

    # Шаг 3: цена выросла → сброс алерта
    client = MockWBClient(price_cents=12000)  # 120.00 BYN
    await _check_single_item(bot, db, client, db.get_item(SKU))
    assert_eq("Шаг 3: is_in_alert сброшен", db.get_item(SKU)['is_in_alert'], 0)
    assert_eq("Шаг 3: уведомлений (без новых)", len(bot.sent), 1)

    # Шаг 4: цена снова упала → новое уведомление
    client = MockWBClient(price_cents=9000)  # 90.00 BYN
    await _check_single_item(bot, db, client, db.get_item(SKU))
    assert_eq("Шаг 4: is_in_alert снова 1", db.get_item(SKU)['is_in_alert'], 1)
    assert_eq("Шаг 4: уведомлений отправлено 2", len(bot.sent), 2)

    print("  ✅ Все шаги антиспама прошли!")


async def test_zero_price_protection(db: Database):
    """
    WB вернул цену 0 → алерт не должен уйти, история не пишется.
    """
    print("\n📋 Тест: защита от цены 0")
    SKU = "ZEROPRICE001"
    TARGET = 10000
    bot = MockBot()

    make_item(db, SKU, TARGET)
    client = MockWBClient(price_cents=0)

    await _check_single_item(bot, db, client, db.get_item(SKU))

    assert_eq("Уведомлений не отправлено", len(bot.sent), 0)
    assert_eq("is_in_alert остался 0", db.get_item(SKU)['is_in_alert'], 0)

    history = db.get_history(db.get_item(SKU)['id'])
    assert_eq("История не писалась", len(history), 0)

    print("  ✅ Защита от нулевой цены работает!")


async def test_history_is_written(db: Database):
    """
    Каждая валидная проверка пишет запись в price_history.
    """
    print("\n📋 Тест: история цен записывается")
    SKU = "HISTORY001"
    TARGET = 10000
    bot = MockBot()

    make_item(db, SKU, TARGET)
    client = MockWBClient(price_cents=9500)

    await _check_single_item(bot, db, client, db.get_item(SKU))
    await _check_single_item(bot, db, client, db.get_item(SKU))
    await _check_single_item(bot, db, client, db.get_item(SKU))

    history = db.get_history(db.get_item(SKU)['id'])
    assert_eq("В истории 3 записи", len(history), 3)

    print("  ✅ История цен пишется корректно!")


async def test_one_item_error_doesnt_break_loop(db: Database):
    """
    Если один товар упал с ошибкой, остальные всё равно проверяются.
    """
    print("\n📋 Тест: ошибка одного товара не ломает цикл")

    class BrokenWBClient:
        def get_item_data(self, sku):
            raise RuntimeError("Симуляция сетевой ошибки")

    SKU_BROKEN = "BROKEN001"
    SKU_GOOD = "GOOD001"
    TARGET = 10000
    bot = MockBot()

    make_item(db, SKU_BROKEN, TARGET)
    make_item(db, SKU_GOOD, TARGET)

    # Проверяем "сломанный" товар — должен залогировать ошибку и не упасть
    from parser.wb_client import WBClient
    try:
        broken_client = BrokenWBClient()
        await _check_single_item(bot, db, broken_client, db.get_item(SKU_BROKEN))
    except Exception:
        raise AssertionError("❌ Ошибка одного товара не должна бросать исключение наружу")

    # "Хороший" товар после этого всё равно проверяется
    good_client = MockWBClient(price_cents=8000)
    await _check_single_item(bot, db, good_client, db.get_item(SKU_GOOD))

    assert_eq("Хороший товар получил алерт", db.get_item(SKU_GOOD)['is_in_alert'], 1)
    print("  ✅ Изоляция ошибок работает!")


# ─── Runner ──────────────────────────────────────────────────────────────────

async def run_all():
    print("=" * 55)
    print("  WB Price Tracker — Smoke Tests (Stage 1)")
    print("=" * 55)

    # Используем временный файл вместо :memory: — каждый _connect() открывает
    # новое соединение, поэтому in-memory таблицы не сохраняются между вызовами.
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(db_path=tmp.name)

    tests = [
        test_antispam_state_machine,
        test_zero_price_protection,
        test_history_is_written,
        test_one_item_error_doesnt_break_loop,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test(db)
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 Неожиданная ошибка в {test.__name__}: {e}")
            failed += 1

    print("\n" + "=" * 55)
    print(f"  Итого: {passed} passed, {failed} failed")
    print("=" * 55)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())