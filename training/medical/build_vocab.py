"""Build the validated medical vocabulary from Sem-Lex, with real video/signer counts.
Only TRUE morphological variants are remapped (eyes->eye); look-alike compounds
(football, numbers, toothbrush, necklace, hippo) are NOT merged - they are different signs."""
import csv, io, json
from collections import defaultdict

txt = open('semlex.csv', 'rb').read().decode('utf-8-sig', errors='replace')
rows = list(csv.reader(io.StringIO(txt)))
h = rows[0]; iL, iS = h.index('label'), h.index('signer_id')
vids = defaultdict(int); signers = defaultdict(set)
for r in rows[1:]:
    if len(r) > max(iL, iS) and r[iL].strip():
        g = r[iL].strip().lower(); vids[g] += 1; signers[g].add(r[iS].strip())

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

json.dump(out, open('vocab_medical_analysis.json','w'), indent=1)
json.dump({"words": sorted(A), "source": "Sem-Lex", "gate": f">={MIN_V} videos & >={MIN_S} signers"},
          open('vocab_medical.json','w'), indent=1)
print("\nwrote vocab_medical.json + vocab_medical_analysis.json")
