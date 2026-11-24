import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Замените на юзернейм вашего канала (например, @my_channel) или числовой ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")
