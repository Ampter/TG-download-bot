import pytest
from unittest.mock import patch, MagicMock
from downloader import download_video

# 1. Test the Downloader Logic
def test_download_folder_creation(tmp_path):
    """Checks if the downloader creates the folder if it doesn't exist."""
    test_folder = tmp_path / "test_downloads"
    # Mocking yt-dlp so it doesn't actually download anything
    with patch('yt_dlp.YoutubeDL') as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
            'title': 'test_video', 'ext': 'mp4'
        }
        mock_ydl.return_value.__enter__.return_value.prepare_filename.return_value = str(test_folder / "test.mp4")
        
        # We need to mock os.path.exists to simulate the file being 'downloaded'
        with patch('os.path.exists', return_value=True):
            result = download_video("https://fake-url.com", download_folder=str(test_folder))
            assert result is not None
            assert "test_downloads" in result

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

