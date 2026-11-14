# How the kiosk works (and how to explain it)

## The one-sentence version

The kiosk takes six camera frames and answers three questions on the laptop itself:
**is this a real person, who is it, and are they allowed here now?** It replies
ALLOW, STEP-UP or DENY in well under 2 seconds, and keeps working without a network.

The flow chart is in [FLOW.md](FLOW.md).

## The picture

```
 Camera (browser page)
        |  6 frames, about 0.5 s
        v
 KIOSK SERVICE (on the laptop, port 8000)
   1. Find the face            YuNet
   2. Real or spoof?           two liveness models, averaged, with a veto
   3. Who is it?               SFace
   4. Scheduled here, now?     signed copy of the campus schedule
   5. Decide                   one policy function -> ALLOW / STEP-UP / DENY + reason
        |                                   |
        | audit record (no photo)           | if STEP-UP: two random head moves,
        v                                   v or a 6-digit authenticator code
 local queue (SQLite)  -- when connected -->  CENTRAL SERVICE (port 9000 today, AWS later)
                                              owns the schedule + permanent audit log
```

## The models we use

All four are small, open-source models that run on the laptop's processor. Nothing
is sent to the cloud, and we did not train any of them ourselves.

| Job | Model | What it gives us |
|---|---|---|
| Find the face | **YuNet** (OpenCV model zoo) | The face box and 5 points: both eyes, nose tip, both mouth corners |
| Liveness, view 1: surroundings | **MiniFASNetV2** (Minivision "Silent Face Anti-Spoofing") | A score 0 to 1. It looks at the face plus the area around it (2.7 times the face box), where phone edges, paper borders and screen glare show up |
| Liveness, view 2: skin texture | **MiniFAS texture model** (facenox "face-antispoof-onnx", trained on the CelebA-Spoof dataset) | A score 0 to 1. It looks closely at the face itself (1.5 times the face box) for the texture of real skin versus a screen or print |
| Who is it | **SFace** (OpenCV model zoo) | 128 numbers that describe the face. Two faces are compared by how similar their numbers are |

Why two liveness models: each one alone was fooled in our tests. The surroundings
model once scored a close phone photo 0.58, and the texture model scored a phone
video 1.00. They are fooled by different things, so together they cover each other.

## How we detect a spoof, step by step

1. **Position.** The face must fill the oval on screen (42% to 68% of the frame
   height). Too far or too close and the kiosk asks the person to move, and makes no
   decision. We found a phone held far away scores much higher than one held close,
   so a fixed distance is part of the defence.
2. **Six frames, two models.** Each liveness model scores every frame. We average
   each model over the frames, then average the two models. That average is the
   **liveness score**.
3. **Veto.** If either model alone is sure it is a spoof (below 0.12), the answer is
   DENY, whatever the other model says.
4. **Three bands.**

   | Liveness score | Meaning | What happens |
   |---|---|---|
   | below 0.25 | Spoof | DENY |
   | 0.25 to 0.45 | Not sure | STEP-UP: two random head moves |
   | 0.45 or more | Live | Continue to identity and schedule |

5. **Head moves when unsure.** The kiosk picks left or right at random, twice. The
   person must be still, then turn the right way each time. The service measures how
   far the nose moves away from the midpoint of the eyes. A photo cannot do this, and
   a recorded video cannot know which directions will be asked. Turning the wrong way
   is an immediate DENY.

The score is not a percentage of "how real". What matters is which side of the
pass line it falls on.

## How we check who it is

- **Enrolment:** five shots of the person are turned into five sets of 128 numbers
  and stored. Photos are never stored.
- **At the door:** the live face is compared with every enrolled person and the best
  match wins.

| Match score | Meaning | What happens |
|---|---|---|
| below 0.36 | Nobody we know | DENY |
| 0.36 to 0.45 | Probably, not surely | STEP-UP: 6-digit code |
| 0.45 or more | Confident match | Continue to schedule |

In our tests the enrolled person scored 0.76 to 0.90 and strangers 0.20 to 0.25.

## Schedule

Being recognised is not enough. The schedule says which role may enter which zone on
which days and hours. In the window: continue. Within 15 minutes of it: STEP-UP with
the code. Outside it: DENY.

## The three outcomes

| Outcome | When |
|---|---|
| ALLOW | Live, known, scheduled, and nothing in doubt |
| DENY | Spoof (band or veto), unknown person, outside schedule, unsafe offline case, or a failed step-up |
| STEP-UP | The first answer is "not sure". Three kinds: recapture, two random head moves, 6-digit code |

The first answer always comes within 2 seconds. A step-up takes a few more seconds
because a person has to act.

## What changes when the connection is lost

| Requirement from the brief | What the kiosk does |
|---|---|
| Continue using a safe local decision process | Same models and same policy function, all on the laptop |
| Avoid unsafe automatic access | Face alone never opens the door offline. Pass lines are stricter, and restricted zones are denied |
| Provide fallback verification | The authenticator code, which needs no network |
| Store only minimum temporary information | The queue holds an id, time, zone, decision and scores. No photos, no names |
| Synchronise when the connection returns | The queue is sent, the central service confirms each record, confirmed records are deleted. Sending twice is harmless |

The local copy of the schedule is signed and expires after 8 hours. Offline with an
expired or altered copy means DENY.

## Speed

| Step | Time |
|---|---|
| Camera frames | about 0.5 s (kept ready before the button is pressed) |
| All four models on six frames | about 0.1 to 0.2 s |
| Whole decision | about 0.4 to 0.65 s in our runs |

## What we have measured so far

From labelled test attempts on the demo laptop:

| Scenario | Samples | Result with the current rules |
|---|---|---|
| Enrolled live person | 7 | 7 direct ALLOW |
| Phone photo, close enough to judge | 3 | 3 DENY |
| Phone photo, held further away | 7 | 7 asked to move closer (never allowed) |
| Phone video | 1 | DENY (veto) |

These are small numbers. Quote them as "early results on N samples", not as an
accuracy figure.

## Likely judge questions

- **Why not a cloud liveness service?** It cannot answer when the connection is
  down, and a network round trip puts the 2-second limit at risk.
- **Where is AWS?** It is the central service: the schedule and the permanent audit
  log. Today a local stand-in with the same three routes plays that part.
- **Did you train a model?** No. We combine existing open-source models and set the
  pass lines from our own labelled test attempts.
- **What stops a video replay?** The veto, and for unsure cases the two random head
  moves.

## Honest limits

- The pass lines come from a small number of samples on one laptop and one phone.
- The two-move head check is built and unit-tested but has had little real use.
- Printed photos and 3D masks have not been tested yet. Masks are outside what
  these liveness models were trained on.
- A colour-flash check (screen shows random colours, the face should reflect them)
  exists as an optional trial. It is off and does not affect decisions.
- Enrolment happens at the kiosk and does not check liveness. Stored face numbers
  are not encrypted on disk.
