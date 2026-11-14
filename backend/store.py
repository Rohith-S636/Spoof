"""Local storage: enrolled people, the offline event queue, evaluation log, TOTP."""
from __future__ import annotations

import base64
import hmac
import json
import os
import sqlite3
import struct
import threading
import time
import uuid

import numpy as np

from config import KIOSK_DB, USERS_PATH

_lock = threading.Lock()


# ---- enrolled people (face templates only, never photos) -------------------
def load_users() -> list[dict]:
    return json.loads(USERS_PATH.read_text()) if USERS_PATH.exists() else []


def save_users(users: list[dict]) -> None:
    USERS_PATH.write_text(json.dumps(users))


def add_user(name: str, role: str, embeddings: list[np.ndarray]) -> dict:
    with _lock:
        users = load_users()
        user = {
            "id": uuid.uuid4().hex[:8], "name": name, "role": role,
            "totp_secret": base64.b32encode(os.urandom(10)).decode(),
            "embeddings": [e.tolist() for e in embeddings],
        }
        users.append(user)
        save_users(users)
        return user


def delete_user(user_id: str) -> bool:
    with _lock:
        users = load_users()
        kept = [u for u in users if u["id"] != user_id]
        save_users(kept)
        return len(kept) != len(users)


def best_match(emb: np.ndarray, users: list[dict]) -> tuple[dict | None, float]:
    best, score = None, 0.0
    for u in users:
        s = float(np.max(np.asarray(u["embeddings"], dtype=np.float32) @ emb))
        if s > score:
            best, score = u, s
    return best, score


# ---- TOTP (RFC 6238): works in any authenticator app, needs no network ------
def totp(secret: str, at: float | None = None) -> str:
    counter = int((at or time.time()) // 30)
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), "sha1").digest()
    o = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_ok(secret: str, code: str) -> bool:
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + d * 30), code.strip()) for d in (-1, 0, 1))


# ---- sqlite: offline queue + evaluation log ---------------------------------
def _db() -> sqlite3.Connection:
    con = sqlite3.connect(KIOSK_DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS queue(
        id TEXT PRIMARY KEY, ts REAL, user_id TEXT, zone TEXT, decision TEXT,
        reason TEXT, live REAL, match REAL, ms REAL, online INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS eval(
        id TEXT PRIMARY KEY, ts REAL, label TEXT, decision TEXT, reason TEXT,
        live REAL, match REAL, ms REAL, online INTEGER)""")
    return con


def queue_event(ev: dict) -> None:
    """Audit record waiting to be sent to the central service. No images, no names."""
    with _lock, _db() as con:
        con.execute("INSERT OR IGNORE INTO queue VALUES(?,?,?,?,?,?,?,?,?,?)", (
            ev["id"], ev["ts"], ev.get("user_id"), ev["zone"], ev["decision"], ev["reason"],
            ev.get("live"), ev.get("match"), ev.get("ms"), int(ev["online"])))


def queued(limit: int = 200) -> list[dict]:
    with _lock, _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM queue ORDER BY ts LIMIT ?", (limit,))]


def queue_len() -> int:
    with _lock, _db() as con:
        return con.execute("SELECT COUNT(*) FROM queue").fetchone()[0]


def drop_events(ids: list[str]) -> None:
    """Delete records once the central service has confirmed them."""
    with _lock, _db() as con:
        con.executemany("DELETE FROM queue WHERE id=?", [(i,) for i in ids])


def log_eval(ev: dict, label: str) -> None:
    with _lock, _db() as con:
        con.execute("INSERT OR REPLACE INTO eval VALUES(?,?,?,?,?,?,?,?,?)", (
            ev["id"], ev["ts"], label, ev["decision"], ev["reason"],
            ev.get("live"), ev.get("match"), ev.get("ms"), int(ev["online"])))


def eval_rows() -> list[dict]:
    with _lock, _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM eval ORDER BY ts")]


def clear_eval() -> None:
    with _lock, _db() as con:
        con.execute("DELETE FROM eval")
