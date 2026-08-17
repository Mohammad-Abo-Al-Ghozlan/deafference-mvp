# GPU notebook — canonical rebuild + retrain (commit 1)

> # 🛑 THIS RAN 2026-08-14. THE RESULT WAS NEGATIVE. DO NOT RE-RUN IT.
>
> The run executed exactly as designed — `left_dead 1.000`, `hand_nan 0.307`, `aligned 60.0%`,
> `both_blocks 4.2%`, 41/41 geometry checks green, smoke line `layout = CANONICAL | hflip swaps
> hands = False | hand-drop blocks = 1`. This was **not** a plumbing failure.
>
> **Acceptance test failed.** Mean delta on 34503 / 32319 / 29302 = **−0.0064**, against a bar of
> +0.02. The four *unaffected* signers moved **−0.0067** — statistically the same amount, so
> there was **no differential effect at all**. 29302, the both-blocks signer the entire theory
> was built to rescue, moved **−0.0002**. Pooled 0.6591 vs 0.6656.
>
> **Hand-block layout correlates with the per-signer spread but does not cause it.**
>
> ⚠️ **The "affected signers down → try `--unaligned hand`" row in the decision table at the
> bottom of this file is WITHDRAWN.** It assumed some differential signal to chase; zero was
> measured. That flag only re-orients the 39.8% `unaligned_orient_by_moving` clips and barely
> touches 29302. Not worth 3 h 45 m.
>
> Artifacts: Kaggle dataset **`asl250-canon-v1-REFUTED`** (Private) — the corpus,
> `extract_meta.parquet`, fold-0 weights + SavedModel, and `per_signer.json`. The name carries the
> verdict on purpose: do not mount it as "the good corpus."
>
> Full analysis, including the augmentation confound and why it does not rescue the theory:
> **`SESSION_HANDOFF.md` §0.5**. Kept below for provenance and because the *method* — judging a
> layout change per signer rather than on pooled accuracy — was correct and is reusable.

Written 2026-08-13, after the masking A/B produced a result nobody was looking for: per-signer
accuracy on one fold-0 model ranges **0.314 → 0.823**, and it tracks hand-block layout.
Full context: `SESSION_HANDOFF.md` §0.4, `MODEL_250_MVP_REPORT.md` §1.0.

## What this run is for, and what would make it a failure

Two measured failure modes, neither visible in pooled test accuracy:

| layout | signers | accuracy | vs pure-R |
|---|---|---|---|
| pure R (L-contamination ≤0.02) | 37779, 2044, 26734 | 0.780 – 0.823 | — |
| pure **L** | 32319, 34503 | 0.614, 0.577 | **≈ −20 pts** |
| **both blocks** populated | 29302 | **0.314** | **≈ −50 pts** |

The test split holds only R-dominant signers, so **it cannot measure either penalty**. That is
why the acceptance criterion for this run is `per_signer.py` on **34503 / 32319 / 29302**, and
why a pooled-test improvement on its own does not count as success. Arm B's canonical run
(0.7590 vs shipped 0.7576) looked like a null result for exactly this reason — it was blind by
construction, not negative.

**Success:** mean delta on those three signers > +0.02.
**Failure:** they don't move. Then the handedness theory rests on too little and face landmarks
should not be built on top of it.

## Two things this run does differently from every previous one

**Geometric dominance.** `canonicalize()` used to pick the dominant hand by *frame count* —
most tracked frames wins. That is the R5 bug: the tracker holds the **still** hand longest, so
frame count systematically selects the resting hand. It now picks the block whose landmark 0
co-locates with the **moving** arm's pose wrist (`--dominance geometric`, the default).
`--dominance frames` reproduces the old rule for comparison only.

**An explicit both-blocks policy.** For the ~45% of takes whose only tracked hand is the resting
one, you can align the hand *block* or the signing *arm*, not both. Default `--unaligned moving`
orients by the signing arm and keeps the hand anyway — keeping it is not a guess, it's the
2026-08-13 result: NaN-ing exactly these hands cost 0.0312 test and dropped *train* accuracy
0.767 → 0.498. `--unaligned hand` is the untested alternative and is a flag, not a finding.

