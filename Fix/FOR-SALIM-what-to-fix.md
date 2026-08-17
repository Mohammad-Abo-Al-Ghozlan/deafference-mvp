# Deafference — what to change in the landmark export

**To:** Mohammad Salim
**From:** animation / retargeting side
**Subject:** contract v3 → v4. The retargeting is finished; the avatar is now limited by the data.
**Attached:** `check-export.py` (self-check script), `coverage-per-word.csv` (per-word data)

---

## Contents

1. [TL;DR — four asks](#1-tldr)
2. [Where the pipeline stands, measured](#2-where-the-pipeline-stands)
3. [ASK 1 — track the hand that MOVES *(critical)*](#3-ask-1--track-the-hand-that-moves)
4. [ASK 2 — ship native clip duration](#4-ask-2--ship-native-clip-duration)
5. [ASK 3 — send per-landmark confidence](#5-ask-3--send-per-landmark-confidence)
6. [ASK 4 — two schema fixes](#6-ask-4--two-schema-fixes)
7. [Clips to re-check individually](#7-clips-to-re-check)
8. [Acceptance criteria + the self-check script](#8-acceptance-criteria)
9. [What I fixed on my side, for the record](#9-what-i-fixed-on-my-side)
10. [Recommended order of work](#10-recommended-order)

---

## 1. TL;DR

The retargeting is done and verified. Against your landmarks it now reproduces **74.4% of
the signer's real wrist travel — which is 100.5% of what our current avatar's arm can
physically reach** — with **250 of 250 clips passing the anatomical gate**, zero
backward-bending joints, and motion measurably smoother than the source footage.

**There is no remaining headroom on my side.** What still looks wrong traces to four
properties of the export:

| # | Ask | Your effort | What it unblocks |
|---|---|---|---|
| **1** | **Track the hand that MOVES** | High — capture + pipeline | **164 of 250 words**, currently unusable |
| **2** | Ship native clip duration | Low — you already emit `segments` | Sign timing, a real linguistic channel |
| **3** | Send per-landmark confidence | Very low — one field | ~4% more motion, removes a failure mode |
| **4** | Two schema fixes | Trivial | Prevents silent corruption |

Ask 1 is the whole game. Asks 2–4 are quick wins.

---

## 2. Where the pipeline stands

All 250 words, on our current avatar (`model.glb`):

| Metric | Value | What it means |
|---|---|---|
| Wrist travel reproduced | **74.4%** | of the signer's own, like-for-like |
| …as a share of what the arm allows | **100.5%** | the solver is saturated |
| Anatomical gate | **250 / 250** | no self-intersection, no impossible joints |
| Frames faster than the signer's p99 | **0** | nothing reads as a glitch |
| Smoothness (jerk ÷ velocity) | **0.43 – 0.52** | vs the signer's own raw **0.909** |
| Backward-bending elbows | **0** | |
| Finger joints past their limit | 0.1% of joint-frames | |
| Rig test suite | **317 / 317** | |

The 25.6% shortfall is **not** a solver defect. Our avatar's arm measures 1.261
shoulder-widths against the signer's 1.705, so identical joint angles sweep a shorter arc.
That is a property of the model we picked, and it's on us — I mention it only so the 74.4%
isn't read as a data problem.

### Two measurement errors I made, so you don't repeat them

**I was comparing our *filtered* output against your *unfiltered* landmarks.** Path length
rewards noise — every jitter adds length — so the denominator contained motion the avatar
correctly refuses to reproduce. Measured like-for-like, the figure moved from 53% to 74%.
If you ever benchmark this, clean both sides with the same filter first.

**I assumed the residual gap was a short arm.** It was partly **two different rulers**: our
shoulder bone sat at the acromion, while MediaPipe's landmarks 11/12 track the glenohumeral
joint ~3.5 cm medial to it. Same arm, different measuring points, 20% phantom difference.
Worth knowing if you ever compare limb lengths across systems.

Neither was your problem. The four below are.

---

## 3. ASK 1 — track the hand that MOVES

### 3.1 The measurement

For every frame, I split by whether a 21-point hand block came back, then measured how fast
that hand was moving at that moment:

| | median wrist speed |
|---|---|
| hand block **present** | 0.016 shoulder-widths / frame |
| hand block **missing** | **0.032** |
| **ratio** | **1.98×** |

**The untracked hand is moving exactly twice as fast as the tracked one.**

This is not random dropout. It is systematic and inverted: motion blur and self-occlusion
defeat the hand detector, so the hand MediaPipe tracks cleanly is the one hanging still. In
a one-handed sign, that is the wrong hand.

### 3.2 The consequence

Per word, across 64 frames:

| | coverage |
|---|---|
| the hand **doing the sign** | **28.8%** |
| the **resting** hand | **51.5%** |

The resting hand is tracked nearly twice as well as the signing hand.

To score this properly I first had to split the corpus by **handedness**, because a
one-handed sign needs handshape on the hand that signs while a **two-handed sign needs it on
both**. Classifying by the ratio of wrist travel between the hands gives **195 one-handed /
55 two-handed**:

| | words | missing a required hand outright |
|---|---|---|
| one-handed — signing hand absent | 195 | **114** |
| two-handed — one of the two absent | 55 | **50** |
| **total** | **250** | **164** |

**164 of 250 words are missing a hand the sign phonemically requires.** Coverage measured
over required hands only: **30.3%**. Full per-word breakdown — handedness, which hand is
required, coverage, verdict — in `coverage-per-word.csv`.

Verdict split: **164 MISSING, 53 partial, 33 ok.**

> **Why this number differs from the 165 in my earlier audit and the 137 in my first
> spreadsheet — worth two minutes, because it's a trap in your data too.** Both were the same
> mistake in opposite directions. Scoring each word against a single "dominant" hand
> undercounts: it silently forgives a two-handed sign that lost one hand completely (→ 137).
> Deciding dominance from the *retargeted output* while reading coverage from the *input* mixes
> two frames of reference (→ 165). And the 48 words where those two methods disagreed turned
> out to be near-ties — median travel ratio **0.71** between the hands, against **0.37** for
> the words they agreed on. Those aren't ambiguous measurements; they're **two-handed signs**,
> where "the dominant hand" isn't a well-posed question. Splitting by handedness first makes
> the number stable at 164 and the criterion meaningful. If anything on your side buckets by
> dominant hand, it has the same blind spot.

### 3.3 Why this is fatal, not cosmetic

Handshape is one of the **five phonemic parameters** of a sign — handshape, location,
movement, palm orientation, non-manual markers. CAT and FATHER share location and movement
and differ *only* by handshape. So for roughly two-thirds of the dictionary, the feature that
distinguishes the sign is absent from the data entirely.

I can make those hands *look* plausible. They now rest in a relaxed curl rather than the
rig's splayed reference pose, which is what was making them read as rigid claws — that was
the single biggest visual complaint and it's fixed. But plausible is not correct. **No
avatar, no solver, and no amount of smoothing reconstructs a handshape that was never
recorded.**

Only **33 of 250** words currently have adequate coverage on every hand the sign needs.

One diagnostic detail that pins this on tracking rather than on the signer: the two-handed
signs are missing **one** hand 50 times out of 55 and **both** hands **zero** times. If the
signer's hands were simply out of frame, or the exemplar were badly segmented, you'd expect
to lose both together. Losing exactly one, almost every time, is the detector holding onto
the slower hand and dropping the faster one — the same 1.98× effect, visible from a second
angle.

### 3.4 It also inverts the obvious heuristic

If anything on your side keys off hand-block presence — picking exemplars, deciding
dominance, scoring quality — it is currently getting the answer backwards. Using presence to
determine the dominant hand is **wrong on 60% of words**, because presence identifies the
*resting* hand. I had to derive dominance from wrist travel instead.

### 3.5 What to change, in order of expected payoff

**1. Shutter speed at capture.** Motion blur is the most likely primary cause, and nothing
in post-processing beats fixing it at source. If the footage can be re-shot: faster shutter,
more light, higher ISO. A hand moving 0.032 shoulder-widths per frame at 30 fps is covering
roughly 40 cm/s — at 1/30 s exposure that is over a centimetre of smear, which is most of a
finger.

**2. Per-hand ROI tracking.** Instead of one Holistic pass over the full frame, crop to the
hand region predicted from the previous frame and run the hand model on that crop. The hand
then occupies most of the input rather than a few percent of it. This is the standard remedy
for precisely this failure and typically recovers most of it. Rough shape:

```python
# per frame, per hand
roi = predict_roi(prev_landmarks, margin=0.6)      # expand generously; fast hands move
crop = frame[roi.y0:roi.y1, roi.x0:roi.x1]
res  = hands_model.process(crop)                    # hand fills the frame now
if res.multi_hand_landmarks:
    lm = to_full_frame_coords(res.multi_hand_landmarks[0], roi)
else:
    lm = None                                       # null, NOT zeros — see ASK 4
```

**3. Config changes** — cheap, worth trying before anything else:
- `model_complexity=2` (if not already)
- **lower** `min_tracking_confidence` — perhaps 0.3
- **lower** `min_detection_confidence` — perhaps 0.4

Please bias hard toward returning *something*. A noisy hand is far more useful to me than an
absent one: I can filter noise, and I cannot invent a handshape. Right now the tracker is
tuned conservatively and it is costing us the entire parameter.

**4. Check the source parquet before re-shooting.** A 70% loss looks as much like an
export/extraction bug as a tracking limit. If the raw pipeline output is denser than what
reached me, this is a plumbing fix rather than a re-record — dramatically cheaper. Worth
confirming first.

### 3.6 How we'll know it worked

Run `check-export.py` (attached) on the new export. The number to move is **required-hand
coverage: 30.3% now, ≥70% is the target.** Above ~70% handshape becomes usable for most of
the vocabulary. The script also prints the 1.98× diagnostic — that should come down toward
1.0 — and re-derives the re-record list, so you can watch it shrink.

---

## 4. ASK 2 — ship native clip duration

All 250 clips are resampled to exactly **64 frames / 2.133 s**. Every sign in the dictionary
therefore plays at identical speed.

Sign duration is not cosmetic. It carries **aspect** (continuous vs. punctual), **emphasis**,
and **repetition**. Flattening it removes a real linguistic channel, and it makes inherently
fast signs look sluggish and slow signs look rushed.

Mean wrist motion is flat across the window, so this is genuine resampling rather than
padding — **except** that several clips end in dropped frames. `down` loses its last 21, so
its real motion stops at 1.4 s inside a 2.13 s window, and the player was scrubbing through
dead time before looping.

**Ask:** either ship the native frame count, or keep 64 frames and record the true extent.
You already emit `segments` and it currently just spans `0–64`:

```json
"segments": [{ "gloss": "bird", "start": 0, "end": 64 }]
```

Putting the real start/end in there is nearly free and I can re-time from it:

```json
"segments": [{ "gloss": "bird", "start": 7, "end": 48 }],
"nativeFrames": 41,
"nativeFps": 30
```

---

## 5. ASK 3 — send per-landmark confidence

MediaPipe computes `visibility` and `presence` for every landmark. The current schema drops
both.

Without them I infer which samples to distrust, using a median-based statistical test to
find points that don't fit their neighbours. It works — it's how the pipeline got from 51%
to 74% reproduction — but it is **guessing at something you already know**.

Two concrete benefits:

**~4 percentage points of motion.** I currently smooth defensively in places where the data
was actually fine, because I can't tell those places from the bad ones.

**It removes a real failure mode.** My spike detector has a safety valve: if it wants to
reject more than 35% of a series it gives up and passes everything through, on the grounds
that at that point the threshold is more likely wrong than the data. On badly-tracked clips
that is exactly what triggers — so **the worst clips receive no cleaning at all.** With
`visibility` I would know rather than guess, and could clean aggressively where it's
justified.

**Ask:** add both fields per landmark. One number per point, already computed, cheapest item
on this list:

```json
[[0.12, -0.34, 0.05, 0.98], ...]     // x, y, z, visibility
```

or as a parallel array if that's less disruptive to the schema.

---

## 6. ASK 4 — two schema fixes

### 6a. Missing hand blocks must be `null`, not zeros

**19,002 hand blocks (60%) arrive as 21 exact `[0,0,0]` values** rather than `null`.

In shoulder-centred space the origin is mid-sternum. So anything following §6 of the
contract sees 21 perfectly valid numbers and draws the entire hand collapsed into the chest.
`null` I can bridge with interpolation; zeros I have to detect by sniffing for them, which
is precisely the class of ambiguity a contract exists to eliminate.

This already cost real time. My first review claimed the pose-wrist and hand-block-wrist
were **32 cm apart** — a big alarming number that turned out to be the zeros sitting at the
origin and poisoning the median. On real frames only it's **4 cm**, exactly the small offset
you predicted. I retracted it, but a day went into chasing a phantom.

```python
# please
hand = landmarks if landmarks is not None else None   # -> null in JSON
# not
hand = landmarks if landmarks is not None else [[0,0,0]] * 21
```

### 6b. §3's mirroring statement is wrong

> "x: left/right (already mirrored to selfie view — the signer's right hand appears on the
> right of the frame)"

Measured over all 15,877 valid frames: **the signer's right shoulder is at smaller x in 100%
of them.** This is raw camera orientation, not selfie-mirrored.

It doesn't break my renderer, because I derive the lateral axis from landmarks 11/12 rather
than trusting what x means — but it broke my code once, and it will bite whoever reads the
doc and believes it. One-line fix to the contract text.

---

## 7. Clips to re-check

**`wake` — mistracked, unusable.** 42 of its 64 frames project a limb **longer than the
signer's own p99 limb length** (up to 1.08 shoulder-widths against a calibrated 0.87). A
projection can never exceed the true length, so those frames are geometrically impossible
rather than merely foreshortened. It's the only clip that resisted every fix on our side and
the only one that ever failed the anatomy gate by a wide margin (25 cm).

**`hello` — probably the wrong take.** Both wrists stay below the shoulders for all 64
frames with neither hand near the head. HELLO is a salute at the forehead. This matches your
note that exemplars are auto-picked by tracking quality and not yet Deaf-reviewed — which
means there are likely more like it. **Worth a spot-check pass over the 250 before Deaf
review**, since a reviewer flagging mistracked exemplars will waste their time and yours.

---

## 8. Acceptance criteria

`check-export.py` is attached — no dependencies, standard library only. Run it on any new
export before sending, and it will tell you in seconds what would otherwise take a round-trip
through me:

```bash
python3 check-export.py path/to/words      # exit 0 = the critical criteria pass
```

Current output against the v3 export, verbatim:

```
250 words, 15877 valid frames, 123 unusable
classified 195 one-handed / 55 two-handed by wrist-travel ratio

ACCEPTANCE CRITERIA
  [FAIL] required-hand coverage >= 70%                30.3%   (was 30.3%)
  [FAIL] words missing a REQUIRED hand == 0           164 words
  [FAIL] no hand block encoded as 21 zeros            19002 zero-blocks (60%)
  [FAIL] native clip duration (not all 64)            {64: 250}
  [FAIL] per-landmark confidence present              missing
  [FAIL] no limb projects longer than itself          2 words affected, worst: wake
  [PASS] handedness convention is consistent          right shoulder at smaller x in 100% of frames  => raw camera, NOT selfie-mirrored

DIAGNOSTIC — is the tracker dropping the hand that MOVES?
  median wrist speed, hand block PRESENT : 0.0162 sh.w./frame
  median wrist speed, hand block MISSING : 0.0321
  ratio                                  : 1.98x  <-- >1.5 means the tracker is losing the moving hand

  signing hand 28.8%   resting hand 51.5%  <-- resting > signing is the inverted failure

WORST 15 WORDS by required-hand coverage:
   TV                 0 / 64   (one-handed)
   airplane           0 / 64   (two-handed)
   alligator          0 / 64   (one-handed)
   ...

RE-RECORD LIST — 164 words missing a required hand outright:
   TV, airplane, alligator, animal, another, awake, backyard, bad, ...
```

The script prints the full 164-word re-record list at the end, so it stays in sync with the
data rather than with this document.

| Criterion | Now | Target |
|---|---|---|
| **Required-hand coverage** | **30.3%** | **≥ 70%** |
| **Words missing a required hand** | **164** | **0** |
| Moving ÷ still tracking ratio | 1.98× | **≤ 1.2×** |
| Zero-encoded hand blocks | 19,002 (60%) | **0** |
| Native duration shipped | no | **yes** |
| Per-landmark confidence | no | **yes** |
| Words with an impossible limb length | 2 | **0** |

The first two are the ones that matter. The rest are hygiene.

Two notes on the script itself, both from testing it against a synthetic *clean* export rather
than only against the failing one — which I recommend as a habit, because a checker that can
only ever print FAIL is indistinguishable from a broken checker:

- It accepts landmarks with **either 3 or 4 components**, so adding `visibility` per ASK 3
  doesn't make it report every frame as invalid. My first version hard-required 3 and would
  have failed everything the moment you did the thing it asked for.
- The zero-block test looks at **x, y, z only**. A confidence of 0.9 attached to an all-zero
  point must not disguise a missing hand as a real one.

---

## 9. What I fixed on my side

Listing these so it's clear the asks above aren't a deflection — they're what remains after
the animation side is finished. Every one of these was mine:

| Problem | Root cause | Status |
|---|---|---|
| Forearm 18.9 cm inside the chest | IK swivel goes degenerate when the arm is raised | fixed — direct aiming |
| Arm flattened into the coronal plane | depth solved against avatar bone lengths while offsets carried signer proportions | fixed — solve in signer space |
| Elbows bending backward | elbow and wrist depth bits smoothed independently, but the arm is a chain | fixed — joint Viterbi solve |
| Fingers buzzing | hand landmarks were never filtered at all — only elbow and wrist were | fixed |
| Signs looked like a held pose | low-pass filter was eating the signal; 90% of a sign's power is below 3.75 Hz and the cutoff was at 1.6 Hz | fixed — despike + Savitzky-Golay |
| Avatar snapped to a T-pose between signs | lead-in eased to the rig's bind pose | fixed — built a relaxed idle |
| Signing hand switched mid-sentence | 131 left-dominant / 119 right-dominant in the corpus | fixed — mirrored to one hand |
| Hands looked like rigid claws | no finger data → fingers sat in the rig's splayed reference pose | fixed — relaxed curl |
| Clip output depended on batch composition | collision volumes carried state between words | fixed |
| Head, neck, spine, shoulders never moved | face and hip landmarks were in the data and unused | fixed — all now driven |

Also built, and available if useful to you: an anatomical gate, a motion-plausibility check,
a finger-hinge check, a jitter check, a fidelity check against your landmarks, and a
per-word audit of all 250 clips.

---

## 10. Recommended order

**1. Check the source parquet** (hours). If the raw output is denser than the export, this
is a plumbing bug and the cheapest possible fix. Do this before anything else.

**2. Asks 2, 3, 4 together** (a day?). All schema-level, all independent of the tracking
work, all immediately useful. Ask 3 in particular lets me clean the existing data better
while the tracking work happens.

**3. Ask 1** (the real work). Config changes first since they're free, then ROI tracking,
then re-shoot only if those don't move the number.

**4. Spot-check the exemplars** before Deaf review, given what `hello` looks like.

If a full re-record isn't on the table right now, the **164-word list in
`coverage-per-word.csv` is ordered by severity** — the 114 one-handed failures are worth more
per fix than the 50 two-handed ones, because a one-handed sign with no handshape has nothing
left that distinguishes it.

Body motion is at 100% of what our avatar allows. Handshape is at 30.3% coverage on the hands
the signs actually need. **Until Ask 1 lands, roughly two-thirds of the dictionary cannot be
made correct no matter what I do on the animation side** — so it's worth front-loading.

One last framing, because I want to be straight about where the boundary is: nothing above is
a complaint about your work. The tracking failure is a known weakness of Holistic on fast
hands, not a mistake you made, and the schema items are the kind of thing that only surfaces
once two systems meet. What I do want to be unambiguous about is that the animation side has
stopped being the bottleneck — so if we're deciding where to spend the next two weeks, it
should be here.

Happy to get on a call about the ROI-tracking approach, or to look at the raw parquet
directly if that's faster than describing it.
