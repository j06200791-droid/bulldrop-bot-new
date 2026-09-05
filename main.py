import asyncio
import logging
import random
import os
import json
import urllib.request
import urllib.error
import time
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
ADMIN_ID = 5974947091

# PayHamyon Sozlamalari
SHOP_ID = 20
SHOP_KEY = "V04nimOvjY5NGkXtp6qofufRcFB82tT"
BASE_URL = "https://user91.hostx.uz"

# Webhook Server Sozlamalari
WEBHOOK_PATH = "/payhamyon/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))

# Network uzilishlariga chidamli session
session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())


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
                    await db.add_user_balance(user_id, int(amount))
                    await db.log_event(user_id, 'topup', int(amount))
                    if hasattr(db, "mark_payment_as_paid"):
                        await db.mark_payment_as_paid(token)
                        
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


# --- KEYBOARDS ---
def main_menu(user_id: int):
    buttons = [
        [KeyboardButton(text="🎁 Promokod sotib olish"),],
        #   KeyboardButton(text="➕ Promokod sotish")],
        [KeyboardButton(text="💳 Balans"), KeyboardButton(text="💳 Balans to'ldirish")],
        # [KeyboardButton(text="🎟️ Bonus kod"), KeyboardButton(text="👑 VIP")],
        # [KeyboardButton(text="🎫 Support")]
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
            [KeyboardButton(text="➕ PM qo'shish"), KeyboardButton(text="📦 PM qoldiq")],
            [KeyboardButton(text="✏️ PM narxini o'zgartirish"), KeyboardButton(text="🏷️ Foydalanuvchi sotish narxi")],
            [KeyboardButton(text="🔑 Kodlar soni"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="💰 Balans +"), KeyboardButton(text="💸 Balans -")],
            [KeyboardButton(text="👤 User ma'lumot"), KeyboardButton(text="🔎 User qidirish")],
            [KeyboardButton(text="🚫 Ban"), KeyboardButton(text="✅ Unban")],
            [KeyboardButton(text="🎁 Promo boshqaruvi"), KeyboardButton(text="👑 VIP boshqaruvi")],
            [KeyboardButton(text="🛒 Savdo tarixi"), KeyboardButton(text="💳 To'lovlar tarixi")],
            [KeyboardButton(text="📈 Daromad"), KeyboardButton(text="🎫 Support")],
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="📝 Admin log")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="⬅️ Bosh menyu")]
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
    c24 = await db.get_pm_count("24")
    c49 = await db.get_pm_count("49")
    c99 = await db.get_pm_count("99")
    c149 = await db.get_pm_count("149")
    c179 = await db.get_pm_count("179")
    c199 = await db.get_pm_count("199")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 24 lik — {prices.get('24', 1500):,} so'm ({c24} ta bor)", callback_data="buy_24")],
        [InlineKeyboardButton(text=f"🎁 49 lik — {prices.get('49', 3500):,} so'm ({c49} ta bor)", callback_data="buy_49")],
        [InlineKeyboardButton(text=f"🎁 99 lik — {prices.get('99', 9000):,} so'm ({c99} ta bor)", callback_data="buy_99")],
        [InlineKeyboardButton(text=f"🎁 149 lik — {prices.get('149', 16000):,} so'm ({c149} ta bor)", callback_data="buy_149")],
        [InlineKeyboardButton(text=f"🎁 179 lik — {prices.get('179', 18000):,} so'm ({c179} ta bor)", callback_data="buy_179")],
        [InlineKeyboardButton(text=f"🎁 199 lik — {prices.get('199', 21000):,} so'm ({c199} ta bor)", callback_data="buy_199")]
    ])


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


# --- MIDDLEWARES ---
@dp.message.outer_middleware()
async def ban_middleware(handler, event, data):
    if isinstance(event, types.Message):
        user_id = event.from_user.id
        if user_id != ADMIN_ID and await db.is_user_banned(user_id):
            await event.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
            return
    return await handler(event, data)


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
    await db.get_user_balance(message.from_user.id)
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu(message.from_user.id))


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
        "Videoda botdan kod olinishi, nusxalanib (Copy) darhol Bulldrop saytiga qo'yilishi (Paste) va faolllashtirilishi kesilmasdan ko'rinishi shart.\n\n"
        "⚠️ Aks holda 'ishlamadi' yoki 'ishlatilgan' degan e'tirozlar ko'rib chiqilmaydi va pul qaytarilmaydi.\n\n"
        "👇 Qoidaga rozilik bildirsangiz, quyidagi tugmani bosing:"
    )
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ROZIMAN", callback_data="agree_rules")]
    ])
    await message.answer(rules_text, reply_markup=confirm_kb)


