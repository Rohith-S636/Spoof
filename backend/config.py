"""All tunable settings in one place."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

YUNET = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE = MODEL_DIR / "face_recognition_sface_2021dec.onnx"
MINIFAS = MODEL_DIR / "MiniFASNetV2.onnx"
MINIFAS_SE = MODEL_DIR / "MiniFASNetV1SE.onnx"
TEXTURE_PAD = MODEL_DIR / "antispoof_texture_q.onnx"   # second, independently trained liveness model
EVAL_FRAMES = DATA_DIR / "eval_frames"   # test-mode frames, kept for tuning only

USERS_PATH = DATA_DIR / "users.json"
KIOSK_DB = DATA_DIR / "kiosk.db"
POLICY_CACHE = DATA_DIR / "policy_cache.json"
CENTRAL_DB = DATA_DIR / "central.db"

# Central service (local stand-in today, AWS later). Change with env var.
CENTRAL_URL = os.environ.get("CENTRAL_URL", "http://127.0.0.1:9000")
# Shared key used to sign the schedule so the kiosk can trust its cached copy.
POLICY_KEY = os.environ.get("POLICY_KEY", "dev-only-change-me").encode()

# ---- Decision thresholds (tune from the evaluation page) -------------------
THRESHOLDS = {
    # liveness = probability the face is real, averaged over the frames
    "live_pass": 0.80,      # at or above: treated as live
    "live_spoof": 0.25,     # models together below this -> DENY
    "live_veto": 0.12,      # ANY single liveness model below this -> DENY (veto)
    # between the two: ask for a random head turn (a photo or replay cannot follow it)
    "turn_need": 0.18,      # head-turn size needed to pass the challenge
    "turn_wrong": 0.12,     # this far the wrong way fails it
    # identity = cosine similarity to the best enrolled template
    "match_pass": 0.45,     # at or above: confident match
    "match_low": 0.363,     # below: unknown person -> DENY (OpenCV SFace default)
    # stricter values used while the kiosk is offline
    "offline_live_pass": 0.90,
    "offline_match_pass": 0.50,
    "min_face_px": 80,      # face narrower than this -> ask to move closer
    "max_face_ratio": 0.55, # face taller than this share of the frame -> move back
}

STEPUP_TTL_S = 90           # how long a step-up request stays open
STEPUP_MAX_TRIES = 3
HEALTH_INTERVAL_S = 3       # how often the kiosk checks the central service
