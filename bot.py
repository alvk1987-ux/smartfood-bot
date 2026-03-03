import os
import logging
import json
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# НАСТРОЙКИ ВАШЕГО КАНАЛА И PAYWALL
PREMIUM_CHANNEL_ID = "@smartfood_premium"  # Ваш платный канал
CHANNEL_PAYMENT_LINK = "https://paywall.pw/smartfood_premium"  # Ваша ссылка оплаты
TRIAL_DAYS = 2
PRICE = 399

# Хранилище данных
users_db = {}
meals_db = {}

async def check_subscription(context, user_id):
    """Проверка подписки на платный канал"""
    try:
        member = await context.bot.get_chat_member(
            chat_id=PREMIUM_CHANNEL_ID,
            user_id=user_id
        )
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Check subscription error: {e}")
        return False

def get_user_status(user_id):
    """Получение статуса пользователя"""
    user_id = str(user_id)
    
    if user_id not in users_db:
        return 'new', TRIAL_DAYS
    
    user = users_db[user_id]
    now = datetime.now()
    
    # Проверяем триал
    if 'trial_start' in user:
        trial_start = datetime.fromisoformat(user['trial_start'])
        trial_end = trial_start + timedelta(days=TRIAL_DAYS)
        
        if now <= trial_end:
            hours_left = int((trial_end - now).total_seconds() / 3600)
            days_left = hours_left // 24
            if days_left > 0:
                return 'trial', f"{days_left}д {hours_left % 24}ч"
            else:
                return 'trial', f"{hours_left} часов"
        else:
            return 'expired', 0
    
    return 'expired', 0

