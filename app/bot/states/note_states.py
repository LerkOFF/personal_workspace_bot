from aiogram.fsm.state import StatesGroup, State


class NewNoteStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()
    waiting_for_tags = State()
