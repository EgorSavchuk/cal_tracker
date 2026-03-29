from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import WEBAPP_HOST, WEBAPP_PORT
from services import database as db
from services.formatting import format_day_full, format_day_close_card
from services.states import TrackerStates
from view import messages as msg
from view.keyboards import dashboard_kb

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    user = await db.get_user(uid)
    is_new = user is None or user.get("status") == "pending"

    await message.answer(msg.start)

    if is_new or not await _has_any_data(uid):
        import asyncio
        await asyncio.sleep(0.5)
        await message.answer(msg.onboarding_1)
        await asyncio.sleep(1.0)
        await message.answer(msg.onboarding_2)


async def _has_any_data(user_id: int) -> bool:
    """Check if user has any meals or activities recorded."""
    meals = await db.get_meals_by_date(user_id, "")
    # Quick check — just see if any dates exist
    dates = await db.get_all_dates(user_id)
    return len(dates) > 0


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(msg.help_text)


@router.message(Command("day"))
async def cmd_day(message: Message):
    uid = message.from_user.id
    today = date.today().isoformat()
    summary = await db.get_day_summary(uid, today)
    profile = await db.get_profile(uid)

    if not summary["meals"] and not summary["activities"]:
        await message.answer("Сегодня пока ничего не записано.")
        return

    text = format_day_full(summary, profile)
    await message.answer(text)


@router.message(Command("close"))
async def cmd_close(message: Message, state: FSMContext):
    await state.set_state(TrackerStates.closing_day)
    await message.answer(msg.close_prompt)


@router.message(Command("undo"))
async def cmd_undo(message: Message):
    uid = message.from_user.id
    deleted = await db.delete_last_entry(uid)
    if deleted:
        await message.answer(f"Удалено: {deleted}")
    else:
        await message.answer(msg.nothing_to_undo)


@router.message(Command("products"))
async def cmd_products(message: Message):
    uid = message.from_user.id
    products = await db.get_known_products(uid)
    if not products:
        await message.answer("Список известных продуктов пуст.\n\nПри оценке блюда нажми ⭐ Запомнить, чтобы сохранить продукт.")
        return

    lines = ["⭐ <b>Известные продукты</b>\n"]
    for p in products:
        serving = f" ({p['serving']})" if p.get("serving") else ""
        lines.append(
            f"  {p['name']}{serving}\n"
            f"  {int(p['kcal'])} ккал · Б{int(p['protein'])} Ж{int(p['fat'])} У{int(p['carbs'])}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message):
    # TODO: replace with actual WEBAPP_URL from config
    url = f"https://localhost:{WEBAPP_PORT}"
    await message.answer("📊 Открой дашборд:", reply_markup=dashboard_kb(url))
