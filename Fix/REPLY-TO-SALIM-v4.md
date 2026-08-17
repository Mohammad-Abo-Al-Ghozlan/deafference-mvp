# Re: contract v4 — verified, and you found a bug on my side

**To:** Mohammad Salim
**From:** animation / retargeting
**Re:** `READ-ME-FIRST_what-changed.md`

---

## 0. Short version

| | |
|---|---|
| ✅ Your v4 export | **Verified.** Zeros 19,002 → 0, `segments` real, contract §3 corrected |
| ✅ ASK 3 (`visibility`) | **Dropped permanently.** You're right, and it was in your contract §0 — I missed it |
| ✅ ASK 1 (tracking work) | **Cancelled.** No time reserved. Retargeted as data *selection* |
| 🔴 **Your §5.4 dominance question** | **You found a real bug in my mirroring.** Fixed. Details in §2 |
| ⚠️ **Your new selector** | **Still carries the old bias in a subtler form.** Please read §3 before you rebuild |

§3 is the one that matters. Your selector fix is correct but I think it will
under-deliver for a reason that isn't obvious, and it's cheap to guard against now versus
after a day of restoring 2.1 GB.

---

## 1. Your v4 export, verified

Ran `check-export.py` against `animation_handoff/words`:

```
250 words, 15877 valid frames, 123 unusable
  [PASS] no hand block encoded as 21 zeros            0 zero-blocks (0%)
  [PASS] handedness convention is consistent          right shoulder at smaller x in 100% => raw camera
```

- **Zeros:** 19,002 → **0**. Confirmed.
- **`down`:** `segments` reads **0–45**, matching my independent "loses its last 21 frames". Good cross-check.
- **28 of 250** words have an extent shorter than the window — matches your count exactly.
- **`note` field:** correct on all three conventions.

I've deleted the zero-sniffing path and now use `null` + interpolation as the contract
always intended.

**One detail worth flagging as a positive.** Coverage came out at **30.3% / 164 words —
byte-identical to the v3 numbers.** That is the correct outcome and a useful cross-check: it
confirms my zero-detection had been reading the zeros correctly all along, so your fix
changed the *encoding* without changing the *information*. If those numbers had moved, one of
us would have had a second bug. They didn't.

Your three-independent-manufacture-points root cause is the more alarming version of what I
reported, and `canonicalize_missing()` at every load site is the right shape of fix.

---

## 2. You were right about dominance — and it was worse than you flagged

Your §5.4 asked me to check one number. It was a real bug and I'd have missed it.

**Your reconciliation was correct.** My CSV reads 171R/24L because it was computed on
`words-normalized/` — my *post-mirroring* data, from a normalization step I never told you
about. I mirror every left-dominant word to right so the avatar always signs with the same
hand. So we were describing different stages of the same pipeline, and my raw measurement
reproduces yours exactly:

```
RAW corpus (your side)    : 132 left / 118 right
my raw re-measurement     : 132 left / 118 right     <- identical
```

**But that's also what exposed the bug.** If mirroring worked, *all* 195 one-handed words
would be right-dominant afterwards. 24 weren't. Your question was the only reason I looked.

### Root cause: I shipped the exact inverted heuristic I warned you about

`mirror-words.mjs` had a `--from-clips` flag that took dominance from the **retargeted 3D
output** instead of the landmarks. My reasoning, written in a comment defending it: *"a sign
that moves toward the camera has little 2D travel, so measure the avatar's real 3D path
instead."*

The flaw: **the avatar's depth is not measured, it's reconstructed** as
`|dz| = √(L² − d_2d²)`. So reconstructed depth is *largest* exactly where 2D travel is
*smallest*. 3D path length tracks my own reconstruction rather than the signer's motion.

Measured rather than argued — on the 45 words where the two methods disagree:

```
3D picked the hand with LESS 2D travel:  45 / 45  =  100%
```

Not noise. A systematic inversion, in the same family as the presence heuristic I told you
would get the answer backwards in §3.4. I wrote a paragraph diagnosing that failure mode for
you and shipped it myself, in a form I'd explicitly justified in a comment.

### What it cost, measured on what a viewer actually sees

Screen-space (x,y) travel of the hand bone — not 3D, because the viewer sees a projection:

| | before | after |
|---|---|---|
| one-handed words signed with the **wrong** hand | **27** | **5** |
| words whose visible signing hand changed | — | 45 |

Of the 5 remaining: 3 (`cut`, `give`, `mouse`) are near-ties in the source (travel ratio
0.94–0.95 — effectively two-handed, harmless). 2 (`beside`, `on`) are genuine, and differ
because shoulder-relative articulation and absolute screen travel disagree about which hand
"dominates" when the torso carries both. I'm leaving those rather than special-casing.

### Why none of my checks caught it

Worth stating because it's the same lesson as your `presence < 0.5` warning that couldn't
fire. **Every check I had was invariant to this bug:**

- **Fidelity** compares output to the *mirrored* source — a wrongly-mirrored word is still
  perfectly faithful to its wrongly-mirrored input. Identical r-values before and after
  (0.941–0.950, 250/250 > 0.90). Blind by construction.
- **Anatomy gate, jitter, motion** — all bilaterally symmetric. A mirrored pose is exactly as
  valid as the original.

The step wrote `doc.dominantHand = 'right'` and nothing ever tested whether that was true.
Yours reported `250/250 clean`; mine asserted its own success flag. Same shape of failure.

**Fixed:** `--from-clips` is removed and now exits with an error rather than being silently
ignored, and the step verifies its own postcondition on the output:

