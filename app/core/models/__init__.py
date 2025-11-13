from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех моделей ORM."""
    pass


from .user import User
from .task import Task
from .note import Note
from .project import Project
from .task_file import TaskFile
from .subtask import SubTask