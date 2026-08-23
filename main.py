import os
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

import database as db
# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8938283613:AAH2P8pk2M8LrICkbYT-fo9supIVL6Rlj6U").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "5974947091"))

# SHOP_ID va SHOP_KEY qiymatlarini to'g'ri va ortiqcha bo'shliqlarsiz olish
SHOP_ID = int(os.getenv("PAY_HAMYON_KASSA_ID", "20"))
SHOP_KEY = os.getenv("PAY_HAMYON_KEY", "V04nim0vjY5NGkXtp6qofufRcFB82tT").strip()
BASE_URL = os.getenv("PAY_HAMYON_BASE_URL", "https://user91.hostx.uz").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- PAY HAMYON ASINXRON API FUNKSIYALARI ---

async def send_payhamyon_request(endpoint: str, payload: dict):
    url = f"{BASE_URL}{endpoint}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=15) as resp:
                return await resp.json()
        except Exception as exc:
            return {"success": False, "error": str(exc)}

async def create_payment_api(amount: int, user_id: int):
    payload = {
        "shop_id": SHOP_ID,
        "shop_key": SHOP_KEY.strip(),
        "amount": int(amount),
        "user_id": user_id
    }
    # Universal kassa API yo'llari
    res = await send_payhamyon_request("/api/create", payload)
    if not res.get("status") and not res.get("success"):
        res = await send_payhamyon_request("/api/payment/create", payload)
    return res

async def check_payment_api(token: str):
    payload = {
        "shop_id": SHOP_ID,
        "shop_key": SHOP_KEY.strip(),
        "token": str(token).strip()
    }
    res = await send_payhamyon_request("/api/check", payload)
    if not res.get("status") and not res.get("success"):
        res = await send_payhamyon_request("/api/payment/check", payload)
    return res

async def cancel_payment_api(token: str):
    payload = {
        "shop_id": SHOP_ID,
        "shop_key": SHOP_KEY.strip(),
        "token": str(token).strip()
    }
    return await send_payhamyon_request("/api/payment/cancel", payload)

# --- STATES ---

class TopUpState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_receipt = State()

class AdminPMState(StatesGroup):
    waiting_for_code = State()

class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()

class AdminEditPriceState(StatesGroup):
    waiting_for_category = State()
    waiting_for_new_price = State()

class AdminUserOpState(StatesGroup):
    waiting_for_user_id_add = State()
    waiting_for_amount_add = State()
    waiting_for_user_id_sub = State()
    waiting_for_amount_sub = State()
    waiting_for_user_info = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()

# --- KEYBOARDS ---

def main_menu(user_id: int):
    buttons = [
        [KeyboardButton(text="🎁 Promokod sotib olish")],
        [KeyboardButton(text="💳 Balans"), KeyboardButton(text="💳 Balans to'ldirish")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Admin Menyu")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ PM qo'shish"), KeyboardButton(text="📦 PM qoldiq"), KeyboardButton(text="✏️ PM nomi/narxini o'zgartirish")],
            [KeyboardButton(text="🔑 Kodlar soni"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="💰 Balans +"), KeyboardButton(text="💸 Balans -")],
            [KeyboardButton(text="👤 User ma'lumot"), KeyboardButton(text="🚫 Ban")],
            [KeyboardButton(text="✅ Unban"), KeyboardButton(text="📢 Xabar yuborish")],
            [KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Orqaga")]],
        resize_keyboard=True
    )

async def pm_menu_keyboard():
    prices = await db.get_pm_prices()
    c42 = await db.get_pm_count("42")
    c79 = await db.get_pm_count("79")
    c99 = await db.get_pm_count("99")
    c299 = await db.get_pm_count("299")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 42 lik — {prices.get('42', 0):,} so'm ({c42} ta bor)", callback_data="buy_42")],
        [InlineKeyboardButton(text=f"🎁 79 lik — {prices.get('79', 0):,} so'm ({c79} ta bor)", callback_data="buy_79")],
        [InlineKeyboardButton(text=f"🎁 99 lik — {prices.get('99', 0):,} so'm ({c99} ta bor)", callback_data="buy_99")],
        [InlineKeyboardButton(text=f"🎁 299 lik — {prices.get('299', 0):,} so'm ({c299} ta bor)", callback_data="buy_299")]
    ])

