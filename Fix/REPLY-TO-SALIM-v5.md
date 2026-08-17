# Re: selector objective — metric fixed, and I calibrated your §3 instead of eyeballing it

**To:** Mohammad Salim
**From:** animation / retargeting
**Attached:** `check-export.py` (updated), `handedness-analysis.csv`, `asymmetric-detect.py`,
`handedness-groundtruth.py`, `symmetry-test.py`

---

## 0. Short version

| | |
|---|---|
| ✅ **Your §2** — `check-export.py` used strict `min` | **Fixed. You were right.** Metric now matches your objective — §1 |
| ✅ **Your §3** — asymmetric signs hide in the one-handed bucket | **Confirmed, and calibrated.** Your concern is real; your estimate is ~4× high — §2 |
| 🔴 **Your §3** — the 250 clips can't calibrate it | **They don't show their own signs.** 14 of 20 unambiguous two-handed signs don't — §3 |
| ⚠️ **Your §4** — `max(L,R)` for symmetric | **Reasoning sound, data can't test it, don't adopt yet** — §4 |

Headline: **your §3 instinct was right and your number was wrong in the safe direction.** The
travel-ratio split does miss asymmetric signs — 6 of 8 in my labelled set. But the height test
runs at precision 0.27, so of your 123 roughly 33 are real, not 123.

---

## 1. `check-export.py` fixed — you were right, and it was the same class of bug

You caught it exactly. I asked you to optimize `0.7·dom + 0.3·passive` while my acceptance
criterion still used strict `min` — so a clip with a perfect dominant hand and an absent
passive hand scored 0.70 for you and MISSING for me. Same shape as the zeros: two systems
optimizing and measuring different numbers.

Changed:

```python
W_DOM, W_PAS = 0.70, 0.30          # MUST match the selector's objective
req_cov += W_DOM * cov[dom] + W_PAS * cov[oth]
if   cov[dom] == 0: missing_required.append(...)   # unrecoverable
elif cov[oth] == 0: degraded.append(...)           # synthesizable, reported not failed
```

MISSING is now reserved for an absent **dominant** hand. An absent passive hand is reported
separately as `degraded`. On your v4 export:

```
  [FAIL] required-hand coverage >= 70%          28.5%   (0.70*dom + 0.30*passive)
  [FAIL] words missing the DOMINANT hand == 0   137 words
  [FAIL] two-handed words missing the passive   27 words (degraded, not fatal)
```

**164 = 137 fatal + 27 degraded.** Which also closes out the 137-vs-164-vs-165 thread from
two rounds ago: 137 was always the right answer to "dominant hand absent", 164 to "strict min",
and the taxonomy was the thing missing, not the arithmetic. Re-verified against a synthetic
clean export — still exits 0, so the criteria can still pass.

---

## 2. Your §3 is real — here is the calibration, instead of 30 eyeballs

Eyeballing 30 clips gives 30 labels and no error bars. Instead I labelled **96 signs by their
known citation form**, ran both classifiers against them, and measured. Script attached so you
can disagree with individual labels.

**Caveat first, because it matters:** those labels are my reading of ASL citation forms, not a
Deaf reviewer's. Several signs have documented two-handed variants, and this is children's
vocabulary where caretaker signing varies more than citation form. Treat it as a calibration
prior, not ground truth.

### Your structural claim is correct

```
             called one-handed   called two-handed
  ONE  (64)        54                  10
  SYM  (20)        14                   6
  ASYM  (8)         6                   2
```

**6 of 8 asymmetric signs land in the one-handed bucket** — `tree`, `table`, `mitten`,
`napkin`, `helicopter`, `toy`. That's structural, not noise: the passive hand is static *by
definition*, so a motion-based test cannot see it. You were right to flag it.

### But the height test is far too loose

Scored on the labelled signs the ratio called one-handed:

```
  correctly flagged two-handed :  14
  missed                       :   6
  ONE-handed wrongly flagged   :  37     <-- precision 0.27, recall 0.70
```

It flags `bird`, `cat`, `dad`, `mom`, `hat`, `hair`, `ear`, `mouth`, `drink`, `milk` — all
unambiguously one-handed. Signers park the non-signing hand mid-torso constantly; height alone
can't distinguish a parked hand from a base hand.

**So: of your 123, roughly 33 are genuinely two-handed** — and since my labelled set is
enriched for two-handed signs, 0.27 is an *optimistic* precision and 33 is an upper bound.
Corrected split ≈ **160 one-handed / 90 two-handed**, not 71/179. Still materially worse than
195/55, so the target does get harder — just not as much as you feared.

### I tried to build you a better detector and it failed

The linguistically right discriminator isn't height, it's *relation*: in an asymmetric sign
the dominant hand acts **on** the passive hand, which is a place of articulation. So I measured
closest approach, median separation, and whether the dominant hand sits nearer the passive hand
than the face. Result:

```
  minDist       TWO median 1.365   ONE median 1.349   separation 0.016
  medDist       TWO median 1.686   ONE median 1.715   separation 0.029
  dToPassive    TWO median 1.685   ONE median 1.713   separation 0.029
```

**Essentially zero separation.** Best single-feature rule reaches F1 0.51. Reporting the
negative result rather than shipping a detector that looks principled and isn't — §3 explains
why it failed, and it isn't the detector's fault.

---

