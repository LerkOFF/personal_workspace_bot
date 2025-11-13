from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class TaskFile(Base):
    __tablename__ = "task_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Идентификаторы файла в Telegram
    telegram_file_id: Mapped[str] = mapped_column()
    telegram_unique_id: Mapped[str] = mapped_column()

    # Метаданные
    file_name: Mapped[str] = mapped_column()
    mime_type: Mapped[Optional[str]] = mapped_column(nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(nullable=True)

    # document | photo (для выбора send_document / send_photo)
    file_kind: Mapped[str] = mapped_column(default="document")

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # связи
    task = relationship("Task", back_populates="files")
    user = relationship("User", back_populates="task_files")
