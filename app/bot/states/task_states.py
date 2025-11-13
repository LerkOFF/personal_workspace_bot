from aiogram.fsm.state import StatesGroup, State


class NewTaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_project = State()
    waiting_for_due_date = State()


class TaskFileStates(StatesGroup):
    # Ждём, когда пользователь отправит файл для конкретной задачи
    waiting_for_file = State()
