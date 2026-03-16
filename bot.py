import os
import re
import logging
import asyncio
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ─── إعداد السجلات ───────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── الحلقة البرمجية (Asyncio Fix) ───────────────────────────────────────────
# Fix for asyncio on Python 3.14+ on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Pyrogram Dispatcher calls get_event_loop() during Client initialization. 
# We must ensure a loop exists and is set as the current loop.
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Now it is safe to import Pyrogram
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
import yt_dlp

# ─── الإعدادات ──────────────────────────────────────────────────────────────────
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Error: Please fill API_ID, API_HASH, and BOT_TOKEN in the .env file.")
    sys.exit(1)

# Initialize Pyrogram Client
app = Client(
    "youtube_bot",
    api_id=int(API_ID) if API_ID else 0,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ─── مجلد التنزيل المؤقت ─────────────────────────────────────────────────────
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ─── قاموس لحفظ بيانات المستخدمين مؤقتًا ────────────────────────────────────
user_data_store = {}


# ─── دالة التحقق من رابط يوتيوب ──────────────────────────────────────────────
def is_youtube_url(url: str) -> bool:
    pattern = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    return bool(re.match(pattern, url.strip()))


# ─── جلب معلومات الفيديو ──────────────────────────────────────────────────────
def fetch_video_info(url: str) -> dict | None:
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error fetching info: {e}")
        return None


# ─── /start ───────────────────────────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 ابدأ الآن", callback_data="begin")]])

    welcome_text = (
        "🎬 **مرحباً بك في YouTube Downloader Bot!**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 **ما يمكنني فعله:**\n"
        "  • تحميل فيديوهات يوتيوب بجودات مختلفة\n"
        "  • تحميل الصوت فقط بصيغة MP3\n"
        "  • **دعم الفيديوهات الضخمة (حتى 2 جيجابايت)** 🚀\n\n"
        "⚡ **طريقة الاستخدام:**\n"
        "  ١. اضغط على زر **ابدأ الآن**\n"
        "  ٢. أرسل رابط فيديو يوتيوب\n"
        "  ٣. اختر الجودة والصيغة المناسبة\n"
        "  ٤. انتظر حتى يكتمل التحميل 🎉\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    await message.reply_text(
        welcome_text,
        reply_markup=keyboard
    )


# ─── زر ابدأ الآن ─────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex("^begin$"))
async def begin_callback(client: Client, query: CallbackQuery):
    await query.answer()

    user_id = query.from_user.id
    user_data_store[user_id] = {"state": "waiting_url"}

    await query.message.reply_text(
        "🔗 **أرسل رابط فيديو يوتيوب الآن:**\n\n"
        "_مثال: https://www.youtube.com/watch?v=..._"
    )


# ─── استقبال الرسائل (الرابط) ────────────────────────────────────────────────
@app.on_message(filters.text & filters.private)
async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # التحقق من حالة المستخدم
    state = user_data_store.get(user_id, {}).get("state")

    if state != "waiting_url":
        await message.reply_text(
            "⚠️ اضغط على /start أولاً ثم أرسل الرابط."
        )
        return

    if not is_youtube_url(text):
        await message.reply_text(
            "❌ **الرابط غير صالح!**\n\n"
            "يرجى إرسال رابط يوتيوب صحيح.\n"
            "_مثال: https://www.youtube.com/watch?v=..._"
        )
        return

    # إرسال رسالة انتظار
    wait_msg = await message.reply_text(
        "⏳ **جاري جلب معلومات الفيديو...**"
    )

    # جلب معلومات الفيديو في thread منفصل
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, fetch_video_info, text)

    if not info:
        await wait_msg.edit_text(
            "❌ **تعذّر جلب معلومات الفيديو!**\n\n"
            "تأكد من صحة الرابط وحاول مرة أخرى."
        )
        return

    # حفظ البيانات
    user_data_store[user_id] = {
        "state": "choosing_format",
        "url": text,
        "title": info.get("title", "Unknown"),
    }

    duration = info.get("duration", 0)
    mins = duration // 60
    secs = duration % 60
    title = info.get("title", "غير معروف")[:50]

    # بناء لوحة مفاتيح الجودة
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 MP3 - صوت فقط", callback_data="fmt_mp3"),
        ],
        [
            InlineKeyboardButton("📱 360p", callback_data="fmt_360"),
            InlineKeyboardButton("📺 480p", callback_data="fmt_480"),
        ],
        [
            InlineKeyboardButton("🖥️ 720p HD", callback_data="fmt_720"),
            InlineKeyboardButton("🎯 1080p FHD", callback_data="fmt_1080"),
        ],
        [
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel"),
        ],
    ])

    await wait_msg.edit_text(
        f"✅ **تم العثور على الفيديو!**\n\n"
        f"📹 **العنوان:** {title}\n"
        f"⏱️ **المدة:** {mins}:{secs:02d}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎛️ **اختر الجودة والصيغة:**",
        reply_markup=keyboard
    )


