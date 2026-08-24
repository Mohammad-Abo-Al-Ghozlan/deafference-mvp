#!/usr/bin/env python
"""How long does a hand genuinely hold STILL *inside* a sign? Measured, not guessed.

WHY
---
`live_demo.py` ends a sign when the hand stops moving for `STILL_SEC` (0.50 s), so that value is
a direct term in the response-latency budget: halving it saves 250 ms on every commit that takes
the slow path. But it cannot simply be lowered, because many signs contain an INTERNAL hold --
a pause partway through that is part of the word. Cut there and you commit half a sign, which
costs accuracy rather than latency.

The floor is therefore not a preference, it is a measurable property of the vocabulary: the
longest internal still-run across the 250 exemplars. This script measures it.

`STILL_SEC` must sit ABOVE that, or the affected words break.

HOW, AND WHY IT MATCHES THE LIVE PATH
-------------------------------------
Stillness is replicated exactly as `live_demo.py` computes it (around line 935):

    mv = mean(|hand_xy[t] - hand_xy[t-1]|)     over landmarks present in BOTH frames
    still  <=>  mv < MOTION_EPS (0.02)

Points 33..74 only (both hand blocks); pose is excluded, matching the live code. A frame where
no hand landmark is shared with its predecessor yields `mv = None`, and the live loop CARRIES
`still_count` across those rather than resetting -- so this does too. Clips are NOT hold-filled,
because the live path sees the genuine dropouts and its None-carrying behaviour depends on them.

Only INTERNAL runs count. The trailing run is the legitimate end-of-sign hold -- that is the
signal `STILL_SEC` is meant to detect, not a hazard.

THE FPS TRAP (the reason this sweeps a range)
---------------------------------------------
`mv` is a PER-FRAME displacement, and `MOTION_EPS` is a fixed constant. Every *duration* in
live_demo is converted to frames using the live frame rate (`still_fr = round(STILL_SEC * fps)`),
but this *velocity* threshold never is. The same real hand speed at 30 fps produces roughly a
quarter of the `mv` it produces at 7 fps, so the demo declares "still" far more readily at high
frame rates. The exemplars are 30 fps; the demo runs nearer 7. Comparing them at face value
would be wrong, so every rate is reported and the threshold is scaled to each.

USAGE
    python measure_still_runs.py                 # sweep, then the recommendation
    python measure_still_runs.py --fps 7         # one rate
    python measure_still_runs.py --worst 15      # show more offending words
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import preview_signs as ps

HERE = Path(__file__).resolve().parent
MOTION_EPS = 0.02          # live_demo.py:182 -- "hand movement below this = still"
HAND_LO, HAND_HI = 33, 75  # live_demo uses norm[POSE_N:N_POINTS] -- the two hand blocks
SRC_FPS = 30               # the exemplar corpus rate


def mv_series(arr: np.ndarray, eps: float) -> list[float | None]:
    """Per-frame hand displacement, exactly as live_demo computes `mv`. None = no shared point."""
    out: list[float | None] = []
    for t in range(1, arr.shape[0]):
        a = arr[t, HAND_LO:HAND_HI, :2]
        b = arr[t - 1, HAND_LO:HAND_HI, :2]
        m = ~(np.isnan(a).any(1) | np.isnan(b).any(1))
        out.append(float(np.mean(np.abs(a[m] - b[m]))) if m.any() else None)
    return out


def longest_internal_still(mv: list[float | None], eps: float) -> tuple[int, int]:
    """(longest internal still-run in frames, trailing still-run in frames).

    Mirrors live_demo's counter: a still frame increments, real movement resets, and `None`
    CARRIES the count (live_demo.py:968 -- resetting there meant face-signs never committed)."""
    runs, cur = [], 0
    for v in mv:
        if v is None:
            continue                       # carry: neither increment nor reset
        if v < eps:
            cur += 1
        else:
            if cur:
                runs.append((cur, False))  # ended by movement -> internal
            cur = 0
    trailing = cur                          # the run still open at the end of the clip
    internal = max((n for n, _ in runs), default=0)
    return internal, trailing


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"))
    ap.add_argument("--fps", type=float, nargs="*",
                    default=[5.0, 7.0, 10.0, 15.0, 30.0],
                    help="live frame rates to evaluate (default: sweep)")
    ap.add_argument("--worst", type=int, default=8, help="how many offending words to list")
    args = ap.parse_args()

    files = sorted((Path(args.handoff) / "words").glob("*.json"))
    if not files:
        raise SystemExit(f"[err] no word JSONs under {Path(args.handoff) / 'words'}")

    clips = {}
    for p in files:
        arr, _s, _g, _f = ps.load_json_clip(p)      # deliberately NOT hold-filled
        clips[p.stem] = arr
    print(f"[ok] {len(clips)} exemplars, source {SRC_FPS} fps\n")

    print(f"{'live fps':>9} {'eps':>8} {'p50':>7} {'p90':>7} {'p95':>7} {'max':>7} "
          f"{'>=0.50s':>8} {'>=0.30s':>8}")
    print("-" * 68)

    table = {}
    for fps in args.fps:
        step = SRC_FPS / fps
        # MOTION_EPS is calibrated against per-frame displacement at the live rate. A slower
        # rate means bigger steps between frames, so the threshold scales with the step.
        eps = MOTION_EPS * (SRC_FPS / fps) / (SRC_FPS / 7.0)   # anchored to the observed ~7 fps
        rows = []
        for w, arr in clips.items():
            idx = np.arange(0, arr.shape[0], step).round().astype(int)
            idx = idx[idx < arr.shape[0]]
            if idx.size < 3:
                continue
            mv = mv_series(arr[idx], eps)
            internal, _trail = longest_internal_still(mv, eps)
            rows.append((internal / fps, w))          # seconds
        secs = np.array([s for s, _ in rows])
        table[fps] = rows
        print(f"{fps:>9.0f} {eps:>8.4f} {np.percentile(secs,50):>7.2f} "
              f"{np.percentile(secs,90):>7.2f} {np.percentile(secs,95):>7.2f} {secs.max():>7.2f} "
              f"{int((secs>=0.50).sum()):>8} {int((secs>=0.30).sum()):>8}")

    # The demo's own fallback rate is 7 fps (live_demo.py:891), so that row drives the decision.
    key = min(table, key=lambda f: abs(f - 7.0))
    rows = sorted(table[key], reverse=True)
    p95 = float(np.percentile([s for s, _ in rows], 95))
    print(f"\nAt {key:.0f} fps (the demo's observed rate) the worst internal holds are:")
    for s, w in rows[:args.worst]:
        print(f"   {w:<14} {s:.2f}s")

    safe = max(0.20, round(p95 + 0.05, 2))
    print(f"\n  p95 internal hold : {p95:.2f}s")
    print(f"  RECOMMENDED STILL_SEC : {safe:.2f}s   (currently 0.50s)")
    if safe < 0.50:
        print(f"  -> saves {(0.50 - safe) * 1000:.0f} ms per slow-path commit, and by construction "
              f"still clears 95% of internal holds.")
        print(f"  -> the {int(sum(1 for s, _ in rows if s >= safe))} words above it are the ones to "
              f"watch in a live test; they are listed above.")
    else:
        print("  -> 0.50s is already at or below the measured floor. The latency is NOT here; "
              "look at inference cost and frame rate instead.")

    print("\n  NOTE: MOTION_EPS (live_demo.py:182) is a per-frame threshold that is never scaled "
          "by fps,\n  while every duration threshold is. The 'eps' column shows what it is "
          "effectively worth at\n  each rate. Two same-speed signers on different hardware get "
          "different segmentation.")


if __name__ == "__main__":
    main()
