from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

CATEGORIES = [
    ("💻 Код", "code"),
    ("🤝 Митинг", "meeting"),
    ("📚 Обучение", "learning"),
    ("☕ Перерыв", "break"),
    ("🔧 Другое", "other"),
]

CAT_DISPLAY = {v: k for k, v in CATEGORIES}


def main_keyboard(has_active: bool = False) -> ReplyKeyboardMarkup:
    if has_active:
        rows = [[KeyboardButton(text="⏹ Стоп")], [KeyboardButton(text="📊 День")]]
    else:
        rows = [[KeyboardButton(text="▶️ Старт")], [KeyboardButton(text="📊 День")]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cat:{cb}")]
        for name, cb in CATEGORIES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
