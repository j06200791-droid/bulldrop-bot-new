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
        await db.commit()


# ===================== MAJBURIY OBUNA =====================
async def init_subscription_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE NOT NULL,
            invite_link TEXT,
            title TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.commit()

_original_init_db_with_sub = init_db
async def _legacy_init_db():
    await _original_init_db_with_sub()
    await init_subscription_db()
    await init_pro_max_db()

async def get_required_channels():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id,chat_id,invite_link,title,active FROM required_channels WHERE active=1 ORDER BY id") as cur:
            return await cur.fetchall()

async def add_required_channel(chat_id, invite_link=None, title=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO required_channels(chat_id,invite_link,title,active) VALUES(?,?,?,1) ON CONFLICT(chat_id) DO UPDATE SET invite_link=excluded.invite_link,title=excluded.title,active=1",
            (str(chat_id).strip(), invite_link, title)
        )
        await db.commit()

async def remove_required_channel(channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM required_channels WHERE id=?", (int(channel_id),))
        await db.commit()

async def toggle_required_channel(enabled):
    await set_setting("required_subscription", "1" if enabled else "0")

async def is_required_subscription_enabled():
    return (await get_setting("required_subscription", "1")) == "1"


# ============================================================
# PRO/MAX UPGRADE
# ============================================================
async def _column_exists(table, column):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(f"PRAGMA table_info({table})") as cur:
            return any(row[1] == column for row in await cur.fetchall())

async def _add_column(table, column, definition):
    if not await _column_exists(table, column):
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            await conn.commit()

async def init_pro_max_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS referrals (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            bonus_paid INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS daily_bonus (
            user_id INTEGER PRIMARY KEY,
            last_claim TEXT,
            streak INTEGER DEFAULT 0
        )""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            target TEXT,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS vip_notifications (
            user_id INTEGER,
            notice_date TEXT,
            PRIMARY KEY(user_id, notice_date)
        )""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS group_members (
            chat_id TEXT,
            user_id INTEGER,
            username TEXT,
            last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id,user_id)
        )""")
        await conn.commit()
    for table, col, definition in [
        ("users", "username", "TEXT"),
        ("users", "first_name", "TEXT"),
        ("users", "last_seen", "TEXT"),
        ("users", "referred_by", "INTEGER"),
        ("vip_users", "discount", "INTEGER DEFAULT 10"),
        ("promo_bonuses", "expires_at", "TEXT"),
        ("promo_bonuses", "target_user_id", "INTEGER"),
    ]:
        await _add_column(table, col, definition)

async def touch_user(user_id, username=None, first_name=None, chat_id=None):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""INSERT INTO users(user_id,username,first_name,last_seen)
            VALUES(?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
            first_name=excluded.first_name,last_seen=CURRENT_TIMESTAMP""",
            (user_id, username, first_name))
        if chat_id is not None:
            await conn.execute("""INSERT INTO group_members(chat_id,user_id,username,last_seen)
                VALUES(?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id,user_id) DO UPDATE SET username=excluded.username,last_seen=CURRENT_TIMESTAMP""",
                (str(chat_id), user_id, username))
        await conn.commit()

async def set_referral(user_id, referrer_id):
    if not referrer_id or int(referrer_id) == int(user_id):
        return False
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT referred_by FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row and row[0]:
            return False
        await conn.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)", (user_id,))
        await conn.execute("UPDATE users SET referred_by=? WHERE user_id=? AND (referred_by IS NULL OR referred_by=0)", (referrer_id, user_id))
        await conn.execute("INSERT OR IGNORE INTO referrals(user_id,referrer_id) VALUES(?,?)", (user_id, referrer_id))
        await conn.commit()
        return True

async def complete_referral_bonus(user_id, amount=500):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT referrer_id,bonus_paid FROM referrals WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row[1]:
            await conn.rollback()
            return 0
        referrer = row[0]
        await conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, referrer))
        await conn.execute("UPDATE referrals SET bonus_paid=1 WHERE user_id=?", (user_id,))
        await conn.commit()
        return referrer

async def get_referral_stats(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)) as cur:
            total = (await cur.fetchone())[0]
        async with conn.execute("SELECT COALESCE(SUM(CASE WHEN bonus_paid=1 THEN 500 ELSE 0 END),0) FROM referrals WHERE referrer_id=?", (user_id,)) as cur:
            earned = (await cur.fetchone())[0]
        return total, earned

async def claim_daily_bonus(user_id, amount=10):
    import datetime as _dt
    today = _dt.datetime.utcnow().date().isoformat()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT last_claim,streak FROM daily_bonus WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row and row[0] == today:
            await conn.rollback()
            return 0, row[1]
        streak = (row[1] + 1) if row and row[0] else 1
        await conn.execute("INSERT INTO daily_bonus(user_id,last_claim,streak) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET last_claim=excluded.last_claim,streak=excluded.streak", (user_id,today,streak))
        await conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount,user_id))
        await conn.commit()
        return amount, streak

