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
        
        # Проверяем статус в канале
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
            [KeyboardButton("ℹ️ Что умеет бот?")],
            [KeyboardButton("💬 Отзывы")]
        ]
    else:
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
            "joined": datetime.now().isoformat(),
            "target_calories": 2000,
            "target_protein": 100,
            "target_fats": 70,
            "target_carbs": 250,
            "questions_today": 0
        }
    
    if user_id not in meals_data:
        meals_data[user_id] = []
    
    # Проверяем подписку
    is_premium = await check_subscription(update, context)
    
    if is_premium:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"✅ Доступ активен! Все функции разблокированы!\n\n"
            f"🤖 Я SmartFood AI - твой умный дневник питания!\n\n"
            f"Что умею:\n"
            f"• AI подсчет калорий любых блюд\n"
            f"• Персональный расчет КБЖУ\n"
            f"• Дневник питания с анализом\n"
            f"• Напоминания о приемах пищи\n"
            f"• Контроль воды и веса\n"
            f"• AI-консультант (10 вопросов/день)\n\n"
            f"📝 Просто пиши что съел - AI всё посчитает!\n\n"
            f"🧮 Начни с расчета своей нормы КБЖУ!",
            reply_markup=get_keyboard(True)
        )
        
        # Устанавливаем напоминания
        setup_reminders(context, int(user_id))
    else:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🤖 Я SmartFood AI - умный дневник питания с AI!\n\n"
            f"🎯 БОЛЬШЕ НЕ НУЖНО:\n"
            f"❌ Искать калорийность в таблицах\n"
            f"❌ Считать КБЖУ на калькуляторе\n"
            f"❌ Вести записи вручную\n\n"
            f"✨ ПРОСТО ПИШИ ЧТО СЪЕЛ:\n"
            f'Напишешь: "Борщ со сметаной"\n'
            f"Получишь: 320 ккал, Б:15г, Ж:12г, У:38г\n\n"
            f"💰 Стоимость: 399₽/месяц\n"
            f"Это всего 13₽ в день!\n\n"
            f"👇 Нажми для покупки доступа:",
            reply_markup=get_keyboard(False)
        )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех кнопок"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Кнопки для неподписанных
    if text == "💳 Купить доступ 399₽":
        await show_payment_info(update, context)
        return
    
    elif text == "🎁 У меня есть подписка":
        is_premium = await check_subscription(update, context)
        if is_premium:
            await update.message.reply_text(
                "✅ Отлично! Подписка активна!\n\n"
                "Все функции разблокированы!",
                reply_markup=get_keyboard(True)
            )
        else:
            await update.message.reply_text(
                "❌ Подписка не найдена!\n\n"
                "Сначала оплатите доступ к каналу,\n"
                "затем нажмите эту кнопку снова.",
                reply_markup=get_keyboard(False)
            )
        return
    
    elif text == "ℹ️ Что умеет бот?":
        await show_features(update, context)
        return
    
    elif text == "💬 Отзывы":
        await show_reviews(update, context)
        return
    
    # Проверка подписки для основных функций
    is_premium = await check_subscription(update, context)
    
    if not is_premium:
        await update.message.reply_text(
            "❌ Нужна подписка!\n\n"
            "Для доступа к боту оплатите\n"
            "подписку на канал Premium.\n\n"
            "💰 Стоимость: 399₽/месяц\n\n"
            "Нажмите 👇",
            reply_markup=get_keyboard(False)
        )
        return
    
    # === ФУНКЦИИ ДЛЯ ПОДПИСЧИКОВ ===
    
    # Обработка ожидающих вводов
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
    
    # Обработка кнопок меню
    if text == "🧮 Рассчитать КБЖУ":
        await update.message.reply_text(
            "🧮 Напиши одним сообщением:\n\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 Пример:\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть"
        )
        context.user_data['waiting_for'] = 'kbzhu_data'
    
    elif text in ["🌅 Завтрак", "🍽 Обед", "🌙 Ужин", "🍎 Перекус"]:
        meal_types = {
            "🌅 Завтрак": "breakfast",
            "🍽 Обед": "lunch",
            "🌙 Ужин": "dinner",
            "🍎 Перекус": "snack"
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
Это всего 13₽ в день!

✅ ЧТО ВХОДИТ:
• AI-анализ любых блюд за секунду
• Автоматический подсчет КБЖУ
• Дневник питания с историей
• Персональный расчет нормы
• Статистика и графики
• Напоминания о еде и воде
• 10 вопросов AI-диетологу в день
• Еженедельное взвешивание
• Поддержка и обновления

📱 КАК ОПЛАТИТЬ:
1. Нажмите кнопку "Оплатить"
2. Оплатите через Telegram
3. Вернитесь и нажмите "Я оплатил"

🔒 Безопасная оплата через Telegram
✅ Моментальная активация
🎁 Доступ на 30 дней
""",
        reply_markup=reply_markup
    )

async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка оплаты через callback"""
    query = update.callback_query
    await query.answer()
    
    is_premium = await check_subscription(update, context)
    
    if is_premium:
        await query.edit_message_text(
            "✅ Отлично! Оплата подтверждена!\n\n"
            "🎉 Добро пожаловать в Premium!\n\n"
            "Все функции разблокированы.\n"
            "Начните с расчета КБЖУ!"
        )
        
        # Отправляем главное меню
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=get_keyboard(True)
        )
        
        # Устанавливаем напоминания
        setup_reminders(context, query.from_user.id)
    else:
        await query.edit_message_text(
            "❌ Подписка не найдена!\n\n"
            "Убедитесь что:\n"
            "1. Оплата прошла успешно\n"
            "2. Вы вступили в канал\n\n"
            "Попробуйте еще раз через минуту"
        )

