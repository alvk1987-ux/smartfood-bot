import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
WAITING_KBZHU_DATA = 1
WAITING_MENU_PREFERENCES = 2
WAITING_FOOD_INFO = 3
WAITING_AI_QUESTION = 4

# Хранилище данных
user_data = {}

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
        f"🤖 Я SmartFood AI — твой персональный нутрициолог на базе искусственного интеллекта!\n\n"
        f"Что я умею:\n"
        f"🧮 Рассчитать КБЖУ — точный расчет твоей нормы\n"
        f"🍱 Составить меню — персональный рацион\n"
        f"🍽 Анализ питания — оценка любого блюда\n"
        f"💬 Задать вопрос — консультация по питанию\n\n"
        f"Выбери действие 👇",
        reply_markup=get_main_keyboard()
    )

# === РАСЧЕТ КБЖУ ===
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
    
    # Проверяем что это не команда
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
        Для активности используй коэффициенты:
        - низкая: 1.2
        - средняя: 1.55
        - высокая: 1.725
        
        Для цели:
        - похудеть: -15% от TDEE
        - набрать: +15% от TDEE
        - поддержать: TDEE без изменений
        
        Ответь структурированно:
        
        📊 АНАЛИЗ ДАННЫХ:
        [перечисли полученные данные]
        
        📐 РАСЧЕТ:
        • BMR = [формула и результат]
        • TDEE = BMR × [коэффициент] = [результат]
        • Для цели = [корректировка]
        
        🎯 ВАША НОРМА КБЖУ:
        🔥 Калории: [число] ккал
        🥩 Белки: [число] г (2г на кг для похудения, 1.6г для поддержания)
        🥑 Жиры: [число] г (25-30% от калорий)
        🍞 Углеводы: [число] г (остаток калорий)
        💧 Вода: [число] л
        
        📱 РАСПРЕДЕЛЕНИЕ ПО ПРИЕМАМ:
        Завтрак (25%): [ккал]
        Перекус (10%): [ккал]
        Обед (35%): [ккал]
        Полдник (10%): [ккал]
        Ужин (20%): [ккал]
        
        💡 3 ПЕРСОНАЛЬНЫХ СОВЕТА:
        [конкретные рекомендации]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты профессиональный нутрициолог. Делаешь точные расчеты КБЖУ с объяснениями."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        # Сохраняем результат
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['kbzhu'] = result
        user_data[user_id]['user_info'] = user_input
        
        await update.message.reply_text(result, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error in KBZHU calculation: {e}")
        await update.message.reply_text(
            "❌ Ошибка при расчете. Проверьте формат данных.\n"
            "Пример: Ж, 25, 60, 170, средняя, похудеть",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === СОСТАВЛЕНИЕ МЕНЮ ===
async def menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало составления меню"""
    user_id = update.effective_user.id
    
    if user_id in user_data and 'kbzhu' in user_data[user_id]:
        context_text = "✅ Использую ваши рассчитанные КБЖУ\n\n"
    else:
        context_text = "⚠️ КБЖУ не рассчитаны. Меню будет примерным.\n\n"
    
    await update.message.reply_text(
        f"🍱 Составлю персональное меню!\n\n"
        f"{context_text}"
        f"Напишите через запятую:\n"
        f"• Сколько дней? (1-7)\n"
        f"• Что любите?\n"
        f"• Что НЕ едите?\n"
        f"• Аллергии?\n"
        f"• Особенности? (веган/кето/др)\n\n"
        f"📝 Пример:\n"
        f"3 дня, люблю курицу и рыбу, не ем свинину, нет аллергий, обычное питание"
    )
    return WAITING_MENU_PREFERENCES

async def process_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Составление меню через AI"""
    preferences = update.message.text
    user_id = update.effective_user.id
    
    if preferences.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI составляет персональное меню...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        # Добавляем контекст КБЖУ если есть
        kbzhu_context = ""
        if user_id in user_data and 'kbzhu' in user_data[user_id]:
            kbzhu_context = f"\n\nИспользуй эти КБЖУ:\n{user_data[user_id]['kbzhu']}"
        
        prompt = f"""
        Составь детальное меню по запросу: {preferences}
        {kbzhu_context}
        
        Требования:
        - Простые доступные продукты
        - Точные граммовки
        - Расчет КБЖУ для каждого приема
        - Разнообразие блюд
        
        Формат ответа:
        
        📅 МЕНЮ НА [N] ДНЕЙ
        
        ═══ ДЕНЬ 1 ═══
        
        🌅 ЗАВТРАК (8:00):
        • [блюдо] - [грамм]
        • [напиток]
        📊 КБЖУ: [ккал] | Б:[г] | Ж:[г] | У:[г]
        
        🥤 ПЕРЕКУС (11:00):
        • [продукт] - [грамм]
        📊 КБЖУ: [данные]
        
        🍽 ОБЕД (14:00):
        • [первое] - [грамм]
        • [второе] - [грамм]
        • [салат] - [грамм]
        📊 КБЖУ: [данные]
        
        🍎 ПОЛДНИК (17:00):
        • [продукт] - [грамм]
        📊 КБЖУ: [данные]
        
        🌙 УЖИН (19:00):
        • [блюдо] - [грамм]
        📊 КБЖУ: [данные]
        
        📊 ИТОГО ЗА ДЕНЬ:
        Калории: [сумма]
        Белки: [сумма]
        Жиры: [сумма]
        Углеводы: [сумма]
        
        [Повтори для остальных дней]
        
        🛒 СПИСОК ПОКУПОК:
        [все продукты с количеством на все дни]
        
        👨‍🍳 СОВЕТЫ ПО ПРИГОТОВЛЕНИЮ:
        [3 полезных совета]
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты профессиональный диетолог. Составляешь детальные меню с точным подсчетом КБЖУ."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.5
        )
        
        menu = response.choices[0].message.content
        
        # Разбиваем длинное сообщение если нужно
        if len(menu) > 4000:
            parts = [menu[i:i+4000] for i in range(0, len(menu), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(menu)
        
        await update.message.reply_text("✅ Меню готово!", reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error creating menu: {e}")
        await update.message.reply_text(
            "❌ Ошибка при составлении меню.\n"
            "Попробуйте упростить запрос.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === АНАЛИЗ ПИТАНИЯ ===
async def analyze_food_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало анализа питания"""
    await update.message.reply_text(
        "🍽 Опишите что съели или планируете съесть:\n\n"
        "Примеры:\n"
        "• 'Борщ со сметаной, 300г'\n"
        "• 'Цезарь с курицей и гренками'\n"
        "• 'Овсянка на молоке с бананом и медом'\n"
        "• 'Паста карбонара, порция в ресторане'\n\n"
        "Чем подробнее — тем точнее анализ!"
    )
    return WAITING_FOOD_INFO

async def process_food_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ еды через AI"""
    food_description = update.message.text
    
    if food_description.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI анализирует блюдо...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        prompt = f"""
        Проанализируй блюдо/прием пищи: {food_description}
        
        Дай подробный анализ:
        
        🍽 АНАЛИЗ БЛЮДА:
        Название: [что это]
        Примерный вес порции: [грамм]
        
        📊 СОСТАВ (разбей на ингредиенты):
        • [продукт] - [грамм]
        • [продукт] - [грамм]
        
        📈 ПИЩЕВАЯ ЦЕННОСТЬ:
        🔥 Калории: [ккал]
        🥩 Белки: [г] ([% от калорий])
        🥑 Жиры: [г] ([% от калорий])
        - насыщенные: [г]
        🍞 Углеводы: [г] ([% от калорий])
        - сахара: [г]
        - клетчатка: [г]
        
        💎 ПОЛЕЗНЫЕ ВЕЩЕСТВА:
        • Витамины: [какие]
        • Минералы: [какие]
        • Особые вещества: [омега-3, антиоксиданты и тд]
        
        ⚖️ ОЦЕНКА:
        • Калорийность: [низкая/средняя/высокая]
        • Сытость: [надолго ли насытит]
        • Польза: [оценка из 10]
        • Сбалансированность БЖУ: [оценка]
        
        ✅ ПЛЮСЫ:
        [что хорошего]
        
        ⚠️ МИНУСЫ:
        [что не очень]
        
        💡 РЕКОМЕНДАЦИИ:
        • Когда лучше есть это блюдо
        • Как сделать полезнее
        • С чем сочетать
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты опытный нутрициолог. Даешь детальный анализ блюд с точными расчетами КБЖУ."},
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
            "❌ Ошибка анализа. Попробуйте еще раз.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END

# === ВОПРОСЫ К AI ===
async def ask_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога с AI"""
    await update.message.reply_text(
        "💬 Задайте любой вопрос о питании и здоровье!\n\n"
        "Например:\n"
        "• Как убрать живот?\n"
        "• Можно ли есть после 18:00?\n"
        "• Что есть после тренировки?\n"
        "• Какие продукты содержат белок?\n"
        "• Вреден ли сахар?\n\n"
        "Пишите ваш вопрос:"
    )
    return WAITING_AI_QUESTION

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ AI на вопрос"""
    question = update.message.text
    
    # Проверяем не кнопка ли это
    if question in ["🧮 Рассчитать КБЖУ", "🍱 Составить меню", "🍽 Анализ питания", "💬 Задать вопрос"]:
        return ConversationHandler.END
    
    if question.startswith("/"):
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ AI готовит ответ...")
    
    try:
        client = get_client()
        if not client:
            raise ValueError("No API client")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Ты опытный нутрициолог, диетолог и фитнес-консультант. 
                Даешь экспертные ответы на вопросы о питании, диетах, здоровье.
                Отвечаешь подробно, с научным обоснованием, но простым языком.
                Используешь эмодзи для наглядности.
                Даешь практические советы и примеры.
                Если вопрос не по теме - вежливо говоришь что консультируешь только по питанию и здоровью."""},
                {"role": "user", "content": question}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        
        await update.message.reply_text(
            f"{answer}\n\n"
            "➡️ Можете задать еще вопрос или выбрать действие:",
            reply_markup=get_main_keyboard()
        )
        
        # Остаемся в режиме вопросов для продолжения диалога
        return WAITING_AI_QUESTION
        
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении ответа.\n"
            "Попробуйте переформулировать вопрос.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

# === ОТМЕНА ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "❌ Отменено",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

# === ТЕСТ API ===
async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирование подключения к API"""
    await update.message.reply_text("🔧 Тестирую подключение к AI...")
    
    try:
        client = get_client()
        if not client:
            await update.message.reply_text("❌ API ключ не найден в переменных окружения")
            return
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Скажи 'Привет, я работаю!'"}],
            max_tokens=50
        )
        
        await update.message.reply_text(
            f"✅ API работает!\n\n"
            f"Ответ AI: {response.choices[0].message.content}",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка API:\n{str(e)}\n\n"
            f"Проверьте:\n"
            f"1. API ключ в Railway Variables\n"
            f"2. Баланс на ProxyAPI",
            reply_markup=get_main_keyboard()
        )

def main():
    """Главная функция"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    logger.info("Starting SmartFood AI Bot...")
    
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
            WAITING_FOOD_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_food_analysis)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчик вопросов (с продолжением диалога)
    question_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 Задать вопрос$"), ask_question_start)],
        states={
            WAITING_AI_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_question)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^(🧮|🍱|🍽)"), cancel)
        ]
    )
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_api))
    app.add_handler(kbzhu_conv)
    app.add_handler(menu_conv)
    app.add_handler(food_conv)
    app.add_handler(question_conv)
    
    # Запуск
    logger.info("Bot started successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
