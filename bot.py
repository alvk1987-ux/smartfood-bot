import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOOD = 1

def get_client():
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://api.proxyapi.ru/openai/v1"
    )

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🍽 Анализ питания"), KeyboardButton("📊 Мой профиль")],
        [KeyboardButton("💡 Совет дня"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🥗 Привет, {user.first_name}! Я SmartFood AI — твой персональный нутрициолог!\n"
        f"🍽 Анализ питания — опиши еду, получи КБЖУ\n"
        f"📊 Профиль — твои данные\n"
        f"💡 Советы — рекомендации\n\n"
        f"Нажми кнопку ниже! 👇",
        reply_markup=get_main_keyboard()
    )

async def analyze_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍽 Опиши что ты съел(а)?\n\nНапример: «Гречка с курицей и салат»")
    return WAITING_FOOD

async def analyze_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    food_text = update.message.text
    await update.message.reply_text("⏳ Анализирую...")
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Проанализируй еду. Укажи КБЖУ и дай оценку. На русском, с эмодзи."},
                {"role": "user", "content": f"Я съел: {food_text}"}
            ],
            max_tokens=500
        )
        await update.message.reply_text(response.choices[0].message.content, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуй позже.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def tip_of_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Дай один короткий совет про питание. На русском, с эмодзи."},
                {"role": "user", "content": "Совет дня про здоровое питание"}
            ],
            max_tokens=200
        )
        await update.message.reply_text(f"💡 Совет дня:\n\n{response.choices[0].message.content}", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка.", reply_markup=get_main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Помощь\n\n🍽 Анализ питания — опиши еду\n📊 Профиль — о тебе\n💡 Совет дня\n\nНажимай кнопки! 👇",
        reply_markup=get_main_keyboard()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"📊 Профиль\n\n👤 {user.first_name}\n🆔 {user.id}\n\n🚧 Полный профиль скоро!",
        reply_markup=get_main_keyboard()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽 Анализ питания$"), analyze_food_start)],
        states={WAITING_FOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_food)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^💡 Совет дня$"), tip_of_day))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Помощь$"), help_cmd))
    app.add_handler(MessageHandler(filters.Regex("^📊 Мой профиль$"), profile))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
