#!/usr/bin/env python3
"""
Diff two `build_sign_clips.py` arms word by word — and look for REGRESSIONS.

The 2026-08-26 reselect A/B shipped on medians: `--require-passive-up 2s-only` moved 2a
median coverage 0.432 -> 0.829 and cleared all 24 tier-C 2a words. Both invariants held (2s
and class 1 unchanged), so the gain was attributable to the flag.

**A median cannot show you a word that got worse.** 250 words moved; if six of them dropped
below a usable threshold while the other 244 rose, the medians would look exactly the same and
the renderer would be visibly broken on six signs. Nobody had checked. This checks.

It also re-verifies the invariants EXACTLY rather than on medians: class 1 and 2s should keep
byte-identical exemplars, because the gate is scoped to 2s and class 1 returns before it. An
invariant that holds "on the median" is not an invariant.

What each column means
  coverage   DOMINANT-hand tracking coverage inside the sign extent. This is the selector's
             objective and the thing that degrades the avatar when it falls.
  exemplar   which take was chosen (`source_clip`). A word can keep its coverage and still
             swap exemplars; that is worth seeing separately.
  valid_candidates  how many takes survived the validity filter — the starvation measure.

Usage
  python training/diff_reselect_arms.py --a clips_off.meta.json --b clips_2sonly.meta.json
  python training/diff_reselect_arms.py --a ... --b ... --out docs/RESELECT_DIFF.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

# Below this the animation side treats a word as not usable (docs/AVATAR_LIMITS.md tiering).
TIER_C = 0.50
TIER_B = 0.70


def load(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc, {w["word"]: w for w in doc["words"]}


def tier(c):
    return "A" if c >= TIER_B else ("B" if c >= TIER_C else "C")


def main():
    ap = argparse.ArgumentParser(description="word-level diff of two reselect arms")
    ap.add_argument("--a", type=Path, default=Path("clips_off.meta.json"), help="control arm")
    ap.add_argument("--b", type=Path, default=Path("clips_2sonly.meta.json"), help="test arm")
    ap.add_argument("--out", type=Path, default=Path("docs/RESELECT_DIFF.csv"))
    ap.add_argument("--eps", type=float, default=0.005,
                    help="coverage change below this counts as unchanged (rounding)")
    args = ap.parse_args()

    da, A = load(args.a)
    db, B = load(args.b)
    ga = da["validity_filter"].get("require_passive_up")
    gb = db["validity_filter"].get("require_passive_up")
    print(f"A = {args.a.name}   require_passive_up = {ga!r}")
    print(f"B = {args.b.name}   require_passive_up = {gb!r}")
    shared = sorted(set(A) & set(B))
    print(f"{len(shared)} words in both  (A only {len(set(A)-set(B))}, B only {len(set(B)-set(A))})\n")

    rows = []
    for w in shared:
        a, b = A[w], B[w]
        ca, cb = a["dominant_hand_coverage"], b["dominant_hand_coverage"]
        rows.append({
            "word": w, "class": a["handedness_class"], "conf": a["handedness_confidence"],
            "coverage_a": ca, "coverage_b": cb, "delta": round(cb - ca, 4),
            "tier_a": tier(ca), "tier_b": tier(cb),
            "exemplar_changed": "yes" if a["source_clip"] != b["source_clip"] else "",
            "valid_cand_a": a["valid_candidates"], "valid_cand_b": b["valid_candidates"],
            "fallback_a": a["validity_fallback"], "fallback_b": b["validity_fallback"],
            "source_a": a["source_clip"], "source_b": b["source_clip"],
        })

    by_class = defaultdict(list)
    for r in rows:
        by_class[r["class"]].append(r)

    print(f"{'class':7}{'n':>5}{'median A':>10}{'median B':>10}{'delta':>9}"
          f"{'exemplars changed':>19}")
    for cls in ("1", "2s", "2a"):
        rs = by_class.get(cls, [])
        if not rs:
            continue
        ma = float(np.median([r["coverage_a"] for r in rs]))
        mb = float(np.median([r["coverage_b"] for r in rs]))
        ch = sum(1 for r in rs if r["exemplar_changed"])
        print(f"{cls:7}{len(rs):>5}{ma:>10.3f}{mb:>10.3f}{mb-ma:>+9.3f}{ch:>13} / {len(rs)}")

    # THE INVARIANTS. Which classes SHOULD be identical is a function of the two flag values,
    # not a constant — get this wrong and the expected behaviour reads as a broken invariant.
    # `require_passive_up` names the classes the gate is applied to; class 1 returns before it
    # in every setting.
    expected_scope = {"off": set(), "2s-only": {"2s"}, "on": {"2s", "2a"}, "all": {"2s", "2a"}}
    sa, sb = expected_scope.get(ga), expected_scope.get(gb)
    if sa is None or sb is None:
        changed_by_design = None
        print(f"\n[warn] unrecognised gate value(s) {ga!r}/{gb!r} — cannot predict which "
              f"classes should move; treating every class as free to change.")
    else:
        changed_by_design = sa ^ sb                     # classes where the gate differs
        print(f"\nGATE SCOPE  A={sorted(sa) or ['none']}  B={sorted(sb) or ['none']}  "
              f"-> only class {sorted(changed_by_design) or ['none']} should move")

    print("INVARIANTS:")
    for cls in ("1", "2s", "2a"):
        rs = by_class.get(cls, [])
        if not rs:
            continue
        moved = [r for r in rs if abs(r["delta"]) > args.eps or r["exemplar_changed"]]
        if changed_by_design is not None and cls in changed_by_design:
            print(f"  class {cls:<3} {len(moved)}/{len(rs)} moved — EXPECTED, the gate differs here")
            continue
        state = "HOLDS exactly" if not moved else f"⚠️ BROKEN — {len(moved)} word(s) moved"
        print(f"  class {cls:<3} {state}")
        for r in moved[:8]:
            print(f"      {r['word']:14} {r['coverage_a']:.3f} -> {r['coverage_b']:.3f} "
                  f"({r['delta']:+.3f}) exemplar_changed={r['exemplar_changed'] or 'no'}")

    # THE POINT OF THIS SCRIPT: a median cannot show you the words that got worse.
    regressed = sorted((r for r in rows if r["delta"] < -args.eps), key=lambda r: r["delta"])
    dropped = [r for r in regressed if r["tier_a"] != r["tier_b"]]
    to_c = [r for r in regressed if r["tier_b"] == "C" and r["tier_a"] != "C"]
    print(f"\nREGRESSIONS — words B made WORSE than A: {len(regressed)}"
          f"   ({len(dropped)} changed tier, {len(to_c)} fell into tier C)")
    if regressed:
        print(f"  {'word':14}{'class':>6}{'A':>8}{'B':>8}{'delta':>9}  tier")
        for r in regressed[:20]:
            arrow = f"{r['tier_a']}->{r['tier_b']}"
            flag = "  <-- fell to UNUSABLE" if r["tier_b"] == "C" and r["tier_a"] != "C" else ""
            print(f"  {r['word']:14}{r['class']:>6}{r['coverage_a']:>8.3f}"
                  f"{r['coverage_b']:>8.3f}{r['delta']:>+9.3f}  {arrow}{flag}")
        if len(regressed) > 20:
            print(f"  ... {len(regressed) - 20} more, full list in the CSV")
        print("\n  ⚠️ A regression here is a COST, not necessarily a bug. Where the gate is ON,"
              "\n     it is deliberately trading dominant-hand coverage for a passive wrist that"
              "\n     is actually raised — for 2s that wrist is where the mirrored handshape gets"
              "\n     placed, so a hanging one renders a wrong pose at full coverage. This is the"
              "\n     price of that trade, per word, which the medians could not show.")
    else:
        print("  none. The median gain came with no word-level cost.")

    improved = [r for r in rows if r["delta"] > args.eps]
    print(f"\nIMPROVED {len(improved)}   unchanged "
          f"{len(rows) - len(improved) - len(regressed)}   regressed {len(regressed)}")
    moves = defaultdict(int)
    for r in rows:
        if r["tier_a"] != r["tier_b"]:
            moves[f"{r['tier_a']} -> {r['tier_b']}"] += 1
    print("tier movement: " + (", ".join(f"{k} x{v}" for k, v in sorted(moves.items()))
                               if moves else "none"))

    # Starvation: the gate's whole cost is how many candidates it removes.
    print("\nCANDIDATE STARVATION (valid takes surviving the filter):")
    for cls in ("1", "2s", "2a"):
        rs = by_class.get(cls, [])
        if not rs:
            continue
        va = float(np.median([r["valid_cand_a"] for r in rs]))
        vb = float(np.median([r["valid_cand_b"] for r in rs]))
        fa = sum(1 for r in rs if r["fallback_a"])
        fb = sum(1 for r in rs if r["fallback_b"])
        print(f"  class {cls:<3} median valid candidates {va:6.0f} -> {vb:6.0f}    "
              f"words falling back to an invalid take: {fa} -> {fb}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(sorted(rows, key=lambda r: r["delta"]))
    print(f"\nwritten: {args.out}  ({len(rows)} words, biggest regressions first)")


if __name__ == "__main__":
    main()
