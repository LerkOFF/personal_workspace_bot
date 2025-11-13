from aiogram.fsm.state import StatesGroup, State


class SettingsStates(StatesGroup):
    # Ожидаем ввода времени напоминаний в формате ЧЧ:ММ
    waiting_for_reminder_time = State()
