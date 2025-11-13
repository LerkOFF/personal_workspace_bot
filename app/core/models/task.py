from __future__ import annotations

from datetime import datetime
from typing import Optional
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class TaskStatus(PyEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # теперь задача МОЖЕТ быть привязана к проекту, а может и нет
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str]
    description: Mapped[Optional[str]]

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus),
        default=TaskStatus.TODO,
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    due_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    # связи
    user = relationship("User", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    files = relationship(
        "TaskFile",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    subtasks = relationship(
        "SubTask",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    # ====== Напоминания по дедлайнам ======
    # Отправлено ли напоминание за 1 день до дедлайна
    remind_1day_sent: Mapped[bool] = mapped_column(default=False)
    # Отправлено ли напоминание за 3 часа
    remind_3h_sent: Mapped[bool] = mapped_column(default=False)
    # Отправлено ли напоминание за 1 час
    remind_1h_sent: Mapped[bool] = mapped_column(default=False)
