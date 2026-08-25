#!/usr/bin/env python
"""What does the commit gate buy? Precision vs throughput, priced on the real ensemble.

WHY
---
A Kaggle diagnostic (2026-08-25, fold-0 canonical model, 7 held-out signers, 30,200 clips)
established that per-signer variance is NOT fixable downstream. Nine hypotheses were measured
and refuted, including calibration itself: an ORACLE mean-shift using all 4,361 of the worst
signer's own clips moved it -0.0018, and a within-signer classifier fit on its own labels caps
at 0.3845 while the best signer reaches 0.9282. The information is gone before the model runs.

One axis did work. Gating on softmax confidence collapsed the per-signer spread:

    gate    worst signer   best signer   spread
    none        0.314         0.816       0.502
    0.50        0.690         0.919       0.229
    0.70        0.836         0.971       0.135
    0.80        0.884         0.985       0.101

The worst signer goes 0.314 -> 0.884. What the model does not know about WHICH word it saw, it
does know about WHETHER it knows. A coverage gate (hand_cov) was tested alongside and is
STRICTLY DOMINATED at matched throughput -- confidence already encodes the tracking signal --
so this script gates on confidence only, deliberately.

WHY THOSE NUMBERS CANNOT BE SHIPPED AS-IS
-----------------------------------------
That table came from a SINGLE fold-0 model scoring isolated clips. The demo runs the FOUR-fold
ensemble through `classify_commit` (view + mirror averaging) and then through `decide_commit`,
a three-level engine using confidence AND margin AND segment quality AND temporal stability.
Ensemble averaging changes the confidence DISTRIBUTION, not just its quality, so accept rates
at a fixed threshold shift. Transplanting 0.70 or 0.80 into live_demo would be guessing again.

This script re-prices the curve through the code that actually runs.

WHAT IT CANNOT TELL YOU
-----------------------
`sign_clips_250.npz` is keyed by WORD -- one exemplar per word, no participant ids. So there is
NO per-signer number here, and per-signer precision was the entire point of the Kaggle table.
This measures the ENSEMBLE + decide_commit correction to the curve's SHAPE. Reproducing the
per-signer table needs a Kaggle run with the 4 ensemble folds against the by-signer corpus.

Absolute precision here is not a model score either -- but NOT for the reason
measure_prefix_accuracy.py's docstring gives. That file asserts these exemplars are training data
and therefore "inflated"; the measurement contradicts it. Ungated top-1 here is 0.696 and it
measured 0.680 full-clip, both BELOW the shipped 4-fold test accuracy of 0.7755. So these clips
are HARDER than the real test set, not easier -- whatever the 7 fps downsample plus whatever these
250 canonical exemplars are costs more than any training-set familiarity gains. Treat the
precision column as a SHAPE and quite possibly a CONSERVATIVE one; do not quote it as a model
score in either direction. Between-row comparisons are the result. Same discipline as
measure_prefix_accuracy.py: the project has been burned three times by pooled absolutes.

USAGE
    python measure_conf_gate.py                    # 7 fps, 4-fold ensemble
    python measure_conf_gate.py --fps 15
    python measure_conf_gate.py --single           # fold-0 only (faster, not the demo's path)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import live_demo as ld
from sign_landmarks import canonicalize_missing

HERE = Path(__file__).resolve().parent
SRC_FPS = 30                       # the exemplar corpus rate

# live_demo.py:1340-1347 -- the thresholds `--vocab250` installs. They are assigned INSIDE the
# argparse branch, which never runs on import, so an importer gets the module-level 30-word
# values instead (L1_CONF 0.70, L1_MARGIN 0.30, L2_CONF 0.50, L2_MARGIN 0.18, L2_STABLE 1).
# Measuring against those would price a gate the 250 demo does not use. This is the THIRD time
# this trap has bitten -- see measure_prefix_accuracy.py:81-84 for the ARTIFACTS/VOCAB_PATH
# version of it. If live_demo's 250 branch changes, this dict must change with it.
V250 = dict(L1_CONF=0.58, L1_MARGIN=0.18, Q_STRONG=0.45,
            L2_CONF=0.40, L2_MARGIN=0.10, L2_STABLE=2)


def to_live(arr: np.ndarray, live_fps: float) -> np.ndarray:
    """The 30 fps exemplar as a camera running at `live_fps` would have captured it."""
    n = max(2, int(round(arr.shape[0] / SRC_FPS * live_fps)))
    idx = np.linspace(0, arr.shape[0] - 1, n).round().astype(int)
    return arr[idx]


def accepted(row: dict, L1_CONF: float, L1_MARGIN: float, Q_STRONG: float,
             L2_CONF: float, L2_MARGIN: float) -> int:
    """Mirror decide_commit's LEVEL 1/2 arithmetic -> 1 (level 1), 2 (level 2), 0 (rejected).

    Parameter names match live_demo's globals on purpose: every caller here passes them as
    **kwargs pulled from V250, so a rename on either side fails loudly instead of silently
    pricing the wrong gate.

    `stable` is treated as satisfied, exactly as commit_segment does: it calls
    decide_commit(..., stable=L2_STABLE) at the pause, because the sign is FINISHED there and
    temporal confirmation has already happened (live_demo.py:788)."""
    margin = row["conf"] - row["second"]
    if row["conf"] >= L1_CONF and margin >= L1_MARGIN and row["q"] >= Q_STRONG:
        return 1
    if row["conf"] >= L2_CONF and margin >= L2_MARGIN:
        return 2
    return 0


def score(rows: list[dict], **th) -> tuple[int, int, float]:
    """-> (accepted, correct-among-accepted, precision)."""
    hits = [r for r in rows if accepted(r, **th)]
    ok = sum(r["ok"] for r in hits)
    return len(hits), ok, (ok / len(hits) if hits else float("nan"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--artifacts", default=str(HERE / "artifacts_250"))
    ap.add_argument("--fps", type=float, default=7.0,
                    help="simulated camera rate (default: the demo's observed 7)")
    ap.add_argument("--single", action="store_true",
                    help="fold-0 only; NOT what the demo runs, use for a quick check")
    ap.add_argument("--worst", type=int, default=12, help="how many never-committed words to list")
    args = ap.parse_args()

    words = json.loads(Path(args.vocab).read_text(encoding="utf-8"))["words"]
    index = {w: i for i, w in enumerate(words)}
    # canonicalize_missing turns the npz zero-sentinel into NaN. Without it an absent hand sits
    # at [0,0,0] = mid-sternum and PreprocessLayer's padding mask (built from is_nan) is told
    # every frame is real. Skipping it once already produced a fake 0.000 accuracy.
    with np.load(args.clips) as z:
        clips = {w: canonicalize_missing(z[w].astype(np.float32))
                 for w in z.files if w in index}
    print(f"[ok] {len(clips)} exemplars, {len(words)} classes")

    art = Path(args.artifacts)
    dirs = ([art / "savedmodel_fold0"] if args.single
            else [art / f"savedmodel_fold{k}" for k in range(4)])
    _keep, fns = ld.load_models(dirs)
    print(f"[ok] {'fold-0 only' if args.single else '4-fold ensemble'} from {art.name}")

    for k, v in V250.items():
        was = getattr(ld, k)
        setattr(ld, k, v)
        if was != v:
            print(f"[cfg] {k}: {was} -> {v}   (module default was the 30-word value)")

    # One forward pass per word. Every threshold sweep below is then pure arithmetic over
    # `rows`, so the sweep costs nothing and the numbers cannot drift between conditions.
    rows: list[dict] = []
    for w, arr in clips.items():
        seg = list(to_live(arr, args.fps))                  # list of (75,3), as the live loop holds
        probs = ld.classify_commit(fns, seg)                # view + mirror, the real commit path
        order = np.argsort(probs)[::-1]
        q, hp = ld.segment_quality(seg)
        rows.append({"word": w, "conf": float(probs[order[0]]),
                     "second": float(probs[order[1]]), "q": float(q), "hp": float(hp),
                     "ok": int(order[0] == index[w])})

    ceiling = sum(r["ok"] for r in rows) / len(rows)
    print(f"[ok] ungated top-1 at {args.fps:.0f} fps: {ceiling:.3f}   "
          f"<- CEILING for these rows, NOT a model score\n")

    # L2_STABLE is not a decide_commit threshold, it is the stability COUNT the caller supplies,
    # so it is excluded here rather than passed and ignored.
    shipped = {k: v for k, v in V250.items() if k != "L2_STABLE"}
    n, ok, prec = score(rows, **shipped)
    lv = [accepted(r, **shipped) for r in rows]
    print(f"THE DEMO AS IT SHIPS TODAY (L1 {V250['L1_CONF']} / L2 {V250['L2_CONF']})")
    print(f"  accept {n}/{len(rows)} ({100*n/len(rows):.0f}%)   precision {prec:.3f}   "
          f"vs ungated {ceiling:.3f}  ({prec - ceiling:+.3f})")
    for level in (1, 2):
        sel = [r for r, l in zip(rows, lv) if l == level]
        if sel:
            print(f"    level {level}: {len(sel):>3} accepted, precision "
                  f"{sum(r['ok'] for r in sel)/len(sel):.3f}")
    print()

    # Sweep one scalar as BOTH gates -- the form comparable to the Kaggle table, which used a
    # plain max-softmax threshold. Margins stay at their shipped values.
    print("CONFIDENCE SWEEP (margins at shipped values, L1_CONF = L2_CONF = gate)")
    print(f"  {'gate':>6} {'accept':>8} {'precision':>10} {'vs ungated':>11}")
    for t in (0.0, 0.30, 0.40, 0.50, 0.58, 0.60, 0.70, 0.80, 0.90):
        n, ok, prec = score(rows, L1_CONF=t, L1_MARGIN=V250["L1_MARGIN"],
                            Q_STRONG=V250["Q_STRONG"], L2_CONF=t, L2_MARGIN=V250["L2_MARGIN"])
        tag = "   <- L2 today" if abs(t - V250["L2_CONF"]) < 1e-9 else (
              "   <- L1 today" if abs(t - V250["L1_CONF"]) < 1e-9 else "")
        print(f"  {t:>6.2f} {f'{100*n/len(rows):.0f}%':>8} {prec:>10.3f} "
              f"{prec - ceiling:>+11.3f}{tag}")
    print()

    # Does the margin rule earn its complexity? The Kaggle table showed confidence alone is a
    # strong discriminator; if zeroing the margins costs nothing at matched throughput, the
    # engine can lose two thresholds. Compare ROWS AT SIMILAR ACCEPT RATES, not at equal gate.
    print("MARGIN ABLATION (same sweep, L1_MARGIN = L2_MARGIN = 0)")
    print(f"  {'gate':>6} {'accept':>8} {'precision':>10}")
    for t in (0.0, 0.30, 0.40, 0.50, 0.58, 0.60, 0.70, 0.80, 0.90):
        n, ok, prec = score(rows, L1_CONF=t, L1_MARGIN=0.0, Q_STRONG=V250["Q_STRONG"],
                            L2_CONF=t, L2_MARGIN=0.0)
        print(f"  {t:>6.2f} {f'{100*n/len(rows):.0f}%':>8} {prec:>10.3f}")
    print()

    never = [r for r, l in zip(rows, lv) if l == 0]
    print(f"NEVER COMMITTED at the shipped gate: {len(never)} words "
          f"({100*len(never)/len(rows):.0f}%) -- these hit top-K instead")
    for r in sorted(never, key=lambda r: -r["conf"])[:args.worst]:
        print(f"   {r['word']:<14} conf {r['conf']:.2f}  margin "
              f"{r['conf']-r['second']:.2f}  q {r['q']:.2f}  "
              f"{'(top-1 was RIGHT)' if r['ok'] else ''}")
    right_rejected = sum(r["ok"] for r in never)
    print(f"\n  {right_rejected} of those {len(never)} had the CORRECT top-1 -- the gate's cost, "
          f"paid\n  to remove {len(never) - right_rejected} wrong ones. Read that ratio before "
          f"raising the gate.")

    print("\nREAD THIS AS A SHAPE. One exemplar per word (n=250, so precision has an SE near\n"
          "0.03 at 50% accept), training-corpus data, and NO per-signer breakdown is possible\n"
          "from this npz. The per-signer table -- the reason the gate matters at all -- needs a\n"
          "Kaggle run with these 4 folds against the by-signer corpus.")


if __name__ == "__main__":
    main()
