from datetime import datetime, date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from aiogram import Bot

from app.core.db import async_session_maker
from app.core.models.user import User
from app.core.models.task import Task, TaskStatus
from app.core.models.note import Note
from app.core.models.project import Project


def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Каждый день в 09:00
    scheduler.add_job(
        daily_digest,
        trigger="cron",
        hour=9,
        minute=0,
        args=[bot],
    )

    scheduler.start()


async def daily_digest(bot: Bot):
    today = date.today()
    yesterday = today - timedelta(days=1)

    async with async_session_maker() as session:
        # Получаем всех пользователей
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # Выбираем задачи
            tasks_result = await session.execute(
                select(Task)
                .where(Task.user_id == user.id)
            )
            tasks = tasks_result.scalars().all()

            tasks_today = []
            tasks_overdue = []
            tasks_no_deadline = []

            for task in tasks:
                if task.due_at is None:
                    tasks_no_deadline.append(task)
                else:
                    d = task.due_at.date()
                    if d < today:
                        tasks_overdue.append(task)
                    elif d == today:
                        tasks_today.append(task)

            # выбираем заметки за вчера
            notes_result = await session.execute(
                select(Note)
                .where(Note.user_id == user.id)
                .where(Note.created_at >= datetime(yesterday.year, yesterday.month, yesterday.day))
            )
            notes = notes_result.scalars().all()

            # проекты
            projects_result = await session.execute(
                select(Project)
                .where(Project.user_id == user.id)
            )
            projects = projects_result.scalars().all()

            # Формируем сообщение
            text_lines = []
            text_lines.append("👋 <b>Доброе утро!</b>\n")

            if tasks_today:
                text_lines.append("🟠 <b>Задачи на сегодня:</b>")
                for t in tasks_today:
                    text_lines.append(f"• {t.title}")
                text_lines.append("")

            if tasks_overdue:
                text_lines.append("🔥 <b>Просроченные задачи:</b>")
                for t in tasks_overdue:
                    text_lines.append(f"• {t.title} — было до {t.due_at.strftime('%d.%m.%Y')}")
                text_lines.append("")

            if tasks_no_deadline:
                text_lines.append("📝 <b>Задачи без дедлайна:</b>")
                for t in tasks_no_deadline:
                    text_lines.append(f"• {t.title}")
                text_lines.append("")

            if notes:
                text_lines.append("🧠 <b>Новые заметки с вчера:</b>")
                for n in notes:
                    base = (n.content or "").strip()
                    if not base:
                        base = (n.title or "").strip()

                    if not base:
                        base = "(пустая заметка)"

                    short = base
                    if len(short) > 50:
                        short = short[:47] + "..."

                    text_lines.append(f"• {short}")
                text_lines.append("")

            if projects:
                text_lines.append("📁 <b>Твои проекты:</b>")
                for p in projects:
                    text_lines.append(f"• {p.name}")
                text_lines.append("")

            full_text = "\n".join(text_lines).strip()

            # если данных нет — пропускаем отправку
            if not tasks_today and not tasks_overdue and not tasks_no_deadline and not notes and not projects:
                continue

            try:
                await bot.send_message(
                    user.telegram_id,
                    full_text,
                )
            except Exception:
                pass
