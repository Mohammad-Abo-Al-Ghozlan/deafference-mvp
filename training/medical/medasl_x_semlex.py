"""THE decisive question: MedASL's glosses tell us what medical ASL actually uses.
Sem-Lex tells us what we can actually train. Where do they overlap?"""
import urllib.request, csv, io, re, json
from collections import Counter, defaultdict

B = ('https://raw.githubusercontent.com/INDUCE-Lab/'
     'ADAT-Adaptive-Transformer-for-Sign-Language-Translation/main/Datasets/MedASL/')

def dl(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode('utf-8-sig', errors='replace')

# ---- 1. the real medical gloss vocabulary, straight from MedASL ----
gloss_tokens = Counter()
sent_count = 0
gloss_lens = []
for tag in ('MedASL2000', 'MedASL500'):
    rows = list(csv.DictReader(io.StringIO(dl(B + tag + '/Annotations/Gloss-Text%20Annotations.csv'))))
    for r in rows:
        g = (r.get('Gloss') or '').strip()
        if not g:
            continue
        sent_count += 1
        toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-']*", g.upper()) if t]
        gloss_lens.append(len(toks))
        gloss_tokens.update(toks)

print(f"MedASL (500+2000): {sent_count} sentences")
print(f"  gloss vocabulary: {len(gloss_tokens)} distinct tokens")
print(f"  glosses/sentence: min={min(gloss_lens)} median={sorted(gloss_lens)[len(gloss_lens)//2]} max={max(gloss_lens)}")
print(f"  top 30 by frequency: {[w for w,_ in gloss_tokens.most_common(30)]}\n")

# ---- 2. what Sem-Lex can train ----
txt = open('semlex.csv', 'rb').read().decode('utf-8-sig', errors='replace')
rows = list(csv.reader(io.StringIO(txt)))
h = rows[0]; iL, iS = h.index('label'), h.index('signer_id')
vids, signers = Counter(), defaultdict(set)
for r in rows[1:]:
    if len(r) > max(iL, iS) and r[iL].strip():
        g = r[iL].strip().lower(); vids[g] += 1; signers[g].add(r[iS].strip())

def lookup(tok):
    """try the token, then simple morphological variants Sem-Lex might label differently"""
    t = tok.lower()
    for cand in (t, t + 's', t.rstrip('s'), t + 'e', t.replace('-', '_'), t.replace('-', '')):
        if cand in vids:
            return cand, vids[cand], len(signers[cand])
    return None, 0, 0

MIN_V, MIN_S = 8, 3
tiers = {'trainable': [], 'thin': [], 'absent': []}
for tok, freq in gloss_tokens.items():
    lab, n, s = lookup(tok)
    rec = (tok, freq, lab, n, s)
    tiers['trainable' if (n >= MIN_V and s >= MIN_S) else ('thin' if n else 'absent')].append(rec)

tot = len(gloss_tokens)
print(f"MedASL gloss vocabulary vs Sem-Lex trainability (>={MIN_V} videos, >={MIN_S} signers):")
for t in ('trainable', 'thin', 'absent'):
    print(f"  {t:10} {len(tiers[t]):4} / {tot}  ({len(tiers[t])/tot*100:.0f}%)")

# weight by usage: covering frequent glosses matters more than rare ones
tok_total = sum(gloss_tokens.values())
cov = sum(f for _, f, _, _, _ in tiers['trainable'])
print(f"\nTOKEN-WEIGHTED coverage: {cov:,}/{tok_total:,} gloss occurrences trainable = {cov/tok_total*100:.1f}%")
print("  (i.e. of every gloss token used across all 2,500 medical sentences,")
print(f"   {cov/tok_total*100:.0f}% can be trained from Sem-Lex video today)")

# ---- 3. how many whole sentences are FULLY covered? (retrieval-first needs this) ----
trainable_toks = {t for t, _, _, _, _ in tiers['trainable']}
full, partial = 0, 0
for tag in ('MedASL2000', 'MedASL500'):
    pass  # already counted; recompute per-sentence below

rows_all = []
for tag in ('MedASL2000', 'MedASL500'):
    rows_all += list(csv.DictReader(io.StringIO(dl(B + tag + '/Annotations/Gloss-Text%20Annotations.csv'))))
ok_sent = []
for r in rows_all:
    g = (r.get('Gloss') or '').strip()
    if not g: continue
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-']*", g.upper()) if t]
    if toks and all(t in trainable_toks for t in toks):
        ok_sent.append((r.get('Text', '').strip(), g))
print(f"\nFULLY-COVERED SENTENCES (every gloss trainable): {len(ok_sent)} of {sent_count} "
      f"({len(ok_sent)/sent_count*100:.0f}%)")
print("  examples:")
for t, g in ok_sent[:8]:
    print(f"    \"{t}\"  ->  {g}")

print(f"\nMOST-FREQUENT MISSING glosses (fix these first — highest usage):")
miss = sorted(tiers['absent'] + tiers['thin'], key=lambda x: -x[1])
for tok, freq, lab, n, s in miss[:25]:
    print(f"    {tok:18} used {freq:4}x   semlex: {n:3}v/{s:2}s {'(thin)' if n else '(ABSENT)'}")

json.dump({
    'medasl_sentences': sent_count,
    'medasl_gloss_vocab': len(gloss_tokens),
    'trainable': sorted(t for t, _, _, _, _ in tiers['trainable']),
    'thin': sorted((t, n) for t, _, _, n, _ in tiers['thin']),
    'absent': sorted(t for t, _, _, _, _ in tiers['absent']),
    'token_weighted_coverage': round(cov / tok_total, 4),
    'fully_covered_sentences': len(ok_sent),
}, open('medasl_semlex_overlap.json', 'w'), indent=1)
print("\nwrote medasl_semlex_overlap.json")
