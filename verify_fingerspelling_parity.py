#!/usr/bin/env python
"""Does the ASL Fingerspelling corpus really share our landmark convention? Ten minutes, CPU.

WHY RUN THIS BEFORE WRITING A CTC MODEL
---------------------------------------
The probe on 2026-08-26 showed 1,631 columns = 543 landmarks x 3 + frame + sequence_id, split
face 468 / pose 33 / left_hand 21 / right_hand 21. That is the SAME MediaPipe Holistic layout
GISLR uses, and our 75-point convention is exactly pose(33) + left_hand(21) + right_hand(21) --
so on paper `normalize()` and `canonicalize_missing()` apply unchanged and only 13.8% of the
columns are needed (~26 GB of I/O instead of ~190 GB).

"On paper" is doing a lot of work in that sentence. Four things could differ silently, and every
one of them would produce a model that trains and is wrong rather than a model that crashes:

  1. COLUMN NAMES. We have to know the exact spelling to slice, and the naming scheme is not
     guaranteed to be `x_pose_0`.
  2. LANDMARK ORDER. Our normalization hard-codes pose index 11 = left shoulder, 12 = right
     (live_demo.py:234). If this corpus orders pose differently, normalize() silently centres on
     the wrong pair and every clip is scaled by a meaningless width.
  3. MISSING-VALUE ENCODING. GISLR writes a ZERO sentinel, which is why canonicalize_missing()
     exists to rewrite zeros as NaN (sign_landmarks.py:89) -- isfinite(0.0) is True, and that
     exact confusion once made 238 of 250 clips score a perfect 1.0 on a presence metric that
     could not fail. If this corpus writes NaN directly, the rewrite is a harmless no-op; if it
     writes zeros, skipping it poisons everything downstream.
  4. COORDINATE RANGE. MediaPipe image coords are normalized to roughly [0,1] with y DOWN.
     normalize() assumes that. Pixel coordinates, or y-up, would both pass silently.

This checks all four against the real file, using OUR OWN functions rather than reimplementing
them -- the same discipline that made the canonical port work first time.

USAGE (Kaggle, CPU, no accelerator; needs sign_landmarks.py + live_demo.py staged, or run from a
repo checkout with the competition mounted)
    python verify_fingerspelling_parity.py
    python verify_fingerspelling_parity.py --base /kaggle/input/competitions/asl-fingerspelling
"""
from __future__ import annotations

import argparse
import glob

import os
import sys
from pathlib import Path

import numpy as np

POSE_N, HAND_N = 33, 21
N_POINTS = 75
L_SHOULDER, R_SHOULDER = 11, 12          # live_demo.py:234 — the assumption under test
L_HIP, R_HIP = 23, 24
L_WRIST, R_WRIST = 15, 16

OK, BAD = [], []


