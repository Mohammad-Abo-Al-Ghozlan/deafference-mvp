#!/usr/bin/env python3
"""Measure the medical confidence gate on the HELD-OUT test split.

WHY THIS FILE EXISTS, and why measure_conf_gate.py cannot do its job
--------------------------------------------------------------------
`measure_conf_gate.py` scores the per-word *exemplar* clips. Those clips are TRAINING data,
so it reported in-domain precision **1.000 at every gate from 0.30 to 0.90** — pinned at the
ceiling, carrying no information — and its out-of-domain half divided by zero because every
clip was inside the mask. A gate measured there would be a number about memorisation.

This script scores the 1,373 clips in `split_manifest.parquet` marked `split == "test"`,
from **9 signers no fold ever trained on**. Same clips that produced the published 0.8383.

THE MEASUREMENT THE SAFETY DOC IS MISSING
-----------------------------------------
`docs/MEDICAL_SAFETY_GATES.md` gates words on `per_word_acc` >= 0.80. That is **recall**:
P(model says X | truth is X). A speaking device needs the other direction --
**precision**: P(truth is X | model says X). When the tool speaks "pain", the clinician acts
on "pain"; what matters is whether that utterance is trustworthy, not whether the model
usually catches pain when it occurs. The two come apart badly for rare classes, and nothing
in this project has measured the precision direction until now.

Everything here is local: no GPU, no Kaggle, no network.

Usage:
  python measure_medical_gate.py                       # full measurement -> json + stdout
  python measure_medical_gate.py --selftest             # logic checks, no models needed
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

VOCAB = Path("vocab_medical_123.json")
SHIP = Path("vocab_medical_ship55.json")
GATES = Path("safety_gates_medical.json")
MANIFEST = Path("data_medical/split_manifest.parquet")
BY_WORD = Path("data_medical/by_word")
MODELS = [Path(f"artifacts_medical/savedmodel_fold{i}") for i in range(4)]
PUBLISHED = Path("artifacts_medical/ensemble_test.json")

# The published ensemble number this script must reproduce before any gate figure is
# allowed out. If the clip loading or the class order were wrong, every number downstream
# would be confidently meaningless -- exactly the failure mode `1c9a2fa` exists to prevent.
TARGET_ACC = 0.8383
TOL = 0.002

GRID = [0.0, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

# Recommended operating threshold, chosen from the measured curve rather than inherited from
# the 250-word model: 51% coverage at 0.987 precision, 25x fewer spoken errors than ungated,
# and it sits 0.054 above the highest confidence any dangerous confusion reached (0.746).
# 0.90 buys +0.007 precision for -15% coverage; 0.70 keeps +8% coverage at 0.979.
TAU_REC = 0.80


# ══════════════════════════════════════════════════════════════════════════════════════════
# the two directions, kept explicitly apart
# ══════════════════════════════════════════════════════════════════════════════════════════
def recall_at(y_true, y_pred, conf, cls, tau):
    """P(said cls | truth is cls), among clips that clear tau. The safety doc's number."""
    sel = (y_true == cls) & (conf >= tau)
    return (float((y_pred[sel] == cls).mean()), int(sel.sum())) if sel.sum() else (None, 0)


def precision_at(y_true, y_pred, conf, cls, tau):
    """P(truth is cls | said cls), among clips that clear tau. The number a SPEAKER needs.

    If the tool says `no` and this is 0.75, then one in four spoken refusals is not a
    refusal. Recall cannot see that: a class can be caught 90% of the time it occurs and
    still be wrong most of the times it is announced, if other classes leak into it.
    """
    sel = (y_pred == cls) & (conf >= tau)
    return (float((y_true[sel] == cls).mean()), int(sel.sum())) if sel.sum() else (None, 0)


