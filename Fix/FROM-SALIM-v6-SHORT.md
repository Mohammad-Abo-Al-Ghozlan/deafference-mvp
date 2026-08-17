# Root-caused your §3 + §4 — and 3 things I need from you before I rebuild

**From:** Mohammad Salim (data pipeline) · **Re:** `REPLY-TO-SALIM-v5.md` · **2026-08-11`
**Attached:** `asl_handedness_250.json`

---

## ⛔ First: don't run `symmetry-test.py` on the new exemplars

You wrote you'd expect re-selection to produce paired frames "in quantity". It will produce
**zero**. §1 is why. That run would cost you a day and give you a wrong conclusion.

---

## 1. Your §3 and §4 are the same finding. It's the source, not selection.

I attached the raw competition data. **300 random sequences of known two-handed signs, 21
participants:**

```
left_hand rows present in parquet   300/300      <- not a parsing problem
BOTH hands live                       1.7% of clips
frames with BOTH hands               mean 0.1%   max 4.8%
ONLY_L 41.0%   ONLY_R 56.7%   NEITHER 0.7%
14 of 21 participants: EVERY clip the same class

book  (2 hands)  both hands in 3% of clips
hello (1 hand)   both hands in 3% of clips     <- identical. no signal at all.
```

Not tracker flakiness: independent per-hand failure at these rates predicts ~2,600 clips with
*neither* hand. We observed **3** of 11,225. Exactly-one-of-two is a constraint, not a failure
distribution.

**GISLR recorded one hand per participant, baked in at capture.** Our extraction reproduces the
41/57 split exactly, so we didn't lose it.

- **Your §4** (3 paired frames) — permanently unanswerable, not fixable by re-selection.
- **Your §3** (`owl` 0.27, `stairs` 0.20, `tiger` 0.28) — real, but it's **weak drop**: signers
  dropping the passive hand in casual signing. GISLR is crowd-sourced caretaker signing. Not an
  arbitrary draw. Your measurement was good; the diagnosis was one level too shallow — same as mine.

## 2. 🟢 The passive WRIST is available every frame

The missing block is the 21-point **hand**. The **wrist** is a *pose* landmark — present in
**3192/3192** frames measured.

> **Position is known. Only the handshape is missing.**

You're scoping "synthesize the passive hand". You need a handshape on a wrist trajectory I can
hand you. `2s` → mirror the dominant handshape. `2a` → one of 7 unmarked handshapes at the real
wrist. That's Battison doing the work, with the place of articulation measured rather than guessed.

## 3. Lexicon attached — and we agree 91%

Handedness isn't in the landmarks. Four classifiers vs 40 labelled words: path-length ratio AUC
**0.335** (inverted), extent ratio 0.460, passive height 0.468, weak-hand presence 0.500. So I
labelled it instead.

```
one-handed 163 | SYMMETRIC 52 | ASYMMETRIC 35     (87 two-handed = 35%)
vs your 96 labels: 84/92 agree = 91%, zero disagreements where we were both max-confident
```

**`table` is yours — changed it.** Static passive forearm = Dominance, not Symmetry. Mirroring it
would've been a visible renderer error.

7 open, all low-confidence somewhere: `sad`, `toy`, `napkin`, `shower`, `cut`, `owie`,
`refrigerator`. Those go to the Deaf reviewer with 45 I'd already flagged — not resolved by two
hearing developers arguing.

## 4. Your §3 correlation, which you asked for first

```
r = -0.214 mean, -0.220 median, negative on 100% of 250 words     STRONG
```

Your mechanism is real. `--travel-floor median` is in and on by default.

## 5. Two of mine, so you can check your own artifacts

- **I reported 99.4% coverage from a metric that scored my own choice.** Each candidate decided its
  own handedness, so a one-hand take self-classified one-handed and got a free 1.000. Withdrawn
  before it reached you. Caught it by asking why 234/250 words had coverage of exactly
  `L 1.00 / R 0.00`.
- **The corpus was gap-filled** (ffill+bfill per landmark): `raw 57% → stored 100%`,
  `raw 9% → stored 32%`. A hand seen for 9% of frames is **frozen at its last position** for the
  rest. **If you're seeing hands stop dead mid-sign on the avatar, that's the cause.** Re-extracted
  from raw with true `NaN`; real presence is ~57–65%.

---

## 6. What I'm doing — selector v7

1. Handedness from the lexicon; landmark inference **deleted**.
2. **Weak-drop rejection using your travel ratio.** It failed as a *classifier* because it was
   being asked to infer handedness. Given handedness externally it becomes a validity filter:
   lexicon says `2s` + this take's passive-arm ratio is 0.27 → reject. **Your number + my lexicon
   is worth more than either alone** — that's what I got most out of your reply.
3. Re-select from the un-gap-filled corpus so coverage means real presence.
4. Score dominant-hand coverage only; the passive hand is known-absent and adds a constant.
5. Ship `passiveWrist` as a first-class per-frame track.

Full inventory of all 22 known defects with causes and ordering is in our `MASTER_FIX_PLAN.md` —
12 already closed today. Happy to send it if you want the whole picture; the above is the part
that touches you.

---

## 7. 🔴 Three things I need from you BEFORE I rebuild

I'd rather wait than rebuild twice.

**① The acceptance criterion.** Yours to define — the metric is yours. Your current one can never
pass: `two-handed words missing the passive hand` will read ~87 forever, on any export, from any
selector. Proposed:

```
PASS/FAIL   dominant-hand coverage >= 70%              <- on us, and real
REPORTED    passive hand absent: N          expected == 87 (the 2s/2a count)
PASS/FAIL   every 2s/2a word carries a passiveWrist track
PASS/FAIL   a synthesis class is present for all 87    <- so none gets silently skipped
```

Send it back in whatever form you want and I'll optimize exactly that.

**② Can your rig consume `wrist trajectory + synthesized handshape`?** This is a real dependency,
not a courtesy question. If your retargeter needs a full 21-point hand and can't take a wrist
position with a handshape supplied separately, my export design in §2 is wrong and I need to know
now. Also: does mirroring the dominant handshape onto the passive side read correctly on the
avatar for `2s`?

**③ Your full suspect-clip list.** You named `owl`, `stairs`, `tiger`, `alligator`, `book`, and
mentioned 8 clips contradicting their own sign. Send all of them — that's the test set for the
weak-drop filter in §6.2. Without it I'm tuning a threshold against nothing.

Also, if you have it: `asymmetric-detect.py` didn't come through (only `check-export.py`,
`handedness-groundtruth.py`, `handedness-analysis.csv`, and your reply arrived). Not urgent.

---

Agreed on your closing point, and I'll stop returning the compliment. `both failures were silent
success reports` is the sentence worth keeping. Mine printed `250/250 clean` from a warning that
couldn't fire, then `99.4%` from a metric scoring its own input. Every guard since asserts on the
**output** and prints what the alternative strategy would have given.
