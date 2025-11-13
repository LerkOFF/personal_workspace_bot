from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.core.models import Base

# Движок для SQLite (async)
engine = create_async_engine(
    settings.database_url,
    echo=False,          # можно поменять на True для отладки SQL
    future=True,
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Создаёт таблицы в БД, если их ещё нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
