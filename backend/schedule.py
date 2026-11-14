"""Campus schedule: who may enter which zone, on which days and hours.

The central service owns the schedule and signs it. The kiosk keeps a signed
copy with an expiry so it can still answer while offline.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

from config import POLICY_CACHE, POLICY_KEY

DEFAULT_POLICY = {
    "version": 1,
    "ttl_s": 8 * 3600,          # a cached copy is trusted for 8 hours
    "grace_min": 15,            # this close to the window -> step-up, not deny
    "zones": {
        "main_gate": {"label": "Main gate", "restricted": False},
        "lab": {"label": "Computer lab", "restricted": False},
        "server_room": {"label": "Server room", "restricted": True},
    },
    # days: 0 = Monday ... 6 = Sunday
    "rules": [
        {"role": "student", "zone": "main_gate", "days": [0, 1, 2, 3, 4, 5, 6], "start": "06:00", "end": "22:00"},
        {"role": "student", "zone": "lab", "days": [0, 1, 2, 3, 4, 5], "start": "09:00", "end": "17:00"},
        {"role": "staff", "zone": "main_gate", "days": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"},
        {"role": "staff", "zone": "lab", "days": [0, 1, 2, 3, 4, 5, 6], "start": "07:00", "end": "21:00"},
        {"role": "staff", "zone": "server_room", "days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00"},
    ],
}


def sign(policy: dict) -> str:
    body = json.dumps(policy, sort_keys=True).encode()
    return hmac.new(POLICY_KEY, body, hashlib.sha256).hexdigest()


def save_cache(policy: dict, signature: str) -> None:
    POLICY_CACHE.write_text(json.dumps(
        {"policy": policy, "signature": signature, "fetched_at": time.time()}))


def load_cache() -> tuple[dict | None, bool]:
    """Return (policy, valid). valid = signature is correct and copy has not expired."""
    if not POLICY_CACHE.exists():
        return None, False
    try:
        c = json.loads(POLICY_CACHE.read_text())
        ok = hmac.compare_digest(sign(c["policy"]), c["signature"])
        fresh = time.time() - c["fetched_at"] < c["policy"]["ttl_s"]
        return c["policy"], ok and fresh
    except (ValueError, KeyError):
        return None, False


def check(policy: dict | None, user: dict, zone: str, now: datetime) -> str:
    """'in' = scheduled now, 'grace' = within grace minutes of a window, 'out' = no."""
    if not policy:
        return "out"
    grace = timedelta(minutes=policy.get("grace_min", 0))
    best = "out"
    for r in policy["rules"]:
        if r["zone"] != zone:
            continue
        if r.get("role") != user.get("role") and r.get("user_id") != user.get("id"):
            continue
        if now.weekday() not in r["days"]:
            continue
        start = datetime.combine(now.date(), datetime.strptime(r["start"], "%H:%M").time())
        end = datetime.combine(now.date(), datetime.strptime(r["end"], "%H:%M").time())
        if start <= now <= end:
            return "in"
        if start - grace <= now <= end + grace:
            best = "grace"
    return best
