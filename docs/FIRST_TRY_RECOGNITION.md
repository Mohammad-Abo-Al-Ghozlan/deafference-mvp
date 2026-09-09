# Making a sign work on the FIRST attempt

**Measured 2026-09-09.** The goal is a demo where signing a word once is enough. This
records what actually stops that, in the order the measurements found it.

Everything here is on the 1,373-clip held-out test split (9 unseen signers) with the
shipped 4-fold medical ensemble, masking bit-identical to `live_demo._mask_probs`. Every
run reproduced the published unmasked **0.8383** first — the frame-rate sweep matched the
cached probabilities at **max |diff| = 0.000e+00**, so the pipeline is verified rather
than assumed.

---

## The number the goal reduces to

"I do not want to repeat it" is **first-try success**. Decomposed at the shipped
τ=0.80 on the boot topic (intake27, 665 answerable clips):

```
spoken on the FIRST try     467   0.7023
HELD for a tap              151   0.2271   <- the safety gate, by design
SILENT, model unsure         47   0.0707   <- the actual repeat tax
```

**The "29% need repeating" figure quoted before this was wrong** — it counted safety
holds as failures. Only 7% is the model being unsure, and 42 of those 47 clips already
had the right word at the top. On the signs the gate is not going to hold, first-try
success was **0.9086**.

## 1. Vocabulary size is the dominant lever — and it inverts the obvious plan

Same model, same signers, same clips. Only the mask differs:

| vocabulary | first-try @ τ=0.80 | precision | wrong spoken |
|---|---|---|---|
| **intake27** | 0.9086 | 1.0000 | 0 / 467 |
| **ship55** | 0.7728 | 0.9983 | 1 / 575 |
| **all123, open** | **0.4957** | 0.9895 | 6 / 572 |

On the open vocabulary **half the signs do not come out on the first try.** So a domain
mask is not a later specialisation of a working general demo — it is the mechanism that
makes first-try reliability exist at all. The 250-word model is the *harder* target, not
the easier one: 0.7755 on unseen signers against medical's 0.8383 on three times as many,
on crowd-sourced phone video rather than studio capture.

## 2. LEVEL 1a — fold agreement, free on a narrow mask

The ensemble runs four folds and averages them into one number, discarding whether they
agreed. Agreement is evidence independent of magnitude, so requiring it lets the
confidence bar drop without letting errors through:

| mask | `mean ≥ 0.80` | `3/4 folds + mean ≥ 0.60` |
|---|---|---|
| intake27 | 0.9086, **0 wrong** | **0.9572, 0 wrong** |
| ship55 | 0.7728, 1 wrong | 0.8817, 5 wrong |
| all123 | 0.4957, 6 wrong | 0.6534, **23 wrong** |

**+0.049 first-try for nothing at 27 words; at 123 the same relaxation quadruples the
wrong words.** Shipped as `AGREE_K=3 / AGREE_CONF=0.60 / AGREE_MAX_VOCAB=30`, gated on
mask size, with a selftest that fails if the bound is widened. Unreachable from the
fold-0 preview path, which measures no agreement.

> **Refuted on the way:** "accumulate the repeat" — average attempt 1 and 2 instead of
> re-rolling. It *loses*: 97.7% resolved within two tries by re-rolling against 93.3% by
> accumulating. Averaging drags a good second attempt back toward the failed first.
> Today's behaviour was already right.

## 3. The demo runs at ~7 fps and every published number was at 30

`CORPUS_FPS = 30`; the clips are stored time-resized to 64 frames. Simulating the capture
rate by subsampling and rebuilding to `MAX_LEN`:

| fps | frames | STRETCH (was) | NaN-PAD (now) |
|---|---|---|---|
| 30 | 64 | 0.8383 | 0.8383 |
| 15 | 32 | 0.8281 | — |
| 10 | 21 | 0.8230 | 0.8332 |
| **7** | **15** | **0.8150** | **0.8296** |
| 5 | 11 | 0.8055 | 0.8216 |

Two findings. The rate costs **−0.0233** unmasked at 7 fps; and **+0.0146 of that was a
bug, not physics.** `live_demo` stretched every short clip to 64 frames with
`time_resize`, where training's `fit_to_maxlen` **NaN-pads** and `train.py:305` builds a
per-frame mask from `~is_nan` — padded clips are a first-class trained input, and the
0.7–1.4× resample in `augment` puts roughly half of all augmented clips under 64 frames.
Stretching was this file's own invention.

It matters most where the demo lives. At 7 fps on intake27, first-try goes 0.8889 →
0.9066 at the shipped gate and 0.9357 → **0.9533** at LEVEL 1a — **with precision back to
1.0000.** Stretching at 7 fps was the one configuration in which LEVEL 1a let a wrong word
through, so **the gate change is only safe together with the padding fix.** That is the
reason the frame-rate check ran first.

> **Do not repeat the velocity explanation for why stretching loses.** It runs the wrong
> way: interpolating 15 frames up to 64 *preserves* the per-frame delta scale the model
> trained on, where padding leaves it ~4× too large. Interpolation also destroys real
> detail — 64 frames carrying 15 knots — and that evidently costs more. The mechanism is
> not established; the ordering is, at three rates and three masks.

