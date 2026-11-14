# Handoff: state of the work and exact next steps

For any person or coding agent picking this up. Read `docs/ARCHITECTURE.md` first
(5 minutes). The brief is in `docs/brief/` (two images).

## Constraints

- Hackathon: first review about 2 hours after 11:50 on 2026-11-14. Keep changes small.
- Team is one person plus a coding agent. Demo runs on a Mac laptop (M1 here, maybe an M4).
- Be careful with AWS sandbox credits. Nothing is deployed to AWS yet. The AWS CLI is
  not installed and the sandbox's allowed services are unknown.
- Branch: `hackathon/passive-pad-policy` (from `hackathon/active-liveness-prototype`).
  Nothing has been committed or pushed on this branch yet.

## Run it

```
scripts/get_models.sh      # once: downloads 3 ONNX models (40 MB) into models/
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt   # once
scripts/run.sh             # central stand-in on :9000, kiosk on :8000
open http://localhost:8000
.venv/bin/python -m pytest -q tests     # 9 tests, all pass
```

## File map

| File | What it does |
|---|---|
| `backend/main.py` | Kiosk API + serves the page. `/api/authenticate`, `/api/stepup`, `/api/enroll`, `/api/status`, `/api/eval/summary`, `/api/debug/offline`. Background thread checks the central service, refreshes the schedule, flushes the queue. |
| `backend/engine.py` | The three models. `analyse(frames)` returns liveness, embedding, face size. |
| `backend/policy.py` | `decide(Signals, thresholds)`: the whole decision logic, pure function. |
| `backend/schedule.py` | Schedule rules, signing, cached copy with expiry, `check()`. |
| `backend/store.py` | Enrolled users (`data/users.json`), SQLite queue + evaluation log, TOTP. |
| `backend/central.py` | Stand-in central service. Replace with AWS later. |
| `backend/config.py` | Paths and every threshold. |
| `frontend/index.html` | Single kiosk page, no external downloads (works offline). |
| `tests/test_policy.py` | Policy, schedule and TOTP tests. |
| `legacy/` | Old PCA/Eigenfaces app and the old blink/head-turn page. Not used. |

## What is verified, and what is not

Verified by running it:
- Models load and process 4 frames in about 80 ms on an M1.
- A face image taken from the poster is denied as a spoof (liveness 0.03) in about 0.4 s
  including a 0.3 s capture allowance.
- Forced offline: events queue locally; after reconnect they reach the central service
  and the local queue empties.
- 9 unit tests pass.

NOT yet verified (needs a person at the camera):
- That a real live face scores above `live_pass` (0.80) on this webcam and lighting.
- That an enrolled person matches above `match_pass` (0.45), and a stranger falls below
  `match_low` (0.363).
- The page in a browser (camera permission, enrol flow, step-up code entry).
- Real printed-photo, phone-screen and video attacks.

## Update after the first camera test (about 13:00)

First results (16 labelled attempts, one person, one phone):
- Attacks (phone photo and video): 0 of 7 allowed. 6 denied, 1 sent to step-up.
- Genuine: only 2 of 9 allowed, 3 step-up, 4 wrongly denied as spoof. Liveness for the
  same real face ranged from 0.16 to 0.98. This is the main problem.
- Identity is solid: 0.75 to 0.93 for the enrolled person.
- Decision time about 0.4 s, except three attempts of 2 to 3 s caused by slow capture.

Changes made in response (NOT yet re-tested with a camera):
- Second liveness model (MiniFASNetV1SE, 4x crop) averaged with the first. On the one
  poster image the two models disagree (0.03 vs 0.87), so do not assume this helps
  until `scripts/rescore.py` shows it on real frames.
- Camera now 640x480 (4:3) with an oval guide and a FACE_TOO_CLOSE recapture rule,
  because the liveness models need background around the face.
- Page keeps a rolling buffer of 6 frames, so Authenticate no longer waits on capture.
- Test mode saves frames to `data/eval_frames/<label>/`. `scripts/rescore.py` re-scores
  them per model and reports whether genuine and attack scores overlap.

Immediate next step: collect 10 genuine + 10 screen + 10 video with labels, run
`.venv/bin/python scripts/rescore.py`, then set `live_pass` / `live_spoof` in
`backend/config.py` (or switch the combination in `engine.analyse` to one model)
based on what it prints. If scores still overlap, do step 4 below.

## Update at about 13:30: second model removed, head-turn challenge added

- The second liveness model (MiniFASNetV1SE) is OFF. In the user's camera test it
  scored about 0.9 for phone screens as well as real faces, so every attack was
  allowed or stepped up. `engine.PAD_MODELS` now lists only MiniFASNetV2.
- New three-band liveness rule in `policy.decide`: below `live_spoof` (0.25) DENY,
  at or above `live_pass` (0.80) continue, in between `LIVENESS_UNSURE` with
  step `action`.
