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
        
        # Promokodlar jadvali (uploader_id orqaimport aiosqlite

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

# ============================================================
# QO'SHIMCHA ADMIN / STATISTIKA / PROMO / VIP / SUPPORT
# ============================================================

async def init_extra_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_bonuses (
            code TEXT PRIMARY KEY,
            amount INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_redemptions (
            code TEXT,
            user_id INTEGER,
            redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(code, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS vip_users (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS bot_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            category TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            status TEXT DEFAULT 'open',
            admin_reply TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            amount INTEGER DEFAULT 0,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        await db.commit()


# init_db ga qo'shimcha jadvallarni ham ishga tushirish
_original_init_db = init_db
async def init_db():
    await _original_init_db()
    await init_extra_db()


async def log_event(user_id, event_type, amount=0, category=None, details=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO bot_events (user_id,event_type,amount,category,details) VALUES (?,?,?,?,?)",
            (user_id, event_type, amount, category, details)
        )
        await db.commit()


async def log_admin_action(admin_id, action, target_id=None, amount=0, details=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO admin_logs (admin_id,action,target_id,amount,details) VALUES (?,?,?,?,?)",
            (admin_id, action, target_id, amount, details)
        )
        await db.commit()


async def create_promo_bonus(code, amount, max_uses=1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO promo_bonuses(code,amount,max_uses,used_count,active) VALUES(?,?,?,0,1)",
            (code, amount, max_uses)
        )
        await db.commit()


async def redeem_promo_bonus(code, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT amount,max_uses,used_count,active FROM promo_bonuses WHERE code=?",
            (code,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None, "not_found"
        amount, max_uses, used_count, active = row
        if not active or used_count >= max_uses:
            return None, "inactive"
        async with db.execute(
            "SELECT 1 FROM promo_redemptions WHERE code=? AND user_id=?",
            (code, user_id)
        ) as cur:
            if await cur.fetchone():
                return None, "already"
        await db.execute(
            "INSERT INTO promo_redemptions(code,user_id) VALUES(?,?)",
            (code, user_id)
        )
        await db.execute(
            "UPDATE promo_bonuses SET used_count=used_count+1 WHERE code=?",
            (code,)
        )
        await db.commit()
        return amount, "ok"


async def delete_promo_bonus(code):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM promo_bonuses WHERE code=?", (code,))
        await db.commit()


async def get_promo_bonuses():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT code,amount,max_uses,used_count,active,created_at FROM promo_bonuses ORDER BY created_at DESC"
        ) as cur:
            return await cur.fetchall()


async def set_vip(user_id, days):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """INSERT INTO vip_users(user_id,expires_at)
               VALUES(?, datetime('now', ? || ' days'))
               ON CONFLICT(user_id) DO UPDATE SET expires_at=datetime(
                   CASE WHEN vip_users.expires_at > datetime('now')
                        THEN vip_users.expires_at ELSE datetime('now') END,
                   ? || ' days')""",
            (user_id, str(days), str(days))
        )
        await db.commit()


async def is_vip(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT expires_at FROM vip_users WHERE user_id=? AND expires_at > datetime('now')",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def remove_vip(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM vip_users WHERE user_id=?", (user_id,))
        await db.commit()


async def get_vip_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT user_id,expires_at FROM vip_users WHERE expires_at > datetime('now') ORDER BY expires_at"
        ) as cur:
            return await cur.fetchall()


async def create_support_ticket(user_id, message):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "INSERT INTO support_tickets(user_id,message) VALUES(?,?)",
            (user_id, message)
        )
        await db.commit()
        return cur.lastrowid


async def get_open_tickets():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id,user_id,message,created_at FROM support_tickets WHERE status='open' ORDER BY id DESC"
        ) as cur:
            return await cur.fetchall()


async def reply_support_ticket(ticket_id, reply):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM support_tickets WHERE id=?", (ticket_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE support_tickets SET status='closed',admin_reply=?,closed_at=CURRENT_TIMESTAMP WHERE id=?",
            (reply, ticket_id)
        )
        await db.commit()
        return row[0]


async def get_event_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        result = {}
        async with db.execute(
            "SELECT COUNT(*) FROM bot_events WHERE date(created_at)=date('now')"
        ) as cur:
            result["events_today"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM bot_events WHERE event_type IN ('topup','sale_income') AND date(created_at)=date('now')"
        ) as cur:
            result["money_today"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM bot_events WHERE event_type='purchase' AND date(created_at)=date('now')"
        ) as cur:
            result["purchases_today"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM bot_events WHERE event_type='purchase' AND date(created_at)=date('now')"
        ) as cur:
            result["sales_today"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM bot_events WHERE event_type='purchase' AND date(created_at)>=date('now','-6 days')"
        ) as cur:
            result["purchases_week"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM bot_events WHERE event_type='purchase' AND date(created_at)>=date('now','-29 days')"
        ) as cur:
            result["sales_month"] = (await cur.fetchone())[0]
        return result


async def get_user_events(user_id, limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT event_type,amount,category,details,created_at FROM bot_events WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()


async def get_open_tickets_count():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM support_tickets WHERE status='open'") as cur:
            return (await cur.fetchone())[0]


async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO bot_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
# database.py ga qo'shiladigan qism
async def init_sub_db():
  async with aiosqlite.connect(DB_NAME) as conn:
    await conn.execute("""
            CREATE TABLE IF NOT EXISTS mandatory_channels (
                channel_id TEXT PRIMARY KEY,
                channel_name TEXT
            )
        """)
    await conn.commit()


async def get_mandatory_channels():
  async with aiosqlite.connect(DB_NAME) as conn:
    async with conn.execute(
        "SELECT channel_id, channel_name FROM mandatory_channels"
    ) as cursor:
      return await cursor.fetchall()


async def add_mandatory_channel(channel_id: str, channel_name: str):
  async with aiosqlite.connect(DB_NAME) as conn:
    await conn.execute(
        "INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_name)"
        " VALUES (?, ?)",
        (channel_id, channel_name),
    )
    await conn.commit()


async def remove_mandatory_channel(channel_id: str):
  async with aiosqlite.connect(DB_NAME) as conn:
    await conn.execute(
        "DELETE FROM mandatory_channels WHERE channel_id = ?", (channel_id,)
    )
    await conn.commit()
