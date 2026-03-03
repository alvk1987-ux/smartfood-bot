import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(WAITING_GENDER, WAITING_AGE, WAITING_WEIGHT, WAITING_HEIGHT, 
 WAITING_ACTIVITY, WAITING_GOAL, WAITING_QUESTION, WAITING_PHOTO) = range(8)

# Хранилище данных пользователей (в реальном проекте используйте БД)
user_data = {}

def get_client():
    """Клиент OpenAI с ProxyAPI"""
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://api.proxyapi.ru/openai/v1"
    )

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton("🧮 Рассчитать КБЖУ")],
        [KeyboardButton("🍱 Меню на день")],
        [KeyboardButton("📸 Анализ по фото")],
        [KeyboardButton("💬 Задать вопрос")],
        [KeyboardButton("📊 Мой профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я SmartFood AI — твой персональный нутрициолог!\n\n"
        f"Что я умею:\n"
        f"🧮 Рассчитать твою норму КБЖУ\n"
        f"🍱 Составить меню на день\n"
        f"📸 Анализировать еду по фото\n"
        f"💬 Отвечать на вопросы о питании\n"
        f"📊 Вести твой профиль\n\n"
        f"Выбери действие 👇",
        reply_markup=get_main_keyboard()
    )

# === РАСЧЕТ КБЖУ ===
async def calculate_kbzhu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало расчета КБЖУ"""
    keyboard = [
        [KeyboardButton("👨 Мужской"), KeyboardButton("👩 Женский")]
    ]
    await update.message.reply_text(
        "🧮 Начинаем расчет КБЖУ!\n\n"
        "Шаг 1/6: Укажите ваш пол:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return WAITING_GENDER

async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение пола"""
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    
    text = update.message.text
    if "Мужской" in text:
        user_data[user_id]['gender'] = 'male'
    else:
        user_data[user_id]['gender'] = 'female'
    
    await update.message.reply_text("Шаг 2/6: Введите ваш возраст (например: 25):")
    return WAITING_AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение возраста"""
    user_id = update.effective_user.id
    try:
        age = int(update.message.text)
        if age < 10 or age > 100:
            raise ValueError
        user_data[user_id]['age'] = age
        await update.message.reply_text("Шаг 3/6: Введите ваш вес в кг (например: 70):")
        return WAITING_WEIGHT
    except:
        await update.message.reply_text("❌ Введите корректный возраст (число от 10 до 100):")
        return WAITING_AGE

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение веса"""
    user_id = update.effective_user.id
    try:
        weight = float(update.message.text.replace(',', '.'))
        if weight < 30 or weight > 300:
            raise ValueError
        user_data[user_id]['weight'] = weight
        await update.message.reply_text("Шаг 4/6: Введите ваш рост в см (например: 175):")
        return WAITING_HEIGHT
    except:
        await update.message.reply_text("❌ Введите корректный вес (число от 30 до 300):")
        return WAITING_WEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение роста"""
    user_id = update.effective_user.id
    try:
        height = int(update.message.text)
        if height < 100 or height > 250:
            raise ValueError
        user_data[user_id]['height'] = height
        
        keyboard = [
            [KeyboardButton("🛋 Минимальная (сидячая работа)")],
            [KeyboardButton("🚶 Легкая (1-3 тренировки)")],
            [KeyboardButton("🏃 Средняя (3-5 тренировок)")],
            [KeyboardButton("💪 Высокая (6-7 тренировок)")],
            [KeyboardButton("🔥 Экстремальная (спортсмен)")]
        ]
        await update.message.reply_text(
            "Шаг 5/6: Выберите уровень активности:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return WAITING_ACTIVITY
    except:
        await update.message.reply_text("❌ Введите корректный рост (число от 100 до 250):")
        return WAITING_HEIGHT

async def get_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение уровня активности"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if "Минимальная" in text:
        user_data[user_id]['activity'] = 1