# ─── اختيار الصيغة والتحميل ───────────────────────────────────────────────────
@app.on_callback_query(filters.regex("^(fmt_|cancel)"))
async def format_callback(client: Client, query: CallbackQuery):
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel":
        user_data_store.pop(user_id, None)
        await query.message.edit_text(
            "🚫 **تم إلغاء العملية.**\n\nأرسل /start للبدء من جديد."
        )
        return

    data = user_data_store.get(user_id, {})
    if data.get("state") != "choosing_format":
        await query.message.reply_text("⚠️ حدث خطأ. أرسل /start للبدء من جديد.")
        return

    url = data["url"]
    fmt = query.data  # fmt_mp3, fmt_360, fmt_480, fmt_720, fmt_1080

    # خريطة الصيغ
    fmt_map = {
        "fmt_mp3": ("MP3 🎵", "bestaudio/best", "mp3"),
        "fmt_360": ("360p 📱", "bestvideo[height<=360]+bestaudio/best[height<=360]", "mp4"),
        "fmt_480": ("480p 📺", "bestvideo[height<=480]+bestaudio/best[height<=480]", "mp4"),
        "fmt_720": ("720p HD 🖥️", "bestvideo[height<=720]+bestaudio/best[height<=720]", "mp4"),
        "fmt_1080": ("1080p FHD 🎯", "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "mp4"),
    }

    label, ydl_format, ext = fmt_map.get(fmt, ("غير معروف", "best", "mp4"))

    await query.message.edit_text(
        f"⬇️ **جاري تحميل الفيديو بجودة {label}...**\n\n"
        f"⏳ قد يستغرق هذا بعض الوقت، يرجى الانتظار."
    )

    # إعداد خيارات التحميل
    output_template = os.path.join(DOWNLOAD_DIR, f"{user_id}_%(title)s.%(ext)s")

    ydl_opts = {
        "format": ydl_format,
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": ext,
    }

    if fmt == "fmt_mp3":
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    # تحميل الفيديو
    downloaded_file = None
    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info_dict)

        loop = asyncio.get_running_loop()
        downloaded_file = await loop.run_in_executor(None, download)

        # البحث عن الملف الفعلي
        if downloaded_file and isinstance(downloaded_file, str):
            base = os.path.splitext(downloaded_file)[0]
            for candidate_ext in [ext, "mp3", "mp4", "webm", "mkv", "m4a"]:
                candidate = f"{base}.{candidate_ext}"
                if os.path.exists(candidate):
                    downloaded_file = candidate
                    break

        if not downloaded_file or not os.path.exists(downloaded_file):
            raise FileNotFoundError("الملف لم يُنشأ")

        # إرسال الملف
        await query.message.reply_text("📤 **جاري رفع الملف إلى تيليجرام...**")

        if fmt == "fmt_mp3":
            await query.message.reply_audio(
                audio=downloaded_file,
                title=data.get("title", "audio"),
                caption=f"🎵 **{data.get('title', '')}**"
            )
        else:
            await query.message.reply_video(
                video=downloaded_file,
                caption=f"🎬 **{data.get('title', '')}**\n📺 الجودة: {label}",
                supports_streaming=True
            )

        # رسالة الانتهاء
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحميل فيديو آخر", callback_data="begin")]])
        await query.message.reply_text(
            "✅ **تم التحميل والرفع بنجاح!** 🎉",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.message.reply_text(
            f"❌ **حدث خطأ أثناء تحميل الملف أو رفعه.**\n\n"
            f"السبب: `{str(e)[:100]}`"
        )
    finally:
        # حذف الملف المؤقت
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except:
                pass
        user_data_store.pop(user_id, None)


if __name__ == "__main__":
    logger.info("🤖 Bot is starting with Pyrogram...")
    app.run()
