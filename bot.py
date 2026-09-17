import asyncio
import logging
import sys
import os
import psycopg2
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
import aiohttp

TOKEN = "8844658209:AAH41cGWIdMiSLQq8PO5VNU_qds7vWJpmmE"
DATABASE_URL = os.getenv("DATABASE_URL")

router = Router()

# --- راه‌اندازی و اتصال به پایگاه داده PostgreSQL ---
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
    
    # جدول فایل‌ها
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_key TEXT PRIMARY KEY,
            user_id BIGINT,
            file_id TEXT,
            file_type TEXT,
            file_name TEXT,
            deleted INTEGER DEFAULT 0
        )
    """)
    
    # جدول لینک‌های کاربران
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            long_url TEXT,
            short_url TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()

# وضعیت‌های ربات برای ثبت نام فایل و لینک
class UploadStates(StatesGroup):
    waiting_for_file_name = State()
    waiting_for_new_link = State()

# دیتابیس موقت برای نگهداری فایل در حال آپلود هر کاربر پیش از نام‌گذاری
user_temp_file = {}

# --- کیبوردها ---
main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🗂️ مدیریت فایل‌ها"), KeyboardButton(text="🔗 خدمات لینک")],
        [KeyboardButton(text="👤 حساب کاربری")]
    ],
    resize_keyboard=True,
    input_field_placeholder="لطفاً یکی از گزینه‌های زیر را انتخاب کنید... 👇"
)

link_services_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن لینک جدید"), KeyboardButton(text="📋 لینک‌های من")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

file_management_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📁 آپلود فایل و دریافت لینک"), KeyboardButton(text="📂 فایل‌های من")],
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

file_received_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📥 دریافت لینک دانلود")],
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
        cursor.close()
        conn.close()

        if row:
            file_id, file_type, deleted = row
            if deleted == 1:
                await message.answer("⚠️ متأسفانه فایل مورد نظر توسط کاربر حذف شده است. ❌")
            else:
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
            await message.answer("⚠️ متأسفانه فایل مورد نظر پیدا نشد یا منقضی شده است. ❌")

        await message.answer(
            "🏠 به منوی اصلی برگشتید: 👇",
            reply_markup=main_menu_keyboard
        )
        return

    await message.answer(
        f"سلام {message.from_user.first_name}! 👋 به ربات مگابات خوش آمدید. 🤖\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=main_menu_keyboard
    )


@router.message(F.text == "🗂️ مدیریت فایل‌ها")
async def management_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🛠️ به بخش مدیریت فایل‌ها خوش آمدید. 📂\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=file_management_keyboard
    )


@router.message(F.text == "📁 آپلود فایل و دریافت لینک")
async def upload_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "📂 لطفاً فایل خود را با هر فرمت دلخواهی که دارید ارسال کنید! 📎✨",
        reply_markup=back_keyboard
    )


# --- بخش خدمات لینک ---

@router.message(F.text == "🔗 خدمات لینک")
async def link_services_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🔗 به بخش خدمات لینک و کوتاه‌کننده خوش آمدید. 🌐\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=link_services_keyboard
    )


@router.message(F.text == "➕ افزودن لینک جدید")
async def add_new_link_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(UploadStates.waiting_for_new_link)
    await message.answer(
        "🔗 لطفاً لینک طولانی خود را ارسال کنید تا آن را کوتاه کنم و در لیست شما ذخیره کنم: 📝✨",
        reply_markup=back_keyboard
    )


async def shorten_url(long_url: str) -> str:
    api_url = f"https://is.gd/create.php?format=simple&url={long_url}"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            if response.status == 200:
                short_url = await response.text()
                return short_url.strip()
            else:
                return None


@router.message(UploadStates.waiting_for_new_link, F.text)
async def process_new_link(message: Message, state: FSMContext) -> None:
    user_link = message.text.strip()
    
    if user_link == "🔙 بازگشت":
        await state.clear()
        await message.answer(
            "🔙 به بخش خدمات لینک برگشتید: 👇",
            reply_markup=link_services_keyboard
        )
        return

    if not (user_link.startswith("http://") or user_link.startswith("https://") or user_link.startswith("www.")):
        await message.answer("⚠️ لطفاً یک لینک معتبر (شروع شده با http یا https) ارسال کنید: ❌")
        return

    waiting_msg = await message.answer("⏳ در حال کوتاه کردن لینک... 🔄")
    short_result = await shorten_url(user_link)

    if short_result and short_result.startswith("http"):
        user_id = message.from_user.id
        
        # ذخیره در پایگاه داده PostgreSQL
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO links (user_id, long_url, short_url) VALUES (%s, %s, %s)", (user_id, user_link, short_result))
        conn.commit()
        cursor.close()
        conn.close()

        await state.clear()
        await waiting_msg.edit_text(
            f"🎉 لینک شما با موفقیت کوتاه و ذخیره شد! ✅\n\n🔗 لینک کوتاه شده:\n`{short_result}`\n\n✨ می‌توانید از این لینک در پیامک یا هر جای دیگری استفاده کنید.",
            parse_mode="Markdown"
        )
        await message.answer(
            "🔙 بازگشت به بخش خدمات لینک: 👇",
            reply_markup=link_services_keyboard
        )
    else:
        await waiting_msg.edit_text("❌ خطا در کوتاه‌کردن لینک. لطفاً دوباره تلاش کنید.")


@router.message(F.text == "📋 لینک‌های من")
async def list_user_links(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT long_url, short_url FROM links WHERE user_id = %s", (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await message.answer(
            "📭 شما هنوز هیچ لینکی در ربات ذخیره نکرده‌اید. ⚠️",
            reply_markup=link_services_keyboard
        )
        return

    links_text = "📋 لیست لینک‌های کوتاه شده‌ی شما: 👇\n\n"
    for idx, item in enumerate(rows, 1):
        links_text += f"{idx}. اصلی: {item[0]}\n   کوتاه: `{item[1]}`\n\n"

    await message.answer(
        links_text,
        parse_mode="Markdown",
        reply_markup=link_services_keyboard
    )


@router.message(F.text == "👤 حساب کاربری")
async def user_account_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👤 **اطلاعات حساب کاربری شما:** 📊\n\n✨ وضعیت اشتراک: عادی 🌟\n🎁 موجودی ترافیک: رایگان 🚀",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard
    )


@router.message(F.text == "🔙 بازگشت")
async def back_action(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🔙 به بخش مدیریت فایل‌ها برگشتید: 👇",
        reply_markup=file_management_keyboard
    )


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 به منوی اصلی برگشتید: 👇",
        reply_markup=main_menu_keyboard
    )


@router.message(F.document | F.video | F.audio | F.photo)
async def handle_files(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    
    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    else:
        return

    user_temp_file[user_id] = {
        "file_id": file_id,
        "type": file_type
    }

    await state.set_state(UploadStates.waiting_for_file_name)
    await message.answer(
        "✅ فایل با موفقیت دریافت شد. 📁\n\n✍️ لطفاً یک نام (فقط به صورت متن) برای این فایل انتخاب و ارسال کنید: 👇",
        reply_markup=back_keyboard
    )


@router.message(UploadStates.waiting_for_file_name, F.text)
async def save_file_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    file_name = message.text.strip()

    if file_name == "🔙 بازگشت":
        await state.clear()
        await message.answer(
            "🔙 به بخش مدیریت فایل‌ها برگشتید: 👇",
            reply_markup=file_management_keyboard
        )
        return

    if user_id not in user_temp_file:
        await message.answer("⚠️ خطایی رخ داد. لطفاً دوباره فایل خود را ارسال کنید. ❌", reply_markup=file_management_keyboard)
        await state.clear()
        return

    file_info = user_temp_file.pop(user_id)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files")
    count = cursor.fetchone()[0]
    file_key = f"{user_id}_{count + 1}"

    cursor.execute("""
        INSERT INTO files (file_key, user_id, file_id, file_type, file_name, deleted)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (file_key, user_id, file_info["file_id"], file_info["type"], file_name))
    conn.commit()
    cursor.close()
    conn.close()

    await state.update_data(current_file_key=file_key)
    await state.set_state(None)

    await message.answer(
        f"🎉 نام فایل با موفقیت ثبت شد: <b>{file_name}</b> ✅\n\nحالا روی دکمه‌ی زیر کلیک کنید تا لینک دانلود را دریافت کنید: 👇",
        reply_markup=file_received_keyboard
    )


