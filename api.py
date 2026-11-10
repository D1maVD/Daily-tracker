"""FastAPI backend for the Tracker Mini App."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, unquote

import aiosqlite
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import db

BOT_TOKEN = os.environ["BOT_TOKEN"]

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _verified_user(b: dict) -> int:
    user_id = await _verified_user(b)
    if not await db.is_consented(user_id):
        raise HTTPException(status_code=403, detail="consent_required")
    return user_id


async def _body(request: Request) -> dict:
    """Read JSON body regardless of Content-Type. Works with text/plain, application/json, or none."""
    try:
        return json.loads(await request.body())
    except Exception:
        return {}


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
        auth_date = int(parsed.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            raise HTTPException(status_code=401, detail="initData expired")
        return json.loads(unquote(parsed["user"]))["id"]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="initData parse error")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/api/today")
async def get_today(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
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
    total = sum(s[5] for s in sessions if s[5])
    return {"sessions": result, "active": active_data, "total_minutes": total}


@app.post("/api/stats")
async def get_stats(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    period = b.get("period", "week")
    today = date.today()

    async with aiosqlite.connect(db.DB_PATH) as conn:
        if period == "year":
            result = []
            for m in range(1, today.month + 1):
                key = f"{today.year}-{m:02d}"
                cur = await conn.execute("""
                    SELECT SUM(duration_minutes) FROM sessions
                    WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND end_time IS NOT NULL
                """, (user_id, key))
                row = await cur.fetchone()
                label = date(today.year, m, 1).strftime("%b")
                result.append({"date": key, "label": label, "total_minutes": row[0] or 0, "is_current": m == today.month})
            return {"bars": result, "period": "year"}

        if period == "month":
            result = []
            for day in range(1, today.day + 1):
                dt = date(today.year, today.month, day)
                cur = await conn.execute("""
                    SELECT SUM(duration_minutes) FROM sessions
                    WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
                """, (user_id, dt.isoformat()))
                row = await cur.fetchone()
                label = str(day) if day == 1 or day % 5 == 0 or day == today.day else ""
                result.append({"date": dt.isoformat(), "label": label, "total_minutes": row[0] or 0, "is_current": day == today.day})
            return {"bars": result, "period": "month"}

        result = []
        for i in range(6, -1, -1):
            dt = today - timedelta(days=i)
            cur = await conn.execute("""
                SELECT SUM(duration_minutes) FROM sessions
                WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
            """, (user_id, dt.isoformat()))
            row = await cur.fetchone()
            result.append({"date": dt.isoformat(), "label": dt.strftime("%a"), "total_minutes": row[0] or 0, "is_current": i == 0})
        return {"bars": result, "period": "week"}


@app.post("/api/day")
async def get_day_sessions(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    day = b.get("date", "")
    is_month = len(day) == 7
    async with aiosqlite.connect(db.DB_PATH) as conn:
        if is_month:
            cur = await conn.execute("""
                SELECT id, category, start_time, end_time, description, duration_minutes
                FROM sessions WHERE user_id = ? AND strftime('%Y-%m', date) = ? AND end_time IS NOT NULL
                ORDER BY start_time
            """, (user_id, day))
        else:
            cur = await conn.execute("""
                SELECT id, category, start_time, end_time, description, duration_minutes
                FROM sessions WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
                ORDER BY start_time
            """, (user_id, day))
        rows = await cur.fetchall()
    total = sum(r[5] for r in rows if r[5])
    return {
        "date": day, "total_minutes": total,
        "sessions": [{"id": r[0], "category": r[1], "start": r[2], "end": r[3], "description": r[4], "duration": r[5]} for r in rows]
    }


@app.post("/api/categories/list")
async def list_categories(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    rows = await db.get_categories(user_id)
    return {"categories": [{"id": r[0], "name": r[1]} for r in rows]}


@app.post("/api/categories/add")
async def add_category(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    name = b.get("name", "").strip()[:50]
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    cat_id = await db.add_category(user_id, name)
    return {"ok": True, "id": cat_id, "name": name}


@app.post("/api/categories/delete")
async def delete_category(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    ok = await db.delete_category(user_id, int(b.get("cat_id", 0)))
    if not ok:
        raise HTTPException(status_code=404)
    return {"ok": True}


@app.post("/api/sessions/delete")
async def delete_session(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    await db.delete_session(user_id, int(b.get("session_id", 0)))
    return {"ok": True}


@app.post("/api/start")
async def start(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    category = b.get("category", "")
    if not category:
        raise HTTPException(status_code=400, detail="category required")
    await db.start_session(user_id, category)
    return {"ok": True}


@app.post("/api/stop")
async def stop(request: Request):
    b = await _body(request)
    user_id = await _verified_user(b)
    desc = b.get("description", "").strip() or None
    duration = await db.stop_session(user_id, desc)
    return {"ok": True, "duration": duration}
