from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from html import escape

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot.keyboards.tasks_menu import tasks_menu_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.task_states import NewTaskStates, TaskFileStates, SubTaskStates
from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.task import Task, TaskStatus
from app.core.models.project import Project
from app.core.models.task_file import TaskFile
from app.core.models.subtask import SubTask

tasks_router = Router()


# ====== CallbackData для действий над задачами ======
class TaskActionCb(CallbackData, prefix="task"):
    # Возможные значения:
    #  - "cycle"        — сменить статус
    #  - "delete"       — удалить задачу
    #  - "files"        — открыть список файлов
    #  - "attach"       — прикрепить файл
    #  - "subtasks"     — открыть список подзадач
    #  - "add_subtask"  — добавить новую подзадачу
    action: str
    task_id: int


class TaskFileCb(CallbackData, prefix="tfile"):
    action: str   # "download" | "delete"
    file_id: int


class SubTaskCb(CallbackData, prefix="subt"):
    # "toggle" — переключить выполнено/невыполнено
    # "delete" — удалить подзадачу
    action: str
    subtask_id: int


# ====== CallbackData для выбора проекта при создании задачи ======
class TaskProjectCb(CallbackData, prefix="tproj"):
    project_id: int  # 0 - без проекта


# ====== Вспомогательные функции ======
def format_task_text(task: Task) -> str:
    status_map = {
        TaskStatus.TODO: "📝 To Do",
        TaskStatus.IN_PROGRESS: "⏳ In Progress",
        TaskStatus.DONE: "✅ Done",
    }

    lines: list[str] = [
        f"📌 <b>{escape(task.title)}</b>",
        "",
        f"Статус: <b>{status_map.get(task.status, str(task.status))}</b>",
    ]

    # Проект
    if getattr(task, "project", None):
        # в твоём проекте поле у проекта называется title или name — подгони при необходимости
        project_title = getattr(task.project, "title", None) or getattr(
            task.project, "name", ""
        )
        if project_title:
            lines.append(f"Проект: <b>{escape(project_title)}</b>")

    # Дедлайн (ИСПОЛЬЗУЕМ due_at, а не due_date)
    if getattr(task, "due_at", None):
        lines.append(f"Дедлайн: <code>{task.due_at.strftime('%d.%m.%Y')}</code>")

    # Прогресс по подзадачам
    if hasattr(task, "subtasks"):
        subs = task.subtasks or []
        if subs:
            done = sum(1 for s in subs if s.is_done)
            total = len(subs)
            lines.append(f"Подзадачи: <b>{done}/{total}</b> выполнено")

    # Описание
    if getattr(task, "description", None):
        lines.append("")
        lines.append(escape(task.description))

    return "\n".join(lines)


def task_inline_kb(task: Task):
    builder = InlineKeyboardBuilder()

    # Кнопка смены статуса
    builder.button(
        text="🔄 Статус",
        callback_data=TaskActionCb(
            action="cycle",
            task_id=task.id,
        ).pack(),
    )

    # Кнопка удаления
    builder.button(
        text="🗑 Удалить",
        callback_data=TaskActionCb(
            action="delete",
            task_id=task.id,
        ).pack(),
    )

    # Кнопка файлов
    builder.button(
        text="📎 Файлы",
        callback_data=TaskActionCb(
            action="files",
            task_id=task.id,
        ).pack(),
    )

    # кнопка подзадач
    builder.button(
        text="☑️ Подзадачи",
        callback_data=TaskActionCb(
            action="subtasks",
            task_id=task.id,
        ).pack(),
    )

    # две кнопки в первой строке, две во второй
    builder.adjust(2, 2)
    return builder.as_markup()

