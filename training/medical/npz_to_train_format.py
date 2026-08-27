#!/usr/bin/env python3
"""semlex_medical_landmarks.npz -> the on-disk layout train.py actually reads.

train.py's contract, read out of the source rather than assumed (train.py:576-620, 914-916):

    <out>/split_manifest.parquet     columns: word, participant_id, sequence_id,
                                              split, fold, is_outlier
    <out>/by_word/<word>/sequences.npz   keys: f"{participant_id}_{sequence_id}"
                                         values: (T, 75, 3) float32, NaN for untracked

  * `split == "cv"` is the ONLY thing train.py trains on — `cv = man[man["split"] == "cv"]`.
    Any other value is held out entirely. Test rows get `split == "test"`.
  * `train_man = cv[cv["fold"] != fold]`, `val_man = cv[cv["fold"] == fold & ~is_outlier]`.
  * NaN must SURVIVE: fit_to_maxlen pads with NaN and the model maps NaN->0. Filling it here
    would invent coordinates, which is the gap-fill defect extract_canonical.py was written to
    undo (a hand seen 9% of frames frozen in place for the rest).

WHY THE SPLIT IS BUILT WHOLE-SIGNER
-----------------------------------
Because `train_man = cv[cv["fold"] != fold]` takes every other fold as training data, a signer
who appears in two folds is in fold k's TRAINING set while also being in fold k's VAL set. That
is the leak measured on the 250-word model on 2026-08-27: folds 1/2/3 trained on fold 0's val
participants, and leaked signer 32319 read 0.6114 for fold 0 against 0.8930/0.8910/0.8959 for
the three that had seen it — a 28-point gap that looks like a fixed bug and is not one.

So: **every clip of a signer goes to exactly one bucket.** That makes each fold individually
honest. It does NOT make the fold ENSEMBLE scorable on any fold's val — the ensemble contains
models that trained on those signers. That is why a `test` bucket is held out of all folds, and
why the rule earned on 2026-08-27 stands: score a fold-ensemble on TEST ONLY.

Sem-Lex's own `split` column is deliberately IGNORED. Its test split is signer-disjoint but its
**val shares 31 of 32 signers with train**, and 915 video_ids appear under both train and val.
Reusing it would reintroduce exactly the leak above.

SIGNER CONCENTRATION IS THE REAL CONSTRAINT
-------------------------------------------
41 signers, top 10 hold 58% of the clinical subset, max/min 330x. A random signer split
therefore has enormous variance in bucket size, so buckets are filled SERPENTINE over
size-sorted signers (largest first, snaking back and forth). Deterministic, no seed, and it
balances clip counts without tuning.

With 16-22 concepts under 8 clips, holding whole signers out can leave a class with zero clips
in test, or zero in some fold's val. That is not hypothetical at these counts, so it is
MEASURED AND PRINTED rather than discovered during training.

`is_outlier` is all False. GISLR had a measured outlier flag; Sem-Lex has none yet, and
inventing one here would be a silent modelling decision. Stated, not hidden.

USAGE
    python npz_to_train_format.py --npz semlex_medical_landmarks.npz --out data_medical
    python npz_to_train_format.py --npz ... --out ... --folds 4 --min-clips 8
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

SAFE_WORD = re.compile(r"^[a-z0-9_]+$")


def serpentine(sizes: list, n_buckets: int) -> dict:
    """Assign each signer to exactly one of n_buckets, balancing total clips.

    Largest-first into the currently-lightest bucket (LPT). Beats plain round-robin when the
    size distribution is as skewed as this one (330x): round-robin would hand bucket 0 the
    single biggest signer and nothing else could compensate.
    """
    load = [0] * n_buckets
    out = {}
    for signer, n in sorted(sizes, key=lambda kv: (-kv[1], kv[0])):
        b = min(range(n_buckets), key=lambda i: (load[i], i))
        out[signer] = b
        load[b] += n
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--npz", required=True, help="output of semlex_poses_to_75.py")
    ap.add_argument("--out", required=True, help="directory to write by_word/ + the manifest")
    ap.add_argument("--folds", type=int, default=4,
                    help="CV folds (default 4, matching the 250-word ensemble)")
    ap.add_argument("--min-clips", type=int, default=8,
                    help="drop concepts with fewer than this many clips (default 8). Set 0 to "
                         "keep everything and let train.py cope.")
    ap.add_argument("--min-signers", type=int, default=2,
                    help="drop concepts seen by fewer than this many signers (default 2): a "
                         "one-signer class cannot be scored signer-disjointly at all.")
    ap.add_argument("--compress", action="store_true",
                    help="savez_compressed instead of savez. Smaller on disk, slower to load.")
    args = ap.parse_args()

    d = np.load(args.npz, allow_pickle=False)
    need = {"X", "y", "words", "signer", "clip"}
    if not need <= set(d.files):
        raise SystemExit(f"[err] {args.npz} has {sorted(d.files)}; needs {sorted(need)}")
    X, y = d["X"], d["y"].astype(int)
    words = [str(w) for w in d["words"]]
    signer = [str(s) for s in d["signer"]]
    clip = [str(c) for c in d["clip"]]

    if X.ndim != 4 or X.shape[2:] != (75, 3):
        raise SystemExit(f"[err] X is {X.shape}; train.py needs (N, T, 75, 3)")
    bad = [w for w in words if not SAFE_WORD.match(w)]
    if bad:
        raise SystemExit(f"[err] these class names are not safe as directory names: {bad}")
    print(f"[src] {args.npz}: X={X.shape} {X.dtype} | {len(words)} classes | "
          f"{len(set(signer))} signers | NaN {np.isnan(X).mean():.1%} of coordinates")
    if not np.isnan(X).any():
        print("[warn] X contains NO NaN. Untracked landmarks should be NaN, not 0 — a "
              "zero-filled corpus silently teaches the model that a missing hand is at "
              "the body centre.")

    # ── prune thin classes BEFORE splitting: a 2-clip class cannot be split at all ─────────
    per_cls_n, per_cls_sg = defaultdict(int), defaultdict(set)
    for i in range(len(y)):
        per_cls_n[y[i]] += 1
        per_cls_sg[y[i]].add(signer[i])
    drop = {c for c in range(len(words))
            if per_cls_n[c] < args.min_clips or len(per_cls_sg[c]) < args.min_signers}
    if drop:
        print(f"\n[prune] dropping {len(drop)} of {len(words)} concepts under "
              f"{args.min_clips} clips / {args.min_signers} signers:")
        for c in sorted(drop, key=lambda c: words[c]):
            print(f"     {words[c]:14} {per_cls_n[c]:3} clips, {len(per_cls_sg[c])} signers")
    keep_i = [i for i in range(len(y)) if y[i] not in drop]
    kept_words = sorted({words[y[i]] for i in keep_i})
    print(f"[prune] {len(kept_words)} concepts survive, {len(keep_i):,} of {len(y):,} clips")

    # ── whole-signer buckets: bucket 0 = TEST, buckets 1..folds = the CV folds ─────────────
    sizes = defaultdict(int)
    for i in keep_i:
        sizes[signer[i]] += 1
    bucket = serpentine(list(sizes.items()), args.folds + 1)
    n_by_b = defaultdict(int)
    for i in keep_i:
        n_by_b[bucket[signer[i]]] += 1
    print(f"\n[split] {len(sizes)} signers -> 1 test bucket + {args.folds} folds, whole-signer")
    for b in range(args.folds + 1):
        sg = sorted((s for s, bb in bucket.items() if bb == b), key=lambda s: -sizes[s])
        tag = "TEST" if b == 0 else f"fold {b - 1}"
        print(f"  {tag:7} {len(sg):2} signers, {n_by_b[b]:5,} clips "
              f"({n_by_b[b] / len(keep_i):5.1%})  {sg}")

    overlap = [s for s in sizes if sum(bucket[s] == b for b in range(args.folds + 1)) != 1]
    if overlap:
        raise SystemExit(f"[err] signers in more than one bucket: {overlap}")

    # ── the check that matters at these class sizes ────────────────────────────────────────
    cov = defaultdict(lambda: defaultdict(int))
    for i in keep_i:
        cov[words[y[i]]][bucket[signer[i]]] += 1
    no_test = sorted(w for w in kept_words if cov[w][0] == 0)
    no_val = {}
    for w in kept_words:
        empty = [b - 1 for b in range(1, args.folds + 1) if cov[w][b] == 0]
        if empty:
            no_val[w] = empty
    print(f"\n[coverage] {len(kept_words) - len(no_test)}/{len(kept_words)} concepts have "
          f"clips in TEST")
    if no_test:
        print(f"[warn] {len(no_test)} concepts have NO test clips — they cannot be scored at "
              f"all: {no_test}")
    if no_val:
        worst = sorted(no_val.items(), key=lambda kv: -len(kv[1]))[:12]
        print(f"[warn] {len(no_val)} concepts miss at least one fold's val split "
              f"(that fold cannot measure them): "
              + ", ".join(f"{w}(folds {v})" for w, v in worst))

    # ── write ─────────────────────────────────────────────────────────────────────────────
    out = Path(args.out)
    (out / "by_word").mkdir(parents=True, exist_ok=True)
    saver = np.savez_compressed if args.compress else np.savez
    rows, per_word, nbytes = [], defaultdict(dict), 0
    for i in keep_i:
        w, sg, vid = words[y[i]], signer[i], clip[i]
        per_word[w][f"{sg}_{vid}"] = X[i]
        b = bucket[sg]
        rows.append({"word": w, "participant_id": sg, "sequence_id": vid,
                     "split": "test" if b == 0 else "cv",
                     "fold": -1 if b == 0 else b - 1, "is_outlier": False})
    dup = len(keep_i) - sum(len(v) for v in per_word.values())
    if dup:
        raise SystemExit(f"[err] {dup} clips collide on (participant_id, sequence_id) — "
                         f"train.py keys arrays on that pair, so a collision silently drops rows")
    for w, arrs in sorted(per_word.items()):
        p = out / "by_word" / w / "sequences.npz"
        p.parent.mkdir(parents=True, exist_ok=True)
        saver(p, **arrs)
        nbytes += p.stat().st_size

    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("[err] pandas is required to write split_manifest.parquet")
    man = pd.DataFrame(rows)
    man["fold"] = man["fold"].astype("int32")
    man["is_outlier"] = man["is_outlier"].astype(bool)
    mp = out / "split_manifest.parquet"
    man.to_parquet(mp, index=False)

    print(f"\n[ok] {out}/by_word/  {len(per_word)} words, {nbytes / 1e6:.0f} MB"
          f"{' (compressed)' if args.compress else ''}")
    print(f"[ok] {mp}  {len(man):,} rows: "
          + "  ".join(f"{s}={int((man['split'] == s).sum()):,}"
                      for s in sorted(man["split"].unique())))
    print(f"[ok] columns {list(man.columns)}")

    (out / "PROVENANCE.json").write_text(json.dumps({
        "source_npz": str(Path(args.npz).name), "corpus": "Sem-Lex (CC BY-NC-SA)",
        "licence": "NON-COMMERCIAL. Share-Alike would also cover derived weights.",
        "classes": len(per_word), "clips": len(man), "folds": args.folds,
        "split_rule": "whole-signer serpentine; bucket 0 = test, held out of every fold",
        "semlex_split_column": "IGNORED — its val shares 31/32 signers with train",
        "score_on": "split == 'test' only. NEVER score the fold ensemble on any fold's val.",
        "is_outlier": "all False — Sem-Lex has no measured outlier flag",
        "nan": "preserved; untracked landmarks must stay NaN",
        "pruned_concepts": sorted(words[c] for c in drop),
        "concepts_without_test_clips": no_test,
    }, indent=1), encoding="utf-8")
    print(f"[ok] {out}/PROVENANCE.json")
    print(f"\nNEXT:  python train.py --data-dir {out} --all-words --fold 0")
    print("       ⚠️  score on split=='test' only; the fold ensemble is NOT scorable on val")


if __name__ == "__main__":
    main()
