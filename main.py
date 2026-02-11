from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Replace 'YOUR_TOKEN_HERE' with the token from BotFather
TOKEN = 'YOUR_TOKEN_HERE'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Hello {update.effective_user.first_name}!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Register the /start command handler
    app.add_handler(CommandHandler("start", start))
    
    print("Bot is running...")
    app.run_polling()
