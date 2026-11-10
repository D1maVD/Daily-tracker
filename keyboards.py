from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_keyboard(has_active: bool = False) -> ReplyKeyboardMarkup:
    if has_active:
        rows = [[KeyboardButton(text="⏹ Стоп")], [KeyboardButton(text="📊 День")]]
    else:
        rows = [[KeyboardButton(text="▶️ Старт")], [KeyboardButton(text="📊 День")]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Согласен", callback_data="consent:yes"),
        InlineKeyboardButton(text="❌ Отказать", callback_data="consent:no"),
    ]])


def confirm_delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, удалить всё", callback_data="delete:confirm"),
        InlineKeyboardButton(text="Отмена", callback_data="delete:cancel"),
    ]])


def category_keyboard(categories: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=cat_name, callback_data=f"cat:{cat_id}")]
        for cat_id, cat_name in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
