from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )
    first_name: Mapped[Optional[str]]
    last_name: Mapped[Optional[str]]
    username: Mapped[Optional[str]]

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # ====== НАСТРОЙКИ НАПОМИНАНИЙ ======
    # Включены ли ежедневные напоминания (дайджест)
    reminders_enabled: Mapped[bool] = mapped_column(default=True)

    # Время, когда слать дайджест (по умолчанию 09:00)
    reminder_hour: Mapped[int] = mapped_column(default=9)
    reminder_minute: Mapped[int] = mapped_column(default=0)

    # Когда в последний раз отправлялся дайджест этому пользователю
    last_digest_date: Mapped[Optional[date]] = mapped_column(default=None)

    # ====== Связи ======
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notes: Mapped[List["Note"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    projects: Mapped[List["Project"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
