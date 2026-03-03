import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from openai import OpenAI

# ================= НАСТРОЙКИ =================
# Вставьте сюда свои ключи
TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"
OPENAI_API_KEY = "ВАШ_КЛЮЧ_OPENAI"

# Ссылка на оплату Paywall (создайте товар "VIP Меню" за 299р)
PAYWALL_LINK = "https://paywall.pw/chef_vip" 
ADMIN_ID = 123456789  # Ваш ID

# Лимиты
FREE_RECIPES_LIMIT = 3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище пользователей (в памяти)
users_db = {}

def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    return OpenAI(
        api_key=OPENAI_API_KEY,
        base_url="https://api.proxyapi.ru/openai/v1" # Если нужен прокси
    )

# ================= КЛАВИАТУРЫ =================
def get_main_keyboard(is_vip=False):
    keyboard = [
        [KeyboardButton("🍳 Что приготовить? (Из продуктов)")],
        [KeyboardButton("📅 Меню на неделю (VIP)")],
        [KeyboardButton("👤 Мой профиль")]
    ]
    if not is_vip:
        keyboard.append([KeyboardButton("💎 КУПИТЬ VIP (299₽)")])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= ЛОГИКА БОТА =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    
    if uid not in users_db:
        users_db[uid] = {"vip": False, "recipes_today": 0}
    
    await update.message.reply_text(
        f"👨‍🍳 **Привет, я твой AI Шеф-повар!**\n\n"
        f"Не знаешь, что приготовить? Просто напиши мне список продуктов, которые есть в холодильнике!\n\n"
        f"Например: *Курица, картошка, сметана*\n\n"
        f"👇 Жми кнопку ниже:",
        reply_markup=get_main_keyboard(users_db[uid]["vip"]),
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    uid = user.id
    
    if uid not in users_db:
        users_db[uid] = {"vip": False, "recipes_today": 0}

    # --- ЛОГИКА КНОПОК ---
    
    if text == "💎 КУПИТЬ VIP (299₽)":
        keyboard = [[InlineKeyboardButton("💳 Оплатить доступ", url=PAYWALL_LINK)]]
        await update.message.reply_text(
            "💎 **VIP ДОСТУП ШЕФ-ПОВАРА**\n\n"
            "Что вы получите за 299₽ (навсегда):\n"
            "✅ Составление меню на неделю (ПП, Кето, Дешево)\n"
            "✅ Автоматический список покупок\n"
            "✅ Безлимитные рецепты\n"
            "✅ Подбор вина и соусов\n\n"
            "👇 Нажмите кнопку для оплаты:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if text == "👤 Мой профиль":
        status = "👑 VIP Шеф" if users_db[uid]["vip"] else "Обычный повар"
        limit = "Безлимит" if users_db[uid]["vip"] else f"{FREE_RECIPES_LIMIT - users_db[uid]['recipes_today']} шт."
        await update.message.reply_text(
            f"👤 **Ваш профиль:**\n"
            f"Статус: {status}\n"
            f"Осталось рецептов сегодня: {limit}"
        )
        return

    if text == "📅 Меню на неделю (VIP)":
        if not users_db[uid]["vip"]:
            await update.message.reply_text("❌ Эта функция доступна только VIP пользователям!\nКупите доступ за 299₽.")
            return
        
        # Если VIP - спрашиваем детали
        context.user_data['waiting_for'] = 'weekly_plan'
        await update.message.reply_text("Напишите ваши предпочтения:\nНапример: *ПП меню на 1500 ккал* или *Бюджетное меню для студента*")
        return

    if text == "🍳 Что приготовить? (Из продуктов)":
        context.user_data['waiting_for'] = 'ingredients'
        await update.message.reply_text("📝 **Напишите список продуктов через запятую:**\n\nПример: *Яйца, помидор, старый хлеб, сыр*")
        return

    # --- ОБРАБОТКА ТЕКСТА (ИНГРЕДИЕНТЫ) ---
    
    waiting = context.user_data.get('waiting_for')
    
    if waiting == 'ingredients':
        # Проверка лимитов
        if not users_db[uid]["vip"] and users_db[uid]["recipes_today"] >= FREE_RECIPES_LIMIT:
            await update.message.reply_text("❌ **Лимит на сегодня исчерпан!**\n\nКупите VIP за 299₽ для безлимита.", reply_markup=get_main_keyboard(False))
            return

        ingredients = text
        await update.message.reply_text("👨‍🍳 **Шеф думает...** Подбираю лучший рецепт...")
        
        try:
            client = get_openai_client()
            prompt = f"Ты шеф-повар со звездой Мишлен. У меня есть продукты: {ingredients}. Придумай вкусный, креативный, но простой рецепт. Напиши: 1. Название блюда (с эмодзи). 2. Время готовки. 3. Ингредиенты. 4. Пошаговый рецепт. Пиши вкусно и аппетитно!"
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            recipe = response.choices[0].message.content
            
            # Списываем лимит
            if not users_db[uid]["vip"]:
                users_db[uid]["recipes_today"] += 1
            
            await update.message.reply_text(recipe, parse_mode=ParseMode.MARKDOWN)
            
            # Реклама VIP после рецепта
            if not users_db[uid]["vip"]:
                await update.message.reply_text("💡 Хотите меню на всю неделю с списком покупок? Жмите 'Купить VIP'!")
                
        except Exception as e:
            logger.error(e)
            await update.message.reply_text("Ошибка AI. Попробуйте позже.")
            
        context.user_data['waiting_for'] = None
        return

    if waiting == 'weekly_plan' and users_db[uid]["vip"]:
        preferences = text
        await update.message.reply_text("📅 **Составляю меню и список покупок...** Это займет около 30 секунд.")
        
        try:
            client = get_openai_client()
            prompt = f"Составь подробное меню на 7 дней с учетом пожеланий: {preferences}. Также в конце напиши полный список продуктов для магазина, разбитый по отделам. Оформи красиво."
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            plan = response.choices[0].message.content
            await update.message.reply_text(plan, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text("Ошибка создания плана.")
            
        context.user_data['waiting_for'] = None
        return

# Команда для вас (активировать VIP вручную другу или себе)
async def admin_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        if target_id not in users_db: users_db[target_id] = {}
        users_db[target_id]["vip"] = True
        await update.message.reply_text(f"✅ VIP активирован для {target_id}")
    except:
        await update.message.reply_text("Пиши: /activate ID_ПОЛЬЗОВАТЕЛЯ")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", admin_activate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("👨‍🍳 ШЕФ-ПОВАР ЗАПУЩЕН!")
    app.run_polling()

if __name__ == "__main__":
    main()
