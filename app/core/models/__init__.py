from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех моделей ORM."""
    pass


from .user import User    # noqa: F401
from .task import Task    # noqa: F401
from .note import Note    # noqa: F401
from .project import Project  # noqa: F401
