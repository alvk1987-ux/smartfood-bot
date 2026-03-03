import os
import logging
import json
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# НАСТРОЙКИ
PREMIUM_CHANNEL_ID = "@smartfood_premium"
CHANNEL_PAYMENT_LINK = "https://paywall.pw/smartfood_premium"
TRIAL_DAYS = 2
PRICE = 399

# Хранилище
users_db = {}
meals_db = {}

def get_openai_client():
    """Создание клиента OpenAI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("No OPENAI_API_KEY found!")
        return None
    
    return OpenAI(
        api_key=api_key,
        base_url="https://api.proxyapi.ru/openai/v1"
    )

async def check_subscription(context, user_id):
    """Проверка подписки на канал"""
    try:
        member = await context.bot.get_chat_member(
            chat_id=PREMIUM_CHANNEL_ID,
            user_id=user_id
        )
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

def get_user_status(user_id):
    """Статус пользователя"""
    user_id = str(user_id)
    
    if user_id not in users_db:
        return 'new', TRIAL_DAYS
    
    user = users_db[user_id]
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
    
    return 'expired', 0

def get_keyboard(has_access=False):
    """Клавиатура"""
    if has_access:
        keyboard = [
            [KeyboardButton("🧮 КБЖУ"), KeyboardButton("⚖️ Мой вес")],
            [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍎 Перекус")],
            [KeyboardButton("🍽 Обед"), KeyboardButton("🌙 Ужин")],
            [KeyboardButton("💧 Вода"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Вопрос о еде"), KeyboardButton("💳 Моя подписка")]
        ]
    else:
        keyboard = [
            [KeyboardButton("💳 Купить доступ 399₽")],
            [KeyboardButton("✅ Я оплатил и вступил в канал")],
            [KeyboardButton("ℹ️ Что умеет бот?")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Сброс состояния
    context.user_data.clear()
    
    if user_id not in users_db:
        users_db[user_id] = {
            "name": user.first_name,
            "trial_start": datetime.now().isoformat(),
            "questions_today": 0,
            "questions_date": datetime.now().strftime("%Y-%m-%d")
        }
        meals_db[user_id] = {"water": 0, "meals": []}
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🎁 **2 ДНЯ БЕСПЛАТНО!**\n\n"
            f"🤖 Я SmartFood AI - твой дневник питания!\n"
            f"Просто пиши что съел - AI всё посчитает!\n\n"
            f"Начни с расчета КБЖУ 👇",
            reply_markup=get_keyboard(True),
            parse_mode='Markdown'
        )
    else:
        status, time_left = get_user_status(user.id)
        has_premium = await check_subscription(context, user.id)
        
        if has_premium or status == 'trial':
            await update.message.reply_text(
                f"С возвращением, {user.first_name}!\n"
                f"{'✅ Подписка активна' if has_premium else f'⏰ Триал: {time_left}'}",
                reply_markup=get_keyboard(True)
            )
        else:
            await update.message.reply_text(
                "❌ Пробный период завершен!\n"
                "💰 Подписка: 399₽/месяц",
                reply_markup=get_keyboard(False)
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    user_id = str(update.effective_user.id)
    
    # Проверка ожидания ввода
    waiting = context.user_data.get('waiting_for')
    
    # ОБРАБОТКА ВВОДА ДАННЫХ
    if waiting == 'kbzhu_input':
        await calculate_kbzhu(update, context)
        return
    elif waiting == 'weight_input':
        await save_weight(update, context)
        return
    elif waiting == 'meal_input':
        await analyze_meal(update, context)
        return
    elif waiting == 'question_input':
        await answer_question(update, context)
        return
    
    # КНОПКИ БЕЗ ПОДПИСКИ
    if text == "💳 Купить доступ 399₽":
        keyboard = [[InlineKeyboardButton("💳 Оплатить на Paywall", url=CHANNEL_PAYMENT_LINK)]]
        await update.message.reply_text(
            "💳 **ОПЛАТА ПОДПИСКИ**\n\n"
            "💰 Стоимость: 399₽/месяц\n\n"
            "📝 Как оплатить:\n"
            "1. Нажмите кнопку 'Оплатить'\n"
            "2. Оплатите картой 399₽\n"
            "3. После оплаты получите ссылку\n"
            "4. Вступите в канал по ссылке\n"
            "5. Вернитесь и нажмите 'Я оплатил'\n\n"
            "✅ Что получаете:\n"
            "• AI-анализ любых блюд\n"
            "• Расчет личной нормы КБЖУ\n"
            "• Дневник питания\n"
            "• 10 вопросов AI в день",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    elif text == "✅ Я оплатил и вступил в канал":
        await update.message.reply_text("⏳ Проверяю подписку...")
        has_premium = await check_subscription(context, update.effective_user.id)
        
        if has_premium:
            users_db[user_id]['has_premium'] = True
            await update.message.reply_text(
                "✅ **ПОДПИСКА АКТИВНА!**\n\n"
                "Добро пожаловать в Premium!\n"
                "Все функции разблокированы!",
                reply_markup=get_keyboard(True),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Вас нет в канале**\n\n"
                f"Проверьте:\n"
                f"1. Оплатили на Paywall?\n"
                f"2. Вступили в {PREMIUM_CHANNEL_ID}?\n\n"
                f"После оплаты вы получите ссылку на канал",
                reply_markup=get_keyboard(False),
                parse_mode='Markdown'
            )
        return
    
    elif text == "ℹ️ Что умеет бот?":
        await update.message.reply_text(
            "🤖 **SMARTFOOD AI**\n\n"
            "• Расчет личной нормы КБЖУ\n"
            "• AI-анализ любых блюд\n"
            "• Дневник питания\n"
            "• Контроль воды (8 стаканов)\n"
            "• График веса\n"
            "• 10 вопросов диетологу/день\n\n"
            "💰 Первые 2 дня - БЕСПЛАТНО\n"
            "Далее - 399₽/месяц",
            parse_mode='Markdown'
        )
        return
    
    # ПРОВЕРКА ДОСТУПА
    status, time_left = get_user_status(update.effective_user.id)
    has_premium = await check_subscription(context, update.effective_user.id)
    
    if not has_premium and status != 'trial':
        await update.message.reply_text(
            "❌ Нет доступа!\n\n"
            "Пробный период завершен.\n"
            "Оформите подписку для продолжения.",
            reply_markup=get_keyboard(False)
        )
        return
    
    # ОСНОВНЫЕ ФУНКЦИИ
    if text == "🧮 КБЖУ":
        context.user_data['waiting_for'] = 'kbzhu_input'
        await update.message.reply_text(
            "🧮 **РАСЧЕТ ВАШЕЙ НОРМЫ**\n\n"
            "Напишите одним сообщением:\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 Пример:\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть",
            parse_mode='Markdown'
        )
    
    elif text == "⚖️ Мой вес":
        context.user_data['waiting_for'] = 'weight_input'
        await update.message.reply_text(
            "⚖️ **ВВЕДИТЕ ВЕС**\n\n"
            "Напишите ваш текущий вес в кг\n"
            "Например: 65.5",
            parse_mode='Markdown'
        )
    
    elif text in ["🌅 Завтрак", "🍎 Перекус", "🍽 Обед", "🌙 Ужин"]:
        context.user_data['waiting_for'] = 'meal_input'
        context.user_data['meal_type'] = text
        await update.message.reply_text(
            f"{text}\n\n"
            "📝 Напишите что съели:\n\n"
            "Примеры:\n"
            "• Овсянка с бананом и медом\n"
            "• Куриная грудка 150г с рисом\n"
            "• Борщ со сметаной, 2 куска хлеба"
        )
    
    elif text == "💧 Вода":
        if user_id not in meals_db:
            meals_db[user_id] = {'water': 0, 'meals': []}
        
        meals_db[user_id]['water'] = meals_db[user_id].get('water', 0) + 250
        water = meals_db[user_id]['water']
        
        emoji = "✅" if water >= 2000 else "💧"
        await update.message.reply_text(
            f"{emoji} **+250 мл**\n\n"
            f"Сегодня выпито: {water}/2000 мл\n"
            f"{'Отлично! Норма выполнена!' if water >= 2000 else f'Осталось: {2000-water} мл'}",
            parse_mode='Markdown'
        )
    
    elif text == "📊 Статистика":
        if user_id in users_db and 'calories' in users_db[user_id]:
            cal = users_db[user_id]['calories']
            prot = users_db[user_id]['protein']
            fats = users_db[user_id]['fats']
            carbs = users_db[user_id]['carbs']
            
            water = meals_db.get(user_id, {}).get('water', 0)
            meals_count = len(meals_db.get(user_id, {}).get('meals', []))
            
            eaten_cal = sum(m.get('calories', 0) for m in meals_db.get(user_id, {}).get('meals', []))
            eaten_prot = sum(m.get('protein', 0) for m in meals_db.get(user_id, {}).get('meals', []))
            eaten_fats = sum(m.get('fats', 0) for m in meals_db.get(user_id, {}).get('meals', []))
            eaten_carbs = sum(m.get('carbs', 0) for m in meals_db.get(user_id, {}).get('meals', []))
            
            await update.message.reply_text(
                f"📊 **СТАТИСТИКА ДНЯ**\n\n"
                f"📈 Съедено / Норма:\n"
                f"🔥 Калории: {eaten_cal}/{cal} ккал ({eaten_cal*100//cal if cal else 0}%)\n"
                f"🥩 Белки: {eaten_prot:.0f}/{prot} г\n"
                f"🥑 Жиры: {eaten_fats:.0f}/{fats} г\n"
                f"🍞 Углеводы: {eaten_carbs:.0f}/{carbs} г\n\n"
                f"💧 Вода: {water}/2000 мл\n"
                f"🍽 Приемов пищи: {meals_count}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "📊 **НЕТ ДАННЫХ**\n\n"
                "Сначала рассчитайте норму КБЖУ\n"
                "Нажмите кнопку 🧮 КБЖУ",
                parse_mode='Markdown'
            )
    
    elif text == "❓ Вопрос о еде":
        today = datetime.now().strftime("%Y-%m-%d")
        if users_db[user_id].get('questions_date') != today:
            users_db[user_id]['questions_today'] = 0
            users_db[user_id]['questions_date'] = today
        
        questions_left = 10 - users_db[user_id].get('questions_today', 0)
        
        if questions_left <= 0:
            await update.message.reply_text(
                "❌ **ЛИМИТ ИСЧЕРПАН**\n\n"
                "Вы использовали все 10 вопросов на сегодня.\n"
                "Новые вопросы будут доступны завтра!",
                parse_mode='Markdown'
            )
        else:
            context.user_data['waiting_for'] = 'question_input'
            await update.message.reply_text(
                f"❓ **ЗАДАЙТЕ ВОПРОС**\n\n"
                f"Напишите любой вопрос о питании.\n"
                f"Осталось вопросов сегодня: {questions_left}/10\n\n"
                f"Примеры:\n"
                f"• Что есть после тренировки?\n"
                f"• Как убрать живот?\n"
                f"• Полезен ли кефир на ночь?",
                parse_mode='Markdown'
            )
    
    elif text == "💳 Моя подписка":
        status, time_left = get_user_status(update.effective_user.id)
        has_premium = await check_subscription(context, update.effective_user.id)
        
        if has_premium:
            status_text = "✅ **ПОДПИСКА АКТИВНА**\n\nДоступ к каналу подтвержден.\nВсе функции разблокированы."
            button_text = "Управление подпиской"
        elif status == 'trial':
            status_text = f"🎁 **ПРОБНЫЙ ПЕРИОД**\n\n⏰ Осталось: {time_left}\n\nПосле окончания нужна подписка."
            button_text = "Оформить подписку"
        else:
            status_text = "❌ **НЕТ АКТИВНОЙ ПОДПИСКИ**\n\nПробный период завершен.\nДля продолжения нужна оплата."
            button_text = "Купить подписку"
        
        keyboard = [[InlineKeyboardButton(button_text, url=CHANNEL_PAYMENT_LINK)]]
        
        await update.message.reply_text(
            f"💳 **МОЯ ПОДПИСКА**\n\n"
            f"{status_text}\n\n"
            f"💰 Тариф: 399₽/месяц\n"
            f"📱 Канал: {PREMIUM_CHANNEL_ID}\n\n"
            f"При оплате вы получаете:\n"
            f"• Полный доступ к боту\n"
            f"• Эксклюзивный контент в канале\n"
            f"• Приоритетную поддержку",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    else:
        await update.message.reply_text(
            "Используйте кнопки меню 👇",
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )

async def calculate_kbzhu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ через AI"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI рассчитывает вашу норму...")
    
    try:
        client = get_openai_client()
        
        if not client:
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
        
        users_db[user_id]['calories'] = calories
        users_db[user_id]['protein'] = protein
        users_db[user_id]['fats'] = fats
        users_db[user_id]['carbs'] = carbs
        
        status, _ = get_user_status(update.effective_user.id)
        has_premium = await check_subscription(context, update.effective_user.id)
        
        await update.message.reply_text(
            f"✅ **ВАША НОРМА РАССЧИТАНА!**\n\n"
            f"🔥 Калории: {calories} ккал/день\n"
            f"🥩 Белки: {protein} г/день\n"
            f"🥑 Жиры: {fats} г/день\n"
            f"🍞 Углеводы: {carbs} г/день\n"
            f"💧 Вода: 2000 мл/день\n\n"
            f"📊 Распределение по приемам:\n"
            f"🌅 Завтрак: {int(calories*0.25)} ккал\n"
            f"🍽 Обед: {int(calories*0.35)} ккал\n"
            f"🌙 Ужин: {int(calories*0.25)} ккал\n"
            f"🍎 Перекусы: {int(calories*0.15)} ккал\n\n"
            f"Теперь записывайте приемы пищи!",
            parse_mode='Markdown',
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )
    except Exception as e:
        logger.error(f"KBZHU error: {e}")
        await update.message.reply_text("❌ Ошибка расчета. Попробуйте еще раз.")
    
    context.user_data['waiting_for'] = None

async def save_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение веса"""
    try:
        weight = float(update.message.text.replace(',', '.'))
        user_id = str(update.effective_user.id)
        
        if weight < 30 or weight > 300:
            await update.message.reply_text("❌ Некорректный вес. Введите реальное значение.")
            return
        
        users_db[user_id]['current_weight'] = weight
        users_db[user_id]['weight_date'] = datetime.now().isoformat()
        
        status, _ = get_user_status(update.effective_user.id)
        has_premium = await check_subscription(context, update.effective_user.id)
        
        await update.message.reply_text(
            f"✅ **ВЕС ЗАПИСАН**\n\n"
            f"Ваш текущий вес: {weight} кг\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"Взвешивайтесь каждую неделю в одно время!",
            parse_mode='Markdown',
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )
    except:
        await update.message.reply_text("❌ Введите число. Например: 65.5")
    
    context.user_data['waiting_for'] = None

