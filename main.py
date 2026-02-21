from downloader import download_video
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest, Conflict
from telegram.constants import ChatAction
import asyncio
import logging
import os
import socket
import threading
import time
from asyncio.subprocess import DEVNULL
from contextlib import suppress
from typing import BinaryIO, cast
from urllib.parse import urlparse
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
376


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
APP_ENV = os.getenv("APP_ENV", "local")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", socket.gethostname())
HOSTNAME = socket.gethostname()
PROCESS_ID = os.getpid()
BOT_API_BASE_URL = os.getenv("TELEGRAM_BOT_API_BASE_URL")
BOT_API_FILE_URL = os.getenv("TELEGRAM_BOT_API_FILE_URL")
BOT_API_HOSTPORT = os.getenv("TELEGRAM_BOT_API_HOSTPORT")

if not BOT_API_BASE_URL and BOT_API_HOSTPORT:
    BOT_API_BASE_URL = f"http://{BOT_API_HOSTPORT}/bot"
if not BOT_API_FILE_URL and BOT_API_HOSTPORT:
    BOT_API_FILE_URL = f"http://{BOT_API_HOSTPORT}/file/bot"
DEFAULT_PUBLIC_API_UPLOAD_LIMIT_MB = 50
DEFAULT_LOCAL_API_UPLOAD_LIMIT_MB = 2000


def _is_public_telegram_api(base_url: str | None) -> bool:
    if not base_url:
        return True
    parsed = urlparse(base_url)
    return parsed.hostname == "api.telegram.org"


ENDPOINT_UPLOAD_LIMIT_MB = (
    DEFAULT_PUBLIC_API_UPLOAD_LIMIT_MB
    if _is_public_telegram_api(BOT_API_BASE_URL)
    else DEFAULT_LOCAL_API_UPLOAD_LIMIT_MB
)
CONFIGURED_MAX_UPLOAD_SIZE_MB = int(
    os.getenv("MAX_UPLOAD_SIZE_MB", str(ENDPOINT_UPLOAD_LIMIT_MB))
)
MAX_UPLOAD_SIZE_MB = min(CONFIGURED_MAX_UPLOAD_SIZE_MB,
                         ENDPOINT_UPLOAD_LIMIT_MB)
MAX_VIDEO_SIZE_MB = min(
    int(os.getenv("MAX_VIDEO_SIZE_MB", str(MAX_UPLOAD_SIZE_MB))),
    MAX_UPLOAD_SIZE_MB,
)
DOWNLOAD_TARGET_SIZE_MB = MAX_VIDEO_SIZE_MB
_last_conflict_log_time = 0.0

if CONFIGURED_MAX_UPLOAD_SIZE_MB > ENDPOINT_UPLOAD_LIMIT_MB:
    logger.warning(
        "MAX_UPLOAD_SIZE_MB=%s exceeds endpoint limit=%sMB; using %sMB. "
        "Set TELEGRAM_BOT_API_BASE_URL/TELEGRAM_BOT_API_FILE_URL to a self-hosted "
        "Bot API server for larger uploads.",
        CONFIGURED_MAX_UPLOAD_SIZE_MB,
        ENDPOINT_UPLOAD_LIMIT_MB,
        MAX_UPLOAD_SIZE_MB,
    )

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


def _truncate_text(value: str | None, max_len: int, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[:max_len - 3]}..."


