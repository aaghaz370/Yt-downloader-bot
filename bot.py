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
import time

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Flask app for health check
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running! 🚀", 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# YouTube link validation
def is_youtube_url(url):
    patterns = [
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|shorts/|playlist\?list=|.+\?v=)?([^&=%\?]{11})',
        r'(https?://)?(www\.)?youtu\.be/([^&=%\?]{11})',
    ]
    for pattern in patterns:
        if re.match(pattern, url):
            return True
    return False

# Extract video ID from URL
def extract_video_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# Check if playlist
def is_playlist(url):
    return 'list=' in url

# Extract video info
def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'id': info.get('id', ''),
            }
    except Exception as e:
        logger.error(f"Error extracting info: {e}")
        return None

# Get download info with direct URL
def get_download_info(url, format_type='video', quality='best'):
    if format_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }
    else:
        if quality == 'best':
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 30,
            }
        else:
            ydl_opts = {
                'format': f'best[height<={quality}][ext=mp4]/best[height<={quality}]/best',
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 30,
            }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get the best format URL
            if 'url' in info:
                return {
                    'url': info['url'],
                    'title': info.get('title', 'video'),
                    'ext': info.get('ext', 'mp4'),
                    'filesize': info.get('filesize', 0),
                }
            elif 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                return {
                    'url': entry.get('url', ''),
                    'title': entry.get('title', 'video'),
                    'ext': entry.get('ext', 'mp4'),
                    'filesize': entry.get('filesize', 0),
                }
    except Exception as e:
        logger.error(f"Error getting download info: {e}")
    return None

# Get playlist info
def get_playlist_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                videos = []
                for entry in info['entries'][:10]:  # Limit to 10 videos
                    videos.append({
                        'title': entry.get('title', 'Unknown'),
                        'id': entry.get('id', ''),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    })
                return {
                    'playlist_title': info.get('title', 'Playlist'),
                    'videos': videos,
                    'total_count': len(info.get('entries', [])),
                }
    except Exception as e:
        logger.error(f"Error getting playlist info: {e}")
    return None

# Search YouTube
def search_youtube(query, max_results=5):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
        'socket_timeout': 30,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return results.get('entries', [])
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

# Format file size
def format_size(bytes):
    if not bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} TB"

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🎬 **Advanced YouTube Downloader Bot** 🚀

**✨ Key Features:**
✅ Direct Telegram Download (Video/Audio)
✅ Browser Download Links
✅ YouTube Shorts Support
✅ Playlist Download
✅ Forward Video/Link Support
✅ Multiple Quality Options
✅ Lightning Fast Speed ⚡

**📌 How to Use:**
1️⃣ Send YouTube link
2️⃣ Choose format & quality
3️⃣ Get file in Telegram OR browser link

**🎯 Commands:**
/start - Start bot
/help - Detailed help
/search <query> - Search YouTube

**Just send any YouTube link!** 🔗
"""
    
    keyboard = [
        [InlineKeyboardButton("📖 Help", callback_data='help'),
         InlineKeyboardButton("ℹ️ About", callback_data='about')],
        [InlineKeyboardButton("🔍 Search YouTube", switch_inline_query_current_chat='')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **Complete Guide:**

**1️⃣ Download Videos:**
   • Send YouTube link
   • Choose Video/Audio format
   • Select quality (144p-4K)
   • Get file in Telegram + Browser link

**2️⃣ Download Shorts:**
   • Send YouTube Shorts link
   • Works same as regular videos

**3️⃣ Download Playlist:**
   • Send playlist link
   • Choose video from list
   • Download individually

**4️⃣ Forward Messages:**
   • Forward any message with YT link
   • Bot will detect and process

**5️⃣ Search YouTube:**
   • Use /search <query>
   • Get top 5 results
   • Download directly

**📊 Quality Options:**
🎬 Video: Best, 720p, 480p, 360p, 144p
🎵 Audio: MP3 format

**⏰ Download Links:**
• Browser links expire in 6 hours
• Telegram files permanent

**💡 Pro Tips:**
✨ Bot works with all YT formats
✨ No file size limit for links
✨ Fast processing (under 10s)
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

# About command
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = """
ℹ️ **About This Bot**

