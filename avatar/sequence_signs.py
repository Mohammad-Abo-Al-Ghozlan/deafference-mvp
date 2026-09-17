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

IT ALSO PUTS THE GRAMMAR ON THE FACE. A yes/no question and the same words as a statement
differ in ASL only in the brows; negation is a headshake, not a sign. Those markers are
grammatical -- they scope over phrases and are decided by the sentence -- so they need no face
landmarks, and the rig already has eyebrow, eyelid, jaw and mouth bones. See apply_nonmanual().

WHAT THIS DOES NOT DO, so nobody reads it as more than it is. There is no co-articulation
model here: a real signer's handshape for word N is already forming during word N-1, and the
transition's own shape carries information (movement epenthesis). This is a smooth eased path
between two citation forms, which is the honest floor. It does not fingerspell a word outside
the 250 and it does not inflect. And the OTHER kind of non-manual -- the lexical mouth
morphemes TH, MM and CS that belong to individual signs -- stays missing, because that one
really does need face landmarks and the corpus has none.

    python avatar/sequence_signs.py hello mom hungry
    python avatar/sequence_signs.py --text "are you sick?"           # infers the brow raise
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

# NO SEPARATE DEFAULT HERE. There was one -- 8, the landmark stitcher's contract default (§10)
# -- left over from when the transition was a fixed frame COUNT. It stopped meaning anything
# when blend_len() started deriving the length from distance and `cap` became only an upper
# bound, and it then silently disagreed with itself: sequence()'s own default was 8 while the
# CLI passed MAX_BLEND and the viewer used MAX_BLEND, so the same sentence animated differently
# depending on which door you came in by -- `rain blue` was 89 frames from a script and 95 from
# the command line and the browser. Caught by running the viewer's JS and this file side by
# side on the same bake; see the parity check in the commit that added this note.
#
# One bound, named once, below: MAX_BLEND.


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
    """The sign without its rest padding: frames[hold_in : hold_in+stroke].

    COPIED, not sliced through. A slice of a list of dicts hands out the dictionary's own
    frame objects, so anything that writes a bone into an utterance -- apply_nonmanual does
    exactly that -- edits the baked sign itself and every later utterance inherits it. Caught
    by measuring a neutral sentence and finding a 12-degree brow raise on it, left over from
    the wh-question measured before.
    """
    fr = sign["frames"]
    hi = int(sign.get("hold_in", 0) or 0)
    st = int(sign.get("stroke", len(fr) - hi) or len(fr) - hi)
    return [dict(f) for f in (fr[hi:hi + st] or fr)]


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


def sequence(glosses, signs, rest, cap=MAX_BLEND):
    """Returns (frames, segments, missing). One track, one segment record per sign played."""
    frames, segments, missing = [], [], []
    picked = [g for g in glosses if g in signs]
    missing = [g for g in glosses if g not in signs]
    for i, g in enumerate(picked):
        s = signs[g]
        body = stroke_of(s)
        if i == 0:
            hi = int(s.get("hold_in", 0) or 0)
            frames.extend(dict(f) for f in s["frames"][:hi])   # first sign keeps its lead-in
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
                frames.extend(dict(f) for f in s["frames"][-ho:])  # ... and the last its tail
    return frames, segments, missing


# ── non-manual markers ───────────────────────────────────────────────────────────────────
# THE GRAMMAR IS ON THE FACE, and until now none of it was rendered. In ASL a yes/no question
# and the same words as a statement differ ONLY in the brows; negation is carried by a
# headshake, not by a sign; a topic is marked by a brow raise on the topicalised element. A
# sentence signed with a neutral face is not a neutral sentence, it is a different one.
#
# This does not need the face landmarks we do not have. Those four markers are GRAMMATICAL --
# they scope over phrases and are determined by the sentence, not by the word -- so they can
# be driven from the utterance itself, which is exactly what gloss_to_motion.NONMANUALS has
# specified since the contract was written. What needs landmarks is the other kind: the
# lexical mouth morphemes (TH, MM, CS) that belong to individual signs. Those stay missing,
# and no marker here pretends otherwise.
#
# AMPLITUDES ARE MEASURED OFF THE RIG, not chosen. Each face bone's skinned vertices were
# read out of the GLB with their weights, and the rotation below is the one that moves them
# by the stated distance:
#
#   bone         verts   mean dist from bone   20 deg about +z moves them
#   eyebrow_l       29          19.2 mm            3.60 mm DOWN  (so a raise is -z)
#   eyebrow_r       30          18.8 mm            3.60 mm down
#   jaw           1137          62.3 mm           16.15 mm down about +x
#
# so BROW_RAISE lifts the brow about 3.6 mm on average and BROW_FURROW lowers it about 2 mm.
# A Deaf reviewer should tune these; they are legible, not authoritative.
BROW_RAISE = -20.0        # degrees about +z on the left brow, mirrored on the right
BROW_FURROW = 12.0
HEAD_TILT = 7.0           # wh-questions come with a slight forward tilt
SHAKE_DEG = 8.0           # negation headshake amplitude, degrees of yaw
SHAKE_HZ = 1.6            # ... and its rate. Two to three shakes over a short clause.
NM_RAMP = 4               # frames to ease a marker in and out. Non-manuals do not snap on.

