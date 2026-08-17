# Train the 250-word model — detailed step-by-step

**Goal:** produce the same deliverables you have for the 30 words, but for all 250 —
a trained model, a per-word eval JSON, exported **SavedModels**, and it running in
`live_demo.py`. **Target: >0.8** overall (it will be below the 30-word 0.94 — more
classes = more confusable pairs; Kaggle top solutions land ~0.87–0.89 on 250, which
clears 0.8 comfortably).

**Read `SESSION_HANDOFF.md` first** for the surrounding context (model facts,
environment, why SavedModel, the vocab-order gotcha).

---

## The two golden rules (do not violate)

1. **All training / eval / export runs on a Linux GPU (Colab or EC2).** Not your
   Windows machine — GPU is needed, AND the `.weights.h5` files don't load on
   Windows (the path-separator bug). Windows only *runs* the exported SavedModel.
2. **Freeze `vocab_250.json` ON the training machine** (Step 2). The model's output
   index → word map is `sorted(manifest words)`; if you regenerate the vocab later
   from a different manifest, every label silently shifts. Freeze once, ship it with
   the model.

---

## What already exists (don't redo it)

- **Data in S3:** `s3://asl-mvp-dataset/preprocessed/by_word/<word>/sequences.npz`
  (all 250 words, `(T,75,3)` arrays) + `s3://asl-mvp-dataset/splits/split_manifest.parquet`
  (94,198 rows, participant-grouped, 5-fold CV + 3 held-out test signers
  2044/37779/53618).
- **A 250-class backbone:** `artifacts/backbone_250.weights.h5` — trained with
  `train.py --all-words` as pretraining for the 30-word model. It's a real 250-class
  model; it was just never honestly evaluated or exported. **We measure it first.**
- **`training/train.py`** already supports `--all-words` (dynamic 250 vocab from the
  manifest), `--fold all` (5-fold), and `--init-from` (warm start).

---

## Step 0 — Compute + environment (Colab or EC2)

- **Pick the machine.** Colab (Pro T4/A100, like `colab_fold0.ipynb`) or an EC2 GPU
  (g4dn/g5). *(Decision needed — it only changes how you sync data: Drive vs
  `aws s3 sync`.)*
- **Match the training environment.** `build_model` uses raw `tf.matmul` on symbolic
  tensors → it only builds under the **Keras 2 API**. Use the same setup that trained
  the 30-word model (see `training/README.md`): TF 2.15, or TF ≥2.16 with
  `TF_USE_LEGACY_KERAS=1` + `tf-keras`. Install: `tensorflow`, `tf-keras`, `numpy`,
  `pandas`, `pyarrow`.
- **Sync the data:**
  ```bash
  aws s3 sync s3://asl-mvp-dataset/preprocessed ./data/preprocessed
  aws s3 sync s3://asl-mvp-dataset/splits       ./data/splits
  # (or mount Google Drive if the data is there)
  ```
  This is the FULL 250-word set (several GB), not the 30-word subset.
- **Sanity check:** `split_manifest.parquet` loads; `by_word/` has 250 folders.

## Step 1 — Freeze the 250 vocab (CRITICAL, do it here)

On the training machine, dump the exact class order the model will use:
```python
# freeze_vocab250.py
import json
from pathlib import Path
import sys; sys.path.insert(0, "training")
from train import load_vocab
v = load_vocab(all_words=True, data_dir=Path("data/preprocessed"))  # sorted 250 words
json.dump({
    "vocab_version": "v1-all250",
    "num_classes": len(v["words"]),
    "words": v["words"],
    "word_to_index": v["word_to_index"],
}, open("vocab_250.json", "w"), indent=2)
print("froze", len(v["words"]), "words")
```
`vocab_250.json` now ships with the model forever. **Never regenerate it elsewhere.**

## Step 2 — FAST PATH: measure the existing backbone first

Before spending hours retraining, find out if `backbone_250` is already >0.8. Write
a small eval (it's `ensemble_eval.py` with `all_words=True` — that script hardcodes
the 30-word vocab, so make a variant):
```python
# eval_250.py  (Linux/GPU)
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, "training")
import json, numpy as np
from pathlib import Path
from train import build_model, load_vocab, load_dataset, make_tf_dataset
import tensorflow as tf

data = Path("data/preprocessed")
vocab = load_vocab(all_words=True, data_dir=data); words = vocab["words"]
man, arrays = load_dataset(data, vocab)
ev = man[(man["split"] == "test") & (~man["is_outlier"])].reset_index(drop=True)
ds = make_tf_dataset(ev, arrays, len(words), training=False)
y = ev["y"].to_numpy()

model = build_model(num_classes=len(words))
model.load_weights("artifacts/backbone_250.weights.h5")      # loads fine on Linux
probs = tf.nn.softmax(model.predict(ds), axis=1).numpy()
pred = probs.argmax(1)
overall = float((pred == y).mean())
per_word = {words[c]: float((pred[y == c] == c).mean()) for c in np.unique(y)}
json.dump({"overall_acc": overall, "per_word_acc": per_word,
           "worst": sorted(per_word, key=per_word.get)[:15]},
          open("eval_mvp250.json", "w"), indent=2)
print("BACKBONE test acc:", round(overall, 4))
```
- **If `overall` > 0.8 → you're done training. Go to Step 4 (export the backbone).**
  This can save you the whole retrain.
