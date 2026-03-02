import threading
import base64
import json
import logging
import os
import tempfile
import urllib.request
from typing import Any, Optional, Tuple, cast

import yt_dlp

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "2000"))
_COOKIEFILE_CACHE: Optional[str] = None
_COOKIE_LOCK = threading.Lock()
DEFAULT_BGUTIL_BASE_URL = os.getenv(
    "YTDLP_BGUTIL_BASE_URL", "http://127.0.0.1:4416"
)


class YdlLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            logger.debug(msg)
        else:
            logger.info(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def _video_format(max_size_mb: int) -> str:
    max_bytes = max_size_mb * 1024 * 1024
    # Prefer mp4 for Telegram compatibility while allowing large files.
    return (
        f"bestvideo[ext=mp4][filesize<={max_bytes}]"
        f"+bestaudio[filesize<={max_bytes}]"
        f"/best[ext=mp4][filesize<={max_bytes}]"
        f"/best[filesize<={max_bytes}]"
        "/best"
    )


def _get_cookiefile_from_env() -> Optional[str]:
    global _COOKIEFILE_CACHE

    cookie_path = os.getenv("YTDLP_COOKIES_FILE")
    if cookie_path:
        if os.path.exists(cookie_path):
            logger.info("Using cookies from file: %s", cookie_path)
            return cookie_path
        logger.warning(
            "YTDLP_COOKIES_FILE is set but file does not exist: %s",
            cookie_path,
        )

    cookies_b64 = os.getenv("YTDLP_COOKIES_B64")
    if not cookies_b64:
        logger.info(
            "No cookies provided via YTDLP_COOKIES_FILE or YTDLP_COOKIES_B64")
        return None

    with _COOKIE_LOCK:
        if _COOKIEFILE_CACHE and os.path.exists(_COOKIEFILE_CACHE):
            logger.debug("Using cached temporary cookie file: %s",
                         _COOKIEFILE_CACHE)
            return _COOKIEFILE_CACHE

        try:
            logger.info("Decoding YTDLP_COOKIES_B64...")
            cookie_bytes = base64.b64decode(cookies_b64, validate=True)
            cookie_text = cookie_bytes.decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to decode YTDLP_COOKIES_B64: %s", exc)
            return None

        try:
            fd, temp_path = tempfile.mkstemp(
                prefix="yt-dlp-cookies-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(cookie_text)
            os.chmod(temp_path, 0o600)
            _COOKIEFILE_CACHE = temp_path
            logger.info("Created temporary cookie file: %s", temp_path)
            return temp_path
        except Exception as exc:
            logger.warning("Failed to create temporary cookie file: %s", exc)
            return None


def _is_youtube_antibot_error(message: str) -> bool:
    lower = message.lower()
    return (
        ("sign in to confirm" in lower and "not a bot" in lower)
        or "confirm you’re not a bot" in lower
        or "the following content is not available on this app" in lower
        or "this video is unavailable" in lower and "bot" in lower
        or "too many requests" in lower
        or "429" in lower
    )


def _check_bgutil_health() -> bool:
    # The bgutil provider has a /ping endpoint that returns version info.
    # We hit it to ensure the provider is active and responsive.
    ping_url = f"{DEFAULT_BGUTIL_BASE_URL.rstrip('/')}/ping"
    try:
        with urllib.request.urlopen(ping_url, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if "version" in data:
                    logger.debug(
                        "bgutil provider is healthy: version %s", data["version"])
                    return True
                logger.warning(
                    "bgutil provider /ping returned 200 but missing version field")
            else:
                logger.warning(
                    "bgutil provider /ping returned status %d at %s", response.status, ping_url)
    except Exception as exc:
        logger.warning(
            "bgutil provider health check failed at %s: %s", ping_url, exc)
    return False


def _build_ydl_opts(
    max_size_mb: int,
    cookiefile: Optional[str],
    disable_innertube: bool = False,
    clients: Optional[list[str]] = None,
) -> dict[str, Any]:
    provider_args: dict[str, list[str]] = {
        "base_url": [DEFAULT_BGUTIL_BASE_URL]
    }
    youtube_args: dict[str, Any] = {
        "player_client": clients if clients else ["ios", "android", "web", "mweb", "tv"],
        "po_token": (
            f"web+bgutilhttp:base_url={DEFAULT_BGUTIL_BASE_URL},"
            f"ios+bgutilhttp:base_url={DEFAULT_BGUTIL_BASE_URL},"
            f"android+bgutilhttp:base_url={DEFAULT_BGUTIL_BASE_URL}"
        ),
    }
    if disable_innertube:
        provider_args["disable_innertube"] = ["1"]
        youtube_args["disable_innertube"] = ["1"]

    opts: dict[str, Any] = {
        "format": _video_format(max_size_mb),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "extractor_args": {
            # Plugin-specific provider args for bgutil HTTP token provider.
            "youtubepot-bgutilhttp": provider_args,
            "youtube": youtube_args,
        },
        "concurrent_fragment_downloads": 5,
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "restrictfilenames": True,
        "logger": YdlLogger(),
        "verbose": True,  # Keep verbose for better logs in our logger
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile

    logger.debug("Built yt-dlp options (cookiefile: %s, disable_innertube: %s, clients: %s)",
                 cookiefile, disable_innertube, clients)
    return opts


def download_video(
    url: str,
    download_folder: str = "downloads",
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    logger.info("Starting download: %s (max_size=%dMB)", url, max_size_mb)
    os.makedirs(download_folder, exist_ok=True)

    bgutil_healthy = _check_bgutil_health()
    if bgutil_healthy:
        logger.info("bgutil provider is active at %s", DEFAULT_BGUTIL_BASE_URL)
    else:
        logger.warning(
            "bgutil provider seems down or unreachable at %s. PO tokens might fail.", DEFAULT_BGUTIL_BASE_URL)

    cookiefile = _get_cookiefile_from_env()
    last_error_text: Optional[str] = None
    retry_with_legacy_innertube = not cookiefile

    # Strategy 1: Default clients (ios, android, web, mweb, tv)
    # Strategy 2: Same but with disable_innertube=1
    # Strategy 3: Just ios and android (sometimes more reliable)

    attempts = [
        {"disable_innertube": False, "clients": None},
        {"disable_innertube": True, "clients": None},
        {"disable_innertube": False, "clients": ["ios", "android"]},
    ]

    for attempt in attempts:
        disable_innertube = attempt["disable_innertube"]
        clients = attempt["clients"]

        if disable_innertube and not retry_with_legacy_innertube:
            continue

        logger.info("Download attempt with disable_innertube=%s, clients=%s",
                    disable_innertube, clients or "default")

        ydl_opts = _build_ydl_opts(
            max_size_mb=max_size_mb,
            cookiefile=cookiefile,
            disable_innertube=disable_innertube,
            clients=clients,
        )
        ydl_opts["outtmpl"] = f"{download_folder}/%(title)s.%(ext)s"

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                logger.info("Extracting info and downloading...")
                info = ydl.extract_info(url, download=True)
                if not info:
                    logger.error("yt-dlp returned no info for %s", url)
                    return None, "Extraction failed", None, None

                title = info.get("title")
                author = info.get("uploader") or info.get(
                    "channel") or info.get("creator")
                logger.info("Successfully extracted info for: %s", title)

                file_path = ydl.prepare_filename(info)
                logger.debug("Expected file path: %s", file_path)

                if not os.path.exists(file_path):
                    logger.debug(
                        "File not found at %s, checking for .mp4", file_path)
                    base, _ = os.path.splitext(file_path)
                    mp4_path = f"{base}.mp4"
                    if os.path.exists(mp4_path):
                        file_path = mp4_path
                        logger.debug("Found .mp4 file at %s", file_path)

                if not os.path.exists(file_path):
                    logger.error(
                        "Download completed but output file was not found: %s", file_path)
                    return (
                        None,
                        "Download completed but output file was not found",
                        title,
                        author,
                    )

                logger.info("Download successful: %s", file_path)
                return file_path, None, title, author
        except Exception as exc:
            last_error_text = str(exc)
            logger.warning("Attempt failed (disable_innertube=%s, clients=%s): %s",
                           disable_innertube, clients or "default", last_error_text)

            if _is_youtube_antibot_error(last_error_text):
                logger.warning("Anti-bot check hit. Moving to next strategy.")
                continue
            else:
                logger.error("Download exception: %s", exc, exc_info=True)
                return None, last_error_text, None, None

    if _is_youtube_antibot_error(last_error_text):
        if not cookiefile:
            logger.error(
                "Anti-bot verification failed and no cookies provided. URL: %s", url
            )
        else:
            logger.error(
                "Anti-bot verification failed even with cookies. URL: %s", url
            )

    return None, last_error_text or "Download failed", None, None
