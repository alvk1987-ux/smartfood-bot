import os
import logging
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import AsyncOpenAI

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
DATABASE_URL = os.getenv("DATABASE_URL") 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

# Оперативная память бота (чтобы помнить контекст диалога)
user_states = {}
last_recipes = {} # Запоминаем последний выданный рецепт для функции "Заменить ингредиент"
last_prompts = {} # Запоминаем последний запрос для кнопки "Другой вариант"

# === МЕНЮ ===
MENU_FREE = [
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "⏳ Успеть за..."],
    ["⭐ Сохраненные рецепты", "👑 Моя подписка"]
]

# === НОВЫЙ СТРОГИЙ ШАБЛОН С КБЖУ НА 100Г ===
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
        # Добавляем колонку для сохраненных рецептов, если ее не было
        try: await conn.execute("ALTER TABLE users ADD COLUMN saved_recipes TEXT DEFAULT '';")
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
    await update.message.reply_text(f"👨‍🍳 <b>Добро пожаловать, {user.first_name}!</b>\n\nЯ ваш личный Премиальный Шеф. Что будем готовить?", reply_markup=reply_markup, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    # --- ОБРАБОТКА МЕНЮ С КОПИРУЕМЫМИ ПРИМЕРАМИ (<code>) ---
    if text == "🔍 Найти рецепт":
        user_states[user_id] = "find_recipe"
        await update.message.reply_text("📝 <b>Какой рецепт ищем?</b>\n\n👇 <i>Нажмите на пример, чтобы скопировать:</i>\n<code>Куриный суп с лапшой</code>\n<code>Паста Карбонара</code>\n<code>Сырники из творога</code>", parse_mode="HTML")
        return
    elif text == "🧺 Из того, что есть":
        user_states[user_id] = "from_fridge"
        await update.message.reply_text("🥦 <b>Напишите продукты через запятую.</b>\n\n👇 <i>Нажмите на пример, чтобы скопировать:</i>\n<code>Курица, картошка, сыр, чеснок</code>\n<code>Яйца, помидоры, хлеб</code>", parse_mode="HTML")
        return
    elif text == "⚡ Быстрый ужин":
        user_states[user_id] = "quick_dinner"
        await update.message.reply_text("⚡ <b>Главный продукт для быстрого ужина?</b>\n\n👇 <i>Нажмите на пример:</i>\n<code>Фарш</code>\n<code>Куриное филе</code>\n<code>Грибы</code>", parse_mode="HTML")
        return
    elif text == "🥗 Рецепты для похудения":
        user_states[user_id] = "diet_recipe"
        await update.message.reply_text("🌿 <b>Какой лёгкий рецепт хотите?</b>\n\n👇 <i>Нажмите на пример:</i>\n<code>Белковый ужин до 300 ккал</code>\n<code>Салат с тунцом и авокадо</code>", parse_mode="HTML")
        return
    elif text == "⏳ Успеть за...":
        user_states[user_id] = "time_limit"
        await update.message.reply_text("⏳ <b>Сколько минут у вас есть на готовку?</b>\n\n👇 <i>Нажмите на пример:</i>\n<code>15 минут</code>\n<code>30 минут</code>", parse_mode="HTML")
        return
    
    # --- БАЗА ДАННЫХ: СПИСОК ПОКУПОК ---
    elif text == "🛒 Мой список покупок":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT shopping_list FROM users WHERE user_id = $1', user_id)
            await conn.close()
            shop_list = row['shopping_list'] if row and row['shopping_list'] else ""
            if not shop_list.strip():
                await update.message.reply_text("🛒 <b>Ваша корзина пуста.</b>", parse_mode="HTML")
            else:
                keyboard = [[InlineKeyboardButton("🗑 Очистить список", callback_data="clear_list")]]
                await update.message.reply_text(f"🛒 <b>Список покупок:</b>\n\n{shop_list}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    # --- БАЗА ДАННЫХ: СОХРАНЕННЫЕ РЕЦЕПТЫ ---
    elif text == "⭐ Сохраненные рецепты":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT saved_recipes FROM users WHERE user_id = $1', user_id)
            await conn.close()
            saved = row['saved_recipes'] if row and row['saved_recipes'] else ""
            if not saved.strip():
                await update.message.reply_text("⭐ <b>У вас пока нет сохраненных блюд.</b>\nНажимайте «⭐ Сохранить» под рецептами!", parse_mode="HTML")
            else:
                keyboard = [[InlineKeyboardButton("🗑 Очистить избранное", callback_data="clear_saved")]]
                await update.message.reply_text(f"📚 <b>Ваша кулинарная книга:</b>\n{saved}\n\n<i>💡 Просто напишите мне название любого блюда отсюда, и я напомню рецепт!</i>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    elif text == "👑 Моя подписка":
        await update.message.reply_text("👑 <b>Тариф:</b> Пробный\n⏳ <b>Осталось:</b> 48 часов", parse_mode="HTML")
        return

    # --- ЛОГИКА ГЕНЕРАЦИИ (ИДЕМ В НЕЙРОСЕТЬ) ---
    state = user_states.get(user_id, "start")
    
    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe", "time_limit", "replace_ingredient", "another"]:
        await context.bot.send_chat_action(chat_id=user_id, action='typing')
        
        # Формируем запрос
        if state == "replace_ingredient":
            old_recipe = last_recipes.get(user_id, "")
            user_prompt = f"Вот прошлый рецепт:\n{old_recipe}\n\nПользователь просит: {text}. Перепиши рецепт, заменив этот ингредиент, сохранив формат и пересчитав КБЖУ."
        elif state == "time_limit":
            user_prompt = f"Придумай вкусный рецепт, который гарантированно можно приготовить за {text}."
        elif state == "another":
            # Берем прошлый запрос из памяти
            old_prompt = last_prompts.get(user_id, text)
            user_prompt = f"Пользователю не понравился прошлый вариант. Дай АБСОЛЮТНО ДРУГОЙ рецепт по этому же запросу: {old_prompt}."
        else:
            user_prompt = f"Запрос: {text}."
            last_prompts[user_id] = text # Запоминаем оригинальный запрос для кнопки "Другой вариант"

        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
            )
            recipe_text = response.choices[0].message.content
            last_recipes[user_id] = recipe_text # Запоминаем рецепт для замены ингредиентов
            
            # КНОПКИ ПОД РЕЦЕПТОМ (Умная сетка)
            keyboard = [
                [InlineKeyboardButton("🛒 В список покупок", callback_data="add_to_cart"), InlineKeyboardButton("⭐ Сохранить", callback_data="save_recipe")],
                [InlineKeyboardButton("🔄 Заменить ингредиент", callback_data="replace_btn")],
                [InlineKeyboardButton("🎲 Другой вариант", callback_data="another_recipe")]
            ]
            await update.message.reply_text(recipe_text, reply_markup=InlineKeyboardMarkup(keyboard))
            user_states[user_id] = "start" # Сбрасываем состояние
            
        except Exception as e:
            await update.message.reply_text(f"Ошибка на кухне: {e}")
    else:
        # Если человек просто пишет текст без кнопок, ищем это как рецепт
        user_states[user_id] = "find_recipe"
        await handle_message(update, context)

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
            await query.answer("✅ Добавлено в корзину!", show_alert=True)
        except:
            await query.answer("❌ Не удалось найти ингредиенты.", show_alert=True)

    elif query.data == "save_recipe":
        try:
            # Вытаскиваем название рецепта и КБЖУ для красивого списка
            recipe_name = message_text.split("«")[1].split("»")[0]
            calories = message_text.split("🔥 Калории: ")[1].split(" ккал")[0]
            save_text = f"\n• <b>{recipe_name}</b> ({calories} ккал)"
            
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute("UPDATE users SET saved_recipes = saved_recipes || $1 WHERE user_id = $2", save_text, user_id)
                await conn.close()
            await query.answer("⭐ Рецепт сохранен в вашу книгу!", show_alert=True)
        except:
            await query.answer("❌ Ошибка сохранения.", show_alert=True)

    elif query.data == "replace_btn":
        user_states[user_id] = "replace_ingredient"
        await context.bot.send_message(chat_id=user_id, text="🔄 <b>Какой ингредиент заменить?</b>\n\n👇 <i>Нажмите, чтобы скопировать:</i>\n<code>Замени сливки на молоко</code>\n<code>Убери лук и чеснок</code>", parse_mode="HTML")
        
    elif query.data == "another_recipe":
        user_states[user_id] = "another"
        # Имитируем отправку сообщения пользователем, чтобы запустить генерацию
        update.message = query.message 
        update.message.from_user = query.from_user
        await handle_message(update, context)

    elif query.data == "clear_list":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET shopping_list = '' WHERE user_id = $1", user_id)
            await conn.close()
        await query.edit_message_text("🛒 <b>Корзина очищена!</b>", parse_mode="HTML")

    elif query.data == "clear_saved":
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET saved_recipes = '' WHERE user_id = $1", user_id)
            await conn.close()
        await query.edit_message_text("🗑 <b>Книга рецептов очищена!</b>", parse_mode="HTML")

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
