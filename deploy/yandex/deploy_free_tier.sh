#!/usr/bin/env bash
set -euo pipefail

YC_BIN="${YC_BIN:-$HOME/yandex-cloud/bin/yc}"
if ! command -v "$YC_BIN" >/dev/null 2>&1; then
  if command -v yc >/dev/null 2>&1; then
    YC_BIN="yc"
  else
    echo "Yandex CLI is not installed. Install it first: https://yandex.cloud/en/docs/cli/quickstart"
    exit 1
  fi
fi

if ! "$YC_BIN" iam create-token >/dev/null 2>&1; then
  cat <<'EOF'
Yandex CLI is not authenticated.
Run:
  yc init
and complete OAuth login before retrying this script.
EOF
  exit 1
fi

: "${BOT_TOKEN:?BOT_TOKEN is required}"

CONTAINER_NAME="${CONTAINER_NAME:-tg-download-bot}"
REGISTRY_NAME="${REGISTRY_NAME:-tg-download-bot}"
IMAGE_NAME="${IMAGE_NAME:-tg-download-bot}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
PORT="${PORT:-10000}"
MAX_VIDEO_SIZE_MB="${MAX_VIDEO_SIZE_MB:-2000}"
MAX_UPLOAD_SIZE_MB="${MAX_UPLOAD_SIZE_MB:-50}"
APP_ENV="${APP_ENV:-yandex-free}"
INSTANCE_NAME="${INSTANCE_NAME:-yc-serverless}"
WEBHOOK_PATH="${WEBHOOK_PATH:-telegram/webhook}"
WEBHOOK_SECRET_TOKEN="${WEBHOOK_SECRET_TOKEN:-}"

MEMORY="${MEMORY:-512MB}"
CORES="${CORES:-1}"
CORE_FRACTION="${CORE_FRACTION:-20}"
EXECUTION_TIMEOUT="${EXECUTION_TIMEOUT:-600s}"
CONCURRENCY="${CONCURRENCY:-1}"

get_json_value() {
  python - "$1" <<'PY'
import json
import sys

path = sys.argv[1]
raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit(0)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("")
    raise SystemExit(0)
node = data
for key in path.split("."):
    if isinstance(node, dict):
        node = node.get(key)
    else:
        node = None
    if node is None:
        break
if node is None:
    print("")
else:
    print(node)
PY
}

registry_json="$("$YC_BIN" container registry get --name "$REGISTRY_NAME" --format json 2>/dev/null || true)"
registry_id="$(printf '%s' "$registry_json" | get_json_value id)"
if [ -z "$registry_id" ]; then
  registry_json="$("$YC_BIN" container registry create --name "$REGISTRY_NAME" --format json)"
  registry_id="$(printf '%s' "$registry_json" | get_json_value id)"
fi

if [ -z "$registry_id" ]; then
  echo "Failed to resolve registry id."
  exit 1
fi

echo "Using registry: $registry_id"
"$YC_BIN" container registry configure-docker >/dev/null

image_uri="cr.yandex/${registry_id}/${IMAGE_NAME}:${IMAGE_TAG}"
echo "Building image: $image_uri"
docker build -t "$image_uri" .
docker push "$image_uri"

if ! "$YC_BIN" serverless container get --name "$CONTAINER_NAME" >/dev/null 2>&1; then
  "$YC_BIN" serverless container create --name "$CONTAINER_NAME" >/dev/null
fi

"$YC_BIN" serverless container allow-unauthenticated-invoke --name "$CONTAINER_NAME" >/dev/null

container_json="$("$YC_BIN" serverless container get --name "$CONTAINER_NAME" --format json)"
service_url="$(printf '%s' "$container_json" | get_json_value url)"
if [ -z "$service_url" ]; then
  service_url="$(printf '%s' "$container_json" | get_json_value http_invoke_url)"
fi
if [ -z "$service_url" ]; then
  service_url="$(printf '%s' "$container_json" | get_json_value status.url)"
fi
if [ -z "$service_url" ]; then
  echo "Could not resolve service URL from container metadata."
  exit 1
fi

env_map="BOT_TOKEN=${BOT_TOKEN},BOT_RUNTIME_MODE=webhook,WEBHOOK_BASE_URL=${service_url},WEBHOOK_PATH=${WEBHOOK_PATH},PORT=${PORT},MAX_VIDEO_SIZE_MB=${MAX_VIDEO_SIZE_MB},MAX_UPLOAD_SIZE_MB=${MAX_UPLOAD_SIZE_MB},APP_ENV=${APP_ENV},INSTANCE_NAME=${INSTANCE_NAME}"
if [ -n "$WEBHOOK_SECRET_TOKEN" ]; then
  env_map="${env_map},WEBHOOK_SECRET_TOKEN=${WEBHOOK_SECRET_TOKEN}"
fi

"$YC_BIN" serverless container revision deploy \
  --container-name "$CONTAINER_NAME" \
  --image "$image_uri" \
  --memory "$MEMORY" \
  --cores "$CORES" \
  --core-fraction "$CORE_FRACTION" \
  --execution-timeout "$EXECUTION_TIMEOUT" \
  --concurrency "$CONCURRENCY" \
  --runtime http \
  --environment "$env_map" \
  >/dev/null

webhook_url="${service_url%/}/${WEBHOOK_PATH#/}"
echo "Setting Telegram webhook: $webhook_url"

if [ -n "$WEBHOOK_SECRET_TOKEN" ]; then
  curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
    -d "url=${webhook_url}" \
    -d "secret_token=${WEBHOOK_SECRET_TOKEN}" >/dev/null
else
  curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
    -d "url=${webhook_url}" >/dev/null
fi

echo "Deployed successfully."
echo "Service URL: ${service_url}"
echo "Webhook URL: ${webhook_url}"
