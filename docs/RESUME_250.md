# Resume the 250-word training (after Colab GPU quota resets)

**Where we stopped (2026-07-21):** Colab free-tier **GPU usage limit** hit mid fold-1.
Nothing lost. Wait ~12–24h for the quota to reset, then follow this.

## Status snapshot
- **fold-0:** DONE. Test acc **0.7576** (beats the 0.726 backbone). Weights on Drive:
  `/content/drive/MyDrive/asl250_out/weights_all250_fold0_seed42.weights.h5`.
- **fold-1:** partial (~epoch 30). Resume-checkpoint on Drive:
  `/content/drive/MyDrive/asl250_out/backup_all250_fold1/`. Re-running the fold-1
  command resumes from there (won't repeat those epochs). It early-stops ~epoch 31
  (val peaked at epoch 1, PATIENCE=30) and restores best weights.
- **folds 2–4:** not started.
- **Goal:** ensemble the folds → target **>0.80** on the 3 test signers
  (2044 / 37779 / 53618).

## The golden gotcha (why things broke before)
`build_model` in the **notebook kernel** decomposes Dense/attention into untracked
ops → `load_weights` silently loads a random model (0.004 = chance). **Always run
train / eval / export as a `!python` SUBPROCESS** (`!TF_USE_LEGACY_KERAS=1 python ...`),
never build+load in a notebook cell. The subprocess builds proper layers and loads
correctly. Confirm with the `>> proper build? classifier: True` line.

---

## Step A — reconnect + rehydrate `/content`
Colab wipes `/content` on recycle; Drive persists. After connecting to a GPU runtime:

```python
# 1) mount Drive
from google.colab import drive; drive.mount("/content/drive")

# 2) restore code from the Drive backup
!cp /content/drive/MyDrive/asl250_code/train.py .
!cp /content/drive/MyDrive/asl250_code/backbone_250.weights.h5 .

# 3) AWS creds (re-enter — they clear on recycle)
import os
os.environ["AWS_ACCESS_KEY_ID"]     = "PASTE"
os.environ["AWS_SECRET_ACCESS_KEY"] = "PASTE"
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"
!pip -q install awscli 2>/dev/null; echo ok

# 4) re-sync the data (~10-20 min)
!mkdir -p data
!aws s3 cp   s3://asl-mvp-dataset/splits/split_manifest.parquet data/split_manifest.parquet
!aws s3 sync s3://asl-mvp-dataset/preprocessed/by_word          data/by_word --quiet

# 5) verify
import os
print("train.py:", os.path.exists("train.py"),
      "| backbone:", os.path.exists("backbone_250.weights.h5"),
      "| data:", os.path.exists("data/by_word"))
```

## Step B — lock in fold-0 as a SavedModel (if not already done)
```python
%%writefile export_fold.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, ".")
import json
from pathlib import Path
import tensorflow as tf
from train import build_model, load_vocab
data = Path("data")
vocab = load_vocab(all_words=True, data_dir=data); words = vocab["words"]
m = build_model(num_classes=len(words))
m.load_weights("/content/drive/MyDrive/asl250_out/weights_all250_fold0_seed42.weights.h5")
out = "/content/drive/MyDrive/asl250_out/savedmodel_fold0"
try: m.export(out)
except AttributeError: tf.saved_model.save(m, out)
json.dump({"vocab_version": "v1-all250", "num_classes": len(words),
           "words": words, "word_to_index": vocab["word_to_index"]},
          open("/content/drive/MyDrive/asl250_out/vocab_250.json", "w"), indent=2)
print("exported SavedModel + froze vocab_250.json")
```
```python
!TF_USE_LEGACY_KERAS=1 python export_fold.py
```

## Step C — resume fold-1, then run fold-2
Same command as before → `BackupAndRestore` resumes fold-1 from ~epoch 30:
```python
!TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 1 \
  --init-from backbone_250.weights.h5 --lr 2e-4 --epochs 80 \
  --out-dir /content/drive/MyDrive/asl250_out
```
Then fold-2 (change `--fold 1` → `--fold 2`). Each fold auto-exports
`savedmodel_fold{N}` to Drive when it finishes (patched `train.py`).

## Step D — ensemble eval (the real >0.8 number)
After you have folds 0,1,2 (and optionally 3,4):
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

OUT = "/content/drive/MyDrive/asl250_out"
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
```

## Decision
- **ensemble ≥ 0.80** → done. Package `savedmodel_fold*/` + `vocab_250.json` +
  `ensemble_eval_250.json`, zip, pull to `artifacts_250/`, wire `--vocab250` into
  `live_demo.py` (TRAIN_250_PLAN.md Step 5).
- **~0.78–0.79** → train folds 3 and 4, re-run Step D.
- **Lever if stuck under 0.8:** add mirror TTA in the ensemble (average each fold's
  prediction on the clip AND its x→−x mirror) — the live demo already does this; it
  usually adds ~1–2%.

## If GPU is STILL limited when you return
Free-tier quota is per rolling ~24h. Options: wait longer, Colab Pro (~$10/mo,
continue immediately), or your EC2 GPU (no limits, ~$0.5–1/hr, needs the Step-A env
setup on the instance).
