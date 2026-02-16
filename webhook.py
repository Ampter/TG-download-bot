import logging
import os

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

logger = logging.getLogger(__name__)

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram/webhook").strip("/")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL") or os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")
PORT = int(os.getenv("PORT", "10000"))


def _build_webhook_url() -> str | None:
    if not WEBHOOK_BASE_URL:
        return None
    base = WEBHOOK_BASE_URL.rstrip("/")
    if not WEBHOOK_PATH:
        return base
    return f"{base}/{WEBHOOK_PATH}"


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

    bot = app_builder.build()
    bot.add_error_handler(_telegram_error_handler)
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_download))

    try:
        bot.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET_TOKEN or None,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
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