async def analyze_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды через AI"""
    meal_description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('meal_type', '🍴')
    
    await update.message.reply_text("⏳ AI анализирует блюдо...")
    
    try:
        client = get_openai_client()
        
        if not client:
            calories = 350
            protein = 25
            fats = 15
            carbs = 40
        else:
            prompt = f"""
            Проанализируй блюдо и рассчитай КБЖУ: {meal_description}
            
            Если не указан вес - возьми стандартную порцию.
            
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
        
        if user_id not in meals_db:
            meals_db[user_id] = {'water': 0, 'meals': []}
        
        meals_db[user_id]['meals'].append({
            'type': meal_type,
            'description': meal_description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'time': datetime.now().strftime('%H:%M')
        })
        
        status, _ = get_user_status(update.effective_user.id)
        has_premium = await check_subscription(context, update.effective_user.id)
        
        await update.message.reply_text(
            f"✅ **ЗАПИСАНО!**\n\n"
            f"{meal_type} {meal_description}\n\n"
            f"📊 Пищевая ценность:\n"
            f"🔥 Калории: {calories} ккал\n"
            f"🥩 Белки: {protein:.1f} г\n"
            f"🥑 Жиры: {fats:.1f} г\n"
            f"🍞 Углеводы: {carbs:.1f} г\n\n"
            f"Продолжайте записывать приемы пищи!",
            parse_mode='Markdown',
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )
    except Exception as e:
        logger.error(f"Meal error: {e}")
        await update.message.reply_text("❌ Ошибка анализа. Попробуйте описать иначе.")
    
    context.user_data['waiting_for'] = None

async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на вопрос о еде"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    
    users_db[user_id]['questions_today'] = users_db[user_id].get('questions_today', 0) + 1
    questions_left = 10 - users_db[user_id]['questions_today']
    
    await update.message.reply_text("⏳ AI формирует ответ...")
    
    try:
        client = get_openai_client()
        
        if not client:
            answer = "К сожалению, AI временно недоступен. Попробуйте позже."
        else:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты опытный диетолог. Даешь краткие полезные советы по питанию на русском языке."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.7
            )
            answer = response.choices[0].message.content
        
        status, _ = get_user_status(update.effective_user.id)
        has_premium = await check_subscription(context, update.effective_user.id)
        
        await update.message.reply_text(
            f"💬 **ОТВЕТ AI:**\n\n"
            f"{answer}\n\n"
            f"Осталось вопросов сегодня: {questions_left}/10",
            parse_mode='Markdown',
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )
    except Exception as e:
        logger.error(f"Question error: {e}")
        await update.message.reply_text("❌ Ошибка AI. Попробуйте позже.")
    
    context.user_data['waiting_for'] = None

def main():
    """Запуск бота"""
    token =
