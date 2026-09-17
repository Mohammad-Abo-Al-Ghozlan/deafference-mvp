# What the avatar cannot do, and why

**Written 2026-08-14.** Companion to `SIGN_ANIMATION_CONTRACT.md`, which says what the pipeline
*does*. This file exists because several ceilings in this system are structural — they come from
the source corpus or from the absence of a data channel, not from unfinished work — and a reader
who does not know which is which will keep filing them as bugs and keep expecting a fix.

Every number here is measured against the shipped 250-word export, not estimated.

---

## 1. 🟠 Non-manual markers: the GRAMMATICAL four now render; the lexical ones do not

> **Updated 2026-09-18.** This section used to say the avatar renders none of these, and that
> the face channel "does not exist in the data we have" so nothing could be done without a
> re-export. Half of that was wrong, and the wrong half was the actionable half.
>
> The four markers in `gloss_to_motion.NONMANUALS` — `q`, `wh`, `neg`, `top` — are
> **grammatical**: they scope over a phrase and are determined by the sentence, not by the
> word. So the sentence is the whole input, and no face landmark is needed to know that a
> yes/no question takes a brow raise. The rig turned out to have the bones already
> (`eyebrow_l/r`, `eyelid_l/r`, `jaw`, `mouth_l/r`, all parented to `head`, all skinned), and
> `avatar/sequence_signs.py` now drives them, with the marker inferred from the raw sentence.
> Amplitudes come from the rig's own skin weights, not from taste: 29 vertices ride
> `eyebrow_l` at a mean 19.2 mm, and 20° about +z moves them 3.6 mm.
>
> **They have not been reviewed by a Deaf signer.** Legible, not authoritative.
>
> What is still missing is below, and it is the part that really does need the data.

The export carries **75 points: 33 pose + 21 + 21 hands. There is no face.**

ASL grammar is not carried by the hands alone. Eyebrow position marks the difference between a
yes/no question and a statement. Head tilt and eye gaze carry topicalisation, conditionals, and
role shift. Mouth morphemes (`MM`, `TH`, `CHA`) modify a verb's manner and are lexically required
on some signs. Negation is frequently carried by a headshake with no manual sign at all.

Of that list the avatar now renders the brow and headshake markers. It renders **none of the
rest**: eye gaze, role shift, conditionals, and every lexical mouth morpheme. Those are the ones
that attach to a particular sign rather than to a clause, and they cannot be inferred from the
sentence — `MM` on a verb is a fact about that verb, and nothing but the face channel or a
per-sign lexicon can supply it.

A signed sentence with correct hands and a neutral face is not a neutral sentence — for a fluent
reader it is closer to ungrammatical, or to a different meaning.

**Scope of the impact.** For the current product — isolated word playback from a 250-word
vocabulary — this is acceptable, because isolated citation forms are the one context where
non-manuals carry the least. **For anything sentence-level it is a correctness failure, not a
polish item**, and it should block any claim that the system "produces ASL" rather than "plays
ASL signs."

**Why the rest is not simply "next up."** The face channel does not exist in the data we have.
GISLR provides 468 face landmarks and `training/medical/extract_landmarks.py` already runs
MediaPipe **Holistic**, which emits them — we write 33 + 21 + 21 and drop the face. So the
capture side is a change to code we own, on both paths. What is not a day's work is everything
after it: which non-manual attaches to which gloss, how it aligns in time with the manual sign,
and a Deaf reviewer to confirm any of it. The rig half of that objection is now answered — the
bones exist and are driven.

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

## 3. 🟠 39 words are degraded at the source — and the 2s gate that starves them is now free to drop