# --- BAN FILTRI ---
@dp.message.outer_middleware()
async def ban_middleware(handler, event, data):
    if isinstance(event, types.Message):
        user_id = event.from_user.id
        if user_id != ADMIN_ID and await db.is_user_banned(user_id):
            await event.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
            return
    return await handler(event, data)

# --- GLOBAL ORQAGA HANDLER ---
@dp.message(F.text == "🔙 Orqaga")
async def global_back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyuga qaytdingiz:", reply_markup=main_menu(message.from_user.id))

# --- BASE HANDLERS ---
@dp.message(Command("start"))
@dp.message(F.text.in_({"⬅️ Bosh menyu", "🏠 Bosh menyu"}))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await db.get_user_balance(message.from_user.id)
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu(message.from_user.id))

@dp.message(F.text == "⚙️ Admin Menyu")
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("Admin panelga xush kelibsiz!", reply_markup=admin_menu_keyboard())

# --- PROMOKOD SOTIB OLISH ---
@dp.message(F.text == "🎁 Promokod sotib olish")
async def show_purchase_rules(message: types.Message):
    rules_text = (
        "❗️ **Muhim xarid qoidasi!**\n\n"
        "📹 Xarid qilish tugmasini bosishdan oldin uzluksiz ekran videosini (Screen Record) yoqing!\n\n"
        "Videoda botdan kod olinishi, nusxalanib (Copy) darhol Bulldrop saytiga qo'yilishi (Paste) va faolllashtirilishi kesilmasdan ko'rinishi shart.\n\n"
        "⚠️ Aks holda \"Ishlamadi\" yoki \"Ishlatilgan\" degan e'tirozlar ko'rib chiqilmaydi va pul qaytarilmaydi."
    )
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ROZIMAN", callback_data="agree_rules")]
    ])
    await message.answer(rules_text, reply_markup=confirm_kb, parse_mode="Markdown")

