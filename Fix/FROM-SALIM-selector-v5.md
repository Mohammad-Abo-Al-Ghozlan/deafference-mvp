# Re: selector objective — all three changes in, and two things back at you

**To:** animation / retargeting side
**From:** Mohammad Salim (data pipeline)
**Re:** `REPLY-TO-SALIM-v4.md`
**Date:** 2026-08-11

---

## 0. Short version

| | |
|---|---|
| ✅ **§4** — drop strict `min`, use `0.7·dom + 0.3·passive` | **Done.** Adopted your weights unchanged |
| ✅ **§3** — score coverage inside `segments` | **Done** |
| ✅ **§3** — within-word coverage-vs-travel diagnostic | **Built.** Runs automatically; needs the corpus to produce a number |
| ✅ **§4** — no chirality bias | **Confirmed and unit-tested.** There never was one |
| 🔴 **Your `check-export.py` still uses strict `min`** | Please fix, or we'll disagree again — §2 |
| ⚠️ **The one/two-handed split is worse than either of us assumed** | 123 of 194 — §3 |

Your §3 argument was right and I'm not going to pretend otherwise: I fixed the *mechanism*
that made `hello` win and left the *incentive* intact. `argmax(coverage)` is still partly
`argmax(stillness)` for exactly the causal reason you gave.

---

## 1. What changed

**Two-handed scoring is now `0.7·dominant + 0.3·passive`.** Your ranking argument is
straightforwardly correct and the unit test now pins it:

```
dominant 100% / passive   0%  ->  score 0.700
dominant  30% / passive  30%  ->  score 0.300
strict min would have given       0.000   and   0.300     <- backwards
```

Battison's Dominance Condition is the right justification and I've cited it in the code so the
next person doesn't "simplify" it back to `min`.

**Coverage is scored inside the sign extent.** Test case: a clip tracked only in its last 20
frames, moving only in its first 30. Whole-window coverage reads 0.333; inside the extent it
reads 0.000. The inflation is gone.

**The diagnostic is wired in and prints every run**, per-word Pearson r between candidate
coverage and candidate dominant-wrist travel, plus mean / median / %-negative. It also runs
*both* selection strategies every time and reports what the other one would have given, so the
choice stays measured rather than argued:

```
DIAGNOSTIC — within a word, is coverage anti-correlated with motion?
  pearson r over N words : mean ...  median ...
  words with r < 0       : ...%
  verdict                : STRONG / MILD / ABSENT
```

**And I implemented your fallback ahead of the answer** — `--travel-floor median` restricts to
candidates whose dominant-wrist travel is at or above that word's median, *then* maximizes
coverage. It defaults to on. Verified against a synthetic word built to be the exact trap:

```
c0: travel 0.20  coverage 1.00   <- stillest AND best-covered: the trap
c1: travel 1.00  coverage 0.60
c2: travel 1.10  coverage 0.55
c3: travel 1.20  coverage 0.50

--travel-floor none   -> c0    (reproduces the trap)
--travel-floor median -> c2    (excluded it, still maximized coverage)
within-word r = -1.000
```

**I cannot answer your §3 question yet.** It needs the ~365 candidates per word, and our
corpus restore isn't finished. The harness will print it the moment the rebuild runs, and it
goes to you before the export does — as you asked, so the objective can change before the day
is spent rather than after.

---

## 2. 🔴 Your `check-export.py` still uses strict `min`

`check-export.py` line 103:

```python
worst = min(cov['L'], cov['R'])
if worst == 0: missing_required.append((w, 'two-handed, one hand absent'))
```

So if I optimize `0.7/0.3` and you accept on `min`, **a two-handed clip with a perfectly
tracked dominant hand and an absent passive hand scores 0.70 for me and MISSING for you.** We
would be back to optimizing and measuring different numbers — the same class of mismatch as
the zeros.

Since the metric is your call, you should own the change. Suggested:

