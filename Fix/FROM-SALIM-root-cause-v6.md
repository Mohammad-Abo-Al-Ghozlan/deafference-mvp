# Re: your §3 and §4 are the same finding, and I have the source-side measurement

**To:** animation / retargeting
**From:** Mohammad Salim (data pipeline)
**Re:** `REPLY-TO-SALIM-v5.md`
**Date:** 2026-08-11
**Attached:** `asl_handedness_250.json`

---

## 0. Read this section first

**Do not run `symmetry-test.py` or `handedness-groundtruth.py` on the new exemplars yet.** You
wrote that you'd expect re-selection to produce paired frames "in quantity". It will not produce
any. I went to the raw competition data to find out why your §4 only found 3 paired frames, and
the answer invalidates that expectation.

| | |
|---|---|
| ✅ **Your §1** — `check-export.py` fixed to `0.7/0.3` + `degraded` | **Right call.** The taxonomy was the missing piece, exactly as you said |
| ✅ **Your §2** — my 123 estimate was ~4× high | **Accepted.** Calibrating beat eyeballing; I'd have given you 30 labels and no error bars |
| 🔴 **Your §3 and §4 are ONE finding** | **Root-caused at the source. It is not selection.** — §1 |
| ✅ **Your §4** — don't adopt `max(L,R)` yet | **Agreed, same reasoning.** Also now untestable — §1 |
| 🟢 **The unblock you don't know you have** | **The passive WRIST is available every frame.** You need a handshape, not a hand — §3 |
| 🔴 **Your acceptance criteria can never pass** | Not fixable by a better export. New criterion proposed — §5 |
| ⚠️ **I reported 99.4% coverage from a broken metric** | Withdrawn before it reached you. You should know why — §6 |
| 📊 **Your §3 within-word correlation** | **r = −0.214 mean, −0.220 median, negative on 100% of 250 words** — §4 |

---

## 1. GISLR records ONE hand per participant

Your §3 said the clips don't show their own signs. Your §4 found 3 paired frames for symmetric
signs and you wrote *"the corpus contains almost no frames where a symmetric two-handed sign has
both hands visible at once — the same root cause again."*

You were one measurement away. I attached the original competition data and took it.

**300 random sequences of known two-handed signs, 21 participants, raw parquets — not our export:**

```
left_hand rows present in parquet   300/300        <- not a parsing or schema problem
BOTH hands live                       1.7% of clips
frames with BOTH hands live          mean 0.1%   max 4.8%
ONLY_L 41.0%    ONLY_R 56.7%    NEITHER 0.7%
14 of 21 participants: EVERY clip the same class
  49445: ONLY_R x24     22343: ONLY_L x18     55372: ONLY_L x16
```

And per-word, the two-handed signs are indistinguishable from the one-handed ones:

```
book  (needs 2 hands)   both hands in  3% of clips
hello (needs 1 hand)    both hands in  3% of clips
```

The corpus contains 41% / 57% of our clips as left-only / right-only, and our extraction
reproduces those proportions exactly — so this is not something we lost. **One hand was recorded
per participant, baked in at capture.**

A statistical note, because "the tracker was flaky" was my first hypothesis too and it does not
survive: with `P(L present) = 0.44` and `P(R present) = 0.59`, independent per-hand failure
predicts ~2,600 clips with *neither* hand. We observed **3** out of 11,225. Exactly-one-of-two is
a constraint, not a failure distribution.

**What follows for your two findings:**

* **§4 is unanswerable, permanently.** `symmetry-test.py` needs frames where a symmetric sign has
  both hands tracked. There are essentially none, and re-selection cannot create them. Your
  instinct to report the negative result rather than ship a detector was right, and it is worth
  more than the test would have been.
* **§3 is real but is not an arbitrary draw.** `owl` 0.27, `stairs` 0.20, `tiger` 0.28 —
  those are **weak drop**: signers dropping the passive hand in casual signing. GISLR is
  crowd-sourced caretaker signing, so it is everywhere, not a selection accident. Which means
  your measurement is good and your diagnosis was one level too shallow — the same as mine was.

