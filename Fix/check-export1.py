#!/usr/bin/env python3
"""Self-check for the Deafference landmark export. Run this BEFORE sending a new batch.

    python3 check-export.py path/to/words

Prints a pass/fail report against the acceptance criteria in DEAFFERENCE-DATA-SPEC-v4.md,
so a re-export can be validated in seconds instead of a round-trip through the animation
side.

The single number that matters is REQUIRED-HAND COVERAGE. Everything else is cheap to fix;
that one gates two thirds of the vocabulary.

"Required hand" is deliberate. A one-handed sign needs handshape on the hand that signs; a
TWO-handed sign needs it on both, because both carry handshape. Scoring every word against a
single "dominant" hand undercounts the problem: it silently forgives a two-handed sign that
lost one hand completely. Whether a sign is one- or two-handed is inferred from the ratio of
wrist travel between the hands (below TWO_HANDED they differ enough to call a dominant hand;
above it they move together and both are required).
"""
import json, glob, math, os, sys
from collections import Counter

root = sys.argv[1] if len(sys.argv) > 1 else 'words'
files = sorted(glob.glob(os.path.join(root, '*.json')))
if not files:
    sys.exit(f'no *.json under {root}')

def ok(p):
    # 3 components, or 4 once ASK 3 lands and visibility is appended. Accept both, so that
    # adding confidence does not make this script report every frame as invalid.
    return (isinstance(p, list) and 3 <= len(p) <= 4
            and all(isinstance(v, (int, float)) for v in p))

def block_state(fr, base):
    """'ok' | 'zeros' | 'null' | 'partial' — zeros are the failure mode we care about."""
    pts = fr[base:base+21]
    if len(pts) < 21:            return 'partial'
    if all(p is None for p in pts): return 'null'
    if not all(ok(p) for p in pts): return 'partial'
    # only x,y,z count as "is this actually a position" — a confidence of 0.9 on an all-zero
    # point must not disguise a zero block as real data
    if not any(abs(v) > 1e-9 for p in pts for v in p[:3]): return 'zeros'
    return 'ok'

LSH, RSH, LEL, REL, LWR, RWR = 11, 12, 13, 14, 15, 16
TWO_HANDED = 0.70          # weaker/stronger wrist travel above this => both hands required
W_DOM, W_PAS = 0.70, 0.30  # two-handed weighting; MUST match the selector's objective
tot_valid = tot_null = 0
sign_cov = rest_cov = 0
req_cov = req_den = 0      # coverage counted only over hands the sign actually needs
missing_required = []      # words where the DOMINANT hand is absent — unrecoverable
degraded = []              # passive hand absent — synthesizable, reported not failed
onehanded = twohanded = 0
block = Counter()
mirror_right_smaller = mirror_total = 0
durations = Counter()
per_word = []
impossible = []
speed_tracked, speed_untracked = [], []
has_conf = None

for fp in files:
    d = json.load(open(fp))
    F = d.get('frames', [])
    w = os.path.basename(fp)[:-5]
    durations[len(F)] += 1
    if has_conf is None:
        # confidence would appear as a 4th component or a sibling array
        f0 = next((f for f in F if isinstance(f, list) and f and isinstance(f[0], list)), None)
        has_conf = bool(f0 and len(f0[0]) > 3) or ('visibility' in d) or ('confidence' in d)

    path = {'L': 0.0, 'R': 0.0}; prev = {}; cov = {'L': 0, 'R': 0}
    valid = 0; nullf = 0; longlimb = 0
    prevspd = {}
    for fr in F:
        if not isinstance(fr, list) or len(fr) < 75 or not ok(fr[LSH]) or not ok(fr[RSH]):
            nullf += 1; continue
        valid += 1
        sw = math.hypot(fr[RSH][0]-fr[LSH][0], fr[RSH][1]-fr[LSH][1]) or 1
        mirror_total += 1
        if fr[RSH][0] < fr[LSH][0]: mirror_right_smaller += 1
        for s, sh, el, wr, base in (('L', LSH, LEL, LWR, 33), ('R', RSH, REL, RWR, 54)):
            st = block_state(fr, base); block[st] += 1
            if st == 'ok': cov[s] += 1
            if not (ok(fr[sh]) and ok(fr[el]) and ok(fr[wr])): continue
            # a projected limb can never exceed the true limb length
            if math.hypot(fr[el][0]-fr[sh][0], fr[el][1]-fr[sh][1]) / sw > 1.0: longlimb += 1
            p = ((fr[wr][0]-fr[sh][0])/sw, (fr[wr][1]-fr[sh][1])/sw)
            if s in prev:
                v = math.hypot(p[0]-prev[s][0], p[1]-prev[s][1])
                path[s] += v
                (speed_tracked if st == 'ok' else speed_untracked).append(v)
            prev[s] = p
    dom = 'R' if path['R'] >= path['L'] else 'L'
    oth = 'L' if dom == 'R' else 'R'
    sign_cov += cov[dom]; rest_cov += cov[oth]
    tot_valid += valid; tot_null += nullf
    if longlimb: impossible.append((w, longlimb))

    # one- vs two-handed, and coverage over the hands the sign actually requires.
    #
    # Two-handed words are scored W_DOM/W_PAS, matching what the selector optimizes. Strict
    # min() was wrong and this file had it: it scored a perfectly-tracked dominant hand with
    # an absent passive hand at 0, ranking it below a clip that tracked both hands badly.
    # That is backwards — a passive base hand in an asymmetric sign is drawn from a small set
    # of unmarked handshapes and can be synthesized; a dominant handshape never can.
    #
    # MISSING is therefore reserved for an absent DOMINANT hand, which is unrecoverable at
    # any effort. An absent passive hand is reported separately as 'degraded'.
    ratio = path[oth] / max(1e-9, path[dom])
    if ratio >= TWO_HANDED:
        twohanded += 1
        req_cov += W_DOM * cov[dom] + W_PAS * cov[oth]; req_den += valid
        score = W_DOM * cov[dom] + W_PAS * cov[oth]
        if cov[dom] == 0:
            missing_required.append((w, 'two-handed, DOMINANT hand absent'))
        elif cov[oth] == 0:
            degraded.append((w, 'two-handed, passive hand absent (synthesizable)'))
        per_word.append((w, int(round(score)), valid, 'two'))
    else:
        onehanded += 1
        req_cov += cov[dom]; req_den += valid
        if cov[dom] == 0: missing_required.append((w, 'one-handed, signing hand absent'))
        per_word.append((w, cov[dom], valid, 'one'))