```python
score = 0.70 * cov[dom] + 0.30 * cov[oth]
# and drop the `worst == 0` gate for two-handed words, or re-express it on the
# dominant hand only: if cov[dom] == 0
```

I'd rather you make it and send the script back than have me patch your acceptance criteria.

---

## 3. ⚠️ The one/two-handed split is shakier than either of us assumed

This came out of implementing your §4 and I think it's the biggest open item now.

**Wrist-travel ratio cannot distinguish a one-handed sign from an ASYMMETRIC two-handed sign.**
In both, one hand barely moves. But in the asymmetric case that static hand is a phonemically
required *base* — it just doesn't travel. Both our classifiers put it in the one-handed bucket
and score it on the dominant hand alone, so its handshape is never required and never counted.

A rough test: is the passive wrist *hanging* (below the shoulder→hip midpoint) or *held up in
signing space*? On the 250 clips we shipped:

```
one-handed words                     194
  passive hand hanging down            71
  passive hand held UP in signing space  123    <- likely asymmetric two-handed
two-handed (ratio >= 0.70)            56
```

**Caveats, stated plainly:** this is a crude y-position threshold, it is unvalidated, and 123
of 194 is high enough that I distrust it as a point estimate. It is also measured on 250
arbitrarily-selected clips, which is a biased sample. I have wired it in as a **reported field
only** — `passive_resting` in the meta — and it does **not** affect scoring. I'm not changing
the classification on the strength of a heuristic I can't check.

But if even half of it holds, our "195 one-handed" is substantially wrong, and the honest
number of words needing two good hands is well above 55. That makes the target *harder*, not
easier, so I'd rather surface it now than discover it after a rebuild.

**What would settle it:** you have the retargeted output and can see whether the passive hand
is doing anything structural. If you can classify even 30 of those 123 by eye, that calibrates
the threshold and I'll fold it into the classifier properly.

---

## 4. Something that makes your §4 argument stronger

For **symmetric** two-handed signs, `0.7/0.3` may be more conservative than it needs to be.

Under Battison's Symmetry Condition, symmetric two-handed signs have **the same handshape on
both hands**. So a well-tracked dominant hand doesn't just make the passive hand *guessable* —
it determines it exactly, by mirroring. No synthesis, no unmarked-handshape assumption.

If that's true in your renderer, symmetric signs need only **one** good hand and could score
`max(L, R)` rather than a weighted blend — which would let the selector reach for candidates it
currently discounts. Asymmetric signs keep `0.7/0.3`, since there the passive handshape is a
different (if predictable) shape.

Convenient accident of the current threshold: `ratio >= 0.70` means both hands travel similarly,
which is close to the definition of symmetric. So the two-handed bucket is *mostly* symmetric
already, and the asymmetric ones are hiding in the one-handed bucket per §3. Fixing §3 and this
are the same piece of work.

**Your call** — you know whether mirroring the dominant hand onto the passive one reads
correctly on the avatar. If it does, tell me and I'll use `max` for that bucket.

---

## 5. On your §2

For what it's worth: a normalizer that inverted the thing it normalized, justified in a comment,
verified by five checks that were all invariant to the failure — that's a harder bug than mine.
Mine was a wrong function; yours was a right function fed the wrong input by a flag that
existed to be clever. And 27 → 5 words signed with the correct hand is a bigger visible
improvement than anything I shipped this week.

`check the postcondition on the output, not the intent in the code` — taken. `build_sign_clips.py`
now asserts its own postconditions and prints what the *alternative* strategy would have given,
so it can't quietly report success.

---

## 6. What's next, in your order

1. **The within-word correlation** — first thing out of the rebuild, before the export
2. **The `0.7/0.3` weighting** — adopted as-is; awaiting your call on `max` for symmetric (§4)
3. **The new export** — after 1

Blocked only on the corpus restore. Then: rebuild → correlation to you → your call on the
objective → export → your re-run.

Two asks back:
- **§2** — update `check-export.py` to the metric you asked me to optimize
- **§3** — eyeball 30 of the 123 so we can calibrate the asymmetric detector
