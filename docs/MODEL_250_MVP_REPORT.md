# 250-Word ASL Model — MVP Report

Status of the sign→speech recognition model and the sign-animation export, as of the
CPU verification session. Written to be read by someone who was not in the room.

> ⚠️ **Updated 2026-08-13.** The single-number headline below has been replaced by a per-signer
> distribution — see §1.0. A point estimate is not a defensible way to state this model's
> accuracy. §1.1's conclusion about canonicalization is also **withdrawn**; see §1.1.

**Headline:** the recognition model works, and its accuracy depends far more on *who is signing*
than on anything else. Pooled over 7 held-out signers it scores **0.666**; per signer it ranges
from **0.314 to 0.823**. The best single-fold split-level number, **0.7658** (the 4-fold
ensemble reaches 0.7755), is measured on a test split that happens to contain only the easy
configuration. The animation export was, until the
2026-08-12 session, **shipping the wrong hand on 249 of 250 words** — that is now fixed and
verified at 76.2% dominant-hand coverage. The recognition and animation numbers are unrelated;
they are two different products off one corpus.

---

## 1.0 Accuracy, stated honestly (2026-08-13)

One model (fold 0, `mask=off`, seed 42, 120 epochs) scored on every signer it never trained on:

| pid | group | L-block | R-block | **acc** | layout |
|---|---|---|---|---|---|
| 26734 | val | 0.02 | 1.00 | **0.823** | pure R |
| 2044 | test | 0.01 | 1.00 | 0.806 | pure R |
| 37779 | test | 0.00 | 1.00 | 0.780 | pure R |
| 53618 | test | 0.13 | 0.88 | 0.707 | R + contamination |
| 32319 | val | 1.00 | 0.04 | 0.614 | pure **L** |
| 34503 | val | 1.00 | 0.08 | 0.577 | pure **L** |
| 29302 | val | 0.48 | 0.99 | **0.314** | **both blocks** |

**Pooled 0.666. Median 0.707. Spread 0.509.**

Both split-level figures reconcile exactly from these rows — val fold 0 = 0.5791, test = 0.7658
— so the spread is arithmetic, not sampling noise in the measurement.

Accuracy **correlates with** hand-block layout, which is a recording artifact, not signer skill:

- **Left-recorded signers sit ~20 points lower** (0.577, 0.614 against 0.780–0.823).
- **Both blocks populated sits ~50 points lower.** 29302 carries a right-hand block in 99% of
  clips *and* a left-hand block in 48%; the model trained on clips carrying essentially one block.
  Accuracy is flat near 0.80 while L-contamination stays ≤0.02, then 0.13 → 0.707, 0.48 → 0.314.

> ### ⚠️ The causal reading of this correlation was tested and REFUTED (2026-08-14)
>
> An earlier version of this section said accuracy *tracks* layout and treated layout as the
> cause. The corpus was rebuilt canonically — every signing hand in one block, geometric
> dominance, `left_dead 1.000`, `aligned 60.0%`, all 41 geometry checks green — and fold 0
> retrained identically. Result:
>
> | | legacy | canonical | delta |
> |---|---|---|---|
> | 34503 (pure L) | 0.5774 | 0.5692 | −0.0082 |
> | 32319 (pure L) | 0.6143 | 0.6035 | −0.0108 |
> | 29302 (both blocks) | 0.3141 | 0.3139 | **−0.0002** |
> | **mean, affected** | | | **−0.0064** |
> | **mean, unaffected (4)** | | | **−0.0067** |
> | pooled | 0.6656 | 0.6591 | −0.0065 |
>
> The intervention hurt the three targeted signers by the same amount as the four it was not aimed
> at — **no differential effect at all** — and 29302, the entire reason for the theory, moved
> −0.0002. Spread 0.5090 → 0.5019, narrowing only because everything drifted down together.
>
> Layout is a **proxy** for whatever drives the spread, not the cause. Both plausibly correlate
> with something else about how those sessions were recorded, which is unidentified.
>
> Confound, stated honestly: canonical data also changes augmentation (`hflip` no longer swaps
> hands, hand-drop has 1 block not 2) and train acc fell 0.767 → 0.710, so the corpus lost
> fittable signal too. Either explains the uniform −0.0066; **neither can manufacture a
> differential gain, which is what was on trial.** Full detail: `SESSION_HANDOFF.md` §0.5.
>
> **Not refuted:** the same geometry, used to pick which hand to *animate*, is verified correct by
> direct measurement — the export went from 137/250 words rendering the resting hand to 1.

