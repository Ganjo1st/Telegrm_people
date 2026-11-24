import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла (для локальной разработки)
load_dotenv()

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID вашего канала (например, @my_news_channel или -1001234567890)
# Замените на ваш реальный ID или юзернейм
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username") 