🤖 **Advanced YT Downloader**
⚡ Ultra-fast processing
🆓 100% Free forever
🔒 Privacy focused
💾 No data stored
🌐 Hosted on Render.com

**Features:**
• Direct Telegram download
• Browser download links
• Shorts support
• Playlist support
• Forward detection
• Multi-quality options

**Version:** 3.0
**Engine:** yt-dlp (latest)
**Status:** Always online

**Developer:** @YourUsername
**Feedback:** Use /feedback command

Made with ❤️ for you!
"""
    await update.message.reply_text(about_text, parse_mode='Markdown')

# Search command
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ **Usage:** /search <query>\n\n**Example:**\n/search lofi music 2025", parse_mode='Markdown')
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Searching for: **{query}**...", parse_mode='Markdown')
    
    results = search_youtube(query, 5)
    
    if not results:
        await msg.edit_text("❌ No results found! Try different keywords.")
        return
    
    keyboard = []
    text = f"🔍 **Search Results:** {query}\n\n"
    
    for i, video in enumerate(results, 1):
        title = video.get('title', 'Unknown')[:60]
        video_id = video.get('id', '')
        duration = video.get('duration', 0)
        
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "🔴 Live"
        text += f"{i}. **{title}**\n   ⏱ {duration_str}\n\n"
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        keyboard.append([InlineKeyboardButton(f"📥 Download #{i}", callback_data=f"dl_{url}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Handle YouTube links
async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get URL from message or forwarded message
    text = update.message.text or update.message.caption or ""
    
    # Check if forwarded
    if update.message.forward_from or update.message.forward_from_chat:
        # Extract URL from forwarded message
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        if urls:
            url = urls[0]
        else:
            await update.message.reply_text("❌ No YouTube link found in forwarded message!")
            return
    else:
        url = text.strip()
    
    if not is_youtube_url(url):
        return  # Ignore non-YouTube links
    
    # Check if playlist
    if is_playlist(url):
        await handle_playlist(update, context, url)
        return
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode='Markdown')
    
    info = get_video_info(url)
    if not info:
        await msg.edit_text("❌ Failed to fetch video info. Please try again!")
        return
    
    # Store URL in user data
    context.user_data['current_url'] = url
    context.user_data['video_info'] = info
    
    # Duration format
    duration = info['duration']
    duration_str = f"{duration//60}:{duration%60:02d}" if duration else "N/A"
    
    # Views format
    views = info['view_count']
    views_str = f"{views:,}" if views else "N/A"
    
    # Detect shorts
    is_short = 'shorts' in url.lower()
    video_type = "📱 Shorts" if is_short else "📺 Video"
    
    caption = f"""
{video_type} **{info['title'][:100]}**

👤 **Uploader:** {info['uploader']}
⏱️ **Duration:** {duration_str}
👁️ **Views:** {views_str}

