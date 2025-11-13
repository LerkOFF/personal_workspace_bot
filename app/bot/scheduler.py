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

    # Запускаем джоб каждые 1 минуту
    scheduler.add_job(
        daily_digest,
        trigger="interval",
        minutes=1,
        args=[bot],
    )

    scheduler.start()


async def daily_digest(bot: Bot):
    today = date.today()
    yesterday = today - timedelta(days=1)
    now = datetime.now()

    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # Настройки пользователя
            digest_enabled = getattr(user, "reminders_enabled", True)
            deadline_enabled = getattr(user, "deadline_reminders_enabled", True)
            reminder_hour = getattr(user, "reminder_hour", 9)
            reminder_minute = getattr(user, "reminder_minute", 0)
            last_digest_date = getattr(user, "last_digest_date", None)

            # ------ общие данные: задачи, заметки, проекты ------
            tasks_result = await session.execute(
                select(Task).where(Task.user_id == user.id)
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

            notes_result = await session.execute(
                select(Note)
                .where(Note.user_id == user.id)
                .where(
                    Note.created_at >= datetime(
                        yesterday.year, yesterday.month, yesterday.day
                    )
                )
            )
            notes = notes_result.scalars().all()

            projects_result = await session.execute(
                select(Project).where(Project.user_id == user.id)
            )
            projects = projects_result.scalars().all()

            # ------ Ежедневный дайджест ------
            if digest_enabled:
                if (
                    last_digest_date != today
                    and now.hour == reminder_hour
                    and now.minute == reminder_minute
                ):
                    if (
                        tasks_today
                        or tasks_overdue
                        or tasks_no_deadline
                        or notes
                        or projects
                    ):
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
                                text_lines.append(
                                    f"• {t.title} — было до {t.due_at.strftime('%d.%m.%Y')}"
                                )
                            text_lines.append("")

                        if tasks_no_deadline:
                            text_lines.append("📝 <b>Задачи без дедлайна:</b>")
                            for t in tasks_no_deadline:
                                text_lines.append(f"• {t.title}")
                            text_lines.append("")

                        if notes:
                            text_lines.append("🧠 <b>Новые заметки со вчера:</b>")
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

                        try:
                            await bot.send_message(user.telegram_id, full_text)
                        except Exception:
                            pass
                        else:
                            user.last_digest_date = today

            # ------ Напоминания о дедлайнах задач ------
            if deadline_enabled:
                for task in tasks:
                    if task.due_at is None:
                        continue
                    if task.status == TaskStatus.DONE:
                        continue

                    delta = task.due_at - now
                    delta_minutes = delta.total_seconds() / 60

                    if delta_minutes <= 0:
                        continue

                    def in_window(target_minutes: int, tolerance: int = 5) -> bool:
                        return (
                            target_minutes - tolerance
                            <= delta_minutes
                            <= target_minutes + tolerance
                        )

                    # за 1 день
                    if (
                        in_window(24 * 60)
                        and not task.remind_1day_sent
                    ):
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                (
                                    "⏰ <b>Напоминание по задаче</b>\n"
                                    f"До дедлайна по задаче <b>«{task.title}»</b> "
                                    "остался <b>1 день</b>."
                                ),
                            )
                        except Exception:
                            pass
                        task.remind_1day_sent = True

                    # за 3 часа
                    if (
                        in_window(3 * 60)
                        and not task.remind_3h_sent
                    ):
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                (
                                    "⏰ <b>Напоминание по задаче</b>\n"
                                    f"До дедлайна по задаче <b>«{task.title}»</b> "
                                    "осталось <b>3 часа</b>."
                                ),
                            )
                        except Exception:
                            pass
                        task.remind_3h_sent = True

                    # за 1 час
                    if (
                        in_window(60)
                        and not task.remind_1h_sent
                    ):
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                (
                                    "⏰ <b>Напоминание по задаче</b>\n"
                                    f"До дедлайна по задаче <b>«{task.title}»</b> "
                                    "остался <b>1 час</b>."
                                ),
                            )
                        except Exception:
                            pass
                        task.remind_1h_sent = True

            await session.commit()
