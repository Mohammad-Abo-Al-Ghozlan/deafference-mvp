#!/usr/bin/env python3
"""Mine the UNMARKED HANDSHAPE templates (B A S 1 5 C O) from the corpus.

WHY
---
GISLR records one hand per participant, so for the 35 two-handed ASYMMETRIC signs the
passive hand's landmarks do not exist in any take. Under Battison's Dominance Condition the
passive hand of an asymmetric sign is restricted to a small set of UNMARKED handshapes, so it
is synthesizable — but only if the renderer has those handshapes to place. The animation side
currently renders all 35 with a relaxed curl for exactly this reason and asked (2026-08-12)
for "the B/A/S/1/5/C/O configurations, even as 21-point landmark templates in the same
coordinate convention as the export".

This does not invent them. Each target handshape is mined from real frames of signs whose
DOMINANT hand already forms it — `milk` is a fist (S), `think` is an index point (1), `drink`
is a curved C. We have thousands of takes of those, and the dominant hand IS recorded.

METHOD
------
1. For each handshape, take its anchor words (below).
2. Keep only well-tracked takes: dominant-hand coverage and a long contiguous run.
3. Inside the sign extent, choose the HOLD frame — the lowest-velocity frame, where a
   handshape is fully formed and momentarily static. Peak-of-motion frames are transitional.
4. Express the 21 points in a canonical PALM FRAME: origin at the wrist, x toward the index
   MCP, palm normal from the pinky MCP, scaled by wrist->middle-MCP length. That makes the
   template independent of where the hand was, how big the signer was, and which way it faced.
5. Average over takes, and REPORT the spread. A handshape whose takes disagree is not a
   template, it is noise with an average — that number decides whether it ships.

HONEST LIMITS, stated because they affect what the renderer can trust:
  * `O` has no clean anchor in this 250-word vocabulary. The closest forms are flattened-O
    (`flower`, `home`), which is a different handshape. It is emitted flagged, not trusted.
  * GISLR `z` is raw MediaPipe relative depth, not metric, and is not on the same scale as
    x,y. Templates are therefore emitted BOTH as xy (2D, reliable) and xyz (3D, use with
    care), with separate agreement numbers so the animation side can see which to use.
  * These are hearing-developer choices of anchor word. A Deaf reviewer should confirm that
    e.g. `milk` is S rather than a squeezed-A before these drive a shipped avatar.

RUN
    python build_handshape_templates.py --data-dir /kaggle/input/.../canon/none \
        --out handshape_templates.json
"""
from __future__ import annotations

import os

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
REPO = _HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(_HERE))
if not (REPO / "vocab_250.json").exists() and (_HERE / "vocab_250.json").exists():
    REPO = _HERE

from train import load_dataset                                        # noqa: E402
from sign_landmarks import (                                          # noqa: E402
    L_HAND, R_HAND, canonicalize_missing, hand_coverage,
    hand_coverage_runs, motion_extent,
)

# MediaPipe hand landmark layout, 0-20
WRIST, THUMB_CMC, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP = 0, 1, 5, 9, 13, 17
TIPS = (4, 8, 12, 16, 20)

# Anchor words whose DOMINANT hand forms each unmarked handshape.
# conf: "high" = the handshape is not in doubt; "low" = approximate, needs review.
ANCHORS: dict[str, dict] = {
    "B": {"words": ["thankyou", "please", "bad", "white"], "conf": "high",
          "desc": "flat hand, fingers together and extended, thumb alongside"},
    "A": {"words": ["tomorrow", "yesterday", "aunt"], "conf": "high",
          "desc": "fist with the thumb alongside the index, thumb up"},
    # `milk` and `orange` were DROPPED 2026-08-12. Both are dynamic: the hand opens and
    # closes DURING the sign (milk squeezes, orange squeezes at the chin), so a single
    # hold frame lands anywhere in that cycle and the takes genuinely disagree — which is
    # exactly what agreement_xy 0.337 was reporting. The takes were not noisy, the anchor
    # choice was wrong. `yes` (a fist bobbing at the wrist) is the only static S in this
    # vocabulary, so agreement here is WITHIN-word across takes, a weaker claim than the
    # across-word agreement the other shapes get. Stated, not hidden.
    "S": {"words": ["yes"], "conf": "high", "single_anchor": True, "fallback": "A",
          "desc": "fist with the thumb crossed over the front of the fingers"},
    "1": {"words": ["think", "nose", "eye", "chin"], "conf": "high",
          "desc": "index finger extended, remaining fingers closed"},
    "5": {"words": ["dad", "mom", "fine", "grandma"], "conf": "high",
          "desc": "all five fingers extended and spread"},
    "C": {"words": ["drink", "hungry", "giraffe"], "conf": "high",
          "desc": "fingers and thumb curved into a C"},
    "O": {"words": ["flower", "home", "old"], "conf": "low", "fallback": "C",
          "desc": "fingertips meeting the thumb in a round O. NO clean anchor exists in "
                  "this 250-word vocabulary — all 250 words were checked 2026-08-12: "
                  "flower and home are flattened-O (a DIFFERENT handshape) and old is "
                  "dynamic C-to-S. This is unfixable from this vocabulary, not a "
                  "measurement problem. Emitted for completeness; do not trust it."},
}

