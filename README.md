# TG-download-bot

Telegram bot that downloads YouTube videos and sends them back in chat.

[![Python package](https://github.com/Ampter/TG-download-bot/actions/workflows/python-package.yml/badge.svg)](https://github.com/Ampter/TG-download-bot/actions/workflows/python-package.yml)

## Features

- Accepts `youtube.com` and `youtu.be` links.
- Downloads video with `yt-dlp` (prefers MP4).
- Uploads video to Telegram as a document (better for larger files).
- Shows an in-chat progress bar while uploading.
- Configurable download size limit (upload cap fixed at 2000MB).
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
PORT=10000
```

### Variable notes

- `BOT_TOKEN` (**required**): Telegram bot token from BotFather.
- `MAX_VIDEO_SIZE_MB`: max target size when selecting stream formats to download (capped at 2000MB).
- Upload cap is fixed in code to 2000MB.
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
  - Bot upload cap is fixed to `2000MB`.
  - If Telegram still rejects uploads, your endpoint may enforce a lower upstream limit.
- **No response from bot**: Verify `BOT_TOKEN` and check logs.

---

## License

MIT (see [LICENSE](LICENSE)).
