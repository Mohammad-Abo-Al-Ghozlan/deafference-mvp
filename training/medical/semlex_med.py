import csv, io, json
from collections import defaultdict

txt = open('semlex.csv', 'rb').read().decode('utf-8-sig', errors='replace')
rows = list(csv.reader(io.StringIO(txt)))
h = rows[0]
iL, iS, iT = h.index('label'), h.index('signer_id'), h.index('label_type')

vids = defaultdict(int); signers = defaultdict(set); ltype = defaultdict(set)
for r in rows[1:]:
    if len(r) <= max(iL, iS, iT): continue
    g = r[iL].strip().lower()
    if not g: continue
    vids[g] += 1; signers[g].add(r[iS].strip()); ltype[g].add(r[iT].strip())

print(f"Sem-Lex: {len(rows)-1} videos, {len(vids)} unique glosses, "
      f"{len({r[iS] for r in rows[1:] if len(r)>iS})} signers\n")

MED = {
 "body part": ["head","face","eye","ear","nose","mouth","tooth","teeth","tongue","throat","neck",
               "shoulder","arm","elbow","hand","finger","chest","heart","lung","lungs","back","stomach",
               "belly","hip","leg","knee","foot","feet","skin","bone","blood","brain","muscle"],
 "symptom":   ["pain","hurt","sick","ache","headache","fever","hot","cold","cough","sneeze",
               "vomit","nausea","dizzy","tired","weak","swell","bleed","itch","rash","burn",
               "breathe","choke","faint","numb","cramp","diarrhea","infection","allergy"],
 "severity":  ["bad","worse","better","big","very","much","strong","light","sharp"],
 "time":      ["when","today","yesterday","tomorrow","now","morning","afternoon","night","day",
               "week","month","year","hour","minute","long","always","sometimes","never","start"],
 "people":    ["doctor","nurse","patient","hospital","clinic","dentist","mother","father","family",
               "baby","child","man","woman","interpreter"],
 "action":    ["help","need","want","take","give","eat","drink","sleep","sit","stand","walk","move",
               "stop","wait","come","go","look","show","tell","understand","ask","feel","touch",
               "open","close"],
 "object":    ["medicine","pill","shot","needle","water","food","bathroom","bed","wheelchair",
               "glasses","test","surgery","bandage"],
 "core":      ["yes","no","not","please","thank","sorry","again","more","finish","all","some",
               "maybe","where","what","why","how","who","which","can"],
}

MIN_VID, MIN_SIGNER = 8, 3        # a class needs enough examples AND signer variety to generalize

rowsout = []
tiers = {"TRAINABLE": [], "THIN": [], "ABSENT": []}
for cat, ws in MED.items():
    for w in ws:
        n, s = vids.get(w, 0), len(signers.get(w, ()))
        tier = "ABSENT" if n == 0 else ("TRAINABLE" if n >= MIN_VID and s >= MIN_SIGNER else "THIN")
        tiers[tier].append((cat, w, n, s))

print(f"Gate: >={MIN_VID} videos AND >={MIN_SIGNER} signers = TRAINABLE\n")
for t in ("TRAINABLE", "THIN", "ABSENT"):
    g = tiers[t]
    print(f"### {t}  ({len(g)} words)")
    if t == "ABSENT":
        print("   " + ", ".join(w for _, w, _, _ in g) + "\n")
    else:
        for cat, w, n, s in sorted(g, key=lambda x: -x[2]):
            print(f"   {w:12} {n:4} videos  {s:2} signers   [{cat}]")
        print()

tot = sum(len(v) for v in tiers.values())
print(f"SUMMARY of {tot} clinical words in Sem-Lex:")
for t in ("TRAINABLE","THIN","ABSENT"):
    print(f"  {t:10} {len(tiers[t]):3}  ({len(tiers[t])/tot*100:.0f}%)")
tr = [w for _,w,_,_ in tiers['TRAINABLE']]
print(f"\ntotal videos available for the {len(tr)} trainable words: "
      f"{sum(vids[w] for w in tr):,}")
json.dump({t:[w for _,w,_,_ in v] for t,v in tiers.items()}, open('semlex_med_tiers.json','w'), indent=1)