Choose format and quality:
"""
    
    keyboard = [
        [InlineKeyboardButton("🎬 Video - Best Quality", callback_data='fmt_video_best')],
        [InlineKeyboardButton("🎬 720p HD", callback_data='fmt_video_720'),
         InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
        [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360'),
         InlineKeyboardButton("🎬 144p", callback_data='fmt_video_144')],
        [InlineKeyboardButton("🎵 Audio Only (MP3)", callback_data='fmt_audio')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send with thumbnail if available
    if info['thumbnail']:
        try:
            await msg.delete()
            await update.message.reply_photo(
                photo=info['thumbnail'],
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except:
            await msg.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await msg.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')

# Handle playlist
async def handle_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE, url):
    msg = await update.message.reply_text("⏳ **Loading playlist...**", parse_mode='Markdown')
    
    playlist_info = get_playlist_info(url)
    if not playlist_info:
        await msg.edit_text("❌ Failed to load playlist!")
        return
    
    videos = playlist_info['videos']
    total = playlist_info['total_count']
    title = playlist_info['playlist_title']
    
    text = f"📑 **Playlist:** {title}\n📊 **Total Videos:** {total}\n\n**First 10 videos:**\n\n"
    
    keyboard = []
    for i, video in enumerate(videos, 1):
        text += f"{i}. {video['title'][:50]}\n"
        keyboard.append([InlineKeyboardButton(f"📥 Download #{i}", callback_data=f"dl_{video['url']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Callback query handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'help':
        await query.message.reply_text(
            "📖 Use /help command for detailed guide!",
            parse_mode='Markdown'
        )
        return
    
    if data == 'about':
        await about_command(update, context)
        return
    
    # Handle download from search/playlist
    if data.startswith('dl_'):
        url = data.replace('dl_', '')
        context.user_data['current_url'] = url
        
        await query.edit_message_text("⏳ **Loading video info...**", parse_mode='Markdown')
        
        info = get_video_info(url)
        if not info:
            await query.edit_message_text("❌ Failed to fetch video info!")
            return
        
        context.user_data['video_info'] = info
        
        keyboard = [
            [InlineKeyboardButton("🎬 Video - Best", callback_data='fmt_video_best')],
            [InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720'),
             InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480')],
            [InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360'),
             InlineKeyboardButton("🎬 144p", callback_data='fmt_video_144')],
            [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='fmt_audio')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📺 **{info['title'][:100]}**\n\nChoose format:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Handle format selection
    if data.startswith('fmt_'):
        url = context.user_data.get('current_url')
        info = context.user_data.get('video_info', {})
        
        if not url:
            await query.edit_message_text("❌ Session expired. Please send the link again!")
            return
        
        await query.edit_message_text("⏳ **Preparing your download...**\n\n_This may take 5-15 seconds_", parse_mode='Markdown')
        
        format_type = 'audio' if 'audio' in data else 'video'
        quality = 'best'
        
        if 'video_720' in data:
            quality = '720'
        elif 'video_480' in data:
            quality = '480'
        elif 'video_360' in data:
            quality = '360'
        elif 'video_144' in data:
            quality = '144'
        
        download_info = get_download_info(url, format_type, quality)
        
        if not download_info:
            await query.edit_message_text("❌ Failed to generate download link. Try another quality!")
            return
        
        download_url = download_info['url']
        title = download_info['title']
        file_ext = download_info['ext']
        filesize = download_info.get('filesize', 0)
        
        format_emoji = "🎵" if format_type == 'audio' else "🎬"
        quality_text = "MP3 Audio" if format_type == 'audio' else f"{quality}p Video" if quality != 'best' else "Best Quality"
        size_text = format_size(filesize) if filesize else "Unknown"
        
        # Send file to Telegram
        caption = f"""
✅ **Download Ready!**

{format_emoji} **{title[:80]}**
📊 **Format:** {quality_text}
💾 **Size:** ~{size_text}

⬇️ **Downloading to Telegram...**
"""
        
        await query.edit_message_text(caption, parse_mode='Markdown')
        
        try:
            # Send the file
            if format_type == 'audio':
                await query.message.reply_audio(
                    audio=download_url,
                    caption=f"🎵 {title}",
                    title=title,
                    performer=info.get('uploader', 'Unknown'),
                )
            else:
                await query.message.reply_video(
                    video=download_url,
                    caption=f"🎬 {title}",
                    supports_streaming=True,
                )
            
            # Add browser download button
            keyboard = [
                [InlineKeyboardButton("🌐 Open in Browser (Alternative)", url=download_url)],
                [InlineKeyboardButton("🔄 Download Another Format", callback_data=f"dl_{url}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            success_msg = f"""
✅ **File sent successfully!**

📥 Check above for your {format_emoji} **{quality_text}** file!

**Alternative:** Click below to download in browser
⚠️ **Note:** Browser link expires in 6 hours!
"""
            
            await query.message.reply_text(success_msg, reply_markup=reply_markup, parse_mode='Markdown')
            
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            # If file too large, send only link
            keyboard = [
                [InlineKeyboardButton("🌐 Download in Browser", url=download_url)],
                [InlineKeyboardButton("🔄 Try Lower Quality", callback_data=f"dl_{url}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            error_msg = f"""
⚠️ **File too large for Telegram!**

{format_emoji} **{title[:80]}**
📊 **Format:** {quality_text}
💾 **Size:** {size_text}

Use browser download link below:
⏰ **Link expires in 6 hours!**
"""
            
            await query.message.reply_text(error_msg, reply_markup=reply_markup, parse_mode='Markdown')

# Main function
def main():
    # Start Flask in separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Flask server started!")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Run bot
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
