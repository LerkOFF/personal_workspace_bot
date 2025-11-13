from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех моделей ORM."""
    pass


# Импортируем модели, чтобы Alembic/metadata всё видели
from .user import User  # noqa: F401
