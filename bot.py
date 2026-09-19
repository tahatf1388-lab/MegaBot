import asyncio
import logging
import sys
import os
import aiohttp
import psycopg2
from urllib.parse import urlparse, urlunparse
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

TOKEN = "8844658209:AAH41cGWIdMiSLQq8PO5VNU_qds7vWJpmmE"
DATABASE_URL = os.getenv("DATABASE_URL")

KUTT_API_URL = "https://kutt-production-0880.up.railway.app/api/v2/links"
KUTT_API_KEY = "OBwH3VujRdD29sakT7dgJ_OqEGxWz8KZ2mWw5EkJ"

router = Router()

def get_db_connection():
    parsed_url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=parsed_url.path[1:],
        user=parsed_url.username,
        password=parsed_url.password,
        host=parsed_url.hostname,
        port=parsed_url.port
    )
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_key TEXT PRIMARY KEY,
            user_id BIGINT,
            file_id TEXT,
            file_type TEXT,
            file_name TEXT,
            views INTEGER DEFAULT 0,
            forwards INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0
        )
    """)
    cursor.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0;")
    cursor.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS forwards INTEGER DEFAULT 0;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id SERIAL PRIMARY KEY,
            link_id TEXT UNIQUE,
            user_id BIGINT,
            link_name TEXT,
            long_url TEXT,
            short_url TEXT,
            kutt_id TEXT,
            password TEXT,
            expire_date TEXT,
            expire_gregorian TIMESTAMP,
            deleted INTEGER DEFAULT 0
        )
    """)
    cursor.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS kutt_id TEXT;")
    cursor.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS password TEXT;")
    cursor.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS expire_date TEXT;")
    cursor.execute("ALTER TABLE links ADD COLUMN IF NOT EXISTS expire_gregorian TIMESTAMP;")
    
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def jalali_to_gregorian(jy, jm, jd):
    gy = (jy <= 979) and 621 or 1600
    jy = (jy <= 979) and jy or jy - 979
    days = (365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4 + 
            78 + jd + (jm < 7 and (jm - 1) * 31 or (jm - 7) * 30 + 186))
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * (--days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)) and 29 or 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for v in sal_a:
        if gd <= v:
            break
        gd -= v
        gm += 1
    return datetime(gy, gm, gd)


class BotStates(StatesGroup):
    waiting_for_file_upload = State()
    waiting_for_file_name = State()
    waiting_for_link_url = State()
    waiting_for_link_name = State()
    waiting_for_link_password_choice = State()
    waiting_for_link_password = State()
    waiting_for_link_expire_choice = State()
    waiting_for_link_expire_date = State()

user_temp_storage = {}

main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🗂️ مدیریت فایل‌ها"), KeyboardButton(text="🔗 خدمات لینک")],
        [KeyboardButton(text="👤 حساب کاربری")]
    ],
    resize_keyboard=True,
    input_field_placeholder="لطفاً یکی از گزینه‌های زیر را انتخاب کنید... 👇"
)

file_management_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📁 آپلود فایل و دریافت لینک"), KeyboardButton(text="📂 فایل‌های من")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

link_services_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن لینک جدید"), KeyboardButton(text="📋 لینک‌های من")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

back_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

password_choice_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔒 بله، گذاشتن رمز عبور"), KeyboardButton(text="⏭️ رد کردن")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

expire_choice_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏳ بله، تعیین تاریخ انقضا"), KeyboardButton(text="⏭️ رد کردن")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1 and args[1].startswith("file_"):
        file_key = args[1].replace("file_", "")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, file_type, deleted FROM files WHERE file_key = %s", (file_key,))
        row = cursor.fetchone()

        if row:
            file_id, file_type, deleted = row
            if deleted == 1:
                cursor.close()
                conn.close()
                await message.answer("⚠️ متأسفانه این فایل توسط صاحب آن حذف شده است. ❌")
            else:
                cursor.execute("UPDATE files SET views = views + 1 WHERE file_key = %s", (file_key,))
                conn.commit()
                cursor.close()
                conn.close()

                await message.answer("🎁 این هم فایل درخواستی شما: 👇")
                if file_type == "document":
                    await message.answer_document(file_id)
                elif file_type == "video":
                    await message.answer_video(file_id)
                elif file_type == "audio":
                    await message.answer_audio(file_id)
                elif file_type == "photo":
                    await message.answer_photo(file_id)
        else:
            cursor.close()
            conn.close()
            await message.answer("⚠️ متأسفانه فایل مورد نظر پیدا نشد یا منقضی شده است. ❌")

        await message.answer("🏠 به منوی اصلی برگشتید: 👇", reply_markup=main_menu_keyboard)
        return

    await message.answer(
        f"سلام {message.from_user.first_name}! 👋 به ربات مگابات خوش آمدید. 🤖\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=main_menu_keyboard
    )