**Why 0.7658 must not be quoted as "the" accuracy.** The test split contains three signers at
L-contamination 0.13 / 0.00 / 0.01 — **no left-recorded signer and no both-blocks signer.** It
cannot measure either failure mode. The number is structurally optimistic, not merely fortunate.
The val fold, which holds three of the four affected signers, is the sensitive endpoint; and it
is if anything generous itself, since model selection used it (EMA retains best-`val_acc`
weights).

For product purposes: a new user should be told to expect roughly **0.6–0.8**, with a real
chance of much worse if their tracking lands in the both-blocks regime. The 0.82–0.85 target
from `MASTER_PLAN.md` §5 is a **mean-over-signers** goal and should be restated as such.

---

## 1. What actually got measured

| | |
|---|---|
| Vocabulary | 250 words |
| Corpus | GISLR (Google Isolated Sign Language Recognition), 82,942 clips |
| Model | TF/Keras, exported SavedModel; runs in TF.js in the browser |
| Split | by participant — **verified** 2026-08-13: 18 cv / 3 test participants, **0 overlap**, `0 / 14245` test clips from a cv participant |
| **Test top-1, single fold** | **0.7658** (2026-08-13 control arm, legacy corpus) — read §1.0 before quoting it |
| Test top-1, 4-fold ensemble | **0.7755** (measured 2026-08-06; per-fold 0.7544 / 0.7570 / 0.7545 / 0.7615, so ensembling is worth +1.86) — the highest number we have |
| Earlier single folds | 0.7590 (arm B, canonical corpus) · 0.7576 (previously shipped) |
| Pooled over all 7 held-out signers | **0.666** — see §1.0 |

### 1.1 The A/B run, corrected

Two arms were trained to compare corpus layouts. My first reading of the result was wrong
and the corrected reading is the one that matters:

| arm | corpus | test top-1 |
|---|---|---|
| A | legacy layout, gap-filled | 0.7445 |
| B | canonical layout | 0.7590 |

**The +1.46-point gap is not a real effect and must not be quoted.** Arm A was doubly
handicapped by its own augmentation config:

1. It applied hand-swapping horizontal flip to data that was already canonicalized, which
   moves the real hand into a slot that is NaN in every frame — on roughly half of its
   samples the model saw no hand at all.
2. Its second drop-block was a no-op on that layout.

Corrected reading: **arm B's 0.7590 versus the historically shipped 0.7576 is parity, not a
win.** It was worth doing for other reasons — it removes the left/right ambiguity from the
animation export, and it frees the 33–53 landmark block for face landmarks.

> 🔴 **WITHDRAWN 2026-08-13.** This section used to conclude "canonicalization did not buy
> accuracy." **That conclusion is not supported and must not be repeated.** The test split
> contains no left-recorded signer and no both-blocks signer (§1.0), so canonicalization had
> nothing to fix in the data it was scored on — it paid the cost of a different preprocessing
> with none of its benefit measurable. The comparison was blind by construction, which is a
> different thing from a null result.
>
> What we now know: the two configurations canonicalization exists to eliminate cost **~20 and
> ~50 accuracy points** on the signers that have them. Canonicalization is the highest-value
> remaining lever, and any future layout A/B must be judged **per signer on 34503, 32319 and
> 29302**, never on pooled test accuracy. See `SESSION_HANDOFF.md` §0.4.

### 1.2 Per-class breakdown

One- versus two-handed signs perform the same:

