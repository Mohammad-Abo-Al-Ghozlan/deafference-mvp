#!/usr/bin/env python3
r"""
Stage 3b (medical MVP): Sem-Lex POSE .npy -> 75-landmark tensors, live_demo parity.

WHY THIS EXISTS SEPARATELY FROM extract_landmarks.py
----------------------------------------------------
`extract_landmarks.py` runs MediaPipe over *video*. Sem-Lex also ships a poses-only
release (`sem-lex-{train,val,test}-poses.tar.gz`, 13.3 GB total vs 53.6 GB of video),
which is 4x smaller and skips hours of MediaPipe. Same destination, different source.

THE TRAP THIS FILE EXISTS TO CLOSE — Sem-Lex is 553 landmarks, not 543
---------------------------------------------------------------------
Every other landmark array in this project is 543 = face 468 + pose 33 + hands 21+21.
Sem-Lex ran MediaPipe Face Mesh with `refine_landmarks=True`, which appends **10 iris
points** to the face block:

    553 = (468 face + 10 iris) + 33 pose + 21 left hand + 21 right hand

So every index after the face block is shifted by +10. Slicing a Sem-Lex array with
543-style offsets reads *iris and cheek points as the pose*, and pose points as hands.
The shapes still line up, training still runs, and accuracy is merely bad -- the exact
silent-degradation failure `extract_landmarks.py`'s header warns about. Note that
`test_parity.py` does NOT catch this: it compares *functions*, and those functions are
correct. It is the *input indices* that were wrong.

VERIFIED, NOT ASSUMED (2026-08-27, 12 clips / 1,056 frames from the real release)
--------------------------------------------------------------------------------
The offsets below were proved geometrically, the same way
`verify_fingerspelling_parity.py` proved the competition layout, rather than trusted:

    face=468 (543-style)   arithmetic fails (543 != 553)
    face=478 (iris, +10)   4/4
        shoulders |dx| 0.3993 vs |dy| 0.0231        -> POSE+11/12 really are shoulders
        shoulder y 0.635 -> hip y 1.396             -> y grows downward, POSE+23 is a hip
        L-hand -> own wrist 0.1519 vs other 0.3115  -> L block is the LEFT hand
        R-hand -> own wrist 0.1424 vs other 0.5940  -> R block is the RIGHT hand

    sentinel: NaN fraction 0.0594, exact-zero fraction 0.0000

The NaN sentinel already matches our convention (`sign_landmarks` contract §2), so
`canonicalize_missing` is a no-op here -- unlike GISLR, which uses a zero sentinel.
`assert_sentinel()` below re-checks it per run so a future re-release cannot change it
underneath us.

Source dtype is **float16**. Cast to float32 BEFORE normalizing: `normalize` divides by
shoulder width, and float16 has ~3 decimal digits, so the division loses real precision.

RUN
  # from the tar produced by the Kaggle download notebook
  python training/medical/semlex_poses_to_75.py \
      --poses semlex_clinical_poses.tar --manifest clinical_manifest.csv \
      --out semlex_medical_landmarks.npz --report

  # or from an already-extracted directory of <video_id>.npy
  python training/medical/semlex_poses_to_75.py --poses ./clinical --manifest clinical_manifest.csv \
      --out semlex_medical_landmarks.npz

OUTPUT (.npz) -- byte-compatible with extract_landmarks.py so downstream code is shared
  X       (N, 64, 75, 3) float32   normalized, resampled clips
  y       (N,) int32               label index
  words   (C,) str                 label names, y indexes into this
  signer  (N,) str                 signer id -- REQUIRED for signer-disjoint folds
  clip    (N,) str                 source video_id, for tracing a bad sample back
  split   (N,) str                 Sem-Lex's own split. See the warning below.

⚠️  SEM-LEX'S `val` IS NOT HELD-OUT. Measured on the clinical subset: train∩test = 0
    signers and val∩test = 0, but **train∩val = 31 of 32 signers**, and 995 video_ids
    appear in BOTH the train and val archives. Score generalization on `split == "test"`
    only (9 signers). Using `val` reads optimistically for the same reason the 250-word
    fold ensemble did.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# Imported, never re-implemented. Copying these would recreate exactly the drift this
# whole file exists to prevent; test_semlex_adapter.py asserts they are the same objects.
from extract_landmarks import (                                          # noqa: E402
    HANDPRESENCE_MIN, MAX_LEN, MIN_VALID_FRAMES, N_POINTS, POSE_N, HAND_N,
    normalize, time_resize,
)

# ── the Sem-Lex 553 layout, verified above ────────────────────────────────────
SEMLEX_N       = 553
SEMLEX_FACE_N  = 478                      # 468 face mesh + 10 iris (refine_landmarks=True)
SEMLEX_POSE    = slice(478, 511)          # 33 pose
SEMLEX_L_HAND  = slice(511, 532)          # 21 left hand
SEMLEX_R_HAND  = slice(532, 553)          # 21 right hand
assert SEMLEX_FACE_N + POSE_N + 2 * HAND_N == SEMLEX_N

# our destination blocks (sign_landmarks contract §2)
OUR_POSE   = slice(0, POSE_N)
OUR_L_HAND = slice(POSE_N, POSE_N + HAND_N)
OUR_R_HAND = slice(POSE_N + HAND_N, N_POINTS)


def assert_sentinel(a: np.ndarray) -> None:
    """Sem-Lex marks 'not observed' with NaN. If a re-release switches to a zero sentinel,
    every untracked hand silently becomes a real coordinate at the shoulder midpoint --
    fail loudly instead."""
    zero_frac = float((a == 0).mean())
    assert zero_frac < 0.005, (
        f"{zero_frac:.4f} of values are exactly 0.0 -- this release may use a ZERO "
        f"sentinel, not NaN. Run canonicalize_missing() first; do NOT proceed."
    )


def to_75(clip: np.ndarray) -> np.ndarray:
    """(T,553,3) Sem-Lex -> (T,75,3) ours. Pure re-indexing: nothing is invented or dropped
    except the face block, which our 75-point convention does not carry."""
    assert clip.ndim == 3 and clip.shape[1] == SEMLEX_N and clip.shape[2] == 3, \
        f"expected (T,{SEMLEX_N},3), got {clip.shape}"
    out = np.full((clip.shape[0], N_POINTS, 3), np.nan, dtype=np.float32)
    src = clip.astype(np.float32)                     # float16 -> float32 BEFORE any maths
    out[:, OUR_POSE]   = src[:, SEMLEX_POSE]
    out[:, OUR_L_HAND] = src[:, SEMLEX_L_HAND]
    out[:, OUR_R_HAND] = src[:, SEMLEX_R_HAND]
    return out


def hand_seen(frame_block: np.ndarray) -> bool:
    """A hand is 'seen' when its block is not entirely NaN. This is the array-side
    equivalent of extract_landmarks' `if res.left_hand_landmarks or res.right_hand_landmarks`:
    MediaPipe emits no landmark object at all for an undetected hand, which the poses
    release records as an all-NaN block."""
    return not bool(np.isnan(frame_block).all())


def clip_to_tensor(clip553: np.ndarray, *, min_hand_rate=HANDPRESENCE_MIN,
                   min_frames=MIN_VALID_FRAMES) -> tuple:
    """One Sem-Lex clip -> ((64,75,3), stats) or (None, stats) if unusable.
    Gates and their order are copied from extract_landmarks.clip_to_tensor."""
    st = {"frames": int(clip553.shape[0]), "valid": 0, "hand_frames": 0,
          "l_frames": 0, "r_frames": 0, "hand_rate": 0.0, "reason": ""}
    pts = to_75(clip553)

    seq = []
    for f in pts:
        l_ok = hand_seen(f[OUR_L_HAND])
        r_ok = hand_seen(f[OUR_R_HAND])
        st["l_frames"] += l_ok
        st["r_frames"] += r_ok
        st["hand_frames"] += (l_ok or r_ok)
        nrm = normalize(f)                            # None when shoulders aren't both visible
        if nrm is not None:
            seq.append(nrm)
            st["valid"] += 1

    if st["valid"] < min_frames:
        st["reason"] = f"only {st['valid']} normalizable frames (<{min_frames})"
        return None, st
    st["hand_rate"] = st["hand_frames"] / st["frames"] if st["frames"] else 0.0
    if st["hand_rate"] < min_hand_rate:
        st["reason"] = (f"hand in only {st['hand_rate']:.0%} of frames "
                        f"(<{min_hand_rate:.0%}) — no usable handshape")
        return None, st
    return time_resize(np.stack(seq), MAX_LEN), st


# ── sources: a tar or a directory, same interface ─────────────────────────────
class PoseSource:
    """Yields (video_id, (T,553,3)) from either a .tar of <id>.npy or a directory of them.
    Streams the tar rather than extracting it: 8k files is ~1.4 GB and there is no reason
    to write them twice."""

    def __init__(self, path: Path):
        self.path = path
        self.is_tar = path.is_file() and path.suffix in (".tar", ".gz", ".tgz")
        if not self.is_tar and not path.is_dir():
            raise SystemExit(f"[err] --poses is neither a tar nor a directory: {path}")

    def ids(self) -> set:
        if self.is_tar:
            mode = "r:gz" if self.path.suffix in (".gz", ".tgz") else "r"
            with tarfile.open(self.path, mode) as t:
                return {Path(m.name).stem for m in t.getmembers() if m.name.endswith(".npy")}
        return {p.stem for p in self.path.rglob("*.npy")}

    def iter(self, wanted: set):
        if self.is_tar:
            mode = "r:gz" if self.path.suffix in (".gz", ".tgz") else "r"
            with tarfile.open(self.path, mode) as t:
                for m in t:
                    if not m.isfile() or not m.name.endswith(".npy"):
                        continue
                    vid = Path(m.name).stem
                    if vid in wanted:
                        yield vid, np.load(io.BytesIO(t.extractfile(m).read()))
        else:
            for p in sorted(self.path.rglob("*.npy")):
                if p.stem in wanted:
                    yield p.stem, np.load(p)


def read_manifest(path: Path, allowed: set | None):
    """CSV with columns video_id,label[,signer_id][,split]. Returns {video_id: (label, signer, split)}."""
    out = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in (rd.fieldnames or [])}
        c_v = cols.get("video_id") or cols.get("video")
        c_l = cols.get("label")
        if not c_v or not c_l:
            raise SystemExit(f"[err] manifest needs video_id and label columns; got {rd.fieldnames}")
        c_s, c_sp = cols.get("signer_id") or cols.get("signer"), cols.get("split")
        for r in rd:
            lab = (r[c_l] or "").strip().lower()
            if not lab or (allowed is not None and lab not in allowed):
                continue
            out[(r[c_v] or "").strip()] = (lab,
                                           str(r[c_s]).strip() if c_s else "",
                                           str(r[c_sp]).strip() if c_sp else "")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sem-Lex pose .npy (553 landmarks) -> (64,75,3) tensors, live_demo parity")
    ap.add_argument("--poses", required=True, help="semlex_clinical_poses.tar OR a dir of <id>.npy")
    ap.add_argument("--manifest", required=True, help="CSV video_id,label[,signer_id][,split]")
    ap.add_argument("--vocab", help="JSON {'words':[...]} — keep only these labels")
    ap.add_argument("--out", default="semlex_medical_landmarks.npz")
    ap.add_argument("--limit", type=int, help="process at most N clips (smoke test)")
    ap.add_argument("--min-hand-rate", type=float, default=HANDPRESENCE_MIN)
    ap.add_argument("--min-frames", type=int, default=MIN_VALID_FRAMES)
    ap.add_argument("--report", action="store_true",
                    help="per-signer hand-block presence — the diagnostic that predicted "
                         "the 250-word model's 0.314 signer. Read it BEFORE training.")
    args = ap.parse_args()

    allowed = None
    if args.vocab:
        raw = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
        allowed = {w.lower() for w in (raw["words"] if isinstance(raw, dict) else raw)}
        print(f"[cfg] restricting to {len(allowed)} labels from {Path(args.vocab).name}")

    man = read_manifest(Path(args.manifest), allowed)
    src = PoseSource(Path(args.poses))
    have = src.ids()
    wanted = set(man) & have
    print(f"[cfg] manifest {len(man):,} | poses available {len(have):,} | to extract {len(wanted):,}")
    absent = set(man) - have
    if absent:
        # 39 of 8,103 were absent from the release itself when this was measured. Report the
        # count so a big number (a wrong --poses path) cannot look like a small data gap.
        print(f"[warn] {len(absent)} manifest ids have no pose file, e.g. {sorted(absent)[:5]}")
    if not wanted:
        sys.exit("[err] no overlap between manifest and pose files — check --poses / --manifest")

    words = sorted({man[v][0] for v in wanted})
    widx = {w: i for i, w in enumerate(words)}

    X, y, signer, clip, split = [], [], [], [], []
    per_signer, skipped = {}, []
    checked_sentinel = False
    t0 = time.perf_counter()

    for n, (vid, raw) in enumerate(src.iter(wanted), 1):
        if args.limit and len(clip) >= args.limit:
            break
        if not checked_sentinel:                 # once is enough; it is a release-wide property
            assert_sentinel(np.asarray(raw, np.float32))
            checked_sentinel = True
        lab, sg, sp = man[vid]
        arr, st = clip_to_tensor(np.asarray(raw), min_hand_rate=args.min_hand_rate,
                                 min_frames=args.min_frames)
        if arr is None:
            skipped.append((vid, lab, st["reason"]))
        else:
            X.append(arr); y.append(widx[lab]); signer.append(sg)
            clip.append(vid); split.append(sp)
            d = per_signer.setdefault(sg, {"n": 0, "l": 0.0, "r": 0.0, "frames": 0})
            d["n"] += 1; d["frames"] += st["frames"]
            d["l"] += st["l_frames"]; d["r"] += st["r_frames"]
        if args.report and n <= 20:
            print(f"  {vid} {lab:12} frames={st['frames']:3} valid={st['valid']:3} "
                  f"L={st['l_frames']:3} R={st['r_frames']:3} "
                  f"{'SKIP: ' + st['reason'] if arr is None else 'ok'}")
        if n % 500 == 0:
            el = time.perf_counter() - t0
            print(f"[{n}/{len(wanted)}] kept={len(X)} skipped={len(skipped)} {el:.0f}s")

    if not X:
        sys.exit("[err] nothing extracted — every clip failed the gates (see reasons above)")

    Xn = np.stack(X).astype(np.float32)
    np.savez_compressed(args.out, X=Xn, y=np.array(y, np.int32), words=np.array(words),
                        signer=np.array(signer, dtype=object).astype(str),
                        clip=np.array(clip, dtype=object).astype(str),
                        split=np.array(split, dtype=object).astype(str))
    print(f"\n[ok] wrote {args.out}: X={Xn.shape} classes={len(words)} "
          f"signers={len(set(signer)) } skipped={len(skipped)}")

    cnt = np.bincount(np.array(y, np.int32), minlength=len(words))
    print(f"[stats] videos/class: min={cnt.min()} median={int(np.median(cnt))} max={cnt.max()} "
          f"imbalance={cnt.max() / max(cnt.min(), 1):.0f}x")
    weak = [(words[i], int(c)) for i, c in enumerate(cnt) if c < 8]
    if weak:
        print(f"[warn] {len(weak)} classes under 8 clips AFTER extraction: {weak[:20]}")
    sp = np.array(split)
    print("[stats] split: " + "  ".join(f"{s}={int((sp == s).sum())}" for s in sorted(set(split))))
    print("[stats] ⚠️  score on split=='test' only — Sem-Lex's val shares 31/32 signers with train")

    if args.report:
        # The 250-word post-mortem: per-signer accuracy tracked HAND-BLOCK LAYOUT, which is a
        # recording artifact, and the worst signer (0.314) was the one with BOTH blocks
        # populated. Printing it here means a bad signer is visible before the GPU bill, not
        # after. A signer near 1.00/0.00 or 0.00/1.00 is cleanly one-handed-dominant; one near
        # 0.50/1.00 is the dangerous pattern.
        print("\nPER-SIGNER HAND-BLOCK PRESENCE (fraction of frames the block is tracked)")
        print(f"{'signer':>8} {'clips':>6} {'L':>7} {'R':>7}  pattern")
        rows = sorted(per_signer.items(), key=lambda kv: -kv[1]["n"])
        for sg, d in rows:
            l, r = d["l"] / max(d["frames"], 1), d["r"] / max(d["frames"], 1)
            pat = ("pure R" if l < 0.10 <= r else "pure L" if r < 0.10 <= l
                   else "BOTH blocks <- watch this one" if min(l, r) > 0.30 else "mixed")
            print(f"{sg:>8} {d['n']:>6} {l:>7.3f} {r:>7.3f}  {pat}")

    if skipped:
        print(f"\n[warn] skipped {len(skipped)} clips; first few:")
        for vid, lab, why in skipped[:10]:
            print(f"        {vid} ({lab}): {why}")


if __name__ == "__main__":
    main()
