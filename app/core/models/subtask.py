from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class SubTask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    title: Mapped[str] = mapped_column()
    is_done: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # связи
    task = relationship("Task", back_populates="subtasks")
    user = relationship("User", back_populates="subtasks")
