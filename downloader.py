import os
import yt_dlp
import logging

logger = logging.getLogger(__name__)

def download_video(url: str, download_folder: str = "downloads"):
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    ydl_opts = {
        'extractor_args': {'youtube': {'player_client': ['ios']}}, 
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
        'noplaylist': True,
        'restrictfilenames': True,
        # Quiet stops yt-dlp from flooding logs, but we still capture errors
        'quiet': True, 
        'no_warnings': False,
    }

    try:
        logger.info(f"Attempting to download: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None, "Could not extract info"
                
            base_path = ydl.prepare_filename(info)
            # yt-dlp converts to mp3, so we check for that extension
            file_path = os.path.splitext(base_path)[0] + ".mp3"
            
            logger.info(f"Download complete: {file_path}")
            return file_path, None
            
    except yt_dlp.utils.DownloadError as e:
        clean_error = str(e).split(';')[0] # Shorten the error message
        logger.error(f"yt-dlp DownloadError: {clean_error}")
        return None, "YouTube blocked the request or link is dead"
    except Exception as e:
        logger.error(f"Unexpected error in downloader: {e}")
        return None, str(e)
