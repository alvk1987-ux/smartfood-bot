import os
import logging
import json
import re
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных в памяти
user_data = {}
meals_data = {}

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

def get_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍽 Обед")],
        [KeyboardButton("🌙 Ужин"), KeyboardButton("🍎 Перекус")],
        [KeyboardButton("💧 Выпил воду"), KeyboardButton("⚖️ Мой вес")],
        [KeyboardButton("📊 Статистика дня"), KeyboardButton("❓ Вопрос AI")],
        [KeyboardButton("🧮 Рассчитать КБЖУ"), KeyboardButton("ℹ️ Помощь")]
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
            "target_calories": 2000,
            "target_protein": 100,
            "target_fats": 70,
            "target_carbs": 250,
            "weight_history": [],
            "questions_today": 0,
            "last_question_date": None
        }
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    # Устанавливаем напоминания
    setup_reminders(context, int(user_id))
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я твой дневник питания с AI!\n\n"
        f"📋 Что умею:\n"
        f"• Рассчитываю твою норму КБЖУ\n"
        f"• Записываю все приемы пищи\n"
        f"• Считаю калории и БЖУ автоматически\n"
        f"• Отправляю итоги дня в 21:00\n"
        f"• Напоминаю про еду и воду\n"
        f"• Отвечаю на вопросы (10 в день)\n\n"
        f"🧮 Начни с расчета КБЖУ!",
        reply_markup=get_keyboard()
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех кнопок"""
    text = update.message.text
    user_id = str(update.effective_user.id)
    
    # Если ждем ввода данных
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
    
    # Обработка кнопок
    if text == "🧮 Рассчитать КБЖУ":
        await update.message.reply_text(
            "🧮 Напиши одним сообщением:\n\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 Пример:\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть"
        )
        context.user_data['waiting_for'] = 'kbzhu_data'
    
    elif text in ["🌅 Завтрак", "🍽 Обед", "🌙 Ужин", "🍎 Перекус"]:
        meal_types = {"🌅 Завтрак": "breakfast", "🍽 Обед": "lunch", 
                     "🌙 Ужин": "dinner", "🍎 Перекус": "snack"}
        context.user_data['current_meal'] = meal_types[text]
        await update.message.reply_text(
            f"{text}\n\n"
            f"📝 Напиши что съел(а) и сколько грамм:\n\n"
            f"Примеры:\n"
            f"• Овсянка 100г, банан 150г\n"
            f"• Куриная грудка 150г, рис 100г\n"
            f"• Творог 200г, яблоко 100г"
        )
        context.user_data['waiting_for'] = 'meal_description'
    
    elif text == "💧 Выпил воду":
        await record_water(update, context)
    
    elif text == "⚖️ Мой вес":
        await update.message.reply_text("⚖️ Введи свой вес (кг):")
        context.user_data['waiting_for'] = 'weight'
    
    elif text == "📊 Статистика дня":
        await show_daily_stats(update, context)
    
    elif text == "❓ Вопрос AI":
        await ask_question(update, context)
    
    elif text == "ℹ️ Помощь":
        await show_help(update, context)
    
    else:
        await update.message.reply_text(
            "Используй кнопки меню 👇",
            reply_markup=get_keyboard()
        )

async def process_kbzhu_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ через AI"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI рассчитывает твою норму...")
    
    try:
        client = get_client()
        if not client:
            await update.message.reply_text("❌ API ключ не настроен")
            context.user_data['waiting_for'] = None
            return
        
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
        
        # Парсим числа
        try:
            calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', result).group(1))
            protein = int(re.search(r'БЕЛКИ:\s*(\d+)', result).group(1))
            fats = int(re.search(r'ЖИРЫ:\s*(\d+)', result).group(1))
            carbs = int(re.search(r'УГЛЕВОДЫ:\s*(\d+)', result).group(1))
            
            user_data[user_id]['target_calories'] = calories
            user_data[user_id]['target_protein'] = protein
            user_data[user_id]['target_fats'] = fats
            user_data[user_id]['target_carbs'] = carbs
            
            await update.message.reply_text(
                f"✅ ТВОЯ НОРМА:\n\n"
                f"🔥 Калории: {calories} ккал/день\n"
                f"🥩 Белки: {protein} г/день\n"
                f"🥑 Жиры: {fats} г/день\n"
                f"🍞 Углеводы: {carbs} г/день\n"
                f"💧 Вода: 2000 мл/день\n\n"
                f"📝 Теперь записывай приемы пищи!",
                reply_markup=get_keyboard()
            )
        except:
            await update.message.reply_text("❌ Не удалось рассчитать. Попробуй еще раз")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка AI")
    
    context.user_data['waiting_for'] = None

async def process_meal_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ приема пищи через AI"""
    description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('current_meal', 'snack')
    
    await update.message.reply_text("⏳ AI анализирует КБЖУ...")
    
    try:
        client = get_client()
        if not client:
            # Если нет AI, используем примерные значения
            calories, protein, fats, carbs = 350, 25, 15, 40
        else:
            prompt = f"""
            Проанализируй: {description}
            
            Рассчитай КБЖУ. Ответ ТОЛЬКО числа:
            КАЛОРИИ: [число]
            БЕЛКИ: [число]
            ЖИРЫ: [число]
            УГЛЕВОДЫ: [число]
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Рассчитай КБЖУ продуктов точно."},
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
                calories, protein, fats, carbs = 350, 25, 15, 40
        
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
            'breakfast': '🌅 Завтрак',
            'lunch': '🍽 Обед',
            'dinner': '🌙 Ужин',
            'snack': '🍎 Перекус'
        }.get(meal_type, '🍴')
        
        await update.message.reply_text(
            f"✅ {meal_emoji} записан!\n\n"
            f"📊 Пищевая ценность:\n"
            f"🔥 {calories} ккал\n"
            f"🥩 {protein:.1f} г белка\n"
            f"🥑 {fats:.1f} г жиров\n"
            f"🍞 {carbs:.1f} г углеводов",
            reply_markup=get_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_keyboard())
    
    context.user_data['waiting_for'] = None

async def record_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись воды"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    # Считаем воду за сегодня
    water_today = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    meals_data[user_id].append({
        'type': 'water',
        'date': today,
        'time': datetime.now().strftime("%H:%M")
    })
    
    water_ml = (water_today + 1) * 250
    
    await update.message.reply_text(
        f"💧 Записано!\n\n"
        f"Сегодня: {water_ml} мл / 2000 мл\n"
        f"{'✅ Норма выполнена!' if water_ml >= 2000 else f'Осталось: {2000 - water_ml} мл'}",
        reply_markup=get_keyboard()
    )

async def process_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка веса"""
    try:
        weight = float(update.message.text.replace(',', '.'))
        user_id = str(update.effective_user.id)
        
        if 'weight_history' not in user_data[user_id]:
            user_data[user_id]['weight_history'] = []
        
        user_data[user_id]['weight_history'].append({
            'weight': weight,
            'date': datetime.now().strftime("%Y-%m-%d")
        })
        
        await update.message.reply_text(
            f"✅ Вес записан: {weight} кг",
            reply_markup=get_keyboard()
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
    
    target_cal = user_data[user_id]['target_calories']
    water_count = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    report = f"""
📊 СТАТИСТИКА ДНЯ

📈 Потреблено / Цель:
🔥 {total_cal:.0f} / {target_cal} ккал ({total_cal/target_cal*100:.0f}%)
🥩 {total_prot:.0f} г белка
🥑 {total_fats:.0f} г жиров
🍞 {total_carbs:.0f} г углеводов
💧 {water_count * 250} / 2000 мл воды

🍽 Приемов пищи: {len(today_meals)}
"""
    
    await update.message.reply_text(report, reply_markup=get_keyboard())

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вопрос к AI"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Проверяем лимит
    if user_data[user_id].get('last_question_date') != today:
        user_data[user_id]['questions_today'] = 0
        user_data[user_id]['last_question_date'] = today
    
    if user_data[user_id]['questions_today'] >= 10:
        await update.message.reply_text("❌ Лимит 10 вопросов в день")
        return
    
    await update.message.reply_text(
        f"❓ Задай вопрос о питании\n"
        f"Осталось: {10 - user_data[user_id]['questions_today']}/10"
    )
    context.user_data['waiting_for'] = 'question'

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ AI на вопрос"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI думает...")
    
    try:
        client = get_client()
        if not client:
            await update.message.reply_text("❌ API не настроен")
        else:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты диетолог. Отвечай кратко."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            user_data[user_id]['questions_today'] += 1
            
            await update.message.reply_text(
                response.choices[0].message.content,
                reply_markup=get_keyboard()
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка AI")
    
    context.user_data['waiting_for'] = None

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = """
ℹ️ КАК ПОЛЬЗОВАТЬСЯ:

1️⃣ Рассчитай КБЖУ - твоя норма
2️⃣ Записывай приемы пищи
3️⃣ Пей воду - отмечай
4️⃣ Взвешивайся по пятницам
5️⃣ Смотри статистику дня
6️⃣ Задавай вопросы AI (10/день)

⏰ Напоминания:
• 8:00 - Завтрак
• 13:00 - Обед
• 19:00 - Ужин
• 21:00 - Итоги дня
"""
    await update.message.reply_text(help_text, reply_markup=get_keyboard())

# === НАПОМИНАНИЯ ===
def setup_reminders(context, user_id):
    """Установка напоминаний"""
    job_queue = context.job_queue
    
    # Напоминания о еде
    job_queue.run_daily(
        lambda c: c.bot.send_message(user_id, "🌅 Время завтрака! Не забудь записать"),
        time(hour=8, minute=0),
        name=f"breakfast_{user_id}"
    )
    
    job_queue.run_daily(
        lambda c: c.bot.send_message(user_id, "🍽 Время обеда! Запиши что съел(а)"),
        time(hour=13, minute=0),
        name=f"lunch_{user_id}"
    )
    
    job_queue.run_daily(
        lambda c: c.bot.send_message(user_id, "🌙 Время ужина! Не забудь записать"),
        time(hour=19, minute=0),
        name=f"dinner_{user_id}"
    )
    
    # Напоминания о воде
    job_queue.run_daily(
        lambda c: c.bot.send_message(user_id, "💧 Выпей стакан воды!"),
        time(hour=10, minute=0),
        name=f"water1_{user_id}"
    )
    
    job_queue.run_daily(
        lambda c: c.bot.send_message(user_id, "💧 Время пить воду!"),
        time(hour=15, minute=0),
        name=f"water2_{user_id}"
    )
    
    # Итоги дня
    job_queue.run_daily(
        lambda c: send_daily_report(c, user_id),
        time(hour=21, minute=0),
        name=f"report_{user_id}"
    )

async def send_daily_report(context, user_id):
    """Отправка итогов дня"""
    user_id = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_data:
        return
    
    today_meals = [m for m in meals_data[user_id] 
                   if m.get('date') == today and m.get('type') != 'water']
    
    if not today_meals:
        await context.bot.send_message(
            int(user_id),
            "📊 Сегодня нет записей о питании"
        )
        return
    
    total_cal = sum(m.get('calories', 0) for m in today_meals)
    total_prot = sum(m.get('protein', 0) for m in today_meals)
    
    target_cal = user_data.get(user_id, {}).get('target_calories', 2000)
    
    await context.bot.send_message(
        int(user_id),
        f"📊 ИТОГИ ДНЯ\n\n"
        f"🔥 Калории: {total_cal:.0f} / {target_cal} ккал\n"
        f"🥩 Белки: {total_prot:.0f} г\n"
        f"🍽 Приемов пищи: {len(today_meals)}\n\n"
        f"{'✅ Отличный день!' if total_cal < target_cal * 1.1 else '⚠️ Перебор калорий'}"
    )

def main():
    """Главная функция"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("No token!")
        return
    
    logger.info("Starting bot...")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button))
    
    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