def _upload_progress_text(
    sent_bytes: int,
    total_bytes: int,
    video_title: str,
    video_author: str,
) -> str:
    if total_bytes <= 0:
        return (
            "⬆️ Uploading video...\n"
            f"🎬 {video_title}\n"
            f"👤 {video_author}"
        )

    percent = min(100, int((sent_bytes * 100) / total_bytes))
    bar_width = 20
    filled = int((bar_width * percent) / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    return (
        "⬆️ Uploading video...\n"
        f"🎬 {video_title}\n"
        f"👤 {video_author}\n"
        f"[{bar}] {percent}%\n"
        f"{_format_bytes(sent_bytes)} / {_format_bytes(total_bytes)}"
    )


def _token_fingerprint(token: str | None) -> str:
    if not token:
        return "missing"
    return f"...{token[-6:]}"


def _friendly_download_error(error: str | None) -> str:
    if not error:
        return "❌ Failed to download video. Please try again later."

    lowered = error.lower()
    # Check for various anti-bot or restricted content messages
    is_antibot = (
        ("sign in to confirm" in lowered and "not a bot" in lowered)
        or "confirm you’re not a bot" in lowered
        or "the following content is not available on this app" in lowered
    )

    if is_antibot:
        return (
            "❌ YouTube blocked this download with anti-bot verification.\n\n"
            "To fix this:\n"
            "1. Configure yt-dlp cookies (YTDLP_COOKIES_FILE / YTDLP_COOKIES_B64).\n"
            "2. Ensure the PO token provider is running.\n"
            "3. Try another video or try again later."
        )
    if "video unavailable" in lowered:
        return "❌ This video is unavailable. Try a different link."

    # Return a slightly more detailed error if possible, but keep it clean
    return f"❌ Download failed: {error[:200]}"


async def _telegram_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    global _last_conflict_log_time

    error = context.error
    if isinstance(error, Conflict):
        now = time.time()
        if now - _last_conflict_log_time >= 60:
            logger.error(
                "Telegram getUpdates conflict. Another bot instance is using this "
                "BOT_TOKEN. Keep only one active instance per token. "
                "env=%s instance=%s host=%s pid=%s token=%s",
                APP_ENV,
                INSTANCE_NAME,
                HOSTNAME,
                PROCESS_ID,
                _token_fingerprint(TOKEN),
            )
            _last_conflict_log_time = now
        return

    logger.exception("Unhandled Telegram error: %s", error, exc_info=error)


async def _probe_duration_seconds(file_path: str) -> float | None:
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return None
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return None
    try:
        duration = float(stdout.decode().strip())
    except ValueError:
        return None
    if duration <= 0:
        return None
    return duration


async def _compress_video_to_limit(
    file_path: str,
    max_size_mb: int,
) -> tuple[str | None, str | None]:
    duration_seconds = await _probe_duration_seconds(file_path)
    if duration_seconds is None:
        return None, "Could not determine video duration for compression"

    target_size_bytes = int(max_size_mb * 1024 * 1024 * 0.95)
    if target_size_bytes <= 0:
        return None, "Invalid upload size limit"

    audio_bitrate_kbps = 96
    total_bitrate_kbps = int((target_size_bytes * 8) /
                             (duration_seconds * 1000))
    video_bitrate_kbps = max(200, total_bitrate_kbps - audio_bitrate_kbps)
    max_rate_kbps = int(video_bitrate_kbps * 1.1)
    buffer_size_kbps = max(video_bitrate_kbps * 2, 400)

    base_name, _ = os.path.splitext(file_path)
    compressed_path = f"{base_name}.compressed.mp4"

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            f"{video_bitrate_kbps}k",
            "-maxrate",
            f"{max_rate_kbps}k",
            "-bufsize",
            f"{buffer_size_kbps}k",
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate_kbps}k",
            "-movflags",
            "+faststart",
            compressed_path,
            stdout=DEVNULL,
            stderr=DEVNULL,
        )
    except FileNotFoundError:
        return None, "ffmpeg is not installed"
    await process.wait()

    if process.returncode != 0 or not os.path.exists(compressed_path):
        with suppress(FileNotFoundError):
            os.remove(compressed_path)
        return None, "ffmpeg compression failed"

    max_size_bytes = max_size_mb * 1024 * 1024
    if os.path.getsize(compressed_path) > max_size_bytes:
        with suppress(FileNotFoundError):
            os.remove(compressed_path)
        return None, "Compressed file is still above upload limit"

    return compressed_path, None


