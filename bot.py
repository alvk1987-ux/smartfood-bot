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
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ChatAction
from openai import AsyncOpenAI

load_dotenv()

# =========================
# НАСТРОЙКИ
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

ADMIN_ID = 230764474
GROUP_LINK = "https://t.me/premium_chef_ru"
BOT_USERNAME = "recept_chef_ai_bot"

ROBOKASSA_SHOP_ID = os.getenv("ROBOKASSA_SHOP_ID", "")
ROBOKASSA_PASS_1 = os.getenv("ROBOKASSA_PASS_1", "")
ROBOKASSA_PASS_2 = os.getenv("ROBOKASSA_PASS_2", "")
ROBOKASSA_TEST_PASS_1 = os.getenv("ROBOKASSA_TEST_PASS_1", "")
ROBOKASSA_TEST_PASS_2 = os.getenv("ROBOKASSA_TEST_PASS_2", "")

IS_TEST_MODE = False

PRICE_RUB = 249.00
TRIAL_HOURS = 48
PREMIUM_DAYS = 30

OPENAI_BASE_URL = "https://api.proxyapi.ru/openai/v1"
OPENAI_MODEL_TEXT = "gpt-3.5-turbo"
OPENAI_MODEL_FALLBACK = "gpt-4o-mini"
OPENAI_MODEL_VISION = "gpt-4o-mini"

REQUEST_TIMEOUT_SECONDS = 35
RATE_LIMIT_SECONDS = 5
RATE_LIMIT_HOURLY_TRIAL = 20

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
db_pool = None

MENU_FREE = [
    ["📖 Как общаться с Шефом"],
    ["🔍 Найти рецепт", "🧺 Из того, что есть"],
    ["⚡ Быстрый ужин", "🥗 Рецепты для похудения"],
    ["🛒 Мой список покупок", "📸 Калории по фото"],
    ["⭐ Сохраненные рецепты", "🕘 История рецептов"],
    ["📷 Рецепт по фото", "👑 Моя подписка"],
    ["💬 Наш Чат-Форум", "📜 Правовая информация"],
]

ONBOARDING_MENU = [
    ["🧺 Попробовать: Из того, что есть"],
    ["⚡ Попробовать: Быстрый ужин"],
    ["📸 Попробовать: Калории по фото"],
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

GUIDE_TEXT = (
    "👨‍🍳 <b>Как выжать максимум из Шефа</b>\n\n"
    "Шеф создан для одного: чтобы вы <b>быстро понимали, что приготовить</b>, "
    "не тратили время на бесконечный поиск рецептов и могли получать идеи под свою реальную ситуацию.\n\n"
    "Он помогает, когда:\n"
    "• не знаете, что приготовить сегодня\n"
    "• хотите использовать продукты, которые уже есть дома\n"
    "• нужен быстрый ужин после работы\n"
    "• хотите более легкие блюда с КБЖУ\n"
    "• нужно сохранить удачные рецепты и собрать список покупок\n\n"
    "➖➖➖➖➖➖➖➖➖➖\n"
    "<b>1. Как правильно писать запросы</b>\n"
    "➖➖➖➖➖➖➖➖➖➖\n\n"
    "Пишите Шефу так, как будто общаетесь с личным поваром. "
    "Чем конкретнее запрос, тем полезнее получится результат.\n\n"
    "<b>Хорошие примеры:</b>\n"
    "• «Что приготовить из курицы, сыра и макарон»\n"
    "• «Сделай быстрый ужин из фарша за 20 минут»\n"
    "• «Подбери легкий ужин до 500 ккал»\n"
    "• «Нужен ужин без молочки и без лука»\n"
    "• «Хочу что-то необычное из индейки в духовке»\n\n"
    "Можно указывать:\n"
    "• главный продукт\n"
    "• желаемое время приготовления\n"
    "• цель: похудение / легкий ужин / сытно / быстро\n"
    "• ограничения: без лука, без молочки, без сахара и т.д.\n\n"
    "➖➖➖➖➖➖➖➖➖➖\n"
    "<b>2. Что делает каждая кнопка</b>\n"
    "➖➖➖➖➖➖➖➖➖➖\n\n"
    "<b>🔍 Найти рецепт</b>\n"
    "Используйте, когда уже примерно знаете, чего хотите.\n\n"
    "<b>🧺 Из того, что есть</b>\n"
    "Самая удобная кнопка, когда не хочется идти в магазин. Просто перечислите продукты, и Шеф соберет из них блюдо.\n\n"
    "<b>⚡ Быстрый ужин</b>\n"
    "Для ситуаций, когда нужно приготовить что-то вкусное без долгой возни.\n\n"
    "<b>🥗 Рецепты для похудения</b>\n"
    "Когда нужен более легкий вариант с акцентом на КБЖУ.\n\n"
    "<b>📸 Калории по фото</b>\n"
    "Отправляете фото еды — Шеф оценивает примерное КБЖУ.\n\n"
    "<b>📷 Рецепт по фото</b>\n"
    "Отправляете фото блюда — Шеф предлагает похожий домашний рецепт.\n\n"
    "<b>🛒 Мой список покупок</b>\n"
    "Сюда попадают ингредиенты из рецептов, чтобы вы ничего не забыли в магазине.\n\n"
    "<b>⭐ Сохраненные рецепты</b>\n"
    "Ваши любимые рецепты в одном месте.\n\n"
    "<b>🕘 История рецептов</b>\n"
    "Позволяет быстро вернуться к последним рецептам.\n\n"
    "<b>👑 Моя подписка</b>\n"
    "Здесь можно посмотреть статус доступа и оформить VIP.\n\n"
    "➖➖➖➖➖➖➖➖➖➖\n"
    "<b>3. Что означают кнопки под рецептом</b>\n"
    "➖➖➖➖➖➖➖➖➖➖\n\n"
    "<b>🛒 В список покупок</b>\n"
    "Добавляет ингредиенты рецепта в ваш список продуктов.\n\n"
    "<b>⭐ Сохранить рецепт</b>\n"
    "Сохраняет удачный рецепт, чтобы потом быстро его найти.\n\n"
    "<b>🔄 Заменить продукт</b>\n"
    "Если рецепт нравится, но хотите что-то изменить — просто скажите, что заменить.\n"
    "<i>Например: «Убери лук и замени молоко на сливки».</i>\n\n"
    "<b>🎲 Другой вариант</b>\n"
    "Если идея не зашла, Шеф сразу предложит новый рецепт по тому же запросу.\n\n"
    "➖➖➖➖➖➖➖➖➖➖\n"
    "<b>4. С чего лучше начать прямо сейчас</b>\n"
    "➖➖➖➖➖➖➖➖➖➖\n\n"
    "Если хотите быстро понять, насколько это удобно, начните с одной из этих кнопок:\n"
    "• <b>🧺 Из того, что есть</b> — если хотите приготовить из того, что уже лежит дома\n"
    "• <b>⚡ Быстрый ужин</b> — если нужен ужин без лишних раздумий\n"
    "• <b>📸 Калории по фото</b> — если хотите сразу протестировать одну из самых интересных функций\n\n"
    "Шеф создан, чтобы <b>экономить вам время, снимать ежедневную головную боль «что приготовить» и делать готовку проще</b>.\n\n"
    "Выбирайте кнопку в меню и давайте готовить 👇"
)

LEGAL_TEXT = (
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
    "• Для возврата средств необходимо направить письменное обращение в свободной форме на email: al.smm-manager@yandex.ru.\n"
    "• Срок рассмотрения заявки — до 3 рабочих дней.\n"
    "• Возврат производится в полном объеме на ту же карту, с которой была произведена оплата, в течение 3–10 рабочих дней.\n\n"
    "🔐 <b>Политика обработки персональных данных</b>\n"
    "• Бот собирает только Telegram ID для идентификации подписки. Платежные данные обрабатываются на стороне Robokassa."
)

# =========================
# DB
# =========================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                premium_until TIMESTAMP NULL,
                shopping_list TEXT DEFAULT ''
            )
        """)

        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS source TEXT")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN DEFAULT FALSE")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                inv_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount NUMERIC(10,2) NOT NULL,
                status TEXT DEFAULT 'paid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                event_name TEXT NOT NULL,
                event_value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_recipes (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                title TEXT,
                recipe_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_history (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                recipe_text TEXT NOT NULL,
                source_mode TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id BIGINT PRIMARY KEY,
                last_request_at TIMESTAMP,
                hourly_count INT DEFAULT 0,
                hourly_window_start TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message_type TEXT NOT NULL,
                send_at TIMESTAMP NOT NULL,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def get_main_menu():
    return ReplyKeyboardMarkup(MENU_FREE, resize_keyboard=True)

def get_onboarding_menu():
    return ReplyKeyboardMarkup(ONBOARDING_MENU, resize_keyboard=True)

async def log_event(user_id: int, event_name: str, event_value: str = None):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO events (user_id, event_name, event_value) VALUES ($1, $2, $3)",
                user_id, event_name, event_value
            )
    except Exception:
        logger.exception("Ошибка записи события")

async def upsert_user(user_id: int, username: str = None, source: str = None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, source, created_at, last_seen_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id)
            DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                source = COALESCE(users.source, EXCLUDED.source),
                last_seen_at = CURRENT_TIMESTAMP
        """, user_id, username, source)

