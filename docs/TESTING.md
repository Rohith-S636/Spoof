# How to test the kiosk, step by step

You need: this laptop with its camera, a phone, and about 25 minutes.
Do the parts in order. Each step says what to do and what you should see.

> Page layout note (updated 15:45): the page now has collapsible panels at the bottom.
> **Enrol a person**, **Measured results** and **Test tools** open when clicked. The
> Test label, Pretend time, Light challenge and "Collect 10 samples" are inside
> **Test tools**. An amber chip at the top right shows whenever a test label or pretend
> time is active. Full numbers for an attempt are under **All metrics for this attempt**.

## Part 0: Start it (1 minute)

1. Open the Terminal in the project folder and run:
   ```
   scripts/run.sh
   ```
   Leave that window open. (If it says the address is already in use, it is
   already running. Carry on.)
2. Open **http://localhost:8000** in Chrome.
3. Chrome asks to use the camera. Click **Allow**.

You should see: yourself in the video box, and at the top right a green
**Central: online**.

## Part 1: Enrol yourself (1 minute)

Enrolling means teaching the kiosk your face.

1. Scroll to **Enrol a person**.
2. Type your name, leave the role as **student**.
3. Sit so your face fits inside the dashed oval, shoulders visible, face well lit.
4. Click **Enrol from camera** and turn your head slightly left and right for 2 seconds.

You should see: "Enrolled (your name) with 5 templates" and a **key** of 16 letters
and digits.

5. **Copy that key and paste it somewhere now.** It is shown only once. You need it
   later for the 6-digit code.

## Part 2: Check that it lets you in (2 minutes)

1. At the top, Zone = **Main gate**. Test label = **none**.
2. Click **Authenticate**. Look at the camera.

You should see: a green **ALLOW** and a table. Read three lines:

| Line | Good value |
|---|---|
| Decision time | under 2000 ms |
| Liveness score | 0.80 or more |
| Identity match score | 0.45 or more |

3. Click Authenticate 5 times and **write down the liveness and match scores each time**.

If you get STEP-UP or DENY instead, do not worry. Write the scores down and see
"If something goes wrong" at the bottom.

## Part 3: Try to fool it (5 minutes)

1. Take a selfie on your phone.
2. Hold the phone up to the laptop camera so your photo fills the same space your
   real face did. Keep your real face out of view.
3. Click **Authenticate**.

You should see: a red **DENY** with "Presentation attack suspected", and a low
liveness score (below 0.45).

4. Do the same with a **video** of your face playing on the phone.
5. If you can print a photo of your face, do the same with the paper.
6. Ask a friend who is **not enrolled** to click Authenticate.
   You should see: **DENY**, "Face does not match any enrolled person".

### The head-turn check (new)

If the kiosk is not sure you are live, the result box turns yellow and shows
**TURN YOUR HEAD LEFT** or **RIGHT**. Start facing the camera, then turn your head
slowly that way (your own left or right) and hold it. It records for about 2.5
seconds, then shows ALLOW or DENY. You get one retry.

- A real person should get ALLOW, "Head turn confirmed".
- A phone photo or video should get DENY, "Head turn not confirmed".
- If you turned the correct way and it says WRONG_DIRECTION, report that. It is a
  one-line fix.

## Part 4: Record the results for the judges (10 minutes)

This is the same as Parts 2 and 3, but you tell the kiosk the truth about what is in
front of the camera, so it can count how often it was right.

1. Set **Test label** to the real situation.
2. Click **Authenticate** about 10 times. Move a little between tries (angle, distance).
3. Change the label and repeat.

| Test label | What you put in front of the camera | Correct answer |
|---|---|---|
| genuine | you, live | ALLOW |
| impostor | a friend who is not enrolled | DENY |
| print | printed photo of you | DENY |
| screen | photo of you on a phone | DENY |
| video | video of you on a phone | DENY |

4. Look at **Measured results** at the bottom right. Each row shows tries, how many
   were allowed or denied, the error rate, and the decision time.
5. **Take a screenshot of that table.** It is your performance report.
6. Set Test label back to **none** when you finish.

Important: the label must be true. A wrong label makes the numbers wrong.
If you make a mistake, click **Clear results** and start Part 4 again.

## Part 5: Schedule check (2 minutes)

A recognised person is only allowed at the right place and time.

| Do this, then Authenticate | You should see |
|---|---|
| Zone = **Server room (restricted)** | DENY, "not scheduled for this place and time" (students cannot enter) |
| Zone = Main gate, **Pretend time** = today at 23:30 | DENY, same reason (gate closes at 22:00) |
| Zone = Main gate, Pretend time = today at 22:10 | STEP-UP (within 15 minutes of closing), asks for a code |

For the code: open a second Terminal window in the project folder and run this
with the key you saved in Part 1:
```
.venv/bin/python scripts/code.py YOURKEY
```
It prints 6 digits. Type them into the page and click **Verify code**.
You should see: **ALLOW**, "Extra verification passed". (The code changes every 30
seconds. For the real demo, add the key to Google Authenticator on your phone
instead: Add, Enter a setup key, paste the key.)

Clear the Pretend time box when you finish.

## Part 6: Connection loss (3 minutes)

1. Click **Simulate connection loss** (top right).
   You should see: **Central: OFFLINE** in yellow.
2. Zone = Main gate. Click **Authenticate**.
   You should see: **STEP-UP**, "Offline: face alone is not enough. Enter your code."
3. Get a code as in Part 5 and enter it. You should see **ALLOW**.
4. Look at the top: **Queued locally** is now 1 or more.
5. Click **Restore connection**. Wait about 6 seconds.
   You should see: **Central: online**, Queued locally back to **0**, and
   "Synced to central" gone up.
6. Also try while offline: Zone = Server room. You should see **DENY**.

## Part 7: Tuning check (1 minute, after Part 4)

While a Test label is set, the kiosk saves the camera frames in `data/eval_frames/`
on this laptop (test mode only). Run:
```
.venv/bin/python scripts/rescore.py
```
Send back what it prints. It shows the liveness scores for real faces and for
attacks side by side, which is what the thresholds are set from.

## What to send back

- The 5 liveness and match scores from Part 2.
- The liveness scores for the phone photo and video from Part 3.
- The screenshot from Part 4.
- Any step where what you saw did not match "You should see".

## If something goes wrong

| What you see | What to do |
|---|---|
| Page does not open | Run `scripts/run.sh` again and reload the page |
| "Camera failed" | Click the camera icon in Chrome's address bar, allow, reload |
| "No face found" / "Move closer" | Face the camera, come closer, add light on your face |
| Your real face gets STEP-UP or DENY "spoof" | Usually lighting. Face a window or lamp, no bright light behind you. If the score is still below 0.80, send the scores; the threshold needs adjusting |
| Your real face gets DENY "does not match" | Remove yourself from the list and enrol again in the same lighting |
| Phone photo gets ALLOW | Write down the liveness score and send it. This is the most important thing to report |
| "Verification request expired" | You took over 90 seconds. Click Authenticate again |
| Wrong code three times | It denies. Click Authenticate again and use a fresh code |