- Step `action` = random head turn. `/api/authenticate` picks left or right at random
  and returns `direction`; the page shows it, records 14 frames over 2.4 s and posts
  them to `/api/challenge`. The server measures the nose position relative to the
  eyes per frame (`engine.yaw_ratio`, `policy.check_turn`), also re-checks identity,
  allows one retry with a new random direction, then ALLOW or DENY.
- Offline, uncertain liveness still goes to the authenticator code (step `totp`).
- Frame capture now uses `toDataURL` instead of `toBlob` (toBlob was taking up to
  0.5 s per frame, giving 2 to 4 s decisions).
- Verified: 10 unit tests pass; a still image sent to the challenge gets NO_TURN,
  one retry, then DENY.
- NOT verified: a real person passing the head turn. If a correct turn is reported as
  `WRONG_DIRECTION`, the sign is inverted: swap `-1` and `1` in `policy.check_turn`.
  Also not verified: the faster capture in a real browser.
- Not built: the user's flash-reflection idea (flash the screen, measure the colour
  change on the face). It can catch phone screens but not printed photos, is
  unreliable in a brightly lit hall, and costs about 0.5 s of the 2 s budget.
  Consider it only if screens still pass after the head turn.

## Update at about 13:50: phone photo still passing, texture model and overlay added

- User report: a phone photo, with hand and phone visible, was ALLOWED (liveness
  0.9+ from MiniFASNetV2). No labelled frames were saved for those attempts, so the
  cause is not diagnosed. The first round (16:9 frames, face close) scored the same
  attacks 0.05 to 0.43, so the model may be reacting to framing more than to the spoof.
- Added a second, separately trained model: `models/antispoof_texture_q.onnx`
  (facenox/face-antispoof-onnx, Apache-2.0, 1.5x crop at 128 px, RGB, output
  [real, spoof] logits). `engine._live_texture`.
- Combination rule (chosen to fail safe, not yet measured): `live` = the LOWER of the
  two models, so both must say "real" (0.80) for a fast ALLOW. `live_mean` below 0.25
  is an outright DENY. Anything else goes to the random head turn.
- Not verified on any real face or real phone attack. The only check was the poster
  image: surroundings model 0.03, texture model 1.00, which sends it to the head turn.
- Page: bigger oval, live overlay (face box corners + lines joining eyes, nose, mouth)
  fed by the new `/api/track` route, and a position hint. Not checked in a browser.
- NEEDED NEXT: labelled attempts (Test label set) for genuine, screen and video, then
  `scripts/rescore.py`, which prints each model's scores per label. Decide from that
  which model to trust and where the thresholds go. Stop tuning without this data.

## Update at about 14:20: agreed redesign, light challenge on trial

**Read `docs/FLOW.md` first.** It is the flow the user agreed to (mermaid flow chart,
state diagram, and a table of what is built vs to do). The user asked to be consulted
before decision logic changes.

Latest labelled data (5 attempts only): genuine 0.47 / 0.61 (surroundings / texture),
phone photo 0.29 / 0.02, phone video 0.06 / 1.00. The video was ALLOWED because the
strong 0.06 vote was overridden by the head turn and the video showed a person turning.

Built now, measurement only (`backend/light.py`, `/api/light/start`, page option
"Light challenge (trial)"): the screen shows 4 random colours for 280 ms each, 20-odd
frames are recorded, and `light.response` reports `corr` (does the face colour follow
the sequence) and `amp` (how strongly). Shown in the result table, saved with labelled
attempts under `data/eval_frames/_light/<label>/`. It does NOT affect the decision.
Checked only on simulated data and a still image. Not tried on a real face.
With the light step, decision time is about 1.9 s, close to the 2 s limit. If it is
adopted, cut to 3 colours or fewer frames.

To do, in this order, once the user has light-trial numbers for real face vs phone:
1. Veto rule in `policy.decide`: any liveness model below about 0.15 is DENY; add the
   light result as a third voter if the trial shows a clear gap.
2. Two random head moves in a row instead of one (`/api/challenge`, `check_turn`),
   requiring a still start, so a looping video cannot pass.
3. Head moves first, then the code if another doubt remains.
4. Attack memory: after a SPOOF deny against an identity, require step-up for that
   identity for a few minutes.

## Update at about 14:25: veto, two head moves, collection button

User feedback: the colour flash must not run on every attempt and was too bright;
real faces now never reach the fast ALLOW (they score 0.3 to 0.6 on the lower model
while 0.80 is required), so everyone is sent to the head turn.

Done:
- Veto: any single liveness model below `live_veto` (0.12) is DENY. Unit-tested with
  the replayed-video scores.
- Head challenge is now two random moves in a row, must start still (`NOT_STILL`),
  wrong direction is final, one retry in total for other failures.