async def _track_upload_progress(
    status_msg,
    progress_reader: UploadProgressReader,
    video_title: str,
    video_author: str,
):
    last_step = -1
    while True:
        total_bytes = progress_reader.total_bytes
        sent_bytes = min(progress_reader.bytes_read, total_bytes)
        percent = 100 if total_bytes == 0 else int(
            (sent_bytes * 100) / total_bytes)
        step = 100 if percent == 100 else (percent // 5) * 5

        if step != last_step:
            try:
                await status_msg.edit_text(
                    _upload_progress_text(
                        sent_bytes=sent_bytes,
                        total_bytes=total_bytes,
                        video_title=video_title,
                        video_author=video_author,
                    )
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
    return "<html><body><h1>Bot Status</h1><p>Everything is operational</p></body></html>", 200


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
    user = update.effective_user
    username = user.username if user else "unknown"
    user_id = user.id if user else "unknown"
    logger.info("Download request: user=%s (%s) url=%s",
                username, user_id, url)
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

    file_path, error, video_title, video_author = await asyncio.to_thread(download_video,
                                                                          url, max_size_mb=DOWNLOAD_TARGET_SIZE_MB
                                                                          )

    if not file_path or not os.path.exists(file_path):
        logger.error("Download failed (%s): %s", url, error)
        await status_msg.edit_text(_friendly_download_error(error))
        return

    display_title = _truncate_text(
        video_title or os.path.splitext(os.path.basename(file_path))[0],
        max_len=90,
        fallback="Unknown title",
    )
    display_author = _truncate_text(
        video_author,
        max_len=70,
        fallback="Unknown author",
    )

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_SIZE_MB:
        await status_msg.edit_text(
            f"⚙️ Video is {file_size_mb:.1f}MB, above the upload limit "
            f"({MAX_UPLOAD_SIZE_MB}MB).\nCompressing to fit..."
        )
        logger.info("Compressing video: %s (size=%.1fMB, target=%dMB)",
                    file_path, file_size_mb, MAX_UPLOAD_SIZE_MB)
        compressed_file_path, compress_error = await _compress_video_to_limit(
            file_path=file_path, max_size_mb=MAX_UPLOAD_SIZE_MB
        )
        if compressed_file_path is None:
            os.remove(file_path)
            await status_msg.edit_text(
                "❌ Video is too large and could not be compressed to fit the upload "
                "limit."
            )
            logger.error("Compression failed: %s", compress_error)
            return
        os.remove(file_path)
        file_path = compressed_file_path

    try:
        file_size_bytes = os.path.getsize(file_path)
        with open(file_path, "rb") as raw_video:
            progress_video = UploadProgressReader(
                raw_video, total_bytes=file_size_bytes)
            progress_task = asyncio.create_task(
                _track_upload_progress(
                    status_msg, progress_video, display_title, display_author
                )
            )
            upload_completed = False
            try:
                logger.info("Starting Telegram upload: %s (size=%.1fMB)",
                            display_title, os.path.getsize(file_path) / (1024 * 1024))
                await msg.reply_document(
                    document=cast(BinaryIO, progress_video),
                    filename=os.path.basename(file_path),
                    caption=f"🎬 {display_title}\n👤 {display_author}",
                    read_timeout=1200,
                    write_timeout=1200,
                    connect_timeout=120,
                    pool_timeout=120,
                )
                upload_completed = True
                logger.info("Telegram upload completed: %s", display_title)
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
        logger.error("BOT_TOKEN is not set. Bot cannot start.")
        return

    logger.info(
        "Starting bot instance env=%s instance=%s host=%s pid=%s token=%s upload_limit_mb=%s",
        APP_ENV,
        INSTANCE_NAME,
        HOSTNAME,
        PROCESS_ID,
        _token_fingerprint(TOKEN),
        MAX_UPLOAD_SIZE_MB,
    )

    threading.Thread(target=run_flask, daemon=True).start()
    app_builder = ApplicationBuilder().token(TOKEN)
    if BOT_API_BASE_URL:
        app_builder = app_builder.base_url(BOT_API_BASE_URL)
    if BOT_API_FILE_URL:
        app_builder = app_builder.base_file_url(BOT_API_FILE_URL)

    bot = app_builder.build()
    bot.add_error_handler(_telegram_error_handler)
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), handle_download))
    try:
        bot.run_polling()
    except Conflict:
        logger.error(
            "Another bot instance is already running with this BOT_TOKEN. "
            "Stop the other instance or use a separate token per environment. "
            "env=%s instance=%s host=%s pid=%s token=%s",
            APP_ENV,
            INSTANCE_NAME,
            HOSTNAME,
            PROCESS_ID,
            _token_fingerprint(TOKEN),
        )


if __name__ == "__main__":
    main()
