import os
import re
import logging
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError
from flask import Flask
from threading import Thread
import traceback

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not found!")
    exit(1)

logger.info("✅ Bot token loaded")

# Cobalt API endpoint (free alternative to yt-dlp)
COBALT_API = "https://api.cobalt.tools/api/json"

# Flask for health check
app = Flask(__name__)

@app.route('/')
def health():
    return "✅ Bot Running!", 200

@app.route('/health')
def health_check():
    return {"status": "ok"}, 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# YouTube validation
def is_youtube_url(url):
    patterns = [
        r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/(?:watch\?v=|shorts/|embed/)?([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        if re.search(pattern, url):
            return True
    return False

def extract_video_id(url):
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed/)([0-9A-Za-z_-]{11})',
        r'(?:shorts/)([0-9A-Za-z_-]{11})',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def is_playlist(url):
    return 'list=' in url or 'playlist' in url

# Format helpers
def format_duration(seconds):
    try:
        if not seconds:
            return "N/A"
        seconds = int(seconds)
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    except:
        return "N/A"

def format_number(num):
    try:
        return f"{int(num):,}" if num else "N/A"
    except:
        return "N/A"

def format_size(bytes):
    try:
        if not bytes:
            return "Unknown"
        bytes = int(bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} TB"
    except:
        return "Unknown"

# Get video info using Cobalt API
async def get_video_info(url):
    logger.info(f"📹 Getting info via Cobalt: {url[:50]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "url": url,
                "vCodec": "h264",
                "vQuality": "1080",
                "aFormat": "mp3",
                "isAudioOnly": False
            }
            
            async with session.post(COBALT_API, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Cobalt response: {data.get('status', 'unknown')}")
                    
                    # Extract video ID for thumbnail
                    video_id = extract_video_id(url)
                    
                    return {
                        'status': data.get('status'),
                        'url': data.get('url'),
                        'title': f"YouTube Video {video_id[:8]}",
                        'video_id': video_id,
                        'thumbnail': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else '',
                        'raw_data': data
                    }
                else:
                    logger.error(f"❌ Cobalt API error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Info error: {e}")
        return None

# Get download link using Cobalt
async def get_download_link(url, quality='1080', audio_only=False):
    logger.info(f"📥 Getting download link: quality={quality}, audio={audio_only}")
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "url": url,
                "vCodec": "h264",
                "vQuality": quality,
                "aFormat": "mp3",
                "isAudioOnly": audio_only,
                "filenamePattern": "basic"
            }
            
            async with session.post(COBALT_API, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('status') == 'stream' or data.get('status') == 'redirect':
                        download_url = data.get('url')
                        logger.info(f"✅ Got download URL: {download_url[:50]}...")
                        return {
                            'url': download_url,
                            'status': data.get('status'),
                            'filename': data.get('filename', 'video.mp4')
                        }
                    else:
                        logger.error(f"❌ Unexpected status: {data.get('status')}")
                        return None
                else:
                    logger.error(f"❌ Download API error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        return None

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🚀 /start from {update.effective_user.id}")
    
    text = """
🎬 **YouTube Downloader Bot** 🚀

**✨ Features:**
✅ Fast Downloads
✅ Multiple Quality Options
✅ Audio Download (MP3)
✅ YouTube Shorts
✅ Direct Links

**📌 How to Use:**
Just send any YouTube link!

**🎯 Commands:**
/start - Start bot
/help - Get help

**Powered by Cobalt API** ⚡
"""
    
    keyboard = [
        [InlineKeyboardButton("📖 Help", callback_data='help'),
         InlineKeyboardButton("ℹ️ About", callback_data='about')],
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    logger.info("✅ Start sent")

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📖 **How to Use:**

1️⃣ Send any YouTube link
2️⃣ Choose quality (1080p, 720p, 480p, 360p)
3️⃣ Get download link instantly!

**Audio Download:**
Click "Audio MP3" for music

**Shorts:**
Works with YouTube Shorts too!

**Note:** Links expire in 6 hours

💡 **Tip:** For best quality, choose 1080p
"""
    await update.message.reply_text(text, parse_mode='Markdown')

# About command
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
ℹ️ **About This Bot**

🤖 YouTube Downloader
⚡ Powered by Cobalt API
🆓 100% Free
🚀 Fast & Reliable
💾 No data stored

**Version:** 5.0
**Engine:** Cobalt Tools
**Status:** Online 24/7

Made with ❤️
"""
    await update.message.reply_text(text, parse_mode='Markdown')

# Handle YouTube links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    logger.info(f"💬 Message: {text[:50]}...")
    
    # Check for forwarded
    if hasattr(update.message, 'forward_date') and update.message.forward_date:
        urls = re.findall(r'https?://[^\s]+', text)
        if urls:
            text = urls[0]
    
    # Check YouTube URL
    if not is_youtube_url(text):
        return
    
    url = text
    logger.info(f"✅ YouTube URL: {url[:50]}")
    
    try:
        msg = await update.message.reply_text("⏳ **Processing...**", parse_mode='Markdown')
        
        # Get video info
        info = await get_video_info(url)
        
        if not info or info.get('status') not in ['stream', 'redirect', 'picker']:
            await msg.edit_text(
                "❌ **Failed to process video!**\n\n"
                "Possible reasons:\n"
                "• Video is private\n"
                "• Age-restricted\n"
                "• Region blocked\n\n"
                "💡 Try another video!"
            )
            return
        
        # Store in context
        context.user_data['current_url'] = url
        context.user_data['video_info'] = info
        
        video_id = info.get('video_id', '')
        is_short = 'shorts' in url.lower()
        video_type = "📱 Shorts" if is_short else "📺 Video"
        
        caption = f"""
{video_type} **Ready for Download!**

🎬 Video ID: `{video_id}`
📊 Choose your preferred quality:
"""
        
        keyboard = [
            [InlineKeyboardButton("🎬 1080p HD", callback_data='fmt_video_1080')],
            [InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720'),
             InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
            [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360')],
            [InlineKeyboardButton("🎵 Audio MP3", callback_data='fmt_audio')],
        ]
        
        # Try with thumbnail
        if info.get('thumbnail'):
            try:
                await msg.delete()
                await update.message.reply_photo(
                    photo=info['thumbnail'],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                logger.info("✅ Sent with thumbnail")
            except:
                await msg.edit_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await msg.edit_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        logger.info("✅ Options sent")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("❌ An error occurred. Try again!")

# Callback handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"🔘 Button: {data}")
    
    try:
        if data == 'help':
            await help_command(update, context)
            return
        
        if data == 'about':
            await about_command(update, context)
            return
        
        # Format selection
        if data.startswith('fmt_'):
            url = context.user_data.get('current_url')
            
            if not url:
                await query.edit_message_text("❌ Session expired! Send link again.")
                return
            
            await query.edit_message_text("⏳ **Generating download link...**\n\n_Please wait 5-10 seconds_", parse_mode='Markdown')
            
            # Parse quality
            is_audio = 'audio' in data
            quality = '1080'
            
            if '720' in data:
                quality = '720'
            elif '480' in data:
                quality = '480'
            elif '360' in data:
                quality = '360'
            
            # Get download link
            dl_info = await get_download_link(url, quality, is_audio)
            
            if not dl_info or not dl_info.get('url'):
                await query.edit_message_text(
                    "❌ **Failed to generate link!**\n\n"
                    "Try:\n"
                    "• Another quality\n"
                    "• Send link again\n"
                    "• Different video"
                )
                return
            
            dl_url = dl_info['url']
            filename = dl_info.get('filename', 'download')
            
            emoji = "🎵" if is_audio else "🎬"
            format_text = "MP3 Audio" if is_audio else f"{quality}p Video"
            
            # Success message with download link
            keyboard = [
                [InlineKeyboardButton("⬇️ DOWNLOAD NOW", url=dl_url)],
                [InlineKeyboardButton("🔄 Try Another Quality", callback_data='back_to_options')],
            ]
            
            success_msg = f"""
✅ **Download Link Ready!**

{emoji} **Format:** {format_text}
📁 **File:** {filename}

**Click "DOWNLOAD NOW" below!**

⚠️ **Important:**
• Link expires in 6 hours
• Download directly in browser
• Works on all devices

💡 **Tip:** Right-click → Save As
"""
            
            await query.edit_message_text(
                success_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
            logger.info(f"✅ Link sent: {format_text}")
            
        # Back to options
        if data == 'back_to_options':
            url = context.user_data.get('current_url')
            video_id = extract_video_id(url) if url else ''
            
            caption = f"""
📺 **Video Ready!**

🎬 Video ID: `{video_id}`
📊 Choose quality:
"""
            
            keyboard = [
                [InlineKeyboardButton("🎬 1080p HD", callback_data='fmt_video_1080')],
                [InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720'),
                 InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
                [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360')],
                [InlineKeyboardButton("🎵 Audio MP3", callback_data='fmt_audio')],
            ]
            
            await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"❌ Callback error: {e}")
        logger.error(traceback.format_exc())
        await query.message.reply_text("❌ Error occurred. Try again!")

# Error handler
async def error_handler(update, context):
    logger.error(f"❌ Error: {context.error}")
    logger.error(traceback.format_exc())

# Post init
async def post_init(app):
    cmds = [
        BotCommand("start", "🚀 Start bot"),
        BotCommand("help", "📖 Get help"),
    ]
    await app.bot.set_my_commands(cmds)
    logger.info("✅ Commands set")

# Main
def main():
    # Flask
    Thread(target=run_flask, daemon=True).start()
    logger.info("🌐 Flask started")
    
    # Bot
    logger.info("🤖 Creating bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    
    logger.info("=" * 50)
    logger.info("🚀 BOT STARTED - COBALT API!")
    logger.info("=" * 50)
    
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )

if __name__ == '__main__':
    main()
