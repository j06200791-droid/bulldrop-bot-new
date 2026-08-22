import aiosqlite

DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                code TEXT
            )
        """)
        # PM Narxlar uchun jadval
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_prices (
                category TEXT PRIMARY KEY,
                price INTEGER
            )
        """)
        # Boshlang'ich narxlar
        default_prices = [("42", 2500), ("79", 4500), ("99", 7500), ("299", 20000)]
        for cat, pr in default_prices:
            await db.execute("INSERT OR IGNORE INTO pm_prices (category, price) VALUES (?, ?)", (cat, pr))
            
        await db.commit()

async def get_pm_prices() -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT category, price FROM pm_prices") as cursor:
            rows = await cursor.fetchall()
            return {r[0]: r[1] for r in rows}

async def update_pm_price(category: str, new_price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE pm_prices SET price = ? WHERE category = ?", (new_price, category))
        await db.commit()

async def get_user_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            else:
                await db.execute("INSERT INTO users (user_id, balance, is_banned) VALUES (?, 0, 0)", (user_id,))
                await db.commit()
                return 0

async def add_user_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await get_user_balance(user_id)
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_user_ban(user_id: int, status: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await get_user_balance(user_id)
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

async def get_users_count() -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def get_pm_count(category: str) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM pm_codes WHERE category = ?", (category,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_pm_code(category: str, code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO pm_codes (category, code) VALUES (?, ?)", (category, code))
        await db.commit()

async def buy_pm_code(category: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, code FROM pm_codes WHERE category = ? LIMIT 1", (category,)) as cursor:
            row = await cursor.fetchone()
            if row:
                pm_id, code = row
                await db.execute("DELETE FROM pm_codes WHERE id = ?", (pm_id,))
                await db.commit()
                return code
            return None