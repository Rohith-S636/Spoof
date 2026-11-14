# Decision flow

This is the agreed target flow. Status of each part is in the table at the bottom:
some of it is built, some is on trial, some is still to do.

## The idea in one line

Any strong sign of a spoof is a veto. ALLOW needs every check to agree. When the
checks are unsure, the kiosk asks a random question a recording cannot answer:
two head moves in directions chosen at that moment.

## Flow chart

```mermaid
flowchart TD
    A([Person presses Authenticate]) --> B["Capture, about 0.5 s<br/>6 camera frames"]
    B --> C{"One clear face,<br/>right distance?"}
    C -- No --> R["STEP-UP: recapture<br/>try again, move closer or back"]
    R --> A
    C -- Yes --> D["Four checks on the kiosk<br/>1 surroundings model<br/>2 skin-texture model<br/>3 who is it<br/>4 schedule"]
    D --> V{"VETO: any strong spoof sign?<br/>either liveness model very low"}
    V -- Yes --> X1["DENY: spoof<br/>remember the attack on this identity"]
    V -- No --> I{"Face matches<br/>an enrolled person?"}
    I -- No --> X2["DENY: unknown person"]
    I -- Yes --> S{"Scheduled for this<br/>zone and time?"}
    S -- No --> X3["DENY: outside schedule"]
    S -- "Yes, or within 15 min" --> O{"Offline with expired schedule,<br/>or offline at a restricted zone?"}
    O -- Yes --> X4["DENY: not safe offline"]
    O -- No --> L{"Liveness lukewarm?<br/>checks did not all say real"}
    L -- Yes --> H["STEP-UP: two random head moves"]
    H -- Fail --> X5["DENY: challenge failed"]
    H -- Pass --> Q
    L -- No --> Q{"Any other doubt?<br/>identity lukewarm, 15 min grace,<br/>offline, recent attack on this identity"}
    Q -- Yes --> T["STEP-UP: 6-digit code"]
    T -- "Wrong 3 times" --> X6["DENY: code failed"]
    T -- Correct --> OK
    Q -- No --> OK(["ALLOW"])

    OK --> Z[("Audit record, no photo:<br/>decision, reason, scores, colour code")]
    X1 --> Z
    X2 --> Z
    X3 --> Z
    X4 --> Z
    X5 --> Z
    X6 --> Z
    Z --> Y["Sent to the central service.<br/>If offline: queued, sent on reconnect"]
```

## States of one attempt

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Capturing: Authenticate pressed
    Capturing --> Recapture: no face, two faces, too far, too close
    Recapture --> Idle
    Capturing --> Deciding: frames sent to kiosk service
    Deciding --> Denied: veto, unknown, not scheduled, unsafe offline
    Deciding --> HeadMoves: liveness lukewarm
    Deciding --> CodeEntry: other doubt
    Deciding --> Allowed: every check agrees
    HeadMoves --> Denied: failed twice
    HeadMoves --> CodeEntry: passed, other doubt remains
    HeadMoves --> Allowed: passed, no other doubt
    CodeEntry --> Denied: wrong 3 times or 90 s timeout
    CodeEntry --> Allowed: correct code
    Allowed --> Idle: record written
    Denied --> Idle: record written
```

## The three outcomes

| Outcome | When | Time |
|---|---|---|
| ALLOW | All checks agree: live, known, scheduled, no doubt | within 2 s |
| DENY | Any veto, unknown person, not scheduled, unsafe offline, failed step-up | within 2 s (or after a failed step-up) |
| STEP-UP | The first answer is "not sure". Shown within 2 s, then the person does the extra step | 2 s to ask, a few more seconds to complete |

Three kinds of step-up, matching the brief ("recapture, simple action, or OTP"):
recapture, two random head moves, 6-digit code.

## How the checks vote

| Check | Strong spoof sign (veto) | Says "real" | In between |
|---|---|---|---|
| Surroundings model | below 0.12 | 0.80 or more | lukewarm |
| Skin-texture model | below 0.12 | 0.80 or more | lukewarm |

Numbers are starting values. They get set from labelled test attempts
(`scripts/rescore.py`), not by guessing.

## What is built and what is not

| Part | Status |
|---|---|
| Two liveness models, identity, schedule, offline queue and sync, code step-up | Built |
| Two random head moves | Built (14:25). Must start still; two correct random directions in a row; turning the wrong way is final. Not yet tried by a real person. A replay that guesses has about a 1 in 4 chance |
| Light response (random colour sequence) | On trial, OFF by default, colours softened. Measured and shown only. If adopted it belongs in step-up, not in every attempt |
| Veto rule (one strong spoof vote denies) | Built (14:25): any liveness model below 0.12 is DENY. The 0.12 is a first value from 5 attempts |
| Head moves first, then code if other doubt remains | To do. Today it is one or the other |
| Attack memory (step-up for an identity after a spoof attempt on it) | To do |
