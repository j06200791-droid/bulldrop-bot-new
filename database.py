import sqlite3
import asyncio
from concurrent.futures import ThreadPoolExecutor

DB_NAME = "database.db"
executor = ThreadPoolExecutor(max_workers=5)

def _run_query(func, *args):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    res = func(conn, cursor, *args)
    conn.commit()
    conn.close()
    return res

async def run_async(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _run_query, func, *args)

# --- DB METHODS ---
def _init_db(conn, cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pm_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            code TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pm_prices (
            category TEXT PRIMARY KEY,
            price INTEGER
        )
    """)

async def init_db():
    await run_async(_init_db)

def _get_user_balance(conn, cursor, user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
    return 0

async def get_user_balance(user_id: int) -> int:
    return await run_async(_get_user_balance, user_id)

def _add_user_balance(conn, cursor, user_id, amount):
    _get_user_balance(conn, cursor, user_id)
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

async def add_user_balance(user_id: int, amount: int):
    await run_async(_add_user_balance, user_id, amount)

def _is_user_banned(conn, cursor, user_id):
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return bool(row[0]) if row else False

async def is_user_banned(user_id: int) -> bool:
    return await run_async(_is_user_banned, user_id)

def _set_user_ban(conn, cursor, user_id, status):
    _get_user_balance(conn, cursor, user_id)
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))

async def set_user_ban(user_id: int, status: int):
    await run_async(_set_user_ban, user_id, status)

def _get_pm_prices(conn, cursor):
    cursor.execute("SELECT category, price FROM pm_prices")
    rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}

async def get_pm_prices() -> dict:
    return await run_async(_get_pm_prices)

def _update_pm_price(conn, cursor, category, price):
    cursor.execute("INSERT OR REPLACE INTO pm_prices (category, price) VALUES (?, ?)", (category, price))

async def update_pm_price(category: str, price: int):
    await run_async(_update_pm_price, category, price)

def _add_pm_code(conn, cursor, category, code):
    cursor.execute("INSERT INTO pm_codes (category, code) VALUES (?, ?)", (category, code))

async def add_pm_code(category: str, code: str):
    await run_async(_add_pm_code, category, code)

def _get_pm_count(conn, cursor, category):
    cursor.execute("SELECT COUNT(*) FROM pm_codes WHERE category = ?", (category,))
    row = cursor.fetchone()
    return row[0] if row else 0

async def get_pm_count(category: str) -> int:
    return await run_async(_get_pm_count, category)

def _buy_pm_code(conn, cursor, category):
    cursor.execute("SELECT id, code FROM pm_codes WHERE category = ? LIMIT 1", (category,))
    row = cursor.fetchone()
    if row:
        code_id, code = row[0], row[1]
        cursor.execute("DELETE FROM pm_codes WHERE id = ?", (code_id,))
        return code
    return None

async def buy_pm_code(category: str):
    return await run_async(_buy_pm_code, category)

def _get_users_count(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users")
    row = cursor.fetchone()
    return row[0] if row else 0

async def get_users_count() -> int:
    return await run_async(_get_users_count)

def _get_all_users(conn, cursor):
    cursor.execute("SELECT user_id FROM users")
    return cursor.fetchall()

async def get_all_users():
    return await run_async(_get_all_users)
