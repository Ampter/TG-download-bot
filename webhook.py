import asyncio
import logging
import os

from flask import Flask, request
from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from main import (
    APP_ENV,
    BOT_API_BASE_URL,
    BOT_API_FILE_URL,
    HOSTNAME,
    INSTANCE_NAME,
    PROCESS_ID,
    TOKEN,
    _telegram_error_handler,
    _token_fingerprint,
    handle_download,
    start,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram/webhook").strip("/")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL") or os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)


def _build_webhook_url() -> str | None:
    if not WEBHOOK_BASE_URL:
        return None
    base = WEBHOOK_BASE_URL.rstrip("/")
    if not WEBHOOK_PATH:
        return base
    return f"{base}/{WEBHOOK_PATH}"


@app.route("/")
def health_check():
    return "<html><body><h1>Bot Status</h1><p>Everything is operational</p></body></html>", 200


def main() -> None:
    if not TOKEN:
        logger.error("BOT_TOKEN is not set. Bot cannot start.")
        return

    webhook_url = _build_webhook_url()
    if not webhook_url:
        logger.error(
            "WEBHOOK_BASE_URL (or WEBHOOK_URL) is required in webhook mode. "
            "Example: https://<service-id>.containers.yandexcloud.net"
        )
        return

    logger.info(
        "Starting webhook bot env=%s instance=%s host=%s pid=%s token=%s webhook=%s",
        APP_ENV,
        INSTANCE_NAME,
        HOSTNAME,
        PROCESS_ID,
        _token_fingerprint(TOKEN),
        webhook_url,
    )

    app_builder = ApplicationBuilder().token(TOKEN)
    if BOT_API_BASE_URL:
        app_builder = app_builder.base_url(BOT_API_BASE_URL)
    if BOT_API_FILE_URL:
        app_builder = app_builder.base_file_url(BOT_API_FILE_URL)

    application = app_builder.build()
    application.add_error_handler(_telegram_error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_download)
    )

    # Shared event loop for thread-safe updates
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Register the webhook endpoint with Flask
    @app.route(f"/{WEBHOOK_PATH}", methods=["POST"])
    def webhook_handler():
        if WEBHOOK_SECRET_TOKEN:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if token != WEBHOOK_SECRET_TOKEN:
                return "Unauthorized", 403

        update = Update.de_json(data=request.get_json(force=True), bot=application.bot)
        loop.call_soon_threadsafe(application.update_queue.put_nowait, update)
        return "", 200

    async def run_app():
        async with application:
            await application.bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET_TOKEN or None,
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
            )
            await application.start()
            while True:
                await asyncio.sleep(3600)

    # Start Flask in a separate thread for health check and webhook reception
    from threading import Thread
    from werkzeug.serving import make_server

    class ServerThread(Thread):
        def __init__(self, app):
            Thread.__init__(self, daemon=True)
            self.server = make_server("0.0.0.0", PORT, app)

        def run(self):
            logger.info("Starting Flask server on port %s", PORT)
            self.server.serve_forever()

    ServerThread(app).start()

    try:
        loop.run_until_complete(run_app())
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
    except Exception as exc:
        logger.exception("Fatal error in webhook bot: %s", exc)


if __name__ == "__main__":
    main()
