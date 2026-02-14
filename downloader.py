import logging
import os
from typing import Optional, Tuple

import yt_dlp

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "1900"))


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


def download_video(
    url: str,
    download_folder: str = "downloads",
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> Tuple[Optional[str], Optional[str]]:
    os.makedirs(download_folder, exist_ok=True)

    ydl_opts = {
        "format": _video_format(max_size_mb),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "po_token": "bgutilhttp:base_url=http://127.0.0.1:4416",
            }
        },
        "outtmpl": f"{download_folder}/%(title)s.%(ext)s",
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "Extraction failed"

            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                base, _ = os.path.splitext(file_path)
                mp4_path = f"{base}.mp4"
                if os.path.exists(mp4_path):
                    file_path = mp4_path

            if not os.path.exists(file_path):
                return None, "Download completed but output file was not found"

            return file_path, None
    except Exception as exc:
        logger.error("Download error: %s", exc)
        return None, str(exc)
