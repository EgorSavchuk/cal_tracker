from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from view.buttons import (
    CONFIRM, CLARIFY, CLOSE_CONFIRM, CLOSE_CLARIFY,
    SAVE_PRODUCTS, MOD_CONFIRM, MOD_REJECT,
)


def confirm_kb(has_new_products: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Записать", callback_data=CONFIRM),
            InlineKeyboardButton(text="✏️ Уточнить", callback_data=CLARIFY),
        ]
    ]
    if has_new_products:
        rows.append([
            InlineKeyboardButton(text="⭐ Запомнить продукты", callback_data=SAVE_PRODUCTS),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def close_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Записать", callback_data=CLOSE_CONFIRM),
            InlineKeyboardButton(text="✏️ Уточнить", callback_data=CLOSE_CLARIFY),
        ]
    ])


def modification_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=MOD_CONFIRM),
            InlineKeyboardButton(text="❌ Отмена", callback_data=MOD_REJECT),
        ]
    ])


def dashboard_kb(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Дашборд", web_app=WebAppInfo(url=webapp_url))]
    ])
