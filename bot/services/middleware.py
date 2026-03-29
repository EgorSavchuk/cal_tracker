import asyncio
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config import ADMIN_USER_ID
from loader import log
from services import database as db


class AccessControlMiddleware(BaseMiddleware):
    """Controls user access: admin auto-approved, others need admin approval."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Admin always has access and is auto-approved
        if user.id == ADMIN_USER_ID:
            # Ensure admin exists in DB
            existing = await db.get_user(user.id)
            if not existing:
                await db.create_user(user.id, user.username, user.full_name or "Admin")
                await db.set_user_status(user.id, "approved")
            return await handler(event, data)

        # Check user status
        existing = await db.get_user(user.id)

        if existing is None:
            # New user — create as pending, notify admin
            await db.create_user(user.id, user.username, user.full_name or "")
            await _notify_admin_new_user(event, user)
            if isinstance(event, Message):
                await event.answer(
                    "⏳ Запрос на доступ отправлен администратору. Ожидай подтверждения."
                )
            return None

        if existing["status"] == "approved":
            return await handler(event, data)

        if existing["status"] == "pending":
            if isinstance(event, Message):
                await event.answer("⏳ Твой запрос ещё на рассмотрении.")
            return None

        # rejected
        if isinstance(event, Message):
            await event.answer("❌ Доступ отклонён.")
        return None


async def _notify_admin_new_user(event: TelegramObject, user) -> None:
    """Send admin a message about new user with approve/reject buttons."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    name = user.full_name or user.username or str(user.id)
    username_str = f" (@{user.username})" if user.username else ""
    text = (
        f"🆕 <b>Новый пользователь</b>\n\n"
        f"Имя: {name}{username_str}\n"
        f"ID: <code>{user.id}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve:{user.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{user.id}"),
        ]
    ])

    bot = event.bot
    try:
        await bot.send_message(ADMIN_USER_ID, text, reply_markup=kb)
    except Exception as e:
        log.error(f"Failed to notify admin about new user {user.id}: {e}")


class AlbumMiddleware(BaseMiddleware):
    """Collects media group messages into a single list.

    Stores collected photos in data["album"] for the handler.
    Only the first message in a group proceeds to the handler.
    """

    COLLECT_DELAY = 0.5  # seconds

    def __init__(self) -> None:
        super().__init__()
        self._albums: dict[str, list[Message]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not event.media_group_id:
            # Not a media group — pass through
            return await handler(event, data)

        mgid = event.media_group_id

        if mgid not in self._albums:
            self._albums[mgid] = []

        self._albums[mgid].append(event)

        # Cancel previous timer for this group if exists
        if mgid in self._tasks:
            self._tasks[mgid].cancel()

        # Create a future that the first message will await
        if len(self._albums[mgid]) == 1:
            # First message in group — it will be the one that proceeds
            self._albums[mgid + "_event"] = asyncio.Event()

        # Set timer to signal completion
        async def _signal_done(group_id: str):
            await asyncio.sleep(self.COLLECT_DELAY)
            evt = self._albums.get(group_id + "_event")
            if evt:
                evt.set()

        self._tasks[mgid] = asyncio.create_task(_signal_done(mgid))

        if len(self._albums[mgid]) == 1:
            # First message — wait for collection to complete
            await self._albums[mgid + "_event"].wait()
            album = self._albums.pop(mgid, [])
            self._albums.pop(mgid + "_event", None)
            self._tasks.pop(mgid, None)
            data["album"] = album
            return await handler(event, data)
        else:
            # Subsequent messages — absorbed, don't call handler
            return None
