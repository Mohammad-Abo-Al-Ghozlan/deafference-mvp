#!/usr/bin/env python3
r"""Glosses -> ONE continuous rig animation. The piece between the dictionary and a sentence.

WHAT WAS MISSING. `gloss_to_motion.py` already stitches a sentence, but it stitches LANDMARKS
-- it is the seam before retargeting, and it hands the animation side a (T,75,3) stream. The
avatar does not play landmarks; it plays the quaternion tracks in baked_signs.json. So there
was no path from "hello mom" to something the rig can perform, and 250 correctly retargeted
words with nothing to sequence them is a dictionary, not a speech-to-sign system.

Stitching has to happen at THIS layer rather than the landmark one. Concatenating landmarks
first and retargeting afterwards would run the depth solve across the join, where two clips
from two different takes meet: that solve reads a 2D shortfall against a rigid bone as
foreshortening (see retarget.solve_depth), and at a join the shortfall is an artefact of two
poses being different, not of a limb turning. It would invent rotation exactly where there is
no motion to recover.

THE THREE RULES, and each one is about a quantity the bake carries for this purpose:

  DROP THE INTERIOR HOLDS. retime() pads every clip with hold_in leading and hold_out trailing
  frames so a word shown alone starts and ends at rest. Concatenated, two of those meet at
  every join and the avatar stops dead between words -- 16 frames of stillness, half a second,
  which in ASL is not a pause, it is a boundary marker that changes the reading. So only the
  first sign keeps its lead-in and only the last its tail. frames[hold_in : hold_in+stroke] is
  the sign itself, which is what that field was added for.

  BLEND BY THE SHORTER CLIP. Reusing gloss_to_motion.blend_len's rule rather than inventing a
  second one: a fixed 8-frame transition is 12% of a 64-frame clip and 64% of `tiger`'s nine,
  and at that point the sign is a brief event inside a long morph. 15% of the shorter side,
  floor 1.

  PUT THE PASSIVE ARM BACK DOWN. A bone absent from a frame holds its rest pose, and there are
  exactly two bone sets in the bake -- 20 bones one-handed, 38 two-handed -- so every crossing
  between a two-handed and a one-handed sign is an 18-bone discontinuity. RAIN -> BLUE would
  drop the whole left arm in a single frame. Blending towards the rest quaternions in `_rest`
  lowers it over the transition instead.

Interpolation is SLERP per bone, eased, never a linear blend of quaternion components: a lerp
of two rotations more than a few degrees apart shortens the arc and the limb dips through the
body on the way. Signs are 30-180 degrees apart at a join.

WHAT THIS DOES NOT DO, so nobody reads it as more than it is. There is no co-articulation
model here: a real signer's handshape for word N is already forming during word N-1, and the
transition's own shape carries information (movement epenthesis). This is a smooth eased path
between two citation forms, which is the honest floor. It also does not fingerspell a word
outside the 250, does not inflect, and does not mark non-manuals -- the corpus has no face
landmarks at all, so no player built on it can.

    python avatar/sequence_signs.py hello mom hungry
    python avatar/sequence_signs.py --text "I am thirsty please"
    python avatar/sequence_signs.py --text "hello mom" --out utterance.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BAKE = HERE / "baked_signs.json"

# Same cap as the landmark stitcher's contract default (§10), scaled the same way.
DEFAULT_TRANSITION = 8


def load_bake(path=BAKE):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["signs"], d.get("_rest", {})


def smoothstep(t):
    """Eased weight in [0,1]. Co-articulation reads as motion; a linear ramp reads as a wipe."""
    return t * t * (3.0 - 2.0 * t)


def slerp(q0, q1, t):
    """Shortest-arc quaternion interpolation, sign-corrected.

    The sign correction is not cosmetic: q and -q are the same rotation, so without it a join
    can take the long way round -- up to 360 degrees of travel for a rotation of nearly zero.
    """
    a, b = np.asarray(q0, dtype=float), np.asarray(q1, dtype=float)
    d = float(np.dot(a, b))
    if d < 0.0:
        b, d = -b, -d
    if d > 0.9995:                                  # nearly equal: lerp is exact enough
        out = a + t * (b - a)
    else:
        th = np.arccos(np.clip(d, -1.0, 1.0))
        s = np.sin(th)
        out = (np.sin((1.0 - t) * th) / s) * a + (np.sin(t * th) / s) * b
    return out / (np.linalg.norm(out) + 1e-12)


# How far a bone may turn in one frame of a transition, in degrees at 30 fps. The clips
# themselves are filtered so that 5.6% of frames exceed 30 degrees, and a join has no reason
# to be worse than the motion it joins. 12 leaves headroom under that.
MAX_STEP = 12.0
# ... but a transition may not outrun the sign on either side of it. retime() stretches every
# stroke to at least MIN_STROKE = 18 frames, so this is at most about two-thirds of the
# shortest sign in the set.
MAX_BLEND = 15


def blend_len(cap, a, b, rest):
    """How many frames to spend getting from pose `a` to pose `b`.

    gloss_to_motion.blend_len sets this as a fraction of the shorter CLIP, which is the right
    rule there -- it is guarding against a transition that swallows a short sign. It is not
    enough here, because the thing that makes a join look broken is not its share of the clip,
    it is how far the skeleton moves per frame. Measured on the stitched track, 15% of the
    shorter clip gave RAIN -> BLUE three frames to cross 171 degrees of shoulder rotation:
    57 degrees in a single frame, worse than anything inside a sign.

    So the length comes from the distance: enough frames that no bone turns more than
    MAX_STEP per frame, bounded by MAX_BLEND so a long reach does not become a pause. The
    clip-share guard is kept as the other bound, since both failures are real.
    """
    if cap <= 0:
        return 0
    far = 0.0
    for nm in set(a) | set(b):
        q0, q1 = a.get(nm) or rest.get(nm), b.get(nm) or rest.get(nm)
        if q0 is None or q1 is None:
            continue
        far = max(far, np.degrees(2 * np.arccos(
            min(1.0, abs(float(np.dot(np.array(q0), np.array(q1))))))))
    return int(np.clip(round(far / MAX_STEP), 1, min(MAX_BLEND, max(cap, 1))))


def stroke_of(sign):
    """The sign without its rest padding: frames[hold_in : hold_in+stroke]."""
    fr = sign["frames"]
    hi = int(sign.get("hold_in", 0) or 0)
    st = int(sign.get("stroke", len(fr) - hi) or len(fr) - hi)
    return fr[hi:hi + st] or fr


def transition(a, b, n, rest):
    """n eased frames from pose `a` to pose `b`, over the UNION of their bones.

    A bone in only one of the two endpoints is interpolated against its rest quaternion, which
    is what "absent" means in this file. That is the whole passive arm on every crossing
    between a two-handed and a one-handed sign.
    """
    out = []
    names = set(a) | set(b)
    for k in range(1, n + 1):
        w = smoothstep(k / (n + 1.0))
        f = {}
        for nm in names:
            q0 = a.get(nm) or rest.get(nm)
            q1 = b.get(nm) or rest.get(nm)
            if q0 is None or q1 is None:            # no rest known: hold what we have
                q = a.get(nm) or b.get(nm)
                if q is not None:
                    f[nm] = list(q)
                continue
            f[nm] = [round(float(x), 4) for x in slerp(q0, q1, w)]
        out.append(f)
    return out


def sequence(glosses, signs, rest, cap=DEFAULT_TRANSITION):
    """Returns (frames, segments, missing). One track, one segment record per sign played."""
    frames, segments, missing = [], [], []
    picked = [g for g in glosses if g in signs]
    missing = [g for g in glosses if g not in signs]
    for i, g in enumerate(picked):
        s = signs[g]
        body = stroke_of(s)
        if i == 0:
            hi = int(s.get("hold_in", 0) or 0)
            frames.extend(s["frames"][:hi])         # only the first sign keeps its lead-in
        else:
            n = blend_len(cap, frames[-1], body[0], rest)
            frames.extend(transition(frames[-1], body[0], n, rest))
        start = len(frames)
        frames.extend(body)
        segments.append({"gloss": g, "start": start, "end": len(frames),
                         "shape": s.get("shape"), "err": s.get("err"),
                         "synth": s.get("synth"), "hands": s.get("hands")})
        if i == len(picked) - 1:
            ho = int(s.get("hold_out", 0) or 0)
            if ho:
                frames.extend(s["frames"][-ho:])    # ... and only the last one its tail
    return frames, segments, missing


def to_glosses(text):
    """Sentence -> glosses, via the demo's deterministic offline mapper.

    The OFFLINE path on purpose: it needs no key and no network, so a sentence typed in front
    of an audience cannot fail on someone else's service. demo_speech_to_sign.py has an online
    Gemini path for proper ASL reordering; this is not the place to choose between them.
    """
    sys.path.insert(0, str(REPO))
    from demo_speech_to_sign import load_vocab, to_glosses_offline   # noqa: E402
    vocab = load_vocab(REPO / "vocab_250.json")
    return to_glosses_offline(text, set(vocab))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("glosses", nargs="*", help="words to sign, in signing order")
    ap.add_argument("--text", help="an English sentence; mapped to glosses offline")
    ap.add_argument("--transition", type=int, default=MAX_BLEND,
                    help="cap on blend frames between signs; 0 disables blending")
    ap.add_argument("--out", type=Path, help="write the utterance JSON here")
    a = ap.parse_args()

    signs, rest = load_bake()
    if not rest:
        print("[warn] this bake has no _rest block, so the passive arm cannot be lowered "
              "smoothly across a one-handed/two-handed join. Re-run retarget.py --all.")
    dropped = []
    gl = list(a.glosses)
    if a.text:
        gl, dropped = to_glosses(a.text)
    if not gl:
        raise SystemExit("[err] nothing to sign. Give words, or --text \"a sentence\".")

    frames, segments, missing = sequence(gl, signs, rest, a.transition)
    if not frames:
        raise SystemExit(f"[err] none of {gl} is in the bake.")
    fps = float(next(iter(signs.values())).get("fps", 30))
    print(f"glosses  {' '.join(s['gloss'] for s in segments)}")
    if dropped:
        print(f"dropped  {' '.join(dropped)}   (not in the 250-word vocabulary)")
    if missing:
        print(f"missing  {' '.join(missing)}   (in the vocabulary, not in the bake)")
    print(f"\n{'sign':<14}{'frames':>12}{'handshape':>11}{'wrist':>8}  passive hand")
    for s in segments:
        span = f"{s['start']}-{s['end']}"
        shape = "   n/a" if s["shape"] is None else f"{s['shape']:9.1f}%"
        wrist = "  n/a" if s["err"] is None else f"{s['err']:6.1f}%"
        print(f"{s['gloss']:<14}{span:>12}{shape:>10}{wrist:>7}  {s['synth'] or 'recorded'}")
    total = len(frames)
    print(f"\n{total} frames = {total / fps:.2f}s at {fps:.0f} fps "
          f"({total / (fps / 2):.2f}s at half speed), "
          f"{sum(s['end'] - s['start'] for s in segments)} of them sign and "
          f"{total - sum(s['end'] - s['start'] for s in segments)} transition")

    if a.out:
        a.out.write_text(json.dumps(
            {"_note": ("One utterance, baked by avatar/sequence_signs.py. Same convention as "
                       "baked_signs.json: LOCAL quaternions, xyzw, rigger's bone names, a bone "
                       "absent from a frame holds its rest pose. `segments` indexes which "
                       "frames are which sign; the gaps between them are transitions."),
             "fps": fps, "glosses": [s["gloss"] for s in segments],
             "dropped": dropped, "missing": missing,
             "segments": segments, "frames": frames},
            separators=(",", ":")), encoding="utf-8")
        print(f"[ok] {a.out}  ({a.out.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
