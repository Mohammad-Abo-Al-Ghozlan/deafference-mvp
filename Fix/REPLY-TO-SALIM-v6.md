# Re: your three blockers — all answered, ② is YES and I built it

**To:** Mohammad Salim
**From:** animation / retargeting
**Attached:** `check-export.py` (v3 criteria), `suspect-clips.csv`, `chirality-check.mjs`,
`asymmetric-detect.py`, `weakdrop.txt`

---

## 0. Answers, so you can start

| | |
|---|---|
| **① acceptance criterion** | **Rewritten and attached.** Gates only what a selector can change — §1 |
| **② can the rig consume wrist + synthesized handshape** | **YES**, and it's implemented and verified — §2 |
| **② does 2s mirroring read correctly** | **YES**, exact on this rig. But my first attempt was wrong and every check passed it — §2 |
| **③ suspect-clip list** | **Attached**, 57 words, generated not recalled — §3 |
| Your one-hand-per-participant finding | **Independently confirmed, 21× effect** — §4 |
| Your gap-fill warning | **Not present in the v4 export you already sent** — §4 |

Your ⛔ was right and it saved me the day. I had `symmetry-test.py` queued to re-run after
your rebuild.

---

## 1. ① The acceptance criterion

You were right that mine could never pass. Worse, it was the *third* version of the same
mistake, so I've written the history into the file rather than quietly shipping v3:

```
v1  scored every word on one "dominant" hand      -> forgave two-handed signs
v2  scored two-handed words on strict min(L,R)    -> ranked a perfect dominant hand with an
                                                     absent passive hand BELOW a clip that
                                                     tracked both hands badly
v3  gates dominant coverage; treats the passive hand as a synthesis obligation
```

Your proposed shape, adopted essentially as you wrote it:

```
  [FAIL] DOMINANT-hand coverage >= 70%                28.8%
  [FAIL] words missing the DOMINANT hand == 0         137 words
  [PASS] every 2s/2a word has a passive WRIST track   0 words lack one
  [PASS] every 2s/2a word has a synthesis class       87 words classified
  [ -- ] passive hand absent (EXPECTED, not a failure)  37 of 87 two-handed words
         lexicon: 163 one-handed, 52 2s, 35 2a
```

Two deliberate choices: the passive-hand line is `[ -- ]`, not PASS/FAIL, because a constant
of the dataset isn't a criterion. And the synthesis-class line exists so that a two-handed word
with no class **fails** rather than silently rendering a relaxed hand — that's the "none gets
silently skipped" guard you asked for. Re-verified against a synthetic clean export: still
exits 0, so the criteria can still pass.

**One discrepancy to check on your side.** Your renderer contract says the passive hand "DOES
NOT EXIST in our corpus for any take". I measure **37 of 87** two-handed words with zero
passive coverage — so **50 have some**. Consistent with one-hand-per-participant if the
recorded hand is sometimes the one I call passive, but it means the contract line is stronger
than the data. Worth reconciling before it becomes an assumption someone builds on.

---

## 2. ② YES — and here is the part worth reading

**The architecture already does what your §2 proposes**, which is lucky rather than clever:
wrist orientation and finger articulation were separated months ago for a different reason.
Wrist orientation comes from the pose-block knuckles (landmarks 17–22), present in 98.8% of
frames where the 21-point block is missing. Finger articulation is a separate stage with an
explicit hook for "no data". So `wrist trajectory + separately-supplied handshape` is not a new
capability — it's the existing shape of the code. **Your export design is right.**

Implemented, driven by your lexicon:

```
node retarget.mjs model.glb words/*.json --handedness=asl_handedness_250.json
  ...
  passive hand MIRRORED from the dominant on 36 frame-sides (class 2s)
  passive hand relaxed on 56 frame-sides (class 2s)
```

`1` → relaxed curl · `2s` → mirror the dominant · `2a` → relaxed for now, pending the unmarked
handshape set. Full run: 250/250 anatomy gate, hinge check clean, jitter 0.24–0.52 vs the
signer's 0.909, rig suite 60/60.

### But my first mirroring implementation was wrong, and nothing caught it

I mirrored world-space bone **directions** across the sagittal plane. It's a reasonable-looking
approach and it is wrong: `aim()` constrains one axis per bone, but a reflection has
determinant −1 — the chirality lives in the roll about the finger axis, which `aim()` leaves
free. The result was a hand whose fingers curled correctly and whose **palm faced the wrong
way**. An inside-out hand.

It passed **everything**: anatomy gate 250/250, finger hinge check clean, jitter in budget, rig
suite 60/60. All of those are bilaterally symmetric or per-joint, so a correct curl on a
backwards palm is invisible to them. Measured on palm normals it matched a true mirror in 7/80
frames on `book` and **0/80** on `bath`.

The fix is to copy **local** joint rotations — handshape is a wrist-relative quantity, and this
rig's left/right bind poses are mirrored, so identical local rotations already produce mirrored
world geometry, while the passive wrist keeps its own real orientation. Verified statically
rather than assumed:

```
put both hands' finger bones at identical local rotations, wrists at rest:
  mean |left - mirror(right)| = 0.0000 m
  PASS: bind poses ARE mirrored -> local-rotation copy mirrors the handshape exactly
```