## 3. 🔴 The bigger finding: these clips don't show their own signs

This is why no classifier works on them, and I think it outranks the rest.

**14 of 20 symmetric two-handed signs landed in the one-handed bucket.** For asymmetric signs
that's expected. For symmetric signs it is not possible — both hands move, by definition. So
the clip isn't showing the sign.

Measured directly, both wrists tracked in all 64 frames, so this isn't a tracking artifact:

| sign | travel L | travel R | ratio | should be |
|---|---|---|---|---|
| `owl` | 3.31 | 12.35 | 0.27 | ≈1.0 — both hands at both eyes |
| `stairs` | 1.01 | 4.97 | 0.20 | ≈1.0 — hands alternate climbing |
| `tiger` | 1.93 | 6.99 | 0.28 | ≈1.0 — both hands claw across the face |
| `alligator` | 4.76 | 8.87 | 0.54 | ≈1.0 — both arms, jaws |

And 8 clips contradict their own sign outright, including `alligator` and `book` whose hands
never come within 1.3 shoulder-widths, and `cat`/`eye`/`mouse` — one-handed signs — showing
both hands equally active.

`hello` was not an isolated bad take. It was the first symptom of a systematically arbitrary
draw, and structural validity was damaged alongside coverage.

**What this means for sequencing:** the asymmetric detector can't be calibrated on these 250
clips, because the clips don't reliably show their own structure. Calibrate it *after*
re-selection, on the new exemplars. I'd rather tell you that now than have you build a
classifier against a corrupted reference.

---

## 4. Your §4 — sound reasoning, but the data can't test it. Don't adopt yet.

Your Symmetry Condition argument is right: in a symmetric two-handed sign both hands carry the
same handshape, so the passive hand is *determined* by the dominant one, not merely guessable.
If it holds, `max(L,R)` is the correct objective for that bucket.

I tried to confirm it empirically — in landmark space, no rig assumptions: for frames where
both hands are tracked, mirror the dominant handshape and measure the distance to the real
passive hand, against a relaxed-substitute baseline and a shuffled control.

The first result looked decisive and negative — mirroring scored *worse* than the relaxed
baseline and identical to the shuffled control. Then I checked what it was actually measuring:

```
paired frames (both hands tracked) by sign class:
  ONE-handed signs      33 frames   (mouth, white, lips, drink)
  SYMMETRIC two-handed   3 frames   (jeans)
  ASYMMETRIC             0 frames
  unlabelled            84 frames
```

**Three frames.** The test was almost entirely one-handed signs where the "passive" hand is
genuinely resting — so of course a relaxed pose predicts it better than a mirrored handshape.
The result says nothing about your hypothesis.

So the honest answer is **not** "mirroring doesn't work". It's **the corpus contains almost no
frames where a symmetric two-handed sign has both hands visible at once** — the same root
cause again.

**My recommendation: keep `0.7/0.3`, don't adopt `max` yet.** Two reasons:

1. `max(L,R)` is only as safe as the symmetric-vs-asymmetric classifier, and §2 shows that
   classifier is currently unreliable. Misclassify an asymmetric sign as symmetric and `max`
   accepts a clip missing the passive hand — where the passive handshape is a *different*
   shape that mirroring cannot produce. `0.7/0.3` degrades gracefully under the same error.
2. The practical gain is small. For dom=1.0/pas=0.0 the two rules give 0.70 vs 1.00; both
   already rank it above a 0.3/0.3 candidate. It only changes ranking between "dominant-only"
   and "both-partial" candidates.

Asymmetric risk is real and the upside is marginal, so not yet. `symmetry-test.py` is attached
and will answer it in one run once re-selection gives us paired frames — I'd expect the new
exemplars to produce them in quantity, since selecting for dominant-hand coverage should pull
in clips where both hands are visible.

---

## 5. Where that leaves the plan

Unchanged in shape, one addition:

1. **Corpus restore → rebuild** with `0.7/0.3`, extent-scoped coverage, `--travel-floor median`
2. **Within-word correlation** to me before the export — still the number that could change the
   objective
3. **Then**, on the new exemplars: re-run `handedness-groundtruth.py` and `symmetry-test.py`.
   Both are one command and both are currently unanswerable. That decides `max` vs `0.7/0.3`
   and calibrates the asymmetric detector properly.
4. **Deaf review** — and please put the §3 suspect list in front of them first. If `owl` and
   `stairs` are representative, exemplar validity is a bigger quality problem than handshape
   coverage, and it's invisible to every automated check either of us has.

Your `--travel-floor median` synthetic test is the right shape — building the trap deliberately
and confirming the guard excludes it is stronger than asserting the guard works. The `c0`
candidate with travel 0.20 and coverage 1.00 is exactly the `hello` failure in miniature.

One thing I'd add to it: print what the *unguarded* rule would have picked in the real run too,
not just the synthetic. If the floor is excluding the argmax on most words, that's the
within-word correlation showing up in production, and it's worth seeing without waiting for the
diagnostic.

On your §5 — appreciated, but I'd rather not settle into taking turns being generous about each
other's bugs. The useful shared conclusion is narrower: both failures were *silent success
reports*. Yours printed `250/250 clean` from a warning that couldn't fire; mine wrote
`dominantHand = 'right'` and never tested it. Neither was found by a check. Both were found by
the other person asking about one number that looked odd.
