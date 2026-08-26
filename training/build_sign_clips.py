#!/usr/bin/env python3
r"""
Build the SPEECH->SIGN animation clip dictionary (Phase 3, SIGN_ANIMATION_CONTRACT).

The avatar is driven by LANDMARK PLAYBACK, and we already have landmark sequences
for every sign (the recognition training data). This script picks ONE exemplar clip
per word and writes a dictionary the renderer can play:

  word -> (T, 75, 3) landmark clip, shoulder-centered (contract §3), NATIVE length

REWRITTEN 2026-08-10 after the animation-side audit. The previous version had three
defects that compounded into one bad deliverable:

  1. "Cleanest" was measured with np.isfinite(), but the corpus encodes a MISSING
     landmark as exact 0.0 (training/README.md), and isfinite(0.0) is True. 238 of
     250 clips scored a perfect 1.0, so `pres > best[w][0]` never fired and this
     script silently shipped "the first clip in manifest order" for every word.
     The `pres < 0.5` warning could not trigger, which is why it reported 250/250
     clean. See sign_landmarks.py for the full write-up.
  2. Presence was OR-ed across BOTH hands, so a tracked resting hand hid an absent
     signing hand — and because the tracker drops the hand that MOVES, maximizing
     presence actively prefers the clip where the signer moved LEAST.
  3. Clips were pulled through make_tf_dataset(), which resamples every one to
     MAX_LEN=64, destroying native duration. Duration carries aspect, emphasis and
     repetition, so that is a real linguistic channel and not cosmetic.

Now: score REQUIRED-HAND COVERAGE (a one-handed sign needs its signing hand; a
two-handed sign needs both), read the native-length arrays directly, and record the
true motion extent. The score is the same quantity the animation side's
check-export.py reports, so both sides optimize and measure one number.

RUN (in the training env with the S3 data, i.e. the Kaggle GPU notebook):
  cd training
  python build_sign_clips.py --data-dir /kaggle/input/.../data --vocab ../vocab_250.json \
      --out ../sign_clips_250.npz
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
# sign_landmarks.py sits at the repo root in a checkout, but Kaggle notebooks stage every
# script FLAT into /kaggle/working — so try both, own-directory first.
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(_HERE))
if not (REPO / "vocab_250.json").exists() and (_HERE / "vocab_250.json").exists():
    REPO = _HERE                                           # keeps --vocab/--out defaults usable

from train import load_dataset                             # noqa: E402
from sign_landmarks import (                               # noqa: E402
    DOMINANT_WEIGHT, N_POINTS, PASSIVE_WEIGHT, TWO_HANDED_RATIO,
    L_HAND, R_HAND, POSE_L_SHOULDER, POSE_R_SHOULDER, POSE_L_WRIST, POSE_R_WRIST,
    canonicalize_missing, hand_arm_alignment, hand_coverage, hand_coverage_runs,
    mirror_match, motion_extent, pearson, required_hand_coverage, wrist_travel,
)

MIN_FRAMES = 8
# Reject candidates far shorter than the word's own median. Coverage is a FRACTION, so a
# truncated take reaches 1.000 trivially — 15 of the 250 first-attempt picks were under
# 12 frames (0.4 s) for exactly this reason.
LENGTH_FLOOR_FRAC = 0.60

# ── v7: handedness comes from a LEXICON, not from the landmarks ────────────────────────
# Measured 2026-08-11, four candidate classifiers against 40 hand-labelled words:
#     wrist path-length ratio   AUC 0.335   <- INVERTED, one-handed signs score HIGHER
#     spatial-extent ratio      AUC 0.460
#     passive-wrist height      AUC 0.468
#     weaker-hand presence      AUC 0.500   <- 0.000 for every word, both classes
# The whole 250-word ratio distribution sits inside 0.377-0.595: every word converging on
# one value, which is what a statistic with no word-level signal looks like. Root cause:
# GISLR records ONE hand per participant (both hands live in 1.7% of clips, both-hand
# frames mean 0.1%, and 14/21 participants have every clip single-handed), so there is no
# second hand to measure. Handedness is therefore supplied as lexical knowledge.
LEXICON_NAME = "asl_handedness_250.json"

# ── VALIDITY: the animation side's travel ratio, doing the job it CAN do ───────────────
# Their ratio failed as a classifier because it was asked to INFER handedness. Given
# handedness externally, the same number becomes a weak-drop detector: a take whose arms
# contradict the sign's known structure is a bad production, not a bad sign.
#
# Weak drop is a productive ASL process — signers routinely drop the passive hand in
# casual signing — and GISLR is crowd-sourced caretaker signing, so it is everywhere.
# They measured it on the shipped export without naming it: owl 0.27, stairs 0.20,
# tiger 0.28, alligator 0.54, all on signs where both hands must move.
#
# CALIBRATED 2026-08-12 against the animation side's suspect-clips.csv (250 words, armRatio
# per word). That data killed the first version of these rules:
#
#     class     n      p5     p25  median     p75     p95
#     1       163   0.106   0.210   0.387   0.626   0.845
#     2s       52   0.145   0.366   0.542   0.851   0.971
#     2a       35   0.123   0.250   0.535   0.679   0.832
#
# 2s median 0.542 vs 2a median 0.535 — statistically identical. So the arm-travel ratio
# CANNOT be used to police asymmetric signs, and we had written opposite rules from it:
# ours rejected 2a above 0.55 (expecting a static base), theirs flagged 2a below 0.35
# ("barely moves"). Both wrong, because travel cannot separate "static base held up in
# signing space" from "arm hanging at rest" — and those are precisely the two cases.
#
# So: travel gates only the classes where it has signal, and HEIGHT does the rest.
#   1  -> travel ceiling  (their 0.85 == our 0.85, and one-handed p95 is 0.845)
#   2s -> travel floor (both arms must move) AND the passive hand must be up
#   2a -> height only: is the base HELD, or is the arm hanging?
SYM_MIN_PASSIVE_RATIO = 0.50    # 2s: between their 0.35 and our first 0.60; tunable per run
ONE_MAX_PASSIVE_RATIO = 0.85    # 1 : both agree, and it sits exactly at one-handed p95
# MIRROR_MIN is a DIAGNOSTIC, not a gate. Symmetric signs come in simultaneous and
# ALTERNATING forms (`stairs` alternates), and an alternating take has both arms moving
# equally but out of phase — it scores ~0 on the mirror test while being perfectly good.
# Gating on it would throw away every alternating sign. Reported so the trend is visible.
MIRROR_TOL = 0.25               # shoulder-widths; how close counts as a mirror image


def normalize_clip(clip: np.ndarray) -> np.ndarray:
    """Shoulder-center + shoulder-width scale on x,y per frame (contract §3).

    Idempotent — the corpus is already normalized, so this is a near no-op and is
    safe to always apply. NaN is preserved: an absent point stays absent rather
    than being dragged to the origin, which is the bug that shipped 19,002
    hand blocks as [0,0,0].
    """
    out = clip.copy().astype(np.float32)
    for t in range(out.shape[0]):
        ls, rs = out[t, POSE_L_SHOULDER, :2], out[t, POSE_R_SHOULDER, :2]
        if np.isnan(ls).any() or np.isnan(rs).any():
            continue
        mid = (ls + rs) / 2.0
        width = float(np.linalg.norm(ls - rs))
        if width < 1e-6:
            continue
        out[t, :, :2] = (out[t, :, :2] - mid) / width
    return out


def main():
    ap = argparse.ArgumentParser(description="Build the per-word animation clip dictionary")
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="dataset root (has split_manifest.parquet + by_word/)")
    ap.add_argument("--vocab", type=Path, default=REPO / "vocab_250.json",
                    help="frozen class-order vocab (must match the model)")
    ap.add_argument("--out", type=Path, default=REPO / "sign_clips_250.npz")
    ap.add_argument("--fps", type=int, default=30, help="playback fps written to meta")
    ap.add_argument("--fixed-frames", type=int, default=0,
                    help="resample every clip to N frames (0 = keep NATIVE length, "
                         "which is what the animation contract now asks for)")
    ap.add_argument("--lexicon", type=Path, default=None,
                    help=f"per-word handedness table (default: {LEXICON_NAME} beside the vocab). "
                         "Handedness is NOT inferable from these landmarks — see the module "
                         "header for the four AUCs. Pass --lexicon '' to fall back to the v6 "
                         "landmark inference, which is kept only for reproducing old runs.")
    ap.add_argument("--validity", choices=["on", "off"], default="on",
                    help="'on': reject takes whose arm motion contradicts the sign's known "
                         "structure (weak drop). 'off' reproduces v6 exactly.")
    ap.add_argument("--sym-min-ratio", type=float, default=SYM_MIN_PASSIVE_RATIO,
                    help="two-handed SYMMETRIC: minimum passive/dominant arm-travel ratio")
    ap.add_argument("--one-max-ratio", type=float, default=ONE_MAX_PASSIVE_RATIO,
                    help="ONE-handed: maximum ratio before the take looks two-handed")
    ap.add_argument("--require-signing-hand", choices=["on", "off"], default="on",
                    help="reject takes whose tracked hand block belongs to the STILL arm "
                         "(hand landmark 0 co-located with the non-travelling pose wrist). "
                         "v7.1 without this gate shipped 249/250 exemplars carrying the "
                         "resting hand. 'off' only to reproduce that.")
    ap.add_argument("--require-passive-up", choices=["on", "off", "2s-only"], default="on",
                    help="'on': two-handed words need the passive wrist HELD in signing space, "
                         "not hanging. This is the only test that separates an asymmetric "
                         "sign's static base from a dropped arm — arm travel cannot (2s and "
                         "2a have identical travel distributions). "
                         "'2s-only': skip the gate for 2a. MEASURED 2026-08-14: this gate is the "
                         "sole reason two-handed words are starved — class 1 returns before it "
                         "and keeps 49.0%% of takes (median 138 valid), while 2s keeps 1.2%% "
                         "(median 3) and 2a keeps 2.1%% (median 5). Do NOT read the pooled "
                         "corr(valid_candidates, coverage) = +0.804 as causal: WITHIN class it is "
                         "only +0.218 (class 1, n=163), +0.244 (2s), +0.443 (2a), so the pooled "
                         "figure is mostly the between-class contrast. Class-1 words never fall "
                         "below 73 valid takes yet still span 0.56-1.00 coverage, so pool size "
                         "alone does not buy coverage. This flag rests on MECHANISM, not on that "
                         "correlation: for 2a the gate "
                         "protects the recorded passive WRIST POSITION, which is measured at a "
                         "median 1.56 shoulder widths from the dominant wrist and is therefore "
                         "replaced synthetically by the passiveBase lexicon — so on 2a it "
                         "sacrifices ~98%% of the candidate pool to preserve a quantity that is "
                         "discarded downstream. 'off' also drops it for 2s, where the passive "
                         "wrist IS used (the handshape is mirrored onto a recorded wrist), so "
                         "that is a real trade and wants a render comparison first.")
    ap.add_argument("--dump-candidates", type=Path, default=None,
                    help="write one CSV row per CANDIDATE (not per word) to this path: word, "
                         "class, aligned, passive_resting, coverage, valid, reason. The per-word "
                         "meta records only the take that WON, so it cannot answer why. Two "
                         "questions need the losers: (a) does the passive-up gate discard "
                         "better-tracked takes, i.e. is dominant coverage higher among "
                         "passive_resting takes -- which decides the 2a experiment BEFORE the "
                         "test arm runs, from the control arm alone; and (b) what actually "
                         "rejects each take, since the per-word invalid_reason is null whenever "
                         "the word found any valid take at all. ~70k rows, ~4 MB.")
    ap.add_argument("--contiguity", type=float, default=0.0,
                    help="weight w in (1-w)*coverage + w*longest_contiguous_run. The animation "
                         "side bridges gaps by interpolation, so a bridged handshape is a "
                         "straight line between two real ones: 30 frames spanning the stroke "
                         "beat 30 scattered. 0.0 = pure coverage (v7 behaviour), 0.5 = even mix.")
    ap.add_argument("--travel-floor", choices=["median", "none"], default="median",
                    help="'median': only consider candidates whose dominant-wrist travel is "
                         ">= that word's median before maximizing coverage. Guards against "
                         "argmax(coverage) degenerating into argmax(stillness), since the "
                         "tracker keeps the hand that held still. 'none' = pure argmax.")
    args = ap.parse_args()

    frozen = json.loads(args.vocab.read_text(encoding="utf-8"))
    words = frozen["words"] if isinstance(frozen, dict) else frozen
    vocab = {"words": words, "word_to_index": {w: i for i, w in enumerate(words)},
             "num_classes": len(words), "note": "frozen 250 order (build_sign_clips)"}
    print(f"[cfg] {len(words)} words from {args.vocab.name}")

    # ── the handedness lexicon ────────────────────────────────────────────────────────
    lex_path = args.lexicon
    if lex_path is None:
        for cand in (REPO / LEXICON_NAME, _HERE / LEXICON_NAME):
            if cand.exists():
                lex_path = cand
                break
    lex, lex_conf = {}, {}
    if lex_path and str(lex_path) and Path(lex_path).exists():
        blob = json.loads(Path(lex_path).read_text(encoding="utf-8"))["words"]
        lex = {w: v[0] for w, v in blob.items()}
        lex_conf = {w: (v[1] if len(v) > 1 else "?") for w, v in blob.items()}
        absent = [w for w in words if w not in lex]
        assert not absent, f"lexicon is missing {len(absent)} vocab words: {absent[:8]}"
        n = {c: sum(1 for w in words if lex[w] == c) for c in ("1", "2s", "2a")}
        print(f"[cfg] handedness from {Path(lex_path).name}: "
              f"{n['1']} one-handed, {n['2s']} two-handed symmetric, {n['2a']} asymmetric "
              f"({n['2s'] + n['2a']} two-handed)")
    else:
        print("[warn] NO LEXICON — falling back to v6 landmark inference, which was measured "
              "at AUC 0.335 (inverted). Results are not trustworthy; this path exists only to "
              "reproduce old runs.")

    man, arrays = load_dataset(args.data_dir, vocab)
    if "is_outlier" in man.columns:
        man = man[~man["is_outlier"]]
    man = man.reset_index(drop=True)                        # any split — more clips to choose from

    # ── is this the canonical corpus? ─────────────────────────────────────────────────
    # extract_canonical.py parks the DOMINANT hand at 54-74 always and leaves 33-53 NaN.
    # On that layout the dominant BLOCK is R by construction, so coverage must be read from
    # R — deriving it from wrist travel instead would read the empty block whenever travel
    # disagrees with the mirror decision, and score a hard 0.000.
    probe = [np.asarray(arrays[k], np.float32) for k in list(arrays)[:300]]
    left_dead = sum(1 for a in probe if np.isnan(a[:, L_HAND, :2]).all()) / max(1, len(probe))
    canonical = left_dead > 0.99
    print(f"[cfg] corpus layout: {'CANONICAL (dominant hand @54-74)' if canonical else 'LEGACY (L@33-53, R@54-74)'}"
          f"   [left block empty in {left_dead*100:.0f}% of a 300-clip probe]")
    print(f"[cfg] scanning {len(man)} clips for the best exemplar per word "
          f"(metric: dominant-hand coverage inside the sign extent)")

    # ── PASS 1: measure every candidate, keep SCALARS ONLY (83k clips will not fit) ──
    # NOTE: no score yet. Scoring needs the word's handedness, and deciding that from
    # the clip being scored is circular — see required_hand_coverage's docstring.
    # Coverage is measured inside the sign extent, not across the whole window: 30
    # tracked frames on the stroke beat 30 scattered through a rest hold.
    stats: dict[str, dict] = {}                             # clip key -> measurements
    by_word: dict[str, list] = {}                           # word -> [clip keys]
    skipped = 0

    for key, word in zip(man["key"].tolist(), man["word"].tolist()):
        a = arrays.get(key)
        if a is None or a.shape[0] < MIN_FRAMES:
            skipped += 1
            continue
        clip = canonicalize_missing(np.asarray(a, dtype=np.float32))
        extent = motion_extent(clip)
        info = required_hand_coverage(clip, extent, two_handed=None)   # per-clip: diagnostic only
        info["extent"] = extent
        info["frames"] = int(clip.shape[0])
        # longest CONTIGUOUS covered run — the animation side interpolates across gaps, so a
        # bridged handshape is a straight line between two real ones (their 2026-08-12 note)
        info["runs"] = hand_coverage_runs(clip, extent)
        # are both wrists mirror images? diagnostic only — alternating symmetric signs
        # (`stairs`) score ~0 here while being perfectly good takes
        info["mirror"] = mirror_match(clip, MIRROR_TOL)
        # is the tracked hand the SIGNING hand, or the resting one the tracker kept?
        # This is a GATE, not a diagnostic — v7.1 shipped 249/250 exemplars carrying the
        # wrong hand because coverage alone cannot tell those two cases apart.
        info["align"] = hand_arm_alignment(clip)
        stats[key] = info
        by_word.setdefault(word, []).append(key)

    # ── decide handedness ONCE PER WORD, across all of its candidates ──────────────
    # A single take cannot be trusted: if one hand was never detected its arm is still,
    # the take self-reports as one-handed, and the requirement collapses to the one hand
    # it happens to have. Aggregating over ~287 candidates removes that freedom.
    # Dominant SIDE stays per-candidate — signers are 131 left / 119 right in this corpus
    # and the animation side normalizes chirality downstream.
    word_ratio = {w: round(float(np.median([stats[k]["travel_ratio"] for k in keys])), 3)
                  for w, keys in by_word.items()}
    if lex:
        word_class = {w: lex[w] for w in by_word}
    else:                                                   # v6 fallback, AUC 0.335
        word_class = {w: ("2s" if word_ratio[w] >= TWO_HANDED_RATIO else "1") for w in by_word}
    word_two_handed = {w: word_class[w] != "1" for w in by_word}
    HAND_NAME = {"1": "one-handed", "2s": "two-handed symmetric",
                 "2a": "two-handed asymmetric"}

    def dom_block(key: str) -> str:
        """Which hand BLOCK actually holds the signing hand."""
        # On the canonical corpus that is R by construction. Deriving it from wrist travel
        # there would read the empty block whenever travel disagrees with the mirror
        # decision — and score a hard 0.000 on a perfectly good clip.
        return "R" if canonical else stats[key]["dominant"]

    def score_of(key: str, word: str) -> float:
        """Dominant-hand coverage inside the sign extent, optionally blended with contiguity.

        No longer 0.7*dom + 0.3*passive. The passive HAND does not exist in this corpus for
        any word — GISLR records one hand per participant — so the passive term is a
        constant 0 on every candidate and merely rescales the score. Keeping it in made the
        numbers unreadable: it is why "required-hand coverage 0.999" looked like success
        when what it measured was one hand out of a required one hand.
        """
        d = dom_block(key)
        cov = stats[key]["coverage"][d]
        if args.contiguity <= 0.0:
            return cov
        return (1.0 - args.contiguity) * cov + args.contiguity * stats[key]["runs"][d]

    def validity(key: str, word: str) -> tuple[bool, str]:
        """Does this take's ARM behaviour match the sign's KNOWN structure? (weak-drop filter)

        Handedness comes from the lexicon, so these measurements no longer have to *infer*
        structure — they only have to check a take against it. Each class is policed by the
        signal that actually separates it, which is not the same signal for all three:

          1   travel CEILING. Both arms equally active on a one-handed sign is a different
              failure from weak drop; the animation side found cat/eye/mouse this way.
          2s  travel FLOOR (both arms must move) plus the passive hand must be up.
          2a  HEIGHT ONLY. A static base has near-zero travel BY DEFINITION, so a travel
              rule here is either vacuous or backwards — we and the animation side wrote it
              in opposite directions and their armRatio data (2s median 0.542 vs 2a median
              0.535) shows neither could have worked. The real question for 2a is whether
              the passive hand is HELD in signing space or HANGING, which is a position
              measurement, not a motion one.
        """
        if args.validity == "off" or not lex:
            return True, ""
        # ── gate 0, and it outranks every rule below ──────────────────────────────────
        # A take whose tracked hand belongs to the STILL arm carries the resting hand's
        # 21 landmarks under a signing label. No handedness rule can rescue that, and
        # coverage actively rewards it (the tracker keeps the hand that does not move).
        # Safe as a hard gate: every one of the 250 words has >=55 aligned takes.
        if args.require_signing_hand == "on" and not stats[key]["align"]["aligned"]:
            return False, "tracked hand is on the STILL arm — resting hand, not the signing hand"
        r, cls = stats[key]["travel_ratio"], word_class[word]
        if cls == "1":
            if r > args.one_max_ratio:
                return False, "both arms active on a one-handed sign"
            return True, ""
        # two-handed: the passive hand has to be in signing space, whatever it is doing there.
        # '2s-only' exempts 2a because the passive wrist it protects is discarded downstream —
        # see the --require-passive-up help for the measurements behind that.
        gate_on = (args.require_passive_up == "on"
                   or (args.require_passive_up == "2s-only" and cls == "2s"))
        if gate_on and stats[key]["passive_resting"] is True:
            return False, ("passive arm hanging at rest — no base (2a)" if cls == "2a"
                           else "passive arm hanging at rest — weak drop (2s)")
        if cls == "2s" and r < args.sym_min_ratio:
            return False, "weak drop: passive arm barely moves on a symmetric sign"
        return True, ""

    for w, keys in by_word.items():
        for k in keys:
            ok, why = validity(k, w)
            stats[k]["score"] = score_of(k, w)
            stats[k]["valid"], stats[k]["invalid_reason"] = ok, why
            stats[k]["class"] = word_class[w]
            stats[k]["handedness"] = HAND_NAME[word_class[w]]
            stats[k]["required"] = dom_block(k)

    # ── optional per-CANDIDATE dump ───────────────────────────────────────────────
    # Written here, after validity() has run on every take and before pick() throws the
    # losers away. The per-word meta only ever describes the winner, which makes the one
    # question that decides the 2a experiment unanswerable from it: among the takes the
    # passive-up gate REJECTS, is dominant coverage higher or lower than among the ones it
    # keeps? Higher means the gate is discarding the better-tracked takes and dropping it
    # should help; lower or equal means the corpus has no better take and tier C is real.
    # That is readable from the CONTROL arm alone, so it predicts the result rather than
    # merely explaining it afterwards.
    if args.dump_candidates is not None:
        import csv
        args.dump_candidates.parent.mkdir(parents=True, exist_ok=True)
        with open(args.dump_candidates, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["word", "class", "key", "frames", "aligned", "passive_resting",
                         "dominant_travel", "travel_ratio", "coverage", "longest_run",
                         "valid", "reason"])
            for w, keys in by_word.items():
                for k in keys:
                    s = stats[k]
                    wr.writerow([
                        w, s["class"], k, s["frames"],
                        int(bool(s["align"]["aligned"])),
                        # tri-state on purpose: None means "not measurable on this take"
                        # (no passive wrist tracked at all), which is NOT the same as False
                        # and must not silently join the "held up" group.
                        "" if s["passive_resting"] is None else int(s["passive_resting"]),
                        round(float(s["dominant_travel"]), 4),
                        round(float(s["travel_ratio"]), 4),
                        round(float(s["score"]), 4),
                        round(float(s["runs"][s["required"]]), 4),
                        int(bool(s["valid"])), s["invalid_reason"] or "",
                    ])
        n_rows = sum(len(v) for v in by_word.values())
        print(f"[ok] per-candidate dump: {n_rows} rows -> {args.dump_candidates}")

    # ── the animation side's §3 diagnostic ────────────────────────────────────────
    # WITHIN a word, is coverage anti-correlated with motion? That is the only level
    # where "different signs have different inherent speeds" is not a confound, and it
    # decides whether maximizing coverage is secretly maximizing stillness.
    per_word_r = {}
    for w, keys in by_word.items():
        if len(keys) < 3:
            continue
        per_word_r[w] = pearson([stats[k]["score"] for k in keys],
                                [stats[k]["dominant_travel"] for k in keys])
    rs = np.array([v for v in per_word_r.values() if np.isfinite(v)], dtype=float)

    # ── resolve BOTH strategies from the scalars, so the A/B costs nothing ─────────
    def pick(keys, floor: bool):
        cand = keys
        # VALIDITY first: a take that contradicts the sign's structure is the wrong take, no
        # matter how well tracked it is. `or cand` because a word must never be stranded —
        # if every candidate is a weak drop we still ship the best-covered one and SAY SO.
        valid = [k for k in cand if stats[k]["valid"]]
        cand = valid or cand
        # LENGTH floor always applies. Coverage is a FRACTION, so a truncated 8-frame
        # take reaches 1.000 trivially; without this the selector trades
        # argmax(stillness) for argmax(shortness).
        med_len = float(np.median([stats[k]["frames"] for k in keys]))
        long_enough = [k for k in cand
                       if stats[k]["frames"] >= max(MIN_FRAMES, LENGTH_FLOOR_FRAC * med_len)]
        cand = long_enough or cand
        if floor:
            tv = [stats[k]["dominant_travel"] for k in cand]
            med = float(np.median(tv))
            kept = [k for k in cand if stats[k]["dominant_travel"] >= med]
            cand = kept or cand                             # never strand a word
        return max(cand, key=lambda k: stats[k]["score"])

    winners = {"none": {}, "median": {}}
    for w, keys in by_word.items():
        winners["none"][w] = pick(keys, floor=False)
        winners["median"][w] = pick(keys, floor=True)

    chosen = winners[args.travel_floor]

    out_clips, meta_words, weak, missing_word = {}, [], [], []
    old_scores, new_scores = [], []
    for w in words:                                         # keep frozen order
        if w not in chosen:
            missing_word.append(w)
            continue
        key = chosen[w]
        info = stats[key]
        # OLD selector's pick == first clip in manifest order (it scored every clip 1.0)
        old_scores.append(stats[by_word[w][0]]["score"])
        new_scores.append(info["score"])

        clip = canonicalize_missing(np.asarray(arrays[key], dtype=np.float32))
        clip = normalize_clip(clip)
        if args.fixed_frames > 0:
            from train import time_resize
            clip = time_resize(clip, args.fixed_frames)
        start, end = motion_extent(clip)
        out_clips[w] = clip
        cls = word_class[w]
        n_valid = sum(1 for k in by_word[w] if stats[k]["valid"])
        meta_words.append({
            "word": w, "source_clip": key, "candidates": len(by_word[w]),
            "frames": int(clip.shape[0]), "sign_start": start, "sign_end": end,
            "dominant_hand_coverage": round(float(info["score"]), 3),
            # kept under the old key too so check-export.py and the renderer don't break
            "required_hand_coverage": round(float(info["score"]), 3),
            "handedness": info["handedness"], "required_hand": info["required"],
            "handedness_class": cls,
            "handedness_confidence": lex_conf.get(w, "inferred"),
            # what the RENDERER must do about the passive hand. The passive hand's landmarks
            # are absent from every take, but its WRIST is a pose landmark and is present, so
            # only the handshape needs synthesizing — never the position.
            "synthesis": {"1": None, "2s": "mirror_dominant_handshape",
                          "2a": "unmarked_handshape_at_base"}[cls],
            "passive_wrist_available": True,
            "valid_candidates": n_valid,
            "validity_fallback": n_valid == 0,
            "invalid_reason": info.get("invalid_reason") or None,
            # longest contiguous covered run, for their interpolation-bridging concern
            "longest_run": round(float(info["runs"][info["required"]]), 3),
            # both wrists mirror-imaged? diagnostic: alternating symmetric signs score ~0
            "mirror_match": (round(float(info["mirror"]), 3)
                             if np.isfinite(info["mirror"]) else None),
            "dominant": info["dominant"],
            # Is the exported hand the SIGNING hand? v7.1 emitted required_hand "R" beside
            # dominant "L" on all 250 words and nothing compared the two adjacent fields;
            # geometry then showed the hand glued to the still arm in 249/250. These make
            # the answer explicit instead of inferable, so the renderer can assert on it.
            "signing_hand_verified": bool(info["align"]["aligned"]),
            "signing_hand_available": bool(any(stats[k]["align"]["aligned"]
                                               for k in by_word[w])),
            "tracked_hand_on_arm": info["align"]["belongs"],
            "moving_arm": info["align"]["moving"],
            "wrist_colocation": {
                "L": (round(info["align"]["d_L"], 3)
                      if np.isfinite(info["align"]["d_L"]) else None),
                "R": (round(info["align"]["d_R"], 3)
                      if np.isfinite(info["align"]["d_R"]) else None)},
            "clip_travel_ratio": info["travel_ratio"],
            # the WORD-level verdict (median over all candidates) that drove scoring —
            # not this clip's own ratio, which would be circular
            "word_travel_ratio": word_ratio[w],
            "passive_resting": info["passive_resting"],
            "coverage": info["coverage"],
            "within_word_r": (round(per_word_r[w], 3) if w in per_word_r
                              and np.isfinite(per_word_r.get(w, float("nan"))) else None),
        })
        if info["score"] < 0.5:
            weak.append(w)

    np.savez_compressed(args.out, **out_clips)
    lens = [int(c.shape[0]) for c in out_clips.values()]
    scores = np.array([m["required_hand_coverage"] for m in meta_words], dtype=float)
    meta = {
        "schema": "sign-animation/v2", "fps": args.fps,
        "coord_space": "shoulder-centered",
        "missing_encoding": "null (NaN in the npz) — never zeros; see sign_landmarks.py",
        "n_words": len(out_clips),
        "layout": "0-32 pose, 33-53 left hand, 54-74 right hand; (T,75,3)",
        "selection_metric": ("DOMINANT-hand coverage inside the sign extent. The passive hand "
                             "is absent from this corpus for every word, so a passive term "
                             "would be a constant 0 and only rescale the score."),
        "travel_floor": args.travel_floor,
        "length_floor_frac": LENGTH_FLOOR_FRAC,
        "handedness_decided": (f"LEXICON {Path(lex_path).name}" if lex else
                               "v6 landmark inference (AUC 0.335 — untrustworthy)"),
        "handedness_classes": {"1": "one-handed",
                               "2s": "two-handed symmetric — mirror the dominant handshape",
                               "2a": "two-handed asymmetric — unmarked handshape at the base"},
        "corpus_layout": "canonical (dominant hand @54-74)" if canonical else "legacy (L@33-53, R@54-74)",
        "all_exemplars_right_dominant": bool(canonical),
        "passive_hand_absent_by_source": (
            "GISLR records ONE hand per participant: both hands live in 1.7% of clips, "
            "both-hand frames mean 0.1% / max 4.8%, 14/21 participants single-handed "
            "throughout. Measured against the raw competition parquets on 2026-08-11. The "
            "passive hand cannot be selected for; it must be synthesized. Its WRIST is a "
            "pose landmark and IS present every frame, so only the handshape is missing."),
        "validity_filter": {
            "enabled": args.validity == "on" and bool(lex),
            "purpose": "reject weak-drop takes — a take contradicting the sign's known structure",
            "rules": {
                "1": f"reject if passive/dominant arm-travel ratio > {args.one_max_ratio}",
                "2s": f"reject if ratio < {args.sym_min_ratio} OR the passive wrist is hanging",
                "2a": ("reject only if the passive wrist is hanging — a static base has "
                       "near-zero travel by definition, so travel cannot police 2a"
                       if args.require_passive_up == "on" else
                       "NO validity gate — the passive-up test is skipped for 2a because the "
                       "recorded passive wrist it protects (median 1.56 shoulder widths from the "
                       "dominant wrist) is replaced synthetically by the passiveBase lexicon. "
                       "Selection is on dominant-hand coverage alone."),
            },
            "passive_up_gate_note": (
                "This gate is the sole cause of the two-handed candidate starvation measured "
                "2026-08-14: class 1 returns before it and keeps 49.0% of takes (median 138 "
                "valid); 2s keeps 1.2% (median 3) and 2a keeps 2.1% (median 5). "
                "Pooled corr(valid_candidates, coverage) = +0.804 across 250 words, but that is "
                "mostly between-class: within class it is +0.218 / +0.244 / +0.443 for 1 / 2s / 2a, "
                "and class-1 words span 0.56-1.00 coverage while never dropping below 73 valid "
                "takes. Pool size is not established as the cause of low coverage."),
            "sym_min_ratio": args.sym_min_ratio,
            "one_max_ratio": args.one_max_ratio,
            "require_passive_up": args.require_passive_up,
            "contiguity_weight": args.contiguity,
            "calibrated_against": ("the animation side's suspect-clips.csv, 2026-08-12. Their "
                                  "armRatio percentiles gave 2s median 0.542 vs 2a median "
                                  "0.535 — identical — which is why the first version's 2a "
                                  "travel rule was dropped rather than retuned."),
        },
        "n_two_handed_words": int(sum(word_two_handed.values())),
        "native_length": args.fixed_frames == 0,
        "within_word_coverage_vs_travel_r": {
            "mean": round(float(rs.mean()), 4) if rs.size else None,
            "median": round(float(np.median(rs)), 4) if rs.size else None,
            "frac_negative": round(float((rs < 0).mean()), 3) if rs.size else None,
            "n_words": int(rs.size),
        },
        "words": meta_words,
    }
    args.out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    counts = {w: len(k) for w, k in by_word.items()}
    old = np.array(old_scores, dtype=float)
    new = np.array(new_scores, dtype=float)
    alt = "none" if args.travel_floor == "median" else "median"
    alt_scores = np.array([stats[winners[alt][w]]["score"] for w in words if w in chosen])

    print(f"\n[ok] wrote {len(out_clips)} clips -> {args.out}")
    print(f"[ok] meta -> {args.out.with_suffix('.meta.json')}")
    if skipped:
        print(f"[cfg] skipped {skipped} clips shorter than {MIN_FRAMES} frames")

    n_two = int(sum(word_two_handed.values()))
    passive = np.array([min(m["coverage"]["L"], m["coverage"]["R"]) for m in meta_words])
    print(f"\nHANDEDNESS  ({'LEXICON — not inferred from landmarks' if lex else 'v6 INFERENCE — untrustworthy'})")
    for c in ("1", "2s", "2a"):
        k = [m for m in meta_words if m["handedness_class"] == c]
        if k:
            print(f"  {HAND_NAME[c]:26}: {len(k):3}"
                  + (f"   synthesis: {k[0]['synthesis']}" if k[0]["synthesis"] else ""))
    print(f"  two-handed total          : {n_two} / {len(word_two_handed)}")
    med = [m["word"] for m in meta_words if m["handedness_confidence"] == "med"]
    if med:
        print(f"  low-confidence labels     : {len(med)} awaiting review")

    # ── SIGNING HAND — the check that v7.1 did not have, and the one that can fail ────
    # v7.1 reported "dominant-hand coverage 0.962" while 249/250 exemplars carried the
    # RESTING hand. Coverage cannot distinguish those, so it was never evidence. This
    # block is the evidence, and the assert below is deliberately fatal: shipping the
    # wrong hand silently is strictly worse than not shipping.
    aligned = [m for m in meta_words if m["signing_hand_verified"]]
    print(f"\nSIGNING HAND  (hand landmark 0 co-located with the TRAVELLING pose wrist)")
    print(f"  exemplars carrying the SIGNING hand : {len(aligned)} / {len(meta_words)}")
    base_rate = np.mean([np.mean([stats[k]["align"]["aligned"] for k in ks])
                         for ks in by_word.values()])
    print(f"  base rate across all candidates     : {base_rate * 100:.1f}%   "
          f"(gate: {args.require_signing_hand})")
    coloc = np.array([m["wrist_colocation"][m["tracked_hand_on_arm"] or "R"]
                      for m in meta_words
                      if m["tracked_hand_on_arm"] and
                      m["wrist_colocation"][m["tracked_hand_on_arm"]] is not None], dtype=float)
    if coloc.size:
        print(f"  wrist co-location, own limb         : median {np.median(coloc):.3f} sh.w. "
              f"(a different limb measures ~1.0-2.0)")
    # "we could not" and "we did not" are different failures and must not share a message.
    # A word with no aligned take anywhere is a data limit to REPORT (the renderer needs to
    # know that word's handshape is untrustworthy). A word that had aligned takes and still
    # got an unaligned pick is a selector BUG, and that one is fatal.
    had_aligned = {w: any(stats[k]["align"]["aligned"] for k in ks) for w, ks in by_word.items()}
    bad = [m["word"] for m in meta_words if not m["signing_hand_verified"]]
    no_option = [w for w in bad if not had_aligned.get(w, False)]
    selector_bug = [w for w in bad if had_aligned.get(w, False)]
    if no_option:
        print(f"  [warn] {len(no_option)} words have NO aligned take in the whole corpus — "
              f"their handshape is the RESTING hand and cannot be fixed by selection:")
        print(f"         {no_option[:12]}")
    if args.require_signing_hand == "on" and args.validity == "on" and lex:
        assert not selector_bug, (
            f"{len(selector_bug)} words had aligned takes available and the selector still "
            f"picked an unaligned one: {selector_bug[:12]}. That is a selector bug, not a "
            f"data limit — do NOT ship this export.")

    if args.validity == "on" and lex:
        print(f"\nVALIDITY FILTER  (weak-drop rejection)")
        print(f"  rules: 1: ratio<={args.one_max_ratio} | 2s: ratio>={args.sym_min_ratio} "
              f"AND passive up | 2a: passive up only "
              f"(passive-up gate: {args.require_passive_up})")
        tot_c = sum(counts.values())
        tot_v = sum(m["valid_candidates"] for m in meta_words)
        print(f"  candidates rejected       : {tot_c - tot_v} / {tot_c} "
              f"({(tot_c - tot_v) / max(1, tot_c) * 100:.0f}%)")
        stranded = [m["word"] for m in meta_words if m["validity_fallback"]]
        print(f"  words with NO valid take  : {len(stranded)}"
              + (f"  {stranded[:10]}" if stranded else "   <- none stranded"))
        for c in ("1", "2s", "2a"):
            k = [m for m in meta_words if m["handedness_class"] == c]
            if k:
                vr = np.mean([m["valid_candidates"] / max(1, m["candidates"]) for m in k])
                print(f"    {HAND_NAME[c]:24}: {vr * 100:4.0f}% of candidates pass")
        # the animation side's per-frame weak-drop list (weakdrop.txt, 2026-08-12): the
        # worst 2s words in the v4 export, with the fraction of frames where the passive arm
        # actually performed the symmetric sign. Every one of these should now improve.
        THEIRS = {"awake": 0.00, "drawer": 0.00, "hate": 0.00, "loud": 0.00, "pool": 0.00,
                  "same": 0.00, "shoe": 0.00, "stairs": 0.00, "jeans": 0.01, "rain": 0.01,
                  "snow": 0.01, "bedroom": 0.03, "book": 0.18, "owl": 0.19, "tiger": 0.26,
                  "alligator": 0.13, "boat": 0.70, "sad": 0.68}
        watch = [m for m in meta_words if m["word"] in THEIRS]
        if watch:
            print(f"\n  THEIR worst weak-drop words (v4 mirrorPct -> our new pick):")
            print(f"    {'word':11} {'cls':4} {'theirs':>7} {'ratio':>6} {'mirror':>7} "
                  f"{'cov':>5} {'run':>5}  valid")
            for m in sorted(watch, key=lambda m: THEIRS[m["word"]]):
                mir = m.get("mirror_match")
                print(f"    {m['word']:11} {m['handedness_class']:4} "
                      f"{THEIRS[m['word']]*100:6.0f}% {m['clip_travel_ratio']:6.2f} "
                      f"{(f'{mir*100:6.0f}%' if mir is not None else '     -'):>7} "
                      f"{m['dominant_hand_coverage']:5.2f} {m.get('longest_run', 0):5.2f}  "
                      f"{m['valid_candidates']:3}/{m['candidates']:3}"
                      + ("  FALLBACK" if m["validity_fallback"] else ""))

    print(f"\nSELECTION  (travel-floor = {args.travel_floor}, length-floor = {LENGTH_FLOOR_FRAC})")
    print(f"  candidates per word     : median {int(np.median(list(counts.values())))} "
          f"(min {min(counts.values())}, max {max(counts.values())})")
    print(f"  DOMINANT-hand coverage  : mean {new.mean():.3f}  median {np.median(new):.3f}")
    print(f"  passive-hand coverage   : mean {passive.mean():.3f}  "
          f"zero for {int((passive == 0).sum())} / {len(passive)}"
          f"   <- EXPECTED ~all: absent at source, not selectable")
    print(f"  words at 0.00 coverage  : {int((new == 0).sum())} / {len(new)}")
    print(f"  words >= 0.70           : {int((new >= 0.70).sum())} / {len(new)}")
    print(f"  vs the OLD selector     : {new.mean() - old.mean():+.3f} mean "
          f"({old.mean():.3f} -> {new.mean():.3f}), improved {int((new > old).sum())} words")
    print(f"  vs travel-floor '{alt}'   : {new.mean() - alt_scores.mean():+.3f} mean "
          f"(that strategy would give {alt_scores.mean():.3f})")
    print(f"  clip length             : {min(lens)}-{max(lens)} frames"
          + ("  (NATIVE)" if args.fixed_frames == 0 else f"  (forced {args.fixed_frames})"))

    print(f"\nDIAGNOSTIC — within a word, is coverage anti-correlated with motion?")
    if rs.size:
        print(f"  pearson r over {rs.size} words : mean {rs.mean():+.3f}  median {np.median(rs):+.3f}")
        print(f"  words with r < 0             : {100 * (rs < 0).mean():.0f}%")
        verdict = ("STRONG — selecting on coverage IS selecting for stillness; keep the floor"
                   if rs.mean() < -0.20 else
                   "MILD — the floor is cheap insurance, keep it"
                   if rs.mean() < -0.05 else
                   "ABSENT — coverage and motion are independent here; --travel-floor none is safe")
        print(f"  verdict                      : {verdict}")
    else:
        print("  not enough candidates per word to measure")

    n_syn = sum(1 for m in meta_words if m["synthesis"])
    print(f"\nRENDERER CONTRACT")
    print(f"  words needing a synthesized passive hand : {n_syn} / {len(meta_words)}")
    print(f"    mirror the dominant handshape          : "
          f"{sum(1 for m in meta_words if m['synthesis'] == 'mirror_dominant_handshape')}"
          f"   (exact — Battison's Symmetry Condition)")
    print(f"    unmarked handshape at the base         : "
          f"{sum(1 for m in meta_words if m['synthesis'] == 'unmarked_handshape_at_base')}"
          f"   (7-item closed set — Dominance Condition)")
    print(f"  passive WRIST position available          : every frame (pose landmark)")
    if canonical:
        print(f"  all exemplars are RIGHT-dominant          : left-dominant signers were "
              f"mirrored at extraction, so dominantHand is no longer ambiguous")
    if weak:
        print(f"\n[warn] {len(weak)} words still below 0.50 required-hand coverage even after "
              f"picking the best of every candidate — these are a data limit, not a "
              f"selection one: {weak[:12]}")
    if missing_word:
        print(f"[warn] no usable clip at all for {len(missing_word)} words: {missing_word[:12]}")
    print("\n-> next: python gloss_to_motion.py --per-word --out-dir animation_handoff")


if __name__ == "__main__":
    main()
