from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated

from loader import dp
from services.analytics import log_event
from services.user_status import clear_user_blocked, mark_user_blocked


@dp.my_chat_member()
async def handle_bot_block(update: ChatMemberUpdated) -> None:
    if update.chat.type != ChatType.PRIVATE:
        return

    user_id = update.chat.id
    status = update.new_chat_member.status

    if status == ChatMemberStatus.KICKED:
        await mark_user_blocked(user_id)
        await log_event(user_id, "bot_blocked")
        return

    if status == ChatMemberStatus.MEMBER:
        await clear_user_blocked(user_id)
        await log_event(user_id, "bot_unblocked")