@dp.callback_query(F.data == "agree_rules")
async def show_pm_list_after_rules(call: types.CallbackQuery):
    kb = await pm_menu_keyboard()
    await call.message.edit_text("Quyidagi tugmalardan birini tanlang:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_pm(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    prices = await db.get_pm_prices()
    price = prices.get(category, 0)
    user_id = call.from_user.id
    
    balance = await db.get_user_balance(user_id)
    if balance < price:
        await call.answer("❌ Hisobingizda mablag' yetarli emas!", show_alert=True)
        return

    stock_count = await db.get_pm_count(category)
    if stock_count <= 0:
        await call.answer("❌ Afsuski, bu toifada hozirda PM qolmagan!", show_alert=True)
        return

    pm_code = await db.buy_pm_code(category)
    if not pm_code:
        await call.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring!", show_alert=True)
        return

    await db.add_user_balance(user_id, -price)
    await call.message.edit_text(f"✅ Xarid muvaffaqiyatli!\n\nSizning promokodingiz:\n`{pm_code}`", parse_mode="Markdown")
    await call.answer("Muvaffaqiyatli xarid qilindi!")

# --- BALANS VA TO'LOV BO'LIMI ---

@dp.message(F.text == "💳 Balans")
async def show_balance(message: types.Message):
    balance = await db.get_user_balance(message.from_user.id)
    await message.answer(f"🆔 Sening Telegram ID'ingiz: `{message.from_user.id}`\nSizning hisobingizda: **{balance:,} so'm**", parse_mode="Markdown")

@dp.message(F.text == "💳 Balans to'ldirish")
async def start_topup(message: types.Message, state: FSMContext):
    await state.set_state(TopUpState.waiting_for_amount)
    text = (
        "💳 **BALANSNI TO'LDIRISH**\n\n"
        "💰 Minimal: **1 000 so'm**\n"
        "💰 Maksimal: **1 000 000 so'm**\n\n"
        "✍️ Summani kiriting:"
    )
    await message.answer(text, reply_markup=back_keyboard(), parse_mode="Markdown")

@dp.message(TopUpState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!", reply_markup=back_keyboard())
        return

    amount = int(message.text)
    if amount < 1000 or amount > 1000000:
        await message.answer("❌ Minimal 1 000 so'm, maksimal 1 000 000 so'm kiritishingiz mumkin!", reply_markup=back_keyboard())
        return

    await state.clear()
    
    method_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ AVTO TO'LOV", callback_data=f"pay_auto_{amount}")],
        [InlineKeyboardButton(text="💳 KARTA (CHEK YUBORISH)", callback_data=f"pay_manual_{amount}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="pay_cancel")]
    ])

    await message.answer(
        f"💳 **TO'LOV USULINI TANLANG**\n\n💰 Summa: **{amount:,} so'm**", 
        reply_markup=method_kb, 
        parse_mode="Markdown"
    )

# 1. AVTO TO'LOV (PayHamyon)
@dp.callback_query(F.data.startswith("pay_auto_"))
async def process_auto_payment(call: types.CallbackQuery):
    amount = int(call.data.split("_")[2])
    user_id = call.from_user.id

    res = await create_payment_api(amount, user_id)

    if not res.get("success") and res.get("status") != "success" and "url" not in res and "link" not in res:
        error_msg = res.get("message", res.get("error", "Noma'lum xatolik"))
        await call.answer(f"❌ To'lov chekini yaratishda xatolik: {error_msg}", show_alert=True)
        return

    pay_url = res.get("url") or res.get("link") or res.get("pay_url")
    token = res.get("token", res.get("invoice_id", "none"))
    card = res.get("card", "9860160602044267")

    if pay_url:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ TO'LASH (PAYHAMYON)", url=pay_url)],
            [InlineKeyboardButton(text="🔄 To'lovni tekshirish", callback_data=f"chk_{token}_{amount}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cnl_{token}")]
        ])
        text = (
            f"⚡️ **AVTO TO'LOV CHEKI TAYYOR**\n\n"
            f"💵 To'lanishi kerak: **{amount:,} so'm**\n\n"
            f"Tugmani bosib to'lovni amalga oshiring va so'ng **To'lovni tekshirish** tugmasini bosing."
        )
    else:
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 To'lovni tekshirish", callback_data=f"chk_{token}_{amount}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cnl_{token}")]
        ])
        text = (
            f"⚡️ **AVTO TO'LOV CHEKI TAYYOR**\n\n"
            f"💳 Karta raqam: `{card}`\n"
            f"💵 To'lanishi kerak: **{amount:,} so'm**\n\n"
            f"Ko'rsatilgan kartaga **{amount:,} so'm** o'tkazing va **To'lovni tekshirish** tugmasini bosing."
        )

    await call.message.edit_text(text, reply_markup=pay_kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("chk_"))
async def check_auto_payment_handler(call: types.CallbackQuery):
    _, token, amount = call.data.split("_")
    amount = int(amount)
    user_id = call.from_user.id

    res = await check_payment_api(token)

    if res.get("success") or res.get("status") in ["paid", "success", 1, True] or res.get("paid") is True:
        await db.add_user_balance(user_id, amount)
        new_bal = await db.get_user_balance(user_id)
        
        await call.message.edit_text(
            f"🎉 **To'lov muvaffaqiyatli qabul qilindi!**\n\n"
            f"Hisobingizga **{amount:,} so'm** qo'shildi.\n"
            f"Hozirgi balansingiz: **{new_bal:,} so'm**",
            parse_mode="Markdown"
        )
        await call.answer("✅ Balans to'ldirildi!", show_alert=True)
    else:
        await call.answer("❌ To'lov hali amalga oshirilmadi yoki topilmadi!", show_alert=True)

