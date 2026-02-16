# Yandex Cloud free-tier deployment

This setup deploys the bot to **Yandex Serverless Containers** in webhook mode so it can run within the free-tier model (request-based, scales to zero).

## Why webhook mode

Polling keeps a process alive continuously and is not free-tier friendly in serverless.
Webhook mode only runs when Telegram sends updates.

## Prerequisites

- Docker installed locally.
- Yandex Cloud CLI installed and authenticated (`yc init`).
- Telegram bot token (`BOT_TOKEN`).

## Deploy

From project root:

```bash
export BOT_TOKEN='123456:abc...'
export WEBHOOK_SECRET_TOKEN='optional-secret'
./deploy/yandex/deploy_free_tier.sh
```

The script will:

1. Create or reuse a Container Registry.
2. Build and push Docker image.
3. Create/update a Serverless Container revision.
4. Set the Telegram webhook to the deployed service URL.

## Runtime env vars used by the script

- `BOT_TOKEN` (required)
- `WEBHOOK_SECRET_TOKEN` (optional, recommended)
- `CONTAINER_NAME` (default: `tg-download-bot`)
- `REGISTRY_NAME` (default: `tg-download-bot`)
- `IMAGE_NAME` (default: `tg-download-bot`)
- `IMAGE_TAG` (default: current git short SHA)
- `PORT` (default: `10000`)
- `MAX_VIDEO_SIZE_MB` (default: `2000`)
- `MAX_UPLOAD_SIZE_MB` (default: `50`)
- `APP_ENV` (default: `yandex-free`)
- `INSTANCE_NAME` (default: `yc-serverless`)
- `WEBHOOK_PATH` (default: `telegram/webhook`)
- `MEMORY` (default: `512MB`)
- `CORES` (default: `1`)
- `CORE_FRACTION` (default: `20`)
- `EXECUTION_TIMEOUT` (default: `600s`)
- `CONCURRENCY` (default: `1`)

## Post-deploy checks

1. `curl <service-url>/` returns `Bot Active`.
2. `curl https://api.telegram.org/bot<token>/getWebhookInfo` returns your Yandex webhook URL.
3. Send `/start` to the bot in Telegram and verify response.
4. Send a test YouTube link and verify download+upload.
