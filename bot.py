import asyncio
import logging
import sys
import os
import random
import string
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
    InlineKeyboardButton,
    CallbackQuery
)

TOKEN = "8844658209:AAH41cGWIdMiSLQq8PO5VNU_qds7vWJpmmE"
DATABASE_URL = os.getenv("DATABASE_URL")

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
            deleted INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id SERIAL PRIMARY KEY,
            link_id TEXT UNIQUE,
            user_id BIGINT,
            link_name TEXT,
            long_url TEXT,
            short_url TEXT,
            deleted INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()

class UploadStates(StatesGroup):
    waiting_for_file_name = State()
    waiting_for_link_url = State()
    waiting_for_link_name = State()

user_temp_file = {}
user_temp_link = {}

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


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1 and args[1].startswith("s="):
        random_code = args[1].replace("s=", "")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT link_name, long_url FROM links WHERE short_url LIKE %s AND deleted = 0", (f"%?s={random_code}",))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            link_name, long_url = row
            await message.answer(
                f"🎁 لینک اصلیِ شما (نام: <b>{link_name}</b>):\n\n{long_url}"
            )
        else:
            await message.answer("⚠️ متأسفانه لینک مورد نظر پیدا نشد یا منقضی شده است. ❌")
            
        await message.answer(
            "🏠 به منوی اصلی برگشتید: 👇",
            reply_markup=main_menu_keyboard
        )
        return

    elif len(args) > 1 and args[1].startswith("file_"):
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


@router.message(F.text == "🔗 خدمات لینک")
async def link_services_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🔗 به بخش خدمات لینک و کوتاه‌کننده خوش آمدید. 🌐\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=link_services_keyboard
    )


@router.message(F.text == "➕ افزودن لینک جدید")
async def add_new_link_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(UploadStates.waiting_for_link_url)
    await message.answer(
        "🔗 لطفاً لینک طولانی خود را ارسال کنید تا آن را کوتاه کنم: 📝✨",
        reply_markup=back_keyboard
    )


@router.message(UploadStates.waiting_for_link_url, F.text)
async def process_link_url(message: Message, state: FSMContext) -> None:
    user_link = message.text.strip()
    user_id = message.from_user.id
    
    if user_link == "🔙 بازگشت":
        await state.clear()
        await message.answer("🔙 به بخش خدمات لینک برگشتید: 👇", reply_markup=link_services_keyboard)
        return

    if not (user_link.startswith("http://") or user_link.startswith("https://") or user_link.startswith("www.")):
        await message.answer("⚠️ لطفاً یک لینک معتبر (شروع شده با http یا https) ارسال کنید: ❌")
        return

    user_temp_link[user_id] = {"long_url": user_link}
    await state.set_state(UploadStates.waiting_for_link_name)
    await message.answer(
        "✍️ لینک دریافت شد. حالا لطفاً یک **نام دلخواه** برای این لینک ارسال کنید (تا در لیست لینک‌های شما نمایش داده شود): 👇",
        reply_markup=back_keyboard
    )


