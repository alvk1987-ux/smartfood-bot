import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния диалога
WAITING_FOOD_INFO = 1
WAITING_KBZHU_DATA = 2
WAITING_MENU_PREFERENCES = 3
WAITING_AI_RESPONSE = 4

# Хранилище данных пользователей
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
        [KeyboardButton("🍱 Составить меню")],
        [KeyboardButton("🍽 Анализ питания")],
        [KeyboardButton("💬 Задать вопрос")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я SmartFood AI — твой персональный AI-нутрициолог!\n\n"
        f"🧮 Рассчитать КБЖУ — определю твою норму\n"
        f"🍱 Составить меню — создам рацион под тебя\n"
        f"🍽 Анализ питания — оценю что ты ешь\n"
        f"💬 Задать вопрос — спроси что угодно\n\n"
        f"Выбери действие 👇",
        reply_markup=get_main_keyboard()
    )

# === РАСЧЕТ КБЖУ ЧЕРЕЗ AI ===
async def calculate_kbzhu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало расчета КБЖУ через AI"""
    await update.message.reply_text(
        "🧮 Для расчета КБЖУ ответьте на вопросы одним сообщением:\n\n"
        "1. Ваш пол (м/ж)?\n"
        "2. Возраст?\n"
        "3. Вес (кг)?\n"
        "4. Рост (см)?\n"
        "5. Уровень активности (низкий/средний/высокий)?\n"
        "6. Цель (похудеть/поддержать/набрать массу)?\n\n"
        "Пример ответа:\n"
        "Мужчина, 30 лет, 80 кг, 180 см, средняя активность, похудеть"
    )
    return WAITING_KBZHU_DATA

async def process_kbzhu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных для КБЖУ через AI"""
    user_info = update.message.text
    user_id = update.effective_user.id
    
    await update.message.reply_text("⏳ Рассчитываю ваши КБЖУ через AI...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
        
        prompt = f"""
        Ты профессиональный нутрициолог. Рассчитай КБЖУ для человека:
        {user_info}
        
        Используй формулу Миффлина-Сан Жеора для расчета базового метаболизма.
        Учти уровень активности и цель.
        
        Ответь в формате:
        📊 РЕЗУЛЬТАТЫ РАСЧЕТА:
        - Базовый метаболизм: ... ккал
        - С учетом активности: ... ккал
        - Для вашей цели: ... ккал
        
        🎯 ВАША НОРМА:
        Калории: ... ккал
        Белки: ... г (примерно ...г на кг веса)
        Жиры: ... г  
        Углеводы: ... г
        Вода: ... литра
        
        💡 РЕКОМЕНДАЦИИ:
        (дай 3 персональных совета)
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный нутрициолог. Даешь точные расчеты и полезные советы."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        # Сохраняем данные пользователя
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['kbzhu_info'] = user_info
        user_data[user_id]['kbzhu_result'] = result
        
        await update.message.reply_text(result, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error calculating KBZHU: {e}")
        # Если API не работает, даем примерный расчет
        await update.message.reply_text(
            "📊 Примерный расчет КБЖУ:\n\n"
            "Для точного расчета нужна связь с AI.\n"
            "Пока используйте примерные нормы:\n\n"
            "Женщины: 1800-2000 ккал\n"
            "Мужчины: 2200-2500 ккал\n\n"
            "Белки: 1.5-2г на кг веса\n"
            "Жиры: 0.8-1г на кг веса\n"
            "Углеводы: оставшиеся калории\n\n"
            "Попробуйте позже для точного расчета!",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === СОСТАВЛЕНИЕ МЕНЮ ЧЕРЕЗ AI ===
async def menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало составления меню"""
    user_id = update.effective_user.id
    
    # Проверяем, есть ли сохраненные КБЖУ
    if user_id in user_data and 'kbzhu_result' in user_data[user_id]:
        kbzhu_info = "\nУчитываю ваши рассчитанные КБЖУ."
    else:
        kbzhu_info = "\nСначала рассчитайте КБЖУ для точного меню."
    
    await update.message.reply_text(
        f"🍱 Составлю персональное меню!{kbzhu_info}\n\n"
        "Напишите одним сообщением:\n\n"
        "1. На сколько дней составить меню? (1-7)\n"
        "2. Какие продукты ОБЯЗАТЕЛЬНО включить?\n"
        "3. Какие продукты ИСКЛЮЧИТЬ?\n"
        "4. Есть ли аллергии?\n"
        "5. Предпочтения (веган, кето, и т.д.)?\n\n"
        "Пример:\n"
        "1 день, люблю курицу и овощи, без молочки, аллергия на орехи, обычное питание"
    )
    return WAITING_MENU_PREFERENCES

async def process_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Составление меню через AI"""
    preferences = update.message.text
    user_id = update.effective_user.id
    
    await update.message.reply_text("⏳ AI составляет персональное меню...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
        
        # Добавляем КБЖУ если есть
        if user_id in user_data and 'kbzhu_result' in user_data[user_id]:
            kbzhu_context = f"\n\nРанее рассчитанные КБЖУ:\n{user_data[user_id]['kbzhu_result']}"
        else:
            kbzhu_context = ""
        
        prompt = f"""
        Составь детальное меню по запросу:
        {preferences}
        {kbzhu_context}
        
        Формат ответа:
        
        📅 МЕНЮ НА [количество дней]
        
        ДЕНЬ 1:
        
        🌅 ЗАВТРАК (время):
        • Блюдо - граммовка
        • Напиток
        КБЖУ: ... ккал, Б:...г, Ж:...г, У:...г
        
        🥤 ПЕРЕКУС 1:
        • Что съесть
        КБЖУ: ...
        
        🍽 ОБЕД:
        • Блюда с граммовкой
        КБЖУ: ...
        
        🍎 ПЕРЕКУС 2:
        • Что съесть
        КБЖУ: ...
        
        🌙 УЖИН:
        • Блюда с граммовкой
        КБЖУ: ...
        
        📊 ИТОГО ЗА ДЕНЬ:
        Калории: ...
        Белки: ...
        Жиры: ...
        Углеводы: ...
        
        📝 СПИСОК ПОКУПОК:
        (все продукты с количеством)
        
        💡 СОВЕТЫ ПО ПРИГОТОВЛЕНИЮ:
        (3 полезных совета)
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты профессиональный нутрициолог и повар. Составляешь вкусные и полезные меню с точным КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.5
        )
        
        menu = response.choices[0].message.content
        await update.message.reply_text(menu, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error creating menu: {e}")
        await update.message.reply_text(
            "❌ Не удалось составить меню через AI.\n\n"
            "Попробуйте:\n"
            "• Упростить запрос\n"
            "• Повторить позже\n"
            "• Сначала рассчитать КБЖУ",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === АНАЛИЗ ПИТАНИЯ ===
async def analyze_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало анализа питания"""
    await update.message.reply_text(
        "🍽 Опишите что вы съели или планируете съесть.\n\n"
        "Можете написать:\n"
        "• Одно блюдо: 'Цезарь с курицей'\n"
        "• Весь прием пищи: 'гречка 150г, куриная грудка 100г, салат'\n"
        "• Весь день: 'завтрак - овсянка с бананом, обед - борщ...'\n\n"
        "Чем подробнее опишете, тем точнее будет анализ!"
    )
    return WAITING_FOOD_INFO

async def process_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды через AI"""
    food_description = update.message.text
    
    await update.message.reply_text("⏳ AI анализирует питание...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
        
        prompt = f"""
        Проанализируй питание: {food_description}
        
        Дай ответ в формате:
        
        🍽 АНАЛИЗ БЛЮДА/РАЦИОНА:
        
        📊 СОСТАВ (если не указан вес, оцени примерно):
        • [Продукт] - [вес]г
        • ...
        
        📈 ПИЩЕВАЯ ЦЕННОСТЬ:
        🔥 Калории: ... ккал
        🥩 Белки: ... г
        🥑 Жиры: ... г (насыщенные: ...г)
        🍞 Углеводы: ... г (сахар: ...г)
        🥬 Клетчатка: ... г
        
        💎 МИКРОНУТРИЕНТЫ:
        • Основные витамины
        • Основные минералы
        
        ⚖️ ОЦЕНКА:
        • Сбалансированность: .../10
        • Полезность: .../10
        • Калорийность: (низкая/средняя/высокая)
        
        ✅ ПЛЮСЫ:
        • ...
        
        ⚠️ МИНУСЫ:
        • ...
        
        💡 РЕКОМЕНДАЦИИ:
        • Как улучшить это блюдо/рацион
        • Что добавить/убрать
        • Когда лучше есть
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный нутрициолог. Даешь точный анализ питания с расчетом КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        analysis = response.choices[0].message.content
        await update.message.reply_text(analysis, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error analyzing food: {e}")
        await update.message.reply_text(
            "❌ Не удалось проанализировать через AI.\n"
            "Попробуйте позже или упростите описание.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === СВОБОДНЫЙ ДИАЛОГ С AI ===
async def ask_ai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога с AI"""
    await update.message.reply_text(
        "💬 Задайте любой вопрос о питании, диетах, здоровье!\n\n"
        "Например:\n"
        "• Как убрать живот?\n"
        "• Можно ли есть после 6?\n"
        "• Что есть после тренировки?\n"
        "• Вреден ли глютен?\n"
        "• Как набрать мышечную массу?\n\n"
        "Пишите ваш вопрос:"
    )
    return WAITING_AI_RESPONSE

async def process_ai_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка вопроса через AI"""
    question = update.message.text
    
    # Если это не вопрос, а команда/кнопка - выходим
    if question in ["🧮 Рассчитать КБЖУ", "🍱 Составить меню", "🍽 Анализ питания", "💬 Задать вопрос"]:
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI обдумывает ответ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No OpenAI client")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Ты опытный нутрициолог и диетолог с 20-летним стажем. 
                Отвечаешь подробно, с научным обоснованием, но понятным языком. 
                Используешь эмодзи для наглядности. 
                Даешь практические советы.
                Если вопрос не про питание/здоровье - вежливо говоришь что консультируешь только по питанию."""},
                {"role": "user", "content": question}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        
        # Добавляем возможность задать следующий вопрос
        await update.message.reply_text(
            f"{answer}\n\n"
            "➡️ Можете задать следующий вопрос или выбрать действие в меню:",
            reply_markup=get_main_keyboard()
        )
        
        # Остаемся в режиме вопросов
        return WAITING_AI_RESPONSE
        
    except Exception as e:
        logger.error(f"Error with AI question: {e}")
        await update.message.reply_text(
            "❌ Не удалось получить ответ от AI.\n"
            "Попробуйте переформулировать или повторить позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

# === ОТМЕНА ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "❌ Отменено. Выберите действие:",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

# === ОБРАБОТКА ФОТО ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото еды"""
    await update.message.reply_text(
        "📸 Получил фото! Анализирую...\n\n"
        "⚠️ Анализ фото пока в разработке.\n"
        "Пока опишите текстом что на фото, и я проанализирую!",
        reply_markup=get_main_keyboard()
    )

def main():
    """Главная функция"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    app = Application.builder().token(token).build()
    
    # Обработчик расчета КБЖУ
    kbzhu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🧮 Рассчитать КБЖУ$"), calculate_kbzhu_start)],
        states={
            WAITING_KBZHU_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_kbzhu)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик составления меню
    menu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍱 Составить меню$"), menu_start)],
        states={
            WAITING_MENU_PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_menu)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик анализа питания
    food_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽 Анализ питания$"), analyze_food_start)],
        states={
            WAITING_FOOD_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_food)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик вопросов к AI (с продолжением диалога)
    ai_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 Задать вопрос$"), ask_ai_start)],
        states={
            WAITING_AI_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_ai_question)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^(🧮|🍱|🍽|💬)"), cancel)
        ]
    )
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(kbzhu_conv)
    app.add_handler(menu_conv)
    app.add_handler(food_conv)
    app.add_handler(ai_conv)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Запуск бота
    logger.info("SmartFood AI Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
