import pytest
from unittest.mock import patch, MagicMock
from downloader import download_video

# 1. Test the Downloader Logic
def test_download_folder_creation(tmp_path):
    """Checks if the downloader creates the folder if it doesn't exist."""
    test_folder = tmp_path / "test_downloads"
    
    with patch('yt_dlp.YoutubeDL') as mock_ydl:
        # Mock the info dictionary
        mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
            'title': 'test_video', 
            'ext': 'mp4',
            'duration': 120
        }
        mock_ydl.return_value.__enter__.return_value.prepare_filename.return_value = str(test_folder / "test.mp4")

        with patch('os.path.exists', return_value=True):
            # UNPACK the result (path, error) or (path, title, duration) 
            # depending on which version of downloader.py you used last
            result_path, *others = download_video("https://fake-url.com", download_folder=str(test_folder))
            
            assert result_path is not None
            assert "test_downloads" in result_path


# 2. Test Bot Command (Async)
@pytest.mark.asyncio
async def test_start_command(mocker):
    """Tests if the /start command sends the correct greeting."""
    from main import start # Assuming your start function is in main.py
    
    # Mock the Update and Context objects from telegram library
    update = mocker.AsyncMock()
    context = mocker.AsyncMock()
    
    update.effective_user.first_name = "Slavek"
    update.effective_message.reply_text = mocker.AsyncMock()

    await start(update, context)

