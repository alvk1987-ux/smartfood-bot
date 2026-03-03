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
            f"Норма: 2000 мл (                f"Сегодня выпито: {water} мл ({glasses} стаканов)\n"
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
            await update.message.reply_text(
                "❌ <b>Лимит вопросов исчерпан!</b>\n\n"
                "В пробном периоде: 5 вопросов в день\n"
                "С полным доступом: безлимит!\n\n"
                "Новые вопросы будут доступны завтра.",
                parse_mode=ParseMode.HTML
            )
    
    elif text == "👤 Мой профиль":
        await show_profile(update, context)
    
    else:
        await update.message.reply_text(
            "Используйте кнопки меню 👇",
            reply_markup=get_keyboard(status)
        )

# ====== ОБРАБОТКА ВВОДА КБЖУ ======
async def process_kbzhu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ через AI"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI рассчитывает вашу норму...")
    
    try:
        client = get_openai_client()
        
        if not client:
            # Примерный расчет без API
            calories = 2000
            protein = 100
            fats = 70
            carbs = 250
        else:
            prompt = f"""
            Рассчитай точную норму КБЖУ для человека: {user_input}
            
            Используй формулу Миффлина-Сан Жеора.
            Для похудения: дефицит 20%
            Для набора массы: профицит 15%
            Для поддержания: без изменений
            
            Верни ТОЛЬКО числа в формате:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты профессиональный диетолог. Точно рассчитываешь КБЖУ."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.2
            )
            
            result = response.choices[0].message.content
            
            try:
                calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', result).group(1))
                protein = int(re.search(r'БЕЛКИ:\s*(\d+)', result).group(1))
                fats = int(re.search(r'ЖИРЫ:\s*(\d+)', result).group(1))
                carbs = int(re.search(r'УГЛЕВОДЫ:\s*(\d+)', result).group(1))
            except:
                calories = 2000
                protein = 100
                fats = 70
                carbs = 250
        
        # Сохраняем
        users_db[user_id]['calories'] = calories
        users_db[user_id]['protein'] = protein
        users_db[user_id]['fats'] = fats
        users_db[user_id]['carbs'] = carbs
        users_db[user_id]['kbzhu_data'] = user_input
        save_data()
        
        status, _ = get_user_status(user_id)
        
        await update.message.reply_text(
            f"✅ <b>ВАША НОРМА РАССЧИТАНА!</b>\n\n"
            f"🔥 Калории: <b>{calories} ккал/день</b>\n"
            f"🥩 Белки: <b>{protein} г/день</b>\n"
            f"🥑 Жиры: <b>{fats} г/день</b>\n"
            f"🍞 Углеводы: <b>{carbs} г/день</b>\n"
            f"💧 Вода: <b>2000 мл/день</b>\n\n"
            f"📊 <b>Распределение по приемам:</b>\n"
            f"🌅 Завтрак: {int(calories*0.25)} ккал\n"
            f"🍽 Обед: {int(calories*0.35)} ккал\n"
            f"🌙 Ужин: {int(calories*0.25)} ккал\n"
            f"🍎 Перекусы: {int(calories*0.15)} ккал\n\n"
            f"💡 Теперь записывайте приемы пищи!",
            reply_markup=get_keyboard(status),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"KBZHU error: {e}")
        await update.message.reply_text("❌ Ошибка расчета. Попробуйте еще раз.")
    
    context.user_data['waiting_for'] = None

# ====== ОБРАБОТКА ВЕСА ======
async def process_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение веса"""
    try:
        weight = float(update.message.text.replace(',', '.'))
        user_id = str(update.effective_user.id)
        
        if weight < 30 or weight > 300:
            await update.message.reply_text("❌ Некорректный вес. Введите реальное значение.")
            return
        
        # Сохраняем историю веса
        if 'weight_history' not in users_db[user_id]:
            users_db[user_id]['weight_history'] = []
        
        users_db[user_id]['weight_history'].append({
            'weight': weight,
            'date': datetime.now().isoformat()
        })
        users_db[user_id]['current_weight'] = weight
        save_data()
        
        status, _ = get_user_status(user_id)
        
        # Анализ изменения веса
        history = users_db[user_id]['weight_history']
        if len(history) > 1:
            prev_weight = history[-2]['weight']
            diff = weight - prev_weight
            if diff > 0:
                change = f"📈 +{diff:.1f} кг"
            elif diff < 0:
                change = f"📉 {diff:.1f} кг"
            else:
                change = "➡️ Без изменений"
        else:
            change = "Первое взвешивание"
        
        await update.message.reply_text(
            f"✅ <b>ВЕС ЗАПИСАН</b>\n\n"
            f"⚖️ Текущий вес: <b>{weight} кг</b>\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y')}\n"
            f"📊 Изменение: {change}\n\n"
            f"💡 Взвешивайтесь в одно время натощак!",
            reply_markup=get_keyboard(status),
            parse_mode=ParseMode.HTML
        )
    except:
        await update.message.reply_text("❌ Введите число. Например: 65.5")
    
    context.user_data['waiting_for'] = None

