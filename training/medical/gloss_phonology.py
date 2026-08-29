#!/usr/bin/env python3
"""
Answer "are these two glosses the same sign?" from ASL-LEX phonology instead of from a
reviewer's memory.

`semlex_metadata.csv` carries, for every `asllex`-typed clip, the full ASL-LEX feature set
(handshape, selected fingers, flexion, spread, thumb, sign type, path movement, repetition,
major/minor location, contact, nondominant handshape, wrist twist) **and a SignBank Reference
ID**. That ID is the lexical identity: two glosses sharing one are two names for a single
dictionary entry.

That makes a whole class of review questions answerable from data:

  * `MERGE-01 pain/hurt`  -> both are SignBank **489.0**. Same entry. The merge is correct.
  * `MERGE-02 today/now`  -> **299.0 vs 517.0**. Different entries, differing in exactly ONE
    feature: Repeated Movement (TODAY is NOW signed twice). The merge was WRONG and was
    reverted. The model's 7-of-10 confusion is a real model weakness, not a labelling artefact.

It does NOT replace a Deaf reviewer. ASL-LEX is itself an annotation, it covers only
`asllex`-typed rows, and regional//variant forms are outside it. What it does is answer the
questions that have a documented answer, so a reviewer's time goes to the ones that don't.

THE MEASUREMENT THAT MADE THIS WORTH BUILDING
---------------------------------------------
Run with `--confusions`: the pairs the 4-fold model actually confuses on the test set differ
on a median of **4 of 17** features. Random clinical word pairs differ on **11**. Only **1.8%**
of random pairs are as close as the median confused pair.

The recurring culprits are **Path Movement** and **Repeated Movement** — movement features,
not handshape or location. That points at temporal resolution rather than the 75-point
layout's missing face, and it makes `--decimate 0.5` plus the fixed-length time resize worth
testing as a *cause*: if two signs differ only by a repeat, dropping half the frames is
exactly the operation that would erase the difference. Stated as a hypothesis; NOT tested.

Usage
-----
  python gloss_phonology.py --pair pain hurt --pair today now
  python gloss_phonology.py --review docs/CLINICAL_GLOSS_REVIEW.csv   # fill what it can
  python gloss_phonology.py --confusions                              # the measurement above
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

FEATURES = [
    "Handshape", "Selected Fingers", "Flexion", "Flexion Change", "Spread", "Spread Change",
    "Thumb Position", "Thumb Contact", "Sign Type", "Path Movement", "Repeated Movement",
    "Major Location", "Minor Location", "Second Minor Location", "Contact",
    "Nondominant Handshape", "Wrist Twist",
]
SIGNBANK = "SignBank Reference ID"

# Pairs the 4-fold ensemble confuses on the test split, with clip counts, from
# training/medical/results/ensemble_test.confusion.csv.
CONFUSED = [("today", "now", 7), ("pain", "hurt", 6), ("where", "ask", 4),
            ("sometimes", "show", 4), ("maybe", "want", 4), ("where", "who", 3),
            ("man", "woman", 3), ("man", "father", 3), ("lungs", "tired", 3),
            ("hot", "bad", 3), ("heart", "feel", 3)]


def load(path: Path):
    by_label = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_label[row["label"].strip().lower()].append(row)
    return by_label


def profile(by_label, gloss: str):
    """-> (modal feature dict, modal SignBank id, n annotated clips) or None.

    Only `asllex`-typed rows carry features; the rest are blank. Modal value per feature,
    because one gloss can span several annotated variants and the majority is the citation
    form we want to compare.
    """
    rs = [r for r in by_label.get(gloss.strip().lower(), []) if r.get(SIGNBANK, "").strip()]
    if not rs:
        return None
    feats = {k: Counter(r[k] for r in rs).most_common(1)[0][0] for k in FEATURES}
    sb = Counter(r[SIGNBANK] for r in rs).most_common(1)[0][0]
    return feats, sb, len(rs)


def compare(by_label, a: str, b: str):
    pa, pb = profile(by_label, a), profile(by_label, b)
    if pa is None or pb is None:
        missing = a if pa is None else b
        return {"ok": False, "reason": f"no ASL-LEX-annotated clips for '{missing}'"}
    fa, sa, na = pa
    fb, sb, nb = pb
    differ = [k for k in FEATURES if fa[k] != fb[k]]
    return {"ok": True, "a": a, "b": b, "signbank_a": sa, "signbank_b": sb,
            "same_entry": sa == sb, "n_a": na, "n_b": nb,
            "n_differ": len(differ), "differ": differ,
            "verdict": "SAME" if sa == sb else "DIFFERENT",
            "detail": {k: (fa[k], fb[k]) for k in differ}}


def print_pair(r):
    if not r["ok"]:
        print(f"  {r['reason']}")
        return
    mark = "✅ SAME SIGN ENTRY" if r["same_entry"] else "❌ DIFFERENT entries"
    print(f"\n{r['a'].upper()} vs {r['b'].upper()}   {mark}")
    print(f"  SignBank {r['a']}={r['signbank_a']} ({r['n_a']} clips)   "
          f"{r['b']}={r['signbank_b']} ({r['n_b']} clips)")
    print(f"  {17 - r['n_differ']}/17 features identical")
    for k, (va, vb) in r["detail"].items():
        print(f"     {k:24} {va!r:26} vs {vb!r}")


def confusion_measurement(by_label, ship_path: Path):
    print("Do the pairs the MODEL confuses differ on fewer features than random pairs?\n")
    print(f"{'pair':24}{'clips':>6}{'differ':>8}  same entry   leading differences")
    diffs = []
    for a, b, n in CONFUSED:
        r = compare(by_label, a, b)
        if not r["ok"]:
            print(f"{a}->{b:<18}{n:>6}   {r['reason']}")
            continue
        diffs.append(r["n_differ"])
        print(f"{a}->{b:<18}{n:>6}{r['n_differ']:>8}  {str(r['same_entry']):<11}  "
              f"{', '.join(r['differ'][:3])}")

    if not ship_path.exists():
        print(f"\n[skip] baseline needs {ship_path}")
        return
    ship = json.loads(ship_path.read_text())
    pool = [w for w in list(ship["words"]) + list(ship["excluded_too_weak"])
            if profile(by_label, w)]
    rng = np.random.default_rng(0)                 # fixed seed: the baseline must be stable
    rand = []
    for _ in range(400):
        x, y = rng.choice(pool, 2, replace=False)
        r = compare(by_label, x, y)
        if r["ok"]:
            rand.append(r["n_differ"])
    med = float(np.median(diffs))
    frac = sum(1 for d in rand if d <= med) / len(rand)
    print(f"\nconfused pairs    median {med:.1f} of 17 features differ   (n={len(diffs)})")
    print(f"random word pairs median {np.median(rand):.1f}                     (n={len(rand)}, "
          f"pool {len(pool)})")
    print(f"-> only {frac:.1%} of random clinical pairs are as phonologically close as the "
          f"median confused pair.")
    hot = Counter(k for a, b, _ in CONFUSED
                  for k in (compare(by_label, a, b).get("differ") or []))
    print(f"\nfeatures that most often separate a confused pair:")
    for k, c in hot.most_common(5):
        print(f"   {c:2}x  {k}")
    print("\nMOVEMENT features lead. That points at temporal resolution, not the missing face "
          "landmarks —\nand makes `--decimate 0.5` + the fixed-length resize worth testing as "
          "a CAUSE. Hypothesis, untested.")


def fill_review(by_label, path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    i_tied, i_verdict, i_notes = (header.index("tied_glosses"),
                                  header.index("verdict_keep_as"), header.index("notes"))
    filled = 0
    for row in body:
        glosses = [g.strip() for g in row[i_tied].split(";") if g.strip()]
        if len(glosses) != 2 or row[i_verdict].strip():
            continue
        r = compare(by_label, *glosses)
        if not r["ok"] or not r["same_entry"]:
            continue                    # only auto-fill the unambiguous SAME case
        row[i_verdict] = "SAME"
        row[i_notes] = (f"auto: ASL-LEX SignBank {r['signbank_a']} for both "
                        f"({r['n_a']}+{r['n_b']} annotated clips) — same lexical entry. "
                        f"Confirm if you disagree.")
        filled += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + body)
    print(f"auto-resolved {filled} of {len(body)} review rows from ASL-LEX SignBank ids; "
          f"the rest still need a human.")


def main():
    ap = argparse.ArgumentParser(description="resolve gloss identity from ASL-LEX phonology")
    ap.add_argument("--metadata", type=Path, default=Path("semlex_metadata.csv"))
    ap.add_argument("--pair", nargs=2, action="append", metavar=("A", "B"))
    ap.add_argument("--confusions", action="store_true",
                    help="run the confused-vs-random feature-distance measurement")
    ap.add_argument("--review", type=Path,
                    help="fill verdict_keep_as in a review CSV where ASL-LEX is unambiguous")
    ap.add_argument("--ship-vocab", type=Path, default=Path("clinical_ship_vocab.json"))
    args = ap.parse_args()

    if not args.metadata.exists():
        raise SystemExit(f"[err] {args.metadata} not found")
    by_label = load(args.metadata)
    annotated = sum(1 for rs in by_label.values() if any(r.get(SIGNBANK, "").strip() for r in rs))
    print(f"[ok] {len(by_label)} glosses, {annotated} with ASL-LEX annotation\n")

    for a, b in (args.pair or []):
        print_pair(compare(by_label, a, b))
    if args.confusions:
        confusion_measurement(by_label, args.ship_vocab)
    if args.review:
        fill_review(by_label, args.review)
    if not (args.pair or args.confusions or args.review):
        ap.error("nothing to do — pass --pair, --confusions or --review")


if __name__ == "__main__":
    main()
