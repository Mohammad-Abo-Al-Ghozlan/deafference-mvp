#!/usr/bin/env python3
"""Re-extract the 250-word corpus from RAW GISLR with a CANONICAL DOMINANT HAND.

WHY THIS EXISTS
---------------
Measured 2026-08-11 against the raw competition data (300 random sequences of
known two-handed signs, 21 participants):

    left_hand rows present in 300/300 parquets      <- not a parsing problem
    BOTH hands live          1.7% of clips
    frames with both hands   mean 0.1%, max 4.8%
    ONLY_L 41.0%   ONLY_R 56.7%                    <- matches our corpus exactly
    14/21 participants: EVERY clip the same class

GISLR carries ONE hand per sequence, per participant, even for signs that
phonemically require two (`book`, `car`, `open`, `bath`, `all`).  The second hand
is not poorly tracked, it was never recorded.  Two consequences:

1. No extraction fix and no retrain can recover the passive hand.  The animation
   side must SYNTHESIZE it (Battison: mirror the dominant hand for symmetric
   signs, unmarked handshape at a base location for asymmetric ones), which needs
   a per-word handedness + symmetry lexicon, not a landmark heuristic.
2. Reserving 21 of 75 point slots for a hand that is always absent is waste, and
   forcing the model to learn invariance to WHICH block holds the hand is a
   nuisance factor we can simply delete.  That is what this script does.

CANONICAL LAYOUT (still 75 points — architecture unchanged on purpose)
    0-32   pose, mirrored to right-dominant if the signer was left-dominant
    33-53  RESERVED, all NaN.  Phase 1 drops lips/brows/eyes in here for free.
    54-74  the DOMINANT hand, always.  Never the passive one.

Also fixes a second defect found the same day.  The old corpus was gap-filled
(clean_dataset_s3.py:99 ffill+bfill per landmark), which inflates hand presence
from what the tracker actually saw to a solid block of frames:

    book 1688271138   raw 57% -> stored 100%
    bath 1124807407   raw  9% -> stored  32%

so a hand seen for 9% of frames is FROZEN at its last position for the rest.  The
model trains on invented coordinates and the animation export ships a hand that
stops dead mid-sign.  --gap-fill none keeps true NaN; train.py already masks it
(fit_to_maxlen pads with NaN and the model does NaN->0), and HAND_DROP augmentation
exists precisely to train for whole-hand absence.

Both variants are written in ONE pass because reading 94k parquets dominates the
cost — that keeps the A/B honest without paying the read twice.

USAGE
    python extract_canonical.py --raw /kaggle/input/competitions/asl-signs \
        --manifest <old data dir>/split_manifest.parquet \
        --out /kaggle/working/canon --variants none,ffill
    python extract_canonical.py --verify --old <old data dir> --new /kaggle/working/canon/none

The manifest is REUSED verbatim, never regenerated: identical rows, identical
cv/test split, identical is_outlier flags.  Anything else would confound the A/B.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))
try:
    from sign_landmarks import wrist_travel
except ImportError as e:                    # hard requirement, not optional
    raise SystemExit(
        f"[err] cannot import sign_landmarks ({e}).\n"
        f"      Geometric dominance needs it. Stage sign_landmarks.py beside this file — "
        f"without it the only rule available is frame count, which is the R5 bug."
    ) from e

N_POINTS = 75
N_CH = 3
POSE_N, HAND_N = 33, 21
SLOT_BASE = {"pose": 0, "left_hand": 33, "right_hand": 54}
DOM_BLOCK = slice(54, 75)
RESERVED_BLOCK = slice(33, 54)
HAND_L, HAND_R = slice(33, 54), slice(54, 75)
POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
POSE_L_WRIST, POSE_R_WRIST = 15, 16

# pose half of train.py's FLIP_MAP — anatomical left/right pairs. Self-inverse.
POSE_FLIP = np.array([
    0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
    22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31,
], dtype=np.int32)
assert POSE_FLIP.shape[0] == POSE_N and sorted(POSE_FLIP.tolist()) == list(range(POSE_N))

_COLS = ["frame", "type", "landmark_index", "x", "y", "z"]


def pivot_raw(path: Path) -> np.ndarray | None:
    """Raw GISLR parquet -> (T, 75, 3) in MediaPipe's own coordinates, NaN for missing."""
    df = pd.read_parquet(path, columns=_COLS)
    df = df[df["type"].isin(SLOT_BASE)]
    if df.empty:
        return None
    frames = np.sort(df["frame"].unique())
    fmap = {int(f): i for i, f in enumerate(frames)}
    out = np.full((len(frames), N_POINTS, N_CH), np.nan, np.float32)

    base = df["type"].map(SLOT_BASE).to_numpy(np.int32)
    li = df["landmark_index"].to_numpy(np.int32)
    # guard against a stray landmark_index beyond the block width
    width = np.where(base == 0, POSE_N, HAND_N)
    ok = (li >= 0) & (li < width)
    slot = (base + li)[ok]
    fi = df["frame"].map(fmap).to_numpy(np.int32)[ok]
    for c, name in enumerate(("x", "y", "z")):
        out[fi, slot, c] = df[name].to_numpy(np.float32)[ok]
    return out


