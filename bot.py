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

# Файлы для хранения данных
DATA_FILE = "user_data.json"
MEALS_FILE = "meals_data.json"

# Загрузка/сохранение данных
def load_data(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_data(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загружаем данные
user_data = load_data(DATA_FILE)
meals_data = load_data(MEALS_FILE)

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
        [KeyboardButton("📊 Статистика дня"), KeyboardButton("❓ Вопрос")],
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
            "created": datetime.now().isoformat(),
            "target_calories": 2000,
            "target_protein": 100,
            "target_fats": 70,
            "target_carbs": 250,
            "weight_history": [],
            "questions_today": 0,
            "last_question_date": None
        }
        save_data(user_data, DATA_FILE)
    
    if user_id not in meals_data:
        meals_data[user_id] = []
        save_data(meals_data, MEALS_FILE)
    
    # Устанавливаем напоминания
    setup_daily_reminders(context, int(user_id))
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я твой дневник питания!\n\n"
        f"📋 Как работаю:\n"
        f"1️⃣ Сначала рассчитай свою норму КБЖУ\n"
        f"2️⃣ Записывай каждый прием пищи\n"
        f"3️⃣ В 21:00 получишь итоги дня\n"
        f"4️⃣ Каждую пятницу напомню взвеситься\n"
        f"5️⃣ 3 раза в день напомню пить воду\n\n"
        f"💡 Можешь задать 10 вопросов в день\n\n"
        f"🧮 Начни с расчета КБЖУ!",
        reply_markup=get_keyboard()
    )

# === РАСЧЕТ КБЖУ ===
async def calculate_kbzhu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет КБЖУ"""
    await update.message.reply_text(
        "🧮 Для расчета КБЖУ напиши одним сообщением:\n\n"
        "Пол, возраст, вес, рост, активность, цель\n\n"
        "📝 Пример:\n"
        "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть\n\n"
        "Жду твои данные..."
    )
    context.user_data['waiting_for'] = 'kbzhu_data'

# === ЗАПИСЬ ПРИЕМОВ ПИЩИ ===
async def record_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись приема пищи"""
    meal_type = update.message.text
    user_id = str(update.effective_user.id)
    
    meal_types = {
        "🌅 Завтрак": "breakfast",
        "🍽 Обед": "lunch",
        "🌙 Ужин": "dinner",
        "🍎 Перекус": "snack"
    }
    
    if meal_type in meal_types:
        context.user_data['current_meal'] = meal_types[meal_type]
        await update.message.reply_text(
            f"{meal_type}\n\n"
            f"📝 Напиши что съел(а) и сколько грамм:\n\n"
            f"Примеры:\n"
            f"• Овсянка 100г, банан 150г, молоко 200мл\n"
            f"• Куриная грудка 150г, рис 100г, салат 200г\n"
            f"• Творог 200г с ягодами 50г\n\n"
            f"Жду список продуктов..."
        )
        context.user_data['waiting_for'] = 'meal_description'

