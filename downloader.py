import os
import yt_dlp
import logging

logger = logging.getLogger(__name__)

def download_video(url: str, download_folder: str = "downloads"):
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'po_token': f'bgutilhttp:base_url=http://127.0.0.1:4416',
            }
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
        'restrictfilenames': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # This will now utilize Deno from your Dockerfile to solve JS puzzles
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "Extraction failed"
            
            base_path = ydl.prepare_filename(info)
            file_path = os.path.splitext(base_path)[0] + ".mp3"
            
            return file_path, None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None, str(e)