async def get_user_row(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def check_access(user_id: int):
    if user_id == ADMIN_ID:
        return True

    row = await get_user_row(user_id)
    if not row:
        return True

    premium_until = row["premium_until"]
    if premium_until and premium_until > datetime.datetime.now():
        return True

    diff = datetime.datetime.now() - row["created_at"]
    return (diff.total_seconds() / 3600) < TRIAL_HOURS

async def trial_hours_left(user_id: int):
    row = await get_user_row(user_id)
    if not row:
        return TRIAL_HOURS

    premium_until = row["premium_until"]
    if premium_until and premium_until > datetime.datetime.now():
        return None

    diff = datetime.datetime.now() - row["created_at"]
    return int(max(0, TRIAL_HOURS - (diff.total_seconds() / 3600)))

def get_bot_link():
    return f"https://t.me/{BOT_USERNAME}"

def build_payment_keyboard(payment_url: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💎 Оплатить VIP за {int(PRICE_RUB)} ₽", url=payment_url)]
    ])

def get_payment_link(user_id: int):
    amount = f"{PRICE_RUB:.2f}"
    inv_id = int(time.time() * 1000) % 100000000000
    description = "VIP Подписка на Premium Шеф"
    pass1 = ROBOKASSA_TEST_PASS_1 if IS_TEST_MODE else ROBOKASSA_PASS_1

    signature_str = f"{ROBOKASSA_SHOP_ID}:{amount}:{inv_id}:{pass1}:Shp_chatId={user_id}"
    hash_md5 = hashlib.md5(signature_str.encode()).hexdigest()

    params = {
        "MerchantLogin": ROBOKASSA_SHOP_ID,
        "OutSum": amount,
        "InvId": inv_id,
        "Description": description,
        "SignatureValue": hash_md5,
        "Shp_chatId": str(user_id),
    }

    if IS_TEST_MODE:
        params["IsTest"] = "1"

    return "https://auth.robokassa.ru/Merchant/Index.aspx?" + urllib.parse.urlencode(params)

