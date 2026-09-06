
import asyncio
import logging
import random
import os
import json
import urllib.request
import urllib.error
import time
import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
)
from aiohttp import web

import database as db

# --- CONFIGURATION ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "8938283613:AAH2P8pk2M8LrICkbYT-fo9supIVL6Rlj6U")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5974947091"))

# PayHamyon Sozlamalari
SHOP_ID = int(os.getenv("SHOP_ID", "20"))
SHOP_KEY = os.getenv("SHOP_KEY", "V04nimOvjY5NGkXtp6qofufRcFB82tT")
BASE_URL = os.getenv("PAYHAMYON_BASE_URL", "https://user91.hostx.uz")

# Webhook Server Sozlamalari
WEBHOOK_PATH = "/payhamyon/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))

# Network uzilishlariga chidamli session
session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env orqali berilishi kerak")
if not SHOP_KEY:
    logging.warning("SHOP_KEY .env orqali berilmagan; PayHamyon avto tolovlari ishlamaydi.")


# --- PAYHAMYON API FUNKSIYALARI ---
def send_payhamyon_request(url, payload, retries=3):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            if attempt == retries - 1:
                try:
                    return json.loads(exc.read().decode("utf-8"))
                except Exception:
                    return {"success": False, "error": f"network_error: {str(exc)}"}
            time.sleep(1)
        except Exception as exc:
            if attempt == retries - 1:
                return {"success": False, "error": str(exc)}
            time.sleep(1)

async def async_create_payment(amount: int, callback_url: str = None):
    payload = {
        "shop_id": int(SHOP_ID),
        "shop_key": str(SHOP_KEY).strip(),
        "amount": int(amount),
    }
    if callback_url:
        payload["callback_url"] = callback_url
    return await asyncio.to_thread(send_payhamyon_request, f"{BASE_URL}/api/payment/create", payload)

async def async_check_payment(token: str):
    payload = {
        "shop_id": int(SHOP_ID),
        "shop_key": str(SHOP_KEY).strip(),
        "token": str(token).strip(),
    }
    return await asyncio.to_thread(send_payhamyon_request, f"{BASE_URL}/api/payment/check", payload)


# --- PAYHAMYON WEBHOOK HANDLER ---
async def payhamyon_webhook_handler(request: web.Request):
    try:
        data = await request.json()
        
        event = data.get("event")
        status = data.get("status")
        token = data.get("token")
        
        if (event == "payment.paid" or status in ["paid", "success"]) and token:
            check_res = await async_check_payment(token)
            
            if check_res.get("success") and check_res.get("status") in ["paid", "completed", "success"]:
                amount = check_res.get("amount") or check_res.get("pay_amount") or data.get("amount")
                user_id = await db.get_user_id_by_token(token) if hasattr(db, "get_user_id_by_token") else None
                
                if user_id and amount:
                    credited_user = await db.credit_payment_once(token, int(amount)) if hasattr(db, "credit_payment_once") else None
                    if not credited_user:
                        return web.json_response({"status": "ok"}, status=200)
                    user_id = credited_user
                        
                    new_bal = await db.get_user_balance(user_id)
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚡ **Avto to'lov qabul qilindi!**\n\n"
                            f"💳 Hisobingizga **{int(amount):,} so'm** qo'shildi.\n"
                            f"💰 Hozirgi balansingiz: **{new_bal:,} so'm**",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
        
        return web.json_response({"status": "ok"}, status=200)
    except Exception as e:
        logging.error(f"Webhook xatoligi: {e}")
        return web.json_response({"status": "error"}, status=400)


# --- FSM STATES ---
class TopUpState(StatesGroup):
    waiting_for_auto_amount = State()
    waiting_for_manual_amount = State()
    waiting_for_receipt = State()


class AdminPMState(StatesGroup):
    waiting_for_code = State()


class UserAddPMState(StatesGroup):
    waiting_for_category = State()
    waiting_for_code = State()


class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()


class AdminEditPriceState(StatesGroup):
    waiting_for_category = State()
    waiting_for_new_price = State()


class AdminEditUserSellPriceState(StatesGroup):
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

#  KeyboardButton(text="➕ Promokod sotish")]
# --- KEYBOARDS ---
def main_menu(user_id: int):
    buttons = [
        [KeyboardButton(text="🎁 Promokod sotib olish"),],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="💳 Balans to'ldirish")],
        [KeyboardButton(text="🎟️ Bonus kod"), KeyboardButton(text="🛒 Xaridlarim")],
        [KeyboardButton(text="💳 To'lovlarim"), KeyboardButton(text="🤝 Referral")],
        [KeyboardButton(text="🎁 Kunlik bonus"), KeyboardButton(text="🏆 Reyting")],
       
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Admin Menyu")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def topup_methods_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Avto to'ldirish", callback_data="pay_auto")],
            [InlineKeyboardButton(text="👨‍💻 Admin yordamida", callback_data="pay_admin")]
        ]
    )


def admin_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 USERLAR"), KeyboardButton(text="💰 BALANS")],
            [KeyboardButton(text="🛒 SAVDO"), KeyboardButton(text="💳 TO'LOVLAR")],
            [KeyboardButton(text="📦 QOLDIQ"), KeyboardButton(text="🎁 PROMO")],
            [KeyboardButton(text="🎫 SUPPORT"), KeyboardButton(text="📢 REKLAMA")],
            [KeyboardButton(text="📊 STATISTIKA"), KeyboardButton(text="📝 LOG")],
            [KeyboardButton(text="⚙️ SOZLAMALAR"), KeyboardButton(text="🛡️ XAVFSIZlik")],
            [KeyboardButton(text="📢 Majburiy obuna"), KeyboardButton(text="➕ PM qo'shish")],
            [KeyboardButton(text="✏️ PM narxini o'zgartirish"), KeyboardButton(text="🏷️ Foydalanuvchi sotish narxi")],
            [KeyboardButton(text="📈 Daromad"), KeyboardButton(text="🔎 User qidirish")],
            [KeyboardButton(text="💰 Balans +"), KeyboardButton(text="💸 Balans -")],
            [KeyboardButton(text="🚫 Ban"), KeyboardButton(text="✅ Unban")],
            [KeyboardButton(text="👤 User ma'lumot"), KeyboardButton(text="⬅️ Bosh menyu")]
        ], resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Orqaga")]],
        resize_keyboard=True
    )


async def pm_menu_keyboard(user_id: int = None):
    prices = await db.get_pm_prices()
    default_prices = {"24": 1500, "49": 3500, "99": 9000, "149": 16000, "179": 18000, "199": 21000}
    stock = {cat: await db.get_pm_count(cat) for cat in default_prices}
    rows = []
    for cat, base in default_prices.items():
        base = prices.get(cat, base)
        final = base
        # Qoldiq 0 bo'lsa ham kategoriya ko'rinadi: "(0 ta bor)".
        label = f"🎁 {cat} lik — {final:,} so'm ({stock[cat]} ta bor)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy_{cat}")])
    if not rows:
        rows.append([InlineKeyboardButton(text="❌ Hozircha PM qolmagan", callback_data="no_stock")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def user_sell_menu_keyboard():
    user_sell_prices = await db.get_user_sell_prices() if hasattr(db, "get_user_sell_prices") else {}
    default_sell_prices = {"24": 1000, "49": 2500, "99": 7000, "149": 13000, "179": 15000, "199": 18000}

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 24 lik — {user_sell_prices.get('24', default_sell_prices['24']):,} so'm — Sotish", callback_data="sellcat_24")],
        [InlineKeyboardButton(text=f"🎁 49 lik — {user_sell_prices.get('49', default_sell_prices['49']):,} so'm — Sotish", callback_data="sellcat_49")],
        [InlineKeyboardButton(text=f"🎁 99 lik — {user_sell_prices.get('99', default_sell_prices['99']):,} so'm — Sotish", callback_data="sellcat_99")],
        [InlineKeyboardButton(text=f"🎁 149 lik — {user_sell_prices.get('149', default_sell_prices['149']):,} so'm — Sotish", callback_data="sellcat_149")],
        [InlineKeyboardButton(text=f"🎁 179 lik — {user_sell_prices.get('179', default_sell_prices['179']):,} so'm — Sotish", callback_data="sellcat_179")],
        [InlineKeyboardButton(text=f"🎁 199 lik — {user_sell_prices.get('199', default_sell_prices['199']):,} so'm — Sotish", callback_data="sellcat_199")]
    ])


# ===================== MAJBURIY OBUNA =====================
def _channel_join_url(chat_id, invite_link=None):
    if invite_link:
        return invite_link
    value = str(chat_id).strip()
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    return None

async def _subscription_check(user_id: int):
    if user_id == ADMIN_ID:
        return True, []
    if not await db.is_required_subscription_enabled():
        return True, []
    channels = await db.get_required_channels()
    if not channels:
        return True, []
    missing = []
    for row in channels:
        cid, chat_id, invite_link, title, active = row
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            is_member = member.status in ("member", "administrator", "creator")
            if member.status == "restricted" and getattr(member, "is_member", False):
                is_member = True
            if not is_member:
                missing.append(row)
        except Exception as exc:
            logging.warning("Majburiy obuna tekshiruvi xatosi %s: %s", chat_id, exc)
            missing.append(row)
    return len(missing) == 0, missing