def q(a, p):
    if not a: return 0.0
    a = sorted(a); return a[min(len(a)-1, int(len(a)*p))]

nwords = len(files)
sc = 100*sign_cov/max(1, tot_valid)
rc = 100*rest_cov/max(1, tot_valid)
rq = 100*req_cov/max(1, req_den)

def line(label, passed, detail):
    print(f"  [{'PASS' if passed else 'FAIL'}] {label:44} {detail}")

print(f"\n{nwords} words, {tot_valid} valid frames, {tot_null} unusable")
print(f"classified {onehanded} one-handed / {twohanded} two-handed by wrist-travel ratio\n")
print("ACCEPTANCE CRITERIA")
line("required-hand coverage >= 70%", rq >= 70,
     f"{rq:.1f}%   (0.70*dom + 0.30*passive on two-handed)")
line("words missing the DOMINANT hand == 0", not missing_required,
     f"{len(missing_required)} words")
line("two-handed words missing the passive hand", not degraded,
     f"{len(degraded)} words (degraded, not fatal — synthesizable)")
line("no hand block encoded as 21 zeros", block['zeros'] == 0,
     f"{block['zeros']} zero-blocks ({100*block['zeros']/max(1,sum(block.values())):.0f}%)")
line("native clip duration (not all 64)", len(durations) > 1 or 64 not in durations,
     f"{dict(durations)}")
line("per-landmark confidence present", bool(has_conf), 'yes' if has_conf else 'missing')
line("no limb projects longer than itself", not impossible,
     f"{len(impossible)} words affected" + (f", worst: {max(impossible,key=lambda x:x[1])[0]}" if impossible else ""))
mir = 100*mirror_right_smaller/max(1, mirror_total)
# a real check, not a rubber stamp: whichever convention holds, it must hold CONSISTENTLY.
# 100% => raw camera (contract §3 currently claims selfie-mirrored and is wrong).
# 0%   => selfie-mirrored. Anything in between means it varies between clips, which is worse
# than either, because then no single convention can be documented.
line("handedness convention is consistent", mir >= 95 or mir <= 5,
     f"right shoulder at smaller x in {mir:.0f}% of frames"
     + ("  => raw camera, NOT selfie-mirrored" if mir >= 95 else
        "  => selfie-mirrored" if mir <= 5 else
        "  <-- INCONSISTENT between clips"))

print(f"\nDIAGNOSTIC — is the tracker dropping the hand that MOVES?")
mt, mu = q(speed_tracked, .5), q(speed_untracked, .5)
print(f"  median wrist speed, hand block PRESENT : {mt:.4f} sh.w./frame")
print(f"  median wrist speed, hand block MISSING : {mu:.4f}")
print(f"  ratio                                  : {mu/max(1e-9,mt):.2f}x", end='  ')
print("<-- should be ~1.0; >1.5 means the tracker is losing the moving hand"
      if mu/max(1e-9,mt) > 1.5 else "(ok)")

print(f"\n  signing hand {sc:.1f}%   resting hand {rc:.1f}%", end='  ')
print("<-- resting > signing is the inverted failure" if rc > sc else "(ok)")

worst = sorted(per_word, key=lambda x: (x[1], x[0]))[:15]
print(f"\nWORST 15 WORDS by required-hand coverage:")
for w, c, v, kind in worst: print(f"   {w:16} {c:3d} / {v}   ({kind}-handed)")

if missing_required:
    print(f"\nRE-SELECT LIST — {len(missing_required)} words missing the DOMINANT hand:")
    print("   " + ', '.join(w for w, _ in sorted(missing_required)))
if degraded:
    print(f"\nDEGRADED — {len(degraded)} two-handed words missing only the passive hand.")
    print("   Recoverable: for a SYMMETRIC two-handed sign the passive handshape equals the")
    print("   dominant one (Battison's Symmetry Condition), so it is mirrored, not guessed.")
    print("   " + ', '.join(w for w, _ in sorted(degraded)))
print()
sys.exit(0 if (rq >= 70 and not missing_required and block['zeros'] == 0) else 1)
