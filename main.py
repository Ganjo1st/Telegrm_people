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

logging.basicConfig(level=logging.INFO)

PROXY_API_URL = "https://tg-proxy.vadetion.workers.dev" 

session = AiohttpSession(api=TelegramAPIServer.from_base(PROXY_API_URL))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class ChannelStates(StatesGroup):
    waiting_for_link = State()

def get_main_menu():
    kb = [
        [KeyboardButton(text="📢 Добавить свой канал")],
        [KeyboardButton(text="🎯 Получить задание (заработать баллы)")],
        [KeyboardButton(text="🏆 Мой профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_sub_check_kb(channel_link: str, channel_id: str):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)],
        [InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data=f"check_task_{channel_id}")]
    ])
    return kb

async def is_subscribed(user_id: int, channel_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки на {channel_id}: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db.register_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    
    if await is_subscribed(message.from_user.id, CHANNEL_ID):
        await message.answer(
            f"Привет, {message.from_user.full_name}! 👋\n\n"
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

@dp.message(F.text == "📢 Добавить свой канал")
async def add_channel_start(message: types.Message, state: FSMContext):
    # Проверка: не добавил ли он уже канал
    user = db.get_user(message.from_user.id)
    if user and user[2]:
        await message.answer("❌ Ты уже добавил канал. Один пользователь может продвигать только один канал.")
        return
        
    await message.answer(
        "Отправь мне ссылку на свой канал (например, https://t.me/my_channel).\n"
        "⚠️ Важно: добавь нашего бота в администраторы своего канала!"
    )
    await state.set_state(ChannelStates.waiting_for_link)

@dp.message(ChannelStates.waiting_for_link)
async def add_channel_process(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not link.startswith("https://t.me/"):
        await message.answer("❌ Неверный формат ссылки. Она должна начинаться с https://t.me/")
        return

    channel_username = "@" + link.split("/")[-1]
    
    # Проверка на дубликат
    if db.get_user_by_channel(channel_username):
        await message.answer("❌ Этот канал уже добавлен в систему другим пользователем.")
        await state.clear()
        return
    
    try:
        chat = await bot.get_chat(channel_username)
        
        if chat.type not in ["channel", "supergroup"]:
            await message.answer("❌ Это не канал. Пожалуйста, отправь ссылку на канал.")
            return
            
        # Защита от пустых каналов (если есть информация о количестве участников)
        member_count = await bot.get_chat_member_count(channel_username)
        if member_count < 20: # Минимальный порог
            await message.answer(f"❌ В твоем канале слишком мало подписчиков ({member_count}). Для участия нужно минимум 20.")
            return
            
        db.add_channel(message.from_user.id, link, channel_username)
        await message.answer(
            "✅ Твой канал успешно добавлен в очередь!\n"
            "Тебе начислено 10 баллов. Теперь выполняй задания, чтобы заработать еще.",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: бот не может получить доступ к каналу. Убедись, что он добавлен в администраторы.\nДетали: {e}")
    
    await state.clear()

@dp.message(F.text == "🎯 Получить задание (заработать баллы)")
async def get_task(message: types.Message):
    task = db.get_random_channel_for_user(message.from_user.id)
    
    if not task:
        await message.answer("😔 Пока нет доступных заданий (или у всех закончились баллы). Заходи позже!")
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
        await callback_query.answer("❌ Ты еще не подписался. Подпишись и попробуй снова.", show_alert=True)

@dp.message(F.text == "🏆 Мой профиль")
async def show_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if user:
        points = user[4]
        channel = user[2] if user[2] else "Не добавлен"
        
        # Пояснение по баллам
        if points > 0:
            status = "Твой канал участвует в показах."
        else:
            status = "⚠️ У тебя 0 баллов. Твой канал не показывается другим. Выполни задания, чтобы заработать!"
            
        await message.answer(
            f"🏆 <b>Твой профиль:</b>\n\n"
            f"📢 Твой канал: {channel}\n"
            f"💰 Баллы: <b>{points}</b>\n"
            f"📊 Статус: {status}\n\n"
            f"<i>(+10 за добавление, +5 за выполнение, -1 за каждый показ твоего канала другим)</i>"
        )
    else:
        await message.answer("Профиль не найден. Напиши /start")

async def main():
    db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
