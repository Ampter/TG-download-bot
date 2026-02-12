import os
import yt_dlp

def download_video(url: str, download_folder: str = "downloads"):
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        # Use a template that avoids issues with special characters
        'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
        'noplaylist': True,
        'restrictfilenames': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: #type: ignore
            info = ydl.extract_info(url, download=True)
            # Get the expected filename and force the .mp3 extension check
            base_path = ydl.prepare_filename(info)
            file_path = os.path.splitext(base_path)[0] + ".mp3"
            
            return file_path
    except Exception as e:
        print(f"Error downloading audio: {e}")
        return None
