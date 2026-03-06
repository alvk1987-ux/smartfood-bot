import os
import logging
import asyncpg
import base64
import datetime
import re
import time
import hashlib
import urllib.parse
import asyncio
from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import AsyncOpenAI

# === НАСТРОЙКИ ТЕЛЕГРАМ И БД ===
TELEGRAM_TOKEN = "8605434358:AAGBtCzenMeZOGMKJsbMXgY78SnFUC7beL4"
OPENAI_API_KEY = "sk-ZLVREHzoyNGeM8hTTkDEqP4ErNAPiH2y"
DATABASE_URL = "postgresql://botuser:botpass123@127.0.0.1/botdb" 
ADMIN_ID = 230764474  
GROUP_LINK = "https://t.me/premium_chef_ru" 

# === НАСТРОЙКИ РОБОКАССЫ ===
ROBOKASSA_SHOP_ID = "chefpremium"
ROBOKASSA_PASS_1 = "K70v46d5sgUEuupTKbMw"
ROBOKASSA_PASS_2 = "l1ONgktiTu3kocNc94v1"
ROBOKASSA_TEST_PASS_1 = "nl9Blk5uVX35zO3xaeoE"
ROBOKASSA_TEST_PASS_2 = "Taf1jpWp2Jr1w4eMz3sC"

# БОЕВОЙ РЕЖИМ ВКЛЮЧЕН (False)
IS_TEST_MODE = False  

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.proxyapi.ru/openai/v1")

user_states = {}
last_prompts = {} 
last_recipes = {} 

# ДОБАВЛЕНА КНОПКА ПРАВОВОЙ ИНФОРМАЦИИ ДЛЯ РОБОКАССЫ
MENU_FREE = [
    ["📖 Как общаться с Шефом"],
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "📸 Калории по фото"],
    ["⭐ Сохраненные рецепты", "👑 Моя подписка"],
    ["💬 Наш Чат-Форум", "📜 Правовая информация"] 
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

def get_payment_link(user_id):
    amount = "249.00" 
    inv_id = int(time.time()) % 100000000
    description = "VIP Подписка на Premium Шеф"
    pass1 = ROBOKASSA_TEST_PASS_1 if IS_TEST_MODE else ROBOKASSA_PASS_1
    signature_str = f"{ROBOKASSA_SHOP_ID}:{amount}:{inv_id}:{pass1}:Shp_chatId={user_id}"
    hash_md5 = hashlib.md5(signature_str.encode()).hexdigest()
    desc_encoded = urllib.parse.quote(description)
    url = (f"https://auth.robokassa.ru/Merchant/Index.aspx?"
           f"MerchantLogin={ROBOKASSA_SHOP_ID}&OutSum={amount}&InvId={inv_id}&"
           f"Description={desc_encoded}&SignatureValue={hash_md5}&Shp_chatId={user_id}")
    if IS_TEST_MODE: url += "&IsTest=1"
    return url

