#!/usr/bin/env python3
r"""
Acceptance test for semlex_poses_to_75.py — the guard against the 553-vs-543 trap.

WHY THIS FILE IS NOT test_parity.py
-----------------------------------
`test_parity.py` proves `extract_landmarks.py`'s FUNCTIONS match `live_demo.py`'s to
0.000e+00. It passes whatever indices you feed those functions, so it cannot see a
wrong slice. Sem-Lex ships **553** landmarks (face mesh + 10 iris points), not the 543
every other array in this project uses, which shifts pose and both hands by +10. Feed
543-style offsets to a 553 array and you read iris points as the pose: right shapes,
plausible numbers, quietly ruined training.

So this file tests the thing the other one structurally cannot — the INDEX MAP — using
a marker array where every landmark's value IS its own source index. An off-by-anything
shows up as a numeric mismatch, not as a shrug.

It also asserts the adapter *imports* normalize/time_resize rather than copying them.
The parity chain is: live_demo -> (test_parity.py, 0.0 diff) -> extract_landmarks ->
(identity, checked here) -> semlex_poses_to_75. A copy anywhere in that chain breaks it
silently, so the link is a test, not a comment.

RUN
    python training/medical/test_semlex_adapter.py
    python training/medical/test_semlex_adapter.py --poses semlex_clinical_poses.tar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import extract_landmarks as EL                                          # noqa: E402
import semlex_poses_to_75 as SL                                         # noqa: E402

OK = "  [ok]  "
FAIL = "  [FAIL] "
_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{OK if cond else FAIL}{name}" + (f"   {detail}" if detail else ""))
    if not cond:
        _fails.append(name)


def marker_clip(t: int = 5) -> np.ndarray:
    """(t,553,3) float16 where every value equals its own SOURCE landmark index.
    float16 represents integers exactly up to 2048, and 552 < 2048, so the marker
    survives the dtype round-trip and any mismatch is a real index error."""
    idx = np.arange(SL.SEMLEX_N, dtype=np.float32)
    return np.broadcast_to(idx[None, :, None], (t, SL.SEMLEX_N, 3)).astype(np.float16)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", help="optional: a real .tar / dir of pose .npy to re-verify on")
    args = ap.parse_args()

    print("=" * 74)
    print("[1] LAYOUT ARITHMETIC — the offsets must tile 553 with no gap and no overlap")
    blocks = [("face", 0, SL.SEMLEX_FACE_N),
              ("pose", SL.SEMLEX_POSE.start, SL.SEMLEX_POSE.stop),
              ("L hand", SL.SEMLEX_L_HAND.start, SL.SEMLEX_L_HAND.stop),
              ("R hand", SL.SEMLEX_R_HAND.start, SL.SEMLEX_R_HAND.stop)]
    for nm, a, b in blocks:
        print(f"         {nm:<7} {a:>4}..{b - 1:<4} ({b - a} points)")
    check("blocks are contiguous and cover exactly 553",
          all(blocks[i][2] == blocks[i + 1][1] for i in range(3)) and blocks[-1][2] == SL.SEMLEX_N)
    check("face block is 478 = 468 mesh + 10 iris", SL.SEMLEX_FACE_N == 478,
          "refine_landmarks=True is what makes it 553, not 543")
    check("pose/hand sizes match our contract",
          (SL.SEMLEX_POSE.stop - SL.SEMLEX_POSE.start == EL.POSE_N
           and SL.SEMLEX_L_HAND.stop - SL.SEMLEX_L_HAND.start == EL.HAND_N
           and SL.SEMLEX_R_HAND.stop - SL.SEMLEX_R_HAND.start == EL.HAND_N))
    check("the 543-style offset would be WRONG here",
          468 + EL.POSE_N + 2 * EL.HAND_N != SL.SEMLEX_N,
          f"543 != {SL.SEMLEX_N} — this is the bug the file exists to prevent")

    print("\n[2] INDEX MAP — every destination slot must hold its correct SOURCE index")
    out = SL.to_75(marker_clip())
    exp_pose = np.arange(478, 511, dtype=np.float32)
    exp_l    = np.arange(511, 532, dtype=np.float32)
    exp_r    = np.arange(532, 553, dtype=np.float32)
    got_pose, got_l, got_r = out[0, 0:33, 0], out[0, 33:54, 0], out[0, 54:75, 0]
    check("our pose 0-32 <- Sem-Lex 478-510", np.array_equal(got_pose, exp_pose),
          f"first/last got {got_pose[0]:.0f}/{got_pose[-1]:.0f}, want 478/510")
    check("our L hand 33-53 <- Sem-Lex 511-531", np.array_equal(got_l, exp_l),
          f"first/last got {got_l[0]:.0f}/{got_l[-1]:.0f}, want 511/531")
    check("our R hand 54-74 <- Sem-Lex 532-552", np.array_equal(got_r, exp_r),
          f"first/last got {got_r[0]:.0f}/{got_r[-1]:.0f}, want 532/552")
    check("no face/iris index leaked into the output (all >= 478)", float(out.min()) >= 478.0,
          f"min value {float(out.min()):.0f} — anything < 478 is a face point read as pose")
    check("all three coordinate channels mapped identically",
          np.array_equal(out[..., 0], out[..., 1]) and np.array_equal(out[..., 0], out[..., 2]))
    check("output shape and dtype", out.shape == (5, EL.N_POINTS, 3) and out.dtype == np.float32,
          f"{out.shape} {out.dtype}")

    print("\n[3] NOTHING INVENTED, NOTHING DESTROYED")
    c = marker_clip(4).astype(np.float32)
    c[:, SL.SEMLEX_R_HAND, :] = np.nan                 # an untracked right hand
    o = SL.to_75(c)
    check("an all-NaN hand block stays all-NaN (never becomes 0.0)",
          bool(np.isnan(o[:, 54:75]).all()) and not bool(np.isnan(o[:, 0:54]).any()),
          "0.0 is a LEGAL coordinate in our contract — it means 'at the shoulder midpoint'")
    n_finite_in  = int(np.isfinite(c[:, 478:, :]).sum())
    n_finite_out = int(np.isfinite(o).sum())
    check("finite landmark count is preserved (relocated, not fabricated)",
          n_finite_in == n_finite_out, f"{n_finite_in} -> {n_finite_out}")
    check("float16 input is widened before any maths", SL.to_75(marker_clip()).dtype == np.float32)

    print("\n[4] PARITY CHAIN — the adapter must IMPORT, not copy")
    check("normalize is extract_landmarks.normalize (same object)",
          SL.normalize is EL.normalize)
    check("time_resize is extract_landmarks.time_resize (same object)",
          SL.time_resize is EL.time_resize)
    check("constants shared, not redeclared",
          (SL.N_POINTS, SL.POSE_N, SL.HAND_N, SL.MAX_LEN) ==
          (EL.N_POINTS, EL.POSE_N, EL.HAND_N, EL.MAX_LEN))

    print("\n[5] NORMALIZATION INVARIANTS on real-shaped synthetic input")
    T = 20
    rng = np.random.default_rng(0)
    clip = np.full((T, SL.SEMLEX_N, 3), np.nan, dtype=np.float32)
    clip[:, SL.SEMLEX_POSE, :] = rng.normal(0.5, 0.05, (T, EL.POSE_N, 3)).astype(np.float32)
    clip[:, 478 + 11, :2] = [0.40, 0.30]               # left shoulder
    clip[:, 478 + 12, :2] = [0.60, 0.30]               # right shoulder -> width 0.20
    clip[:, SL.SEMLEX_L_HAND, :] = rng.normal(0.45, 0.02, (T, EL.HAND_N, 3)).astype(np.float32)
    clip[:, SL.SEMLEX_R_HAND, :] = rng.normal(0.55, 0.02, (T, EL.HAND_N, 3)).astype(np.float32)

    p = SL.to_75(clip)
    z_before = p[0, 5, 2]
    nrm = EL.normalize(p[0])
    ls, rs = nrm[EL.L_SHOULDER, :2], nrm[EL.R_SHOULDER, :2]
    mid, width = (ls + rs) / 2.0, float(np.linalg.norm(ls - rs))
    check("shoulder midpoint -> (0,0)", abs(mid[0]) < 1e-6 and abs(mid[1]) < 1e-6,
          f"({mid[0]:+.7f}, {mid[1]:+.7f})")
    check("shoulder width -> 1.0", abs(width - 1.0) < 1e-6, f"{width:.7f}")
    check("z is untouched by normalize", nrm[5, 2] == z_before, f"{z_before:.6f}")

    print("\n[6] GATES behave like extract_landmarks'")
    arr, st = SL.clip_to_tensor(clip)
    check("a good clip yields (64,75,3) float32",
          arr is not None and arr.shape == (EL.MAX_LEN, EL.N_POINTS, 3) and arr.dtype == np.float32,
          f"{None if arr is None else arr.shape} valid={st['valid']} hand_rate={st['hand_rate']:.2f}")
    noshoulder = clip.copy()
    noshoulder[:, 478 + 11, :] = np.nan               # shoulders gone -> every frame unnormalizable
    a2, s2 = SL.clip_to_tensor(noshoulder)
    check("frames without both shoulders are DROPPED, not rescaled",
          a2 is None and s2["valid"] == 0, s2["reason"])
    nohands = clip.copy()
    nohands[:, SL.SEMLEX_L_HAND, :] = np.nan
    nohands[:, SL.SEMLEX_R_HAND, :] = np.nan
    # Rejected either way, but by a DIFFERENT gate: with trim on, the span check fires first
    # and says so; with trim off, the hand-rate gate fires. Pin both, so a future change that
    # skips one of them cannot pass silently.
    a3, s3 = SL.clip_to_tensor(nohands, trim=True)
    check("no tracked hand, trim ON -> rejected by the span gate",
          a3 is None and "no tracked hand" in s3["reason"], s3["reason"])
    a3b, s3b = SL.clip_to_tensor(nohands, trim=False)
    check("no tracked hand, trim OFF -> rejected by the hand-rate gate",
          a3b is None and "hand in only" in s3b["reason"], s3b["reason"])
    check("hand_seen: all-NaN False, one finite point True",
          (not SL.hand_seen(np.full((EL.HAND_N, 3), np.nan)))
          and SL.hand_seen(np.where(np.arange(EL.HAND_N * 3).reshape(EL.HAND_N, 3) == 0,
                                    0.5, np.nan)))

    print("\n[6b] TRIM TO THE TRACKED SPAN — the fix for the 48.5% rejection")
    # A realistic Sem-Lex clip: 60 frames, hands tracked only in the middle 24. Raw hand-rate
    # 0.40... so build the miss deliberately below the gate instead: 20 tracked of 60 = 0.33.
    T2 = 60
    dead = np.full((T2, SL.SEMLEX_N, 3), np.nan, dtype=np.float32)
    dead[:, SL.SEMLEX_POSE, :] = rng.normal(0.5, 0.05, (T2, EL.POSE_N, 3)).astype(np.float32)
    dead[:, 478 + 11, :2] = [0.40, 0.30]
    dead[:, 478 + 12, :2] = [0.60, 0.30]
    LO, HI = 20, 40                                    # hands present on frames 20..39 only
    dead[LO:HI, SL.SEMLEX_L_HAND, :] = rng.normal(0.45, 0.02, (HI - LO, EL.HAND_N, 3))
    dead[LO:HI, SL.SEMLEX_R_HAND, :] = rng.normal(0.55, 0.02, (HI - LO, EL.HAND_N, 3))
    raw_rate = (HI - LO) / T2
    check("the fixture reproduces the failure (raw rate below the gate)",
          raw_rate < EL.HANDPRESENCE_MIN, f"{raw_rate:.2f} < {EL.HANDPRESENCE_MIN}")

    first, last = SL.tracked_span(SL.to_75(dead))
    check("tracked_span finds the exact edges", (first, last) == (LO, HI - 1),
          f"got ({first},{last}), want ({LO},{HI - 1})")

    a_no, s_no = SL.clip_to_tensor(dead, trim=False)
    check("WITHOUT trim the clip is rejected — the 2026-08-27 behaviour",
          a_no is None and "no usable handshape" in s_no["reason"], s_no["reason"])

    a_yes, s_yes = SL.clip_to_tensor(dead, trim=True)
    check("WITH trim the same clip is kept",
          a_yes is not None and a_yes.shape == (EL.MAX_LEN, EL.N_POINTS, 3),
          f"span={s_yes['span']} rate={s_yes['hand_rate']:.2f} lead={s_yes['lead']} "
          f"trail={s_yes['trail']}")
    check("trim reports the dead air it cut",
          s_yes["lead"] == LO and s_yes["trail"] == T2 - HI and s_yes["span"] == HI - LO)
    check("post-trim hand-rate is 1.00 on a clean fixture", abs(s_yes["hand_rate"] - 1.0) < 1e-9,
          f"{s_yes['hand_rate']:.4f}")
    check("raw_hand_rate is still reported, so the rescue is auditable",
          abs(s_yes["raw_hand_rate"] - raw_rate) < 1e-6, f"{s_yes['raw_hand_rate']:.4f}")

    # The raw<0.10 bucket: a single spurious hand frame. Trimming it yields a 1-frame span
    # whose hand-rate is a perfect 1.00 — it MUST be rejected on length, before the rate gate.
    spur = dead.copy()
    spur[:, SL.SEMLEX_L_HAND, :] = np.nan
    spur[:, SL.SEMLEX_R_HAND, :] = np.nan
    spur[30, SL.SEMLEX_R_HAND, :] = 0.5
    a_sp, s_sp = SL.clip_to_tensor(spur, trim=True)
    check("a 1-frame spurious detection is rejected on LENGTH, not waved through at rate 1.00",
          a_sp is None and "tracked span only" in s_sp["reason"], s_sp["reason"])
    a_z, s_z = SL.clip_to_tensor(np.where(np.isnan(dead), dead, dead) * 0 + np.nan, trim=True) \
        if False else SL.clip_to_tensor(
            np.full((T2, SL.SEMLEX_N, 3), np.nan, np.float32), trim=True)
    check("a clip with no hand in any frame is rejected", a_z is None, s_z["reason"])

    # Interior gaps must SURVIVE: splicing non-adjacent moments together would fabricate motion.
    gap = dead.copy()
    gap[28:32, SL.SEMLEX_L_HAND, :] = np.nan
    gap[28:32, SL.SEMLEX_R_HAND, :] = np.nan
    a_g, s_g = SL.clip_to_tensor(gap, trim=True)
    check("interior gaps are KEPT, not spliced out",
          a_g is not None and s_g["span"] == HI - LO and s_g["hand_frames"] == (HI - LO) - 4,
          f"span={s_g['span']} tracked={s_g['hand_frames']} of {HI - LO}")

    print("\n[7] SENTINEL GUARD")
    try:
        SL.assert_sentinel(np.zeros((4, SL.SEMLEX_N, 3), np.float32))
        check("assert_sentinel rejects a zero-sentinel release", False, "it did not raise")
    except AssertionError:
        check("assert_sentinel rejects a zero-sentinel release", True)
    try:
        SL.assert_sentinel(clip)
        check("assert_sentinel accepts the real NaN-sentinel layout", True)
    except AssertionError as e:
        check("assert_sentinel accepts the real NaN-sentinel layout", False, str(e))

    if args.poses:
        print("\n[8] RE-VERIFY ON REAL DATA")
        src = SL.PoseSource(Path(args.poses))
        ids = sorted(src.ids())[:8]
        got = list(src.iter(set(ids)))
        check("real pose files load", len(got) > 0, f"{len(got)} clips")
        if got:
            shapes = {c.shape[1:] for _v, c in got}
            check("every real clip is (T,553,3)", shapes == {(SL.SEMLEX_N, 3)}, str(shapes))
            A = np.concatenate([c.astype(np.float32) for _v, c in got], 0)
            SL.assert_sentinel(A)
            P = SL.to_75(A)
            d = np.nanmean(np.abs(P[:, EL.L_SHOULDER] - P[:, EL.R_SHOULDER]), 0)
            check("shoulders are horizontal after mapping", d[0] > 4 * d[1],
                  f"|dx| {d[0]:.4f} vs |dy| {d[1]:.4f}")
            hip_y = np.nanmean(P[:, 23, 1]); sh_y = np.nanmean(P[:, EL.L_SHOULDER, 1])
            check("hips below shoulders after mapping", hip_y > sh_y,
                  f"shoulder y {sh_y:.3f} -> hip y {hip_y:.3f}")
            for nm, blk, own, other in (("L", SL.OUR_L_HAND, 15, 16), ("R", SL.OUR_R_HAND, 16, 15)):
                ctr = np.nanmean(P[:, blk, :2], 1)
                d_own = np.nanmean(np.linalg.norm(ctr - P[:, own, :2], axis=1))
                d_oth = np.nanmean(np.linalg.norm(ctr - P[:, other, :2], axis=1))
                check(f"{nm} hand sits at its OWN pose wrist", d_own < d_oth,
                      f"own {d_own:.4f} vs other {d_oth:.4f}")
            for nm, blk in (("L", SL.OUR_L_HAND), ("R", SL.OUR_R_HAND)):
                print(f"         {nm} block tracked in "
                      f"{1 - np.isnan(P[:, blk, 0]).all(axis=1).mean():.1%} of frames")

    print("\n" + "=" * 74)
    if _fails:
        print(f"FAILED {len(_fails)}: " + "; ".join(_fails))
        sys.exit(1)
    print("ALL CHECKS PASSED — the 553 -> 75 index map is proved, not assumed.")


if __name__ == "__main__":
    main()
