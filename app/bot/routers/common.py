from aiogram import Router, types
from aiogram.filters import CommandStart
from sqlalchemy import select

from app.bot.keyboards.main_menu import main_menu_kb
from app.core.db import async_session_maker
from app.core.models.user import User

common_router = Router()


@common_router.message(CommandStart())
async def cmd_start(message: types.Message):
    tg_user = message.from_user

    # Сохраняем/находим пользователя в БД
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=tg_user.id,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                username=tg_user.username,
            )
            session.add(user)
            await session.commit()

    await message.answer(
        "Привет! Я твой цифровой рабочий стол в Telegram.\n"
        "Ты уже зарегистрирован в системе, скоро здесь появятся задачи, заметки и проекты.",
        reply_markup=main_menu_kb(),
    )
