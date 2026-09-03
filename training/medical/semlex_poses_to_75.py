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

WHY THIS FILE TRIMS, AND WHY THAT IS NOT THE REFUTED TRIM (measured 2026-08-27)
------------------------------------------------------------------------------
The first extraction run rejected **48.5% of clips** (3,913 of 8,064) on
`HANDPRESENCE_MIN`, and 38 classes fell under 8 clips. That was the gate misfiring, not
bad data. On 800 clips / 43,094 frames:

    LEADING  untracked  30.9%
    TRAILING untracked  30.6%     -> 61.5% of all frames are lead-in / lead-out
    INTERIOR untracked   5.3%

    hand-rate AFTER trimming to the tracked span, by raw bucket:
      raw 0.20-0.35   232 clips   median 0.92   span 18 of 52 frames
      raw 0.35-0.60   348 clips   median 1.00   span 23 of 48
      raw 0.60+        55 clips   median 1.00   span 27 of 38
      raw 0.10-0.20    89 clips   median 0.75   span 11 of 50
      raw 0.00-0.10    76 clips   median 0.50   span  2 of 48   <- genuinely unusable

    of the rejected clips, 74.3% pass once trimmed; 16% are too short; 10% still fail.

Sem-Lex clips are **raw recordings** — a participant hits record, signs, hits stop — so the
hands sit out of a head-and-shoulders frame for the lead-in and lead-out. `valid == frames`
in those rows (both shoulders visible throughout), so the signer never left; only the hands
did. `HANDPRESENCE_MIN = 0.35` was calibrated on `live_demo`'s ALREADY-SEGMENTED camera
input, and the corpus median raw rate sits at ~0.33 — right on the threshold, which is why
the cut landed near 50%.

**This is not the trim that was refuted.** `SESSION_HANDOFF` §0.5 records trim-to-tracked-span
moving pooled accuracy −0.0011 with "only 1.9% of frames droppable, so dropouts are interior".
That was measured on **GISLR, which ships pre-trimmed to the sign** — there was nothing to cut.
Sem-Lex is raw video from a different collection process. Same hypothesis, different corpus,
and the corpus was the reason it failed there.

**And trimming RESTORES parity rather than breaking it.** `live_demo` segments the live stream
(sliding window + `MOTION_EPS`) before `classify_segment` ever runs, so the model at inference
time only ever sees a trimmed segment. Training on untrimmed recordings is the actual mismatch.
Trimming on hand-tracking onset/offset is a proxy for live_demo's motion-based boundaries, not
an exact match — it is slightly more generous, keeping the hand-raise transition, which the live
sliding window also catches.

`--no-trim` reproduces the original behaviour, so the decision stays auditable.

CANONICAL ORIENTATION — MIRROR ONLY, NEVER `--canonical-hand` (measured 2026-08-27)
-----------------------------------------------------------------------------------
`training/extract_canonical.py` was built on a measurement of GISLR, quoted in its own
header, and Sem-Lex disagrees with it on the single load-bearing number:

                          GISLR      Sem-Lex     (3,000 clinical clips, trimmed span,
    BOTH hands live        1.7%        41.2%       "live" = tracked >1/3 of the span)
    ONLY_L                41.0%        13.8%
    ONLY_R                56.7%        45.0%
    L share of 1-handed      42%        23.5%
    left-dominant signers   ~10%        19.5%  (8/41)

Two conclusions, and they point in opposite directions:

1. **The reserve step must not run here.** `canonicalize()` ends with
   `a[:, RESERVED_BLOCK, :] = np.nan` — it keeps the dominant hand and deletes the other.
   On GISLR that deletes nothing (both hands live in 1.7% of clips; its header says
   "reserving 21 of 75 point slots for a hand that is ALWAYS absent is waste"). On Sem-Lex
   it would delete a genuinely recorded passive hand in **41.2%** of clips. And the cost is
   already measured on GISLR: `--mask-resting-hand train` NaN-ed exactly these hands and lost
   **0.0312 test / 0.0415 val**, train accuracy 0.767 -> 0.498 (`pick_signing_block` docstring,
   2026-08-13). The passive hand carries signal. Do not throw it away.

2. **The problem canonicalization solves is much smaller here.** GISLR's L-share of one-handed
   clips is 42% — near chance, uncorrelated with handedness, i.e. a pure recording convention
   and free to normalize away. Sem-Lex's is 23.5%, and it tracks the measured left-dominant
   signer rate (19.5%): the blocks mean what they say. So the block assignment is signal, not
   noise.

❌ AND THE MIRROR ITSELF BUYS NOTHING — MEASURED 2026-08-28. `--canonical` IS NOT A DEFAULT.
------------------------------------------------------------------------------------------
Trained both arms on **fold 2**, the only split with power to measure this (its val is 71.6%
left-dominant clips; folds 0 and 1 contain ZERO left-dominant signers and would have returned a
null by construction). Same seed, `--decimate 0.5` on both:

    landmarks  val acc 0.7477   (epochs_run 200)
    canonical  val acc 0.7484   (epochs_run 187)
    difference           +0.0007        <- one clip out of 1,391

Flat, on the most favourable split that exists. The mechanism is in train.py's own config line:

    [cfg] layout = LEGACY (L@33-53, R@54-74) | hflip swaps hands = True

`train.py`'s hflip augmentation ALREADY mirrors the clip and swaps the hand blocks on 50% of
samples every epoch — the identical operation this function performs, applied stochastically at
train time instead of statically here. The model is handedness-invariant before we touch it.

Same verdict on GISLR: canonical-vs-legacy was +0.0032 at 30 fps. The measured win on the
250-word model was `--decimate` (+0.0218 paired at 7 fps), never canonicalization.

So `--canonical` is kept as a MEASURED-NEUTRAL option, the way `--no-trim` is kept: it makes the
comparison reproducible, it is not advice. Reach for it only if hflip's hand-swapping is turned
off (i.e. with `train.py --canonical-hand`, which this corpus must never use — see above).

Hence `--canonical` here means **mirror only**: if the signer is left-dominant, negate x, apply
POSE_FLIP, and **swap the two hand blocks**. Both hands survive; the layout stays 75 points;
33-53 is never reserved.

THE DECISION IS PER SIGNER, NOT PER CLIP — measured 2026-08-27
--------------------------------------------------------------
The first version decided per clip by `wrist_travel` (which arm moved more), on the reasoning
that the tracker drops the MOVING hand so block presence picks the resting one. That reasoning
is correct on GISLR and **wrong here**, and the tripwire built into this script caught it on the
first full run:

    per-clip wrist travel mirrored   3,587 / 6,996 = 51.3%
    clips belonging to left-dominant signers      = 18.4%   (8 signers of 41)

A coin flip. The mechanism, once stated, is obvious:

  * `wrist_travel` asks which ARM moved more. On GISLR one arm signs and the other is absent
    or still, so the answer is decisive. Here **41.2% of clips are genuinely two-handed**, so
    both wrists travel comparably and the SIGN of the difference is noise.
  * The trimmed span begins at hand-tracking ONSET, which includes the bilateral hand-RAISE and
    hand-LOWER. Both arms move through those on every clip.
  * Path length is a sum of |diffs|: it accumulates noise monotonically and never cancels, so a
    near-tie does not average out, it randomizes.

Handedness is a property of a PERSON. Aggregating hand-block presence over all of a signer's
clips separates this corpus cleanly — DOMINANCE = L/(L+R) is bimodal with a **0.100 gap between
0.463 and 0.563** across 41 signers, so any threshold in 0.50-0.60 gives the same 8 signers.
That is `--canonical-mode signer`, the default; `--canonical-mode clip` reproduces the refuted
rule, kept for the same reason `--no-trim` is.

Note the inversion worth remembering: on GISLR block presence was a *recording artifact* and
useless for handedness; here both hands are recorded, the dominant hand is present throughout
while the passive one appears only in two-handed signs, so presence becomes the RELIABLE signal
and per-clip motion becomes the unreliable one. Same two statistics, opposite verdicts, because
the corpora were collected differently.

⚠️ Still opt-in, default OFF, and the mirrored fraction is printed against the per-signer
prediction every run — that check is what caught the bug and it stays.
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


POSE_L_WRIST, POSE_R_WRIST = 15, 16
L_SHOULDER_I, R_SHOULDER_I = 11, 12

# Pose half of train.py's FLIP_MAP: anatomical left/right pairs, self-inverse. Copied from
# extract_canonical.POSE_FLIP rather than imported, because importing that module drags in
# sign_landmarks.py (425 lines, and it raises SystemExit at import time if absent) and both
# would then have to be staged on Kaggle. test_semlex_adapter asserts this array still equals
# extract_canonical.POSE_FLIP whenever that module IS importable, so the copy cannot drift.
POSE_FLIP = np.array([
    0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
    22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31,
], dtype=np.int32)
assert POSE_FLIP.shape[0] == POSE_N and sorted(POSE_FLIP.tolist()) == list(range(POSE_N))


def wrist_travel(clip: np.ndarray) -> dict:
    """Total shoulder-normalized path length of each wrist. Vendored from
    sign_landmarks.wrist_travel (same reason as POSE_FLIP above; the test pins them equal).

    This — not hand-block presence — is how dominance must be decided. Presence identifies the
    hand that stayed STILL, because the tracker drops the moving one.

    Idempotent on already-normalized input: `normalize` leaves the shoulders exactly 1.0 apart
    and centred on the origin, so the rescale below is a divide by 1.0 and a subtract of 0.
    """
    travel = {}
    ls, rs = clip[:, L_SHOULDER_I, :2], clip[:, R_SHOULDER_I, :2]
    sw = np.linalg.norm(ls - rs, axis=-1)
    mid = (ls + rs) / 2.0
    for name, wr in (("L", POSE_L_WRIST), ("R", POSE_R_WRIST)):
        w = clip[:, wr, :2]
        ok = (np.isfinite(w).all(-1) & np.isfinite(ls).all(-1)
              & np.isfinite(rs).all(-1) & (sw > 1e-6))
        p = np.where(ok[:, None], (w - mid) / np.where(sw[:, None] > 1e-6, sw[:, None], 1.0),
                     np.nan)
        travel[name] = float(np.nansum(np.linalg.norm(np.diff(p, axis=0), axis=-1)))
    return travel


def mirror_clip(seq: np.ndarray) -> np.ndarray:
    """UNCONDITIONAL horizontal mirror of a normalized (T,75,3) clip. Both hands kept.

    Deliberately NOT extract_canonical.canonicalize: that function ends by moving the dominant
    hand to 54-74 and NaN-ing 33-53, which deletes a real passive hand in 41.2% of Sem-Lex
    clips (module docstring). Here the two hand blocks are SWAPPED instead of collapsed.

    Every operation is pointwise-in-time (x negation) or a fixed index permutation, so this
    COMMUTES with time_resize — it may be applied before or after resampling. The test pins
    that, because relying on it silently would be a trap for the next reader.
    """
    out = seq.copy()
    out[..., 0] *= -1.0                          # x negation makes a left hand read as a right
    out[:, OUR_POSE, :] = out[:, POSE_FLIP, :]   # fancy-index RHS copies first — safe in place
    # The x negation fixes the GEOMETRY but not the FILING: the left hand's coordinates are
    # still in the L block. Swap, so dominant is always R and passive always L.
    keep = out[:, OUR_L_HAND, :].copy()
    out[:, OUR_L_HAND, :] = out[:, OUR_R_HAND, :]
    out[:, OUR_R_HAND, :] = keep
    return out


def canonical_mirror(seq: np.ndarray) -> tuple:
    """PER-CLIP mirror decision by wrist travel.

    ⚠️ REFUTED AS A DEFAULT ON THIS CORPUS, 2026-08-27. Kept behind `--canonical-mode clip`
    so the measurement stays reproducible, exactly like `--no-trim`.

    Measured on the full clinical set: this rule mirrored **3,587/6,996 clips = 51.3%**, against
    a corpus that has only **8 left-dominant signers of 41 (18.4% of clips)**. It is a coin
    flip, and the mechanism is clear once stated:

      * `wrist_travel` asks WHICH ARM MOVED MORE. On GISLR that is decisive — one arm signs and
        the other is absent or still.
      * Here **41.2% of clips are genuinely two-handed**, so both wrists travel comparably and
        the SIGN of the difference is noise.
      * And the trimmed span starts at hand-tracking ONSET, which includes the bilateral
        hand-RAISE and hand-LOWER. Both arms move through those, on every clip.

    Path length is a sum of absolute differences, so it accumulates noise monotonically and
    never cancels — a near-tie does not average out, it randomizes.

    Use `--canonical-mode signer` (the default): handedness is a property of a PERSON, not of a
    clip, and aggregating block presence per signer separates the corpus cleanly (a 0.100 gap
    between 0.463 and 0.563 on 41 signers).
    """
    tr = wrist_travel(seq)
    st = {"travel_l": round(tr["L"], 4), "travel_r": round(tr["R"], 4), "mirrored": False}
    if tr["L"] <= tr["R"] or (tr["L"] == 0.0 and tr["R"] == 0.0):
        return seq, st
    st["mirrored"] = True
    return mirror_clip(seq), st


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


def tracked_mask(pts: np.ndarray) -> np.ndarray:
    """(T,) bool — is EITHER hand block present on this frame? Same predicate the
    hand-presence gate counts, so trimming and gating cannot disagree."""
    l = ~np.isnan(pts[:, OUR_L_HAND, 0]).all(axis=1)
    r = ~np.isnan(pts[:, OUR_R_HAND, 0]).all(axis=1)
    return l | r


def tracked_span(pts: np.ndarray) -> tuple[int, int]:
    """(first, last) inclusive indices of the tracked span, or (-1,-1) if no hand ever appears.
    Interior gaps are deliberately KEPT: only 5.3% of frames are interior, and dropping them
    would splice together non-adjacent moments of the sign — the same fabrication argument that
    ruled out interpolating the fingerspelling gaps."""
    tr = tracked_mask(pts)
    if not tr.any():
        return -1, -1
    return int(np.argmax(tr)), int(len(tr) - 1 - np.argmax(tr[::-1]))


def clip_to_tensor(clip553: np.ndarray, *, min_hand_rate=HANDPRESENCE_MIN,
                   min_frames=MIN_VALID_FRAMES, trim: bool = True,
                   canonical: bool = False) -> tuple:
    """One Sem-Lex clip -> ((64,75,3), stats) or (None, stats) if unusable.
    Gate order follows extract_landmarks.clip_to_tensor; the trim step is inserted BEFORE the
    hand-presence gate, because on this corpus that gate otherwise measures how long the
    participant left the camera running (see the module docstring)."""
    pts = to_75(clip553)
    n_raw = int(pts.shape[0])
    st = {"frames": n_raw, "raw_frames": n_raw, "valid": 0, "hand_frames": 0,
          "l_frames": 0, "r_frames": 0, "hand_rate": 0.0, "raw_hand_rate": 0.0,
          "lead": 0, "trail": 0, "span": n_raw, "trimmed": False, "reason": ""}
    st["raw_hand_rate"] = float(tracked_mask(pts).mean()) if n_raw else 0.0

    if trim:
        first, last = tracked_span(pts)
        if first < 0:
            st["reason"] = "no tracked hand in any frame"
            return None, st
        st["lead"], st["trail"] = first, n_raw - 1 - last
        st["span"] = last - first + 1
        st["trimmed"] = bool(first or st["trail"])
        # A 2-frame span is what the raw<0.10 bucket looks like: a spurious single-frame hand
        # detection, not a sign. Reject on LENGTH before the rate gate, or a 2-frame span with
        # both frames tracked would score a perfect 1.00 hand-rate and sail through.
        if st["span"] < min_frames:
            st["reason"] = (f"tracked span only {st['span']} frames (<{min_frames}) — "
                            f"raw hand-rate was {st['raw_hand_rate']:.0%}")
            return None, st
        pts = pts[first:last + 1]
        st["frames"] = int(pts.shape[0])

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
        st["reason"] = (f"hand in only {st['hand_rate']:.0%} of the "
                        f"{'trimmed span' if trim else 'clip'} (<{min_hand_rate:.0%}) — "
                        f"no usable handshape")
        return None, st

    arr = np.stack(seq)
    # Mirror LAST, after every gate. l_frames / r_frames deliberately stay PRE-mirror: they
    # measure the corpus's handedness, which is what --report's DOMINANCE column reports, and
    # canonicalizing them first would make that column read 100% right-dominant by construction.
    if canonical:
        arr, mst = canonical_mirror(arr)
        st.update(mst)
    return time_resize(arr, MAX_LEN), st


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


def load_concept_map(path: Path) -> dict:
    """vocab_medical_analysis.json -> {sem-lex label: clinical concept}.

    WHY THIS IS NOT OPTIONAL. The vocabulary is **145 concepts**, but Sem-Lex ships **146
    labels**, and they are not the same set:

        knee     <- ["knee", "knees"]     one sign, two labels
        eye      <- ["eyes"]              renamed
        hand     <- ["hands"]             renamed
        thankyou <- ["thank_you"]         renamed

    Training on raw labels splits KNEE into two classes of 5 and 1 instead of one class of 6,
    and leaves `eyes`/`hands`/`thank_you` as classes the clinical vocabulary never asked for.
    The first extraction run did exactly that: it reported `classes=146`.
    """
    blob = json.loads(path.read_text(encoding="utf-8"))
    m = {}
    for tier in ("tier_A_trainable", "tier_B_thin"):
        for concept, rec in blob.get(tier, {}).items():
            for lab in rec["labels"]:
                m[lab.strip().lower()] = concept
    if not m:
        raise SystemExit(f"[err] no concepts found in {path}")
    return m


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
    ap.add_argument("--concepts", default=None,
                    help="vocab_medical_analysis.json — MERGE Sem-Lex labels into clinical "
                         "concepts (knee+knees -> knee; eyes -> eye; hands -> hand; "
                         "thank_you -> thankyou). Without it you train 146 label-classes "
                         "instead of 145 concept-classes and KNEE is split into 5 and 1. "
                         "Strongly recommended; omit only to inspect raw labels.")
    ap.add_argument("--out", default="semlex_medical_landmarks.npz")
    ap.add_argument("--limit", type=int, help="process at most N clips (smoke test)")
    ap.add_argument("--min-hand-rate", type=float, default=HANDPRESENCE_MIN)
    ap.add_argument("--min-frames", type=int, default=MIN_VALID_FRAMES)
    ap.add_argument("--no-trim", dest="trim", action="store_false",
                    help="do NOT trim to the tracked span. Reproduces the 2026-08-27 first run, "
                         "which rejected 48.5%% of clips because 61.5%% of frames are lead-in/"
                         "lead-out dead air. Kept so the decision stays auditable.")
    ap.set_defaults(trim=True)
    ap.add_argument("--canonical", action="store_true",
                    help="MIRROR-ONLY canonicalization: if wrist travel says the signing arm is "
                         "the left one, negate x, POSE_FLIP the pose, and SWAP the hand blocks "
                         "so the dominant hand is always 54-74 and the passive one always 33-53. "
                         "This is NOT train.py --canonical-hand / extract_canonical.canonicalize: "
                         "those NaN the 33-53 block, which on Sem-Lex deletes a real passive hand "
                         "in 41.2%% of clips (GISLR: 1.7%%), and masking that hand cost 0.0312 "
                         "test on GISLR. Matches what live_demo.py --canonical does to a live "
                         "segment, so both models can share one inference flag. ⚠️ UNVALIDATED "
                         "on this corpus — opt-in, and the mirrored fraction is printed.")
    ap.add_argument("--canonical-mode", choices=("signer", "clip"), default="signer",
                    help="how the signing arm is decided. 'signer' (default): aggregate hand-"
                         "block presence over ALL of a signer's clips and mirror that signer's "
                         "whole set — handedness is a property of a person, not a clip, and the "
                         "corpus separates cleanly (0.100 gap at 41 signers). 'clip': per-clip "
                         "wrist travel — REFUTED 2026-08-27, it mirrored 51.3%% of clips on a "
                         "corpus with 18.4%% left-dominant clips, because 41.2%% of clips are "
                         "two-handed and the trimmed span includes the bilateral hand-raise. "
                         "Kept only so the measurement reproduces.")
    ap.add_argument("--dominance-threshold", type=float, default=0.55,
                    help="L/(L+R) block presence above which a SIGNER is called left-dominant "
                         "(default 0.55). Measured distribution is bimodal with a gap between "
                         "0.463 and 0.563, so anything in 0.50-0.60 gives the same answer.")
    ap.add_argument("--report", action="store_true",
                    help="per-signer hand-block presence — the diagnostic that predicted "
                         "the 250-word model's 0.314 signer. Read it BEFORE training.")
    args = ap.parse_args()

    allowed = None
    if args.vocab:
        raw = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
        allowed = {w.lower() for w in (raw["words"] if isinstance(raw, dict) else raw)}
        print(f"[cfg] restricting to {len(allowed)} labels from {Path(args.vocab).name}")

    cmap = load_concept_map(Path(args.concepts)) if args.concepts else None
    if cmap:
        print(f"[cfg] concept map: {len(cmap)} labels -> {len(set(cmap.values()))} concepts")
    else:
        print("[warn] no --concepts: training on RAW Sem-Lex labels. knee/knees stay split.")

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

    def to_concept(lab: str) -> str:
        return cmap.get(lab, lab) if cmap else lab
    words = sorted({to_concept(man[v][0]) for v in wanted})
    widx = {w: i for i, w in enumerate(words)}
    if cmap:
        unmapped = sorted({man[v][0] for v in wanted if man[v][0] not in cmap})
        if unmapped:
            print(f"[warn] {len(unmapped)} labels absent from the concept map, kept as-is: "
                  f"{unmapped[:10]}")

    X, y, signer, clip, split = [], [], [], [], []
    span, raw_frames, lead, trail = [], [], [], []   # native timing, destroyed by time_resize
    per_signer, skipped = {}, []
    trim_stats = {"trimmed": 0, "cut_frames": 0, "kept_frames": 0, "rescued": 0, "mirrored": 0}
    checked_sentinel = False
    t0 = time.perf_counter()
    print(f"[cfg] trim-to-tracked-span: {'ON' if args.trim else 'OFF (--no-trim)'}")
    if args.canonical:
        _canon_msg = (f"ON, mode={args.canonical_mode} — both hands KEPT, blocks swapped when "
                      f"the signing arm is left")
        if args.canonical_mode == "clip":
            _canon_msg += ("\n      ⚠️ per-CLIP wrist travel is REFUTED on this corpus "
                           "(mirrored 51.3% vs 18.4% of clips actually left-dominant). "
                           "Use --canonical-mode signer unless you are reproducing that.")
    else:
        _canon_msg = "OFF (hand blocks exactly as recorded)"
    print(f"[cfg] canonical mirror: {_canon_msg}")

    for n, (vid, raw) in enumerate(src.iter(wanted), 1):
        if args.limit and len(clip) >= args.limit:
            break
        if not checked_sentinel:                 # once is enough; it is a release-wide property
            assert_sentinel(np.asarray(raw, np.float32))
            checked_sentinel = True
        lab, sg, sp = man[vid]
        lab = to_concept(lab)
        # mode 'signer' needs every clip's block presence before it can decide anything, so the
        # mirror happens after the loop; only mode 'clip' can decide inline.
        arr, st = clip_to_tensor(np.asarray(raw), min_hand_rate=args.min_hand_rate,
                                 min_frames=args.min_frames, trim=args.trim,
                                 canonical=args.canonical and args.canonical_mode == "clip")
        if arr is None:
            skipped.append((vid, lab, st["reason"]))
        else:
            X.append(arr); y.append(widx[lab]); signer.append(sg)
            clip.append(vid); split.append(sp)
            # NATIVE DURATION. time_resize() below stretches every clip to MAX_LEN frames, so
            # the sign's real length is destroyed and cannot be recovered from X afterwards.
            # It is not recoverable from semlex_metadata.csv either: that file's `duration` is
            # the RAW recording (median 1822 ms, spread only 1.60x, CV 0.10) and is dominated
            # by the prompted-studio protocol, not by sign length — 61.5% of those frames are
            # lead-in/lead-out that this function trims away. The trimmed span IS the sign,
            # and it is 18-27 frames against 38-52 raw, so a resized clip plays roughly 2.4x
            # to 3.6x too slow on the avatar.
            #
            # The number already exists three lines up; it was simply never saved. Carry it.
            span.append(st["span"]); raw_frames.append(st["raw_frames"])
            lead.append(st["lead"]); trail.append(st["trail"])
            d = per_signer.setdefault(sg, {"n": 0, "l": 0.0, "r": 0.0, "frames": 0})
            d["n"] += 1; d["frames"] += st["frames"]
            d["l"] += st["l_frames"]; d["r"] += st["r_frames"]
            trim_stats["trimmed"] += st["trimmed"]
            trim_stats["cut_frames"] += st["lead"] + st["trail"]
            trim_stats["kept_frames"] += st["frames"]
            # the whole point: it would have been thrown away without the trim
            trim_stats["rescued"] += st["raw_hand_rate"] < args.min_hand_rate
            trim_stats["mirrored"] += st.get("mirrored", False)
        if args.report and n <= 20:
            print(f"  {vid} {lab:12} raw={st['raw_frames']:3}f rate={st['raw_hand_rate']:4.0%} "
                  f"-> span={st['span']:3}f rate={st['hand_rate']:4.0%} "
                  f"L={st['l_frames']:3} R={st['r_frames']:3} "
                  f"{'SKIP: ' + st['reason'] if arr is None else 'ok'}")
        if n % 500 == 0:
            el = time.perf_counter() - t0
            print(f"[{n}/{len(wanted)}] kept={len(X)} skipped={len(skipped)} {el:.0f}s")

    if not X:
        sys.exit("[err] nothing extracted — every clip failed the gates (see reasons above)")

    # ── PER-SIGNER canonicalization (the default) ──────────────────────────────────────────
    # Handedness belongs to a PERSON. Deciding per clip by wrist travel mirrored 51.3% of a
    # corpus that is 18.4% left-dominant (see canonical_mirror's docstring); aggregating block
    # presence over a signer's whole set separates it cleanly instead. mirror_clip commutes
    # with time_resize, so applying it here to the already-resized tensors is exact.
    left_signers = set()
    if args.canonical and args.canonical_mode == "signer":
        for sg, d in per_signer.items():
            tot = d["l"] + d["r"]
            if tot and d["l"] / tot >= args.dominance_threshold:
                left_signers.add(sg)
        for i, sg in enumerate(signer):
            if sg in left_signers:
                X[i] = mirror_clip(X[i])
                trim_stats["mirrored"] += 1
        thin = sorted(sg for sg in left_signers if per_signer[sg]["n"] < 10)
        if thin:
            detail = ", ".join(f"{s}:{per_signer[s]['n']}" for s in thin)
            print(f"[canonical] ⚠️  {len(thin)} left-dominant calls rest on fewer than 10 clips "
                  f"({detail}) — a thin vote, but mirroring the wrong way costs at most "
                  f"those clips")

    Xn = np.stack(X).astype(np.float32)
    # `span` is the one array here that is NOT reconstructable downstream: X is resized to a
    # fixed length, so without this the avatar has to play every sign for the same duration.
    # npz_to_train_format.py ignores unknown keys, so adding them is backward-compatible.
    np.savez_compressed(args.out, X=Xn, y=np.array(y, np.int32), words=np.array(words),
                        signer=np.array(signer, dtype=object).astype(str),
                        clip=np.array(clip, dtype=object).astype(str),
                        split=np.array(split, dtype=object).astype(str),
                        span=np.array(span, np.int32),
                        raw_frames=np.array(raw_frames, np.int32),
                        lead=np.array(lead, np.int32), trail=np.array(trail, np.int32))
    print(f"\n[ok] wrote {args.out}: X={Xn.shape} classes={len(words)} "
          f"signers={len(set(signer)) } skipped={len(skipped)}")
    sp_a = np.array(span, np.int32)
    print(f"[native] span (the SIGN, post-trim): min={sp_a.min()} median={int(np.median(sp_a))} "
          f"max={sp_a.max()} frames  |  X is {Xn.shape[1]}f, so the median sign is played "
          f"{Xn.shape[1] / max(1, np.median(sp_a)):.1f}x too slow if you use X's length as the "
          f"duration. Retime with `span` (gloss_to_motion reads nativeFrames).")

    cnt = np.bincount(np.array(y, np.int32), minlength=len(words))
    print(f"[stats] videos/class: min={cnt.min()} median={int(np.median(cnt))} max={cnt.max()} "
          f"imbalance={cnt.max() / max(cnt.min(), 1):.0f}x")
    weak = [(words[i], int(c)) for i, c in enumerate(cnt) if c < 8]
    if weak:
        print(f"[warn] {len(weak)} classes under 8 clips AFTER extraction: {weak[:20]}")
    sp = np.array(split)
    print("[stats] split: " + "  ".join(f"{s}={int((sp == s).sum())}" for s in sorted(set(split))))
    print("[stats] ⚠️  score on split=='test' only — Sem-Lex's val shares 31/32 signers with train")
    if args.trim and len(X):
        cut, kept = trim_stats["cut_frames"], trim_stats["kept_frames"]
        print(f"[trim] {trim_stats['trimmed']}/{len(X)} clips trimmed; cut {cut:,} dead-air "
              f"frames, kept {kept:,} ({cut / max(cut + kept, 1):.1%} of recorded frames were "
              f"lead-in/lead-out)")
        print(f"[trim] RESCUED {trim_stats['rescued']:,} clips that the raw hand-rate gate would "
              f"have thrown away ({trim_stats['rescued'] / max(len(X), 1):.1%} of the kept set)")
    if args.canonical and len(X):
        m = trim_stats["mirrored"]
        how = (f"{len(left_signers)} signers called left-dominant at L/(L+R) >= "
               f"{args.dominance_threshold}" if args.canonical_mode == "signer"
               else "per-clip wrist travel (REFUTED — see --canonical-mode)")
        print(f"[canonical] mirrored {m:,}/{len(X):,} clips ({m / len(X):.1%}) via {how}. "
              f"Both hand blocks kept in every clip; 33-53 is never reserved.")
        if left_signers:
            print(f"[canonical] mirrored signers: "
                  f"{sorted(left_signers, key=lambda s: -per_signer[s]['n'])}")
        # The tripwire that caught the per-clip rule. Keep it: it is the only automatic check
        # that the mirror decision tracks handedness rather than noise.
        exp = sum(d["n"] for sg, d in per_signer.items()
                  if (d["l"] + d["r"]) and d["l"] / (d["l"] + d["r"]) >= args.dominance_threshold)
        if abs(m - exp) > 0.25 * max(len(X), 1):
            print(f"[canonical] ⚠️  MIRRORED {m:,} BUT PER-SIGNER DOMINANCE PREDICTS {exp:,} "
                  f"({exp / len(X):.1%}). That gap means the decision rule is not tracking "
                  f"handedness. Do NOT train on this npz until it is explained.")

    if args.report:
        # The 250-word post-mortem: per-signer accuracy tracked HAND-BLOCK LAYOUT, which is a
        # recording artifact, and the worst signer (0.314) was the one with BOTH blocks
        # populated. Printing it here means a bad signer is visible before the GPU bill.
        #
        # DOMINANCE is the column to read, not L and R. The absolute fractions are diluted by
        # however much dead air survived, so on the untrimmed 2026-08-27 run every single
        # signer read "mixed" — an artifact, not a finding. L/(L+R) is scale-free and shows the
        # real split. Both hands are tracked on two-handed signs, so dominance sits near 0.5
        # for a balanced signer; the tails are what matter.
        print("\nPER-SIGNER HAND-BLOCK PRESENCE (fraction of kept frames the block is tracked)")
        print("  measured PRE-mirror, so this column always describes the CORPUS, never the "
              "transform")
        print(f"{'signer':>8} {'clips':>6} {'L':>7} {'R':>7} {'DOMINANCE':>10} {'MIRROR':>7}  "
              f"reading")
        rows = sorted(per_signer.items(), key=lambda kv: -kv[1]["n"])
        n_left = n_right = 0
        for sg, d in rows:
            l, r = d["l"] / max(d["frames"], 1), d["r"] / max(d["frames"], 1)
            dom = l / (l + r) if (l + r) > 0 else float("nan")
            if dom >= 0.60:
                reading, n_left = "LEFT-dominant", n_left + 1
            elif dom <= 0.40:
                reading, n_right = "right-dominant", n_right + 1
            else:
                reading = "balanced / two-handed"
            if min(l, r) > 0.30 and 0.40 < dom < 0.60:
                reading += "  <- BOTH blocks, the 0.314 pattern"
            mk = "YES" if sg in left_signers else ("-" if args.canonical else "")
            print(f"{sg:>8} {d['n']:>6} {l:>7.3f} {r:>7.3f} {dom:>10.3f} {mk:>7}  {reading}")
        tot = len(rows)
        print(f"\n[handedness] {n_left}/{tot} LEFT-dominant, {n_right}/{tot} right-dominant, "
              f"{tot - n_left - n_right}/{tot} balanced")
        # SUPERSEDED 2026-08-27. This line used to say "if the left share is higher than GISLR's
        # ~10%, train with --canonical-hand". Measured on 3,000 clinical clips, that was wrong:
        # BOTH hands are live in 41.2% of Sem-Lex clips vs 1.7% of GISLR's, and --canonical-hand
        # NaN-s the 33-53 block, so it would delete a real passive hand in 2 clips in 5. Masking
        # that hand on GISLR — where it was the ONLY hand — already cost 0.0312 test / 0.0415 val.
        # Use --canonical (mirror only, both hands kept) instead. See the module docstring.
        print("[handedness] ⚠️  do NOT reach for train.py --canonical-hand on this corpus: it "
              "reserves block 33-53, and 41.2% of Sem-Lex clips have a REAL hand there "
              "(GISLR: 1.7%). Use this script's --canonical, which mirrors and SWAPS the blocks "
              "instead of deleting one.")

    if skipped:
        print(f"\n[warn] skipped {len(skipped)} clips; first few:")
        for vid, lab, why in skipped[:10]:
            print(f"        {vid} ({lab}): {why}")


if __name__ == "__main__":
    main()
