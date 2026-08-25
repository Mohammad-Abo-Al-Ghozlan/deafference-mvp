#!/usr/bin/env python
"""What does the commit gate buy, and does NARROWING the vocabulary buy more? Both, measured.

WHY (part 1: the gate)
----------------------
A Kaggle diagnostic (2026-08-25, fold-0 canonical model, 7 held-out signers, 30,200 clips)
established that per-signer variance is NOT fixable downstream. Ten hypotheses measured and
refuted, including calibration itself: an ORACLE mean-shift using all 4,361 of the worst
signer's own clips moved it -0.0018, and a within-signer classifier fit on its own labels caps
at 0.3845 while the best signer reaches 0.9282. The information is gone before the model runs.

One axis did work. Gating on softmax confidence collapsed the per-signer spread:

    gate    worst signer   best signer   spread
    none        0.314         0.816       0.502
    0.50        0.690         0.919       0.229
    0.70        0.836         0.971       0.135
    0.80        0.884         0.985       0.101

A coverage gate (hand_cov) was tested alongside and is STRICTLY DOMINATED at matched
throughput -- confidence already encodes the tracking signal -- so this gates on confidence
only, deliberately. Those numbers came from a SINGLE fold-0 model on isolated clips, while the
demo runs the FOUR-fold ensemble through `classify_commit` and then `decide_commit`, a
three-level engine over confidence AND margin AND quality AND stability. This re-prices the
curve through the code that actually runs.

WHY (part 2: narrowing)
-----------------------
`word_acc_250.json` says 26 of the 250 words score <= 0.50 on held-out test, and in 8 of 9
cases a weak class is being ABSORBED by a strong neighbour: nap 0.109 -> sleep 0.714 (46:1),
mouth 0.300 -> lips 0.845 (41:19), look 0.350 -> see 0.983, puppy 0.344 -> dog 0.582 (41:3).
So the vocabulary is not too small, it is too noisy -- and the medical MVP needs a DIFFERENT
vocabulary, not a bigger one: of 130 clinical words only 43 are in the trained 250, and the
covered ones include give 0.151, go 0.220, mouth 0.300, look 0.350.

`--words` masks the softmax to a subset and RENORMALIZES (live_demo._mask_probs), which is why
its help text promises "concentrates confidence". That is a testable claim and nobody has
tested it. With `--words vocab_clinical_43.json` this script measures three things:

  1. IN-DOMAIN, full 250-way   -- the 43 clinical words as the demo scores them today
  2. IN-DOMAIN, narrowed       -- the same clips with only 43 classes competing
  3. OUT-OF-DOMAIN LEAKAGE     -- the other 207 words forced through the 43-way mask, where
                                  every commit is WRONG by construction because the true class
                                  is masked out. This is the cost of narrowing and the reason
                                  it could be a bad idea; a clinic will not only sign the list.

Renormalizing raises every confidence, so a threshold does NOT mean the same thing in the two
conditions. Compare at matched ACCEPT RATE, never at matched gate.

HOW IT STAYS HONEST
-------------------
One forward pass per word stores the FULL 250-dim probability vector; every condition and
every threshold is then arithmetic over the same stored numbers, so no two rows can drift
apart and masking is applied exactly as `_mask_probs` does.

WHAT IT CANNOT TELL YOU
-----------------------
`sign_clips_250.npz` is keyed by WORD -- one exemplar per word, no participant ids. So there is
NO per-signer number here, and per-signer precision was the entire point of the Kaggle table.
Reproducing that needs a Kaggle run with these 4 folds against the by-signer corpus.

Absolute precision is not a model score either -- but NOT for the reason
measure_prefix_accuracy.py's docstring gives. That file asserts these exemplars are training
data and therefore "inflated"; the measurement contradicts it. Ungated top-1 here is 0.696 and
it measured 0.680 full-clip, both BELOW the shipped 4-fold test accuracy of 0.7755. These clips
are HARDER than the real test set, so the precision column is if anything CONSERVATIVE. Treat
it as a shape. Between-row comparisons are the result; the project has been burned three times
by pooled absolutes.

USAGE
    python measure_conf_gate.py                                   # the gate, full 250
    python measure_conf_gate.py --words vocab_clinical_43.json    # + the narrowing test
    python measure_conf_gate.py --single                          # fold-0 only (not the demo)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import live_demo as ld
from sign_landmarks import canonicalize_missing

HERE = Path(__file__).resolve().parent
SRC_FPS = 30                       # the exemplar corpus rate
GATES = (0.30, 0.40, 0.50, 0.58, 0.70, 0.80, 0.90)

# live_demo.py:1340-1347 -- the thresholds `--vocab250` installs. They are assigned INSIDE the
# argparse branch, which never runs on import, so an importer gets the module-level 30-word
# values instead (L1_CONF 0.70, L1_MARGIN 0.30, L2_CONF 0.50, L2_MARGIN 0.18, L2_STABLE 1).
# Measuring against those would price a gate the 250 demo does not use. This is the THIRD time
# this trap has bitten -- see measure_prefix_accuracy.py:81-84 for the ARTIFACTS/VOCAB_PATH
# version. If live_demo's 250 branch changes, this dict must change with it.
V250 = dict(L1_CONF=0.58, L1_MARGIN=0.18, Q_STRONG=0.45,
            L2_CONF=0.40, L2_MARGIN=0.10, L2_STABLE=2)
SHIPPED = {k: v for k, v in V250.items() if k != "L2_STABLE"}   # L2_STABLE is a count, not a gate


def to_live(arr: np.ndarray, live_fps: float) -> np.ndarray:
    """The 30 fps exemplar as a camera running at `live_fps` would have captured it."""
    n = max(2, int(round(arr.shape[0] / SRC_FPS * live_fps)))
    idx = np.linspace(0, arr.shape[0] - 1, n).round().astype(int)
    return arr[idx]


def mask_renorm(p: np.ndarray, allowed: np.ndarray | None) -> np.ndarray:
    """Subset softmax, byte-for-byte what live_demo._mask_probs does."""
    if allowed is None:
        return p
    m = np.zeros_like(p)
    m[allowed] = p[allowed]
    s = m.sum()
    return m / s if s > 0 else p


def rows_from(names, P, Q, index, allowed=None) -> list[dict]:
    """Decision rows under one mask condition, from the stored full-vocab probabilities."""
    out = []
    for w, p, q in zip(names, P, Q):
        pm = mask_renorm(p, allowed)
        order = np.argsort(pm)[::-1]
        out.append({"word": w, "conf": float(pm[order[0]]), "second": float(pm[order[1]]),
                    "q": float(q), "ok": int(order[0] == index[w])})
    return out


def accepted(row: dict, L1_CONF: float, L1_MARGIN: float, Q_STRONG: float,
             L2_CONF: float, L2_MARGIN: float) -> int:
    """Mirror decide_commit's LEVEL 1/2 arithmetic -> 1 (level 1), 2 (level 2), 0 (rejected).

    Parameter names match live_demo's globals on purpose: every caller passes them as **kwargs
    pulled from V250, so a rename on either side fails loudly instead of silently pricing the
    wrong gate. `stable` is treated as satisfied, exactly as commit_segment does -- it calls
    decide_commit(..., stable=L2_STABLE) at the pause, because the sign is FINISHED there and
    temporal confirmation has already happened (live_demo.py:788)."""
    margin = row["conf"] - row["second"]
    if row["conf"] >= L1_CONF and margin >= L1_MARGIN and row["q"] >= Q_STRONG:
        return 1
    if row["conf"] >= L2_CONF and margin >= L2_MARGIN:
        return 2
    return 0


def score(rows: list[dict], **th) -> tuple[int, float]:
    """-> (accepted, precision among accepted)."""
    hits = [r for r in rows if accepted(r, **th)]
    return len(hits), (sum(r["ok"] for r in hits) / len(hits) if hits else float("nan"))


def sweep(rows: list[dict], label: str) -> None:
    n0 = len(rows)
    ung = sum(r["ok"] for r in rows) / n0
    print(f"  {label:<22} ungated {ung:.3f} over {n0} words")
    print(f"    {'gate':>6} {'accept':>8} {'precision':>10}")
    for t in GATES:
        n, prec = score(rows, L1_CONF=t, L1_MARGIN=V250["L1_MARGIN"],
                        Q_STRONG=V250["Q_STRONG"], L2_CONF=t, L2_MARGIN=V250["L2_MARGIN"])
        tag = "   <- L1 today" if abs(t - V250["L1_CONF"]) < 1e-9 else (
              "   <- L2 today" if abs(t - V250["L2_CONF"]) < 1e-9 else "")
        print(f"    {t:>6.2f} {f'{100*n/n0:.0f}%':>8} {prec:>10.3f}{tag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--artifacts", default=str(HERE / "artifacts_250"))
    ap.add_argument("--words", default=None,
                    help="JSON subset (list, or {'words': [...]}) to also measure NARROWED, "
                         "e.g. vocab_clinical_43.json")
    ap.add_argument("--fps", type=float, default=7.0,
                    help="simulated camera rate (default: the demo's observed 7)")
    ap.add_argument("--single", action="store_true",
                    help="fold-0 only; NOT what the demo runs, use for a quick check")
    ap.add_argument("--worst", type=int, default=12, help="how many never-committed words to list")
    args = ap.parse_args()

    words = json.loads(Path(args.vocab).read_text(encoding="utf-8"))["words"]
    index = {w: i for i, w in enumerate(words)}
    # canonicalize_missing turns the npz zero-sentinel into NaN. Without it an absent hand sits
    # at [0,0,0] = mid-sternum and PreprocessLayer's padding mask (built from is_nan) is told
    # every frame is real. Skipping it once already produced a fake 0.000 accuracy.
    with np.load(args.clips) as z:
        clips = {w: canonicalize_missing(z[w].astype(np.float32))
                 for w in z.files if w in index}
    print(f"[ok] {len(clips)} exemplars, {len(words)} classes")

    art = Path(args.artifacts)
    dirs = ([art / "savedmodel_fold0"] if args.single
            else [art / f"savedmodel_fold{k}" for k in range(4)])
    _keep, fns = ld.load_models(dirs)
    print(f"[ok] {'fold-0 only' if args.single else '4-fold ensemble'} from {art.name}")

    for k, v in V250.items():
        was = getattr(ld, k)
        setattr(ld, k, v)
        if was != v:
            print(f"[cfg] {k}: {was} -> {v}   (module default was the 30-word value)")

    # The forward pass must be UNMASKED so one pass serves every condition. classify_commit
    # ends in _mask_probs, which is identity while ALLOWED_IDX is None.
    assert ld.ALLOWED_IDX is None, "ALLOWED_IDX is set; the stored probs would be pre-masked"
    names, P, Q = [], [], []
    for w, arr in clips.items():
        seg = list(to_live(arr, args.fps))          # list of (75,3), as the live loop holds it
        names.append(w)
        P.append(ld.classify_commit(fns, seg))      # view + mirror, the real commit path
        Q.append(ld.segment_quality(seg)[0])
    P = np.stack(P)
    print(f"[ok] {P.shape[0]} forward passes stored, full {P.shape[1]}-dim probs\n")

    full = rows_from(names, P, Q, index)
    n, prec = score(full, **SHIPPED)
    lv = [accepted(r, **SHIPPED) for r in full]
    ung = sum(r["ok"] for r in full) / len(full)
    print(f"THE DEMO AS IT SHIPS TODAY (L1 {V250['L1_CONF']} / L2 {V250['L2_CONF']}, all "
          f"{len(full)} words)")
    print(f"  accept {n}/{len(full)} ({100*n/len(full):.0f}%)   precision {prec:.3f}   "
          f"vs ungated {ung:.3f}  ({prec - ung:+.3f})")
    for level in (1, 2):
        sel = [r for r, l in zip(full, lv) if l == level]
        if sel:
            print(f"    level {level}: {len(sel):>3} accepted, precision "
                  f"{sum(r['ok'] for r in sel)/len(sel):.3f}")

    print("\nCONFIDENCE SWEEP, FULL 250-WAY (margins at shipped values)")
    sweep(full, "all 250 words")

    # Does the margin rule earn its complexity? If zeroing it reproduces the accept set, the
    # engine carries two thresholds that do nothing for precision (they still route L1 vs L2,
    # which is a LATENCY control -- see the note beside them in live_demo).
    print("\nMARGIN ABLATION (L1_MARGIN = L2_MARGIN = 0)")
    print(f"    {'gate':>6} {'accept':>8} {'precision':>10}")
    for t in GATES:
        n, prec = score(full, L1_CONF=t, L1_MARGIN=0.0, Q_STRONG=V250["Q_STRONG"],
                        L2_CONF=t, L2_MARGIN=0.0)
        print(f"    {t:>6.2f} {f'{100*n/len(full):.0f}%':>8} {prec:>10.3f}")

    never = [r for r, l in zip(full, lv) if l == 0]
    right = sum(r["ok"] for r in never)
    print(f"\nNEVER COMMITTED at the shipped gate: {len(never)} words "
          f"({100*len(never)/len(full):.0f}%) -- these fall through to the top-K tap, which "
          f"SHOW_TOPK\ndocuments as the PRIMARY 250-word interaction, not a fallback")
    for r in sorted(never, key=lambda r: -r["conf"])[:args.worst]:
        print(f"   {r['word']:<14} conf {r['conf']:.2f}  margin "
              f"{r['conf']-r['second']:.2f}  q {r['q']:.2f}  "
              f"{'(top-1 was RIGHT)' if r['ok'] else ''}")
    print(f"\n  {right} of those {len(never)} had the CORRECT top-1 -- the gate spends {right} "
          f"right words\n  to remove {len(never) - right} wrong ones. Read that ratio before "
          f"raising the gate.")

    # ── the narrowing test ──────────────────────────────────────────────────────────────────
    if args.words:
        raw = json.loads(Path(args.words).read_text(encoding="utf-8"))
        allow = raw["words"] if isinstance(raw, dict) else raw
        missing = [w for w in allow if w not in index]
        allowed = np.array(sorted({index[w] for w in allow if w in index}), dtype=np.int64)
        if missing:
            print(f"\n[warn] {len(missing)} subset words are not in the model vocab "
                  f"(ignored): {missing[:8]}")
        inset = {words[i] for i in allowed}
        sel = [i for i, w in enumerate(names) if w in inset]
        out = [i for i, w in enumerate(names) if w not in inset]
        print(f"\n{'='*78}\nNARROWING TEST -- {len(allowed)} allowed classes "
              f"({Path(args.words).name})\n{'='*78}")

        nm = lambda ix, al: rows_from([names[i] for i in ix], P[ix], [Q[i] for i in ix],
                                      index, al)
        print("\nIN-DOMAIN: the subset words, scored two ways")
        sweep(nm(sel, None), "full 250-way")
        print()
        sweep(nm(sel, allowed), "narrowed")
        print("\n  Renormalizing raises every confidence, so the two blocks are NOT comparable\n"
              "  at equal gate. Compare them at matched ACCEPT RATE.")

        # The cost nobody would think to measure. Under the mask the true class is gone, so
        # every one of these commits is wrong -- this is the false-accept rate a clinic pays
        # whenever someone signs outside the list.
        leak = nm(out, allowed)
        assert not any(r["ok"] for r in leak), "an out-of-domain word scored correct; mask is wrong"
        print(f"\nOUT-OF-DOMAIN LEAKAGE: the {len(leak)} non-subset words forced through the "
              f"mask.\n  Every commit here is WRONG by construction -- the true class is masked "
              f"out.\n    {'gate':>6} {'commits':>9}  (false-accept rate)")
        for t in GATES:
            n, _ = score(leak, L1_CONF=t, L1_MARGIN=V250["L1_MARGIN"],
                         Q_STRONG=V250["Q_STRONG"], L2_CONF=t, L2_MARGIN=V250["L2_MARGIN"])
            print(f"    {t:>6.2f} {f'{100*n/len(leak):.0f}%':>9}")
        print("\n  Read this against the in-domain gain. Narrowing is worth it only if the\n"
              "  in-domain lift exceeds what these confident-but-wrong commits cost -- and in\n"
              "  a clinic, a confident wrong word is the expensive failure, not a rejection.")

    print("\nREAD THIS AS A SHAPE. One exemplar per word, so precision has an SE near 0.03 at\n"
          "50% accept on 250 and near 0.08 on a 43-word subset. No per-signer breakdown is\n"
          "possible from this npz; that needs a Kaggle run with these 4 folds.")


if __name__ == "__main__":
    main()
