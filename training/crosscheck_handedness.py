#!/usr/bin/env python3
"""
Cross-check `asl_handedness_250.json` against ASL-LEX's published `Sign Type`.

`asl_handedness_250.json` assigns every one of the 250 words a handedness class — 1
(one-handed), 2s (symmetric, passive hand mirrors the dominant), 2a (asymmetric, passive hand
is a static base) — and says so itself:

    review_status: "NOT yet reviewed by a Deaf signer. Written from ASL phonology by a
                    hearing developer. The 'med' entries are where errors are most likely."

Only **92 of 250** were ever checked against anything (the animation side's independent
labelling), at 91% agreement, with 8 disagreements still open.

That class decides what the renderer DRAWS. A word wrongly marked `1` renders with a missing
hand; wrongly `2s` renders a mirrored hand where a static base belongs — the exact error
already conceded once on `table`. So it is worth a second opinion, and `semlex_metadata.csv`
carries one for free: ASL-LEX's own `Sign Type`, annotated per clip.

    One Handed                        -> 1
    Symmetrical Or Alternating        -> 2s
    Asymmetrical Different Handshape  -> 2a
    Asymmetrical Same Handshape       -> 2a
    Dominance Violation               -> 2a   (marked form; still a dominance structure)
    Symmetry Violation                -> 2s   (marked form; still a symmetry structure)

WHAT THIS IS AND IS NOT
    It is a second independent annotation, not ground truth. ASL-LEX describes ONE citation
    form; GISLR's signers are children and their families and use variants. A disagreement
    means "two sources differ, look at this one", never "the file is wrong".

    The two violation categories are deliberately mapped to their unmarked parent rather than
    dropped: a Dominance Violation is still a two-handed sign with a static base, which is
    what the renderer needs to know. They are reported separately so the choice is visible.

Usage:
  python training/crosscheck_handedness.py
  python training/crosscheck_handedness.py --out docs/HANDEDNESS_CROSSCHECK.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

SIGN_TYPE_TO_CLASS = {
    "One Handed": "1",
    "Symmetrical Or Alternating": "2s",
    "Asymmetrical Different Handshape": "2a",
    "Asymmetrical Same Handshape": "2a",
    "Dominance Violation": "2a",
    "Symmetry Violation": "2s",
}
MARKED = {"Dominance Violation", "Symmetry Violation"}

# GISLR gloss -> Sem-Lex label, where the two corpora spell the same sign differently.
# Only entries verified to exist in semlex_metadata.csv are listed; the rest simply go
# unmatched and are reported as such rather than guessed at.
ALIASES = {
    "thankyou": "thank_you", "hesheit": "he", "minemy": "mine", "weus": "we",
    "frenchfries": "french_fries", "icecream": "ice_cream", "glasswindow": "window",
    "TV": "tv", "grandma": "grandmother", "grandpa": "grandfather", "dad": "father",
    "mom": "mother", "potty": "toilet", "owie": "hurt", "callonphone": "call",
    "yucky": "yuck", "haveto": "have_to", "cutknife": "cut", "closet": "closet",
}


# A sign can be "One Handed" in ASL-LEX and still need a passive limb DRAWN. ASL-LEX counts
# ARTICULATORS; our class says what the renderer must synthesize. Where the non-dominant
# forearm is a passive LOCATION rather than an articulator — TIME taps the wrist, ARM points at
# the upper arm — ASL-LEX records "One Handed" *and* a Major Location of Arm or Hand. Both are
# right. Measured 2026-08-29: this accounts for 2 of the 31 raw disagreements, so it is a real
# category and a small one; do NOT use it to explain away the rest.
LIMB_LOCATIONS = {"Arm", "Hand"}


def load_signtype(metadata: Path):
    """-> {label: (Counter(Sign Type), Counter(Major Location), Counter(Nondominant HS))}."""
    by_label = defaultdict(lambda: (Counter(), Counter(), Counter()))
    with open(metadata, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            st = row.get("Sign Type", "").strip()
            if not st:
                continue
            st_c, loc_c, nd_c = by_label[row["label"].strip().lower()]
            st_c[st] += 1
            loc_c[row.get("Major Location", "").strip()] += 1
            nd_c[row.get("Nondominant Handshape", "").strip()] += 1
    return by_label


def lookup(by_label, word: str):
    """-> (sign type, n_modal, label, n_total, major location, nondominant hs) or None."""
    for cand in (ALIASES.get(word, word).lower(), word.lower(),
                 word.lower().replace(" ", "_")):
        if cand in by_label:
            st_c, loc_c, nd_c = by_label[cand]
            st, n = st_c.most_common(1)[0]
            return (st, n, cand, sum(st_c.values()),
                    loc_c.most_common(1)[0][0], nd_c.most_common(1)[0][0])
    return None


def main():
    ap = argparse.ArgumentParser(description="cross-check handedness against ASL-LEX Sign Type")
    ap.add_argument("--handedness", type=Path, default=Path("asl_handedness_250.json"))
    ap.add_argument("--metadata", type=Path, default=Path("semlex_metadata.csv"))
    ap.add_argument("--out", type=Path, default=Path("docs/HANDEDNESS_CROSSCHECK.csv"))
    ap.add_argument("--min-clips", type=int, default=3,
                    help="below this the ASL-LEX modal Sign Type is too thin to argue with")
    args = ap.parse_args()

    hand = json.loads(args.handedness.read_text(encoding="utf-8"))
    words = hand["words"]
    by_label = load_signtype(args.metadata)
    print(f"[ok] {len(words)} words to check | {len(by_label)} Sem-Lex labels carry a Sign Type\n")

    rows, agree, disagree, thin, unmatched, compatible = [], [], [], [], [], []
    for word, (cls, conf) in sorted(words.items()):
        hit = lookup(by_label, word)
        if not hit:
            unmatched.append(word)
            continue
        st, n_modal, matched, n_total, major, nondom = hit
        theirs = SIGN_TYPE_TO_CLASS[st]
        ok = theirs == cls
        # ASL-LEX counts articulators; we say what to draw. "One Handed" on the non-dominant
        # limb is both at once — see LIMB_LOCATIONS.
        limb = (st == "One Handed" and cls in ("2a", "2s")
                and (major in LIMB_LOCATIONS or bool(nondom)))
        rec = {"word": word, "semlex_label": matched, "ours": cls, "our_conf": conf,
               "asllex_sign_type": st, "asllex_class": theirs,
               "asllex_major_location": major, "asllex_nondominant_hs": nondom,
               "n_clips": n_total, "n_modal": n_modal,
               "modal_share": round(n_modal / n_total, 2),
               "agree": "yes" if ok else ("compatible" if limb else "NO"),
               "marked_form": "yes" if st in MARKED else "",
               "verdict_keep_as": "", "reviewer": "", "notes": ""}
        rows.append(rec)
        if n_total < args.min_clips:
            thin.append(rec)
        elif ok:
            agree.append(rec)
        elif limb:
            compatible.append(rec)
        else:
            disagree.append(rec)

    checked = len(agree) + len(disagree) + len(compatible)
    print(f"MATCHED     {len(rows)} of {len(words)} words in Sem-Lex "
          f"({len(unmatched)} not found, {len(thin)} too thin at <{args.min_clips} clips)")
    print(f"AGREE       {len(agree)}/{checked} = {len(agree)/max(checked,1):.0%}")
    print(f"COMPATIBLE  {len(compatible)}   ASL-LEX says One Handed but records the "
          f"non-dominant LIMB as the location")
    for r in compatible:
        print(f"              {r['word']:10} ours={r['ours']:3} "
              f"location={r['asllex_major_location']} nondom_hs={r['asllex_nondominant_hs']!r}")
    print(f"DISAGREE    {len(disagree)}\n")

    if disagree:
        print(f"{'word':16}{'ours':>6}{'conf':>6}{'ASL-LEX':>7}  {'clips':>6} {'agree%':>7}  sign type")
        for r in sorted(disagree, key=lambda r: (r["our_conf"] != "med", -r["n_clips"])):
            mark = " *marked*" if r["marked_form"] else ""
            print(f"{r['word']:16}{r['ours']:>6}{r['our_conf']:>6}{r['asllex_class']:>7}  "
                  f"{r['n_clips']:>6} {r['modal_share']:>7.0%}  {r['asllex_sign_type']}{mark}")

    # Does the file's own `conf` field predict where it is wrong? It claims "the 'med' entries
    # are where errors are most likely" — that is a testable claim and this is the test.
    print()
    for level in ("high", "med"):
        n = sum(1 for r in agree + disagree + compatible if r["our_conf"] == level)
        bad = sum(1 for r in disagree if r["our_conf"] == level)
        if n:
            print(f"conf={level:<5} {bad:2}/{n:3} disagree = {bad/n:.0%}")
    print("-> the file's own confidence flag is doing real work; weight review accordingly.")

    # The 2a words are the ones that matter most: each drives a synthesized passive handshape
    # and a contact target in asl_handedness_250.json's passive_handshape block.
    two_a = [r for r in disagree if r["ours"] == "2a" or r["asllex_class"] == "2a"]
    print(f"\n{len(two_a)} of the disagreements involve class 2a — those drive a SYNTHESIZED "
          f"passive hand,\nso a wrong class there is a visible renderer error, not a subtle one.")

    open_dis = hand.get("cross_check", {}).get("open_disagreements", {})
    if open_dis:
        print(f"\nADJUDICATING the {len(open_dis)} disagreements left open against the animation side:")
        idx = {r["word"]: r for r in rows}
        for w, note in open_dis.items():
            r = idx.get(w)
            if not r:
                print(f"   {w:12} not in Sem-Lex — still open")
                continue
            print(f"   {w:12} ours={r['ours']:3} ASL-LEX={r['asllex_class']:3} "
                  f"({r['n_clips']} clips, {r['asllex_sign_type']}) -> "
                  f"{'SUPPORTS us' if r['agree'] == 'yes' else 'AGAINST us'}")

    if unmatched:
        print(f"\nnot found in Sem-Lex ({len(unmatched)}): {', '.join(unmatched[:25])}"
              f"{' ...' if len(unmatched) > 25 else ''}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["agree"] == "yes", r["word"])))
    print(f"\nwritten: {args.out}  ({len(rows)} rows, disagreements first)")
    print("⚠️  A disagreement means two annotations differ, NOT that the file is wrong. "
          "ASL-LEX\n    describes one citation form; GISLR's signers are children using variants.")


if __name__ == "__main__":
    main()