def normalize_xy(a: np.ndarray) -> np.ndarray:
    """Per-frame shoulder-center + shoulder-width scale on x,y. z untouched, NaN kept.

    Byte-for-byte the same convention as build_sign_clips.normalize_clip, which is
    the contract the existing corpus and the trained model were built on.
    """
    out = a.copy()
    ls, rs = out[:, POSE_L_SHOULDER, :2], out[:, POSE_R_SHOULDER, :2]
    good = np.isfinite(ls).all(-1) & np.isfinite(rs).all(-1)
    mid = (ls + rs) / 2.0
    w = np.linalg.norm(ls - rs, axis=-1)
    good &= w > 1e-6
    if not good.any():
        return out
    g = np.where(good)[0]
    out[g, :, :2] = (out[g, :, :2] - mid[g, None, :]) / w[g, None, None]
    return out


def gap_fill(a: np.ndarray) -> np.ndarray:
    """Reproduce the OLD ffill+bfill per landmark across frames, for the A/B arm."""
    out = a.copy()
    T = out.shape[0]
    for p in range(N_POINTS):
        for c in range(N_CH):
            v = out[:, p, c]
            m = np.isfinite(v)
            if not m.any() or m.all():
                continue
            idx = np.where(m, np.arange(T), 0)
            np.maximum.accumulate(idx, out=idx)
            v = v[idx]                                   # forward fill
            first = int(np.argmax(m))
            v[:first] = v[first]                         # back fill the head
            out[:, p, c] = v
    return out


