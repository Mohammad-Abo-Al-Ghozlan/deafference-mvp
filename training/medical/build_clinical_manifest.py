#!/usr/bin/env python3
"""Build the clinical download/extraction manifest from semlex_metadata.csv, resolving the
video_ids that carry more than one gloss.

WHY THIS EXISTS
---------------
`semlex_metadata.csv` has 91,148 rows but only 88,174 unique `video_id`. **338 videos carry
two or more DIFFERENT glosses**, and 41 of those touch the 146 clinical labels. The manifest
was previously assembled by hand and read back by `semlex_poses_to_75.read_manifest`, which
does `out[video_id] = (...)` — so for those videos **the label was whichever row came last in
the CSV**. Nondeterministic labels on a medical vocabulary is not an acceptable default.

MEASURED 2026-08-27, and each fact changes the policy
-----------------------------------------------------
1. **`label_type == "signbank"` does not carry a gloss at all.** All 6,192 signbank rows have a
   bare integer in `label` — a SignBank reference id (`heart` vs `3369`, `help` vs `483`).
   asllex 65,154 rows / freetext 19,802 rows are the only real glosses. So the priority order
   quoted in build_vocab.py ("asllex > signbank > freetext") was wrong: it would have labelled
   a video `1117` in preference to `drawn`. signbank is DROPPED, not ranked.
   Dropping it alone resolves 90 of the 338, with no judgement call.

2. **`asllex` is the curated ASL-LEX gloss; `freetext` is a submitter's free typing.** Where the
   two disagree, asllex wins — and that is often the whole point: video NetqYFVxLCOaSt37hO7V is
   `close` (freetext) and `near` (asllex). CLOSE-shut and NEAR are different signs; taking the
   asllex gloss correctly removes it from the clinical set rather than mislabelling it.
   This resolves 96 more.

3. **A tie WITHIN one label_type is a real ambiguity nobody has resolved.** 17 clinical videos
   are tied, and the list is exactly the linguistically dangerous set — `sick`/`very_sick`,
   `sick`/`upset`, `tired`/`not_tired`, `bad`/`badass`, `not`/`slide`, `cold`/`refrigerator`,
   `head`/`kiss`, `show`/`example`, `strong`/`dominant`, `sneeze`/`sneeze_2`. Negations and
   intensifiers are DIFFERENT SIGNS, so guessing here trains SICK on a VERY-SICK take.
   These are QUARANTINED — written to a review CSV, kept out of training. 17 of ~8,036 clips
   is 0.21%, so the cost of being careful is nil.

4. **`hurt` and `pain` collide on one video** (PBiQBaqwWVoYJYuio4u0, both asllex). Both are
   clinical concepts, so no choice of gloss is neutral — it is a coin flip between two of OUR
   classes. Always quarantined, whatever the label_type says.

5. **995 video_ids appear under two splits (train+val), never train+test.** Irrelevant here:
   `npz_to_train_format.py` builds its own signer-disjoint split and ignores Sem-Lex's. The
   count is reported so a future reader does not rediscover it as a bug.

6. **0 video_ids appear under two signer_ids**, so `signer_id` is safe to take from any row.

7. `duration` is in **MILLISECONDS**: median 1,936 / p95 3,764 / max 9,045. Read as seconds it
   would say the median Sem-Lex sign takes 32 minutes. Emitted as `duration_ms` so the unit
   travels with the column.

WHAT IS NOT DECIDED HERE
------------------------
The 17 quarantined videos need a Deaf reviewer, not a heuristic — same policy as
docs/HANDEDNESS_REVIEW_29.csv. The review CSV ships an EMPTY verdict column: Sem-Lex is
CC BY-NC-SA, so its annotations may inform our judgement but must not be copied into a
shipped label file.

USAGE
    python build_clinical_manifest.py --metadata semlex_metadata.csv \
        --concepts vocab_medical_analysis.json --out clinical_manifest.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path

# `label` holds a SignBank reference id, not a gloss (fact 1) — excluded, not ranked.
DROP_LABEL_TYPES = {"signbank"}
# lower is more trustworthy. Ties inside one rank are quarantined, never broken arbitrarily.
LABEL_TYPE_RANK = {"asllex": 0, "freetext": 1}


def load_concepts(path: Path) -> dict:
    """vocab_medical_analysis.json -> {sem-lex label: clinical concept}."""
    blob = json.loads(path.read_text(encoding="utf-8"))
    m = {}
    for tier in ("tier_A_trainable", "tier_B_thin"):
        for concept, rec in blob.get(tier, {}).items():
            for lab in rec["labels"]:
                m[lab.strip().lower()] = concept
    if not m:
        raise SystemExit(f"[err] no concepts found in {path}")
    return m


def read_rows(path: Path) -> tuple:
    txt = path.read_bytes().decode("utf-8-sig", errors="replace")
    rd = csv.reader(io.StringIO(txt))
    head = next(rd)
    need = ("video_id", "label", "label_type", "signer_id", "split", "duration")
    miss = [c for c in need if c not in head]
    if miss:
        raise SystemExit(f"[err] {path.name} is missing columns {miss}; got {head}")
    idx = {c: head.index(c) for c in need}
    return [r for r in rd if len(r) > max(idx.values())], idx


def resolve(rows: list, idx: dict, lab2con: dict) -> tuple:
    """-> (kept {vid: rec}, quarantined [rec], stats dict). One pass, every decision recorded."""
    by_vid, dropped_type = defaultdict(list), 0
    for r in rows:
        lt = r[idx["label_type"]].strip().lower()
        if lt in DROP_LABEL_TYPES:
            dropped_type += 1
            continue
        by_vid[r[idx["video_id"]].strip()].append({
            "label": r[idx["label"]].strip().lower(), "label_type": lt,
            "signer_id": r[idx["signer_id"]].strip(), "split": r[idx["split"]].strip(),
            "duration_ms": r[idx["duration"]].strip(),
            "rank": LABEL_TYPE_RANK.get(lt, 9),
        })

    kept, quar = {}, []
    st = {"rows_dropped_signbank": dropped_type, "videos": len(by_vid), "single_gloss": 0,
          "resolved_by_rank": 0, "quarantined": 0, "quarantined_clinical": 0,
          "multi_split": 0, "multi_signer": 0, "not_clinical": 0}

    for vid, recs in by_vid.items():
        if len({r["signer_id"] for r in recs}) > 1:
            st["multi_signer"] += 1                     # measured as 0; assert-by-counter
        if len({r["split"] for r in recs}) > 1:
            st["multi_split"] += 1
        glosses = {r["label"] for r in recs}

        if len(glosses) == 1:
            st["single_gloss"] += 1
            win, why = recs[0]["label"], "sole gloss"
        else:
            best = min(r["rank"] for r in recs)
            top = {r["label"] for r in recs if r["rank"] == best}
            if len(top) == 1:
                st["resolved_by_rank"] += 1
                win = next(iter(top))
                why = f"{[r['label_type'] for r in recs if r['rank'] == best][0]} beats " \
                      f"{sorted({r['label_type'] for r in recs if r['rank'] != best})}"
            else:
                # TIE inside one label_type. Never broken here (facts 3 and 4).
                st["quarantined"] += 1
                mine = sorted(g for g in top if g in lab2con)
                if mine:
                    st["quarantined_clinical"] += 1
                    quar.append({
                        "video_id": vid, "tied_glosses": ";".join(sorted(top)),
                        "clinical_concepts": ";".join(sorted({lab2con[g] for g in mine})),
                        "label_type": sorted({r["label_type"] for r in recs
                                              if r["rank"] == best})[0],
                        "signer_id": recs[0]["signer_id"],
                        "duration_ms": recs[0]["duration_ms"],
                        "reason": ("two CLINICAL concepts on one video — no neutral choice"
                                   if len({lab2con[g] for g in mine}) > 1 else
                                   "tied gloss may be a DIFFERENT sign (negation / intensifier "
                                   "/ compound / homonym)"),
                        "verdict_keep_as": "",          # left EMPTY for the Deaf reviewer
                        "reviewer": "", "notes": "",
                    })
                continue

        if win not in lab2con:
            st["not_clinical"] += 1
            continue
        kept[vid] = {"video_id": vid, "label": win, "concept": lab2con[win],
                     "signer_id": recs[0]["signer_id"], "split": recs[0]["split"],
                     "duration_ms": recs[0]["duration_ms"],
                     "label_type": [r["label_type"] for r in recs if r["label"] == win][0],
                     "resolution": why}
    return kept, quar, st


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--metadata", default="semlex_metadata.csv")
    ap.add_argument("--concepts", default="vocab_medical_analysis.json")
    ap.add_argument("--out", default="clinical_manifest.csv")
    ap.add_argument("--quarantine", default="docs/CLINICAL_GLOSS_REVIEW.csv")
    args = ap.parse_args()

    lab2con = load_concepts(Path(args.concepts))
    rows, idx = read_rows(Path(args.metadata))
    print(f"[src] {len(rows):,} rows | {len(lab2con)} clinical labels -> "
          f"{len(set(lab2con.values()))} concepts")

    kept, quar, st = resolve(rows, idx, lab2con)

    print(f"\n[policy] dropped {st['rows_dropped_signbank']:,} signbank rows "
          f"(`label` is a reference id, not a gloss)")
    print(f"[policy] {st['videos']:,} videos with a real gloss: "
          f"{st['single_gloss']:,} unambiguous, {st['resolved_by_rank']} resolved by "
          f"asllex>freetext, {st['quarantined']} tied")
    print(f"[policy] QUARANTINED {st['quarantined_clinical']} clinical videos "
          f"({st['quarantined_clinical'] / max(len(kept), 1):.2%} of the clinical set) — "
          f"a tie inside one label_type is a real ambiguity, not a coin flip")
    if st["multi_signer"]:
        raise SystemExit(f"[err] {st['multi_signer']} videos have two signer_ids — signer_id "
                         f"was measured unique on 2026-08-27; the release has changed")
    print(f"[note] {st['multi_split']:,} videos appear under two of Sem-Lex's splits "
          f"(train+val). Irrelevant: npz_to_train_format.py builds its own signer-disjoint "
          f"split. Reported so it is not rediscovered as a bug.")

    cols = ["video_id", "label", "concept", "signer_id", "split", "duration_ms",
            "label_type", "resolution", "npy"]
    out = Path(args.out)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for vid, rec in sorted(kept.items(), key=lambda kv: (kv[1]["concept"], kv[0])):
            w.writerow({**rec, "npy": f"{vid}.npy"})
    print(f"\n[ok] wrote {out}: {len(kept):,} clips, "
          f"{len({r['concept'] for r in kept.values()})} concepts, "
          f"{len({r['signer_id'] for r in kept.values()})} signers")

    if quar:
        q = Path(args.quarantine)
        q.parent.mkdir(parents=True, exist_ok=True)

        # NEVER clobber review work. This file is filled in by hand, one row at a time, by
        # someone whose time is the scarcest input to the project — and the manifest gets
        # regenerated on every vocabulary change. An unconditional write would silently
        # delete hours of it (it deleted three resolved rows on 2026-08-29 before this
        # existed). So: carry forward every human column for any row already present, and
        # keep rows that are NOT auto-generated at all (MERGE-* decisions live here too).
        HUMAN = ("verdict_keep_as", "reviewer", "notes")
        prior, extra = {}, []
        if q.exists():
            with q.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    prior[row["video_id"]] = row
            auto = {r["video_id"] for r in quar}
            extra = [r for vid, r in prior.items() if vid not in auto]

        carried = 0
        for r in quar:
            old = prior.get(r["video_id"])
            if not old:
                continue
            for col in HUMAN:
                if old.get(col, "").strip():
                    r[col] = old[col]
                    carried += 1

        cols = list(quar[0])
        rows = sorted(quar, key=lambda r: r["clinical_concepts"]) + \
            [{c: e.get(c, "") for c in cols} for e in extra]
        with q.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        note = (f", carried {carried} human field(s) forward" if carried else "")
        note += (f", kept {len(extra)} non-auto row(s)" if extra else "")
        print(f"[ok] wrote {q}: {len(quar)} videos for Deaf review{note} "
              f"(verdict_keep_as deliberately EMPTY — Sem-Lex is CC BY-NC-SA, its annotations "
              f"inform the judgement but must not be copied into a shipped label file)")
        for r in sorted(quar, key=lambda r: r["clinical_concepts"]):
            print(f"     {r['video_id']:22} {r['tied_glosses']:32} -> {r['clinical_concepts']}")

    per = defaultdict(set)
    for rec in kept.values():
        per[rec["concept"]].add(rec["signer_id"])
    cnt = defaultdict(int)
    for rec in kept.values():
        cnt[rec["concept"]] += 1
    thin = sorted((n, c) for c, n in cnt.items() if n < 8)
    vals = sorted(cnt.values())
    print(f"\n[stats] clips/concept: min={vals[0]} median={vals[len(vals) // 2]} "
          f"max={vals[-1]} mean={sum(vals) / len(vals):.0f}")
    if thin:
        print(f"[warn] {len(thin)} concepts under 8 clips BEFORE extraction: "
              + ", ".join(f"{c}({n})" for n, c in thin))


if __name__ == "__main__":
    main()
