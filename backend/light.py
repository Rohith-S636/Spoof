"""Light challenge: the screen shows a random colour sequence and we measure
whether the face reflects those colours in the same order.

A real face is lit by the screen, so its colour follows the sequence. A face on a
phone screen makes its own light and a recording cannot know a sequence chosen
just now. TRIAL: measured and reported, not yet used in the decision.
"""
from __future__ import annotations

import random
import time
import uuid

import numpy as np

# Soft colours (not fully saturated) as (R, G, B).
COLOURS = {"red": (235, 130, 130), "green": (130, 225, 130), "blue": (130, 150, 240)}   # softened
STEPS = 4            # colours per challenge
STEP_MS = 280        # each colour stays this long (about 1.1 s in total)

_open: dict[str, dict] = {}     # challenges issued and not yet used


def start() -> dict:
    """Issue a new random sequence. No colour repeats twice in a row."""
    names = [random.choice(list(COLOURS))]
    while len(names) < STEPS:
        names.append(random.choice([c for c in COLOURS if c != names[-1]]))
    cid = uuid.uuid4().hex
    for k in [k for k, v in _open.items() if time.time() - v["at"] > 60]:
        _open.pop(k)
    _open[cid] = {"names": names, "at": time.time()}
    return {"id": cid, "step_ms": STEP_MS, "colours": [list(COLOURS[n]) for n in names],
            "names": names}


def take(cid: str) -> list[str] | None:
    """Each sequence can be answered once."""
    c = _open.pop(cid, None)
    return c["names"] if c else None


def face_colour(img: np.ndarray, face: np.ndarray) -> list[float]:
    """Average (R, G, B) of the middle of the face box."""
    x, y, w, h = [float(v) for v in face[:4]]
    x1, x2 = int(max(0, x + 0.2 * w)), int(x + 0.8 * w)
    y1, y2 = int(max(0, y + 0.15 * h)), int(y + 0.85 * h)
    patch = img[y1:y2, x1:x2]
    if patch.size == 0:
        return [0.0, 0.0, 0.0]
    b, g, r = patch.reshape(-1, 3).mean(axis=0)
    return [float(r), float(g), float(b)]


def response(times_ms: list[float], rgbs: list, names: list[str], step_ms: float = STEP_MS) -> dict:
    """How well the face colour over time follows the colour sequence.

    corr: -1..1, close to 1 = the face followed the sequence.
    amp:  size of the colour change on the face (share of total brightness).
    lag:  delay between the screen changing and the camera seeing it.
    """
    pts = [(t, c) for t, c in zip(times_ms, rgbs) if c is not None and sum(c) > 1]
    if len(pts) < 8:
        return {"corr": None, "amp": None, "lag_ms": None, "frames": len(pts)}
    t = np.array([p[0] for p in pts], dtype=np.float64)
    obs = np.array([p[1] for p in pts], dtype=np.float64)
    obs = obs / obs.sum(axis=1, keepdims=True)          # colour balance, ignores brightness
    want = np.array([COLOURS[n] for n in names], dtype=np.float64)
    want = want / want.sum(axis=1, keepdims=True)
    best = (-2.0, 0)
    for lag in range(0, 401, 20):                       # display + camera delay is unknown
        idx = np.floor((t - lag) / step_ms).astype(int)
        ok = (idx >= 0) & (idx < len(names))
        if ok.sum() < 8:
            continue
        cs = []
        for ch in range(3):
            a, b = obs[ok, ch], want[idx[ok], ch]
            if a.std() > 1e-9 and b.std() > 1e-9:
                cs.append(float(np.corrcoef(a, b)[0, 1]))
        if cs and np.mean(cs) > best[0]:
            best = (float(np.mean(cs)), lag)
    amp = float(np.max(np.percentile(obs, 95, axis=0) - np.percentile(obs, 5, axis=0)))
    return {"corr": None if best[0] < -1 else round(best[0], 3), "amp": round(amp, 4),
            "lag_ms": best[1], "frames": len(pts)}
