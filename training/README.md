# ASL MVP — training (Track A, Phase 4-5)

Companion to `BACKEND_TASKS.md` Phase 4/5 and `SPLIT_TRAIN_VALIDATE.md`.
Vocab is locked in [`../vocab_30.json`](../vocab_30.json) (30 words, label = index).

## Files
| File | Purpose |
|---|---|
| `train.py` | P4.2 — data loader + model (embedded `PreprocessLayer`) + fold training + eval report |
| `tfjs_smoke_test.py` | P4.3 — proves the untrained model converts to TF.js **before** spending GPU time |
| `requirements.txt` | pip deps (Colab has most already) |

## Baked-in decisions (don't change silently — they're cross-team contracts)
- **`MAX_LEN = 64` frames** — also the sliding-window length for frontend #20.
- **z dropped, dx/dx2 motion features added — inside the model** (`PreprocessLayer`), so the browser runs identical math after conversion. `--keep-z` exists for the fold-0 A/B only.
- **NaN = padding sentinel.** Real preprocessed frames contain no NaN. In the browser the window is always full, so padding never occurs at inference.
- **hflip augmentation OFF** until the preprocessing teammate supplies the left/right-hand index map for the 75-point layout (can't mirror hands without it).
- Index **30 reserved** for the no-sign class (Phase 6).

## Order of operations
```bash
pip install -r requirements.txt

# 1. P4.3 smoke test FIRST (any CPU, ~2-5 min, no data needed)
python tfjs_smoke_test.py

# 2. Get the data (~2 GB for 30 words; needs AWS creds or run on the EC2 role)
aws s3 cp s3://asl-mvp-dataset/splits/split_manifest.parquet data/
python - <<'EOF'
import json, subprocess
words = json.load(open("../vocab_30.json"))["words"]
for w in words:
    subprocess.run(["aws","s3","sync",f"s3://asl-mvp-dataset/preprocessed/by_word/{w}",f"data/by_word/{w}"],check=True)
EOF

# 3. P4.5 fold-0 gate run (GPU: Colab free T4 or g4dn.xlarge, ~1-3 h)
python train.py --data-dir ./data --fold 0
#    optional z A/B:  python train.py --data-dir ./data --fold 0 --keep-z

# 4. P5.1: inspect artifacts/eval_fold0.json (overall + per-word acc, worst words)
#    Healthy => P5.2 full CV:
python train.py --data-dir ./data --fold all
```

## Outputs (`artifacts/`)
- `history_fold{k}.csv` — loss/acc curves
- `eval_fold{k}.json` — overall + per-word accuracy, 5 worst words
- `confusion_fold{k}.csv` — 30×30 confusion matrix (feeds the confidence threshold + frontend #27)
- `model_fold{k}.keras` + `savedmodel_fold{k}/` — trained model (SavedModel feeds Phase 7 TF.js export)

## Known caveats (accepted for v1, revisit if fold 0 disappoints)
- **TF must be 2.15.x** (Keras 2). TF ≥2.16 ships Keras 3, which breaks both the custom AWP `train_step` and the tfjs converter. On newer Colab images: `pip install tf-keras` + `TF_USE_LEGACY_KERAS=1`.
- On **Windows**, `pip install tensorflowjs` fails (`uvloop`/`tensorflow-decision-forests` have no Windows builds). Workaround that works: `pip install tensorflowjs==4.17.0 --no-deps`, then `pip install tensorflow-hub --no-deps "packaging~=23.1" six`, then drop a one-line stub package named `tensorflow_decision_forests` into site-packages (`__version__ = "stub"`). Linux/Colab installs cleanly, no workaround needed.
- BatchNorm sees zeroed padded frames (stats slightly diluted). hoyso masked BN properly; we accept the simpler version for MVP and let the fold-0 gate judge it.
- Optimizer is AdamW + cosine (reference used RAdam+Lookahead via TFA, which is deprecated). Same family, close enough for v1.
- Keras version differences: if `label_smoothing` isn't accepted by `SparseCategoricalCrossentropy` in your TF build, the script falls back to plain CCE — you can also one-hot the labels and use `CategoricalCrossentropy(label_smoothing=0.1)`.
