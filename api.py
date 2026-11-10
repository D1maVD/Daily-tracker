"""FastAPI backend for the Tracker Mini App."""
import calendar
import hashlib
import hmac
import json
import os
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, unquote

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db

BOT_TOKEN = os.environ["BOT_TOKEN"]

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class _ForceJson:
    """iOS Telegram WebKit hangs on any request with Content-Type: application/json.
    Client sends text/plain (no CORS preflight, no hang). This middleware rewrites
    the Content-Type to application/json so Pydantic can parse the JSON body."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            headers = [(k, v) for k, v in scope["headers"] if k.lower() != b"content-type"]
            headers.append((b"content-type", b"application/json"))
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)

app.add_middleware(_ForceJson)


def verify(init_data: str) -> int:
    if not init_data:
        raise HTTPException(status_code=401, detail="initData required")
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
        check_str = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash")
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, parsed.get("hash", "")):
            raise HTTPException(status_code=401, detail="Invalid initData")
        return json.loads(unquote(parsed["user"]))["id"]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="initData parse error")


class Base(BaseModel):
    init_data: str = ""

class StartBody(Base):
    category: str

class StopBody(Base):
    description: str = ""

class CategoryBody(Base):
    name: str

class DeleteCatBody(Base):
    cat_id: int

class DeleteSessionBody(Base):
    session_id: int

class StatsPeriodBody(Base):
    period: str = "week"

class DayBody(Base):
    date: str


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/api/today")
async def get_today(body: Base):
    user_id = verify(body.init_data)
    sessions = await db.get_today_sessions(user_id)
    active = await db.get_active_session(user_id)

    active_data = None
    if active:
        _, cat, start = active
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            start_dt = datetime.fromisoformat(start)
        elapsed = int((datetime.now(start_dt.tzinfo) - start_dt).total_seconds())
        active_data = {"category": cat, "start": start, "elapsed_seconds": elapsed}

    result = [
        {"id": sid, "category": cat, "start": start, "end": end, "description": desc, "duration": dur}
        for sid, cat, start, end, desc, dur in sessions
    ]
    total = sum(s[4] for s in sessions if s[4])
    return {"sessions": result, "active": active_data, "total_minutes": total}


@app.post("/api/stats")
async def get_stats(body: StatsPeriodBody):
    user_id = verify(body.init_data)
    today = date.today()

    async with aiosqlite.connect(db.DB_PATH) as conn:

        if body.period == "year":
            result = []
            for m in range(1, today.month + 1):
                key = f"{today.year}-{m:02d}"
                cur = await conn.execute("""
                    SELECT SUM(duration_minutes) FROM sessions
                    WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND end_time IS NOT NULL
                """, (user_id, key))
                row = await cur.fetchone()
                label = date(today.year, m, 1).strftime("%b")
                result.append({
                    "date": key, "label": label,
                    "total_minutes": row[0] or 0,
                    "is_current": m == today.month,
                })
            return {"bars": result, "period": "year"}

        if body.period == "month":
            # Дни текущего месяца с 1-го по сегодня (реальное кол-во дней)
            result = []
            for day in range(1, today.day + 1):
                dt = date(today.year, today.month, day)
                cur = await conn.execute("""
                    SELECT SUM(duration_minutes) FROM sessions
                    WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
                """, (user_id, dt.isoformat()))
                row = await cur.fetchone()
                label = str(day) if day == 1 or day % 5 == 0 or day == today.day else ""
                result.append({
                    "date": dt.isoformat(), "label": label,
                    "total_minutes": row[0] or 0,
                    "is_current": day == today.day,
                })
            return {"bars": result, "period": "month"}

        # Неделя — последние 7 дней
        result = []
        for i in range(6, -1, -1):
            dt = today - timedelta(days=i)
            cur = await conn.execute("""
                SELECT SUM(duration_minutes) FROM sessions
                WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
            """, (user_id, dt.isoformat()))
            row = await cur.fetchone()
            result.append({
                "date": dt.isoformat(), "label": dt.strftime("%a"),
                "total_minutes": row[0] or 0,
                "is_current": i == 0,
            })
        return {"bars": result, "period": "week"}


@app.post("/api/day")
async def get_day_sessions(body: DayBody):
    user_id = verify(body.init_data)
    # Для года приходит "YYYY-MM" — берём весь месяц
    is_month = len(body.date) == 7
    async with aiosqlite.connect(db.DB_PATH) as conn:
        if is_month:
            cur = await conn.execute("""
                SELECT id, category, start_time, end_time, description, duration_minutes
                FROM sessions
                WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND end_time IS NOT NULL
                ORDER BY start_time
            """, (user_id, body.date))
        else:
            cur = await conn.execute("""
                SELECT id, category, start_time, end_time, description, duration_minutes
                FROM sessions
                WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
                ORDER BY start_time
            """, (user_id, body.date))
        rows = await cur.fetchall()
    total = sum(r[5] for r in rows if r[5])
    return {
        "date": body.date,
        "total_minutes": total,
        "sessions": [
            {"id": r[0], "category": r[1], "start": r[2], "end": r[3], "description": r[4], "duration": r[5]}
            for r in rows
        ]
    }


@app.post("/api/categories/list")
async def list_categories(body: Base):
    user_id = verify(body.init_data)
    rows = await db.get_categories(user_id)
    return {"categories": [{"id": r[0], "name": r[1]} for r in rows]}


@app.post("/api/categories/add")
async def add_category(body: CategoryBody):
    user_id = verify(body.init_data)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    cat_id = await db.add_category(user_id, name)
    return {"ok": True, "id": cat_id, "name": name}


@app.post("/api/categories/delete")
async def delete_category(body: DeleteCatBody):
    user_id = verify(body.init_data)
    ok = await db.delete_category(user_id, body.cat_id)
    if not ok:
        raise HTTPException(status_code=404)
    return {"ok": True}


@app.post("/api/sessions/delete")
async def delete_session(body: DeleteSessionBody):
    user_id = verify(body.init_data)
    await db.delete_session(user_id, body.session_id)
    return {"ok": True}


@app.post("/api/start")
async def start(body: StartBody):
    user_id = verify(body.init_data)
    await db.start_session(user_id, body.category)
    return {"ok": True}


@app.post("/api/stop")
async def stop(body: StopBody):
    user_id = verify(body.init_data)
    desc = body.description.strip() or None
    duration = await db.stop_session(user_id, desc)
    return {"ok": True, "duration": duration}
