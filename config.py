import os
from dotenv import load_dotenv

# Загружаем .env только для локального запуска.
# На GitHub Actions этого файла нет, и load_dotenv() просто проигнорирует его отсутствие.
load_dotenv()

# os.getenv сначала ищет переменную в окружении (GitHub Actions),
# а если не находит — берет из .env (локально).
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")
PROXY_API_URL = os.getenv("PROXY_API_URL", "https://tg-proxy.vadetion.workers.dev")