def _subscription_keyboard(missing):
    rows = []
    for row in missing:
        _, chat_id, invite_link, title, _ = row
        url = _channel_join_url(chat_id, invite_link)
        label = f"📢 {title or chat_id}"
        if url:
            rows.append([InlineKeyboardButton(text=label, url=url)])
    rows.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def _send_subscription_required(message_or_call):
    user_id = message_or_call.from_user.id
    ok, missing = await _subscription_check(user_id)
    if ok:
        return True
    text = (
        "🔒 **Botdan foydalanish uchun majburiy obuna**\n\n"
        "Quyidagi kanallarga obuna bo'ling, so'ng `✅ Obunani tekshirish` tugmasini bosing."
    )
    if isinstance(message_or_call, types.CallbackQuery):
        try:
            await message_or_call.message.edit_text(text, reply_markup=_subscription_keyboard(missing), parse_mode="Markdown")
        except Exception:
            await message_or_call.message.answer(text, reply_markup=_subscription_keyboard(missing), parse_mode="Markdown")
        await message_or_call.answer("Avval kanallarga obuna bo'ling.", show_alert=True)
    else:
        await message_or_call.answer(text, reply_markup=_subscription_keyboard(missing), parse_mode="Markdown")
    return False

# --- MIDDLEWARES ---
@dp.message.outer_middleware()
async def ban_middleware(handler, event, data):
    if isinstance(event, types.Message):
        user_id = event.from_user.id
        if user_id != ADMIN_ID and await db.is_user_banned(user_id):
            await event.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
            return
        if hasattr(db, "touch_user"):
            await db.touch_user(user_id, event.from_user.username, event.from_user.first_name, event.chat.id)
        if user_id != ADMIN_ID and await db.get_setting("maintenance_mode", "0") == "1":
            await event.answer("🛠 Bot vaqtincha texnik xizmatda. Iltimos, keyinroq urinib ko'ring.")
            return
        if user_id != ADMIN_ID and event.text != "🔙 Orqaga":
            if not await _send_subscription_required(event):
                return
    return await handler(event, data)

@dp.callback_query.outer_middleware()
async def subscription_callback_middleware(handler, event, data):
    if isinstance(event, types.CallbackQuery) and event.from_user.id != ADMIN_ID:
        if event.data == "check_subscription":
            return await handler(event, data)
        if not await _send_subscription_required(event):
            return
    return await handler(event, data)


@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(call: types.CallbackQuery):
    ok, missing = await _subscription_check(call.from_user.id)
    if ok:
        await call.message.edit_text("✅ **Obuna tasdiqlandi!**\n\nEndi botdan foydalanishingiz mumkin.", parse_mode="Markdown")
        await call.answer("Obuna tasdiqlandi!", show_alert=True)
        await bot.send_message(call.from_user.id, "🏠 Bosh menyu", reply_markup=main_menu(call.from_user.id))
    else:
        names = []
        for row in missing:
            names.append(str(row[3] or row[1]))
        detail = "\n".join(f"• {name}" for name in names[:5])
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmagansiz.", show_alert=True)
        try:
            await call.message.edit_text(
                "🔒 **Obuna hali tasdiqlanmadi**\n\n"
                "Quyidagi kanal(lar)ga obuna bo'ling va qaytadan tekshiring:\n" + detail,
                reply_markup=_subscription_keyboard(missing),
                parse_mode="Markdown"
            )
        except Exception:
            try:
                await call.message.edit_reply_markup(reply_markup=_subscription_keyboard(missing))
            except Exception:
                pass

# --- GLOBAL HANDLERS ---
@dp.message(F.text == "🔙 Orqaga")
async def global_back_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()
    
    if current_state and current_state.startswith("Admin"):
        await message.answer("Admin panelga qaytdingiz:", reply_markup=admin_menu_keyboard())
        return

    await message.answer("Bosh menyuga qaytdingiz:", reply_markup=main_menu(message.from_user.id))


@dp.message(Command("start"))
@dp.message(F.text.in_({"⬅️ Bosh menyu", "🏠 Bosh menyu"}))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await db.get_user_balance(uid)
    if hasattr(db, "touch_user"):
        await db.touch_user(uid, message.from_user.username, message.from_user.first_name, message.chat.id)
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[0].startswith("/start"):
        ref = parts[1].strip().replace("ref_", "")
        if ref.isdigit() and int(ref) != uid and hasattr(db, "set_referral"):
            if await db.set_referral(uid, int(ref)):
                await message.answer("🤝 Referral orqali qo'shildingiz! Do'stingiz bonus oladi.")
    notice = await db.get_setting("bot_notice", "") if hasattr(db,"get_setting") else ""
    await message.answer((notice + "\n\n" if notice else "") + "Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu(uid))


@dp.message(F.text == "⚙️ Admin Menyu")
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("Admin panelga xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=admin_menu_keyboard())


# --- USER: PROMOKOD SOTIB OLISH ---
@dp.message(F.text == "🎁 Promokod sotib olish")
async def show_purchase_rules(message: types.Message):
    rules_text = (
        "❗️ Muhim xarid qoidasi!\n\n"
        "📹 Xarid qilish tugmasini bosishdan oldin uzluksiz ekran videosini (Screen Record) yoqing!\n\n"
        "Videoda botdan kod olinishi, nusxalanib (Copy) darhol Bulldrop saytiga qo'yilishi (Paste) va faollashtirilishi kesilmasdan ko'rinishi shart.\n\n"
        "⚠️ Aks holda 'ishlamadi' yoki 'ishlatilgan' degan e'tirozlar ko'rib chiqilmaydi va pul qaytarilmaydi.\n\n"
        "👇 Qoidaga rozilik bildirsangiz, quyidagi tugmani bosing:"
    )
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ROZIMAN", callback_data="agree_rules")]
    ])
    await message.answer(rules_text, reply_markup=confirm_kb)