The residual **−0.0087** is genuine capture-rate loss and no inference change reaches it:
the shipped folds were trained with `DECIMATE_P = 0.0` and have never seen a decimated
clip. Recovering it needs a retrain with `--decimate`, where the 250-word model measured
+0.0218.

## 4. The real wall was segmentation — and the defect was INSERTIONS

`live_demo` starts a segment when a hand persists and ends it on stillness / hands down /
a length ceiling, previewing from *segment start* to now. In fluent signing no boundary
fires, so that window grows to span several signs and the preview classifies a clip that
is no longer one word.

`--window` never asks where a sign begins: it classifies the last W frames continuously
at three window lengths and speaks the **peak** of each agreement run.

**Harness** (`window_ab*.py`, scratch): 3-sign utterances built from held-out clips of one
signer at 7 fps, real durations from `semlex_metadata.csv` (median 1.94 s, p10 1.22, p90
3.25 — the stored tensors are all 64 frames and a uniform-length corpus would hand a fixed
window a free win), intake27's 22 speakable words, 62 utterances over 2 seeds. Score is
utterances delivered **exactly** right, plus the precision of everything spoken. **ORACLE**
is handed each sign's true boundaries — the ceiling no segmenter can pass.

| condition | ORACLE | today | `--window` |
|---|---|---|---|
| no gap at all | 52/62 p1.00 | **4/62 p0.68** | **36/62 p0.98** |
| 0.30 s pause | 52/62 p1.00 | 6/62 p0.64 | **48/62 p0.98** |
| 0.50 s pause | 52/62 p1.00 | 4/62 p0.63 | 42/62 p0.94 |
| 0.50 s hands down | 52/62 p1.00 | 4/62 p0.63 | 45/62 p0.95 |

**`--window` with no pause beats the default with the 0.5 s pause the docs ask for, 36/62
against 4/62.**

The default's defect was not missed signs — recall was already 0.79–0.85 against the
oracle's 0.89. It **spoke 115–135 words for 93 intended.** `COOLDOWN_SEC = 0.40` is 3
frames at 7 fps and cannot stop an overlapping window re-emitting the same sign. Adding
1.4 s of post-commit silence and a 2.9 s same-word refractory took precision 0.78 → 0.98.
Suppression arms only when a word was really *spoken*, so a safety hold does not blank the
next 1.4 s.

### Two corrections to how this was measured

* **Recall alone is the wrong metric** and an earlier "% of headroom closed" line was
  nonsense: both arms can emit several words per sign, so recall *exceeds* the oracle in
  some conditions while precision collapses. Exact-utterance and precision are the honest
  pair.
* **The first harness was broken and the K=1 control caught it** — it returned 0.625 for
  *both* arms, identical, which cannot be a segmenter difference. Two confounds: safety
  holds were counted as misses (5 of 27 words can never be spoken, capping recall near
  0.815), and there was no ceiling to read deltas against. With both fixed, the oracle at
  K=1 returns 0.875 / precision 1.000 — matching the 0.9066 per-clip reference, which is
  what says the harness is now measuring the right thing.

### 🔴 Why `--window` is not the default

The utterances **concatenate isolated clips, so they contain no movement epenthesis** —
the transition frames where the hand travels from one sign to the next. Real fluent
signing has them; Sem-Lex, GISLR and ASL Citizen have none. So the "no gap" condition is
*not* fluent signing and is easier than it. The offline win is large and consistent across
both seeds and all four conditions, but it cannot settle the real question. **One camera
session promotes it.**

Also unchanged: even perfect boundaries leave 10 of 62 three-sign utterances with an error
(oracle 52/62). That is the recogniser's own limit at 7 fps, not the segmenter's.

---

## Where the remaining accuracy is

Not in the model — intake27 is at 0.985 masked. In order:

1. ~~vocabulary narrowing~~ done, and it is the biggest single lever
2. ~~fold agreement~~ done (+0.049, narrow masks only)
3. ~~temporal handling~~ done (+0.0146 at 7 fps)
4. **retrain with `--decimate`** — the only route to the residual −0.0087, ~+0.02 by the
   250-word precedent
5. **more signers per word** — the clips-per-sign curve measures +0.034 for the same clip
   budget spread across more signers, and ~16 clips/word as the working figure. That is a
   recording session, blocked on task 10 (a fluent Deaf signer / medical interpreter).

## Reproducing

```bash
python live_demo.py --medical --selftest          # LEVEL 1a bound + fit_to_maxlen + predict_batch
python live_demo.py --medical                     # default segmenter
python live_demo.py --medical --window            # confidence-peak segmenter
```

The measurement scripts (`fps_check.py`, `fps_report.py`, `first_try.py`,
`gate_generalises.py`, `window_ab.py` … `window_ab4.py`) are session scratch, not shipped:
they depend on cached probability dumps. The findings they produced are the tables above
and the constants in `live_demo.py`, both of which carry their own numbers.
