# TG-download-bot

Telegram bot that downloads YouTube videos and sends them back in chat.

[![Python package](https://github.com/Ampter/TG-download-bot/actions/workflows/python-package.yml/badge.svg)](https://github.com/Ampter/TG-download-bot/actions/workflows/python-package.yml)

## Features

- Accepts `youtube.com` and `youtu.be` links.
- Downloads video with `yt-dlp` (prefers MP4).
- Uploads video to Telegram as a document (better for larger files).
- Includes title and author in upload status/caption.
- Shows an in-chat progress bar while uploading.
- Automatically compresses oversized videos to fit upload limits when possible.
- Configurable download/upload limits (public API uploads are capped at ~50MB).
- Includes a lightweight Flask healthcheck endpoint for hosting platforms.

---

## Prerequisites

For local (non-Docker) setup:

- Python 3.10+ (3.12 recommended)
- `ffmpeg` installed and available in `PATH`
- Node.js + npm (for the `bgutil` provider)

---

## Environment variables

Create a `.env` file in the project root:

```env
BOT_TOKEN=your_telegram_bot_token
MAX_VIDEO_SIZE_MB=2000
MAX_UPLOAD_SIZE_MB=50
# Optional: set these only for a self-hosted Telegram Bot API server.
TELEGRAM_BOT_API_BASE_URL=
TELEGRAM_BOT_API_FILE_URL=
APP_ENV=local
INSTANCE_NAME=local-dev
PORT=10000
```

### Variable notes

- `BOT_TOKEN` (**required**): Telegram bot token from BotFather.
- `MAX_VIDEO_SIZE_MB`: max target size when selecting stream formats to download (clamped to upload limit).
- `MAX_UPLOAD_SIZE_MB`: desired upload cap. With public Telegram API, effective limit is 50MB.
- `TELEGRAM_BOT_API_BASE_URL` (optional): self-hosted Bot API base URL, e.g. `http://localhost:8081/bot`.
- `TELEGRAM_BOT_API_FILE_URL` (optional): self-hosted Bot API file URL, e.g. `http://localhost:8081/file/bot`.
- `APP_ENV` (optional): environment label shown in startup/conflict logs (for example `local`, `staging`, `prod`).
- `INSTANCE_NAME` (optional): stable instance label shown in startup/conflict logs.
- `PORT`: Flask healthcheck server port (`/` returns `Bot Active`).

---

## Local development setup

### 1) Clone and install Python dependencies

```bash
git clone https://github.com/Ampter/TG-download-bot.git
cd TG-download-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run the bgutil provider (required by current yt-dlp extractor args)

```bash
git clone --single-branch --branch 1.2.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /tmp/bgutil-provider
cd /tmp/bgutil-provider/server
npm install
npx tsc
node build/main.js --port 4416
```

Keep this process running in one terminal.

### 3) Start the bot (new terminal)

```bash
cd /path/to/TG-download-bot
source .venv/bin/activate
python main.py
```

---

## Docker setup (recommended)

This repo includes a Dockerfile that installs Python deps, ffmpeg, Node.js, and the provider, then starts both provider + bot via `start.sh`.

### Build image

```bash
docker build -t tg-download-bot .
```

### Run container

```bash
docker run --rm \
  -e BOT_TOKEN=your_telegram_bot_token \
  -e MAX_VIDEO_SIZE_MB=2000 \
  -e MAX_UPLOAD_SIZE_MB=50 \
  -e APP_ENV=prod \
  -e INSTANCE_NAME=prod-1 \
  -e PORT=10000 \
  -p 10000:10000 \
  tg-download-bot
```

Healthcheck:

```bash
curl http://localhost:10000/
```

Expected response:

```text
Bot Active
```

---

## Deploying on Render

1. Push this repo to GitHub.
2. In Render, create a **Web Service** from the repo.
3. Use:
   - **Environment**: Docker
   - **Build Command**: *(leave empty, Dockerfile handles it)*
   - **Start Command**: *(leave empty, Dockerfile CMD uses `/start.sh`)*
4. Set environment variables in Render dashboard:
   - `BOT_TOKEN`
   - `MAX_VIDEO_SIZE_MB` (optional)
   - `MAX_UPLOAD_SIZE_MB` (optional)
   - `TELEGRAM_BOT_API_BASE_URL` (optional)
   - `TELEGRAM_BOT_API_FILE_URL` (optional)
   - `APP_ENV` (optional)
   - `INSTANCE_NAME` (optional)
   - `PORT` (Render usually injects this automatically)
5. Deploy.
6. Open the service URL and confirm `/` returns `Bot Active`.

> **Tip:** If you want better resilience for temporary downloads on some platforms, attach a persistent disk and keep the app `downloads/` directory on that volume.

---

## Running tests

```bash
pytest -q
```

---

## Troubleshooting

- **"Please send a valid YouTube link"**: Ensure the message contains `youtube.com` or `youtu.be`.
- **Download fails**: Provider may not be running on `http://127.0.0.1:4416`.
- **Upload fails for very large files**:
  - Public `api.telegram.org` endpoint limits bots to about `50MB`.
  - The bot attempts to compress oversized videos automatically before upload.
  - For larger uploads (up to `2000MB`), use a self-hosted Bot API server and set:
    - `TELEGRAM_BOT_API_BASE_URL`
    - `TELEGRAM_BOT_API_FILE_URL`
- **No response from bot**: Verify `BOT_TOKEN` and check logs.

---

## License

MIT (see [LICENSE](LICENSE)).
