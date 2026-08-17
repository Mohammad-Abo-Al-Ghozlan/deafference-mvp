"""Tests for extract_canonical's geometric dominance rule.

The test that matters is section 3: it builds a clip whose RESTING hand has more tracked frames
than the signing hand and asserts the OLD rule picks the resting one.  If that assertion ever
stops failing under --dominance frames, the test has stopped being able to detect the bug it
exists for, and everything else here is decoration.

Run from the repo root:  python <this file>
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "training"))

from sign_landmarks import hand_arm_alignment                       # noqa: E402
from extract_canonical import (canonicalize, limb_assignment,       # noqa: E402
                               normalize_xy, pick_signing_block,
                               DOM_BLOCK, RESERVED_BLOCK, HAND_L, HAND_R)

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAIL.append(name)


def synth(T=24, *, moving="R", blocks=(), pose=True):
    """(T,75,3) clip. blocks = [(block_name, limb_it_sits_on, n_frames), ...]"""
    a = np.full((T, 75, 3), np.nan, np.float32)
    if pose:
        a[:, 11, :2] = [0.5, 0.0]                       # L shoulder (person's left)
        a[:, 12, :2] = [-0.5, 0.0]                      # R shoulder
        a[:, 11, 2] = a[:, 12, 2] = 0.0
        t = np.arange(T, dtype=np.float32)
        swing = 0.6 * np.sin(t / T * 6.0)
        still = np.zeros(T, np.float32)
        for wr, side, sx in ((15, "L", 0.5), (16, "R", -0.5)):
            d = swing if moving == side else still
            a[:, wr, 0] = sx + d
            a[:, wr, 1] = 0.8 + d
            a[:, wr, 2] = 0.0
    for name, limb, nf in blocks:
        blk = HAND_L if name == "L" else HAND_R
        wr = 15 if limb == "L" else 16
        a[:nf, blk.start, :2] = a[:nf, wr, :2]          # landmark 0 IS a wrist
        a[:nf, blk.start + 1:blk.stop, :2] = a[:nf, wr, :2][:, None, :] + 0.02
        a[:nf, blk, 2] = 0.0
    return a


print("\n== 1. cross-check against the proven sign_landmarks function ==")
# limb_assignment reimplements hand_arm_alignment's geometry for BOTH blocks. If the two ever
# disagree on the single-block case the reimplementation has drifted.
for blk_name, limb, mv in [("R", "R", "R"), ("L", "L", "L"), ("R", "R", "L"), ("L", "L", "R")]:
    a = synth(moving=mv, blocks=[(blk_name, limb, 20)])
    la = limb_assignment(normalize_xy(a))
    al = hand_arm_alignment(a)
    check(f"block={blk_name} limb={limb} moving={mv}: limb agrees",
          la["limb"][blk_name] == al["belongs"],
          f"mine={la['limb'][blk_name]} theirs={al['belongs']}")
    check(f"block={blk_name} limb={limb} moving={mv}: moving agrees",
          la["moving"] == al["moving"], f"mine={la['moving']} theirs={al['moving']}")

print("\n== 2. limb assignment is unambiguous, not marginal ==")
a = synth(moving="R", blocks=[("R", "R", 20)])
la = limb_assignment(normalize_xy(a))
d = la["d"]["R"]
check("own-limb distance far below other-limb", d["R"] * 5 < d["L"],
      f"d_to_R={d['R']:.3f}  d_to_L={d['L']:.3f}")
check("moving arm detected as R", la["moving"] == "R",
      f"travel L={la['travel']['L']} R={la['travel']['R']}")

print("\n== 3. THE R5 REGRESSION — resting hand has MORE frames than the signing hand ==")
# Right arm signs. Left (resting) block tracked for 20 frames, right (signing) for 6.
# Frame count therefore points at the resting hand. This is the real corpus's failure mode.
a = synth(moving="R", blocks=[("L", "L", 20), ("R", "R", 6)])
_, geo = canonicalize(a.copy(), dominance="geometric")
_, frm = canonicalize(a.copy(), dominance="frames")
check("geometric picks the SIGNING block (R)", geo["signing_block"] == "R",
      f"got {geo['signing_block']}, reason={geo['pick_reason']}")
check("geometric marks it aligned", geo["aligned"] is True)
check("legacy frame-count picks the RESTING block (L)", frm["signing_block"] == "L",
      f"got {frm['signing_block']} — if this is 'R' the test can no longer detect the bug")
check("the two rules DISAGREE on this clip", geo["signing_block"] != frm["signing_block"],
      "a passing ablation requires them to differ")
check("both_blocks recorded", geo["both_blocks"] is True)

print("\n== 4. both blocks, only one on the moving arm ==")
a = synth(moving="L", blocks=[("L", "L", 8), ("R", "R", 22)])
_, g = canonicalize(a.copy())
check("picks the block on the moving arm despite fewer frames", g["signing_block"] == "L",
      f"got {g['signing_block']} (frames L=8 R=22), reason={g['pick_reason']}")
check("orients by it -> mirrored", g["mirrored"] is True)

print("\n== 5. output invariants ==")
a = synth(moving="R", blocks=[("R", "R", 20)])
src = a.copy()
out, info = canonicalize(a.copy())
check("shape preserved", out.shape == src.shape, str(out.shape))
check("reserved block 33-53 fully NaN", bool(np.isnan(out[:, RESERVED_BLOCK, :]).all()))
check("dominant block carries the chosen hand",
      np.allclose(out[:20, DOM_BLOCK, :2], normalize_xy(src)[:20, HAND_R, :2],
                  equal_nan=True))
check("hand_frames == frames of the chosen block", info["hand_frames"] == 20,
      str(info["hand_frames"]))
check("not mirrored when the moving arm is already R", info["mirrored"] is False)

print("\n== 6. mirroring actually mirrors ==")
a = synth(moving="L", blocks=[("L", "L", 20)])
out, info = canonicalize(a.copy())
pre = normalize_xy(a.copy())
check("mirrored flag set", info["mirrored"] is True)
check("x negated on the pose block",
      np.allclose(out[:, 12, 0], -pre[:, 11, 0], equal_nan=True),
      "POSE_FLIP swaps 11<->12, so mirrored R shoulder == -(original L shoulder)")
check("signing hand ends up in the dominant block",
      bool(np.isfinite(out[:20, DOM_BLOCK, :2]).all()))

print("\n== 7. the --unaligned flag is not a no-op ==")
# Only the RESTING hand is tracked: the two policies must produce different orientations,
# otherwise the flag is a switch that cannot change anything.
a = synth(moving="R", blocks=[("L", "L", 20)])
_, mv = canonicalize(a.copy(), unaligned="moving")
_, hd = canonicalize(a.copy(), unaligned="hand")
check("both keep the only tracked hand",
      mv["signing_block"] == hd["signing_block"] == "L")
check("neither claims to be aligned", not mv["aligned"] and not hd["aligned"])
check("'moving' orients by the signing arm (no mirror)", mv["mirrored"] is False,
      f"reason={mv['pick_reason']}")
check("'hand' orients by the tracked hand's limb (mirror)", hd["mirrored"] is True,
      f"reason={hd['pick_reason']}")
check("policies DIFFER", mv["mirrored"] != hd["mirrored"])

print("\n== 7b. every pick_reason branch is REACHABLE ==")
# wrist_travel returns 0.0 (not NaN) for untracked wrists, so an "is it finite" guard here is
# always True and the no-motion branch would be dead code. These four cases must between them
# hit every reason the function can return; a reason no input can produce is a lie in the
# metadata.
_np = synth(blocks=[("R", "R", 10)]); _np[:, 15, :] = np.nan; _np[:, 16, :] = np.nan
_static = synth(moving=None, blocks=[("R", "R", 10)])              # both wrists still
cases = {
    "aligned": synth(moving="R", blocks=[("R", "R", 20)]),
    "unaligned_orient_by_moving": synth(moving="R", blocks=[("L", "L", 20)]),
    "no_hand": synth(blocks=[]),
    "no_motion_info": _np,
}
seen = {}
for want, clip in cases.items():
    _, info = canonicalize(clip.copy())
    seen[want] = info["pick_reason"]
    check(f"reason '{want}' is produced", info["pick_reason"] == want, f"got {seen[want]}")
_, st = canonicalize(_static.copy())
check("a genuinely static clip also lands in no_motion_info",
      st["pick_reason"] == "no_motion_info", f"got {st['pick_reason']}")
_, both = canonicalize(synth(moving="R", blocks=[("L", "R", 12), ("R", "R", 20)]).copy())
check("reason 'both_aligned_tie_by_distance' is producible",
      both["pick_reason"] == "both_aligned_tie_by_distance", f"got {both['pick_reason']}")

print("\n== 8. degenerate inputs do not crash ==")
for name, a in [
    ("no hands at all", synth(blocks=[])),
    ("no pose at all", synth(blocks=[("R", "R", 10)], pose=False)),
    ("2-frame clip", synth(T=2, blocks=[("R", "R", 2)])),
    ("hand present, pose wrists absent", None),
]:
    if a is None:
        a = synth(blocks=[("R", "R", 10)])
        a[:, 15, :] = np.nan
        a[:, 16, :] = np.nan
    try:
        out, info = canonicalize(a.copy())
        ok = out.shape == a.shape and isinstance(info["pick_reason"], str)
        check(f"{name}", ok, f"reason={info['pick_reason']}")
    except Exception as exc:                                        # noqa: BLE001
        check(f"{name}", False, f"raised {exc!r}")

print("\n== 9. metadata is flat (parquet-writable) ==")
import pandas as pd                                                 # noqa: E402
rows = []
for mv_, blks in [("R", [("R", "R", 20)]), ("L", [("L", "L", 12)]),
                  ("R", [("L", "L", 20), ("R", "R", 6)]), ("R", [])]:
    _, info = canonicalize(synth(moving=mv_, blocks=blks))
    info["key"] = "w/1_2"
    rows.append(info)
nested = [k for k, v in rows[0].items() if isinstance(v, (dict, list, tuple))]
check("no nested values in the metadata", not nested, str(nested))
try:
    df = pd.DataFrame(rows)
    import io
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    rt = pd.read_parquet(io.BytesIO(buf.getvalue()))
    check("round-trips through parquet", len(rt) == 4 and list(rt.columns) == list(df.columns))
except Exception as exc:                                            # noqa: BLE001
    check("round-trips through parquet", False, f"raised {exc!r}")

print(f"\n{'=' * 62}")
print(f"{len(FAIL)} FAILURES" if FAIL else "ALL CHECKS PASSED")
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