async def build_subtasks_view(session, task: Task):
    result = await session.execute(
        select(SubTask)
        .where(SubTask.task_id == task.id)
        .order_by(SubTask.created_at)
    )
    subtasks = result.scalars().all()

    lines = [
        f"☑️ <b>Подзадачи для задачи:</b>\n<b>{escape(task.title)}</b>",
        "",
    ]

    if not subtasks:
        lines.append("Пока нет подзадач.\n")
        lines.append("Нажми «➕ Добавить подзадачу» или отправь текст новой подзадачи.")
    else:
        for idx, s in enumerate(subtasks, start=1):
            status = "✅" if s.is_done else "⬜️"
            lines.append(f"{idx}. {status} {escape(s.title)}")

    text = "\n".join(lines)

    builder = InlineKeyboardBuilder()

    # Кнопки для существующих подзадач
    for s in subtasks:
        status = "✅" if s.is_done else "⬜️"
        short = s.title
        if len(short) > 20:
            short = short[:17] + "..."

        builder.button(
            text=f"{status} {short}",
            callback_data=SubTaskCb(
                action="toggle",
                subtask_id=s.id,
            ).pack(),
        )
        builder.button(
            text="🗑",
            callback_data=SubTaskCb(
                action="delete",
                subtask_id=s.id,
            ).pack(),
        )

    # Кнопка добавления новой подзадачи
    builder.button(
        text="➕ Добавить подзадачу",
        callback_data=TaskActionCb(
            action="add_subtask",
            task_id=task.id,
        ).pack(),
    )

    if subtasks:
        builder.adjust(2, 1)
    else:
        builder.adjust(1)

    return text, builder.as_markup()

async def build_task_files_view(session, task_id: int):
    result = await session.execute(
        select(TaskFile)
        .where(TaskFile.task_id == task_id)
        .order_by(TaskFile.created_at)
    )
    files = result.scalars().all()

    if not files:
        text = (
            "📎 <b>Файлы задачи</b>\n\n"
            "У этой задачи пока нет прикреплённых файлов.\n\n"
            "Отправь документ или фото <b>в ответ</b> на это сообщение, "
            "чтобы прикрепить его к задаче."
        )
        builder = InlineKeyboardBuilder()
        builder.button(
            text="📎 Прикрепить файл",
            callback_data=TaskActionCb(
                action="attach",
                task_id=task_id,
            ).pack(),
        )
        builder.adjust(1)
        return text, builder.as_markup()

    lines = ["📎 <b>Файлы задачи</b>\n"]
    for idx, f in enumerate(files, start=1):
        lines.append(f"{idx}. {f.file_name}")
    text = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    for f in files:
        short = f.file_name
        if len(short) > 20:
            short = short[:17] + "..."
        builder.button(
            text=f"📥 {short}",
            callback_data=TaskFileCb(
                action="download",
                file_id=f.id,
            ).pack(),
        )
        builder.button(
            text=f"🗑 {short}",
            callback_data=TaskFileCb(
                action="delete",
                file_id=f.id,
            ).pack(),
        )

    builder.button(
        text="📎 Прикрепить файл",
        callback_data=TaskActionCb(
            action="attach",
            task_id=task_id,
        ).pack(),
    )

    builder.adjust(2, 1)
    return text, builder.as_markup()

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
            .options(
                selectinload(Task.project),
                selectinload(Task.subtasks),
            )
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
    state: FSMContext,
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
            .options(
                selectinload(Task.project),
                selectinload(Task.subtasks),
            )
            .where(Task.id == callback_data.task_id)
        )
        task = result.scalar_one_or_none()

        if task is None or task.user_id != user.id:
            await callback.answer("Эта задача больше не существует.", show_alert=True)
            try:
                await callback.message.edit_text("❌ Задача недоступна.")
            except Exception:
                pass
            return

        # Смена статуса
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

        # Удаление задачи
        elif callback_data.action == "delete":
            await session.delete(task)
            await session.commit()
            try:
                await callback.message.edit_text(" Задача удалена.")
            except Exception:
                pass
            await callback.answer("Задача удалена ✅")

        # Показать список файлов
        elif callback_data.action == "files":
            text, kb = await build_task_files_view(session, task.id)
            await callback.message.answer(text, reply_markup=kb)
            await callback.answer()

        # Начать прикрепление файла
        elif callback_data.action == "attach":
            await state.set_state(TaskFileStates.waiting_for_file)
            await state.update_data(task_id=task.id)
            await callback.message.answer(
                "Отправь файл (документ или фото) <b>одним сообщением</b>, "
                "чтобы прикрепить его к этой задаче.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()

        # Показать подзадачи
        elif callback_data.action == "subtasks":
            text, kb = await build_subtasks_view(session, task)
            await callback.message.answer(text, reply_markup=kb)
            await callback.answer()

        # Начать добавление новой подзадачи
        elif callback_data.action == "add_subtask":
            await state.set_state(SubTaskStates.waiting_for_title)
            await state.update_data(task_id=task.id)

            await callback.message.answer(
                "Введи текст новой подзадачи для этой задачи.\n\n"
                "Например: <b>Сделать черновик отчёта</b>",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()

@tasks_router.message(SubTaskStates.waiting_for_title)
async def handle_new_subtask(message: types.Message, state: FSMContext):
    tg_user = message.from_user
    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "Текст подзадачи не может быть пустым.\n"
            "Введи, пожалуйста, нормальное описание."
        )
        return

    data = await state.get_data()
    task_id = data.get("task_id")

    if task_id is None:
        await state.clear()
        await message.answer(
            "Не удалось определить, к какой задаче добавить подзадачу.\n"
            "Попробуй ещё раз через кнопку «☑️ Подзадачи» у нужной задачи."
        )
        return

    async with async_session_maker() as session:
        # находим пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return

        # находим задачу
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task is None or task.user_id != user.id:
            await message.answer(
                "Эта задача больше не существует или тебе недоступна."
            )
            await state.clear()
            return

        subtask = SubTask(
            task_id=task.id,
            user_id=user.id,
            title=title,
            is_done=False,
        )
        session.add(subtask)
        await session.commit()

        # Обновляем задачу с подзадачами
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.id == task.id)
        )
        task = result.scalar_one()

        text, kb = await build_subtasks_view(session, task)

    await state.clear()
    await message.answer("✅ Подзадача добавлена.")
    await message.answer(text, reply_markup=kb)

