import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")
PROXY_API_URL = os.getenv("PROXY_API_URL", "https://tg-proxy.vadetion.workers.dev")
SUPER_ADMIN_ID = os.getenv("USER_ID")
