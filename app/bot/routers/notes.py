from __future__ import annotations

from datetime import datetime
from typing import Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select

from app.bot.keyboards.notes_menu import notes_menu_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states.note_states import NewNoteStates
from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.note import Note

notes_router = Router()


# ====== CallbackData для заметок ======
class NoteActionCb(CallbackData, prefix="note"):
    action: str  # "view", "close", "delete"
    note_id: int


# ====== Вспомогательные функции ======
def format_note_short(note: Note) -> str:
    text = f"📝 <b>{note.title}</b>"
    if note.tags:
        text += f"\n    🏷 <i>{note.tags}</i>"
    return text


def format_note_full(note: Note) -> str:
    text = f"📝 <b>{note.title}</b>\n\n{note.content}"
    if note.tags:
        text += f"\n\n🏷 <i>{note.tags}</i>"
    text += f"\n\n📅 Создана: <code>{note.created_at.strftime('%d.%m.%Y %H:%M')}</code>"
    return text


def note_inline_kb_collapsed(note: Note):
    """Клавиатура для свернутой заметки: Открыть + Удалить."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📄 Открыть",
        callback_data=NoteActionCb(action="view", note_id=note.id).pack(),
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=NoteActionCb(action="delete", note_id=note.id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


def note_inline_kb_expanded(note: Note):
    """Клавиатура для развернутой заметки: Закрыть + Удалить."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔼 Закрыть",
        callback_data=NoteActionCb(action="close", note_id=note.id).pack(),
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=NoteActionCb(action="delete", note_id=note.id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


# ====== Обработчик кнопки "📝 Заметки" из главного меню ======
@notes_router.message(F.text == "📝 Заметки")
async def handle_notes_menu(message: types.Message):
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
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.created_at.desc())
            .limit(10)
        )
        notes = result.scalars().all()

    if not notes:
        await message.answer(
            "У тебя пока нет заметок.\n\n"
            "Нажми <b>«➕ Добавить заметку»</b>, чтобы создать первую.",
            reply_markup=notes_menu_kb(),
        )
        return

    await message.answer("Твои последние заметки:")
    for note in notes:
        await message.answer(
            format_note_short(note),
            reply_markup=note_inline_kb_collapsed(note),
        )

    await message.answer(
        "Меню заметок:",
        reply_markup=notes_menu_kb(),
    )


# ====== Создание заметки ======
@notes_router.callback_query(F.data == "notes:add")
async def cb_add_note(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(NewNoteStates.waiting_for_title)
    await callback.message.answer(
        "Введи <b>заголовок заметки</b>:",
        reply_markup=main_menu_kb(),
    )


@notes_router.message(NewNoteStates.waiting_for_title)
async def new_note_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Попробуй ещё раз:")
        return

    await state.update_data(title=title)
    await state.set_state(NewNoteStates.waiting_for_content)
    await message.answer(
        "Теперь отправь <b>текст заметки</b> целиком.",
    )


@notes_router.message(NewNoteStates.waiting_for_content)
async def new_note_content(message: types.Message, state: FSMContext):
    content = message.text.strip()
    if not content:
        await message.answer("Текст заметки не может быть пустым. Попробуй ещё раз:")
        return

    await state.update_data(content=content)
    await state.set_state(NewNoteStates.waiting_for_tags)
    await message.answer(
        "Если хочешь, укажи <b>теги</b> через запятую (например: <code>работа, идеи</code>).\n"
        "Или напиши <code>-</code>, если теги не нужны.",
    )


@notes_router.message(NewNoteStates.waiting_for_tags)
async def new_note_tags(message: types.Message, state: FSMContext):
    tags_raw = message.text.strip()
    tags: Optional[str] = None if tags_raw == "-" else tags_raw

    data = await state.get_data()
    title = data["title"]
    content = data["content"]

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

        note = Note(
            user_id=user.id,
            title=title,
            content=content,
            tags=tags,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(note)
        await session.commit()

    await state.clear()

    await message.answer(
        "✅ Заметка сохранена!\n"
        "Открыть список можно через кнопку <b>«📝 Заметки»</b>.",
        reply_markup=main_menu_kb(),
    )


# ====== Обработка просмотра/закрытия/удаления заметки ======
@notes_router.callback_query(NoteActionCb.filter())
async def note_action_handler(
    callback: types.CallbackQuery,
    callback_data: NoteActionCb,
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
            select(Note).where(Note.id == callback_data.note_id)
        )
        note = result.scalar_one_or_none()

        if note is None or note.user_id != user.id:
            await callback.answer("Эта заметка больше не доступна.", show_alert=True)
            await callback.message.edit_text("❌ Заметка недоступна.")
            return

        # Открыть (развернуть)
        if callback_data.action == "view":
            await callback.message.edit_text(
                format_note_full(note),
                reply_markup=note_inline_kb_expanded(note),
            )
            await callback.answer()

        # Закрыть (свернуть)
        elif callback_data.action == "close":
            await callback.message.edit_text(
                format_note_short(note),
                reply_markup=note_inline_kb_collapsed(note),
            )
            await callback.answer()

        # Удалить
        elif callback_data.action == "delete":
            await session.delete(note)
            await session.commit()
            await callback.message.edit_text("🗑 Заметка удалена.")
            await callback.answer("Заметка удалена ✅")
