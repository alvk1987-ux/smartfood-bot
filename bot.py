import os
import logging
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import AsyncOpenAI

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
DATABASE_URL = os.getenv("DATABASE_URL") 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

user_states = {}

# === МЕНЮ (Добавили Список покупок) ===
MENU_FREE = [
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "📸 Калории по фото"],
    ["👑 Моя подписка"]
]

# === ШАБЛОН ===
SYSTEM_PROMPT = """Ты — элитный шеф-повар и профессиональный диетолог. 
Твоя задача — выдавать рецепты СТРОГО по следующему шаблону. 
ЗАПРЕЩЕНО писать любые вступления или прощания. Только шаблон:

Название блюда
«[Вкусное название]»

⏱ Время: [ХХ] минут
🍽 Порции: [Х]
🔥 Калории: ~[ХХХ] ккал

Ингредиенты:
• [ингредиент 1] — [количество]
• [ингредиент 2] — [количество]

Приготовление:
1. [Шаг 1]
2. [Шаг 2]"""

async def init_db():
    if not DATABASE_URL: return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                status TEXT DEFAULT 'trial',
                trial_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                shopping_list TEXT DEFAULT ''
            )
        ''')
        # Пытаемся добавить колонку, если ее не было (для обновления старой базы)
        try: await conn.execute("ALTER TABLE users ADD COLUMN shopping_list TEXT DEFAULT '';")
        except: pass
        await conn.close()
    except Exception as e:
        logging.error(f"Ошибка БД: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_states[user.id] = "start"
    
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute('INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING', user.id, user.username)
            await conn.close()
        except: pass

    reply_markup = ReplyKeyboardMarkup(MENU_FREE, resize_keyboard=True)
    await update.message.reply_text(f"👨‍🍳 <b>Добро пожаловать, {user.first_name}!</b>\n\nВыберите, что будем готовить:", reply_markup=reply_markup, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    # --- ОБРАБОТКА МЕНЮ ---
    if text == "🔍 Найти рецепт":
        user_states[user_id] = "find_recipe"
        await update.message.reply_text("📝 <b>Напишите, какой рецепт вы хотите найти.</b>", parse_mode="HTML")
        return
    elif text == "🧺 Из того, что есть":
        user_states[user_id] = "from_fridge"
        await update.message.reply_text("🥦 <b>Напишите продукты, которые у вас есть (через запятую).</b>", parse_mode="HTML")
        return
    elif text == "⚡ Быстрый ужин":
        user_states[user_id] = "quick_dinner"
        await update.message.reply_text("⏱ <b>Напишите основной продукт для быстрого рецепта.</b>", parse_mode="HTML")
        return
    elif text == "🥗 Рецепты для похудения":
        user_states[user_id] = "diet_recipe"
        await update.message.reply_text("🌿 <b>Напишите, какой лёгкий рецепт хотите (например: диетический ужин).</b>", parse_mode="HTML")
        return
    
    # === НОВАЯ ФИЧА: ПОСМОТРЕТЬ СПИСОК ПОКУПОК ===
    elif text == "🛒 Мой список покупок":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT shopping_list FROM users WHERE user_id = $1', user_id)
            await conn.close()
            
            shop_list = row['shopping_list'] if row and row['shopping_list'] else ""
            if shop_list.strip() == "":
                await update.message.reply_text("🛒 <b>Ваша корзина пуста.</b>\nНажмите «🛒 В список» под любым рецептом!", parse_mode="HTML")
            else:
                # Кнопка очистки корзины
                keyboard = [[InlineKeyboardButton("🗑 Очистить список", callback_data="clear_list")]]
                await update.message.reply_text(f"🛒 <b>Ваш список покупок:</b>\n\n{shop_list}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    elif text == "📸 Калории по фото" or text == "👑 Моя подписка":
        await update.message.reply_text("⚙️ Эта функция в разработке!")
        return

    # --- ГЕНЕРАЦИЯ РЕЦЕПТА ---
    state = user_states.get(user_id, "start")
    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe"]:
        await context.bot.send_chat_action(chat_id=user_id, action='typing')
        user_prompt = f"Запрос: {text}."
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
            )
            recipe_text = response.choices[0].message.content
            
            # НОВЫЕ СУПЕР-КНОПКИ
            keyboard = [
                [InlineKeyboardButton("🖼 Показать как это выглядит", callback_data="gen_image")],
                [InlineKeyboardButton("🛒 В список покупок", callback_data="add_to_cart")],
                [InlineKeyboardButton("🔄 Другой вариант", callback_data=f"another")]
            ]
            await update.message.reply_text(recipe_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    else:
        await update.message.reply_text("👇 Пожалуйста, сначала выберите действие в меню!")

# --- ОБРАБОТКА НАЖАТИЙ НА ПРОЗРАЧНЫЕ КНОПКИ ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_text = query.message.text
    await query.answer() 

    # 1. ГЕНЕРАЦИЯ КАРТИНКИ
    if query.data == "gen_image":
        # Достаем название блюда из текста рецепта
        try:
            recipe_name = message_text.split("«")[1].split("»")[0]
        except:
            recipe_name = "вкусное блюдо ресторанной подачи"
            
        await context.bot.send_message(chat_id=user_id, text=f"🎨 <i>Рисую аппетитное фото для «{recipe_name}»...\n(Это может занять 10-15 секунд)</i>", parse_mode="HTML")
        
        try:
            # Запрашиваем картинку у DALL-E 3
            image_response = await client.images.generate(
                model="dall-e-3",
                prompt=f"Профессиональное, очень аппетитное фуд-фото. Блюдо: {recipe_name}. Ресторанная подача, красивый свет, вид сверху под углом, высокое качество.",
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = image_response.data[0].url
            await context.bot.send_photo(chat_id=user_id, photo=image_url, caption=f"📸 <b>{recipe_name}</b>", parse_mode="HTML")
        except Exception as e:
            await context.bot.send_message(chat_id=user_id, text="😔 Не удалось сгенерировать фото. Возможно, закончился баланс.")

    # 2. ДОБАВЛЕНИЕ В СПИСОК ПОКУПОК
    elif query.data == "add_to_cart":
        # Умный вырез ингредиентов из текста
        try:
            ingredients = message_text.split("Ингредиенты:\n")[1].split("Приготовление:")[0].strip()
            
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                # Добавляем новые ингредиенты к старым
                await conn.execute("UPDATE users SET shopping_list = shopping_list || '\n\n' || $1 WHERE user_id = $2", ingredients, user_id)
                await conn.close()
                
            await query.answer("✅ Продукты добавлены в ваш список покупок!", show_alert=True)
        except:
            await query.answer("❌ Не удалось найти ингредиенты в тексте.", show_alert=True)

    # 3. ОЧИСТКА СПИСКА ПОКУПОК
    elif query.data == "clear_list":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET shopping_list = '' WHERE user_id = $1", user_id)
            await conn.close()
        # Меняем текст сообщения на "Пусто"
        await query.edit_message_text("🛒 <b>Ваша корзина очищена!</b>", parse_mode="HTML")

def main():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()

if __name__ == "__main__":
    main()
