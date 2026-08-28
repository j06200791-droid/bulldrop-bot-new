import aiosqlite
import json

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Foydalanuvchilar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        """)
        
        # Promokodlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                code TEXT UNIQUE,
                is_used INTEGER DEFAULT 0
            )
        """)
        
        # Narxlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_prices (
                category TEXT PRIMARY KEY,
                price INTEGER
            )
        """)

        # Avto-to'lovlarni kuzatish uchun to'lovlar (payments) jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending'
            )
        """)
        
        await db.commit()


# --- USERS (FOYDALANUVCHILAR) ---
async def get_user_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            else:
                await db.execute("INSERT INTO users (user_id, balance, is_banned) VALUES (?, 0, 0)", (user_id,))
                await db.commit()
                return 0

async def add_user_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await get_user_balance(user_id) # User borligini ta'minlash
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

async def set_user_ban(user_id: int, is_banned: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await get_user_balance(user_id)
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (is_banned, user_id))
        await db.commit()

async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


# --- PM PROMOKODLAR ---
async def add_pm_code(category: str, code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO pm_codes (category, code) VALUES (?, ?)", (category, code))
            await db.commit()
        except Exception:
            pass

async def get_pm_count(category: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM pm_codes WHERE category = ? AND is_used = 0", (category,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def buy_pm_code(category: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, code FROM pm_codes WHERE category = ? AND is_used = 0 LIMIT 1", (category,)) as cursor:
            row = await cursor.fetchone()
            if row:
                code_id, code = row[0], row[1]
                await db.execute("UPDATE pm_codes SET is_used = 1 WHERE id = ?", (code_id,))
                await db.commit()
                return code
            return None

async def get_pm_prices() -> dict:
    default_prices = {"24": 1500, "49": 3500, "99": 9000, "149": 16000, "179": 18000, "199": 21000}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT category, price FROM pm_prices") as cursor:
            rows = await cursor.fetchall()
            for cat, price in rows:
                default_prices[cat] = price
    return default_prices

async def update_pm_price(category: str, price: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO pm_prices (category, price) VALUES (?, ?)", (category, price))
        await db.commit()


# --- PAYHAMYON TO'LOV KUTUBXONASI ---
async def save_payment_token(token: str, user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO payments (token, user_id, amount, status) VALUES (?, ?, ?, 'pending')",
            (token, user_id, amount)
        )
        await db.commit()

async def get_user_id_by_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM payments WHERE token = ?", (token,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_payment_paid(token: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM payments WHERE token = ?", (token,)) as cursor:
            row = await cursor.fetchone()
            return row[0] == "paid" if row else False

async def mark_payment_as_paid(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status = 'paid' WHERE token = ?", (token,))
        await db.commit()
