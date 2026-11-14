# How the kiosk works (and how to explain it)

## The one-sentence version

The kiosk takes four camera frames, checks **is this a real person**, **who is it**,
and **are they allowed here now**, and answers ALLOW, STEP-UP or DENY in well under
2 seconds, using models that run on the kiosk itself so it keeps working offline.

## The picture

```
 Camera (browser page)
        |  4 frames, about 0.3 s
        v
 KIOSK SERVICE (runs on the laptop, port 8000)
   1. Find the face          YuNet
   2. Real or spoof?         MiniFASNetV2  -> liveness score 0..1
   3. Who is it?             SFace         -> match score 0..1
   4. Scheduled here, now?   signed copy of the campus schedule
   5. Decide                 policy.py     -> ALLOW / STEP-UP / DENY + reason
        |                                         |
        | audit record (no photo)                 | if STEP-UP: 6-digit
        v                                         v authenticator code
 local queue (SQLite)  -- when connected -->  CENTRAL SERVICE (port 9000 today, AWS later)
                                              owns the schedule + permanent audit log
```

## The five steps, in plain words

1. **Find the face.** If there is no face, two faces, or the face is too far away,
   the kiosk asks the person to try again.
2. **Real or spoof.** A small neural network looks at the face and its surroundings
   for signs of paper, screen glare and screen borders. It gives a score from 0 to 1.
3. **Who is it.** A second network turns the face into 128 numbers and compares them
   with the people enrolled. Only these numbers are stored, never photos.
4. **Schedule.** Being recognised is not enough. The schedule says which role may
   enter which zone on which days and hours.
5. **Decide.** One small function combines everything (table below).

## The decision table

| Situation | Decision |
|---|---|
| Liveness score clearly low (below 0.25) | DENY: spoof |
| Liveness score in the middle (0.25 to 0.80) | STEP-UP: random head turn, checked on the kiosk service. Fail twice = DENY |
| Face matches nobody | DENY: unknown person |
| Recognised but not scheduled for this zone and time | DENY |
| Identity score in the uncertain middle | STEP-UP: enter authenticator code |
| Within 15 minutes of the scheduled window | STEP-UP |
| No face / two faces / too far | STEP-UP: recapture |
| Live, matched, scheduled, online | ALLOW |

There are two step-up methods. **Head turn**: the kiosk picks left or right at random
at that moment and watches the nose move relative to the eyes. A photo cannot do
this, and a recorded video cannot know which way will be asked. **Authenticator
code**: a 6-digit code (same standard as Google Authenticator), used when identity or
the schedule is in doubt, and always when offline. Three wrong codes means DENY.

The fast check answers within 2 seconds every time. The head turn takes a few more
seconds, but only for the uncertain cases, which is what the brief asks for
("ask for an additional step: recapture, simple action, or OTP").

## What changes when the connection is lost

| Requirement from the brief | What the kiosk does |
|---|---|
| Continue using a safe local decision process | Same models, same policy function, all local |
| Avoid unsafe automatic access | Face alone never opens the door offline; thresholds are stricter; restricted zones are denied |
| Provide fallback verification | Authenticator code, which needs no network |
| Store only minimum temporary information | Queue holds id, time, zone, decision, scores. No photos, no names. |
| Synchronise when the connection returns | Queue is sent, the central service confirms each record, confirmed records are deleted locally. Sending twice is harmless. |

The cached schedule is signed and expires after 8 hours. Offline with an expired or
tampered copy means DENY.

## Why it is built this way (likely judge questions)

- **Why not a cloud liveness service?** It cannot answer when the connection is down,
  and a round trip plus a guided flow puts the 2-second limit at risk. Local models take
  about 0.1 s.
- **Where is AWS?** It is the central service: schedule, enrolment records and the
  permanent audit log. Today a local stand-in with the same three routes
  (`/health`, `/policy`, `/events`) plays that part.
- **How do you know it works?** Test mode. You label what is really in front of the
  camera, and the page reports false acceptance, false rejection and decision time per
  scenario. Only quote numbers from that table.

## Honest limits (say these before a judge finds them)

- The liveness model was trained on printed photos and screen replays. 3D masks are
  outside what it was trained on, so treat mask results as measured, not promised.
- Thresholds are starting values and need tuning on the demo laptop and lighting.
- Enrolment happens at the kiosk and does not yet check liveness.
- The stored face templates are not yet encrypted on disk.
