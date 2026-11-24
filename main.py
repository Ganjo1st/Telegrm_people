import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, CHANNEL_ID
import database as db

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# ==========================================
# НАСТРОЙКИ ПРОКСИ (Cloudflare Worker)
# ==========================================
# ВАЖНО: Убедитесь, что здесь ВАШ реальный адрес с https://
PROXY_API_URL = "https://tg-proxy.vadetion.workers.dev" 

session = AiohttpSession(api=TelegramAPIServer.from_base(PROXY_API_URL))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- Состояния FSM ---
class ChannelStates(StatesGroup):
    waiting_for_link = State()

# --- Клавиатуры ---
def get_main_menu():
    """Главное меню пользователя."""
    kb = [
        [KeyboardButton(text="📢 Добавить свой канал")],
        [KeyboardButton(text="🎯 Получить задание (заработать баллы)")],
        [KeyboardButton(text="🏆 Мой профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_sub_check_kb(channel_link: str, channel_id: str):
    """Клавиатура для проверки подписки на канал из задания."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)],
        [InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data=f"check_task_{channel_id}")]
    ])
    return kb

# --- Хелперы ---
async def is_subscribed(user_id: int, channel_id: str) -> bool:
    """Проверяет подписку пользователя на конкретный канал."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки на {channel_id}: {e}")
        return False

# --- Обработчики ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db.register_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    
    # Проверяем, подписан ли на основной канал
    subscribed = await is_subscribed(message.from_user.id, CHANNEL_ID)
    
    if subscribed:
        await message.answer(
            f"Привет, {message.from_user.full_name}! 👋\n\n"
            "Ты в главном меню системы взаимного пиара.\n"
            "Выбирай действие на клавиатуре ниже.",
            reply_markup=get_main_menu()
        )
    else:
        channel_url = f"https://t.me/{CHANNEL_ID.replace('@', '')}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_url)],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_main_sub")]
        ])
        await message.answer("Для участия необходимо подписаться на наш канал.", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "check_main_sub")
async def process_check_main_sub(callback_query: types.CallbackQuery):
    if await is_subscribed(callback_query.from_user.id, CHANNEL_ID):
        await callback_query.message.delete()
        await callback_query.message.answer("Отлично! Ты подписан.", reply_markup=get_main_menu())
    else:
        await callback_query.answer("Ты еще не подписался.", show_alert=True)

# --- Добавление канала ---
@dp.message(F.text == "📢 Добавить свой канал")
async def add_channel_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Отправь мне ссылку на свой канал (например, https://t.me/my_channel).\n"
        "⚠️ Важно: добавь нашего бота в администраторы своего канала с правами на чтение сообщений, чтобы я мог проверять подписку!"
    )
    await state.set_state(ChannelStates.waiting_for_link)

@dp.message(ChannelStates.waiting_for_link)
async def add_channel_process(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not link.startswith("https://t.me/"):
        await message.answer("❌ Неверный формат ссылки. Она должна начинаться с https://t.me/")
        return

    channel_username = "@" + link.split("/")[-1]
    
    try:
        # Пытаемся получить информацию о канале, чтобы убедиться, что бот там админ
        chat = await bot.get_chat(channel_username)
        if chat.type not in ["channel", "supergroup"]:
            await message.answer("❌ Это не канал. Пожалуйста, отправь ссылку на канал.")
            return
            
        # Сохраняем канал в БД
        db.add_channel(message.from_user.id, link, channel_username)
        await message.answer(
            "✅ Твой канал успешно добавлен в очередь на продвижение!\n"
            "Тебе начислено 10 баллов. Теперь выполняй задания, чтобы заработать еще.",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: бот не может получить доступ к каналу. Убедись, что он добавлен в администраторы.\nДетали: {e}")
    
    await state.clear()

# --- Получение задания ---
@dp.message(F.text == "🎯 Получить задание (заработать баллы)")
async def get_task(message: types.Message):
    # Проверяем, не закончились ли каналы для показа
    task = db.get_random_channel_for_user(message.from_user.id)
    
    if not task:
        await message.answer("😔 Пока нет доступных заданий. Заходи позже, когда другие пользователи добавят свои каналы!")
        return
        
    channel_link, channel_id, owner_id = task
    
    await message.answer(
        f"🎯 <b>Новое задание!</b>\n\n"
        f"Подпишись на этот канал: {channel_link}\n\n"
        f"После подписки нажми кнопку ниже для проверки и получения 5 баллов.",
        reply_markup=get_sub_check_kb(channel_link, channel_id),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("check_task_"))
async def process_task_check(callback_query: types.CallbackQuery):
    channel_id = callback_query.data.replace("check_task_", "")
    user_id = callback_query.from_user.id
    
    if await is_subscribed(user_id, channel_id):
        db.mark_task_completed(user_id, channel_id)
        await callback_query.message.delete()
        await callback_query.message.answer(
            "✅ Задание выполнено! Тебе начислено 5 баллов.\n"
            "Можешь получить следующее задание.",
            reply_markup=get_main_menu()
        )
    else:
        await callback_query.answer("❌ Ты еще не подписался на этот канал. Подпишись и попробуй снова.", show_alert=True)

# --- Профиль ---
@dp.message(F.text == "🏆 Мой профиль")
async def show_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if user:
        # user: (id, username, channel_link, channel_id, points)
        points = user[4]
        channel = user[2] if user[2] else "Не добавлен"
        await message.answer(
            f"🏆 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user[0]}</code>\n"
            f"📢 Твой канал: {channel}\n"
            f"💰 Баллы: <b>{points}</b>\n\n"
            f"<i>(Баллы нужны для того, чтобы твой канал чаще показывали другим. Добавление канала +10, выполнение задания +5)</i>"
        )
    else:
        await message.answer("Профиль не найден. Напиши /start")

async def main():
    db.init_db() # Инициализируем БД при запуске
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