@router.message(UploadStates.waiting_for_file_name)
async def invalid_file_name(message: Message) -> None:
    await message.answer("⚠️ لطفاً نام فایل را **فقط به صورت متن** ارسال کنید: ❌")


@router.message(F.text == "📥 دریافت لینک دانلود")
async def get_download_link(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_key = data.get("current_file_key")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_name, deleted FROM files WHERE file_key = %s", (file_key,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if file_key and row and row[1] == 0:
        bot_info = await message.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start=file_{file_key}"
        file_name = row[0]

        await message.answer(
            f"🔗 لینک اختصاصی دانلود فایل (<b>{file_name}</b>): 📥\n{share_link}\n\n✨ هرکس روی این لینک کلیک کند، ربات مستقیماً فایل را به او تحویل می‌دهد! 🚀",
            reply_markup=file_management_keyboard
        )
        await state.clear()
    else:
        await message.answer(
            "⚠️ ابتدا یک فایل جدید ارسال کنید و برای آن نام انتخاب کنید. ❌",
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
        await message.answer(
            "📭 شما هنوز هیچ فایلی در ربات آپلود نکرده‌اید. ⚠️",
            reply_markup=file_management_keyboard
        )
        return

    inline_keyboard = []
    for file_key, file_name in rows:
        btn_view = InlineKeyboardButton(text=f"📄 {file_name}", callback_data=f"view_{file_key}")
        btn_delete = InlineKeyboardButton(text="🗑️ حذف فایل", callback_data=f"del_{file_key}")
        inline_keyboard.append([btn_view, btn_delete])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await message.answer(
        "📋 فایل‌های شما به شرح زیر است: 📂\n\nبرای مشاهده هر فایل روی نام آن و برای حذف روی دکمه‌ی مربوطه کلیک کنید: 👇",
        reply_markup=keyboard
    )
    await message.answer(
        "🔙 برای بازگشت از منوی زیر استفاده کنید: 👇",
        reply_markup=file_management_keyboard
    )


@router.callback_query(F.data.startswith("view_") | F.data.startswith("del_"))
async def process_file_callback(callback_query):
    data = callback_query.data
    action, file_key = data.split("_", 1)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type, file_name, deleted FROM files WHERE file_key = %s", (file_key,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این فایل دیگر وجود ندارد. ❌", show_alert=True)
        return

    file_id, file_type, file_name, deleted = row

    if action == "view":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این فایل حذف شده است. ❌", show_alert=True)
            return
        
        await callback_query.message.answer(f"📦 فایل درخواستی شما (نام: {file_name}): 📥")
        if file_type == "document":
            await callback_query.message.answer_document(file_id)
        elif file_type == "video":
            await callback_query.message.answer_video(file_id)
        elif file_type == "audio":
            await callback_query.message.answer_audio(file_id)
        elif file_type == "photo":
            await callback_query.message.answer_photo(file_id)
            
        await callback_query.answer("✅ فایل ارسال شد. 🚀")

    elif action == "del":
        cursor.execute("UPDATE files SET deleted = 1 WHERE file_key = %s", (file_key,))
        conn.commit()
        cursor.close()
        conn.close()

        await callback_query.answer("🗑️ فایل با موفقیت حذف شد. ✅", show_alert=True)
        try:
            await callback_query.message.edit_text("✅ این فایل از لیست شما حذف شد. 🗑️")
        except Exception:
            pass


async def main() -> None:
    bot = Bot(token=TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
