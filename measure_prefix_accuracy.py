#!/usr/bin/env python
"""What does committing EARLY cost in accuracy? The exchange rate, measured.

WHY
---
The live demo's own instrumentation (2026-08-25, 28 commits) says response latency is a solved
problem: 25 of 28 commits took the early-commit path at 0 ms, 3 took the still path at 447 ms
p50, and nothing exceeded 500 ms. So there is no latency left to win.

The same log shows why it is that fast. `EARLY_MIN_SEC = 0.45` at the observed ~7 fps yields
early_min_fr = 4, and `--vocab250` sets `L2_STABLE = 1`, so four frames of signing plus ONE
agreeing preview is enough to commit. The log is full of `act4 sig6` -- six frames reaching a
model trained on clips resampled from a median of 41. `time_resize` then stretches 6 -> 64, an
11x upsample of a trajectory that mostly is not there yet.

That is a trade, and nobody had priced it. This prices it.

WHAT IT DOES
------------
Replays each exemplar through the LIVE pipeline at a simulated camera rate, truncated to the
first D seconds, and asks whether the top-1 is still right:

    take the first D seconds of the 30 fps exemplar
    -> subsample to round(D * live_fps) frames     (what the camera would have captured)
    -> time_resize to MAX_LEN                      (what live_demo feeds the model)
    -> predict, ensemble + mask, exactly as classify_segment does

Sweeping D gives accuracy as a function of how long you wait, and the derivative of that curve
is the price of every millisecond the early path saves.

READ THE NUMBERS AS A SHAPE, NOT AN ABSOLUTE
--------------------------------------------
These exemplars came from the corpus the model was trained on, so absolute accuracy here is
inflated and means nothing on its own -- do NOT quote it as a model score. The comparison
BETWEEN prefix lengths is the result, because every row is inflated the same way. This is a
within-condition comparison on purpose; the project has been burned three times by pooled
numbers that hid the structure underneath.

USAGE
    python measure_prefix_accuracy.py                  # sweep at 7 fps
    python measure_prefix_accuracy.py --fps 7 15       # two camera rates
    python measure_prefix_accuracy.py --single         # fold-0 only (faster)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import live_demo as ld
from sign_landmarks import canonicalize_missing

HERE = Path(__file__).resolve().parent
SRC_FPS = 30                      # the exemplar corpus rate


def prefix_clip(arr: np.ndarray, seconds: float, live_fps: float) -> np.ndarray | None:
    """First `seconds` of a 30 fps clip, as the camera at `live_fps` would have captured it."""
    n_src = int(round(seconds * SRC_FPS))
    if n_src < 2:
        return None
    head = arr[:min(n_src, arr.shape[0])]
    n_live = max(2, int(round(seconds * live_fps)))         # frames the camera would hold
    idx = np.linspace(0, head.shape[0] - 1, n_live).round().astype(int)
    return head[idx]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--fps", type=float, nargs="*", default=[7.0],
                    help="simulated camera rates (default: the observed 7)")
    ap.add_argument("--seconds", type=float, nargs="*",
                    default=[0.3, 0.45, 0.6, 0.8, 1.0, 1.4, 2.0],
                    help="prefix durations to test; 0.45 is EARLY_MIN_SEC today")
    ap.add_argument("--single", action="store_true", help="fold-0 only instead of the ensemble")
    # live_demo sets ARTIFACTS/VOCAB_PATH to the 250 versions only inside its --vocab250
    # argparse branch, which never runs on import. Defaulting to the module value silently
    # loaded the 30-CLASS model and scored it against 250 labels -> 0.000, which read like a
    # devastating result and was a harness bug. Pass it explicitly.
    ap.add_argument("--artifacts", default=str(HERE / "artifacts_250"))
    args = ap.parse_args()

    words = json.loads(Path(args.vocab).read_text(encoding="utf-8"))["words"]
    index = {w: i for i, w in enumerate(words)}
    # canonicalize_missing turns the npz zero-sentinel into NaN. Without it an absent hand sits
    # at [0,0,0] = mid-sternum, and PreprocessLayer builds its padding mask from is_nan -- so the
    # model is told every frame is real with a hand planted in the chest. Same trap that
    # gloss_to_motion.load_clips documents; skipping it was the second harness bug.
    with np.load(args.clips) as z:
        clips = {w: canonicalize_missing(z[w].astype(np.float32))
                 for w in z.files if w in index}
    print(f"[ok] {len(clips)} exemplars, {len(words)} classes")

    art = Path(args.artifacts)
    dirs = ([art / "savedmodel_fold0"] if args.single
            else [art / f"savedmodel_fold{k}" for k in range(4)])
    print(f"[ok] models from {art.name}")
    _keep, fns = ld.load_models(dirs)

    # Full-clip accuracy is the CEILING for this data -- every prefix row is measured against it,
    # so the inflation cancels and what remains is the cost of truncating.
    full = {}
    for w, arr in clips.items():
        x = ld.time_resize(arr, ld.MAX_LEN)[None].astype(np.float32)
        p = ld._mask_probs(ld.predict(fns, x))
        full[w] = int(np.argmax(p)) == index[w]
    ceiling = sum(full.values()) / len(full)
    print(f"[ok] full-clip top-1 on this data: {ceiling:.3f}  "
          f"<- CEILING for these rows, not a model score\n")

    for fps in args.fps:
        print(f"simulated camera {fps:.0f} fps")
        print(f"  {'wait':>6} {'frames':>7} {'top-1':>7} {'vs full':>8} {'lost':>6}   "
              f"{'newly wrong (examples)'}")
        for sec in args.seconds:
            ok, wrong_now = 0, []
            n = 0
            for w, arr in clips.items():
                sub = prefix_clip(arr, sec, fps)
                if sub is None:
                    continue
                n += 1
                x = ld.time_resize(sub, ld.MAX_LEN)[None].astype(np.float32)
                p = ld._mask_probs(ld.predict(fns, x))
                hit = int(np.argmax(p)) == index[w]
                ok += hit
                if full[w] and not hit:            # the wait broke it, not the data
                    wrong_now.append(w)
            acc = ok / max(n, 1)
            frames = max(2, int(round(sec * fps)))
            tag = "  <- EARLY_MIN_SEC today" if abs(sec - 0.45) < 1e-6 else ""
            print(f"  {sec:>5.2f}s {frames:>7} {acc:>7.3f} {acc - ceiling:>+8.3f} "
                  f"{len(wrong_now):>6}   {', '.join(wrong_now[:4])}{tag}")
        print()

    print("The 'lost' column is words the model gets RIGHT on the full clip and WRONG on the\n"
          "prefix -- i.e. words the early commit throws away. Latency is already 0 ms p50 on\n"
          "89% of commits, so anything this column shows is being paid for nothing.")


if __name__ == "__main__":
    main()
