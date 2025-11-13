from aiogram import Router, types
from aiogram.filters import CommandStart

from app.bot.keyboards.main_menu import main_menu_kb

common_router = Router()


@common_router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я твой цифровой рабочий стол в Telegram.\n"
        "Пока у меня только скелет интерфейса, но скоро тут будут задачи, заметки и проекты.",
        reply_markup=main_menu_kb(),
    )
