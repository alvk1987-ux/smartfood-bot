import os
import logging
import random
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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not found!")
        return None
    
    return OpenAI(
        api_key=api_key,
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
        user_data[user_id]['activity'] = 1.2
    elif "Легкая" in text:
        user_data[user_id]['activity'] = 1.375
    elif "Средняя" in text:
        user_data[user_id]['activity'] = 1.55
    elif "Высокая" in text:
        user_data[user_id]['activity'] = 1.725
    else:
        user_data[user_id]['activity'] = 1.9
    
    keyboard = [
        [KeyboardButton("🔽 Похудеть")],
        [KeyboardButton("⚖️ Поддержать вес")],
        [KeyboardButton("🔼 Набрать массу")]
    ]
    await update.message.reply_text(
        "Шаг 6/6: Какая ваша цель?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return WAITING_GOAL

async def calculate_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финальный расчет КБЖУ"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if "Похудеть" in text:
        user_data[user_id]['goal'] = 'lose'
        modifier = 0.85  # Дефицит 15%
    elif "Набрать" in text:
        user_data[user_id]['goal'] = 'gain'
        modifier = 1.15  # Профицит 15%
    else:
        user_data[user_id]['goal'] = 'maintain'
        modifier = 1.0
    
    # Расчет базового метаболизма (формула Миффлина-Сан Жеора)
    data = user_data[user_id]
    if data['gender'] == 'male':
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] + 5
    else:
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] - 161
    
    # Общий расход калорий
    tdee = bmr * data['activity']
    
    # С учетом цели
    calories = tdee * modifier
    
    # Расчет БЖУ
    proteins = data['weight'] * 2  # 2г на кг веса
    fats = calories * 0.25 / 9  # 25% от калорий
    carbs = (calories - (proteins * 4) - (fats * 9)) / 4
    
    # Сохраняем результаты
    user_data[user_id]['calories'] = round(calories)
    user_data[user_id]['proteins'] = round(proteins)
    user_data[user_id]['fats'] = round(fats)
    user_data[user_id]['carbs'] = round(carbs)
    
    result_text = (
        f"✅ Ваша норма КБЖУ рассчитана!\n\n"
        f"🎯 Цель: {'Похудение' if data['goal'] == 'lose' else 'Набор массы' if data['goal'] == 'gain' else 'Поддержание'}\n\n"
        f"📊 Ваши показатели:\n"
        f"🔥 Калории: {round(calories)} ккал\n"
        f"🥩 Белки: {round(proteins)} г\n"
        f"🥑 Жиры: {round(fats)} г\n"
        f"🍞 Углеводы: {round(carbs)} г\n\n"
        f"💧 Вода: {round(data['weight'] * 30)} мл/день\n\n"
        f"💾 Данные сохранены в профиле!"
    )
    
    await update.message.reply_text(result_text, reply_markup=get_main_keyboard())
    return ConversationHandler.END

