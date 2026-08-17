#!/usr/bin/env python
"""Per-signer accuracy for one trained fold — the acceptance test for a layout change.

WHY THIS EXISTS (measured 2026-08-13)
-------------------------------------
Pooled test accuracy is blind to the failure that matters most here.  The fold-0 legacy model
scored **0.7658** on the held-out test split and looked like a new best.  Scored per signer, the
same weights ranged from **0.314 to 0.823** — a 51-point spread — because accuracy tracks
hand-block layout, which is a recording artifact:

    pid     L-block  R-block   acc    layout
    26734     0.02     1.00    0.823  pure R
    2044      0.01     1.00    0.806  pure R
    37779     0.00     1.00    0.780  pure R
    53618     0.13     0.88    0.707  R + contamination
    32319     1.00     0.04    0.614  pure L      <- ~-20 pts
    34503     1.00     0.08    0.577  pure L      <- ~-20 pts
    29302     0.48     0.99    0.314  BOTH blocks <- ~-50 pts

The test split contains **only R-dominant signers** (0.13 / 0.00 / 0.01), so it cannot measure
either penalty.  A canonicalization change aimed at those two failure modes would show ~nothing
on pooled test accuracy while moving the affected signers by tens of points.  That is why a
layout A/B must be judged here, on 34503 / 32319 / 29302, and never on the pooled number.

The val fold is the sensitive half (it holds 3 of the 4 affected signers) and is also slightly
optimistic, since model selection used it — EMA retains best-val_acc weights.

USAGE
-----
    python per_signer.py --data-dir <corpus> \
        --weights /kaggle/working/arm_control/weights_all250_fold0_seed42.weights.h5

Both groups are scored with the mask OFF and no augmentation.  Fold 0's model never saw the
fold-0 val participants nor any test participant, so all seven are honest held-out signers.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402
import tensorflow as tf                                                 # noqa: E402

from train import (build_model, load_vocab, load_dataset,                # noqa: E402
                   make_tf_dataset, _MASK_MODE)

# Baseline to compare a canonical run against: the 2026-08-13 legacy control, same seed and
# epochs. Hard-coded so a regression is visible without hunting for the old log.
LEGACY_CONTROL = {29302: 0.3141, 34503: 0.5774, 32319: 0.6143, 53618: 0.7069,
                  37779: 0.7796, 2044: 0.8062, 26734: 0.8231}
LEGACY_POOLED = 0.6656
AFFECTED = (34503, 32319, 29302)          # the two pure-L signers and the both-blocks one


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="corpus with by_word/ and the manifest")
    ap.add_argument("--weights", required=True, help="weights_all250_fold0_seed*.weights.h5")
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--out", default=None, help="optional JSON report path")
    args = ap.parse_args()

    # A mask applied here would silently change the yardstick between two arms.
    assert _MASK_MODE == "off", f"score with the mask OFF, got {_MASK_MODE!r}"
    data = Path(args.data_dir)
    assert (data / "by_word").is_dir(), f"no by_word/ under {data}"

    vocab = load_vocab(all_words=True, data_dir=data)
    words = vocab["words"]
    man, arrays = load_dataset(data, vocab)

    val = man[(man["split"] == "cv") & (man["fold"] == args.fold) & (~man["is_outlier"])]
    tst = man[(man["split"] == "test") & (~man["is_outlier"])]
    assert len(val) and len(tst), f"empty split: val={len(val)} test={len(tst)}"
    shared = set(val["participant_id"]) & set(tst["participant_id"])
    assert not shared, f"val and test share signers {shared} — not independent groups"

    ev = pd.concat([val.assign(grp="val"), tst.assign(grp="test")]).reset_index(drop=True)
    model = build_model(num_classes=len(words))
    model.load_weights(args.weights)
    pred = model.predict(make_tf_dataset(ev, arrays, len(words), training=False),
                         verbose=0).argmax(1)
    ev["ok"] = pred == ev["y"].to_numpy()

    g = (ev.groupby(["grp", "participant_id"])["ok"].agg(["mean", "size"])
           .sort_values("mean"))
    pooled = float(ev["ok"].mean())

    print(f"\nweights: {args.weights}")
    print(f"corpus : {data}\n")
    print(f"{'signer':>8} {'grp':>5} {'clips':>6} {'acc':>7} {'legacy':>8} {'delta':>8}")
    for (grp, pid), row in g.iterrows():
        base = LEGACY_CONTROL.get(int(pid))
        d = f"{row['mean'] - base:+.4f}" if base is not None else "     n/a"
        b = f"{base:.4f}" if base is not None else "   n/a"
        star = "  <-- affected" if int(pid) in AFFECTED else ""
        print(f"{int(pid):>8} {grp:>5} {int(row['size']):>6} {row['mean']:>7.4f} "
              f"{b:>8} {d:>8}{star}")

    lo, hi = float(g["mean"].min()), float(g["mean"].max())
    print(f"\n{len(g)} held-out signers   min {lo:.4f}   median {float(g['mean'].median()):.4f}"
          f"   max {hi:.4f}   spread {hi - lo:.4f}")
    print(f"pooled over all signers: {pooled:.4f}   (legacy control {LEGACY_POOLED:.4f}, "
          f"delta {pooled - LEGACY_POOLED:+.4f})")

    # The verdict the run exists to produce. Pooled movement is NOT the criterion: a layout fix
    # can be worth shipping on the strength of the affected signers alone, and can be worthless
    # despite a pooled gain if the affected signers did not move.
    acc = {int(p): float(m) for (_, p), m in g["mean"].items()}
    deltas = {p: acc[p] - LEGACY_CONTROL[p] for p in AFFECTED if p in acc}
    print("\nACCEPTANCE — the affected signers:")
    for p, d in deltas.items():
        print(f"  {p}: {LEGACY_CONTROL[p]:.4f} -> {acc[p]:.4f}   {d:+.4f}")
    if deltas:
        mean_d = sum(deltas.values()) / len(deltas)
        print(f"  mean delta on affected signers: {mean_d:+.4f}")
        # ~4.1k clips per signer -> SE ~0.008; 3 signers -> ~0.005 on the mean. 0.02 is a
        # deliberately unambitious bar: below it, the layout theory has not been demonstrated.
        # Built outside the f-string on purpose: a multi-line expression inside one is a syntax
        # error before Python 3.12, and this script has to run on Kaggle's interpreter.
        verdict = ("the layout change WORKS" if mean_d > 0.02
                   else "NOT demonstrated — do not build face landmarks on this")
        print(f"  VERDICT: {verdict}")
        if mean_d <= 0.02:
            print("  The handedness theory rests on 2 left-recorded signers and 1 both-blocks "
                  "signer. If they did not move, revisit the theory before spending more GPU.")

    if args.out:
        import json
        Path(args.out).write_text(json.dumps({
            "weights": str(args.weights), "data_dir": str(data), "fold": args.fold,
            "pooled": pooled, "per_signer": acc, "spread": hi - lo,
            "legacy_control": LEGACY_CONTROL,
            "affected_delta": deltas,
        }, indent=2), encoding="utf-8")
        print(f"\n[ok] report -> {args.out}")


if __name__ == "__main__":
    main()
