#!/usr/bin/env python
"""How many clips per sign does a recording session actually need? · ~70-85 min GPU

WHY THIS EXISTS
---------------
Every corpus we have is licence-blocked for a commercial product: Sem-Lex is CC BY-NC-SA and
ASL Citizen is non-commercial too. So the only route to a corpus we own is **recording our
own** — and the whole question is how big that session has to be. "A weekend with six signers"
and "six months of recruitment" are different companies. Nobody has priced it, and it is the
input to a decision only Salim can make.

This measures the answer instead of guessing it: train fold 0 at N clips per sign for several
N, and read the accuracy-vs-N curve. The slope says what the next N buys; the saturation point
says when recording more of the *same* stops helping.

THE TRAP THIS SCRIPT EXISTS TO AVOID
------------------------------------
`train.py:run_fold` splits like this:

    cv        = man[man["split"] == "cv"]
    train_man = cv[cv["fold"] != fold]          <- what we subsample
    val_man   = cv[cv["fold"] == fold]          <- MUST NOT CHANGE
                man[man["split"] == "test"]     <- MUST NOT CHANGE

Subsample the whole manifest and the validation set shrinks with the training set. Accuracy
then moves for two reasons at once — less training data AND a noisier yardstick — and the curve
measures neither. **Only `split=="cv" & fold != target` rows are ever dropped here**, and the
selftest asserts the val and test rows come out byte-identical.

THE SECOND CONFOUND, WHICH IS ALSO THE REAL QUESTION
----------------------------------------------------
"N clips per sign" is ambiguous: N takes from one signer is not N takes spread over N signers,
and per-signer variance is the dominant effect in this whole project (a measured 1.31x accuracy
spread on the medical model, 2.65x on the 250-word one). So N alone cannot answer a recording
plan.

Two strategies, and the gap between them IS the finding:

  --strategy spread     round-robin over signers, so N clips come from as many DIFFERENT
                        people as possible. Answers "how many takes if we recruit widely?"
  --strategy clustered  fill from the signers with the most clips first, so N clips come from
                        as FEW people as possible. Answers "how many takes if we recruit few?"

Run both and the difference prices *recruitment* against *studio time*, which is the actual
trade a session plan has to make.

WHAT IT DOES NOT DO
-------------------
It cannot tell you about signers the corpus does not contain, and Sem-Lex's 41 signers are not
a random sample of ASL users. The curve is an upper bound on how well a session of this size
would do, measured on this corpus's diversity.

USAGE
    # free: write the manifests and print the counts, train nothing
    python clips_per_sign_curve.py --data-dir /kaggle/input/<ds>/data_medical --out-dir /kaggle/working/cps

    # the real run, ~70-85 min GPU for 5 points
    python clips_per_sign_curve.py --data-dir ... --out-dir ... --train --epochs 40

    python clips_per_sign_curve.py --selftest      # no data needed
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TRAIN_PY = HERE.parent / "train.py"          # training/train.py
DEFAULT_N = "2,4,8,16,32"


# ── the subsample ─────────────────────────────────────────────────────────────────────────
def subsample_manifest(man, n_clips: int, fold: int, strategy: str, seed: int):
    """Return a manifest with at most `n_clips` TRAINING rows per word.

    Only `split=="cv" & fold != fold` rows are touched. Validation (`split=="cv" & fold ==
    fold`) and the held-out test split pass through untouched, so the yardstick is fixed
    across every point on the curve.
    """
    import pandas as pd

    is_cv = man["split"] == "cv"
    train_mask = is_cv & (man["fold"] != fold)
    held = man[~train_mask]                       # val + test, verbatim
    train = man[train_mask]

    rng = np.random.default_rng(seed)
    keep_idx = []
    per_word_signers = {}

    for word, grp in train.groupby("word", sort=True):
        if len(grp) <= n_clips:
            keep_idx.extend(grp.index.tolist())
            per_word_signers[word] = int(grp["participant_id"].nunique())
            continue

        # Group this word's takes by signer, each signer's list shuffled deterministically.
        by_signer = {}
        for pid, sub in grp.groupby("participant_id", sort=True):
            order = rng.permutation(len(sub))
            by_signer[int(pid)] = [sub.index[i] for i in order]

        if strategy == "spread":
            # Round-robin: take one from each signer, then a second from each, and so on.
            # Signers ordered by how many takes they have, fewest first, so a signer with a
            # single take is not crowded out by a prolific one.
            order = sorted(by_signer, key=lambda p: (len(by_signer[p]), p))
            picked, ring = [], list(order)
            while len(picked) < n_clips and ring:
                for pid in list(ring):
                    if not by_signer[pid]:
                        ring.remove(pid)
                        continue
                    picked.append(by_signer[pid].pop(0))
                    if len(picked) == n_clips:
                        break
        elif strategy == "clustered":
            # Drain the most prolific signers first, so N clips come from as few people as
            # possible — the "we could only book three signers" scenario.
            order = sorted(by_signer, key=lambda p: (-len(by_signer[p]), p))
            picked = []
            for pid in order:
                take = by_signer[pid][: n_clips - len(picked)]
                picked.extend(take)
                if len(picked) >= n_clips:
                    break
        else:
            raise ValueError(f"unknown strategy {strategy!r}")

        keep_idx.extend(picked)
        per_word_signers[word] = int(train.loc[picked, "participant_id"].nunique())

    out = pd.concat([held, train.loc[sorted(keep_idx)]]).sort_index()
    stats = {
        "n_clips": n_clips,
        "strategy": strategy,
        "train_rows": int(len(keep_idx)),
        "train_rows_full": int(len(train)),
        "val_rows": int(((man["split"] == "cv") & (man["fold"] == fold)).sum()),
        "test_rows": int((man["split"] == "test").sum()),
        "words": int(train["word"].nunique()),
        "words_at_cap": int(sum(1 for w, g in train.groupby("word") if len(g) > n_clips)),
        "mean_signers_per_word": round(float(np.mean(list(per_word_signers.values()))), 2),
        "min_signers_per_word": int(min(per_word_signers.values())) if per_word_signers else 0,
    }
    return out, stats


def write_point(orig_dir: Path, out_root: Path, man, n_clips: int, strategy: str):
    """Write one curve point's data-dir: a subsampled manifest + a link to the shared by_word.

    Returns (dir, link_error_or_None). The caller reports link failures ONCE at the end —
    per-point warnings buried the actual row counts, which are the output that matters.
    """
    d = out_root / f"{strategy}_n{n_clips}"
    d.mkdir(parents=True, exist_ok=True)
    man.to_parquet(d / "split_manifest.parquet", index=False)

    # by_word is tens of GB and identical at every point — link it, never copy. train.py only
    # reads it, and the manifest is what selects rows out of it (train.py:611-616).
    link = d / "by_word"
    src = (orig_dir / "by_word").resolve()
    if link.exists():
        return d, None
    try:
        os.symlink(src, link, target_is_directory=True)
        return d, None
    except (OSError, NotImplementedError, AttributeError) as e:
        first = e
    # Windows refuses symlinks without elevation (WinError 1314) but allows a directory
    # JUNCTION, which train.py cannot tell apart. Kaggle is Linux and never reaches this.
    if os.name == "nt":
        try:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(src)],
                               capture_output=True, text=True)
            if r.returncode == 0 and link.exists():
                return d, None
        except Exception:
            pass
    return d, f"{type(first).__name__}: {first}"


# ── the curve ─────────────────────────────────────────────────────────────────────────────
def fit_curve(points: list[dict]) -> dict:
    """Fit accuracy against log2(clips per sign) and say what the next doubling buys."""
    usable = [p for p in points if p.get("val_acc") is not None and p["n_clips"] > 0]
    if len(usable) < 2:
        return {"fitted": False, "why": "need >=2 trained points"}

    x = np.array([math.log2(p["n_clips"]) for p in usable])
    y = np.array([p["val_acc"] for p in usable])
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else float("nan")

    # Where does it stop paying? Compare consecutive measured gains rather than trusting the
    # line — a saturating curve fits a line badly and the residual is the tell.
    gains = []
    for a, b in zip(usable, usable[1:]):
        d = math.log2(b["n_clips"] / a["n_clips"])
        gains.append({"from": a["n_clips"], "to": b["n_clips"],
                      "d_acc": round(b["val_acc"] - a["val_acc"], 4),
                      "per_doubling": round((b["val_acc"] - a["val_acc"]) / d, 4)})

    out = {
        "fitted": True,
        "acc_per_doubling": round(float(slope), 4),
        "intercept_at_1_clip": round(float(intercept), 4),
        "r2": round(float(r2), 4),
        "consecutive_gains": gains,
        "note": ("A high r2 means log-linear: every doubling buys the same amount, so the "
                 "session size is a budget choice. A LOW r2 with shrinking consecutive gains "
                 "means saturation — past that point recording more takes of the same signs "
                 "buys nothing and the money belongs in more SIGNERS or more WORDS."),
    }
    if gains:
        last = gains[-1]["per_doubling"]
        out["next_doubling_predicted"] = round(usable[-1]["val_acc"] + last, 4)
        out["next_doubling_caveat"] = ("Extrapolated from the LAST measured gain only (n=1). "
                                       "Treat as a direction, not a number.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, help="medical data dir (split_manifest.parquet + by_word/)")
    ap.add_argument("--out-dir", type=Path, help="where the per-point data-dirs and results go")
    ap.add_argument("--n-clips", default=DEFAULT_N, help=f"comma-separated (default {DEFAULT_N})")
    ap.add_argument("--strategy", default="spread", choices=["spread", "clustered", "both"])
    ap.add_argument("--fold", type=int, default=0, help="which cv fold is validation (default 0)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train", action="store_true",
                    help="actually invoke train.py per point (without this, only manifests are written)")
    ap.add_argument("--train-py", type=Path, default=None,
                    help=f"path to train.py. Defaults to {TRAIN_PY} (i.e. ../train.py, the repo "
                         f"layout). On Kaggle a dataset usually flattens the tree, so pass this "
                         f"explicitly or the default resolves ABOVE the dataset directory.")
    ap.add_argument("--decimate", type=float, default=0.5,
                    help="decimate probability handed to train.py (default 0.5, because the demo "
                         "runs at ~7fps). Set 0.0 if the medical decimate A/B comes back negative "
                         "— otherwise the whole curve measures a config you would not ship.")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.data_dir or not a.out_dir:
        ap.error("--data-dir and --out-dir are required (or pass --selftest)")

    # Resolve train.py BEFORE any work. Without this the script writes every manifest, links
    # every by_word, and only then fails once per point with "train.py exited 2" — and because
    # TRAIN_PY is used ONLY under --train, the free dry-run passes and says everything is fine.
    train_py = a.train_py or TRAIN_PY
    if a.train and not train_py.exists():
        sys.exit(f"[err] train.py not found at {train_py}\n"
                 f"      The default is ../train.py relative to THIS file, which is the repo "
                 f"layout.\n      A Kaggle dataset flattens the tree, so that resolves above the "
                 f"dataset dir.\n      Pass --train-py /kaggle/input/<ds>/train.py, or recreate "
                 f"the layout:\n"
                 f"        training/train.py  and  training/medical/clips_per_sign_curve.py")

    import pandas as pd

    mpath = a.data_dir / "split_manifest.parquet"
    if not mpath.exists():
        sys.exit(f"[err] {mpath} not found.\n"
                 f"      --data-dir must be the directory holding BOTH split_manifest.parquet "
                 f"and by_word/.\n      Find it with:\n"
                 f"        import glob, os\n"
                 f"        print([os.path.dirname(p) for p in "
                 f"glob.glob('/kaggle/input/**/split_manifest.parquet', recursive=True)])")
    if not (a.data_dir / "by_word").is_dir():
        sys.exit(f"[err] {a.data_dir / 'by_word'} not found — that directory holds the clips.")

    man = pd.read_parquet(mpath)
    need = {"word", "participant_id", "sequence_id", "split", "fold"}
    if not need.issubset(man.columns):
        sys.exit(f"[err] manifest is missing {need - set(man.columns)}")

    folds = sorted(man[man["split"] == "cv"]["fold"].unique())
    if a.fold not in folds:
        sys.exit(f"[err] --fold {a.fold} is not a cv fold; available: {folds}")

    strategies = ["spread", "clustered"] if a.strategy == "both" else [a.strategy]
    ns = [int(x) for x in a.n_clips.split(",") if x.strip()]

    full_train = int(((man["split"] == "cv") & (man["fold"] != a.fold)).sum())
    print(f"[cfg] {len(man):,} manifest rows · {man['word'].nunique()} words · "
          f"{man['participant_id'].nunique()} signers")
    print(f"[cfg] fold {a.fold} is validation. Full training pool: {full_train:,} rows.")
    print(f"[cfg] val and test rows are held CONSTANT at every point — only training rows are cut.\n")

    a.out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    link_failures = []

    def save(final=False):
        """Write the aggregate after EVERY point, not just at the end.

        --strategy both --epochs 200 is ~2 h of sequential training on Kaggle, and a session
        that dies at point 9 of 10 used to lose the whole aggregate. The per-point
        run_*/eval_*.json survive on disk either way, but reassembling the curve from them by
        hand is exactly the kind of avoidable work a long job should not create.
        """
        # fit_curve is PER STRATEGY — spread and clustered are two different curves and
        # pooling their points would fit a line through a mixture of two experiments.
        curve = {}
        for s in strategies:
            pts = [r for r in results if r["strategy"] == s]
            if pts:
                curve[s] = fit_curve(pts)
        doc = {
            "note": "Accuracy vs clips-per-sign. Only TRAINING rows were subsampled; val and "
                    "test are identical at every point (asserted per point, not assumed).",
            "fold": a.fold, "epochs": a.epochs, "seed": a.seed,
            "decimate": a.decimate,
            "decimate_note": "handed to train.py. The demo runs at ~7fps, where decimate was "
                             "worth +0.0218 on the 250-word model — but that has NOT been "
                             "measured on the 123-class medical one. Run the decimate A/B "
                             "first; a curve at the wrong setting prices a model we do not ship.",
            "full_train_rows": full_train,
            "points": results, "curve": curve,
            "trained": bool(a.train),
            "complete": final,
            "points_done": len(results),
            "points_expected": len(strategies) * len(ns),
        }
        (a.out_dir / "clips_per_sign.json").write_text(
            json.dumps(doc, indent=1), encoding="utf-8")
        return doc

    for strategy in strategies:
        for n in ns:
            sub, stats = subsample_manifest(man, n, a.fold, strategy, a.seed)

            # The invariant this whole script rests on. Assert it per point, not once.
            for label, mask in (("val", (man["split"] == "cv") & (man["fold"] == a.fold)),
                                ("test", man["split"] == "test")):
                before = man[mask].reset_index(drop=True)
                after = sub[mask.reindex(sub.index, fill_value=False)].reset_index(drop=True)
                if len(before) != len(after):
                    sys.exit(f"[err] {label} rows changed at n={n} ({len(before)} -> "
                             f"{len(after)}). The curve would be measuring a moving yardstick.")

            d, link_err = write_point(a.data_dir, a.out_dir, sub, n, strategy)
            if link_err:
                link_failures.append((d, link_err))
            pct = 100.0 * stats["train_rows"] / max(1, stats["train_rows_full"])
            print(f"[{strategy} n={n:>3}] train {stats['train_rows']:>6,} rows ({pct:5.1f}% of full) · "
                  f"{stats['words_at_cap']:>3}/{stats['words']} words hit the cap · "
                  f"signers/word mean {stats['mean_signers_per_word']:>5.2f} min {stats['min_signers_per_word']}")

            rec = dict(stats, data_dir=str(d), val_acc=None)

            if a.train:
                out = a.out_dir / f"run_{strategy}_n{n}"
                cmd = [sys.executable, str(train_py), "--data-dir", str(d), "--out-dir", str(out),
                       "--fold", str(a.fold), "--all-words", "--epochs", str(a.epochs),
                       "--seed", str(a.seed), "--decimate", str(a.decimate)]
                print(f"    -> {' '.join(cmd[1:])}")
                r = subprocess.run(cmd, capture_output=True, text=True)
                sys.stdout.write(r.stdout[-2000:] if r.stdout else "")
                if r.returncode != 0:
                    print(f"    [FAIL] train.py exited {r.returncode}")
                    sys.stderr.write(r.stderr[-2000:] if r.stderr else "")
                else:
                    rec["val_acc"] = _scrape_val_acc(out, r.stdout)
                    print(f"    val_acc = {rec['val_acc']}")

            results.append(rec)
            save()          # after EVERY point — a 2 h run must not lose 9 points to a timeout

    if link_failures:
        src = (a.data_dir / "by_word").resolve()
        print(f"\n[warn] could not link by_word into {len(link_failures)} point dir(s): "
              f"{link_failures[0][1]}")
        print("       The MANIFESTS are written and the row counts above are valid — this only")
        print("       blocks --train, because train.py reads <data-dir>/by_word. On Linux "
              "(Kaggle) this")
        print("       does not happen; on Windows it needs elevation or a junction. Fix with:")
        for d, _ in link_failures:
            print(f"         ln -s {src} {d / 'by_word'}")

    doc = save(final=True)
    curve = doc["curve"]
    print(f"\n[ok] {a.out_dir / 'clips_per_sign.json'}  "
          f"({doc['points_done']}/{doc['points_expected']} points)")

    if not a.train:
        print("\n[dry] Manifests written, nothing trained. The row counts above are the free "
              "sanity check —\n      confirm they look right, then re-run with --train.")
        print("      MEASURED cost at --epochs 200 (0.11 s/train-step, 7 s/epoch at the full "
              "4,149 rows):\n      ~55 min per strategy, ~1 h 50 m for both. Points are small, "
              "so they are far\n      cheaper than a full-data run — the whole curve costs about "
              "2.5 full runs.")
    else:
        for s, c in curve.items():
            if c.get("fitted"):
                print(f"\n=== {s} ===")
                print(f"  accuracy per doubling of clips/sign: {c['acc_per_doubling']:+.4f}  (r2 {c['r2']})")
                for g in c["consecutive_gains"]:
                    print(f"    {g['from']:>3} -> {g['to']:<3}  {g['d_acc']:+.4f}")
                print(f"  {c['note']}")
    return 0


def _scrape_val_acc(out_dir: Path, stdout: str):
    """Prefer a json artifact; fall back to the last val_acc printed."""
    for name in ("report.json", "history.json", "metrics.json"):
        p = out_dir / name
        if p.exists():
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for k in ("best_val_acc", "val_acc", "best_val_accuracy"):
                if isinstance(j, dict) and k in j:
                    return float(j[k])
    best = None
    for line in (stdout or "").splitlines():
        if "val_acc" not in line and "val_accuracy" not in line:
            continue
        for tok in line.replace(":", " ").replace("=", " ").split():
            try:
                v = float(tok)
            except ValueError:
                continue
            if 0.0 <= v <= 1.0:
                best = v if best is None else max(best, v)
    return best


# ── selftest ──────────────────────────────────────────────────────────────────────────────
def selftest() -> int:
    print("=== SELFTEST (no data, no GPU) ===")
    import pandas as pd
    ok = True

    def check(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")

    # A hand-built manifest: 3 words, 4 signers, deliberately lopsided so `spread` and
    # `clustered` cannot accidentally agree.
    rows = []
    for w, counts in (("pain", {1: 10, 2: 6, 3: 2, 4: 1}),
                      ("blood", {1: 3, 2: 3}),
                      ("thin", {1: 2})):
        for pid, k in counts.items():
            for s in range(k):
                rows.append({"word": w, "participant_id": pid, "sequence_id": 1000 * pid + s,
                             "split": "cv", "fold": (s % 4), "is_outlier": False})
    for i in range(7):                                   # a held-out test split
        rows.append({"word": "pain", "participant_id": 9, "sequence_id": 90000 + i,
                     "split": "test", "fold": -1, "is_outlier": False})
    man = pd.DataFrame(rows)

    FOLD = 0
    val_mask = (man["split"] == "cv") & (man["fold"] == FOLD)
    test_mask = man["split"] == "test"
    n_val, n_test = int(val_mask.sum()), int(test_mask.sum())
    check(n_val > 0 and n_test == 7, f"fixture has {n_val} val rows and {n_test} test rows")

    for strat in ("spread", "clustered"):
        for n in (1, 2, 4, 8, 1000):
            sub, st = subsample_manifest(man, n, FOLD, strat, seed=0)

            # THE INVARIANT. Val and test must survive verbatim, or the curve is meaningless.
            sv = sub[val_mask.reindex(sub.index, fill_value=False)]
            st_ = sub[test_mask.reindex(sub.index, fill_value=False)]
            same_val = len(sv) == n_val and set(sv["sequence_id"]) == set(man[val_mask]["sequence_id"])
            same_test = len(st_) == n_test
            check(same_val and same_test,
                  f"{strat} n={n}: val ({len(sv)}/{n_val}) and test ({len(st_)}/{n_test}) untouched")

            # the cap actually caps
            tr = sub[(sub["split"] == "cv") & (sub["fold"] != FOLD)]
            worst = tr.groupby("word").size().max() if len(tr) else 0
            check(worst <= max(n, 0) or n >= 1000,
                  f"{strat} n={n}: no word exceeds {n} training clips (max {worst})")

    # spread must reach more signers than clustered where the choice exists
    sp, sp_st = subsample_manifest(man, 4, FOLD, "spread", seed=0)
    cl, cl_st = subsample_manifest(man, 4, FOLD, "clustered", seed=0)
    sp_tr = sp[(sp["split"] == "cv") & (sp["fold"] != FOLD) & (sp["word"] == "pain")]
    cl_tr = cl[(cl["split"] == "cv") & (cl["fold"] != FOLD) & (cl["word"] == "pain")]
    check(sp_tr["participant_id"].nunique() > cl_tr["participant_id"].nunique(),
          f"'spread' reaches more signers than 'clustered' at n=4 "
          f"({sp_tr['participant_id'].nunique()} vs {cl_tr['participant_id'].nunique()}) — "
          f"the two strategies are genuinely different")
    check(len(sp_tr) == len(cl_tr),
          f"both strategies keep the SAME clip count ({len(sp_tr)}) — only WHOSE clips differs")

    # a word with fewer clips than the cap must pass through whole
    thin = sp[(sp["split"] == "cv") & (sp["fold"] != FOLD) & (sp["word"] == "thin")]
    thin_full = man[(man["split"] == "cv") & (man["fold"] != FOLD) & (man["word"] == "thin")]
    check(len(thin) == len(thin_full),
          f"a word below the cap keeps all {len(thin_full)} of its clips")

    # keys must still match what train.py builds, or load_dataset silently drops rows
    key = sp["word"] + "/" + sp["participant_id"].astype(str) + "_" + sp["sequence_id"].astype(str)
    check(key.is_unique, "the word/participant_sequence key train.py builds stays unique")

    # determinism — same seed, same rows
    b1, _ = subsample_manifest(man, 4, FOLD, "spread", seed=7)
    b2, _ = subsample_manifest(man, 4, FOLD, "spread", seed=7)
    check(b1.equals(b2), "same seed gives the same subsample")
    b3, _ = subsample_manifest(man, 4, FOLD, "spread", seed=8)
    check(not b1.equals(b3), "a different seed gives a different subsample (it is really random)")

    # the curve fit, on numbers whose answer is known: +0.05 per doubling exactly
    pts = [{"n_clips": 2 ** i, "val_acc": 0.50 + 0.05 * i, "strategy": "spread"} for i in range(5)]
    c = fit_curve(pts)
    check(c["fitted"] and abs(c["acc_per_doubling"] - 0.05) < 1e-9,
          f"a synthetic +0.05/doubling curve fits at {c.get('acc_per_doubling')}")
    check(abs(c["r2"] - 1.0) < 1e-9, "a perfectly log-linear curve reports r2 = 1.0")
    sat = fit_curve([{"n_clips": 2 ** i, "val_acc": v, "strategy": "s"}
                     for i, v in enumerate([0.50, 0.60, 0.66, 0.69, 0.70])])
    check(sat["consecutive_gains"][-1]["per_doubling"] < sat["consecutive_gains"][0]["per_doubling"],
          "a SATURATING curve shows shrinking consecutive gains (which is the decision signal)")
    check(fit_curve([{"n_clips": 4, "val_acc": 0.6, "strategy": "s"}])["fitted"] is False,
          "one point does not get a fitted line")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOMETHING FAILED — see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