def check(cond: bool, label: str, detail: str = "") -> bool:
    (OK if cond else BAD).append(label)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{('   ' + detail) if detail else ''}")
    return cond


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="/kaggle/input/competitions/asl-fingerspelling")
    ap.add_argument("--n-seq", type=int, default=25, help="sequences to sample for the stats")
    args = ap.parse_args()

    import pandas as pd
    import pyarrow.parquet as pq

    BASE = Path(args.base)
    if not BASE.exists():
        sys.exit(f"[err] not found: {BASE}\n      attach the competition, or pass --base")

    # ── 1. column naming ────────────────────────────────────────────────────────
    print("\n[1] column naming")
    f0 = sorted(glob.glob(str(BASE / "train_landmarks" / "*.parquet")))[0]
    names = pq.ParquetFile(f0).schema_arrow.names
    print(f"  file: {os.path.basename(f0)}  ({len(names)} columns)")
    print(f"  first 6: {names[:6]}")

    def col(axis: str, grp: str, i: int) -> str:
        return f"{axis}_{grp}_{i}"

    want = [col(a, g, i) for g in ("pose",) for i in range(POSE_N) for a in "xyz"] + \
           [col(a, g, i) for g in ("left_hand", "right_hand") for i in range(HAND_N)
            for a in "xyz"]
    missing = [c for c in want if c not in names]
    if not check(not missing, "our 225 expected column names all exist",
                 f"{len(want)} wanted, {len(missing)} missing"):
        print(f"       missing e.g. {missing[:5]}")
        print("       -> the naming scheme differs; read `names` above and adapt `col()`")
        sys.exit(1)
    print(f"  using {len(want)}/{len(names)} columns = {len(want)/len(names)*100:.1f}%"
          f"  -> ~{190 * len(want)/len(names):.0f} GB effective, not 190 GB")

    # ── 2. build (T,75,3) in OUR order, from one sequence ───────────────────────
    print("\n[2] assembling a (T,75,3) clip in our landmark order")
    meta = pd.read_csv(BASE / "train.csv")
    rel = "train_landmarks/" + os.path.basename(f0)
    rows = meta[meta.path == rel]
    seq = rows.iloc[0]
    df = pd.read_parquet(f0, columns=["sequence_id"] + want,
                         filters=[("sequence_id", "==", int(seq.sequence_id))])
    T = len(df)
    clip = np.full((T, N_POINTS, 3), np.nan, dtype=np.float32)
    for i in range(POSE_N):
        for a, ax in enumerate("xyz"):
            clip[:, i, a] = df[col(ax, "pose", i)].to_numpy()
    for b, grp in enumerate(("left_hand", "right_hand")):
        for i in range(HAND_N):
            for a, ax in enumerate("xyz"):
                clip[:, POSE_N + b * HAND_N + i, a] = df[col(ax, grp, i)].to_numpy()
    print(f"  phrase {seq.phrase!r} ({len(seq.phrase)} chars) -> {T} frames, shape {clip.shape}")
    check(clip.shape[1:] == (75, 3), "shape is (T,75,3)")

    # ── 3. missing-value encoding ──────────────────────────────────────────────
    print("\n[3] how is a missing landmark written?")
    n_nan = int(np.isnan(clip).all(-1).sum())
    n_zero = int((np.abs(np.nan_to_num(clip, nan=9e9)) < 1e-4).all(-1).sum())
    tot = clip.shape[0] * clip.shape[1]
    print(f"  all-NaN points  {n_nan}/{tot} ({n_nan/tot*100:.1f}%)")
    print(f"  all-zero points {n_zero}/{tot} ({n_zero/tot*100:.1f}%)")
    if n_nan and not n_zero:
        print("  -> NaN sentinel. canonicalize_missing() is a documented no-op on NaN input,")
        print("     so applying it anyway is free and keeps one code path.")
    elif n_zero:
        print("  -> ZERO sentinel, same as GISLR. canonicalize_missing() is MANDATORY:")
        print("     isfinite(0.0) is True, so any presence metric silently reads 100%.")
    check(n_nan > 0 or n_zero > 0, "some landmarks are marked absent (a real tracker trace)",
          "if neither, the sentinel is something else — investigate before trusting anything")

    # ── 4. is pose 11/12 really the shoulders? geometry, not faith ─────────────
    print("\n[4] landmark ORDER — is pose 11/12 the shoulder pair?")
    xy = clip[:, :POSE_N, :2]
    good = np.isfinite(xy[:, [L_SHOULDER, R_SHOULDER, L_HIP, R_HIP]]).all((1, 2))
    if not check(bool(good.any()), "some frames have both shoulders and both hips tracked"):
        sys.exit(1)
    g = np.where(good)[0]
    sh_dx = float(np.median(np.abs(xy[g, L_SHOULDER, 0] - xy[g, R_SHOULDER, 0])))
    sh_dy = float(np.median(np.abs(xy[g, L_SHOULDER, 1] - xy[g, R_SHOULDER, 1])))
    check(sh_dx > sh_dy * 1.5, "the 11-12 pair is spread mostly HORIZONTALLY (a shoulder line)",
          f"|dx| {sh_dx:.4f} vs |dy| {sh_dy:.4f}")

    sh_y = float(np.median(xy[g][:, [L_SHOULDER, R_SHOULDER], 1]))
    hip_y = float(np.median(xy[g][:, [L_HIP, R_HIP], 1]))
    check(hip_y > sh_y, "hips are BELOW shoulders, i.e. y increases DOWNWARD as we assume",
          f"shoulder y {sh_y:.3f}, hip y {hip_y:.3f}")

    # a hand block should sit near its own pose wrist — that is what proves the
    # left_hand/right_hand blocks are not swapped relative to pose indices
    for side, wrist, blk in (("left", L_WRIST, slice(POSE_N, POSE_N + HAND_N)),
                             ("right", R_WRIST, slice(POSE_N + HAND_N, N_POINTS))):
        hw = clip[:, blk, :2]
        m = np.isfinite(hw).all(-1).any(-1) & np.isfinite(clip[:, wrist, :2]).all(-1)
        if m.sum() < 3:
            print(f"  --   {side} hand: too few tracked frames to test ({int(m.sum())})")
            continue
        own = float(np.nanmedian(np.linalg.norm(
            np.nanmean(hw[m], axis=1) - clip[m, wrist, :2], axis=-1)))
        other = L_WRIST if wrist == R_WRIST else R_WRIST
        oth = float(np.nanmedian(np.linalg.norm(
            np.nanmean(hw[m], axis=1) - clip[m, other, :2], axis=-1)))
        check(own < oth, f"{side}_hand block sits nearer pose {wrist} than pose {other}",
              f"own {own:.4f} vs other {oth:.4f}")

    # ── 5. coordinate range ────────────────────────────────────────────────────
    print("\n[5] coordinate range — normalized image coords, or pixels?")
    fin = clip[np.isfinite(clip[..., 0]), 0]
    lo, hi = float(np.percentile(fin, 1)), float(np.percentile(fin, 99))
    check(-0.5 < lo and hi < 1.5, "x sits in ~[0,1] (normalized), not pixel coordinates",
          f"p1 {lo:.3f}  p99 {hi:.3f}")

    # ── 6. run OUR functions, unchanged ───────────────────────────────────────
    print("\n[6] our own pipeline, applied unchanged")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from sign_landmarks import canonicalize_missing
    except ImportError:
        sys.exit("[err] sign_landmarks.py not importable — stage it beside this script")
    cm = canonicalize_missing(clip)
    check(cm.shape == clip.shape, "canonicalize_missing accepts the clip unchanged")
    check(np.array_equal(np.isnan(canonicalize_missing(cm)), np.isnan(cm)),
          "canonicalize_missing is idempotent here too")

    # Normalization has three interchangeable implementations in this repo, all verified to use
    # the same convention (shoulder-midpoint centre, shoulder-width scale, x/y only, z untouched,
    # NaN preserved). Try them in order of "closest to what ships" and SAY which one ran --
    # reimplementing it here would defeat the whole purpose of the check.
    #   live_demo.normalize          the shipping path, but imports cv2 at module scope
    #   extract_canonical.normalize_xy   what built the corpus; needs training/ on the path
    #   sign_landmarks._normalized_xy    numpy only, so it works wherever sign_landmarks does
    # On Kaggle only sign_landmarks.py is typically staged, which is why the third exists.
    nz, src = None, None
    try:
        from live_demo import normalize
        outs = [normalize(f) for f in cm]
        kept = [o for o in outs if o is not None]
        check(len(kept) > 0, "live_demo.normalize accepted frames",
              f"{len(kept)}/{len(outs)} — None means both shoulders were not visible")
        if kept:
            nz, src = np.stack(kept), "live_demo.normalize"
    except Exception as e:                                   # noqa: BLE001
        print(f"  --   live_demo not importable ({type(e).__name__}), trying the next one")
    if nz is None:
        try:
            from training.extract_canonical import normalize_xy
            nz, src = normalize_xy(cm), "extract_canonical.normalize_xy"
        except Exception as e:                               # noqa: BLE001
            print(f"  --   extract_canonical not importable ({type(e).__name__}), "
                  f"falling back to sign_landmarks")
    if nz is None:
        from sign_landmarks import _normalized_xy
        xy, ok = _normalized_xy(cm)
        nz = cm.copy()
        nz[:, :, :2] = xy
        nz = nz[ok] if ok.any() else nz
        src = "sign_landmarks._normalized_xy"
    if not check(nz is not None and src is not None,
                 "a normalization implementation was importable"):
        sys.exit(1)
    print(f"  using {src}")
    mid = np.nanmedian(nz[:, [L_SHOULDER, R_SHOULDER], :2].reshape(-1, 2), axis=0)
    w = float(np.nanmedian(np.linalg.norm(
        nz[:, L_SHOULDER, :2] - nz[:, R_SHOULDER, :2], axis=-1)))
    check(abs(float(mid[0])) < 0.05 and abs(float(mid[1])) < 0.05,
          f"after {src}, the shoulder midpoint sits at the origin",
          f"({mid[0]:+.4f}, {mid[1]:+.4f})")
    check(abs(w - 1.0) < 0.05, "after normalization, shoulder width is 1.0", f"{w:.4f}")

    # ── 7. corpus-level stats worth having before designing the model ──────────
    print(f"\n[7] hand-presence over {args.n_seq} sequences (drives the CTC input design)")
    ids = rows.sequence_id.astype(int).tolist()[:args.n_seq]
    hand_cols = [c for c in want if "_hand_" in c]
    d = pd.read_parquet(f0, columns=["sequence_id"] + hand_cols,
                        filters=[("sequence_id", "in", ids)])
    lh = d[[c for c in hand_cols if "left_hand" in c]].to_numpy()
    rh = d[[c for c in hand_cols if "right_hand" in c]].to_numpy()
    lp = float(np.isfinite(lh).any(1).mean())
    rp = float(np.isfinite(rh).any(1).mean())
    print(f"  frames with a LEFT hand  {lp*100:5.1f}%")
    print(f"  frames with a RIGHT hand {rp*100:5.1f}%")
    print(f"  frames with NEITHER      {float((~np.isfinite(lh).any(1) & ~np.isfinite(rh).any(1)).mean())*100:5.1f}%")
    print("  NOTE fingerspelling is ONE-handed, so expect a strong side skew. Whichever side\n"
          "       dominates, canonicalising to a single hand block (as train.py --canonical-hand\n"
          "       does) is likely the right move here too — and it halves the input width.")

    print("\n" + "=" * 74)
    print(f"{len(OK)} checks passed, {len(BAD)} failed")
    if BAD:
        print("FAILED: " + "; ".join(BAD))
        print("\nDo NOT start the CTC build until these are understood. Each one is a silent\n"
              "wrongness, not a crash.")
        sys.exit(1)
    print("Convention matches. The 75-point subset and our normalization carry over,\n"
          "so this is an integration problem, not a new preprocessing problem.")


if __name__ == "__main__":
    main()
