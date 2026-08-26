#!/usr/bin/env python
"""Did dropping the 2a passive-up gate find better-tracked exemplars? And could we have known?

WHAT THIS PRICES
----------------
`build_sign_clips.py --require-passive-up 2s-only` exempts two-handed ASYMMETRIC words from the
gate that requires the passive wrist to be held in signing space. On 2a that gate protects a
quantity that is thrown away downstream: the recorded passive wrist sits a median 1.56 shoulder
widths from the dominant one and is replaced by `asl_2a_base_placement.json`. So it sacrifices
~98% of the candidate pool for nothing -- IF the bigger pool contains a better-tracked take.
That last clause is the whole experiment.

TWO THINGS THIS REPORTS, AND THE SECOND IS THE USEFUL ONE
---------------------------------------------------------
1. WHETHER (needs both arms' .meta.json). Per-class medians, control vs test. The doc's original
   acceptance test also counted "did valid_candidates rise" as evidence of success. It is not
   evidence of anything: with the gate off, 2a has no 2a-specific rule left at all -- the travel
   floor at build_sign_clips.py:362 is `cls == "2s"` and the ceiling at :350 is `cls == "1"` --
   so `valid == aligned`, and :346 states every word has >=55 aligned takes. The pool rise is
   arithmetic and would read as a win even if coverage moved not at all. Only coverage counts.

2. WHY (needs one --dump-candidates CSV, and the CONTROL arm's is enough). Among 2a candidates,
   compare dominant-hand coverage between takes whose passive wrist HANGS and takes where it is
   HELD. The gate keeps only the held ones. So:
       hanging takes score HIGHER  -> the gate is discarding the better-tracked takes. Dropping
                                      it should help, and by roughly the gap shown.
       no difference / lower       -> the corpus has no better take. Tier C is real, and the
                                      remaining levers are the base lexicon and the short-gap hold.
   This is readable from the control arm ALONE, so it predicts the outcome instead of explaining
   it afterwards. Run it on the control dump before the test arm finishes.

   The mechanism it tests is not in the original write-up: root cause R5 is that MediaPipe drops
   the hand that MOVES and struggles most when two hands occlude. A passive hand held UP sits near
   the dominant hand; a hanging one is out of the way. If that dominates, the gate is selecting
   FOR occlusion and therefore AGAINST the very coverage the selector maximizes.

   It could NOT be checked from the shipped per-word meta: every selected 2a exemplar passed the
   gate, so passive_resting is False on 35 of 35 -- zero variance in the predictor. The losers are
   the only place the comparison exists, which is why --dump-candidates was added.

USAGE
    python measure_reselect.py --control clips_control.meta.json --test clips_2sonly.meta.json
    python measure_reselect.py --dump cand_control.csv          # the WHY, control arm alone
    python measure_reselect.py --control A.meta.json --test B.meta.json --dump cand_control.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics as st
from pathlib import Path

CLASSES = ("1", "2s", "2a")
TIER_C = 0.50


# ── stats, hand-rolled: these are bounded fractions with a hard ceiling at 1.0, so a
#    t-test on the means is the wrong shape, and scipy is not installed on the Kaggle CPU
#    image by default.
def mannwhitney_p(a: list[float], b: list[float]) -> tuple[float, float] | tuple[None, None]:
    """Two-sided Mann-Whitney U -> (z, p), normal approximation with tie correction."""
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return None, None
    allv = sorted(a + b)
    rank: dict[float, float] = {}
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        rank[allv[i]] = (i + j) / 2.0 + 1.0
        i = j + 1
    u1 = sum(rank[v] for v in a) - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    counts: dict[float, int] = {}
    for v in allv:
        counts[v] = counts.get(v, 0) + 1
    tie = sum(c ** 3 - c for c in counts.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return None, None
    z = (u1 - n1 * n2 / 2.0) / math.sqrt(var)
    return z, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def cliffs_delta(a: list[float], b: list[float]) -> float:
    """P(a>b) - P(a<b). Reported because a p-value on ~4000 candidates says 'not zero',
    not 'large enough to matter'. |d| < 0.15 is negligible however small p gets."""
    if not a or not b:
        return float("nan")
    b_sorted = sorted(b)
    import bisect
    gt = lt = 0
    for v in a:
        lo = bisect.bisect_left(b_sorted, v)
        hi = bisect.bisect_right(b_sorted, v)
        gt += lo
        lt += len(b_sorted) - hi
    tot = len(a) * len(b)
    return (gt - lt) / tot


def load_meta(p: Path) -> tuple[dict, str]:
    """-> (word -> row, the arm's own name for itself).

    The arm label is read from the meta rather than hardcoded, because a run mislabelled in the
    output is the one way this comparison silently stops being one-variable: `off` and `2s-only`
    differ only on 2s, so a table that calls an `off` run "2s-only" looks like a leaking gate.
    """
    blob = json.loads(p.read_text(encoding="utf-8"))
    arm = (blob.get("validity_filter") or {}).get("require_passive_up") \
        or blob.get("require_passive_up") or "?"
    return {w["word"]: w for w in blob["words"]}, str(arm)


def whether(control: dict, test: dict, arm_a: str = "control", arm_b: str = "test") -> None:
    print("=" * 84)
    print(f"1. WHETHER — per-class medians, --require-passive-up {arm_a} vs {arm_b}")
    print("=" * 84)
    if arm_a == arm_b:
        print(f"  [warn] both arms report --require-passive-up {arm_a!r}. This is not an A/B;\n"
              f"         one of the two files is the wrong run.\n")
    print(f"{'class':<6}{'arm':<10}{'n':>4}{'med valid':>11}{'med cov':>10}"
          f"{'mean cov':>10}{'tierC':>7}")
    # keyed by ARM INDEX, not by label: two runs can legitimately carry the same label (a
    # duplicate file), and a name-keyed dict would silently collapse them into one row.
    got = {}
    for cls in CLASSES:
        for i, (name, M) in enumerate(((arm_a, control), (arm_b, test))):
            r = [v for v in M.values() if v["handedness_class"] == cls]
            if not r:
                continue
            cov = [v["dominant_hand_coverage"] for v in r]
            got[(cls, i)] = dict(
                n=len(r), valid=st.median([v["valid_candidates"] for v in r]),
                med=st.median(cov), mean=st.mean(cov),
                tc=sum(1 for c in cov if c < TIER_C))
            g = got[(cls, i)]
            print(f"{cls:<6}{name:<10}{g['n']:>4}{g['valid']:>11.0f}"
                  f"{g['med']:>10.3f}{g['mean']:>10.3f}{g['tc']:>7}")
        print()

    # 2s is the control on the control: the flag must be a NO-OP there. If 2s moved, the gate is
    # not scoped per class and the 2a number cannot be attributed to the flag.
    if ("2s", 0) in got and ("2s", 1) in got:
        a, b = got[("2s", 0)], got[("2s", 1)]
        same = abs(a["med"] - b["med"]) < 1e-9 and abs(a["mean"] - b["mean"]) < 1e-9
        print(f"  [{'ok' if same else 'FAIL'}] 2s unchanged "
              f"({a['med']:.3f} -> {b['med']:.3f} median, "
              f"{a['mean']:.3f} -> {b['mean']:.3f} mean)")
        if not same:
            print("       The flag is supposed to be a no-op on 2s. It is not, so the gate is not\n"
                  "       applied per class and the 2a result below is NOT clean. Stop and fix.\n"
                  "       (If the test arm is `off` rather than `2s-only`, this is EXPECTED — `off`\n"
                  "        drops the gate for 2s too, which is a different and untested change.)")
        # class 1 never reaches the gate at all (returns at :353) -- a second free invariant
        if ("1", 0) in got and ("1", 1) in got:
            c1a, c1b = got[("1", 0)], got[("1", 1)]
            ok1 = abs(c1a["mean"] - c1b["mean"]) < 1e-9
            print(f"  [{'ok' if ok1 else 'FAIL'}] class 1 unchanged "
                  f"({c1a['mean']:.3f} -> {c1b['mean']:.3f} mean) — it returns before the gate")

    if ("2a", 0) in got and ("2a", 1) in got:
        a, b = got[("2a", 0)], got[("2a", 1)]
        print(f"\n  2a valid candidates : {a['valid']:.0f} -> {b['valid']:.0f}"
              f"   (arithmetic — NOT evidence, see the docstring)")
        print(f"  2a median coverage  : {a['med']:.3f} -> {b['med']:.3f}   ({b['med']-a['med']:+.3f})")
        print(f"  2a mean coverage    : {a['mean']:.3f} -> {b['mean']:.3f}   ({b['mean']-a['mean']:+.3f})")
        print(f"  2a tier-C words     : {a['tc']} -> {b['tc']}   "
              f"({a['tc']-b['tc']:+d} moved out of tier C)")
        d = b["med"] - a["med"]
        print(f"\n  VERDICT: {'RECOVERABLE — re-export the 2a words' if d > 0.15 else 'NOT recoverable — the corpus has no better take; tier C is real'}")
        if 0 < d <= 0.15:
            print(f"           ({d:+.3f} is real but under the 0.15 bar set before the run.\n"
                  f"            It is a gain, not a fix — do not move the bar to fit it.)")


def why(dump: Path) -> None:
    print("\n" + "=" * 84)
    print("2. WHY — does the gate discard the BETTER-tracked 2a takes?")
    print("=" * 84)
    rows = list(csv.DictReader(dump.open(encoding="utf-8")))
    print(f"  {len(rows)} candidates in {dump.name}")

    for cls in CLASSES:
        r = [x for x in rows if x["class"] == cls]
        if not r:
            continue
        # Only ALIGNED takes: a take rejected by the signing-hand gate carries the resting
        # hand and is not a candidate under either arm, so including it would compare the
        # passive-up gate against a different gate's rejects.
        r = [x for x in r if x["aligned"] == "1"]
        hang = [float(x["coverage"]) for x in r if x["passive_resting"] == "1"]
        held = [float(x["coverage"]) for x in r if x["passive_resting"] == "0"]
        none = sum(1 for x in r if x["passive_resting"] == "")
        print(f"\n  class {cls}  (aligned takes only: {len(r)};"
              f" passive wrist untracked on {none}, excluded)")
        if len(hang) < 3 or len(held) < 3:
            print(f"    hanging {len(hang)}, held {len(held)} — too few to compare")
            continue
        print(f"    {'passive wrist':<22}{'n':>6}{'mean cov':>10}{'median':>9}{'>=0.50':>8}")
        for label, g in (("HANGING (gate cuts)", hang), ("HELD (gate keeps)", held)):
            print(f"    {label:<22}{len(g):>6}{st.mean(g):>10.3f}{st.median(g):>9.3f}"
                  f"{sum(1 for v in g if v >= TIER_C) / len(g) * 100:>7.0f}%")
        d = st.median(hang) - st.median(held)
        z, p = mannwhitney_p(hang, held)
        delta = cliffs_delta(hang, held)
        print(f"    median difference (hanging - held): {d:+.3f}")
        if p is not None:
            print(f"    Mann-Whitney p = {p:.2e}   Cliff's delta = {delta:+.3f}"
                  f"   ({'negligible' if abs(delta) < 0.15 else 'small' if abs(delta) < 0.33 else 'medium' if abs(delta) < 0.47 else 'large'})")
        if cls == "2a":
            print()
            if p is not None and p < 0.05 and delta > 0.15:
                print("    READ: the gate is cutting the better-tracked takes. Dropping it should")
                print("          raise 2a coverage, and this is the mechanism that explains why.")
            elif p is not None and p < 0.05 and delta < -0.15:
                print("    READ: the takes the gate KEEPS are better tracked. The gate is helping.")
                print("          Expect the test arm to be flat or worse — and if it improves,")
                print("          the cause is not this mechanism.")
            else:
                print("    READ: no material difference. A bigger pool is unlikely to contain a")
                print("          better take, so expect tier C to hold. That closes the question")
                print("          rather than leaving it open, which is a useful answer.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--control", type=Path, help="control arm .meta.json (--require-passive-up on)")
    ap.add_argument("--test", type=Path, help="test arm .meta.json (--require-passive-up 2s-only)")
    ap.add_argument("--dump", type=Path, help="a --dump-candidates CSV (the control arm's is enough)")
    args = ap.parse_args()

    if not args.control and not args.dump:
        ap.error("give --control and --test (the WHETHER), or --dump (the WHY), or all three")
    if args.control and not args.test:
        ap.error("--control needs --test: comparing against a remembered number confounds the "
                 "flag with whatever else differed between build days")

    if args.control:
        ctrl, arm_a = load_meta(args.control)
        tst, arm_b = load_meta(args.test)
        whether(ctrl, tst, arm_a, arm_b)
    if args.dump:
        why(args.dump)


if __name__ == "__main__":
    main()