@dp.callback_query(F.data == "agree_rules")
async def show_pm_list_after_rules(call: types.CallbackQuery):
    kb = await pm_menu_keyboard(call.from_user.id)
    await call.message.edit_text("Quyidagi tugmalardan birini tanlang:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "no_stock")
async def no_stock(call: types.CallbackQuery):
    await call.answer("Hozircha PM qoldiq yo'q.", show_alert=True)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_pm(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    prices = await db.get_pm_prices()
    default_prices = {"24": 1500, "49": 3500, "99": 9000, "149": 16000, "179": 18000, "199": 21000}
    base_price = prices.get(category, default_prices.get(category, 0))
    
    user_id = call.from_user.id
    price = base_price
    balance = await db.get_user_balance(user_id)
    
    if balance < price:
        await call.answer("❌ Hisobingizda mablag' yetarli emas!", show_alert=True)
        return

    stock_count = await db.get_pm_count(category)
    if stock_count <= 0:
        await call.answer("❌ Afsuski, bu toifada PM qolmagan!", show_alert=True)
        return

    pm_data = await db.purchase_code_atomic(user_id, category, price) if hasattr(db, "purchase_code_atomic") else None
    if not pm_data:
        balance_now = await db.get_user_balance(user_id)
        if balance_now < price:
            await call.answer("❌ Hisobingizda mablag' yetarli emas!", show_alert=True)
        else:
            await call.answer("❌ Kod tugagan yoki xarid band qilingan. Qayta urinib ko'ring!", show_alert=True)
        return

    pm_code, uploader_id = pm_data
    
    if uploader_id and uploader_id != ADMIN_ID:
        user_sell_prices = await db.get_user_sell_prices() if hasattr(db, "get_user_sell_prices") else {}
        default_sell_prices = {"24": 1000, "49": 2500, "99": 7000, "149": 13000, "179": 15000, "199": 18000}
        earned_amount = user_sell_prices.get(category, default_sell_prices.get(category, 1000))
        
        try:
            await bot.send_message(
                uploader_id,
                f"🎉 **Tabriklaymiz! Siz sotuvga qo'ygan promokod sotildi!**\n\n"
                f"📦 Toifa: `{category} PM`\n"
                f"💰 Sizga beriladigan summa: **{earned_amount:,} so'm**\n\n"
                f"⚠️ Admin tez orada sizdan karta raqamini so'raydi va pulingizni o'tkazib beradi!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        try:
            sotuvchi_str = f"ID: `{uploader_id}`"
            try:
                chat_member = await bot.get_chat(uploader_id)
                if chat_member.username:
                    sotuvchi_str = f"@{chat_member.username}"
                elif chat_member.first_name:
                    sotuvchi_str = f"[{chat_member.first_name}](tg://user?id={uploader_id})"
            except Exception:
                pass

            await bot.send_message(
                ADMIN_ID,
                f"🚨 **Foydalanuvchi promokodi sotildi!**\n\n"
                f"📦 Toifa: `{category} PM`\n"
                f"👤 Sotuvchi: {sotuvchi_str}\n"
                f"💰 To'lanishi kerak bo'lgan summa: **{earned_amount:,} so'm**\n\n"
                f"💳 Iltimos, foydalanuvchidan karta raqamini so'rab pulini o'tkazib bering!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Adminga xabar yuborishda xatolik: {e}")

    try:
        ref_bonus = int(await db.get_setting("referral_bonus", "500"))
        referrer_id = await db.complete_referral_bonus(user_id, ref_bonus) if ref_bonus > 0 else 0
        if referrer_id:
            await db.log_event(referrer_id, 'referral_bonus', ref_bonus, details=f'referred_user={user_id}')
            try:
                await bot.send_message(referrer_id, f"🤝 Referral bonusi: **+{ref_bonus:,} so'm**", parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        logging.exception("Referral bonus error")

    cashback_percent = int(await db.get_setting("cashback_percent", "0")) if hasattr(db,"get_setting") else 0
    cashback = round(price * cashback_percent / 100)
    if cashback > 0:
        await db.add_user_balance(user_id, cashback)
        await db.log_event(user_id, 'cashback', cashback, category)

    success_text = (
        "✅ Xarid muvaffaqiyatli amalga oshirildi!\n\n"
        f"Sizning {category} PM promokodingiz:\n"
        f"`{pm_code}`"
        + (f"\n\n💸 Cashback: **+{cashback:,} so'm**" if cashback > 0 else "")
    )
    await call.message.edit_text(success_text, parse_mode="Markdown")
    await call.answer("Muvaffaqiyatli xarid qilindi!")


# --- USER: PROMOKOD SOTISH ---
@dp.message(F.text == "➕ Promokod sotish")
async def user_add_pm_warning(message: types.Message):
    warning_text = (
        "⚠️ **MUHIM ESLATMA**\n\n"
        "• PROMODINGIZ SOTILISHI BILAN ADMIN SIZDAN KARTA SO'RAYDI.\n"
        "• Promokingiz ishlatilgan chiqsa pul berilmaydi!\n"
        "• Yana kattaroq PM ga kichik PM qo'ysangiz, unda ham pulingiz qaytarib berilmaydi!\n\n"
        "Qoidaga rozimisiz?"
    )
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Roziman", callback_data="agree_sell_rules")]
    ])
    await message.answer(warning_text, reply_markup=confirm_kb, parse_mode="Markdown")


@dp.callback_query(F.data == "agree_sell_rules")
async def user_add_pm_menu(call: types.CallbackQuery, state: FSMContext):
    kb = await user_sell_menu_keyboard()
    info_text = (
        "📥 **Promokod sotish bo'limi**\n\n"
        "Quyidagi tugmalardan o'zingiz sotmoqchi bo'lgan promokod turini tanlang"
    )
    await state.set_state(UserAddPMState.waiting_for_category)
    await call.message.edit_text(info_text, reply_markup=kb, parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data.startswith("sellcat_"))
async def user_select_sell_category(call: types.CallbackQuery, state: FSMContext):
    cat = call.data.split("_")[1]
    await state.update_data(selected_cat=cat)
    await state.set_state(UserAddPMState.waiting_for_code)
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Orqaga")]],
        resize_keyboard=True
    )
    await call.message.answer(
        f"📥 **{cat} PM** kodlarini yuboring.\n"
        f"(Bir nechta bo'lsa, har birini yangi qatordan yozing):",
        reply_markup=cancel_kb,
        parse_mode="Markdown"
    )
    await call.answer()


@dp.message(UserAddPMState.waiting_for_code)
async def user_save_pm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("selected_cat")
    codes = message.text.strip().split("\n")
    user_id = message.from_user.id
    
    added_count = 0
    for code in codes:
        if code.strip():
            if hasattr(db, "add_user_pm_code_with_owner"):
                await db.add_user_pm_code_with_owner(cat, code.strip(), user_id)
            else:
                await db.add_pm_code(cat, code.strip())
            added_count += 1
            
    await message.answer(
        f"✅ {added_count} ta {cat} PM muvaffaqiyatli qabul qilindi va bazaga qo'shildi!\n"
        f"🔍 Kodlar sotilgandan so'ng sizga xabar keladi va admin karta so'raydi.",
        reply_markup=main_menu(user_id)
    )
    await state.clear()


# --- ADMIN: FOYDALANUVCHIDAN SOTIB OLish NARXINI SOZLASH ---
@dp.message(F.text == "🏷️ Foydalanuvchi sotish narxi")
async def edit_user_sell_price_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_sell_prices = await db.get_user_sell_prices() if hasattr(db, "get_user_sell_prices") else {}
    default_sell_prices = {"24": 1000, "49": 2500, "99": 7000, "149": 13000, "179": 15000, "199": 18000}
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏷️ 24 PM narxi"), KeyboardButton(text="🏷️ 49 PM narxi")],
            [KeyboardButton(text="🏷️ 99 PM narxi"), KeyboardButton(text="🏷️ 149 PM narxi")],
            [KeyboardButton(text="🏷️ 179 PM narxi"), KeyboardButton(text="🏷️ 199 PM narxi")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
    
    text = (
        "🏷️ **Foydalanuvchilar olib keladigan PM uchun to'lov narxlari:**\n\n"
        f"• 24 PM: {user_sell_prices.get('24', default_sell_prices['24']):,} so'm\n"
        f"• 49 PM: {user_sell_prices.get('49', default_sell_prices['49']):,} so'm\n"
        f"• 99 PM: {user_sell_prices.get('99', default_sell_prices['99']):,} so'm\n"
        f"• 149 PM: {user_sell_prices.get('149', default_sell_prices['149']):,} so'm\n"
        f"• 179 PM: {user_sell_prices.get('179', default_sell_prices['179']):,} so'm\n"
        f"• 199 PM: {user_sell_prices.get('199', default_sell_prices['199']):,} so'm\n\n"
        "Qaysi toifadagi foydalanuvchi narxini o'zgartirmoqchisiz?"
    )
    await state.set_state(AdminEditUserSellPriceState.waiting_for_category)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@dp.message(AdminEditUserSellPriceState.waiting_for_category)
async def process_user_sell_category_select(message: types.Message, state: FSMContext):
    cat = message.text.replace("🏷️ ", "").replace(" PM narxi", "").strip()
    if cat not in ["24", "49", "99", "149", "179", "199"]:
        await message.answer("Iltimos, tugmalardan birini tanlang!")
        return

    await state.update_data(edit_cat=cat)
    await state.set_state(AdminEditUserSellPriceState.waiting_for_new_price)
    await message.answer(f"💰 {cat} PM uchun foydalanuvchiga to'lanadigan yangi narxni kiriting (so'mda):", reply_markup=back_keyboard())


@dp.message(AdminEditUserSellPriceState.waiting_for_new_price)
async def process_user_sell_new_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return

    data = await state.get_data()
    cat = data.get("edit_cat")
    new_price = int(message.text)

    if hasattr(db, "update_user_sell_price"):
        await db.update_user_sell_price(cat, new_price)
        
    await message.answer(f"✅ {cat} PM uchun foydalanuvchi sotish narxi {new_price:,} so'm etib belgilandi!", reply_markup=admin_menu_keyboard())
    await state.clear()


# --- QO'SHIMCHA ADMIN FSM ---
class AdminExtraState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_promo_delete = State()
    waiting_for_ticket_reply = State()
    waiting_for_promo_code = State()
    waiting_for_promo_amount = State()
    waiting_for_promo_uses = State()
    waiting_for_promo_expiry = State()
    waiting_for_promo_target = State()
    waiting_for_ticket_id = State()
    waiting_for_setting = State()
    waiting_for_setting_value = State()
    waiting_for_required_channel = State()
    waiting_for_required_remove = State()
    waiting_for_broadcast_target = State()
    waiting_for_broadcast_message = State()
    waiting_for_maintenance = State()
    waiting_for_cashback = State()
    waiting_for_referral_bonus = State()

class UserExtraState(StatesGroup):
    waiting_for_bonus_code = State()
    waiting_for_support_message = State()


# ============================================================
# PRO/MAX USER FEATURES
# ============================================================
@dp.message(F.text == "👤 Profil")
async def user_profile(message: types.Message):
    uid = message.from_user.id
    p = await db.get_user_profile(uid) if hasattr(db,"get_user_profile") else None
    level, name = await db.get_user_level(uid) if hasattr(db,"get_user_level") else (1,'Bronze')
    refs = await db.get_referral_stats(uid) if hasattr(db,"get_referral_stats") else (0,0)
    username = message.from_user.username or "yo'q"
    # HTML ishlatiladi: username ichidagi _ kabi belgilar Telegram Markdown parserini buzmaydi.
    await message.answer(
        f"👤 <b>PROFIL</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{username}\n"
        f"💰 Balans: <b>{(p[3] if p else 0):,} so'm</b>\n"
        f"🏆 Level: <b>{level} — {name}</b>\n"
        f"🤝 Referallar: <b>{refs[0]} ta</b>\n"
        f"💵 Referral bonusi: <b>{refs[1]:,} so'm</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "🛒 Xaridlarim")
async def user_purchase_history(message: types.Message):
    rows = await db.get_user_purchase_history(message.from_user.id)
    text = "🛒 **XARIDLARIM**\n\n" + ("\n".join([f"• {r[3]} — {r[0]} PM — {r[1]:,} so'm" for r in rows]) or "Hali xarid yo'q.")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 To'lovlarim")
async def user_payment_history(message: types.Message):
    rows = await db.get_user_payment_history(message.from_user.id)
    text = "💳 **TO'LOVLARIM**\n\n" + ("\n".join([f"• {r[1]:,} so'm — {r[2]} — `{r[0]}`" for r in rows]) or "Hali to'lov yo'q.")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🤝 Referral")
async def user_referral(message: types.Message):
    uid = message.from_user.id
    total, earned = await db.get_referral_stats(uid)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await message.answer(
        f"🤝 **REFERRAL**\n\n"
        f"👥 Taklif qilganlaringiz: **{total} ta**\n"
        f"💰 Ishlangan bonus: **{earned:,} so'm**\n\n"
        f"🔗 Sizning linkingiz:\n`{link}`\n\n"
        f"Do'stingiz botga kirganda referral hisoblanadi.",
        parse_mode="Markdown"
    )

@dp.message(F.text == "🎁 Kunlik bonus")
async def daily_bonus(message: types.Message):
    amount, streak = await db.claim_daily_bonus(message.from_user.id)
    if amount:
        await message.answer(f"🎁 **Kunlik bonus olindi!**\n\n💰 +{amount:,} so'm\n🔥 Streak: {streak} kun")
    else:
        await message.answer(f"⏳ Bugungi bonusni allaqachon olgansiz.\n🔥 Streak: {streak} kun")

@dp.message(F.text == "🏆 Reyting")
async def leaderboard(message: types.Message):
    async with db.aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT user_id,COUNT(*) n FROM bot_events WHERE event_type='purchase' GROUP BY user_id ORDER BY n DESC LIMIT 10") as cur:
            rows = await cur.fetchall()
    text = "🏆 **TOP 10 XARIDOR**\n\n" + ("\n".join([f"{i}. `{r[0]}` — {r[1]} ta xarid" for i, r in enumerate(rows, 1)]) or "Ma'lumot yo'q.")
    await message.answer(text, parse_mode="Markdown")


# ============================================================
# PRO/MAX ADMIN MENUS
# ============================================================
@dp.message(F.text == "👤 USERLAR")
async def admin_users_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    s = await db.get_admin_dashboard()
    await message.answer(
        f"👤 **USERLAR**\n\n👥 Jami: {s['users']}\n🟢 Faol (7 kun): {s['active']}\n🚫 Banlar boshqaruvi eski panelda mavjud.\n\n🔎 User qidirish uchun: **User qidirish** tugmasi.",
        parse_mode="Markdown", reply_markup=admin_menu_keyboard()
    )

@dp.message(F.text == "💰 BALANS")
async def admin_balance_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("💰 **BALANS BOSHQARUVI**\n\nBalans qo'shish/ayirish uchun eski `💰 Balans +` va `💸 Balans -` funksiyalari ishlaydi.", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

@dp.message(F.text == "🛒 SAVDO")
async def admin_sales_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await admin_sales_history(message)

@dp.message(F.text == "💳 TO'LOVLAR")
async def admin_payments_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await admin_payment_history(message)

@dp.message(F.text == "📦 QOLDIQ")
async def admin_stock_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await show_stats_and_stock(message)

@dp.message(F.text == "🎁 PROMO")
async def admin_promo_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await admin_promo_menu(message)

@dp.message(F.text == "🎫 SUPPORT")
async def admin_support_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await admin_support_list(message)

@dp.message(F.text == "📊 STATISTIKA")
async def admin_stats_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    s = await db.get_admin_dashboard()
    stocks = {c: await db.get_pm_count(c) for c in ['24','49','99','149','179','199']}
    await message.answer(
        f"📊 **BOT STATISTIKASI**\n\n"
        f"👤 Userlar: {s['users']}\n🟢 Faol: {s['active']}\n\n"
        f"💰 Bugungi daromad: {s['today_money']:,} so'm\n📅 Haftalik: {s['week_money']:,} so'm\n📆 Oylik: {s['month_money']:,} so'm\n\n"
        f"🛒 Bugungi savdo: {s['today_sales']}\n\n"
        f"📦 PM qoldiq:\n" + "\n".join([f"{c} PM — {n}" for c, n in stocks.items()]),
        parse_mode="Markdown", reply_markup=admin_menu_keyboard()
    )

@dp.message(F.text == "📝 LOG")
async def admin_log_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID: await admin_log(message)

@dp.message(F.text == "🛡️ XAVFSIZlik")
async def admin_security_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    maint = await db.get_setting("maintenance_mode","0")
    cashback = await db.get_setting("cashback_percent","0")
    ref = await db.get_setting("referral_bonus","500")
    await message.answer(
        f"🛡️ **XAVFSIZLIK**\n\n"
        f"🔐 Admin ID tekshiruvi: 🟢\n💳 Payment duplicate himoyasi: 🟢\n🗃 SQL parametrizatsiyasi: 🟢\n💾 SQLite saqlash: 🟢\n"
        f"🛠 Maintenance: {'🟢 ON' if maint=='1' else '🔴 OFF'}\n💸 Cashback: {cashback}%\n🤝 Referral bonusi: {ref} so'm",
        parse_mode="Markdown", reply_markup=admin_menu_keyboard()
    )

@dp.message(F.text == "📢 REKLAMA")
async def admin_broadcast_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📢 Barchaga")],[KeyboardButton(text="🟢 Faol userlar"), KeyboardButton(text="👥 Guruh ID bo'yicha")],[KeyboardButton(text="🔙 Orqaga")]], resize_keyboard=True)
    await message.answer("📢 **REKLAMA**\n\nKimga yuborishni tanlang:", parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text.in_({"📢 Barchaga","🟢 Faol userlar","👥 Guruh ID bo'yicha"}))
async def admin_broadcast_target(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    target = message.text
    if target == "👥 Guruh ID bo'yicha":
        await state.update_data(broadcast_target='group')
        await message.answer("Guruh chat ID sini yuboring (masalan: -100...):", reply_markup=back_keyboard())
        await state.set_state(AdminExtraState.waiting_for_broadcast_target)
        return
    mapping = {"📢 Barchaga": "all", "🟢 Faol userlar": "active"}
    await state.update_data(broadcast_target=mapping[target])
    await state.set_state(AdminExtraState.waiting_for_broadcast_message)
    await message.answer("📨 Yuboriladigan xabarni yuboring:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_broadcast_target)
async def admin_broadcast_group_id(message: types.Message, state: FSMContext):
    if not message.text.lstrip('-').isdigit():
        await message.answer("❌ Guruh ID noto'g'ri.")
        return
    await state.update_data(broadcast_group=message.text)
    await state.set_state(AdminExtraState.waiting_for_broadcast_message)
    await message.answer("📨 Endi reklama xabarini yuboring:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_broadcast_message)
async def admin_broadcast_pro(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    target = data.get('broadcast_target','all')
    if target == 'all': ids = await db.get_all_users()
    elif target == 'active': ids = await db.get_active_users(7)
    else: ids = await db.get_group_user_ids(data.get('broadcast_group'))
    sent = failed = 0
    for (uid,) in ids:
        try:
            await message.copy_to(uid)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await db.log_admin_action(ADMIN_ID,'broadcast',details=f'{target}: sent={sent}, failed={failed}')
    await message.answer(f"📢 **Reklama yakunlandi**\n\n✅ Yetib bordi: {sent}\n❌ Yetib bormadi: {failed}", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "⚙️ SOZLAMALAR")
async def admin_settings_max(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    maint = await db.get_setting('maintenance_mode','0')
    cashback = await db.get_setting('cashback_percent','0')
    ref = await db.get_setting('referral_bonus','500')
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛠 Maintenance ON/OFF")],[KeyboardButton(text="💸 Cashback %")],[KeyboardButton(text="🤝 Referral bonus")],[KeyboardButton(text="📝 Bot xabari")],[KeyboardButton(text="👨‍💻 Support nomi")],[KeyboardButton(text="🔗 Support username")],[KeyboardButton(text="🔙 Orqaga")]], resize_keyboard=True)
    await message.answer(f"⚙️ **SOZLAMALAR**\n\n🛠 Maintenance: {'ON' if maint=='1' else 'OFF'}\n💸 Cashback: {cashback}%\n🤝 Referral bonus: {ref} so'm", parse_mode='Markdown', reply_markup=kb)

@dp.message(F.text == "👨‍💻 Support nomi")
async def support_name_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.update_data(setting_key="support_name")
    await state.set_state(AdminExtraState.waiting_for_setting_value)
    await message.answer("Supportchi nomini kiriting:", reply_markup=back_keyboard())

@dp.message(F.text == "🔗 Support username")
async def support_username_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.update_data(setting_key="support_username")
    await state.set_state(AdminExtraState.waiting_for_setting_value)
    await message.answer("Support username'ini kiriting (masalan: JAS_SMM):", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_setting_value)
async def save_setting_value(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    key = data.get("setting_key")
    if key:
        value = message.text.strip().lstrip('@')
        await db.set_setting(key, value)
        await db.log_admin_action(ADMIN_ID, "setting", details=f"{key}={value}")
        await message.answer("✅ Sozlama saqlandi.", reply_markup=admin_menu_keyboard())
        await state.clear()

@dp.message(F.text == "🛠 Maintenance ON/OFF")
async def toggle_maintenance(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    old = await db.get_setting('maintenance_mode','0')
    new = '0' if old=='1' else '1'
    await db.set_setting('maintenance_mode', new)
    await db.log_admin_action(ADMIN_ID, 'maintenance', details=new)
    await message.answer('🟢 Maintenance yoqildi.' if new=='1' else '🔴 Maintenance o‘chirildi.', reply_markup=admin_menu_keyboard())

@dp.message(F.text == "💸 Cashback %")
async def cashback_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_cashback)
    await message.answer("Cashback foizini kiriting (0-100):", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_cashback)
async def cashback_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not 0<=int(message.text)<=100:
        await message.answer('0-100 oralig‘ida raqam kiriting.')
        return
    await db.set_setting('cashback_percent', message.text)
    await db.log_admin_action(ADMIN_ID, 'cashback', details=message.text)
    await state.clear()
    await message.answer('✅ Cashback saqlandi.', reply_markup=admin_menu_keyboard())

@dp.message(F.text == "🤝 Referral bonus")
async def referral_bonus_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_referral_bonus)
    await message.answer("Referral bonusini kiriting (so'm):", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_referral_bonus)
async def referral_bonus_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer('Faqat raqam.')
        return
    await db.set_setting('referral_bonus', message.text)
    await db.log_admin_action(ADMIN_ID, 'referral_bonus', details=message.text)
    await state.clear()
    await message.answer('✅ Referral bonusi saqlandi.', reply_markup=admin_menu_keyboard())


# --- USER: BALANS VA TO'LOV HANDLERLARI ---
@dp.message(F.text == "💳 Balans")
async def show_balance(message: types.Message):
    balance = await db.get_user_balance(message.from_user.id)
    await message.answer(f"🆔 Sening Telegram ID'ingiz: `{message.from_user.id}`\nSizning hisobingizda: **{balance:,} so'm**", parse_mode="Markdown")


@dp.message(F.text == "💳 Balans to'ldirish")
async def start_topup_select(message: types.Message):
    await message.answer("To'lov usulini tanlang:", reply_markup=topup_methods_keyboard())


@dp.callback_query(F.data == "pay_auto")
async def start_auto_topup(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(TopUpState.waiting_for_auto_amount)
    text = (
        "💳 **Hisobni avto to'ldirish**\n\n"
        "💰 Qancha summaga to'ldirmoqchisiz?\n"
        "📊 Limit: **1 000 - 100 000 so'm**\n\n"
        "📝 Summani so'mda kiriting (Masalan: 10000):"
    )
    await call.message.edit_text(text, parse_mode="Markdown")
    await call.message.answer("Bekor qilish uchun pastdagi 'Orqaga' tugmasini bosing:", reply_markup=back_keyboard())
    await call.answer()


@dp.message(TopUpState.waiting_for_auto_amount)
async def process_auto_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat summa kiriting (masalan: 10000):", reply_markup=back_keyboard())
        return

    amount = int(message.text)
    if amount < 1000 or amount > 100000:
        await message.answer("❌ Minimal 1 000 so'm, maksimal 100 000 so'm kiriting!", reply_markup=back_keyboard())
        return

    await state.clear()
    msg = await message.answer("⏳ To'lov hisob-fakturasi (Chek) yaratilmoqda...")
    payment = await async_create_payment(amount)

    if payment.get("success"):
        token = payment.get("token")
        random_addition = random.randint(10, 30)
        pay_amount = amount + random_addition

        if hasattr(db, "save_payment_token"):
            await db.save_payment_token(token, message.from_user.id, amount)

        card = payment.get("card", "9860 1606 0204 4267")

        action_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💳 Kartani nusxalash",
                        copy_text=CopyTextButton(text=str(card))
                    ),
                    InlineKeyboardButton(
                        text="💰 Summani nusxalash",
                        copy_text=CopyTextButton(text=str(pay_amount))
                    )
                ],
                [InlineKeyboardButton(text="🔍 To'lovni tekshirish", callback_data=f"checkpay_{token}")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancelpay_{token}")]
            ]
        )

        text = (
            f"📋 **To'lov ma'lumotlari:**\n\n"
            f"💵 **To'lanishi kerak:** {pay_amount:,} so'm\n"
            f"💳 **Karta raqami:** `{card}`\n"
            f"👤 **Ega:** A.U\n\n"
            f"⚠️ **Muhim:** To'lovni aynan {pay_amount:,} so'm qilib o'tkazing.\n"
            f"⏳ **To'lov muddati:** 5 daqiqa\n"
            f"Tizim sizni summa orqali taniydi."
        )
        await msg.edit_text(text, reply_markup=action_kb, parse_mode="Markdown")
    else:
        err = payment.get("error", "Noma'lum xatolik")
        await msg.edit_text(f"⚠️ To'lov yaratishda xatolik yuz berdi: {err}")

@dp.callback_query(F.data.startswith("checkpay_"))
async def check_auto_pay(call: types.CallbackQuery):
    token = call.data.split("_")[1]
    
    if hasattr(db, "is_payment_paid") and await db.is_payment_paid(token):
        await call.answer("✅ Bu to'lov allaqachon hisobingizga qo'shilgan!", show_alert=True)
        await call.message.edit_text("✅ Ushbu to'lov muvaffaqiyatli yakunlangan!")
        return

    res = await async_check_payment(token)
    
    if res.get("success") and res.get("status") in ["paid", "completed", "success"]:
        amount = res.get("amount") or res.get("pay_amount")
        user_id = call.from_user.id
        
        if amount:
            credited_user = await db.credit_payment_once(token, int(amount)) if hasattr(db, "credit_payment_once") else None
            if not credited_user:
                await call.answer("✅ Bu to'lov allaqachon hisobga olingan!", show_alert=True)
                return
                
            new_bal = await db.get_user_balance(user_id)
            
            await call.message.edit_text(
                f"🎉 **To'lov muvaffaqiyatli tasdiqlandi!**\n\n"
                f"💳 Hisobingizga **{int(amount):,} so'm** qo'shildi.\n"
                f"💰 Hozirgi balansingiz: **{new_bal:,} so'm**",
                parse_mode="Markdown"
            )
            await call.answer("To'lov tasdiqlandi va balansga qo'shildi!", show_alert=True)
        else:
            await call.answer("❌ Summa aniqlanmadi, admin bilan bog'laning.", show_alert=True)
    else:
        status = res.get("status", "pending")
        if status in ["pending", "waiting"]:
            await call.answer("⏳ Pul hali kartaga yetib kelmadi. To'lovni amalga oshirgan bo'lsangiz 10-15 soniya kutib qayta bosing!", show_alert=True)
        elif status in ["expired", "canceled", "failed"]:
            if hasattr(db,"set_payment_status"):
                await db.set_payment_status(token, "failed")
            await call.message.edit_text("❌ To'lov muddati o'tgan yoki bekor qilingan.")
            await call.answer("To'lov muddati tugagan!", show_alert=True)
        else:
            await call.answer("❌ To'lov hali amalga oshirilmadi!", show_alert=True)


@dp.callback_query(F.data.startswith("cancelpay_"))
async def cancel_auto_pay(call: types.CallbackQuery):
    await call.message.edit_text("❌ To'lov bekor qilindi.")
    await call.answer("Bekor qilindi")


@dp.callback_query(F.data == "pay_admin")
async def start_admin_topup(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(TopUpState.waiting_for_manual_amount)
    text = "Qancha summa kiritmoqchisiz? (Masalan: 20000)"
    await call.message.edit_text(text)
    await call.message.answer("Orqaga qaytish uchun bosing:", reply_markup=back_keyboard())
    await call.answer()


@dp.message(TopUpState.waiting_for_manual_amount)
async def process_manual_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting (masalan: 20000):", reply_markup=back_keyboard())
        return

    amount = int(message.text)
    if amount < 1000:
        await message.answer("❌ Minimal summa 1 000 so'm!", reply_markup=back_keyboard())
        return

    await state.update_data(manual_amount=amount)
    await state.set_state(TopUpState.waiting_for_receipt)

    text = (
        f"To'lovni quyidagi kartaga o'tkazing:\n"
        f"💳 `9860160602044267`\n\n"
        f"Summa: {amount:,} so'm\n\n"
        f"To'lovni amalga oshirgach, chek rasmini (skrinshot) shu yerga yuboring."
    )
    await message.answer(text, reply_markup=back_keyboard(), parse_mode="Markdown")


@dp.message(TopUpState.waiting_for_receipt)
async def process_receipt(message: types.Message, state: FSMContext):
    if not (message.photo or message.document):
        await message.answer("Iltimos, chek rasmini (yoki faylini) yuboring!", reply_markup=back_keyboard())
        return

    data = await state.get_data()
    amount = data.get("manual_amount", 0)
    user_id = message.from_user.id
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{user_id}_{amount}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{user_id}")
        ]
    ])
    
    caption_text = (
        f"📥 **Yangi to'lov cheki!**\n\n"
        f"👤 Foydalanuvchi: {message.from_user.full_name} (`{user_id}`)\n"
        f"💵 Summa: **{amount:,} so'm**"
    )

    if message.photo:
        await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption_text, reply_markup=confirm_kb, parse_mode="Markdown")
    elif message.document:
        await bot.send_document(chat_id=ADMIN_ID, document=message.document.file_id, caption=caption_text, reply_markup=confirm_kb, parse_mode="Markdown")

    await message.answer("✅ Chek qabul qilindi. Admin tasdiqlashini kuting.", reply_markup=main_menu(user_id))
    await state.clear()


@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    user_id = int(parts[1])
    amount = int(parts[2])
    
    await db.add_user_balance(user_id, amount)
    await db.log_event(user_id, 'topup', amount)
    
    status_text = f"\n\n✅ **TASDIQLANDI**"
    if call.message.caption:
        await call.message.edit_caption(caption=call.message.caption + status_text, parse_mode="Markdown")
    else:
        await call.message.edit_text(text=call.message.text + status_text, parse_mode="Markdown")
        
    try:
        await bot.send_message(user_id, f"🎉 To'lovingiz tasdiqlandi! Hisobingizga **{amount:,} so'm** qo'shildi.", parse_mode="Markdown")
    except Exception:
        pass
    await call.answer("To'lov tasdiqlandi va balansga qo'shildi!")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    _, user_id = call.data.split("_")
    user_id = int(user_id)
    
    if call.message.caption:
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **RAD ETILDI**", parse_mode="Markdown")
    else:
        await call.message.edit_text(text=call.message.text + "\n\n❌ **RAD ETILDI**", parse_mode="Markdown")
        
    await bot.send_message(user_id, "❌ To'lovingiz rad etildi. Ma'lumotlarni qayta tekshirib ko'ring.")


# --- ADMIN: PM NARXLARINI O'ZGARTIRISH ---
@dp.message(F.text.in_({"✏️ PM nomi/narxini o'zgartirish", "✏️ PM narxini o'zgartirish"}))
async def edit_pm_price_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    prices = await db.get_pm_prices()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ 24 PM"), KeyboardButton(text="✏️ 49 PM")],
            [KeyboardButton(text="✏️ 99 PM"), KeyboardButton(text="✏️ 149 PM")],
            [KeyboardButton(text="✏️ 179 PM"), KeyboardButton(text="✏️ 199 PM")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
    
    text = (
        "📊 **Hozirgi PM narxlari:**\n\n"
        f"• 24 PM: {prices.get('24', 1500):,} so'm\n"
        f"• 49 PM: {prices.get('49', 3500):,} so'm\n"
        f"• 99 PM: {prices.get('99', 9000):,} so'm\n"
        f"• 149 PM: {prices.get('149', 16000):,} so'm\n"
        f"• 179 PM: {prices.get('179', 18000):,} so'm\n"
        f"• 199 PM: {prices.get('199', 21000):,} so'm\n\n"
        "Qaysi toifa narxini o'zgartirmoqchisiz?"
    )
    await state.set_state(AdminEditPriceState.waiting_for_category)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@dp.message(AdminEditPriceState.waiting_for_category)
async def process_category_select(message: types.Message, state: FSMContext):
    cat = message.text.replace("✏️ ", "").replace(" PM", "").strip()
    if cat not in ["24", "49", "99", "149", "179", "199"]:
        await message.answer("Iltimos, tugmalardan birini tanlang!")
        return

    await state.update_data(edit_cat=cat)
    await state.set_state(AdminEditPriceState.waiting_for_new_price)
    await message.answer(f"💰 {cat} PM uchun yangi narxni kiriting (so'mda, faqat raqam):", reply_markup=back_keyboard())


@dp.message(AdminEditPriceState.waiting_for_new_price)
async def process_new_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return

    data = await state.get_data()
    cat = data.get("edit_cat")
    new_price = int(message.text)

    await db.update_pm_price(cat, new_price)
    await message.answer(f"✅ {cat} PM narxi muvaffaqiyatli {new_price:,} so'm ga o'zgartirildi!", reply_markup=admin_menu_keyboard())
    await state.clear()


# --- ADMIN: PM QO'SHISH ---
@dp.message(F.text == "➕ PM qo'shish")
async def admin_add_pm_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ 24-lik PM"), KeyboardButton(text="➕ 49-lik PM")],
            [KeyboardButton(text="➕ 99-lik PM"), KeyboardButton(text="➕ 149-lik PM")],
            [KeyboardButton(text="➕ 179-lik PM"), KeyboardButton(text="➕ 199-lik PM")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
    await message.answer("Qaysi toifaga PM qo'shmoqchisiz?", reply_markup=kb)


@dp.message(F.text.in_({"➕ 24-lik PM", "➕ 49-lik PM", "➕ 99-lik PM", "➕ 149-lik PM", "➕ 179-lik PM", "➕ 199-lik PM"}))
async def admin_add_pm_category(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    cat = message.text.split("-")[0].replace("➕ ", "").strip()
    await state.update_data(selected_cat=cat)
    await state.set_state(AdminPMState.waiting_for_code)
    await message.answer(f"📥 {cat} PM uchun kodlarni yuboring.\n(Bir nechta bo'lsa, har birini yangi qatordan yozing):", reply_markup=back_keyboard())


@dp.message(AdminPMState.waiting_for_code)
async def admin_save_pm(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    cat = data.get("selected_cat")
    codes = message.text.strip().split("\n")
    
    added_count = 0
    for code in codes:
        if code.strip():
            if hasattr(db, "add_user_pm_code_with_owner"):
                await db.add_user_pm_code_with_owner(cat, code.strip(), ADMIN_ID)
            else:
                await db.add_pm_code(cat, code.strip())
            added_count += 1
            
    await message.answer(f"✅ {added_count} ta {cat} PM bazaga muvaffaqiyatli qo'shildi!", reply_markup=admin_menu_keyboard())
    await state.clear()


# --- ADMIN: BALANS AMALLARI ---
@dp.message(F.text == "💰 Balans +")
async def admin_balance_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserOpState.waiting_for_user_id_add)
    await message.answer("Balans to'ldiriladigan foydalanuvchi Telegram ID'sini kiriting:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_user_id_add)
async def admin_balance_add_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqamlardan iborat Telegram ID kiriting!")
        return
    await state.update_data(target_id=int(message.text))
    await state.set_state(AdminUserOpState.waiting_for_amount_add)
    await message.answer("Qancha summa qo'shmoqchisiz? (Masalan: 10000):", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_amount_add)
async def admin_balance_add_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = int(message.text)
    
    await db.add_user_balance(target_id, amount)
    new_bal = await db.get_user_balance(target_id)
    
    await message.answer(f"✅ User (`{target_id}`) hisobiga **{amount:,} so'm** qo'shildi!\nHozirgi balansi: **{new_bal:,} so'm**", reply_markup=admin_menu_keyboard(), parse_mode="Markdown")
    try:
        await bot.send_message(target_id, f"🎉 Hisobingiz **{amount:,} so'm**ga to'ldirildi!\nHozirgi balansingiz: **{new_bal:,} so'm**", parse_mode="Markdown")
    except Exception:
        pass
    await state.clear()


@dp.message(F.text == "💸 Balans -")
async def admin_balance_sub_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserOpState.waiting_for_user_id_sub)
    await message.answer("Balansi ayiriladigan foydalanuvchi Telegram ID'sini kiriting:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_user_id_sub)
async def admin_balance_sub_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqamlardan iborat Telegram ID kiriting!")
        return
    await state.update_data(target_id=int(message.text))
    await state.set_state(AdminUserOpState.waiting_for_amount_sub)
    await message.answer("Qancha summa ayirmoqchisiz?:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_amount_sub)
async def admin_balance_sub_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = int(message.text)
    
    await db.add_user_balance(target_id, -amount)
    new_bal = await db.get_user_balance(target_id)
    
    await message.answer(f"✅ User (`{target_id}`) hisobidan **{amount:,} so'm** olib tashlandi!\nHozirgi balansi: **{new_bal:,} so'm**", reply_markup=admin_menu_keyboard(), parse_mode="Markdown")
    await state.clear()


# --- ADMIN: USER BOSHQARUVI VA STATISTIKA ---
@dp.message(F.text == "👤 User ma'lumot")
async def admin_user_info_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserOpState.waiting_for_user_info)
    await message.answer("Foydalanuvchi Telegram ID'sini kiriting:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_user_info)
async def admin_user_info_get(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    target_id = int(message.text)
    bal = await db.get_user_balance(target_id)
    banned = await db.is_user_banned(target_id)
    status_text = "🚫 Bloklangan" if banned else "✅ Faol"
    
    info_text = (
        f"👤 **Foydalanuvchi Ma'lumoti:**\n\n"
        f"🆔 Telegram ID: `{target_id}`\n"
        f"💰 Balansi: {bal:,} so'm\n"
        f"📌 Holati: {status_text}"
    )
    await message.answer(info_text, reply_markup=admin_menu_keyboard(), parse_mode="Markdown")
    await state.clear()


@dp.message(F.text == "🚫 Ban")
async def admin_ban_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserOpState.waiting_for_ban_id)
    await message.answer("Ban qilmoqchi bo'lgan foydalanuvchining Telegram ID'sini kiriting:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_ban_id)
async def admin_ban_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    target_id = int(message.text)
    await db.set_user_ban(target_id, 1)
    await message.answer(f"🚫 Foydalanuvchi `{target_id}` bloklandi!", reply_markup=admin_menu_keyboard(), parse_mode="Markdown")
    await state.clear()


@dp.message(F.text == "✅ Unban")
async def admin_unban_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserOpState.waiting_for_unban_id)
    await message.answer("Bandan chiqarmoqchi bo'lgan foydalanuvchining Telegram ID'sini kiriting:", reply_markup=back_keyboard())


@dp.message(AdminUserOpState.waiting_for_unban_id)
async def admin_unban_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    target_id = int(message.text)
    await db.set_user_ban(target_id, 0)
    await message.answer(f"✅ Foydalanuvchi `{target_id}` bandan chiqarildi!", reply_markup=admin_menu_keyboard(), parse_mode="Markdown")
    await state.clear()


@dp.message(F.text.in_({"📦 PM qoldiq", "🔑 Kodlar soni", "📊 Statistika"}))
async def show_stats_and_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users_cnt = await db.get_users_count()
    c24 = await db.get_pm_count("24")
    c49 = await db.get_pm_count("49")
    c99 = await db.get_pm_count("99")
    c149 = await db.get_pm_count("149")
    c179 = await db.get_pm_count("179")
    c199 = await db.get_pm_count("199")

    stats_text = (
        f"📊 **Bot Statistikasi & PM Qoldiq:**\n\n"
        f"👤 Jami foydalanuvchilar: {users_cnt} ta\n\n"
        f"📦 **PM Zaxirasi (Kodlar soni):**\n"
        f"• 24 PM: {c24} ta\n"
        f"• 49 PM: {c49} ta\n"
        f"• 99 PM: {c99} ta\n"
        f"• 149 PM: {c149} ta\n"
        f"• 179 PM: {c179} ta\n"
        f"• 199 PM: {c199} ta"
    )
    await message.answer(stats_text, parse_mode="Markdown")


@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminBroadcastState.waiting_for_message)
    await message.answer("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:", reply_markup=back_keyboard())


@dp.message(AdminBroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = await db.get_all_users()
    success, failed = 0, 0
    await message.answer("🚀 Xabar yuborish boshlandi...")

    for user in users:
        uid = user[0] if isinstance(user, (tuple, list)) else user
        try:
            await message.copy_to(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(
        f"✅ Xabar yuborish yakunlandi!\n\n"
        f"👤 Yetib bordi: {success} ta\n"
        f"❌ Yetib bormadi: {failed} ta",
        reply_markup=admin_menu_keyboard()
    )
    await state.clear()


# ============================================================
# QO'SHIMCHA USER FUNKSIYALAR
# ============================================================

@dp.message(F.text == "🎟️ Bonus kod")
async def user_bonus_start(message: types.Message, state: FSMContext):
    if await db.is_user_banned(message.from_user.id):
        return
    await state.set_state(UserExtraState.waiting_for_bonus_code)
    await message.answer("🎟️ Bonus kodingizni yuboring:", reply_markup=back_keyboard())

@dp.message(UserExtraState.waiting_for_bonus_code)
async def user_bonus_process(message: types.Message, state: FSMContext):
    code = message.text.strip()
    amount, status = await db.redeem_promo_bonus_pro(code, message.from_user.id) if hasattr(db,"redeem_promo_bonus_pro") else await db.redeem_promo_bonus(code, message.from_user.id)
    if status == "not_found":
        await message.answer("❌ Bunday bonus kod topilmadi.")
    elif status == "inactive":
        await message.answer("❌ Bu bonus kod tugagan yoki o'chirilgan.")
    elif status == "already":
        await message.answer("⚠️ Siz bu koddan avval foydalangansiz.")
    elif status == "expired":
        await message.answer("❌ Bu promo kodning amal qilish muddati tugagan.")
    elif status == "not_for_user":
        await message.answer("❌ Bu promo kod siz uchun berilmagan.")
    else:
        if not hasattr(db,"redeem_promo_bonus_pro"):
            await db.add_user_balance(message.from_user.id, amount)
        await db.log_event(message.from_user.id, "promo_bonus", amount, details=code)
        bal = await db.get_user_balance(message.from_user.id)
        await message.answer(f"🎉 Bonus qabul qilindi!\n💰 +{amount:,} so'm\n💳 Balans: {bal:,} so'm", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "🎫 Support", F.from_user.id != ADMIN_ID)
async def user_support_start(message: types.Message, state: FSMContext):
    await state.clear()
    support_name = await db.get_setting("support_name", "JAS SMM")
    support_username = await db.get_setting("support_username", "JAS_SMM")
    support_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👨‍💻 {support_name} @{support_username}", url=f"https://t.me/{support_username.lstrip('@')}")],
        [InlineKeyboardButton(text="🎫 Ticket ochish", callback_data="open_support_ticket")]
    ])
    await message.answer(
        "🎫 **Support**\n\nSavol yoki muammo bo'lsa, to'g'ridan-to'g'ri supportga yozing:",
        reply_markup=support_kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data == "open_support_ticket")
async def open_support_ticket(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserExtraState.waiting_for_support_message)
    await call.message.answer("🎫 Muammo yoki savolingizni yozing. Ticket ochiladi:", reply_markup=back_keyboard())
    await call.answer()

@dp.message(UserExtraState.waiting_for_support_message)
async def user_support_process(message: types.Message, state: FSMContext):
    tid = await db.create_support_ticket(message.from_user.id, message.text or "")
    await db.log_event(message.from_user.id, "support_ticket", 0, details=f"ticket={tid}")
    await state.clear()
    try:
        await bot.send_message(ADMIN_ID, f"🎫 **Yangi ticket #{tid}**\n👤 User: `{message.from_user.id}`\n\n{message.text}", parse_mode="Markdown")
    except Exception: pass
    await message.answer(f"✅ Ticket **#{tid}** qabul qilindi.\n\nYoki tezkor aloqa uchun @JAS_SMM ga yozishingiz mumkin.", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))


# ============================================================
# ADMIN: QIDIRUV / PROMO / TARIX / DAROMAD / SUPPORT / LOG
# ============================================================

@dp.message(F.text == "🔎 User qidirish")
async def admin_search_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_user_id)
    await message.answer("🔎 User Telegram ID sini kiriting:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_user_id)
async def admin_search_user_get(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting.")
        return
    uid = int(message.text)
    bal = await db.get_user_balance(uid)
    banned = await db.is_user_banned(uid)
    events = await db.get_user_events(uid, 10)
    text = f"👤 **USER**\n🆔 `{uid}`\n💰 Balans: **{bal:,} so'm**\n📌 Holat: {'🚫 Ban' if banned else '✅ Faol'}\n\n📜 Oxirgi amallar:\n"
    text += "\n".join([f"• {e[4]} — {e[0]} — {e[1]:,} so'm" for e in events]) or "• Tarix yo'q"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "🎁 Promo boshqaruvi")
async def admin_promo_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    promos = await db.get_promo_bonuses()
    text = "🎁 **PROMO BOSHQARUVI**\n\n"
    text += "\n".join([f"• `{r[0]}` — {r[1]:,} so'm | {r[3]}/{r[2]}" for r in promos]) or "Promo kodlar yo'q."
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Promo yaratish"), KeyboardButton(text="🗑️ Promo o'chirish")],
        [KeyboardButton(text="⬅️ Admin menyu")]
    ], resize_keyboard=True)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "➕ Promo yaratish")
async def admin_promo_create_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_promo_code)
    await message.answer("Promo kod nomini yuboring:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_promo_code)
async def admin_promo_code(message: types.Message, state: FSMContext):
    await state.update_data(promo_code=message.text.strip())
    await state.set_state(AdminExtraState.waiting_for_promo_amount)
    await message.answer("Bonus summasi (so'm):")

@dp.message(AdminExtraState.waiting_for_promo_amount)
async def admin_promo_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): await message.answer("Faqat raqam."); return
    await state.update_data(promo_amount=int(message.text))
    await state.set_state(AdminExtraState.waiting_for_promo_uses)
    await message.answer("Necha kishi ishlata oladi?")

@dp.message(AdminExtraState.waiting_for_promo_uses)
async def admin_promo_uses(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text)<1:
        await message.answer("1 yoki undan katta son kiriting."); return
    await state.update_data(promo_uses=int(message.text))
    await state.set_state(AdminExtraState.waiting_for_promo_expiry)
    await message.answer("⏳ Amal qilish muddati necha kun? `0` = muddatsiz", parse_mode="Markdown")

@dp.message(AdminExtraState.waiting_for_promo_expiry)
async def admin_promo_expiry(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): await message.answer("Faqat raqam."); return
    days = int(message.text)
    expires = None
    if days > 0:
        expires = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    await state.update_data(promo_expires=expires)
    await state.set_state(AdminExtraState.waiting_for_promo_target)
    await message.answer("👤 Ma'lum user uchunmi? User ID yuboring yoki `0` deb yozing.", parse_mode="Markdown")

@dp.message(AdminExtraState.waiting_for_promo_target)
async def admin_promo_target(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): await message.answer("User ID raqam bo'lishi kerak. `0` = barchaga.", parse_mode="Markdown"); return
    target = int(message.text) or None
    d = await state.get_data()
    await db.create_promo_bonus_pro(d["promo_code"], d["promo_amount"], d["promo_uses"], d.get("promo_expires"), target)
    await db.log_admin_action(ADMIN_ID, "promo_create", details=f"{d['promo_code']} target={target or 'all'}")
    await message.answer("✅ Promo yaratildi.", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "🗑️ Promo o'chirish")
async def admin_promo_delete_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_promo_delete)
    await message.answer("O'chiriladigan promo kodni yuboring:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_promo_delete)
async def admin_promo_delete_process(message: types.Message, state: FSMContext):
    code = message.text.strip()
    await db.delete_promo_bonus(code)
    await db.log_admin_action(ADMIN_ID, "promo_delete", details=code)
    await message.answer("✅ Promo o'chirildi.", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "🛒 Savdo tarixi")
async def admin_sales_history(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with db.aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT event_type,user_id,amount,category,created_at FROM bot_events WHERE event_type='purchase' ORDER BY id DESC LIMIT 20") as cur:
            rows = await cur.fetchall()
    text = "🛒 **Oxirgi 20 ta savdo**\n\n" + ("\n".join([f"• {r[4]} | `{r[1]}` | {r[3]} PM | {r[2]:,} so'm" for r in rows]) or "Savdo yo'q.")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 To'lovlar tarixi")
async def admin_payment_history(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with db.aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT token,user_id,amount,status FROM payments ORDER BY rowid DESC LIMIT 20") as cur:
            rows = await cur.fetchall()
    text = "💳 **Oxirgi 20 ta to'lov**\n\n" + ("\n".join([f"• `{r[1]}` — {r[2]:,} so'm — {r[3]}" for r in rows]) or "To'lov yo'q.")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📈 Daromad")
async def admin_revenue(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    s = await db.get_event_stats()
    await message.answer(
        f"📈 **DAROMAD / STATISTIKA**\n\n"
        f"🟢 Bugungi xaridlar: {s['purchases_today']} ta\n"
        f"💰 Bugungi savdo: {s['sales_today']:,} so'm\n"
        f"📅 7 kunlik xaridlar: {s['purchases_week']} ta\n"
        f"🗓 30 kunlik savdo: {s['sales_month']:,} so'm\n"
        f"⚡ Bugungi eventlar: {s['events_today']} ta",
        parse_mode="Markdown"
    )

@dp.message(F.text == " ADMIN")
async def admin_support_list(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    rows = await db.get_open_tickets()
    text = "🎫 **OCHIQ SUPPORT**\n\n" + ("\n".join([f"• #{r[0]} — `{r[1]}` — {r[2][:80]}" for r in rows]) or "Ochiq ticket yo'q.")
    await message.answer(text, parse_mode="Markdown")
    if rows:
        await message.answer("Javob berish: `/reply TICKET_ID matn`", parse_mode="Markdown")

@dp.message(F.text.regexp(r"^/reply\s+\d+\s+"))
async def admin_ticket_reply_command(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    tid = int(parts[1])
    reply = parts[2]
    uid = await db.reply_support_ticket(tid, reply)
    if not uid:
        await message.answer("❌ Ticket topilmadi yoki yopilgan.")
        return
    try: await bot.send_message(uid, f"🎫 **Support javobi:**\n\n{reply}", parse_mode="Markdown")
    except: pass
    await db.log_admin_action(ADMIN_ID, "support_reply", uid, details=f"ticket={tid}")
    await message.answer("✅ Javob yuborildi.", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "📝 Admin log")
async def admin_log(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with db.aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT action,target_id,amount,details,created_at FROM admin_logs ORDER BY id DESC LIMIT 20") as cur:
            rows = await cur.fetchall()
    text = "📝 **ADMIN LOG**\n\n" + ("\n".join([f"• {r[4]} — {r[0]} — {r[1] or '-'} — {r[2]:,}" for r in rows]) or "Log yo'q.")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📢 Majburiy obuna")
async def admin_required_subscription(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    enabled = await db.is_required_subscription_enabled()
    channels = await db.get_required_channels()
    text = "📢 **MAJBURIY OBUNA**\n\n"
    text += "Holat: " + ("🟢 Yoqilgan" if enabled else "🔴 O'chirilgan") + "\n\n"
    if channels:
        text += "Kanallar:\n" + "\n".join([f"• #{r[0]} — {r[3] or r[1]}" for r in channels])
    else:
        text += "Hozircha kanal qo'shilmagan."
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Kanal qo'shish"), KeyboardButton(text="🗑️ Kanal o'chirish")],
        [KeyboardButton(text="🟢 Obunani yoqish"), KeyboardButton(text="🔴 Obunani o'chirish")],
        [KeyboardButton(text="⬅️ Admin menyu")]
    ], resize_keyboard=True)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "➕ Kanal qo'shish")
async def admin_required_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminExtraState.waiting_for_required_channel)
    await message.answer(
        "➕ Kanal qo'shish\n\n"
        "Public kanal uchun: `@kanalusername|Kanal nomi`\n"
        "Private kanal uchun: `-1001234567890|https://t.me/+invite|Kanal nomi`\n\n"
        "⚠️ Bot kanalga admin bo'lishi kerak.",
        parse_mode="Markdown", reply_markup=back_keyboard()
    )

@dp.message(AdminExtraState.waiting_for_required_channel)
async def admin_required_add_process(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) == 2:
        chat_id, title = parts
        invite = None
    elif len(parts) == 3:
        chat_id, invite, title = parts
    else:
        await message.answer("❌ Format noto'g'ri. Misol: `@kanal|Kanal nomi`", parse_mode="Markdown")
        return
    if not (chat_id.startswith("@") or chat_id.lstrip("-").isdigit()):
        await message.answer("❌ Kanal username `@...` yoki Telegram chat ID bo'lishi kerak.")
        return
    try:
        chat = await bot.get_chat(chat_id)
        await db.add_required_channel(chat_id, invite, title or chat.title)
        await db.log_admin_action(ADMIN_ID, "required_channel_add", details=str(chat_id))
        await message.answer(f"✅ Kanal qo'shildi: {chat.title or title}", reply_markup=admin_menu_keyboard())
        await state.clear()
    except Exception as e:
        logging.error("Kanal qo'shishda xato: %s", e)
        await message.answer("❌ Kanal topilmadi. Chat ID/username va botning kanalga admin ekanini tekshiring.")

@dp.message(F.text == "🗑️ Kanal o'chirish")
async def admin_required_remove_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    channels = await db.get_required_channels()
    if not channels:
        await message.answer("Kanal yo'q.")
        return
    await state.set_state(AdminExtraState.waiting_for_required_remove)
    text = "🗑️ O'chirish uchun kanal ID sini yuboring:\n\n" + "\n".join([f"#{r[0]} — {r[3] or r[1]}" for r in channels])
    await message.answer(text, reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_required_remove)
async def admin_required_remove_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Kanal ID sini raqam bilan yuboring.")
        return
    cid = int(message.text)
    await db.remove_required_channel(cid)
    await db.log_admin_action(ADMIN_ID, "required_channel_remove", details=str(cid))
    await message.answer("✅ Kanal o'chirildi.", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "🟢 Obunani yoqish")
async def admin_required_enable(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await db.toggle_required_channel(True)
    await db.log_admin_action(ADMIN_ID, "required_subscription_on")
    await message.answer("🟢 Majburiy obuna yoqildi.", reply_markup=admin_menu_keyboard())

@dp.message(F.text == "🔴 Obunani o'chirish")
async def admin_required_disable(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await db.toggle_required_channel(False)
    await db.log_admin_action(ADMIN_ID, "required_subscription_off")
    await message.answer("🔴 Majburiy obuna o'chirildi.", reply_markup=admin_menu_keyboard())

@dp.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ **Sozlamalar**\n\nHozircha asosiy sozlama: bot nomi/xabari.\nYangi qiymatni o'zgartirish uchun `bot_notice` kalitidan foydalaniladi.", parse_mode="Markdown")
    await db.set_setting("last_settings_open","1")

@dp.message(F.text == "⬅️ Admin menyu")
async def back_admin_menu(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("⚙️ Admin panel", reply_markup=admin_menu_keyboard())


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Webhook serverni sozlash (Aiohttp)
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, payhamyon_webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logging.info(f"Web server ishga tushdi: http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}{WEBHOOK_PATH}")

    # Botni ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