def limb_assignment(a: np.ndarray) -> dict:
    """Which pose limb does each POPULATED hand block belong to, and which arm is moving?

    `sign_landmarks.hand_arm_alignment` answers this for ONE block — whichever has the most
    tracked frames — which is correct when all you need is a verdict.  Canonicalization needs
    it for BOTH, because the clip that matters most here is the one where both blocks carry
    data: participant 29302 has a right block in 99% of its clips *and* a left block in 48%,
    and scored **0.314** against 0.78-0.82 for single-block right-recorded signers.  Choosing
    by frame count there picks whichever hand the tracker happened to hold longest, and the
    tracker holds the STILL hand longest (R5) — so frame count systematically picks the
    resting hand.  That is the bug this function exists to not repeat.

    Hand landmark 0 IS a wrist, so co-location with a pose wrist identifies the limb
    regardless of which block the coordinates were filed under.  Measured separation over the
    250 exemplars: 0.088 shoulder-widths to its own limb vs 1.783 to the other — not marginal.

    Expects `a` already through normalize_xy, so distances are in shoulder-width units.
    """
    frames = {n: int(np.isfinite(a[:, blk, :2]).all(-1).any(-1).sum())
              for n, blk in (("L", HAND_L), ("R", HAND_R))}
    out = {"frames": frames, "populated": [n for n in ("L", "R") if frames[n] > 0],
           "limb": {}, "d": {}, "moving": None}

    for n, blk in (("L", HAND_L), ("R", HAND_R)):
        if frames[n] == 0:
            continue
        hw = a[:, blk.start, :2]                    # point 0 of a hand block IS a wrist
        d = {}
        for m, wr in (("L", POSE_L_WRIST), ("R", POSE_R_WRIST)):
            dd = np.linalg.norm(hw - a[:, wr, :2], axis=-1)
            dd = dd[np.isfinite(dd)]
            d[m] = float(np.median(dd)) if dd.size else float("inf")
        out["d"][n] = d
        out["limb"][n] = None if not np.isfinite(list(d.values())).any() else (
            "L" if d["L"] < d["R"] else "R")

    # wrist_travel returns 0.0 — not NaN — when a wrist is untracked, so "is it finite" is
    # always True and cannot be used to detect missing pose. Zero travel on BOTH wrists means
    # there is no measured motion to orient by (untracked wrists, or a genuinely static clip);
    # either way, calling the tie for "R" would be inventing a signing arm out of nothing.
    tr = wrist_travel(a)
    if tr["L"] > 0 or tr["R"] > 0:
        out["moving"] = "L" if tr["L"] > tr["R"] else "R"
    out["travel"] = {k: round(float(v), 4) for k, v in tr.items()}
    return out


def pick_signing_block(la: dict, unaligned: str = "moving") -> tuple[str, str, str]:
    """-> (block to keep, limb to orient as 'right', why).

    Three cases, and the third is a real judgment call rather than a lookup:

      aligned      exactly one populated block sits on the moving arm.  Keep it, orient by it.
                   ~55% of takes.
      both_aligned both blocks claim the moving limb — geometrically impossible, so one is
                   misassigned.  Trust the closer one.
      unaligned    NO populated block is on the moving arm: the only hand we have is the
                   resting one.  ~45% of takes.  Two goals now conflict — you can align the
                   hand BLOCK or the signing ARM, not both.

    For the unaligned case the default is `moving`: orient by the arm that is signing, and
    file whatever hand we have into the dominant slot anyway.  Rationale is measured, not
    assumed — the 2026-08-13 A/B NaN-ed exactly these hands (`--mask-resting-hand train`) and
    lost 0.0312 test / 0.0415 val, with train accuracy falling 0.767 -> 0.498.  So the resting
    hand carries real signal and must be kept; and since the informative channel is the
    signing arm's trajectory, that is what gets the consistent orientation.

    `hand` is the untested alternative (orient by the tracked hand's own limb).  It is a flag
    and not a comment because nobody has measured which is better.
    """
    pop, limb, moving = la["populated"], la["limb"], la["moving"]
    if not pop:
        return "R", "R", "no_hand"                      # pose-only clip; nothing to move

    # No motion measured, or no pose wrist to compare a hand against: there is no signing arm
    # to orient by. Keep the best-tracked hand, and mirror only if we at least know its limb —
    # a coin-flip mirror would add variance for nothing.
    if moving is None or not any(limb.get(n) for n in pop):
        blk = max(pop, key=lambda n: la["frames"][n])
        return blk, (limb.get(blk) or "R"), "no_motion_info"

    on_moving = [n for n in pop if limb.get(n) == moving]
    if len(on_moving) == 1:
        return on_moving[0], moving, "aligned"
    if len(on_moving) > 1:
        blk = min(on_moving, key=lambda n: la["d"][n][moving])
        return blk, moving, "both_aligned_tie_by_distance"

    blk = max(pop, key=lambda n: la["frames"][n])       # resting hand only
    if unaligned == "hand":
        return blk, (limb.get(blk) or blk), "unaligned_orient_by_hand"
    return blk, moving, "unaligned_orient_by_moving"


