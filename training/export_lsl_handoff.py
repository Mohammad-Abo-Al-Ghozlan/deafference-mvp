#!/usr/bin/env python3
"""Pick the best take of each LSL word and write it in the renderer's handoff format.

Turns the recognition-side .npz into the animation side's input. These are different jobs
and they want different takes:

    RECOGNITION wants MANY takes per word, and variety between them IS the signal.
    ANIMATION wants ONE take per word, and it should be the cleanest one that exists.

So this is not the exemplar selector from build_sign_clips.py with a different flag. That one
maximises dominant-hand coverage under a motion floor, because a still take games coverage.
Here stillness is not a threat -- we are not training on it -- and what matters is whether
the renderer can see the hands for the whole sign.

WHY LSL IS EASIER TO ANIMATE THAN ASL WAS
-----------------------------------------
Every synthesis path in retarget.py exists because GISLR never recorded the passive hand:
the left hand block is NaN on 100.00% of frames in all 250 ASL clips, so a two-handed sign
had to have its second hand invented -- mirrored for 2s, placed from an authored lexicon for
2a -- and none of that was ever reviewed by a Deaf signer.

This corpus is video of a person. Measured on lesson 1 after trimming: left hand present on
30.4% of frames, both hands on 16.7%, and 26 of 108 clips carry both hands on more than 10%
of their frames. So the passive hand is REAL here, and retarget.py already does the right
thing with it without being told: it only mirrors when the passive block is empty
(`np.isnan(...).all()`), and `unmarked_base` returns placed=False for a word no lexicon
knows. Both tests fail for LSL, so the recorded hands are used and nothing is synthesized.
That is the single biggest source of doubt in the ASL avatar, gone.

    python training/export_lsl_handoff.py --npz lsl_lesson1.npz --out animation_handoff_lsl
    SIGN_WORDS_DIR=animation_handoff_lsl/words python avatar/retarget.py --bake --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "training"))

from train_lsl import load, trim_to_sign                            # noqa: E402

L_WR, R_WR, L_SH, R_SH = 15, 16, 11, 12
LH0, RH0 = 33, 54


def score(x: np.ndarray) -> dict:
    """How good is this take AS AN ANIMATION SOURCE?

    Coverage of the hand that does the signing, over the trimmed span, is the whole story:
    a frame with no hand is a frame the renderer has to interpolate through, and the avatar
    track is only as good as the frames behind it. Length enters only as a floor -- a
    12-frame take of a sign is not a better take for being densely tracked.
    """
    n = len(x)
    if n < 8:
        return {"ok": False, "why": f"only {n} frames"}
    lh = ~np.isnan(x[:, LH0, 0])
    rh = ~np.isnan(x[:, RH0, 0])
    # Which hand signs: the one that TRAVELS, not the one that is tracked best. The tracker
    # keeps the hand that holds still, so picking by coverage would pick the resting hand --
    # that inversion shipped 249 of 250 ASL exemplars carrying the wrong hand block.
    trav = {}
    for s, k in (("l", L_WR), ("r", R_WR)):
        v = np.linalg.norm(np.diff(x[:, k, :2], axis=0), axis=-1)
        trav[s] = float(np.nansum(v))
    dom = "r" if trav["r"] >= trav["l"] else "l"
    dom_cov = float((rh if dom == "r" else lh).mean())
    pas_cov = float((lh if dom == "r" else rh).mean())
    return {"ok": True, "frames": n, "dom": dom, "dom_cov": dom_cov, "pas_cov": pas_cov,
            "both": float((lh & rh).mean()), "travel": trav[dom],
            # Two-handed if the passive hand is genuinely there for a meaningful stretch.
            # Deliberately NOT "the passive wrist moved": a 2a base is static by definition,
            # so travel cannot separate a held base from a dropped arm -- that is exactly the
            # measurement build_sign_clips.py's --require-passive-up note says fails.
            "two_handed": bool((lh & rh).mean() > 0.10)}


def to_handoff(x: np.ndarray, gloss: str, fps: float, s: dict) -> dict:
    """The renderer's schema. NaN -> null, never [0,0,0].

    The contract is explicit that the origin is mid-sternum, so a zeroed landmark draws the
    hand inside the chest rather than marking it absent. json.dumps would happily emit the
    literal NaN, which is not JSON and which every strict parser rejects, so the conversion
    is done here and not left to the encoder.
    """
    frames = [[[None if not np.isfinite(v) else round(float(v), 5) for v in pt] for pt in fr]
              for fr in x]
    return {
        "schema": "sign-animation/v1",
        "fps": fps,
        "coord_space": "shoulder-centered",
        "note": ("y is DOWN (image space) — the renderer flips y. x is RAW CAMERA "
                 "orientation. A missing point/hand is null, never [0,0,0] — the origin is "
                 "mid-sternum. Lebanese Sign Language, Arabic gloss. BOTH HANDS ARE REAL "
                 "here: unlike the ASL set, nothing on the passive side is synthesized."),
        "glosses": [gloss],
        "language": "LSL",
        "segments": [{"synthesis": {"twoHanded": s["two_handed"],
                                    "dominantHand": s["dom"].upper()}}],
        "nativeFrames": len(x),
        "nativeFps": fps,
        "frames": frames,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=REPO / "animation_handoff_lsl")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--min-cov", type=float, default=0.30,
                    help="reject a word whose BEST take still loses the signing hand more "
                         "than this often; it would be mostly interpolation")
    args = ap.parse_args()

    X, y, date, labels = load(args.npz, trim=True)
    words = args.out / "words"
    words.mkdir(parents=True, exist_ok=True)

    by = {}
    for i, lab in enumerate(y):
        by.setdefault(labels[lab], []).append(i)

    kept, rejected, rows = 0, [], []
    for gloss, ids in sorted(by.items()):
        cand = [(i, score(X[i])) for i in ids]
        cand = [(i, s) for i, s in cand if s["ok"]]
        if not cand:
            rejected.append((gloss, "no usable take"))
            continue
        i, s = max(cand, key=lambda t: (t[1]["dom_cov"], t[1]["frames"]))
        if s["dom_cov"] < args.min_cov:
            rejected.append((gloss, f"best take only {s['dom_cov']*100:.0f}% hand coverage"))
            continue
        (words / f"{gloss}.json").write_text(
            json.dumps(to_handoff(X[i], gloss, args.fps, s), ensure_ascii=False,
                       separators=(",", ":")), encoding="utf-8")
        kept += 1
        rows.append((gloss, len(ids), s["frames"], s["dom_cov"], s["pas_cov"],
                     s["both"], s["dom"], s["two_handed"], date[i]))

    print(f"{'gloss':<16s} {'takes':>5s} {'frames':>6s} {'dom hand':>9s} {'passive':>8s} "
          f"{'both':>6s} {'dom':>4s} {'2H':>3s}  date")
    print("-" * 72)
    for g, nt, nf, dc, pc, bo, dm, th, dt in rows:
        print(f"{g:<16s} {nt:5d} {nf:6d} {dc*100:8.0f}% {pc*100:7.0f}% {bo*100:5.0f}% "
              f"{dm.upper():>4s} {'yes' if th else ' no':>3s}  {dt}")
    arr = np.array([[r[3], r[5]] for r in rows]) if rows else np.zeros((0, 2))
    print(f"\n[ok] {kept} words -> {words}")
    if len(arr):
        print(f"     signing-hand coverage: median {np.median(arr[:,0])*100:.0f}%  "
              f"min {arr[:,0].min()*100:.0f}%")
        print(f"     two-handed signs: {sum(1 for r in rows if r[7])} of {kept} "
              f"(passive hand RECORDED, not synthesized)")
    for g, why in rejected:
        print(f"     rejected {g}: {why}")


if __name__ == "__main__":
    main()
