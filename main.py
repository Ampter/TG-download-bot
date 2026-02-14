import logging
import os
import threading

from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import download_video

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "2000"))

app = Flask(__name__)


@app.route("/")
def health_check():
    return "Bot Active", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🎬 Send a YouTube link and I'll return the video."
    )


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return

    url = msg.text.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        await msg.reply_text("❌ Please send a valid YouTube link.")
        return

    status_msg = await msg.reply_text("⏳ Downloading video...")
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_VIDEO,
    )

    file_path, error = download_video(url)

    if not file_path or not os.path.exists(file_path):
        logger.error("Download failed (%s): %s", url, error)
        await status_msg.edit_text(
            "❌ Failed to download video. Please try again later."
        )
        return

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_SIZE_MB:
        os.remove(file_path)
        await status_msg.edit_text(
            f"❌ Video is {file_size_mb:.1f}MB, above the configured upload limit "
            f"({MAX_UPLOAD_SIZE_MB}MB)."
        )
        return

    try:
        with open(file_path, "rb") as video:
            await msg.reply_document(
                document=video,
                filename=os.path.basename(file_path),
                read_timeout=1200,
                write_timeout=1200,
                connect_timeout=120,
                pool_timeout=120,
            )
        await status_msg.delete()
    except Exception as exc:
        logger.error("Telegram upload failed: %s", exc)
        await status_msg.edit_text("❌ Failed to upload video.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def main():
    if not TOKEN:
        return

    threading.Thread(target=run_flask, daemon=True).start()
    bot = ApplicationBuilder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_download))
    bot.run_polling()


if __name__ == "__main__":
    main()