@dp.callback_query(F.data.startswith("cnl_"))
async def cancel_auto_payment_handler(call: types.CallbackQuery, state: FSMContext):
    _, token = call.data.split("_")
    if token != "none":
        await cancel_payment_api(token)
    await state.clear()
    await call.message.edit_text("❌ To'lov bekor qilindi.")

# 2. KARTA ORQALI CHEK YUBORISH
@dp.callback_query(F.data.startswith("pay_manual_"))
async def process_manual_payment(call: types.CallbackQuery, state: FSMContext):
    amount = int(call.data.split("_")[2])
    
    await state.set_state(TopUpState.waiting_for_receipt)
    await state.update_data(amount=amount)

    card_text = (
        f"💳 **KARTA ORQALI TO'LOV**\n\n"
        f"To'lovni quyidagi kartaga o'tkazing:\n"
        f"💳 `9860160602044267`\n\n"
        f"Summa: **{amount:,} so'm**\n\n"
        f"📷 To'lovni amalga oshirgach, **chek rasmini (skrinshot)** shu yerga yuboring:"
    )
    await call.message.edit_text(card_text, parse_mode="Markdown")

@dp.callback_query(F.data == "pay_cancel")
async def process_cancel_payment(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ To'lov bekor qilindi.")

@dp.message(TopUpState.waiting_for_receipt)
async def process_receipt(message: types.Message, state: FSMContext):
    if not (message.photo or message.document):
        await message.answer("Iltimos, chek rasmini yuboring!", reply_markup=back_keyboard())
        return

    data = await state.get_data()
    amount = data.get("amount", 1000)
    user_id = message.from_user.id
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{user_id}_{amount}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{user_id}")
        ]
    ])
    
    caption_text = f"📥 **Yangi to'lov cheki!**\n\n👤 User: {message.from_user.full_name} (`{user_id}`)\n💵 Summa: **{amount:,} so'm**"

    if message.photo:
        await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption_text, reply_markup=confirm_kb, parse_mode="Markdown")
    elif message.document:
        await bot.send_document(chat_id=ADMIN_ID, document=message.document.file_id, caption=caption_text, reply_markup=confirm_kb, parse_mode="Markdown")

    await message.answer("✅ Chek qabul qilindi. Admin tasdiqlashini kuting.", reply_markup=main_menu(user_id))
    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    _, user_id, amount = call.data.split("_")
    user_id, amount = int(user_id), int(amount)
    
    await db.add_user_balance(user_id, amount)
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ **TASDIQLANDI**", parse_mode="Markdown")
    await bot.send_message(user_id, f"🎉 To'lovingiz tasdiqlandi! Hisobingizga **{amount:,} so'm** qo'shildi.", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    _, user_id = call.data.split("_")
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ **RAD ETILDI**", parse_mode="Markdown")
    await bot.send_message(int(user_id), "❌ To'lovingiz rad etildi.")

# --- ADMIN PANEL HANDLERLARI ---

@dp.message(F.text == "✏️ PM nomi/narxini o'zgartirish")
async def edit_pm_price_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    prices = await db.get_pm_prices()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ 42 lik"), KeyboardButton(text="✏️ 79 lik")],
            [KeyboardButton(text="✏️ 99 lik"), KeyboardButton(text="✏️ 299 lik")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
    text = f"📊 Hozirgi PM narxlari:\n\n• 42 lik: {prices.get('42', 0):,} so'm\n• 79 lik: {prices.get('79', 0):,} so'm\n• 99 lik: {prices.get('99', 0):,} so'm\n• 299 lik: {prices.get('299', 0):,} so'm"
    await state.set_state(AdminEditPriceState.waiting_for_category)
    await message.answer(text, reply_markup=kb)

@dp.message(AdminEditPriceState.waiting_for_category)
async def process_category_select(message: types.Message, state: FSMContext):
    cat = message.text.replace("✏️ ", "").replace(" lik", "").strip()
    if cat not in ["42", "79", "99", "299"]: return
    await state.update_data(edit_cat=cat)
    await state.set_state(AdminEditPriceState.waiting_for_new_price)
    await message.answer(f"💰 {cat}-lik PM uchun yangi narxni kiriting:", reply_markup=back_keyboard())

@dp.message(AdminEditPriceState.waiting_for_new_price)
async def process_new_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    cat = data.get("edit_cat")
    new_price = int(message.text)
    await db.update_pm_price(cat, new_price)
    await message.answer(f"✅ {cat}-lik PM narxi {new_price:,} so'm ga o'zgartirildi!", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "💰 Balans +")
async def admin_balance_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminUserOpState.waiting_for_user_id_add)
    await message.answer("Telegram ID kiriting:", reply_markup=back_keyboard())

@dp.message(AdminUserOpState.waiting_for_user_id_add)
async def admin_balance_add_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(target_id=int(message.text))
    await state.set_state(AdminUserOpState.waiting_for_amount_add)
    await message.answer("Summani kiriting:", reply_markup=back_keyboard())

@dp.message(AdminUserOpState.waiting_for_amount_add)
async def admin_balance_add_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = int(message.text)
    await db.add_user_balance(target_id, amount)
    await message.answer(f"✅ Balans qo'shildi!", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "💸 Balans -")
async def admin_balance_sub_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminUserOpState.waiting_for_user_id_sub)
    await message.answer("Telegram ID kiriting:", reply_markup=back_keyboard())

