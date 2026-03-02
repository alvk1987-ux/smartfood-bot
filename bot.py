import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from openai import OpenAI

# ============ НАСТРОЙКИ ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PREMIUM_CHANNEL_ID = os.getenv("PREMIUM_CHANNEL_ID")  # ID канала SmartFood Premium
PAYWALL_LINK = os.getenv("PAYWALL_LINK", "https://paywall.pw/smartfood")
FREE_MESSAGES_LIMIT = 10

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ OPENAI КЛИЕНТ ============
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.proxyapi.ru/openai/v1"
)

# ============ БАЗА ДАННЫХ (JSON) ============
DB_FILE = "users_db.json"

def load_db():
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    db = load_db()
    user_id = str(user_id)
    if user_id not in db:
        db[user_id] = {
            "free_messages": FREE_MESSAGES_LIMIT,
            "is_premium": False,
            "profile": {},
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_db(db)
    return db[user_id]

def update_user(user_id, data):
    db = load_db()
    db[str(user_id)] = data
    save_db(db)

# ============ ПРОВЕРКА ПОДПИСКИ ============
async def is_premium_member(user_id, context):
    try:
        if not PREMIUM_CHANNEL_ID:
            return False
        member = await context.bot.get_chat_member(
            chat_id=int(PREMIUM_CHANNEL_ID),
            user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# ============ СИСТЕМНЫЙ ПРОМПТ ============
SYSTEM_PROMPT = """Ты — SmartFood, профессиональный AI-нутрициолог. 

Твои правила:
1. Отвечай только на темы питания, диет, КБЖУ, здоровья связанного с едой
2. Если вопрос не по теме — вежливо верни к теме питания
3. Используй научный подход, но объясняй простым языком
4. Используй эмодзи для наглядности
5. Давай конкретные цифры и рекомендации
6. Если пользователь заполнил профиль — учитывай его данные

Формула расчёта КБЖУ:
- Мужчины: BMR = 10 × вес(кг) + 6.25 × рост(см) - 5 × возраст - 5
- Женщины: BMR = 10 × вес(кг) + 6.25 × рост(см) - 5 × возраст - 161
- Коэффициенты активности: 1.2 (минимальная), 1.375 (лёгкая), 1.55 (средняя), 1.725 (высокая), 1.9 (очень высокая)

Отвечай на русском языке. Будь дружелюбным и мотивирующим."""

# ============ КОМАНДА /start ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    
    welcome_text = """🧬 *Добро пожаловать в SmartFood!*

Я — ваш персональный AI-нутрициолог 🥗

*Что я умею:*
📐 Рассчитать КБЖУ
🍽 Проанализировать ваше питание
🎯 Составить план питания
📎 Прочитать фото еды
💬 Ответить на любые вопросы о питании

*Команды:*
/profile — заполнить профиль
/kbju — рассчитать КБЖУ
/plan — план питания на день
/help — помощь

"""
    
    if user["free_messages"] > 0:
        welcome_text += f"🎁 У вас *{user['free_messages']} бесплатных запросов*\n\nПопробуйте — просто напишите вопрос!"
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ============ КОМАНДА /help ============
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """📖 *Как пользоваться SmartFood:*

💬 Просто напишите вопрос о питании:
• «Сколько калорий в банане?»
• «Составь меню на 1500 ккал»
• «Я вешу 80 кг, хочу похудеть»

📎 Отправьте фото еды — я проанализирую

*Команды:*
/profile — заполнить профиль (пол, вес, рост, цель)
/kbju — рассчитать вашу норму КБЖУ
/plan — план питания на день
/status — проверить подписку

/start — начать заново"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ============ КОМАНДА /profile ============
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨 Мужчина", callback_data="gender_male"),
         InlineKeyboardButton("👩 Женщина", callback_data="gender_female")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📋 *Давайте заполним ваш профиль!*\n\nВыберите пол:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ============ ОБРАБОТКА КНОПОК ============
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    data = query.data
    
    if data.startswith("gender_"):
        gender = "мужской" if data == "gender_male" else "женский"
        user["profile"]["gender"] = gender
        update_user(user_id, user)
        await query.edit_message_text(
            f"✅ Пол: {gender}\n\nТеперь напишите ваш *возраст* (число):",
            parse_mode="Markdown"
        )
        context.user_data["awaiting"] = "age"
    
    elif data == "buy_premium":
        keyboard = [[InlineKeyboardButton("💳 Оформить подписку", url=PAYWALL_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💎 *Полный доступ — 399₽/мес*\n\n"
            "✅ Безлимит сообщений\n"
            "✅ Расчёт КБЖУ\n"
            "✅ Анализ питания\n"
            "✅ Планы питания\n"
            "✅ Чтение фото\n"
            "✅ Запоминание профиля\n"
            "✅ Доступ 24/7\n\n"
            "Нажмите кнопку ниже 👇",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# ============ КОМАНДА /kbju ============
async def kbju(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    profile = user.get("profile", {})
    
    if not all(k in profile for k in ["gender", "age", "weight", "height"]):
        await update.message.reply_text(
            "⚠️ Сначала заполните профиль командой /profile\n"
            "Мне нужны: пол, возраст, вес, рост и уровень активности"
        )
        return
    
    prompt = f"""Рассчитай КБЖУ для человека:
Пол: {profile['gender']}
Возраст: {profile['age']}
Вес: {profile['weight']} кг
Рост: {profile['height']} см
Активность: {profile.get('activity', 'средняя')}
Цель: {profile.get('goal', 'поддержание веса')}

Дай точные цифры: калории, белки, жиры, углеводы."""
    
    await send_ai_response(update, context, prompt)

# ============ КОМАНДА /plan ============
async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    profile = user.get("profile", {})
    
    prompt = "Составь план питания на день"
    if profile:
        prompt += f" для человека: вес {profile.get('weight', '?')} кг, цель: {profile.get('goal', 'здоровое питание')}"
    
    await send_ai_response(update, context, prompt)

# ============ КОМАНДА /status ============
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    is_premium = await is_premium_member(user_id, context)
    
    if is_premium:
        text = "💎 *Ваш статус: PREMIUM*\n\n✅ Безлимитный доступ активен!"
    else:
        text = f"🆓 *Ваш статус: Бесплатный*\n\n📊 Осталось запросов: {user['free_messages']}/{FREE_MESSAGES_LIMIT}"
        keyboard = [[InlineKeyboardButton("💎 Купить Premium", callback_data="buy_premium")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        return
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ============ ОТПРАВКА AI ОТВЕТА ============
async def send_ai_response(update, context, user_message):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Проверяем доступ
    is_premium = await is_premium_member(user_id, context)
    
    if not is_premium and user["free_messages"] <= 0:
        keyboard = [[InlineKeyboardButton("💎 Купить Premium — 399₽/мес", callback_data="buy_premium")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔒 *Бесплатные запросы закончились!*\n\n"
            "Вам понравился SmartFood? Оформите подписку\n"
            "и получите безлимитный доступ!\n\n"
            "💎 *Полный доступ — всего 399₽/мес*\n"
            "Это дешевле чашки кофе в день ☕",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return
    
    # Отправляем "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Формируем историю
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Добавляем профиль если есть
    if user.get("profile"):
        profile_text = f"Профиль пользователя: {json.dumps(user['profile'], ensure_ascii=False)}"
        messages.append({"role": "system", "content": profile_text})
    
    # Добавляем последние 10 сообщений из истории
    for msg in user.get("history", [])[-10:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Сохраняем в историю
        user["history"].append({"role": "user", "content": user_message})
        user["history"].append({"role": "assistant", "content": ai_response})
        
        # Оставляем только последние 20 сообщений
        if len(user["history"]) > 20:
            user["history"] = user["history"][-20:]
        
        # Уменьшаем счётчик бесплатных
        if not is_premium:
            user["free_messages"] -= 1
            update_user(user_id, user)
            remaining = user["free_messages"]
            if remaining > 0 and remaining <= 3:
                ai_response += f"\n\n💡 _Осталось бесплатных запросов: {remaining}/{FREE_MESSAGES_LIMIT}_"
            elif remaining == 0:
                ai_response += "\n\n⚠️ _Это был последний бесплатный запрос!_"
        else:
            update_user(user_id, user)
        
        await update.message.reply_text(ai_response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        await update.message.reply_text("😔 Произошла ошибка. Попробуйте ещё раз через минуту.")

# ============ ОБРАБОТКА СООБЩЕНИЙ ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    text = update.message.text
    
    # Обработка заполнения профиля
    awaiting = context.user_data.get("awaiting")
    
    if awaiting == "age":
        try:
            age = int(text)
            user["profile"]["age"] = age
            update_user(user_id, user)
            context.user_data["awaiting"] = "weight"
            await update.message.reply_text(f"✅ Возраст: {age}\n\nТеперь напишите ваш *вес* в кг:", parse_mode="Markdown")
            return
        except ValueError:
            await update.message.reply_text("⚠️ Напишите число (например: 25)")
            return
    
    elif awaiting == "weight":
        try:
            weight = float(text.replace(",", "."))
            user["profile"]["weight"] = weight
            update_user(user_id, user)
            context.user_data["awaiting"] = "height"
            await update.message.reply_text(f"✅ Вес: {weight} кг\n\nТеперь напишите ваш *рост* в см:", parse_mode="Markdown")
            return
        except ValueError:
            await update.message.reply_text("⚠️ Напишите число (например: 75)")
            return
    
    elif awaiting == "height":
        try:
            height = float(text.replace(",", "."))
            user["profile"]["height"] = height
            update_user(user_id, user)
            context.user_data["awaiting"] = "goal"
            keyboard = [
                [InlineKeyboardButton("🔥 Похудеть", callback_data="goal_lose")],
                [InlineKeyboardButton("💪 Набрать массу", callback_data="goal_gain")],
                [InlineKeyboardButton("⚖️ Поддержание", callback_data="goal_maintain")]
            ]
            # Для простоты используем текст
            await update.message.reply_text(
                f"✅ Рост: {height} см\n\n"
                "Какая у вас цель?\n"
                "Напишите: *похудеть*, *набрать массу* или *поддержание*",
                parse_mode="Markdown"
            )
            return
        except ValueError:
            await update.message.reply_text("⚠️ Напишите число (например: 175)")
            return
    
    elif awaiting == "goal":
        user["profile"]["goal"] = text
        update_user(user_id, user)
        context.user_data["awaiting"] = None
        profile = user["profile"]
        await update.message.reply_text(
            f"✅ *Профиль заполнен!*\n\n"
            f"👤 Пол: {profile.get('gender', '?')}\n"
            f"🎂 Возраст: {profile.get('age', '?')}\n"
            f"⚖️ Вес: {profile.get('weight', '?')} кг\n"
            f"📏 Рост: {profile.get('height', '?')} см\n"
            f"🎯 Цель: {profile.get('goal', '?')}\n\n"
            "Теперь используйте /kbju для расчёта нормы! 📐",
            parse_mode="Markdown"
        )
        return
    
    # Обычное сообщение — отправляем AI
    await send_ai_response(update, context, text)

# ============ ОБРАБОТКА ФОТО ============
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Проверяем доступ
    is_premium = await is_premium_member(user_id, context)
    
    if not is_premium and user["free_messages"] <= 0:
        keyboard = [[InlineKeyboardButton("💎 Купить Premium", callback_data="buy_premium")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔒 Бесплатные запросы закончились!\n💎 Оформите подписку для анализа фото.",
            reply_markup=reply_markup
        )
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Получаем фото
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_url = file.file_path
    
    caption = update.message.caption or "Проанализируй это блюдо. Определи продукты и посчитай примерные КБЖУ."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": caption},
                    {"type": "image_url", "image_url": {"url": file_url}}
                ]}
            ],
            max_tokens=1500
        )
        
        ai_response = response.choices[0].message.content
        
        if not is_premium:
            user["free_messages"] -= 1
            update_user(user_id, user)
        
        await update.message.reply_text(ai_response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}")
        await update.message.reply_text("😔 Не удалось проанализировать фото. Попробуйте ещё раз.")

# ============ ЗАПУСК БОТА ============
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("kbju", kbju))
    app.add_handler(CommandHandler("plan", plan))
    app.add_handler(CommandHandler("status", status))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Фото
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Текст
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот SmartFood запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
