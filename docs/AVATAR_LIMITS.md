# What the avatar cannot do, and why

**Written 2026-08-14.** Companion to `SIGN_ANIMATION_CONTRACT.md`, which says what the pipeline
*does*. This file exists because several ceilings in this system are structural — they come from
the source corpus or from the absence of a data channel, not from unfinished work — and a reader
who does not know which is which will keep filing them as bugs and keep expecting a fix.

Every number here is measured against the shipped 250-word export, not estimated.

---

## 1. 🔴 No non-manual markers. This is the largest correctness gap in the system.

The export carries **75 points: 33 pose + 21 + 21 hands. There is no face.**

ASL grammar is not carried by the hands alone. Eyebrow position marks the difference between a
yes/no question and a statement. Head tilt and eye gaze carry topicalisation, conditionals, and
role shift. Mouth morphemes (`MM`, `TH`, `CHA`) modify a verb's manner and are lexically required
on some signs. Negation is frequently carried by a headshake with no manual sign at all.

The avatar renders **none of these**. A signed sentence with correct hands and a neutral face is
not a neutral sentence — for a fluent reader it is closer to ungrammatical, or to a different
meaning.

**Scope of the impact.** For the current product — isolated word playback from a 250-word
vocabulary — this is acceptable, because isolated citation forms are the one context where
non-manuals carry the least. **For anything sentence-level it is a correctness failure, not a
polish item**, and it should block any claim that the system "produces ASL" rather than "plays
ASL signs."

**Why it is not simply "next up."** The face channel does not exist in the data we have. GISLR
provides 468 face landmarks, so a future export could carry them — but every downstream stage
would need building: which non-manual attaches to which gloss, how it aligns in time with the
manual sign, and a rig capable of rendering it. None of that exists, and none of it is a
day's work.

---

## 2. 🟠 Two-handed signs are structurally worse than one-handed ones

Measured across the 250 shipped words, dominant-hand coverage by handedness class:

| class | words | 🟢 A (≥80%) | 🟡 B (50–80%) | 🔴 C (<50%) |
|---|---|---|---|---|
| **1** one-handed | 163 | **144** | 19 | **0** |
| **2s** symmetric | 52 | 3 | 26 | 23 |
| **2a** asymmetric | 35 | **0** | 19 | 16 |
| — combined 2s+2a | 87 | **3** | 45 | **39** |

**Three of 87 two-handed words reach tier A. Zero of 163 one-handed words fall to tier C.** The
split is almost perfectly along the one-vs-two-handed line, which is the tell that this is a
property of the source data rather than of any processing stage.

Two independent causes, both structural:

**(a) GISLR records ONE hand per participant.** Both hands are present in 1.7% of clips; both-hand
frames average 0.1%; 14 of 21 participants are single-handed throughout. So the passive hand is
absent from *every take of every word* and must be synthesized — by mirroring for `2s` (exact,
Battison's Symmetry Condition) and by template + placement lexicon for `2a` (approximate).

**(b) The tracker loses the hand that moves, worst when hands occlude.** Measured on this export:
median wrist speed is **0.0208 sh.w./frame when the hand block is present** and **0.0317 when it
is missing — a 1.52× ratio.** Two-handed signs are exactly where the hands cross and occlude each
other, so the dominant hand drops out most on the words that need it most.

**Neither is fixable with more engineering on this corpus.** A different source — one that records
both hands — is the only real fix, and that is a data-acquisition project.

---

## 3. 🟠 39 words are degraded at the source and re-selection may not save them

Tier C words are missing the dominant hand on more than half their frames. `bath` is the extreme:
**84 frames, 9 with a dominant hand, longest single gap 51 frames (1.70 s).** No renderer recovers
a sign from that; there is nothing to interpolate between.

**One avenue is open and untested.** The validity filter that selects exemplars rejects **98.8% of
candidate takes for two-handed words** (class 1 keeps 49.0%, median 138 valid takes; 2s keeps
1.2%, median 3; 2a keeps 2.1%, median 5), and `corr(valid_candidates, coverage) = +0.804`. Words
with >60 valid takes: 0 of 163 degraded. Words with ≤3: 22 of 38 degraded. So these words may be
degraded because the *pool was starved*, not because the corpus lacks a good take.

`build_sign_clips.py --require-passive-up 2s-only` tests this. Until it runs, treat tier C as
provisional-but-real: **some** of the 39 are probably recoverable, and some certainly are not.

---

## 4. 🟡 The 2a passive hand: a shape floor and an authored placement

**Shape — ⚠️ this entry was wrong on 2026-08-14 and is now unresolved.**

The animation side measured the rendered passive hand against all seven templates and found the
requested shape nearest in only **8 of 35** cases, with a ~0.150 reconstruction error against a
0.206 B–C template gap. An earlier version of this file accepted that and concluded "~26 words
render a slightly cupped flat hand rather than a crisp flat B… it will not reach zero on this rig."

**An independent reproduction contradicts almost every step of that.** His rig and all 250 clips
were extracted from the base64 in `Fix/avatar-player.html`, `template-check.mjs` was reimplemented
from scratch, and his exact numbers reproduced (8/35, 0.150, 0.606) — then re-scored in **bone
direction space, which is the quantity the retargeter actually solves for**:

```
mean direction error vs the requested template, 10 measurable segments/hand
  B 0.00 deg    C 0.00 deg    1 0.00 deg    A 0.00 deg    S 6.59 deg
nearest-in-direction correct: 5/5 shapes = 35/35 words
negative control (rig rest hand): 14.9 deg from B, nearest is `5` -> the test CAN fail
```

Positional error is fully explained by proportion mismatch (avatar/template phalanx ratios
0.77–0.95). Three further corrections, all cutting against the original reading:

- The 0.150 error and the 0.206 gap were **measured on different landmark sets** — templates are
  complete 21-point arrays (20 landmarks), but the rendered hand fills only **14** (the rig has 3
  bones per finger with no tip node, so 4/8/12/16/20 are null, and the thumb resolves such that 3
  is null too). On the 14 the rig can actually express, the B–C gap is **0.124, not 0.206** — so
  the error exceeds the *entire* gap, not half of it.
- The "error is half the gap so nearest-neighbour flips" arithmetic **does not hold**. Simulated at
  4000 trials, isotropic error of 0.150 keeps B nearest 4000/4000; a flip needs a *directed* error.
  His own coin-flip model predicts 63%, not 23% — so 8/35 sits ~5.5σ below his own explanation.
- **Effective n is 5, not 35.** The rendered passive pose is identical across all words requesting
  the same shape (max within-shape distance 2.4e-08). The 26 B "failures" are one failure counted
  26 times. The statistic should be **3/5 shapes**, not a binomial rate over 35 words.

**Status: the ~0.15 "floor" should not be quoted.** In the space the rig controls the shapes are
exact; what is genuinely unresolved is why nearest-of-7 in *position* space fails deterministically
for B and S. This reproduction has not itself been adversarially checked — the refuters for it died
on a session limit — so treat it as a strong single reproduction rather than settled, and resolve
it by having the animation side adopt a direction-space acceptance gate with the rest-hand negative
control.

**And a real render defect found in passing, which neither side had noticed: 0 of 35 `2a` clips key
the distal finger bones, while 52 of 52 `2s` clips do.** The fingertips are not being posed on the
asymmetric path at all. That is independent of everything above and of the side-guard bug in §6.

**Placement.** The recorded passive wrist is unusable — a median **1.56 shoulder widths** from the
dominant wrist across all 35 words, with only 1 of 35 inside 1.38. The arm is *not* hanging
(median 0.34 sh.w. below its own shoulder, never past 0.75); it is raised but on its own side of
the body, because the signer had no reason to form a base for a one-handed recording. A proximity
filter therefore strands 35 of 35 and cannot ship. `asl_2a_base_placement.json` replaces the
position synthetically — **but it was authored by a hearing developer from ASL phonology and has
not been checked against video.** 22 entries are marked high confidence, 11 medium, 2 low.

**Six of the 35 are not handshape-at-a-point problems at all** — `arm`, `table`, `tree`, `flag`,
`morning` act on the passive *forearm*, and `time` targets the *wrist*. The placement schema
cannot express a posed limb, so these are marked `kind: forearm|wrist` and remain approximate no
matter how good the handshape is.

---

## 5. 🟡 Two lexicons are hearing-authored and unreviewed

Both are honest about it in their own `review_status`, and both are load-bearing:

- **`handshape_templates.json`** — anchor words chosen from phonology by a hearing developer.
  Six of seven shapes are measured from real data (`1 5 B A S C`); `O` is not usable and resolves
  to `C`, but **no 2a word requires `O`, so that substitution never fires** — and `S→A` never
  fires either. On this vocabulary it is 35/35 measured shapes with zero approximations live.
- **`asl_2a_base_placement.json`** — 35 base positions, authored 2026-08-14, never validated.

Neither has been seen by a Deaf signer. **Where a reviewer disagrees, the fix is the lexicon, not
the rig** — and `template-check.mjs` exists specifically so the two can be told apart.

---

## 6. 🟢 Fixed, and worth recording as fixed

So these are not re-litigated:

- **The wrong hand.** 137 of 250 words shipped the *resting* hand. Now 1 — and that one
  (`finish`) turned out to be a checker deriving dominance from wrist travel rather than reading
  the asserted field. Fixed 2026-08-14; a zero-counter now guards it.
- **All-64-frame durations.** Native lengths restored, 9–116 frames.
- **Blend length.** `DEFAULT_TRANSITION = 8` was 64% of `tiger`'s span with a neighbour each side.
  Now scaled to the shorter clip; 18.2% on `tiger`, unchanged on anything ≥53 frames.
- **A criterion that could not fail.** "per-landmark confidence present" was retired by both
  sides: a landmark is exported with coordinates or as null, and null *is* not-visible, so a
  fourth component would be a constant function of the first three.

---

## 7. What "isolated words" means, and does not

The system plays a **250-word citation-form vocabulary in sequence**. It is not continuous
signing. Beyond the missing non-manuals in §1, continuous ASL requires co-articulation (each sign
reshaped by its neighbours), spatial referencing (pronouns established at points in signing space
and referred back to), classifier constructions, and a grammar whose word order is not English.

`gloss_to_motion.stitch()` inserts an eased blend between clips. **That is a cross-fade, not
co-articulation** — it hides the seam, it does not reshape either sign. The distinction matters
because the seam is the visible problem and co-articulation is the linguistic one, and fixing the
first does nothing for the second.

---

## The one-line version

**One-handed words are in good shape. Two-handed words are limited by a corpus that recorded one
hand. Sentences are limited by a face channel that does not exist.**