```
one-handed  +0.0146  (n=163)
two-handed  +0.0157  (n=87)
gap         -0.0012   pooled SE 0.0077  ->  -0.15 sigma  (not significant)
```

Two words are effectively dead in both arms (<0.20): `give`, `nap`.

### 1.3 The `--init-from` bug

An attempt to warm-start the 250-word model from the 30-word checkpoint silently produced
a model at chance level. The cause: shape mismatch that was never asserted on.

```
expected inputs : 650      weights had : 450
classifier      : 768                    384
epoch-1 accuracy: 0.0049   (1/250 = 0.004 — chance)
```

The weights loaded partially and training restarted from noise. **Any warm-start path needs
a shape assertion before the first epoch**, and an epoch-1 accuracy near `1/n_classes` should
be treated as a hard failure, not a slow start.

### 1.4 Why "just train longer" is not the next lever

The training script writes best-`val_acc` weights at train-end with
`restore_best_weights=False`, alongside `EarlyStopping(patience=30)`. A longer run therefore
cannot ship a post-peak model — the ceiling is real, not an artifact of stopping early.
Separately, `CosineDecay(decay_steps=epochs*steps - warmup)` ties the entire learning-rate
schedule to `--epochs`, so a 200-epoch run is **a different experiment**, not a continuation
of the 100-epoch one. Both runs are valid; they are just not comparable as "more of the same".

---

## 2. Five root causes in the data

These were found across two independent efforts — the recognition side and the animation
side — and each one is proven, not suspected.

### R1 — GISLR records ONE hand per participant

Not a tracking failure. A property of how the corpus was collected.

```
clips with BOTH hands present :  1.7%
both-hand frames (mean)       :  0.1%
only-left / only-right        : 41.0% / 56.7%
```

**Consequence:** on every two-handed sign, the passive hand is absent in *every take*. This
cannot be selected around, so "passive hand present" can never be an acceptance criterion —
it is a constant of the dataset. The passive **wrist** is still tracked as a pose landmark,
so position is available and only the handshape must be synthesized.

### R2 — the cleaner fabricated hand data

`clean_dataset_s3.py:99` forward-fills then back-fills missing landmarks. For the word
`book`, raw hand presence is 57% and stored presence is 100%. The gap was filled with
copies of neighbouring frames.

**Consequence:** any coverage metric computed on the cleaned corpus reads high and means
nothing. All numbers in this report are computed on raw missingness.

### R3 — handedness is not derivable from these landmarks

Four classifiers were tested. The best was **AUC 0.335** — that is not weak, it is
*inverted*: the signal points the wrong way.

**Consequence:** handedness must come from a hand-written lexicon
(`asl_handedness_250.json`: 163 one-handed, 52 two-handed symmetric, 35 two-handed
asymmetric). It cannot be inferred, and code that tries will be confidently wrong.

### R4 — both sides optimized numbers the other wasn't measuring

The recognition side optimized top-1 accuracy. The animation side optimized hand coverage.
Neither metric detects the other's failure mode, so both could improve while the shared
artifact got worse. R5 is what that looked like in practice.

### R5 — MediaPipe keeps the RESTING hand *(found this session)*

The decisive finding, and the one that had been shipping silently.

The tracker preferentially loses the hand that **moves**:

```
median wrist speed, hand block PRESENT : 0.0208 sh.w./frame
median wrist speed, hand block MISSING : 0.0317
ratio                                  : 1.52x
```

(The same measurement on the pre-fix export read **4.06×**.)

The failure then compounded through three stages, each individually reasonable:

1. `extract_canonical.canonicalize()` chose which hand was dominant from **hand-block frame
   counts** — precisely what `sign_landmarks.wrist_travel`'s own docstring warns against.
   Because the tracker keeps the still hand, this canonicalized on the resting hand.
2. The exemplar selector then **maximized hand coverage**. Coverage is anti-correlated with
   motion — `pearson r = -0.464` averaged over 250 words, **negative for 100% of words** —
   so maximizing coverage actively *selects for stillness*.
