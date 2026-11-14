"""Stand-in for the central service (run on port 9000).

It owns the campus schedule and the permanent audit log. Stop this process to
simulate the kiosk losing its connection. On AWS this becomes API Gateway +
Lambda + DynamoDB with the same three routes.

Run:  uvicorn central:app --port 9000
"""
from __future__ import annotations

import sqlite3

from fastapi import FastAPI

from config import CENTRAL_DB
from schedule import DEFAULT_POLICY, sign

app = FastAPI(title="Central service (stand-in)")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(CENTRAL_DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS events(
        id TEXT PRIMARY KEY, ts REAL, user_id TEXT, zone TEXT, decision TEXT,
        reason TEXT, live REAL, match REAL, ms REAL, online INTEGER)""")
    return con


@app.get("/health")
def health():
    with _db() as con:
        return {"ok": True, "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0]}


@app.get("/policy")
def policy():
    return {"policy": DEFAULT_POLICY, "signature": sign(DEFAULT_POLICY)}


@app.post("/events")
def events(batch: list[dict]):
    """Idempotent: sending the same event id twice stores it once."""
    with _db() as con:
        for e in batch:
            con.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", (
                e["id"], e["ts"], e.get("user_id"), e["zone"], e["decision"], e["reason"],
                e.get("live"), e.get("match"), e.get("ms"), int(e.get("online", 1))))
    return {"accepted": [e["id"] for e in batch]}


@app.get("/events")
def list_events(limit: int = 50):
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]