@dp.message(AdminUserOpState.waiting_for_user_id_sub)
async def admin_balance_sub_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(target_id=int(message.text))
    await state.set_state(AdminUserOpState.waiting_for_amount_sub)
    await message.answer("Ayiriladigan summani kiriting:", reply_markup=back_keyboard())

@dp.message(AdminUserOpState.waiting_for_amount_sub)
async def admin_balance_sub_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = int(message.text)
    await db.add_user_balance(target_id, -amount)
    await message.answer(f"✅ Balans ayirildi!", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "➕ PM qo'shish")
async def admin_add_pm_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ 42-lik PM"), KeyboardButton(text="➕ 79-lik PM")],
            [KeyboardButton(text="➕ 99-lik PM"), KeyboardButton(text="➕ 299-lik PM")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
    await message.answer("Qaysi toifaga PM qo'shasiz?", reply_markup=kb)

@dp.message(F.text.in_({"➕ 42-lik PM", "➕ 79-lik PM", "➕ 99-lik PM", "➕ 299-lik PM"}))
async def admin_add_pm_category(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    cat = message.text.split("-")[0].replace("➕ ", "")
    await state.update_data(selected_cat=cat)
    await state.set_state(AdminPMState.waiting_for_code)
    await message.answer(f"📥 {cat}-lik uchun PM kodlarini har birini yangi qatordan yozib yuboring:", reply_markup=back_keyboard())

@dp.message(AdminPMState.waiting_for_code)
async def admin_save_pm(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    cat = data.get("selected_cat")
    codes = message.text.strip().split("\n")
    added = 0
    for code in codes:
        if code.strip():
            await db.add_pm_code(cat, code.strip())
            added += 1
    await message.answer(f"✅ {added} ta PM ({cat}-lik) qo'shildi!", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text.in_({"📦 PM qoldiq", "🔑 Kodlar soni", "📊 Statistika"}))
async def show_stats_and_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    users_cnt = await db.get_users_count()
    c42 = await db.get_pm_count("42")
    c79 = await db.get_pm_count("79")
    c99 = await db.get_pm_count("99")
    c299 = await db.get_pm_count("299")
    await message.answer(f"📊 Statistika:\n👤 Foydalanuvchilar: {users_cnt} ta\n\n📦 Qoldiq:\n• 42 lik: {c42} ta\n• 79 lik: {c79} ta\n• 99 lik: {c99} ta\n• 299 lik: {c299} ta")

@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminBroadcastState.waiting_for_message)
    await message.answer("Xabarni yuboring:", reply_markup=back_keyboard())

@dp.message(AdminBroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    users = await db.get_all_users()
    success = 0
    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ {success} ta foydalanuvchiga yuborildi!", reply_markup=admin_menu_keyboard())
    await state.clear()

async def main():
    await db.init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
