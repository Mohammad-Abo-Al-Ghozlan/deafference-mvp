#!/usr/bin/env python3
"""Calibrate the handedness classifier against signs whose structure is linguistically fixed.

Salim asked me to eyeball 30 clips. Eyeballing 30 gives 30 labels and no error bars, so
instead: label a set of signs by their KNOWN citation form, then measure how well the
geometric classifiers recover it. That does three things at once —

  1. calibrates the detector,
  2. bounds how wrong the 195/55 split is,
  3. and, where geometry contradicts a sign whose form is not in doubt, flags the CLIP as a
     wrong or mistracked take — which is the `hello` failure, found systematically.

IMPORTANT CAVEAT, stated up front: these labels are my reading of ASL citation forms, not a
Deaf reviewer's. Regional and register variation is real (several of these have two-handed
variants), and this dataset is children's vocabulary where caretaker signing varies more than
citation form. Treat the labels as a calibration prior, not ground truth. Every disagreement
below should be resolved by a Deaf reviewer, not by me.

Structure classes:
  ONE  — one-handed; the other hand plays no part
  SYM  — two-handed, both hands move, SAME handshape (Battison's Symmetry Condition)
  ASYM — two-handed, passive hand static and used as a place of articulation
         (Battison's Dominance Condition)
"""
import csv, json, math, os, sys
import statistics as st

# ---------------------------------------------------------------------------------------
# Labels. Confidence: 3 = citation form not in serious doubt, 2 = confident, 1 = variant known
# ---------------------------------------------------------------------------------------
GT = {
    # --- one-handed: body-part points and face-anchored signs -------------------------
    'bird':('ONE',3), 'duck':('ONE',3), 'hen':('ONE',2), 'goose':('ONE',2),
    'cat':('ONE',3), 'kitty':('ONE',3), 'cow':('ONE',3), 'horse':('ONE',3),
    'donkey':('ONE',2), 'pig':('ONE',3), 'elephant':('ONE',3), 'lion':('ONE',2),
    'mouse':('ONE',3), 'bug':('ONE',3), 'bee':('ONE',2), 'frog':('ONE',2),
    'dad':('ONE',3), 'mom':('ONE',3), 'grandpa':('ONE',2), 'grandma':('ONE',2),
    'boy':('ONE',3), 'girl':('ONE',3), 'man':('ONE',2), 'uncle':('ONE',2),
    'aunt':('ONE',2), 'hat':('ONE',3), 'hair':('ONE',3), 'ear':('ONE',3),
    'eye':('ONE',3), 'nose':('ONE',3), 'mouth':('ONE',3), 'chin':('ONE',3),
    'cheek':('ONE',3), 'tongue':('ONE',3), 'head':('ONE',3), 'lips':('ONE',3),
    'drink':('ONE',3), 'milk':('ONE',3), 'yes':('ONE',3), 'no':('ONE',3),
    'please':('ONE',3), 'thankyou':('ONE',3), 'hello':('ONE',3), 'sad':('ONE',2),
    'red':('ONE',3), 'white':('ONE',2), 'water':('ONE',3), 'thirsty':('ONE',3),
    'hungry':('ONE',2), 'sleepy':('ONE',2), 'sick':('ONE',2), 'flower':('ONE',3),
    'apple':('ONE',3), 'orange':('ONE',3), 'farm':('ONE',2), 'boy':('ONE',3),
    'wolf':('ONE',2), 'owie':('ONE',1), 'yucky':('ONE',1), 'smile':('ONE',3),
    'tooth':('ONE',3), 'toothbrush':('ONE',3), 'talk':('ONE',2), 'say':('ONE',2),

    # --- symmetric two-handed: both hands move, same handshape ------------------------
    'alligator':('SYM',3), 'owl':('SYM',2), 'tiger':('SYM',2), 'butterfly':('SYM',3),
    'book':('SYM',3), 'boat':('SYM',3), 'balloon':('SYM',2), 'cloud':('SYM',2),
    'rain':('SYM',3), 'snow':('SYM',2), 'shoe':('SYM',3), 'jacket':('SYM',2),
    'pajamas':('SYM',2), 'jeans':('SYM',1), 'stairs':('SYM',2), 'store':('SYM',2),
    'refrigerator':('SYM',1), 'puzzle':('SYM',1), 'zebra':('SYM',2), 'bedroom':('SYM',1),
    'friend':('SYM',2), 'shower':('SYM',1), 'airplane':('ONE',3),

    # --- asymmetric two-handed: static passive base -----------------------------------
    'tree':('ASYM',3), 'helicopter':('ASYM',2), 'table':('ASYM',2), 'mitten':('ASYM',2),
    'chair':('ASYM',1), 'cut':('ASYM',1), 'paper':('ASYM',2), 'medicine':('ASYM',2),
    'napkin':('ASYM',1), 'toy':('ASYM',1),
}

root = sys.argv[1] if len(sys.argv) > 1 else 'handedness-analysis.csv'
rows = {r['word']: r for r in csv.DictReader(open(root))}

f = lambda r, k: float(r[k])
b = lambda r, k: r[k] == 'True'