- **If < 0.8 → Step 3.**
- Either way, read `eval_mvp250.json` per-word to know which of the 250 are weak
  (drives the demo word choices + the confidence gate).

> The **test** split (signers 2044/37779/53618) was never in the backbone's training,
> so this number is honest even though the backbone was a pretraining run.

> **RESULT (2026-07-21): backbone-250 test acc = 0.7260** (13,998 test samples) →
> below 0.80 → go to Step 3. The backbone predates the accuracy levers (label
> smoothing, strong aug, hflip) and was single-fold, so proper training should lift
> it well past 0.8. Worst words: nap 0.05, there 0.12, go 0.14, mouth 0.15,
> give 0.15, awake 0.18 … (mostly confusable pairs + abstract words).

## Step 3 — Proper training (ONLY if the backbone is <0.8)

Train the folds you're missing to build a 5-fold ensemble (fold 0 ≈ the backbone):
```bash
# from-scratch-ish 5-fold, warm-started from the backbone (like the 30-word recipe)
python training/train.py --data-dir ./data/preprocessed --all-words --fold all \
    --init-from artifacts/backbone_250.weights.h5 --lr 2e-4 --epochs 120
```
- This applies the same accuracy levers as the 30-word model (label smoothing,
  augmentation incl. **hflip** — `FLIP_MAP` is 75-point, so it works unchanged for
  250, AWP stays OFF).
- It writes `weights_all250_fold{0..4}_seed42.weights.h5` per fold.
- **Quote the ENSEMBLE-ON-TEST accuracy** as the honest headline (test signers are
  clean of both backbone and fold training). CV numbers are slightly optimistic
  because the backbone saw CV participants — same caveat as the 30-word model.
- Watch each fold's val curve for collapse; early stopping is on.
- Time: a few hours per fold on a T4; much faster on an A100. If you only need >0.8,
  **a single good fold may be enough** — you don't strictly need all 5.

## Step 4 — Export to SavedModel + eval (Linux)

`train.py`'s `run_fold` **skips SavedModel export in `--all-words` mode**
(`if not all_words:`), so export explicitly:
```python
# export_250.py  (Linux)
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
import sys; sys.path.insert(0, "training")
from train import build_model
WEIGHTS = ["artifacts/backbone_250.weights.h5"]   # or the 5 fold files from Step 3
for i, w in enumerate(WEIGHTS):
    m = build_model(num_classes=250); m.load_weights(w)
    m.export(f"artifacts_250/savedmodel_fold{i}")   # TF SavedModel (like the 30-word)
    print("exported", w)
```
Then run `ensemble_eval` (the 250 variant) across the exported/weight set for the
final `eval_mvp250.json` (overall + per-word + confusion).

**Package to download to Windows:** `savedmodel_fold*/` + `vocab_250.json` +
`eval_mvp250.json`. Zip them (`fold_all_250.zip`) and pull to `artifacts_250/`.

## Step 5 — Wire into `live_demo.py` (Windows — I can do this)

- Add a `--vocab250` flag: point the model dirs at `artifacts_250/savedmodel_fold*`
  and `VOCAB_PATH` at `vocab_250.json`. The recognition pipeline is
  **class-count-agnostic** (`words[idx]`), so nothing else changes.
- **Sentences:** the rule engine only covers the 30-word combos → for 250 use
  **`--ai`** (handles any words); rules mode will just list unknown words via its
  fallback.
- **Confidence gate:** with 250 classes and more look-alikes, consider raising
  `CONF_GATE` a little; tune from the `[seg]` diagnostic lines.

## Step 6 — Verify

```bash
python live_demo.py --vocab250 --selftest   # expect output shape [250], softmax=1
python live_demo.py --vocab250 --ai         # live; read [seg] lines for weak words
```

## Step 7 — (later) TF.js export for the browser

When the browser path is ready, convert one fold's SavedModel → TF.js (like the
30-word `web_model.zip`) for the frontend. Not needed for the Python demo.

---

## Deliverables checklist (mirrors the 30-word set)
- [ ] `vocab_250.json` (frozen on the training machine)
- [ ] `eval_mvp250.json` (overall + per-word acc on the held-out test signers)
- [ ] `artifacts_250/savedmodel_fold*/` (1 for single, or 5 for the ensemble)
- [ ] `live_demo.py --vocab250` runs and recognizes 250 words
- [ ] (optional later) `web_model_250` TF.js for the browser

## Decisions still needed from Salim
- [ ] **Compute:** Colab or EC2? (only changes the data-sync step)
- [ ] **Single fold vs 5-fold ensemble** for shipping (single is enough for >0.8 and
      faster live; ensemble adds ~1% + robustness)
- [ ] If the backbone is close but under 0.8 — retrain all 5 folds, or just train a
      couple more and ensemble?

## Honest expectations
- Overall ~0.85–0.89 (below 30-word 0.94) — fine, clears >0.8.
- **Many more weak words** across 250 → the confidence gate + the `[seg]` diagnostics
  matter more; lead any demo with the strongest words.
- The grammar rules don't scale to 250 → the **AI sentence path is the real answer**
  at 250 (another reason the AI/sentence server, BE-10, matters).
