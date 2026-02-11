from typing import Any, cast
import yt_dlp

import os

def download_video(url: str, download_folder: str = "downloads"):
    # Ensure the download directory exists
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    ydl_opts = {
        # Format: Best video + best audio merged, or just best single file
        # 'filesize_approx' helps stay under Telegram's 50MB limit
        'format': 'best[ext=mp4][filesize<50M]/best[ext=mp4]/best',
        'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
        # Merge into mp4 for best compatibility with Telegram players
        'merge_output_format': 'mp4',
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(params=cast(Any, ydl_opts)) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            # In case of format merging, filename might change extension to .mp4
            if not os.path.exists(file_path):
                file_path = os.path.splitext(file_path)[0] + ".mp4"
            
            return file_path
    except Exception as e:
        print(f"Error downloading: {e}")
        return None

# Test the function (optional)
if __name__ == "__main__":
    test_url = "https://www.youtube.com"
    print(f"Downloading: {test_url}")
    result = download_video(test_url)
    print(f"Finished: {result}")
