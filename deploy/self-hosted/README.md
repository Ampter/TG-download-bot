# Self-hosted Bot API Example

This example runs:

- The Telegram download bot (`bot`)
- A self-hosted Telegram Bot API server (`telegram-bot-api`)

## Usage

1. Copy env file and fill values:

```bash
cd deploy/self-hosted
cp .env.example .env
```

2. Start both services:

```bash
docker compose up -d --build
```

3. Check bot health:

```bash
curl http://localhost:10000/
```

Expected response:

```text
Bot Active
```

## Notes

- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are from <https://my.telegram.org>.
- Bot uploads above the public API limit require a self-hosted Bot API server.
- This example uses the `aiogram/telegram-bot-api` image.
