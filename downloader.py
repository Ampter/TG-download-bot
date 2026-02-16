import base64
import logging
import os
import tempfile
from typing import Any, Optional, Tuple, cast

import yt_dlp

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "2000"))
_COOKIEFILE_CACHE: Optional[str] = None
DEFAULT_BGUTIL_BASE_URL = os.getenv(
    "YTDLP_BGUTIL_BASE_URL", "http://127.0.0.1:4416"
)


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
            return cookie_path
        logger.warning(
            "YTDLP_COOKIES_FILE is set but file does not exist: %s",
            cookie_path,
        )

    cookies_b64 = os.getenv("YTDLP_COOKIES_B64")
    if not cookies_b64:
        return None

    if _COOKIEFILE_CACHE and os.path.exists(_COOKIEFILE_CACHE):
        return _COOKIEFILE_CACHE

    try:
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
        return temp_path
    except Exception as exc:
        logger.warning("Failed to create temporary cookie file: %s", exc)
        return None


def _is_youtube_antibot_error(message: str) -> bool:
    lower = message.lower()
    return (
        "sign in to confirm" in lower
        and "you" in lower
        and "not a bot" in lower
    )


def _build_ydl_opts(
    max_size_mb: int,
    cookiefile: Optional[str],
    disable_innertube: bool = False,
) -> dict[str, Any]:
    provider_args: dict[str, list[str]] = {
        "base_url": [DEFAULT_BGUTIL_BASE_URL]
    }
    if disable_innertube:
        provider_args["disable_innertube"] = ["1"]

    opts: dict[str, Any] = {
        "format": _video_format(max_size_mb),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "extractor_args": {
            # Plugin-specific provider args for bgutil HTTP token provider.
            "youtubepot-bgutilhttp": provider_args,
        },
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts


def download_video(
    url: str,
    download_folder: str = "downloads",
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    os.makedirs(download_folder, exist_ok=True)
    cookiefile = _get_cookiefile_from_env()
    last_error_text: Optional[str] = None
    retry_with_legacy_innertube = not cookiefile

    for disable_innertube in (False, True):
        if disable_innertube and not retry_with_legacy_innertube:
            continue

        ydl_opts = _build_ydl_opts(
            max_size_mb=max_size_mb,
            cookiefile=cookiefile,
            disable_innertube=disable_innertube,
        )
        ydl_opts["outtmpl"] = f"{download_folder}/%(title)s.%(ext)s"

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None, "Extraction failed", None, None

                title = info.get("title")
                author = info.get("uploader") or info.get(
                    "channel") or info.get("creator")

                file_path = ydl.prepare_filename(info)
                if not os.path.exists(file_path):
                    base, _ = os.path.splitext(file_path)
                    mp4_path = f"{base}.mp4"
                    if os.path.exists(mp4_path):
                        file_path = mp4_path

                if not os.path.exists(file_path):
                    return (
                        None,
                        "Download completed but output file was not found",
                        title,
                        author,
                    )

                return file_path, None, title, author
        except Exception as exc:
            last_error_text = str(exc)
            if (
                _is_youtube_antibot_error(last_error_text)
                and not disable_innertube
                and retry_with_legacy_innertube
            ):
                logger.warning(
                    "Anti-bot check hit. Retrying with disable_innertube=1."
                )
                continue
            if _is_youtube_antibot_error(last_error_text) and not cookiefile:
                logger.error(
                    "Download error: %s (set YTDLP_COOKIES_FILE or YTDLP_COOKIES_B64)",
                    exc,
                )
            else:
                logger.error("Download error: %s", exc)
            return None, last_error_text, None, None

    return None, last_error_text or "Download failed", None, None
