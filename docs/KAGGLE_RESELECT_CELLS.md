# Kaggle runbook — the 2a exemplar re-selection A/B

**Written 2026-08-26.** Ready-to-paste cells. CPU only, no GPU quota, ~35 min.
Supersedes the cells in [`KAGGLE_EXEMPLAR_RESELECT.md`](KAGGLE_EXEMPLAR_RESELECT.md) Part A;
that file's *reasoning* still stands and is worth reading first. Part B (the 29302 question)
is unchanged — run it from the old doc if you want it.

## What changed from the old cells, and why

Three fixes. The first would have wasted a run outright.

1. **The file list was incomplete.** It named 4 files. `build_sign_clips.py:59` does
   `from train import load_dataset` (and `:477` `from train import time_resize`), so with only
   those 4 staged flat into `/kaggle/working`, Cell 3 dies at import:
   `ModuleNotFoundError: No module named 'train'`. Verified locally by staging exactly those 4
   files and running the builder. **Six files now.**

2. **Half the old acceptance test could not fail.** It read "2a valid candidates rises 5 → ~130
   **and** coverage rises" as success. But with the gate off, 2a has *no* 2a-specific rule left:
   the travel floor at `build_sign_clips.py:362` is `cls == "2s"` and the ceiling at `:350` is
   `cls == "1"`, so `valid == aligned`, and `:346` states every word has ≥55 aligned takes. The
   pool rise is arithmetic. On a synthetic corpus the 2a pass rate went **43% → 100% with
   coverage moving +0.000** — a "success" on half the criterion, and a null result in fact.
   `measure_reselect.py` prints it labelled as arithmetic and verdicts on **coverage alone**.

3. **The run can now predict its own result, from the control arm.** `--dump-candidates` writes
   one row per candidate before the losers are discarded, and `measure_reselect.py --dump`
   compares dominant-hand coverage between the takes the gate **cuts** (passive wrist hanging)
   and the ones it **keeps** (held). Run it after Cell 3 — you will know the answer before the
   test arm finishes.

   Why that comparison and not another: root cause R5 is that MediaPipe drops the hand that
   *moves* and struggles most when two hands occlude. A passive hand held **up** sits near the
   dominant hand; a hanging one is out of the way. If that dominates, the gate is selecting
   *for* occlusion and therefore *against* the very coverage the selector maximizes.

   It is not checkable from the shipped per-word meta: every selected 2a exemplar passed the
   gate, so `passive_resting` is False on **35 of 35** — no variance in the predictor. Class 1,
   which never reaches the gate, is 161 hanging / 2 held, so no variance there either. The
   comparison exists *only* among rejected takes, which is why the dump was added.

## Scope correction

Recomputed from the shipped `sign_clips_250.meta.json`: the gate stays **on** for 2s, so only
the **35** 2a words are touched, and **11 already clear 0.50** coverage. **24 words** is the
entire upside — not the 39 that "39 degraded words" suggests. The old doc's baseline does
reproduce (survival 47.3 / 1.1 / 2.0% against its 49.0 / 1.2 / 2.1%), so the premise holds; only
the scope is smaller. Also confirmed: **0 words** are on a `validity_fallback`, so the gate
really is constraining every 2a selection.

---

## Inputs

| dataset | notes |
|---|---|
| **`asl250-canon-v1-REFUTED`** | the corpus. Yes, that one — canonicalization was refuted as an *accuracy* lever, not as hand identification. `build_sign_clips.py:243` needs `left_dead > 0.99` to read a canonical layout, and this corpus measures 1.000. Carries `split_manifest.parquet` + `by_word/`. |
| **a new code dataset** — name it `asl250-anim-v2` | six files, listed below |

⚠️ **Never drag the repo root or any folder** — it contains `.env` and a Kaggle dataset would
publish it. Add the **six files individually**, two at a time, **Private**.

```
training/build_sign_clips.py     the builder, with --require-passive-up and --dump-candidates
training/train.py                REQUIRED — build_sign_clips imports load_dataset from it
sign_landmarks.py                repo ROOT, not training/
measure_reselect.py              repo ROOT — the analysis
vocab_250.json                   frozen class order
asl_handedness_250.json          the handedness lexicon
```

Settings: **CPU** (no accelerator), Internet **off**.

---

## Cell 1 — stage, and refuse to run on a stale build

```python
import os, glob, sys, shutil, json

NEED = {
    "build_sign_clips.py": ("2s-only", "dump-candidates", "gate_on"),
    "train.py":            ("def load_dataset", "def time_resize"),
    "sign_landmarks.py":   ("hand_arm_alignment", "required_hand_coverage",
                            "mirror_match", "_passive_is_resting"),
    "measure_reselect.py": ("cliffs_delta", "mannwhitney_p"),
    "asl_handedness_250.json": ("passive_handshape",),
    "vocab_250.json":      (),
}

def missing(d):
    out = []
    for f, marks in NEED.items():
        p = os.path.join(d, f)
        if not os.path.exists(p):
            return None                      # not a candidate at all
        t = open(p, encoding="utf-8", errors="ignore").read()
        out += [f"{f}:{m}" for m in marks if m not in t]
    return out

# Only DATASETS. A notebook OUTPUT can also contain build_sign_clips.py, and glob order is not
# stable -- that is exactly how an earlier session silently selected a stale train.py and made
# both arms of an A/B identical.
cands = sorted({os.path.dirname(p) for p in
                glob.glob("/kaggle/input/**/build_sign_clips.py", recursive=True)
                if "/notebooks/" not in p})
good = []
for d in cands:
    m = missing(d)
    print(("  [current] " if m == [] else "  [reject ] ") + d, "" if m == [] else m)
    if m == []:
        good.append(d)

assert len(good) == 1, (
    "need exactly 1 code dataset holding all SIX files with the current flags. "
    "'dump-candidates' must appear in build_sign_clips.py -- if it does not, you uploaded a "
    "builder from before 2026-08-26. 'train.py' missing is the other likely cause: the old "
    "runbook listed only 4 files and the builder imports load_dataset from train.")
CODE = good[0]
for f in NEED:
    shutil.copy(os.path.join(CODE, f), f)
sys.path.insert(0, ".")
print("\nstaged:", sorted(NEED))
```