# When a template is unusable the renderer still has to draw something, and 'whatever the
# rig defaults to' is not a specification. FALLBACK names the substitute explicitly:
#   S -> A   both are unmarked fists and MediaPipe cannot separate them anyway (measured:
#            S thu 1.24 / A thu 1.49 is the only difference, and thumb position on a closed
#            fist is where hand tracking is least reliable). Using A for S is a small,
#            bounded visual error; a relaxed curl is a larger one.
#   O -> C   nearest available rounded shape, and C measured clean (agreement 0.198).
# A fallback is a documented approximation, NOT a silent substitution — it is emitted in
# the JSON so the animation side can decide whether to accept it.

MIN_COVERAGE = 0.60          # dominant-hand coverage inside the extent
MIN_RUN = 0.40               # longest contiguous covered run
MAX_TAKES_PER_WORD = 40      # cap so one prolific word cannot dominate a template
MIN_TAKES = 8                # below this a template is not reported as usable


def palm_frame(pts: np.ndarray) -> np.ndarray | None:
    """21x3 hand -> 21x3 in a canonical palm frame, or None if it cannot be built.

    origin  wrist
    x       toward the index MCP
    z       palm normal (index MCP x pinky MCP)
    y       completes a right-handed basis
    scale   |wrist -> middle MCP|, a stable palm length that does not depend on which
            fingers happen to be extended (a fingertip-based scale would)
    """
    need = (WRIST, INDEX_MCP, MIDDLE_MCP, PINKY_MCP)
    if not np.isfinite(pts[list(need)]).all():
        return None
    o = pts[WRIST]
    e1 = pts[INDEX_MCP] - o
    v = pts[PINKY_MCP] - o
    scale = float(np.linalg.norm(pts[MIDDLE_MCP] - o))
    n1 = float(np.linalg.norm(e1))
    if scale < 1e-6 or n1 < 1e-6:
        return None
    e1 = e1 / n1
    e3 = np.cross(e1, v)
    n3 = float(np.linalg.norm(e3))
    if n3 < 1e-9:                                # index, pinky and wrist are collinear
        return None
    e3 = e3 / n3
    e2 = np.cross(e3, e1)
    R = np.stack([e1, e2, e3], axis=0)           # world -> local
    return ((pts - o) @ R.T) / scale