# === ЗАПИСЬ ВОДЫ ===
async def record_water(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись воды"""
    user_id = str(update.effective_user.id)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Добавляем воду
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    # Считаем сколько воды уже выпито
    water_today = sum(1 for meal in meals_data[user_id] 
                     if meal.get('date') == today and meal.get('type') == 'water')
    
    meals_data[user_id].append({
        'type': 'water',
        'date': today,
        'time': datetime.now().strftime("%H:%M")
    })
    save_data(meals_data, MEALS_FILE)
    
    water_ml = (water_today + 1) * 250
    
    await update.message.reply_text(
        f"💧 Записано!\n\n"
        f"Сегодня выпито: {water_ml} мл\n"
        f"Рекомендация: 2000 мл/день\n"
        f"{'✅ Отлично! Норма выполнена!' if water_ml >= 2000 else f'Осталось: {2000 - water_ml} мл'}",
        reply_markup=get_keyboard()
    )

# === ЗАПИСЬ ВЕСА ===
async def record_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запись веса"""
    await update.message.reply_text(
        "⚖️ Введи свой текущий вес (в кг):\n\n"
        "Например: 65.5"
    )
    context.user_data['waiting_for'] = 'weight'

# === СТАТИСТИКА ДНЯ ===
async def show_daily_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики за день"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in meals_data:
        await update.message.reply_text("📊 Нет данных за сегодня")
        return
    
    # Фильтруем приемы пищи за сегодня
    today_meals = [m for m in meals_data[user_id] 
                   if m.get('date') == today and m.get('type') != 'water']
    
    if not today_meals:
        await update.message.reply_text(
            "📊 Сегодня еще нет записей о питании\n\n"
            "Записывай приемы пищи нажимая:\n"
            "🌅 Завтрак / 🍽 Обед / 🌙 Ужин / 🍎 Перекус",
            reply_markup=get_keyboard()
        )
        return
    
    # Подсчет КБЖУ
    total_cal = sum(m.get('calories', 0) for m in today_meals)
    total_prot = sum(m.get('protein', 0) for m in today_meals)
    total_fats = sum(m.get('fats', 0) for m in today_meals)
    total_carbs = sum(m.get('carbs', 0) for m in today_meals)
    
    # Получаем целевые показатели
    targets = user_data.get(user_id, {})
    target_cal = targets.get('target_calories', 2000)
    target_prot = targets.get('target_protein', 100)
    target_fats = targets.get('target_fats', 70)
    target_carbs = targets.get('target_carbs', 250)
    
    # Подсчет воды
    water_count = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    # Формируем отчет
    report = f"""
📊 СТАТИСТИКА ДНЯ ({datetime.now().strftime('%d.%m.%Y')})

🍽 Приемы пищи:
"""
    
    for meal in today_meals:
        meal_emoji = {
            'breakfast': '🌅',
            'lunch': '🍽',
            'dinner': '🌙',
            'snack': '🍎'
        }.get(meal.get('type', ''), '🍴')
        
        report += f"{meal_emoji} {meal.get('time', '')} - {meal.get('description', '')[:30]}...\n"
    
    report += f"""
📈 Потреблено / Цель:
🔥 Калории: {total_cal:.0f} / {target_cal} ккал ({total_cal/target_cal*100:.0f}%)
🥩 Белки: {total_prot:.0f} / {target_prot} г ({total_prot/target_prot*100:.0f}%)
🥑 Жиры: {total_fats:.0f} / {target_fats} г ({total_fats/target_fats*100:.0f}%)
🍞 Углеводы: {total_carbs:.0f} / {target_carbs} г ({total_carbs/target_carbs*100:.0f}%)

💧 Вода: {water_count * 250} / 2000 мл

"""
    
    # Анализ
    if total_cal < target_cal * 0.8:
        report += "⚠️ Мало калорий! Добавь перекус\n"
    elif total_cal > target_cal * 1.1:
        report += "⚠️ Перебор калорий!\n"
    else:
        report += "✅ Отлично! В пределах нормы\n"
    
    if total_prot < target_prot * 0.8:
        report += "⚠️ Мало белка!\n"
    
    if water_count < 6:
        report += "⚠️ Пей больше воды!\n"
    
    await update.message.reply_text(report, reply_markup=get_keyboard())

# === ВОПРОСЫ ===
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вопрос к AI"""
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Проверяем лимит вопросов
    user_info = user_data.get(user_id, {})
    
    if user_info.get('last_question_date') != today:
        user_info['questions_today'] = 0
        user_info['last_question_date'] = today
    
    if user_info['questions_today'] >= 10:
        await update.message.reply_text(
            "❌ Достигнут лимит 10 вопросов в день\n"
            "Попробуй завтра!",
            reply_markup=get_keyboard()
        )
        return
    
    await update.message.reply_text(
        f"❓ Задай вопрос о питании и здоровье\n"
        f"Осталось вопросов: {10 - user_info['questions_today']}/10\n\n"
        f"Жду твой вопрос..."
    )
    context.user_data['waiting_for'] = 'question'

# === ПОМОЩЬ ===
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = """
ℹ️ КАК ПОЛЬЗОВАТЬСЯ БОТОМ:

1️⃣ РАССЧИТАЙ КБЖУ
Нажми "🧮 Рассчитать КБЖУ" и введи свои данные

2️⃣ ЗАПИСЫВАЙ ПРИЕМЫ ПИЩИ
• 🌅 Завтрак - записать завтрак
• 🍽 Обед - записать обед
• 🌙 Ужин - записать ужин
• 🍎 Перекус - записать перекус

Формат: продукт и вес
Пример: Яблоко 200г, творог 150г

3️⃣ ОТМЕЧАЙ ВОДУ
💧 Нажимай каждый раз когда выпил стакан воды (250мл)

4️⃣ СЛЕДИ ЗА ВЕСОМ
⚖️ Записывай вес каждую пятницу

5️⃣ СМОТРИ СТАТИСТИКУ
📊 Проверяй статистику дня

6️⃣ ЗАДАВАЙ ВОПРОСЫ
❓ До 10 вопросов о питании в день

⏰ НАПОМИНАНИЯ:
• 8:00 - Завтрак
• 13:00 - Обед  
• 19:00 - Ужин
• 10:00, 15:00, 18:00 - Вода
• 21:00 - Итоги дня
• Пятница - Взвешивание
"""
    await update.message.reply_text(help_text, reply_markup=get_keyboard())

# === ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    text = update.message.text
    user_id = str(update.effective_user.id)
    waiting_for = context.user_data.get('waiting_for')
    
    # Обработка ожидающих ввода
    if waiting_for == 'kbzhu_data':
        await process_kbzhu_data(update, context)
    elif waiting_for == 'meal_description':
        await process_meal_description(update, context)
    elif waiting_for == 'weight':
        await process_weight(update, context)
    elif waiting_for == 'question':
        await process_question(update, context)
    else:
        # Обработка кнопок
        if text == "🧮 Рассчитать КБЖУ":
            await calculate_kbzhu(update, context)
        elif text in ["🌅 Завтрак", "🍽 Обед", "🌙 Ужин", "🍎 Перекус"]:
            await record_meal(update, context)
        elif text == "💧 Выпил воду":
            await record_water(update, context)
        elif text == "⚖️ Мой вес":
            await record_weight(update, context)
        elif text == "📊 Статистика дня":
            await show_daily_stats(update, context)
        elif text == "❓ Вопрос":
            await ask_question(update, context)
        elif text == "ℹ️ Помощь":
            await show_help(update, context)
        else:
            await update.message.reply_text(
                "Не понимаю команду. Используй кнопки меню 👇",
                reply_markup=get_keyboard()
            )

# === ОБРАБОТКА ДАННЫХ КБЖУ ===
async def process_kbzhu_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных для расчета КБЖУ"""
    user_input = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ Рассчитываю твою норму КБЖУ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Рассчитай точную норму КБЖУ для человека: {user_input}
        
        Используй формулу Миффлина-Сан Жеора.
        
        Ответ СТРОГО в формате (только числа):
        КАЛОРИИ: [число]
        БЕЛКИ: [число]
        ЖИРЫ: [число]
        УГЛЕВОДЫ: [число]
        
        Затем добавь:
        РЕКОМЕНДАЦИИ:
        [3 совета по питанию]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты профессиональный диетолог-нутрициолог."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        # Парсим числа
        try:
            calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', result).group(1))
            protein = int(re.search(r'БЕЛКИ:\s*(\d+)', result).group(1))
            fats = int(re.search(r'ЖИРЫ:\s*(\d+)', result).group(1))
            carbs = int(re.search(r'УГЛЕВОДЫ:\s*(\d+)', result).group(1))
            
            # Сохраняем
            user_data[user_id]['target_calories'] = calories
            user_data[user_id]['target_protein'] = protein
            user_data[user_id]['target_fats'] = fats
            user_data[user_id]['target_carbs'] = carbs
            save_data(user_data, DATA_FILE)
            
            response_text = f"""
✅ ТВОЯ НОРМА КБЖУ:

🔥 Калории: {calories} ккал/день
🥩 Белки: {protein} г/день
🥑 Жиры: {fats} г/день
🍞 Углеводы: {carbs} г/день
💧 Вода: 2000 мл/день

{result.split('РЕКОМЕНДАЦИИ:')[1] if 'РЕКОМЕНДАЦИИ:' in result else ''}

📝 Теперь записывай все приемы пищи!
"""
            await update.message.reply_text(response_text, reply_markup=get_keyboard())
            
        except:
            await update.message.reply_text(
                "❌ Не удалось рассчитать. Попробуй еще раз в формате:\n"
                "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть",
                reply_markup=get_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка расчета", reply_markup=get_keyboard())
    
    context.user_data['waiting_for'] = None

# === ОБРАБОТКА ОПИСАНИЯ ЕДЫ ===
async def process_meal_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания приема пищи"""
    description = update.message.text
    user_id = str(update.effective_user.id)
    meal_type = context.user_data.get('current_meal', 'snack')
    
    await update.message.reply_text("⏳ Анализирую состав и считаю КБЖУ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Проанализируй прием пищи: {description}
        
        Рассчитай точно на основе указанных граммовок.
        
        Ответ СТРОГО в формате (только числа):
        КАЛОРИИ: [число]
        БЕЛКИ: [число]
        ЖИРЫ: [число]
        УГЛЕВОДЫ: [число]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты нутрициолог. Точно считаешь КБЖУ продуктов по граммовкам."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.2
        )
        
        result = response.choices[0].message.content
        
        # Парсим числа
        try:
            calories = int(re.search(r'КАЛОРИИ:\s*(\d+)', result).group(1))
            protein = float(re.search(r'БЕЛКИ:\s*([\d.]+)', result).group(1))
            fats = float(re.search(r'ЖИРЫ:\s*([\d.]+)', result).group(1))
            carbs = float(re.search(r'УГЛЕВОДЫ:\s*([\d.]+)', result).group(1))
        except:
            calories, protein, fats, carbs = 300, 20, 10, 40
        
        # Сохраняем
        today = datetime.now().strftime("%Y-%m-%d")
        
        if user_id not in meals_data:
            meals_data[user_id] = []
        
        meal_entry = {
            'type': meal_type,
            'description': description,
            'calories': calories,
            'protein': protein,
            'fats': fats,
            'carbs': carbs,
            'date': today,
            'time': datetime.now().strftime("%H:%M")
        }
        
        meals_data[user_id].append(meal_entry)
        save_data(meals_data, MEALS_FILE)
        
        meal_emoji = {
            'breakfast': '🌅 Завтрак',
            'lunch': '🍽 Обед',
            'dinner': '🌙 Ужин',
            'snack': '🍎 Перекус'
        }.get(meal_type, '🍴 Прием пищи')
        
        await update.message.reply_text(
            f"✅ {meal_emoji} записан!\n\n"
            f"📊 Пищевая ценность:\n"
            f"🔥 Калории: {calories} ккал\n"
            f"🥩 Белки: {protein:.1f} г\n"
            f"🥑 Жиры: {fats:.1f} г\n"
            f"🍞 Углеводы: {carbs:.1f} г\n\n"
            f"Продолжай записывать приемы пищи!",
            reply_markup=get_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка анализа", reply_markup=get_keyboard())
    
    context.user_data['waiting_for'] = None
    context.user_data['current_meal'] = None

# === ОБРАБОТКА ВЕСА ===
async def process_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода веса"""
    user_id = str(update.effective_user.id)
    
    try:
        weight = float(update.message.text.replace(',', '.'))
        
        if weight < 30 or weight > 300:
            await update.message.reply_text("❌ Некорректный вес. Введи реальный вес в кг")
            return
        
        # Сохраняем
        if 'weight_history' not in user_data[user_id]:
            user_data[user_id]['weight_history'] = []
        
        user_data[user_id]['weight_history'].append({
            'weight': weight,
            'date': datetime.now().strftime("%Y-%m-%d")
        })
        save_data(user_data, DATA_FILE)
        
        # Анализ изменения
        history = user_data[user_id]['weight_history']
        if len(history) > 1:
            prev_weight = history[-2]['weight']
            change = weight - prev_weight
            
            if change < 0:
                emoji = "📉"
                text = f"Снижение на {abs(change):.1f} кг"
            elif change > 0:
                emoji = "📈"
                text = f"Увеличение на {change:.1f} кг"
            else:
                emoji = "➡️"
                text = "Вес не изменился"
            
            await update.message.reply_text(
                f"✅ Вес записан: {weight} кг\n\n"
                f"{emoji} {text}\n\n"
                f"Продолжай следить за питанием!",
                reply_markup=get_keyboard()
            )
        else:
            await update.message.reply_text(
                f"✅ Первая запись веса: {weight} кг\n\n"
                f"Взвешивайся каждую пятницу!",
                reply_markup=get_keyboard()
            )
        
    except ValueError:
        await update.message.reply_text("❌ Введи число. Например: 65.5")
    
    context.user_data['waiting_for'] = None

# === ОБРАБОТКА ВОПРОСОВ ===
async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка вопроса к AI"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI готовит ответ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный диетолог-нутрициолог. Отвечай кратко и по делу."},
                {"role": "user", "content": question}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        # Увеличиваем счетчик
        user_data[user_id]['questions_today'] += 1
        save_data(user_data, DATA_FILE)
        
        questions_left = 10 - user_data[user_id]['questions_today']
        
        await update.message.reply_text(
            f"{response.choices[0].message.content}\n\n"
            f"❓ Осталось вопросов: {questions_left}/10",
            reply_markup=get_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка ответа", reply_markup=get_keyboard())
    
    context.user_data['waiting_for'] = None

# === НАПОМИНАНИЯ ===
def setup_daily_reminders(context, user_id):
    """Установка ежедневных напоминаний"""
    job_queue = context.job_queue
    
    # Удаляем старые задания
    current_jobs = job_queue.get_jobs_by_name(str(user_id))
    for job in current_jobs:
        job.schedule_removal()
    
    # Напоминания о приемах пищи
    job_queue.run_daily(
        reminder_breakfast,
        time(hour=8, minute=0),
        data=user_id,
        name=str(user_id)
    )
    
    job_queue.run_daily(
        reminder_lunch,
        time(hour=13, minute=0),
        data=user_id,
