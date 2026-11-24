import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, CHANNEL_ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def is_subscribed(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.
    Бот должен быть администратором в канале.
    """
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Явно проверяем статусы, означающие подписку
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Ошибка при проверке подписки: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    subscribed = await is_subscribed(user_id)

    if subscribed:
        await message.answer(
            f"Привет, {message.from_user.full_name}! 👋\n\n"
            "Ты уже подписан на наш канал. Добро пожаловать в систему взаимного пиара!"
        )
    else:
        # Создаем кнопку со ссылкой на канал (убираем @ из юзернейма для URL)
        channel_url = f"https://t.me/{CHANNEL_ID.replace('@', '')}"
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_url)],
                [types.InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
            ]
        )
        await message.answer(
            "Для участия в системе необходимо подписаться на наш канал.",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback_query: types.CallbackQuery):
    subscribed = await is_subscribed(callback_query.from_user.id)
    if subscribed:
        await callback_query.message.edit_text("Отлично! Ты подписан. Теперь ты можешь участвовать в взаимном пиаре.")
    else:
        await callback_query.answer("Ты еще не подписался на канал. Пожалуйста, подпишись и попробуй снова.", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
