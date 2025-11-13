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

    title: Mapped[str]
    description: Mapped[Optional[str]]

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus),
        default=TaskStatus.TODO,
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    due_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    # связь с User
    user = relationship("User", back_populates="tasks")
