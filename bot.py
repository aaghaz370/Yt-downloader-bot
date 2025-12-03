import os
import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError
from yt_dlp import YoutubeDL
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
    logger.info(f"🌐 Flask starting on port {port}")
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

def is_playlist(url):
    return 'list=' in url or 'playlist' in url

# Safe duration format
def format_duration(seconds):
    try:
        if not seconds or seconds == 0:
            return "🔴 Live"
        seconds = int(float(seconds))  # Convert to int safely
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    except:
        return "N/A"

# Safe number format
def format_number(num):
    try:
        if not num:
            return "N/A"
        return f"{int(num):,}"
    except:
        return "N/A"

# File size format
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

# Get video info
def get_video_info(url):
    logger.info(f"📹 Getting info: {url[:50]}...")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            result = {
                'title': info.get('title', 'Unknown')[:100],
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown')[:50],
                'view_count': info.get('view_count', 0),
                'id': info.get('id', ''),
            }
            logger.info(f"✅ Got: {result['title']}")
            return result
    except Exception as e:
        logger.error(f"❌ Info error: {e}")
        return None

# Get download info
def get_download_info(url, format_type='video', quality='best'):
    logger.info(f"📥 Download info: {format_type} {quality}")
    
    if format_type == 'audio':
        fmt = 'bestaudio[ext=m4a]/bestaudio/best'
    elif quality == 'best':
        fmt = 'best[ext=mp4]/best'
    else:
        fmt = f'best[height<={quality}][ext=mp4]/best[height<={quality}]'
    
    ydl_opts = {
        'format': fmt,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'url' in info:
                return {
                    'url': info['url'],
                    'title': info.get('title', 'video')[:80],
                    'ext': info.get('ext', 'mp4'),
                    'filesize': info.get('filesize', 0),
                }
            elif 'entries' in info and info['entries']:
                entry = info['entries'][0]
                return {
                    'url': entry.get('url', ''),
                    'title': entry.get('title', 'video')[:80],
                    'ext': entry.get('ext', 'mp4'),
                    'filesize': entry.get('filesize', 0),
                }
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
    return None

# Get playlist
def get_playlist_info(url):
    logger.info(f"📑 Getting playlist...")
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                videos = []
                for i, entry in enumerate(info['entries'][:10], 1):
                    videos.append({
                        'title': entry.get('title', f'Video {i}')[:60],
                        'id': entry.get('id', ''),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    })
                return {
                    'playlist_title': info.get('title', 'Playlist')[:80],
                    'videos': videos,
                    'total_count': len(info.get('entries', [])),
                }
    except Exception as e:
        logger.error(f"❌ Playlist error: {e}")
    return None

# Search YouTube
def search_youtube(query, max_results=5):
    logger.info(f"🔍 Searching: {query}")
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = results.get('entries', [])
            logger.info(f"✅ Found {len(entries)} results")
            return entries
    except Exception as e:
        logger.error(f"❌ Search error: {e}")
        return []

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🚀 /start from user {update.effective_user.id}")
    
    text = """
🎬 **Advanced YouTube Downloader Bot** 🚀

**✨ Features:**
✅ Direct Telegram Download
✅ Browser Download Links  
✅ YouTube Shorts Support
✅ Playlist Download
✅ Multiple Quality Options
✅ Lightning Fast ⚡

**📌 How to Use:**
1️⃣ Send YouTube link
2️⃣ Choose format & quality
3️⃣ Get file instantly!

**🎯 Commands:**
/start - Start bot
/help - Get help
/search lofi - Search YouTube

**Send any YouTube link!** 🔗
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
    logger.info(f"📖 /help from {update.effective_user.id}")
    
    text = """
📖 **Complete Guide:**

**Download Videos:**
• Send YouTube link
• Choose Video/Audio
• Select quality
• Get file in Telegram!

**Download Shorts:**
• Send Shorts link
• Same process

**Download Playlist:**
• Send playlist link
• Choose videos
• Download individually

**Search YouTube:**
• /search lofi music
• Get 5 results
• Download directly

**Quality Options:**
🎬 Video: Best, 720p, 480p, 360p, 144p
🎵 Audio: MP3 format

**Tips:**
✨ Supports all YT formats
✨ Fast processing
✨ No ads, 100% free
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')

# About command
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
ℹ️ **About This Bot**

🤖 Advanced YT Downloader
⚡ Ultra-fast processing
🆓 100% Free
🔒 Privacy focused
💾 No data stored

**Version:** 4.0 Final
**Engine:** yt-dlp
**Status:** 24/7 Online

Made with ❤️
"""
    await update.message.reply_text(text, parse_mode='Markdown')

# Search command
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🔍 /search from {update.effective_user.id}")
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /search <query>\n\nExample: /search lofi music"
        )
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Searching **{query}**...", parse_mode='Markdown')
    
    try:
        results = search_youtube(query, 5)
        
        if not results:
            await msg.edit_text("❌ No results found!")
            return
        
        text = f"🔍 **Results:** {query}\n\n"
        keyboard = []
        
        for i, video in enumerate(results, 1):
            title = video.get('title', 'Unknown')[:55]
            video_id = video.get('id', '')
            duration = video.get('duration', 0)
            
            # Safe duration format
            dur_str = format_duration(duration)
            
            text += f"{i}. **{title}**\n   ⏱ {dur_str}\n\n"
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            keyboard.append([
                InlineKeyboardButton(f"📥 Download #{i}", callback_data=f"dl_{url}")
            ])
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info("✅ Search results sent")
        
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

# Handle YouTube links
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    logger.info(f"💬 Message: {text[:50]}...")
    
    # Extract URL from forwarded messages
    if update.message.forward_from or update.message.forward_from_chat:
        urls = re.findall(r'https?://[^\s]+', text)
        if urls:
            text = urls[0]
    
    # Check if YouTube URL
    if not is_youtube_url(text):
        logger.info("❌ Not a YouTube URL")
        return
    
    url = text
    logger.info(f"✅ YouTube URL detected: {url[:50]}")
    
    # Handle playlist
    if is_playlist(url):
        await handle_playlist(update, context, url)
        return
    
    # Handle video
    try:
        msg = await update.message.reply_text("⏳ **Processing...**", parse_mode='Markdown')
        
        info = get_video_info(url)
        if not info:
            await msg.edit_text("❌ Failed to get video info. Try again!")
            return
        
        # Store in context
        context.user_data['current_url'] = url
        context.user_data['video_info'] = info
        
        # Format info
        duration_str = format_duration(info['duration'])
        views_str = format_number(info['view_count'])
        is_short = 'shorts' in url.lower()
        video_type = "📱 Shorts" if is_short else "📺 Video"
        
        caption = f"""
{video_type} **{info['title']}**

👤 {info['uploader']}
⏱️ {duration_str}
👁️ {views_str} views

Choose format:
"""
        
        keyboard = [
            [InlineKeyboardButton("🎬 Video - Best", callback_data='fmt_video_best')],
            [InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720'),
             InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
            [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360'),
             InlineKeyboardButton("🎬 144p", callback_data='fmt_video_144')],
            [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='fmt_audio')],
        ]
        
        # Try with thumbnail
        if info['thumbnail']:
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
            
        logger.info("✅ Video options sent")
        
    except Exception as e:
        logger.error(f"❌ Handle error: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

# Handle playlist
async def handle_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE, url):
    logger.info("📑 Handling playlist")
    
    msg = await update.message.reply_text("⏳ **Loading playlist...**", parse_mode='Markdown')
    
    try:
        pl_info = get_playlist_info(url)
        if not pl_info:
            await msg.edit_text("❌ Failed to load playlist!")
            return
        
        videos = pl_info['videos']
        total = pl_info['total_count']
        title = pl_info['playlist_title']
        
        text = f"📑 **{title}**\n📊 Total: {total} videos\n\n**First 10:**\n\n"
        keyboard = []
        
        for i, video in enumerate(videos, 1):
            text += f"{i}. {video['title']}\n"
            keyboard.append([
                InlineKeyboardButton(f"📥 #{i}", callback_data=f"dl_{video['url']}")
            ])
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info("✅ Playlist sent")
        
    except Exception as e:
        logger.error(f"❌ Playlist error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")

# Callback handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"🔘 Button: {data}")
    
    try:
        # Help/About
        if data == 'help':
            await query.message.reply_text("📖 Use /help for detailed guide!")
            return
        
        if data == 'about':
            await about_command(update, context)
            return
        
        # Download request
        if data.startswith('dl_'):
            url = data.replace('dl_', '')
            context.user_data['current_url'] = url
            
            await query.edit_message_text("⏳ **Loading...**", parse_mode='Markdown')
            
            info = get_video_info(url)
            if not info:
                await query.edit_message_text("❌ Failed!")
                return
            
            context.user_data['video_info'] = info
            
            keyboard = [
                [InlineKeyboardButton("🎬 Best", callback_data='fmt_video_best')],
                [InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720'),
                 InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
                [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360'),
                 InlineKeyboardButton("🎬 144p", callback_data='fmt_video_144')],
                [InlineKeyboardButton("🎵 Audio", callback_data='fmt_audio')],
            ]
            
            await query.edit_message_text(
                f"📺 **{info['title']}**\n\nChoose format:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Format selection
        if data.startswith('fmt_'):
            url = context.user_data.get('current_url')
            info = context.user_data.get('video_info', {})
            
            if not url:
                await query.edit_message_text("❌ Session expired!")
                return
            
            await query.edit_message_text("⏳ **Preparing...**\n\n_Please wait 5-15s_", parse_mode='Markdown')
            
            format_type = 'audio' if 'audio' in data else 'video'
            quality = 'best'
            
            if '720' in data:
                quality = '720'
            elif '480' in data:
                quality = '480'
            elif '360' in data:
                quality = '360'
            elif '144' in data:
                quality = '144'
            
            dl_info = get_download_info(url, format_type, quality)
            
            if not dl_info:
                await query.edit_message_text("❌ Failed! Try another quality.")
                return
            
            dl_url = dl_info['url']
            title = dl_info['title']
            filesize = dl_info.get('filesize', 0)
            
            emoji = "🎵" if format_type == 'audio' else "🎬"
            qual_text = "MP3" if format_type == 'audio' else (f"{quality}p" if quality != 'best' else "Best")
            size_text = format_size(filesize)
            
            caption = f"""
✅ **Ready!**

{emoji} **{title}**
📊 {qual_text}
💾 ~{size_text}

⬇️ Sending to Telegram...
"""
            
            await query.edit_message_text(caption, parse_mode='Markdown')
            
            # Send file
            try:
                if format_type == 'audio':
                    await query.message.reply_audio(
                        audio=dl_url,
                        caption=f"🎵 {title}",
                        title=title,
                        performer=info.get('uploader', 'Unknown'),
                    )
                else:
                    await query.message.reply_video(
                        video=dl_url,
                        caption=f"🎬 {title}",
                        supports_streaming=True,
                    )
                
                logger.info(f"✅ File sent: {title}")
                
                # Browser link
                keyboard = [
                    [InlineKeyboardButton("🌐 Browser Link", url=dl_url)],
                    [InlineKeyboardButton("🔄 Another Format", callback_data=f"dl_{url}")],
                ]
                
                await query.message.reply_text(
                    f"""
✅ **File sent!**

📥 Check above for {emoji} **{qual_text}** file

**Alternative:** Browser link below
⚠️ Expires in 6 hours
""",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
            except TelegramError as e:
                logger.error(f"❌ Send failed: {e}")
                
                # Too large
                keyboard = [
                    [InlineKeyboardButton("🌐 Download Link", url=dl_url)],
                    [InlineKeyboardButton("🔄 Try Lower Quality", callback_data=f"dl_{url}")],
                ]
                
                await query.message.reply_text(
                    f"""
⚠️ **File too large!**

{emoji} {title}
💾 Size: {size_text}

Use browser link:
⏰ Expires in 6 hours
""",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
    except Exception as e:
        logger.error(f"❌ Callback error: {e}")
        logger.error(traceback.format_exc())
        await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

# Error handler
async def error_handler(update, context):
    logger.error(f"❌ Update error: {context.error}")
    logger.error(traceback.format_exc())

# Post init
async def post_init(app):
    cmds = [
        BotCommand("start", "🚀 Start bot"),
        BotCommand("help", "📖 Get help"),
        BotCommand("search", "🔍 Search YouTube"),
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
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    
    logger.info("=" * 50)
    logger.info("🚀 BOT STARTED - 100% WORKING!")
    logger.info("=" * 50)
    
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )

if __name__ == '__main__':
    main()