3. Result: the wrong hand was selected with **99.6% precision against a 44.9% base rate**.
   The selector was not making mistakes; it was reliably optimizing the wrong thing.

The evidence had been sitting in the export the whole time: every word's metadata carried
`"required_hand": "R"` next to `"dominant": "L"`. The two fields were never compared.

**What settled it was geometry, not labels.** Hand landmark 0 *is* a wrist, so its
co-location with a pose wrist identifies the limb independent of any naming convention:

```
median distance to own limb   : 0.082 shoulder-widths
median distance to other limb : 1.783
```

That is a 20× separation — not a threshold that needed tuning.

**The corpus was never the problem.** 55.1% of takes have the tracked hand on the moving
arm, and all 250 words have at least 55 such takes (median 178). This was a selection bug
with a selection fix; no retraining was required.

---

## 3. The fix, and what it cost

A **signing-hand gate** (`sign_landmarks.hand_arm_alignment`) now rejects any take whose
tracked hand sits on the still arm, *before* any coverage or class rule is considered.

Verified against the independent acceptance script (`Fix/check-export3.py`):

| criterion | before | after |
|---|---|---|
| dominant-hand coverage | **0.4%** | **76.2%** |
| words missing the dominant hand | **249** | **1** (see §3.2) |
| exemplars carrying the signing hand | 0.4% | **100% (250/250)** |
| exemplars carrying the resting hand | 96.9% | **0.1%** |
| tracker-drop ratio | 4.06× | 1.52× |

### 3.1 The cost was coverage, and that is the correct trade

Two coverage numbers appear in this report and they are not in conflict: **76.2%** is the
acceptance script's figure, pooled over every exported frame, and **0.685** is the selector's
per-word mean measured inside the sign extent. The pooled number is higher because long,
well-tracked one-handed clips contribute more frames. Both are reported because the gate is
0.70 on the first and the second is what the renderer actually experiences per word.

Reported dominant-hand coverage **fell** from 0.962 to 0.685. That drop is the fix working:
the old 0.962 was coverage *of the resting hand*, which is easy to track because it does not
move. Coverage of the correct hand is lower and worth more.

Per class, the remaining coverage is not evenly distributed:

| class | n | coverage, sign extent | coverage, whole clip | valid takes (median) |
|---|---|---|---|---|
| one-handed | 163 | 0.829 | 0.888 | 138 |
| two-handed symmetric | 52 | 0.412 | 0.494 | 3 |
| two-handed asymmetric | 35 | 0.422 | 0.504 | 5 |
| pooled | 250 | 0.685 | 0.752 | — |

Both columns are needed because two different consumers read two different windows. The
sign-extent column is `dominant_hand_coverage` in `sign_clips_250.meta.json` and is what the
selector optimizes against. The whole-clip column is what the exporter puts in
`segments[].synthesis.dominantCoverage`, and it is the one the renderer sees. They differ by
6–8 points per class in the same direction, because the trimmed core of a sign is exactly where
the hand moves fastest and is therefore lost most often. **Three numbers now describe coverage
in this project — 0.685, 0.752 and 0.762 — and they are all correct about different windows.**
Any comparison that does not name its window is meaningless.

**One-handed signs are done.** The remaining problem is entirely the 87 two-handed words,
and its cause is pool size rather than selection: the validity filter passes 48% of
one-handed candidates but only **1% of 2s** and **2% of 2a**. With a median of 3 valid takes,
there is essentially no selection pressure left — 20 words have ≤2 valid takes and 7 have
exactly one. For those words the exemplar is not "the best take", it is "the only take".

This is structural, not a tuning miss. Two-handed signs require *both* motion (to be a valid
take) and *coverage* (to be usable), and R5 established that those two demands trade directly
against each other. Loosening the filter would raise coverage by re-admitting takes where the
passive arm is merely hanging — a worse artifact that is harder to detect.

