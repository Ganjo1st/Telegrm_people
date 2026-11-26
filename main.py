import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ChatAdministratorRights

from config import BOT_TOKEN, CHANNEL_ID, PROXY_API_URL, SUPER_ADMIN_ID
import database as db

logging.basicConfig(level=logging.INFO)

MIN_SUBSCRIBERS = 50

session = AiohttpSession(api=TelegramAPIServer.from_base(PROXY_API_URL))
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния больше не нужны для рассылки, оставляем пустым или убираем
# class ChannelStates(StatesGroup):
#     pass

def get_main_menu(user_id: int):
    kb = [
        [KeyboardButton(text="📢 Добавить свой канал")],
        [KeyboardButton(text="🗑 Удалить мой канал")],
        [KeyboardButton(text="🎯 Получить задание (заработать баллы)")],
        [KeyboardButton(text="🏆 Мой профиль"), KeyboardButton(text="👥 Пригласить друга")]
    ]
    # Убрали кнопку "Админ-панель", так как рассылка удалена
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_sub_check_kb(channel_link: str, channel_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)],
        [InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data=f"check_task_{channel_id}")]
    ])

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

@dp.my_chat_member()
async def on_bot_promoted_to_admin(event: types.ChatMemberUpdated):
    if event.new_chat_member.status != "administrator":
        return
    chat = event.chat
    user_id = event.from_user.id
    if chat.type != "channel":
        return
    existing = db.get_user_by_channel(f"@{chat.username}" if chat.username else str(chat.id))
    if existing and existing[5] == 1:
        return
    member_count = await bot.get_chat_member_count(chat.id)
    if user_id != SUPER_ADMIN_ID and member_count < MIN_SUBSCRIBERS:
        return
    channel_link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{chat.id}"
    channel_id = f"@{chat.username}" if chat.username else str(chat.id)
    db.add_channel(user_id, channel_link, channel_id)
    await bot.send_message(user_id, f"✅ Канал «{chat.title}» успешно подключён!")

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)

    db.register_user(message.from_user.id, message.from_user.username or message.from_user.first_name, referrer_id)
    
    if await is_subscribed(message.from_user.id, CHANNEL_ID):
        await message.answer(
            f"Привет, {message.from_user.full_name}! 👋\n\nВыбирай действие на клавиатуре ниже.",
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

@dp.message(F.text == "📢 Добавить свой канал")
async def add_channel_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if user and user[2]:
        await message.answer("❌ Ты уже добавил канал.")
        return

    bot_username = (await bot.me()).username
    add_link = f"https://t.me/{bot_username}?startchannel&admin=post_messages+edit_messages+delete_messages"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подключить сервис", url=add_link)]
    ])

    await message.answer(
        "Чтобы добавить канал, нажмите кнопку ниже.\n\n"
        "👇 Нажмите «Добавить», выберите свой канал и подтвердите права.",
        reply_markup=keyboard
    )

@dp.message(F.text == "🗑 Удалить мой канал")
async def remove_channel_handler(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or not user[2]:
        await message.answer("❌ У тебя нет добавленного канала.")
        return
    db.remove_channel(message.from_user.id)
    await message.answer("✅ Канал удален.", reply_markup=get_main_menu(message.from_user.id))

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
        f"🎯 <b>Новое задание!</b>\n\nПодпишись на этот канал: {channel_link}\n\nПосле подписки нажми кнопку ниже.",
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
    user_id = message.from_user.id
    bot_username = (await bot.me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    count = db.get_referral_count(user_id)
    
    share_text = "Присоединяйся к системе взаимного пиара! Бонус за вход."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}&text={share_text}")]
    ])
    
    await message.answer(
        f"👥 <b>Приглашай друзей и зарабатывай баллы!</b>\n\n"
        f"За каждого друга, который зайдет по твоей ссылке и запустит бота, ты получишь <b>+50 баллов</b>.\n"
        f"А твой друг получит <b>+10 баллов</b> в подарок! 🎁\n\n"
        f"👇 Нажми на кнопку ниже, чтобы отправить приглашение:",
        reply_markup=keyboard
    )
    
    await message.answer(
        f"<i>Или скопируй ссылку вручную, нажав на неё:</i>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 Ты уже пригласил: <b>{count}</b> чел.",
        disable_web_page_preview=True
    )

@dp.message(F.text == "🏆 Мой профиль")
async def show_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if user:
        points, channel, views = user[4], user[2] or "Нет", user[7] if len(user) > 7 else 0
        is_active = "✅" if user[5] == 1 else "❌"
        await message.answer(
            f"🏆 <b>Профиль:</b>\n\n📢 {channel} {is_active}\n💰 Баллы: <b>{points}</b>\n👁 Показов: {views}"
        )
    else:
        await message.answer("Напиши /start")

async def main():
    db.init_db()
    try:
        await bot.set_my_default_administrator_rights(
            rights=ChatAdministratorRights(
                can_post_messages=True,
                can_edit_messages=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_restrict_members=True,
                can_promote_members=False,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True,
            ),
            for_channels=True
        )
        logging.info("Права по умолчанию для каналов установлены.")
    except Exception as e:
        logging.error(f"Ошибка при установке прав по умолчанию: {e}")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.wait_for(dp.start_polling(bot), timeout=5.83 * 3600)
    except asyncio.TimeoutError:
        logging.info("Завершение по таймауту...")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
