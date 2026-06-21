# database/db_manager.py
import sqlite3
import os
import logging
from config import DB_NAME
from database.schema import CREATE_ITEMS_TABLE, CREATE_HISTORY_TABLE, CREATE_INDEXES

class Database:    
    def set_alert_status(self, item_id: int, in_alert: bool):
        """Обновляем статус: находимся ли мы в режиме тревоги"""
        val = 1 if in_alert else 0
        with self._connect() as conn:
            conn.execute("UPDATE items SET is_in_alert = ? WHERE id = ?", (val, item_id))
            conn.commit()
    
    def __init__(self, db_path=DB_NAME):
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_db()

    def _ensure_db_directory(self):
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            logging.info(f"Created DB directory: {directory}")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(CREATE_ITEMS_TABLE + CREATE_HISTORY_TABLE + CREATE_INDEXES)
            conn.commit()

    def add_item(self, sku: str, name: str, target_price_cents: int):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO items (sku, name, target_price_cents, status)
                VALUES (?, ?, ?, 'active')
                ON CONFLICT(sku) DO UPDATE SET
                    target_price_cents = excluded.target_price_cents,
                    status = 'active',
                    name = excluded.name
            """, (sku, name, target_price_cents))
            conn.commit()

    def get_item(self, sku: str):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
            return dict(row) if row else None

    def list_items(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_active_items(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM items WHERE status = 'active'").fetchall()
            return [dict(r) for r in rows]

    def delete_item(self, sku: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM items WHERE sku = ?", (sku,))
            conn.commit()

    def set_status(self, sku: str, status: str):
        with self._connect() as conn:
            conn.execute("UPDATE items SET status = ? WHERE sku = ?", (status, sku))
            conn.commit()

    def log_price(self, item_id: int, price_cents: int):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO price_history (item_id, price_cents) VALUES (?, ?)",
                (item_id, price_cents)
            )
            conn.execute("""
                UPDATE items
                SET last_price_cents = ?,
                    last_checked_at = datetime('now','localtime')
                WHERE id = ?
            """, (price_cents, item_id))
            conn.commit()

    def mark_notified(self, item_id: int):
        with self._connect() as conn:
            conn.execute("""
                UPDATE items
                SET last_notified_at = datetime('now','localtime')
                WHERE id = ?
            """, (item_id,))
            conn.commit()

    def get_history(self, item_id: int, limit: int = 10):
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT price_cents, checked_at
                FROM price_history
                WHERE item_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
            """, (item_id, limit)).fetchall()
            return [dict(r) for r in rows]