async def robokassa_handler(request):
    data = await request.post()
    out_sum = data.get("OutSum", "0")
    inv_id = data.get("InvId", "0")
    signature = data.get("SignatureValue", "")
    user_id = data.get("Shp_chatId")
    pass2 = ROBOKASSA_TEST_PASS_2 if IS_TEST_MODE else ROBOKASSA_PASS_2
    
    my_sig = f"{out_sum}:{inv_id}:{pass2}:Shp_chatId={user_id}"
    my_hash = hashlib.md5(my_sig.encode()).hexdigest().upper()
    
    if my_hash == signature.upper():
        if DATABASE_URL and user_id:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET has_premium = TRUE WHERE user_id = $1", int(user_id))
            await conn.close()
        
        bot = request.app['bot']
        try:
            await bot.send_message(
                chat_id=int(user_id), 
                text="🎉 <b>Оплата успешно получена!</b>\n\nВам активирован VIP-доступ. Приятного пользования Шефом!",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить: {e}")
        return web.Response(text=f"OK{inv_id}")
    else:
        return web.Response(text="BAD SIGNATURE", status=400)

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
    total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
    vip_users = await conn.fetchval('SELECT COUNT(*) FROM users WHERE has_premium = TRUE')
    await conn.close()
    
    keyboard = [
        [InlineKeyboardButton("🎁 Выдать VIP", callback_data="give_premium")],
        [InlineKeyboardButton("🗑 Удалить пользователя", callback_data="delete_user")]
    ]
    await update.message.reply_text(
        f"👑 <b>ПАНЕЛЬ ВЛАДЕЛЬЦА</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💎 Купили VIP: <b>{vip_users}</b>", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    state = user_states.get(user_id, "start")

    # --- ТЕКСТ ДЛЯ РОБОКАССЫ ---
    if text == "📜 Правовая информация":
        legal_text = (
            "📝 <b>Юридическая и контактная информация</b>\n"
            "• Самозанятый: Ширякин Олег Юрьевич\n"
            "• ИНН: 732705248482\n"
            "• Контакты (техподдержка): al.smm-manager@yandex.ru\n\n"
            "📦 <b>Заказ, Оплата и Оказание услуг</b>\n"
            "• Заказ: оформляется в меню бота нажатием кнопки «Оплатить VIP». Сроки исполнения — мгновенно.\n"
            "• Оплата: банковскими картами или по СБП через защищенное соединение сервиса Robokassa.\n"
            "• Оказание услуг: услуга предоставляется в цифровом виде. VIP-доступ к функционалу бота активируется автоматически сразу после успешной оплаты.\n\n"
            "🔄 <b>Политика возврата средств</b>\n"
            "• Покупатель вправе отказаться от услуги.\n"
            "• <b>Алгоритм возврата:</b> для возврата средств необходимо направить письменное обращение в свободной форме на email: al.smm-manager@yandex.ru.\n"
            "• Срок рассмотрения заявки — до 3 рабочих дней.\n"
            "• Возврат производится в полном объеме. Возврат производится БЕЗ вычета комиссии платежного сервиса или банка. Денежные средства возвращаются на ту же карту, с которой была произведена оплата, в течение 3-10 рабочих дней.\n\n"
            "🔐 <b>Политика обработки персональных данных</b>\n"
            "• Бот собирает только публичный ID пользователя в Telegram для идентификации подписки. Мы не запрашиваем и не храним платежные данные (они обрабатываются исключительно на стороне Робокассы)."
        )
        await update.message.reply_text(legal_text, parse_mode="HTML")
        return

    if text == "📖 Как общаться с Шефом":
        await update.message.reply_text("👨‍🍳 <b>Секрет идеального блюда кроется в деталях!</b>\n\nЯ — ваш личный профессиональный Шеф. Чем интереснее вы опишете, что хотите, тем вкуснее будет результат!\n\n❌ <b>Скучный запрос:</b> <i>жареная картошка с мясом</i>\n✅ <b>Ресторанный запрос:</b> <i>как приготовить картошку с говядиной как в дорогом ресторане, с необычным сливочным соусом и красивой подачей?</i>\n\nЖмите «🔍 Найти рецепт» и дайте волю фантазии! 🪄", parse_mode="HTML")
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

    if state == "waiting_for_delete_id" and user_id == ADMIN_ID:
        try:
            target_id = int(text.strip())
            if target_id == ADMIN_ID:
                await update.message.reply_text("❌ Вы не можете удалить сами себя!")
                user_states[user_id] = "start"
                return
            conn = await asyncpg.connect(DATABASE_URL)
            deleted = await conn.execute("DELETE FROM users WHERE user_id = $1", target_id)
            await conn.close()
            if deleted == "DELETE 0":
                await update.message.reply_text("⚠️ Пользователь с таким ID не найден в базе.")
            else:
                await update.message.reply_text(f"✅ Пользователь {target_id} навсегда удален из базы бота!")
            user_states[user_id] = "start"
        except:
            await update.message.reply_text("❌ Ошибка. Пришлите только цифры ID.")
        return

    if text == "💬 Наш Чат-Форум":
        inline_kb = [[InlineKeyboardButton("🚀 Перейти в Комьюнити Шефа", url=GROUP_LINK)]]
        await update.message.reply_text("👨‍🍳 <b>Добро пожаловать на нашу Кухню!</b>\n\nПрисоединяйтесь, там очень вкусно и интересно! 👇", reply_markup=InlineKeyboardMarkup(inline_kb), parse_mode="HTML")
        return

    if text == "👑 Моя подписка":
        pricing_info = "\n\n💎 <b>Условия подписки:</b>\nПервые 48 часов — БЕСПЛАТНО\nДалее — всего 249 рублей в месяц."
        if user_id == ADMIN_ID:
            await update.message.reply_text(f"👑 <b>Тариф:</b> Владелец проекта\n⏳ <b>Осталось:</b> БЕЗЛИМИТ НАВСЕГДА\n{pricing_info}", parse_mode="HTML")
            return
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow('SELECT created_at, has_premium FROM users WHERE user_id = $1', user_id)
        await conn.close()
        if row and row['has_premium']:
            await update.message.reply_text(f"👑 <b>Тариф:</b> VIP Доступ\n⏳ <b>Осталось:</b> Оплачено ✅\n{pricing_info}", parse_mode="HTML")
        else:
            payment_url = get_payment_link(user_id)
            pay_keyboard = [[InlineKeyboardButton("💎 Оплатить VIP (249 руб)", url=payment_url)]]
            diff = datetime.datetime.now() - row['created_at']
            hours_passed = diff.total_seconds() / 3600
            if hours_passed >= 48:
                await update.message.reply_text(f"👑 <b>Тариф:</b> Истек ❌\n⏳ Ваш бесплатный период завершен.\n\nОформите подписку, чтобы продолжить!{pricing_info}", reply_markup=InlineKeyboardMarkup(pay_keyboard), parse_mode="HTML")
            else:
                hours_left = int(48 - hours_passed)
                await update.message.reply_text(f"👑 <b>Тариф:</b> Пробный VIP\n⏳ <b>Осталось:</b> {hours_left} часов{pricing_info}", reply_markup=InlineKeyboardMarkup(pay_keyboard), parse_mode="HTML")
        return

    has_access = await check_access(user_id)
    if not has_access:
        await update.message.reply_text("⏳ <b>Ваш бесплатный период подошел к концу!</b>\n\nК сожалению, доступ к генерации рецептов, вашей базе и списку закрыт 🔒\n\nЧтобы продолжить пользоваться Шефом, перейдите в меню «👑 Моя подписка».", parse_mode="HTML")
        return

    if text == "🔍 Найти рецепт":
        user_states[user_id] = "find_recipe"
        await update.message.reply_text("Напишите, какой рецепт вы хотите найти.")
        return
    elif text == "🧺 Из того, что есть":
        user_states[user_id] = "from_fridge"
        await update.message.reply_text("Напишите продукты, которые у вас есть (через запятую).")
        return
    elif text == "⚡ Быстрый ужин":
        user_states[user_id] = "quick_dinner"
        await update.message.reply_text("Напишите главный продукт для быстрого ужина.")
        return
    elif text == "🥗 Рецепты для похудения":
        user_states[user_id] = "diet_recipe"
        await update.message.reply_text("Какой лёгкий рецепт вы хотите?")
        return
    elif text == "📸 Калории по фото":
        user_states[user_id] = "photo_calories"
        await update.message.reply_text("📸 Отправьте мне фотографию вашей еды, и я посчитаю примерное КБЖУ!")
        return
    elif text == "🛒 Мой список покупок":
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
    
    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe", "replace_ingredient"]:
        await context.bot.send_chat_action(chat_id=user_id, action='typing')
        if state == "replace_ingredient":
            old_recipe = last_recipes.get(user_id, "")
            user_prompt = f"Вот прошлый рецепт:\n{old_recipe}\n\nПользователь просит: {text}. Перепиши рецепт, выполнив эту просьбу."
        elif state == "from_fridge":
            user_prompt = f"Сделай рецепт строго из этих продуктов (или части): {text}."
            last_prompts[user_id] = text
        elif state == "quick_dinner":
            user_prompt = f"Сделай очень БЫСТРЫЙ рецепт (до 20 минут), главное: {text}."
            last_prompts[user_id] = text
        elif state == "diet_recipe":
            user_prompt = f"Сделай низкокалорийный ДИЕТИЧЕСКИЙ рецепт, главное: {text}."
            last_prompts[user_id] = text
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
        await update.message.reply_text("⏳ Ваш бесплатный период подошел к концу! Оформите подписку.")
        return
    state = user_states.get(user_id, "start")
    if state != "photo_calories":
        await update.message.reply_text("Если хотите узнать калории, сначала нажмите кнопку «📸 Калории по фото»!")
        return

    await context.bot.send_chat_action(chat_id=user_id, action='typing')
    await update.message.reply_text("🔍 Анализирую фото... Это займет пару секунд.")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Определи еду на фото и напиши примерное КБЖУ на 100 грамм в формате:\n🍽 Блюдо: ...\n🔥 Калории: ...\n🥩 Белки: ...\n🥑 Жиры: ...\n🌾 Углеводы: ..."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}]
        )
        await update.message.reply_text(response.choices[0].message.content)
        user_states[user_id] = "start" 
    except Exception as e:
        await update.message.reply_text("❌ Не удалось распознать фото.")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_text = query.message.text
    await query.answer() 

    if query.data == "give_premium":
        if user_id == ADMIN_ID:
            user_states[user_id] = "waiting_for_user_id"
            await context.bot.send_message(chat_id=user_id, text="👇 <b>Пришлите ID пользователя (только цифры):</b>", parse_mode="HTML")
        return

    if query.data == "delete_user":
        if user_id == ADMIN_ID:
            user_states[user_id] = "waiting_for_delete_id"
            await context.bot.send_message(chat_id=user_id, text="👇 <b>Пришлите ID пользователя</b>, которого нужно удалить из базы:", parse_mode="HTML")
        return

    has_access = await check_access(user_id)
    if not has_access:
        await context.bot.send_message(chat_id=user_id, text="⏳ Ваш бесплатный период завершен. Функция заблокирована 🔒")
        return

    if query.data == "add_to_cart":
        try:
            match = re.search(r'(?i)Ингредиенты:(.*?)(?:Приготовление:|$)', message_text, re.DOTALL)
            ingredients = match.group(1).strip() if match else message_text 
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET shopping_list = COALESCE(shopping_list, '') || '\n\n' || $1 WHERE user_id = $2", ingredients, user_id)
            await conn.close()
            await context.bot.send_message(chat_id=user_id, text="🛒 ✅ Ингредиенты добавлены в список продуктов!")
        except: pass

    elif query.data == "save_recipe":
        try:
            full_recipe = f"\n\n➖➖➖➖➖➖➖➖➖➖\n\n{message_text}"
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("UPDATE users SET saved_recipes = COALESCE(saved_recipes, '') || $1 WHERE user_id = $2", full_recipe, user_id)
            await conn.close()
            await context.bot.send_message(chat_id=user_id, text="⭐ ✅ Рецепт сохранен в базе!")
        except: pass

    elif query.data == "replace_btn":
        user_states[user_id] = "replace_ingredient"
        await context.bot.send_message(chat_id=user_id, text="🔄 <b>Напишите, какой продукт нужно заменить.</b>", parse_mode="HTML")

    elif query.data == "another_recipe":
        await context.bot.send_message(chat_id=user_id, text="👨‍🍳 Ищу другой вариант...")
        old_prompt = last_prompts.get(user_id, "вкусное блюдо")
        user_prompt = f"Напиши АБСОЛЮТНО ДРУГОЙ рецепт по этому же запросу: {old_prompt}."
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
        except: pass

    elif query.data == "clear_list":
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("UPDATE users SET shopping_list = '' WHERE user_id = $1", user_id)
        await conn.close()
        await query.edit_message_text("🛒 Список продуктов очищен!")

    elif query.data == "clear_saved":
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("UPDATE users SET saved_recipes = '' WHERE user_id = $1", user_id)
        await conn.close()
        await query.edit_message_text("🗑 Ваша база рецептов очищена!")

async def main():
    await init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel)) 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_click))
    
    web_app = web.Application()
    web_app.router.add_post('/robokassa', robokassa_handler)
    web_app['bot'] = app.bot
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("🌍 Сервер оплат Робокассы успешно запущен на порту 8080!")

    async with app:
        await app.start()
        await app.updater.start_polling()
        logging.info("🤖 Бот успешно запущен!")
        stop_event = asyncio.Event()
        await stop_event.wait()

if __name__ == "__main__":
    asyncio.run(main())
