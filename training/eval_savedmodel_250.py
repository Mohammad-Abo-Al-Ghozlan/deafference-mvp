#!/usr/bin/env python3
r"""
Verify the DEPLOYED 250-word model — the honest accuracy of what actually runs.

Why this script exists (and why it is NOT ensemble_eval.py):
  * The live demo loads the exported TF **SavedModels** in artifacts_250/
    (savedmodel_fold0..3) — NOT the .weights.h5 files.
  * ensemble_eval.py rebuilds the graph with build_model() + load_weights(). In
    newer/"polluted" tf-keras runtimes that path silently fails (Dense/MHA get
    decomposed into untracked TFOpLambda ops) → chance accuracy 0.0040. It also
    would measure a DIFFERENT set of weights than the ones we ship.
  * So this script loads the SavedModels DIRECTLY (exactly like live_demo.py) and
    averages their softmax on the held-out TEST signers. That is the deploy-
    relevant number: "how good is the model the user is actually signing to?"

It reuses train.py's data pipeline (load_dataset / make_tf_dataset) so the model
sees BYTE-IDENTICAL inputs to training — no normalization drift. Crucially, the
class order is pinned to the frozen vocab_250.json (NOT re-derived), so label i
means the same word the classifier was trained to output at index i.

RUN (in the training env where the S3 data + tensorflow live, i.e. your Kaggle GPU notebook):
  cd training
  python eval_savedmodel_250.py --data-dir /content/data
  # optional: point at a different export / vocab / split
  python eval_savedmodel_250.py --data-dir ./data \
      --models ../artifacts_250 --vocab ../vocab_250.json --split test

OUTPUT:
  * prints per-fold acc, the ENSEMBLE acc, and the worst words
  * writes artifacts_250/eval_savedmodel_<split>.json (overall + per-word)
This is the number that decides everything downstream: if it's ~0.76+ we tune
the UX; if it's weak we retrain + re-export. Until it exists, we're flying blind.
"""
from __future__ import annotations

# train.py expects Keras 2 semantics; set BEFORE any tf import it triggers.
import os
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

# data pipeline only — we deliberately do NOT use build_model/load_weights here.
from train import load_dataset, make_tf_dataset

REPO = Path(__file__).resolve().parent.parent


def _serving_fn(saved_model_dir: Path):
    """Load a SavedModel and return (kept_object, serving_fn, input_kwarg_name).
    Keep the loaded object alive so TF doesn't garbage-collect the fn's graph."""
    obj = tf.saved_model.load(str(saved_model_dir))
    sigs = obj.signatures
    key = "serving_default" if "serving_default" in sigs else list(sigs.keys())[0]
    fn = sigs[key]
    try:                                   # the input kwarg is the Keras input name
        in_key = list(fn.structured_input_signature[1].keys())[0]
    except Exception:
        in_key = "landmarks"
    return obj, fn, in_key


def _fold_probs(fn, in_key, xb) -> np.ndarray:
    """(B, C) softmax for ONE SavedModel on one batch. Falls back to per-row if
    the serving signature was traced with a fixed batch size."""
    x = tf.cast(xb, tf.float32)

    def _run(t):
        out = fn(**{in_key: t})
        logits = out["output_0"] if "output_0" in out else list(out.values())[0]
        return tf.nn.softmax(logits, axis=1).numpy()

    try:
        return _run(x)
    except Exception:                       # fixed-batch signature -> one row at a time
        return np.concatenate([_run(x[r:r + 1]) for r in range(int(x.shape[0]))], 0)