@router.message(F.text == "🗂️ مدیریت فایل‌ها")
async def file_management_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🗂️ به بخش مدیریت فایل‌ها خوش آمدید. 📁\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇", reply_markup=file_management_keyboard)


@router.message(F.text == "🔗 خدمات لینک")
async def link_services_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔗 به بخش خدمات لینک و کوتاه‌کننده خوش آمدید. 🌐\nانتخاب کنید: 👇", reply_markup=link_services_keyboard)


@router.message(F.text == "👤 حساب کاربری")
async def profile_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"📊 اطلاعات حساب کاربری شما: 👤\n\n"
        f"🆔 شناسه کاربری: `{message.from_user.id}`\n"
        f" نام: {message.from_user.first_name}\n\n"
        f"✨ وضعیت اشتراک: عادی 🌟\n"
        f"🎁 موجودی ترافیک: رایگان 🚀",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard
    )


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 به منوی اصلی برگشتید: 👇", reply_markup=main_menu_keyboard)


@router.message(F.text == "📁 آپلود فایل و دریافت لینک")
async def upload_file_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.waiting_for_file_upload)
    await message.answer(
        "📥 لطفاً فایل خود (سند، ویدیو، صوت یا تصویر) را بفرستید تا لینک اختصاصی‌اش را تحویل بگیرید: 👇",
        reply_markup=back_keyboard
    )


@router.message(BotStates.waiting_for_file_upload, F.text == "🔙 بازگشت")
async def cancel_file_upload_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔙 به بخش مدیریت فایل‌ها برگشتید: 👇", reply_markup=file_management_keyboard)