def canonicalize(a: np.ndarray, dominance: str = "geometric",
                 unaligned: str = "moving") -> tuple[np.ndarray, dict]:
    """Normalize, mirror so the signing arm reads as right, and park its hand at 54-74.

    `dominance="frames"` reproduces the pre-2026-08-13 rule (most tracked frames wins) so the
    two can be A/B'd on the same corpus.  It is kept ONLY for that comparison: it is the rule
    that put the resting hand in the dominant slot, and it must not be the default again.
    """
    a = normalize_xy(a)
    la = limb_assignment(a)

    if dominance == "frames":
        lf, rf = la["frames"]["L"], la["frames"]["R"]
        block = orient = "L" if lf > rf else "R"
        why = "frame_count_legacy"
    else:
        block, orient, why = pick_signing_block(la, unaligned)

    if orient == "L":
        # mirror the geometry; POSE_FLIP swaps the anatomical L/R pose indices.  Hand blocks
        # are NOT reindexed — hand topology is identical for both hands, the x negation is
        # what turns a left hand into a right-shaped one.
        a[..., 0] *= -1.0
        a[:, :POSE_N, :] = a[:, POSE_FLIP, :]

    # Extract AFTER mirroring: mirroring changes coordinates, never which block holds them,
    # so `block` still names the right source. Doing it in the other order silently keeps the
    # unmirrored hand.
    hand = a[:, HAND_L if block == "L" else HAND_R, :].copy()
    a[:, RESERVED_BLOCK, :] = np.nan
    a[:, DOM_BLOCK, :] = hand

    # Flat scalars only: `limb`/`d` are keyed by which blocks were populated, so they vary
    # per row, and pyarrow infers one struct type for the whole column — a nested dict here
    # writes nulls or raises rather than round-tripping.
    d = la["d"]
    return a, {
        "dominant": orient, "mirrored": orient == "L", "signing_block": block,
        "pick_reason": why, "aligned": why == "aligned",
        "both_blocks": len(la["populated"]) == 2,
        "moving": la["moving"],
        "limb_L": la["limb"].get("L"), "limb_R": la["limb"].get("R"),
        "travel_L": la["travel"]["L"], "travel_R": la["travel"]["R"],
        "d_Lblk_L": d.get("L", {}).get("L"), "d_Lblk_R": d.get("L", {}).get("R"),
        "d_Rblk_L": d.get("R", {}).get("L"), "d_Rblk_R": d.get("R", {}).get("R"),
        "frames_L": la["frames"]["L"], "frames_R": la["frames"]["R"],
        "hand_frames": la["frames"].get(block, 0), "frames": int(a.shape[0]),
    }


