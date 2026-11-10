import os
import aiosqlite
from datetime import datetime, date

DB_PATH = os.getenv("DB_PATH", "tracker.db")


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
        await db.commit()


async def start_session(user_id: int, category: str) -> int:
    now = datetime.now()
    async with aiosqlite.connect(DB_PATH) as db:
        # Закрываем незавершённые сессии если были
        await db.execute("""
            UPDATE sessions
            SET end_time = ?,
                duration_minutes = CAST((julianday(?) - julianday(start_time)) * 1440 AS INTEGER)
            WHERE user_id = ? AND end_time IS NULL
        """, (now.isoformat(), now.isoformat(), user_id))

        cursor = await db.execute("""
            INSERT INTO sessions (user_id, category, start_time, date)
            VALUES (?, ?, ?, ?)
        """, (user_id, category, now.isoformat(), date.today().isoformat()))
        await db.commit()
        return cursor.lastrowid


async def stop_session(user_id: int, description: str = None) -> int | None:
    now = datetime.now()
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