---

## 2. Handedness is not in the landmarks. I stopped trying to infer it.

Before accepting that, I tested four classifiers against 40 hand-labelled words:

```
wrist path-length ratio     AUC 0.335    <- INVERTED: one-handed signs score HIGHER
spatial-extent ratio        AUC 0.460
passive-wrist height        AUC 0.468    <- your precision-0.27 result, independently
weaker-hand presence        AUC 0.500    <- 0.000 for every word, both classes
```

Your `handedness-analysis.csv` and my scan agree on the shape of this. The whole 250-word
distribution of my ratio sits inside `0.377–0.595` — every word converging on the same value,
which is what a statistic with no word-level signal looks like.

So: **attached is `asl_handedness_250.json`** — all 250 words, hand-labelled from ASL phonology,
three classes matching yours (`1` / `2s` / `2a`).

```
one-handed                163
two-handed SYMMETRIC       52     mirror the dominant handshape -> exact
two-handed ASYMMETRIC      35     unmarked handshape at a base  -> not a mirror
                          ---
two-handed total           87     (35%)
```

**Cross-checked against your 96 labels: 84/92 agree = 91%, and zero disagreements where we were
both maximally confident.** Two independent labellings converging like that is the best evidence
either of us has produced. Your figure was ~90 two-handed; mine is 87. We landed in the same place
from different directions.

**`table` is yours — I've changed it.** You had ASYM, I had SYM. The non-dominant forearm is a
static base the dominant taps on: Dominance, not Symmetry. Mirroring it would have been a visible
renderer error, so thank you for that one specifically.

Seven still open, all low-confidence on at least one side: `sad`, `toy`, `napkin`, `shower`,
`cut`, `owie`, `refrigerator`. Those go to the Deaf reviewer with the 45 I already flagged. Same
caveat you gave: my labels are a hearing developer's reading of citation forms, not ground truth.

---

## 3. 🟢 The passive WRIST is available every frame

This is the part that changes what you build, and neither of us has said it yet.

The missing hand is the 21-point **hand** block. The **wrist** is a *pose* landmark, and pose
wrists are present in **3192/3192 frames** I measured. So for every two-handed sign, in every
frame:

> **the passive hand's POSITION is known. Only its HANDSHAPE is missing.**

You are currently scoping "synthesize the passive hand". You only need to synthesize a handshape
and hang it on a wrist trajectory we can hand you.

Which makes Battison do the actual work:

* **`2s` — 52 words.** Same handshape on both hands. Mirror the dominant handshape onto the real
  passive wrist position. No assumption, no invention.
* **`2a` — 35 words.** Passive hand restricted to an unmarked handshape (B, A, S, 1, 5, C, O) —
  a closed 7-item set — positioned at the real passive wrist. The wrist tells you the place of
  articulation, which is the part that actually has to be right.
* **`1` — 163 words.** Nothing to do.

I'll add `passiveWrist` as a first-class per-frame track in the export so you don't have to dig
it out of the pose block.

---

## 4. Your §3 number, which you asked for first

Within each word, Pearson r between candidate coverage and candidate dominant-wrist travel, over
all ~287 candidates per word:

```
mean   -0.214
median -0.220
words with r < 0   100%  (250/250)
verdict            STRONG
```

**Your mechanism is real.** Selecting on coverage is partly selecting for stillness, for exactly
the causal reason you gave. `--travel-floor median` is in and on by default.

Taking your suggestion about printing the unguarded pick in the real run too, not just the
synthetic — that's how I'd have caught the next one earlier.

---

## 5. 🔴 Your acceptance criteria can never pass, and that's correct

On your updated checker:

```
[FAIL] required-hand coverage >= 70%          28.5%
[FAIL] words missing the DOMINANT hand == 0   137 words
[FAIL] two-handed words missing the passive    27 words (degraded)
```

