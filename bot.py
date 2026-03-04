import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Получаем ключи из Railway
TELEGRAM_TOKEN = os.getenv("8605434358:AAH5hJYulH1YJIjS8eS88sCb8u3OHpBDqMc")
OPENAI_API_KEY = os.getenv("sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y")

# Настраиваем клиента OpenAI
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Создаем меню (кнопки)
MENU = [
    ["🍽 Что приготовить?", "🛒 Список покупок"],
    ["👨‍🍳 Совет шефа", "⭐ Премиум рецепт"]
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(MENU, resize_keyboard=True)
    await update.message.reply_text(
        "👨‍🍳 Добро пожаловать! Я ваш персональный Премиальный Шеф.\n\n"
        "Выберите, что вас интересует в меню ниже, или просто напишите мне из каких продуктов вы хотите приготовить блюдо!",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Показываем статус "печатает...", пока думает ИИ
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # Определяем, что спросить у нейросети в зависимости от кнопки
    if user_text == "🍽 Что приготовить?":
        prompt = "Выступи в роли шеф-повара. Предложи 3 интересных и вкусных варианта ужина из простых продуктов. Опиши их аппетитно."
    elif user_text == "🛒 Список покупок":
        prompt = "Выступи в роли диетолога. Составь базовый список продуктов на неделю для здорового и вкусного питания."
    elif user_text == "👨‍🍳 Совет шефа":
        prompt = "Дай один очень полезный, но малоизвестный кулинарный лайфхак от профессионального шеф-повара."
    elif user_text == "⭐ Премиум рецепт":
        prompt = "Поделись одним подробным пошаговым рецептом ресторанного блюда, которое можно приготовить дома."
    else:
        prompt = f"Ответь на следующий вопрос пользователя как опытный, вежливый и креативный шеф-повар: {user_text}"

    try:
        # Отправляем запрос в OpenAI
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo", # Можете поменять на gpt-4o-mini, если хотите
            messages=[
                {"role": "system", "content": "Ты — элитный шеф-повар. Твои ответы всегда структурированные, вежливые и со вкусом."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"К сожалению, на кухне небольшие технические неполадки с ИИ. Проверьте ключ OpenAI. Ошибка: {e}"

    # Отправляем ответ пользователю
    await update.message.reply_text(answer)

def main():
    if not TELEGRAM_TOKEN:
        print("❌ ОШИБКА: Токен Telegram не найден!")
        return
    if not OPENAI_API_KEY:
        print("❌ ОШИБКА: Ключ OPENAI_API_KEY не найден в настройках!")
        
    print("🚀 Запуск полноценного Шеф-повара с ИИ...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
