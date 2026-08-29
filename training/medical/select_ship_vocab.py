#!/usr/bin/env python3
"""
Pick the SHIPPABLE clinical vocabulary from a measured confusion matrix.

Why this exists — the 2026-08-29 lesson
---------------------------------------
`ensemble_eval.py` prints per-word accuracy for every class present in the split. On the
first clinical run that produced "50 concepts >=0.90 / 66 >=0.80 / 75 >=0.70", and all three
numbers were wrong in BOTH directions, because **15 of the 122 scored classes had <=2 test
clips**. A class with one test clip scores exactly 0.000 or exactly 1.000 — it measures
nothing. `throat 0.000` was one clip called `give`; `arm 0.000` was two clips. Words also
landed in the ship list on a single lucky clip.

So the rule here has TWO gates, not one:

    n >= --min-test-clips   AND   acc >= --min-acc

and everything below the first gate is reported as **unmeasured**, never as "bad". The
distinction matters: an unmeasured word needs more held-out signers, a weak word needs a
different fix.

Reading the confusion matrix
----------------------------
`ensemble_test.confusion.csv` is num_classes-square, `conf[true, predicted]`, in the vocab
order `train.py` built (`sorted(manifest.word.unique())`). Newer reports carry that order in
`class_names`. Older ones do not, and reconstructing it from `per_word_acc`'s keys alone is
WRONG — those keys cover only the classes present in the split, so every row after the first
absent class shifts by one. The fallback below recovers it exactly instead: a class is absent
from the split iff its confusion ROW sums to zero (a row sum is how many times that class was
the true label), so zipping `sorted(per_word_acc)` onto the non-empty rows is an exact
alignment. It is proven against the diagonal before anything is printed.

Row counts (`n`) always come from the confusion matrix; `per_word_acc` does not carry them.

Usage
-----
  python select_ship_vocab.py \
      --report /kaggle/input/notebooks/<user>/<nb>/art_medical/ensemble_test.json \
      --out clinical_ship_vocab.json

  # stricter, e.g. for an unattended kiosk
  python select_ship_vocab.py --report ... --min-acc 0.90 --min-test-clips 8

Output is drop-in compatible with `live_demo.py --words <file>` (same shape as the
`topic_*.json` masks: `note` / `min_test_acc` / `mean_test_acc` / `words`).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# Words where being WRONG is materially worse than being silent, because the error does not
# degrade the sentence — it inverts or rescales it. "I am NOT allergic" / "it is WORSE".
# These must route through the L2 confirm path regardless of measured accuracy, and if one of
# them fails the gate, dropping it silently is not an answer: the UI needs an explicit control
# (a negation toggle, a severity picker) or the clinician gets a confident half-truth.
SAFETY_CRITICAL = {
    "not", "no", "yes", "never", "always",          # polarity
    "all", "some", "much", "maybe",                 # quantity / hedge
    "worse", "better", "very", "strong", "bad",     # severity direction
}


def load_report(report_path: Path):
    """-> (report, conf, labels, order_source). Raises if the two files disagree."""
    conf_path = report_path.with_suffix(".confusion.csv")
    if not conf_path.exists():
        raise SystemExit(f"[err] no confusion matrix beside the report: {conf_path}")
    rep = json.loads(report_path.read_text())
    conf = np.loadtxt(conf_path, delimiter=",", dtype=int)
    if conf.ndim != 2 or conf.shape[0] != conf.shape[1]:
        raise SystemExit(f"[err] confusion matrix is {conf.shape}, expected square")
    if conf.shape[0] != rep["n_classes"]:
        raise SystemExit(f"[err] confusion is {conf.shape[0]}-square but the report says "
                         f"n_classes={rep['n_classes']} — mismatched files")

    if rep.get("class_names"):
        labels = list(rep["class_names"])
        source = "class_names (recorded by ensemble_eval.py)"
    else:
        # Legacy report. Recover the order exactly — see the module docstring.
        scored = sorted(rep["per_word_acc"])
        present = [i for i in range(conf.shape[0]) if conf[i].sum() > 0]
        if len(scored) != len(present):
            raise SystemExit(f"[err] {len(scored)} scored words but {len(present)} non-empty "
                             f"confusion rows — cannot recover the label order. Re-run "
                             f"ensemble_eval.py, which now records class_names.")
        # Classes absent from the split have no recoverable NAME (they appear in neither
        # per_word_acc nor as a non-empty row), only an index. Number the placeholders — a
        # shared name would collapse two distinct classes into one dict key and silently
        # lose a class from every count below.
        labels = [f"<unnamed-class-{i}>" for i in range(conf.shape[0])]
        for w, i in zip(scored, present):
            labels[i] = w
        source = "recovered from non-empty rows (report predates class_names)"
    return rep, conf, labels, source


def verify(rep, conf, labels) -> float:
    """Max |diagonal accuracy - reported accuracy| over scored words. Proves the row order."""
    idx = {w: i for i, w in enumerate(labels)}
    worst = 0.0
    for w, a in rep["per_word_acc"].items():
        i = idx.get(w)
        if i is None or conf[i].sum() == 0:
            raise SystemExit(f"[err] '{w}' is scored in the report but has an empty "
                             f"confusion row — the label order is wrong")
        worst = max(worst, abs(conf[i, i] / conf[i].sum() - a))
    return worst


def main():
    ap = argparse.ArgumentParser(description="pick the shippable vocabulary from a confusion matrix")
    ap.add_argument("--report", type=Path, required=True,
                    help="ensemble_test.json (the .confusion.csv must sit beside it)")
    ap.add_argument("--min-test-clips", type=int, default=5,
                    help="below this a class is UNMEASURED, not bad (default 5)")
    ap.add_argument("--min-acc", type=float, default=0.80,
                    help="accuracy gate for the ship list (default 0.80)")
    ap.add_argument("--out", type=Path, default=Path("clinical_ship_vocab.json"))
    args = ap.parse_args()

    rep, conf, labels, source = load_report(args.report)
    err = verify(rep, conf, labels)
    if err >= 0.006:
        raise SystemExit(f"[err] label alignment FAILED — max diagonal error {err:.4f}")
    print(f"[ok] {conf.shape[0]} classes, {conf.sum()} clips in split '{rep.get('split')}'")
    print(f"[ok] label order from {source}; verified, max diagonal error {err:.5f}\n")

    n = conf.sum(1)
    acc = np.divide(np.diag(conf), n, out=np.zeros(conf.shape[0], float), where=n > 0)

    ship, weak, unmeasured = {}, {}, {}
    for i, w in enumerate(labels):
        if n[i] < args.min_test_clips:
            unmeasured[w] = int(n[i])
        elif acc[i] >= args.min_acc:
            ship[w] = round(float(acc[i]), 3)
        else:
            weak[w] = round(float(acc[i]), 3)

    # Every class lands in exactly one bucket. If this ever trips, two classes are sharing a
    # name and one is being silently overwritten — which is how the first version lost a class.
    total = len(ship) + len(weak) + len(unmeasured)
    if total != conf.shape[0]:
        raise SystemExit(f"[err] {total} classes bucketed but the matrix has {conf.shape[0]} — "
                         f"duplicate class names in the label list")

    # A safety-critical word that fails the gate is NOT simply dropped — see SAFETY_CRITICAL.
    dropped_critical = sorted(w for w in set(weak) | set(unmeasured) if w in SAFETY_CRITICAL)
    kept_critical = sorted(w for w in ship if w in SAFETY_CRITICAL)

    measurable = int((n >= args.min_test_clips).sum())
    mean_acc = float(np.mean(list(ship.values()))) if ship else 0.0
    out = {
        "note": f"Shippable clinical vocabulary: {len(ship)} concepts, every one measured on "
                f">={args.min_test_clips} held-out test clips and scoring >={args.min_acc:.2f}. "
                f"Drop-in for live_demo.py --words. Narrowing also HELPS accuracy — the 250-word "
                f"A/B measured +0.116 at 43 words and +0.014 at 224 — so removing "
                f"{conf.shape[0] - len(ship)} competitors is a second, separate win.",
        "min_test_acc": args.min_acc,
        "min_test_clips": args.min_test_clips,
        "mean_test_acc": round(mean_acc, 4),
        "words": sorted(ship),
        "ship_detail": dict(sorted(ship.items(), key=lambda kv: -kv[1])),
        "excluded_too_weak": dict(sorted(weak.items(), key=lambda kv: kv[1])),
        "excluded_unmeasured": dict(sorted(unmeasured.items(), key=lambda kv: kv[1])),
        "confirm_required": kept_critical,
        "excluded_but_safety_critical": dropped_critical,
        "source_report": str(args.report),
        "source_model": {k: rep.get(k) for k in
                         ("split", "n_models", "n_classes", "n_samples", "ensemble_acc",
                          "ensemble_top5_acc", "per_word_macro_mean")},
        "caveats": [
            f"{len(unmeasured)} classes have <{args.min_test_clips} test clips. They are "
            f"UNMEASURED, not bad — a 1-clip class scores exactly 0.000 or 1.000. Do not quote "
            f"them in either direction; they need more held-out signers, not a model change.",
            "Macro accuracy rises with test-n (0.7202 at n>=1 to 0.8474 at n>=10) but that is "
            "CONFOUNDED: test is a ~22% whole-signer split, so a thin test class is also a thin "
            "TRAINING class. Undertrained and unmeasured cannot be separated from this data.",
            "Regenerate after any vocabulary merge (pain<-hurt, now<-today) — those change the "
            "class set, so every number here is measured on the pre-merge model.",
        ],
    }
    args.out.write_text(json.dumps(out, indent=1))

    print(f"SHIP        {len(ship):3} concepts   mean acc {mean_acc:.3f}")
    print(f"too weak    {len(weak):3} concepts   {', '.join(sorted(weak)) or '-'}")
    print(f"unmeasured  {len(unmeasured):3} concepts   (<{args.min_test_clips} test clips)")
    print(f"            of {measurable} measurable classes, {len(ship)} pass, {len(weak)} fail\n")
    if kept_critical:
        print(f"⚠️  shipped but MUST route through L2 confirm (an error here inverts the "
              f"sentence): {', '.join(kept_critical)}")
    if dropped_critical:
        print(f"🚨 safety-critical words that FAILED the gate: {', '.join(dropped_critical)}")
        print("   Dropping these silently is not an answer — the UI needs an explicit control "
              "(negation toggle / severity picker) or the clinician gets a confident half-truth.")
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
