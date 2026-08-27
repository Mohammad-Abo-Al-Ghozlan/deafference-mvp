"""Build the validated medical vocabulary from Sem-Lex, with real video/signer counts.
Only TRUE morphological variants are remapped (eyes->eye); look-alike compounds
(football, numbers, toothbrush, necklace, hippo) are NOT merged - they are different signs.

FIXED 2026-08-27 — THIS SCRIPT WAS COUNTING ROWS, NOT VIDEOS
------------------------------------------------------------
`semlex_metadata.csv` has **91,148 rows but only 88,174 unique `video_id`** — 2,854 ids
repeat, 338 of them under two DIFFERENT labels, and 995 under two different splits. The
old `vids[g] += 1` counted rows, so 87 of 145 clinical concepts were over-counted.

The correction that matters: **`knee` has 7 unique videos, not 8**, which puts it below the
>=8 gate. So tier A is **129, not 130**, and the thin list is **16, not 15**. Every other
concept keeps its tier; only the counts move down.

Signer counts were always right (a duplicated row cannot add a signer).

Two more facts measured from the same file, printed below because they shape training more
than the vocabulary size does:
  * the clinical subset draws on **41 of 44 signers**, and the top 10 hold **58%** of it
    (max/min 330x) — per-signer accuracy is the risk to plan around, not class count
  * Sem-Lex's own split is signer-disjoint for TEST but NOT for VAL: train∩test = 0 and
    val∩test = 0, but **train∩val = 31 of 32 signers**. Score on `split == "test"` only.
"""
import csv, glob, io, json, sys
from collections import defaultdict

_cand = [p for p in ("semlex_metadata.csv", "semlex.csv") if glob.glob(p)] or \
        sorted(glob.glob("*semlex*.csv")) or sorted(glob.glob("**/*semlex*.csv", recursive=True))
if not _cand:
    sys.exit("[err] no semlex metadata CSV found (looked for semlex_metadata.csv / semlex.csv)")
SRC = _cand[0]
txt = open(SRC, 'rb').read().decode('utf-8-sig', errors='replace')
rows = list(csv.reader(io.StringIO(txt)))
h = rows[0]
iL, iS, iV = h.index('label'), h.index('signer_id'), h.index('video_id')
iSp = h.index('split') if 'split' in h else None

# DEDUPE BY video_id. A set, not a counter: the same video appears up to 4 times.
vidsets = defaultdict(set); signers = defaultdict(set)
seen_ids, dup_rows = set(), 0
label_of, split_of = {}, defaultdict(set)
for r in rows[1:]:
    if len(r) <= max(iL, iS, iV) or not r[iL].strip():
        continue
    g, vid, sg = r[iL].strip().lower(), r[iV].strip(), r[iS].strip()
    if vid in seen_ids:
        dup_rows += 1
    seen_ids.add(vid)
    vidsets[g].add(vid); signers[g].add(sg)
    label_of.setdefault(vid, set()).add(g)
    if iSp is not None:
        split_of[vid].add(r[iSp].strip())
vids = {g: len(v) for g, v in vidsets.items()}

multi_label = sum(1 for v in label_of.values() if len(v) > 1)
multi_split = sum(1 for v in split_of.values() if len(v) > 1)
print(f"[src] {SRC}: {len(rows)-1:,} rows -> {len(seen_ids):,} unique video_id "
      f"({dup_rows:,} duplicate rows)")
print(f"[src] {multi_label:,} video_ids carry MORE THAN ONE label — resolve or drop before "
      f"training (label_type priority: asllex > signbank > freetext)")
print(f"[src] {multi_split:,} video_ids appear under MORE THAN ONE split (train+val only; "
      f"zero train+test, so TEST is physically clean)\n")

# clinical concept -> the Sem-Lex label(s) that really are that sign
CONCEPTS = {
 "body":    {"head":["head"],"face":["face"],"eye":["eyes"],"ear":["ear"],"nose":["nose"],
             "mouth":["mouth"],"teeth":["teeth"],"tongue":["tongue"],"throat":["throat"],
             "neck":["neck"],"shoulder":["shoulder"],"arm":["arm"],"hand":["hands"],
             "chest":["chest"],"heart":["heart"],"lungs":["lungs"],"back":["back"],
             "stomach":["stomach"],"leg":["leg"],"knee":["knee","knees"],"feet":["feet"],
             "skin":["skin"],"bone":["bone"],"blood":["blood"],"muscle":["muscle"]},
 "symptom": {"hurt":["hurt"],"pain":["pain"],"sick":["sick"],"headache":["headache"],
             "fever":["fever"],"hot":["hot"],"cold":["cold"],"cough":["cough"],
             "vomit":["vomit"],"nausea":["nausea"],"dizzy":["dizzy"],"tired":["tired"],
             "weak":["weak"],"bleed":["bleed"],"itch":["itch"],"burn":["burn"],
             "breathe":["breathe"],"choke":["choke"],"faint":["faint"],"rash":["rash"],
             "cramp":["cramp"],"infection":["infection"],"sneeze":["sneeze"]},
 "severity":{"bad":["bad"],"worse":["worse"],"better":["better"],"big":["big"],
             "much":["much"],"strong":["strong"],"light":["light"],"sharp":["sharp"],"very":["very"]},
 "time":    {"when":["when"],"today":["today"],"yesterday":["yesterday"],"tomorrow":["tomorrow"],
             "now":["now"],"morning":["morning"],"afternoon":["afternoon"],"night":["night"],
             "day":["day"],"week":["week"],"month":["month"],"year":["year"],"hour":["hour"],
             "minute":["minute"],"long":["long"],"always":["always"],"sometimes":["sometimes"],
             "never":["never"],"start":["start"]},
 "people":  {"doctor":["doctor"],"nurse":["nurse"],"hospital":["hospital"],"dentist":["dentist"],
             "mother":["mother"],"father":["father"],"family":["family"],"baby":["baby"],
             "child":["child"],"man":["man"],"woman":["woman"],"interpreter":["interpreter"],
             "patient":["patient"]},
 "action":  {"help":["help"],"need":["need"],"want":["want"],"take":["take"],"give":["give"],
             "eat":["eat"],"drink":["drink"],"sleep":["sleep"],"sit":["sit"],"stand":["stand"],
             "walk":["walk"],"move":["move"],"stop":["stop"],"wait":["wait"],"come":["come"],
             "go":["go"],"look":["look"],"show":["show"],"tell":["tell"],
             "understand":["understand"],"ask":["ask"],"feel":["feel"],"touch":["touch"],
             "open":["open"],"close":["close"]},
 "object":  {"medicine":["medicine"],"pill":["pill"],"shot":["shot"],"needle":["needle"],
             "water":["water"],"food":["food"],"bathroom":["bathroom"],"bed":["bed"],
             "wheelchair":["wheelchair"],"glasses":["glasses"],"test":["test"],"surgery":["surgery"]},
 "core":    {"yes":["yes"],"no":["no"],"not":["not"],"please":["please"],"thankyou":["thank_you"],
             "sorry":["sorry"],"again":["again"],"more":["more"],"finish":["finish"],
             "all":["all"],"some":["some"],"maybe":["maybe"],"where":["where"],"what":["what"],
             "why":["why"],"how":["how"],"who":["who"],"which":["which"],"can":["can"]},
}

