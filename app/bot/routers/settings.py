from __future__ import annotations

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select

from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.settings_states import SettingsStates
from app.core.db import async_session_maker
from app.core.models.user import User


settings_router = Router()


class SettingsCb(CallbackData, prefix="settings"):
    # Возможные значения:
    #  - "toggle_digest"      — включить/выключить ежедневный дайджест
    #  - "toggle_deadlines"   — включить/выключить напоминания по дедлайнам
    #  - "change_time"        — изменить время дайджеста
    action: str


def _build_settings_text(user: User) -> str:
    digest_status = "включён ✅" if user.reminders_enabled else "выключен ❌"
    deadline_enabled = getattr(user, "deadline_reminders_enabled", True)
    deadlines_status = "включены ✅" if deadline_enabled else "выключены ❌"

    time_str = f"{user.reminder_hour:02d}:{user.reminder_minute:02d}"

    return (
        "⚙️ <b>Настройки напоминаний</b>\n\n"
        f"📨 Ежедневный дайджест: <b>{digest_status}</b>\n"
        f"⏰ Время дайджеста: <code>{time_str}</code>\n\n"
        f"📅 Напоминания о дедлайнах задач: <b>{deadlines_status}</b>\n\n"
        "Ты можешь отдельно управлять утренним дайджестом и напоминаниями "
        "о приближении дедлайна задач."
    )


def _build_settings_kb(user: User):
    builder = InlineKeyboardBuilder()

    # Переключатель ежедневного дайджеста
    if user.reminders_enabled:
        builder.button(
            text="🔕 Выключить дайджест",
            callback_data=SettingsCb(action="toggle_digest").pack(),
        )
    else:
        builder.button(
            text="🔔 Включить дайджест",
            callback_data=SettingsCb(action="toggle_digest").pack(),
        )

    # Переключатель напоминаний по дедлайнам
    deadline_enabled = getattr(user, "deadline_reminders_enabled", True)
    if deadline_enabled:
        builder.button(
            text="📅 Выключить напоминания по дедлайнам",
            callback_data=SettingsCb(action="toggle_deadlines").pack(),
        )
    else:
        builder.button(
            text="📅 Включить напоминания по дедлайнам",
            callback_data=SettingsCb(action="toggle_deadlines").pack(),
        )

    # Изменение времени дайджеста
    builder.button(
        text="⏰ Изменить время дайджеста",
        callback_data=SettingsCb(action="change_time").pack(),
    )

    builder.adjust(1)
    return builder.as_markup()


# ====== Обработчик кнопки "⚙️ Настройки" из главного меню ======
@settings_router.message(F.text == "⚙️ Настройки")
async def handle_settings_menu(message: types.Message):
    tg_user = message.from_user

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
            await session.refresh(user)

        text = _build_settings_text(user)
        kb = _build_settings_kb(user)

    await message.answer(text, reply_markup=kb)


# ====== Обработка нажатий на инлайн-кнопки настроек ======
@settings_router.callback_query(SettingsCb.filter())
async def settings_action_handler(
    callback: types.CallbackQuery,
    callback_data: SettingsCb,
    state: FSMContext,
):
    tg_user = callback.from_user

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        # Переключить ежедневный дайджест
        if callback_data.action == "toggle_digest":
            user.reminders_enabled = not user.reminders_enabled
            await session.commit()
            await session.refresh(user)

            text = _build_settings_text(user)
            kb = _build_settings_kb(user)

            await callback.message.edit_text(text, reply_markup=kb)
            await callback.answer("Настройки дайджеста обновлены ✅")

        # Переключить напоминания по дедлайнам
        elif callback_data.action == "toggle_deadlines":
            current = getattr(user, "deadline_reminders_enabled", True)
            user.deadline_reminders_enabled = not current
            await session.commit()
            await session.refresh(user)

            text = _build_settings_text(user)
            kb = _build_settings_kb(user)

            await callback.message.edit_text(text, reply_markup=kb)
            await callback.answer("Настройки напоминаний о дедлайнах обновлены ✅")

        # Изменить время дайджеста
        elif callback_data.action == "change_time":
            await state.set_state(SettingsStates.waiting_for_reminder_time)
            await callback.message.answer(
                "Введи время напоминания в формате <code>ЧЧ:ММ</code>\n"
                "Например: <b>09:00</b> или <b>18:30</b>.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()


# ====== Ввод времени напоминаний ======
@settings_router.message(SettingsStates.waiting_for_reminder_time)
async def set_reminder_time(message: types.Message, state: FSMContext):
    tg_user = message.from_user
    raw = message.text.strip()

    # Парсим ЧЧ:ММ
    try:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError

        hour = int(parts[0])
        minute = int(parts[1])

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError

    except ValueError:
        await message.answer(
            "Некорректный формат времени.\n"
            "Используй формат <code>ЧЧ:ММ</code>, например: <b>09:00</b> или <b>18:30</b>."
        )
        return

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
            await session.refresh(user)

        user.reminder_hour = hour
        user.reminder_minute = minute
        user.reminders_enabled = True
        user.last_digest_date = None

        await session.commit()
        await session.refresh(user)

        text = _build_settings_text(user)
        kb = _build_settings_kb(user)

    await state.clear()
    await message.answer(
        f"✅ Время дайджеста обновлено: <b>{hour:02d}:{minute:02d}</b>",
        reply_markup=main_menu_kb(),
    )
    # Дополнительно ещё раз показать карточку настроек
    await message.answer(text, reply_markup=kb)