def main():
    ap = argparse.ArgumentParser(description="Evaluate the deployed 250-word SavedModels on held-out signers")
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="dataset root (has split_manifest.parquet + by_word/)")
    ap.add_argument("--models", type=Path, default=REPO / "artifacts_250",
                    help="dir of savedmodel_fold* (default ../artifacts_250)")
    ap.add_argument("--vocab", type=Path, default=REPO / "vocab_250.json",
                    help="frozen class-order vocab the models were trained with")
    ap.add_argument("--split", default="test", choices=["test", "cv"],
                    help="'test' = held-out unseen signers (the honest number)")
    ap.add_argument("--out", type=Path, default=None,
                    help="report path (default artifacts_250/eval_savedmodel_<split>.json)")
    args = ap.parse_args()

    # 1) class order PINNED to the frozen vocab (never re-derive — it would shift labels)
    frozen = json.loads(args.vocab.read_text(encoding="utf-8"))
    words = frozen["words"] if isinstance(frozen, dict) else frozen
    num_classes = len(words)
    vocab = {"words": words,
             "word_to_index": {w: i for i, w in enumerate(words)},
             "num_classes": num_classes,
             "note": "frozen 250 order (eval_savedmodel_250)"}
    print(f"[cfg] {num_classes} classes pinned to {args.vocab.name}")

    # 2) resolve the SavedModels the demo actually ships
    if args.models.is_dir() and not (args.models / "saved_model.pb").exists():
        model_dirs = sorted(d for d in args.models.glob("savedmodel_fold*") if d.is_dir())
    else:
        model_dirs = [args.models]                     # a single SavedModel dir
    if not model_dirs:
        raise SystemExit(f"[err] no savedmodel_fold* under {args.models}")
    print(f"[cfg] {len(model_dirs)} SavedModel(s): {[d.name for d in model_dirs]}")

    # 3) build the deterministic, no-aug eval set (identical inputs for every fold)
    man, arrays = load_dataset(args.data_dir, vocab)
    ev = man[man["split"] == args.split]
    if "is_outlier" in ev.columns:
        ev = ev[~ev["is_outlier"]]                     # honest eval excludes outliers
    ev = ev.reset_index(drop=True)
    parts = sorted(int(p) for p in ev["participant_id"].unique())
    print(f"[cfg] split='{args.split}': {len(ev)} samples, participants {parts}")
    ds = make_tf_dataset(ev, arrays, num_classes, training=False)
    y_true = ev["y"].to_numpy()

    # 4) per-fold probabilities (SavedModels loaded DIRECTLY — no build_model/load_weights)
    fns_keys = [_serving_fn(d) for d in model_dirs]
    per_fold_chunks = [[] for _ in fns_keys]
    n = 0
    for xb, _yb in ds:                                 # training=False -> order == ev
        for i, (_obj, fn, in_key) in enumerate(fns_keys):
            per_fold_chunks[i].append(_fold_probs(fn, in_key, xb))
        n += int(xb.shape[0])
    per_fold = [np.concatenate(c, 0) for c in per_fold_chunks]   # each (N, C)
    ens_probs = np.mean(per_fold, axis=0)                        # ensemble = mean softmax
    assert ens_probs.shape[0] == len(y_true) == n, \
        f"count mismatch: probs {ens_probs.shape[0]} vs labels {len(y_true)} vs seen {n}"

    # 5) metrics
    per_fold_acc = []
    for i, d in enumerate(model_dirs):
        acc = float((per_fold[i].argmax(1) == y_true).mean())
        per_fold_acc.append({"model": d.name, "acc": round(acc, 4)})
        print(f"  {d.name:24s} acc {acc:.4f}")
    ens_pred = ens_probs.argmax(1)
    ens_acc = float((ens_pred == y_true).mean())
    per_word = {words[c]: round(float((ens_pred[y_true == c] == c).mean()), 3)
                for c in np.unique(y_true)}
    mean_single = round(float(np.mean([m["acc"] for m in per_fold_acc])), 4)

    tiers = {f">={t:.2f}": int(sum(v >= t for v in per_word.values()))
             for t in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4)}
    report = {
        "split": args.split, "n_models": len(model_dirs), "n_samples": len(y_true),
        "participants": parts,
        "per_fold_acc": per_fold_acc,
        "mean_single_model_acc": mean_single,
        "ensemble_acc": round(ens_acc, 4),
        "ensemble_gain_vs_mean_single": round(ens_acc - mean_single, 4),
        "per_word_tiers": tiers,
        "worst_words": sorted(per_word, key=per_word.get)[:15],
        "per_word_acc": per_word,
    }
    out = args.out or (args.models / f"eval_savedmodel_{args.split}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nmean single-fold acc : {mean_single:.4f}")
    print(f"ENSEMBLE acc         : {ens_acc:.4f}  (+{ens_acc - mean_single:.4f} vs mean single)")
    print(f"per-word tiers       : {tiers}")
    print(f"worst 15 words       : {report['worst_words']}")
    print(f"\nwritten: {out}")
    print("→ compare ensemble_acc to fold-0's 0.7576. Higher = ship & tune UX; "
          "much lower = the export is weak, retrain + re-export.")


if __name__ == "__main__":
    main()