async def get_user_level(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM bot_events WHERE user_id=? AND event_type='purchase'", (user_id,)) as cur:
            n = (await cur.fetchone())[0]
    if n >= 100: return 5, '💎 Diamond'
    if n >= 50: return 4, '🏆 Platinum'
    if n >= 20: return 3, '🥇 Gold'
    if n >= 5: return 2, '🥈 Silver'
    return 1, '🥉 Bronze'

async def get_user_profile(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id,username,first_name,balance,banned,last_seen,referred_by FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def get_user_purchase_history(user_id, limit=20):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT category,amount,details,created_at FROM bot_events WHERE user_id=? AND event_type='purchase' ORDER BY id DESC LIMIT ?", (user_id,limit)) as cur:
            return await cur.fetchall()

async def get_user_payment_history(user_id, limit=20):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT token,amount,status FROM payments WHERE user_id=? ORDER BY rowid DESC LIMIT ?", (user_id,limit)) as cur:
            return await cur.fetchall()

async def get_vip_info(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT expires_at,COALESCE(discount,10) FROM vip_users WHERE user_id=? AND expires_at>datetime('now')", (user_id,)) as cur:
            row = await cur.fetchone()
            return row if row else None

async def set_vip_with_discount(user_id, days, discount):
    days, discount = int(days), max(0,min(100,int(discount)))
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""INSERT INTO vip_users(user_id,expires_at,discount) VALUES(?,datetime('now',?||' days'),?)
            ON CONFLICT(user_id) DO UPDATE SET expires_at=datetime(CASE WHEN vip_users.expires_at>datetime('now') THEN vip_users.expires_at ELSE datetime('now') END, ?||' days'),discount=?""",
            (user_id,str(days),discount,str(days),discount))
        await conn.commit()

async def update_vip_discount(user_id, discount):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE vip_users SET discount=? WHERE user_id=?", (int(discount),user_id))
        await conn.commit()

async def get_vip_stats():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM vip_users WHERE expires_at>datetime('now')") as cur:
            users=(await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM bot_events WHERE event_type='purchase' AND details LIKE '%VIP%' AND date(created_at)>=date('now','-29 days')") as cur:
            sales,amount=await cur.fetchone()
        return users,sales,amount

async def create_promo_bonus_pro(code, amount, max_uses=1, expires_at=None, target_user_id=None):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO promo_bonuses(code,amount,max_uses,used_count,active,expires_at,target_user_id) VALUES(?,?,?,0,1,?,?)", (code,int(amount),int(max_uses),expires_at,target_user_id))
        await conn.commit()

async def redeem_promo_bonus_pro(code, user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT amount,max_uses,used_count,active,expires_at,target_user_id FROM promo_bonuses WHERE code=?", (code.strip(),)) as cur:
            row=await cur.fetchone()
        if not row: await conn.rollback(); return None,'not_found'
        amount,max_uses,used,active,expires,target=row
        import datetime as _dt
        if not active or used>=max_uses: await conn.rollback(); return None,'inactive'
        if expires and expires < _dt.datetime.utcnow().isoformat(sep=' '): await conn.rollback(); return None,'expired'
        if target and int(target)!=int(user_id): await conn.rollback(); return None,'not_for_user'
        async with conn.execute("SELECT 1 FROM promo_redemptions WHERE code=? AND user_id=?",(code.strip(),user_id)) as cur:
            if await cur.fetchone(): await conn.rollback(); return None,'already'
        await conn.execute("INSERT INTO promo_redemptions(code,user_id) VALUES(?,?)",(code.strip(),user_id))
        await conn.execute("UPDATE promo_bonuses SET used_count=used_count+1,active=CASE WHEN used_count+1>=max_uses THEN 0 ELSE active END WHERE code=?",(code.strip(),))
        await conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amount,user_id))
        await conn.commit()
        return amount,'ok'

async def credit_payment_once(token, amount):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT user_id,status,amount FROM payments WHERE token=?",(token,)) as cur:
            row=await cur.fetchone()
        if not row or row[1]=='paid':
            await conn.rollback(); return None
        user_id=row[0]
        real_amount=int(amount or row[2])
        await conn.execute("UPDATE payments SET status='paid',amount=? WHERE token=?",(real_amount,token))
        await conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(real_amount,user_id))
        await conn.execute("INSERT INTO bot_events(user_id,event_type,amount,details) VALUES(?,?,?,?)",(user_id,'topup',real_amount,'payment:'+token))
        await conn.commit()
        return user_id

async def set_payment_status(token, status):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE payments SET status=? WHERE token=? AND status!='paid'",(status,token))
        await conn.commit()

async def get_active_users(days=7):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM users WHERE last_seen>=datetime('now',?) AND banned=0",(f'-{int(days)} days',)) as cur:
            return await cur.fetchall()

async def get_vip_user_ids():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM vip_users WHERE expires_at>datetime('now')") as cur:
            return await cur.fetchall()

async def get_group_user_ids(chat_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM group_members WHERE chat_id=?",(str(chat_id),)) as cur:
            return await cur.fetchall()

async def get_admin_dashboard():
    async with aiosqlite.connect(DB_NAME) as conn:
        out={}
        async with conn.execute("SELECT COUNT(*) FROM users") as cur: out['users']=(await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_seen>=datetime('now','-7 days') AND banned=0") as cur: out['active']=(await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM vip_users WHERE expires_at>datetime('now')") as cur: out['vip']=(await cur.fetchone())[0]
        for key, where in [('today',"date(created_at)=date('now')"),('week',"date(created_at)>=date('now','-6 days')"),('month',"date(created_at)>=date('now','-29 days')")]:
            async with conn.execute(f"SELECT COALESCE(SUM(amount),0),COUNT(*) FROM bot_events WHERE event_type='purchase' AND {where}") as cur:
                money,count=await cur.fetchone(); out[key+'_money']=money; out[key+'_sales']=count
        async with conn.execute("SELECT COUNT(*) FROM payments WHERE date(rowid,'unixepoch') IS NOT NULL") as cur:
            out['payments']= (await cur.fetchone())[0]
        return out


async def purchase_code_atomic(user_id, category, price):
    """Atomically reserve one code and charge the user. Returns (code,uploader_id) or None."""
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as cur:
            bal_row=await cur.fetchone()
        if not bal_row or int(bal_row[0]) < int(price):
            await conn.rollback(); return None
        async with conn.execute("SELECT id,code,uploader_id FROM pm_codes WHERE category=? ORDER BY id LIMIT 1", (category,)) as cur:
            row=await cur.fetchone()
        if not row:
            await conn.rollback(); return None
        code_id,code,uploader=row
        await conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(int(price),user_id))
        await conn.execute("DELETE FROM pm_codes WHERE id=?",(code_id,))
        await conn.execute("INSERT INTO bot_events(user_id,event_type,amount,category,details) VALUES(?,?,?,?,?)",(user_id,'purchase',int(price),category,'atomic_purchase'))
        await conn.commit()
        return code,uploader


# --- PUBG UC DATABASE QO'SHIMCHASI ---
async def init_db():
    await _legacy_init_db()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS uc_prices (
            package TEXT PRIMARY KEY,
            price INTEGER NOT NULL
        )""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS uc_redeem_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package TEXT,
            code TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        async with conn.execute("PRAGMA table_info(uc_redeem_codes)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "package" not in cols:
            await conn.execute("ALTER TABLE uc_redeem_codes ADD COLUMN package TEXT")
            if "category" in cols:
                await conn.execute("UPDATE uc_redeem_codes SET package=category WHERE package IS NULL")
        defaults = {"60": 9500, "120": 19000, "240": 38000, "325": 47000, "660": 95000, "1800": 250000, "3850": 500000}
        for package, price in defaults.items():
            await conn.execute("INSERT OR IGNORE INTO uc_prices(package,price) VALUES(?,?)", (package, price))
        await conn.commit()

async def get_uc_prices() -> dict:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT package,price FROM uc_prices ORDER BY CAST(package AS INTEGER)") as cur:
            return {str(r[0]): int(r[1]) for r in await cur.fetchall()}

async def get_uc_count(package: str) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM uc_redeem_codes WHERE package=?", (str(package),)) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

async def purchase_uc_atomic(user_id: int, package: str, price: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or int(row[0]) < int(price):
            await conn.rollback()
            return None
        async with conn.execute("SELECT id,code FROM uc_redeem_codes WHERE package=? ORDER BY id LIMIT 1", (str(package),)) as cur:
            code_row = await cur.fetchone()
        if not code_row:
            await conn.rollback()
            return None
        code_id, code = code_row
        await conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (int(price), user_id))
        await conn.execute("DELETE FROM uc_redeem_codes WHERE id=?", (code_id,))
        await conn.execute("INSERT INTO bot_events(user_id,event_type,amount,category,details) VALUES(?,?,?,?,?)", (user_id, 'purchase', int(price), f'PUBG UC {package}', 'uc_redeem_purchase'))
        await conn.commit()
        return code

async def update_uc_price(package: str, price: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO uc_prices(package,price) VALUES(?,?) ON CONFLICT(package) DO UPDATE SET price=excluded.price", (str(package), int(price)))
        await conn.commit()

async def add_uc_redeem_code(package: str, code: str) -> bool:
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("INSERT INTO uc_redeem_codes(package,code) VALUES(?,?)", (str(package), str(code).strip()))
            await conn.commit()
            return True
    except aiosqlite.IntegrityError:
        return False
