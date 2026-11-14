import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config import THRESHOLDS as T  # noqa: E402
from policy import ALLOW, DENY, STEP_UP, Signals, check_turn, decide  # noqa: E402
from schedule import DEFAULT_POLICY, check  # noqa: E402
from store import totp, totp_ok  # noqa: E402

GOOD = dict(faces=1, face_px=200, face_ratio=0.5, live=0.97, match=0.7, schedule="in")


def d(**kw):
    return decide(Signals(**{**GOOD, **kw}), T)[:2]


def test_allow():
    assert d() == (ALLOW, "OK")


def test_spoof_denied_even_if_identity_matches():
    assert d(live=0.1) == (DENY, "SPOOF_DETECTED")


def test_unknown_person_denied():
    assert d(match=0.2) == (DENY, "UNKNOWN_IDENTITY")


def test_low_confidence_steps_up():
    assert decide(Signals(**{**GOOD, "live": 0.35}), T) == (STEP_UP, "LIVENESS_UNSURE", "action")
    assert d(match=0.4) == (STEP_UP, "LOW_CONFIDENCE")


def test_no_face_or_two_faces_recapture():
    assert decide(Signals(faces=0), T) == (STEP_UP, "NO_FACE", "recapture")
    assert d(faces=2) == (STEP_UP, "MULTIPLE_FACES")


def test_schedule():
    assert d(schedule="out") == (DENY, "OUTSIDE_SCHEDULE")
    assert d(schedule="grace") == (STEP_UP, "SCHEDULE_GRACE")


def test_offline_never_allows_on_face_alone():
    assert d(online=False) == (STEP_UP, "OFFLINE_FALLBACK")
    assert d(online=False, policy_valid=False) == (DENY, "OFFLINE_NO_VALID_POLICY")
    assert d(online=False, zone_restricted=True) == (DENY, "OFFLINE_RESTRICTED_ZONE")
    assert decide(Signals(**{**GOOD, "online": False, "live": 0.5}), T) == (STEP_UP, "LIVENESS_UNSURE", "totp")


def test_schedule_windows():
    student = {"id": "x", "role": "student"}
    mon = lambda h, m=0: datetime(2026, 11, 16, h, m)  # a Monday
    assert check(DEFAULT_POLICY, student, "lab", mon(10)) == "in"
    assert check(DEFAULT_POLICY, student, "lab", mon(17, 10)) == "grace"
    assert check(DEFAULT_POLICY, student, "lab", mon(20)) == "out"
    assert check(DEFAULT_POLICY, student, "server_room", mon(10)) == "out"
    assert check(DEFAULT_POLICY, student, "lab", datetime(2026, 11, 15, 10)) == "out"  # Sunday


def test_totp_matches_rfc6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ascii 12345678901234567890
    assert totp(secret, 59) == "287082"
    assert totp_ok(secret, totp(secret))
    assert not totp_ok(secret, "000000")


def test_head_turn_challenge():
    ct = lambda ys, d: check_turn(ys, d, 0.18, 0.12)
    turn_right = [0.0, 0.01, -0.02, -0.1, -0.2, -0.3]
    assert ct(turn_right, "right") == (True, "TURN_OK")
    assert ct(turn_right, "left") == (False, "WRONG_DIRECTION")
    assert ct([0.0, 0.01, 0.02, -0.01, 0.03, 0.0], "left") == (False, "NO_TURN")   # a still photo
    assert ct([0.0, None, None, None, None, 0.3], "left") == (False, "FACE_LOST")
    assert ct([0.0, 0.0, 0.01, None, 0.1, 0.25], "left") == (True, "TURN_OK")
    assert ct([0.0, 0.15, 0.3, 0.1, -0.2, -0.3], "right") == (False, "NOT_STILL")   # already moving


def test_one_sure_model_is_a_veto():
    s = Signals(**{**GOOD, "live": 0.06, "live_mean": 0.53, "live_lowest": 0.06})   # the replayed video
    assert decide(s, T)[:2] == (DENY, "SPOOF_DETECTED")