async def schedule_trial_end_messages(user_id: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT created_at FROM users WHERE user_id = $1", user_id)
        if not user:
            return

        trial_end = user["created_at"] + datetime.timedelta(hours=TRIAL_HOURS)
        send_1 = trial_end + datetime.timedelta(hours=12)
        send_2 = trial_end + datetime.timedelta(hours=24)

        existing = await conn.fetchval("""
            SELECT COUNT(*) FROM scheduled_messages
            WHERE user_id = $1 AND message_type IN ('trial_end_12h', 'trial_end_24h')
        """, user_id)

        if existing == 0:
            await conn.execute("""
                INSERT INTO scheduled_messages (user_id, message_type, send_at)
                VALUES ($1, 'trial_end_12h', $2),
                       ($1, 'trial_end_24h', $3)
            """, user_id, send_1, send_2)

async def send_due_scheduled_messages(app: Application):
    while True:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, user_id, message_type
                    FROM scheduled_messages
                    WHERE sent = FALSE AND send_at <= CURRENT_TIMESTAMP
                    ORDER BY send_at ASC
                    LIMIT 50
                """)

                for row in rows:
                    user_id = row["user_id"]
                    msg_type = row["message_type"]

                    if await check_access(user_id):
                        await conn.execute("UPDATE scheduled_messages SET sent = TRUE WHERE id = $1", row["id"])
                        continue

                    payment_url = get_payment_link(user_id)
                    kb = build_payment_keyboard(payment_url)

                    if msg_type == "trial_end_12h":
                        text = (
                            "👨‍🍳 Я уже жду вас на кухне.\n\n"
                            "Доступ к новым рецептам сейчас закрыт, но его можно сразу вернуть через «Моя подписка»."
                        )
                    else:
                        text = (
                            "🍽 У вас по-прежнему закрыт доступ к рецептам, списку покупок и сохранениям.\n\n"
                            "Активируйте VIP, и можно продолжать пользоваться Шефом без ограничений."
                        )

                    try:
                        await app.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
                        await conn.execute("UPDATE scheduled_messages SET sent = TRUE WHERE id = $1", row["id"])
                        await log_event(user_id, "scheduled_message_sent", msg_type)
                    except Exception:
                        logger.exception("Ошибка отправки отложенного сообщения user_id=%s", user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка фоновой отправки scheduled messages")

        await asyncio.sleep(60)

async def is_rate_limited(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT last_request_at, hourly_count, hourly_window_start
            FROM rate_limits
            WHERE user_id = $1
        """, user_id)

        now = datetime.datetime.now()

        if not row:
            await conn.execute("""
                INSERT INTO rate_limits (user_id, last_request_at, hourly_count, hourly_window_start)
                VALUES ($1, $2, 1, $2)
            """, user_id, now)
            return False, None

        last_request_at = row["last_request_at"]
        hourly_count = row["hourly_count"] or 0
        hourly_window_start = row["hourly_window_start"] or now

        if last_request_at and (now - last_request_at).total_seconds() < RATE_LIMIT_SECONDS:
            wait_seconds = RATE_LIMIT_SECONDS - int((now - last_request_at).total_seconds())
            return True, f"Слишком быстро 😊 Подождите {wait_seconds} сек."

        user = await get_user_row(user_id)
        premium = bool(user and user["premium_until"] and user["premium_until"] > now)

        if (now - hourly_window_start).total_seconds() >= 3600:
            hourly_count = 0
            hourly_window_start = now

        if not premium and hourly_count >= RATE_LIMIT_HOURLY_TRIAL:
            return True, "Вы исчерпали лимит запросов за час для пробного периода. Попробуйте позже."

        await conn.execute("""
            UPDATE rate_limits
            SET last_request_at = $2,
                hourly_count = $3,
                hourly_window_start = $4
            WHERE user_id = $1
        """, user_id, now, hourly_count + 1, hourly_window_start)

        return False, None

async def save_recipe_history(user_id: int, recipe_text: str, source_mode: str = None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO recipe_history (user_id, recipe_text, source_mode)
            VALUES ($1, $2, $3)
        """, user_id, recipe_text, source_mode)

async def save_recipe_item(user_id: int, recipe_text: str):
    title_match = re.search(r'«(.+?)»', recipe_text)
    title = title_match.group(1) if title_match else "Сохраненный рецепт"
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO saved_recipes (user_id, title, recipe_text)
            VALUES ($1, $2, $3)
        """, user_id, title, recipe_text)

async def get_last_history(user_id: int, limit: int = 10):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT id, recipe_text, source_mode, created_at
            FROM recipe_history
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)

async def get_saved_recipes(user_id: int, limit: int = 20):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT id, title, recipe_text, created_at
            FROM saved_recipes
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)

async def clear_saved_recipes(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM saved_recipes WHERE user_id = $1", user_id)

async def clear_history(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM recipe_history WHERE user_id = $1", user_id)

async def add_to_shopping_list(user_id: int, ingredients: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET shopping_list = COALESCE(shopping_list, '') || CASE
                WHEN shopping_list IS NULL OR shopping_list = '' THEN $2
                ELSE E'\n\n' || $2
            END
            WHERE user_id = $1
        """, user_id, ingredients)

async def get_shopping_list(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT shopping_list FROM users WHERE user_id = $1", user_id)
        return row["shopping_list"] if row and row["shopping_list"] else ""

async def clear_shopping_list(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET shopping_list = '' WHERE user_id = $1", user_id)

async def activate_premium(user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT premium_until FROM users WHERE user_id = $1", user_id)
        now = datetime.datetime.now()
        if row and row["premium_until"] and row["premium_until"] > now:
            base_date = row["premium_until"]
        else:
            base_date = now

        new_premium_until = base_date + datetime.timedelta(days=PREMIUM_DAYS)
        await conn.execute("""
            UPDATE users SET premium_until = $2 WHERE user_id = $1
        """, user_id, new_premium_until)
        return new_premium_until

async def call_text_model(messages):
    try:
        return await asyncio.wait_for(
            client.chat.completions.create(
                model=OPENAI_MODEL_TEXT,
                messages=messages
            ),
            timeout=REQUEST_TIMEOUT_SECONDS
        )
    except Exception:
        logger.exception("Основная модель не ответила, пробую fallback")
        return await asyncio.wait_for(
            client.chat.completions.create(
                model=OPENAI_MODEL_FALLBACK,
                messages=messages
            ),
            timeout=REQUEST_TIMEOUT_SECONDS
        )

async def generate_recipe(user_id: int, source_mode: str, user_prompt: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    response = await call_text_model(messages)
    recipe_text = response.choices[0].message.content
    await save_recipe_history(user_id, recipe_text, source_mode)
    await log_event(user_id, "recipe_generated", source_mode)
    return recipe_text

def recipe_actions_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 В список покупок", callback_data="add_to_cart")],
        [InlineKeyboardButton("⭐ Сохранить рецепт", callback_data="save_recipe")],
        [InlineKeyboardButton("🔄 Заменить продукт", callback_data="replace_btn")],
        [InlineKeyboardButton("🎲 Другой вариант", callback_data="another_recipe")],
    ])

# =========================
# ADMIN STATS
# =========================
async def get_admin_stats_data():
    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_premium = await conn.fetchval("""
            SELECT COUNT(*) FROM users
            WHERE premium_until IS NOT NULL AND premium_until > CURRENT_TIMESTAMP
        """)
        expired_trial = await conn.fetchval("""
            SELECT COUNT(*) FROM users
            WHERE (premium_until IS NULL OR premium_until <= CURRENT_TIMESTAMP)
              AND created_at <= CURRENT_TIMESTAMP - INTERVAL '48 hours'
        """)
        total_payments = await conn.fetchval("SELECT COUNT(*) FROM payments")
        revenue = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM payments")

        total_starts = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name = 'start'
        """)

        starts_today = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name = 'start'
              AND created_at::date = CURRENT_DATE
        """)
        payments_today = await conn.fetchval("""
            SELECT COUNT(*) FROM payments
            WHERE created_at::date = CURRENT_DATE
        """)
        revenue_today = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE created_at::date = CURRENT_DATE
        """)
        recipes_today = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name = 'recipe_generated'
              AND created_at::date = CURRENT_DATE
        """)
        photo_today = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name IN ('photo_calories', 'recipe_from_photo')
              AND created_at::date = CURRENT_DATE
        """)

        total_conversion = (total_payments / total_starts * 100) if total_starts else 0
        today_conversion = (payments_today / starts_today * 100) if starts_today else 0
        arpu = (float(revenue) / total_users) if total_users else 0
        arppu = (float(revenue) / total_payments) if total_payments else 0

        top_sources = await conn.fetch("""
            SELECT COALESCE(source, 'unknown') AS src, COUNT(*) AS cnt
            FROM users
            GROUP BY COALESCE(source, 'unknown')
            ORDER BY cnt DESC
            LIMIT 5
        """)

    return {
        "total_users": total_users,
        "active_premium": active_premium,
        "expired_trial": expired_trial,
        "total_payments": total_payments,
        "revenue": float(revenue),
        "total_starts": total_starts,
        "starts_today": starts_today,
        "payments_today": payments_today,
        "revenue_today": float(revenue_today),
        "recipes_today": recipes_today,
        "photo_today": photo_today,
        "total_conversion": total_conversion,
        "today_conversion": today_conversion,
        "arpu": arpu,
        "arppu": arppu,
        "top_sources": top_sources,
    }

