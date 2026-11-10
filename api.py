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


@app.post("/api/week")
async def get_week(body: Base):
    user_id = verify(body.init_data)
    days = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("""
                SELECT category, SUM(duration_minutes)
                FROM sessions
                WHERE user_id = ? AND date = ? AND end_time IS NOT NULL
                GROUP BY category
            """, (user_id, d))
            rows = await cur.fetchall()
        total = sum(r[1] for r in rows if r[1])
        cats = {r[0]: r[1] for r in rows if r[1]}
        label = (date.today() - timedelta(days=i)).strftime("%a")
        days.append({"date": d, "label": label, "total_minutes": total, "categories": cats})
    return {"days": days}


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
