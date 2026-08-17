# Resume the 250-word training on **Kaggle** (free GPU, 30 h/week)

**Why this doc exists.** Colab free-tier throttled the 250 training twice. Kaggle
Notebooks give **30 GPU-hours/week** (T4/P100), sessions up to ~12 h, and don't cut
out mid-run the way Colab did. Only ~**4 GPU-hours** of work remain, so this fits
easily inside one week's quota.

This is the Kaggle-adapted twin of [`RESUME_250.md`](RESUME_250.md). **Everything
already done in Colab is reused** — you do not retrain fold-0. The training recipe,
the scripts, and the S3 data are identical; only the *plumbing* changes:

| Thing | Colab (old) | Kaggle (this doc) |
|---|---|---|
| Persistent storage | Google Drive (`/content/drive/...`) | **S3** (`s3://asl-mvp-dataset/asl250_out/`) — Kaggle has no Drive |
| Output dir (`--out-dir`) | `/content/drive/MyDrive/asl250_out` | `/kaggle/working/asl250_out` (wiped between sessions → **push to S3 after each fold**) |
| AWS creds | pasted into a cell each recycle | **Kaggle Secrets** (set once, no pasting) |
| Data sync | `aws s3 sync` OR Drive | `aws s3 sync` (identical) |
| GPU | hidden daily limit | 30 h/week, phone-verified |

> 🔑 **The one new prerequisite:** your fold-0 weights, the backbone, and (optionally)
> the fold-1 backup live **only on Google Drive** right now. Kaggle can't see Drive.
> **Phase 0** moves them Drive → S3 **once**, from a *CPU-only* Colab session so it
> **doesn't spend any GPU quota.** After that, Kaggle is fully self-sufficient.

---

## Status snapshot (unchanged from RESUME_250)
- **fold-0: DONE**, test acc **0.7576** (beats the 0.726 backbone). Weights on Drive:
  `MyDrive/asl250_out/weights_all250_fold0_seed42.weights.h5`.
- **fold-1:** partial (~epoch 30). It early-stops ~epoch 31 and barely diverges from
  the backbone — **not worth resuming the exact checkpoint**; just re-run it fresh on
  Kaggle (fast). Backup on Drive if you want it: `MyDrive/asl250_out/backup_all250_fold1/`.
- **folds 2–4:** not started.
- **Goal:** ensemble the folds → target **>0.80** on the 3 held-out test signers
  (2044 / 37779 / 53618). fold-0 alone (0.7576) is under target.

## 🚨 The golden gotcha (same on Kaggle — do NOT skip)
On TF 2.17/2.18 + tf-keras, calling `build_model` **inside the notebook kernel**
decomposes Dense/attention into untracked ops → `load_weights` silently loads a
**random** model (**0.004 acc = 1/250, pure chance**). **ALWAYS run train / eval /
export as a `!python` SUBPROCESS** (`!TF_USE_LEGACY_KERAS=1 python script.py`), never
build+load in a plain cell. Confirm each run prints `>> proper build? classifier: True`.
(This is why fold-0 first read 0.004, then 0.7576 once run via subprocess.)

---

# Phase 0 — One-time: push the reusable artifacts → S3 (from Windows)

The Drive folders were downloaded + extracted to `~/Downloads`, so the files are
already on Windows — **no CPU-Colab bridge needed.** Upload the two weights + the
patched `train.py` straight to S3.

**Prereq:** AWS CLI installed on Windows, then `aws configure` (enter your keys +
region `eu-north-1`) in a terminal — do this yourself, don't paste keys into chat.

