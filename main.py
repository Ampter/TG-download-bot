import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# Import the function from your downloader.py
from downloader import download_video

# 1. Load Environment Variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# 2. Greeting Logic (/start)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and update.effective_message:
        await update.effective_message.reply_text(
            f"Hello {user.first_name}! 👋\nSend me a YouTube link and I'll download it for you."
        )

# 3. Download and Sending Logic
async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text
    
    # Simple check for YouTube links
    if "youtube.com" in url or "youtu.be" in url:
        status_msg = await update.message.reply_text("⏳ Processing your link...")
        
        # Show "Uploading video" status in the top bar
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action=ChatAction.UPLOAD_VIDEO
        )

        # Run downloader (runs in a separate thread if needed, but simple for now)
        file_path = download_video(url)

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption="Here is your video! 📥"
                    )
                os.remove(file_path)  # Cleanup Fedora storage
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ Error sending file: {str(e)}")
        else:
            await status_msg.edit_text("❌ Download failed. The video might be too large (>50MB).")
    else:
        await update.message.reply_text("Please send a valid YouTube link!")

def main():
    if not TOKEN:
        print("Error: BOT_TOKEN not found in .env file!")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_download))

    print("Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
