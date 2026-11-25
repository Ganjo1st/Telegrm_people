import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, CHANNEL_ID, PROXY_API_URL, SUPER_ADMIN_ID
import database as db

logging.basicConfig(level=logging.INFO)

MIN_SUBSCRIBERS = 50  # Для обычных пользователей

session = AiohttpSession(api=TelegramAPIServer.from_base(PROXY_API_URL))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния
class ChannelStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_broadcast_text = State()  # Для ввода текста рассылки

# --- Клавиатуры ---
def get_main_menu(user_id: int):
    kb = [
        [KeyboardButton(text="📢 Добавить свой канал")],
        [KeyboardButton(text="🗑 Удалить мой канал")],
        [KeyboardButton(text="🎯 Получить задание (заработать баллы)")],
        [KeyboardButton(text="🏆 Мой профиль"), KeyboardButton(text="👥 Пригласить друга")]
    ]
    if user_id == SUPER_ADMIN_ID:
        kb.append([KeyboardButton(text="👑 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_sub_check_kb(channel_link: str, channel_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)],
        [InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data=f"check_task_{channel_id}")]
    ])

# --- Вспомогательные функции ---
async def is_subscribed(user_id: int, channel_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception:
        return False

async def check_channel_alive(channel_id: str) -> bool:
    try:
        await bot.get_chat(chat_id=channel_id)
        return True
    except Exception:
        return False

# --- Обработчики ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)

    db.register_user(message.from_user.id, message.from_user.username or message.from_user.first_name, referrer_id)
    
    if await is_subscribed(message.from_user.id, CHANNEL_ID):
        await message.answer(
            f"Привет, {message.from_user.full_name}! 👋\n\n"
            "Выбирай действие на клавиатуре ниже.",
            reply_markup=get_main_menu(message.from_user.id)
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
        await callback_query.message.answer("Отлично! Ты подписан.", reply_markup=get_main_menu(callback_query.from_user.id))
    else:
        await callback_query.answer("Ты еще не подписался.", show_alert=True)

# --- Админ-панель ---
@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: types.Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать промо-рассылку", callback_data="admin_create_broadcast")],
        [InlineKeyboardButton(text="💰 Начислить баллы", callback_data="admin_add_points_menu")]
    ])
    await message.answer("👑 Добро пожаловать в админ-панель.", reply_markup=kb)

@dp.callback_query(F.data == "admin_create_broadcast")
async def admin_create_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != SUPER_ADMIN_ID:
        return
    await callback_query.message.answer("Введите текст промо-сообщения для рассылки (можно использовать HTML):")
    await state.set_state(ChannelStates.waiting_for_broadcast_text)
    await callback_query.answer()

@dp.message(ChannelStates.waiting_for_broadcast_text)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    # Сохраняем текст и показываем предпросмотр с кнопками утверждения
    await state.update_data(broadcast_text=message.text)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Утверждаю", callback_data="approve_broadcast")],
        [InlineKeyboardButton(text="❌ Отклоняю", callback_data="reject_broadcast")]
    ])
    
    await message.answer(
        f"<b>Предпросмотр рассылки:</b>\n\n{message.text}\n\n"
        f"<i>Нажмите кнопку для подтверждения.</i>",
        reply_markup=kb
    )
    await state.clear()

@dp.callback_query(F.data == "approve_broadcast")
async def approve_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != SUPER_ADMIN_ID:
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    if not text:
        await callback_query.answer("Текст не найден. Попробуйте снова.", show_alert=True)
        return

    await callback_query.message.edit_text("🚀 Рассылка утверждена. Начинаю отправку...")
    
    # Получаем всех пользователей из БД (нужно добавить функцию в database.py)
    # Для простоты создадим inline-запрос здесь, но лучше вынести в БД
    import sqlite3
    conn = sqlite3.connect("pr_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    success = 0
    fail = 0
    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text, disable_web_page_preview=True)
            success += 1
            # Задержка, чтобы не получить бан (лимит Telegram ~30 сообщений/сек)
            await asyncio.sleep(0.1) 
        except Exception:
            fail += 1
    
    await bot.send_message(SUPER_ADMIN_ID, f"✅ Рассылка завершена.\nУспешно: {success}\nОшибок: {fail}")
    await callback_query.answer()

