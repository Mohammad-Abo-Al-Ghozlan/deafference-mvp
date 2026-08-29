#!/usr/bin/env python3
"""
Ensemble evaluation (Track A, Phase 5 — P5.2/P5.3).

Loads N trained models, runs each on a chosen split, averages their softmax
probabilities, and reports ensemble accuracy + per-word + confusion.

TWO WAYS TO LOAD (this matters — see the warning below):
  --models  artifacts_250/savedmodel_fold0 ...   EXPORTED SavedModel dirs  <-- USE THIS
  --weights artifacts/weights_*.weights.h5       raw Keras weights

  ⚠️  `.weights.h5` DOES NOT RELIABLY RELOAD on newer/"polluted" TF-Keras runtimes:
      build_model decomposes Dense/MultiHeadAttention into untracked TFOpLambda ops,
      so load_weights silently fails and you get CHANCE-LEVEL accuracy (the infamous
      0.0040) that looks like a broken model rather than a broken load. The SavedModel
      export sidesteps it entirely — which is why artifacts_250/ ships SavedModels and
      live_demo.py loads those. Prefer --models for anything you intend to quote.

IMPORTANT — which split to evaluate on:
  * --split test  : the held-out unseen participants. This is the HONEST
                    generalization number and the right one to quote. All models
                    predict the SAME test samples, so averaging is valid.
  * --split cv    : the whole CV pool (mixes each model's train+val) — only a
                    rough sanity check, NOT an honest number.

Note on the "honest average": each fold's own val accuracy (printed by train.py) averaged
across folds is the participant-CV estimate. This script instead measures the *ensemble on
the test set*, the deploy-relevant ceiling. Read both together.

Usage:
  # 250-word 4-fold ensemble from the exported SavedModels (the number to quote)
  python ensemble_eval.py --data-dir ./data --all-words \
      --models artifacts_250/savedmodel_fold0 artifacts_250/savedmodel_fold1 \
               artifacts_250/savedmodel_fold2 artifacts_250/savedmodel_fold3 \
      --out artifacts_250/ensemble_eval_250.json

  # 30-word 5-fold, same idea
  python ensemble_eval.py --data-dir ./data --models artifacts/savedmodel_fold*

  # legacy weights path (30-word only; see the warning above)
  python ensemble_eval.py --data-dir ./data --weights artifacts/weights_mvp30_fold*_seed42.weights.h5
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from train import build_model, load_vocab, load_dataset, make_tf_dataset


def load_savedmodel_fns(dirs):
    """Load exported SavedModels -> serving fns. Keeps the loaded objects alive so TF
    does not garbage-collect them (same approach as live_demo.load_models)."""
    loaded, fns = [], []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            raise SystemExit(f"[err] missing model dir: {d}")
        obj = tf.saved_model.load(str(d))
        sigs = obj.signatures
        # model.export() names the endpoint "serving_default" on some TF builds and
        # "serve" on others — take serving_default if present, else the first.
        key = "serving_default" if "serving_default" in sigs else list(sigs.keys())[0]
        loaded.append(obj)
        fns.append(sigs[key])
        print(f"[ok] loaded {d.name}  (signature '{key}')")
    return loaded, fns


def probs_from_savedmodel(fn, ds):
    """Run one SavedModel over the eval dataset -> (N, C) softmax probabilities."""
    out_probs = []
    for batch in ds:
        x = batch[0] if isinstance(batch, (tuple, list)) else batch
        try:
            out = fn(landmarks=x)                       # build_model names its Input "landmarks"
        except TypeError:
            out = fn(x)                                 # fall back to positional
        logits = out["output_0"] if "output_0" in out else list(out.values())[0]
        out_probs.append(tf.nn.softmax(logits, axis=1).numpy())
    return np.concatenate(out_probs, axis=0)


def probs_from_weights(model, w, ds):
    """Legacy path: load raw weights into a freshly built model -> (N, C) probs."""
    model.load_weights(w)
    logits = model.predict(ds, verbose=0)
    return tf.nn.softmax(logits, axis=1).numpy()


def main():
    ap = argparse.ArgumentParser(description="ensemble eval on a held-out split")
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--models", nargs="+", help="exported SavedModel dirs (PREFERRED)")
    ap.add_argument("--weights", nargs="+", help="legacy .weights.h5 files (see warning)")
    ap.add_argument("--all-words", action="store_true",
                    help="use the full (250-word) vocabulary instead of the 30-word set")
    ap.add_argument("--split", default="test", choices=["test", "cv"])
    ap.add_argument("--out", type=Path, default=Path("artifacts/ensemble_eval.json"))
    args = ap.parse_args()

    if not args.models and not args.weights:
        raise SystemExit("[err] pass --models (SavedModel dirs) or --weights (.weights.h5)")
    if args.models and args.weights:
        raise SystemExit("[err] pass only one of --models / --weights")

    vocab = load_vocab(all_words=args.all_words, data_dir=args.data_dir)
    words = vocab["words"]
    num_classes = len(words)
    man, arrays = load_dataset(args.data_dir, vocab)

    ev = man[man["split"] == args.split]
    ev = ev[~ev["is_outlier"]].reset_index(drop=True)   # honest eval excludes outliers
    if ev.empty:
        raise SystemExit(f"[err] no samples in split='{args.split}'")
    parts = sorted(int(p) for p in ev["participant_id"].unique())
    srcs = args.models or args.weights
    print(f"[cfg] {num_classes} classes | ensembling {len(srcs)} model(s) on "
          f"split='{args.split}': {len(ev)} samples, participants {parts}")

    # deterministic, no-aug dataset — identical inputs for every model (training=False
    # does not shuffle, so row order matches ev["y"] below)
    ds = make_tf_dataset(ev, arrays, num_classes, training=False)
    y_true = ev["y"].to_numpy()

    per_model, probs_sum = [], None
    if args.models:
        _loaded, fns = load_savedmodel_fns(args.models)
        for src, fn in zip(args.models, fns):
            p = probs_from_savedmodel(fn, ds)
            acc = float((p.argmax(1) == y_true).mean())
            per_model.append({"model": Path(src).name, "acc": round(acc, 4)})
            print(f"  {Path(src).name:40s} acc {acc:.4f}")
            probs_sum = p if probs_sum is None else probs_sum + p
    else:
        model = build_model(num_classes=num_classes)
        for w in args.weights:
            p = probs_from_weights(model, w, ds)
            acc = float((p.argmax(1) == y_true).mean())
            per_model.append({"model": Path(w).name, "acc": round(acc, 4)})
            print(f"  {Path(w).name:40s} acc {acc:.4f}")
            if acc < 2.0 / num_classes:
                print("      ⚠️  chance-level — this is the .weights.h5 reload bug, "
                      "not a bad model. Re-run with --models on the SavedModel export.")
            probs_sum = p if probs_sum is None else probs_sum + p

    ens_probs = probs_sum / len(srcs)
    ens_pred = ens_probs.argmax(1)
    ens_acc = float((ens_pred == y_true).mean())
    # top-5 matters for this product: live_demo's L3 gate shows top-K for the user to tap,
    # so top-5 is the ceiling of the "reject -> tap to fix" UX, not a vanity metric.
    top5 = float(np.mean([t in row for t, row in
                          zip(y_true, np.argsort(-ens_probs, axis=1)[:, :5])]))

    per_word = {words[c]: float((ens_pred[y_true == c] == c).mean())
                for c in np.unique(y_true)}
    conf = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, ens_pred):
        conf[t, p] += 1

    vals = np.array(list(per_word.values()))
    buckets = {f">={b:.1f}": int((vals >= b).sum()) for b in (0.9, 0.8, 0.7, 0.5)}
    buckets["<0.4"] = int((vals < 0.4).sum())

    mean_single = float(np.mean([m["acc"] for m in per_model]))
    report = {
        "split": args.split, "n_models": len(srcs), "n_classes": num_classes,
        # The row/col order of the .confusion.csv written below. WITHOUT this the CSV is
        # unreadable: per_word_acc only holds the classes PRESENT in the split (122 of 124
        # on the 2026-08-28 test run), so reconstructing labels from its keys silently
        # shifts every row after the first unscored class. Carry the order in the report.
        "class_names": list(words),
        "loaded_from": "savedmodel" if args.models else "weights.h5",
        "n_samples": int(len(ev)), "participants": parts,
        "per_model_acc": per_model,
        "mean_single_model_acc": round(mean_single, 4),
        "ensemble_acc": round(ens_acc, 4),
        "ensemble_gain_vs_mean_single": round(ens_acc - mean_single, 4),
        "ensemble_top5_acc": round(top5, 4),
        "per_word_bucket_counts": buckets,
        # MACRO = every word counts once, regardless of how many clips it has. On a corpus with
        # 170x class imbalance (Sem-Lex clinical: `water` 341 clips vs 8-clip classes) the
        # ensemble_acc above is a MICRO average carried by the frequent, easy words, and it hides
        # classes at exactly 0.000 — on 2026-08-28 those were burn / ear / face / faint / heart,
        # all core clinical vocabulary. Quote macro for a per-word menu; micro for stream accuracy.
        "per_word_macro_mean": round(float(vals.mean()), 4),
        "per_word_zeros": sorted(k for k, v in per_word.items() if v == 0.0),
        "per_word_median": round(float(np.median(vals)), 4),
        "per_word_acc": {k: round(v, 3) for k, v in per_word.items()},
        "worst_words": sorted(per_word, key=per_word.get)[:15],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    np.savetxt(args.out.with_suffix(".confusion.csv"), conf, fmt="%d", delimiter=",")

    print(f"\nmean single-model acc : {mean_single:.4f}")
    print(f"ENSEMBLE acc          : {ens_acc:.4f}  ({ens_acc - mean_single:+.4f} vs mean single)")
    print(f"ENSEMBLE top-5 acc    : {top5:.4f}   <- ceiling of the tap-to-fix UX")
    print(f"per-word MACRO mean   : {vals.mean():.4f}   <- every word counts once")
    print(f"per-word median       : {np.median(vals):.4f}   buckets {buckets}")
    print(f"words at exactly 0.00 : {len(report['per_word_zeros'])}  "
          f"{report['per_word_zeros'][:10]}")
    print(f"worst words           : {report['worst_words'][:8]}")
    print(f"written: {args.out}")
    print("\nQUOTE THIS as the ensemble number — and note it is the TEST split "
          "(unseen participants).")
    print("⚠️  On an imbalanced vocabulary quote the MACRO mean, not ensemble_acc: the latter is "
          "a micro average and a class at 0.000 barely moves it.")
    # Kaggle can finish every cell, write __results__.html, then hang in the output-save step and
    # report `Output 0 B` — losing this file while stdout survives in Logs (happened twice on
    # 2026-08-28). So the report goes to the LOG as well as to disk.
    print("\n----- report (also written to disk; echoed here so a save failure cannot lose it)")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
