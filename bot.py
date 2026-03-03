import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_keyboard():
    """Создаем клавиатуру"""
    keyboard = [
        [KeyboardButton("🧮 Тест 1"), KeyboardButton("📊 Тест 2")],
        [KeyboardButton("💬 Тест 3"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    logger.info(f"Start command from {update.effective_user.id}")
    await update.message.reply_text(
        "👋 Привет! Я работаю!\n\nНажми любую кнопку:",
        reply_markup=get_keyboard()
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех кнопок"""
    text = update.message.text
    logger.info(f"Button pressed: {text}")
    
    if text == "🧮 Тест 1":
        await update.message.reply_text("✅ Кнопка 1 работает!")
    elif text == "📊 Тест 2":
        await update.message.reply_text("✅ Кнопка 2 работает!")
    elif text == "💬 Тест 3":
        await update.message.reply_text("✅ Кнопка 3 работает!")
    elif text == "ℹ️ Помощь":
        await update.message.reply_text("✅ Помощь работает!")
    else:
        await update.message.reply_text(f"Получил: {text}")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test"""
    logger.info("Test command executed")
    await update.message.reply_text("✅ Команда /test работает!")

def main():
    """Главная функция"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    logger.info(f"Starting bot with token: {token[:10]}...")
    
    # Создаем приложение
    app = Application.builder().token(token).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button))
    
    # Запускаем
    logger.info("Bot starting polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
