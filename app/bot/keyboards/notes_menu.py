from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def notes_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text="➕ Добавить заметку",
        callback_data="notes:add",
    )

    builder.adjust(1)
    return builder.as_markup()