def hold_frame(clip: np.ndarray, blk: slice, extent: tuple[int, int]) -> int | None:
    """Index of the lowest-velocity fully-tracked frame inside the extent.

    A handshape is fully formed during the HOLD, not during transport. Peak-of-motion frames
    are transitional and would average into a smear.
    """
    s, e = extent
    s, e = max(0, s), min(clip.shape[0], max(e, s + 1))
    xy = clip[:, blk, :2]
    live = ~np.isnan(xy).all(axis=(1, 2)) & np.isfinite(clip[:, blk, :]).all(axis=(1, 2))
    idx = [i for i in range(s, e) if live[i]]
    if len(idx) < 3:
        return None
    best, best_v = None, np.inf
    for i in idx:
        prev = [j for j in idx if j < i]
        nxt = [j for j in idx if j > i]
        if not prev or not nxt:
            continue
        a, b = clip[prev[-1], blk, :2], clip[nxt[0], blk, :2]
        v = float(np.nanmean(np.linalg.norm(b - a, axis=-1)))
        if np.isfinite(v) and v < best_v:
            best, best_v = i, v
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="corpus root (canon/none is preferred: no gap-filled frames)")
    ap.add_argument("--vocab", type=Path, default=REPO / "vocab_250.json")
    ap.add_argument("--out", type=Path, default=REPO / "handshape_templates.json")
    ap.add_argument("--min-takes", type=int, default=MIN_TAKES)
    args = ap.parse_args()

    frozen = json.loads(args.vocab.read_text(encoding="utf-8"))
    words = frozen["words"] if isinstance(frozen, dict) else frozen
    vocab = {"words": words, "word_to_index": {w: i for i, w in enumerate(words)},
             "num_classes": len(words)}

    wanted = {w for a in ANCHORS.values() for w in a["words"]}
    missing = sorted(wanted - set(words))
    if missing:
        print(f"[warn] anchor words not in the vocab, dropped: {missing}")

    man, arrays = load_dataset(args.data_dir, vocab)
    if "is_outlier" in man.columns:
        man = man[~man["is_outlier"]]
    man = man[man["word"].isin(wanted)].reset_index(drop=True)
    print(f"[cfg] {len(man)} candidate takes across {man['word'].nunique()} anchor words\n")

    # ── collect palm-frame samples per handshape ──────────────────────────────────────
    samples: dict[str, list] = {k: [] for k in ANCHORS}
    per_word_n: dict[str, int] = {}
    word_to_shape = {w: k for k, a in ANCHORS.items() for w in a["words"]}
    taken: dict[str, int] = {}

    for key, word in zip(man["key"].tolist(), man["word"].tolist()):
        shape = word_to_shape.get(word)
        if shape is None or taken.get(word, 0) >= MAX_TAKES_PER_WORD:
            continue
        a = arrays.get(key)
        if a is None or a.shape[0] < 8:
            continue
        clip = canonicalize_missing(np.asarray(a, dtype=np.float32))
        extent = motion_extent(clip)
        cov, runs = hand_coverage(clip, extent), hand_coverage_runs(clip, extent)
        # the canonical corpus always parks the recorded hand at 54-74; on the legacy layout
        # take whichever block is actually populated
        blk_name = "R" if cov["R"] >= cov["L"] else "L"
        blk = R_HAND if blk_name == "R" else L_HAND
        if cov[blk_name] < MIN_COVERAGE or runs[blk_name] < MIN_RUN:
            continue
        i = hold_frame(clip, blk, extent)
        if i is None:
            continue
        loc = palm_frame(clip[i, blk, :])
        if loc is None or not np.isfinite(loc).all():
            continue
        # a LEFT hand is a mirror image of a right one; reflect it so all samples of a
        # handshape live in one chirality before they are averaged
        if blk_name == "L":
            loc = loc.copy()
            loc[:, 2] *= -1.0
        samples[shape].append(loc)
        taken[word] = taken.get(word, 0) + 1
        per_word_n[word] = per_word_n.get(word, 0) + 1

    # ── average, and measure whether the average means anything ───────────────────────
    out = {
        "schema": "asl-handshape-templates/v1",
        "date": "2026-08-12",
        "coord_space": ("canonical PALM FRAME: origin at the wrist, x toward the index MCP, "
                        "z the palm normal (index x pinky), y right-handed; scaled by "
                        "|wrist->middle MCP| = 1. Right-hand chirality; left-hand samples "
                        "were reflected in z before averaging."),
        "z_warning": ("z comes from raw MediaPipe relative depth, which is NOT on the same "
                      "scale as x,y and is much noisier. Compare agreement_xy against "
                      "agreement_xyz before using the 3D form; prefer template_xy if the "
                      "3D agreement is materially worse."),
        "usage": ("For a two-handed ASYMMETRIC sign (class 2a), place this handshape at the "
                  "passive wrist position carried in the export's passiveWrist track. The "
                  "wrist POSITION is measured, not synthesized — only the handshape is."),
        "review_status": ("Anchor words chosen by a hearing developer from ASL phonology. A "
                          "Deaf reviewer should confirm each anchor forms the handshape "
                          "claimed before this drives a shipped avatar."),
        "thresholds": {"min_coverage": MIN_COVERAGE, "min_run": MIN_RUN,
                       "min_takes": args.min_takes},
        "handshapes": {},
    }

    print(f"{'shape':6} {'takes':>6} {'agree_xy':>9} {'agree_xyz':>10} {'conf':>5}  verdict")
    print("-" * 74)
    usable = 0
    for shape, meta in ANCHORS.items():
        S = samples[shape]
        entry = {"description": meta["desc"], "anchor_words": meta["words"],
                 "anchor_confidence": meta["conf"], "n_takes": len(S),
                 "takes_per_word": {w: per_word_n.get(w, 0) for w in meta["words"]}}
        if meta.get("single_anchor"):
            # agreement across takes of ONE word is a weaker claim than across words: it
            # cannot detect a systematically wrong anchor, only an inconsistent one.
            entry["agreement_scope"] = "within-word only (single anchor) — weaker evidence"
        if meta.get("fallback"):
            entry["fallback_handshape"] = meta["fallback"]
            entry["fallback_note"] = (
                f"if this template is unusable, substitute {meta['fallback']} rather than a "
                f"rig default — a named approximation, not a silent one")
        if len(S) < args.min_takes:
            entry["usable"] = False
            entry["reason"] = f"only {len(S)} usable takes, need {args.min_takes}"
            out["handshapes"][shape] = entry
            print(f"{shape:6} {len(S):6} {'-':>9} {'-':>10} {meta['conf']:>5}  "
                  f"TOO FEW TAKES")
            continue
        A = np.stack(S, axis=0)                                  # (n, 21, 3)
        tmpl = np.median(A, axis=0)                              # median: robust to outliers
        # agreement = median per-point distance from the template, in palm-length units.
        # 0.10 means the typical landmark sits within a tenth of a palm of the template.
        d_xy = np.linalg.norm(A[:, :, :2] - tmpl[None, :, :2], axis=-1)
        d_xyz = np.linalg.norm(A - tmpl[None], axis=-1)
        ag_xy, ag_xyz = float(np.median(d_xy)), float(np.median(d_xyz))
        good = ag_xy <= 0.20 and meta["conf"] == "high"
        usable += int(good)
        entry.update({
            "usable": bool(good),
            "agreement_xy": round(ag_xy, 4),
            "agreement_xyz": round(ag_xyz, 4),
            "spread_p90_xy": round(float(np.percentile(d_xy, 90)), 4),
            "template_xy": [[round(float(v), 5) for v in p] for p in tmpl[:, :2]],
            "template_xyz": [[round(float(v), 5) for v in p] for p in tmpl],
            # fingertip distances from the wrist: a compact, human-checkable signature.
            # a fist should read ~0.6-0.9, a flat hand ~1.7-2.2, in palm lengths.
            "tip_distances": {n: round(float(np.linalg.norm(tmpl[t, :2])), 3)
                              for n, t in zip(("thumb", "index", "middle", "ring", "pinky"),
                                              TIPS)},
        })
        out["handshapes"][shape] = entry
        verdict = ("OK" if good else
                   "LOW-CONFIDENCE ANCHOR" if meta["conf"] != "high" else
                   "TAKES DISAGREE — do not ship")
        print(f"{shape:6} {len(S):6} {ag_xy:9.3f} {ag_xyz:10.3f} {meta['conf']:>5}  {verdict}")

    out["n_usable"] = usable
    # Resolve every shape to something drawable, so the renderer never has to invent a
    # policy. A shape is either its own measured template, a NAMED fallback, or explicitly
    # unresolved — and the third case is the one the animation side must be told about.
    out["resolution"] = {}
    for shape, meta in ANCHORS.items():
        e = out["handshapes"].get(shape, {})
        if e.get("usable"):
            out["resolution"][shape] = {"use": shape, "why": "measured template"}
        elif meta.get("fallback") and out["handshapes"].get(meta["fallback"], {}).get("usable"):
            out["resolution"][shape] = {
                "use": meta["fallback"],
                "why": f"{shape} not measurable from this vocabulary "
                       f"({e.get('reason') or 'takes disagree'}); "
                       f"{meta['fallback']} substituted — documented approximation"}
        else:
            out["resolution"][shape] = {"use": None, "why": "unresolved — relaxed curl"}
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"\n[ok] {usable}/{len(ANCHORS)} templates usable -> {args.out}")
    print("\nRESOLUTION — what the renderer draws for each unmarked handshape")
    for shape, r in out["resolution"].items():
        tag = shape if r["use"] == shape else (f"-> {r['use']}" if r["use"] else "-> NONE")
        print(f"  {shape:3} {tag:9} {r['why']}")
    print("\nFINGERTIP SIGNATURE (distance from wrist, palm lengths — eyeball these)")
    print("  a fist should be ~0.6-0.9, a flat hand ~1.7-2.2, a single point mixed")
    for shape, e in out["handshapes"].items():
        if "tip_distances" in e:
            t = e["tip_distances"]
            print(f"  {shape}: " + "  ".join(f"{k[:3]} {v:.2f}" for k, v in t.items())
                  + f"    <- {e['description'][:44]}")
    bad = [s for s, e in out["handshapes"].items() if not e.get("usable")]
    if bad:
        print(f"\n[warn] NOT usable: {bad}")
        print("  The animation side keeps a relaxed curl for these. Say so explicitly rather "
              "than shipping a template nobody checked.")


if __name__ == "__main__":
    main()
