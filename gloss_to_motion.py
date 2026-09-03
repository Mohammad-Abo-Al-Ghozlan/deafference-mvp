#!/usr/bin/env python3
r"""
Phase 3 (speech -> sign): gloss list -> continuous landmark MOTION STREAM.

This is the pre-animation deliverable in SIGN_ANIMATION_CONTRACT.md: it turns the
canonical-clip dictionary (sign_clips_250.npz, built by training/build_sign_clips.py)
plus an ordered gloss list into ONE stitched (T,75,3) landmark stream with interpolated
transition frames, and writes the §1 JSON the animation side (your teammate) consumes.

It also produces the two things the contract (§8, §11.2) says you must hand the teammate
so they can start building the rig/renderer TODAY:
  * 2-3 SAMPLE §1 JSON files (real signs in the exact format)
  * one neutral REFERENCE POSE (a single static frame to build the rig against)

WHY THIS EXISTS: the teammate's avatar is DRIVEN by landmark playback (Approach A). You
own "ASR -> gloss -> motion data + stitch"; they own "render the motion onto an avatar".
This module is the "+ stitch -> §1 JSON" seam.

RUN — once you have sign_clips_250.npz in the project root:
  # one utterance -> a playable §1 stream
  python gloss_to_motion.py --glosses "hello hungry" --out hello_hungry.json
  # the teammate's starter pack: samples + reference pose
  python gloss_to_motion.py --samples --out-dir animation_handoff

Delivered coordinates are shoulder-centered with y DOWN (image space) exactly as §3
promises — the RENDERER flips y. We do NOT flip here.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
from sign_landmarks import canonicalize_missing, motion_extent   # noqa: E402

N_POINTS = 75
POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
POSE_L_WRIST, POSE_R_WRIST = 15, 16
L_HAND, R_HAND = slice(33, 54), slice(54, 75)
SCHEMA = "sign-animation/v1"
DEFAULT_FPS = 30
DEFAULT_TRANSITION = 8          # CAP on blend frames between signs (contract §10; see blend_len)

# Every exemplar is RIGHT-dominant: build_sign_clips canonicalizes left-dominant signers by
# negating x and swapping the pose L/R indices, so the tracked hand always lands at 54-74.
# This is a GUARANTEE of the export, not something to re-derive. Re-deriving it from wrist
# travel is what cost us `finish`: on a symmetric sign the two wrists tie (ratio 1.00), the
# tie broke toward L, and the checker then read the always-empty 33-53 block as 0% coverage
# and called a healthy 10-of-22-frame clip an unrecoverable hole.
DOMINANT_HAND = "R"
PASSIVE_HAND = "L"

LEXICON_NAME = "asl_handedness_250.json"

# Exemplar-quality facts come from build_sign_clips' metadata, not from the clip array:
# how many takes survived validity is NOT recoverable from the one take we shipped.
# The corpus median is 114 valid takes; the words below are extreme outliers, and a
# renderer that treats them like the other 230 will make them look broken rather than thin.
META_NAME = "sign_clips_250.meta.json"
THIN_TAKES = 2            # <= this many valid takes: no alternative was available
BRIEF_SEC = 0.53          # shorter than this: too few frames to read as a sign unaided

# class -> what the renderer must DO about the hand that isn't in the data
SYNTH_RULE = {
    "1":  "none",                            # one-handed: nothing to synthesize
    "2s": "mirror_dominant_handshape",       # Battison's Symmetry Condition — exact, not a guess
    "2a": "unmarked_handshape_at_base",      # Dominance Condition — passive from a closed 7-set
}

MISSING_NOTE = ("y is DOWN (image space) — the renderer flips y (contract §3). "
                "x is RAW CAMERA orientation, NOT selfie-mirrored: the signer's right "
                "shoulder is at smaller x. A missing point/hand is null, never [0,0,0] "
                "(§6) — the origin is mid-sternum, so zeros would draw the hand in the "
                "chest. z is noisy; 2D drops it (§4).")

SYNTH_NOTE = (
    "segments[].synthesis tells you what to do about the hand that is NOT in the data. "
    "🔑 READ passiveHandRecorded FIRST — it is measured on the exemplar in THIS file and it "
    "decides whether you synthesize at all. On the GISLR 250-word corpus it is ~0.0 for "
    "every two-handed sign, because that corpus records ONE hand per participant (both "
    "hands in 1.7% of clips, 0.1% of frames) — there, the passive HAND is genuinely absent "
    "and you must synthesize it. On the Sem-Lex clinical corpus it is typically 0.3-0.9: "
    "the passive hand is REAL and already in frames[], so USE IT and fall back to the "
    "synthesis rule only on the frames where it is null. Synthesizing over a recorded hand "
    "would discard the best data in the file. Either way its WRIST is tracked as a pose "
    "landmark (passiveWristIndex), so position is never the missing part. "
    "dominantHand is 'R' in every file BY CONSTRUCTION (left-dominant signers were mirrored "
    "at extraction); do NOT re-derive it from wrist travel — symmetric signs tie. "
    "class/labelConfidence come from a hand-written lexicon because handedness is NOT "
    "recoverable from these landmarks (four classifiers tested, best AUC 0.335 — inverted). "
    "For 2a words, passiveHandshape.shape is a key into handshape_templates.json; if that "
    "shape's template is unusable, follow that file's `resolution` map rather than a rig "
    "default. dominantCoverage is the fraction of frames where the dominant HAND is actually "
    "measured — the rest are nulls you must hold or interpolate through, and on two-handed "
    "signs that is typically well under half. "
    "sourceQuality reports how thin the source was: validTakes is how many takes passed "
    "validity for this word (corpus median 114). thin=true means <=2 takes existed, so this "
    "exemplar is the only thing available and no better one is being withheld; brief=true "
    "means the sign is under 0.53s and may need slowing to read. Treat thin/brief words as "
    "candidates for extra hold or easing, not as bugs to report.")


# ── load the canonical-clip dictionary ────────────────────────────────────────
def load_clips(npz_path: Path) -> dict:
    """word -> (T,75,3) float32 canonical clip (shoulder-centered by build_sign_clips).

    Canonicalizes the zero-sentinel to NaN on the way in, so an absent hand
    encodes as null in the JSON instead of 21 points stacked at mid-sternum. This
    runs on load rather than at build time on purpose: it also repairs clip
    dictionaries produced by the pre-2026-08-10 builder, so a re-export fixes the
    deliverable without re-running the Kaggle build.
    """
    with np.load(npz_path) as z:
        return {w: canonicalize_missing(z[w].astype(np.float32)) for w in z.files}


# ── stitching ─────────────────────────────────────────────────────────────────
def _smoothstep(t: float) -> float:
    """ease-in/out weight in [0,1] (co-articulation feels natural, not linear/robotic)."""
    return t * t * (3.0 - 2.0 * t)


def interp_transition(a_frame: np.ndarray, b_frame: np.ndarray, n: int) -> np.ndarray:
    """n eased frames morphing pose a_frame -> b_frame. A point that is NaN in EITHER
    endpoint stays NaN across the transition (the renderer holds/interpolates it, §6)."""
    out = np.empty((n, N_POINTS, 3), dtype=np.float32)
    for k in range(1, n + 1):
        w = _smoothstep(k / (n + 1))
        out[k - 1] = a_frame * (1.0 - w) + b_frame * w      # NaN * w == NaN (propagates)
    return out


def blend_len(cap: int, a_len: int, b_len: int) -> int:
    """Blend frames to insert between two clips: `cap`, scaled down to the SHORTER clip.

    A FIXED count was only ever safe while every clip was 64 frames. §10 set it to 8, which is
    12% of 64 — invisible. Clips now carry native durations of 9-116 frames, and 8 frames of
    blend on each side of `tiger` (9 frames) is 16/25 = 64% of that word's span: the sign
    becomes a brief event inside a long morph. Nothing raises, the clip just stops reading as
    a sign, which is the failure that does not announce itself.

    15% mirrors the fix the animation side applied to its own rest lead-in for the same reason.
    The floor of 1 keeps a single eased frame rather than a hard pose cut; `cap <= 0` still
    disables blending outright so `--transition 0` behaves as before. For any pair of clips
    >= ~53 frames this returns `cap` unchanged, so it is a no-op on everything that was fine.
    """
    if cap <= 0:
        return 0
    return max(1, min(cap, round(0.15 * min(a_len, b_len))))


def stitch(glosses, clips: dict, transition: int = DEFAULT_TRANSITION, lex: dict | None = None):
    """Concatenate each gloss's clip with eased transition frames between signs.

    `glosses` accepts bare strings and/or extended gloss objects (§12, see parse_gloss) in the
    same list, so ["hello", {"gloss": "sick", "nonmanual": "q"}] is valid.
    Returns (frames (T,75,3), segments [{gloss,start,end,nonmanual?,hold?,synthesis?}],
    present, missing)."""
    frames: list[np.ndarray] = []
    segments: list[dict] = []
    present: list[str] = []
    missing: list[str] = []
    prev_last = None
    prev_len = 0
    for raw in glosses:
        g, extras = parse_gloss(raw)
        clip = clips.get(g)
        if clip is None or clip.shape[0] == 0:
            missing.append(g)                                # no clip -> skip (or fingerspell later)
            continue
        if prev_last is not None and transition > 0:
            frames.extend(interp_transition(prev_last, clip[0],
                                            blend_len(transition, prev_len, clip.shape[0])))
        start = len(frames)
        frames.extend(clip)
        end = len(frames)
        segments.append(make_segment(g, start, end, lex or {}, clip, extras))
        present.append(g)
        prev_last = clip[-1]
        prev_len = clip.shape[0]
    arr = (np.stack(frames).astype(np.float32) if frames
           else np.zeros((0, N_POINTS, 3), dtype=np.float32))
    return arr, segments, present, missing


# ── synthesis descriptors (what to do about the hand that isn't in the data) ───
def load_lexicon(path: Path | None = None) -> dict:
    """word -> synthesis descriptor, from the handedness lexicon.

    Returns {} and warns if the lexicon is absent, rather than raising: a motion stream
    without the block is still playable, it just leaves the renderer guessing on 87 words.
    """
    p = Path(path) if path else HERE / LEXICON_NAME
    if not p.exists():
        print(f"[warn] {p.name} not found — segments will carry NO synthesis block. The "
              f"renderer then has to guess handedness, which is NOT derivable from these "
              f"landmarks. Ship the lexicon beside the clips.")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    passive = (d.get("passive_handshape") or {}).get("words", {})
    out = {}
    for w, v in (d.get("words") or {}).items():
        cls = v[0] if isinstance(v, (list, tuple)) else (v or {}).get("class")
        conf = v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else None
        e = {"class": cls, "rule": SYNTH_RULE.get(cls, "unknown"),
             "dominantHand": DOMINANT_HAND, "twoHanded": cls != "1"}
        if conf:
            e["labelConfidence"] = conf
        if cls != "1":
            e["passiveHand"] = PASSIVE_HAND
            e["passiveWristIndex"] = POSE_L_WRIST       # the passive hand's position IS tracked
        if cls == "2a":
            ph = passive.get(w)
            # A 2a word with no assigned passive handshape is unrenderable, so say so in the
            # file instead of emitting a silently incomplete descriptor.
            e["passiveHandshape"] = dict(ph) if ph else None
            if not ph:
                e["passiveHandshapeMissing"] = True
        out[w] = e
    return out


# Anatomical pose flip PLUS a swap of the two hand blocks (33-53 <-> 54-74). Same array as
# live_demo.FLIP_MAP; duplicated rather than imported because importing live_demo pulls in
# TensorFlow and MediaPipe for a 75-element lookup table.
#
# ⚠️ Use THIS, not training/extract_canonical.canonicalize, to canonicalize a render clip.
# That function does `a[:, RESERVED_BLOCK, :] = np.nan` — it deliberately DESTROYS the
# non-dominant block, which is correct for the recognition corpus and catastrophic here: on
# Sem-Lex the passive hand is real in ~81% of frames on two-handed signs and is the single
# most valuable thing in the clip. Swapping preserves both hands.
FLIP_MAP_SWAP_HANDS = np.array([
    0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
    22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31,
    54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74,
    33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
], dtype=np.int32)


def mirror_clip(clip: np.ndarray) -> np.ndarray:
    """Horizontal mirror of a (T,75,3) shoulder-centered clip, hands SWAPPED.

    Coordinates are shoulder-centered, so the mirror is x -> -x; the index map swaps the
    anatomical pose L/R pairs and exchanges the two hand blocks. Hand topology is identical
    for both hands, so a negated left hand IS a right-shaped hand.
    """
    out = clip[:, FLIP_MAP_SWAP_HANDS, :].copy()
    out[..., 0] *= -1.0
    return out


def canonicalize_clips(clips: dict, meta_path: Path | None = None) -> tuple[dict, dict]:
    """Make every exemplar right-dominant, so `dominantHand: "R"` is true again.

    THE CONTRACT SAYS: "dominantHand is 'R' in every file BY CONSTRUCTION (left-dominant
    signers were mirrored at extraction)." That holds for the GISLR 250-word clips, whose
    meta records all_exemplars_right_dominant: true. It does NOT hold for the Sem-Lex
    clinical clips: that corpus was extracted WITHOUT --canonical-hand (the medical training
    config records canonical_hand: false in all four folds), so its meta says
    all_exemplars_right_dominant: false and 20 of 55 exemplars are left-dominant.

    Exported unmirrored, those 20 words tell the animator the dominant hand is at 54-74 when
    it is at 33-53, and dominantCoverage reads 0.000 on the five words whose R block is
    entirely empty. Nothing raises. This is the same failure the DOMINANT_HAND comment above
    describes costing us `finish`, arriving from the other direction.

    Dominance is taken from build_sign_clips' recorded per-word `dominant`, not re-derived:
    that decision was made across all candidate takes using wrist TRAVEL, and it disagrees
    with "whichever block has more tracked frames" on exactly the words where the tracker
    kept the RESTING hand (3 of 55 here). Re-deriving it per clip is the known-bad rule.
    """
    p = Path(meta_path) if meta_path else HERE / META_NAME
    info = {"applied": False, "mirrored": [], "reason": None}
    if not p.exists():
        info["reason"] = f"{p.name} not found — cannot know which words are left-dominant"
        print(f"[warn] {info['reason']}. Clips exported AS-IS; if any exemplar is "
              f"left-dominant, its dominantHand field is WRONG.")
        return clips, info
    blob = json.loads(p.read_text(encoding="utf-8"))
    if blob.get("all_exemplars_right_dominant"):
        info["reason"] = "meta says all exemplars are already right-dominant"
        print(f"[ok] {p.name}: exemplars are already canonical (all right-dominant) — "
              f"no mirroring needed")
        return clips, info
    dom = {m.get("word"): m.get("dominant") for m in (blob.get("words") or [])}
    out, missing = {}, []
    for w, c in clips.items():
        d = dom.get(w)
        if d is None:
            missing.append(w)
            out[w] = c
        elif d == "L":
            out[w] = mirror_clip(c)
            info["mirrored"].append(w)
        else:
            out[w] = c
    info["applied"] = True
    print(f"[ok] canonicalized {len(info['mirrored'])}/{len(clips)} left-dominant exemplars "
          f"-> dominant hand at 54-74, passive hand PRESERVED at 33-53")
    if info["mirrored"]:
        print(f"     mirrored: {', '.join(sorted(info['mirrored']))}")
    if missing:
        print(f"[warn] {len(missing)} words have no `dominant` in {p.name} and were left "
              f"as-is: {sorted(missing)[:8]}")
    return out, info


def attach_source_quality(lex: dict, path: Path | None = None,
                          fps: int = DEFAULT_FPS) -> dict:
    """Fold per-word exemplar-quality facts into the lexicon entries, in place.

    Folded into `lex` rather than threaded as a new argument because make_segment already
    shallow-copies the lexicon entry into `synthesis` — so this rides along through stitch(),
    word_contract_json() and glosses_to_contract() with no signature change.

    `validTakes` is the one fact here that is NOT derivable from the shipped JSON: the clip
    array shows the take we chose, never how many we chose it from. 20 of 250 words had <= 2
    valid takes against a corpus median of 114, and 7 had exactly one — for those, "pick a
    better take" was never an option, and the renderer should compensate rather than assume
    the data is representative. Absent metadata is a warning, not an error: the block is
    advisory and every file stays playable without it.
    """
    p = Path(path) if path else HERE / META_NAME
    if not p.exists():
        print(f"[warn] {p.name} not found — synthesis blocks will carry NO sourceQuality. "
              f"The renderer cannot then tell a thin-pool word from a well-sampled one.")
        return lex
    try:
        words = json.loads(p.read_text(encoding="utf-8")).get("words") or []
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] {p.name} unreadable ({e}) — no sourceQuality emitted.")
        return lex
    n = thin = brief = 0
    for m in words:
        w = m.get("word")
        if w not in lex:
            continue
        takes = m.get("valid_candidates")
        frames = m.get("frames")
        q = {"sourceClip": m.get("source_clip")}
        if isinstance(takes, int):
            q["validTakes"] = takes
            q["thin"] = takes <= THIN_TAKES
            thin += q["thin"]
        if isinstance(frames, int) and fps:
            q["brief"] = frames / fps < BRIEF_SEC
            brief += q["brief"]
        lex[w]["sourceQuality"] = q
        n += 1
    print(f"[ok] sourceQuality for {n}/{len(lex)} words "
          f"({thin} thin-pool <= {THIN_TAKES} takes, {brief} briefer than {BRIEF_SEC}s)")
    return lex


def dominant_coverage(clip: np.ndarray) -> float:
    """Fraction of frames in which the DOMINANT hand block is actually measured."""
    if clip is None or len(clip) == 0:
        return 0.0
    have = np.isfinite(clip[:, R_HAND, :2]).all(-1).any(-1)
    return round(float(have.mean()), 4)


def passive_hand_recorded(clip: np.ndarray, passive: str | None = PASSIVE_HAND) -> float:
    """Fraction of frames in which the PASSIVE hand block is actually measured.

    The v1 contract asserted this is 0.0 on every two-handed sign, because GISLR records
    one hand per participant. That is a fact about GISLR, not about the format — Sem-Lex
    records both. Measured on the 55 clinical words: class 2s 75.0% of frames, class 2a
    59.8%, and 29 of 30 two-handed exemplars carry a real passive hand.

    A renderer that synthesizes whenever `twoHanded` is true would overwrite recorded
    landmarks with a guess, and nothing would raise. So the number ships in the file and
    SYNTH_NOTE tells the animator to branch on it.
    """
    if clip is None or len(clip) == 0:
        return 0.0
    blk = L_HAND if (passive or PASSIVE_HAND) == "L" else R_HAND
    have = np.isfinite(clip[:, blk, :2]).all(-1).any(-1)
    return round(float(have.mean()), 4)


# Tier boundaries on dominant-hand coverage. Measured over the shipped 250 on 2026-08-14:
# A 146 words, B 59, C 45 — and the split is almost entirely by handedness class
# (class 1: 143/20/0, class 2s: 3/21/28, class 2a: 0/18/17). Two-handed signs are where the
# tracker loses the moving hand, because that is where the hands cross and occlude.
TIER_A, TIER_B = 0.80, 0.50
HOLDABLE_GAP = 4          # gaps this short are tracker dropout, not the hand leaving


def dominant_gaps(clip: np.ndarray) -> dict:
    """Where the dominant hand is missing, and for how long at a stretch.

    A renderer needs the RUN structure, not just the total: 70.9% of the 776 gaps in the
    shipped corpus are 1-3 frames and 751 of 776 are interior, i.e. the hand did not go
    anywhere and the tracker simply lost it. Holding the last handshape across those is
    correct and relaxing the hand is not — the handshape visibly collapses and re-forms.
    A long gap is a different thing and relaxing IS right there, which is why the two are
    reported separately rather than as one coverage number.
    """
    out = {"gaps": 0, "longestGapFrames": 0, "holdableFrames": 0, "relaxFrames": 0}
    if clip is None or len(clip) == 0:
        return out
    miss = ~np.isfinite(clip[:, R_HAND, :2]).all(-1).any(-1)
    n, i = len(miss), 0
    while i < n:
        if not miss[i]:
            i += 1
            continue
        j = i
        while j < n and miss[j]:
            j += 1
        run = j - i
        out["gaps"] += 1
        out["longestGapFrames"] = max(out["longestGapFrames"], run)
        # An edge gap has no earlier pose to hold, so it can never be holdable.
        if run <= HOLDABLE_GAP and i > 0:
            out["holdableFrames"] += run
        else:
            out["relaxFrames"] += run
        i = j
    return out


def quality_tier(coverage: float) -> str:
    return "A" if coverage >= TIER_A else "B" if coverage >= TIER_B else "C"


# ── extended gloss form (contract §12) ───────────────────────────────────────────────────────
# A gloss may be a bare string, or an object carrying grammar that a bare word cannot:
#     "sick"                                  -> the sign, nothing more
#     {"gloss": "sick", "nonmanual": "q"}     -> the sign, marked as a yes/no question
#
# WHY THIS EXISTS. ASL grammar is not carried by word order alone -- questions, negation and
# topicalisation live on the FACE, simultaneously with the manual sign. A flat list of English
# words cannot express them, which is why the honest description of the current system is that it
# *plays ASL signs* rather than *produces ASL* (docs/AVATAR_LIMITS.md §1).
#
# Our 75-point corpus has no face landmarks, and contract §7 explains that the 468-point face
# stream IS recoverable upstream -- but also why that would not help: the clips are ISOLATED
# WORDS, so the signers' expressions are neutral rather than grammatical. Recovering the face
# gives motion without meaning; the grammar was never performed, so no retraining can find it.
# Rendering a non-manual, by contrast, needs no data at all -- only a rule and a rig. So the
# production direction can carry grammar the recognition direction cannot, and this is it.
#
# Additive on purpose: a bare string stays valid forever, every consumer that ignores these keys
# keeps working, and the keys exist now so Ghozlan's rig can be built to read them rather than
# retrofitted later.
NONMANUALS = {
    "q":    "yes/no question -- brow raise, held for the marked span",
    "wh":   "wh-question -- brow furrow + slight head tilt",
    "neg":  "negation -- headshake across the marked span",
    "top":  "topic -- brow raise on the topicalised element only",
    None:   "neutral",
}


def parse_gloss(g) -> tuple[str, dict]:
    """'sick' or {'gloss':'sick','nonmanual':'q','hold':0.2} -> ('sick', extras).

    Unknown non-manuals are REJECTED rather than silently dropped: a typo'd marker that renders
    as neutral is a sentence that quietly means something else, which is worse than a crash."""
    if isinstance(g, str):
        return g, {}
    if not isinstance(g, dict) or "gloss" not in g:
        raise ValueError(f"gloss must be a string or an object with a 'gloss' key, got {g!r}")
    word = g["gloss"]
    extras = {}
    nm = g.get("nonmanual")
    if nm is not None:
        if nm not in NONMANUALS:
            raise ValueError(f"unknown nonmanual {nm!r} on {word!r}; "
                             f"expected one of {sorted(k for k in NONMANUALS if k)}")
        extras["nonmanual"] = nm
    if g.get("hold"):
        extras["hold"] = float(g["hold"])           # extra seconds to freeze on the final pose
    return word, extras


def make_segment(word: str, start: int, end: int, lex: dict,
                 clip: np.ndarray | None = None, extras: dict | None = None) -> dict:
    seg = {"gloss": word, "start": int(start), "end": int(end)}
    if extras:
        seg.update(extras)                          # nonmanual / hold, only when actually set
    ent = lex.get(word)
    if ent:
        s = dict(ent)
        if clip is not None:
            cov = dominant_coverage(clip)
            s["dominantCoverage"] = cov
            s["quality"] = {"tier": quality_tier(cov), **dominant_gaps(clip)}
            # MEASURED on the exemplar that ships, not assumed from the corpus. The v1
            # contract asserted the passive hand is absent in every take, which is true of
            # GISLR and FALSE of Sem-Lex (medical: 29 of 30 two-handed exemplars carry a
            # real passive hand, mean 68.9% of frames). Telling the animator to synthesize
            # over recorded data is the kind of error that never announces itself, so the
            # number goes in the file and the note tells him to read it first.
            if s.get("twoHanded"):
                s["passiveHandRecorded"] = passive_hand_recorded(clip, s.get("passiveHand"))
        seg["synthesis"] = s
    return seg


def _round_or_null(v: float):
    return None if not math.isfinite(v) else round(float(v), 5)   # NaN -> null (§6)


def to_contract_json(frames: np.ndarray, segments, glosses, fps: int = DEFAULT_FPS) -> dict:
    """Build the SIGN_ANIMATION_CONTRACT §1 object. frames: (T,75,3)."""
    out = {
        "schema": SCHEMA,
        "fps": fps,
        "coord_space": "shoulder-centered",
        "note": MISSING_NOTE,
        "glosses": list(glosses),
        "segments": segments,
        "nativeFrames": int(len(frames)),
        "nativeFps": fps,
        "frames": [[[_round_or_null(v) for v in pt] for pt in frame] for frame in frames],
    }
    # only claim the synthesis contract when a segment actually carries one
    if any("synthesis" in s for s in segments):
        out["synthesisNote"] = SYNTH_NOTE
    return out


def write_json(obj: dict, path: Path):
    path.write_text(json.dumps(obj), encoding="utf-8")


def word_contract_json(word: str, clip: np.ndarray, fps: int = DEFAULT_FPS,
                       lex: dict | None = None) -> dict:
    """One word's motion as a §1 object (same schema as an utterance, just length-1 and
    no transitions) — the per-word file the avatar plays. frames = that word's (T,75,3).

    `segments` carries the REAL sign extent, not 0..T. Several clips end in dropped
    frames (`down` stops moving at frame ~45 of 64), so a player that loops the whole
    window scrubs through dead time. The full clip still ships — the animator can
    re-time from the extent rather than being handed a pre-trimmed guess.
    """
    start, end = motion_extent(clip)
    segs = [make_segment(word, start, end, lex or {}, clip)]
    return to_contract_json(clip, segs, [word], fps)


# ── neutral reference pose (contract §11.2) ───────────────────────────────────
def _hand_points_finite(frame: np.ndarray) -> int:
    return int(np.isfinite(frame[33:N_POINTS, :2]).all(axis=-1).sum())


def reference_pose(clips: dict) -> tuple:
    """A single static frame for the teammate to build/test the rig against. We pick the
    frame (across all clips) that has finite shoulders AND the most detected hand points —
    a clear, fully-tracked pose. Returns (word, frame_index, (75,3) frame)."""
    best = None                                              # (score, word, idx, frame)
    for w, clip in clips.items():
        for t in range(clip.shape[0]):
            fr = clip[t]
            if not np.isfinite(fr[POSE_L_SHOULDER, :2]).all() or not np.isfinite(fr[POSE_R_SHOULDER, :2]).all():
                continue
            score = _hand_points_finite(fr)
            if best is None or score > best[0]:
                best = (score, w, t, fr)
    if best is None:
        raise SystemExit("[err] no clip had a finite-shoulder frame — is the .npz valid?")
    _, w, t, fr = best
    return w, t, fr


def reference_pose_json(word: str, idx: int, frame: np.ndarray) -> dict:
    return {
        "schema": "sign-animation/reference-pose/v1",
        "coord_space": "shoulder-centered",
        "note": ("neutral-ish rig-building pose (contract §11.2). Source: clearest fully-tracked "
                 f"frame in the dataset ('{word}' frame {idx}). y is DOWN — flip in the renderer."),
        "layout": "0-32 pose, 33-53 left hand, 54-74 right hand; each point [x,y,z]",
        "pose": [[_round_or_null(v) for v in pt] for pt in frame],
    }


# ── runtime entry used by speech_to_sign.py Phase 3 ───────────────────────────
def glosses_to_contract(glosses, clips_path: Path, fps: int = DEFAULT_FPS,
                        transition: int = DEFAULT_TRANSITION, lexicon: Path | None = None):
    """Load clips, stitch the glosses, return (contract_dict, present, missing).
    Raises FileNotFoundError if the clip dictionary hasn't been built yet."""
    if not Path(clips_path).exists():
        raise FileNotFoundError(clips_path)
    clips = load_clips(Path(clips_path))
    frames, segments, present, missing = stitch(glosses, clips, transition,
                                                load_lexicon(lexicon))
    return to_contract_json(frames, segments, present, fps), present, missing


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Gloss list -> stitched landmark motion stream (contract §1)")
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"),
    
                    help="canonical-clip dictionary from training/build_sign_clips.py")
    ap.add_argument("--glosses", help="space-separated glosses to stitch, e.g. \"hello hungry\"")
    ap.add_argument("--out", default="motion.json", help="output §1 JSON (with --glosses)")
    ap.add_argument("--word", help="export ONE word's motion JSON (e.g. hello) — for a format sample")
    ap.add_argument("--per-word", action="store_true",
                    help="export EVERY word as its own JSON (the avatar's per-word motion library)")
    ap.add_argument("--samples", action="store_true",
                    help="write the teammate starter-pack (sample utterances + reference pose)")
    ap.add_argument("--out-dir", default="animation_handoff",
                    help="folder for --samples / --per-word output")
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--transition", type=int, default=DEFAULT_TRANSITION,
                    help="interpolation frames inserted between signs (contract §10)")
    ap.add_argument("--lexicon", default=None,
                    help=f"handedness lexicon for the per-segment synthesis block "
                         f"(default: {LEXICON_NAME} beside this script)")
    ap.add_argument("--meta", default=None,
                    help=f"clip metadata from build_sign_clips.py, for synthesis.sourceQuality "
                         f"and the canonicalization decision. DEFAULT is derived from --clips "
                         f"(sign_clips_X.npz -> sign_clips_X.meta.json), falling back to "
                         f"{META_NAME}. Deriving it matters: a fixed default silently pairs "
                         f"one vocabulary's clips with another's metadata, and only the words "
                         f"present in BOTH get a sourceQuality block — 15 of 55 on the "
                         f"clinical set, each carrying the wrong take count.")
    ap.add_argument("--canonicalize", choices=["auto", "off"], default="auto",
                    help="'auto' (default): if the clip metadata says the exemplars are NOT "
                         "all right-dominant, mirror the left-dominant ones so the contract's "
                         "dominantHand:'R' guarantee holds. Required for the Sem-Lex clinical "
                         "clips (20 of 55 are left-dominant); a no-op on the GISLR 250-word "
                         "clips, which were canonicalized at extraction. 'off' exports as-is "
                         "and is only for reproducing a pre-2026-09-04 run — it emits "
                         "dominantHand:'R' for words whose hand is in the 33-53 block, which "
                         "is silently wrong.")
    args = ap.parse_args()

    clips_path = Path(args.clips)
    if not clips_path.exists():
        raise SystemExit(f"[err] clip dictionary not found: {clips_path}\n"
                         f"      Build it first on Kaggle: cd training && python build_sign_clips.py --data-dir <data>")
    clips = load_clips(clips_path)
    print(f"[ok] loaded {len(clips)} canonical clips from {clips_path.name}")
    # Pair the metadata with the clips it describes. Without this, --clips
    # sign_clips_medical.npz silently reads sign_clips_250.meta.json and attaches the
    # 250-word corpus's take counts to whichever 15 words the two vocabularies share.
    if args.meta is None:
        cand = clips_path.parent / (clips_path.stem + ".meta.json")
        if cand.exists():
            args.meta = str(cand)
            print(f"[ok] metadata: {cand.name} (derived from --clips)")
        else:
            print(f"[warn] no {cand.name} beside the clips — falling back to {META_NAME}. "
                  f"If that describes a DIFFERENT vocabulary, sourceQuality and the "
                  f"canonicalization decision will be wrong.")
    if args.canonicalize == "auto":
        clips, _canon = canonicalize_clips(clips, args.meta)
    else:
        print("[warn] --canonicalize off: any left-dominant exemplar will ship with "
              "dominantHand:'R' and a 0.000 dominantCoverage. Diagnostic use only.")
    lex = load_lexicon(args.lexicon)
    if lex:
        attach_source_quality(lex, args.meta, args.fps)
        n2 = sum(1 for w in clips if lex.get(w, {}).get("twoHanded"))
        gap = sorted(w for w in clips if w not in lex)
        miss = sorted(w for w in clips if lex.get(w, {}).get("passiveHandshapeMissing"))
        print(f"[ok] synthesis block for {sum(1 for w in clips if w in lex)}/{len(clips)} words "
              f"({n2} two-handed need a synthesized passive hand)")
        if gap:
            print(f"[warn] {len(gap)} exported words are NOT in the lexicon — they ship with no "
                  f"synthesis block: {gap[:12]}")
        if miss:
            print(f"[warn] {len(miss)} 2a words have no passive handshape assigned — the renderer "
                  f"cannot draw them: {miss}")

    if args.word:                                   # ONE word -> format sample for the teammate
        clip = clips.get(args.word)
        if clip is None:
            raise SystemExit(f"[err] no clip for '{args.word}' (have {len(clips)} words)")
        out = Path(args.out) if args.out and args.out != "motion.json" else Path(f"{args.word}.json")
        write_json(word_contract_json(args.word, clip, args.fps, lex), out)
        print(f"[ok] wrote per-word motion -> {out}  ({clip.shape[0]} frames of 75 joint positions)")
        return

    if args.per_word:                               # the avatar's full per-word motion library
        wdir = Path(args.out_dir) / "words"
        wdir.mkdir(parents=True, exist_ok=True)
        for w, clip in clips.items():
            write_json(word_contract_json(w, clip, args.fps, lex), wdir / f"{w}.json")
        w0, idx, fr = reference_pose(clips)
        write_json(reference_pose_json(w0, idx, fr), Path(args.out_dir) / "reference_pose.json")
        print(f"\n[ok] wrote {len(clips)} per-word motion files -> {wdir}/")
        print(f"[ok] reference_pose.json -> {args.out_dir}/  (build the rig against this, §11.2)")
        print("\n-> Hand the whole folder + SIGN_ANIMATION_CONTRACT.md to your friend. At RUNTIME you")
        print("   send him the ordered gloss list; his avatar plays <word>.json in that order.")
        return

    if args.samples:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        # a couple of common demo utterances, using whatever words exist in the dictionary
        wants = [["hello"], ["hungry"], ["hello", "mom", "hungry", "please"]]
        made = []
        for glist in wants:
            usable = [g for g in glist if g in clips]
            if not usable:
                continue
            frames, segments, present, missing = stitch(usable, clips, args.transition, lex)
            name = "sample_" + "_".join(present) + ".json"
            write_json(to_contract_json(frames, segments, present, args.fps), out_dir / name)
            made.append((name, len(frames), present))
        # the neutral reference pose for rig-building
        w, idx, fr = reference_pose(clips)
        write_json(reference_pose_json(w, idx, fr), out_dir / "reference_pose.json")

        print(f"\n[ok] teammate starter-pack -> {out_dir}/")
        for name, n, present in made:
            print(f"   {name:38s} {n:4d} frames  ({' '.join(present)})")
        print(f"   reference_pose.json                    1 frame   (from '{w}')")
        print("\n-> Hand this folder + SIGN_ANIMATION_CONTRACT.md to your teammate. They build the")
        print("   rig against reference_pose.json and test playback against the sample_*.json streams.")
        return

    if not args.glosses:
        raise SystemExit("[err] pass --glosses \"...\" to stitch an utterance, or --samples for the starter-pack")
    glosses = args.glosses.split()
    frames, segments, present, missing = stitch(glosses, clips, args.transition, lex)
    write_json(to_contract_json(frames, segments, present, args.fps), Path(args.out))
    dur = len(frames) / max(1, args.fps)
    print(f"[ok] stitched {present} -> {len(frames)} frames ({dur:.1f}s @ {args.fps}fps) -> {args.out}")
    if missing:
        print(f"[warn] no clip for {missing} — skipped (add to the dictionary or fingerspell later)")


if __name__ == "__main__":
    main()
