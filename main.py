from downloader import download_video
import os

async def handle_message(update, context):
    url = update.message.text
    if "youtube.com" in url or "youtu.be" in url:
        sent_msg = await update.message.reply_text("⏳ Downloading... please wait.")
        
        file_path = download_video(url)
        
        if file_path:
            await update.message.reply_video(video=open(file_path, 'rb'))
            os.remove(file_path) # Clean up Fedora storage after sending
            await sent_msg.delete()
        else:
            await sent_msg.edit_text("❌ Failed to download. Video might be too large (>50MB).")