## Inputs to attach

| dataset | why |
|---|---|
| `asl250-code-v18` | the code — must contain the geometric rule (upload after this doc's edits) |
| **`asl-signs`** (Kaggle competition data) | the RAW parquets. Add via **+ Add Input → Competitions → asl-signs**. You must have joined the competition. |
| `asl250-mask-ab-v1` | supplies `data/split_manifest.parquet`, reused **verbatim** so cv/test/is_outlier are identical |

**No AWS, no S3, no secrets.** The manifest comes from a dataset you already made and the raw
data from Kaggle's own competition mount. Internet can stay off.

Settings: **GPU T4 ×2**, Internet **off**, ~12 h commit cap. This run is ~3 h 45 m.

---

## Cell 1 — stage the code by content *and* version

```python
import os, glob, sys, shutil, subprocess
os.environ["TF_USE_LEGACY_KERAS"] = "1"
!pip -q install tf-keras

# Version markers, not filenames. An output dataset from a previous run is a snapshot of
# /kaggle/working and carries its own train.py + extract_canonical.py, so several inputs look
# like "the code" and only one has the geometric rule.
NEED = {
    "extract_canonical.py": ("limb_assignment", "pick_signing_block", "dominance",
                             "no_motion_info"),
    "train.py":             ("mask_resting_hand", "canonicalize_missing(a)", '"config"'),
    "sign_landmarks.py":    ("hand_arm_alignment", "wrist_travel", "canonicalize_missing"),
    "per_signer.py":        ("LEGACY_CONTROL", "AFFECTED"),
    "test_canonical_geometry.py": ("R5 REGRESSION",),
}

def missing(d):
    out = []
    for f, marks in NEED.items():
        p = os.path.join(d, f)
        if not os.path.exists(p):
            return None                     # not a code dataset at all
        t = open(p, encoding="utf-8").read()
        out += [f"{f}:{m}" for m in marks if m not in t]
    return out

cands = sorted({os.path.dirname(p)
                for p in glob.glob("/kaggle/input/**/extract_canonical.py", recursive=True)})
good = []
for d in cands:
    m = missing(d)
    if m is None:
        print(f"  [partial] {d}")
    elif m:
        print(f"  [reject ] {d}  missing {m}")
    else:
        good.append(d); print(f"  [current] {d}")
assert len(good) == 1, (f"need exactly 1 CURRENT code dataset, found {len(good)}. Upload the "
                       f"post-2026-08-13 code as asl250-code-v18 — extract_canonical.py must "
                       f"contain 'pick_signing_block'.")
CODE = good[0]
for f in NEED:
    shutil.copy(os.path.join(CODE, f), f)
sys.path.insert(0, ".")
print("\nstaged:", sorted(NEED))
```

## Cell 2 — run the test suite BEFORE spending an hour extracting

```python
# The ablation in section 3 is the point: it asserts the OLD frame-count rule picks the RESTING
# hand. If that stops failing, the test can no longer detect the bug and the run is unguarded.
r = subprocess.run([sys.executable, "test_canonical_geometry.py"],
                   capture_output=True, text=True)
print(r.stdout[-4000:])
assert r.returncode == 0, "geometry tests FAILED on this machine — do not extract"
assert "ALL CHECKS PASSED" in r.stdout
print("\nGEOMETRY OK — the staged rule behaves here the way it does locally")
```

## Cell 3 — locate the raw data and the manifest

```python
import pandas as pd
raws = sorted(glob.glob("/kaggle/input/**/train.csv", recursive=True))
raws = [os.path.dirname(p) for p in raws
        if os.path.isdir(os.path.join(os.path.dirname(p), "train_landmark_files"))]
print("raw candidates:", raws)
assert len(raws) == 1, ("need exactly 1 asl-signs competition dir (train.csv + "
                        "train_landmark_files/). + Add Input -> Competitions -> asl-signs. "
                        "You must have joined the competition for it to mount.")
RAW = raws[0]

mans = sorted(glob.glob("/kaggle/input/**/data/split_manifest.parquet", recursive=True))
assert mans, "no split_manifest.parquet — attach asl250-mask-ab-v1"
MAN = mans[0]
_m = pd.read_parquet(MAN)
assert _m["word"].nunique() == 250, f"{_m['word'].nunique()} words, expected 250"
assert len(_m) == 94198, f"{len(_m)} rows, expected 94198 — a different manifest changes the split"
print(f"raw      : {RAW}")
print(f"manifest : {MAN}   ({len(_m)} rows, 250 words)")
print(f"splits   : cv {(_m['split']=='cv').sum()}  test {(_m['split']=='test').sum()}")

free = os.statvfs("/kaggle/working")
print(f"working free: {free.f_bavail*free.f_frsize/2**30:.1f} GiB  (corpus needs ~4)")
```

## Cell 4 — extract (~1 h)

```python
OUT = "/kaggle/working/canon"
!rm -rf {OUT}
# variants=none only. The 'ffill' arm is dead: gap-filling fabricates coordinates by freezing
# an absent hand at its last position, which is what made the old coverage metrics meaningless.
!python extract_canonical.py --raw {RAW} --manifest {MAN} --out {OUT} \
    --variants none --dominance geometric --unaligned moving --workers 8
```

Watch the report card at the end. **`aligned` should land near 55%** — that figure was measured
over 80,647 takes on 2026-08-12. Far from it means the geometry isn't resolving here and the
corpus should not be trained on. The extractor prints its own warning below 40%.

## Cell 5 — fingerprint the OUTPUT and assert it is CANONICAL

```python
import numpy as np, random
from sign_landmarks import canonicalize_missing

def fingerprint(root, n_words=40, per_word=5):
    """left_dead ~1.00 = CANONICAL | ~0.56 = LEGACY.  hand_nan >0.20 = raw missingness."""
    fs = sorted(glob.glob(os.path.join(root, "by_word", "*", "sequences.npz")))
    if not fs: return None
    random.seed(0); random.shuffle(fs)
    ld, hn, n = [], [], 0
    for f in fs[:n_words]:
        z = np.load(f)
        for k in list(z.keys())[:per_word]:
            a = canonicalize_missing(z[k].astype("float32"))
            if a.shape[1] < 75: continue
            L = np.isfinite(a[:, 33:54, :2]).all(-1).any(-1)
            R = np.isfinite(a[:, 54:75, :2]).all(-1).any(-1)
            ld.append(float(not L.any())); hn.append(float((~R).mean())); n += 1
    return dict(n=n, left_dead=float(np.mean(ld)), hand_nan=float(np.mean(hn)))

DATA = f"{OUT}/none"
fp = fingerprint(DATA)
print(f"{DATA}: n={fp['n']}  left_dead {fp['left_dead']:.3f}  hand_nan {fp['hand_nan']:.3f}")

# POLARITY IS THE OPPOSITE OF THE MASKING NOTEBOOK. There, LEGACY was expected and asserted.
# Here the whole point is that 33-53 is now empty, so left_dead must be ~1.00. Getting this
# backwards is how arm A applied a hand-swapping flip to already-canonical data and trained
# half its samples with no hand at all.
assert fp["left_dead"] > 0.90, (
    f"left_dead {fp['left_dead']:.3f} — NOT canonical. The reserved block still has data, so "
    f"canonicalize() did not run or wrote to the wrong slice. Do NOT pass --canonical-hand.")
assert fp["hand_nan"] > 0.20, f"hand_nan {fp['hand_nan']:.3f} — looks gap-filled"
CANON_FLAG = "--canonical-hand"     # REQUIRED on this corpus; wrong on the legacy one
EPOCHS = 120                        # val_acc plateaus ~epoch 93; more buys nothing (§0.4)

import pandas as pd
md = pd.read_parquet(f"{OUT}/extract_meta.parquet")
print(f"\nextract metadata: {len(md)} clips")
print(f"  aligned            : {md['aligned'].mean()*100:.1f}%   (expected ~55%)")
print(f"  both blocks        : {md['both_blocks'].mean()*100:.1f}%")
print(f"  mirrored           : {md['mirrored'].mean()*100:.1f}%")
print(md["pick_reason"].value_counts().to_string())
assert md["signing_block"].nunique() == 2, "only one block ever chosen — the rule is a constant"
print(f"\nCANONICAL OK — flag={CANON_FLAG!r}  EPOCHS={EPOCHS}")
```

## Cell 6 — smoke (3 epochs, ~4 min)

```python
SMOKE = True          # <- set False before Save & Run All
if SMOKE:
    !rm -rf /kaggle/working/canon_smoke
    !python train.py --data-dir {DATA} --all-words --fold 0 {CANON_FLAG} \
        --epochs 3 --lr 4e-4 --seed 42 --out-dir /kaggle/working/canon_smoke
```

The `[cfg]` line **must** read `layout = CANONICAL`, `hflip swaps hands = False`, and
`hand-drop blocks = 1`. If it says LEGACY, `--canonical-hand` didn't reach the process and the
run is arm A all over again — stop.

## Cell 7 — train fold 0 (~2 h 32 m)

```python
!rm -rf /kaggle/working/canon_fold0
!python train.py --data-dir {DATA} --all-words --fold 0 {CANON_FLAG} \
    --epochs {EPOCHS} --lr 4e-4 --seed 42 --out-dir /kaggle/working/canon_fold0
```

## Cell 8 — the acceptance test

```python
!python per_signer.py --data-dir {DATA} \
    --weights /kaggle/working/canon_fold0/weights_all250_fold0_seed42.weights.h5 \
    --out /kaggle/working/canon_fold0/per_signer.json
```

Read the **ACCEPTANCE** block, not the pooled number. It prints each of 34503 / 32319 / 29302
against its legacy value and the mean delta, and states a verdict.

## Cell 9 — save, or the corpus is gone

**Version → Output → New Dataset → `asl250-canon-v1` → Private.** A brand-new name; never write
onto an existing dataset.

This is not housekeeping. Arm B's canonical corpus was written to `/kaggle/working/canon` during
a commit, never saved as a dataset output, and **no longer exists** — which is why the masking
A/B had to be redesigned around a corpus that had evaporated, and why the canonical question sat
unanswered for a session. A commit starts from an empty `/kaggle/working`. Save it.

---

## Before Save & Run All

1. `SMOKE = False` in Cell 6
2. Cells 1–5 green: `[current]` code dataset, `GEOMETRY OK`, manifest 94198 rows, `aligned` near
   55%, `CANONICAL OK`
3. Cell 6 smoke showed `layout = CANONICAL` / `hflip swaps hands = False` / `hand-drop blocks = 1`
4. Internet off, GPU on

Then Save Version → Save & Run All, and close the laptop. ~3 h 45 m.

## What the result means

| outcome | read |
|---|---|
| affected signers **+0.02 or better** | layout theory confirmed; proceed to face landmarks in the freed 33–53 block |
| affected signers flat, pooled up | canonicalization helped something else; do NOT credit handedness, and don't build face on it |
| affected signers flat, pooled flat | theory not demonstrated on 3 signers. Stop and reconsider before more GPU |
| ~~affected signers **down**~~ | ~~try `--unaligned hand` before abandoning~~ — **WITHDRAWN, see the banner at the top.** This is the row that fired, and the retry it prescribes is not worth running: the four unaffected signers fell by the same amount as the three affected ones, so there is no differential signal for a different unaligned policy to recover. |

**What actually happened: row 4, and the theory is dead rather than mis-parameterized.** The tell
was not the sign of the delta — it was that the delta was *uniform across all seven signers*. A
mis-parameterized layout rule would have moved the three affected signers differently from the
four unaffected ones, in either direction. Identical movement everywhere says the mechanism has no
purchase on the per-signer spread at all.

`val_acc` will read ~0.60 regardless; the val fold is four held-out participants including the
0.314 signer, so it is not comparable to a test number. Don't panic at it.
