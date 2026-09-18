import asyncio
import logging
import sys
import os
import aiohttp
import psycopg2
from urllib.parse import urlparse

from aiohttp import web
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

# دریافت دامنه عمومی از متغیرهای محیطی Railway (مثل your-app.up.railway.app)
# اگر روی لوکال تست می‌کنی، پیش‌فرض روی پورت محلی می‌رود
RAILWAY_STATIC_URL = os.getenv("RAILWAY_STATIC_URL", "localhost:8080")

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

class BotStates(StatesGroup):
    waiting_for_file_upload = State()
    waiting_for_file_name = State()
    waiting_for_link_url = State()
    waiting_for_link_name = State()

user_temp_storage = {}

# کیبوردها
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
                await message.answer("⚠️ متأسفانه این فایل توسط صاحب آن حذف شده است. ❌")
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


# ================= بخش آپلود فایل =================

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
        INSERT INTO files (file_key, user_id, file_id, file_type, file_name, deleted)
        VALUES (%s, %s, %s, %s, %s, 0)
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
    cursor.execute("SELECT file_id, file_type, file_name, deleted FROM files WHERE file_key = %s", (file_key,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این فایل دیگر وجود ندارد.", show_alert=True)
        return

    file_id, file_type, file_name, deleted = row

    if action == "vfile":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این فایل حذف شده است.", show_alert=True)
            return
        
        await callback_query.message.answer(f"📁 فایل شما ({file_name}): 👇")
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
        await callback_query.answer("✅ فایل و لینک ارسال شد.")

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


# ================= بخش خدمات لینک (جهانی و وب‌پایه) =================

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
        await message.answer("⚠️ خطا رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=link_services_keyboard)
        return

    long_url = user_temp_storage.pop(user_id)["long_url"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM links")
    count = cursor.fetchone()[0]
    # تولید یک شناسه کوتاه برای لینک
    short_code = f"s{count + 1}"
    link_id = f"link_{user_id}_{count + 1}"
    
    # ساخت لینک کوتاه جهانی بر اساس آدرس دامنه هاست
    base_domain = RAILWAY_STATIC_URL
    if not base_domain.startswith("http"):
        base_domain = f"https://{base_domain}"
    short_url = f"{base_domain}/{short_code}"

    cursor.execute("""
        INSERT INTO links (link_id, user_id, link_name, long_url, short_url, deleted)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (short_code, user_id, link_name, long_url, short_url))
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()
    await message.answer(
        f"🎉 لینک شما با موفقیت کوتاه شد! ✅\n\n"
        f"📌 نام: {link_name}\n"
        f"🔗 لینک کوتاه جهانی:\n"
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
    cursor.execute("SELECT link_name, long_url, short_url, deleted FROM links WHERE link_id = %s", (link_key_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        await callback_query.answer("⚠️ این لینک وجود ندارد.", show_alert=True)
        return

    link_name, long_url, short_url, deleted = row

    if action == "vlink":
        cursor.close()
        conn.close()
        if deleted == 1:
            await callback_query.answer("⚠️ این لینک حذف شده است.", show_alert=True)
            return
        
        await callback_query.message.answer(
            f"📊 اطلاعات لینک ({link_name}):\n\n"
            f"🌐 لینک اصلی:\n{long_url}\n\n"
            f"🔗 لینک کوتاه:\n{short_url}"
        )
        await callback_query.answer("✅ اطلاعات ارسال شد.")

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


# ================= بخش وب‌سرور داخلی برای ریدایرکت لینک‌ها =================

async def handle_redirect(request):
    short_code = request.match_info.get("short_code")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT long_url, deleted FROM links WHERE link_id = %s", (short_code,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row:
        long_url, deleted = row
        if deleted == 0:
            raise web.HTTPFound(long_url)
            
    return web.Response(text="404 - لینک مورد نظر پیدا نشد یا حذف شده است.", status=404)


async def run_web_server():
    app = web.Application()
    app.router.add_get("/{short_code}", handle_redirect)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


async def main() -> None:
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    # راه‌اندازی همزمان وب‌سرور و بات تلگرام
    await run_web_server()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