def get_keyboard(has_access=False):
    """Клавиатура в зависимости от доступа"""
    if has_access:
        keyboard = [
            [KeyboardButton("🧮 КБЖУ"), KeyboardButton("⚖️ Мой вес")],
            [KeyboardButton("🌅 Завтрак"), KeyboardButton("🍎 Перекус")],
            [KeyboardButton("🍽 Обед"), KeyboardButton("🌙 Ужин")],
            [KeyboardButton("💧 Вода"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Вопрос о еде"), KeyboardButton("💳 Моя подписка")]
        ]
    else:
        keyboard = [
            [KeyboardButton("💳 Купить доступ 399₽")],
            [KeyboardButton("✅ Я оплатил и вступил в канал")],
            [KeyboardButton("ℹ️ Что умеет бот?")],
            [KeyboardButton("📞 Поддержка")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Новый пользователь
    if user_id not in users_db:
        users_db[user_id] = {
            "name": user.first_name,
            "trial_start": datetime.now().isoformat(),
            "joined": datetime.now().isoformat()
        }
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🎁 **ПОДАРОК: 2 ДНЯ БЕСПЛАТНО!**\n"
            f"Все функции доступны 48 часов!\n\n"
            f"🤖 Я SmartFood AI - твой дневник питания!\n\n"
            f"✨ Что я умею:\n"
            f"• Считаю калории любых блюд\n"
            f"• Веду дневник питания\n"
            f"• Рассчитываю норму КБЖУ\n"
            f"• Отвечаю на вопросы о питании\n\n"
            f"📝 Просто пиши что съел - я посчитаю!\n\n"
            f"⏰ После 2 дней - подписка 399₽/месяц\n\n"
            f"Начни с расчета КБЖУ 👇",
            reply_markup=get_keyboard(True),
            parse_mode='Markdown'
        )
        
        # Планируем напоминание
        await schedule_trial_reminder(context, int(user_id))
        
    else:
        # Существующий пользователь
        status, time_left = get_user_status(user.id)
        has_premium = await check_subscription(context, user.id)
        
        if has_premium:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"✅ Подписка на канал активна!\n"
                f"Все функции разблокированы!\n\n"
                f"Выбери действие 👇",
                reply_markup=get_keyboard(True)
            )
        elif status == 'trial':
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"🎁 Пробный период активен!\n"
                f"⏰ Осталось: {time_left}\n\n"
                f"Выбери действие 👇",
                reply_markup=get_keyboard(True)
            )
        else:
            await update.message.reply_text(
                f"👋 С возвращением, {user.first_name}!\n\n"
                f"❌ Пробный период завершен!\n\n"
                f"Для продолжения нужна подписка:\n"
                f"💰 399₽/месяц (13₽/день)\n\n"
                f"Нажми для оплаты 👇",
                reply_markup=get_keyboard(False)
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # === КНОПКИ БЕЗ ПОДПИСКИ ===
    
    if text == "💳 Купить доступ 399₽":
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить на Paywall", url=CHANNEL_PAYMENT_LINK)],
            [InlineKeyboardButton("📹 Видео как оплатить", url="https://youtube.com/watch?v=xxx")]  # Можете добавить видео-инструкцию
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status, time_left = get_user_status(user_id)
        trial_text = f"⏰ У вас еще {time_left} бесплатного доступа!\n\n" if status == 'trial' else ""
        
        await update.message.reply_text(
            f"💳 **ОФОРМЛЕНИЕ ПОДПИСКИ**\n\n"
            f"{trial_text}"
            f"💰 Стоимость: 399₽/месяц\n"
            f"Это всего 13₽ в день!\n\n"
            f"✅ Что получаете:\n"
            f"• Доступ к каналу {PREMIUM_CHANNEL_ID}\n"
            f"• AI-анализ любых блюд\n"
            f"• Дневник питания\n"
            f"• Персональные рекомендации\n"
            f"• Поддержка 24/7\n\n"
            f"📝 **КАК ОПЛАТИТЬ:**\n"
            f"1️⃣ Нажмите 'Оплатить на Paywall'\n"
            f"2️⃣ Оплатите картой (399₽)\n"
            f"3️⃣ После оплаты вы получите ссылку\n"
            f"4️⃣ Вступите в канал по ссылке\n"
            f"5️⃣ Вернитесь и нажмите 'Я оплатил'\n\n"
            f"🔒 Безопасная оплата через Paywall\n"
            f"✅ Автопродление можно отключить",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    elif text == "✅ Я оплатил и вступил в канал":
        await update.message.reply_text("⏳ Проверяю подписку...")
        
        # Проверяем подписку на канал
        has_premium = await check_subscription(context, user_id)
        
        if has_premium:
            users_db[user_id_str]['has_premium'] = True
            users_db[user_id_str]['premium_activated'] = datetime.now().isoformat()
            
            await update.message.reply_text(
                "✅ **ПОДПИСКА ПОДТВЕРЖДЕНА!**\n\n"
                "🎉 Добро пожаловать в Premium!\n\n"
                "Теперь вам доступны:\n"
                "• Все функции бота\n"
                "• Эксклюзивный контент в канале\n"
                "• Приоритетная поддержка\n\n"
                "Приятного использования! 🚀",
                reply_markup=get_keyboard(True),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ **Подписка не найдена!**\n\n"
                "Проверьте:\n"
                f"1️⃣ Оплатили ли вы на Paywall?\n"
                f"2️⃣ Вступили ли в канал {PREMIUM_CHANNEL_ID}?\n\n"
                "После оплаты на Paywall:\n"
                "• Вы получите ссылку на канал\n"
                "• Перейдите по ссылке\n"
                "• Вступите в канал\n"
                "• Вернитесь сюда и нажмите снова\n\n"
                "Если оплатили только что - подождите 30 секунд",
                reply_markup=get_keyboard(False),
                parse_mode='Markdown'
            )
        return
    
    elif text == "ℹ️ Что умеет бот?":
        await update.message.reply_text(
            "🤖 **SMARTFOOD AI - ВАШ ДИЕТОЛОГ**\n\n"
            "🎯 **Главная фишка:**\n"
            "Пишете 'съел борщ' - получаете КБЖУ!\n"
            "Не нужно искать в таблицах!\n\n"
            "📱 **Возможности:**\n"
            "• Расчет личной нормы КБЖУ\n"
            "• AI-анализ любых блюд\n"
            "• Дневник всех приемов пищи\n"
            "• Контроль воды (8 стаканов)\n"
            "• График веса\n"
            "• 10 вопросов диетологу в день\n"
            "• Статистика и отчеты\n\n"
            "💰 **Стоимость:**\n"
            "Первые 2 дня - БЕСПЛАТНО\n"
            "Далее - 399₽/месяц\n\n"
            "🎁 **Бонус:**\n"
            "Доступ к закрытому каналу с рецептами",
            parse_mode='Markdown'
        )
        return
    
    elif text == "📞 Поддержка":
        await update.message.reply_text(
            "📞 **ПОДДЕРЖКА**\n\n"
            "Есть вопросы? Пишите:\n"
            "📧 @your_support_username\n\n"
            "Частые вопросы:\n\n"
            "❓ Как оплатить?\n"
            "Нажмите 'Купить доступ' и следуйте инструкции\n\n"
            "❓ Не приходит ссылка после оплаты?\n"
            "Проверьте папку спам или напишите в поддержку\n\n"
            "❓ Можно ли отменить подписку?\n"
            "Да, в любой момент на Paywall",
            parse_mode='Markdown'
        )
        return
    
    elif text == "💳 Моя подписка":
        status, time_left = get_user_status(user_id)
        has_premium = await check_subscription(context, user_id)
        
        if has_premium:
            status_text = "✅ Подписка активна\nДоступ к каналу подтвержден"
        elif status == 'trial':
            status_text = f"🎁 Пробный период\n⏰ Осталось: {time_left}"
        else:
            status_text = "❌ Нет активной подписки"
        
        keyboard = [
            [InlineKeyboardButton("💳 Управление подпиской", url=CHANNEL_PAYMENT_LINK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💳 **СТАТУС ПОДПИСКИ**\n\n"
            f"{status_text}\n\n"
            f"Тариф: 399₽/месяц\n"
            f"Канал: {PREMIUM_CHANNEL_ID}\n\n"
            f"Для управления подпиской нажмите кнопку ниже",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # === ПРОВЕРКА ДОСТУПА ===
    
    status, time_left = get_user_status(user_id)
    has_premium = await check_subscription(context, user_id)
    
    # Если нет доступа
    if not has_premium and status != 'trial':
        await update.message.reply_text(
            "❌ **Пробный период завершен!**\n\n"
            "Для доступа к функциям нужна подписка\n"
            "💰 Всего 399₽/месяц\n\n"
            "Нажмите 'Купить доступ' 👇",
            reply_markup=get_keyboard(False),
            parse_mode='Markdown'
        )
        return
    
    # === ФУНКЦИИ ДЛЯ ПОДПИСЧИКОВ ===
    
    if text == "🧮 КБЖУ":
        await update.message.reply_text(
            "🧮 **РАСЧЕТ ВАШЕЙ НОРМЫ**\n\n"
            "Напишите одним сообщением:\n"
            "Пол, возраст, вес, рост, активность, цель\n\n"
            "📝 Пример:\n"
            "Женщина, 25 лет, 60 кг, 170 см, средняя активность, похудеть",
            parse_mode='Markdown'
        )
    
    elif text == "⚖️ Мой вес":
        await update.message.reply_text("⚖️ Введите ваш текущий вес (кг):")
    
    elif text in ["🌅 Завтрак", "🍎 Перекус", "🍽 Обед", "🌙 Ужин"]:
        await update.message.reply_text(
            f"{text}\n\n"
            "📝 Напишите что съели:\n\n"
            "Примеры:\n"
            "• Овсянка с бананом и медом\n"
            "• Куриная грудка 150г с рисом\n"
            "• Борщ со сметаной, 2 куска хлеба"
        )
    
    elif text == "💧 Вода":
        await update.message.reply_text(
            "💧 **+250 мл**\n\n"
            "Отлично! Записал стакан воды.\n"
            "Сегодня: 250/2000 мл",
            parse_mode='Markdown'
        )
    
    elif text == "📊 Статистика":
        await update.message.reply_text(
            "📊 **СТАТИСТИКА ДНЯ**\n\n"
            "🔥 Калории: 0/2000 ккал\n"
            "🥩 Белки: 0/100 г\n"
            "🥑 Жиры: 0/70 г\n"
            "🍞 Углеводы: 0/250 г\n"
            "💧 Вода: 0/2000 мл\n\n"
            "Начните записывать приемы пищи!",
            parse_mode='Markdown'
        )
    
    elif text == "❓ Вопрос о еде":
        await update.message.reply_text(
            "❓ **ЗАДАЙТЕ ВОПРОС**\n\n"
            "Напишите любой вопрос о питании.\n"
            "Осталось вопросов сегодня: 10/10\n\n"
            "Примеры:\n"
            "• Что есть после тренировки?\n"
            "• Как убрать живот?\n"
            "• Полезен ли кефир на ночь?",
            parse_mode='Markdown'
        )
    
    else:
        # Если текст не кнопка - считаем что это ответ на вопрос
        await update.message.reply_text(
            "Используйте кнопки меню 👇",
            reply_markup=get_keyboard(has_premium or status == 'trial')
        )

async def schedule_trial_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Планирование напоминания об окончании триала"""
    # Напоминание за 6 часов до конца
    context.job_queue.run_once(
        send_trial_reminder,
        when=timedelta(days=TRIAL_DAYS, hours=-6),
        data=user_id,
        name=f"reminder_{user_id}"
    )

async def send_trial_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминания"""
    user_id = context.job.data
    
    keyboard = [
        [InlineKeyboardButton("💳 Оформить подписку", url=CHANNEL_PAYMENT_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=user_id,
        text="⏰ **ПРОБНЫЙ ПЕРИОД ЗАКАНЧИВАЕТСЯ!**\n\n"
             "Осталось 6 часов!\n\n"
             "Оформите подписку сейчас:\n"
             "✅ Не потеряете данные\n"
             "✅ Продолжите без перерыва\n"
             "✅ Получите полный доступ\n\n"
             "💰 Всего 399₽/месяц",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def main():
    """Запуск бота"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN!")
        return
    
    logger.info("Starting bot...")
    app = Application.builder().token(token).build()
    
    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
