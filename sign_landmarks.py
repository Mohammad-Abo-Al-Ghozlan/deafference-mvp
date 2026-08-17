#!/usr/bin/env python3
"""Shared landmark conventions for the speech->sign (animation) pipeline.

WHY THIS MODULE EXISTS
----------------------
The preprocessed corpus encodes a MISSING landmark as exact ``0.0``, not NaN.
See training/README.md: *"NaN = padding sentinel. Real preprocessed frames
contain no NaN."*  Every consumer downstream was written against the NaN
convention instead, so each one independently treated a hand collapsed at the
origin as a fully tracked hand.

That single mismatch produced three separate defects, all found in the
2026-08-10 animation-side audit:

1. ``build_sign_clips.hand_presence()`` tested ``np.isfinite()``, and
   ``np.isfinite(0.0)`` is True.  238 of 250 clips therefore scored a perfect
   1.0, the ``pres > best[w][0]`` comparison never fired, and the "pick the
   cleanest exemplar per word" selector silently degenerated into "keep the
   first clip in manifest order".  The ``pres < 0.5`` weak-clip warning was
   mathematically unable to trigger, which is why the build reported a clean
   250/250.
2. The same function OR-ed both hand blocks together (``clip[:, 33:75]``), so a
   single tracked RESTING hand masked a completely absent SIGNING hand.  This is
   the measured inversion: 51.5% coverage on the resting hand vs 28.8% on the
   hand actually doing the sign.
3. ``normalize_clip()`` maps an exact ``0.0`` to a ~6e-8 floating-point residue,
   which ``round(v, 5)`` in the JSON encoder snaps back to exactly ``0.0``.
   19,002 hand blocks (59.4%) shipped as ``[0,0,0]`` rather than ``null`` — and
   in shoulder-centred space the origin is mid-sternum, so a renderer that
   correctly follows the contract draws the entire hand inside the chest.

Fix the convention in ONE place and all three disappear.  Import from here;
do not re-implement any of it.

CONVENTION AFTER canonicalize_missing()
---------------------------------------
NaN means "not observed" — for a padded frame, an undetected hand, or an
undetected point.  ``0.0`` is a legitimate coordinate again (it means
"at the shoulder midpoint"), which is what the contract has always promised.
"""
from __future__ import annotations

import numpy as np

# ── layout (contract §2) ──────────────────────────────────────────────────────
N_POINTS = 75
POSE_N = 33
HAND_N = 21
L_HAND = slice(33, 54)
R_HAND = slice(54, 75)
HAND_BLOCKS = (("L", L_HAND), ("R", R_HAND))

POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
POSE_L_WRIST, POSE_R_WRIST = 15, 16
POSE_L_HIP, POSE_R_HIP = 23, 24

# A coordinate this close to the origin is the zero sentinel, not a measurement.
# Deliberately looser than float32 epsilon: normalize_clip() re-centres by the
# shoulder midpoint, which turns an exact 0.0 into a ~6e-8 residue, and the JSON
# encoder rounds to 5 decimals.  1e-4 sits above that noise and far below any
# real landmark, which lives at O(0.1-1) shoulder-widths.
ZERO_EPS = 1e-4

# Above this weaker/stronger wrist-travel ratio a sign is TWO-handed and both
# hands carry handshape.  Matches the animation side's check-export.py so our
# selection metric and their acceptance metric are the same number.
TWO_HANDED_RATIO = 0.70

# Two-handed scoring weights (animation side's request, 2026-08-11 REPLY-TO-SALIM-v4 §4).
#
# NOT strict min(left, right).  Under strict min a candidate with a perfectly tracked
# dominant hand and an absent passive hand scores 0 — ranked BELOW a candidate that is
# mediocre on both.  That ordering is backwards for the renderer: a passive hand can be
# synthesized credibly, a dominant hand cannot.
#
# The linguistics agree.  Battison's Dominance Condition: in ASYMMETRIC two-handed signs
# the passive hand is a static base and its handshape is restricted to a small set of
# unmarked handshapes (B, A, S, 1, 5, C, O), so it is highly predictable and carries little
# contrast.  The dominant hand carries the phonemic load.
DOMINANT_WEIGHT = 0.70
PASSIVE_WEIGHT = 0.30

# A passive wrist this far down (fraction of the shoulder->hip span, y is DOWN) is HANGING
# rather than held in signing space.  Used only to report the symmetric/asymmetric gap
# below; it does not drive scoring.
RESTING_HAND_FRAC = 0.50


def canonicalize_missing(clip: np.ndarray) -> np.ndarray:
    """Rewrite the zero-sentinel as NaN so the NaN-based logic downstream works.

    Two rules, both unambiguous:
      * a whole 21-point hand block sitting at the origin was never detected —
        21 landmarks cannot all be exactly at mid-sternum;
      * an individual point at exactly (0, 0, 0) is a sentinel, since three
        exact zeros do not occur in measured, re-centred data.

    Idempotent: NaN input stays NaN.  Never resurrects data, only re-labels
    absence, so it is safe to apply unconditionally at every load site.
    """
    out = np.array(clip, dtype=np.float32, copy=True)
    if out.ndim != 3 or out.shape[1] != N_POINTS:
        raise ValueError(f"expected (T,{N_POINTS},C), got {out.shape}")

    for _name, blk in HAND_BLOCKS:
        xy = out[:, blk, :2]
        gone = (np.abs(xy) < ZERO_EPS).all(axis=(1, 2)) | np.isnan(xy).all(axis=(1, 2))
        out[gone, blk, :] = np.nan

    exact = (np.abs(out) < ZERO_EPS).all(axis=-1)              # (T, 75)
    out[exact] = np.nan
    return out


def hand_coverage(clip: np.ndarray, extent: tuple[int, int] | None = None) -> dict:
    """Fraction of frames in which each hand block is actually present.

    Per hand, never OR-ed together — conflating them is defect #2 above.
    Expects a canonicalized clip.

    ``extent`` restricts the measurement to the real sign, per the animation side's
    request: 30 tracked frames concentrated on the stroke are worth more than 30
    scattered through a rest hold, because their interpolation bridges gaps but
    cannot invent a stroke.
    """
    if extent is not None:
        s, e = extent
        clip = clip[s:e]
    cov = {}
    for name, blk in HAND_BLOCKS:
        xy = clip[:, blk, :2]
        live = ~np.isnan(xy).all(axis=(1, 2))
        cov[name] = float(live.mean()) if live.size else 0.0
    return cov


def hand_coverage_runs(clip: np.ndarray, extent: tuple[int, int] | None = None) -> dict:
    """Per hand, the LONGEST CONTIGUOUS run of present frames, as a fraction of the window.

    Requested by the animation side 2026-08-12: their retargeter bridges gaps by
    interpolation, so a bridged handshape is a straight line between two real ones. 30
    frames spanning the stroke therefore beat 30 scattered across the take, and a plain
    fraction cannot tell those apart. This is the cheap proxy they suggested.
    """
    if extent is not None:
        s, e = extent
        clip = clip[s:e]
    runs = {}
    for name, blk in HAND_BLOCKS:
        live = ~np.isnan(clip[:, blk, :2]).all(axis=(1, 2))
        best = cur = 0
        for v in live:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        runs[name] = float(best / len(live)) if len(live) else 0.0
    return runs


def _normalized_xy(clip: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame shoulder-centred, shoulder-width-scaled x,y. Returns (xy, ok_mask).

    Several measurements below need this and the corpus is NOT normalized when the
    selector measures it (build_sign_clips normalizes only the winning clip, after
    selection). Doing it here means a caller cannot silently feed raw pixel coordinates
    into a test whose thresholds assume shoulder-width units — which is exactly how
    _passive_is_resting was wrong before 2026-08-12.
    """
    ls, rs = clip[:, POSE_L_SHOULDER, :2], clip[:, POSE_R_SHOULDER, :2]
    sw = np.linalg.norm(ls - rs, axis=-1)
    ok = np.isfinite(ls).all(-1) & np.isfinite(rs).all(-1) & (sw > 1e-6)
    mid = (ls + rs) / 2.0
    denom = np.where(sw[:, None, None] > 1e-6, sw[:, None, None], 1.0)
    xy = (clip[:, :, :2] - mid[:, None, :]) / denom
    xy[~ok] = np.nan
    return xy, ok


def _passive_is_resting(clip: np.ndarray, passive: str) -> bool | None:
    """Is the passive wrist HANGING (one-handed sign) or held up in signing space?

    Distinguishes a genuinely one-handed sign from an ASYMMETRIC two-handed sign,
    which the wrist-travel ratio alone cannot: in both cases one hand barely moves,
    but in the asymmetric case that static hand is a phonemically required base.

    Returns None when the hips or the wrist are untracked. Reported only — it does
    not drive scoring, because it is not yet validated against the corpus.
    """
    # FIXED 2026-08-12: this used to read clip[:, wr, 1] directly and comment that
    # "shoulders sit at y == 0 by construction". They do not — build_sign_clips normalizes
    # only the WINNING clip, after selection, so every candidate reached this function in raw
    # coordinates and the comparison against a shoulder-relative fraction was meaningless.
    # It did not matter while this was reported-only; it matters now that it is the actual
    # criterion for whether an asymmetric sign's passive hand is a held base or a dropped arm.
    xy, _ = _normalized_xy(clip)
    wr = POSE_L_WRIST if passive == "L" else POSE_R_WRIST
    w_col = xy[:, wr, 1]
    hip_col = np.concatenate([xy[:, POSE_L_HIP, 1], xy[:, POSE_R_HIP, 1]])
    # guard before nanmedian: an all-NaN slice is a legitimate input (untracked clip) and
    # warning on it would print once per candidate across a 94k-clip scan
    if not np.isfinite(w_col).any() or not np.isfinite(hip_col).any():
        return None
    y_w = float(np.nanmedian(w_col))
    y_hip = float(np.nanmedian(hip_col))
    if y_hip <= 0:
        return None
    # y is DOWN and shoulders are now at y == 0, so y_hip > 0 and the shoulder->hip span is
    # y_hip. Past RESTING_HAND_FRAC of the way down, the wrist is hanging, not held.
    return bool(y_w > RESTING_HAND_FRAC * y_hip)


def mirror_match(clip: np.ndarray, tol: float = 0.25) -> float:
    """Fraction of frames in which the two wrists are MIRROR IMAGES of each other.

    For a symmetric two-handed sign, both hands do the same thing on opposite sides, so the
    passive wrist should sit at the dominant wrist's reflection across the body midline.
    The animation side measured the renderer-side equivalent (mirrorPct) and found the median
    2s exemplar mirroring in 1 frame out of 8 — a much sharper signal than a travel ratio.

    Computed from POSE wrists only, so it works on every clip: pose wrists were present in
    3192/3192 frames measured, unlike the 21-point hand blocks.

    Dominance-free by construction: with the mirror being x -> -x,
        |p_pas - mirror(p_dom)|  ==  |p_dom - mirror(p_pas)|
    so the answer does not depend on which wrist is called dominant.

    CAVEAT: symmetric signs come in simultaneous and ALTERNATING forms (`stairs` alternates).
    An alternating sign has both arms moving equally but out of phase, so it scores low here
    while being a perfectly good take. That is why this is reported as a diagnostic and does
    NOT gate selection — see build_sign_clips.validity().
    """
    xy, ok = _normalized_xy(clip)
    l, r = xy[:, POSE_L_WRIST, :], xy[:, POSE_R_WRIST, :]
    good = ok & np.isfinite(l).all(-1) & np.isfinite(r).all(-1)
    if not good.any():
        return float("nan")
    mir = np.stack([-r[:, 0], r[:, 1]], axis=-1)               # reflect the right wrist
    d = np.linalg.norm(l - mir, axis=-1)
    return float((d[good] <= tol).mean())


def wrist_travel(clip: np.ndarray) -> dict:
    """Total shoulder-normalized path length of each wrist.

    This — not hand-block presence — is how dominance must be decided.  Presence
    identifies the hand that stayed STILL, because the tracker drops the moving
    one, so using presence to pick the dominant hand is wrong on ~60% of words.
    """
    travel = {}
    for name, wr in (("L", POSE_L_WRIST), ("R", POSE_R_WRIST)):
        ls, rs = clip[:, POSE_L_SHOULDER, :2], clip[:, POSE_R_SHOULDER, :2]
        w = clip[:, wr, :2]
        sw = np.linalg.norm(ls - rs, axis=-1)
        ok = np.isfinite(w).all(-1) & np.isfinite(ls).all(-1) & np.isfinite(rs).all(-1) & (sw > 1e-6)
        mid = (ls + rs) / 2.0
        p = np.where(ok[:, None], (w - mid) / np.where(sw[:, None] > 1e-6, sw[:, None], 1.0), np.nan)
        d = np.linalg.norm(np.diff(p, axis=0), axis=-1)
        travel[name] = float(np.nansum(d))
    return travel


def hand_arm_alignment(clip: np.ndarray) -> dict:
    """Does the TRACKED hand belong to the arm that is actually SIGNING?

    Hand landmark 0 is a wrist, so a tracked hand block must be co-located with the pose
    wrist of the limb it belongs to.  Comparing that limb against the travel-dominant limb
    answers the question coverage cannot: presence proves a hand was *tracked*, never that
    it was the signing hand.

    Why this is a GATE and not another diagnostic (measured 2026-08-12):

      * On the 250 exported exemplars the tracked hand sat on the STILL arm in 249/250 --
        median 0.082 shoulder-widths from one pose wrist and 1.783 from the other, so the
        limb assignment is not marginal, it is unambiguous.
      * Across all 80,647 corpus takes it sits on the MOVING arm 55.1% of the time, and
        every one of the 250 words has at least 55 such takes.
      * So chance would have given 55% good picks and maximizing hand-block coverage gave
        0.4%.  The old objective did not merely fail to avoid bad takes, it selected them,
        because the tracker drops the hand that moves -- the animation side measured 4.06x
        wrist speed in hand-missing frames, and our own within-word r = -0.464 said the
        same thing in different units.

    Nothing is stranded by demanding alignment, which is what makes it safe as a gate.
    Returns block/belongs/moving/aligned plus both distances, so a rejection can be
    explained rather than merely counted.
    """
    xy, ok = _normalized_xy(clip)                 # already in shoulder-width units
    out = {"block": None, "belongs": None, "moving": None, "aligned": False,
           "d_L": float("nan"), "d_R": float("nan")}

    counts = {n: int(np.isfinite(xy[:, blk, :]).all(-1).any(-1).sum())
              for n, blk in HAND_BLOCKS}
    if max(counts.values()) == 0:                 # no hand tracked at all
        return out
    block = max(counts, key=counts.get)
    out["block"] = block

    base = L_HAND.start if block == "L" else R_HAND.start   # point 0 of a hand block IS a wrist
    hw = xy[:, base, :]
    d = {}
    for n, wr in (("L", POSE_L_WRIST), ("R", POSE_R_WRIST)):
        dd = np.linalg.norm(hw - xy[:, wr, :], axis=-1)
        dd = dd[ok & np.isfinite(dd)]
        d[n] = float(np.median(dd)) if dd.size else float("inf")
    out["d_L"], out["d_R"] = d["L"], d["R"]
    if not np.isfinite([d["L"], d["R"]]).any():   # no frame with both a hand and a pose wrist
        return out

    out["belongs"] = "L" if d["L"] < d["R"] else "R"
    tr = wrist_travel(clip)
    out["moving"] = "L" if tr["L"] > tr["R"] else "R"
    out["aligned"] = out["belongs"] == out["moving"]
    return out


def required_hand_coverage(clip: np.ndarray, extent: tuple[int, int] | None = None,
                           two_handed: bool | None = None) -> dict:
    """Coverage over the hands the sign PHONEMICALLY REQUIRES — the score to maximize.

    One-handed: the signing hand only.  Two-handed: a WEIGHTED blend, not strict
    ``min`` — see DOMINANT_WEIGHT for why min ranks a perfect dominant hand below a
    mediocre pair, which is backwards for the renderer.

    Dominance comes from wrist TRAVEL, never from hand-block presence: the tracker
    keeps the hand that stayed still, so presence identifies the RESTING hand and
    using it would be wrong on ~60% of words.  There is deliberately no preference
    for either side — the animation side normalizes chirality downstream, so a
    left-dominant candidate is worth exactly as much as a right-dominant one.

    ``two_handed`` MUST be supplied when selecting between candidates.
    ---------------------------------------------------------------------------
    Handedness is a property of the SIGN, not of one recording.  Deciding it from
    the clip being scored is circular and the 2026-08-11 rebuild proved it
    catastrophic: a take in which one hand was never detected has a still passive
    arm, so it self-classifies as one-handed, the requirement collapses to that one
    hand, and it scores a perfect 1.000.  The selector duly picked a single-handed
    take for all 250 words — including `airplane` and `all`, which need two hands —
    and reported 99.4% coverage while doing it.  Pass the word-level verdict
    computed across ALL candidates (see build_sign_clips.py) and the loop is closed.
    Leaving it None reproduces the old per-clip behaviour and is for diagnostics only.
    """
    cov = hand_coverage(clip, extent)
    tv = wrist_travel(clip)
    dom = "R" if tv["R"] >= tv["L"] else "L"
    oth = "L" if dom == "R" else "R"
    ratio = tv[oth] / max(1e-9, tv[dom])

    is_two = (ratio >= TWO_HANDED_RATIO) if two_handed is None else bool(two_handed)
    # ALWAYS measured, never gated on the handedness guess (fixed 2026-08-12). This used to
    # be computed only in the one-handed branch and returned None otherwise — so once the
    # selector started GATING on it, the gate silently skipped every candidate whose own
    # travel ratio happened to look two-handed, which is precisely the set it had to check.
    # Whether the passive wrist is hanging is a property of the clip, not of a classification.
    resting = _passive_is_resting(clip, oth)
    if is_two:
        kind, required = "two-handed", "both"
        score = DOMINANT_WEIGHT * cov[dom] + PASSIVE_WEIGHT * cov[oth]
    else:
        kind, required = "one-handed", dom
        score = cov[dom]

    return {"score": float(score), "handedness": kind, "required": required,
            "dominant": dom, "passive": oth, "travel_ratio": round(ratio, 3),
            "dominant_travel": round(tv[dom], 4),
            # None for two-handed; False on a "one-handed" sign means the passive hand is
            # held UP in signing space, i.e. probably an ASYMMETRIC two-handed sign whose
            # static base we are not currently counting as required.
            "passive_resting": resting,
            "coverage": {k: round(v, 3) for k, v in cov.items()},
            "travel": {k: round(v, 3) for k, v in tv.items()}}


def pearson(a, b) -> float:
    """Pearson r, NaN-safe, 0.0 when either series is constant. No scipy dependency."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    da, db = float(np.sqrt((a ** 2).sum())), float(np.sqrt((b ** 2).sum()))
    if da < 1e-12 or db < 1e-12:
        return 0.0
    return float((a * b).sum() / (da * db))


def motion_extent(clip: np.ndarray, frac: float = 0.12, pad: int = 2) -> tuple[int, int]:
    """``(start, end)`` of the real sign inside the clip, as a half-open range.

    Answers the animation side's ASK 2: several clips end in dropped frames
    (``down`` loses its last 21), so the player scrubs through dead time before
    looping.  Frames are kept from the first to the last whose wrist speed
    exceeds ``frac`` of the clip's 90th-percentile speed.

    Falls back to the whole clip whenever the estimate would be degenerate —
    a wrong trim is worse than no trim.
    """
    t = int(clip.shape[0])
    if t < 8:
        return 0, t

    speeds = []
    for _n, wr in (("L", POSE_L_WRIST), ("R", POSE_R_WRIST)):
        p = clip[:, wr, :2]
        d = np.linalg.norm(np.diff(p, axis=0), axis=-1)
        speeds.append(d)
    # np.nanmax warns on an all-NaN column (both wrists untracked in that frame).
    # -inf is the correct identity here and compares below every threshold, so a
    # fully untracked frame simply reads as "not moving".
    st = np.stack(speeds)
    v = np.where(np.isnan(st).all(axis=0), -np.inf, np.nanmax(np.where(np.isnan(st), -np.inf, st), axis=0))
    if not np.isfinite(v).any():
        return 0, t

    peak = float(np.nanpercentile(v[np.isfinite(v)], 90))
    if peak <= 0.0:
        return 0, t
    moving = np.flatnonzero(np.nan_to_num(v, nan=0.0) > frac * peak)
    if moving.size == 0:
        return 0, t

    start = max(0, int(moving[0]) - pad)
    end = min(t, int(moving[-1]) + 2 + pad)                    # +1 for diff, +1 half-open
    if end - start < max(4, t // 8):
        return 0, t
    return start, end
