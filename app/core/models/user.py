from __future__ import annotations

from datetime import datetime
from typing import Optional

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

    # Связь: один пользователь -> много задач
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
