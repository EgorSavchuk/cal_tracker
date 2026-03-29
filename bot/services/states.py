from aiogram.fsm.state import State, StatesGroup


class TrackerStates(StatesGroup):
    awaiting_confirmation = State()
    awaiting_clarification = State()
    closing_day = State()
    awaiting_close_confirmation = State()
    awaiting_close_clarification = State()
    awaiting_modification_confirmation = State()
