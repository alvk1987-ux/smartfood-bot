import os
import logging
import asyncpg
import base64
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import AsyncOpenAI

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
DATABASE_URL = os.getenv("DATABASE_URL") 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

# Оперативная память бота
user_states = {}
last_prompts = {} # Память для кнопки "Другой вариант"
last_recipes = {} # НОВОЕ: Память для кнопки "Заменить продукт"

# === МЕНЮ ===
MENU_FREE = [
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "📸 Калории по фото"],
    ["⭐ Сохраненные рецепты", "👑 Моя подписка"]
]

# === ШАБЛОН ===
SYSTEM_PROMPT = """Ты — элитный шеф-повар и профессиональный диетолог. 
Выдавай рецепты СТРОГО по шаблону ниже. НИКАКИХ вступлений и прощаний. 

Название блюда
«[Вкусное название]»

⏱ Время: [ХХ] минут
🍽 Порции: [Х]

⚖️ КБЖУ на 100 г:
🔥 Калории: [ХХ] ккал
🥩 Белки: [ХХ] г
🥑 Жиры: [ХХ] г
🌾 Углеводы: [ХХ] г

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
                shopping_list TEXT DEFAULT '',
                saved_recipes TEXT DEFAULT ''
            )
        ''')
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
    await update.message.reply_text(f"👨‍🍳 Добро пожаловать, {user.first_name}!\n\nЯ ваш личный Премиальный Шеф. Что будем готовить?", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    # --- ОБРАБОТКА МЕНЮ ---
    if text == "🔍 Найти рецепт":
        user_states[user_id] = "find_recipe"
        await update.message.reply_text("Напишите, какой рецепт вы хотите найти.\n\nНапример: куриный суп, паста карбонара или сырники.")
        return
    elif text == "🧺 Из того, что есть":
        user_states[user_id] = "from_fridge"
        await update.message.reply_text("Напишите продукты, которые у вас есть (через запятую).\n\nНапример: курица, картошка, сыр, чеснок.")
        return
    elif text == "⚡ Быстрый ужин":
        user_states[user_id] = "quick_dinner"
        await update.message.reply_text("Напишите главный продукт для быстрого ужина.\n\nНапример: фарш, филе или грибы.")
        return
    elif text == "🥗 Рецепты для похудения":
        user_states[user_id] = "diet_recipe"
        await update.message.reply_text("Какой лёгкий рецепт вы хотите?\n\nНапример: белковый ужин до 300 ккал или салат с тунцом.")
        return
    elif text == "📸 Калории по фото":
        user_states[user_id] = "photo_calories"
        await update.message.reply_text("📸 Отправьте мне фотографию вашей еды, и я посчитаю примерное КБЖУ на 100 грамм!")
        return
    
    # --- БАЗА ДАННЫХ ---
    elif text == "🛒 Мой список покупок":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT shopping_list FROM users WHERE user_id = $1', user_id)
            await conn.close()
            shop_list = row['shopping_list'] if row and row['shopping_list'] else ""
            if not shop_list.strip():
                await update.message.reply_text("🛒 Ваша корзина пуста.")
            else:
                keyboard = [[InlineKeyboardButton("🗑 Очистить список", callback_data="clear_list")]]
                await update.message.reply_text(f"🛒 Ваш список покупок:\n\n{shop_list}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif text == "⭐ Сохраненные рецепты":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT saved_recipes FROM users WHERE user_id = $1', user_id)
            await conn.close()
            saved = row['saved_recipes'] if row and row['saved_recipes'] else ""
            if not saved.strip():
                await update.message.reply_text("⭐ У вас пока нет сохраненных рецептов.")
            else:
                keyboard = [[InlineKeyboardButton("🗑 Очистить сохраненное", callback_data="clear_saved")]]
                await update.message.reply_text(f"📚 ВАШИ СОХРАНЕННЫЕ РЕЦЕПТЫ:\n{saved}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif text == "👑 Моя подписка":
        await update.message.reply_text("👑 Тариф: Пробный\n⏳ Осталось: 48 часов")
        return

    # --- ГЕНЕРАЦИЯ РЕЦЕПТА (С УЧЕТОМ ЗАМЕНЫ ПРОДУКТА) ---
    state = user_states.get(user_id, "start")
    
    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe", "replace_ingredient"]:
        await context.bot.send_chat_action(chat_id=user_id, action='typing')
        
        # ЛОГИКА ЗАМЕНЫ ИЛИ НОВОГО ЗАПРОСА
        if state == "replace_ingredient":
            old_recipe = last_recipes.get(user_id, "")
            user_prompt = f"Вот прошлый рецепт:\n{old_recipe}\n\nПользователь просит: {text}. Перепиши рецепт, выполнив эту просьбу, сохранив формат и пересчитав КБЖУ."
        else:
            user_prompt = f"Запрос: {text}."
            last_prompts[user_id] = text # Запомнили для кнопки "Другой вариант"

        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
            )
            recipe_text = response.choices[0].message.content
            last_recipes[user_id] = recipe_text # Запомнили сам рецепт для будущей замены!
            
            # КНОПКИ ПОД РЕЦЕПТОМ (ВЕРНУЛ КНОПКУ ЗАМЕНЫ!)
            keyboard = [
                [InlineKeyboardButton("🛒 В список покупок", callback_data="add_to_cart")],
                [InlineKeyboardButton("⭐ Сохранить рецепт", callback_data="save_recipe")],
                [InlineKeyboardButton("🔄 Заменить продукт", callback_data="replace_btn")],
                [InlineKeyboardButton("🎲 Другой вариант", callback_data="another_recipe")]
            ]
            await update.message.reply_text(recipe_text, reply_markup=InlineKeyboardMarkup(keyboard))
            user_states[user_id] = "start" 
            
        except Exception as e:
            await update.message.reply_text(f"Ошибка на кухне: {e}")
    else:
        user_states[user_id] = "find_recipe"
        await handle_message(update, context)

# --- АНАЛИЗ ФОТО ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_states.get(user_id, "start")

    if state != "photo_calories":
        await update.message.reply_text("Если хотите узнать калории, сначала нажмите кнопку «📸 Калории по фото» в меню!")
        return

    await context.bot.send_chat_action(chat_id=user_id, action='typing')
    await update.message.reply_text("🔍 Анализирую фото... Это займет пару секунд.")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Определи, что за еда на фото, и напиши примерное КБЖУ на 100 грамм в формате:\n🍽 Блюдо: ...\n🔥 Калории: ...\n🥩 Белки: ...\n🥑 Жиры: ...\n🌾 Углеводы: ..."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        )
        await update.message.reply_text(response.choices[0].message.content)
        user_states[user_id] = "start" 
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось распознать фото. Ошибка: {e}")

# --- ОБРАБОТКА НАЖАТИЙ НА ПРОЗРАЧНЫЕ КНОПКИ ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_text = query.message.text
    await query.answer() 

    if query.data == "add_to_cart":
        try:
            ingredients = message_text.split("Ингредиенты:\n")[1].split("Приготовление:")[0].strip()
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute("UPDATE users SET shopping_list = shopping_list || '\n\n' || $1 WHERE user_id = $2", ingredients, user_id)
                await conn.close()
            await context.bot.send_message(chat_id=user_id, text="🛒 ✅ Ингредиенты успешно добавлены в ваш список продуктов!")
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ Ошибка: Не удалось найти ингредиенты в тексте рецепта.")

    elif query.data == "save_recipe":
        try:
            full_recipe = f"\n\n➖➖➖➖➖➖➖➖➖➖\n\n{message_text}"
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute("UPDATE users SET saved_recipes = saved_recipes || $1 WHERE user_id = $2", full_recipe, user_id)
                await conn.close()
            await context.bot.send_message(chat_id=user_id, text="⭐ ✅ Полный рецепт сохранен в вашей базе! Вы найдете его в меню «Сохраненные рецепты».")
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ Ошибка сохранения рецепта.")

    # ВЕРНУЛИ ЛОГИКУ КНОПКИ "ЗАМЕНИТЬ ПРОДУКТ"
    elif query.data == "replace_btn":
        user_states[user_id] = "replace_ingredient"
        await context.bot.send_message(
            chat_id=user_id, 
            text="🔄 <b>Напишите, какой продукт нужно заменить.</b>\n\nНапример: замени сливки на сметану, или убери лук.", 
            parse_mode="HTML"
        )

    elif query.data == "another_recipe":
        await context.bot.send_message(chat_id=user_id, text="👨‍🍳 Ищу другой вариант... одну секунду!")
        
        old_prompt = last_prompts.get(user_id, "вкусное блюдо")
        user_prompt = f"Пользователю не понравился прошлый рецепт. Напиши АБСОЛЮТНО ДРУГОЙ рецепт по этому же запросу: {old_prompt}."

        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
            )
            recipe_text = response.choices[0].message.content
            last_recipes[user_id] = recipe_text # Запомнили новый рецепт тоже!
            
            keyboard = [
                [InlineKeyboardButton("🛒 В список покупок", callback_data="add_to_cart")],
                [InlineKeyboardButton("⭐ Сохранить рецепт", callback_data="save_recipe")],
                [InlineKeyboardButton("🔄 Заменить продукт", callback_data="replace_btn")],
                [InlineKeyboardButton("🎲 Другой вариант", callback_data="another_recipe")]
            ]
            await context.bot.send_message(chat_id=user_id, text=recipe_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
             await context.bot.send_message(chat_id=user_id, text=f"Ошибка: {e}")

    elif query.data == "clear_list":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET shopping_list = '' WHERE user_id = $1", user_id)
            await conn.close()
        await query.edit_message_text("🛒 Список продуктов очищен!")

    elif query.data == "clear_saved":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET saved_recipes = '' WHERE user_id = $1", user_id)
            await conn.close()
        await query.edit_message_text("🗑 Ваша база рецептов очищена!")

def main():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()

if __name__ == "__main__":
    main()