Under §1, the third line will read ~87 forever, on any export, from any selector. The passive
hand is not absent because we chose badly — it does not exist in the source. Chasing it is a
treadmill.

**Proposed criterion, your call since the metric is yours:**

```
PASS/FAIL   dominant-hand coverage >= 70%           <- this is on us, and it's real
REPORTED    passive hand absent: N words            <- expected == the 2s/2a count (87)
PASS/FAIL   every 2s/2a word carries a passiveWrist track
PASS/FAIL   synthesis class present for all 87      <- so you can't silently skip one
```

That way the check still fails loudly when *we* ship something bad, and stops failing for a
condition neither of us can fix. If you'd rather express it differently, send it back — I'd
rather use your criterion than patch it myself, same as last round.

---

## 6. I reported 99.4% coverage from a metric that measured my own choice

You should know this happened, because it is the same failure mode as your `dominantHand` bug and
it nearly reached you.

I let each candidate clip decide its own handedness from its own wrist travel. A take where one
hand was never detected has a still passive arm → self-classifies one-handed → the requirement
collapses to the hand it happens to have → **scores a free 1.000.** The selector found that corner
for all 250 words, picked a single-hand take for `airplane`, `all`, `book`, and reported 99.4%
coverage while doing it.

Caught it by asking why 234 of 250 words had coverage of exactly `L 1.00 / R 0.00`. Exact 1 and
exact 0 is structural; tracking noise gives you 0.87 and 0.34.

Handedness is a property of the sign, not of one recording. Fixed per-word first, then replaced
entirely by the lexicon in §2.

One more, found the same day and it affects clips you already have: the corpus was
**gap-filled** — forward-fill then back-fill per landmark. It inflates hand presence from what
the tracker saw to a solid block:

```
book 1688271138   raw 57% -> stored 100%
bath 1124807407   raw  9% -> stored  32%
yes  1071364049   raw 64% -> stored 100%
```

So a hand seen for 9% of frames is **frozen at its last position** for the rest. That is why
coverage came out as exactly `1.00` or `0.00` and never anything between — the number you asked me
to optimize was measuring our forward-fill, not tracking quality. **If you are seeing hands that
stop dead mid-sign on the avatar, that is where it comes from.** I've re-extracted from raw with
true `NaN` preserved; real presence is ~57–65%, not 100%.

---

## 7. What I'm doing next

1. **Selector v7** — handedness from the lexicon, landmark inference deleted. Coverage scored on
   the dominant hand only, since the passive one is known-absent and adds a constant.
2. **Weak-drop rejection, using your measurement.** Your travel ratio failed as a *classifier*
   because it was being asked to infer handedness. Given handedness externally, it becomes a
   validity filter: lexicon says `2s` + this take's passive-arm ratio is 0.27 → weak-drop take,
   reject. Your `owl`/`stairs`/`tiger` list is the test set for it. **Your number plus my lexicon
   is worth more than either alone** — that's the part of your reply I got the most out of.
3. **Re-select from the un-gap-filled corpus**, so coverage means real presence.
4. **`passiveWrist` per-frame track** in the export, per §3.
5. **Deaf review**, your ordering: the 45+7 lexicon words first, then your suspect-clip list
   (`owl`, `stairs`, `tiger`, `alligator`, `book`). Agreed that if those are representative,
   exemplar validity outranks handshape coverage and no check either of us owns can see it.

Two asks:
* **§5** — the acceptance criterion. Yours to define.
* **Don't spend a run on `symmetry-test.py`.** §1 is why. If you disagree with my reading of the
  raw data, the scan is short and I'll send it — I'd rather you check it than take it from me.

On your last paragraph: agreed, and I'll stop returning the compliment. `both failures were
silent success reports` is the useful sentence. Mine printed `250/250 clean` from a warning that
could not fire and then `99.4%` from a metric scoring its own input. Every guard I've added since
asserts on the output and prints what the alternative strategy would have given, so it can't
report success quietly.
