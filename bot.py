import os
import logging
import asyncpg
import base64
import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import AsyncOpenAI

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
DATABASE_URL = os.getenv("DATABASE_URL") 
ADMIN_ID = 230764474  

# ВАША ССЫЛКА НА ГРУППУ
GROUP_LINK = "https://t.me/premium_chef_ru" 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

user_states = {}
last_prompts = {} 
last_recipes = {} 

# === ОБНОВЛЕННОЕ МЕНЮ С НОВОЙ КНОПКОЙ ===
MENU_FREE = [
    ["📖 Как общаться с Шефом"],
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "📸 Калории по фото"],
    ["⭐ Сохраненные рецепты", "👑 Моя подписка"],
    ["💬 Наш Чат-Форум"] 
]

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
        try: await conn.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        except: pass
        try: await conn.execute("ALTER TABLE users ADD COLUMN has_premium BOOLEAN DEFAULT FALSE;")
        except: pass
        await conn.close()
    except Exception as e:
        logging.error(f"Ошибка БД: {e}")

async def check_access(user_id):
    if user_id == ADMIN_ID: return True 
    if not DATABASE_URL: return True
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT created_at, has_premium FROM users WHERE user_id = $1', user_id)
    await conn.close()
    if not row: return True
    if row['has_premium']: return True 
    diff = datetime.datetime.now() - row['created_at']
    return (diff.total_seconds() / 3600) < 48 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_states[user.id] = "start"
    
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute('''INSERT INTO users (user_id, username, created_at, has_premium) 
                                  VALUES ($1, $2, CURRENT_TIMESTAMP, FALSE) ON CONFLICT DO NOTHING''', 
                               user.id, user.username)
            await conn.close()
        except: pass

    reply_markup = ReplyKeyboardMarkup(MENU_FREE, resize_keyboard=True)
    
    await update.message.reply_text(f"👨‍🍳 Добро пожаловать, {user.first_name}!\n\nЯ ваш личный Премиальный Шеф. Что будем готовить?\n\n🎁 <i>Вам начислено 48 часов бесплатного VIP-доступа!</i>", reply_markup=reply_markup, parse_mode="HTML")
    
    inline_kb = [[InlineKeyboardButton("🚀 Перейти в Комьюнити", url=GROUP_LINK)]]
    await update.message.reply_text("👇 <b>Обязательно подпишитесь на наш Чат-Форум!</b>\n\nТам мы делимся кулинарными шедеврами, обсуждаем идеи для бота и дарим промокоды на бесплатную подписку! Присоединяйтесь к нашей Кухне 🥗", reply_markup=InlineKeyboardMarkup(inline_kb), parse_mode="HTML")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID: return 
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval('SELECT COUNT(*) FROM users')
    await conn.close()
    keyboard = [[InlineKeyboardButton("🎁 Выдать VIP-доступ", callback_data="give_premium")]]
    await update.message.reply_text(f"👑 <b>ПАНЕЛЬ ВЛАДЕЛЬЦА</b>\n\n👥 Всего пользователей: <b>{count}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    state = user_states.get(user_id, "start")

    # НОВАЯ КНОПКА: Инструкция
    if text == "📖 Как общаться с Шефом":
        await update.message.reply_text(
            "👨‍🍳 <b>Секрет идеального блюда кроется в деталях!</b>\n\n"
            "Я — нейро-шеф. Чем интереснее вы опишете, что хотите, тем вкуснее будет результат!\n\n"
            "❌ <b>Скучный запрос:</b> <i>жареная картошка с мясом</i>\n"
            "✅ <b>Ресторанный запрос:</b> <i>как приготовить картошку с говядиной как в дорогом ресторане, с необычным сливочным соусом и красивой подачей?</i>\n\n"
            "❌ <b>Скучный запрос:</b> <i>омлет</i>\n"
            "✅ <b>Ресторанный запрос:</b> <i>французский омлет с трюфельным маслом, шпинатом и сыром бри за 10 минут</i>\n\n"
            "💡 <b>Лайфхаки от Шефа:</b>\n"
            "• Указывайте стиль кухни (итальянская, паназиатская).\n"
            "• Пишите повод (романтический ужин, детский праздник).\n"
            "• Просите добавить необычные специи или маринад.\n\n"
            "Жмите «🔍 Найти рецепт» и дайте волю фантазии! 🪄",
            parse_mode="HTML"
        )
        return

    if state == "waiting_for_user_id" and user_id == ADMIN_ID:
        try:
            target_id = int(text.strip())
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET has_premium = TRUE WHERE user_id = $1", target_id)
            await conn.close()
            await update.message.reply_text(f"✅ VIP успешно выдан пользователю {target_id}!")
            user_states[user_id] = "start"
        except:
            await update.message.reply_text("❌ Ошибка. Пришлите только цифры ID.")
        return

    if text == "💬 Наш Чат-Форум":
        inline_kb = [[InlineKeyboardButton("🚀 Перейти в Комьюнити Шефа", url=GROUP_LINK)]]
        await update.message.reply_text(
            "👨‍🍳 <b>Добро пожаловать на нашу Кухню!</b>\n\n"
            "У нас есть уютный чат-форум, где мы:\n"
            "📸 Делимся фотографиями приготовленных блюд\n"
            "💡 Обсуждаем новые фишки для бота\n"
            "🎁 Разыгрываем VIP-подписки\n\n"
            "Присоединяйтесь, там очень вкусно и интересно! 👇", 
            reply_markup=InlineKeyboardMarkup(inline_kb), 
            parse_mode="HTML"
        )
        return

    if text == "👑 Моя подписка":
        # ДОБАВЛЕНЫ РЕКВИЗИТЫ ДЛЯ РОБОКАССЫ
        legal_info = "\n\n📝 <b>Официальная информация:</b>\nИП Ширякин О.Ю.\nИНН: 732705248482\nEmail: al.smm-manager@yandex.ru"
        
        if user_id == ADMIN_ID:
            await update.message.reply_text(f"👑 <b>Тариф:</b> Владелец проекта\n⏳ <b>Осталось:</b> БЕЗЛИМИТ НАВСЕГДА{legal_info}", parse_mode="HTML")
            return
        if DATABASE_URL:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow('SELECT created_at, has_premium FROM users WHERE user_id = $1', user_id)
            await conn.close()
            if row['has_premium']:
                await update.message.reply_text(f"👑 <b>Тариф:</b> VIP Безлимит\n⏳ <b>Осталось:</b> Навсегда{legal_info}", parse_mode="HTML")
            else:
                diff = datetime.datetime.now() - row['created_at']
                hours_passed = diff.total_seconds() / 3600
                if hours_passed >= 48:
                    await update.message.reply_text(f"👑 <b>Тариф:</b> Истек ❌\n⏳ Ваш пробный период завершен.\n\nДоступ к боту заблокирован. Оформите подписку!{legal_info}", parse_mode="HTML")
                else:
                    hours_left = int(48 - hours_passed)
                    await update.message.reply_text(f"👑 <b>Тариф:</b> Пробный VIP\n⏳ <b>Осталось:</b> {hours_left} часов{legal_info}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"👑 <b>Тариф:</b> Базовый\n💳 Для оплаты подписки перейдите по ссылке (в разработке).{legal_info}", parse_mode="HTML")
        return

    has_access = await check_access(user_id)
    if not has_access:
        await update.message.reply_text("⏳ <b>Ваш бесплатный период (48 часов) подошел к концу!</b>\n\nК сожалению, доступ к генерации рецептов, вашей сохраненной базе и списку покупок закрыт 🔒\n\nЧтобы продолжить пользоваться Шефом, перейдите в меню «👑 Моя подписка».\n\n<i>💬 Либо загляните в наш Чат-Форум (там можно получить скидку)!</i>", parse_mode="HTML")
        return

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
        else:
             await update.message.reply_text("🛒 Ваша корзина пока пуста. (Функция сохранения заработает после подключения базы данных).")
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
        else:
            await update.message.reply_text("⭐ У вас пока нет сохраненных рецептов. (Функция заработает после подключения базы данных).")
        return
    
    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe", "replace_ingredient"]:
        await context.bot.send_chat_action(chat_id=user_id, action='typing')
        if state == "replace_ingredient":
            old_recipe = last_recipes.get(user_id, "")
            user_prompt = f"Вот прошлый рецепт:\n{old_recipe}\n\nПользователь просит: {text}. Перепиши рецепт, выполнив эту просьбу, сохранив формат и пересчитав КБЖУ."
        else:
            user_prompt = f"Запрос: {text}."
            last_prompts[user_id] = text 

        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
            )
            recipe_text = response.choices[0].message.content
            last_recipes[user_id] = recipe_text 
            
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

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    has_access = await check_access(user_id)
    if not has_access:
        await update.message.reply_text("⏳ <b>Ваш бесплатный период (48 часов) подошел к концу!</b>\n\nФункция распознавания еды по фото заблокирована. Оформите подписку!", parse_mode="HTML")
        return

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

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_text = query.message.text
    await query.answer() 

    if query.data == "give_premium":
        if user_id == ADMIN_ID:
            user_states[user_id] = "waiting_for_user_id"
            await context.bot.send_message(chat_id=user_id, text="👇 <b>Пришлите ID пользователя (только цифры)</b>, которому вы хотите навсегда включить Премиум:", parse_mode="HTML")
        return

    has_access = await check_access(user_id)
    if not has_access:
        await context.bot.send_message(chat_id=user_id, text="⏳ Ваш бесплатный период завершен. Функция заблокирована 🔒")
        return

    if query.data == "add_to_cart":
        try:
            ingredients = message_text.split("Ингредиенты:\n")[1].split("Приготовление:")[0].strip()
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute("UPDATE users SET shopping_list = shopping_list || '\n\n' || $1 WHERE user_id = $2", ingredients, user_id)
                await conn.close()
                await context.bot.send_message(chat_id=user_id, text="🛒 ✅ Ингредиенты добавлены в список продуктов!")
            else:
                 await context.bot.send_message(chat_id=user_id, text="🛒 Функция сохранения заработает после настройки базы данных!")
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ Ошибка: Не удалось найти ингредиенты.")

    elif query.data == "save_recipe":
        try:
            full_recipe = f"\n\n➖➖➖➖➖➖➖➖➖➖\n\n{message_text}"
            if DATABASE_URL:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute("UPDATE users SET saved_recipes = saved_recipes || $1 WHERE user_id = $2", full_recipe, user_id)
                await conn.close()
                await context.bot.send_message(chat_id=user_id, text="⭐ ✅ Рецепт сохранен в базе!")
            else:
                await context.bot.send_message(chat_id=user_id, text="⭐ Функция сохранения заработает после настройки базы данных!")
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ Ошибка сохранения.")

    elif query.data == "replace_btn":
        user_states[user_id] = "replace_ingredient"
        await context.bot.send_message(chat_id=user_id, text="🔄 <b>Напишите, какой продукт нужно заменить.</b>", parse_mode="HTML")

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
            last_recipes[user_id] = recipe_text 
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
    app.add_handler(CommandHandler("admin", admin_panel)) 
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()

if __name__ == "__main__":
    main()