@router.message(BotStates.waiting_for_file_upload, F.document | F.video | F.audio | F.photo)
async def receive_file(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    file_id, file_type = None, None

    if message.document:
        file_id, file_type = message.document.file_id, "document"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.audio:
        file_id, file_type = message.audio.file_id, "audio"
    elif message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"

    if file_id:
        user_temp_storage[user_id] = {"file_id": file_id, "file_type": file_type}
        await state.set_state(BotStates.waiting_for_file_name)
        await message.answer(
            "✍️ فایل شما دریافت شد.\nحالا یک **نام دلخواه** برای این فایل وارد کنید: 👇",
            reply_markup=back_keyboard
        )


@router.message(BotStates.waiting_for_file_name, F.text)
async def receive_file_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "🔙 بازگشت":
        await state.clear()
        user_temp_storage.pop(user_id, None)
        await message.answer("🔙 به بخش مدیریت فایل‌ها برگشتید: 👇", reply_markup=file_management_keyboard)
        return

    if user_id not in user_temp_storage:
        await state.clear()
        await message.answer("⚠️ اطلاعات فایل منقضی شد. لطفاً دوباره تلاش کنید.", reply_markup=file_management_keyboard)
        return

    file_data = user_temp_storage.pop(user_id)
    file_name = text

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files")
    count = cursor.fetchone()[0]
    file_key = f"f_{user_id}_{count + 1}"

    cursor.execute("""
        INSERT INTO files (file_key, user_id, file_id, file_type, file_name, views, forwards, deleted)
        VALUES (%s, %s, %s, %s, %s, 0, 0, 0)
    """, (file_key, user_id, file_data["file_id"], file_data["file_type"], file_name))
    conn.commit()
    cursor.close()
    conn.close()

    bot_info = await message.bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=file_{file_key}"

    await state.clear()
    await message.answer(
        f"🎉 فایل شما با نام {file_name} ثبت شد! ✅\n\n"
        f"🔗 لینک اختصاصی:\n"
        f"{share_link}",
        reply_markup=file_management_keyboard
    )


@router.message(F.text == "📂 فایل‌های من")
async def list_user_files(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_key, file_name FROM files WHERE user_id = %s AND deleted = 0", (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await message.answer("📭 شما هنوز هیچ فایلی آپلود نکرده‌اید. ⚠️", reply_markup=file_management_keyboard)
        return

    inline_keyboard = []
    for file_key, file_name in rows:
        btn_view = InlineKeyboardButton(text=f"📂 {file_name}", callback_data=f"vfile_{file_key}")
        btn_delete = InlineKeyboardButton(text="🗑️ حذف", callback_data=f"dfile_{file_key}")
        inline_keyboard.append([btn_view, btn_delete])

    await message.answer(
        "📋 لیست فایل‌های شما: 🗂️\nبرای دریافت لینک روی نام فایل و برای حذف روی دکمه مربوطه کلیک کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    )


@router.callback_query(F.data.startswith("vfile_") | F.data.startswith("dfile_"))
async def file_callbacks(callback_query: CallbackQuery):
    action, file_key = callback_query.data.split("_", 1)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type, file_name, views, forwards, deleted FROM files WHERE file_key = %s", (file_key,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این فایل دیگر وجود ندارد.", show_alert=True)
        return

    file_id, file_type, file_name, views, forwards, deleted = row

    if action == "vfile":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این فایل حذف شده است.", show_alert=True)
            return
        
        await callback_query.message.answer(
            f"📁 فایل شما ({file_name}): 👇\n\n"
            f"📊 آمار فایل:\n"
            f"👁️ تعداد مشاهده: {views}\n"
            f"🔄 تعداد ذخیره شده (فوروارد): {forwards}"
        )

        if file_type == "document":
            await callback_query.message.answer_document(file_id)
        elif file_type == "video":
            await callback_query.message.answer_video(file_id)
        elif file_type == "audio":
            await callback_query.message.answer_audio(file_id)
        elif file_type == "photo":
            await callback_query.message.answer_photo(file_id)

        bot_info = await callback_query.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start=file_{file_key}"
        await callback_query.message.answer(
            f"🔗 لینک اختصاصی فایل ({file_name}):\n\n"
            f"{share_link}"
        )
        await callback_query.answer("✅ فایل و آمار ارسال شد.")

    elif action == "dfile":
        cursor.execute("UPDATE files SET deleted = 1 WHERE file_key = %s", (file_key,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await callback_query.answer("🗑️ فایل با موفقیت حذف شد.", show_alert=True)
        try:
            await callback_query.message.edit_text("🗑️ این فایل از لیست شما حذف شد.")
        except Exception:
            pass


@router.message(F.text == "➕ افزودن لینک جدید")
async def add_link_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.waiting_for_link_url)
    await message.answer("🔗 لطفاً لینک طولانی خود را ارسال کنید تا کوتاه شود: 👇", reply_markup=back_keyboard)


@router.message(BotStates.waiting_for_link_url, F.text == "🔙 بازگشت")
async def cancel_link_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔙 به بخش خدمات لینک برگشتید: 👇", reply_markup=link_services_keyboard)


@router.message(BotStates.waiting_for_link_url, F.text)
async def receive_link_url(message: Message, state: FSMContext) -> None:
    user_link = message.text.strip()
    user_id = message.from_user.id

    if not user_link.startswith("http://") and not user_link.startswith("https://"):
        await message.answer("⚠️ لطفاً یک لینک معتبر که با http:// یا https:// شروع می‌شود بفرستید:", reply_markup=back_keyboard)
        return

    user_temp_storage[user_id] = {"long_url": user_link}
    await state.set_state(BotStates.waiting_for_link_name)
    await message.answer("✍️ لینک ثبت شد. حالا یک **نام دلخواه** برای این لینک بفرستید:", reply_markup=back_keyboard)


@router.message(BotStates.waiting_for_link_name, F.text)
async def receive_link_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    link_name = message.text.strip()

    if link_name == "🔙 بازگشت":
        await state.clear()
        user_temp_storage.pop(user_id, None)
        await message.answer("🔙 به بخش خدمات لینک برگشتید: 👇", reply_markup=link_services_keyboard)
        return

    if user_id not in user_temp_storage:
        await state.clear()
        await message.answer("⚠️ اطلاعات منقضی شد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    user_temp_storage[user_id]["link_name"] = link_name
    await state.set_state(BotStates.waiting_for_link_password_choice)
    await message.answer("🔒 آیا می‌خواهید برای این لینک **رمز عبور** تعیین کنید؟", reply_markup=password_choice_keyboard)


@router.message(BotStates.waiting_for_link_password_choice, F.text)
async def receive_password_choice(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "🔙 بازگشت":
        await state.clear()
        user_temp_storage.pop(user_id, None)
        await message.answer("🔙 به بخش خدمات لینک برگشتید: 👇", reply_markup=link_services_keyboard)
        return

    if text == "⏭️ رد کردن":
        user_temp_storage[user_id]["password"] = None
        await state.set_state(BotStates.waiting_for_link_expire_choice)
        await message.answer("⏳ آیا می‌خواهید برای این لینک **تاریخ انقضا** تعیین کنید؟", reply_markup=expire_choice_keyboard)
    elif text == "🔒 بله، گذاشتن رمز عبور":
        await state.set_state(BotStates.waiting_for_link_password)
        await message.answer("🔑 لطفاً رمز عبور دلخواه خود را برای لینک وارد کنید:", reply_markup=back_keyboard)
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کیبورد را انتخاب کنید:", reply_markup=password_choice_keyboard)


@router.message(BotStates.waiting_for_link_password, F.text)
async def receive_link_password(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    password = message.text.strip()

    if password == "🔙 بازگشت":
        await state.set_state(BotStates.waiting_for_link_password_choice)
        await message.answer("🔒 آیا می‌خواهید برای این لینک **رمز عبور** تعیین کنید؟", reply_markup=password_choice_keyboard)
        return

    if user_id not in user_temp_storage:
        await state.clear()
        await message.answer("⚠️ اطلاعات منقضی شد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    user_temp_storage[user_id]["password"] = password
    await state.set_state(BotStates.waiting_for_link_expire_choice)
    await message.answer("⏳ رمز ثبت شد. آیا می‌خواهید برای این لینک **تاریخ انقضا** تعیین کنید؟", reply_markup=expire_choice_keyboard)


@router.message(BotStates.waiting_for_link_expire_choice, F.text)
async def receive_expire_choice(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "🔙 بازگشت":
        await state.set_state(BotStates.waiting_for_link_password_choice)
        await message.answer("🔒 آیا می‌خواهید برای این لینک **رمز عبور** تعیین کنید؟", reply_markup=password_choice_keyboard)
        return

    if text == "⏭️ رد کردن":
        user_temp_storage[user_id]["expire_at"] = None
        user_temp_storage[user_id]["expire_date_str"] = None
        user_temp_storage[user_id]["expire_gregorian"] = None
        await finalize_and_create_link(message, state)
    elif text == "⏳ بله، تعیین تاریخ انقضا":
        await state.set_state(BotStates.waiting_for_link_expire_date)
        await message.answer(
            "📅 لطفاً تاریخ انقضا را به صورت شمسی و در فرمت `سال/ماه/روز` وارد کنید (مثلا: `1405/07/15`): 👇",
            reply_markup=back_keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های کیبورد را انتخاب کنید:", reply_markup=expire_choice_keyboard)


@router.message(BotStates.waiting_for_link_expire_date, F.text)
async def receive_link_expire_date(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    date_text = message.text.strip()

    if date_text == "🔙 بازگشت":
        await state.set_state(BotStates.waiting_for_link_expire_choice)
        await message.answer("⏳ آیا می‌خواهید برای این لینک **تاریخ انقضا** تعیین کنید؟", reply_markup=expire_choice_keyboard)
        return

    if user_id not in user_temp_storage:
        await state.clear()
        await message.answer("⚠️ اطلاعات منقضی شد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    try:
        parts = date_text.split('/')
        if len(parts) != 3:
            raise ValueError("Format error")
        j_year, j_month, j_day = int(parts[0]), int(parts[1]), int(parts[2])
        
        gregorian_date = jalali_to_gregorian(j_year, j_month, j_day)
        iso_expire = gregorian_date.strftime("%Y-%m-%dT23:59:59.000Z")
        
        user_temp_storage[user_id]["expire_at"] = iso_expire
        user_temp_storage[user_id]["expire_date_str"] = date_text
        user_temp_storage[user_id]["expire_gregorian"] = gregorian_date
        
        await finalize_and_create_link(message, state)
    except Exception:
        await message.answer("⚠️ فرمت تاریخ نامعتبر است! لطفاً تاریخ را به صورت صحیح و شمسی مانند `1405/07/15` وارد کنید:", reply_markup=back_keyboard)


async def finalize_and_create_link(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    data = user_temp_storage.pop(user_id, None)

    if not data:
        await state.clear()
        await message.answer("⚠️ خطا رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    long_url = data["long_url"]
    link_name = data["link_name"]
    password = data.get("password")
    expire_at = data.get("expire_at")
    expire_date_str = data.get("expire_date_str")
    expire_gregorian = data.get("expire_gregorian")

    short_url = None
    kutt_id = None
    error_details = ""
    
    payload = {
        "target": long_url
    }
    if password:
        payload["password"] = password
    if expire_at:
        payload["expire_at"] = expire_at

    async with aiohttp.ClientSession() as session:
        headers = {
            "X-API-Key": KUTT_API_KEY,
            "Content-Type": "application/json"
        }
        try:
            async with session.post(KUTT_API_URL, json=payload, headers=headers) as resp:
                if resp.status in (200, 201):
                    resp_data = await resp.json()
                    short_url = resp_data.get("link") or resp_data.get("full_url")
                    kutt_id = resp_data.get("id")
                    if short_url:
                        parsed_short = urlparse(short_url)
                        parsed_short = parsed_short._replace(netloc="kutt-production-0880.up.railway.app", scheme="https")
                        short_url = urlunparse(parsed_short)
                else:
                    error_details = await resp.text()
                    logging.error(f"Kutt API Error: {resp.status} - {error_details}")
        except Exception as e:
            error_details = str(e)
            logging.error(f"Exception connecting to Kutt API: {e}")

    if not short_url:
        await state.clear()
        await message.answer(f"⚠️ خطا در ارتباط با Kutt:\n`{error_details[:200]}`", parse_mode="Markdown", reply_markup=link_services_keyboard)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM links")
    count = cursor.fetchone()[0]
    link_id = f"link_{user_id}_{count + 1}"

    cursor.execute("""
        INSERT INTO links (link_id, user_id, link_name, long_url, short_url, kutt_id, password, expire_date, expire_gregorian, deleted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
    """, (link_id, user_id, link_name, long_url, short_url, kutt_id, password, expire_date_str, expire_gregorian))
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()
    await message.answer(
        f"🎉 لینک شما با موفقیت کوتاه و تنظیم شد! ✅\n\n"
        f"📌 نام: {link_name}\n"
        f"🔒 رمز عبور: {'دارد ✅' if password else 'ندارد ❌'}\n"
        f"⏳ تاریخ انقضا: {expire_date_str if expire_date_str else 'ندارد ❌'}\n\n"
        f"🔗 لینک کوتاه شده:\n"
        f"{short_url}",
        reply_markup=link_services_keyboard
    )


@router.message(F.text == "📋 لینک‌های من")
async def list_user_links(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link_id, link_name FROM links WHERE user_id = %s AND deleted = 0", (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await message.answer("📭 شما هیچ لینکی ذخیره نکرده‌اید.", reply_markup=link_services_keyboard)
        return

    inline_keyboard = []
    for link_id, link_name in rows:
        btn_view = InlineKeyboardButton(text=f"🌐 {link_name}", callback_data=f"vlink_{link_id}")
        btn_delete = InlineKeyboardButton(text="🗑️ حذف", callback_data=f"dlink_{link_id}")
        inline_keyboard.append([btn_view, btn_delete])

    await message.answer(
        "📋 لیست لینک‌های شما: 🔗",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    )


@router.callback_query(F.data.startswith("vlink_") | F.data.startswith("dlink_"))
async def link_callbacks(callback_query: CallbackQuery):
    action, link_key_id = callback_query.data.split("_", 1)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link_name, long_url, short_url, kutt_id, password, expire_date, expire_gregorian, deleted FROM links WHERE link_id = %s", (link_key_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این لینک وجود ندارد.", show_alert=True)
        return

    link_name, long_url, short_url, kutt_id, password, expire_date, expire_gregorian, deleted = row

    if action == "vlink":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این لینک حذف شده است.", show_alert=True)
            return

        total_clicks = 0
        referrers_text = "ندارد یا مستقیم ❌"
        browsers_text = "اطلاعاتی ثبت نشده ❌"
        countries_text = "اطلاعاتی ثبت نشده ❌"
        os_text = "اطلاعاتی ثبت نشده ❌"

        if kutt_id:
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": KUTT_API_KEY}
                stats_urls = [
                    f"https://kutt-production-0880.up.railway.app/api/v2/links/{kutt_id}/stats",
                    f"https://kutt-production-0880.up.railway.app/api/v2/links/stats?id={kutt_id}"
                ]
                stats_data = None
                for stats_url in stats_urls:
                    try:
                        async with session.get(stats_url, headers=headers) as resp:
                            if resp.status == 200:
                                stats_data = await resp.json()
                                break
                    except Exception as e:
                        logging.error(f"Error fetching stats from {stats_url}: {e}")

                if stats_data:
                    # خواندن تعداد کلیک از کلید total
                    total_clicks = stats_data.get("total", 0)
                    if isinstance(total_clicks, dict):
                        total_clicks = total_clicks.get("count", 0)

                    # 1. منابع ورود (Referrer)
                    refs = stats_data.get("referrer", []) or stats_data.get("referrers", [])
                    if refs:
                        ref_list = []
                        for item in refs[:5]:
                            name = item.get('name') or item.get('_id') or 'Direct/مستقیم'
                            cnt = item.get('value') or item.get('count') or 0
                            if cnt > 0:
                                ref_list.append(f"• {name}: {cnt} بار")
                        if ref_list:
                            referrers_text = "\n" + "\n".join(ref_list)

                    # 2. مرورگرها (Browsers)
                    browsers = stats_data.get("browser", []) or stats_data.get("browsers", [])
                    if browsers:
                        b_list = []
                        for item in browsers[:5]:
                            name = item.get('name') or 'سایر'
                            cnt = item.get('value') or 0
                            if cnt > 0:
                                b_list.append(f"• {name}: {cnt} بار")
                        if b_list:
                            browsers_text = "\n" + "\n".join(b_list)

                    # 3. کشورها (Countries)
                    countries = stats_data.get("country", []) or stats_data.get("countries", [])
                    if countries:
                        c_list = []
                        for item in countries[:5]:
                            name = item.get('name') or 'سایر'
                            cnt = item.get('value') or 0
                            if cnt > 0:
                                c_list.append(f"• {name}: {cnt} بار")
                        if c_list:
                            countries_text = "\n" + "\n".join(c_list)

                    # 4. سیستم‌عامل‌ها (Operating Systems)
                    os_list_data = stats_data.get("os", []) or stats_data.get("operating_systems", [])
                    if os_list_data:
                        o_list = []
                        for item in os_list_data[:5]:
                            name = item.get('name') or 'سایر'
                            cnt = item.get('value') or 0
                            if cnt > 0:
                                o_list.append(f"• {name}: {cnt} بار")
                        if o_list:
                            os_text = "\n" + "\n".join(o_list)

        if password:
            pass_text = f"🔒 رمز عبور: {password}"
        else:
            pass_text = "🔒 رمز عبور: ندارد ❌"

        if expire_date:
            if expire_gregorian and datetime.now() > expire_gregorian:
                expire_text = f"⏳ تاریخ انقضا: {expire_date} (منقضی شده ❌)"
            else:
                expire_text = f"⏳ تاریخ انقضا: {expire_date} ✅"
        else:
            expire_text = "⏳ تاریخ انقضا: ندارد ❌"

        await callback_query.message.answer(
            f"📊 اطلاعات و آمار لینک ({link_name}):\n\n"
            f"🌐 لینک اصلی:\n{long_url}\n\n"
            f"🔗 لینک کوتاه:\n{short_url}\n\n"
            f"👁️ کل کلیک‌ها: {total_clicks}\n"
            f"───────────────────\n"
            f"📍 **منابع ورود کاربران** (از کجا وارد شده‌اند):\n{referrers_text}\n\n"
            f"💻 **مرورگرهای استفاده شده**:\n{browsers_text}\n\n"
            f"🌍 **کشور بازدیدکنندگان**:\n{countries_text}\n\n"
            f"📱 **سیستم‌عامل دستگاه‌ها**:\n{os_text}\n\n"
            f"───────────────────\n"
            f"{pass_text}\n"
            f"{expire_text}"
        )
        await callback_query.answer("✅ آمار کامل ارسال شد.")

    elif action == "dlink":
        cursor.execute("UPDATE links SET deleted = 1 WHERE link_id = %s", (link_key_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await callback_query.answer("🗑️ لینک با موفقیت حذف شد.", show_alert=True)
        try:
            await callback_query.message.edit_text("🗑️ این لینک حذف شد.")
        except Exception:
            pass


async def main() -> None:
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