> **Updated 2026-09-18. The blocker on the 2s half of this was removed by a renderer change, and
> the arm that tests it is already on disk (`clips_off.npz`). This is now a decision, not an
> experiment.** Read the caveat at the end before acting on it.
>
> **Why the gate could not be dropped for 2s, and why it now can.** The 2026-08-26 A/B turned it
> off for `2a` only, and kept it for `2s` with a stated reason: 2s mirrors the passive handshape
> onto a **recorded** passive wrist, so a take where that arm hangs would anchor the mirrored hand
> at the signer's hip. `avatar/retarget.py` now reflects the **whole limb** when the passive arm is
> parked (`mirror_passive_arm`), so a hanging passive arm costs nothing. The gate is protecting a
> quantity the renderer no longer reads.
>
> **What it buys, on the 35 words the retargeter currently tracks worst — all of them class 2s:**
>
> | | control (shipped) | gate off |
> | --- | --- | --- |
> | dominant-hand coverage | 39.3% | **83.8%** |
> | share of the sign actually scored | 38.6% | **83.8%** |
> | all 250: coverage | 79.9% | **87.7%** |
>
> Coverage is the honest headline here and the only quantity comparable across the two arms. At
> 20% coverage four frames in five of the animation are `bridge_gaps` interpolating between
> guesses, and no handshape number covers them.
>
> **The cost, measured and real:** the gate-off takes move **22% less** (mean spatial extent of the
> dominant wrist on those 35 words, 0.72 → 0.56 shoulder-widths — measured as distance from the
> wrist's own median position, so tracking dropouts cannot inflate it). That is the failure the
> gate guards against, and it does not disappear. Class 2s does keep its travel floor and the
> signing-hand gate with `require_passive_up off`, so the laziest takes are still rejected.
>
> ### ⚠️ Two reasons this is a decision and not a result
>
> 1. **Handshape error is NOT comparable between the arms.** Each arm is scored against *its own*
>    take's landmarks, so the two numbers have different ground truths. Across all 250 it reads
>    11.27% → 11.08%, better on 56 words and worse on 51 — and several of those regressions
>    (`story` 8.1 → 17.4, `cheek` 6.9 → 15.9, `fine` 6.3 → 15.1) are words whose *coverage went up*.
>    That combination is the tell: a different take is a different performance, not a worse solve.
> 2. **`clips_off.npz` is not a clean A/B of the gate.** 71 of 163 **class-1** exemplars differ
>    between the arms, and the gate cannot apply to class 1 — so the two builds differ in something
>    besides the flag, and part of the coverage delta is not attributable to it. A clean re-run
>    would be `build_sign_clips.py --require-passive-up off` against the same snapshot as the
>    control.
>
> **Recommendation:** take it, after a look. It changes the exemplar on 154 of 250 words, which is
> a data change no metric here can validate — `docs/BASE_HAND_REVIEW.md`'s argument applies. The
> switch is `gloss_to_motion.py --clips clips_off.npz --per-word --out-dir animation_handoff`
> followed by `retarget.py --all`; the animator holds a copy of that folder, so it is his change
> too.

## 3a. The original entry (2026-08-14)

Tier C words are missing the dominant hand on more than half their frames. `bath` is the extreme:
**84 frames, 9 with a dominant hand, longest single gap 51 frames (1.70 s).** No renderer recovers
a sign from that; there is nothing to interpolate between.

**One avenue is open and untested.** The validity filter that selects exemplars rejects **98.8% of
candidate takes for two-handed words** (class 1 keeps 49.0%, median 138 valid takes; 2s keeps
1.2%, median 3; 2a keeps 2.1%, median 5). So these words *may* be degraded because the pool was
starved rather than because the corpus lacks a good take.

> **Do not overstate this.** An earlier version of this section cited a pooled
> `corr(valid_candidates, coverage) = +0.804` as if starvation were the demonstrated cause. **That
> correlation is mostly a between-class artifact** — within class it is only **+0.218** (class 1),
> **+0.244** (2s), **+0.443** (2a). Class-1 words never fall below **73** valid takes and still span
> **0.56–1.00** coverage, so pool size does not buy coverage; and 2a's valid range is **2–9**, which
> cannot predict behaviour at 130. The pooled number largely restates "two-handed signs have fewer
> valid takes *and* worse coverage" — two consequences of two-handedness, not one causing the other.
> Third time this project has been caught by a pooled metric (see §0.4 of `SESSION_HANDOFF.md`).

`build_sign_clips.py --require-passive-up 2s-only` tests it, and the justification for testing is
**mechanism rather than correlation**: on 2a the gate protects a recorded passive wrist that
`asl_2a_base_placement.json` now discards, so it cannot be buying anything there. Until it runs,
treat tier C as real, and treat the outcome as a **genuine unknown** — not a likely recovery.

> **It ran, on both arms, and both results are above.** `2s-only` recovered 2a (coverage
> 0.432 → 0.829, tier-C 2a words 24 → 0) and left 2s untouched, which is why 2s is the whole
> remaining problem; `off` recovers 2s as well. The caution in this paragraph was right about the
> correlation and right to insist on mechanism — the mechanism is what carried it, in both arms.

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

### 🔴 The dominant hand's fingertips are never posed — on any of the 250 words

Found while checking the above, then **verified directly** by parsing the `CLIPS` array out of
`Fix/avatar-player.html` (line 3925 is plain JSON, no decoding needed) and counting bone tracks:

```
segment-3 (distal) tracks, across all 250 clips:
  LeftHandIndex3 / Middle3 / Ring3 / Pinky3 / Thumb3     52 clips each
  RightHandIndex3 / Middle3 / Ring3 / Pinky3 / Thumb3     0 clips  -- never, on any word

clips with ANY distal finger track, by class:
  class 1   0 / 163      class 2s  52 / 52 (passive hand only)      class 2a  0 / 35
```

The reproduction first reported this as "0 of 35 `2a` versus 52 of 52 `2s`", which is true but scopes
it too narrowly. **It is not a 2a defect: the dominant hand's distal phalanges are unposed on all
250 words**, including the 163 one-handed ones where the dominant hand *is* the sign. The only path
that keys a segment-3 bone anywhere in the system is the `2s` mirror, acting on the passive hand. A
`2s` clip carries a median 38 tracks against 33 for class 1 and 2a — a difference of exactly the five
distal bones.

**Likely mechanism (inference, not proof).** `retarget.mjs`'s aim loop takes
`child = ch.bones[i+1] || b.children.find(c => c.isBone)` and `break`s when there is no child. With
three bones per finger, `i = 2` has no `ch.bones[3]`, so it needs a tip node; if the rig has none,
segment 3 is never aimed. The `2s` branch escapes this for the same reason it escaped the side-guard
bug — it copies local quaternions wholesale and never asks for a child. This would also explain why
landmarks 4/8/12/16/20 read null in the rendered hand: one mechanism, two symptoms.

**Why nothing caught it:** the anatomy gate, hinge check, jitter metric and 60/60 rig suite all score
poses that *were* produced. **None of them asks whether a bone was keyed at all** — a bone left at
its bind rotation is anatomically perfect. A non-zero counter would have caught it, which is the same
instrument that caught the animation side's `Pinky`/`Little` bug.

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
