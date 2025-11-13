from __future__ import annotations

from datetime import datetime
from typing import Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select

from app.bot.keyboards.projects_menu import projects_menu_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.project_states import NewProjectStates
from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.project import Project

projects_router = Router()


# ====== CallbackData для проектов ======
class ProjectActionCb(CallbackData, prefix="proj"):
    action: str   # "view", "close", "delete"
    project_id: int


# ====== Форматирование текста ======
def format_project_collapsed(project: Project) -> str:
    """
    Краткий вид проекта для списка:
    только название + дата создания.
    Описание показываем ТОЛЬКО в раскрытом виде.
    """
    text = f"📁 <b>{project.name}</b>"
    text += f"\n📅 Создан: <code>{project.created_at.strftime('%d.%m.%Y %H:%M')}</code>"
    return text


def format_project_expanded(project: Project) -> str:
    """
    Развёрнутый вид проекта: полное описание + дата.
    """
    text = f"📁 <b>{project.name}</b>\n\n"

    if project.description:
        text += f"{project.description}\n\n"
    else:
        text += "<i>Описание не указано.</i>\n\n"

    text += f"📅 Создан: <code>{project.created_at.strftime('%d.%m.%Y %H:%M')}</code>"
    return text


# ====== Клавиатуры ======
def project_inline_kb_collapsed(project: Project):
    """Клавиатура для свернутого проекта: Открыть + Удалить."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="ℹ Открыть",
        callback_data=ProjectActionCb(action="view", project_id=project.id).pack(),
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=ProjectActionCb(action="delete", project_id=project.id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


def project_inline_kb_expanded(project: Project):
    """Клавиатура для раскрытого проекта: Закрыть + Удалить."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔼 Закрыть",
        callback_data=ProjectActionCb(action="close", project_id=project.id).pack(),
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=ProjectActionCb(action="delete", project_id=project.id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


# ====== Обработчик кнопки "📁 Проекты" из главного меню ======
@projects_router.message(F.text == "📁 Проекты")
async def handle_projects_menu(message: types.Message):
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

        result = await session.execute(
            select(Project)
            .where(Project.user_id == user.id)
            .order_by(Project.created_at.desc())
            .limit(10)
        )
        projects = result.scalars().all()

    if not projects:
        await message.answer(
            "У тебя пока нет проектов.\n\n"
            "Нажми <b>«➕ Создать проект»</b>, чтобы создать первый.",
            reply_markup=projects_menu_kb(),
        )
        return

    await message.answer("Твои последние проекты:")
    for project in projects:
        await message.answer(
            format_project_collapsed(project),
            reply_markup=project_inline_kb_collapsed(project),
        )

    await message.answer(
        "Меню проектов:",
        reply_markup=projects_menu_kb(),
    )


# ====== Создание проекта ======
@projects_router.callback_query(F.data == "projects:add")
async def cb_add_project(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(NewProjectStates.waiting_for_name)
    await callback.message.answer(
        "Введи <b>название проекта</b>:",
        reply_markup=main_menu_kb(),
    )


@projects_router.message(NewProjectStates.waiting_for_name)
async def new_project_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Название проекта не может быть пустым. Попробуй ещё раз:")
        return

    await state.update_data(name=name)
    await state.set_state(NewProjectStates.waiting_for_description)
    await message.answer(
        "Теперь отправь <b>описание проекта</b>.\n"
        "Или напиши <code>-</code>, если описание не нужно.",
    )


@projects_router.message(NewProjectStates.waiting_for_description)
async def new_project_description(message: types.Message, state: FSMContext):
    desc_raw = message.text.strip()
    description: Optional[str] = None if desc_raw == "-" else desc_raw

    data = await state.get_data()
    name = data["name"]

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

        project = Project(
            user_id=user.id,
            name=name,
            description=description,
            created_at=datetime.utcnow(),
        )
        session.add(project)
        await session.commit()

    await state.clear()

    await message.answer(
        "✅ Проект создан!\n"
        "Посмотреть список можно через кнопку <b>«📁 Проекты»</b>.",
        reply_markup=main_menu_kb(),
    )


# ====== Просмотр / закрытие / удаление проекта ======
@projects_router.callback_query(ProjectActionCb.filter())
async def project_action_handler(
    callback: types.CallbackQuery,
    callback_data: ProjectActionCb,
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

        result = await session.execute(
            select(Project).where(Project.id == callback_data.project_id)
        )
        project = result.scalar_one_or_none()

        if project is None or project.user_id != user.id:
            await callback.answer("Этот проект больше не доступен.", show_alert=True)
            await callback.message.edit_text("❌ Проект недоступен.")
            return

        # Развернуть
        if callback_data.action == "view":
            await callback.message.edit_text(
                format_project_expanded(project),
                reply_markup=project_inline_kb_expanded(project),
            )
            await callback.answer()

        # Свернуть
        elif callback_data.action == "close":
            await callback.message.edit_text(
                format_project_collapsed(project),
                reply_markup=project_inline_kb_collapsed(project),
            )
            await callback.answer()

        # Удалить
        elif callback_data.action == "delete":
            await session.delete(project)
            await session.commit()
            await callback.message.edit_text("🗑 Проект удалён.")
            await callback.answer("Проект удалён ✅")
