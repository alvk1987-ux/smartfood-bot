import os
import logging
import re
from datetime import datetime, timedelta, time
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
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я SmartFood AI — твой персональный нутрициолог!\n\n"
        f"✨ НОВЫЕ ФУНКЦИИ:\n"
        f"📝 Дневник питания — записывайте все приемы пищи\n"
        f"📊 Статистика — анализ за день/неделю/месяц\n"
        f"⏰ Напоминания — не пропустите прием пищи\n\n"
        f"Основные функции:\n"
        f"🧮 Рассчитать КБЖУ\n"
        f"🍱 Составить меню\n"
        f"🍽 Анализ питания\n"
        f"💬 Задать вопрос\n\n"
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
        
        today = datetime.now().strftime("%Y-%m-%d")
        water_count = sum(1 for meal in meals_data[user_id] 
                         if meal['type'] == 'water' and meal['date'] == today)
        
        await query.edit_message_text(
            f"✅ Записано!\n\n"
            f"💧 Сегодня выпито: {water_count * 250} мл\n"
            f"🎯 Рекомендация: 2000 мл/день\n"
            f"{'✅ Норма выполнена!' if water_count >= 8 else f'Осталось: {2000 - water_count * 250} мл'}"
        )
        return ConversationHandler.END
    
    meal_names = {
        'breakfast': '🌅 Завтрак',
        'lunch': '🍽 Обед',
        'dinner': '🌙 Ужин',
        'snack': '🍎 Перекус'
    }
    
    await query.edit_message_text(
        f"{meal_names[meal_type]}\n\n"
        f"Опишите что вы съели:\n\n"
        f"Примеры:\n"
        f"• Овсянка с бананом\n"
        f"• Куриная грудка 150г с рисом\n"
        f"• Греческий салат\n"
    )
    return WAITING_MEAL_RECORD

async def process_meal_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ и сохранение приема пищи"""
    meal_description = update.message.text
    user_id = update.effective_user.id
    meal_type = context.user_data.get('current_meal_type', 'snack')
    
    # Проверка на кнопки
    if meal_description in ["📝 Записать прием пищи", "📊 Моя статистика", "🧮 Рассчитать КБЖУ", 
                            "🍱 Составить меню", "🍽 Анализ питания", "⏰ Напоминания", "💬 Задать вопрос"]:
        return ConversationHandler.END
    
    if meal_description.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI анализирует...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Проанализируй прием пищи: {meal_description}
        
        Ответ СТРОГО в формате:
        КАЛОРИИ: [число]
        БЕЛКИ: [число]
        ЖИРЫ: [число]
        УГЛЕВОДЫ: [число]
        
        СОСТАВ:
        • [продукт] - [грамм]
        
        АНАЛИЗ: [оценка]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Точно рассчитываешь КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        analysis = response.choices[0].message.content
        
        # Парсим числа
        try:
            calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', analysis).group(1))
            protein = float(re.search(r'БЕЛКИ:\s*([\d.]+)', analysis).group(1))
            fats = float(re.search(r'ЖИРЫ:\s*([\d.]+)', analysis).group(1))
            carbs = float(re.search(r'УГЛЕВОДЫ:\s*([\d.]+)', analysis).group(1))
        except:
            calories, protein, fats, carbs = 300, 20, 10, 40
        
        # Сохраняем
        if user_id not in meals_data:
            meals_data[user_id] = []
        
        meals_data[user_id].append({
            'type': meal_type,
            'description': meal_description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': datetime.now().strftime("%Y-%m-%d"),
            'time': datetime.now().strftime("%H:%M")
        })
        
        # Статистика за день
        today = datetime.now().strftime("%Y-%m-%d")
        today_meals = [m for m in meals_data[user_id] if m['date'] == today and m['type'] != 'water']
        
        total_cal = sum(m['calories'] for m in today_meals)
        total_prot = sum(m['protein'] for m in today_meals)
        total_fats = sum(m['fats'] for m in today_meals)
        total_carbs = sum(m['carbs'] for m in today_meals)
        
        response_text = f"""
✅ Записано!

📊 Анализ:
{analysis}

📈 Сегодня:
🔥 Калории: {total_cal:.0f} ккал
🥩 Белки: {total_prot:.1f} г
🥑 Жиры: {total_fats:.1f} г
🍞 Углеводы: {total_carbs:.1f} г

