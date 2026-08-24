#!/usr/bin/env python
"""Export clean per-word skeleton videos to drive a pose-conditioned video model.

WHY THIS EXISTS, AND WHY NOT `preview_signs.py --save`
-----------------------------------------------------
`preview_signs.py` is the debug/review tool: its video path calls
`render_frame(pts, hud=[...])`, which burns a word label into every frame. Feeding that to an
image-to-video or pose-conditioned generator bakes the text into the generated output. This
writes the same skeleton with `hud=None` and nothing else on the canvas.

WHAT THE OUTPUT IS FOR
----------------------
A DRIVING video, not a deliverable. The linguistics (handshape, movement, location) come from
the recorded corpus; a generative model is only asked to supply appearance. That is the whole
point of driving it with real landmarks rather than prompting from a word: prompted hands are
invented, and in ASL the handshape IS the word.

Frames are hold-filled by default (contract §6): a point missing for 1-3 frames carries its
last value forward instead of vanishing. 550 of the 776 gaps in this corpus are that short and
are tracker dropout, not movement, so holding is correct here. `--raw` disables it.

Output is split by quality tier, because credits should not be spent evenly:
    tierA  coverage >= 80%   the ones worth generating
    tierB  50-80%            usable, check each
    tierC  < 50%             the dominant hand is missing over half the time; generating these
                             produces a confident-looking video of a sign that is not there

USAGE
    python export_driving_video.py                       # all 250, split by tier
    python export_driving_video.py --tier A              # just the good ones
    python export_driving_video.py --words hello thanks   # a specific demo list
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

import preview_signs as ps

HERE = Path(__file__).resolve().parent
TIER_A, TIER_B = 0.80, 0.50

# MediaPipe pose 25-32 are knees / ankles / heels / feet. `render_frame` draws every pose joint but
# POSE_EDGES connects only 0-16 and 23-24, so the legs come out as disconnected dots below the
# torso. They carry nothing for a seated-framing signing clip, and because they sit far down the
# canvas they dominated the global fit -- forcing the scale to 0.66x and shrinking the HANDS, which
# are the highest-information part of the frame. Dropped from both the fit and the render.
LEGS = slice(25, 33)


def upper_body(a: np.ndarray) -> np.ndarray:
    """Copy with the leg joints NaN'd. `_project` returns None for non-finite, so they vanish."""
    out = a.copy()
    out[:, LEGS, :] = np.nan
    return out


def tier_of(cov: float) -> str:
    return "A" if cov >= TIER_A else "B" if cov >= TIER_B else "C"


# ── human-figure renderer (--style human) ─────────────────────────────────────
# WHY THIS EXISTS
# `preview_signs.render_frame` is a DEBUG overlay: 2px lines and 3px dots on near-black. It is
# the right tool for review (you can see exactly which landmark is missing) and the wrong input
# for a motion-transfer model. Kling 3.0 Motion Control takes a *reference video of a person* and
# extracts the motion itself -- so the driving clip has to contain something its pose estimator
# recognises as a human body. Dots and hairlines on black almost certainly do not.
#
# So: same landmarks, same geometry, drawn as a filled figure with limb volume, a head, and
# hands that read as hands. No landmark is invented -- a missing hand block still draws nothing.
# Everything below is a rendering choice; the motion is untouched.
HB_BG      = (208, 208, 206)      # light neutral studio grey (matches the character-still prompt)
HB_CLOTH   = (118, 116, 114)      # mid-grey long-sleeved top
HB_CLOTH_E = (84, 82, 80)         # its darker edge, for silhouette definition
HB_SKIN    = (152, 178, 208)      # BGR -> a light warm tan
HB_SKIN_E  = (110, 136, 168)

# Limb thicknesses as a fraction of the on-screen shoulder width, so they track the global fit.
HB_UPPER, HB_FORE, HB_NECK, HB_FINGER, HB_HEAD = 0.17, 0.14, 0.20, 0.075, 0.30


def _pt(pts: np.ndarray, i: int):
    return ps._project(pts[i])


def _shoulder_px(pts: np.ndarray) -> float:
    """On-screen shoulder width. Every thickness derives from this, so the figure keeps its
    proportions whatever `fit_all` chose for SCALE."""
    a, b = _pt(pts, 11), _pt(pts, 12)
    if a is None or b is None:
        return ps.SCALE                                  # 1 shoulder-width by definition
    return math.hypot(a[0] - b[0], a[1] - b[1]) or ps.SCALE


def _capsule(img, a, b, w: float, fill, edge) -> None:
    """A limb: dark stroke, then fill, with round caps at both ends.

    Drawn as line+circles rather than a thick cv2.line alone because OpenCV's thick lines have
    square ends -- which read as blocky stumps at the elbow and wrist, exactly the joints a pose
    estimator keys on."""
    if a is None or b is None:
        return
    we, wf = max(2, int(round(w * 1.30))), max(1, int(round(w)))
    for width, col in ((we, edge), (wf, fill)):
        cv2.line(img, a, b, col, width, cv2.LINE_AA)
        for p in (a, b):
            cv2.circle(img, p, width // 2, col, -1, cv2.LINE_AA)


def _fill_scaled(img, quad, sx: float, sy: float, col) -> None:
    """Fill a polygon scaled about its own centroid (used to get the torso's edge pass)."""
    c = np.mean(np.asarray(quad, dtype=np.float64), axis=0)
    poly = np.array([[c[0] + (x - c[0]) * sx, c[1] + (y - c[1]) * sy] for x, y in quad],
                    dtype=np.int32)
    cv2.fillPoly(img, [poly], col, cv2.LINE_AA)


def _torso(img, pts: np.ndarray, sw: float) -> None:
    """Shoulders down to the hips, then CONTINUED off the bottom of the frame.

    Stopping the fill at the hip landmarks left a floating trapezoid with a hard flat base -- a
    body that simply ends. Real waist-up framing has the torso leave the frame, so the quad is
    extended well past the canvas and clipped by it."""
    sl, sr, hr, hl = _pt(pts, 11), _pt(pts, 12), _pt(pts, 24), _pt(pts, 23)
    if any(v is None for v in (sl, sr, hr, hl)):
        return
    drop = ps.CANVAS_H                                   # far enough to always clear the canvas
    quad = [sl, sr, (hr[0], hr[1] + drop), (hl[0], hl[1] + drop)]
    # Widen about the body's own midline, HORIZONTALLY ONLY. Scaling this quad about its centroid
    # (as _fill_scaled does) is wrong once it extends off-canvas: the taller edge pass rose higher
    # than the fill, leaving a dark band floating above the shoulders, and the vertical stretch
    # splayed the hips wider than the shoulders. Keeping y fixed also preserves the measured
    # shoulder-to-hip taper instead of inventing one.
    midx = (sl[0] + sr[0]) / 2.0
    for k, col in ((1.13, HB_CLOTH_E), (1.02, HB_CLOTH)):
        poly = np.array([[midx + (x - midx) * k, y] for x, y in quad], dtype=np.int32)
        cv2.fillPoly(img, [poly], col, cv2.LINE_AA)
    # Round off the shoulder caps so the arms join the body instead of meeting a sharp corner.
    for p in (sl, sr):
        r = max(3, int(round(sw * HB_UPPER * 0.62)))
        cv2.circle(img, p, int(r * 1.28), HB_CLOTH_E, -1, cv2.LINE_AA)
        cv2.circle(img, p, r, HB_CLOTH, -1, cv2.LINE_AA)


def _head(img, pts: np.ndarray, sw: float) -> None:
    ears = [_pt(pts, 7), _pt(pts, 8)]
    if all(v is not None for v in ears):
        ctr = ((ears[0][0] + ears[1][0]) // 2, (ears[0][1] + ears[1][1]) // 2)
    else:
        ctr = _pt(pts, 0)                                # fall back to the nose
    if ctr is None:
        return
    r = max(5, int(round(sw * HB_HEAD)))
    # The outline pass is wider here than elsewhere on purpose: signs made at the face put the
    # hand directly over the head, and with a thin edge the two same-toned shapes merged into one
    # blob. A heavier rim keeps the hand readable as a separate object in front of the face.
    cv2.ellipse(img, ctr, (int(r * 0.86), int(r * 1.04)), 0, 0, 360, HB_SKIN_E, -1, cv2.LINE_AA)
    cv2.ellipse(img, ctr, (int(r * 0.73), int(r * 0.91)), 0, 0, 360, HB_SKIN, -1, cv2.LINE_AA)
    # Brow + eyes: two dark marks. Not decoration -- a face-detector finding nothing on the head
    # is one more reason for a video model to read the figure as an object rather than a person.
    ey = ctr[1] - int(r * 0.10)
    for dx in (-int(r * 0.30), int(r * 0.30)):
        cv2.circle(img, (ctr[0] + dx, ey), max(2, int(r * 0.10)), HB_SKIN_E, -1, cv2.LINE_AA)


def _fist(img, wrist, sw: float) -> None:
    """A relaxed hand at a TRACKED pose wrist whose 21-point block is missing.

    APPEARANCE ONLY, and only ever a featureless blob -- never a handshape. The distinction that
    matters: the wrist here is measured (pose landmark 15/16), it is the finger detail that is
    absent. Leaving it bare rendered the signer with an amputated arm, which is both wrong about
    the person and a strong cue to a video model that this is not a human. It carries no
    linguistic content: a one-handed sign's passive hand means nothing, and for a two-handed sign
    the tier already records that the data is degraded (see AVATAR_LIMITS.md)."""
    if wrist is None:
        return
    r = max(3, int(round(sw * 0.115)))
    cv2.circle(img, wrist, int(r * 1.26), HB_SKIN_E, -1, cv2.LINE_AA)
    cv2.circle(img, wrist, r, HB_SKIN, -1, cv2.LINE_AA)


def _hand(img, pts: np.ndarray, base: int, sw: float, wrist) -> bool:
    """Draw the measured hand. Returns False if its block is absent (caller draws a fist)."""
    P = [_pt(pts, base + i) for i in range(ps.HAND_N)]
    if P[0] is None:
        return False
    palm = [P[0], P[5], P[9], P[13], P[17]]
    if all(v is not None for v in palm):
        _fill_scaled(img, palm, 1.30, 1.30, HB_SKIN_E)
        _fill_scaled(img, palm, 1.14, 1.14, HB_SKIN)
    fw = max(2.0, sw * HB_FINGER)
    for a, b in ps.HAND_EDGES:
        _capsule(img, P[a], P[b], fw, HB_SKIN, HB_SKIN_E)
    for tip in (4, 8, 12, 16, 20):                       # fingertip pads, drawn last
        if P[tip] is not None:
            cv2.circle(img, P[tip], max(2, int(fw * 0.60)), HB_SKIN, -1, cv2.LINE_AA)
    return True


def render_human(pts: np.ndarray) -> np.ndarray:
    """(75,3) -> a BGR frame of a filled figure. Painter order puts the hands on top of
    everything, because an arm crossing in front of the signing hand would hide the word."""
    img = np.full((ps.CANVAS_H, ps.CANVAS_W, 3), HB_BG, dtype=np.uint8)
    sw = _shoulder_px(pts)

    _torso(img, pts, sw)

    sh = [_pt(pts, 11), _pt(pts, 12)]
    if all(v is not None for v in sh):                   # neck: shoulder midpoint -> head
        mid = ((sh[0][0] + sh[1][0]) // 2, (sh[0][1] + sh[1][1]) // 2)
        _capsule(img, mid, _pt(pts, 0), sw * HB_NECK, HB_SKIN, HB_SKIN_E)

    arms = ((11, 13, 15, ps.LHAND_BASE), (12, 14, 16, ps.RHAND_BASE))
    for shoulder, elbow, wrist, hbase in arms:
        _capsule(img, _pt(pts, shoulder), _pt(pts, elbow), sw * HB_UPPER, HB_CLOTH, HB_CLOTH_E)
        _capsule(img, _pt(pts, elbow), _pt(pts, wrist), sw * HB_FORE, HB_CLOTH, HB_CLOTH_E)
        # bridge the pose wrist to the hand block's own wrist -- they are separate estimates and
        # a few px apart, which without this shows as a gap between sleeve and hand.
        _capsule(img, _pt(pts, wrist), _pt(pts, hbase), sw * HB_FORE * 0.85, HB_SKIN, HB_SKIN_E)

    _head(img, pts, sw)
    for _s, _e, wrist, hbase in arms:                    # hands last: never occluded by an arm
        if not _hand(img, pts, hbase, sw, _pt(pts, wrist)):
            _fist(img, _pt(pts, wrist), sw)
    return img


def fit_all(clips: list[np.ndarray], margin: int = 40) -> tuple[float, float, float, float]:
    """One projection fitted across EVERY clip, so nothing clips and scale stays constant.

    `preview_signs.SCALE` is a fixed 210 px per shoulder-width, deliberately, so that words are
    size-comparable in the review tool. For a driving video that is wrong: measured on `thankyou`,
    11.5% of projected points fell OUTSIDE the canvas (y reached 1063 on an 820 px canvas), which
    clips hands — and a crop that clips a hand destroys the sign.

    Fitted GLOBALLY rather than per word on purpose. Per-word autofit would make the figure grow
    and shrink between words, and a generative model would render that as a person changing size
    mid-sentence. One scale for the whole set keeps the subject stable.
    """
    xs, ys = [], []
    for a in clips:
        f = a[np.isfinite(a[:, :, :2]).all(-1)]
        if f.size:
            xs.append(f[:, 0]); ys.append(f[:, 1])
    if not xs:
        return ps.CX, ps.CY, ps.SCALE, 0.0
    x = np.concatenate(xs); y = np.concatenate(ys)
    x0, x1, y0, y1 = float(x.min()), float(x.max()), float(y.min()), float(y.max())
    w, h = ps.CANVAS_W - 2 * margin, ps.CANVAS_H - 2 * margin
    scale = min(w / max(x1 - x0, 1e-6), h / max(y1 - y0, 1e-6))
    cx = ps.CANVAS_W / 2.0 - (x0 + x1) / 2.0 * scale
    cy = ps.CANVAS_H / 2.0 - (y0 + y1) / 2.0 * scale
    return cx, cy, scale, scale / ps.SCALE


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"))
    ap.add_argument("--out", default=str(HERE / "driving_video"))
    ap.add_argument("--words", nargs="*", help="specific words (default: every word found)")
    ap.add_argument("--tier", choices=["A", "B", "C"], help="only export this tier")
    ap.add_argument("--raw", action="store_true",
                    help="disable hold-fill so genuine dropouts flicker (debug only)")
    ap.add_argument("--flat", action="store_true", help="all files in one folder, no tier subdirs")
    ap.add_argument("--no-fit", action="store_true",
                    help="keep preview_signs' fixed 210px scale (clips ~11%% of points)")
    ap.add_argument("--style", choices=["human", "skeleton"], default="human",
                    help="human = filled figure a motion-transfer model can read (default); "
                         "skeleton = the debug overlay, for review only")
    ap.add_argument("--margin", type=int, default=None,
                    help="fit margin in px (default: 76 for human, 40 for skeleton)")
    ap.add_argument("--legs", action="store_true",
                    help="keep the orphan leg dots (they shrink the hands; see LEGS)")
    args = ap.parse_args()
    human = args.style == "human"
    # A filled figure extends past the landmark bbox by roughly half a limb thickness plus the
    # head radius (~0.30 shoulder-widths). The skeleton's 40px margin clips both.
    if args.margin is None:
        args.margin = 76 if human else 40

    wdir = Path(args.handoff) / "words"
    files = sorted(wdir.glob("*.json"))
    if not files:
        raise SystemExit(f"[err] no word JSONs under {wdir}")
    if args.words:
        want = {w.lower() for w in args.words}
        files = [p for p in files if p.stem.lower() in want]
        missing = want - {p.stem.lower() for p in files}
        if missing:
            print(f"[warn] not in the export: {sorted(missing)}")
    out_root = Path(args.out)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    manifest, skipped, total_frames = [], [], 0

    # ── pass 1: load everything, so the projection can be fitted before anything renders ──
    loaded = []
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        word = d["glosses"][0]
        syn = d["segments"][0]["synthesis"]
        cov = float(syn.get("dominantCoverage") or 0.0)
        t = tier_of(cov)
        if args.tier and t != args.tier:
            continue
        arr, _segs, _g, fps = ps.load_json_clip(p)
        arr = ps.hold_fill(arr, args.raw)
        if arr.shape[0] == 0:
            skipped.append(word)
            continue
        loaded.append((word, syn, cov, t, upper_body(arr) if not args.legs else arr, fps))

    if not loaded:
        raise SystemExit("[err] nothing to export")

    if args.no_fit:
        print(f"[cfg] fixed scale {ps.SCALE:.0f}px — expect clipping")
    else:
        cx, cy, scale, ratio = fit_all([a for *_r, a, _f in loaded], args.margin)
        ps.CX, ps.CY, ps.SCALE = cx, cy, scale
        print(f"[cfg] fitted across {len(loaded)} clips: scale {scale:.1f}px "
              f"({ratio:.2f}x the default), centre ({cx:.0f},{cy:.0f})")
        off = 0; tot = 0
        for *_r, a, _f in loaded:
            for fr in range(a.shape[0]):
                for i in range(a.shape[1]):
                    q = ps._project(a[fr, i])
                    if q is None:
                        continue
                    tot += 1
                    if not (0 <= q[0] < ps.CANVAS_W and 0 <= q[1] < ps.CANVAS_H):
                        off += 1
        print(f"[cfg] points outside canvas after fit: {off}/{tot} ({off / max(tot,1) * 100:.2f}%)")

    # ── pass 2: render ────────────────────────────────────────────────────────────────────
    for word, syn, cov, t, arr, fps in loaded:
        sub = out_root if args.flat else out_root / f"tier{t}"
        sub.mkdir(parents=True, exist_ok=True)
        dest = sub / f"{word}.mp4"
        vw = cv2.VideoWriter(str(dest), fourcc, float(max(1, fps)),
                             (ps.CANVAS_W, ps.CANVAS_H))
        if not vw.isOpened():
            raise SystemExit(f"[err] could not open a writer for {dest}")
        for f in range(arr.shape[0]):
            # hud=None on the skeleton path -> no baked-in word label either way
            vw.write(render_human(arr[f]) if human else ps.render_frame(arr[f], None))
        vw.release()
        total_frames += arr.shape[0]

        q = syn.get("quality") or {}
        manifest.append({
            "word": word, "tier": t, "class": syn.get("class"),
            "frames": arr.shape[0], "fps": fps,
            "seconds": round(arr.shape[0] / max(fps, 1), 2),
            "dominantCoverage": cov,
            "longestGapFrames": q.get("longestGapFrames"),
            "passiveHandshape": (syn.get("passiveHandshape") or {}).get("shape"),
            "file": str(dest.relative_to(out_root)).replace("\\", "/"),
        })

    if not manifest:
        raise SystemExit("[err] nothing exported")
    out_root.mkdir(parents=True, exist_ok=True)
    manifest.sort(key=lambda r: (r["tier"], -r["dominantCoverage"]))
    (out_root / "manifest.json").write_text(
        json.dumps({"n": len(manifest),
                    "canvas": [ps.CANVAS_W, ps.CANVAS_H],
                    "style": args.style,
                    "hold_filled": not args.raw,
                    "purpose": ("driving input for a pose-conditioned video model; the skeleton "
                                "carries the real handshape and movement, the model supplies "
                                "appearance only"),
                    "words": manifest}, indent=1), encoding="utf-8")

    by = {}
    for r in manifest:
        by.setdefault(r["tier"], []).append(r)
    mb = sum(f.stat().st_size for f in out_root.rglob("*.mp4")) / 2 ** 20
    print(f"[ok] {len(manifest)} videos, {total_frames} frames, {mb:.1f} MB -> {out_root}")
    for t in sorted(by):
        r = by[t]
        secs = sum(x["seconds"] for x in r)
        print(f"   tier {t}: {len(r):>3} words   {secs:6.1f}s total   "
              f"median coverage {sorted(x['dominantCoverage'] for x in r)[len(r)//2]:.2f}")
    if skipped:
        print(f"[warn] empty clips skipped: {skipped}")
    print(f"[ok] manifest -> {out_root / 'manifest.json'}")
    print("\nSpend credits tier A first. Tier C has the dominant hand missing over half the "
          "time — a generated video of those looks confident and shows a sign that is not there.")


if __name__ == "__main__":
    main()
