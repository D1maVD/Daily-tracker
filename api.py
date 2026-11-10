"""FastAPI backend for the Tracker Mini App."""
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify(init_data: str) -> int:
    if not init_data:
        raise HTTPException(status_code=401, detail="initData required")
    parsed = dict(parse_qsl(init_data, strict_parsing=False))
    check_str = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash")
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parsed.get("hash", "")):
        raise HTTPException(status_code=401, detail="Invalid initData")
    return json.loads(unquote(parsed["user"]))["id"]


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


class StatsPeriodBody(Base):
    period: str = "week"  # week | month | year

class DayBody(Base):
    date: str


@app.post("/api/stats")
async def get_stats(body: StatsPeriodBody):
    user_id = verify(body.init_data)
    today = date.today()
    async with aiosqlite.connect(db.DB_PATH) as conn:

        if body.period == "year":
            cur = await conn.execute("""
                SELECT strftime('%Y-%m', date) as m, SUM(duration_minutes)
                FROM sessions
                WHERE user_id = ? AND end_time IS NOT NULL
                  AND date >= date('now', '-11 months', 'start of month')
                GROUP BY m ORDER BY m
            """, (user_id,))
            rows = await cur.fetchall()
            months = {r[0]: r[1] for r in rows if r[1]}
            result = []
            for i in range(11, -1, -1):
                from dateutil.relativedelta import relativedelta
                d = (today.replace(day=1) - relativedelta(months=i))
                key = d.strftime("%Y-%m")
                result.append({
                    "date": key,
                    "label": d.strftime("%b"),
                    "total_minutes": months.get(key, 0),
                    "is_current": i == 0,
                })
            return {"bars": result, "period": "year"}

        days_count = 30 if body.period == "month" else 7
        result = []
        for i in range(days_count - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            cur = await conn.execute("""
                SELECT SUM(duration_minutes) FROM sessions
                WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
            """, (user_id, d))
            row = await cur.fetchone()
            total = row[0] or 0
            dt = today - timedelta(days=i)
            if body.period == "month":
                label = str(dt.day) if dt.day % 5 == 0 or i == 0 or i == days_count - 1 else ""
            else:
                label = dt.strftime("%a")
            result.append({"date": d, "label": label, "total_minutes": total, "is_current": i == 0})

    return {"bars": result, "period": body.period}


@app.post("/api/day")
async def get_day_sessions(body: DayBody):
    user_id = verify(body.init_data)
    async with aiosqlite.connect(db.DB_PATH) as conn:
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