@tasks_router.message(SubTaskStates.waiting_for_title)
async def handle_new_subtask(message: types.Message, state: FSMContext):
    tg_user = message.from_user
    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "Текст подзадачи не может быть пустым.\n"
            "Введи, пожалуйста, нормальное описание."
        )
        return

    data = await state.get_data()
    task_id = data.get("task_id")

    if task_id is None:
        await state.clear()
        await message.answer(
            "Не удалось определить, к какой задаче добавить подзадачу.\n"
            "Попробуй ещё раз через кнопку «☑️ Подзадачи» у нужной задачи."
        )
        return

    async with async_session_maker() as session:
        # находим пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return

        # находим задачу
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task is None or task.user_id != user.id:
            await message.answer(
                "Эта задача больше не существует или тебе недоступна."
            )
            await state.clear()
            return

        subtask = SubTask(
            task_id=task.id,
            user_id=user.id,
            title=title,
            is_done=False,
        )
        session.add(subtask)
        await session.commit()

        # Обновляем задачу с подзадачами
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.id == task.id)
        )
        task = result.scalar_one()

        text, kb = await build_subtasks_view(session, task)

    await state.clear()
    await message.answer("✅ Подзадача добавлена.")
    await message.answer(text, reply_markup=kb)

@tasks_router.callback_query(SubTaskCb.filter())
async def subtask_action_handler(
    callback: types.CallbackQuery,
    callback_data: SubTaskCb,
):
    tg_user = callback.from_user

    async with async_session_maker() as session:
        # пользователь
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        # подзадача
        result = await session.execute(
            select(SubTask).where(SubTask.id == callback_data.subtask_id)
        )
        subtask = result.scalar_one_or_none()
        if subtask is None or subtask.user_id != user.id:
            await callback.answer(
                "Эта подзадача больше не существует или тебе недоступна.",
                show_alert=True,
            )
            return

        task_id = subtask.task_id

        # переключение статуса
        if callback_data.action == "toggle":
            subtask.is_done = not subtask.is_done
            await session.commit()

        # удаление
        elif callback_data.action == "delete":
            await session.delete(subtask)
            await session.commit()

        # после изменения подзадачи — обновляем список
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task is None:
            try:
                await callback.message.edit_text(
                    "☑️ Подзадачи недоступны (задача была удалена)."
                )
            except Exception:
                pass
            await callback.answer("Подзадача обновлена.")
            return

        text, kb = await build_subtasks_view(session, task)
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            # если Telegram скажет "message is not modified" — просто игнорируем
            pass

        await callback.answer("Подзадача обновлена ✅")

