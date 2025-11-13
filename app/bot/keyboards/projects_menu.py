from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def projects_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text="➕ Создать проект",
        callback_data="projects:add",
    )

    builder.adjust(1)
    return builder.as_markup()
