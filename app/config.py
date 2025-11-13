from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field("sqlite+aiosqlite:///./app.db", alias="DATABASE_URL")
    env: str = Field("dev", alias="ENV")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