## Cell 2 — find the corpus and prove it is the canonical one

```python
import numpy as np, random
from sign_landmarks import canonicalize_missing

roots = sorted({os.path.dirname(p) for p in
                glob.glob("/kaggle/input/**/split_manifest.parquet", recursive=True)})
roots = [r for r in roots if os.path.isdir(os.path.join(r, "by_word"))]
print("corpus candidates:", roots)
assert len(roots) == 1, "need exactly 1 corpus with split_manifest.parquet + by_word/"
DATA = roots[0]

fs = sorted(glob.glob(os.path.join(DATA, "by_word", "*", "sequences.npz")))
random.seed(0); random.shuffle(fs)
ld = []
for f in fs[:40]:
    z = np.load(f)
    for k in list(z.keys())[:5]:
        a = canonicalize_missing(z[k].astype("float32"))
        if a.shape[1] < 75:
            continue
        ld.append(float(not np.isfinite(a[:, 33:54, :2]).all(-1).any()))
print(f"{DATA}\n  left_dead {np.mean(ld):.3f}   (build_sign_clips needs > 0.99 for CANONICAL)")
assert np.mean(ld) > 0.99, "not the canonical corpus — the builder would read it as LEGACY"
```

## Cell 3 — the CONTROL arm

```python
!python build_sign_clips.py --data-dir {DATA} --vocab vocab_250.json \
    --lexicon asl_handedness_250.json --require-passive-up on \
    --dump-candidates /kaggle/working/cand_control.csv \
    --out /kaggle/working/clips_control.npz
```

Do not skip it. The shipped `sign_clips_250.meta.json` was built on a different day from a
corpus that no longer exists, so comparing against it would confound the flag with whatever else
differed. **Two arms, one session, one variable.**

## Cell 4 — the prediction, before the test arm runs

```python
!python measure_reselect.py --dump /kaggle/working/cand_control.csv
```

Read the **class 2a** block. `HANGING (gate cuts)` scoring materially above
`HELD (gate keeps)` — Cliff's delta above +0.15 — means the gate is discarding the
better-tracked takes and Cell 5 should show a gain. No material difference means expect tier C
to hold. Cliff's delta is reported next to the p-value on purpose: with a few thousand
candidates a p-value only says "not exactly zero".

## Cell 5 — the TEST arm

```python
!python build_sign_clips.py --data-dir {DATA} --vocab vocab_250.json \
    --lexicon asl_handedness_250.json --require-passive-up 2s-only \
    --dump-candidates /kaggle/working/cand_2sonly.csv \
    --out /kaggle/working/clips_2sonly.npz
```

## Cell 6 — the acceptance test

```python
!python measure_reselect.py \
    --control /kaggle/working/clips_control.meta.json \
    --test    /kaggle/working/clips_2sonly.meta.json \
    --dump    /kaggle/working/cand_control.csv
```

The **load-bearing line is `[ok] 2s unchanged`**. `2s-only` must change nothing for 2s; if it
moved, the gate is not scoped per class and the 2a number means nothing. `[ok] class 1
unchanged` is a second free invariant — class 1 returns before the gate is ever reached.

That check was tested for its ability to *fail*, not just to pass: run with `off` as the test arm
it correctly reports 2s moving 0.689 → 0.844. This project has already shipped one check that
could not fail (the "250/250 clean" claim), which is why the negative case was run.

**Bar, set before the run:** 2a median coverage **+0.15** or better is RECOVERABLE. A smaller
positive number is a gain, not a fix — the script says so rather than letting the bar drift.

## Cell 7 — save

**Version → Output → New Dataset → `asl250-anim-reselect-v1` → Private.**
Brand-new name, **never onto an existing dataset**. Both `.npz`, both `.meta.json` and both
candidate CSVs are in the output.

---

## If it says RECOVERABLE

⚠️ It changes the 35 2a word files, breaking the "byte-identical" promise in
`Fix/REPLY-TO-GHOZLAN-v9.md` §0.1. **Tell the animation side before they build on it.** The
re-export is local and takes a minute:

```
python gloss_to_motion.py --per-word --out-dir animation_handoff
```

## If it says NOT recoverable

That closes the question rather than leaving it open, which is worth the 35 minutes. The
remaining levers for the two-handed words are then `asl_2a_base_placement.json` (already
authored, never Deaf-reviewed) and the short-gap hold — **550 of 776 dominant-hand gaps are 1–3
frames**, and holding the last handshape instead of relaxing recovers 1177 frames, 45.4% of all
missing. That one is the animation side's fix and it touches all 250 words.
