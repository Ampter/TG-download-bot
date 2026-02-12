import os
import logging
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from downloader import download_video

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID') # Add your ID to Render Env Vars

app = Flask(__name__)
@app.route('/')
def health_check(): return "Bot Active", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- NEW: ADMIN NOTIFICATION FUNCTION ---
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, error_msg: str):
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ **Admin Alert**\n\nError: `{error_msg}`")
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🎵 Send me a YouTube link!")

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    url = msg.text
    
    if "youtube.com" in url or "youtu.be" in url:
        status_msg = await msg.reply_text("⏳ Processing...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VOICE)

        file_path, error = download_video(url)

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as audio:
                    await msg.reply_audio(audio=audio, title=os.path.basename(file_path))
                os.remove(file_path)
                await status_msg.delete()
            except Exception as e:
                # Notify Admin of Upload Failures
                await notify_admin(context, f"Telegram Upload Fail: {e}")
                await msg.reply_text(f"❌ Upload error: {e}")
        else:
            # Notify Admin of YouTube Blocks/Download Failures
            await notify_admin(context, f"Download Fail ({url}): {error}")
            await status_msg.edit_text(f"❌ Error: {error}")
    else:
        await msg.reply_text("❌ Invalid link.")

def main():
    if not TOKEN: return
    threading.Thread(target=run_flask, daemon=True).start()
    bot = ApplicationBuilder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_download))
    bot.run_polling()

if __name__ == "__main__":
    main()