🍽 Приемов пищи: {len(today_meals)}
"""
        
        await update.message.reply_text(response_text, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
    
    return ConversationHandler.END

# === СТАТИСТИКА ===
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики"""
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="stats_today")],
        [InlineKeyboardButton("📊 За неделю", callback_data="stats_week")],
        [InlineKeyboardButton("📈 За месяц", callback_data="stats_month")]
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
        await query.edit_message_text("📊 Нет данных")
        return
    
    today = datetime.now().date()
    
    if period == "today":
        target_date = today.strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] == target_date and m['type'] != 'water']
        water = sum(1 for m in meals_data[user_id] if m['date'] == target_date and m['type'] == 'water')
        period_name = f"Сегодня"
    elif period == "week":
        week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] >= week_ago and m['type'] != 'water']
        period_name = "За неделю"
        water = 0
    else:
        month_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        meals = [m for m in meals_data[user_id] if m['date'] >= month_ago and m['type'] != 'water']
        period_name = "За месяц"
        water = 0
    
    if not meals:
        await query.edit_message_text(f"📊 {period_name}: нет данных")
        return
    
    total_cal = sum(m['calories'] for m in meals)
    total_prot = sum(m['protein'] for m in meals)
    total_fats = sum(m['fats'] for m in meals)
    total_carbs = sum(m['carbs'] for m in meals)
    
    days_count = len(set(m['date'] for m in meals))
    avg_cal = total_cal / days_count if days_count > 0 else 0
    
    response = f"""
📊 {period_name}

📅 Дней: {days_count}
🍽 Приемов: {len(meals)}
{'💧 Воды: ' + str(water * 250) + ' мл' if water > 0 else ''}

📈 Всего:
🔥 {total_cal:.0f} ккал
🥩 {total_prot:.0f} г белка
🥑 {total_fats:.0f} г жиров
🍞 {total_carbs:.0f} г углеводов

📊 В день:
🔥 {avg_cal:.0f} ккал
"""
    
    await query.edit_message_text(response)

# === НАПОМИНАНИЯ ===
async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка напоминаний"""
    keyboard = [
        [InlineKeyboardButton("🌅 Завтрак 8:00", callback_data="remind_breakfast")],
        [InlineKeyboardButton("🍽 Обед 13:00", callback_data="remind_lunch")],
        [InlineKeyboardButton("🌙 Ужин 19:00", callback_data="remind_dinner")],
        [InlineKeyboardButton("❌ Отключить все", callback_data="remind_off")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⏰ Настройка напоминаний:",
        reply_markup=reply_markup
    )

async def toggle_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение напоминания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data.replace("remind_", "")
    
    if action == "off":
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()
        await query.edit_message_text("✅ Напоминания отключены")
    else:
        if action == "breakfast":
            context.job_queue.run_daily(
                send_reminder,
                time(hour=8, minute=0),
                data={'user_id': user_id, 'type': 'breakfast'},
                name=str(user_id)
            )
        elif action == "lunch":
            context.job_queue.run_daily(
                send_reminder,
                time(hour=13, minute=0),
                data={'user_id': user_id, 'type': 'lunch'},
                name=str(user_id)
            )
        elif action == "dinner":
            context.job_queue.run_daily(
                send_reminder,
                time(hour=19, minute=0),
                data={'user_id': user_id, 'type': 'dinner'},
                name=str(user_id)
            )
        
        await query.edit_message_text(f"✅ Напоминание '{action}' включено!")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминания"""
    user_id = context.job.data['user_id']
    reminder_type = context.job.data['type']
    
    messages = {
        'breakfast': '🌅 Время завтрака!',
        'lunch': '🍽 Время обеда!',
        'dinner': '🌙 Время ужина!'
    }
    
    await context.bot.send_message(
        chat_id=user_id,
        text=messages.get(reminder_type, 'Напоминание!'),
        reply_markup=get_main_keyboard()
    )

# === РАСЧЕТ КБЖУ ===
async def calculate_kbzhu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало расчета КБЖУ"""
    await update.message.reply_text(
        "🧮 Для расчета КБЖУ напишите через запятую:\n\n"
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
    """Расчет КБЖУ"""
    user_input = update.message.text
    user_id = update.effective_user.id
    
    if user_input.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Рассчитываю...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Рассчитай КБЖУ для: {user_input}
        
        Формула Миффлина-Сан Жеора.
        
        Ответ:
        🎯 НОРМА:
        🔥 Калории: [число] ккал
        🥩 Белки: [число] г
        🥑 Жиры: [число] г
        🍞 Углеводы: [число] г
        💧 Вода: [число] л
        
        💡 СОВЕТЫ:
        [3 совета]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Точно рассчитываешь КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['kbzhu'] = result
        
        await update.message.reply_text(result, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
    
    return ConversationHandler.END

# === СОСТАВЛЕНИЕ МЕНЮ ===
async def menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало составления меню"""
    await update.message.reply_text(
        "🍱 Составлю меню!\n\n"
        "Напишите:\n"
        "• Сколько дней?\n"
        "• Что любите?\n"
        "• Что НЕ едите?\n\n"
        "📝 Пример:\n"
        "3 дня, люблю курицу, не ем свинину"
    )
    return WAITING_MENU_PREFERENCES