The honest lever is at the render layer, not the selection layer: **hold or interpolate the
handshape through gaps, and declare which frames are measured**. The renderer needs a pose
every frame regardless, and `gloss_to_motion.py` now emits
`segments[].synthesis.dominantCoverage` so it knows how much holding each word requires. That
is interpolation the consumer knows about — the opposite of R2, where the fill was silent.

> The field exists in the exporter as of 2026-08-13, which means it is present only in exports
> generated *after* that date. The handoff sent before it does not carry the block, and a
> consumer reading the field there gets `undefined`. §9 of `Fix/FROM-SALIM-v7.md` ships a
> one-line check so the animation side detects a stale folder immediately instead of
> discovering it mid-renderer.

### 3.2 The one remaining failure is a definition mismatch, not a hole

`check-export3.py` reports `finish` as missing its dominant hand. It is not. The right hand
is present in 10 of 22 frames.

The cause is R4 in miniature. The two sides derive dominance differently — we use absolute
wrist travel, the acceptance script uses shoulder-relative wrist path with an elbow-present
gate — and across all 250 words those two definitions disagree on **exactly one word**:

```
words where the two dominance metrics disagree : 1/250  (finish)
finish travel ratio                            : 1.00
```

A ratio of 1.00 is a perfect tie, and `finish` is a symmetric two-handed sign, so both arms
genuinely move equally. The tie broke toward L on their side. Since canonicalization
guarantees the tracked hand is always at landmarks 54–74, reading the left block returns 0%
**by construction**.

**The fix is to stop re-deriving a guaranteed fact.** Every exemplar is right-dominant
because left-dominant signers are mirrored at extraction, and the exporter now asserts
`dominantHand: "R"` per word rather than leaving it to be inferred. The same fact has been in
`sign_clips_250.meta.json` all along as per-word `required_hand` — `"R"` for 250/250 — which is
the part that stings: the assertion the checker needed was already sitting next to the value it
disagreed with.

### 3.3 Exemplar duration

Selection is on native (untrimmed) clip length, and the tail is short:

```
duration: min 9 frames, p10 21, median 40, max 116  (30 fps)
  under 16 frames (0.53 s):  6 words
  under 20 frames (0.67 s): 20 words
```

Six words are under half a second, which is short for a legible sign. These are words whose
valid pool collapsed to one or two takes, so there was nothing longer to pick. A minimum
duration floor on the *exemplar* (as distinct from the candidate) is a cheap improvement,
but it can only help where the pool has more than one survivor.

---

## 4. Handshape synthesis for the absent passive hand

R1 means 87 words need a passive hand that was never recorded. Sign linguistics constrains
what it can be, so this is synthesis, not invention:

- **52 two-handed symmetric words** — Battison's Symmetry Condition: the passive hand
  mirrors the dominant handshape. Exact, not a guess.
- **35 two-handed asymmetric words** — Battison's Dominance Condition: the passive hand is
  restricted to the unmarked set {B, A, S, 1, 5, C, O}. This narrows the choice to seven but
  does not pick from it, so each of the 35 words was assigned a passive handshape *and* a
  contact target, since a handshape alone does not say which surface the dominant hand meets.

```
shape   : B 26, A 3, 1 3, C 2, S 1
conf    : high 18, med 11, low 6
contact : palm 14, forearm 5, back_of_hand 5, side_of_hand 3, opening 2, ...
```

B at 26/35 is a useful sanity check: Battison predicts B as the dominant unmarked base, and
that distribution fell out of the assignment rather than being imposed on it.

Handshape templates were measured from the corpus at 24 anchor words. **Six of seven shapes
measured cleanly** (`1 5 B A S C`); only `O` did not, and it resolves through a documented map
(`O→C`) rather than leaving the renderer to invent a policy. The gap this leaves is **none**:

```
2a words on a MEASURED template : 35/35
2a words on a documented fallback:  0/35
shapes requested by the 35 words : B 26, A 3, 1 3, C 2, S 1   (all measured)
templates never requested        : 5, O      -> only 5 of 7 are reachable here
resolution map entries that fire :  0        -> S->S and O->C are both dead code
```