async def get_admin_stats_text():
    data = await get_admin_stats_data()

    source_lines = []
    for row in data["top_sources"]:
        source_lines.append(f"• {row['src']} — {row['cnt']}")
    source_block = "\n".join(source_lines) if source_lines else "• Нет данных"

    return (
        "📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Всего пользователей: <b>{data['total_users']}</b>\n"
        f"🚀 Всего стартов: <b>{data['total_starts']}</b>\n"
        f"💎 Активных VIP: <b>{data['active_premium']}</b>\n"
        f"⌛ Триал закончился: <b>{data['expired_trial']}</b>\n"
        f"💳 Всего оплат: <b>{data['total_payments']}</b>\n"
        f"📈 Конверсия старт → оплата: <b>{data['total_conversion']:.2f}%</b>\n"
        f"💰 Общая выручка: <b>{data['revenue']:.2f} ₽</b>\n"
        f"💵 ARPU: <b>{data['arpu']:.2f} ₽</b>\n"
        f"💎 ARPPU: <b>{data['arppu']:.2f} ₽</b>\n\n"
        f"📅 <b>Сегодня</b>\n"
        f"• Стартов: <b>{data['starts_today']}</b>\n"
        f"• Оплат: <b>{data['payments_today']}</b>\n"
        f"• Конверсия: <b>{data['today_conversion']:.2f}%</b>\n"
        f"• Выручка: <b>{data['revenue_today']:.2f} ₽</b>\n"
        f"• Сгенерировано рецептов: <b>{data['recipes_today']}</b>\n"
        f"• Фото-функции: <b>{data['photo_today']}</b>\n\n"
        f"🔗 <b>Топ источников трафика</b>\n{source_block}"
    )