@router.message(UploadStates.waiting_for_link_name, F.text)
async def process_link_name(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    link_name = message.text.strip()

    if link_name == "🔙 بازگشت":
        await state.clear()
        await message.answer("🔙 به بخش خدمات لینک برگشتید: 👇", reply_markup=link_services_keyboard)
        return

    if user_id not in user_temp_link:
        await state.clear()
        await message.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    long_url = user_temp_link.pop(user_id)["long_url"]

    waiting_msg = await message.answer("⏳ در حال تولید لینک کوتاه... 🔄")
    
    random_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    bot_info = await message.bot.get_me()
    short_result = f"https://t.me/{bot_info.username}?s={random_code}"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM links")
    count = cursor.fetchone()[0]
    link_id = f"link_{user_id}_{count + 1}"

    cursor.execute("""
        INSERT INTO links (link_id, user_id, link_name, long_url, short_url, deleted)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (link_id, user_id, link_name, long_url, short_result))
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()
    await waiting_msg.edit_text(
        f"🎉 لینک شما با موفقیت کوتاه و ذخیره شد! ✅\n\n"
        f"📌 نام لینک: <b>{link_name}</b>\n"
        f"🔗 لینک کوتاه شده:\n`{short_result}`",
        parse_mode="HTML"
    )
    await message.answer(
        "🔙 بازگشت به بخش خدمات لینک: 👇",
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
        await message.answer(
            "📭 شما هنوز هیچ لینکی در ربات ذخیره نکرده‌اید. ⚠️",
            reply_markup=link_services_keyboard
        )
        return

    inline_keyboard = []
    for link_id, link_name in rows:
        btn_view = InlineKeyboardButton(text=f"🌐 {link_name}", callback_data=f"vlink_{link_id}")
        btn_delete = InlineKeyboardButton(text="🗑️ حذف لینک", callback_data=f"dlink_{link_id}")
        inline_keyboard.append([btn_view, btn_delete])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await message.answer(
        "📋 لیست لینک‌های کوتاه شده‌ی شما: 🔗\n\nبرای مشاهده جزئیات روی نام لینک و برای حذف روی دکمه‌ی مربوطه کلیک کنید: 👇",
        reply_markup=keyboard
    )
    await message.answer(
        "🔙 برای بازگشت از منوی زیر استفاده کنید: 👇",
        reply_markup=link_services_keyboard
    )


@router.callback_query(F.data.startswith("vlink_") | F.data.startswith("dlink_"))
async def process_link_callback(callback_query: CallbackQuery):
    data = callback_query.data
    parts = data.split("_", 1)
    action = parts[0]
    link_key_id = parts[1]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link_name, long_url, short_url, deleted FROM links WHERE link_id = %s", (link_key_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این لینک دیگر وجود ندارد. ❌", show_alert=True)
        return

    link_name, long_url, short_url, deleted = row

    if action == "vlink":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این لینک حذف شده است. ❌", show_alert=True)
            return
        
        await callback_query.message.answer(
            f"📊 **اطلاعات لینک ({link_name}):**\n\n"
            f"🌐 لینک اصلی (طولانی):\n`{long_url}`\n\n"
            f"🔗 لینک کوتاه شده:\n`{short_url}`",
            parse_mode="Markdown"
        )
        await callback_query.answer("✅ اطلاعات لینک ارسال شد. 🚀")

    elif action == "dlink":
        cursor.execute("UPDATE links SET deleted = 1 WHERE link_id = %s", (link_key_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await callback_query.answer("🗑️ لینک با موفقیت حذف شد. ✅", show_alert=True)
        try:
            await callback_query.message.edit_text("🗑️ این لینک از لیست شما حذف شد.")
        except Exception:
            pass


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
        display_name = file_name if file_name else f"فایل {file_key}"
        btn_view = InlineKeyboardButton(text=f"📂 {display_name}", callback_data=f"vfile_{file_key}")
        btn_delete = InlineKeyboardButton(text="🗑️ حذف فایل", callback_data=f"dfile_{file_key}")
        inline_keyboard.append([btn_view, btn_delete])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await message.answer(
        "📋 لیست فایل‌های آپلود شده‌ی شما: 🗂️\n\nبرای دریافت لینک اختصاصی روی نام فایل و برای حذف روی دکمه‌ی مربوطه کلیک کنید: 👇",
        reply_markup=keyboard
    )
    await message.answer(
        "🔙 برای بازگشت از منوی زیر استفاده کنید: 👇",
        reply_markup=file_management_keyboard
    )


@router.callback_query(F.data.startswith("vfile_") | F.data.startswith("dfile_"))
async def process_file_callback(callback_query: CallbackQuery):
    data = callback_query.data
    parts = data.split("_", 1)
    action = parts[0]
    file_key = parts[1]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_name, deleted FROM files WHERE file_key = %s", (file_key,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این فایل دیگر وجود ندارد. ❌", show_alert=True)
        return

    file_name, deleted = row

    if action == "vfile":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این فایل حذف شده است. ❌", show_alert=True)
            return
        
        bot_info = await callback_query.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start=file_{file_key}"
        
        display_name = file_name if file_name else "فایل اختصاصی"
        await callback_query.message.answer(
            f"🔗 لینک اختصاصی برای فایل (<b>{display_name}</b>):\n\n`{share_link}`",
            parse_mode="HTML"
        )
        await callback_query.answer("✅ لینک فایل ارسال شد. 🚀")

    elif action == "dfile":
        cursor.execute("UPDATE files SET deleted = 1 WHERE file_key = %s", (file_key,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await callback_query.answer("🗑️ فایل با موفقیت حذف شد. ✅", show_alert=True)
        try:
            await callback_query.message.edit_text("🗑️ این لینک از لیست شما حذف شد.")
        except Exception:
            pass


@router.message(F.document | F.video | F.audio | F.photo)
async def handle_user_files(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    user_id = message.from_user.id

    if current_state != UploadStates.waiting_for_file_name.state:
        file_id = None
        file_type = None

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

        if file_id:
            user_temp_file[user_id] = {
                "file_id": file_id,
                "file_type": file_type
            }
            await state.set_state(UploadStates.waiting_for_file_name)
            await message.answer(
                "✍️ فایل شما دریافت شد.\nحالا لطفاً یک **نام دلخواه** برای این فایل وارد کنید (تا در لیست فایل‌های شما ذخیره شود): 👇",
                reply_markup=back_keyboard
            )
        return


@router.message(UploadStates.waiting_for_file_name, F.text)
async def process_file_name_step(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "🔙 بازگشت":
        await state.clear()
        user_temp_file.pop(user_id, None)
        await message.answer("🔙 به بخش مدیریت فایل‌ها برگشتید: 👇", reply_markup=file_management_keyboard)
        return

    if user_id not in user_temp_file:
        await state.clear()
        await message.answer("⚠️ اطلاعات فایل منقضی شد. لطفاً دوباره فایل را ارسال کنید.", reply_markup=file_management_keyboard)
        return

    file_data = user_temp_file.pop(user_id)
    file_id = file_data["file_id"]
    file_type = file_data["file_type"]
    file_name = text

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files")
    count = cursor.fetchone()[0]
    file_key = f"f_{user_id}_{count + 1}"

    cursor.execute("""
        INSERT INTO files (file_key, user_id, file_id, file_type, file_name, deleted)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (file_key, user_id, file_id, file_type, file_name))
    conn.commit()
    cursor.close()
    conn.close()

    bot_info = await message.bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=file_{file_key}"

    await state.clear()
    await message.answer(
        f"🎉 فایل شما با نام **{file_name}** ثبت شد! ✅\n\n"
        f"🔗 لینک اختصاصی برای اشتراک‌گذاری:\n`{share_link}`",
        parse_mode="Markdown",
        reply_markup=file_management_keyboard
    )


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 به منوی اصلی برگشتید: 👇",
        reply_markup=main_menu_keyboard
    )


async def main() -> None:
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
    
