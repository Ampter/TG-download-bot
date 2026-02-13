import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
import yt_dlp

# Import your modules
from main import start, handle_download
from downloader import download_video

# -------------------------------
# Fixtures
# -------------------------------

@pytest.fixture
def mock_update():
    """Create a mock Update object with a text message."""
    update = AsyncMock(spec=Update)
    message = AsyncMock(spec=Message)
    chat = AsyncMock(spec=Chat)
    user = AsyncMock(spec=User)
    
    chat.id = 12345
    user.id = 67890
    message.chat = chat
    message.from_user = user
    message.reply_text = AsyncMock()
    message.reply_audio = AsyncMock()
    update.effective_message = message
    update.effective_chat = chat
    update.effective_user = user
    return update

@pytest.fixture
def mock_context():
    """Create a mock Context object."""
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot.send_chat_action = AsyncMock()
    return context

# -------------------------------
# Unit tests for downloader.py
# -------------------------------

def test_download_video_success(tmp_path):
    """Test download_video with a real short YouTube URL (use carefully)."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    
    with patch('yt_dlp.YoutubeDL') as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = {'title': 'Test Video'}
        instance.prepare_filename.return_value = '/fake/path/Test Video.mp4'
        
        file_path, error = download_video(url, download_folder=str(tmp_path))
        
        assert error is None
        # Because of postprocessor, .mp4 becomes .mp3
        assert file_path == '/fake/path/Test Video.mp3'
        instance.extract_info.assert_called_once_with(url, download=True)

def test_download_video_failure(tmp_path):
    """Test download_video when extraction fails."""
    url = "https://youtu.be/invalid"
    
    with patch('yt_dlp.YoutubeDL') as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Sign in to confirm")
        
        file_path, error = download_video(url, download_folder=str(tmp_path))
        
        assert file_path is None
        assert "Sign in to confirm" in error

# -------------------------------
# Tests for bot handlers (with mocks)
# -------------------------------

@pytest.mark.asyncio
async def test_start_handler(mock_update, mock_context):
    """Test the /start command."""
    await start(mock_update, mock_context)
    mock_update.effective_message.reply_text.assert_called_once_with(
        "🎵 Send me a YouTube link!"
    )

@pytest.mark.asyncio
async def test_handle_download_valid_youtube(mock_update, mock_context, tmp_path, monkeypatch):
    """Test handle_download with a valid YouTube URL, mocking download_video."""
    # Setup
    mock_update.effective_message.text = "https://youtu.be/abc123"
    
    # Mock reply_text to return a status message that we can later delete
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=status_mock)
    
    mock_context.bot.send_chat_action = AsyncMock()

    # Mock download_video to return a fake file path (synchronous function!)
    fake_mp3 = tmp_path / "test.mp3"
    fake_mp3.write_text("fake audio")
    
    def fake_download(url):
        return str(fake_mp3), None
    
    monkeypatch.setattr('main.download_video', fake_download)

    # Mock os.path.exists and os.remove
    with patch('os.path.exists', return_value=True), \
         patch('os.remove') as mock_remove:
        
        await handle_download(mock_update, mock_context)
        
        # Assertions
        mock_update.effective_message.reply_text.assert_any_call("⏳ Processing...")
        mock_context.bot.send_chat_action.assert_called_once()
        # Verify audio was sent
        mock_update.effective_message.reply_audio.assert_called_once()
        # Verify status message was deleted
        status_mock.delete.assert_awaited_once()
        # Verify file was removed
        mock_remove.assert_called_once_with(str(fake_mp3))

@pytest.mark.asyncio
async def test_handle_download_non_youtube(mock_update, mock_context):
    """Test handle_download with a non-YouTube link."""
    mock_update.effective_message.text = "https://google.com"
    
    await handle_download(mock_update, mock_context)
    
    mock_update.effective_message.reply_text.assert_called_once_with(
        "❌ Please send a valid YouTube link."
    )

@pytest.mark.asyncio
async def test_handle_download_failure(mock_update, mock_context, monkeypatch):
    """Test handle_download when download_video returns an error."""
    mock_update.effective_message.text = "https://youtu.be/abc123"
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=status_mock)
    
    # Synchronous mock function returning error
    def fake_download_error(url):
        return None, "Download failed"
    
    monkeypatch.setattr('main.download_video', fake_download_error)
    
    with patch('os.path.exists', return_value=False):
        await handle_download(mock_update, mock_context)
        
        # Check that the status message was edited with error
        status_mock.edit_text.assert_called_once_with(
            "❌ YouTube blocked the request. Please try again later."
        )

# -------------------------------
# Integration test for provider (optional)
# -------------------------------

@pytest.mark.skip(reason="Requires provider running at localhost:4416")
@pytest.mark.asyncio
async def test_provider_integration():
    """Test that yt-dlp can use the bgutil provider (requires provider running)."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'po_token': 'bgutilhttp:base_url=http://127.0.0.1:4416',
            }
        },
        'quiet': True,
        'simulate': True,  # Don't download, just extract info
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            assert info is not None
            assert 'title' in info
    except Exception as e:
        pytest.fail(f"Provider integration failed: {e}")

# -------------------------------
# Run instructions
# -------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
