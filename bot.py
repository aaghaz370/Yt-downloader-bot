import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from yt_dlp import YoutubeDL
from flask import Flask
from threading import Thread

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

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# YouTube link validation
def is_youtube_url(url):
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return re.match(youtube_regex, url) is not None

# Extract video info
def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
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
            }
    except Exception as e:
        logger.error(f"Error extracting info: {e}")
        return None

# Get direct download link
def get_download_link(url, format_type='video', quality='best'):
    if format_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
        }
    else:
        if quality == 'best':
            ydl_opts = {'format': 'best', 'quiet': True, 'no_warnings': True}
        else:
            ydl_opts = {'format': f'best[height<={quality}]', 'quiet': True, 'no_warnings': True}
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'url' in info:
                return info['url'], info.get('title', 'video')
            elif 'entries' in info:
                return info['entries'][0]['url'], info['entries'][0].get('title', 'video')
    except Exception as e:
        logger.error(f"Error getting download link: {e}")
    return None, None

# Search YouTube
def search_youtube(query, max_results=5):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return results.get('entries', [])
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🎬 **YouTube Downloader Bot** 🚀

📌 **Features:**
✅ Video/Audio Download
✅ Multiple Quality Options
✅ Direct Browser Download Links
✅ YouTube Search
✅ Fast Lightning Speed ⚡

**Commands:**
/start - Start bot
/help - Get help
/search <query> - Search YouTube

**Just send me a YouTube link!** 🔗
"""
    
    keyboard = [
        [InlineKeyboardButton("📺 How to Use", callback_data='help'),
         InlineKeyboardButton("ℹ️ About", callback_data='about')],
        [InlineKeyboardButton("🔍 Search YouTube", switch_inline_query_current_chat='')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **How to Use:**

1️⃣ **Download Video/Audio:**
   - Send any YouTube link
   - Choose quality
   - Get instant download link

2️⃣ **Search YouTube:**
   - Use /search <query>
   - Click on results
   - Download directly

3️⃣ **Direct Browser Link:**
   - Get links that work in Chrome/Browser
   - Links expire in 6 hours
   - Direct device download

**Tips:**
⚡ Bot processes in seconds
🎵 Audio = MP3 format
🎬 Video = MP4 format
🔗 No files stored on server

**Note:** Download links expire in 6 hours!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

# About command
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = """
ℹ️ **About This Bot**

🤖 **YouTube Downloader Bot**
⚡ Lightning fast downloads
🆓 100% Free to use
🔒 Privacy focused (no data stored)
🌐 Hosted on Render.com

**Developer:** @YourUsername
**Version:** 2.0
**Powered by:** yt-dlp

**Support:** For issues, contact developer
"""
    await update.message.reply_text(about_text, parse_mode='Markdown')

# Search command
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /search <query>\n\nExample: /search lofi music")
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
    
    results = search_youtube(query)
    
    if not results:
        await msg.edit_text("❌ No results found!")
        return
    
    keyboard = []
    for i, video in enumerate(results[:5], 1):
        title = video.get('title', 'Unknown')
        video_id = video.get('id', '')
        url = f"https://www.youtube.com/watch?v={video_id}"
        duration = video.get('duration', 0)
        
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"
        button_text = f"{i}. {title[:50]}... [{duration_str}]"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"dl_{url}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text(f"🔍 **Search Results for:** {query}\n\nChoose a video:", reply_markup=reply_markup, parse_mode='Markdown')

# Handle YouTube links
async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not is_youtube_url(url):
        await update.message.reply_text("❌ Please send a valid YouTube link!")
        return
    
    msg = await update.message.reply_text("⏳ Processing your request...")
    
    info = get_video_info(url)
    if not info:
        await msg.edit_text("❌ Failed to fetch video info. Try again!")
        return
    
    # Store URL in user data
    context.user_data['current_url'] = url
    context.user_data['video_info'] = info
    
    # Duration format
    duration = info['duration']
    duration_str = f"{duration//60}:{duration%60:02d}"
    
    # Views format
    views = info['view_count']
    views_str = f"{views:,}" if views else "N/A"
    
    caption = f"""
📺 **{info['title']}**

👤 Uploader: {info['uploader']}
⏱️ Duration: {duration_str}
👁️ Views: {views_str}

Choose format and quality:
"""
    
    keyboard = [
        [InlineKeyboardButton("🎬 Video - Best Quality", callback_data='fmt_video_best'),
         InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720')],
        [InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480'),
         InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360')],
        [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='fmt_audio')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')

# Callback query handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'help':
        await help_command(update, context)
        return
    
    if data == 'about':
        await about_command(update, context)
        return
    
    # Handle download from search
    if data.startswith('dl_'):
        url = data.replace('dl_', '')
        context.user_data['current_url'] = url
        
        info = get_video_info(url)
        if not info:
            await query.edit_message_text("❌ Failed to fetch video info!")
            return
        
        context.user_data['video_info'] = info
        
        keyboard = [
            [InlineKeyboardButton("🎬 Video - Best", callback_data='fmt_video_best'),
             InlineKeyboardButton("🎬 720p", callback_data='fmt_video_720')],
            [InlineKeyboardButton("🎬 480p", callback_data='fmt_video_480'),
             InlineKeyboardButton("🎬 360p", callback_data='fmt_video_360')],
            [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='fmt_audio')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"📺 **{info['title']}**\n\nChoose format:", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Handle format selection
    if data.startswith('fmt_'):
        url = context.user_data.get('current_url')
        if not url:
            await query.edit_message_text("❌ Session expired. Please send the link again!")
            return
        
        await query.edit_message_text("⏳ Generating download link... Please wait...")
        
        format_type = 'audio' if 'audio' in data else 'video'
        quality = 'best'
        
        if 'video_720' in data:
            quality = '720'
        elif 'video_480' in data:
            quality = '480'
        elif 'video_360' in data:
            quality = '360'
        
        download_url, title = get_download_link(url, format_type, quality)
        
        if not download_url:
            await query.edit_message_text("❌ Failed to generate download link. Try again!")
            return
        
        format_emoji = "🎵" if format_type == 'audio' else "🎬"
        quality_text = "MP3" if format_type == 'audio' else f"{quality}p" if quality != 'best' else "Best Quality"
        
        message = f"""
✅ **Link Generated!**

{format_emoji} **Title:** {title}
📊 **Format:** {quality_text}

🔗 **Download Link:**
Click below to download directly in your browser!

⚠️ **Note:** This link will expire in 6 hours!
Download it soon! ⏰
"""
        
        keyboard = [
            [InlineKeyboardButton("⬇️ Download Now", url=download_url)],
            [InlineKeyboardButton("🔄 Choose Another Format", callback_data=f"dl_{url}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# Main function
def main():
    # Start Flask in a separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help"),
        BotCommand("search", "Search YouTube videos"),
    ]
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_link))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Run bot
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
