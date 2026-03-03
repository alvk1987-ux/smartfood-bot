import os
import logging
import json
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
from telegram.constants import ChatMemberStatus, ParseMode
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== НАСТРОЙКИ ======
ADMIN_ID = 123456789  # ЗАМЕНИТЕ НА ВАШ ID!
ADMIN_USERNAME = "@alexs_v_k"
TRIAL_DAYS = 3
PRICE = 999
PHONE = "+7 937 275 37 81"
RECIPIENT = "Олег Юш"
BANKS = "Сбер, ВТБ"

# ====== ФАЙЛЫ ДАННЫХ ======
USERS_FILE = "users.json"
PAYMENTS_FILE = "payments.json"
MEALS_FILE = "meals.json"

# ====== ХРАНИЛИЩЕ ======
users_db = {}
payments_db = {}
meals_db = {}

# ====== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ======
def load_data():
    global users_db, payments_db, meals_db
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users_db = json.load(f)
    except:
        users_db = {}
    
    try:
        with open(PAYMENTS_FILE, 'r', encoding='utf-8') as f:
            payments_db = json.load(f)
    except:
        payments_db = {}
    
    try:
        with open(MEALS_FILE, 'r', encoding='utf-8') as f:
            meals_db = json.load(f)
    except:
        meals_db = {}

