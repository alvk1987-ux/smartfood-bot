import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.proxyapi.ru/openai/v1"
)

WAITING_FOOD = 1

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🍽 Анализ питания"), KeyboardButton("📊 Мой профиль")],
        [KeyboardButton("💡 Совет дня"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🥗 Привет, {user.first_name}!\n\n"
        f"Я SmartFood AI — твой персональный нутрициолог!\n\n"
        f"Что я умею:\n"
        f"🍽 Анализ питания — отправь фото или опиши еду\n"
        f"📊 Профиль — твои данные и цели\n"
        f"💡 Советы — персональные рекомендации\n\n"
        f"Начнём? Нажми кнопку ниже! 👇",
        reply_markup=get_main_keyboard()
    )

async def analyze_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍽 Опиши что ты съел(а)?\n\n"
        "Например: «Гречка с курицей и салат»"
    )
    return WAITING_FOOD

async def analyze_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    food_text = update.message.text
    await update.message.reply_text("⏳ Анализирую...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты профессиональный нутрициолог. Проанализируй еду пользователя. Укажи примерные КБЖУ (калории, белки, жиры, углеводы) и дай краткую оценку. Отвечай на русском, используй эмодзи."},
                {"role": "user", "content": f"Я съел: {food_text}"}
            ],
            max_tokens=500
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        await update.message.reply_text(
            "❌ Ошибка анализа. Попробуй позже.",
            reply_markup=get_main_keyboard()
        )
    return ConversationHandler.END

async def tip_of_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Дай один короткий полезный совет про питание. На русском, с эмодзи."},
                {"role": "user", "content": "Дай совет дня про здоровое питание"}
            ],
            max_tokens=200
        )
        tip = response.choices[0].message.content
        await update.message.reply_text(f"💡 Совет дня:\n\n{tip}", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуй позже.", reply_markup=get_main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ SmartFood AI — Помощь\n\n"
        "🍽 Анализ питания — опиши еду, получи КБЖУ\n"
        "📊 Профиль — информация о тебе\n"
        "💡 Совет дня — полезная рекомендация\n\n"
        "Просто нажимай кнопки! 👇",
        reply_markup=get_main_keyboard()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"📊 Профиль\n\n"
        f"👤 {user.first_name}\n"
        f"🆔 {user.id}\n\n"
        f"🚧 Полный профиль — в разработке!",
        reply_markup=get_main_keyboard()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽 Анализ питания$"), analyze_food_start)],
        states={WAITING_FOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_food)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("^💡 Совет дня$"), tip_of_day))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Помощь$"), help_cmd))
    app.add_handler(MessageHandler(filters.Regex("^📊 Мой профиль$"), profile))
    
    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