```powershell
# adjust the two "asl250_*-2026...-001" folder names to match your Downloads
$CODE = "$HOME\Downloads\asl250_code-20260722T133918Z-1-001\asl250_code"
$OUT  = "$HOME\Downloads\asl250_out-20260722T133921Z-1-001\asl250_out"
$S    = "s3://asl-mvp-dataset/asl250_out"

# the 250-class backbone (warm-start source for every fold)
aws s3 cp "$CODE\backbone_250.weights.h5" "$S/backbone_250.weights.h5" --region eu-north-1
# fold-0 weights — the DONE 0.7576 fold (do NOT retrain this)
aws s3 cp "$OUT\weights_all250_fold0_seed42.weights.h5" "$S/weights_all250_fold0_seed42.weights.h5" --region eu-north-1
# the patched training script (repo copy == the Drive copy)
aws s3 cp "training\train.py" "$S/train.py" --region eu-north-1

# verify all three landed
aws s3 ls "$S/" --region eu-north-1
```

> **What's NOT uploaded and why it's fine:** `savedmodel_fold0/` (never exported in
> Colab → Phase 3 re-creates it), `vocab_250.json` (generated in Phase 3), and the
> `backup_all250_fold1/` resume checkpoint (we re-run fold-1 fresh in Phase 4 — cross-
> platform `BackupAndRestore` files are TF-version-fragile anyway).

---

# Phase 1 — Kaggle account + notebook setup (one time)

1. **Sign up** at kaggle.com and **verify your phone** (Settings → Phone Verification).
   *This is mandatory* — GPU **and internet** are locked until you verify.
2. **New notebook:** kaggle.com → Create → **New Notebook**.
3. **Enable GPU:** right sidebar → **Session options → Accelerator → `GPU T4 x2`**
   (or `GPU P100`). Single-GPU use is fine — `train.py` needs no code change.
4. **Enable Internet:** same panel → **Internet → On**. Without this, `pip` and
   `aws s3` fail. (Requires the phone verification from step 1.)
5. **Store AWS creds as Secrets** (so you never paste keys in a cell):
   **Add-ons → Secrets → Add** two secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   Toggle both **attached** to this notebook.

> ⏱️ Kaggle idle-timeouts an interactive session after ~20–40 min of no activity and
> caps a session at ~12 h. Because `/kaggle/working` is wiped between sessions, the
> rule is simple: **after every fold finishes, push it to S3** (built into Phase 4).

---

# Phase 2 — Rehydrate the Kaggle session (run at the start of every session)

```python
# --- deps: Keras-2 stack for build_model + aws cli ---
!pip -q install tf-keras awscli
import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"      # build_model needs the Keras 2 API

# --- AWS creds from Kaggle Secrets (no pasting) ---
from kaggle_secrets import UserSecretsClient
us = UserSecretsClient()
os.environ["AWS_ACCESS_KEY_ID"]     = us.get_secret("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = us.get_secret("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"

S = "s3://asl-mvp-dataset"
OUT = "/kaggle/working/asl250_out"
!mkdir -p {OUT}

# --- pull code + reusable weights from S3 ---
!aws s3 cp {S}/asl250_out/train.py .
!aws s3 cp {S}/asl250_out/backbone_250.weights.h5 .
!aws s3 cp {S}/asl250_out/weights_all250_fold0_seed42.weights.h5 {OUT}/weights_all250_fold0_seed42.weights.h5

# --- pull the data (~10–20 min; several GB) ---
!mkdir -p data
!aws s3 cp   {S}/splits/split_manifest.parquet data/split_manifest.parquet
!aws s3 sync {S}/preprocessed/by_word          data/by_word --quiet

# --- verify ---
print("train.py:",   os.path.exists("train.py"),
      "| backbone:",  os.path.exists("backbone_250.weights.h5"),
      "| fold0 wts:", os.path.exists(f"{OUT}/weights_all250_fold0_seed42.weights.h5"),
      "| data:",      os.path.exists("data/by_word"))
```

> 💡 To skip the 10–20 min data sync every session, you can instead publish the
> `by_word/` folder + `split_manifest.parquet` as a **private Kaggle Dataset** once
> and attach it to the notebook (it mounts read-only at `/kaggle/input/<name>/`,
> then set `--data-dir /kaggle/input/<name>`). S3 sync is simpler for a one-week job;
> the Kaggle Dataset is worth it if you'll iterate a lot.

---

# Phase 3 — Lock fold-0 as a SavedModel (skip if Phase 0 already copied it)

```python
%%writefile export_fold0.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, ".")
import json
import tensorflow as tf
from pathlib import Path
from train import build_model, load_vocab
data = Path("data")
vocab = load_vocab(all_words=True, data_dir=data); words = vocab["words"]
m = build_model(num_classes=len(words))
m.load_weights("/kaggle/working/asl250_out/weights_all250_fold0_seed42.weights.h5")
out = "/kaggle/working/asl250_out/savedmodel_fold0"
try: m.export(out)
except AttributeError: tf.saved_model.save(m, out)
json.dump({"vocab_version": "v1-all250", "num_classes": len(words),
           "words": words, "word_to_index": vocab["word_to_index"]},
          open("/kaggle/working/asl250_out/vocab_250.json", "w"), indent=2)
print("exported SavedModel + froze vocab_250.json")
```
```python
!TF_USE_LEGACY_KERAS=1 python export_fold0.py
!aws s3 sync /kaggle/working/asl250_out s3://asl-mvp-dataset/asl250_out --quiet
```

> `vocab_250.json` is **load-bearing** (output index → word). Freeze it here on the
> training machine and ship it with the model — never regenerate it elsewhere.

---

# Phase 4 — Train the remaining folds (the actual GPU work)

Each fold warm-starts from the backbone and auto-exports its SavedModel when done
(patched `train.py`). **After each fold, immediately push to S3** so a session
timeout costs nothing. Run these as separate cells so you can stop between folds.

```python
# fold 1
!TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 1 \
  --init-from backbone_250.weights.h5 --lr 2e-4 --epochs 80 --out-dir /kaggle/working/asl250_out
!aws s3 sync /kaggle/working/asl250_out s3://asl-mvp-dataset/asl250_out --quiet
```
```python
# fold 2  (then fold 3, fold 4 — change the two "--fold N" numbers only)
!TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 2 \
  --init-from backbone_250.weights.h5 --lr 2e-4 --epochs 80 --out-dir /kaggle/working/asl250_out
!aws s3 sync /kaggle/working/asl250_out s3://asl-mvp-dataset/asl250_out --quiet
```

Notes:
- Some folds **early-stop fast** (their val signers are easy for the backbone;
  `PATIENCE=30`). That's expected and fine — the **ensemble on the test split** is the
  real number, not any single fold's val curve.
- `BackupAndRestore` snapshots to `--out-dir` each epoch, so if a session dies
  mid-fold, re-running the **same** fold command resumes it — **as long as
  `/kaggle/working/asl250_out` was restored from S3 first** (Phase 2 pulls fold-0;
  add a `aws s3 sync s3://.../asl250_out /kaggle/working/asl250_out` at session start
  if you're mid-fold).
- Budget: ~0.5–1.5 GPU-h per fold on a T4. Four folds ≈ your remaining ~4 h.

---

# Phase 5 — Ensemble eval (the honest >0.8 number)

```python
%%writefile ensemble_eval_250.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, ".")
import numpy as np, json, glob
from pathlib import Path
import tensorflow as tf
from train import build_model, load_vocab, load_dataset, make_tf_dataset

data = Path("data")
vocab = load_vocab(all_words=True, data_dir=data); words = vocab["words"]
man, arrays = load_dataset(data, vocab)
ev = man[(man["split"] == "test") & (~man["is_outlier"])].reset_index(drop=True)
ds = make_tf_dataset(ev, arrays, len(words), training=False)
y  = ev["y"].to_numpy()

OUT = "/kaggle/working/asl250_out"
folds = sorted(glob.glob(OUT + "/weights_all250_fold*_seed42.weights.h5"))
print("folds found:", [f.split('/')[-1] for f in folds])

probs_sum = None
for wf in folds:
    m = build_model(num_classes=len(words))
    m.load_weights(wf)
    p = tf.nn.softmax(m.predict(ds, verbose=0), axis=1).numpy()
    print("  %s  test acc: %.4f" % (wf.split('/')[-1], float((p.argmax(1) == y).mean())))
    probs_sum = p if probs_sum is None else probs_sum + p

ens = probs_sum / len(folds)
overall = float((ens.argmax(1) == y).mean())
per_word = {words[c]: float((ens.argmax(1)[y == c] == c).mean()) for c in np.unique(y)}
print("=== ENSEMBLE (%d folds) TEST acc: %.4f ===" % (len(folds), overall))
print("worst 20:", [(w, round(per_word[w], 2)) for w in sorted(per_word, key=per_word.get)[:20]])
json.dump({"ensemble_acc": overall, "n_folds": len(folds), "per_word_acc": per_word},
          open(OUT + "/ensemble_eval_250.json", "w"), indent=2)
```
```python
!TF_USE_LEGACY_KERAS=1 python ensemble_eval_250.py
!aws s3 sync /kaggle/working/asl250_out s3://asl-mvp-dataset/asl250_out --quiet
```

---

# Phase 6 — Decision

- **ensemble ≥ 0.80** → **done.** Go to Phase 7.
- **~0.78–0.79** → train the remaining folds (3, 4) and re-run Phase 5.
- **Still under 0.8 with all 5 folds** → add **mirror TTA** to the ensemble (average
  each fold's prediction on the clip AND its `x → −x` mirror). The live demo already
  does this; it usually adds ~1–2%. (Edit `ensemble_eval_250.py` to also predict the
  flipped input using `FLIP_MAP` from `train.py`, and average.)

---

# Phase 7 — Ship it (S3 → Windows, then wire the demo)

Everything is already in `s3://asl-mvp-dataset/asl250_out/`. On your Windows machine:

```powershell
# pull the 250 artifacts next to the repo
aws s3 sync s3://asl-mvp-dataset/asl250_out artifacts_250 `
  --exclude "*" --include "savedmodel_fold*/*" --include "vocab_250.json" --include "ensemble_eval_250.json" `
  --region eu-north-1
```

You need, in `artifacts_250/`: `savedmodel_fold*/` + `vocab_250.json` +
`ensemble_eval_250.json`. Then wire the demo (I can do this part):
- Add a `--vocab250` flag to `live_demo.py` → model dirs = `artifacts_250/savedmodel_fold*`,
  `VOCAB_PATH = vocab_250.json`. The recognition pipeline is class-count-agnostic
  (`words[idx]`), so nothing else changes.
- **Sentences:** rules only cover the 30-word combos → for 250, use `--ai`.
- Verify: `python live_demo.py --vocab250 --selftest` (expect output shape `[250]`),
  then `python live_demo.py --vocab250 --ai` live; read the `[seg]` lines for weak words.

See `TRAIN_250_PLAN.md` Step 5 for the full wiring detail.

---

# Kaggle troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pip`/`aws` can't reach network | **Internet is Off** — enable it in Session options (needs phone verification). |
| GPU option greyed out | Phone not verified, or you've hit the 30 h/week quota (check the sidebar meter — Kaggle **does** show it, unlike Colab). |
| eval prints **0.004** acc | The golden gotcha — you built+loaded in a notebook cell. Re-run as `!TF_USE_LEGACY_KERAS=1 python …`. Look for `proper build? classifier: True`. |
| `No module named tf_keras` / Keras-3 build errors | `!pip install tf-keras` and ensure `TF_USE_LEGACY_KERAS=1` is set **before** TF is imported (the subprocess sets it inline — that's why we use `!python`). |
| Session ended, `/kaggle/working` empty | Expected — it's ephemeral. Everything important was pushed to S3; re-run Phase 2, then resume the fold you were on. |
| Weekly quota exhausted | Resets weekly. ~4 h of work fits one week; if you split across weeks, each fold is independent. |

*Kaggle twin of `RESUME_250.md`. Same recipe, same scripts, S3 instead of Drive.
If anything here conflicts with `train.py`, the code wins — verify before asserting.*