def save_data():
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)
    
    with open(PAYMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(payments_db, f, ensure_ascii=False, indent=2)
    
    with open(MEALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(meals_db, f, ensure_ascii=False, indent=2)

# Загружаем данные при старте
load_data()

# ====== OPENAI КЛИЕНТ ======
def get_openai_client():
    """Создание клиента OpenAI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    return OpenAI(
        api_key=api_key,
        base_url="https://api.proxyapi.ru/openai/v1"
    )

# ====== ПРОВЕРКА СТАТУСА ======
def get_user_status(user_id):
    """Получить статус пользователя"""
    user_id = str(user_id)
    
    # Новый пользователь
    if user_id not in users_db:
        return 'new', TRIAL_DAYS
    
    user = users_db[user_id]
    
    # Оплаченный доступ
    if user.get('paid', False):
        return 'paid', None
    
    # Проверка триала
    now = datetime.now()
    if 'trial_start' in user:
        trial_start = datetime.fromisoformat(user['trial_start'])
        trial_end = trial_start + timedelta(days=TRIAL_DAYS)
        
        if now <= trial_end:
            hours_left = int((trial_end - now).total_seconds() / 3600)
            days_left = hours_left // 24
            
            if days_left > 0:
                return 'trial', f"{days_left}д {hours_left % 24}ч"
            else:
                return 'trial', f"{hours_left} часов"
        else:
            return 'expired', 0
    
    return 'expired', 0

# ====== КЛАВИАТУРЫ ======
def get_keyboard(status):
    """Клавиатура в зависимости от статуса"""
    if status in ['trial', 'paid']:
        # Полный доступ
        keyboard = [
            [KeyboardButton("🧮 Расчет КБЖУ"), KeyboardButton("⚖️ Мой вес")],
            [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍎 Перекус")],
            [KeyboardButton("🍽 Обед"), KeyboardButton("🌙 Ужин")],
            [KeyboardButton("💧 Вода"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Вопрос диетологу"), KeyboardButton("👤 Мой профиль")]
        ]
    else:
        # Триал закончился
        keyboard = [
            [KeyboardButton("💳 Купить доступ 999₽")],
            [KeyboardButton("✅ Я оплатил")],
            [KeyboardButton("📞 Связаться с поддержкой")],
            [KeyboardButton("ℹ️ О боте")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====== КОМАНДА START ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Сброс состояния
    context.user_data.clear()
    
    # Новый пользователь
    if user_id not in users_db:
        users_db[user_id] = {
            "username": user.username,
            "name": user.first_name,
            "trial_start": datetime.now().isoformat(),
            "joined": datetime.now().isoformat(),
            "paid": False,
            "questions_today": 0,
            "questions_date": datetime.now().strftime("%Y-%m-%d")
        }
        meals_db[user_id] = {"water": 0, "meals": []}
        save_data()
        
        # Уведомление админу
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👤 Новый пользователь:\n"
                     f"Имя: {user.first_name}\n"
                     f"Username: @{user.username}\n"
                     f"ID: {user_id}\n"
                     f"Начал пробный период на {TRIAL_DAYS} дня"
            )
        except:
            pass
        
        # Планируем напоминания
        await schedule_trial_reminders(context, int(user_id))
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🎁 <b>ПОДАРОК: {TRIAL_DAYS} ДНЯ БЕСПЛАТНО!</b>\n"
            f"Все функции разблокированы!\n\n"
            f"🤖 Я SmartFood AI - твой личный диетолог!\n\n"
            f"✨ Что я умею:\n"
            f"• Рассчитаю твою норму КБЖУ\n"
            f"• Проанализирую любое блюдо\n"
            f"• Веду дневник питания\n"
            f"• Отвечаю на вопросы о еде\n"
            f"• Контролирую воду и вес\n\n"
            f"📝 Просто пиши что съел - я всё посчитаю!\n\n"
            f"После {TRIAL_DAYS} дней - {PRICE}₽ навсегда!\n\n"
            f"Начни с расчета КБЖУ 👇",
            reply_markup=get_keyboard('trial'),
            parse_mode=ParseMode.HTML
        )
    
    # Существующий пользователь
    else:
        status, time_left = get_user_status(user_id)
        
        if status == 'paid':
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"✅ У вас полный доступ!\n"
                f"Все функции разблокированы навсегда!",
                reply_markup=get_keyboard('paid')
            )
        elif status == 'trial':
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"🎁 Пробный период активен\n"
                f"⏰ Осталось: {time_left}\n\n"
                f"Используйте все функции!",
                reply_markup=get_keyboard('trial')
            )
        else:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"❌ Пробный период завершен!\n\n"
                f"💳 Получите полный доступ навсегда\n"
                f"всего за {PRICE}₽!",
                reply_markup=get_keyboard('expired')
            )

# ====== ОБРАБОТКА СООБЩЕНИЙ ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех текстовых сообщений"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    user_id = str(update.effective_user.id)
    user = update.effective_user
    
    # Проверка ожидания ввода
    waiting = context.user_data.get('waiting_for')
    
    # ОБРАБОТКА ВВОДОВ
    if waiting == 'kbzhu_input':
        await process_kbzhu(update, context)
        return
    elif waiting == 'weight_input':
        await process_weight(update, context)
        return
    elif waiting == 'meal_input':
        await process_meal(update, context)
        return
    elif waiting == 'question_input':
        await process_question(update, context)
        return
    
    # КНОПКИ БЕЗ ДОСТУПА
    if text == "💳 Купить доступ 999₽":
        keyboard = [
            [InlineKeyboardButton("📱 Инструкция оплаты", callback_data="payment_info")],
            [InlineKeyboardButton("✅ Я оплатил", callback_data="i_paid")]
        ]
        
        await update.message.reply_text(
            f"💳 <b>ПОКУПКА ПОЛНОГО ДОСТУПА</b>\n\n"
            f"💰 Стоимость: <b>{PRICE}₽</b>\n"
            f"✅ Один раз и НАВСЕГДА!\n\n"
            f"<b>Что вы получите:</b>\n"
            f"• Полный доступ ко всем функциям\n"
            f"• AI-анализ любых блюд\n"
            f"• Персональный расчет КБЖУ\n"
            f"• Дневник питания\n"
            f"• Неограниченные вопросы диетологу\n"
            f"• Пожизненные обновления\n\n"
            f"<b>📱 Как оплатить:</b>\n\n"
            f"1️⃣ Переведите {PRICE}₽ на номер:\n"
            f"📞 <code>{PHONE}</code>\n\n"
            f"Банк: {BANKS}\n"
            f"Получатель: {RECIPIENT}\n\n"
            f"2️⃣ Сделайте скриншот чека\n\n"
            f"3️⃣ Отправьте чек в Telegram:\n"
            f"👤 {ADMIN_USERNAME}\n\n"
            f"Напишите: 'Оплата бота' + ваш @{user.username if user.username else 'username'}\n\n"
            f"4️⃣ Ожидайте активации (до 30 минут)\n\n"
            f"✅ После проверки получите полный доступ НАВСЕГДА!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return
    
    elif text == "✅ Я оплатил":
        # Уведомление админу
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💰 УВЕДОМЛЕНИЕ ОБ ОПЛАТЕ\n\n"
                     f"Пользователь сообщил об оплате:\n"
                     f"Имя: {user.first_name}\n"
                     f"Username: @{user.username}\n"
                     f"ID: {user_id}\n\n"
                     f"Проверьте поступление {PRICE}₽\n"
                     f"Для активации используйте:\n"
                     f"<code>/activate {user_id}</code>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>Спасибо за оплату!</b>\n\n"
            f"📝 Не забудьте отправить чек:\n"
            f"👤 {ADMIN_USERNAME}\n\n"
            f"Напишите в сообщении:\n"
            f"'Оплата бота @{user.username}'\n\n"
            f"⏰ Активация в течение 30 минут\n"
            f"после проверки платежа.\n\n"
            f"❓ Если есть вопросы:\n"
            f"{ADMIN_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    elif text == "📞 Связаться с поддержкой":
        await update.message.reply_text(
            f"📞 <b>ПОДДЕРЖКА</b>\n\n"
            f"По всем вопросам обращайтесь:\n\n"
            f"👤 {ADMIN_USERNAME}\n\n"
            f"Ответим в течение 30 минут!",
            parse_mode=ParseMode.HTML
        )
        return
    
    elif text == "ℹ️ О боте":
        await update.message.reply_text(
            f"🤖 <b>SMARTFOOD AI</b>\n\n"
            f"Персональный диетолог в вашем телефоне!\n\n"
            f"<b>Возможности:</b>\n"
            f"• AI-анализ любых блюд\n"
            f"• Расчет личной нормы КБЖУ\n"
            f"• Дневник всех приемов пищи\n"
            f"• Контроль воды (8 стаканов)\n"
            f"• График изменения веса\n"
            f"• Ответы на вопросы о питании\n\n"
            f"<b>Как это работает:</b>\n"
            f"Просто напишите что съели, например:\n"
            f"'Борщ со сметаной и 2 куска хлеба'\n"
            f"AI мгновенно рассчитает КБЖУ!\n\n"
            f"💰 <b>Стоимость:</b>\n"
            f"Первые {TRIAL_DAYS} дня - БЕСПЛАТНО\n"
            f"Далее - {PRICE}₽ навсегда!\n\n"
            f"👨‍💻 Поддержка: {ADMIN_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # ПРОВЕРКА ДОСТУПА
    status, time_left = get_user_status(user_id)
    
    if status == 'expired':
        await update.message.reply_text(
            f"❌ <b>Пробный период завершен!</b>\n\n"
            f"Для продолжения оформите полный доступ.\n"
            f"💰 Всего {PRICE}₽ - навсегда!\n\n"
            f"Нажмите кнопку 'Купить доступ' 👇",
            reply_markup=get_keyboard('expired'),
            parse_mode=ParseMode.HTML
        )
        return
    
    # === ФУНКЦИИ С ПОЛНЫМ ДОСТУПОМ ===
    
    if text == "🧮 Расчет КБЖУ":
        context.user_data['waiting_for'] = 'kbzhu_input'
        await update.message.reply_text(
            "🧮 <b>РАСЧЕТ ВАШЕЙ НОРМЫ КБЖУ</b>\n\n"
            "Напишите одним сообщением:\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 <b>Пример:</b>\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть",
            parse_mode=ParseMode.HTML
        )
    
    elif text == "⚖️ Мой вес":
        context.user_data['waiting_for'] = 'weight_input'
        await update.message.reply_text(
            "⚖️ <b>ВВЕДИТЕ ВАШ ВЕС</b>\n\n"
            "Напишите текущий вес в кг\n"
            "Например: 65.5",
            parse_mode=ParseMode.HTML
        )
    
    elif text in ["🌅 Завтрак", "🍎 Перекус", "🍽 Обед", "🌙 Ужин"]:
        context.user_data['waiting_for'] = 'meal_input'
        context.user_data['meal_type'] = text
        await update.message.reply_text(
            f"{text}\n\n"
            "📝 <b>Что вы съели?</b>\n\n"
            "Напишите блюда и примерный вес.\n\n"
            "<b>Примеры:</b>\n"
            "• Овсянка с бананом и медом\n"
            "• Куриная грудка 150г с рисом\n"
            "• Борщ со сметаной, 2 куска хлеба\n"
            "• Творог 5% 200г с ягодами",
            parse_mode=ParseMode.HTML
        )
    
    elif text == "💧 Вода":
        if user_id not in meals_db:
            meals_db[user_id] = {'water': 0, 'meals': []}
        
        meals_db[user_id]['water'] = meals_db[user_id].get('water', 0) + 250
        water = meals_db[user_id]['water']
        save_data()
        
        glasses = water // 250
        emoji = "✅" if water >= 2000 else "💧"
        
        await update.message.reply_text(
            f"{emoji} <b>+1 стакан (250 мл)</b>\n\n"
            f"Сегодня выпито: {water} мл ({glasses} стаканов)\n"
            f"Норма: 2000 мл (8 стаканов)\n\n"
            f"{'🎉 Отлично! Норма выполнена!' if water >= 2000 else f'Осталось: {2000-water} мл ({(2000-water)//250} стаканов)'}",
            parse_mode=ParseMode.HTML
        )
    
    elif text == "📊 Статистика":
        await show_statistics(update, context)
    
    elif text == "❓ Вопрос диетологу":
        # Проверка лимита вопросов
        today = datetime.now().strftime("%Y-%m-%d")
        
        if users_db[user_id].get('questions_date') != today:
            users_db[user_id]['questions_today'] = 0
            users_db[user_id]['questions_date'] = today
        
        # Для оплативших - без лимита
        if status == 'paid':
            questions_left = "Безлимит"
            can_ask = True
        else:
            questions_left = 5 - users_db[user_id].get('questions_today', 0)
            can_ask = questions_left > 0
        
        if can_ask:
            context.user_data['waiting_for'] = 'question_input'
            await update.message.reply_text(
                f"❓ <b>ЗАДАЙТЕ ВОПРОС ДИЕТОЛОГУ</b>\n\n"
                f"Напишите любой вопрос о питании.\n"
                f"AI-диетолог ответит на него!\n\n"
                f"<b>Примеры вопросов:</b>\n"
                f"• Что есть после тренировки?\n"
                f"• Как убрать живот?\n"
                f"• Полезен ли кефир на ночь?\n"
                f"• Сколько калорий в банане?\n\n"
                f"Осталось вопросов: {questions_left if status != 'paid' else 'Безлимит'}",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply
