# Personal Workspace Bot

Этот проект создан для развития собственных навыком, он не несет цель стать коммерческим, если вы наткнулись на него и он Вам понравился - свяжитель со мной по почте lerk@joulerk.ru


Telegram-бот — личный цифровой рабочий стол:
задачи, заметки, проекты, файлы и интеграции — всё внутри Telegram.

## Стек

- Python 3.13
- aiogram 3.22
- SQLite + SQLAlchemy (async)
- pydantic / pydantic-settings

## Быстрый старт

```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# заполнить .env (BOT_TOKEN)
python -m app.main