TWO_HANDED = 0.70

present = [(w, c, s) for w, (c, s) in GT.items() if w in rows]
print(f"labelled {len(GT)} signs, {len(present)} present in the corpus\n")

# ---------------------------------------------------------------------------------------
# 1. How well does the wrist-travel-ratio split recover known structure?
# ---------------------------------------------------------------------------------------
print("=" * 78)
print("1. TRAVEL-RATIO SPLIT vs known structure   (ratio >= 0.70 => called two-handed)")
print("=" * 78)
tab = {}
for w, cls, conf in present:
    called = 'two' if f(rows[w], 'ratio') >= TWO_HANDED else 'one'
    tab.setdefault((cls, called), []).append(w)

for cls in ('ONE', 'SYM', 'ASYM'):
    one = tab.get((cls, 'one'), []); two = tab.get((cls, 'two'), [])
    n = len(one) + len(two)
    if not n: continue
    print(f"  {cls:5} (n={n:3})  called one-handed: {len(one):3}   called two-handed: {len(two):3}")

sym  = tab.get(('SYM','one'), []) + tab.get(('SYM','two'), [])
asym = tab.get(('ASYM','one'), []) + tab.get(('ASYM','two'), [])
sym_missed  = tab.get(('SYM','one'), [])
asym_missed = tab.get(('ASYM','one'), [])
print()
print(f"  SYMMETRIC signs misfiled as one-handed : {len(sym_missed)}/{len(sym)}")
print(f"    {', '.join(sorted(sym_missed))}")
print(f"  ASYMMETRIC signs misfiled as one-handed: {len(asym_missed)}/{len(asym)}")
print(f"    {', '.join(sorted(asym_missed))}")
print()
print("  ASYM landing in the one-handed bucket is EXPECTED — the passive hand is static by")
print("  definition, so travel ratio cannot see it. SYM landing there is not expected, and")
print("  points at the clip rather than the classifier.")

# ---------------------------------------------------------------------------------------
# 2. Salim's height test, scored against the labels
# ---------------------------------------------------------------------------------------
print()
print("=" * 78)
print("2. PASSIVE-HAND-HELD-UP test (Salim's), on signs the ratio called one-handed")
print("=" * 78)
tp = [w for w, c, _ in present if c in ('SYM','ASYM') and f(rows[w],'ratio') < TWO_HANDED and b(rows[w],'passiveUp')]
fn = [w for w, c, _ in present if c in ('SYM','ASYM') and f(rows[w],'ratio') < TWO_HANDED and not b(rows[w],'passiveUp')]
fp = [w for w, c, _ in present if c == 'ONE' and f(rows[w],'ratio') < TWO_HANDED and b(rows[w],'passiveUp')]
tn = [w for w, c, _ in present if c == 'ONE' and f(rows[w],'ratio') < TWO_HANDED and not b(rows[w],'passiveUp')]
prec = len(tp)/max(1,len(tp)+len(fp)); rec = len(tp)/max(1,len(tp)+len(fn))
print(f"  correctly flagged two-handed  : {len(tp)}")
print(f"  missed                        : {len(fn)}")
print(f"  ONE-handed wrongly flagged    : {len(fp)}   <-- the false-positive load")
print(f"  correctly left alone          : {len(tn)}")
print(f"\n  precision {prec:.2f}   recall {rec:.2f}")
print(f"\n  ONE-handed signs it wrongly flags:\n    {', '.join(sorted(fp)[:24])}")

# ---------------------------------------------------------------------------------------
# 3. Where geometry CONTRADICTS a sign whose form is not in doubt -> suspect the CLIP
# ---------------------------------------------------------------------------------------
print()
print("=" * 78)
print("3. CLIPS THAT CONTRADICT THEIR OWN SIGN  (confidence 3 labels only)")
print("=" * 78)
print("  A symmetric two-handed sign whose hands never come within 1.0 shoulder-widths, or")
print("  whose passive hand barely moves, is not showing that sign.\n")
suspect = []
for w, cls, conf in present:
    if conf < 3: continue
    r = rows[w]
    if cls == 'SYM' and (f(r,'ratio') < 0.35 or f(r,'minDist') > 1.0):
        suspect.append((w, cls, f(r,'ratio'), f(r,'minDist'), 'hands never meet / passive static'))
    if cls == 'ONE' and f(r,'ratio') > 0.85:
        suspect.append((w, cls, f(r,'ratio'), f(r,'minDist'), 'both hands equally active'))
print(f"  {len(suspect)} suspect clips:")
for w, cls, ratio, md, why in sorted(suspect):
    print(f"    {w:14} [{cls:4}] ratio {ratio:.2f}  minDist {md:.2f}  — {why}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print(f"  travel-ratio split misses {len(asym_missed)}/{len(asym)} asymmetric signs — real, and")
print(f"  structural: a static passive hand is invisible to a motion-based test.")
print(f"  The height test recovers them at precision {prec:.2f}, i.e. it flags roughly")
print(f"  {len(fp)} genuinely one-handed signs for every {len(tp)} it gets right.")
