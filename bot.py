import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
WAITING_KBZHU_DATA = 1
WAITING_MENU_PREFERENCES = 2
WAITING_FOOD_INFO = 3
WAITING_AI_QUESTION = 4
WAITING_MEAL_RECORD = 5
SETTING_REMINDERS = 6

# Хранилище данных
user_data = {}
meals_data = {}
reminders_data = {}

def get_client():
    """Клиент OpenAI через ProxyAPI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not found!")
        return None
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.proxyapi.ru/openai/v1"
    )
    logger.info("OpenAI client created successfully")
    return client

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton("📝 Записать прием пищи")],
        [KeyboardButton("📊 Моя статистика")],
        [KeyboardButton("🧮 Рассчитать КБЖУ"), KeyboardButton("🍱 Составить меню")],
        [KeyboardButton("🍽 Анализ питания"), KeyboardButton("⏰ Напоминания")],
        [KeyboardButton("💬 Задать вопрос")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Инициализация данных пользователя
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я SmartFood AI — твой персональный нутрициолог!\n\n"
        f"🆕 НОВЫЕ ФУНКЦИИ:\n"
        f"📝 Дневник питания — записывайте все приемы пищи\n"
        f"📊 Статистика — анализ за день/неделю/месяц\n"
        f"⏰ Напоминания — не пропустите прием пищи\n\n"
        f"Основные функции:\n"
        f"🧮 Рассчитать КБЖУ — точный расчет вашей нормы\n"
        f"🍱 Составить меню — персональный рацион\n"
        f"🍽 Анализ питания — оценка любого блюда\n"
        f"💬 Задать вопрос — консультация по питанию\n\n"
        f"Выберите действие 👇",
        reply_markup=get_main_keyboard()
    )

# === ЗАПИСЬ ПРИЕМА ПИЩИ ===
async def record_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало записи приема пищи"""
    keyboard = [
        [InlineKeyboardButton("🌅 Завтрак", callback_data="meal_breakfast")],
        [InlineKeyboardButton("🍽 Обед", callback_data="meal_lunch")],
        [InlineKeyboardButton("🌙 Ужин", callback_data="meal_dinner")],
        [InlineKeyboardButton("🍎 Перекус", callback_data="meal_snack")],
        [InlineKeyboardButton("💧 Вода (250мл)", callback_data="meal_water")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 Выберите тип приема:",
        reply_markup=reply_markup
    )

async def meal_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа приема пищи"""
    query = update.callback_query
    await query.answer()
    
    meal_type = query.data.replace("meal_", "")
    context.user_data['current_meal_type'] = meal_type
    
    meal_names = {
        'breakfast': '🌅 Завтрак',
        'lunch': '🍽 Обед',
        'dinner': '🌙 Ужин',
        'snack': '🍎 Перекус',
        'water': '💧 Вода'
    }
    
    # Для воды сразу записываем
    if meal_type == 'water':
        user_id = query.from_user.id
        if user_id not in meals_data:
            meals_data[user_id] = []
        
        meals_data[user_id].append({
            'type': 'water',
            'description': 'Стакан воды (250 мл)',
            'calories': 0,
            'protein': 0,
            'fats': 0,
            'carbs': 0,
            'date': datetime.now().strftime("%Y-%m-%d"),
            'time': datetime.now().strftime("%H:%M")
        })
        
        # Считаем воду за день
        today = datetime.now().strftime("%Y-%m-%d")
        water_count = sum(1 for meal in meals_data[user_id] 
                         if meal['type'] == 'water' and meal['date'] == today)
        
        await query.edit_message_text(
            f"✅ Записано!\n\n"
            f"💧 Сегодня выпито: {water_count * 250} мл\n"
            f"🎯 Рекомендация: 2000 мл/день\n"
            f"{'✅ Отлично! Норма выполнена!' if water_count >= 8 else f'Осталось: {2000 - water_count * 250} мл'}"
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        f"{meal_names[meal_type]}\n\n"
        f"Опишите что вы съели:\n\n"
        f"Примеры:\n"
        f"• Овсянка с бананом\n"
        f"• Куриная грудка 150г с рисом\n"
        f"• Греческий салат\n\n"
        f"💡 Чем подробнее — тем точнее расчет!"
    )
    return WAITING_MEAL_RECORD

async def process_meal_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ и сохранение приема пищи"""
    meal_description = update.message.text
    user_id = update.effective_user.id
    meal_type = context.user_data.get('current_meal_type', 'snack')
    
    # Проверка на команды/кнопки
    if meal_description.startswith("/") or meal_description in ["📝 Записать прием пищи", "📊 Моя статистика"]:
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI анализирует ваш прием пищи...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Проанализируй прием пищи: {meal_description}
        
        Рассчитай точно КБЖУ. Ответ СТРОГО в формате:
        КАЛОРИИ: [число]
        БЕЛКИ: [число]
        ЖИРЫ: [число]
        УГЛЕВОДЫ: [число]
        
        СОСТАВ:
        • [продукт] - [грамм]
        
        АНАЛИЗ: [оценка баланса и пользы]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Точно рассчитываешь КБЖУ блюд."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        analysis = response.choices[0].message.content
        
        # Парсим числа из ответа
        try:
            calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', analysis).group(1))
            protein = float(re.search(r'БЕЛКИ:\s*([\d.]+)', analysis).group(1))
            fats = float(re.search(r'ЖИРЫ:\s*([\d.]+)', analysis).group(1))
            carbs = float(re.search(r'УГЛЕВОДЫ:\s*([\d.]+)', analysis).group(1))
        except:
            calories, protein, fats, carbs = 300, 20, 10, 40
        
        # Сохраняем данные
        if user_id not in meals_data:
            meals_data[user_id] = []
        
        meal_entry = {
            'type': meal_type,
            'description': meal_description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': datetime.now().strftime("%Y-%m-%d"),
            'time': datetime.now().strftime("%H:%M")
        }
        
        meals_data[user_id].append(meal_entry)
        
        # Статистика за день
        today = datetime.now().strftime("%Y-%m-%d")
        today_meals = [m for m in meals_data[user_id] if m['date'] == today and m['type'] != 'water']
        
        total_cal = sum(m['calories'] for m in today_meals)
        total_prot = sum(m['protein'] for m in today_meals)
        total_fats = sum(m['fats'] for m in today_meals)
        total_carbs = sum(m['carbs'] for m in today_meals)
        
        # Целевые КБЖУ
        target_cal = user_data.get(user_id, {}).get('target_calories', 2000)
        
        response_text = f"""
✅ Прием пищи записан!

📊 Анализ:
{analysis}

📈 Итого за сегодня:
🔥 Калории: {total_cal:.0f} / {target_cal} ккал ({total_cal/target_cal*100:.0f}%)
🥩 Белки: {total_prot:.1f} г
🥑 Жиры: {total_fats:.1f} г
🍞 Углеводы: {total_carbs:.1f} г

🍽 Приемов пищи сегодня: {len(today_meals)}
"""
        
        await update.message.reply_text(response_text, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error recording meal: {e}")
        await update.message.reply_text(
            "❌ Ошибка при анализе. Попробуйте описать подробнее.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === СТАТИСТИКА ===
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики питания"""
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="stats_today")],
        [InlineKeyboardButton("📊 За неделю", callback_data="stats_week")],
        [InlineKeyboardButton("📈 За месяц", callback_data="stats_month")],
        [InlineKeyboardButton("🍽 Все приемы", callback_data="stats_meals")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📊 Выберите период:",
        reply_markup=reply_markup
    )

async def show_stats_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики за период"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    period = query.data.replace("stats_", "")
    
    if user_id not in meals_data or not meals_data[user_id]:
        await query.edit_message_text(
            "📊 Нет данных\n\nНачните записывать приемы пищи!"
        )
        return
    
    today = datetime.now().date()
    
    if period == "today":
        target_date = today.strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] == target_date and m['type'] != 'water']
        water = sum(1 for m in meals_data[user_id] if m['date'] == target_date and m['type'] == 'water')
        period_name = f"Сегодня ({today.strftime('%d.%m')})"
    elif period == "week":
        week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] >= week_ago and m['type'] != 'water']
        period_name = "За неделю"
        water = 0
    elif period == "month":
        month_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] >= month_ago and m['type'] != 'water']
        period_name = "За месяц"
        water = 0
    else:
        # Показываем последние приемы
        meals = [m for m in meals_data[user_id] if m['type'] != 'water'][-10:]
        meals_text = "🍽 Последние приемы пищи:\n\n"
        for meal in reversed(meals):
            meal_emoji = {'breakfast': '🌅', 'lunch': '🍽', 'dinner': '🌙', 'snack': '🍎'}.get(meal['type'], '🍴')
            meals_text += f"{meal_emoji} {meal['date']} {meal.get('time', '')}\n"
            meals_text += f"📝 {meal['description'][:30]}...\n"
            meals_text += f"📊 {meal['calories']} ккал\n\n"
        
        await query.edit_message_text(meals_text[:4000])
        return
    
    if not meals:
        await query.edit_message_text(f"📊 {period_name}: нет данных")
        return
    
    # Расчет статистики
    total_cal = sum(m['calories'] for m in meals)
    total_prot = sum(m['protein'] for m in meals)
    total_fats = sum(m['fats'] for m in meals)
    total_carbs = sum(m['carbs'] for m in meals)
    
    # Группировка по типам
    meal_types = {}
    for meal in meals:
        meal_types[meal['type']] = meal_types.get(meal['type'], 0) + 1
    
    days_count = len(set(m['date'] for m in meals))
    avg_cal = total_cal / days_count if days_count > 0 else 0
    
    response = f"""
📊 Статистика: {period_name}

📅 Дней с записями: {days_count}
🍽 Всего приемов пищи: {len(meals)}
{'💧 Воды выпито: ' + str(water * 250) + ' мл' if water > 0 else ''}

📈 Всего потреблено:
🔥 Калории: {total_cal:.0f} ккал
🥩 Белки: {total_prot:.0f} г
🥑 Жиры: {total_fats:.0f} г
🍞 Углеводы: {total_carbs:.0f} г

📊 В среднем в день:
🔥 Калории: {avg_cal:.0f} ккал
🥩 Белки: {total_prot/days_count if days_count else 0:.0f} г

📝 Типы приемов:
🌅 Завтраков: {meal_types.get('breakfast', 0)}
🍽 Обедов: {meal_types.get('lunch', 0)}
🌙 Ужинов: {meal_types.get('dinner', 0)}
🍎 Перекусов: {meal_types.get('snack', 0)}
"""
    
    await query.edit_message_text(response)

# === НАПОМИНАНИЯ ===
async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка напоминаний"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🌅 Завтрак в 8:00", callback_data="remind_breakfast")],
        [InlineKeyboardButton("🍽 Обед в 13:00", callback_data="remind_lunch")],
        [InlineKeyboardButton("🌙 Ужин в 19:00", callback_data="remind_dinner")],
        [InlineKeyboardButton("📊 Итоги дня в 22:00", callback_data="remind_summary")],
        [InlineKeyboardButton("❌ Отключить все", callback_data="remind_off")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current = reminders_data.get(user_id, {})
    status = "✅ Активные:\n" + "\n".join([k for k, v in current.items() if v]) if current else "Не настроены"
    
    await update.message.reply_text(
        f"⏰ Напоминания\n\n{status}\n\nВыберите:",
        reply_markup=reply_markup
    )

async def toggle_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение/выключение напоминания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data.replace("remind_", "")
    
    if user_id not in reminders_data:
        reminders_data[user_id] = {}
    
    if action == "off":
        reminders_data[user_id] = {}
        # Отменяем все задания
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()
        await query.edit_message_text("✅ Все напоминания отключены")
    else:
        reminders_data[user_id][action] = True
        
        # Планируем напоминание
        from datetime import time
        
        if action == "breakfast":
            context.job_queue.run_daily(
                send_reminder,
                time=time(hour=8, minute=0),
                data={'user_id': user_id, 'type': 'breakfast'},
                name=str(user_id)
            )
        elif action == "lunch":
            context.job_queue.run_daily(
                send_reminder,
                time=time(hour=13, minute=0),
                data={'user_id': user_id, 'type': 'lunch'},
                name=str(user_id)
            )
        elif action == "dinner":
            context.job_queue.run_daily(
                send_reminder,
                time=time(hour=19, minute=0),
                data={'user_id': user_id, 'type': 'dinner'},
                name=str(user_id)
            )
        elif action == "summary":
            context.job_queue.run_daily(
                send_daily_summary,
                time=time(hour=22, minute=0),
                data={'user_id': user_id},
                name=str(user_id)
            )
        
        await query.edit_message_text(f"✅ Напоминание '{action}' включено!")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминания"""
    user_id = context.job.data['user_id']
    reminder_type = context.job.data['type']
    
    messages = {
        'breakfast': '🌅 Доброе утро! Время завтрака!\n\nНе забудьте записать прием пищи 📝',
        'lunch': '🍽 Время обеда!\n\nЗапишите что съели 📝',
        'dinner': '🌙 Время ужина!\n\nНе забудьте записать 📝'
    }
    
    await context.bot.send_message(
        chat_id=user_id,
        text=messages.get(reminder_type, 'Напоминание!'),
        reply_markup=get_main_keyboard()
    )

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневный отчет"""
    user_id = context.job.data['user_id']
    
    if user_id not in meals_data:
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    today_meals = [m for m in meals_data[user_id] if m['date'] == today and m['type'] != 'water']
    water = sum(1 for m in meals_data[user_id] if m['date'] == today and m['type'] == 'water')
    
    if not today_meals:
        await context.bot.send_message(
            chat_id=user_id,
            text="📊 Сегодня нет записей о питании.\n\nНе забудьте записывать приемы пищи завтра!"
        )
        return
    
    total_cal = sum(m['calories'] for m in today_meals)
    total_prot = sum(m['protein'] for m in today_meals)
    total_fats = sum(m['fats'] for m in today_meals)
    total_carbs = sum(m['carbs'] for m in today_meals)
    
    summary = f"""
📊 Итоги дня ({datetime.now().strftime('%d.%m.%Y')})

🍽 Приемов пищи: {len(today_meals)}
💧 Воды: {water * 250} мл

📈 Потреблено:
🔥 Калории: {total_cal:.0f} ккал
🥩 Белки: {total_prot:.0f} г
🥑 Жиры: {total_fats:.0f} г
🍞 Углеводы: {total_carbs:.0f} г

{'✅ Отличный день!' if total_cal < 2200 else '⚠️ Много калорий!'}

💤 Спокойной ночи!
"""
    
    await context.bot.send_message(chat_id=user_id, text=summary)

# === РАСЧЕТ КБЖУ (оставляем старую функцию) ===
async def calculate_kbzhu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало расчета КБЖУ"""
    await update.message.reply_text(
        "🧮 Для расчета КБЖУ ответьте одним сообщением:\n\n"
        "Напишите через запятую:\n"
        "• Пол (М/Ж)\n"
        "• Возраст\n"
        "• Вес (кг)\n"
        "• Рост (см)\n"
        "• Активность (низкая/средняя/высокая)\n"
        "• Цель (похудеть/поддержать/набрать)\n\n"
        "📝 Пример:\n"
        "Ж, 25, 60, 170, средняя, похудеть"
    )
    return WAITING_KBZHU_DATA

async def process_kbzhu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ через AI"""
    user_input = update.message.text
    user_id = update.effective_user.id
    
    if user_input.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI рассчитывает ваши персональные КБЖУ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Рассчитай КБЖУ для человека: {user_input}
        
        Используй формулу Миффлина-Сан Жеора.
        
        ОБЯЗАТЕЛЬНО укажи:
        
        🎯 ИТОГОВАЯ НОРМА:
        🔥 Калории: [ЧИСЛО] ккал/день
        🥩 Белки: [ЧИСЛО] г/день
        🥑 Жиры: [ЧИСЛО] г/день
        🍞 Углеводы: [ЧИСЛО] г/день
        💧 Вода: [ЧИСЛО] л/день
        
        📱 РАСПРЕДЕЛЕНИЕ:
        Завтрак: [ккал]
        Обед: [ккал]
        Ужин: [ккал]
        Перекусы: [ккал]
        
        💡 СОВЕТЫ:
        [3 персональных совета]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. ВСЕГДА указывай конкретные числа КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        # Сохраняем результат и парсим калории
        if user_id not in user_data:
            user_data[user_id] = {}
        
        user_data[user_id]['kbzhu'] = result
        
        # Пытаемся извлечь целевые калории
        try:
            calories_match = re.search(r'Калории:\s*(\d+)', result)
            if calories_match:
                user_data[user_id]['target_calories'] = int(calories_match.group(1))
        except:
            user_data[user_id]['target_calories'] = 2000
        
        await update.message.reply_text(result, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error in KBZHU: {e}")
        await update.message.reply_text(
            "❌ Ошибка при расчете. Проверьте формат данных.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === СОСТАВЛЕНИЕ МЕНЮ (оставляем старую) ===
async def menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало составления меню"""
    await update.message.reply_text(
        "🍱 Составлю персональное меню!\n\n"
        "Напишите через запятую:\n"
        "• Сколько дней? (1-7)\n"
        "• Что любите?\n"
        "• Что НЕ едите?\n"
        "• Особенности?\n\n"
        "📝 Пример:\n"
        "3 дня, люблю курицу, не ем свинину, обычное питание"
    )
    return WAITING_MENU_PREFERENCES

async def process_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Составление меню через AI"""
    preferences = update.message.text
    user_id = update.effective_user.id
    
    if preferences.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI составляет меню...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        kbzhu_context = ""
        if user_id in user_data and 'kbzhu' in user_data[user_id]:
            kbzhu_context = f"\nИспользуй КБЖУ пользователя:\n{user_data[user_id]['kbzhu']}"
        
        prompt = f"""
        Составь меню: {preferences}
        {kbzhu_context}
        
        Формат:
        
        📅 ДЕНЬ 1
        
        🌅 ЗАВТРАК:
        • [блюдо] - [грамм]
        📊 КБЖУ: [ккал] | Б:[г] | Ж:[г] | У:[г]
        
        🍽 ОБЕД:
        • [блюдо] - [грамм]
        📊 КБЖУ: [данные]
        
        🌙 УЖИН:
        • [блюдо] - [грамм]
        📊 КБЖУ: [данные]
        
        📊 ИТОГО: [сумма]
        
        🛒 СПИСОК ПОКУПОК:
        [продукты]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            