WH_WORDS = {"who", "what", "where", "when", "why", "how", "which", "whose"}
NEG_WORDS = {"not", "no", "dont", "don't", "cannot", "cant", "can't", "never", "nothing"}


def axis_quat(axis, deg):
    a = np.asarray(axis, dtype=float)
    a = a / (np.linalg.norm(a) + 1e-12)
    t = np.radians(deg) / 2.0
    s = np.sin(t)
    return np.array([a[0] * s, a[1] * s, a[2] * s, np.cos(t)])


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def infer_nonmanual(text, glosses):
    """Which marker this sentence carries, from the sentence -- never from the glosses alone.

    The glosses have already lost it: ASL drops the copula and the auxiliaries, so "are you
    sick?" and "you are sick" both come out as the single gloss `sick`. The question mark is
    the only surviving evidence and it is in the raw text, which is why this takes both.
    """
    t = (text or "").lower()
    words = set(t.replace("?", " ").split()) | set(glosses)
    if any(w in WH_WORDS for w in words):
        return "wh"
    if "?" in t:
        return "q"
    if any(w in NEG_WORDS for w in words):
        return "neg"
    return None


def apply_nonmanual(frames, segments, marker, fps, rest):
    """Write the marker's face and head motion across the span it scopes over.

    Scope is the marker's own, not one span for all of them: `q` and `wh` mark the whole
    clause, `top` marks only the topicalised element (the first sign), and `neg` runs from the
    negated predicate to the end. Getting the scope wrong changes the sentence as surely as
    omitting the marker -- a brow raise over the wrong half is a different question.
    """
    if not marker or not segments:
        return frames
    if marker == "top":
        lo, hi = segments[0]["start"], segments[0]["end"]
    elif marker == "neg":
        lo, hi = segments[0]["start"], segments[-1]["end"]
    else:
        lo, hi = segments[0]["start"], segments[-1]["end"]
    span = max(hi - lo, 1)
    for i in range(lo, min(hi, len(frames))):
        # eased in and out, so the marker arrives with the phrase rather than switching on
        k = i - lo
        w = min(1.0, min(k, span - 1 - k, NM_RAMP) / float(NM_RAMP))
        w = max(0.0, w * w * (3.0 - 2.0 * w))
        f = frames[i]
        if marker in ("q", "top", "wh"):
            deg = BROW_RAISE if marker in ("q", "top") else BROW_FURROW
            f["eyebrow_l"] = [round(float(x), 4) for x in axis_quat((0, 0, 1), deg * w)]
            f["eyebrow_r"] = [round(float(x), 4) for x in axis_quat((0, 0, -1), deg * w)]
        if marker in ("wh", "neg"):
            # COMPOSED onto the head rotation the sign already has, never replacing it. The
            # head is driven from the signer's own pose (head_frames in retarget.py), and
            # overwriting it would delete a real movement to add a synthetic one.
            base = np.array(f.get("head") or rest.get("head") or [0, 0, 0, 1], dtype=float)
            if marker == "wh":
                extra = axis_quat((1, 0, 0), HEAD_TILT * w)
            else:
                extra = axis_quat((0, 1, 0),
                                  SHAKE_DEG * w * np.sin(2 * np.pi * SHAKE_HZ * k / fps))
            f["head"] = [round(float(x), 4) for x in qmul(base, extra)]
    return frames


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
    ap.add_argument("--nonmanual", choices=("q", "wh", "neg", "top", "none"),
                    help="force the grammatical marker instead of inferring it from --text")
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
    marker = (None if a.nonmanual == "none"
              else a.nonmanual or infer_nonmanual(a.text, gl))
    frames = apply_nonmanual(frames, segments, marker, fps, rest)
    print(f"glosses  {' '.join(s['gloss'] for s in segments)}")
    said = {"q": "yes/no question: brow raise across the clause",
            "wh": "wh-question: brow furrow + head tilt",
            "neg": "negation: headshake across the clause",
            "top": "topic: brow raise on the first sign only"}
    print(f"marker   {marker or 'none'}   {said.get(marker, '')}")
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
