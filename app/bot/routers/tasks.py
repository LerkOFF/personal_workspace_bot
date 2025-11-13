from __future__ import annotations

from datetime import datetime
from typing import Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.bot.keyboards.tasks_menu import tasks_menu_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.task_states import NewTaskStates
from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.task import Task, TaskStatus

tasks_router = Router()


# 📋 Кнопка "Задачи" из главного меню
@tasks_router.message(F.text == "📋 Задачи")
async def handle_tasks_menu(message: types.Message):
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
            select(Task)
            .where(Task.user_id == user.id)
            .order_by(Task.created_at.desc())
            .limit(10)
        )
        tasks = result.scalars().all()

    if not tasks:
        text = (
            "У тебя пока нет задач.\n\n"
            "Нажми <b>«➕ Добавить задачу»</b>, чтобы создать первую."
        )
    else:
        lines = ["Твои последние задачи:"]
        for task in tasks:
            status_emoji = {
                TaskStatus.TODO: "🟡",
                TaskStatus.IN_PROGRESS: "🟠",
                TaskStatus.DONE: "🟢",
            }[task.status]

            line = f"{status_emoji} <b>{task.title}</b>"
            if task.description:
                line += f"\n    <i>{task.description}</i>"
            lines.append(line)

        text = "\n\n".join(lines)

    await message.answer(
        text,
        reply_markup=tasks_menu_kb(),
    )


# ➕ Добавить задачу
@tasks_router.callback_query(F.data == "tasks:add")
async def cb_add_task(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(NewTaskStates.waiting_for_title)
    await callback.message.answer(
        "Введи <b>название задачи</b>:",
        reply_markup=main_menu_kb(),
    )


# Название задачи
@tasks_router.message(NewTaskStates.waiting_for_title)
async def new_task_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуй ещё раз:")
        return

    await state.update_data(title=title)
    await state.set_state(NewTaskStates.waiting_for_description)
    await message.answer(
        "Теперь отправь <b>описание задачи</b>.\n"
        "Если не хочешь добавлять описание — напиши <code>-</code>.",
    )


# Описание задачи
@tasks_router.message(NewTaskStates.waiting_for_description)
async def new_task_description(message: types.Message, state: FSMContext):
    desc_raw = message.text.strip()
    description: Optional[str] = None if desc_raw == "-" else desc_raw

    await state.update_data(description=description)
    await state.set_state(NewTaskStates.waiting_for_due_date)
    await message.answer(
        "Укажи <b>дедлайн</b> в формате <code>ГГГГ-ММ-ДД</code>\n"
        "или напиши <code>-</code>, если дедлайна нет.",
    )


# Дедлайн
@tasks_router.message(NewTaskStates.waiting_for_due_date)
async def new_task_due_date(message: types.Message, state: FSMContext):
    due_raw = message.text.strip()

    due_at: Optional[datetime] = None
    if due_raw != "-":
        try:
            date_obj = datetime.strptime(due_raw, "%Y-%m-%d").date()
            due_at = datetime(
                year=date_obj.year,
                month=date_obj.month,
                day=date_obj.day,
                hour=23,
                minute=59,
            )
        except ValueError:
            await message.answer(
                "Некорректный формат даты. Используй <code>ГГГГ-ММ-ДД</code> или <code>-</code>."
            )
            return

    data = await state.get_data()
    title = data["title"]
    description = data["description"]

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

        task = Task(
            user_id=user.id,
            title=title,
            description=description,
            status=TaskStatus.TODO,
            due_at=due_at,
        )
        session.add(task)
        await session.commit()

    await state.clear()

    await message.answer(
        "✅ Задача создана!\n"
        "Чтобы посмотреть список задач, нажми <b>«📋 Задачи»</b>.",
        reply_markup=main_menu_kb(),
    )
