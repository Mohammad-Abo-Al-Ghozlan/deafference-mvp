# Master fix plan — 2026-08-11

Every known defect in the ASL↔speech pipeline, what causes it, whether it is fixable, and in
what order. Written after the day's root-cause work, which collapsed a dozen separate symptoms
into **four** real causes.

Owners: **DP** = data pipeline (Salim) · **AN** = animation/retargeting · **DEAF** = Deaf reviewer

---

## 0. The four root causes

Almost everything below is a symptom of one of these.

| # | Root cause | Fixable? |
|---|---|---|
| **R1** | **GISLR records ONE hand per participant.** Both hands live in 1.7% of clips; frames with both hands: mean 0.1%, max 4.8%; 14/21 participants have *every* clip single-handed. Measured against the raw competition parquets, so it is not our extraction. | **No.** Mitigate by synthesis. |
| **R2** | **The cleaner gap-filled the corpus** (`clean_dataset_s3.py:99`, ffill+bfill per landmark). Turns "detected once" into "present in every frame": `raw 9% → stored 32%`, `raw 57% → stored 100%`. | **Yes — done.** |
| **R3** | **Handedness was inferred from landmarks.** Four classifiers tested against 40 hand-labelled words: path-length ratio AUC **0.335** (inverted), extent ratio 0.460, passive height 0.468, weak-hand presence 0.500. It is not in the data. | **Yes — done.** Supply it lexically. |
| **R4** | **Both sides optimized numbers the other side wasn't measuring.** Zeros-vs-NaN, `min` vs `0.7/0.3`, coverage-as-quality vs coverage-as-ever-detected. | **Yes** — by writing the postcondition down and checking it on the output. |

### The consequence nobody had stated

Under R1, **for all 87 two-handed words the passive hand's landmarks do not exist in any take.**
No selector, threshold, or metric changes that. But the loss is narrower than it first looks:

> **The passive WRIST is always available.** It is a *pose* landmark (11–16), and pose wrists are
> present in 3192/3192 frames measured. So the passive hand's **position** is known every frame;
> only its **handshape** is missing.

That converts the renderer's problem from "invent a hand" to "**place a known-position hand and
supply a handshape**", which Battison's conditions make tractable:

* **symmetric (52 words)** — same handshape on both hands → mirror the dominant handshape onto the real passive wrist position. Exact, no assumption.
* **asymmetric (35 words)** — passive hand is restricted to an unmarked handshape (B, A, S, 1, 5, C, O) → pick from that closed set, positioned at the real passive wrist.
* **one-handed (163 words)** — nothing to do.

### And his travel ratio finally gets a job it can do

AN measured wrist-travel ratios on the 250 exported clips and found symmetric signs signing as
one-handed: `owl` 0.27, `stairs` 0.20, `tiger` 0.28, `alligator` 0.54. He read this as an
arbitrary draw. It is really **weak drop** — a productive ASL process where signers drop the
passive hand in casual signing, and GISLR is crowd-sourced caretaker signing, so it is rampant.

The ratio failed as a *classifier* (R3) because it was being asked to infer handedness. Given
handedness **externally** from the lexicon, the same number becomes a **validity filter**:

```
lexicon says 2s  +  this take's passive-arm ratio is 0.27   ->  weak-drop take, reject
lexicon says 1   +  this take's passive-arm ratio is 0.95   ->  wrong/odd take, reject
```

His measurement plus our lexicon is worth more than either alone. That is the plan's core.

---

## 1. Status of every known defect

### Data layer

| ID | Defect | Cause | Status |
|---|---|---|---|
| D1 | Passive handshape absent for all 87 two-handed words | R1 | **Unfixable.** Synthesis, §2 |
| D2 | Frozen forward-filled hands in export and training data | R2 | **Fixed** — `extract_canonical.py --variants none` |
| D3 | 21 of 75 point slots reserved for a hand never recorded | R1 | **Fixed** — dominant hand parked at 54–74, 33–53 reserved for face |
| D4 | Model had to learn invariance to *which* block holds the hand | R1 | **Fixed** — canonicalized + `FLIP_MAP_CANON` |
| D5 | `/kaggle/working` wiped between sessions; corpus lost once already | process | **Mitigated** — commit runs only, new dataset name every time |

### Selector layer

