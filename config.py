import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")
PROXY_API_URL = os.getenv("PROXY_API_URL", "https://tg-proxy.vadetion.workers.dev")

# Ваш ID для админ-панели (берется из секретов GitHub или .env)
SUPER_ADMIN_ID = int(os.getenv("USER_ID", 0))
