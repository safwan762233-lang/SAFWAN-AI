import sqlite3
from pathlib import Path
from .config import DATABASE_PATH

def connect():
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'New conversation',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS api_usage (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            api_key_id INTEGER NOT NULL,\n            endpoint TEXT NOT NULL,\n            status_code INTEGER NOT NULL,\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE\n        )""")\n        con.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_key_time ON api_usage(api_key_id, created_at)")\n\n        con.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            stock_qty REAL NOT NULL DEFAULT 0 CHECK(stock_qty >= 0),
            low_stock_at REAL NOT NULL DEFAULT 5 CHECK(low_stock_at >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            reference TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','confirmed','cancelled')),
            total REAL NOT NULL DEFAULT 0 CHECK(total >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            line_total REAL NOT NULL CHECK(line_total >= 0),
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )""")
