"""Kiosk service: serves the kiosk page and makes the access decision locally.

Run (from the backend folder):  uvicorn main:app --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

import light
import schedule
import store
import cv2
import numpy as np

from config import (BASE_DIR, CENTRAL_URL, EVAL_FRAMES, HEALTH_INTERVAL_S,
                    STEPUP_MAX_TRIES, STEPUP_TTL_S, THRESHOLDS)
from engine import FaceEngine, decode
from policy import ALLOW, DENY, MESSAGES, STEP_UP, Signals, check_turn, decide

app = FastAPI(title="HID liveness kiosk")
engine = FaceEngine()

state = {"online": False, "forced_offline": False, "central_events": None, "last_sync": None}
pending: dict[str, dict] = {}       # open step-up requests, kept in memory only

ATTACKS = ("print", "screen", "video", "mask")


# ---- link to the central service (runs in the background, never in a request) ----
def _link_loop() -> None:
    last_policy = 0.0
    while True:
        try:
            if state["forced_offline"]:
                raise ConnectionError("forced offline")
            r = httpx.get(f"{CENTRAL_URL}/health", timeout=1.0)
            r.raise_for_status()
            state["central_events"] = r.json().get("events")
            came_back = not state["online"]
            state["online"] = True
            if came_back or time.time() - last_policy > 60:
                p = httpx.get(f"{CENTRAL_URL}/policy", timeout=2.0).json()
                if schedule.sign(p["policy"]) == p["signature"]:
                    schedule.save_cache(p["policy"], p["signature"])
                    last_policy = time.time()
            batch = store.queued()
            if batch:                       # send what piled up, delete what was confirmed
                ok = httpx.post(f"{CENTRAL_URL}/events", json=batch, timeout=3.0).json()
                store.drop_events(ok.get("accepted", []))
                state["last_sync"] = time.time()
        except Exception:
            state["online"] = False
        time.sleep(HEALTH_INTERVAL_S)


threading.Thread(target=_link_loop, daemon=True).start()


async def _read_frames(frames: list[UploadFile]) -> list:
    imgs = [decode(await f.read()) for f in frames]
    imgs = [i for i in imgs if i is not None]
    if not imgs:
        raise HTTPException(400, "No readable images were sent.")
    return imgs


def _record(ev: dict, label: str) -> None:
    store.queue_event(ev)
    if label:
        store.log_eval(ev, label)


# ---- routes -----------------------------------------------------------------
@app.get("/api/status")
def status():
    pol, valid = schedule.load_cache()
    return {
        "online": state["online"], "forced_offline": state["forced_offline"],
        "policy_valid": valid, "policy_version": pol and pol["version"],
        "zones": (pol or schedule.DEFAULT_POLICY)["zones"],
        "queued": store.queue_len(), "central_events": state["central_events"],
        "last_sync": state["last_sync"], "users": len(store.load_users()),
        "thresholds": THRESHOLDS,
    }


@app.post("/api/debug/offline")
def force_offline(on: bool = Form(...)):
    """Demo switch: pretend the connection to the central service is lost."""
    state["forced_offline"] = on
    if on:
        state["online"] = False
    return {"forced_offline": on}


@app.post("/api/enroll")
async def enroll(name: str = Form(...), role: str = Form("student"),
                 frames: list[UploadFile] = File(...)):
    embs = []
    for img in await _read_frames(frames):
        a = engine.analyse([img])
        if a["faces"] == 1 and a["face_px"] >= THRESHOLDS["min_face_px"]:
            embs.append(a["embedding"])
    if len(embs) < 2:
        raise HTTPException(400, "Could not see one clear face. Move closer and try again.")
    u = store.add_user(name.strip(), role, embs)
    return {"id": u["id"], "name": u["name"], "role": u["role"], "templates": len(embs),
            "totp_secret": u["totp_secret"],
            "otpauth": f"otpauth://totp/HID-Kiosk:{u['name']}?secret={u['totp_secret']}&issuer=HID-Kiosk"}


@app.get("/api/users")
def users():
    return [{"id": u["id"], "name": u["name"], "role": u["role"]} for u in store.load_users()]


@app.delete("/api/users/{user_id}")
def remove_user(user_id: str):
    if not store.delete_user(user_id):
        raise HTTPException(404, "No such user.")
    return {"deleted": user_id}


@app.post("/api/track")
async def track(frame: UploadFile = File(...)):
    """Face box and landmark points for the live overlay on the page. Stores nothing."""
    img = decode(await frame.read())
    if img is None:
        return {"faces": 0}
    with engine._lock:
        faces = engine.detect(img)
    if len(faces) == 0:
        return {"faces": 0}
    f = [float(v) for v in faces[0]]
    return {"faces": len(faces), "w": img.shape[1], "h": img.shape[0], "box": f[:4],
            "points": [[f[i], f[i + 1]] for i in range(4, 14, 2)],   # eyes, nose, mouth corners
            "face_ratio": f[3] / img.shape[0]}


@app.post("/api/light/start")
def light_start():
    """Issue a random colour sequence for the screen to show (light challenge)."""
    return light.start()


@app.post("/api/authenticate")
async def authenticate(frames: list[UploadFile] = File(...), zone: str = Form("main_gate"),
                       capture_ms: float = Form(0), label: str = Form(""), at: str = Form(""),
                       light_id: str = Form(""), light_t: str = Form(""),
                       light_frames: list[UploadFile] = File([]), collect: str = Form("")):
    """label = ground truth for test mode; at = pretend time 'YYYY-MM-DDTHH:MM' (demo)."""
    t0 = time.perf_counter()
    imgs = await _read_frames(frames)
    t1 = time.perf_counter()
    a = engine.analyse(imgs)
    # Light challenge (trial): measured and reported, not used in the decision yet.
    lit, light_imgs, names = None, [], light.take(light_id) if light_id else None
    if names:
        light_imgs = [decode(await f.read()) for f in light_frames]
        times = json.loads(light_t)
        with engine._lock:
            cols = []
            for im in light_imgs:
                fs = engine.detect(im) if im is not None else []
                cols.append(light.face_colour(im, fs[0]) if len(fs) else None)
        lit = light.response(times, cols, names)
        lit["sequence"] = names
    t2 = time.perf_counter()

    online = state["online"]
    pol, valid = schedule.load_cache()
    user, score, sched = None, 0.0, "out"
    if a["faces"]:
        user, score = store.best_match(a["embedding"], store.load_users())
        if user and pol:
            now = datetime.fromisoformat(at) if at else datetime.now()
            sched = schedule.check(pol, user, zone, now)
    restricted = bool(pol and pol["zones"].get(zone, {}).get("restricted"))
    sig = Signals(faces=a["faces"], face_px=a.get("face_px", 0),
                  face_ratio=a.get("face_ratio", 0), live=a.get("live", 0),
                  live_mean=a.get("live_mean"),
                  live_lowest=min(a["live_models"]) if a.get("live_models") else None,
                  match=score, schedule=sched, online=online, policy_valid=valid,
                  zone_restricted=restricted)
    decision, reason, step = decide(sig, THRESHOLDS)
    known = user if score >= THRESHOLDS["match_low"] else None
    t3 = time.perf_counter()

    server_ms = (t3 - t0) * 1000
    ev = {"id": uuid.uuid4().hex, "ts": time.time(), "user_id": known and known["id"],
          "zone": zone, "decision": decision, "reason": reason, "live": a.get("live"),
          "match": score, "ms": capture_ms + server_ms, "online": online}
    out = {
        "decision": decision, "reason": reason, "message": MESSAGES[reason], "step": step,
        "name": known and known["name"], "role": known and known["role"],
        "live": a.get("live"), "live_min": a.get("live_min"), "match": score,
        "live_models": a.get("live_models"), "face_px": a.get("face_px"),
        "face_ratio": a.get("face_ratio"), "light": lit,
        "schedule": sched, "online": online, "event_id": ev["id"],
        "timing_ms": {"capture": capture_ms, "decode": (t1 - t0) * 1000,
                      "models": (t2 - t1) * 1000, "policy": (t3 - t2) * 1000,
                      "server_total": server_ms, "decision_total": capture_ms + server_ms},
    }
    if label:   # test mode only: keep the frames so thresholds can be tuned offline
        folder = EVAL_FRAMES / label
        folder.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(imgs):
            cv2.imwrite(str(folder / f"{ev['id']}_{i}.png"), img)
        if lit:     # light-challenge frames and timings, for tuning offline
            lf = EVAL_FRAMES / "_light" / label
            lf.mkdir(parents=True, exist_ok=True)
            for i, im in enumerate(light_imgs):
                if im is not None:
                    cv2.imwrite(str(lf / f"{ev['id']}_{i:02d}.jpg"), im)
            (lf / f"{ev['id']}.json").write_text(json.dumps(
                {"names": names, "times": times, "result": lit}))
    if collect:     # sample collection for tuning: record the scores, no step-up
        if label and a["faces"]:
            store.log_eval(ev, label)
        return out
    if step in ("totp", "action"):
        # keep the request open; /api/stepup or /api/challenge records the final result
        pending[ev["id"]] = {"ev": ev, "user": known, "label": label, "tries": 0,
                             "step": step, "direction": random.choice(["left", "right"]),
                             "moves_left": 2, "retried": False,
                             "expires": time.time() + STEPUP_TTL_S}
        out["session_id"] = ev["id"]
        if step == "action":
            out["direction"] = pending[ev["id"]]["direction"]
        if label:                       # unresolved step-up still counts in test results
            store.log_eval(ev, label)
    elif step != "recapture":
        _record(ev, label)
    return out


@app.post("/api/stepup")
def stepup(session_id: str = Form(...), code: str = Form(...)):
    p = pending.get(session_id)
    if not p or time.time() > p["expires"] or p["step"] != "totp":
        pending.pop(session_id, None)
        raise HTTPException(410, "Verification request expired. Start again.")
    p["tries"] += 1
    ok = store.totp_ok(p["user"]["totp_secret"], code)
    if not ok and p["tries"] < STEPUP_MAX_TRIES:
        return {"decision": STEP_UP, "reason": "WRONG_CODE", "step": "totp",
                "session_id": session_id,
                "message": f"Wrong code. {STEPUP_MAX_TRIES - p['tries']} attempt(s) left."}
    pending.pop(session_id, None)
    ev = dict(p["ev"], decision=ALLOW if ok else DENY,
              reason=p["ev"]["reason"] + ("+STEPUP_PASSED" if ok else "+STEPUP_FAILED"))
    _record(ev, p["label"])
    return {"decision": ev["decision"], "reason": ev["reason"], "step": None,
            "name": p["user"]["name"],
            "message": "Extra verification passed." if ok else "Extra verification failed."}


@app.post("/api/challenge")
async def challenge(session_id: str = Form(...), frames: list[UploadFile] = File(...)):
    """Head-turn check. The direction was picked at random when the request opened."""
    p = pending.get(session_id)
    if not p or time.time() > p["expires"] or p["step"] != "action":
        pending.pop(session_id, None)
        raise HTTPException(410, "Verification request expired. Start again.")
    imgs = await _read_frames(frames)
    p["tries"] += 1
    ok, why = check_turn(engine.yaw_track(imgs), p["direction"],
                         THRESHOLDS["turn_need"], THRESHOLDS["turn_wrong"])
    # the person turning must still be the person who was recognised
    a = engine.analyse(imgs[:2])
    same = a["faces"] == 1 and float(np.max(
        np.asarray(p["user"]["embeddings"], dtype=np.float32) @ a["embedding"])) >= THRESHOLDS["match_low"]
    if ok and not same:
        ok, why = False, "DIFFERENT_PERSON"
    if ok:
        p["moves_left"] -= 1
        if p["moves_left"] > 0:     # two correct random moves in a row are needed
            p["direction"] = random.choice(["left", "right"])
            return {"decision": STEP_UP, "reason": "TURN_OK", "step": "action",
                    "session_id": session_id, "direction": p["direction"],
                    "message": "Good. Face the camera again for move 2 of 2."}
    # Turning the wrong way is final. Anything else gets one retry in total.
    elif why != "WRONG_DIRECTION" and not p["retried"]:
        p["retried"] = True
        p["direction"] = random.choice(["left", "right"])
        return {"decision": STEP_UP, "reason": why, "step": "action", "session_id": session_id,
                "direction": p["direction"],
                "message": "Face the camera, keep still, then turn when asked. One more try."}
    pending.pop(session_id, None)
    ev = dict(p["ev"], decision=ALLOW if ok else DENY,
              reason=p["ev"]["reason"] + ("+TURN_PASSED" if ok else "+TURN_FAILED:" + why))
    _record(ev, p["label"])
    return {"decision": ev["decision"], "reason": ev["reason"], "step": None,
            "name": p["user"]["name"],
            "message": "Head turn confirmed: live person." if ok
            else "Head turn not confirmed. Treated as a spoof."}


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


@app.get("/api/eval/summary")
def eval_summary():
    """Measured results per test scenario, from attempts labelled in test mode."""
    rows = store.eval_rows()
    out = []
    for label in sorted({r["label"] for r in rows}):
        rs = [r for r in rows if r["label"] == label]
        n = len(rs)
        allowed = sum(r["decision"] == ALLOW for r in rs)
        denied = sum(r["decision"] == DENY for r in rs)
        ms = [r["ms"] for r in rs if r["ms"]]
        correct = allowed if label == "genuine" else n - allowed
        out.append({
            "scenario": label, "attempts": n, "allow": allowed, "deny": denied,
            "step_up": sum(r["decision"] == STEP_UP or "+" in r["reason"] for r in rs),
            "correct_rate": correct / n,
            # genuine: wrongly refused. everything else: wrongly let in.
            "error_name": "false rejection" if label == "genuine" else "false acceptance",
            "error_rate": (denied if label == "genuine" else allowed) / n,
            "spoof_flagged": sum(r["reason"].startswith("SPOOF") for r in rs),
            "live_avg": sum(r["live"] or 0 for r in rs) / n,
            "ms_p50": _pct(ms, 0.5), "ms_p95": _pct(ms, 0.95), "ms_max": max(ms) if ms else None,
            "within_2s": sum(m <= 2000 for m in ms) / len(ms) if ms else None,
        })
    return {"scenarios": out, "total": len(rows), "attack_labels": ATTACKS}


@app.delete("/api/eval")
def eval_clear():
    store.clear_eval()
    return {"cleared": True}


app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
