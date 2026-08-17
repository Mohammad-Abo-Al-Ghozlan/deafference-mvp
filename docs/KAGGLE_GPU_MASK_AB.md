# GPU notebook — the resting-hand masking A/B (complete cell set)

> # 🔴 RESULT: MASKING LOSES. DO NOT RE-RUN THIS.
>
> Ran 2026-08-13, both arms in one commit. `epochs=120 run=120 seed=42` on both;
> `masked_clips=0` vs `39369`.
>
> | arm | TEST (13,998) | val fold 0 (16,202) | train acc |
> |---|---|---|---|
> | control `mask=off` | **0.7658** | 0.5791 | 0.7673 |
> | masked `mask=train` | 0.7346 | 0.5376 | 0.4983 |
> | delta | **−0.0312 (−6.0σ)** | −0.0415 (−7.5σ) | −0.269 |
>
> The train-accuracy column is what settles it: `train`-only masking creates a train/eval
> mismatch, so the val and test deltas alone could be explained without information loss — but
> 0.767 → 0.498 is measured on the distribution the model trained on. The deleted hand block
> carries class-discriminative signal.
>
> **No selective variant survives either.** Per-word 48 helped / 177 hurt / 25 tied, but at 2σ
> only **3 helped** against **~6 expected by chance** over 250 tests. Apparent winners are the
> other half of zero-sum shifts inside confusion clusters — `wake` +0.197 *is* `awake` −0.250.
>
> Deploy recipe: **`--mask-resting-hand off`.** Artifacts: `asl250-mask-ab-v1` (Private).
> Full write-up: `SESSION_HANDOFF.md` §0.4.
>
> **The valuable result from this run was not the A/B.** It was the per-signer breakdown of the
> control arm: 7 held-out signers spanning **0.314 to 0.823**, driven by hand-block layout. See
> §0.4 and `MODEL_250_MVP_REPORT.md` §1.0. Read that before planning the next run.

Rewritten 2026-08-13 after discovering **arm B's canonical corpus no longer exists**.
Supersedes `FINISH_250.md` STEP 1 for any run using `--mask-resting-hand`.

## What changed and why

The first plan was: train one masked arm on the canonical corpus and compare against arm B's
`0.7590`. That is not possible. A full search found **one** corpus prefix in the bucket:

```
prefixes containing by_word/: ['preprocessed/']
  LEGACY / raw-missing   s3://asl-mvp-dataset/preprocessed/   left_dead 0.42  hand_nan 0.68
```

Nothing canonical on S3, nothing in the attached datasets, nothing in `/kaggle/working`.
`extract_canonical.py` wrote arm B's corpus to `/kaggle/working/canon` during a commit and it
was never saved as a dataset output. The layout arm B trained on is gone.

`left_dead` readings of 0.42 / 0.56 / 0.64 across samples are the same corpus at different
sample sizes — small-`n` noise around the true ~0.56, which is the `ONLY_R` rate (56.7%)
measured in R1. All well below the 0.90 canonical threshold.

### The design this forces, and why it is better anyway

Run **both arms in one commit on the legacy corpus**: an unmasked control and a masked arm,
same data, same code, same session, one variable.

| | regenerate canonical (rejected) | **two arms on legacy (this file)** |
|---|---|---|
| wall clock | ~1 h extract + 2.5 h train ≈ 3.6 h | ~20 min sync + 2×2.5 h ≈ 5.3 h |
| baseline | reuse arm B's 0.7590 | measured in the same run |
| risk | `extract_canonical.py` is **untracked** — it cannot be diffed against the version that produced arm B, so a reproduced corpus might not be arm B's, silently contaminating the comparison | none — nothing external is trusted |

The extra 1.7 h buys a comparison that depends on no lost artifact. It also produces the
honest same-corpus baseline that `MASTER_FIX_PLAN.md` M2 flagged as missing ("0.7755 and
0.7544 both used the broken init and a different LR").

> 🔴 **This paragraph used to end: "Canonical is not worth reconstructing for this: arm B was
> parity with the shipped model (0.7590 vs 0.7576), so the layout never justified itself."
> WITHDRAWN 2026-08-13.** That inference was invalid, and it came from the same blind spot the
> rest of this file documents. Arm B's parity was measured on a test split with **no
> left-recorded signer and no both-blocks signer** — the only two configurations
> canonicalization exists to eliminate. It could not have shown a gain there. Those two
> configurations cost **~20 and ~50 accuracy points** on the signers that have them (§0.4), so
> rebuilding the canonical corpus is now the **top** priority. The decision to run two legacy
> arms was still correct for *this* question; the conclusion drawn about canonicalization was
> not.

**Do NOT pass `--canonical-hand`.** On legacy data it switches `hflip` to a pose-only mirror
that deliberately does not swap the hand blocks, producing anatomically impossible samples on
roughly half of all augmentations. That flag is the difference between the two recipes, and
this corpus needs the legacy one.

---

## Cell 1 — secrets + code (version-gated)

```python
import os, glob, json, subprocess, sys
os.environ["TF_USE_LEGACY_KERAS"] = "1"
!pip -q install tf-keras awscli
from kaggle_secrets import UserSecretsClient
us = UserSecretsClient()
os.environ["AWS_ACCESS_KEY_ID"]     = us.get_secret("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = us.get_secret("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"

# Pick the code dataset by CONTENT *and VERSION*. An output dataset from a previous run is a
# snapshot of /kaggle/working, so it carries its own train.py + sign_landmarks.py; both look
# like "the code" and only one has the mask. 'canonicalize_missing(a)' is the 2026-08-13
# sentinel fix — without it the mask decision is a CONSTANT and masks nearly everything.
TRAIN_MARKS = ("mask_resting_hand", "scan_resting_hands", "apply_resting_mask",
               "canonicalize_missing(a)")
SL_MARKS    = ("hand_arm_alignment", "canonicalize_missing")

def missing_marks(d):
    try:
        t = open(os.path.join(d, "train.py"), encoding="utf-8").read()
        s = open(os.path.join(d, "sign_landmarks.py"), encoding="utf-8").read()
    except OSError:
        return None
    return [m for m in TRAIN_MARKS if m not in t] + [m for m in SL_MARKS if m not in s]

cands = sorted({os.path.dirname(p) for p in glob.glob("/kaggle/input/**/train.py", recursive=True)
                if os.path.exists(os.path.join(os.path.dirname(p), "sign_landmarks.py"))})
good = []
for d in cands:
    miss = missing_marks(d)
    if miss == []:
        good.append(d); print(f"  [current] {d}")
    else:
        print(f"  [reject ] {d}  missing {miss}")
assert len(good) == 1, (f"need exactly 1 CURRENT code dataset, found {len(good)}. Attach the "
                        f"newest asl250-code-v* — train.py must contain 'canonicalize_missing(a)'.")
CODE = good[0]
!cp {CODE}/train.py {CODE}/sign_landmarks.py .
sys.path.insert(0, ".")
print("\nstaged:", [f for f in ("train.py", "sign_landmarks.py") if os.path.exists(f)])
```

---

## Cell 2 — the corpus fingerprint

```python
import numpy as np, random
from sign_landmarks import canonicalize_missing

def fingerprint(root, n_words=40, per_word=5):
    """Identify a corpus from its DATA, never its path.
      left_dead ~1.00 = CANONICAL | ~0.56 = LEGACY (that is the ONLY_R rate, 56.7%)
      hand_nan  >0.20 = raw missingness | <0.10 = gap-filled (fabricated coords)
    canonicalize_missing FIRST: absence is stored as 0.0 and isfinite(0.0) is True."""
    fs = sorted(glob.glob(os.path.join(root, "by_word", "*", "sequences.npz")))
    if not fs:
        return None
    random.seed(0); random.shuffle(fs)
    ld, hn, n = [], [], 0
    for f in fs[:n_words]:
        try:
            z = np.load(f)
        except Exception:
            continue
        for k in list(z.keys())[:per_word]:
            a = canonicalize_missing(z[k].astype("float32"))
            if a.shape[1] < 75:
                continue
            L = np.isfinite(a[:, 33:54, :2]).all(-1).any(-1)
            R = np.isfinite(a[:, 54:75, :2]).all(-1).any(-1)
            ld.append(float(not L.any())); hn.append(float((~R).mean())); n += 1
    if not n:
        return None
    return dict(n=n, left_dead=float(np.mean(ld)), hand_nan=float(np.mean(hn)))

def classify(fp):
    if fp is None:
        return "no clips found"
    layout = ("CANONICAL" if fp["left_dead"] > 0.90 else
              "LEGACY"    if fp["left_dead"] < 0.80 else "AMBIGUOUS")
    fill   = ("raw-missing" if fp["hand_nan"] > 0.20 else
              "gap-filled"  if fp["hand_nan"] < 0.10 else "AMBIGUOUS")
    return f"{layout} / {fill}"

print("fingerprint() ready. This run expects: LEGACY / raw-missing")
```

---

## Cell 3 — corpus, and gate on what we actually expect

```python
DATA = "data"
if not os.path.exists(f"{DATA}/by_word"):
    !mkdir -p {DATA}
    !aws s3 cp   s3://asl-mvp-dataset/splits/split_manifest.parquet {DATA}/split_manifest.parquet
    !aws s3 sync s3://asl-mvp-dataset/preprocessed/by_word {DATA}/by_word --quiet

fp = fingerprint(DATA)          # 200 clips, not the 24-clip probe — small n reads noisy
print(f"{DATA}: {classify(fp)}  n={fp['n']}  left_dead {fp['left_dead']:.2f}  hand_nan {fp['hand_nan']:.2f}")

# LEGACY is expected here and is NOT a failure — it is the only corpus that exists. What must
# be true is that we are NOT about to apply the canonical recipe to it, and that the gap-filler
# never ran (fabricated coordinates would make both arms meaningless in the same way).
assert fp["left_dead"] < 0.80, (
    f"left_dead {fp['left_dead']:.2f} looks CANONICAL. If a canonical corpus has appeared, this "
    f"notebook's recipe is wrong for it — add --canonical-hand to both arms below.")
assert fp["hand_nan"] > 0.20, (
    f"hand_nan {fp['hand_nan']:.2f} — gap-filled. Fabricated coordinates: the cleaner froze "
    f"absent hands at their last position, so 'masking the resting hand' has nothing to mask.")
CANONICAL_FLAG = ""             # deliberately empty: legacy corpus -> legacy recipe

import pandas as pd
_m = pd.read_parquet(f"{DATA}/split_manifest.parquet")
assert _m["word"].nunique() == 250, f"{_m['word'].nunique()} words, expected 250"
print(f"CORPUS OK — legacy layout, raw missingness, 250 classes, {len(_m)} rows")
print(f"canonical flag = {CANONICAL_FLAG!r}  (empty is correct for this corpus)")
```

---

## Cell 4 — the epoch flag

Both arms must use the same `--epochs`, because `CosineDecay(decay_steps=epochs*steps -
warmup)` is tied to it. Since both arms run here, the value only has to be *consistent* — but
matching the previous runs keeps the numbers loosely comparable to `0.7576` / `0.7590`.

```python
import pandas as pd
hs = sorted(glob.glob("/kaggle/input/**/armB_canonical/history_all250_fold0.csv", recursive=True))
if hs:
    h = pd.read_csv(hs[0]); rows = len(h); best = int(h["val_acc"].idxmax()) + 1
    print(f"arm B: {rows} rows, best val_acc {h['val_acc'].max():.4f} at epoch {best}")
    EPOCHS = 200 if rows - best >= 28 else rows
    print(f"  -> {'EarlyStopping fired; flag was larger than ' + str(rows) if rows - best >= 28 else 'ran to completion'}")
else:
    EPOCHS = 120
    print("no arm B history attached — defaulting to 120")
assert 60 <= EPOCHS <= 400, f"implausible EPOCHS={EPOCHS}"
print(f"\nEPOCHS = {EPOCHS}  (used identically by BOTH arms)")
```

---

## Cell 5 — PREFLIGHT. Everything cheap, before the 5 hours

```python
print("code")
t = open("train.py", encoding="utf-8").read()
assert all(m in t for m in TRAIN_MARKS), "staged train.py is stale"
assert '"config"' in t and "epochs_run" in t, "train.py does not record its run config"
print("   mask + sentinel fix + config recording present")

print("corpus")
assert fp["left_dead"] < 0.80 and fp["hand_nan"] > 0.20
print(f"   {DATA} = LEGACY / raw-missing, and no --canonical-hand will be passed")

print("mask decision is real (not a constant)")
from sign_landmarks import hand_arm_alignment
seen = set()
for f in sorted(glob.glob(os.path.join(DATA, "by_word", "*", "sequences.npz")))[:8]:
    z = np.load(f)
    for k in list(z.keys())[:6]:
        a = canonicalize_missing(z[k].astype("float32"))
        al = hand_arm_alignment(a)
        seen.add((al["block"], al["belongs"], al["moving"], al["aligned"]))
assert len({s[3] for s in seen}) == 2, (
    f"alignment verdict is CONSTANT across sampled clips: {seen}. That is the sentinel-bug "
    f"signature — the mask would blank nearly everything while printing a believable percent.")
assert len({s[0] for s in seen}) == 2, (
    f"only one hand block is ever populated in this sample: {seen}. On a LEGACY corpus both "
    f"blocks should appear — check the corpus is what Cell 3 says it is.")
print(f"   {len(seen)} distinct verdicts; both aligned=True and False present; both blocks seen")

print("disk")
free = os.statvfs("/kaggle/working")
print(f"   /kaggle/working free: {free.f_bavail * free.f_frsize / 2**30:.1f} GiB "
      f"(two runs of weights + savedmodels ~ 2 GiB)")

print(f"\nPREFLIGHT OK — EPOCHS={EPOCHS}, DATA={DATA}, canonical flag empty")
print("Safe to Save & Run All.")
```

---

## Cell 6 — smoke (set `SMOKE = False` before committing)

```python
SMOKE = True          # <- set False before Save & Run All
if SMOKE:
    !python train.py --data-dir {DATA} --all-words --fold 0 \
        --mask-resting-hand train --epochs 3 --lr 4e-4 --seed 42 \
        --out-dir /kaggle/working/mask_smoke
```

Check the `[mask]` line reports **25–65%** masked. Above ~70% means the sentinel fix is not
running. Ignore the accuracy — a 3-epoch cosine schedule is a different schedule.

---

## Cell 7 — ARM 1: the CONTROL, unmasked (~2–2.5 h)

The control runs first on purpose. No unmasked baseline exists on raw legacy, so this number is
a reusable asset even if the session dies before arm 2 — and it confirms the corpus and recipe
reproduce something sane before the second 2.5 h is spent.

```python
!python train.py --data-dir {DATA} --all-words --fold 0 \
    --mask-resting-hand off --epochs {EPOCHS} --lr 4e-4 --seed 42 \
    --out-dir /kaggle/working/arm_control
```

---

## Cell 8 — ARM 2: MASKED (~2–2.5 h)

Identical but for one flag. Same seed, same epochs, same corpus, same process.

```python
!python train.py --data-dir {DATA} --all-words --fold 0 \
    --mask-resting-hand train --epochs {EPOCHS} --lr 4e-4 --seed 42 \
    --out-dir /kaggle/working/arm_masked
```

---

## Cell 9 — score both on TEST and print the delta

```python
%%writefile eval_arms.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, ".")
import glob, json
import numpy as np
import tensorflow as tf
from pathlib import Path
from train import build_model, load_vocab, load_dataset, make_tf_dataset, _MASK_MODE

# A fresh process, so the module default holds. Both arms are scored on the SAME unmasked test
# set — that is what makes the delta attributable to training rather than to the yardstick.
assert _MASK_MODE == "off", "the TEST set must be unmasked for both arms"

DATA = Path(os.environ["MASK_DATA"])
vocab = load_vocab(all_words=True, data_dir=DATA); words = vocab["words"]
man, arrays = load_dataset(DATA, vocab)
ev = man[(man["split"] == "test") & (~man["is_outlier"])].reset_index(drop=True)
y = ev["y"].to_numpy()
print(f"test set: {len(ev)} clips, {len(words)} classes\n")

res = {}
for name, d in (("control (unmasked)", "arm_control"), ("masked", "arm_masked")):
    wf = sorted(glob.glob(f"/kaggle/working/{d}/weights_all250_fold0_seed42.weights.h5"))
    if not wf:
        print(f"{name:20} NO WEIGHTS at /kaggle/working/{d} — arm did not finish"); continue
    ds = make_tf_dataset(ev, arrays, len(words), training=False)
    m = build_model(num_classes=len(words)); m.load_weights(wf[0])
    p = tf.nn.softmax(m.predict(ds, verbose=0), axis=1).numpy()
    res[name] = float((p.argmax(1) == y).mean())
    cfg = json.load(open(f"/kaggle/working/{d}/eval_all250_fold0.json")).get("config", {})
    print(f"{name:20} TEST {res[name]:.4f}   mask={cfg.get('mask_resting_hand')} "
          f"epochs={cfg.get('epochs')} run={cfg.get('epochs_run')} "
          f"masked_clips={cfg.get('masked_clips')} seed={cfg.get('seed')}")

if len(res) == 2:
    a, b = res["control (unmasked)"], res["masked"]
    n = len(ev)
    se = float(np.sqrt((a * (1 - a) + b * (1 - b)) / n))   # rough, paired would be tighter
    print(f"\nDELTA (masked - control): {b - a:+.4f}   ~{(b - a) / max(se, 1e-9):+.1f} sigma "
          f"(SE {se:.4f}, n={n})")
    print("reference: shipped 0.7576, arm B canonical 0.7590 — different corpora, loose only")
```

```python
os.environ["MASK_DATA"] = DATA
!python eval_arms.py
```

Then **Version → Output → New Dataset → `asl250-mask-ab-v1` → Private.** A brand-new name;
never write onto an existing dataset.

### Reading the delta

| delta | read | next |
|---|---|---|
| **> +0.010** | masking helps | adopt it; run folds 1–4 masked, then the ensemble |
| **+0.003 to +0.010** | probably helps, inside noise | check the sigma; a second seed decides it |
| **−0.003 to +0.003** | no effect | the handshape channel carried little either way; drop the lever |
| **< −0.010** | masking hurts | the block held real signal — see below |

A negative result is informative, not a failure. Masking removes ~45% of the handshape channel;
if the model was extracting even weak signal from it — including as a participant or
recording-condition cue rather than linguistic content — removing it costs accuracy. That would
say the wrong hand was still doing useful work for *recognition*, while remaining unusable for
*animation*. Those are separate products off one corpus and they are allowed to disagree.

Mind the sigma. With n ≈ 17k test clips, SE is roughly 0.004, so anything under ~0.008 is
one-sigma noise and needs a second seed before it means anything.