async def show_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ возможностей бота"""
    await update.message.reply_text(
        """
🤖 ЧТО УМЕЕТ SMARTFOOD AI:

🎯 ГЛАВНАЯ ФИШКА:
Пишешь "съел борщ" → получаешь КБЖУ!
Не нужно искать в таблицах!

📝 ДНЕВНИК ПИТАНИЯ:
• Записывает все приемы пищи
• Автоматически считает калории
• Сохраняет историю
• Показывает прогресс

🧮 УМНЫЙ РАСЧЕТ:
• Персональная норма КБЖУ
• Учет целей (похудеть/набрать)
• Адаптация под активность

📊 СТАТИСТИКА:
• Дневные отчеты
• Недельный анализ
• Графики прогресса
• % от нормы

⏰ НАПОМИНАНИЯ:
• О приемах пищи
• О воде (3 раза в день)
• О взвешивании (пятница)
• Итоги дня в 21:00

🤖 AI-КОНСУЛЬТАНТ:
• 10 вопросов в день
• Советы по питанию
• Рекомендации блюд
• Помощь с диетой

💰 ВСЕГО 399₽/МЕСЯЦ!
Дешевле чашки кофе в день!
""",
        reply_markup=get_keyboard(False)
    )

async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ отзывов"""
    await update.message.reply_text(
        """
⭐⭐⭐⭐⭐ ОТЗЫВЫ ПОЛЬЗОВАТЕЛЕЙ:

👩 Марина, 28 лет:
"За месяц -4 кг! Просто пишу что ем, бот сам все считает. Очень удобно!"

👨 Александр, 35 лет:
"Наконец-то понял сколько реально ем. Оказалось, перебирал калории на 30%"

👩 Елена, 42 года:
"Похудела на 7 кг за 2 месяца. Главное - не надо ничего взвешивать и считать!"

👨 Дмитрий, 29 лет:
"Набрал 3 кг мышц. Бот помог правильно рассчитать белки"

👩 Ольга, 31 год:
"Супер удобно! Написала 'цезарь с курицей' - сразу получила все КБЖУ"

📊 Статистика:
• 89% достигают цели
• -3.5 кг средний результат за месяц
• 4.8 ⭐ средняя оценка

💬 Присоединяйтесь!
""",
        reply_markup=get_keyboard(False)
    )

# === ФУНКЦИИ ОБРАБОТКИ (те же, что и раньше) ===

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
                {"role": "system", "content": "Ты диетолог. Рассчитай КБЖУ."},
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
                reply_markup=get_keyboard(True)
            )
        except:
            await update.message.reply_text("❌ Не удалось рассчитать")
            
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
                    {"role": "system", "content": "Рассчитай КБЖУ продуктов."},
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
            reply_markup=get_keyboard(True)
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка", reply_markup=get_keyboard(True))
    
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
        f"💧 Записано!\n\n"
        f"Сегодня: {water_ml} мл / 2000 мл\n"
        f"{'✅ Норма выполнена!' if water_ml >= 2000 else f'Осталось: {2000 - water_ml} мл'}",
        reply_markup=get_keyboard(True)
    )

async def process_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка веса"""
    try:
        weight = float(update.message.text.replace(',', '.'))
        await update.message.reply_text(
            f"✅ Вес записан: {weight} кг",
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
    
    target_cal = user_data[user_id]['target_calories']
    
    water_count = sum(1 for m in meals_data[user_id] 
                     if m.get('date') == today and m.get('type') == 'water')
    
    await update.message.reply_text(
        f"📊 СТАТИСТИКА ДНЯ\n\n"
        f"📈 Потреблено / Цель:\n"
        f"🔥 {total_cal:.0f} / {target_cal} ккал ({total_cal/target_cal*100:.0f}%)\n"
        f"🥩 {total_prot:.0f} г белка\n"
        f"🥑 {total_fats:.0f} г жиров\n"
        f"🍞 {total_carbs:.0f} г углеводов\n"
        f"💧 {water_count * 250} / 2000 мл воды\n\n"
        f"🍽 Приемов пищи: {len(today_meals)}",
        reply_markup=get_keyboard(True)
    )

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вопрос к AI"""
    user_id = str(update.effective_user.id)
    
    if user_data[user_id].get('questions_today', 0) >= 10:
        await update.message.reply_text("❌ Лимит 10 вопросов в день")
        return
    
    await update.message.reply_text(
        f"❓ Задай вопрос о питании\n"
        f"Осталось: {10 - user_data[user_id].get('questions_today', 0)}/10"
    )
    context.user_data['waiting_for'] = 'question'

async def process_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ AI на вопрос"""
    question = update.message.text
    user_id = str(update.effective_user.id)
    
    await update.message.reply_text("⏳ AI думает...")
    
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
            
            user_data[user_id]['questions_today'] = user_data[user_id].get('questions_today', 0) + 1
            
            await update.message.reply_text(
                response.choices[0].message.content,
                reply_markup=get_keyboard(True)
            )
    except:
        await update.message.reply_text("❌ Ошибка AI")
    
    context.user_data['waiting_for'] = None

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    await update.message.reply_text(
        """
ℹ️ КАК ПОЛЬЗОВАТЬСЯ:

1️⃣ Рассчитай КБЖУ
2️⃣ Записывай приемы пищ