async def process_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Составление меню"""
    preferences = update.message.text
    
    if preferences.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Составляю...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Составь меню: {preferences}
        
        📅 ДЕНЬ 1
        🌅 ЗАВТРАК:
        • [блюдо]
        🍽 ОБЕД:
        • [блюдо]
        🌙 УЖИН:
        • [блюдо]
        
        [повтори для остальных дней]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты диетолог."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2500,
            temperature=0.5
        )
        
        await update.message.reply_text(response.choices[0].message.content, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
    
    return ConversationHandler.END

# === АНАЛИЗ ПИТАНИЯ ===
async def analyze_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало анализа"""
    await update.message.reply_text(
        "🍽 Опишите блюдо:\n\n"
        "Например:\n"
        "• Борщ со сметаной\n"
        "• Цезарь с курицей"
    )
    return WAITING_FOOD_INFO

async def process_food_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды"""
    food = update.message.text
    
    if food.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Анализирую...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Анализ: {food}
        
        📊 КБЖУ:
        🔥 Калории: [число]
        🥩 Белки: [г]
        🥑 Жиры: [г]
        🍞 Углеводы: [г]
        
        ⚖️ Оценка: [из 10]
        💡 Рекомендации: [когда есть]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        await update.message.reply_text(response.choices[0].message.content, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
    
    return ConversationHandler.END

# === ВОПРОСЫ ===
async def ask_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало вопроса"""
    await update.message.reply_text(
        "💬 Задайте вопрос о питании:"
    )
    return WAITING_AI_QUESTION

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на вопрос"""
    question = update.message.text
    
    if question in ["📝 Записать прием пищи", "📊 Моя статистика", "🧮 Рассчитать КБЖУ", 
                    "🍱 Составить меню", "🍽 Анализ питания", "⏰ Напоминания", "💬 Задать вопрос"]:
        return ConversationHandler.END
    
    if question.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Думаю...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог."},
                {"role": "user", "content": question}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        await update.message.reply_text(
            response.choices[0].message.content,
            reply_markup=get_main_keyboard()
        )
        return WAITING_AI_QUESTION
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    await update.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    """Запуск бота"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No token!")
        return
    
    app = Application.builder().token(token).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    
    # Обработчики inline кнопок
    app.add_handler(CallbackQueryHandler(meal_type_selected, pattern="^meal_"))
    app.add_handler(CallbackQueryHandler(show_stats_period, pattern="^stats_"))
    app.add_handler(CallbackQueryHandler(toggle_reminder, pattern="^remind_"))
    
    # Обработчики кнопок клавиатуры
    app.add_handler(MessageHandler(filters.Regex("^📝 Записать прием пищи$"), record_meal_start))
    app.add_handler(MessageHandler(filters.Regex("^📊 Моя статистика$"), show_statistics))
    app.add_handler(MessageHandler(filters.Regex("^⏰ Напоминания$"), setup_reminders))
    
    # Обработчики с состояниями
    meal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(meal_type_selected, pattern="^meal_")],
        states={
            WAITING_MEAL_RECORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_meal_record)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    kbzhu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧮 Рассчитать КБЖУ$"), calculate_kbzhu_start)],
        states={
            WAITING_KBZHU_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_kbzhu)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    menu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍱 Составить меню$"), menu_start)],
        states={
            WAITING_MENU_PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_menu)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    food_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽 Анализ питания$"), analyze_food_start)],
        states={
            WAITING_FOOD_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_food_analysis)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    question_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 Задать вопрос$"), ask_question_start)],
        states={
            WAITING_AI_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_question)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(meal_conv)
    app.add_handler(kbzhu_conv)
    app.add_handler(menu_conv)
    app.add_handler(food_conv)
    app.add_handler(question_conv)
    
    logger.info("Bot started!")
    