- Light trial is off by default and softened.
- "Collect 10 samples for the test label" button: 10 captures, scores + frames saved,
  no step-up (`collect=1` on `/api/authenticate`).

THE open problem: thresholds `live_pass` / `live_veto` are guesses from 5 attempts.
Get 10 samples each of genuine, screen, video (and print if possible) with the
collection button, run `scripts/rescore.py`, then set the two numbers so that
genuine attempts mostly clear `live_pass` and attacks do not. Do not change models
or combination rules again before that data exists.

Still to do after that: head moves then code when both doubts apply; attack memory;
decide on the light step from trial numbers; AWS central service; evidence screenshot.

## Update at about 14:50: thresholds set from collected samples

Samples (surroundings / texture, at face height as share of frame):
- genuine, n=7, all at 0.52 to 0.55: averages 0.50 to 0.75; lowest single model 0.28.
- phone screen, n=10: at 0.42 or closer (3 samples) averages 0.01 to 0.29; held
  further away (7 samples, 0.30 to 0.39) averages up to 0.70.
- video, n=1: 0.06 / 1.00.

Changes: `live` is now the AVERAGE of the two models (was the lower one);
`live_pass` 0.45; face must fill the oval (`min_face_ratio` 0.42, `max_face_ratio`
0.68) or the kiosk asks to move closer/back; veto stays at 0.12; offline pass 0.60.

Replaying the rule on the saved samples: genuine 7 of 7 ALLOW; screen 3 DENY and
7 "move closer" (never allowed); video 1 DENY.

Weak point: only 3 phone samples were close enough to be judged, and 1 video. The
0.45 line sits just under the lowest genuine average (0.50). Collect 10 more phone
photo and 10 video samples WITH THE PHONE FILLING THE OVAL, plus 10 more genuine,
then re-check with `scripts/rescore.py`. These changes are not committed or pushed.

## Update at about 15:30: phone VIDEO held close is NOT detected

- Verified by looking at the saved frames: 17 attempts labelled "video" (14:55 to
  14:56) are a real phone video held so close that the phone fills the camera view.
  16 of 17 were ALLOWED, liveness 0.61 to 0.98 (both models high). The passive models
  do not catch this. This is the main open security gap.
- The "screen" label is contaminated after 15:04: those ALLOWs are live people tested
  with the label left on. Do not use the screen numbers after 14:50 as attack results.
  The clean early set is 3 close phone photos denied, 7 further away asked to move closer.
- Two `TURN_FAILED:WRONG_DIRECTION` results at 15:01 and 15:06 are unexplained. If a
  real person turning correctly gets this, swap the sign in `policy.check_turn`.
- Page fix: `freshFrames` now uses only frames from the last 0.7 s, or grabs 4 new
  ones at once. Before this the page could wait 1.5 s and report 2 to 4 s decision
  times. Not yet checked in a browser.
- Deck: `docs/Commit-and-Conquer-HID-Kiosk.pptx` (6 slides, states the video gap).
- Options for the video gap, none built: (1) detect the phone itself (dark bezel bands
  beside the face; can be tuned on the saved frames), (2) make the light-reflection
  trial part of the decision after measuring it on real face vs phone, (3) require head
  moves on every attempt (breaks the 2 s direct ALLOW).

## Next steps, in order

1. **Camera check (10 min).** Open the page, enrol yourself, authenticate 5 times.
   Read the liveness and match scores in the result panel. If genuine attempts land in
   STEP-UP, adjust `THRESHOLDS` in `backend/config.py` and restart.
2. **Collect evidence (20 min).** Use the "Test label" dropdown. At least 10 attempts
   each for: genuine, impostor, print, screen, video. The results table on the page is
   the performance report for the judges. Screenshot it.
3. **Demo script.** genuine ALLOW, phone photo DENY, stranger DENY, set "Pretend time"
   to 23:30 for OUTSIDE_SCHEDULE, pick "Server room" as a student for DENY, press
   "Simulate connection loss" then authenticate for STEP-UP with code, restore and
   watch "Queued" drop to 0.
4. **If liveness is weak against screens:** add a second cue in `engine.py`
   (for example a moire/high-frequency check on the face crop) and combine it with
   the model score. Measure before and after with step 2.
5. **Active challenge as a second step-up option.** The old code is in
   `legacy/frontend/kiosk.html`. It has a bug (`blinkClosed` and `baseline` are never
   reset between attempts) and loads MediaPipe from a CDN, which breaks offline. Fix
   both before reusing it.
6. **AWS (only after 1 to 3 work).** Re-create `central.py`'s three routes as
   API Gateway + Lambda + DynamoDB, then start the kiosk with
   `CENTRAL_URL=https://...` and a real `POLICY_KEY`. Check the sandbox's allowed
   services first.
7. **Hardening if time allows:** liveness check during enrolment, encrypt
   `data/users.json`, enrolment owned by the central service instead of the kiosk.