| ID | Defect | Cause | Status |
|---|---|---|---|
| S1 | Coverage is binary 1.00/0.00 — measures "ever detected", not quality | R2 | **Fixed** by D2; re-select on the `none` variant |
| S2 | `argmax(coverage)` ≈ `argmax(stillness)`; within-word r = **−0.214**, negative on 100% of words | — | **Fixed** — `--travel-floor median` |
| S3 | Circular handedness: the candidate decided its own requirement → free 1.000, fake 99.4% | R3 | **Fixed** — per-word, then superseded by the lexicon |
| S4 | Truncated takes game the fraction (15 picks under 12 frames) | — | **Fixed** — `LENGTH_FLOOR_FRAC 0.60` |
| S5 | Strict `min` ranked a perfect dominant below a mediocre pair | R4 | **Fixed** — `0.7·dom + 0.3·passive` both sides |
| S6 | Coverage scored over the whole window, not the sign extent | — | **Fixed** |
| S7 | **Weak-drop takes selected for two-handed signs** (`owl` 0.27, `stairs` 0.20) | — | **OPEN — §3 step 2** |
| S8 | Handedness split unknown: 195/55 → 160/90 → lexicon says 163/87 | R3 | **Fixed** — lexicon, 91% agreement with AN's independent labels |

### Contract / renderer layer

| ID | Defect | Cause | Status |
|---|---|---|---|
| C1 | 19,002 hand blocks exported as `[0,0,0]` instead of `null` | R4 | **Fixed & verified** with AN's own script |
| C2 | x-axis documented as selfie-mirrored; it is raw camera | R4 | **Fixed** — measured on 15,877 frames |
| C3 | `segments` were placeholders | — | **Fixed** — real `motion_extent` |
| C4 | `check-export.py` used strict `min` while we optimized `0.7/0.3` | R4 | **Fixed by AN** — `check-export1.py`, `degraded` taxonomy added |
| C5 | **Acceptance criteria can never pass for 87 words** — they demand a hand the corpus lacks | R1 | **OPEN — §3 step 1.** Needs a new criterion, not a better export |
| C6 | AN does not yet know the passive wrist position *is* available | — | **OPEN — §3 step 1** |

### Model layer

| ID | Defect | Cause | Status |
|---|---|---|---|
| M1 | `--init-from` silently skipped `stem_dense` (needs 650 in, weights have 450) and `classifier` (768 vs 384). Epoch-1 acc 0.0049 ≈ 1/250 = chance | — | **Sidestepped** — from-scratch arms; still to be documented |
| M2 | No honest baseline: 0.7755 and 0.7544 both used the broken init and a different LR | M1 | **In progress** — arm A |
| M3 | Augmentation A/B came back flat (0.7492 vs 0.7544) | R1 | **Explained.** Augmentation cannot recover an absent channel |
| M4 | Feature extractor computes 45 passive-hand + 10 cross-hand distances that are always 0 — **55 of 100 extra dims dead** | R1 | **OPEN — §4.** Deliberately deferred: one variable at a time |
| M5 | No face landmarks (no non-manual markers: negation, questions, adverbials) | — | **OPEN — Phase 1.** Slots 33–53 now free |

### Process

| ID | Defect | Status |
|---|---|---|
| P1 | Lexicon not reviewed by a Deaf signer — 45 `med` + 7 open disagreements | **OPEN — blocking correctness, not progress** |
| P2 | Exemplars never reviewed by a Deaf signer | **OPEN** |
| P3 | Findings not in `docs/` | **OPEN — §5** |

---

## 2. What the animation side needs from us

In the order he needs it:

1. **The within-word correlation.** Measured: **r = −0.214 mean, −0.220 median, negative on 100% of 250 words.** His §3 mechanism is real; the travel floor is in and on by default. *He asked for this before the export and has been waiting.*
2. **The R1 finding, with numbers.** His §3 ("these clips don't show their own signs") and his §4 ("only 3 paired frames for symmetric signs") are **two independent detections of the same root cause.** He got within one measurement of it from the export side; we confirmed it from the source side. He must not spend another day building detectors against a corpus that cannot support them.
3. **That the passive wrist position is available.** This is the piece that unblocks his renderer. He is planning to synthesize a whole hand; he only needs a handshape.
4. **The lexicon**, plus the 91% agreement and the 7 open disagreements. `table` conceded to him.
5. **A new acceptance criterion (C5).** His current criteria will fail forever on 87 words. Proposed: split the check into `dominant-hand coverage` (must pass) and `passive hand present` (reported, expected to fail for 2s/2a, satisfied by synthesis).
6. **A retraction.** We reported 99.4% coverage from a circular metric. It was withdrawn before it reached him, but he should know it happened and why.

