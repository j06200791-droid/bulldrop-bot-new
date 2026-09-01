import aiosqlite

DB_NAME = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Foydalanuvchilar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0
            )
        """)
        
        # Promokodlar jadvali (uploader_id orqali kimnikiligini bilish uchun)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                code TEXT UNIQUE,
                uploader_id INTEGER DEFAULT 5974947091
            )
        """)
        
        # PM narxlari jadvali (Sotib olish narxlari)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_prices (
                category TEXT PRIMARY KEY,
                price INTEGER
            )
        """)
        
        # Foydalanuvchidan sotib olish narxlari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_sell_prices (
                category TEXT PRIMARY KEY,
                price INTEGER
            )
        """)
        
        # To'lov tokenlari jadvali (Avto to'lovlar uchun)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending'
            )
        """)
        
        await db.commit()
        
        # Standart narxlarni kiritish (agar mavjud bo'lmasa)
        default_prices = {"24": 1500, "49": 3500, "99": 9000, "149": 16000, "179": 18000, "199": 21000}
        for cat, price in default_prices.items():
            await db.execute(
                "INSERT OR IGNORE INTO pm_prices (category, price) VALUES (?, ?)", 
                (cat, price)
            )
            
        default_sell_prices = {"24": 1000, "49": 2500, "99": 7000, "149": 13000, "179": 15000, "199": 18000}
        for cat, price in default_sell_prices.items():
            await db.execute(
                "INSERT OR IGNORE INTO user_sell_prices (category, price) VALUES (?, ?)", 
                (cat, price)
            )
        await db.commit()

# --- USERS FUNKSIYALARI ---
async def get_user_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                await db.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
                await db.commit()
                return 0
            return row[0]

async def add_user_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
            (user_id, amount, amount)
        )
        await db.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

async def set_user_ban(user_id: int, status: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO users (user_id, banned) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET banned = ?",
            (user_id, status, status)
        )
        await db.commit()

async def get_users_count() -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            return await cursor.fetchall()


# --- PM (PROMOKOD) FUNKSIYALARI ---
async def get_pm_count(category: str) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM pm_codes WHERE category = ?", (category,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_pm_code(category: str, code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO pm_codes (category, code, uploader_id) VALUES (?, ?, 5974947091)", (category, code))
        await db.commit()

async def add_user_pm_code_with_owner(category: str, code: str, uploader_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO pm_codes (category, code, uploader_id) VALUES (?, ?, ?)", (category, code, uploader_id))
        await db.commit()

async def buy_pm_code_with_owner(category: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, code, uploader_id FROM pm_codes WHERE category = ? LIMIT 1", (category,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            code_id, code, uploader_id = row
            await db.execute("DELETE FROM pm_codes WHERE id = ?", (code_id,))
            await db.commit()
            return code, uploader_id

async def buy_pm_code(category: str):
    res = await buy_pm_code_with_owner(category)
    return res[0] if res else None


# --- NARXLLARNI BOSHQARISH ---
async def get_pm_prices() -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT category, price FROM pm_prices") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def update_pm_price(category: str, price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO pm_prices (category, price) VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET price = ?", (category, price, price))
        await db.commit()

async def get_user_sell_prices() -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT category, price FROM user_sell_prices") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def update_user_sell_price(category: str, price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO user_sell_prices (category, price) VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET price = ?", (category, price, price))
        await db.commit()


# --- TO'LOV (PAYMENT) TOKENLARI ---
async def save_payment_token(token: str, user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO payments (token, user_id, amount, status) VALUES (?, ?, ?, 'pending')",
            (token, user_id, amount)
        )
        await db.commit()

async def get_user_id_by_token(token: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM payments WHERE token = ?", (token,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_payment_paid(token: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT status FROM payments WHERE token = ?", (token,)) as cursor:
            row = await cursor.fetchone()
            return row[0] == 'paid' if row else False

async def mark_payment_as_paid(token: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE payments SET status = 'paid' WHERE token = ?", (token,))
        await db.commit()