@tasks_router.message(TaskFileStates.waiting_for_file)
async def handle_task_file_upload(message: types.Message, state: FSMContext):
    tg_user = message.from_user

    doc = message.document
    photo = message.photo[-1] if message.photo else None

    if not doc and not photo:
        await message.answer(
            "Это не похоже на файл.\n"
            "Отправь, пожалуйста, <b>документ</b> или <b>фото</b>, "
            "чтобы прикрепить его к задаче."
        )
        return

    if doc:
        file_id = doc.file_id
        unique_id = doc.file_unique_id
        file_name = doc.file_name or f"document_{unique_id}"
        mime_type = doc.mime_type
        size = doc.file_size
        file_kind = "document"
    else:
        file_id = photo.file_id
        unique_id = photo.file_unique_id
        file_name = f"photo_{unique_id}.jpg"
        mime_type = "image/jpeg"
        size = photo.file_size
        file_kind = "photo"

    data = await state.get_data()
    task_id = data.get("task_id")

    if task_id is None:
        await state.clear()
        await message.answer(
            "Не удалось определить задачу для файла.\n"
            "Попробуй ещё раз через кнопку «Файлы» у нужной задачи."
        )
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Пользователь не найден в системе.")
            await state.clear()
            return

        result = await session.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None or task.user_id != user.id:
            await message.answer(
                "Эта задача больше не существует или тебе недоступна."
            )
            await state.clear()
            return

        task_file = TaskFile(
            task_id=task.id,
            user_id=user.id,
            telegram_file_id=file_id,
            telegram_unique_id=unique_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=size,
            file_kind=file_kind,
        )
        session.add(task_file)
        await session.commit()

        text, kb = await build_task_files_view(session, task.id)

    await state.clear()
    await message.answer("✅ Файл прикреплён к задаче.")
    await message.answer(text, reply_markup=kb)

@tasks_router.callback_query(TaskFileCb.filter())
async def task_file_action_handler(
    callback: types.CallbackQuery,
    callback_data: TaskFileCb,
):
    tg_user = callback.from_user

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Пользователь не найден в системе.",
                show_alert=True,
            )
            return

        result = await session.execute(
            select(TaskFile).where(TaskFile.id == callback_data.file_id)
        )
        file = result.scalar_one_or_none()
        if file is None or file.user_id != user.id:
            await callback.answer(
                "Файл больше не существует или тебе недоступен.",
                show_alert=True,
            )
            return

        # Скачать файл
        if callback_data.action == "download":
            await callback.answer()
            if file.file_kind == "photo":
                await callback.message.answer_photo(
                    file.telegram_file_id,
                    caption=f"📎 {file.file_name}",
                )
            else:
                await callback.message.answer_document(
                    file.telegram_file_id,
                    caption=f"📎 {file.file_name}",
                )

        # Удалить файл
        elif callback_data.action == "delete":
            task_id = file.task_id
            await session.delete(file)
            await session.commit()

            # Пытаемся обновить список файлов
            result_task = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result_task.scalar_one_or_none()

            if task is None:
                try:
                    await callback.message.edit_text(
                        "📎 Файлы задачи недоступны (задача удалена)."
                    )
                except Exception:
                    pass
                await callback.answer("Файл удалён ✅")
                return

            text, kb = await build_task_files_view(session, task.id)
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:
                # если текст/клавиатура не изменились — игнорируем
                pass

            await callback.answer("Файл удалён ✅")