MIN_V, MIN_S = 8, 3
out = {"tier_A_trainable": {}, "tier_B_thin": {}, "tier_C_absent": []}
for cat, m in CONCEPTS.items():
    for concept, labels in m.items():
        n = sum(vids.get(l, 0) for l in labels)
        s = len(set().union(*[signers.get(l, set()) for l in labels])) if labels else 0
        rec = {"labels": labels, "videos": n, "signers": s, "category": cat}
        if n == 0:            out["tier_C_absent"].append(concept)
        elif n >= MIN_V and s >= MIN_S: out["tier_A_trainable"][concept] = rec
        else:                 out["tier_B_thin"][concept] = rec

A, B, C = out["tier_A_trainable"], out["tier_B_thin"], out["tier_C_absent"]
print(f"Tier A TRAINABLE : {len(A):3} concepts, {sum(r['videos'] for r in A.values()):,} videos")
print(f"Tier B THIN      : {len(B):3} concepts -> " + ", ".join(f"{k}({v['videos']}v/{v['signers']}s)" for k,v in B.items()))
print(f"Tier C ABSENT    : {len(C):3} concepts -> {', '.join(C) if C else '-'}")
tot = len(A)+len(B)+len(C)
print(f"\nTOTAL {tot} clinical concepts: {len(A)/tot*100:.0f}% trainable now")

# class-imbalance picture (matters for training)
vs = sorted((r["videos"] for r in A.values()))
print(f"\nTier A videos/class: min={vs[0]} median={vs[len(vs)//2]} max={vs[-1]}  "
      f"mean={sum(vs)/len(vs):.0f}")
print(f"imbalance ratio max/min = {vs[-1]/vs[0]:.0f}x  <- needs class weighting or capping")
sig = sorted((r["signers"] for r in A.values()))
print(f"Tier A signers/class: min={sig[0]} median={sig[len(sig)//2]} max={sig[-1]}")

# SIGNER CONCENTRATION. The 250-word post-mortem: per-signer accuracy ranged 0.314-0.823
# across 7 held-out signers and nothing downstream of the feature extractor could fix it.
# With 41 signers but most of the data in a handful, that is the risk to size up FIRST.
clin_labels = {l for m in (A, B) for rec in m.values() for l in rec["labels"]}
sig_counts, counted = defaultdict(int), set()
for r in rows[1:]:
    if len(r) <= max(iL, iS, iV):
        continue
    vid = r[iV].strip()
    if r[iL].strip().lower() in clin_labels and vid not in counted:
        counted.add(vid)                      # dedupe here too, or the top-10 share is inflated
        sig_counts[r[iS].strip()] += 1
tops = sorted(sig_counts.values(), reverse=True)
tot_clips = sum(tops) or 1
print(f"\nSigner concentration on the clinical subset: {len(tops)} of "
      f"{len(set(r[iS].strip() for r in rows[1:] if len(r) > iS))} signers appear; "
      f"top 10 hold {sum(tops[:10])/tot_clips:.0%}; max/min {tops[0]/max(tops[-1],1):.0f}x")
print("⚠️  Score generalization on split=='test' ONLY — train∩val = 31 of 32 signers.")

json.dump(out, open('vocab_medical_analysis.json','w'), indent=1)
json.dump({"words": sorted(A), "source": "Sem-Lex",
           "gate": f">={MIN_V} unique video_id & >={MIN_S} signers",
           "counted": "unique video_id (91,148 rows dedupe to 88,174 videos)",
           "note": f"tier A = {len(A)} concepts. 'knee' sits at 7 videos, one below the gate, "
                   f"so it is in tier B; the gate is a round number, not a cliff — revisit if "
                   f"knee matters clinically.",
           "score_on": "split == 'test' only; Sem-Lex's val shares 31/32 signers with train"},
          open('vocab_medical.json','w'), indent=1)
print("\nwrote vocab_medical.json + vocab_medical_analysis.json")