async def get_admin_sources_text():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                COALESCE(u.source, 'unknown') AS source,
                COUNT(DISTINCT u.user_id) AS users_count,
                COUNT(DISTINCT CASE WHEN p.user_id IS NOT NULL THEN u.user_id END) AS buyers_count,
                COALESCE(SUM(p.amount), 0) AS revenue
            FROM users u
            LEFT JOIN payments p ON p.user_id = u.user_id
            GROUP BY COALESCE(u.source, 'unknown')
            ORDER BY revenue DESC, users_count DESC
        """)

    if not rows:
        return "📊 Нет данных по источникам."

    lines = ["🔗 <b>СТАТИСТИКА ПО ИСТОЧНИКАМ</b>\n"]
    for row in rows:
        users_count = row["users_count"] or 0
        buyers_count = row["buyers_count"] or 0
        conversion = (buyers_count / users_count * 100) if users_count else 0
        revenue = float(row["revenue"] or 0)
        arpu = (revenue / users_count) if users_count else 0
        arppu = (revenue / buyers_count) if buyers_count else 0

        lines.append(
            f"\n<b>{row['source']}</b>\n"
            f"• Пользователей: {users_count}\n"
            f"• Покупателей: {buyers_count}\n"
            f"• Конверсия: {conversion:.2f}%\n"
            f"• Выручка: {revenue:.2f} ₽\n"
            f"• ARPU: {arpu:.2f} ₽\n"
            f"• ARPPU: {arppu:.2f} ₽"
        )
    return "\n".join(lines)

async def get_admin_today_text():
    async with db_pool.acquire() as conn:
        starts = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name='start' AND created_at::date = CURRENT_DATE
        """)
        subs = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name='subscription_opened' AND created_at::date = CURRENT_DATE
        """)
        recipes = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name='recipe_generated' AND created_at::date = CURRENT_DATE
        """)
        saves = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name='recipe_saved' AND created_at::date = CURRENT_DATE
        """)
        cart = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name='add_to_cart' AND created_at::date = CURRENT_DATE
        """)
        photo = await conn.fetchval("""
            SELECT COUNT(*) FROM events
            WHERE event_name IN ('photo_calories', 'recipe_from_photo')
              AND created_at::date = CURRENT_DATE
        """)
        payments = await conn.fetchval("""
            SELECT COUNT(*) FROM payments WHERE created_at::date = CURRENT_DATE
        """)
        revenue = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0) FROM payments WHERE created_at::date = CURRENT_DATE
        """)
        users_today = await conn.fetchval("""
            SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE
        """)

    conversion = (payments / starts * 100) if starts else 0
    arpu = (float(revenue) / users_today) if users_today else 0
    arppu = (float(revenue) / payments) if payments else 0

    return (
        "📅 <b>СЕГОДНЯ</b>\n\n"
        f"🚀 Стартов: <b>{starts}</b>\n"
        f"👥 Новых пользователей: <b>{users_today}</b>\n"
        f"👑 Открытий подписки: <b>{subs}</b>\n"
        f"🍽 Генераций рецептов: <b>{recipes}</b>\n"
        f"⭐ Сохранений: <b>{saves}</b>\n"
        f"🛒 Добавлений в список: <b>{cart}</b>\n"
        f"📸 Фото-функций: <b>{photo}</b>\n"
        f"💳 Оплат: <b>{payments}</b>\n"
        f"📈 Конверсия старт → оплата: <b>{conversion:.2f}%</b>\n"
        f"💰 Выручка: <b>{float(revenue):.2f} ₽</b>\n"
        f"💵 ARPU: <b>{arpu:.2f} ₽</b>\n"
        f"💎 ARPPU: <b>{arppu:.2f} ₽</b>"
    )

def admin_stats_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats_general")],
        [InlineKeyboardButton("🔗 Источники трафика", callback_data="admin_stats_sources")],
        [InlineKeyboardButton("📅 Статистика за сегодня", callback_data="admin_stats_today")],
        [InlineKeyboardButton("🎁 Выдать VIP", callback_data="give_premium")],
        [InlineKeyboardButton("🗑 Удалить пользователя", callback_data="delete_user")],
    ])

# =========================
# PAYMENT
# =========================
async def robokassa_handler(request):
    try:
        data = await request.post()
        out_sum = data.get("OutSum", "0")
        inv_id = data.get("InvId", "0")
        signature = data.get("SignatureValue", "")
        user_id = data.get("Shp_chatId")
        pass2 = ROBOKASSA_TEST_PASS_2 if IS_TEST_MODE else ROBOKASSA_PASS_2

        logger.info(f"ROBOKASSA CALLBACK: inv_id={inv_id}, user_id={user_id}, out_sum={out_sum}")

        my_sig = f"{out_sum}:{inv_id}:{pass2}:Shp_chatId={user_id}"
        my_hash = hashlib.md5(my_sig.encode()).hexdigest().upper()

        if my_hash != signature.upper():
            logger.warning(f"ROBOKASSA BAD SIGNATURE: inv_id={inv_id}, user_id={user_id}, out_sum={out_sum}")
            return web.Response(text="BAD SIGNATURE", status=400)

        async with db_pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT inv_id FROM payments WHERE inv_id = $1",
                int(inv_id)
            )
            if existing:
                logger.info(f"ROBOKASSA DUPLICATE: inv_id={inv_id}, user_id={user_id}")
                return web.Response(text=f"OK{inv_id}")

            await conn.execute("""
                INSERT INTO payments (inv_id, user_id, amount, status)
                VALUES ($1, $2, $3, 'paid')
            """, int(inv_id), int(user_id), float(out_sum))

        premium_until = await activate_premium(int(user_id))
        await log_event(int(user_id), "payment_success", out_sum)
        logger.info(f"ROBOKASSA SUCCESS: inv_id={inv_id}, user_id={user_id}, out_sum={out_sum}")

        bot = request.app["bot"]
        try:
            await bot.send_message(
                chat_id=int(user_id),
                text=(
                    "🎉 <b>Оплата успешно получена!</b>\n\n"
                    f"VIP-доступ активирован до: <b>{premium_until.strftime('%d.%m.%Y %H:%M')}</b>"
                ),
                parse_mode="HTML"
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение об оплате")

        return web.Response(text=f"OK{inv_id}")
    except Exception:
        logger.exception("Ошибка в robokassa_handler")
        return web.Response(text="ERROR", status=500)

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    source = context.args[0] if context.args else None

    await upsert_user(user.id, user.username, source)
    await log_event(user.id, "start", source)

    context.user_data["state"] = "start"

    text = (
        f"👨‍🍳 Добро пожаловать, {user.first_name}!\n\n"
        "Я ваш личный Премиальный Шеф.\n\n"
        f"🎁 Вам начислено <b>{TRIAL_HOURS} часов бесплатного VIP-доступа</b>.\n\n"
        "Чтобы было проще начать, вот 3 самых удобных сценария:"
    )

    await update.message.reply_text(
        text,
        reply_markup=get_onboarding_menu(),
        parse_mode="HTML"
    )

    inline_kb = [[InlineKeyboardButton("🚀 Перейти в Комьюнити", url=GROUP_LINK)]]
    await update.message.reply_text(
        "👇 <b>Загляните в Чат-Форум</b>\n\n"
        "Там делятся блюдами, идеями и полезными находками.",
        reply_markup=InlineKeyboardMarkup(inline_kb),
        parse_mode="HTML"
    )

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET onboarding_done = TRUE WHERE user_id = $1", user.id)

    await schedule_trial_end_messages(user.id)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    stats_text = await get_admin_stats_text()
    await update.message.reply_text(
        stats_text,
        reply_markup=admin_stats_keyboard(),
        parse_mode="HTML"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    data = await get_admin_stats_data()
    text = (
        "📈 <b>БЫСТРАЯ СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: <b>{data['total_users']}</b>\n"
        f"🚀 Стартов: <b>{data['total_starts']}</b>\n"
        f"💳 Оплат: <b>{data['total_payments']}</b>\n"
        f"📈 Конверсия: <b>{data['total_conversion']:.2f}%</b>\n"
        f"💎 Активных VIP: <b>{data['active_premium']}</b>\n"
        f"⌛ Триал закончился: <b>{data['expired_trial']}</b>\n"
        f"💰 Выручка: <b>{data['revenue']:.2f} ₽</b>\n"
        f"💵 ARPU: <b>{data['arpu']:.2f} ₽</b>\n"
        f"💎 ARPPU: <b>{data['arppu']:.2f} ₽</b>\n\n"
        f"📅 Сегодня:\n"
        f"• Стартов: <b>{data['starts_today']}</b>\n"
        f"• Оплат: <b>{data['payments_today']}</b>\n"
        f"• Конверсия: <b>{data['today_conversion']:.2f}%</b>\n"
        f"• Выручка: <b>{data['revenue_today']:.2f} ₽</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def show_subscription(update: Update, user_id: int):
    pricing_info = (
        f"\n\n💎 <b>Условия подписки:</b>\n"
        f"Первые {TRIAL_HOURS} часов — БЕСПЛАТНО\n"
        f"Далее — всего {int(PRICE_RUB)} рублей в месяц."
    )

    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"👑 <b>Тариф:</b> Владелец проекта\n"
            f"⏳ <b>Осталось:</b> БЕЗЛИМИТ НАВСЕГДА\n{pricing_info}",
            parse_mode="HTML"
        )
        return

    row = await get_user_row(user_id)
    if not row:
        await update.message.reply_text("Не удалось получить данные профиля.")
        return

    now = datetime.datetime.now()
    payment_url = get_payment_link(user_id)
    pay_keyboard = build_payment_keyboard(payment_url)

    if row["premium_until"] and row["premium_until"] > now:
        await update.message.reply_text(
            f"👑 <b>Тариф:</b> VIP Доступ\n"
            f"⏳ <b>Оплачен до:</b> {row['premium_until'].strftime('%d.%m.%Y %H:%M')}{pricing_info}",
            parse_mode="HTML"
        )
    else:
        hours_left = await trial_hours_left(user_id)
        if hours_left <= 0:
            await update.message.reply_text(
                f"👑 <b>Тариф:</b> Истек ❌\n"
                "⏳ Ваш бесплатный период завершен.\n\n"
                f"Оформите подписку, чтобы продолжить!{pricing_info}",
                reply_markup=pay_keyboard,
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"👑 <b>Тариф:</b> Пробный VIP\n"
                f"⏳ <b>Осталось:</b> {hours_left} часов{pricing_info}",
                reply_markup=pay_keyboard,
                parse_mode="HTML"
            )

    await log_event(user_id, "subscription_opened")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    await upsert_user(user_id, update.effective_user.username)
    state = context.user_data.get("state", "start")

    if text == "📜 Правовая информация":
        await update.message.reply_text(LEGAL_TEXT, parse_mode="HTML")
        return

    if text == "📖 Как общаться с Шефом":
        await update.message.reply_text(GUIDE_TEXT, parse_mode="HTML")
        return

    if text == "👑 Моя подписка":
        await show_subscription(update, user_id)
        return

    if text == "💬 Наш Чат-Форум":
        inline_kb = [[InlineKeyboardButton("🚀 Перейти в Комьюнити Шефа", url=GROUP_LINK)]]
        await update.message.reply_text(
            "👨‍🍳 <b>Добро пожаловать на нашу Кухню!</b>\n\n"
            "Присоединяйтесь, там вкусно и интересно 👇",
            reply_markup=InlineKeyboardMarkup(inline_kb),
            parse_mode="HTML"
        )
        return

    if state == "waiting_for_user_id" and user_id == ADMIN_ID:
        try:
            target_id = int(text)
            premium_until = await activate_premium(target_id)
            await update.message.reply_text(
                f"✅ VIP успешно выдан пользователю {target_id} до {premium_until.strftime('%d.%m.%Y %H:%M')}!"
            )
            context.user_data["state"] = "start"
        except Exception:
            logger.exception("Ошибка выдачи VIP вручную")
            await update.message.reply_text("❌ Ошибка. Пришлите только цифры ID.")
        return

    if state == "waiting_for_delete_id" and user_id == ADMIN_ID:
        try:
            target_id = int(text)
            if target_id == ADMIN_ID:
                await update.message.reply_text("❌ Вы не можете удалить сами себя!")
                context.user_data["state"] = "start"
                return

            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM users WHERE user_id = $1", target_id)
                await conn.execute("DELETE FROM saved_recipes WHERE user_id = $1", target_id)
                await conn.execute("DELETE FROM recipe_history WHERE user_id = $1", target_id)
                await conn.execute("DELETE FROM rate_limits WHERE user_id = $1", target_id)
                await conn.execute("DELETE FROM scheduled_messages WHERE user_id = $1", target_id)

            await update.message.reply_text(f"✅ Пользователь {target_id} удален из базы!")
            context.user_data["state"] = "start"
        except Exception:
            logger.exception("Ошибка удаления пользователя")
            await update.message.reply_text("❌ Ошибка. Пришлите только цифры ID.")
        return

    if text == "🧺 Попробовать: Из того, что есть":
        context.user_data["state"] = "from_fridge"
        await update.message.reply_text(
            "Напишите продукты, которые у вас есть (через запятую).",
            reply_markup=get_main_menu()
        )
        return

    if text == "⚡ Попробовать: Быстрый ужин":
        context.user_data["state"] = "quick_dinner"
        await update.message.reply_text(
            "Напишите главный продукт для быстрого ужина.",
            reply_markup=get_main_menu()
        )
        return

    if text == "📸 Попробовать: Калории по фото":
        context.user_data["state"] = "photo_calories"
        await update.message.reply_text(
            "📸 Отправьте фото вашей еды.",
            reply_markup=get_main_menu()
        )
        return

    has_access = await check_access(user_id)
    if not has_access:
        payment_url = get_payment_link(user_id)
        kb = build_payment_keyboard(payment_url)
        await update.message.reply_text(
            "⏳ <b>Ваш бесплатный период подошел к концу!</b>\n\n"
            "Доступ к рецептам, списку покупок и сохранениям сейчас закрыт.\n\n"
            "Чтобы продолжить пользоваться Шефом, откройте «👑 Моя подписка».",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    if text == "🔍 Найти рецепт":
        context.user_data["state"] = "find_recipe"
        await update.message.reply_text(
            "Напишите, какой рецепт вы хотите найти.\n\n"
            "Примеры:\n"
            "• курица в сливочном соусе\n"
            "• ужин из фарша\n"
            "• паста без мяса"
        )
        return

    if text == "🧺 Из того, что есть":
        context.user_data["state"] = "from_fridge"
        await update.message.reply_text(
            "Напишите продукты, которые у вас есть (через запятую).\n\n"
            "Пример:\n"
            "курица, сыр, помидоры, макароны"
        )
        return

    if text == "⚡ Быстрый ужин":
        context.user_data["state"] = "quick_dinner"
        await update.message.reply_text(
            "Напишите главный продукт.\n\n"
            "Пример:\n"
            "индейка\n"
            "или\n"
            "яйца"
        )
        return

    if text == "🥗 Рецепты для похудения":
        context.user_data["state"] = "diet_recipe"
        await update.message.reply_text(
            "Напишите, что хотите получить.\n\n"
            "Пример:\n"
            "легкий ужин без сахара\n"
            "или\n"
            "белковый завтрак"
        )
        return

    if text == "📸 Калории по фото":
        context.user_data["state"] = "photo_calories"
        await update.message.reply_text("📸 Отправьте мне фотографию вашей еды, и я посчитаю примерное КБЖУ!")
        return

    if text == "📷 Рецепт по фото":
        context.user_data["state"] = "recipe_from_photo"
        await update.message.reply_text("📷 Отправьте фото блюда, и я предложу похожий рецепт для дома.")
        return

    if text == "🛒 Мой список покупок":
        shop_list = await get_shopping_list(user_id)
        if not shop_list.strip():
            await update.message.reply_text("🛒 Ваш список покупок пока пуст.")
        else:
            keyboard = [[InlineKeyboardButton("🗑 Очистить список", callback_data="clear_list")]]
            await update.message.reply_text(
                f"🛒 <b>Ваш список покупок:</b>\n\n{shop_list}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        await log_event(user_id, "shopping_list_opened")
        return

    if text == "⭐ Сохраненные рецепты":
        items = await get_saved_recipes(user_id)
        if not items:
            await update.message.reply_text("⭐ У вас пока нет сохраненных рецептов.")
        else:
            parts = ["📚 <b>ВАШИ СОХРАНЕННЫЕ РЕЦЕПТЫ:</b>\n"]
            for idx, item in enumerate(items[:10], start=1):
                parts.append(f"{idx}. <b>{item['title']}</b> — {item['created_at'].strftime('%d.%m %H:%M')}")
            keyboard = [[InlineKeyboardButton("🗑 Очистить сохраненное", callback_data="clear_saved")]]
            await update.message.reply_text(
                "\n".join(parts),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        await log_event(user_id, "saved_recipes_opened")
        return

    if text == "🕘 История рецептов":
        items = await get_last_history(user_id)
        if not items:
            await update.message.reply_text("🕘 История пока пуста.")
        else:
            parts = ["🕘 <b>Последние рецепты:</b>\n"]
            for idx, item in enumerate(items, start=1):
                title_match = re.search(r'«(.+?)»', item["recipe_text"])
                title = title_match.group(1) if title_match else "Без названия"
                mode = item["source_mode"] or "recipe"
                parts.append(f"{idx}. <b>{title}</b> — {mode} — {item['created_at'].strftime('%d.%m %H:%M')}")
            keyboard = [[InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_history")]]
            await update.message.reply_text(
                "\n".join(parts),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        await log_event(user_id, "history_opened")
        return

    if state in ["find_recipe", "from_fridge", "quick_dinner", "diet_recipe", "replace_ingredient"]:
        limited, reason = await is_rate_limited(user_id)
        if limited:
            await update.message.reply_text(f"⏳ {reason}")
            return

        await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)

        last_recipe = context.user_data.get("last_recipe", "")
        if state == "replace_ingredient":
            user_prompt = (
                f"Вот прошлый рецепт:\n{last_recipe}\n\n"
                f"Пользователь просит: {text}. Перепиши рецепт, выполнив эту просьбу."
            )
            source_mode = "replace_ingredient"
        elif state == "from_fridge":
            user_prompt = f"Сделай рецепт строго из этих продуктов (или части): {text}."
            context.user_data["last_prompt"] = text
            source_mode = "from_fridge"
        elif state == "quick_dinner":
            user_prompt = f"Сделай очень БЫСТРЫЙ рецепт (до 20 минут), главное: {text}."
            context.user_data["last_prompt"] = text
            source_mode = "quick_dinner"
        elif state == "diet_recipe":
            user_prompt = f"Сделай низкокалорийный ДИЕТИЧЕСКИЙ рецепт, главное: {text}."
            context.user_data["last_prompt"] = text
            source_mode = "diet_recipe"
        else:
            user_prompt = f"Запрос: {text}."
            context.user_data["last_prompt"] = text
            source_mode = "find_recipe"

        try:
            recipe_text = await generate_recipe(user_id, source_mode, user_prompt)
            context.user_data["last_recipe"] = recipe_text
            await update.message.reply_text(recipe_text, reply_markup=recipe_actions_keyboard())
            context.user_data["state"] = "start"
        except asyncio.TimeoutError:
            logger.exception("Таймаут генерации рецепта")
            await update.message.reply_text("⏳ Шеф немного задержался. Попробуйте еще раз через минуту.")
        except Exception:
            logger.exception("Ошибка генерации рецепта")
            await update.message.reply_text("❌ Что-то пошло не так при создании рецепта. Попробуйте еще раз.")
        return

    context.user_data["state"] = "find_recipe"
    await update.message.reply_text("Напишите, какой рецепт вы хотите найти.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get("state", "start")

    has_access = await check_access(user_id)
    if not has_access:
        payment_url = get_payment_link(user_id)
        kb = build_payment_keyboard(payment_url)
        await update.message.reply_text(
            "⏳ Ваш бесплатный период подошел к концу. Оформите подписку, чтобы продолжить.",
            reply_markup=kb
        )
        return

    limited, reason = await is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ {reason}")
        return

    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    await update.message.reply_text("🔍 Анализирую фото... Это займет пару секунд.")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        base64_image = base64.b64encode(photo_bytes).decode("utf-8")

        if state == "photo_calories":
            prompt = (
                "Определи еду на фото и напиши примерное КБЖУ на 100 грамм в формате:\n"
                "🍽 Блюдо: ...\n"
                "🔥 Калории: ...\n"
                "🥩 Белки: ...\n"
                "🥑 Жиры: ...\n"
                "🌾 Углеводы: ..."
            )
            event_name = "photo_calories"
        elif state == "recipe_from_photo":
            prompt = (
                "Определи блюдо на фото и предложи похожий домашний рецепт. "
                "Ответ дай строго в формате рецепта: название, время, порции, КБЖУ, ингредиенты, приготовление."
            )
            event_name = "recipe_from_photo"
        else:
            await update.message.reply_text("Сначала выберите нужную функцию: «📸 Калории по фото» или «📷 Рецепт по фото».")
            return

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=OPENAI_MODEL_VISION,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }]
            ),
            timeout=REQUEST_TIMEOUT_SECONDS
        )

        result = response.choices[0].message.content
        await update.message.reply_text(result)

        if state == "recipe_from_photo":
            context.user_data["last_recipe"] = result
            await save_recipe_history(user_id, result, "recipe_from_photo")
            await update.message.reply_text("👇 Что делаем дальше?", reply_markup=recipe_actions_keyboard())

        await log_event(user_id, event_name)
        context.user_data["state"] = "start"

    except asyncio.TimeoutError:
        logger.exception("Таймаут анализа фото")
        await update.message.reply_text("⏳ Анализ фото занял слишком много времени. Попробуйте еще раз.")
    except Exception:
        logger.exception("Ошибка анализа фото")
        await update.message.reply_text("❌ Не удалось обработать фото. Попробуйте другое изображение.")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    message_text = query.message.text or ""
    await query.answer()

    if query.data == "admin_stats_general" and user_id == ADMIN_ID:
        text = await get_admin_stats_text()
        await query.edit_message_text(text, reply_markup=admin_stats_keyboard(), parse_mode="HTML")
        return

    if query.data == "admin_stats_sources" and user_id == ADMIN_ID:
        text = await get_admin_sources_text()
        await query.edit_message_text(text, reply_markup=admin_stats_keyboard(), parse_mode="HTML")
        return

    if query.data == "admin_stats_today" and user_id == ADMIN_ID:
        text = await get_admin_today_text()
        await query.edit_message_text(text, reply_markup=admin_stats_keyboard(), parse_mode="HTML")
        return

    if query.data == "give_premium":
        if user_id == ADMIN_ID:
            context.user_data["state"] = "waiting_for_user_id"
            await context.bot.send_message(
                chat_id=user_id,
                text="👇 <b>Пришлите ID пользователя (только цифры):</b>",
                parse_mode="HTML"
            )
        return

    if query.data == "delete_user":
        if user_id == ADMIN_ID:
            context.user_data["state"] = "waiting_for_delete_id"
            await context.bot.send_message(
                chat_id=user_id,
                text="👇 <b>Пришлите ID пользователя</b>, которого нужно удалить из базы:",
                parse_mode="HTML"
            )
        return

    has_access = await check_access(user_id)
    if not has_access and query.data not in ["clear_saved", "clear_history", "clear_list"]:
        await context.bot.send_message(
            chat_id=user_id,
            text="⏳ Ваш бесплатный период завершен. Функция заблокирована 🔒"
        )
        return

    if query.data == "add_to_cart":
        try:
            match = re.search(r"(?i)Ингредиенты:(.*?)(?:Приготовление:|$)", message_text, re.DOTALL)
            ingredients = match.group(1).strip() if match else message_text
            await add_to_shopping_list(user_id, ingredients)
            await context.bot.send_message(chat_id=user_id, text="🛒 ✅ Ингредиенты добавлены в список продуктов!")
            await log_event(user_id, "add_to_cart")
        except Exception:
            logger.exception("Ошибка добавления в список покупок")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось добавить ингредиенты в список.")
        return

    if query.data == "save_recipe":
        try:
            last_recipe = context.user_data.get("last_recipe") or message_text
            await save_recipe_item(user_id, last_recipe)
            await context.bot.send_message(chat_id=user_id, text="⭐ ✅ Рецепт сохранен!")
            await log_event(user_id, "recipe_saved")
        except Exception:
            logger.exception("Ошибка сохранения рецепта")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось сохранить рецепт.")
        return

    if query.data == "replace_btn":
        context.user_data["state"] = "replace_ingredient"
        await context.bot.send_message(
            chat_id=user_id,
            text="🔄 <b>Напишите, какой продукт нужно заменить.</b>",
            parse_mode="HTML"
        )
        return

    if query.data == "another_recipe":
        limited, reason = await is_rate_limited(user_id)
        if limited:
            await context.bot.send_message(chat_id=user_id, text=f"⏳ {reason}")
            return

        await context.bot.send_message(chat_id=user_id, text="👨‍🍳 Ищу другой вариант...")
        old_prompt = context.user_data.get("last_prompt", "вкусное блюдо")
        user_prompt = f"Напиши АБСОЛЮТНО ДРУГОЙ рецепт по этому же запросу: {old_prompt}."
        try:
            recipe_text = await generate_recipe(user_id, "another_recipe", user_prompt)
            context.user_data["last_recipe"] = recipe_text
            await context.bot.send_message(
                chat_id=user_id,
                text=recipe_text,
                reply_markup=recipe_actions_keyboard()
            )
            await log_event(user_id, "another_recipe")
        except asyncio.TimeoutError:
            logger.exception("Таймаут другого варианта")
            await context.bot.send_message(chat_id=user_id, text="⏳ Шеф задержался. Попробуйте еще раз.")
        except Exception:
            logger.exception("Ошибка генерации другого варианта")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось подобрать другой вариант.")
        return

    if query.data == "clear_list":
        try:
            await clear_shopping_list(user_id)
            await query.edit_message_text("🛒 Список продуктов очищен!")
            await log_event(user_id, "shopping_list_cleared")
        except Exception:
            logger.exception("Ошибка очистки списка")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось очистить список.")
        return

    if query.data == "clear_saved":
        try:
            await clear_saved_recipes(user_id)
            await query.edit_message_text("🗑 Ваши сохраненные рецепты очищены!")
            await log_event(user_id, "saved_cleared")
        except Exception:
            logger.exception("Ошибка очистки saved")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось очистить сохраненные рецепты.")
        return

    if query.data == "clear_history":
        try:
            await clear_history(user_id)
            await query.edit_message_text("🗑 История рецептов очищена!")
            await log_event(user_id, "history_cleared")
        except Exception:
            logger.exception("Ошибка очистки history")
            await context.bot.send_message(chat_id=user_id, text="❌ Не удалось очистить историю.")
        return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Ошибка во время обработки апдейта", exc_info=context.error)

async def main():
    await init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_error_handler(error_handler)

    web_app = web.Application()
    web_app.router.add_post("/robokassa", robokassa_handler)
    web_app["bot"] = app.bot

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("🌍 Сервер Robokassa запущен на порту 8080")

    scheduler_task = None

    async with app:
        await app.start()
        await app.updater.start_polling()
        logger.info("🤖 Бот запущен")

        scheduler_task = asyncio.create_task(send_due_scheduled_messages(app))

        try:
            await asyncio.Event().wait()
        finally:
            if scheduler_task:
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except asyncio.CancelledError:
                    pass

if __name__ == "__main__":
    asyncio.run(main())