@dp.callback_query(F.data == "reject_broadcast")
async def reject_broadcast(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != SUPER_ADMIN_ID:
        return
    await callback_query.message.edit_text("❌ Рассылка отклонена.")
    await callback_query.answer()

# --- Добавление канала (с проверкой для супер-админа) ---
@dp.message(F.text == "📢 Добавить свой канал")
async def add_channel_start(message: types.Message, state: FSMContext):
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
    
    if db.get_user_by_channel(channel_username):
        await message.answer("❌ Этот канал уже добавлен в систему другим пользователем.")
        await state.clear()
        return
    
    try:
        chat = await bot.get_chat(channel_username)
        
        if chat.type not in ["channel", "supergroup"]:
            await message.answer("❌ Это не канал. Пожалуйста, отправь ссылку на канал.")
            return
            
        member_count = await bot.get_chat_member_count(channel_username)
        
        # ПРОВЕРКА: Если это не супер-админ, требуем 50 подписчиков
        if message.from_user.id != SUPER_ADMIN_ID and member_count < MIN_SUBSCRIBERS:
            await message.answer(f"❌ В твоем канале слишком мало подписчиков ({member_count}). Для участия нужно минимум {MIN_SUBSCRIBERS}.")
            return
            
        db.add_channel(message.from_user.id, link, channel_username)
        await message.answer(
            "✅ Твой канал успешно добавлен в очередь!\n"
            "Тебе начислено 10 баллов.",
            reply_markup=get_main_menu(message.from_user.id)
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: бот не может получить доступ к каналу.\nДетали: {e}")
    
    await state.clear()

# --- Остальные обработчики (без изменений, но с передачей user_id в меню) ---
@dp.message(F.text == "🗑 Удалить мой канал")
async def remove_channel_handler(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or not user[2]:
        await message.answer("❌ У тебя нет добавленного канала.")
        return
    db.remove_channel(message.from_user.id)
    await message.answer("✅ Твой канал удален.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🎯 Получить задание (заработать баллы)")
async def get_task(message: types.Message):
    task = db.get_random_channel_for_user(message.from_user.id)
    if not task:
        await message.answer("😔 Пока нет доступных заданий.")
        return
        
    channel_link, channel_id, owner_id = task
    if not await check_channel_alive(channel_id):
        db.mark_channel_inactive(owner_id)
        await message.answer("⚠️ Попался неактивный канал. Ищем другое...")
        await asyncio.sleep(1)
        await get_task(message)
        return

    await message.answer(
        f"🎯 <b>Новое задание!</b>\n\nПодпишись на этот канал: {channel_link}\n\n"
        f"После подписки нажми кнопку ниже.",
        reply_markup=get_sub_check_kb(channel_link, channel_id),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("check_task_"))
async def process_task_check(callback_query: types.CallbackQuery):
    channel_id = callback_query.data.replace("check_task_", "")
    if await is_subscribed(callback_query.from_user.id, channel_id):
        db.mark_task_completed(callback_query.from_user.id, channel_id)
        await callback_query.message.delete()
        await callback_query.message.answer("✅ Задание выполнено! +5 баллов.", reply_markup=get_main_menu(callback_query.from_user.id))
    else:
        await callback_query.answer("❌ Ты еще не подписался.", show_alert=True)

@dp.message(F.text == "👥 Пригласить друга")
async def invite_friend(message: types.Message):
    bot_username = (await bot.me()).username
    ref_link = f"https://t.me/{bot_username}?start={message.from_user.id}"
    count = db.get_referral_count(message.from_user.id)
    
    share_text = "Присоединяйся к системе взаимного пиара! Бонус за вход по ссылке."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text={share_text}")]
    ])
    await message.answer(
        f"👥 За друга +50 баллов (друг получает +10).\n\n"
        f"🔗 <code>{ref_link}</code>\n\n"
        f"📊 Приглашено: {count}",
        reply_markup=kb
    )

@dp.message(F.text == "🏆 Мой профиль")
async def show_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if user:
        points, channel, views = user[4], user[2] or "Нет", user[7] if len(user) > 7 else 0
        is_active = "✅" if user[5] == 1 else "❌"
        await message.answer(
            f"🏆 <b>Профиль:</b>\n\n📢 {channel} {is_active}\n"
            f"💰 Баллы: <b>{points}</b>\n👁 Показов: {views}"
        )
    else:
        await message.answer("Напиши /start")

async def main():
    db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.wait_for(dp.start_polling(bot), timeout=5.83 * 3600)
    except asyncio.TimeoutError:
        logging.info("Завершение по таймауту...")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
