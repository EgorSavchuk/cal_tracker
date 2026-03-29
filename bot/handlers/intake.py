"""Handles all user input: text, photo, voice, media groups → LLM agent."""

import re
from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from loader import log
from services import database as db
from services import llm
from services.formatting import (
    format_agent_result,
    format_modification,
    format_save_products,
)
from services.states import TrackerStates
from services.voice import voice_to_text
from view import messages as msg
from view.keyboards import confirm_kb, close_confirm_kb, modification_kb

router = Router()


def _md_to_html(text: str) -> str:
    """Convert basic Markdown to Telegram HTML as safety net."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!</)\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
    return text


async def _download_photo(bot: Bot, message: Message) -> bytes:
    """Download the largest photo from a message."""
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    from io import BytesIO
    buf = BytesIO()
    await bot.download_file(file.file_path, buf)
    return buf.getvalue()


def _strip_images(conversation: list[dict]) -> list[dict]:
    """Remove image data from conversation for state storage (save memory)."""
    cleaned = []
    for msg_item in conversation:
        if isinstance(msg_item.get("content"), list):
            new_content = []
            for part in msg_item["content"]:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    new_content.append({"type": "text", "text": "[фото]"})
                else:
                    new_content.append(part)
            cleaned.append({**msg_item, "content": new_content})
        else:
            cleaned.append(msg_item)
    return cleaned


async def _extract_input(message: Message, bot: Bot, **kwargs) -> tuple[str, list[bytes]]:
    """Extract text and images from a message (text, photo, voice, album)."""
    user_text = ""
    images: list[bytes] = []

    album: list[Message] | None = kwargs.get("album")
    if album and len(album) > 1:
        caption = ""
        for msg_item in album:
            if msg_item.photo:
                images.append(await _download_photo(bot, msg_item))
            if msg_item.caption and not caption:
                caption = msg_item.caption
        user_text = caption
    elif message.voice:
        user_text = await voice_to_text(bot, message.voice)
    elif message.photo:
        user_text = message.caption or ""
        images.append(await _download_photo(bot, message))
    elif message.text:
        user_text = message.text

    return user_text, images


async def _cancel_pending_confirmation(message: Message, state: FSMContext) -> None:
    """Remove inline keyboard from the previous confirmation message."""
    data = await state.get_data()
    pending_msg_id = data.get("pending_message_id")
    if pending_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=pending_msg_id,
                reply_markup=None,
            )
        except Exception:
            pass


async def _process_agent_result(
    result: llm.AgentResult,
    message: Message,
    state: FSMContext,
    uid: int,
    is_close: bool = False,
) -> None:
    """Handle agent result: route to appropriate response."""

    if result.type == "text":
        # Direct text response (chat, analytics, help)
        text = _md_to_html(result.text or "🤷")
        await message.answer(text)
        # Save conversation history, stay in idle (no state change)
        await state.set_state(None)
        await state.update_data(
            conversation=_strip_images(result.conversation),
            pending_message_id=None,
        )
        return

    if result.type in ("log_food", "log_activity"):
        text = format_agent_result(result)

        has_new = False
        if result.meals and not is_close:
            known = await db.get_known_products(uid)
            known_names = {p["name"].lower() for p in known}
            has_new = any(m.name.lower() not in known_names for m in result.meals)

        state_data = {
            "agent_result": _serialize_result(result),
            "conversation": _strip_images(result.conversation),
            "date": date.today().isoformat(),
            "time": datetime.now().strftime("%H:%M"),
            "is_close": is_close,
        }
        await state.update_data(**state_data)

        if is_close:
            await state.set_state(TrackerStates.awaiting_close_confirmation)
            sent = await message.answer(text, reply_markup=close_confirm_kb())
        else:
            await state.set_state(TrackerStates.awaiting_confirmation)
            sent = await message.answer(text, reply_markup=confirm_kb(has_new_products=has_new))

        # Remember message ID so we can remove buttons later
        await state.update_data(pending_message_id=sent.message_id)
        return

    if result.type == "modify_entries":
        text = format_modification(result)
        await state.update_data(
            agent_result=_serialize_result(result),
            conversation=_strip_images(result.conversation),
        )
        await state.set_state(TrackerStates.awaiting_modification_confirmation)
        sent = await message.answer(text, reply_markup=modification_kb())
        await state.update_data(pending_message_id=sent.message_id)
        return

    if result.type == "save_products":
        saved = []
        for m in (result.meals or []):
            await db.add_known_product(
                user_id=uid,
                name=m.name,
                serving=m.description or None,
                kcal=m.kcal,
                protein=m.protein,
                fat=m.fat,
                carbs=m.carbs,
            )
            saved.append(m.name)
        names = ", ".join(saved)
        await message.answer(f"⭐ Запомнил: {names}")
        await state.update_data(
            conversation=_strip_images(result.conversation),
            pending_message_id=None,
        )
        return

    # Fallback
    await message.answer(result.text or msg.error_text)


def _serialize_result(result: llm.AgentResult) -> dict:
    """Serialize AgentResult for FSM state storage."""
    data = {"type": result.type}
    if result.meals:
        data["meals"] = [m.model_dump() for m in result.meals]
    if result.activities:
        data["activities"] = [a.model_dump() for a in result.activities]
    if result.modifications:
        data["modifications"] = [m.model_dump() for m in result.modifications]
    if result.mod_description:
        data["mod_description"] = result.mod_description
    if result.comment:
        data["comment"] = result.comment
    return data


def _deserialize_result(data: dict) -> llm.AgentResult:
    """Deserialize AgentResult from FSM state."""
    return llm.AgentResult(
        type=data["type"],
        meals=[llm.MealItem(**m) for m in data.get("meals", [])] or None,
        activities=[llm.ActivityItem(**a) for a in data.get("activities", [])] or None,
        modifications=[llm.ModifyAction(**m) for m in data.get("modifications", [])] or None,
        mod_description=data.get("mod_description"),
        comment=data.get("comment"),
    )


async def _run_agent(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user_text: str = "",
    images: list[bytes] | None = None,
    is_close: bool = False,
    conversation: list[dict] | None = None,
) -> None:
    """Run LLM agent and handle result."""
    uid = message.from_user.id
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    profile = await db.get_profile(uid)
    known_products = await db.get_known_products(uid)

    try:
        result = await llm.process_message(
            user_id=uid,
            user_text=user_text,
            profile=profile,
            images=images,
            known_products=known_products,
            conversation=conversation,
            is_close=is_close,
        )
    except Exception as e:
        log.error(f"LLM agent error: {e}")
        await message.answer(msg.error_text)
        return

    await _process_agent_result(result, message, state, uid, is_close)


# ── Closing day: user answers about activities ───────────


@router.message(TrackerStates.closing_day, F.text)
async def handle_close_activities(message: Message, state: FSMContext, bot: Bot):
    await _run_agent(message, state, bot, user_text=message.text, is_close=True)


# ── Clarification after "Уточнить" button ─────────────────


@router.message(TrackerStates.awaiting_clarification, F.text | F.photo | F.voice)
async def handle_clarification(message: Message, state: FSMContext, bot: Bot, **kwargs):
    data = await state.get_data()
    conversation = data.get("conversation", [])
    is_close = data.get("is_close", False)

    user_text, images = await _extract_input(message, bot, **kwargs)
    if not user_text and not images:
        return

    await _run_agent(
        message, state, bot,
        user_text=user_text,
        images=images or None,
        conversation=conversation,
        is_close=is_close,
    )


@router.message(TrackerStates.awaiting_close_clarification, F.text | F.photo | F.voice)
async def handle_close_clarification(message: Message, state: FSMContext, bot: Bot, **kwargs):
    data = await state.get_data()
    conversation = data.get("conversation", [])

    user_text, images = await _extract_input(message, bot, **kwargs)
    if not user_text and not images:
        return

    await _run_agent(
        message, state, bot,
        user_text=user_text,
        images=images or None,
        conversation=conversation,
        is_close=True,
    )


# ── Continue conversation during pending confirmation ──────
# Instead of blocking, cancel the pending confirmation and
# re-run agent with conversation history + new input.


@router.message(TrackerStates.awaiting_confirmation, F.text | F.photo | F.voice)
@router.message(TrackerStates.awaiting_close_confirmation, F.text | F.photo | F.voice)
@router.message(TrackerStates.awaiting_modification_confirmation, F.text | F.photo | F.voice)
async def handle_continue_during_pending(message: Message, state: FSMContext, bot: Bot, **kwargs):
    """User sent new input while confirmation is pending — treat as continuation."""
    data = await state.get_data()
    conversation = data.get("conversation", [])
    is_close = data.get("is_close", False)
    current_state = await state.get_state()

    # Remove buttons from the old confirmation message
    await _cancel_pending_confirmation(message, state)

    user_text, images = await _extract_input(message, bot, **kwargs)
    if not user_text and not images:
        return

    # Determine if we're in close-day flow
    if current_state in (
        TrackerStates.awaiting_close_confirmation,
    ):
        is_close = True

    await _run_agent(
        message, state, bot,
        user_text=user_text,
        images=images or None,
        conversation=conversation,
        is_close=is_close,
    )


# ── Main catch-all: text, photo, voice ───────────────────


@router.message(F.text | F.photo | F.voice)
async def handle_input(message: Message, state: FSMContext, bot: Bot, **kwargs):
    user_text, images = await _extract_input(message, bot, **kwargs)

    if not user_text and not images:
        return

    # Load conversation history for context continuity
    data = await state.get_data()
    conversation = data.get("conversation") or None

    await _run_agent(
        message, state, bot,
        user_text=user_text,
        images=images or None,
        conversation=conversation,
    )
