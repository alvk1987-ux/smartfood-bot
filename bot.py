import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("8605434358:AAH5hJYuIH1YIjIS8eS8BsCb8u3OHpBDqMc")
OPENAI_API_KEY = os.getenv("sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y")
ADMIN_ID = 230764474

openai.api_key = OPENAI_API_KEY

MENU = [["🍽 Что приготовить?", "🛒 Список покупок"],
        ["👨‍🍳 Совет шефа", "⭐ Премиум рецепт"]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👨‍🍳 Привет! Я Премиальный Шеф!\n\nЧем могу помочь?",
        reply_markup=ReplyKeyboardMarkup(MENU, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.message.from_user.first_name

    if text == "🍽 Что приготовить?":
        prompt = "Предложи 3 интересных рецепта на ужин с простыми ингредиентами."
    elif text == "🛒 Список покупок":
        prompt = "Составь список продуктов для здорового питания на неделю."
    elif text == "👨‍🍳 Совет шефа":
        prompt = "Дай один профессиональный кулинарный совет от шеф-повара."
    elif text == "⭐ Премиум рецепт":
        prompt = "Дай один премиальный ресторанный рецепт с пошаговым приготовлением."
    else:
        prompt = f"Пользователь спрашивает: {text}. Ответь как шеф-повар."

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"Ошибка: {e}"

    await update.message.reply_text(answer)

def main():
    print("👨‍🍳 ШЕФ-ПОВАР ЗАПУЩЕН!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
