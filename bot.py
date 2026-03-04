import os
from telegram.ext import Application

print("=== НАЧАЛО ЗАПУСКА ===")

# Проверяем токен
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ ОШИБКА: ТОКЕН НЕ НАЙДЕН! Проверьте название переменной во вкладке Variables в Railway. Должно быть TELEGRAM_BOT_TOKEN")
else:
    print(f"✅ Токен найден (начинается на {TOKEN[:5]}...)")
    print("Пробуем подключиться к Telegram...")
    
    try:
        app = Application.builder().token(TOKEN).build()
        print("🚀 БОТ УСПЕШНО ПОДКЛЮЧЕН И РАБОТАЕТ!")
        app.run_polling()
    except Exception as e:
        print(f"❌ ОШИБКА ПРИ ПОДКЛЮЧЕНИИ: {e}")
