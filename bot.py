import os
import logging
import json
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue
from telegram.constants import ChatMemberStatus
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== НАСТРОЙКИ ПЛАТНОГО КАНАЛА =====
PREMIUM_CHANNEL_ID = "@your_premium_channel"  # ВАШ ПЛАТНЫЙ КАНАЛ (замените!)
CHANNEL_PAYMENT_LINK = "https://paywall.pw/your_link"  # ВАША ССЫЛКА PAYWALL (замените!)
PRICE = 399  # Цена подписки
TRIAL_DAYS = 2  # Дней бесплатно

# ===== ХРАНИЛИЩЕ ДАННЫХ =====
USERS_FILE = "users.json"
MEALS_FILE = "meals.json"

def load_json(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_json(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загружаем данные
users_db = load_json(USERS_FILE)
meals_db = load_json(MEALS_FILE)

def get_client():
    """OpenAI клиент"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.proxyapi.ru/openai/v1")

async def check_channel_subscription(context, user_id):
    """Проверка подписки на платный канал"""
    try:
        member = await context.bot.get_chat_member(
            chat_id=PREMIUM_CHANNEL_ID,
            user_id=user_id
        )
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Check subscription error: {e}")
        return False

def get_user_status(user_id, context=None):
    """
    Получение статуса пользователя
    Returns: ('trial', days_left) | ('premium', None) | ('expired', None)
    """
    user_id = str(user_id)
    
    # Новый пользователь
    if user_id not in users_db:
        return ('new', TRIAL_DAYS)
    
    user = users_db[user_id]
    now = datetime.now()
    
    # Проверяем пробный период
    if 'trial_start' in user:
        trial_start = datetime.fromisoformat(user['trial_start'])
        trial_end = trial_start + timedelta(days=TRIAL_DAYS)
        
        if now <= trial_end:
            # Еще в пробном периоде
            time_left = trial_end - now
            days = time_left.days
            hours = time_left.seconds // 3600
            
            if days > 0:
                return ('trial', f"{days}д {hours}ч")
            else:
                return ('trial', f"{hours} часов")
    
    # Проверяем подписку на канал (будет проверяться при каждом действии)
    if user.get('has_premium', False):
        return ('premium', None)
    
    return ('expired', None)

def get_keyboard(status):
    """Клавиатура в зависимости от статуса"""
    if status in ['trial', 'premium']:
        # Полный доступ
        keyboard = [
            [KeyboardButton("🧮 КБЖУ"), KeyboardButton("⚖️ Мой вес")],
            [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍎 Перекус")],
            [KeyboardButton("🍽 Обед"), KeyboardButton("🌙 Ужин")],
            [KeyboardButton("💧 Вода"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Вопрос о еде"), KeyboardButton("💳 Подписка")]
        ]
    else:
        # Ограниченный доступ
        keyboard = [
            [KeyboardButton("💳 Купить доступ 399₽")],
            [KeyboardButton("✅ Я оплатил подписку")],
            [KeyboardButton("ℹ️ Что умеет бот?")],
            [KeyboardButton("🎁 Активировать промокод")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Проверяем подписку на канал
    has_premium = await check_channel_subscription(context, user.id)
    
    # Новый пользователь
    if user_id not in users_db:
        users_db[user_id] = {
            "name": user.first_name,
            "trial_start": datetime.now().isoformat(),
            "joined": datetime.now().isoformat(),
            "has_premium": has_premium,
            "target_calories": 2000,
            "target_protein": 100,
            "target_fats": 70,
            "target_carbs": 250,
            "questions_today": 0
        }
        save_json(users_db, USERS_FILE)
        
        if user_id not in meals_db:
            meals_db[user_id] = []
            save_json(meals_db, MEALS_FILE)
        
        # Планируем напоминания о конце триала
        await schedule_trial_reminders(context, int(user_id))
        
        # Приветствие для нового пользователя
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🎁 **ПОДАРОК: 2 ДНЯ БЕСПЛАТНО!**\n"
            f"Все функции разблокированы на 48 часов!\n\n"
            f"🤖 Я SmartFood AI - твой умный дневник питания!\n\n"
            f"✨ Что умею:\n"
            f"• AI подсчет калорий любых блюд\n"
            f"• Персональный расчет КБЖУ\n"
            f"• Дневник питания с анализом\n"
            f"• Контроль воды и веса\n"
            f"• Ответы на вопросы о питании\n\n"
            f"📝 Просто пиши что съел - AI всё посчитает!\n\n"
            f"⏰ Пробный период: 2 дня\n"
            f"💰 Далее: 399₽/месяц\n\n"
            f"Начни с расчета КБЖУ! 👇",
            reply_markup=get_keyboard('trial'),
            parse_mode='Markdown'
        )
    else:
        # Существующий пользователь
        users_db[user_id]['has_premium'] = has_premium
        save_json(users_db, USERS_FILE)
        
        status, time_left = get_user_status(user_id)
        
        if has_premium:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"✅ Подписка на канал активна!\n"
                f"Все функции разблокированы!\n\n"
                f"Выбери действие 👇",
                reply_markup=get_keyboard('premium')
            )
        elif status == 'trial':
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"🎁 Пробный период активен!\n"
                f"⏰ Осталось: {time_left}\n\n"
                f"Выбери действие 👇",
                reply_markup=get_keyboard('trial')
            )
        else:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"❌ Пробный период завершен!\n\n"
                f"Для продолжения нужна подписка:\n"
                f"💰 399₽/месяц - это всего 13₽/день!\n\n"
                f"Нажми для оплаты 👇",
                reply_markup=get_keyboard('expired')
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Проверяем ожидающие вводы
    waiting_for = context.user_data.get('waiting_for')
    
    if waiting_for:
        if waiting_for == 'kbzhu_data':
            await process_kbzhu_data(update, context)
        elif waiting_for == 'meal_description':
            await process_meal_description(update, context)
        elif waiting_for == 'weight':
            await process_weight(update, context)
        elif waiting_for == 'question':
            await process_question(update, context)
        return
    
    # === КНОПКИ БЕЗ ПОДПИСКИ ===
    
    if text == "💳 Купить доступ 399₽":
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить на Paywall", url=CHANNEL_PAYMENT_LINK)],
            [InlineKeyboardButton("✅ Я оплатил", callback_data="check_payment")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status, time_left = get_user_status(user_id)
        
        if status == 'trial':
            trial_text = f"⏰ У вас еще есть {time_left} бесплатного доступа!\n\n"
        else:
            trial_text = ""
        
        await update.message.reply_text(
            f"💳 **ОФОРМЛЕНИЕ ПОДПИСКИ**\n\n"
            f"{trial_text}"
            f"💰 Стоимость: 399₽/месяц\n"
            f"Это всего 13₽ в день!\n\n"
            f"✅ Что входит:\n"
            f"• Доступ к платному каналу с контентом\n"
            f"• AI-бот для подсчета калорий\n"
            f"• Дневник питания\n"
            f"• Персональные рекомендации\n"
            f"• Поддержка 24/7\n\n"
            f"📝 Как оплатить:\n"
            f"1. Нажмите 'Оплатить на Paywall'\n"
            f"2. Оплатите подписку картой\n"
            f"3. Вернитесь и нажмите 'Я оплатил'\n\n"
            f"После оплаты вы получите:\n"
            f"• Доступ к каналу {PREMIUM_CHANNEL_ID}\n"
            f"• Полный функционал бота",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    elif text == "✅ Я оплатил подписку":
        # Проверяем подписку
        has_premium = await check_channel_subscription(context, user_id)
        
        if has_premium:
            users_db[user_id_str]['has_premium'] = True
            save_json(users_db, USERS_FILE)
            
            await update.message.reply_text(
                "✅ Отлично! Подписка подтверждена!\n\n"
                "🎉 Добро пожаловать в Premium!\n"
                "Все функции разблокированы!",
                reply_markup=get_keyboard('premium')
            )
        else:
            await update.message.reply_text(
                "❌ Подписка не найдена!\n\n"
                "Убедитесь, что:\n"
                "1. Оплата прошла успешно\n"
                f"2. Вы вступили в канал {PREMIUM_CHANNEL_ID}\n\n"
                "Если оплатили только что, подождите 1 минуту и попробуйте снова.",
                reply_markup=get_keyboard('expired')
            )
        return
    
    elif text == "ℹ️ Что умеет бот?":
        await show_features(update, context)
        return
    
    elif text == "🎁 Активировать промокод":
        await update.message.reply_text(
            "🎁 Введите промокод:\n\n"
            "Промокоды можно получить:\n"
            "• В нашем канале\n"
            "• У блогеров-партнеров\n"
            "• На специальных акциях"
        )
        return
    
    elif text == "💳 Подписка":
        # Показываем статус подписки
        status, time_left = get_user_status(user_id)
        has_premium = await check_channel_subscription(context, user_id)
        
        if has_premium:
            status_text = "✅ Подписка активна!\nДоступ к каналу подтвержден."
        elif status == 'trial':
            status_text = f"🎁 Пробный период\n⏰ Осталось: {time_left}"
        else:
            status_text = "❌ Нет активной подписки"
        
        keyboard = [
            [InlineKeyboardButton("💳 Продлить подписку", url=CHANNEL_PAYMENT_LINK)],
            [InlineKeyboardButton("📊 История платежей", callback_data="payment_history")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💳 **СТАТУС ПОДПИСКИ**\n\n"
            f"{status_text}\n\n"
            f"Тариф: 399₽/месяц\n"
            f"Канал: {PREMIUM_CHANNEL_ID}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # === ПРОВЕРКА ДОСТУПА К ФУНКЦИЯМ ===
    
    # Проверяем статус для основных функций
    status, time_left = get_user_status(user_id)
    has_premium = await check_channel_subscription(context, user_id)
    
    # Обновляем статус премиума
    if has_premium:
        users_db[user_id_str]['has_premium'] = True
        save_json(users_db, USERS_FILE)
        status = 'premium'
    
    if status not in ['trial', 'premium']:
        await update.message.reply_text(
            "❌ Пробный период завершен!\n\n"
            "Для доступа к функциям нужна подписка.\n"
            "💰 Всего 399₽/месяц\n\n"
            "Нажмите 'Купить доступ' 👇",
            reply_markup=get_keyboard('expired')
        )
        return
    
    # === ФУНКЦИИ ДЛЯ ПОДПИСЧИКОВ ===
    
    if text == "🧮 КБЖУ":
        await update.message.reply_text(
            "🧮 Напиши одним сообщением:\n\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 Пример:\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть"
        )
        context.user_data['waiting_for'] = 'kbzhu_data'
    
    elif text == "⚖️ Мой вес":
        await update.message.reply_text("⚖️ Введи свой вес (кг):")
        context.user_data['waiting_for'] = 'weight'
    
    elif text in ["🌅 Завтрак", "🍎 Перекус", "🍽 Обед", "🌙 Ужин"]:
        meal_types = {
            "🌅 Завтрак": "breakfast",
            "🍎 Перекус": "snack",
            "🍽 Обед": "lunch",
            "🌙 Ужин": "dinner"
        }
        context.user_data['current_meal'] = meal_types[text]
        
        await update.message.reply_text(
            f"{text}\n\n"
            f"📝 Напиши что съел(а):\n\n"
            f"Примеры:\n"
            f"• Овсянка с бананом\n"
            f"• Куриная грудка 150г с рисом\n"
            f"• Борщ со сметаной"
        )
        context.user_data['waiting_for'] = 'meal_description'
    
    elif text == "💧 Вода":
        await record_water(update, context)
    
    elif text == "📊 Статистика":
        await show_daily_stats(update, context)
    
    elif text == "❓ Вопрос о еде":
        await ask_question(update, context)
    
    else:
        await update.message.reply_text(
            "Используй кнопки меню 👇",
            reply_markup=get_keyboard(status)
        )

# === НАПОМИНАНИЯ О КОНЦЕ ТРИАЛА ===

async def schedule_trial_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Планирование напоминаний о конце пробного периода"""
    job_queue = context.job_queue
    
    # Напоминание за 6 часов до конца
    job_queue.run_once(
        trial_ending_soon,
        when=timedelta(days=TRIAL_DAYS, hours=-6),
        data=user_id,
        name=f"trial_6h_{user_id}"
    )
    
    # Напоминание когда закончится
    job_queue.run_once(
        trial_ended,
        when=timedelta(days=TRIAL_DAYS),
        data=user_id,
        name=f"trial_end_{user_id}"
    )

async def trial_ending_soon(context: ContextTypes.DEFAULT_TYPE):
    """Напоминание за 6 часов до конца триала"""
    user_id = context.job.data
    
    keyboard = [
        [InlineKeyboardButton("💳 Оформить подписку", url=CHANNEL_PAYMENT_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=user_id,
        text="⏰ **ПРОБНЫЙ ПЕРИОД ЗАКАНЧИВАЕТСЯ!**\n\n"
             "Осталось всего 6 часов!\n\n"
             "Оформите подписку сейчас и получите:\n"
             "✅ Полный доступ к боту\n"
             "✅ Эксклюзивный контент в канале\n"
             "✅ Персональные рекомендации\n\n"
             "💰 Всего 399₽/месяц",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def trial_ended(context: ContextTypes.DEFAULT_TYPE):
    """Уведомление об окончании триала"""
    user_id = context.job.data
    
    keyboard = [
        [InlineKeyboardButton("💳 Купить доступ", url=CHANNEL_PAYMENT_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=user_id,
        text="❌ **ПРОБНЫЙ ПЕРИОД ЗАВЕРШЕН!**\n\n"
             "Спасибо, что попробовали SmartFood AI!\n\n"
             "Для продолжения использования нужна подписка:\n"
             "💰 399₽/месяц (это всего 13₽ в день!)\n\n"
             "Нажмите кнопку ниже для оплаты 👇",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# === ФУНКЦИИ ОБРАБОТКИ ===

async def process_kbzhu_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI рассчитывает...")
    
    try:
        client = get_client()
        if not client:
            # Если нет API, используем примерные значения
            calories = 2000
            protein = 100
            fats = 70
            carbs = 250
        else:
            prompt = f"""
            Рассчитай норму КБЖУ для: {user_input}
            
            Используй формулу Миффлина-Сан Жеора.
            
            Ответ ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты диетолог. Рассчитай КБЖУ точно."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
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
        
        users_db[user_id]['target_calories'] = calories
        users_db[user_id]['target_protein'] = protein
        users_db[user_id]['target_fats'] = fats
        users_db[user_id]['target_carbs'] = carbs
        save_json(users_db, USERS_FILE)
        
        status, _ = get_user_status(update.effective_user.id)
        
        await update.message.reply_text(
            f"✅ **ТВОЯ НОРМА:**\n\n"
            f"🔥 Калории: {calories} ккал\n"
            f"🥩 Белки: {protein} г\n"
            f"🥑 Жиры: {fats} г\n"
            f"🍞 Углеводы: {carbs} г\n"
            f"💧 Вода: 2000 мл\n\n"
            f"Теперь записывай приемы пищи!",
            reply_markup=get_keyboard(status),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка расчета")
    
    context.user_data['waiting_for'] = None

async def process_meal_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды"""
    description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('current_meal', 'snack')
    
    await update.message.reply_text("⏳ AI анализирует...")
    
    try:
        client = get_client()
        if not client:
            calories = 350
            protein = 25
            fats = 15
            carbs = 40
        else:
            prompt = f"""
            Проанализируй еду: {description}
            
            Ответ ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Рассчитай КБЖУ точно."},
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
        today = datetime.now().strftime("%Y-%m-%d")
        if user_id not in meals_db:
            meals_db[user_id] = []
        
        meals_db[user_id].append({
            'type': meal_type,
            'description': description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': today,
            'time': datetime.now().strftime("%H:%M")
        })
        save_json(meals_db, MEALS_FILE)
        
        meal_emoji = {
            'breakfast': '🌅',
            'snack': '🍎',
            'lunch': '🍽',
            'dinner': '🌙'
        }.get(meal_type, '🍴')
        
        status, _ = get_user_status(update.effective_user.id)
        
        await update.message.reply_text(
            f"✅ Записано!\n\n"
            f"{meal_emoji} {description}\n\n"
            f"📊 **КБЖУ:**\n"
            f"🔥 {calories} ккал\n"
            f"🥩 {protein:.1f} г белка\n"
            f"🥑 {fats:.1f} г жиров\n"
            f"🍞 {carbs:.1f} г углеводов",
            reply_markup=get_keyboard(status),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка анализа")
    
    context.user_data['waiting_for'] = None

async def record_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись воды"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_db:
        meals_db[user_id] = []
    
    water_today = sum(1 for m in meals_db[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    meals_db[user_id].append({
        'type': 'water',
        'date': today,
        'time': datetime.now().strftime("%H:%M")
    })
    save_json(meals_db, MEALS_FILE)
    
    water_ml = (water_today + 1) * 250
    
    status, _ = get_user_status(update.effective_user.id)
    
    await update.message.reply_text(
        f"💧 +250 мл\n\n"
        f"Сегодня: {water_ml} / 2000 мл\
