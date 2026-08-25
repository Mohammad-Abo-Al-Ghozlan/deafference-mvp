#!/usr/bin/env python
"""Three cheap ideas for "it took me six tries", priced before any of them is built.

WHY
---
A webcam log (2026-08-25) has the signer producing `lips` six times -- conf 0.32, 0.16, 0.23,
0.22, 0.22, 0.21 -- and the demo throwing every attempt away, because commit_segment scores
each segment independently. Twenty-two segments produced eight commits. That is the actual
user complaint, and three fixes for it cost nothing but arithmetic:

  B. ACCUMULATE ACROSS ATTEMPTS. Average the probability vectors of consecutive attempts at the
     same sign instead of discarding the losers. Capture noise is independent between attempts
     and the sign is not, so the average should be cleaner than any single try.

  C. RE-RANK BY EXPECTED CORRECTNESS. The demo already loads word_acc_250.json. Ranking by
     conf * word_acc instead of conf alone should demote words that are historically wrong --
     `nap` at 0.109 should not outrank `sleep` at 0.714 on a near-tie.

  D. PER-WORD GATES. One threshold for `nose` (1.000) and `nap` (0.109) is indefensible.
     Demand more confidence from words known to be unreliable.

All three are HYPOTHESES. This session has already watched several plausible mechanisms fail
an intervention (clip-edge dilution -0.0011, tempo +0.019, oracle calibration -0.0018, and a
224-word curation that returned +0.014 against a predicted large gain), so none of them gets
built before it is measured.

HOW ATTEMPTS ARE SIMULATED (the honest caveat)
----------------------------------------------
A real second attempt is a fresh sign: different speed, different hand path, different
MediaPipe luck. That cannot be manufactured from one exemplar. What CAN be manufactured is the
dominant source of between-attempt variation at 7 fps -- WHICH FRAMES THE CAMERA HAPPENED TO
CATCH. Each simulated attempt subsamples the same 30 fps exemplar at a different phase offset,
so attempt 2 sees genuinely different frames of the same sign.

That makes this an OPTIMISTIC simulation of B: real attempts vary in more ways than phase, and
some of that extra variance is signal-destroying rather than independent noise. Read a positive
result here as "worth building and testing live", never as the live number.

USAGE
    python measure_recovery.py                      # all three, full 250
    python measure_recovery.py --attempts 5
    python measure_recovery.py --words topic_everyday.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import live_demo as ld
from sign_landmarks import canonicalize_missing

HERE = Path(__file__).resolve().parent
SRC_FPS = 30
GATES = (0.30, 0.40, 0.50, 0.58, 0.70, 0.80, 0.90)
V250 = dict(L1_CONF=0.58, L1_MARGIN=0.18, Q_STRONG=0.45, L2_CONF=0.40, L2_MARGIN=0.10)


def attempt_frames(arr: np.ndarray, live_fps: float, k: int, n_att: int) -> np.ndarray:
    """Attempt k of n_att: the same sign, but the camera caught different frames of it."""
    n = max(2, int(round(arr.shape[0] / SRC_FPS * live_fps)))
    span = arr.shape[0] - 1
    shift = (k / n_att) * span / max(n - 1, 1)          # sub-step phase offset
    idx = np.clip((np.linspace(0, span, n) + shift).round().astype(int), 0, span)
    return arr[idx]


def mask_renorm(p, allowed):
    if allowed is None:
        return p
    m = np.zeros_like(p)
    m[allowed] = p[allowed]
    s = m.sum()
    return m / s if s > 0 else p


def gate_pass(conf, second, q, t, margin_l1=V250["L1_MARGIN"], margin_l2=V250["L2_MARGIN"]):
    """decide_commit's LEVEL 1/2 arithmetic with both conf gates set to t."""
    margin = conf - second
    if conf >= t and margin >= margin_l1 and q >= V250["Q_STRONG"]:
        return True
    return conf >= t and margin >= margin_l2