> **Corrected 2026-08-14.** This block previously read "five of seven measure cleanly", "`S` and
> `O` did not", "34/35", and defended an `S→A` substitution on the grounds that `S` and `A` are
> both unmarked fists. All of it was stale: the `S` anchor fix landed (`agreement_xy` 0.1636,
> n=40, `usable: true`), `S` resolves to itself, and `time` — the word the fallback existed for —
> is on a measured template like every other. The `S→A` defence described a substitution that
> does not happen. Adding vocabulary can re-activate `O→C`; nothing on the current 250 does.

**All 35 assignments are NOT DEAF-REVIEWED.** They are written from published descriptions
to unblock the rig. Three things are flagged for a reviewer rather than smoothed over:

- **5 words contact the FOREARM, not a hand** (`arm`, `flag`, `morning`, `table`, `tree`).
- **`chair` and `helicopter` have passive handshapes outside the unmarked set** (H and 3).
  Either casual signing violates the Dominance Condition there, or the `2a` class label is
  wrong for those two.
- **6 rows are `conf: low`** — my confidence in the assignment, tracked separately from the
  lexicon's confidence in the *class*, so a reviewer can see which rows are guesses.

---

## 5. Two acceptance criteria that should change

**`per-landmark confidence present` cannot be satisfied and should be dropped.** GISLR
carries no per-landmark confidence, and nullness already encodes visibility exactly — a
fourth component would be a constant function of the first three. A criterion that can never
pass is not a criterion.

**`passive hand present` likewise cannot be satisfied** (R1) and is already correctly
reported as informational rather than as a failure.

---

## 6. Known-good, and known-open

**Verified working**

- Recognition at 0.7590 top-1, participant-split, 250 words.
- 250/250 exemplars carry the signing hand, geometrically verified.
- Chirality is consistent: the signer's right shoulder is at smaller x in 100% of frames, so
  the export is raw camera orientation and *not* selfie-mirrored. This survives
  canonicalization because `x`-negation and the pose L/R swap together preserve the
  `RSH.x < LSH.x` ordering.
- No hand block is encoded as 21 zeros — a missing hand is `null`, so nothing draws at
  mid-sternum.
- Clip durations are native, not padded to a uniform 64.
- Every two-handed word has a passive wrist trajectory and a synthesis class.

**Open**

| item | owner | note |
|---|---|---|
| Two-handed coverage ~0.42 | render layer | needs declared hold/interpolation, not better selection |
| 20 words with ≤2 valid takes | data limit | no selection pressure available |
| 6 exemplars under 0.53 s | data limit | pool collapsed to one take |
| 50-word handedness review | Deaf reviewer | plus the 6 low-conf + 2 outside-unmarked passive shapes |
| Mask the resting-hand block during training | next GPU run | see below |
| Face landmarks into the freed 33–53 block | later phase | canonicalization emptied it |

**The next recognition lever is masking, not epochs.** On the ~45% of training clips where
the populated hand block is the resting hand, that block is noise in the handshape channel
with a label attached. NaN-ing it out keeps all 80,647 samples while removing the misleading
signal — a better bet than a longer run, for the reasons in §1.4.

---

## 7. Methodological notes

Two failure modes recurred often enough to be worth naming, because both produced
false confidence rather than visible errors:

**A check that cannot fail is indistinguishable from a check that passes.** This happened
twice in one session. A probe compared two corpora that turned out to have the same layout,
so it could neither pass nor fail — and it reported "no regression". A staleness check named
only symbols that the *old* code also contained, so a stale build ran silently and produced
byte-identical output that was read as a successful re-run. Both were mine. Any assertion
worth writing should be run once against the case it is meant to catch.

**Prefer geometry to labels.** Every naming-convention argument in this project (which hand
is "dominant", which block is "left", whether the image is mirrored) was settled quickly and
permanently by measuring a distance instead of trusting a field name. R5 sat undetected
inside two metadata fields that contradicted each other on every one of 250 words.