```
normalised 250 words to right-dominant
   mirrored 132   already correct 118
   verified on output: 195/195 one-handed words are right-dominant
```

Full re-run on your v4 data: **250/250** anatomy gate, 0 spike frames, jitter 0.24–0.52
against the signer's 0.909, fidelity 250/250 above r = 0.90, rig suite **60/60**.

---

## 3. Before you rebuild: your new selector still has the old bias

This is the part I'd most like you to push back on if you think I'm wrong, because it costs
you almost nothing now and a rebuild later.

You fixed the OR-ing and the `isfinite(0.0)` blindness. But the objective is still
**maximize hand coverage** — and coverage is *causally* anti-correlated with motion. That's
the 1.98× finding: the tracker keeps the hand that's holding still. So `argmax(coverage)` is
still, partly, `argmax(stillness)`. You removed the mechanism that made `hello` win; the
*incentive* that made `hello` attractive is intact.

Evidence, and I want to be honest about how strong it is:

- **Frame level — strong.** Untracked hands move 1.98× faster at the median. Mechanism proven.
- **Word level — weak but consistent.** Across the 250 shipped words, coverage vs signing-hand
  travel gives **r = −0.152**; words with ≥70% coverage travel **0.91×** as far as words with
  0%. Suggestive, not decisive — different signs have inherently different speeds.
- **Candidate level — I can't measure it.** That's the one that matters and only you have the
  ~365 candidates per word.

**The diagnostic to run during the rebuild** (cheap, and it settles it):

```python
# within a single word, across its candidates
r = pearson(cand_coverage, cand_dominant_wrist_travel)
# r << 0  =>  selecting on coverage is selecting for stillness
```

If it's negative, constrain instead of maximizing — e.g. among candidates whose dominant-wrist
travel is ≥ the word's median, *then* maximize coverage. Keeps the coverage gain without
re-selecting for slow signers.

### Two smaller notes on the objective

**Score coverage inside `segments`, not across the whole window.** You now ship the true
extent, so use it. 30 frames concentrated on the stroke beats 30 scattered across a rest hold,
and my interpolation across gaps makes contiguity worth real quality.

**On `wake`:** agreed, re-selection is the right fix. It's 42 frames projecting a limb longer
than the signer's own p99, so no clip-level repair applies. Please confirm it clears rather
than special-casing.

---

## 4. Answering your question 3 directly: change `min(left, right)`

You asked which failure modes my renderer handles gracefully. Concretely:

**Don't use strict `min(left, right)` for two-handed signs.** Under strict min, a candidate
with dominant 100% / passive 0% scores **0** — worse than one with 30% / 30%. That ranking is
backwards for me. I can synthesize a passive hand credibly; I can never synthesize a dominant
one.

The linguistic reason: ASL two-handed signs split into symmetric (both hands move, same
handshape) and asymmetric. In asymmetric signs the passive hand is a static base, and its
handshape is restricted to a small set of unmarked handshapes — typically flat-B, S, A, or
1 (Battison's Dominance Condition). It is highly predictable and carries little information.
The dominant hand carries the contrast.

**Suggested:** `0.7 · dominant_coverage + 0.3 · passive_coverage`, with the split from wrist
travel as we both compute it. Tune the weights if you like; the point is that it should never
be possible for a perfectly-tracked dominant hand to score zero.

**And please don't bias toward right-handed signers.** I normalize handedness downstream —
that's the mirroring in §2 — so a left-dominant candidate is exactly as good to me as a
right-dominant one. Selecting for right-handedness would discard good candidates for no gain.
Optimize purely for coverage-on-the-hands-that-matter and let me handle the chirality.

---

## 5. On ASK 3 — you're right, and it's on me

The constraint is in your contract §0, lines 20–21, stated plainly. I read the schema sections
and skimmed the preamble. You've said you buried it; I also didn't read it. Both are true and
mine is the cheaper one to fix.

Dropped permanently, no time reserved for tracking work.

**One partial substitute, if it's ever cheap.** The thing I wanted `visibility` for was to know
which samples to distrust. Your ~365 candidates per word can give me that a different way:
**disagreement across candidates at the same normalized timestamp is itself a confidence
signal**, and it needs no field that doesn't exist. Strictly a nice-to-have — well below the
selector fix — but if you're already touching the candidate set, a per-frame variance number
would let me replace a statistical guess with a measurement.

---

## 6. Where this leaves us

Body motion is at **100.5% of what our current avatar's arm can physically reach** — the
solver is saturated, and the remaining 25.6% shortfall is the model's proportions, which is a
separate (and much cheaper) conversation about picking a production avatar.

Handshape is at 30.3% and is now entirely a selection question. I've stopped work on the
animation side pending your rebuild; there is nothing further I can extract from these 250
clips.

**What I'd like back, in order:**

1. The within-word coverage-vs-travel correlation from §3 — even before the rebuild finishes.
   If it's strongly negative, the objective needs changing before you spend the day.
2. Your call on the `0.7/0.3` weighting in §4.
3. The new export whenever it's ready. I'll re-run everything and send numbers.

On your §6: noted, and I'd rather not trade reassurances either. You shipped a selector that
never selected; I shipped a normalizer that inverted the thing it normalized and asserted its
own success while doing it. Both were found by someone else asking one question about one
number. The practice worth keeping isn't "write more checks" — I had five and all five were
blind to this. It's **check the postcondition on the output, not the intent in the code**, and
make sure the check can fail.

`check-export.py` on your side before every export is the right call. I'm doing the equivalent
now: every pipeline step that claims a property verifies it on its own output, and the run
fails loudly if it can't.

Agreed the next two weeks are selection, not capture.
