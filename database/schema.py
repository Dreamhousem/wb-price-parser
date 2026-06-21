# database/schema.py

CREATE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT,
    target_price_cents INTEGER NOT NULL,
    last_price_cents INTEGER,
    
    status TEXT NOT NULL DEFAULT 'active', -- active / paused
    is_in_alert INTEGER DEFAULT 0,         -- 0 = Нет алерта, 1 = Алерт активен (цена была низкой)
    
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    last_checked_at TEXT,
    last_notified_at TEXT
);
"""

# Остальное без изменений (HISTORY TABLE и INDEXES)
CREATE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    price_cents INTEGER NOT NULL,
    checked_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_history_item_time ON price_history(item_id, checked_at);
"""