So **2s mirroring is exact on this rig**, and your Symmetry Condition reasoning holds in the
renderer. Not "looks fine" — 0.0000 m.

### The failed check turned into your §6.2 filter

I'd written `chirality-check.mjs` to gate the synthesis at runtime. After the static test made
it redundant, I looked at what it was actually measuring: the palm normal is dominated by
**wrist** orientation, and the passive wrist isn't synthesized — it's real pose-block data. So
on a 2s word it asks *"is the passive ARM in this take actually performing the symmetric
sign?"*

Which is a per-frame weak-drop detector. On the current corpus:

```
frames where the passive arm performs the symmetric sign: 1066/4123 = 25.9%
weak-drop candidates: 46 of 52 2s words below 80%
  awake 0/80 · drawer 0/80 · hate 0/77 · loud 0/80 · pool 0/80 · same 0/80
  shoe 0/80 · stairs 0/80 · jeans 1/80 · rain 1/80 · snow 1/80 · bedroom 2/80 ...
```

Attached as `weakdrop.txt`. It's finer-grained than a clip-level ratio because it's per frame,
so it can also tell you *when* in a take the hand drops.

---

## 3. ③ The suspect list — `suspect-clips.csv`, 57 words

Generated against your lexicon rather than recalled from what I happened to mention. Three
rules, each flagging a different contradiction between the clip and the sign it claims to be:

| rule | n |
|---|---|
| class `2s`/`2a` but the passive arm barely moves (ratio < 0.35) | 41 |
| class `2s` but the passive arm never mirrors (< 20% of frames) | 8 |
| class `1` but **both** arms are equally active (ratio > 0.85) | 8 |

Worst: `flag` 0.03, `tree` 0.07, `noisy` 0.11, `store` 0.13, `person` 0.14, `read` 0.14,
`glasswindow` 0.15, `backyard` 0.15, `helicopter` 0.16, `owie` 0.16.

The third rule is the one I'd watch — a one-handed sign with two active arms isn't weak drop,
it's a different failure, and it's where `cat`, `eye` and `mouse` landed earlier.

Caveat: every threshold is mine and unvalidated. Treat the CSV as ranked candidates, not
labels — the `armRatio` column is there so you can move the cut yourself.

---

## 4. Your findings, independently checked

**One hand per participant — confirmed, and the effect is larger than your framing.** On my 250
clips:

```
P(L)=0.385  P(R)=0.412
if independent:  expect 2538 both-hand frames    observed 120     (21x short)
clip level:      109 only-L   124 only-R   17 both-at-some-point   0 neither
```

233 of 250 clips only ever show one hand. Your "exactly-one-of-two is a constraint, not a
failure distribution" is right, and I can't see a mechanism other than capture.

**Gap-fill — not present in the v4 export you already sent me.** This one matters for your
re-extraction, so I tested it three ways:

```
bit-identical consecutive wrist positions : 0 / 31754
bit-identical consecutive hand blocks     : 0 / 12752
handshape frozen while the wrist moves    : 0 / 12181   <- the ffill signature after smoothing
```

Resampling to 64 frames preserves ffill bit-exactly (interpolating between two identical values
returns that value), so the first two are meaningful, and the third catches a fill that was
later smoothed. **Nothing froze.** So the fill lives upstream of whatever produced v4, which
should narrow your search — and my current numbers are on genuinely observed data, not inflated.

No, I'm not seeing hands stop dead mid-sign.

**Your lexicon vs mine: 92% (85/92), zero max-confidence disagreements.** Matches your 91%.
Conceding `napkin` (`2a`→`1`) and `shower` (`2s`→`1`) — you're at high confidence, I was at
low. `sad`, `toy`, `cut`, `owie`, `refrigerator` to the Deaf reviewer. Thank you for taking
`table`.

---

## 5. What I need, and what I'd change in your v7

Nothing blocking — go ahead and rebuild.

**One suggestion on §6.4.** You're scoring dominant-hand coverage only, which matches my v3
criterion, good. But consider scoring it **within `segments`** *and* requiring contiguity: 30
frames spanning the stroke beats 30 scattered across the take, because I bridge gaps by
interpolation and a bridged handshape is a straight line between two real ones. A cheap proxy
is the longest single run of covered frames, not just the count.

**And the `2a` set.** I've left `2a` on the relaxed curl because I don't have your unmarked
handshape set. If you can attach the B/A/S/1/5/C/O configurations — even as 21-point landmark
templates in the same coordinate convention as the export — I'll wire them in the same way as
2s. That closes the last synthesis gap.

Three things back to you when the rebuild lands: the within-word correlation, the new export,
and I'll re-run the whole suite and send numbers.

---

On your closing note — agreed, and I'll add the version that cost me most today: **a check that
cannot fail is indistinguishable from a check that passes.** Your `presence < 0.5` warning, my
`dominantHand = 'right'` assertion, my `passive hand absent == 0` criterion, and today the four
green checks over an inside-out hand. Every one of them reported success from a test with no
power to detect the failure. The static 0.0000 m test is the first thing today I actually
believe, because it could have come back non-zero.
