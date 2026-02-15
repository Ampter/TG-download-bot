import asyncio
import logging
import os
import threading
from contextlib import suppress
from typing import BinaryIO, cast

from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
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
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MAX_UPLOAD_SIZE_MB = 2000
MAX_VIDEO_SIZE_MB = min(
    int(os.getenv("MAX_VIDEO_SIZE_MB", str(MAX_UPLOAD_SIZE_MB))),
    MAX_UPLOAD_SIZE_MB,
)
DOWNLOAD_TARGET_SIZE_MB = MAX_VIDEO_SIZE_MB

app = Flask(__name__)


class UploadProgressReader:
    def __init__(self, stream: BinaryIO, total_bytes: int):
        self._stream = stream
        self.total_bytes = total_bytes
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        if chunk:
            self.bytes_read += len(chunk)
        return chunk

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def _format_bytes(num_bytes: int) -> str:
    megabytes = num_bytes / (1024 * 1024)
    if megabytes < 1024:
        return f"{megabytes:.1f}MB"
    return f"{megabytes / 1024:.2f}GB"


def _upload_progress_text(sent_bytes: int, total_bytes: int) -> str:
    if total_bytes <= 0:
        return "⬆️ Uploading video..."

    percent = min(100, int((sent_bytes * 100) / total_bytes))
    bar_width = 20
    filled = int((bar_width * percent) / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    return (
        "⬆️ Uploading video...\n"
        f"[{bar}] {percent}%\n"
        f"{_format_bytes(sent_bytes)} / {_format_bytes(total_bytes)}"
    )


async def _track_upload_progress(status_msg, progress_reader: UploadProgressReader):
    last_step = -1
    while True:
        total_bytes = progress_reader.total_bytes
        sent_bytes = min(progress_reader.bytes_read, total_bytes)
        percent = 100 if total_bytes == 0 else int((sent_bytes * 100) / total_bytes)
        step = 100 if percent == 100 else (percent // 5) * 5

        if step != last_step:
            try:
                await status_msg.edit_text(
                    _upload_progress_text(sent_bytes=sent_bytes, total_bytes=total_bytes)
                )
            except BadRequest as exc:
                if "Message is not modified" not in str(exc):
                    logger.debug("Upload progress update skipped: %s", exc)
            except Exception as exc:
                logger.debug("Upload progress update failed: %s", exc)
            last_step = step

        if sent_bytes >= total_bytes:
            break
        await asyncio.sleep(1)


@app.route("/")
def health_check():
    return "Bot Active", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        logger.warning("Received /start without an effective message.")
        return

    await msg.reply_text(
        "🎬 Send a YouTube link and I'll return the video."
    )


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or msg.text is None:
        return

    url = msg.text.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        await msg.reply_text("❌ Please send a valid YouTube link.")
        return

    status_msg = await msg.reply_text("⏳ Downloading video...")
    chat = update.effective_chat
    if chat is not None:
        await context.bot.send_chat_action(
            chat_id=chat.id,
            action=ChatAction.UPLOAD_VIDEO,
        )

    file_path, error = download_video(url, max_size_mb=DOWNLOAD_TARGET_SIZE_MB)

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
        file_size_bytes = os.path.getsize(file_path)
        with open(file_path, "rb") as raw_video:
            progress_video = UploadProgressReader(raw_video, total_bytes=file_size_bytes)
            progress_task = asyncio.create_task(
                _track_upload_progress(status_msg, progress_video)
            )
            upload_completed = False
            try:
                await msg.reply_document(
                    document=cast(BinaryIO, progress_video),
                    filename=os.path.basename(file_path),
                    read_timeout=1200,
                    write_timeout=1200,
                    connect_timeout=120,
                    pool_timeout=120,
                )
                upload_completed = True
            finally:
                if upload_completed:
                    progress_video.bytes_read = file_size_bytes
                    await progress_task
                else:
                    progress_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await progress_task
        await status_msg.delete()
    except BadRequest as exc:
        if "Request Entity Too Large" in str(exc):
            await status_msg.edit_text(
                f"❌ Telegram rejected the file as too large. App limit is set to "
                f"{MAX_UPLOAD_SIZE_MB}MB."
            )
        else:
            logger.error("Telegram upload failed: %s", exc)
            await status_msg.edit_text("❌ Failed to upload video.")
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
