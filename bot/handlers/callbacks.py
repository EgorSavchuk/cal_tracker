"""Inline button handlers for confirm/clarify/modify cycle."""

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import ADMIN_USER_ID
from services import database as db
from services.formatting import format_day_summary_short, format_day_close_card
from services.llm import MealItem, ActivityItem, ModifyAction
from services.states import TrackerStates
from view.buttons import (
    CONFIRM, CLARIFY, CLOSE_CONFIRM, CLOSE_CLARIFY,
    SAVE_PRODUCTS, MOD_CONFIRM, MOD_REJECT,
)
from view import messages as msg
from view.keyboards import confirm_kb

router = Router()


async def _save_meals_activities(uid: int, data: dict) -> None:
    """Save meals and activities from agent result to database."""
    agent_data = data["agent_result"]
    meal_date = data.get("date", date.today().isoformat())
    meal_time = data.get("time", "")

    for m in agent_data.get("meals", []):
        await db.add_meal(
            user_id=uid,
            meal_date=meal_date,
            meal_time=meal_time,
            name=m["name"],
            description=m.get("description") or None,
            kcal=m["kcal"],
            protein=m["protein"],
            fat=m["fat"],
            carbs=m["carbs"],
        )

    for a in agent_data.get("activities", []):
        await db.add_activity(
            user_id=uid,
            act_date=meal_date,
            name=a["name"],
            duration=a.get("duration") or None,
            kcal=a["kcal"],
            category=a.get("category", ""),
        )


# ── Regular confirm/clarify ─────────────────────────────


@router.callback_query(F.data == CONFIRM, TrackerStates.awaiting_confirmation)
async def on_confirm(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    await _save_meals_activities(uid, data)

    today = date.today().isoformat()
    summary = await db.get_day_summary(uid, today)
    profile = await db.get_profile(uid)

    text = format_day_summary_short(summary["totals"], profile)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(text)
    # Preserve conversation history, clear the rest
    conversation = data.get("conversation")
    await state.clear()
    if conversation:
        await state.update_data(conversation=conversation)


@router.callback_query(F.data == CLARIFY, TrackerStates.awaiting_confirmation)
async def on_clarify(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TrackerStates.awaiting_clarification)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.clarify_prompt)


# ── Close-day confirm/clarify ───────────────────────────


@router.callback_query(F.data == CLOSE_CONFIRM, TrackerStates.awaiting_close_confirmation)
async def on_close_confirm(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    await _save_meals_activities(uid, data)

    today = date.today().isoformat()
    summary = await db.get_day_summary(uid, today)
    profile = await db.get_profile(uid)
    cumulative = await db.get_cumulative_balance(uid)

    text = format_day_close_card(summary, profile, cumulative["balance"])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(text)
    conversation = data.get("conversation")
    await state.clear()
    if conversation:
        await state.update_data(conversation=conversation)


@router.callback_query(F.data == CLOSE_CLARIFY, TrackerStates.awaiting_close_confirmation)
async def on_close_clarify(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TrackerStates.awaiting_close_clarification)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.clarify_prompt)


# ── Save products to known_products ──────────────────────


@router.callback_query(F.data == SAVE_PRODUCTS, TrackerStates.awaiting_confirmation)
async def on_save_products(callback: CallbackQuery, state: FSMContext):
    """Save all meals from current result as known products."""
    uid = callback.from_user.id
    data = await state.get_data()
    agent_data = data["agent_result"]

    saved = []
    for m in agent_data.get("meals", []):
        await db.add_known_product(
            user_id=uid,
            name=m["name"],
            serving=m.get("description") or None,
            kcal=m["kcal"],
            protein=m["protein"],
            fat=m["fat"],
            carbs=m["carbs"],
        )
        saved.append(m["name"])

    await callback.message.edit_reply_markup(reply_markup=confirm_kb(has_new_products=False))
    names = ", ".join(saved)
    await callback.message.answer(f"⭐ Запомнил: {names}")


# ── Modification confirm/reject ──────────────────────────


@router.callback_query(F.data == MOD_CONFIRM, TrackerStates.awaiting_modification_confirmation)
async def on_mod_confirm(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    agent_data = data["agent_result"]

    results = []
    for mod in agent_data.get("modifications", []):
        action = mod["action"]
        table = mod["table"]
        entry_id = mod["entry_id"]

        if action == "delete":
            name = await db.delete_entry(uid, table, entry_id)
            if name:
                results.append(f"🗑 Удалено: {name}")
            else:
                results.append(f"❌ Запись #{entry_id} не найдена")

        elif action == "move":
            updates = {}
            if mod.get("new_date"):
                updates["date"] = mod["new_date"]
            if mod.get("new_time"):
                updates["time"] = mod["new_time"]
            if table == "meals":
                ok = await db.update_meal(uid, entry_id, **updates)
            else:
                ok = await db.update_activity(uid, entry_id, **updates)
            if ok:
                dest = mod.get("new_date", "")
                if mod.get("new_time"):
                    dest += f" {mod['new_time']}"
                results.append(f"📦 Перенесено #{entry_id} → {dest}")
            else:
                results.append(f"❌ Запись #{entry_id} не найдена")

        elif action == "edit":
            new_vals = mod.get("new_values", {})
            if table == "meals":
                ok = await db.update_meal(uid, entry_id, **new_vals)
            else:
                ok = await db.update_activity(uid, entry_id, **new_vals)
            if ok:
                results.append(f"✏️ Изменено #{entry_id}")
            else:
                results.append(f"❌ Запись #{entry_id} не найдена")

    await callback.message.edit_reply_markup(reply_markup=None)
    text = "✅ Готово\n\n" + "\n".join(results)
    await callback.message.answer(text)
    conversation = data.get("conversation")
    await state.clear()
    if conversation:
        await state.update_data(conversation=conversation)


@router.callback_query(F.data == MOD_REJECT, TrackerStates.awaiting_modification_confirmation)
async def on_mod_reject(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Отменено")
    data = await state.get_data()
    conversation = data.get("conversation")
    await state.clear()
    if conversation:
        await state.update_data(conversation=conversation)


# ── Admin approve/reject ─────────────────────────────────


@router.callback_query(F.data.startswith("admin_approve:"))
async def on_admin_approve(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_USER_ID:
        return

    target_id = int(callback.data.split(":")[1])
    await db.set_user_status(target_id, "approved")

    user = await db.get_user(target_id)
    name = user["full_name"] or user["username"] or str(target_id)

    await callback.message.edit_text(
        f"✅ <b>{name}</b> (ID: {target_id}) — доступ одобрен",
    )

    try:
        await callback.bot.send_message(
            target_id,
            "✅ Доступ одобрен! Отправь /start чтобы начать.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reject:"))
async def on_admin_reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_USER_ID:
        return

    target_id = int(callback.data.split(":")[1])
    await db.set_user_status(target_id, "rejected")

    user = await db.get_user(target_id)
    name = user["full_name"] or user["username"] or str(target_id)

    await callback.message.edit_text(
        f"❌ <b>{name}</b> (ID: {target_id}) — доступ отклонён",
    )

    try:
        await callback.bot.send_message(target_id, "❌ Доступ отклонён.")
    except Exception:
        pass
