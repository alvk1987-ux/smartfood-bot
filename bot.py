import os
import logging
from telegram.ext import Application

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def main():
    # Берем токен из переменных Railway
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        print("ОШИБКА: Переменная TELEGRAM_BOT_TOKEN не найдена в настройках Railway!")
        return

    print(f"Попытка запуска бота с токеном: {token[:10]}...")
    
    try:
        app = Application.builder().token(token).build()
        print("👨‍🍳 БОТ ПОДКЛЮЧИЛСЯ К TELEGRAM!")
        app.run_polling()
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ: {e}")

if __name__ == "__main__":
    main()