@dp.callback_query(F.data == "agree_rules")
async def show_pm_list_after_rules(call: types.CallbackQuery):
    kb = await pm_menu_keyboard()
    await call.message.edit_text("Quyidagi tugmalardan birini tanlang:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_pm(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    prices = await db.get_pm_prices()
    default_prices = {"24": 1500, "49": 3500, "99": 9000, "149": 16000, "179": 18000, "199": 21000}
    price = prices.get(category, default_prices.get(category, 0))
    
    user_id = call.from_user.id
    balance = await db.get_user_balance(user_id)
    
    if balance < price:
        await call.answer("❌ Hisobingizda mablag' yetarli emas!", show_alert=True)
        return

    stock_count = await db.get_pm_count(category)
    if stock_count <= 0:
        await call.answer("❌ Afsuski, bu toifada hozirda PM qolmagan!", show_alert=True)
        return

    if hasattr(db, "buy_pm_code_with_owner"):
        pm_data = await db.buy_pm_code_with_owner(category)
    else:
        code = await db.buy_pm_code(category)
        pm_data = (code, ADMIN_ID) if code else None

    if not pm_data:
        await call.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring!", show_alert=True)
        return

    pm_code, uploader_id = pm_data

    await db.add_user_balance(user_id, -price)
    await db.log_event(user_id, 'purchase', price, category)
    
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

    success_text = (
        "✅ Xarid muvaffaqiyatli amalga oshirildi!\n\n"
        f"Sizning {category} PM promokodingiz:\n"
        f"`{pm_code}`"
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


# --- ADMIN: FOYDALANUVCHIDAN SOTIB OLISH NARXINI SOZLASH ---
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
    waiting_for_vip_remove = State()
    waiting_for_ticket_reply = State()
    waiting_for_promo_code = State()
    waiting_for_promo_amount = State()
    waiting_for_promo_uses = State()
    waiting_for_vip_id = State()
    waiting_for_vip_days = State()
    waiting_for_ticket_id = State()
    waiting_for_setting = State()
    waiting_for_setting_value = State()

class UserExtraState(StatesGroup):
    waiting_for_bonus_code = State()
    waiting_for_support_message = State()


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
            await db.add_user_balance(user_id, int(amount))
            await db.log_event(user_id, 'topup', int(amount))
            if hasattr(db, "mark_payment_as_paid"):
                await db.mark_payment_as_paid(token)
                
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
        elif status in ["expired", "canceled"]:
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
    amount, status = await db.redeem_promo_bonus(code, message.from_user.id)
    if status == "not_found":
        await message.answer("❌ Bunday bonus kod topilmadi.")
    elif status == "inactive":
        await message.answer("❌ Bu bonus kod tugagan yoki o'chirilgan.")
    elif status == "already":
        await message.answer("⚠️ Siz bu koddan avval foydalangansiz.")
    else:
        await db.add_user_balance(message.from_user.id, amount)
        await db.log_event(message.from_user.id, "promo_bonus", amount, details=code)
        bal = await db.get_user_balance(message.from_user.id)
        await message.answer(f"🎉 Bonus qabul qilindi!\n💰 +{amount:,} so'm\n💳 Balans: {bal:,} so'm", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "👑 VIP")
async def user_vip_info(message: types.Message):
    expires = await db.is_vip(message.from_user.id)
    if expires:
        await message.answer(f"👑 **VIP holati: FAOL**\n⏳ Tugash vaqti: `{expires}`", parse_mode="Markdown")
    else:
        await message.answer("👑 Sizda hozir VIP faol emas.")

@dp.message(F.text == "🎫 Support", F.from_user.id != ADMIN_ID)
async def user_support_start(message: types.Message, state: FSMContext):
    await state.set_state(UserExtraState.waiting_for_support_message)
    await message.answer("🎫 Muammo yoki savolingizni yozing. Admin ko'rib chiqadi:", reply_markup=back_keyboard())

@dp.message(UserExtraState.waiting_for_support_message)
async def user_support_process(message: types.Message, state: FSMContext):
    tid = await db.create_support_ticket(message.from_user.id, message.text.strip())
    await bot.send_message(
        ADMIN_ID,
        f"🎫 **Yangi support #{tid}**\n\n"
        f"👤 User: `{message.from_user.id}`\n"
        f"📝 {message.text}",
        parse_mode="Markdown"
    )
    await message.answer(f"✅ Murojaatingiz #{tid} qabul qilindi.", reply_markup=main_menu(message.from_user.id))
    await state.clear()


# ============================================================
# ADMIN: QIDIRUV / PROMO / VIP / TARIX / DAROMAD / SUPPORT / LOG
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
    vip = await db.is_vip(uid)
    events = await db.get_user_events(uid, 10)
    
    vip_text = f"✅ {vip}" if vip else "❌ Yo'q"
    text = f"👤 **USER**\n🆔 `{uid}`\n💰 Balans: **{bal:,} so'm**\n📌 Holat: {'🚫 Ban' if banned else '✅ Faol'}\n👑 VIP: {vip_text}\n\n📜 Oxirgi amallar:\n"
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
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("1 yoki undan katta son kiriting."); return
    d = await state.get_data()
    await db.create_promo_bonus(d["promo_code"], d["promo_amount"], int(message.text))
    await db.log_admin_action(ADMIN_ID, "promo_create", details=d["promo_code"])
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

@dp.message(F.text == "👑 VIP boshqaruvi")
async def admin_vip_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    vips = await db.get_vip_users()
    text = "👑 **VIP FOYDALANUVCHILAR**\n\n" + ("\n".join([f"• `{v[0]}` — {v[1]}" for v in vips]) or "VIP foydalanuvchilar yo'q.")
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ VIP berish"), KeyboardButton(text="❌ VIP olish")],
        [KeyboardButton(text="⬅️ Admin menyu")]
    ], resize_keyboard=True)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "➕ VIP berish")