# ====== ОБРАБОТКА ЕДЫ ======
async def process_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды через AI"""
    meal_description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('meal_type', '🍴')
    
    await update.message.reply_text("⏳ AI анализирует блюдо...")
    
    try:
        client = get_openai_client()
        
        if not client:
            # Примерные значения без API
            calories = 350
            protein = 25
            fats = 15
            carbs = 40
        else:
            prompt = f"""
            Проанализируй блюдо и рассчитай точное КБЖУ: {meal_description}
            
            Если не указан вес - возьми стандартную порцию.
            Учитывай все ингредиенты и способ приготовления.
            
            Верни ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]  
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты диетолог. Точно рассчитываешь КБЖУ блюд."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.2
            )
            
            result = response.choices[0].message.content
            
            try:
                calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', result).group(1))
                protein = float(re.search(r'БЕЛКИ:\s*([\d.]+)', result).group(1))
                fats = float(re.search(r'ЖИРЫ:\s*([\d.]+)', result).group(1))
                carbs = float(re.search(r'УГЛЕВОДЫ:\s*([\d.]+)', result).group(1))
            except:
                calories = 350
                protein = 25
                fats = 15
                carbs = 40
        
        # Сохраняем
        if user_id not in meals_db:
            meals_db[user_id] = {'water': 0, 'meals': []}
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        meals_db[user_id]['meals'].append({
            'type': meal_type,
            'description': meal_description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': today,
            'time': datetime.now().strftime('%H:%M')
        })
        save_data()
        
        status, _ = get_user_status(user_id)
        
        await update.message.reply_text(
            f"✅ <b>ЗАПИСАНО!</b>\n\n"
            f"{meal_type} {meal_description}\n\n"
            f"📊 <b>Пищевая ценность:</b>\n"
            f"🔥 Калории: <b>{calories} ккал</b>\n"
            f"🥩 Белки: <b>{protein:.1f} г</b>\n"
            f"🥑 Жиры: <b>{fats:.1f} г</b>\n"
            f"🍞 Углеводы: <b>{carbs:.1f} г</b>\n\n"
            f"💡 Продолжайте записывать приемы пищи!",
            reply_markup=get_keyboard(status),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Meal error: {e}")
        await update.message.reply_text("❌ Ошибка анализа. Попробуйте описать иначе.")
    
    context.user_data['waiting_for'] = None

# ====== ОБРАБОТКА ВОПРОСОВ ======
async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на вопрос через AI"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    status, _ = get_user_status(user_id)
    
    # Увеличиваем счетчик для триала
    if status != 'paid':
        users_db[user_id]['questions_today'] = users_db[user_id].get('questions_today', 0) + 1
        questions_left = 5 - users_db[user_id]['questions_today']
    else:
        questions_left = "Безлимит"
    
    save_data()
    
    await update.message.reply_text("⏳ AI формирует ответ...")
    
    try:
        client = get_openai_client()
        
        if not client:
            answer = "К сожалению, AI временно недоступен. Попробуйте позже."
        else:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты опытный диетолог-нутрициолог. Даешь подробные, научно обоснованные ответы на вопросы о питании. Отвечай на русском языке."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.7
            )
            answer = response.choices[0].message.content
        
        await update.message.reply_text(
            f"💬 <b>ОТВЕТ ДИЕТОЛОГА:</b>\n\n"
            f"{answer}\n\n"
            f"Осталось вопросов: {questions_left}",
            reply_markup=get_keyboard(status),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Question error: {e}")
        await update.message.reply_text("❌ Ошибка AI. Попробуйте позже.")
    
    context.user_data['waiting_for'] = None

# ====== СТАТИСТИКА ======
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику дня"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Получаем норму
    if 'calories' in users_db[user_id]:
        norm_cal = users_db[user_id]['calories']
        norm_prot = users_db[user_id]['protein']
        norm_fats = users_db[user_id]['fats']
        norm_carbs = users_db[user_id]['carbs']
    else:
        await update.message.reply_text(
            "📊 Сначала рассчитайте норму КБЖУ\n"
            "Нажмите кнопку 🧮 Расчет КБЖУ"
        )
        return
    
    # Считаем съеденное за сегодня
    if user_id in meals_db and 'meals' in meals_db[user_id]:
        today_meals = [m for m in meals_db[user_id]['meals'] if m.get('date') == today]
        
        eaten_cal = sum(m.get('calories', 0) for m in today_meals)
        eaten_prot = sum(m.get('protein', 0) for m in today_meals)
        eaten_fats = sum(m.get('fats', 0) for m in today_meals)
        eaten_carbs = sum(m.get('carbs', 0) for m in today_meals)
        
        water = meals_db[user_id].get('water', 0)
        meals_count = len(today_meals)
    else:
        eaten_cal = eaten_prot = eaten_fats = eaten_carbs = 0
        water = 0
        meals_count = 0
    
    # Расчет процентов
    cal_percent = int(eaten_cal * 100 / norm_cal) if norm_cal else 0
    prot_percent = int(eaten_prot * 100 / norm_prot) if norm_prot else 0
    fats_percent = int(eaten_fats * 100 / norm_fats) if norm_fats else 0
    carbs_percent = int(eaten_carbs * 100 / norm_carbs) if norm_carbs else 0
    water_percent = int(water * 100 / 2000)
    
    # Визуализация прогресса
    def get_progress_bar(percent):
        filled = min(10, percent // 10)
        return "🟩" * filled + "⬜" * (10 - filled)
    
    status, _ = get_user_status(user_id)
    
    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА НА {datetime.now().strftime('%d.%m.%Y')}</b>\n\n"
        f"<b>📈 Съедено / Норма:</b>\n\n"
        f"🔥 Калории: {eaten_cal}/{norm_cal} ккал ({cal_percent}%)\n"
        f"{get_progress_bar(cal_percent)}\n\n"
        f"🥩 Белки: {eaten_prot:.0f}/{norm_prot} г ({prot_percent}%)\n"
        f"{get_progress_bar(prot_percent)}\n\n"
        f"🥑 Жиры: {eaten_fats:.0f}/{norm_fats} г ({fats_percent}%)\n"
        f"{get_progress_bar(fats_percent)}\n\n"
        f"🍞 Углеводы: {eaten_carbs:.0f}/{norm_carbs} г ({carbs_percent}%)\n"
        f"{get_progress_bar(carbs_percent)}\n\n"
        f"💧 Вода: {water}/2000 мл ({water_percent}%)\n"
        f"{get_progress_bar(water_percent)}\n\n"
        f"🍽 Приемов пищи: {meals_count}\n\n"
        f"{'✅ Отличный день!' if cal_percent < 110 and cal_percent > 80 else '💡 Следите за калориями!'}",
        reply_markup=get_keyboard(status),
        parse_mode=ParseMode.HTML
    )

# ====== ПРОФИЛЬ ======
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать профиль пользователя"""
    user_id = str(update.effective_user.id)
    user = update.effective_user
    status, time_left = get_user_status(user_id)
    
    # Формируем текст статуса
    if status == 'paid':
        status_text = "✅ Полный доступ (навсегда)"
    elif status == 'trial':
        status_text = f"🎁 Пробный период ({time_left})"
    else:
        status_text = "❌ Нет доступа"
    
    # Данные профиля
    joined = users_db[user_id].get('joined', 'Неизвестно')
    if joined != 'Неизвестно':
        joined_date = datetime.fromisoformat(joined).strftime('%d.%m.%Y')
    else:
        joined_date = joined
    
    weight = users_db[user_id].get('current_weight', 'Не указан')
    
    await update.message.reply_text(
        f"👤 <b>МОЙ ПРОФИЛЬ</b>\n\n"
        f"📱 ID: <code>{user_id}</code>\n"
        f"👤 Имя: {user.first_name}\n"
        f"📅 Дата регистрации: {joined_date}\n"
        f"💳 Статус: {status_text}\n"
        f"⚖️ Текущий вес: {weight} кг\n\n"
        f"<b>Ваша норма КБЖУ:</b>\n"
        f"🔥 {users_db[user_id].get('calories', 'Не рассчитано')} ккал\n"
        f"🥩 {users_db[user_id].get('protein', 'Не рассчитано')} г белка\n"
        f"🥑 {users_db[user_id].get('fats', 'Не рассчитано')} г жиров\n"
        f"🍞 {users_db[user_id].get('carbs', 'Не рассчитано')} г углеводов",
        reply_markup=get_keyboard(status),
        parse_mode=ParseMode.HTML
    )

# ====== АДМИН КОМАНДЫ ======
async def activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация пользователя админом"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /activate USER_ID\n"
            "Пример: /activate 123456789"
        )
        return
    
    user_id = context.args[0]
    
    if user_id not in users_db:
        await update.message.reply_text(f"❌ Пользователь {user_id} не найден!")
        return
    
    users_db[user_id]['paid'] = True
    users_db[user_id]['payment_date'] = datetime.now().isoformat()
    
    payments_db[user_id] = {
        'amount': PRICE,
        'date': datetime.now().isoformat(),
        'confirmed_by': 'admin',
        'method': 'manual'
    }
    save_data()
    
    # Уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                 f"✅ Ваша оплата подтверждена!\n"
                 f"Полный доступ активирован НАВСЕГДА!\n\n"
                 f"Теперь вам доступны:\n"
                 f"• Все функции без ограничений\n"
                 f"• Безлимитные вопросы диетологу\n"
                 f"• Пожизненные обновления\n\n"
                 f"Спасибо за покупку! 🙏",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ Пользователь {user_id} активирован!\n"
        f"Имя: {users_db[user_id].get('name', 'Неизвестно')}\n"
        f"Username: @{users_db[user_id].get('username', 'Неизвестно')}"
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админа"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    total_users = len(users_db)
    paid_users = len([u for u in users_db.values() if u.get('paid', False)])
    trial_users = len([u for u, data in users_db.items() if get_user_status(u)[0] == 'trial'])
    expired_users = total_users - paid_users - trial_users
    revenue = paid_users * PRICE
    
    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Оплатили: {paid_users}\n"
        f"🎁 На триале: {trial_users}\n"
        f"❌ Триал закончился: {expired_users}\n\n"
        f"💰 Доход: {revenue}₽\n"
        f"📈 Конверсия: {paid_users*100//total_users if total_users else 0}%",
        parse_mode=ParseMode.HTML
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей для админа"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = "<b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ:</b>\n\n"
    
    for user_id, data in users_db.items():
        status, _ = get_user_status(user_id)
        status_emoji = "✅" if status == 'paid' else "🎁" if status == 'trial' else "❌"
        
        text += f"{status_emoji} {data.get('name', 'Неизвестно')} "
        text += f"(@{data.get('username', 'нет')})\n"
        text += f"ID: <code>{user_id}</code>\n\n"
    
    # Разбиваем на части если слишком длинное
    if len(text) > 4000:
        text = text[:4000] + "\n\n...и другие"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ====== НАПОМИНАНИЯ ======
async def schedule_trial_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Планирование напоминаний о конце триала"""
    job_queue = context.job_queue
    
    # Напоминание за 12 часов до конца
    job_queue.run_once(
        trial_reminder,
        when=timedelta(days=TRIAL_DAYS, hours=-12),
        data=user_id,
        name=f"reminder_{user_id}"
    )

async def trial_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Напоминание о конце триала"""
    user_id = context.job.data
    
    keyboard = [
        [InlineKeyboardButton("💳 Купить сейчас", callback_data="buy_now")]
    ]
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"⏰ <b>ПРОБНЫЙ ПЕРИОД ЗАКАНЧИВАЕТСЯ!</b>\n\n"
             f"Осталось меньше 12 часов!\n\n"
             f"Не потеряйте свои данные и прогресс!\n"
             f"Оформите полный доступ сейчас:\n\n"
             f"💰 {PRICE}₽ - один раз и навсегда!\n\n"
             f"После окончания триала функции будут заблокированы.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

# ====== MAIN ======
def main():
    """Запуск бота"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Нет токена! Установите TELEGRAM_BOT_TOKEN")
        return
    
    # Создаем приложение
    app = Application.builder().token(token).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_user))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("users", admin_users))
    
    # Сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем
    logger.info("🚀 Бот запущен!")
    logger.info(f"💰 Цена: {PRICE}₽")
    logger.info(f"📱 Номер для оплаты: {PHONE}")
    logger.info(f"👤 Получатель: {RECIPIENT}")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
