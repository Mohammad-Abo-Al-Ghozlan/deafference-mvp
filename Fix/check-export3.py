#!/usr/bin/env python3
"""Self-check for the Deafference landmark export. Run this BEFORE sending a new batch.

    python3 check-export.py path/to/words

Prints a pass/fail report against the acceptance criteria in DEAFFERENCE-DATA-SPEC-v4.md,
so a re-export can be validated in seconds instead of a round-trip through the animation
side.

The single number that matters is DOMINANT-HAND COVERAGE. Everything else is cheap to fix or
is a constant of the dataset.

This criterion has been through three versions and the history is the point:

  v1  scored every word on one "dominant" hand           -> forgave two-handed signs
  v2  scored two-handed words on strict min(L, R)        -> ranked a perfect dominant hand
                                                            with an absent passive hand at 0,
                                                            below a clip that tracked both
                                                            hands badly. Backwards.
  v3  (this) scores DOMINANT-hand coverage only, and treats the passive hand as a synthesis
      obligation rather than a coverage failure.

v3 is what the data actually supports. GISLR records ONE hand per participant — independence
would predict ~2,538 both-hand frames in our 250 clips and we observe 120 — so for a
two-handed sign the passive hand is absent in EVERY take. No selector can change that. A
criterion that can never pass is not a criterion, so "passive hand absent" is REPORTED, and
what is GATED is the thing that can be fixed: dominant-hand coverage, a real passive wrist
trajectory to hang a synthesized handshape on, and a synthesis class for every two-handed word
so none is silently skipped.

Synthesis classes come from the handedness lexicon, because handedness is not derivable from
these landmarks (four classifiers tested; best AUC 0.335, i.e. inverted):
    2s -> mirror the dominant handshape (Symmetry Condition — exact, not a guess)
    2a -> unmarked handshape at the base location (Dominance Condition — never mirror)
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

# --- handedness lexicon -----------------------------------------------------------------
# Handedness is not derivable from GISLR landmarks (four classifiers tested, best AUC 0.335,
# i.e. inverted). Supplied lexically. Given it, the criteria below change shape: the passive
# hand is absent in EVERY take of a two-handed sign, because the corpus records one hand per
# participant. So "passive hand absent" can never reach 0 and must not be a PASS/FAIL gate —
# it is a constant of the dataset, and a criterion that can never pass is not a criterion.
LEXICON = 'asl_handedness_250.json'
try:
    _lex = json.load(open(LEXICON))
    LEX = {k: v[0] for k, v in _lex['words'].items()}
except Exception:
    LEX = {}
tot_valid = tot_null = 0
sign_cov = rest_cov = 0
req_cov = req_den = 0      # coverage counted only over hands the sign actually needs
missing_required = []      # words where the DOMINANT hand is absent — unrecoverable
missing_wrist = []         # two-handed words lacking a usable passive WRIST trajectory
needs_synth = []           # every two-handed word, with the synthesis class it requires
passive_absent = 0         # expected to equal len(needs_synth): a constant of the dataset
onehanded = twohanded = 0
block = Counter()
mirror_right_smaller = mirror_total = 0
durations = Counter()
per_word = []
impossible = []
derived_dominance = []     # words whose dominantHand had to be guessed from travel (see below)
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
    wrist_ok = {'L': 0, 'R': 0}
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
            if ok(fr[wr]): wrist_ok[s] += 1
            if not (ok(fr[sh]) and ok(fr[el]) and ok(fr[wr])): continue
            # a projected limb can never exceed the true limb length
            if math.hypot(fr[el][0]-fr[sh][0], fr[el][1]-fr[sh][1]) / sw > 1.0: longlimb += 1
            p = ((fr[wr][0]-fr[sh][0])/sw, (fr[wr][1]-fr[sh][1])/sw)
            if s in prev:
                v = math.hypot(p[0]-prev[s][0], p[1]-prev[s][1])
                path[s] += v
                (speed_tracked if st == 'ok' else speed_untracked).append(v)
            prev[s] = p
    # READ dominance, do not derive it. Deriving from wrist travel is the R5 failure wearing a
    # third hat: the tracker keeps the hand that does NOT move, so travel is exactly the signal
    # that is unreliable here. `finish` is the proof — its two arms travel within a few percent
    # of each other, the >= tie-break flips on noise, and this script reported it as the one
    # failure in an otherwise clean 250 while the export had asserted dominantHand: 'R' all
    # along (wrist co-location 0.09 to its own limb vs 1.793 to the other — not close).
    # The exporter guarantees this field on all 250; travel stays only as a fallback for
    # hand-made or truncated files, and says so out loud when it fires.
    _syn = (d.get('segments') or [{}])[0].get('synthesis') or {}
    _declared = _syn.get('dominantHand')
    if _declared in ('L', 'R'):
        dom = _declared
    else:
        dom = 'R' if path['R'] >= path['L'] else 'L'
        derived_dominance.append(w)
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
    # class from the lexicon where available; fall back to the travel ratio otherwise
    cls = LEX.get(w) or ('2s' if path[oth] / max(1e-9, path[dom]) >= TWO_HANDED else '1')
    kind = 'one' if cls == '1' else 'two'
    if kind == 'two':
        twohanded += 1
        needs_synth.append((w, cls))
        if cov[oth] == 0: passive_absent += 1
    else:
        onehanded += 1
    # DOMINANT-hand coverage is the whole criterion. The passive hand is known-absent for
    # every two-handed word, so including it would only add a constant and hide the signal.
    req_cov += cov[dom]; req_den += valid
    if cov[dom] == 0: missing_required.append((w, f'{cls}: dominant hand absent'))
    per_word.append((w, cov[dom], valid, kind))
    # the passive WRIST is a pose landmark and must be present so the avatar can place a
    # synthesized handshape on a real trajectory rather than a guessed one
    if kind == 'two' and wrist_ok[oth] < 0.9 * valid:
        missing_wrist.append((w, wrist_ok[oth], valid))

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
line("DOMINANT-hand coverage >= 70%", rq >= 70, f"{rq:.1f}%")
line("words missing the DOMINANT hand == 0", not missing_required,
     f"{len(missing_required)} words")
line("every 2s/2a word has a passive WRIST track", not missing_wrist,
     f"{len(missing_wrist)} words lack one")
line("every 2s/2a word has a synthesis class", all(c in ('2s','2a') for _, c in needs_synth),
     f"{len(needs_synth)} words classified")
# A counter that SHOULD read zero. If it does not, this script silently went back to inferring
# dominance from wrist travel — the exact measurement R5 says is unreliable — and any word it
# names is being scored against a coin flip rather than against the export's own assertion.
line("dominantHand READ, never derived", not derived_dominance,
     "0 words derived" if not derived_dominance
     else f"{len(derived_dominance)} derived from travel: {', '.join(sorted(derived_dominance)[:6])}")
print(f"  [ -- ] passive hand absent (EXPECTED, not a failure)  "
      f"{passive_absent} of {len(needs_synth)} two-handed words")
if LEX:
    from collections import Counter as _C
    _c = _C(LEX.values())
    print(f"         lexicon: {_c.get('1',0)} one-handed, {_c.get('2s',0)} 2s, {_c.get('2a',0)} 2a")
line("no hand block encoded as 21 zeros", block['zeros'] == 0,
     f"{block['zeros']} zero-blocks ({100*block['zeros']/max(1,sum(block.values())):.0f}%)")
line("native clip duration (not all 64)", len(durations) > 1 or 64 not in durations,
     f"{dict(durations)}")
# RETIRED 2026-08-14, by agreement with the animation side, who removed the same criterion from
# their copy first. A landmark is either exported with coordinates or exported as null, and null
# IS "not visible" — so a 4th confidence component would be a constant function of the first
# three and could never fail independently. It is the check-that-cannot-fail pattern again, and
# it was FAILING here on a 250/250-clean export purely because the field does not exist by
# design. Kept as a comment rather than deleted so nobody re-adds it in a later round.
# line("per-landmark confidence present", bool(has_conf), 'yes' if has_conf else 'missing')
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
if False:
    print(f"\nDEGRADED — {len(degraded)} two-handed words missing only the passive hand.")
    print("   Recoverable: for a SYMMETRIC two-handed sign the passive handshape equals the")
    print("   dominant one (Battison's Symmetry Condition), so it is mirrored, not guessed.")
    print("   " + ', '.join(w for w, _ in sorted(degraded)))
print()
sys.exit(0 if (rq >= 70 and not missing_required and not missing_wrist and block['zeros'] == 0) else 1)
