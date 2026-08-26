#!/usr/bin/env python
"""How much accuracy is sitting in the top-K that top-1 throws away? The headroom, measured.

WHY
---
Every fix tried so far operates on top-1: gates, margins, per-word thresholds, averaging
repeated attempts, re-ranking. Most were refuted. But live_demo.py:1333 already asserts
something none of them exploit -- "full 250: top-1 is unreliable (0.76 mean) but the right
word is almost always in the top-5 -> tap 1-5 to fix. This is the PRIMARY interaction at 250."

If that is true, the vocabulary problem is not really a recognition problem. Speech recognition
solved the same shape of problem with an acoustic model that is individually unreliable plus a
LANGUAGE MODEL that picks the best SEQUENCE from a lattice of candidates. This demo already has
an LLM wired in -- but it runs on DONE, over words that were already committed, so it can only
rephrase what top-1 chose. It never sees the alternatives.

Decoding the sentence from the top-K lattice instead would need no new data, no retraining, and
no new dataset licence. The value of that idea is exactly the gap between top-1 and top-K, so
measure the gap before building anything.

WHAT TO DO WITH THE NUMBER
--------------------------
top1 is what ships. topK is the CEILING an oracle chooser would reach; a language model gets
somewhere between the two, and how far depends on how much the sentence constrains the choice.
If top5 - top1 is small the idea is dead and the vocabulary is genuinely the limit. If it is
large, sequence decoding is worth more than everything measured this week combined.

Reported per topic mask as well, because narrowing and lattice decoding compound: fewer classes
means both a better top-1 AND a shorter lattice for the language model to search.

USAGE
    python measure_topk.py
    python measure_topk.py --words topic_everyday.json vocab_clinical_43.json
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
KS = (1, 2, 3, 5, 10, 20)


def to_live(arr: np.ndarray, live_fps: float) -> np.ndarray:
    n = max(2, int(round(arr.shape[0] / SRC_FPS * live_fps)))
    return arr[np.linspace(0, arr.shape[0] - 1, n).round().astype(int)]


def topk_table(P, names, index, allowed=None) -> dict:
    """Accuracy if an oracle could pick from the top K, under an optional class mask."""
    hits = {k: 0 for k in KS}
    n = 0
    for w, p in zip(names, P):
        if allowed is not None:
            if index[w] not in allowed:
                continue
            m = np.zeros_like(p)
            m[allowed] = p[allowed]
            p = m
        n += 1
        order = np.argsort(p)[::-1]
        rank = int(np.where(order == index[w])[0][0])
        for k in KS:
            if rank < k:
                hits[k] += 1
    return {k: hits[k] / n for k in KS} | {"n": n}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--artifacts", default=str(HERE / "artifacts_250"))
    ap.add_argument("--fps", type=float, default=7.0)
    ap.add_argument("--words", nargs="*", default=["topic_everyday.json",
                                                   "vocab_clinical_43.json"])
    args = ap.parse_args()

    words = json.loads(Path(args.vocab).read_text(encoding="utf-8"))["words"]
    index = {w: i for i, w in enumerate(words)}
    with np.load(args.clips) as z:
        clips = {w: canonicalize_missing(z[w].astype(np.float32))
                 for w in z.files if w in index}
    dirs = [Path(args.artifacts) / f"savedmodel_fold{k}" for k in range(4)]
    _keep, fns = ld.load_models(dirs)
    assert ld.ALLOWED_IDX is None

    names = list(clips)
    P = np.stack([ld.classify_commit(fns, list(to_live(clips[w], args.fps)))
                  for w in names])
    print(f"[ok] {len(names)} words at {args.fps:.0f} fps\n")

    rows = [("all 250", topk_table(P, names, index))]
    for f in args.words:
        p = Path(f)
        if not p.exists():
            print(f"[skip] {f} not found")
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        allow = raw["words"] if isinstance(raw, dict) else raw
        idx = np.array(sorted({index[w] for w in allow if w in index}), dtype=np.int64)
        rows.append((f"{p.stem} ({len(idx)})", topk_table(P, names, index, idx)))

    print(f"{'vocabulary':<28} {'n':>4} " + " ".join(f"{'top'+str(k):>7}" for k in KS))
    print("-" * (34 + 8 * len(KS)))
    for label, t in rows:
        print(f"{label:<28} {t['n']:>4} " + " ".join(f"{t[k]:>7.3f}" for k in KS))

    print("\nHEADROOM a sequence decoder could reach (top5 - top1):")
    for label, t in rows:
        print(f"  {label:<28} {t[1]:.3f} -> {t[5]:.3f}   {t[5]-t[1]:+.3f}")
    print("\ntop1 is what ships today. topK is an ORACLE ceiling -- a language model lands\n"
          "between the two. One exemplar per word, so read the gap, not the absolutes.")


if __name__ == "__main__":
    main()