And one thing we need from him: **run `symmetry-test.py` and `handedness-groundtruth.py` on the new exemplars.** He is right that they are currently unanswerable — but he is expecting re-selection to produce paired frames "in quantity". Under R1 it will not. He should see the R1 numbers before he spends the run.

---

## 3. The plan

### Step 0 — in flight (today)
* Commit run: extract → arm A (legacy, from scratch) → arm B (canonical). ~5.5 h. **M2**
* Save the output under a **brand-new** dataset name. **D5**

### Step 1 — tell AN everything (today, no compute) — **highest value per hour**
Send items 1–6 from §2. He is currently building against a corpus that cannot answer his
questions, and every hour of that is wasted. **C5, C6**

### Step 2 — selector v7 (½ day) — **S7, S8, S1**
1. Read handedness from `asl_handedness_250.json`; delete the landmark inference entirely.
2. **Weak-drop rejection**: for `2s` words require the passive-arm travel ratio ≥ 0.60; for `2a` require the passive wrist to be *held* (low travel, in signing space) — that is what an asymmetric base looks like; for `1` words reject ratio ≥ 0.85 as a suspicious take. This is AN's measurement doing the job it can actually do.
3. Re-select from the **`none`** variant so coverage means real tracker presence. **S1**
4. Score `dominant` coverage only — the passive hand is known-absent, so including it just adds a constant.
5. Emit per word: `class`, `confidence`, `passive_wrist` track, `synthesis_required`, `weak_drop_rejected`.
6. Re-run `check-export1.py`; expect `degraded` ≈ 87 and **that is correct**, not a failure.

### Step 3 — Deaf review (blocking correctness) — **P1, P2**
Two lists, in this order:
1. **45 `med` + 7 disagreements** from the lexicon — `cry`, `happy`, `hate`, `sick`, `smile`, `talk`, `go`, `same`, `fast`, `sad`, `toy`, `napkin`, `shower`, `cut`, `owie`, `refrigerator`.
2. **AN's suspect-clip list** — `owl`, `stairs`, `tiger`, `alligator`, `book`. If those are representative, exemplar validity outranks handshape coverage, and no automated check either side owns can see it.

Neither list should be resolved by two hearing developers arguing. AN said the same thing independently; we agree.

### Step 4 — model, after the A/B reads out
* If arm B wins: adopt canonical, then **M4** — replace the 55 dead feature dims with something real. That is a second, independent lever we currently leave on the table.
* If arm B loses: `canon/ffill` is already on disk; one run isolates whether the layout or the gap-fill removal hurt.
* Either way, document **M1** so nobody warm-starts from `backbone_250.weights.h5` again.

### Step 5 — Phase 1, face landmarks — **M5**
Slots 33–53 are free and 21 points is the right budget for lips + brows. Extraction is one flag
in `extract_canonical.py` since it already reads the raw parquets, which carry all 468 face
points. This is the next real accuracy lever after canonicalization, and it is the only route to
non-manual markers — negation, question marking, adverbial mouth morphemes — which the current
model cannot represent at all.

### Step 6 — docs — **P3**
`MODEL_250_MVP_REPORT.md`: the R1 measurement, M1, arm A/B numbers.
`SIGN_ANIMATION_CONTRACT.md`: synthesis requirement, passive-wrist availability, new criteria.

---

## 4. What we are deliberately NOT doing yet

| Not doing | Why |
|---|---|
| `max(L,R)` for symmetric signs | AN's argument is sound but it is only as safe as the sym/asym classifier, and 7 labels are still open. `0.7/0.3` degrades gracefully under the same error; `max` does not. He reached this conclusion independently — agreed. |
| Fixing the 55 dead feature dims (**M4**) | Two variables already move in the current A/B. Adding a third would make the result uninterpretable. |
| Shrinking to 54 points | Keeping 75 makes Phase 1 a drop-in with no architecture change. |
| A new dataset for 1000 words | Nothing here scales until R1's mitigation is proven on 250. |

---

## 5. The one lesson worth keeping

Both sides shipped a **silent success report**. Ours printed `250/250 clean` from a warning that
could not fire, then `99.4% coverage` from a metric that scored our own choice back at us. Theirs
wrote `dominantHand = 'right'` and never tested it. Neither was caught by a check. Both were
caught by the other person asking about one number that looked odd.

Every guard added since asserts on the **output**, not the intent — and prints what the
alternative strategy would have produced, so it cannot quietly report success.