def coverage_curve(y_true, y_pred, conf, grid=GRID):
    """What a threshold buys overall: how much you still say, and how often it is right."""
    rows = []
    for tau in grid:
        sel = conf >= tau
        n = int(sel.sum())
        rows.append({
            "tau": tau,
            "coverage": round(n / len(conf), 4),
            "n_spoken": n,
            "precision": round(float((y_true[sel] == y_pred[sel]).mean()), 4) if n else None,
            # errors that still get through -- the number that decides whether a gate helps
            "errors_spoken": int((y_true[sel] != y_pred[sel]).sum()) if n else 0,
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════
def load_test_clips(vocab):
    import pandas as pd
    m = pd.read_parquet(MANIFEST)
    t = m[m["split"] == "test"].reset_index(drop=True)
    idx = {w: i for i, w in enumerate(vocab)}

    cache, X, y, sig, missing = {}, [], [], [], []
    for r in t.itertuples():
        if r.word not in cache:
            p = BY_WORD / r.word / "sequences.npz"
            cache[r.word] = np.load(p, allow_pickle=False) if p.exists() else None
        z = cache[r.word]
        key = f"{r.participant_id}_{r.sequence_id}"
        if z is None or key not in z:
            missing.append((r.word, key))
            continue
        X.append(z[key])
        y.append(idx[r.word])
        sig.append(str(r.participant_id))
    if missing:
        print(f"[warn] {len(missing)} manifest rows had no clip, e.g. {missing[:3]}")
    return np.asarray(X, np.float32), np.asarray(y, np.int64), np.asarray(sig), t


def ensemble_probs(X):
    import tensorflow as tf
    keep, per_model = [], []
    for d in MODELS:
        if not d.exists():
            sys.exit(f"[err] missing {d}")
        obj = tf.saved_model.load(str(d))
        sigs = obj.signatures
        k = "serving_default" if "serving_default" in sigs else list(sigs)[0]
        fn = sigs[k]
        keep.append(obj)                                   # keep alive; TF will GC otherwise
        out = []
        for i in range(0, len(X), 128):
            b = tf.constant(X[i:i + 128])
            try:
                o = fn(landmarks=b)
            except TypeError:
                o = fn(b)
            logits = o["output_0"] if "output_0" in o else list(o.values())[0]
            out.append(tf.nn.softmax(logits, axis=1).numpy())
        per_model.append(np.concatenate(out, 0))
        print(f"[ok] {d.name}")
    return np.mean(per_model, 0), per_model


# ══════════════════════════════════════════════════════════════════════════════════════════
def selftest() -> int:
    print("=== SELFTEST (no models, no data) ===")
    ok = True

    def check(c, label):
        nonlocal ok
        ok &= bool(c)
        print(f"  {'ok  ' if c else 'FAIL'} {label}")

    # A class caught every time it occurs (recall 1.0) can still be wrong most times it is
    # ANNOUNCED. This is the whole reason the script exists, so assert it on a hand case.
    #   truth:  A A B B B B     pred: A A A A A B
    yt = np.array([0, 0, 1, 1, 1, 1])
    yp = np.array([0, 0, 0, 0, 0, 1])
    cf = np.ones(6)
    r, nr = recall_at(yt, yp, cf, 0, 0.0)
    p, npv = precision_at(yt, yp, cf, 0, 0.0)
    check(r == 1.0 and nr == 2, f"recall(A) = 1.00 on {nr} true-A clips")
    check(abs(p - 0.4) < 1e-9 and npv == 5, f"precision(A) = {p:.2f} on {npv} announcements")
    check(r > p, "recall and precision DISAGREE — a 0.80 recall gate says nothing about "
                 "what an utterance is worth")

    # a threshold must trade coverage for precision monotonically in coverage
    conf = np.array([0.95, 0.85, 0.55, 0.35])
    yt2, yp2 = np.array([0, 1, 2, 3]), np.array([0, 1, 9, 9])
    cur = coverage_curve(yt2, yp2, conf, [0.0, 0.5, 0.9])
    check([c["coverage"] for c in cur] == [1.0, 0.75, 0.25],
          "coverage falls as tau rises (4/4 -> 3/4 -> 1/4)")
    check(cur[0]["precision"] == 0.5 and cur[-1]["precision"] == 1.0,
          "precision rises as tau rises (0.50 -> 1.00)")
    check(cur[0]["errors_spoken"] == 2 and cur[-1]["errors_spoken"] == 0,
          "errors_spoken counts the mistakes a gate still lets through")

    # empty selections must return None, not crash or report a fake 0.0
    check(precision_at(yt, yp, cf, 5, 0.0) == (None, 0), "an unannounced class returns None")
    check(recall_at(yt, yp, cf, 0, 1.5) == (None, 0), "a tau nothing clears returns None")

    # the reproduce gate must actually be able to fail
    check(abs(0.8383 - TARGET_ACC) < TOL and not abs(0.80 - TARGET_ACC) < TOL,
          "the 0.8383 reproduce check accepts the published value and rejects 0.80")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


# ══════════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="medical_gate_test.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))["words"]
    ship = set(json.loads(SHIP.read_text(encoding="utf-8"))["words"])
    gates = json.loads(GATES.read_text(encoding="utf-8"))
    never = set(gates["never_auto_commit"])
    print(f"[vocab] {len(vocab)} classes, {len(ship)} shippable, {len(never)} never-auto-commit")

    X, y, sig, man = load_test_clips(vocab)
    print(f"[data] {len(X)} test clips, {len(set(sig.tolist()))} held-out signers, "
          f"{len(set(y.tolist()))} classes present")

    probs, per_model = ensemble_probs(X)
    pred = probs.argmax(1)
    conf = probs.max(1)
    acc = float((pred == y).mean())

    # ── the reproduce gate ────────────────────────────────────────────────────────────────
    pub = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    singles = [float((p.argmax(1) == y).mean()) for p in per_model]
    top5 = float(np.mean([y[i] in probs[i].argsort()[-5:] for i in range(len(y))]))
    print(f"\n[reproduce] ensemble {acc:.4f} vs published {pub['ensemble_acc']:.4f}   "
          f"top5 {top5:.4f} vs {pub['ensemble_top5_acc']:.4f}")
    print(f"[reproduce] per-fold {[round(s, 4) for s in singles]}")
    print(f"[reproduce] published {[m['acc'] for m in pub['per_model_acc']]}")
    if abs(acc - TARGET_ACC) > TOL:
        sys.exit(f"[err] REFUSING to report gate numbers. Reproduced {acc:.4f}, expected "
                 f"{TARGET_ACC} +/- {TOL}.\n      The clip loading or the class order is "
                 f"wrong, and every figure below would be confidently meaningless.")
    print("[reproduce] ✅ matches — the loading and class order are right, so the gate "
          "numbers below mean something")

    # ── 1. what a threshold buys overall ─────────────────────────────────────────────────
    curve = coverage_curve(y, pred, conf)
    print("\n=== 1. THE GATE CURVE — what a confidence threshold actually buys ===")
    print(f"{'tau':>6} {'coverage':>9} {'spoken':>7} {'precision':>10} {'errors still spoken':>20}")
    for r in curve:
        print(f"{r['tau']:>6.2f} {r['coverage']:>9.1%} {r['n_spoken']:>7} "
              f"{r['precision']:>10.4f} {r['errors_spoken']:>20}")

    # ── 2. recall vs precision, per word ─────────────────────────────────────────────────
    print("\n=== 2. RECALL vs PRECISION per word (ungated) — the doc gates on recall ===")
    rows = []
    for c, w in enumerate(vocab):
        rec, nrec = recall_at(y, pred, conf, c, 0.0)
        pre, npre = precision_at(y, pred, conf, c, 0.0)
        if rec is None and pre is None:
            continue
        rows.append({"word": w, "recall": rec, "n_true": nrec, "precision": pre,
                     "n_said": npre, "in_ship": w in ship, "never_auto": w in never,
                     "gap": None if (rec is None or pre is None) else round(rec - pre, 4)})
    both = [r for r in rows if r["recall"] is not None and r["precision"] is not None]
    print(f"{'word':<12} {'recall':>7} {'n_true':>7} {'prec':>7} {'n_said':>7} "
          f"{'gap':>7}  flags")
    worst = sorted([r for r in both if r["in_ship"]], key=lambda r: r["precision"])[:12]
    for r in worst:
        f = ("SHIP " if r["in_ship"] else "") + ("NEVER-AUTO" if r["never_auto"] else "")
        print(f"{r['word']:<12} {r['recall']:>7.3f} {r['n_true']:>7} {r['precision']:>7.3f} "
              f"{r['n_said']:>7} {r['gap']:>+7.3f}  {f}")
    print("  ^ the 12 SHIPPED words with the worst precision. Recall passed the 0.80 gate; "
          "precision is what an utterance is worth.")

    # ── 2b. does the gate RESCUE those words? precision at the operating threshold ────────
    print(f"\n=== 2b. THE SHIP LIST RE-CUT ON PRECISION AT tau={TAU_REC} ===")
    print("The 0.80 ship gate is on ungated RECALL. This is the same bar on precision at "
          "the\noperating point — i.e. how much a spoken utterance is actually worth.")
    resc, still, unmeasurable = [], [], []
    for r in rows:
        if not r["in_ship"]:
            continue
        c = vocab.index(r["word"])
        p, n = precision_at(y, pred, conf, c, TAU_REC)
        r["precision_at_tau"], r["n_said_at_tau"] = p, n
        if p is None:
            unmeasurable.append(r["word"])
        elif r["precision"] < 0.80 <= p:
            resc.append((r["word"], r["precision"], p, n))
        elif p < 0.80:
            still.append((r["word"], r["precision"], p, n))
    print(f"\n  RESCUED by the gate ({len(resc)}) — fail ungated, pass at tau={TAU_REC}:")
    for w, p0, p1, n in sorted(resc, key=lambda t: -t[2]):
        print(f"    {w:<10} {p0:.3f} -> {p1:.3f}  (said {n}x at tau)")
    print(f"\n  🔴 STILL FAILING at tau={TAU_REC} ({len(still)}) — these are the de-ship "
          f"candidates:")
    for w, p0, p1, n in sorted(still, key=lambda t: t[2]):
        print(f"    {w:<10} {p0:.3f} -> {p1:.3f}  (said {n}x at tau)")
    if unmeasurable:
        print(f"\n  never announced at tau={TAU_REC}, so precision is undefined "
              f"({len(unmeasurable)}): {', '.join(sorted(unmeasurable))}")
        print("    ^ NOT a pass. The gate simply silences them; they cannot be spoken at all.")

    # ── 3. the never-auto-commit words, gated and ungated ────────────────────────────────
    print("\n=== 3. THE 10 NEVER-AUTO-COMMIT WORDS — precision at each tau ===")
    print(f"{'word':<10} " + " ".join(f"{t:>6.2f}" for t in [0.0, 0.5, 0.7, 0.8, 0.9]) +
          "   (n said at tau=0)")
    gated = {}
    for w in sorted(never):
        if w not in vocab:
            print(f"{w:<10} not in the model")
            continue
        c = vocab.index(w)
        cells, n0 = [], precision_at(y, pred, conf, c, 0.0)[1]
        for t in [0.0, 0.5, 0.7, 0.8, 0.9]:
            p, n = precision_at(y, pred, conf, c, t)
            cells.append("   --- " if p is None else f"{p:>6.3f} ")
        gated[w] = {str(t): precision_at(y, pred, conf, c, t) for t in GRID}
        print(f"{w:<10} " + " ".join(cells) + f"   n={n0}")

    # ── 4. do dangerous confusions happen at HIGH confidence? ────────────────────────────
    print("\n=== 4. THE DECISIVE ONE — at what confidence do dangerous confusions fire? ===")
    print("If they fire HIGH, no threshold can stop them and the never-auto-commit list is "
          "the only defence.")
    danger = []
    for d in gates["dangerous_confusions"]:
        tw, pw = d["true"], d["predicted"]
        if tw not in vocab or pw not in vocab:
            continue
        tc, pc = vocab.index(tw), vocab.index(pw)
        sel = (y == tc) & (pred == pc)
        if not sel.sum():
            continue
        cs = conf[sel]
        danger.append({"true": tw, "predicted": pw, "n": int(sel.sum()),
                       "conf_median": round(float(np.median(cs)), 4),
                       "conf_max": round(float(cs.max()), 4),
                       "n_above_0.80": int((cs >= 0.80).sum()),
                       "kinds": d["kinds"],
                       "predicted_in_ship_vocab": d["predicted_in_ship_vocab"]})
    danger.sort(key=lambda r: -r["conf_max"])
    print(f"{'true':<10} -> {'said':<10} {'n':>3} {'med conf':>9} {'max conf':>9} "
          f"{'>=0.80':>7}  kinds")
    for r in danger[:15]:
        print(f"{r['true']:<10} -> {r['predicted']:<10} {r['n']:>3} {r['conf_median']:>9.3f} "
              f"{r['conf_max']:>9.3f} {r['n_above_0.80']:>7}  {','.join(r['kinds'])}")
    tot = sum(r["n"] for r in danger)
    hi = sum(r["n_above_0.80"] for r in danger)
    print(f"\n  {tot} dangerous-confusion clips occurred; {hi} of them at confidence "
          f">= 0.80 ({hi/max(tot,1):.0%}).")
    print("  A 0.80 gate would suppress the other "
          f"{tot-hi} and let these {hi} through unchanged.")

    # ── 5. per-signer, because pooled numbers hide subgroups ─────────────────────────────
    print("\n=== 5. PER-SIGNER accuracy — mandatory, not a courtesy ===")
    ps = {}
    for s in sorted(set(sig.tolist())):
        m = sig == s
        ps[s] = {"acc": round(float((pred[m] == y[m]).mean()), 4), "n": int(m.sum()),
                 "mean_conf": round(float(conf[m].mean()), 4)}
        print(f"  p{s:<4} acc {ps[s]['acc']:.4f}  n={ps[s]['n']:<4} "
              f"mean conf {ps[s]['mean_conf']:.3f}")
    accs = [v["acc"] for v in ps.values()]
    print(f"  spread {min(accs):.4f} -> {max(accs):.4f} = {max(accs)/min(accs):.2f}x")

    out = {
        "note": "Confidence gate measured on the HELD-OUT test split (9 unseen signers). "
                "Supersedes measure_conf_gate.py, which scored TRAINING exemplars and "
                "reported precision 1.000 at every gate.",
        "reproduced": {"ensemble_acc": round(acc, 4), "published": pub["ensemble_acc"],
                       "top5": round(top5, 4), "per_fold": [round(s, 4) for s in singles]},
        "n_clips": int(len(X)), "n_signers": len(set(sig.tolist())),
        "recommended_tau": TAU_REC,
        "ship_recut_at_tau": {"rescued": resc, "still_failing": still,
                              "silenced_never_announced": sorted(unmeasurable)},
        "gate_curve": curve,
        "per_word_recall_vs_precision": rows,
        "never_auto_commit_precision": {k: {t: v for t, v in d.items()}
                                        for k, d in gated.items()},
        "dangerous_confusions_observed": danger,
        "dangerous_clips_total": tot, "dangerous_clips_above_080": hi,
        "per_signer": ps,
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
