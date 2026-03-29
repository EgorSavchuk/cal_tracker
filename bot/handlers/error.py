from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types.error_event import ErrorEvent

from loader import bot, log
from view import messages as msg

router = Router()


@router.errors()
async def errors_handler(event: ErrorEvent):
    if isinstance(event.exception, TelegramBadRequest) and "query is too old" in str(
        event.exception
    ):
        return

    log.exception(f"Error: {event.exception}")

    user_id = None
    if event.update:
        if event.update.callback_query:
            user_id = event.update.callback_query.from_user.id
        elif event.update.message:
            user_id = event.update.message.from_user.id

    if user_id:
        try:
            await bot.send_message(user_id, msg.error_text)
        except Exception:
            pass
