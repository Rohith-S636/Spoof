"""Re-score the frames saved in test mode and suggest thresholds.

Usage:  .venv/bin/python scripts/rescore.py
Reads data/eval_frames/<label>/<attempt>_<n>.png (written when a Test label is set).
"""
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from config import EVAL_FRAMES  # noqa: E402
from engine import FaceEngine  # noqa: E402

eng = FaceEngine()
by_label = defaultdict(list)
for folder in sorted(p for p in EVAL_FRAMES.glob("*") if p.is_dir()):
    attempts = defaultdict(list)
    for f in sorted(folder.glob("*.png")):
        attempts[f.stem.rsplit("_", 1)[0]].append(cv2.imread(str(f)))
    for frames in attempts.values():
        a = eng.analyse(frames)
        if a["faces"]:
            by_label[folder.name].append((a["live"], *a["live_models"], a["face_ratio"]))

print(f"{'label':10} {'n':>3} {'live min':>9} {'median':>7} {'max':>6}   per model (median)   face/frame")
for label, rows in by_label.items():
    r = np.array(rows)
    print(f"{label:10} {len(r):3d} {r[:,0].min():9.2f} {np.median(r[:,0]):7.2f} {r[:,0].max():6.2f}   "
          f"{np.round(np.median(r[:,1:-1], axis=0), 2)}   {np.median(r[:,-1]):.2f}")
gen = [x[0] for x in by_label.get("genuine", [])]
att = [x[0] for l, v in by_label.items() if l not in ("genuine", "impostor") for x in v]
if gen and att:
    print(f"\nHighest attack score: {max(att):.2f}   Lowest genuine score: {min(gen):.2f}")
    print("Clean gap: set live_pass just above the highest attack score." if max(att) < min(gen)
          else "Scores overlap: thresholds alone cannot separate them.")
