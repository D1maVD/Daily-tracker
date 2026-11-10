import os
import aiosqlite
from datetime import datetime, date, timezone

def now_utc():
    return datetime.now(timezone.utc)

DB_PATH = os.getenv("DB_PATH", "tracker.db")

DEFAULT_CATEGORIES = [
    ("💻 Код", "code"),
    ("🤝 Митинг", "meeting"),
    ("📚 Обучение", "learning"),
    ("☕ Перерыв", "break"),
    ("🔧 Другое", "other"),
]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                description TEXT,
                date TEXT NOT NULL,
                duration_minutes INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_categories(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, name FROM categories
            WHERE user_id = ?
            ORDER BY sort_order, id
        """, (user_id,))
        rows = await cursor.fetchall()

    if not rows:
        # Первый запуск — засеять дефолтные категории
        await seed_default_categories(user_id)
        return await get_categories(user_id)

    return rows


async def seed_default_categories(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        for i, (name, _) in enumerate(DEFAULT_CATEGORIES):
            await db.execute("""
                INSERT INTO categories (user_id, name, sort_order) VALUES (?, ?, ?)
            """, (user_id, name, i))
        await db.commit()


async def add_category(user_id: int, name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO categories (user_id, name, sort_order)
            VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories WHERE user_id = ?))
        """, (user_id, name, user_id))
        await db.commit()
        return cursor.lastrowid


async def delete_category(user_id: int, category_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM categories WHERE id = ? AND user_id = ?
        """, (category_id, user_id))
        await db.commit()
        return cursor.rowcount > 0


async def start_session(user_id: int, category: str) -> int:
    now = now_utc()
    today_utc = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE sessions
            SET end_time = ?,
                duration_minutes = CAST((julianday(?) - julianday(start_time)) * 1440 AS INTEGER)
            WHERE user_id = ? AND end_time IS NULL
        """, (now.isoformat(), now.isoformat(), user_id))

        cursor = await db.execute("""
            INSERT INTO sessions (user_id, category, start_time, date)
            VALUES (?, ?, ?, ?)
        """, (user_id, category, now.isoformat(), today_utc))
        await db.commit()
        return cursor.lastrowid


async def stop_session(user_id: int, description: str = None) -> int | None:
    now = now_utc()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, start_time FROM sessions
            WHERE user_id = ? AND end_time IS NULL
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        session_id, start_time = row
        start_dt = datetime.fromisoformat(start_time)
        duration = max(1, int((now - start_dt).total_seconds() / 60))

        await db.execute("""
            UPDATE sessions
            SET end_time = ?, description = ?, duration_minutes = ?
            WHERE id = ?
        """, (now.isoformat(), description, duration, session_id))
        await db.commit()
        return duration


async def get_active_session(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, category, start_time FROM sessions
            WHERE user_id = ? AND end_time IS NULL
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        return await cursor.fetchone()


async def get_today_sessions(user_id: int) -> list:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT category, start_time, end_time, description, duration_minutes
            FROM sessions
            WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
            ORDER BY start_time
        """, (user_id, today))
        return await cursor.fetchall()