def run_extract(args: argparse.Namespace) -> None:
    raw = Path(args.raw)
    man = pd.read_parquet(args.manifest)
    tr = pd.read_csv(raw / "train.csv")
    by_sid = {int(s): p for s, p in zip(tr["sequence_id"], tr["path"])}

    if "key" not in man.columns:
        man = man.copy()
        man["key"] = (man["word"] + "/" + man["participant_id"].astype(str)
                      + "_" + man["sequence_id"].astype(str))
    words = sorted(man["word"].unique())
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    print(f"[cfg] {len(man)} sequences | {len(words)} words | variants {variants}")
    for v in variants:
        (Path(args.out) / v / "by_word").mkdir(parents=True, exist_ok=True)

    meta_rows, t0, done, failed = [], time.time(), 0, []

    def one(row):
        sid = int(row.sequence_id)
        p = by_sid.get(sid)
        if p is None:
            return row.key, None, None
        try:
            a = pivot_raw(raw / p)
        except Exception as exc:                                  # noqa: BLE001
            return row.key, None, repr(exc)
        if a is None or a.shape[0] < 2:
            return row.key, None, "empty"
        canon, info = canonicalize(a, args.dominance, args.unaligned)
        return row.key, (canon, info), None

    for w in words:
        sub = man[man["word"] == w]
        store = {v: {} for v in variants}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for key, res, err in pool.map(one, sub.itertuples(index=False)):
                if res is None:
                    failed.append((key, err)); continue
                canon, info = res
                short = key.split("/", 1)[1]
                for v in variants:
                    store[v][short] = (canon if v == "none" else gap_fill(canon))
                info["key"] = key
                meta_rows.append(info)
        for v in variants:
            d = Path(args.out) / v / "by_word" / w
            d.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(d / "sequences.npz", **store[v])
        done += len(sub)
        if done % 5000 < len(sub):
            el = time.time() - t0
            print(f"  {done}/{len(man)}  {el/60:.1f} min  "
                  f"eta {el/max(1,done)*(len(man)-done)/60:.0f} min", flush=True)

    # the manifest is copied VERBATIM so the cv/test split and is_outlier are identical
    for v in variants:
        man.to_parquet(Path(args.out) / v / "split_manifest.parquet", index=False)
    md = pd.DataFrame(meta_rows)
    md.to_parquet(Path(args.out) / "extract_meta.parquet", index=False)

    print(f"\n[ok] {done - len(failed)} clips in {(time.time()-t0)/60:.1f} min")
    if failed:
        print(f"[warn] {len(failed)} failed, e.g. {failed[:3]}")
    print(f"  dominant hand: L {int((md['dominant']=='L').sum())}  "
          f"R {int((md['dominant']=='R').sum())}   (mirrored {int(md['mirrored'].sum())})")
    print(f"  hand-present frames: mean {float((md['hand_frames']/md['frames']).mean())*100:.1f}%")

    # The rule's own report card. `aligned` near 55% is the expected figure (measured over
    # 80,647 takes on 2026-08-12); far from it means the geometry is not doing what it did
    # then, and the run should be questioned before it is trained on.
    n = len(md)
    print(f"\n  dominance rule = {args.dominance}   unaligned policy = {args.unaligned}")
    print(f"  signing block:  L {int((md['signing_block']=='L').sum())}  "
          f"R {int((md['signing_block']=='R').sum())}")
    print(f"  aligned (tracked hand on the MOVING arm): {int(md['aligned'].sum())}/{n} "
          f"({float(md['aligned'].mean())*100:.1f}%)   expected ~55%")
    print(f"  both blocks populated: {int(md['both_blocks'].sum())}/{n} "
          f"({float(md['both_blocks'].mean())*100:.1f}%)")
    print("  pick_reason:")
    for r, c in md["pick_reason"].value_counts().items():
        print(f"    {r:34} {c:7d}  ({c/n*100:.1f}%)")
    if args.dominance == "geometric" and float(md["aligned"].mean()) < 0.40:
        print("\n  [warn] alignment well below the 55% measured baseline. Either the corpus "
              "is not what it was, or the pose wrists are not resolving — check before "
              "training on this.")
    for v in variants:
        print(f"  -> {Path(args.out)/v}")


def run_verify(args: argparse.Namespace) -> None:
    """Prove the new arrays match the old CONVENTION before spending a training run.

    Compares the POSE block only — the hand blocks are deliberately different (that
    is the whole point), but pose must be identical up to the mirror, or the
    coordinate convention has silently drifted and the A/B would be meaningless.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # words come from what the NEW dir actually holds — a smoke run has only a few,
    # and taking them from the old 250-word manifest would look for words never extracted
    new_root = Path(args.new) / "by_word"
    avail = sorted(p.name for p in new_root.iterdir() if (p / "sequences.npz").exists())
    words = [w for w in avail
             if (Path(args.old) / "by_word" / w / "sequences.npz").exists()][: args.words]
    assert words, f"no overlapping words between {args.old} and {args.new}"
    print(f"verifying {len(words)} of {len(avail)} extracted words against {args.old}\n")
    print(f"{'word':12} {'n':>4}  {'pose |dx| median':>17} {'pose corr':>10} "
          f"{'hand pres old':>14} {'new':>7}")
    print("-" * 74)
    tot = []
    for w in words:
        o = np.load(Path(args.old) / "by_word" / w / "sequences.npz")
        n = np.load(Path(args.new) / "by_word" / w / "sequences.npz")
        keys = [k for k in o.files if k in n.files][: args.per_word]
        d, corr, po, pn = [], [], [], []
        for k in keys:
            A, B = o[k], n[k]
            if A.shape[0] != B.shape[0]:
                continue
            ap, bp = A[:, :POSE_N, :2], B[:, :POSE_N, :2]
            # B may be mirrored; compare against whichever orientation fits
            cand = [bp, np.stack([-bp[..., 0], bp[..., 1]], -1)[:, POSE_FLIP, :]]
            errs = [np.nanmedian(np.abs(ap - c)) for c in cand]
            j = int(np.nanargmin(errs))
            d.append(errs[j])
            m = np.isfinite(ap) & np.isfinite(cand[j])
            if m.sum() > 50:
                corr.append(float(np.corrcoef(ap[m], cand[j][m])[0, 1]))
            po.append(float(np.isfinite(A[:, 33:75, 0]).any(axis=1).mean()))
            pn.append(float(np.isfinite(B[:, 54:75, 0]).any(axis=1).mean()))
        if not d:
            continue
        print(f"{w:12} {len(d):>4}  {np.nanmedian(d):17.5f} {np.nanmean(corr):10.4f} "
              f"{np.mean(po)*100:13.0f}% {np.mean(pn)*100:6.0f}%")
        tot.append((np.nanmedian(d), np.nanmean(corr)))
    dm = float(np.nanmedian([t[0] for t in tot])); cm = float(np.nanmean([t[1] for t in tot]))
    print("\n" + "=" * 74)
    print(f"pose |dx| median {dm:.5f}   pose corr {cm:.4f}")
    if cm > 0.999 and dm < 0.01:
        print("PASS — coordinate convention reproduced. The A/B is valid.")
    elif cm > 0.99:
        print("CLOSE — convention matches but not exactly. Inspect before training.")
    else:
        print("FAIL — the new arrays are NOT in the old coordinate space. Do not train.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", help="asl-signs competition dir (has train.csv)")
    ap.add_argument("--manifest", help="EXISTING split_manifest.parquet — reused verbatim")
    ap.add_argument("--out", default="/kaggle/working/canon")
    ap.add_argument("--variants", default="none,ffill",
                    help="'none' = true NaN (recommended), 'ffill' = reproduce the old gap-fill")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dominance", choices=("geometric", "frames"), default="geometric",
                    help="how to decide which hand is signing. 'geometric' = the block whose "
                         "landmark 0 co-locates with the MOVING arm's pose wrist (default). "
                         "'frames' = most tracked frames wins — the pre-2026-08-13 rule, kept "
                         "only so the two can be A/B'd; it selects the RESTING hand, because "
                         "the tracker holds the still hand longest (R5).")
    ap.add_argument("--unaligned", choices=("moving", "hand"), default="moving",
                    help="for the ~45%% of takes whose only tracked hand is the RESTING one, "
                         "which limb gets oriented as 'right': 'moving' = the signing arm "
                         "(default; keeps the informative trajectory consistent), 'hand' = the "
                         "tracked hand's own limb. Untested — this is a flag, not a finding.")
    ap.add_argument("--verify", action="store_true", help="compare against the old corpus")
    ap.add_argument("--old", help="old data dir (verify mode)")
    ap.add_argument("--new", help="new variant dir (verify mode)")
    ap.add_argument("--words", type=int, default=8)
    ap.add_argument("--per-word", type=int, default=25)
    args = ap.parse_args()
    if args.verify:
        if not (args.old and args.new):
            ap.error("--verify needs --old and --new")
        run_verify(args)
    else:
        if not (args.raw and args.manifest):
            ap.error("extraction needs --raw and --manifest")
        run_extract(args)


if __name__ == "__main__":
    main()
