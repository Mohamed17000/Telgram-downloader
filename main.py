import os
import sys
import re
import asyncio

# Fix for Pyrogram on Python 3.14+: ensure there is an event loop before import
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

from downloader import extract_video_info, download_video

# Load environment variables
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    print("Error: Please fill API_ID, API_HASH, and BOT_TOKEN in the .env file.")
    exit(1)

# Initialize Pyrogram Client
app = Client(
    "youtube_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# A simple dictionary to track user states and video info
# Format: {user_id: {"state": "waiting_for_url", "current_url": "..."}}
user_data = {}

# Regex for basic YouTube URL validation
YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'

def is_valid_youtube_url(url: str) -> bool:
    return bool(re.match(YOUTUBE_REGEX, url))

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    welcome_text = (
        "مرحباً بك في بوت تحميل فيديوهات يوتيوب بصيغ وجودات متعددة! 🎥\n\n"
        "أنا أستطيع تحميل الفيديوهات بأي حجم بفضل استخدامي لتقنية MTProto.\n"
        "اضغط على الزر أدناه للبدء."
    )
    
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("ابدأ 🚀", callback_data="start_download")]]
    )
    
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("start_download"))
async def prompt_for_url(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Update state: listening for URL
    user_data[user_id] = {"state": "waiting_for_url"}
    
    await callback_query.message.edit_text(
        "ممتاز! الآن، يرجى إرسال رابط فيديو يوتيوب الذي تريد تحميله 🔗:"
    )

@app.on_message(filters.text & filters.private)
async def handle_text_messages(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = user_data.get(user_id, {})
    user_state = state_info.get("state")
    
    if user_state == "waiting_for_url":
        url = message.text.strip()
        
        if not is_valid_youtube_url(url):
            await message.reply_text("عذراً، هذا الرابط لا يبدو كرابط يوتيوب صحيح. يرجى إرسال رابط صالح.")
            return
        
        processing_msg = await message.reply_text("جاري استخراج معلومات الفيديو... يرجى الانتظار ⏳\n*(قد يستغرق هذا بضع ثوانٍ)*")
        
        # Run synchronous extraction in executor so it doesn't block
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, extract_video_info, url)
        
        if not info or not info.get('formats'):
            await processing_msg.edit_text("عذراً، حدث خطأ أثناء استخراج معلومات الفيديو. يرجى التأكد من الرابط والمحاولة مرة أخرى.")
            user_data.pop(user_id, None)
            return
        
        # Build inline keyboard options from formats
        buttons = []
        for fmt in info['formats']:
            callback_data = f"dl_{fmt['format_id']}"
            # Ensure callback_data isn't too long (Telegram limit is 64 bytes)
            # If it's too long, we might need a cache mechanism. For now, we'll slice it if needed,
            # but usually it's short enough.
            if len(callback_data) > 64:
                # We'd need a short hash to index the real format, but let's hope it's under 64 for bestaudio/bestvideo...
                pass 
            
            buttons.append([InlineKeyboardButton(fmt['resolution'], callback_data=callback_data)])
            
        keyboard = InlineKeyboardMarkup(buttons)
        
        # Save URL in state for the callback query to access
        user_data[user_id] = {
            "state": "waiting_format_selection",
            "url": url,
            "title": info['title']
        }
        
        title_text = f"**{info['title']}**\nاختر الصيغة التي تريد التحميل بها:"
        
        await processing_msg.edit_text(title_text, reply_markup=keyboard)
        
    else:
        # If no state matches, prompt to start again
        await message.reply_text("أرسل /start للبدء.")

@app.on_callback_query(filters.regex(r"^dl_"))
async def process_download(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Check if we have the URL in state
    state_info = user_data.get(user_id, {})
    url = state_info.get("url")
    
    if not url:
        await callback_query.answer("انتهت صلاحية الجلسة. يرجى إرسال الرابط من جديد.", show_alert=True)
        return
    
    format_id = callback_query.data.replace("dl_", "")
    
    # Acknowledge the button press
    await callback_query.answer("جاري معالجة طلبك...")
    
    # Edit message to show downloading status
    status_msg = await callback_query.message.edit_text("⏳ جاري تحميل الفيديو من يوتيوب... قد يستغرق الأمر بعض الوقت حسب حجم الفيديو.")
    
    try:
        # Download the video synchronously in the executor
        file_path = await download_video(url, format_id)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("عذراً، فشل تحميل الفيديو. حاول اختيار جودة أخرى.")
            return
            
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        print(f"Downloaded file size: {file_size_mb:.2f} MB")
        
        await status_msg.edit_text(f"✅ تم التحميل محلياً بنجاح!\nحجم الملف: `{file_size_mb:.2f} MB`\n\n📤 جاري الرفع إلى تيليجرام... (هذا بفضل MTProto!)")
        
        # Determine if it's audio or video to send appropriately
        if format_id == 'bestaudio' or (isinstance(file_path, str) and file_path.endswith('.mp3')):
            await client.send_audio(
                chat_id=callback_query.message.chat.id,
                audio=file_path,
                caption=f"🎵 {state_info.get('title', 'Audio')}"
            )
        else:
            await client.send_video(
                chat_id=callback_query.message.chat.id,
                video=file_path,
                caption=f"🎥 {state_info.get('title', 'Video')}",
                supports_streaming=True
            )
            
        await status_msg.delete()
        
    except Exception as e:
        print(f"Error during download/upload process: {e}")
        await status_msg.edit_text("❌ حدث خطأ غير متوقع أثناء المعالجة.")
        
    finally:
        # Clean up local file
        if 'file_path' in locals() and isinstance(file_path, str) and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
                
        # Clear state
        user_data.pop(user_id, None)

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
