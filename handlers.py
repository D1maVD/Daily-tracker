from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

import db
from keyboards import main_keyboard, category_keyboard

router = Router()


class SessionStates(StatesGroup):
    waiting_description = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    active = await db.get_active_session(message.from_user.id)
    await message.answer(
        "👋 Привет! Я трекер времени.\n\n"
        "▶️ Старт — начать сессию\n"
        "⏹ Стоп — завершить и записать\n"
        "📊 День — итоги сегодня",
        reply_markup=main_keyboard(has_active=bool(active))
    )


@router.message(F.text == "▶️ Старт")
async def start_session(message: Message):
    active = await db.get_active_session(message.from_user.id)
    if active:
        _, cat, start = active
        elapsed = int((datetime.now() - datetime.fromisoformat(start)).total_seconds() / 60)
        h, m = divmod(elapsed, 60)
        time_str = f"{h}ч {m}мин" if h else f"{m}мин"
        await message.answer(f"⚠️ Уже идёт сессия: {cat} ({time_str})\n\nСначала нажми ⏹ Стоп")
        return

    categories = await db.get_categories(message.from_user.id)
    await message.answer("Выбери категорию:", reply_markup=category_keyboard(categories))


@router.callback_query(F.data.startswith("cat:"))
async def category_selected(callback: CallbackQuery):
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    categories = await db.get_categories(user_id)
    cat_map = {c[0]: c[1] for c in categories}
    cat = cat_map.get(cat_id, "Другое")

    await db.start_session(user_id, cat)
    await callback.message.edit_text(f"✅ Начал: {cat}")
    await callback.message.answer(
        f"⏱ Идёт трекинг — {cat}\n\nНажми ⏹ Стоп когда закончишь",
        reply_markup=main_keyboard(has_active=True)
    )
    await callback.answer()


@router.message(F.text == "⏹ Стоп")
async def stop_session(message: Message, state: FSMContext):
    active = await db.get_active_session(message.from_user.id)
    if not active:
        await message.answer("Нет активной сессии.", reply_markup=main_keyboard(has_active=False))
        return

    await state.set_state(SessionStates.waiting_description)
    await message.answer("Коротко — что сделал? (или отправь «-» чтобы пропустить)")


@router.message(SessionStates.waiting_description)
async def save_description(message: Message, state: FSMContext):
    description = None if message.text.strip() == "-" else message.text.strip()
    duration = await db.stop_session(message.from_user.id, description)
    await state.clear()

    if duration is None:
        await message.answer("Сессия не найдена.", reply_markup=main_keyboard(has_active=False))
        return

    h, m = divmod(duration, 60)
    time_str = f"{h}ч {m}мин" if h else f"{m}мин"
    await message.answer(f"✅ Записано!\n⏱ Время: {time_str}", reply_markup=main_keyboard(has_active=False))


@router.message(F.text == "📊 День")
async def day_summary(message: Message):
    sessions = await db.get_today_sessions(message.from_user.id)

    if not sessions:
        await message.answer("Сегодня нет завершённых сессий.")
        return

    total = sum(s[4] for s in sessions if s[4])
    h, m = divmod(total, 60)
    total_str = f"{h}ч {m}мин" if h else f"{m}мин"

    lines = [f"📊 *Сегодня:* {total_str}\n"]
    for cat, start, _, desc, dur in sessions:
        t = datetime.fromisoformat(start).strftime("%H:%M")
        line = f"• {t} {cat} — {dur}мин"
        if desc:
            line += f"\n  _{desc}_"
        lines.append(line)

    await message.answer("\n".join(lines), parse_mode="Markdown")
