from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def tasks_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text="➕ Добавить задачу",
        callback_data="tasks:add",
    )

    # нужно будет добавить ещё кнопок позже (фильтры, статусы и т.д.)

    builder.adjust(1)
    return builder.as_markup()
