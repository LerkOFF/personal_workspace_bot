from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot.keyboards.tasks_menu import tasks_menu_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.task_states import NewTaskStates
from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.task import Task, TaskStatus
from app.core.models.project import Project

tasks_router = Router()


# ====== CallbackData для действий над задачами ======
class TaskActionCb(CallbackData, prefix="task"):
    action: str  # "cycle", "delete"
    task_id: int


# ====== CallbackData для выбора проекта при создании задачи ======
class TaskProjectCb(CallbackData, prefix="tproj"):
    project_id: int  # 0 - без проекта


# ====== Вспомогательные функции ======
def format_task_text(task: Task) -> str:
    status_emoji = {
        TaskStatus.TODO: "🟡",
        TaskStatus.IN_PROGRESS: "🟠",
        TaskStatus.DONE: "🟢",
    }[task.status]

    line = f"{status_emoji} <b>{task.title}</b>"

    if task.description:
        line += f"\n    <i>{task.description}</i>"

    if task.project:
        line += f"\n    📁 Проект: <b>{task.project.name}</b>"

    if task.due_at:
        formatted = task.due_at.strftime("%d.%m.%Y")
        line += f"\n    ⏰ до <b>{formatted}</b>"

    return line


def task_inline_kb(task: Task):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🔁 Статус",
        callback_data=TaskActionCb(
            action="cycle",
            task_id=task.id,
        ).pack(),
    )

    builder.button(
        text="🗑 Удалить",
        callback_data=TaskActionCb(
            action="delete",
            task_id=task.id,
        ).pack(),
    )

    builder.adjust(2)
    return builder.as_markup()


# ====== Кнопка "📋 Задачи" из главного меню ======
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
            .options(selectinload(Task.project))
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
        await message.answer(
            text,
            reply_markup=tasks_menu_kb(),
        )
        return

    await message.answer("Твои последние задачи:")

    for task in tasks:
        await message.answer(
            format_task_text(task),
            reply_markup=task_inline_kb(task),
        )

    await message.answer(
        "Меню задач:",
        reply_markup=tasks_menu_kb(),
    )


# ====== Создание задачи ======
@tasks_router.callback_query(F.data == "tasks:add")
async def cb_add_task(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(NewTaskStates.waiting_for_title)
    await callback.message.answer(
        "Введи <b>название задачи</b>:",
        reply_markup=main_menu_kb(),
    )


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


@tasks_router.message(NewTaskStates.waiting_for_description)
async def new_task_description(message: types.Message, state: FSMContext):
    desc_raw = message.text.strip()
    description: Optional[str] = None if desc_raw == "-" else desc_raw

    await state.update_data(description=description)

    tg_user = message.from_user

    # Проверяем, есть ли у пользователя проекты
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

    # Если проектов нет — пропускаем шаг выбора и сразу спрашиваем дедлайн
    if not projects:
        await state.set_state(NewTaskStates.waiting_for_due_date)
        await message.answer(
            "Укажи <b>дедлайн</b> в формате <code>ДД.ММ.ГГГГ</code>\n"
            "или напиши <code>-</code>, если дедлайна нет.",
        )
        return

    # Есть проекты — даём выбрать
    builder = InlineKeyboardBuilder()

    for project in projects:
        builder.button(
            text=f"📁 {project.name}",
            callback_data=TaskProjectCb(project_id=project.id).pack(),
        )

    # опция "Без проекта"
    builder.button(
        text="Без проекта",
        callback_data=TaskProjectCb(project_id=0).pack(),
    )

    builder.adjust(1)

    await state.set_state(NewTaskStates.waiting_for_project)
    await message.answer(
        "Выбери <b>проект</b> для задачи или нажми <b>«Без проекта»</b>:",
        reply_markup=builder.as_markup(),
    )


# ====== Выбор проекта (callback) ======
@tasks_router.callback_query(TaskProjectCb.filter(), NewTaskStates.waiting_for_project)
async def choose_task_project(
    callback: types.CallbackQuery,
    callback_data: TaskProjectCb,
    state: FSMContext,
):
    await callback.answer()

    project_id = callback_data.project_id if callback_data.project_id != 0 else None
    await state.update_data(project_id=project_id)

    await state.set_state(NewTaskStates.waiting_for_due_date)
    await callback.message.answer(
        "Укажи <b>дедлайн</b> в формате <code>ДД.ММ.ГГГГ</code>\n"
        "или напиши <code>-</code>, если дедлайна нет.",
    )


# ====== Дедлайн ======
@tasks_router.message(NewTaskStates.waiting_for_due_date)
async def new_task_due_date(message: types.Message, state: FSMContext):
    due_raw = message.text.strip()

    due_at: Optional[datetime] = None
    if due_raw != "-":
        try:
            parsed_date = datetime.strptime(due_raw, "%d.%m.%Y").date()
            today = date.today()
            if parsed_date < today:
                await message.answer(
                    "Дата не может быть в прошлом.\n"
                    "Укажи дату в формате <code>ДД.ММ.ГГГГ</code> "
                    "или напиши <code>-</code>.",
                )
                return

            due_at = datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                23,
                59,
            )
        except ValueError:
            await message.answer(
                "Некорректный формат даты.\n"
                "Используй формат <code>ДД.ММ.ГГГГ</code> или напиши <code>-</code>.",
            )
            return

    data = await state.get_data()
    title = data["title"]
    description = data["description"]
    project_id: Optional[int] = data.get("project_id")

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
            project_id=project_id,
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


# ====== Обработка инлайн-кнопок "🔁 Статус" и "🗑 Удалить" ======
@tasks_router.callback_query(TaskActionCb.filter())
async def task_action_handler(
    callback: types.CallbackQuery,
    callback_data: TaskActionCb,
):
    tg_user = callback.from_user

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("Пользователь не найден в системе.", show_alert=True)
            return

        result = await session.execute(
            select(Task)
            .options(selectinload(Task.project))
            .where(Task.id == callback_data.task_id)
        )
        task = result.scalar_one_or_none()

        if task is None or task.user_id != user.id:
            await callback.answer("Эта задача больше не существует.", show_alert=True)
            await callback.message.edit_text("❌ Задача недоступна.")
            return

        if callback_data.action == "cycle":
            if task.status == TaskStatus.TODO:
                task.status = TaskStatus.IN_PROGRESS
            elif task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.DONE
            else:
                task.status = TaskStatus.TODO

            await session.commit()
            await session.refresh(task)

            await callback.message.edit_text(
                format_task_text(task),
                reply_markup=task_inline_kb(task),
            )
            await callback.answer("Статус обновлён ✅")

        elif callback_data.action == "delete":
            await session.delete(task)
            await session.commit()

            await callback.message.edit_text("🗑 Задача удалена.")
            await callback.answer("Задача удалена ✅")
