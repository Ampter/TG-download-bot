import os
from unittest.mock import AsyncMock, patch

import pytest
import yt_dlp
from telegram import Chat, Message, Update, User
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from downloader import download_video
from main import MAX_UPLOAD_SIZE_MB, handle_download, start


@pytest.fixture
def mock_update():
    update = AsyncMock(spec=Update)
    message = AsyncMock(spec=Message)
    chat = AsyncMock(spec=Chat)
    user = AsyncMock(spec=User)

    chat.id = 12345
    user.id = 67890
    message.chat = chat
    message.from_user = user
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()
    update.effective_message = message
    update.effective_chat = chat
    update.effective_user = user
    return update


@pytest.fixture
def mock_context():
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot.send_chat_action = AsyncMock()
    return context


def test_download_video_success(tmp_path):
    url = "https://youtu.be/dQw4w9WgXcQ"

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = {"title": "Test Video"}

        fake_video = tmp_path / "Test Video.mp4"
        fake_video.write_text("fake video")
        instance.prepare_filename.return_value = str(fake_video)

        file_path, error, title, author = download_video(
            url, download_folder=str(tmp_path)
        )

        assert error is None
        assert file_path == str(fake_video)
        assert title == "Test Video"
        assert author is None
        instance.extract_info.assert_called_once_with(url, download=True)


def test_download_video_failure(tmp_path):
    url = "https://youtu.be/invalid"

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "Sign in to confirm"
        )

        file_path, error, title, author = download_video(
            url, download_folder=str(tmp_path)
        )

        assert file_path is None
        assert "Sign in to confirm" in error
        assert title is None
        assert author is None


def test_download_video_uses_cookiefile(tmp_path, monkeypatch):
    url = "https://youtu.be/dQw4w9WgXcQ"
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(cookie_file))

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = {"title": "Test Video"}

        fake_video = tmp_path / "Test Video.mp4"
        fake_video.write_text("fake video")
        instance.prepare_filename.return_value = str(fake_video)

        file_path, error, _, _ = download_video(
            url, download_folder=str(tmp_path))

        assert error is None
        assert file_path == str(fake_video)
        called_opts = MockYDL.call_args.args[0]
        assert called_opts["cookiefile"] == str(cookie_file)


@pytest.mark.asyncio
async def test_start_handler(mock_update, mock_context):
    await start(mock_update, mock_context)
    mock_update.effective_message.reply_text.assert_called_once_with(
        "🎬 Send a YouTube link and I'll return the video."
    )


@pytest.mark.asyncio
async def test_handle_download_valid_youtube(
    mock_update, mock_context, tmp_path, monkeypatch
):
    mock_update.effective_message.text = "https://youtu.be/abc123"

    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(
        return_value=status_mock)

    fake_mp4 = tmp_path / "test.mp4"
    fake_mp4.write_bytes(b"x" * 1024)

    monkeypatch.setattr(
        "main.download_video",
        lambda *args, **kwargs: (str(fake_mp4), None,
                                 "Video title", "Video author"),
    )

    with patch("os.remove") as mock_remove:
        await handle_download(mock_update, mock_context)

    mock_update.effective_message.reply_text.assert_any_call(
        "⏳ Downloading video...")
    mock_context.bot.send_chat_action.assert_called_once()
    mock_update.effective_message.reply_document.assert_called_once()
    assert (
        mock_update.effective_message.reply_document.call_args.kwargs["caption"]
        == "🎬 Video title\n👤 Video author"
    )
    status_mock.delete.assert_awaited_once()
    mock_remove.assert_called_once_with(str(fake_mp4))


@pytest.mark.asyncio
async def test_handle_download_non_youtube(mock_update, mock_context):
    mock_update.effective_message.text = "https://google.com"

    await handle_download(mock_update, mock_context)

    mock_update.effective_message.reply_text.assert_called_once_with(
        "❌ Please send a valid YouTube link."
    )


@pytest.mark.asyncio
async def test_handle_download_failure(mock_update, mock_context, monkeypatch):
    mock_update.effective_message.text = "https://youtu.be/abc123"
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(
        return_value=status_mock)

    monkeypatch.setattr(
        "main.download_video",
        lambda *args, **kwargs: (None, "Download failed", None, None),
    )

    with patch("os.path.exists", return_value=False):
        await handle_download(mock_update, mock_context)

    status_mock.edit_text.assert_called_once_with(
        "❌ Failed to download video. Please try again later."
    )


@pytest.mark.asyncio
async def test_handle_download_antibot_failure_message(
    mock_update, mock_context, monkeypatch
):
    mock_update.effective_message.text = "https://youtu.be/abc123"
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(
        return_value=status_mock)

    monkeypatch.setattr(
        "main.download_video",
        lambda *args, **kwargs: (
            None,
            "ERROR: [youtube] xyz: Sign in to confirm you're not a bot",
            None,
            None,
        ),
    )

    with patch("os.path.exists", return_value=False):
        await handle_download(mock_update, mock_context)

    status_mock.edit_text.assert_called_once()
    error_text = status_mock.edit_text.call_args.args[0]
    assert "anti-bot verification" in error_text
    assert "YTDLP_COOKIES_FILE" in error_text


@pytest.mark.asyncio
async def test_handle_download_above_configured_limit(
    mock_update, mock_context, tmp_path, monkeypatch
):
    mock_update.effective_message.text = "https://youtu.be/abc123"
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(
        return_value=status_mock)

    fake_mp4 = tmp_path / "big.mp4"
    fake_mp4.write_bytes(b"x" * 1024)

    monkeypatch.setattr(
        "main.download_video",
        lambda *args, **kwargs: (str(fake_mp4), None,
                                 "Video title", "Video author"),
    )
    monkeypatch.setattr("main.MAX_UPLOAD_SIZE_MB", 0)
    monkeypatch.setattr(
        "main._compress_video_to_limit",
        AsyncMock(return_value=(None, "Compression failed")),
    )

    with patch("os.remove") as mock_remove:
        await handle_download(mock_update, mock_context)

    status_mock.edit_text.assert_awaited()
    mock_remove.assert_called_once_with(str(fake_mp4))


@pytest.mark.asyncio
async def test_handle_download_telegram_413(
    mock_update, mock_context, tmp_path, monkeypatch
):
    mock_update.effective_message.text = "https://youtu.be/abc123"
    status_mock = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(
        return_value=status_mock)

    fake_mp4 = tmp_path / "too_big.mp4"
    fake_mp4.write_bytes(b"x" * 1024)

    monkeypatch.setattr(
        "main.download_video",
        lambda *args, **kwargs: (str(fake_mp4), None,
                                 "Video title", "Video author"),
    )
    mock_update.effective_message.reply_document = AsyncMock(
        side_effect=BadRequest("Request Entity Too Large")
    )

    with patch("os.remove") as mock_remove:
        await handle_download(mock_update, mock_context)

    status_mock.edit_text.assert_awaited_once_with(
        f"❌ Telegram rejected the file as too large. App limit is set to {MAX_UPLOAD_SIZE_MB}MB."
    )
    mock_remove.assert_called_once_with(str(fake_mp4))


@pytest.mark.skip(reason="Requires provider running at localhost:4416")
@pytest.mark.asyncio
async def test_provider_integration():
    url = "https://youtu.be/dQw4w9WgXcQ"

    ydl_opts = {
        "format": "best",
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "po_token": "bgutilhttp:base_url=http://127.0.0.1:4416",
            }
        },
        "quiet": True,
        "simulate": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            assert info is not None
            assert "title" in info
    except Exception as e:
        pytest.fail(f"Provider integration failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
