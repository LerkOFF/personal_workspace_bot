from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton(text="📋 Задачи"),
            KeyboardButton(text="📝 Заметки"),
        ],
        [
            KeyboardButton(text="📁 Проекты"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )
