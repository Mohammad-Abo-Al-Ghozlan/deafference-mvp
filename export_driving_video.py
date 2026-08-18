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
    ap.add_argument("--margin", type=int, default=40, help="fit margin in px")
    ap.add_argument("--legs", action="store_true",
                    help="keep the orphan leg dots (they shrink the hands; see LEGS)")
    args = ap.parse_args()

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
            vw.write(ps.render_frame(arr[f], None))       # hud=None -> no baked text
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
