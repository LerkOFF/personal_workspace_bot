import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.bot.scheduler import setup_scheduler

from app.config import settings
from app.bot.routers.common import common_router
from app.bot.routers.tasks import tasks_router
from app.bot.routers.notes import notes_router
from app.bot.routers.projects import projects_router
from app.bot.routers.settings import settings_router
from app.core.db import init_db


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dp = Dispatcher()

    dp.include_routers(
        common_router,
        tasks_router,
        notes_router,
        projects_router,
        settings_router,
    )

    logging.info("Initializing database...")
    await init_db()
    logging.info("Database initialized.")

    logging.info("Bot is starting...")
    setup_scheduler(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