async def admin_vip_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_vip_id)
    await message.answer("VIP beriladigan User ID:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_vip_id)
async def admin_vip_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): await message.answer("Faqat ID raqam."); return
    await state.update_data(vip_id=int(message.text))
    await state.set_state(AdminExtraState.waiting_for_vip_days)
    await message.answer("Necha kun VIP?")

@dp.message(AdminExtraState.waiting_for_vip_days)
async def admin_vip_days(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1: await message.answer("Kun sonini kiriting."); return
    d = await state.get_data()
    uid = d["vip_id"]
    days = int(message.text)
    await db.set_vip(uid, days)
    await db.log_admin_action(ADMIN_ID, "vip_add", uid, details=f"{days} days")
    try: await bot.send_message(uid, f"👑 Sizga **{days} kun VIP** berildi!", parse_mode="Markdown")
    except: pass
    await message.answer("✅ VIP berildi.", reply_markup=admin_menu_keyboard())
    await state.clear()

@dp.message(F.text == "❌ VIP olish")
async def admin_vip_remove_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminExtraState.waiting_for_vip_remove)
    await message.answer("VIP olinadigan User ID ni yuboring:", reply_markup=back_keyboard())

@dp.message(AdminExtraState.waiting_for_vip_remove)
async def admin_vip_remove_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): await message.answer("Faqat ID raqam."); return
    uid = int(message.text)
    await db.remove_vip(uid)
    await db.log_admin_action(ADMIN_ID, "vip_remove", uid)
    try: await bot.send_message(uid, "ℹ️ VIP holatingiz admin tomonidan bekor qilindi.")
    except: pass
    await message.answer("✅ VIP olib tashlandi.", reply_markup=admin_menu_keyboard())
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
        f"🟢 Bugungi xaridlar: {s['purchases_today']} ta\n\n"
        f"💰 Bugungi savdo: {s['sales_today']:,} so'm\n\n"
        f"📅 7 kunlik xaridlar: {s['purchases_week']} ta\n\n"
        f"🗓 30 kunlik savdo: {s['sales_month']:,} so'm\n\n"
        f"⚡ Bugungi eventlar: {s['events_today']} ta"
        , parse_mode="Markdown")

@dp.message(F.text == "🎫 Support")
async def admin_support_list(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    rows = await db.get_open_tickets()
    text = "🎫 **OCHIQ SUPPORT**\n\n" + ("\n".join([f"• #{r[0]} — `{r[1]}` — {r[2][:80]}" for r in rows]) or "Ochiq ticket yo'q.")
    await message.answer(text, parse_mode="Markdown")
    if rows:
        await message.answer("Javob berish: `/reply TICKET_ID matn`", parse_mode="Markdown")

@dp.message(F.text.startswith("/reply"))
async def admin_ticket_reply_command(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Xato format! Masalan: `/reply 1 Salom`", parse_mode="Markdown")
        return
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

@dp.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ **Sozlamalar**\n\nHozircha asosiy sozlama: bot nomi/xabari.\nYangi qiymatni o'zgartirish uchun `bot_notice` kalitidan foydalaniladi.", parse_mode="Markdown")
    await db.set_setting("last_settings_open", "1")

@dp.message(F.text == "⬅️ Admin menyu")
async def back_admin_menu(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("⚙️ Admin panel", reply_markup=admin_menu_keyboard())

# --- BOTni va WEBHOOK SERVERNI BIRGA ISHGA TUSHIRISH ---
async def main():
    await db.init_db()
    logging.basicConfig(level=logging.INFO)
    
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, payhamyon_webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    
    logging.info(f"Webhook server running on http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}{WEBHOOK_PATH}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
