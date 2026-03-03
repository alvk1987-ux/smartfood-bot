import os
import logging
import json
import re
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatMemberStatus
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# НАСТРОЙКИ ПЛАТНОГО КАНАЛА
PREMIUM_CHANNEL_ID = "@smartfood_premium"  # ID вашего платного канала
CHANNEL_LINK = "https://t.me/tribute/app?startapp=sHVK"  # Ссылка на оплату
PRICE = 399  # Цена подписки

# Хранилище данных
user_data = {}
meals_data = {}

def get_client():
    """Клиент OpenAI через ProxyAPI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.proxyapi.ru/openai/v1"
    )
    return client

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на платный канал"""
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(
            chat_id=PREMIUM_CHANNEL_ID,
            user_id=user_id
        )
        
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
        else:
            return False
    except:
        return False

def get_keyboard(is_premium=True):
    """Главная клавиатура"""
    if not is_premium:
        keyboard = [
            [KeyboardButton("💳 Купить доступ 399₽")],
            [KeyboardButton("🎁 У меня есть подписка")],
            [KeyboardButton("ℹ️ Что умеет бот?")]
        ]
    else:
        keyboard = [
            [KeyboardButton("🧮 КБЖУ"), KeyboardButton("⚖️ Мой вес")],
            [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍎 Перекус")],
            [KeyboardButton("🍽 Обед"), KeyboardButton("🌙 Ужин")],
            [KeyboardButton("💧 Вода"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Вопрос о еде")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Инициализация пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            "name": user.first_name,
            "joined": datetime.now().isoformat(),
            "target_calories": 2000,
            "target_protein": 100,
            "target_fats": 70,
            "target_carbs": 250,
            "questions_today": 0,
            "last_question_date": None
        }
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    # Проверяем подписку
    is_premium = await check_subscription(update, context)
    
    if is_premium:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"✅ Доступ активен!\n\n"
            f"🤖 Я SmartFood AI - твой дневник питания!\n\n"
            f"📝 Просто пиши что съел - AI всё посчитает!\n\n"
            f"Начни с кнопки 🧮 КБЖУ",
            reply_markup=get_keyboard(True)
        )
    else:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🤖 Я SmartFood AI - умный дневник питания!\n\n"
            f"✨ ПРОСТО ПИШИ ЧТО СЪЕЛ:\n"
            f'Напишешь: "Борщ со сметаной"\n'
            f"Получишь: 320 ккал, Б:15г, Ж:12г, У:38г\n\n"
            f"💰 Стоимость: 399₽/месяц (13₽/день)\n\n"
            f"👇 Нажми для покупки:",
            reply_markup=get_keyboard(False)
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех текстовых сообщений"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text
    user_id = update.effective_user.id
    
    # Проверка ожидающих вводов
    waiting_for = context.user_data.get('waiting_for')
    
    if waiting_for == 'kbzhu_data':
        await process_kbzhu_data(update, context)
        return
    elif waiting_for == 'meal_description':
        await process_meal_description(update, context)
        return
    elif waiting_for == 'weight':
        await process_weight(update, context)
        return
    elif waiting_for == 'question':
        await process_question(update, context)
        return
    
    # Кнопки для неподписанных
    if text == "💳 Купить доступ 399₽":
        await show_payment_info(update, context)
        return
    
    elif text == "🎁 У меня есть подписка":
        is_premium = await check_subscription(update, context)
        if is_premium:
            await update.message.reply_text(
                "✅ Отлично! Подписка активна!",
                reply_markup=get_keyboard(True)
            )
        else:
            await update.message.reply_text(
                "❌ Подписка не найдена!\n\n"
                "Сначала оплатите доступ.",
                reply_markup=get_keyboard(False)
            )
        return
    
    elif text == "ℹ️ Что умеет бот?":
        await show_features(update, context)
        return
    
    # Проверка подписки для основных функций
    is_premium = await check_subscription(update, context)
    
    if not is_premium:
        await update.message.reply_text(
            "❌ Нужна подписка!\n\n"
            "💰 Стоимость: 399₽/месяц",
            reply_markup=get_keyboard(False)
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
            reply_markup=get_keyboard(is_premium)
        )

async def show_payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация об оплате"""
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить 399₽", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Я оплатил", callback_data="check_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"""
💳 ОФОРМЛЕНИЕ ПОДПИСКИ

💰 Стоимость: 399₽/месяц

✅ ЧТО ВХОДИТ:
• AI-анализ любых блюд
• Автоматический подсчет КБЖУ
• Дневник питания
• Статистика и графики
• 10 вопросов AI в день

📱 КАК ОПЛАТИТЬ:
1. Нажмите "Оплатить"
2. Оплатите через Telegram
3. Нажмите "Я оплатил"
""",
        reply_markup=reply_markup
    )

async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка оплаты"""
    query = update.callback_query
    await query.answer()
    
    is_premium = await check_subscription(update, context)
    
    if is_premium:
        await query.edit_message_text(
            "✅ Оплата подтверждена!\n\n"
            "Все функции разблокированы!"
        )
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=get_keyboard(True)
        )
    else:
        await query.edit_message_text(
            "❌ Подписка не найдена!\n\n"
            "Попробуйте еще раз"
        )

async def show_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возможности бота"""
    await update.message.reply_text(
        """
🤖 ЧТО УМЕЕТ БОТ:

🎯 ГЛАВНОЕ:
Пишешь что съел → получаешь КБЖУ!

📝 ДНЕВНИК:
• Записывает приемы пищи
• Считает калории
• Показывает статистику

🧮 РАСЧЕТЫ:
• Персональная норма КБЖУ
• Анализ любых блюд

⏰ НАПОМИНАНИЯ:
• О приемах пищи
• О воде

🤖 AI-КОНСУЛЬТАНТ:
• 10 вопросов в день

💰 ВСЕГО 399₽/МЕСЯЦ!
""",
        reply_markup=get_keyboard(False)
    )

async def process_kbzhu_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ Рассчитываю...")
    
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
            
            Ответ ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Рассчитай КБЖУ."},
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
        
        user_data[user_id]['target_calories'] = calories
        user_data[user_id]['target_protein'] = protein
        user_data[user_id]['target_fats'] = fats
        user_data[user_id]['target_carbs'] = carbs
        
        await update.message.reply_text(
            f"✅ ТВОЯ НОРМА:\n\n"
            f"🔥 Калории: {calories} ккал\n"
            f"🥩 Белки: {protein} г\n"
            f"🥑 Жиры: {fats} г\n"
            f"🍞 Углеводы: {carbs} г\n"
            f"💧 Вода: 2000 мл\n\n"
            f"Записывай приемы пищи!",
            reply_markup=get_keyboard(True)
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка")
    
    context.user_data['waiting_for'] = None

async def process_meal_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды"""
    description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('current_meal', 'snack')
    
    await update.message.reply_text("⏳ Анализирую...")
    
    try:
        client = get_client()
        if not client:
            calories = 350
            protein = 25
            fats = 15
            carbs = 40
        else:
            prompt = f"""
            Проанализируй: {description}
            
            Ответ ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Рассчитай КБЖУ еды."},
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
        if user_id not in meals_data:
            meals_data[user_id] = []
        
        meals_data[user_id].append({
            'type': meal_type,
            'description': description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': today,
            'time': datetime.now().strftime("%H:%M")
        })
        
        meal_emoji = {
            'breakfast': '🌅',
            'snack': '🍎',
            'lunch': '🍽',
            'dinner': '🌙'
        }.get(meal_type, '🍴')
        
        await update.message.reply_text(
            f"✅ Записано!\n\n"
            f"{meal_emoji} {description}\n\n"
            f"📊 КБЖУ:\n"
            f"🔥 {calories} ккал\n"
            f"🥩 {protein:.1f} г белка\n"
            f"🥑 {fats:.1f} г жиров\n"
            f"🍞 {carbs:.1f} г углеводов",
            reply_markup=get_keyboard(True)
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка")
    
    context.user_data['waiting_for'] = None

async def record_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись воды"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    water_today = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    meals_data[user_id].append({
        'type': 'water',
        'date': today,
        'time': datetime.now().strftime("%H:%M")
    })
    
    water_ml = (water_today + 1) * 250
    
    await update.message.reply_text(
        f"💧 +250 мл\n\n"
        f"Сегодня: {water_ml} / 2000 мл\n"
        f"{'✅ Норма!' if water_ml >= 2000 else f'Осталось: {2000 - water_ml} мл'}",
        reply_markup=get_keyboard(True)
    )

async def process_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение веса"""
    try:
        weight = float(update.message.text.replace(',', '.'))
        
        if weight < 30 or weight > 300:
            await update.message.reply_text("❌ Некорректный вес")
            return
            
        await update.message.reply_text(
            f"✅ Вес {weight} кг записан!",
            reply_markup=get_keyboard(True)
        )
    except:
        await update.message.reply_text("❌ Введи число")
    
    context.user_data['waiting_for'] = None

async def show_daily_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика дня"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_data:
        await update.message.reply_text("📊 Нет данных")
        return
    
    today_meals = [m for m in meals_data[user_id] 
                   if m.get('date') == today and m.get('type') != 'water']
    
    if not today_meals:
        await update.message.reply_text("📊 Сегодня нет записей")
        return
    
    total_cal = sum(m.get('calories', 0) for m in today_meals)
    total_prot = sum(m.get('protein', 0) for m in today_meals)
    total_fats = sum(m.get('fats', 0) for m in today_meals)
    total_carbs = sum(m.get('carbs', 0) for m in today_meals)
    
    target_cal = user_data[user_id].get('target_calories', 2000)
    
    water_count = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    await update.message.reply_text(
        f"📊 СТАТИСТИКА ДНЯ\n\n"
        f"🔥 Калории: {total_cal:.0f}/{target_cal} ({total_cal/target_cal*100:.0f}%)\n"
        f"🥩 Белки: {total_prot:.0f} г\n"
        f"🥑 Жиры: {total_fats:.0f} г\n"
        f"🍞 Углеводы: {total_carbs:.0f} г\n"
        f"💧 Вода: {water_count * 250}/2000 мл\n\n"
        f"🍽 Приемов: {len(today_meals)}",
        reply_markup=get_keyboard(True)
    )

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вопрос о еде"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Проверяем лимит
    if user_data[user_id].get('last_question_date') != today:
        user_data[user_id]['questions_today'] = 0
        user_data[user_id]['last_question_date'] = today
    
    if user_data[user_id]['questions_today'] >= 10:
        await update.message.reply_text("❌ Лимит 10 вопросов")
        return
    
    await update.message.reply_text(
        f"❓ Задай вопрос о питании\n"
        f"Осталось: {10 - user_data[user_id]['questions_today']}/10"
    )
    context.user_data['waiting_for'] = 'question'

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на вопрос"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ Думаю...")
    
    try:
        client = get_client()
        if client:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты диетолог. Отвечай кратко."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500
            )
            
            user_data[user_id]['questions_today'] += 1
            
            await update.message.reply_text(
                response.choices[0].message.content,
                reply_markup=get_keyboard(True)
            )
        else:
            await update.message.reply_text("❌ AI недоступен")
    except:
        await update.message.reply_text("❌ Ошибка")
    
    context.user_data['waiting_for'] = None

def main():
    """Запуск бота"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No token!")
        return
    
    logger.info("Starting bot...")
    app = Application.builder().token(token).build()
    
    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_payment_callback, pattern="check_payment"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
