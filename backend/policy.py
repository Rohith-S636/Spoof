"""The decision engine: one pure function, no I/O, easy to test and explain.

Inputs: what the models saw + the schedule answer + whether we are online.
Output: ALLOW, REQUEST_VERIFICATION (step-up) or DENY, with a reason code.
"""
from __future__ import annotations

from dataclasses import dataclass

ALLOW, STEP_UP, DENY = "ALLOW", "REQUEST_VERIFICATION", "DENY"

MESSAGES = {
    "NO_FACE": "No face found. Look at the camera and try again.",
    "MULTIPLE_FACES": "More than one face in view. One person at a time.",
    "FACE_TOO_SMALL": "Move closer so your face fills the oval.",
    "FACE_TOO_CLOSE": "Move back a little so your whole head and shoulders show.",
    "SPOOF_DETECTED": "Presentation attack suspected (photo, screen or mask).",
    "UNKNOWN_IDENTITY": "Face does not match any enrolled person.",
    "OUTSIDE_SCHEDULE": "Recognised, but not scheduled for this place and time.",
    "OFFLINE_NO_VALID_POLICY": "Offline and the cached schedule is missing or expired.",
    "OFFLINE_RESTRICTED_ZONE": "Offline: restricted zones need the central service.",
    "LOW_CONFIDENCE": "Not confident enough. Extra verification needed.",
    "LIVENESS_UNSURE": "Not sure this is a live person. Follow the head-turn instruction.",
    "SCHEDULE_GRACE": "Just outside the scheduled time. Extra verification needed.",
    "OFFLINE_FALLBACK": "Offline: face alone is not enough. Enter your code.",
    "OK": "Live person, identity verified, access scheduled.",
}


@dataclass
class Signals:
    faces: int                  # 0, 1, or 2 (2 = more than one)
    face_px: float = 0.0
    face_ratio: float = 0.0     # face height as a share of the frame height
    live: float = 0.0           # 0..1, the more doubtful of the liveness models
    live_mean: float | None = None   # average of the models (None = same as live)
    live_lowest: float | None = None # lowest single model score (None = same as live)
    match: float = 0.0          # 0..1 cosine similarity to best enrolled person
    schedule: str = "out"       # "in" | "grace" | "out"
    online: bool = True
    policy_valid: bool = True   # schedule copy is signed and not expired
    zone_restricted: bool = False


def decide(s: Signals, t: dict) -> tuple[str, str, str | None]:
    """Return (decision, reason_code, step). step is 'recapture', 'totp' or None."""
    # 1. Can we even see one clear face?
    if s.faces == 0:
        return STEP_UP, "NO_FACE", "recapture"
    if s.faces > 1:
        return STEP_UP, "MULTIPLE_FACES", "recapture"
    if s.face_px < t["min_face_px"] or s.face_ratio < t["min_face_ratio"]:
        return STEP_UP, "FACE_TOO_SMALL", "recapture"
    if s.face_ratio > t["max_face_ratio"]:
        return STEP_UP, "FACE_TOO_CLOSE", "recapture"

    live_pass = t["live_pass"] if s.online else t["offline_live_pass"]
    match_pass = t["match_pass"] if s.online else t["offline_match_pass"]

    # 2. Hard failures -> DENY
    # Deny outright only when the models together say spoof. If they disagree,
    # the head-turn check below decides.
    # Veto: one model being sure it is a spoof is enough. A challenge must never
    # be able to override that (a replayed video passed that way on 14 Nov).
    if (s.live if s.live_lowest is None else s.live_lowest) < t["live_veto"]:
        return DENY, "SPOOF_DETECTED", None
    if (s.live if s.live_mean is None else s.live_mean) < t["live_spoof"]:
        return DENY, "SPOOF_DETECTED", None
    if s.match < t["match_low"]:
        return DENY, "UNKNOWN_IDENTITY", None
    if not s.online and not s.policy_valid:
        return DENY, "OFFLINE_NO_VALID_POLICY", None
    if s.schedule == "out":
        return DENY, "OUTSIDE_SCHEDULE", None
    if not s.online and s.zone_restricted:
        return DENY, "OFFLINE_RESTRICTED_ZONE", None

    # 3. Uncertain -> ask for a second factor
    if s.match < match_pass:
        return STEP_UP, "LOW_CONFIDENCE", "totp"
    if s.live < live_pass:
        # offline needs the code anyway; online a random head turn settles liveness
        return STEP_UP, "LIVENESS_UNSURE", "action" if s.online else "totp"
    if s.schedule == "grace":
        return STEP_UP, "SCHEDULE_GRACE", "totp"
    if not s.online:
        return STEP_UP, "OFFLINE_FALLBACK", "totp"

    # 4. Everything is confident
    return ALLOW, "OK", None


def check_turn(yaws: list, direction: str, need: float, wrong: float) -> tuple[bool, str]:
    """Did the head turn the requested way? yaws = one value per frame (None = no face).

    direction is the person's own 'left' or 'right'. The first two frames set the
    starting pose; after that the nose must move the requested way by `need`
    without first moving the other way by `wrong`.
    """
    seen = [y for y in yaws if y is not None]
    if len(seen) < max(4, len(yaws) // 2):
        return False, "FACE_LOST"
    # The head must be still at the start. A video of someone already turning
    # back and forth fails here.
    if max(seen[:3]) - min(seen[:3]) > 0.08:
        return False, "NOT_STILL"
    base = (seen[0] + seen[1]) / 2
    sign = -1 if direction == "right" else 1
    for y in seen[2:]:
        moved = (y - base) * sign
        if moved <= -wrong:
            return False, "WRONG_DIRECTION"
        if moved >= need:
            return True, "TURN_OK"
    return False, "NO_TURN"