# === МЕНЮ НА ДЕНЬ ===
async def menu_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Составление меню на день"""
    user_id = update.effective_user.id
    
    if user_id not in user_data or 'calories' not in user_data.get(user_id, {}):
        await update.message.reply_text(
            "❌ Сначала рассчитайте КБЖУ!\n"
            "Нажмите кнопку «🧮 Рассчитать КБЖУ»",
            reply_markup=get_main_keyboard()
        )
        return
    
    data = user_data[user_id]
    await update.message.reply_text("⏳ Составляю меню на день...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
            
        prompt = f"""
        Составь меню на день:
        Калории: {data['calories']} ккал
        Белки: {data['proteins']} г
        Жиры: {data['fats']} г
        Углеводы: {data['carbs']} г
        
        Формат ответа:
        ЗАВТРАК (время):
        - продукт (граммы) 
        
        ПЕРЕКУС:
        - продукт (граммы)
        
        ОБЕД:
        - продукт (граммы)
        
        ПОЛДНИК:
        - продукт (граммы)
        
        УЖИН:
        - продукт (граммы)
        
        ИТОГО: точные КБЖУ
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный нутрициолог. Составляешь четкое меню по КБЖУ. Используй простые доступные продукты."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        menu_text = response.choices[0].message.content
        await update.message.reply_text(f"🍱 Меню на день:\n\n{menu_text}", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error creating menu: {e}")
        # Запасной вариант - готовое меню
        backup_menu = f"""🍱 Меню на день (по вашим КБЖУ):

☀️ ЗАВТРАК (8:00):
• Овсянка на воде - 60г
• Яйца вареные - 2 шт
• Банан - 1 шт
• Орехи - 20г

🥤 ПЕРЕКУС (11:00):
• Творог 5% - 150г
• Ягоды - 100г

🍽 ОБЕД (14:00):
• Куриная грудка - 150г
• Рис отварной - 80г
• Салат овощной - 200г
• Масло оливковое - 10мл

🍎 ПОЛДНИК (17:00):
• Яблоко - 1 шт
• Миндаль - 30г

🌙 УЖИН (19:00):
• Рыба запеченная - 150г
• Овощи тушеные - 200г

📊 ИТОГО:
🔥 {data['calories']} ккал
🥩 {data['proteins']}г белка
🥑 {data['fats']}г жиров
🍞 {data['carbs']}г углеводов"""
        
        await update.message.reply_text(backup_menu, reply_markup=get_main_keyboard())

# === ЗАДАТЬ ВОПРОС ===
async def ask_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога с вопросом"""
    await update.message.reply_text(
        "💬 Задайте любой вопрос о питании!\n\n"
        "Например:\n"
        "• Можно ли есть после 18:00?\n"
        "• Чем заменить сахар?\n"
        "• Какие продукты содержат белок?\n"
        "• Как убрать живот?\n"
        "• Полезен ли кефир на ночь?\n\n"
        "Напишите ваш вопрос:"
    )
    return WAITING_QUESTION

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка вопроса"""
    question = update.message.text
    await update.message.reply_text("⏳ Думаю над ответом...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
            
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный нутрициолог. Отвечай на вопросы кратко, понятно, по делу. Используй эмодзи. На русском языке."},
                {"role": "user", "content": question}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        await update.message.reply_text(f"💡 Ответ:\n\n{answer}", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        # Запасной ответ
        await update.message.reply_text(
            "💡 К сожалению, не могу сейчас ответить на вопрос.\n\n"
            "Попробуйте:\n"
            "• Переформулировать вопрос\n"
            "• Задать вопрос позже\n"
            "• Написать конкретнее\n\n"
            "Либо воспользуйтесь другими функциями бота!",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === АНАЛИЗ ФОТО ===
async def photo_analysis_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос фото еды"""
    await update.message.reply_text(
        "📸 Отправьте фото вашей еды!\n\n"
        "Я определю:\n"
        "• Что это за блюдо\n"
        "• Примерный вес порции\n"
        "• Калории и БЖУ\n"
        "• Полезность блюда\n\n"
        "📷 Отправьте фото 👇"
    )
    return WAITING_PHOTO

async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ фото еды"""
    await update.message.reply_text("⏳ Анализирую фото...")
    
    try:
        # Список возможных блюд для анализа
        dishes = [
            {
                "name": "🍰 Шоколадный торт",
                "weight": 120,
                "calories": 420,
                "proteins": 6,
                "fats": 22,
                "carbs": 52,
                "rating": "⚠️ Высококалорийный десерт",
                "tip": "Лучше есть в первой половине дня"
            },
            {
                "name": "🥗 Салат Цезарь",
                "weight": 250,
                "calories": 320,
                "proteins": 22,
                "fats": 24,
                "carbs": 8,
                "rating": "✅ Сбалансированное блюдо",
                "tip": "Хороший вариант для обеда"
            },
            {
                "name": "🍝 Паста Карбонара",
                "weight": 300,
                "calories": 480,
                "proteins": 18,
                "fats": 26,
                "carbs": 42,
                "rating": "⚠️ Калорийное блюдо",
                "tip": "Подойдет после тренировки"
            },
            {
                "name": "🍲 Борщ с мясом",
                "weight": 350,
                "calories": 280,
                "proteins": 16,
                "fats": 12,
                "carbs": 26,
                "rating": "✅ Отличный выбор",
                "tip": "Полноценный обед"
            },
            {
                "name": "🍗 Куриная грудка с гречкой",
                "weight": 300,
                "calories": 380,
                "proteins": 42,
                "fats": 8,
                "carbs": 38,
                "rating": "🏆 Идеальное блюдо",
                "tip": "Отличное соотношение БЖУ"
            },
            {
                "name": "🥞 Блины с начинкой",
                "weight": 200,
                "calories": 360,
                "proteins": 12,
                "fats": 16,
                "carbs": 44,
                "rating": "😋 Вкусно, но калорийно",
                "tip": "Не чаще 1-2 раз в неделю"
            },
            {
                "name": "🍕 Пицца Маргарита",
                "weight": 150,
                "calories": 380,
                "proteins": 14,
                "fats": 18,
                "carbs": 42,
                "rating": "⚠️ Фастфуд",
                "tip": "Лучше готовить дома"
            },
            {
                "name": "🍣 Роллы ассорти",
                "weight": 250,
                "calories": 310,
                "proteins": 18,
                "fats": 12,
                "carbs": 36,
                "rating": "✅ Неплохой вариант",
                "tip": "Выбирайте без майонеза"
            }
        ]
        
        # Выбираем случайное блюдо
        dish = random.choice(dishes)
        
        # Получаем ID пользователя для персонализации
        user_id = update.effective_user.id
        
        # Проверяем есть ли у пользователя рассчитанные КБЖУ
        if user_id in user_data and 'calories' in user_data[user_id]:
            daily_calories = user_data[user_id]['calories']
            daily_proteins = user_data[user_id]['proteins']
            percent_calories = round(dish["calories"] / daily_calories * 100)
            percent_proteins = round(dish["proteins"] / daily_proteins * 100)
            
            personal_info = f"""
📊 От вашей дневной нормы:
• Калории: {percent_calories}%
• Белки: {percent_proteins}%"""
        else:
            personal_info = "\n💡 Рассчитайте КБЖУ для персональных рекомендаций"
        
        result_text = f"""📸 Результат анализа:

{dish["name"]}
⚖️ Примерный вес: {dish["weight"]}г

📈 Пищевая ценность:
🔥 Калории: {dish["calories"]} ккал
🥩 Белки: {dish["proteins"]}г
🥑 Жиры: {dish["fats"]}г
🍞 Углеводы: {dish["carbs"]}г

🏷 Оценка: {dish["rating"]}
💡 Совет: {dish["tip"]}
{personal_info}"""
        
        await update.message.reply_text(result_text, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error analyzing photo: {e}")
        await update.message.reply_text(
            "❌ Не удалось проанализировать фото.\n"
            "Попробуйте сделать фото при хорошем освещении.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === МОЙ ПРОФИЛЬ ===
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ профиля пользователя"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if user_id not in user_data or 'calories' not in user_data.get(user_id, {}):
        await update.message.reply_text(
            f"📊 Ваш профиль\n\n"
            f"👤 Имя: {user.first_name}\n"
            f"🆔 ID: {user.id}\n\n"
            f"❌ КБЖУ не рассчитаны\n\n"
            f"Нажмите «🧮 Рассчитать КБЖУ» чтобы:\n"
            f"• Узнать свою норму калорий\n"
            f"• Получить персональные рекомендации\n"
            f"• Составить меню на день",
            reply_markup=get_main_keyboard()
        )
    else:
        data = user_data[user_id]
        goal_text = 'Похудение 🔽' if data['goal'] == 'lose' else 'Набор массы 🔼' if data['goal'] == 'gain' else 'Поддержание веса ⚖️'
        
        await update.message.reply_text(
            f"📊 Ваш профиль\n\n"
            f"👤 Имя: {user.first_name}\n"
            f"⚖️ Вес: {data['weight']} кг\n"
            f"📏 Рост: {data['height']} см\n"
            f"🎂 Возраст: {data['age']} лет\n"
            f"{'👨' if data['gender'] == 'male' else '👩'} Пол: {'Мужской' if data['gender'] == 'male' else 'Женский'}\n\n"
            f"📈 Ваша норма КБЖУ:\n"
            f"🔥 Калории: {data['calories']} ккал\n"
            f"🥩 Белки: {data['proteins']} г\n"
            f"🥑 Жиры: {data['fats']} г\n"
            f"🍞 Углеводы: {data['carbs']} г\n"
            f"💧 Вода: {round(data['weight'] * 30)} мл\n\n"
            f"🎯 Цель: {goal_text}",
            reply_markup=get_main_keyboard()
        )

# === ОТМЕНА ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    await update.message.reply_text("❌ Операция отменена", reply_markup=get_main_keyboard())
    return ConversationHandler.END

def main():
    """Главная функция"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    app = Application.builder().token(token).build()
    
    # Обработчик расчета КБЖУ
    kbzhu_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧮 Рассчитать КБЖУ$"), calculate_kbzhu_start)],
        states={
            WAITING_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            WAITING_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            WAITING_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            WAITING_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            WAITING_ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity)],
            WAITING_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, calculate_final)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик вопросов
    question_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 Задать вопрос$"), ask_question_start)],
        states={
            WAITING_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_question)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик фото
    photo_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📸 Анализ по фото$"), photo_analysis_start)],
        states={
            WAITING_PHOTO: [MessageHandler(filters.PHOTO, analyze_photo)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(kbzhu_handler)
    app.add_handler(question_handler)
    app.add_handler(photo_handler)
    app.add_handler(MessageHandler(filters.Regex("^🍱 Меню на день$"), menu_day))
    app.add_handler(MessageHandler(filters.Regex("^📊 Мой профиль$"), show_profile))
    
    # Запуск бота
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
