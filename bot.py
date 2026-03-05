import os
import logging
import asyncpg
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

# === ВАШИ НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
# Получаем ссылку на базу данных из Railway
DATABASE_URL = os.getenv("DATABASE_URL") 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ИИ пока ждет своего часа (мы подключим его к новым кнопкам на следующем шаге)
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

# === ВАШЕ НОВОЕ МЕНЮ (Базовое) ===
MENU_FREE = [
    ["🔍 Найти рецепт", "🧺 Из продуктов, которые есть дома"],
    ["⚡ Быстрый ужин"],
    ["👑 Моя подписка"]
]

async def init_db():
    """Создает в базе данных блокнот для записи пользователей"""
    if not DATABASE_URL:
        logging.error("❌ DATABASE_URL не найден! Бот работает без памяти.")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Создаем таблицу, если ее еще нет
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                status TEXT DEFAULT 'trial',
                trial_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.close()
        print("✅ База данных успешно подключена и готова!")
    except Exception as e:
        print(f"❌ Ошибка при подключении к БД: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 1. ЗАПИСЫВАЕМ ПОЛЬЗОВАТЕЛЯ В БАЗУ ДАННЫХ
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            # Записываем ID, если такого еще нет
            await conn.execute('''
                INSERT INTO users (user_id, username) 
                VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING
            ''', user.id, user.username)
            await conn.close()
        except Exception as e:
            logging.error(f"Ошибка записи в БД: {e}")

    # 2. ПОКАЗЫВАЕМ НОВЫЕ КНОПКИ
    reply_markup = ReplyKeyboardMarkup(MENU_FREE, resize_keyboard=True)
    await update.message.reply_text(
        f"👨‍🍳 Добро пожаловать, {user.first_name}!\n\n"
        "Вам активирован бесплатный доступ ко всем функциям шеф-повара на 2 дня 🎁\n\n"
        "Выберите, что будем готовить:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # ВАШИ ЗАГОТОВЛЕННЫЕ ОТВЕТЫ
    if text == "🔍 Найти рецепт":
        await update.message.reply_text(
            "Напишите, какой рецепт хотите найти.\n\n"
            "Примеры:\n"
            "• куриный суп\n"
            "• паста с грибами\n"
            "• салат с тунцом\n"
            "• шоколадный десерт"
        )
    elif text == "🧺 Из продуктов, которые есть дома":
        await update.message.reply_text(
            "Напишите продукты, которые у вас есть. Можно через запятую.\n\n"
            "Примеры:\n"
            "• курица, картошка, сыр\n"
            "• яйца, помидоры, хлеб\n"
            "• рис, курица, морковь"
        )
    elif text == "⚡ Быстрый ужин":
        await update.message.reply_text(
            "Напишите основной продукт, и я предложу быстрый рецепт.\n\n"
            "Примеры:\n"
            "• курица\n"
            "• фарш\n"
            "• макароны\n"
            "• картошка"
        )
    elif text == "👑 Моя подписка":
        await update.message.reply_text(
            "Статус подписки:\n\n"
            "Тариф: Пробный (Trial)\n"
            "Доступ активен: еще 48 часов ⏳\n\n"
            "*(Здесь позже появится кнопка оплаты)*"
        )
    else:
        await update.message.reply_text("Отличный выбор! *(Здесь скоро будет ответ от ИИ по вашему запросу)* 👨‍🍳")

def main():
    import asyncio
    
    # Подключаем БД до старта бота
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    
    print("🚀 Запуск обновленного бота...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