def report(rows, label, n_total):
    """rows: list of (conf, second, q, ok)."""
    print(f"  {label:<28} ungated {sum(r[3] for r in rows)/len(rows):.3f}")
    print(f"    {'gate':>6} {'accept':>8} {'precision':>10}")
    for t in GATES:
        hit = [r for r in rows if gate_pass(r[0], r[1], r[2], t)]
        prec = sum(r[3] for r in hit) / len(hit) if hit else float("nan")
        print(f"    {t:>6.2f} {f'{100*len(hit)/n_total:.0f}%':>8} {prec:>10.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--acc", default=str(HERE / "word_acc_250.json"))
    ap.add_argument("--artifacts", default=str(HERE / "artifacts_250"))
    ap.add_argument("--words", default=None, help="optional topic mask to measure inside")
    ap.add_argument("--fps", type=float, default=7.0)
    ap.add_argument("--attempts", type=int, default=4, help="simulated repeats per sign")
    args = ap.parse_args()

    words = json.loads(Path(args.vocab).read_text(encoding="utf-8"))["words"]
    index = {w: i for i, w in enumerate(words)}
    wacc = json.loads(Path(args.acc).read_text(encoding="utf-8"))
    with np.load(args.clips) as z:
        clips = {w: canonicalize_missing(z[w].astype(np.float32))
                 for w in z.files if w in index}
    for k, v in V250.items():
        setattr(ld, k, v)
    dirs = [Path(args.artifacts) / f"savedmodel_fold{k}" for k in range(4)]
    _keep, fns = ld.load_models(dirs)
    assert ld.ALLOWED_IDX is None, "ALLOWED_IDX set; stored probs would be pre-masked"

    allowed = None
    if args.words:
        raw = json.loads(Path(args.words).read_text(encoding="utf-8"))
        allow = raw["words"] if isinstance(raw, dict) else raw
        allowed = np.array(sorted({index[w] for w in allow if w in index}), dtype=np.int64)
        keep = {words[i] for i in allowed}
        clips = {w: a for w, a in clips.items() if w in keep}
        print(f"[cfg] restricted to {len(allowed)} classes, {len(clips)} clips")

    A = args.attempts
    names = list(clips)
    print(f"[ok] {len(names)} words x {A} simulated attempts at {args.fps:.0f} fps "
          f"= {len(names)*A} forward passes\n")

    # P[i, k] = full prob vector for word i, attempt k.  Q likewise for segment quality.
    P = np.zeros((len(names), A, len(words)), dtype=np.float32)
    Q = np.zeros((len(names), A), dtype=np.float32)
    for i, w in enumerate(names):
        for k in range(A):
            seg = list(attempt_frames(clips[w], args.fps, k, A))
            P[i, k] = ld.classify_commit(fns, seg)
            Q[i, k] = ld.segment_quality(seg)[0]
        if i % 50 == 0:
            print(f"  {i}/{len(names)}")

    def rows_at(cum_k, use_rank=False, gate_shift=0.0):
        """Decision rows using the mean of the first cum_k attempts."""
        out = []
        for i, w in enumerate(names):
            p = mask_renorm(P[i, :cum_k].mean(0), allowed)
            if use_rank:
                # C: rank by expected correctness. Renormalized so `conf` stays a probability
                # and the same gates remain comparable.
                r = p * np.array([wacc.get(x, 0.5) for x in words], dtype=np.float32)
                s = r.sum()
                p = r / s if s > 0 else p
            o = np.argsort(p)[::-1]
            out.append((float(p[o[0]]), float(p[o[1]]), float(Q[i, :cum_k].mean()),
                        int(o[0] == index[w])))
        return out

    n = len(names)
    print("\n" + "=" * 74)
    print("B. ACCUMULATE ACROSS ATTEMPTS -- average the probs instead of discarding")
    print("=" * 74)
    for k in range(1, A + 1):
        report(rows_at(k), f"mean of {k} attempt(s)", n)
        print()

    first, best = rows_at(1), rows_at(A)
    for t in (0.58, 0.80, 0.90):
        f1 = {i for i, r in enumerate(first) if gate_pass(r[0], r[1], r[2], t)}
        fA = {i for i, r in enumerate(best) if gate_pass(r[0], r[1], r[2], t)}
        rescued = [i for i in fA - f1 if best[i][3]]
        broke = [i for i in f1 - fA if first[i][3]]
        print(f"  at gate {t:.2f}: {A} attempts RESCUE {len(rescued)} words that attempt 1 "
              f"failed, and lose {len(broke)}")
        if rescued:
            print(f"     rescued e.g. {', '.join(names[i] for i in rescued[:8])}")

    print("\n" + "=" * 74)
    print("C. RE-RANK BY conf * word_acc  (single attempt, so B is not confounded)")
    print("=" * 74)
    report(rows_at(1), "raw confidence", n)
    print()
    report(rows_at(1, use_rank=True), "reranked by expected acc", n)

    print("\n" + "=" * 74)
    print("D. PER-WORD GATES -- demand more confidence from unreliable words")
    print("=" * 74)
    base = rows_at(1)
    mean_acc = sum(wacc.values()) / len(wacc)
    print("  gate_w = t + s * (mean_acc - acc[predicted]);  s=0 is the global gate today")
    print(f"    {'s':>5} {'gate':>6} {'accept':>8} {'precision':>10}")
    for s in (0.0, 0.15, 0.30, 0.50):
        for t in (0.40, 0.58, 0.80):
            hit, ok = 0, 0
            for i, r in enumerate(base):
                p = mask_renorm(P[i, 0], allowed)
                w_pred = words[int(np.argmax(p))]
                tw = t + s * (mean_acc - wacc.get(w_pred, mean_acc))
                if gate_pass(r[0], r[1], r[2], tw):
                    hit += 1
                    ok += r[3]
            print(f"    {s:>5.2f} {t:>6.2f} {f'{100*hit/n:.0f}%':>8} "
                  f"{(ok/hit if hit else float('nan')):>10.3f}")
        print()

    print("Read B as OPTIMISTIC: simulated attempts vary only in which frames were caught,\n"
          "while real ones also vary in speed and hand path. One exemplar per word, so an SE\n"
          "near 0.03 at 50% accept on 250 classes and much wider on a topic mask.")


if __name__ == "__main__":
    main()
