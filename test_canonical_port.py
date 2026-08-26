#!/usr/bin/env python
"""Does --canonical actually put a left-dominant signer's hand where the weights expect it?

WHY THIS FILE EXISTS
--------------------
`live_demo.py --selftest` feeds the model random noise directly. It proves the graph loads and
predicts, and it passes IDENTICALLY with and without --canonical -- it never calls
classify_segment, so it never touches canonicalize_seg or _mirror. The two functions that make
canonical weights usable were, until this file, covered by nothing.

That matters because both failure modes here are SILENT. A left-dominant signer whose hand stays
at 33-53 does not crash; the model just returns confident nonsense for a block it has never seen
once (L-block occupancy is 0.000 across all seven corpus signers). And the mirror-map bug is
worse: classify_commit averages every clip with its mirror, so the legacy hand-swapping map would
feed HALF of every canonical prediction a clip whose only hand sits in the reserved block. Both
would read as "the new weights are worse than the old ones" and cost days.

No camera, no corpus, no weights -- a synthetic left-dominant clip is enough, because the claim
under test is about landmark bookkeeping, not accuracy.

USAGE
    python test_canonical_port.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "training"))

import live_demo as ld                      # noqa: E402
import extract_canonical as ec              # noqa: E402

T = 20


def occupancy(a: np.ndarray, block: slice) -> float:
    """Fraction of frames in which this hand block carries any finite coordinate."""
    return float(np.isfinite(a[:, block, :]).any(axis=(1, 2)).mean())


def left_dominant_clip() -> np.ndarray:
    """A clip whose LEFT arm signs and whose only tracked hand sits in the L block (33-53).

    Shoulders at x=-0.5 / +0.5 make mid=0 and width=1, i.e. the clip arrives already normalized
    the way live_demo.normalize() leaves it -- which is the real input canonicalize_seg gets.
    """
    a = np.full((T, ec.N_POINTS, ec.N_CH), np.nan, dtype=np.float32)
    a[:, :ec.POSE_N, :] = 0.0                                    # pose tracked, unremarkable
    a[:, ec.POSE_L_SHOULDER, :2] = (-0.5, 0.0)
    a[:, ec.POSE_R_SHOULDER, :2] = (0.5, 0.0)

    ly = np.linspace(0.5, -0.5, T, dtype=np.float32)              # left wrist travels 1.0
    a[:, ec.POSE_L_WRIST, 0] = -0.6
    a[:, ec.POSE_L_WRIST, 1] = ly
    a[:, ec.POSE_R_WRIST, :2] = (0.6, 0.5)                        # right wrist parked

    # 21 hand points clustered on the moving left wrist, L block only; R block stays NaN.
    off = np.linspace(-0.05, 0.05, 21, dtype=np.float32)
    a[:, ec.HAND_L, 0] = -0.6 + off[None, :]
    a[:, ec.HAND_L, 1] = ly[:, None]
    a[:, ec.HAND_L, 2] = 0.0
    return a


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{('   ' + detail) if detail else ''}")
    if not cond:
        raise AssertionError(label + " " + detail)


def main() -> None:
    print(__doc__.split("USAGE")[0].strip().splitlines()[0])
    print()

    # ---- 1. the two flip maps differ in exactly the way the docstring claims ----------------
    print("[1] flip maps")
    hands = slice(ld.POSE_N, ld.N_POINTS)
    legacy_moved = int((ld.FLIP_MAP[hands] != np.arange(ld.POSE_N, ld.N_POINTS)).sum())
    canon_moved = int((ld.FLIP_MAP_CANON[hands] != np.arange(ld.POSE_N, ld.N_POINTS)).sum())
    check("legacy map reindexes all 42 hand slots", legacy_moved == 42, f"{legacy_moved}")
    check("canonical map reindexes no hand slots", canon_moved == 0, f"{canon_moved}")
    check("canonical map keeps the pose half identical to legacy",
          np.array_equal(ld.FLIP_MAP_CANON[:ld.POSE_N], ld.FLIP_MAP[:ld.POSE_N]))
    check("both maps are permutations of 0..74",
          sorted(ld.FLIP_MAP.tolist()) == list(range(ld.N_POINTS))
          and sorted(ld.FLIP_MAP_CANON.tolist()) == list(range(ld.N_POINTS)))

    # ---- 2. canonicalize_seg moves the hand into the block the weights were trained on ------
    print("\n[2] canonicalize_seg on a LEFT-dominant clip")
    raw = left_dominant_clip()
    check("before: hand is in the L block, R block empty",
          occupancy(raw, ec.HAND_L) == 1.0 and occupancy(raw, ec.HAND_R) == 0.0,
          f"L {occupancy(raw, ec.HAND_L):.3f}  R {occupancy(raw, ec.HAND_R):.3f}")

    canon = np.stack(ld.canonicalize_seg(list(raw)))
    check("after: hand is in the dominant block, reserved block NaN",
          occupancy(canon, ec.DOM_BLOCK) == 1.0 and occupancy(canon, ec.RESERVED_BLOCK) == 0.0,
          f"L {occupancy(canon, ec.RESERVED_BLOCK):.3f}  R {occupancy(canon, ec.DOM_BLOCK):.3f}")
    check("the clip was mirrored (this signer is left-dominant)",
          ec.canonicalize(raw.copy())[1]["mirrored"] is True,
          ec.canonicalize(raw.copy())[1]["pick_reason"])
    check("no landmark was invented: same finite count, just relocated",
          np.isfinite(canon).sum() == np.isfinite(raw).sum(),
          f"{np.isfinite(raw).sum()} -> {np.isfinite(canon).sum()}")

    # ---- 3. idempotence: the live path may canonicalize an already-canonical segment --------
    print("\n[3] idempotence")
    again = np.stack(ld.canonicalize_seg(list(canon)))
    d = np.nanmax(np.abs(again - canon)) if np.isfinite(canon).any() else 0.0
    check("re-canonicalizing changes nothing", d == 0.0, f"max abs diff {d:.2e}")
    check("normalize_xy is the identity on normalized input",
          np.nanmax(np.abs(ec.normalize_xy(canon) - canon)) == 0.0)

    # ---- 4. the mirror map bug, reproduced then fixed ---------------------------------------
    print("\n[4] mirror TTA -- the bug classify_commit would have hit")
    x = canon[None]                                   # (1,T,75,3), the shape _mirror takes
    saved = ld.CANONICAL_HAND
    try:
        ld.CANONICAL_HAND = True
        good = ld._mirror(x)[0]
        ld.CANONICAL_HAND = False
        bad = ld._mirror(x)[0]
    finally:
        ld.CANONICAL_HAND = saved

    check("canonical map: mirrored view keeps the hand in the dominant block",
          occupancy(good, ec.DOM_BLOCK) == 1.0 and occupancy(good, ec.RESERVED_BLOCK) == 0.0,
          f"L {occupancy(good, ec.RESERVED_BLOCK):.3f}  R {occupancy(good, ec.DOM_BLOCK):.3f}")
    check("legacy map: mirrored view moves it to the block the model never saw  <- THE BUG",
          occupancy(bad, ec.RESERVED_BLOCK) == 1.0 and occupancy(bad, ec.DOM_BLOCK) == 0.0,
          f"L {occupancy(bad, ec.RESERVED_BLOCK):.3f}  R {occupancy(bad, ec.DOM_BLOCK):.3f}")
    check("mirroring negates x and leaves y alone",
          np.allclose(np.nan_to_num(good[:, ec.DOM_BLOCK, 0]),
                      -np.nan_to_num(canon[:, ec.DOM_BLOCK, 0]))
          and np.allclose(np.nan_to_num(good[:, ec.DOM_BLOCK, 1]),
                          np.nan_to_num(canon[:, ec.DOM_BLOCK, 1])))

    # ---- 5. a right-dominant clip must be left alone ---------------------------------------
    print("\n[5] right-dominant clip is not mirrored")
    flipped = raw.copy()
    flipped[..., 0] *= -1.0
    flipped[:, :ec.POSE_N, :] = flipped[:, ec.POSE_FLIP, :]
    hand = flipped[:, ec.HAND_L, :].copy()
    flipped[:, ec.HAND_L, :] = np.nan
    flipped[:, ec.HAND_R, :] = hand                    # same clip, right-handed
    meta = ec.canonicalize(flipped.copy())[1]
    check("dominant reads as R and no mirror is applied",
          meta["dominant"] == "R" and meta["mirrored"] is False, str(meta["pick_reason"]))
    rc = np.stack(ld.canonicalize_seg(list(flipped)))
    check("hand stays in the dominant block",
          occupancy(rc, ec.DOM_BLOCK) == 1.0 and occupancy(rc, ec.RESERVED_BLOCK) == 0.0)

    # ---- 6. the flag is off unless asked for ------------------------------------------------
    print("\n[6] default")
    check("CANONICAL_HAND defaults to False (legacy artifacts_250 unaffected)",
          ld.CANONICAL_HAND is False)

    print("\nALL CHECKS PASSED -- --canonical is safe to point at the decimate weights.")


if __name__ == "__main__":
    main()
