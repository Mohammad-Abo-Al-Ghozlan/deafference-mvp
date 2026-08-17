# Re: v8 — the export is FINAL, your 2.13 s warning found ours, and one bug in `retarget.mjs`

**To:** animation / retargeting
**From:** Mohammad Salim
**Date:** 2026-08-14
**Attached:** corrected `animation_handoff/` (now with `sourceQuality`), `sign_clips_250.meta.json`,
`asl_handedness_250.json`, `handshape_templates.json`, `docs/SIGN_ANIMATION_CONTRACT.md`,
`Fix/FROM-SALIM-v7.md` (one number corrected — see §5)

---

## 0. Read this first: the export is FINAL. Stop hedging against a re-export.

You have been building against a target that was still moving. It stopped yesterday.

The recognition track is **closed**. We tested the last open lever — rebuilding the whole training
corpus so every signer's signing hand lands in one canonical block — and it was **refuted**. Mean
change on the three signers it was designed to rescue: **−0.0064**. On the four signers it was not
aimed at: **−0.0067**. Identical. The one signer the entire theory existed for moved **−0.0002**.

**What that means for you: no new corpus, no re-export, no new `sign_clips_250.npz`.** The 250
files attached are the ones that ship.

**What it does NOT mean — and this is the part worth being careful about.** Two separate claims
were on trial and only one died:

| claim | verdict |
|---|---|
| *"Canonicalising the corpus raises recognition accuracy"* | **dead** |
| *"The geometric rule identifies the correct signing hand"* | **alive, verified by direct measurement** |

The second one is the one your work depends on, and it was never in doubt: the export went from
**137 of 250 words rendering the resting hand** to **1** (`finish`), and signing/resting coverage
from 28.8%/51.5% to **76.2%/0.1%**. That is a count of hands, not an accuracy proxy — it cannot be
wrong in the way an accuracy number can. If you hear "the handedness work was refuted," it refers
to a model-accuracy experiment that has nothing to do with which hand you animate.

---

### 0.1 Your three post-export checks, answered — and **do not re-run the pipeline**

You said you'd want to check three things when the export landed. It has landed, and the headline
is: **every `frames` array is byte-identical to the copy you already processed — all 250 of them.**
I diffed it rather than asserting it. No landmark has moved, so nothing in your solver, your
anatomy gate or your rig suite can change value.

What did change is **one additive metadata key** plus documents:

```
  NEW      animation_handoff/words/*.json   segments[].synthesis.quality  (250 files, ADDITIVE)
  NEW      asl_2a_base_placement.json       the 2a base positions - §3
  NEW      Fix/REPLY-TO-GHOZLAN-v9.md       this letter
  NEW      docs/AVATAR_LIMITS.md            what this system cannot do, measured
  changed  Fix/FROM-SALIM-v7.md             one word corrected (§5)
  changed  handshape_templates.json         two notes added; the templates themselves untouched
```

**`quality` is the one you want**, because it is what makes §1.5 below actionable:

```json
"quality": {"tier": "C", "gaps": 3, "longestGapFrames": 51,
            "holdableFrames": 1, "relaxFrames": 74}
```

`tier` is A/B/C on dominant-hand coverage (A 147, B 64, C 39 across the 250) so you can down-rank
or skip the weak ones. The gap fields are per-word run structure, split into gaps short enough to
hold through versus long enough that relaxing is genuinely right.

Your checks, run on the bundle so you don't have to:

| your check | answer |
|---|---|
| `dominantHand` still `"R"` on all 250? | **Yes — 250/250 `R`.** Unchanged. |
| Did durations move? | **No.** `nativeFrames` 9 / 41 / 116 (min/median/max), `nativeFps` 30 on all 250 — identical to what you have. |
| Did the `synthesis` block shape change? | **No.** Three key-sets, by class: 163 one-handed, 52 with `passiveHand` + `passiveWristIndex`, 35 also with `passiveHandshape`. `sourceQuality` is present on all 250 and was already present in your copy. |

So: **nothing to re-run, and your "same zip, nothing to re-run" instinct is right again.** The
value in this one is §2 — a bug in your `retarget.mjs` — and §3, which moves the numbers on the
contact problem you just flagged.

The one caveat worth naming, given you now read `synthesis` directly rather than joining against
the lexicon: the key-set is **not uniform across the 250** — it varies by handedness class, as the
table above shows. That was already true in your copy, so nothing has broken; but a parser that
assumes a fixed key-set will trip on it, and `passiveHandshape` exists on the 35 `2a` words only.

---

## 1. Your 2.13 s warning was right, and it found a live bug on our side

You wrote:

> *Anything calibrated when every clip was 2.13 s needs re-checking — leads, smoothing windows,
> minimum-duration assumptions. [...] I'd guess a captions or playback layer has a similar
> constant.*

Ours was `DEFAULT_TRANSITION = 8` in `gloss_to_motion.py`, the eased blend `stitch()` inserts
**between** consecutive signs. At 64 frames that is 12% of a clip and invisible — exactly your
case. With native durations it is not:

```
              sign span   blend frames    blend as % of the word's span
  tiger          9f       8 + 8 = 16      16/25  =  64%      <-- was
  tiger          9f       1 + 1 =  2       2/11  =  18%      <-- now
  puppy        116f       8 + 8 = 16      16/132 =  12%      (unchanged)
```

Nothing raised. `tiger` was a 9-frame sign inside 16 frames of morph — the same failure you had,
in a different layer, and I would not have gone looking without your paragraph.

Fixed with the same shape as yours, `min(cap, 15% of the shorter of the two clips)`:

```python
def blend_len(cap: int, a_len: int, b_len: int) -> int:
    if cap <= 0:
        return 0
    return max(1, min(cap, round(0.15 * min(a_len, b_len))))
```

It returns `cap` unchanged for any pair of clips ≥ ~53 frames, so it is a **no-op on everything
that was already fine** and only bites on the short clips. `--transition 0` still disables
blending. One fix covers all five entry points — `gloss_to_motion.py`, `preview_signs.py`,
`demo_speech_to_sign.py`, `demo_voice_gui.py`, `demo_voice_to_sign.py` — because they all route
through `stitch()`.

**This does not change the files you receive.** Per-word JSONs contain single signs with no
transitions; the blend only exists when we stitch a sentence. Flagging it because your warning
generalises: the pattern is *"a constant that was a small fraction of 64 and is a large fraction
of 9,"* and it is worth one grep in any layer either of us still has.

---

## 1.5 🔴 The relax branch is a third instance of the same pattern — and this one costs the most

Your lead-in was calibrated on 2.13 s clips. Our `DEFAULT_TRANSITION` was calibrated on 64-frame
clips. **Your relax branch at line 1081 was calibrated on the BROKEN export**, and it is the
biggest of the three because it touches all 250 words rather than 35.

Its comment says *"165 of 250 words have ZERO hand-block frames on the hand that signs."* That was
true of the export you had when you wrote it. It is not true now — the corrected export has the
dominant hand on 76.3% of frames — and the gap structure that replaced it is a different problem
with a different right answer:

```
dominant hand missing on 2595 of 10956 frames (23.7%), in 776 gaps
  751 of 776 gaps are INTERIOR (mid-sign, not at a clip edge)
  550 of 776 gaps are 1-3 frames         =  70.9%
  1177 missing frames sit in gaps <= 4 frames  =  45.4% of all missing frames
```

A 1–3 frame gap at 30 fps is 33–100 ms. **The hand did not go anywhere — the tracker lost it.**
Relaxing there makes the handshape visibly collapse and re-form, and it happens **550 times across
the vocabulary**. Contract §6 already says a null landmark is for the renderer to hold or
interpolate; this is that case.

Long gaps are a genuinely different thing and relaxing IS right there — `bath` has a 51-frame
(1.70 s) hole, and holding a handshape across 1.7 s would be worse than admitting the hand is
gone. So it needs to be a threshold, not a global switch.

**Suggested:** hold the last solved handshape across gaps of ≤4 frames, relax beyond that. The new
`quality` block gives you the split per word without recomputing it — `holdableFrames` is what a
hold recovers, `relaxFrames` is what it cannot. Corpus-wide that is **1177 frames recovered**.

I am not certain 4 is the right threshold — it is where the run-length distribution flattens, not
a perceptual result. If it looks wrong at 4, the data supports anything from 3 to 8.

---

## 2. 🔴 A bug in `retarget.mjs`: the 2a branch has no side guard

This is the highest-value item in this letter. I verified it two independent ways before writing it
down, because an unverified bug report in your own code is worse than none.

**The code.** Your 2s branch at line 990 is guarded on the *other* side having data:

```js
if (!H && HANDCLASS === '2s' && e[other(s)].hpts && PALM[s]){        // line 990
```

Your 2a branch at line 1042 is not:

```js
else if (!H && HANDCLASS === '2a' && TPL && PASSIVE_SHAPE && PALM[s]){   // line 1042
```

`!H` means *"this side has no hand block."* On a 2a word, that is true of the passive side on every
frame — correct, that is the branch's purpose. But it is **also true of the dominant side on any
frame where the dominant hand was not tracked**, and nothing in the condition distinguishes the
two. So on those frames the **dominant** hand is given the **passive** base handshape.

The 2s branch is immune precisely because of `e[other(s)].hpts`: when the dominant hand is missing,
the passive side has no data either, the guard fails, and both sides fall through to the relax
branch at 1081. That is the right behaviour, and it is the guard 2a is missing.

**The measurement.** From the attached export, dominant-hand block present per frame:

```
class   words   frames   dominant MISSING
  1      163     7400      797   (10.8%)   -> falls to relax at 1081, correct
  2s      52     2182     1132   (51.9%)   -> guarded, correct
  2a      35     1374      666   (48.5%)   <-- templated on the DOMINANT hand
```

**666 of 1374 frame-sides across all 35 asymmetric words.** Worst affected — these are where a
viewer would see it:

```
  arm         18.2% of frames have the dominant hand   (18 of 22 frames affected)
  chocolate   22.2%                                    (42 of 54)
  hide        25.6%                                    (32 of 43)
  night       28.6%                                    (30 of 42)
  jump        31.6%                                    (13 of 19)
  into        32.0%                                    (17 of 25)
  ride        33.3%                                    (20 of 30)
```

**A falsifiable check you can run in one line**, using the counter you already print at line 1520.
Across the 35 2a words, `report.templateHands` summed should be **1374** (passive side, one per
frame). If it sums to about **2040**, the dominant side is being templated on 666 frames. You
found your `Pinky`/`Little` bug because a counter read zero when it should have read 35 — this is
the same instrument pointed at the same class of failure, and it distinguishes the two states
without needing to look at a render.

**The patch.** `DOMINANT` is already in scope at line 567:

```js
const DOM_SIDE = DOMINANT === 'L' ? 'left' : DOMINANT === 'R' ? 'right' : null;
// ...
else if (!H && HANDCLASS === '2a' && TPL && PASSIVE_SHAPE && PALM[s]
         && DOM_SIDE && s !== DOM_SIDE){
```

The dominant side then falls through to the relax branch at 1081, which is correct: an untracked
hand should be relaxed, never given a handshape belonging to the other hand. (`dominantHand` is
`'R'` in all 250 by construction, so in practice this means the template may only ever touch the
left hand — but keep it expressed via `DOMINANT` rather than hard-coding `'left'`.)

**One thing to check after the fix — it may contaminate your §3.** Your read-back scored the
rendered hand against all seven templates and got 23% nearest-of-7 with a ~0.150 error floor,
every mis-assignment B→C. If any of the frames you sampled were dominant-hand frames that this bug
had also templated, then the 0.150 and the 23% are measuring a mixture of two different hands. I
am not claiming they are — that depends on which frames `template-check.mjs` samples, which you
know and I don't. Worth re-running it after the guard lands: if the floor drops, the ceiling you
described is lower than you thought.

---

## 3. Your 2a contact problem: confirmed, **larger** than you measured, and your diagnosis is wrong

You ranked this above handshape fidelity. I agree, and after measuring it I agree more strongly
than you did.

I measured the passive wrist against the dominant wrist across all 35 2a words, per frame, median
per word. `|L11−L12|` is normalised to exactly 1.0000 in every clip, so I report shoulder widths
and convert at 40 cm biacromial — **if you used a different cm-per-shoulder constant, our absolute
numbers will differ and the shoulder-width figures are the ones to compare.**

**① The gap is bigger than 45–55 cm.**

```
passive-wrist -> dominant-wrist gap, median per word, n=35
  median 1.56 shoulder widths  (62.4 cm at 40 cm/shoulder)
  range  0.80 - 2.22 sh.w.     (31.8 - 88.9 cm)
  inside your 45-55cm band :  1 / 35
  above 40cm              : 34 / 35
```

Your 45–55 cm was, if anything, generous. `beside` is 88.9 cm; `read` is 72.0; `chocolate` 66.8.

**② But the passive arm is NOT hanging.** This is where your diagnosis breaks, and it is robust to
the cm constant because it is a ratio:

```
passive wrist relative to its OWN shoulder (+ve = below), n=35
  median  +0.34 sh.w.        raised above the shoulder :  4 / 35
  range   -0.41 to +0.68     0 - 0.75 sh.w. below      : 31 / 35
                             more than 0.75 below      :  0 / 35
```

A hanging arm puts the wrist roughly **1.1–1.3 shoulder widths** below the shoulder — upper arm
plus forearm. Nothing in this corpus is even close. **The passive arm is up, at chest-to-waist
height, in a posture a signer could plausibly hold.** The 62 cm is almost entirely *lateral*: the
arm is raised but on its own side of the body, not brought across to where the dominant hand is
working.

**③ Which kills the contact filter you asked for.** If the criterion is "passive wrist near enough
to the dominant hand to be a base," the tightest word in the vocabulary is `every` at 0.80 sh.w.
(31.8 cm) — still most of a forearm away. **A contact filter strands 35 of 35 words.** There is no
threshold that keeps any of them, so it cannot ship, and that is not a tuning problem.

**④ What the fix has to be, and it is attached.** The recorded passive wrist has to be **ignored**
for 2a words and the base placed **synthetically, relative to the dominant hand**. That file now
exists: **`asl_2a_base_placement.json`**, all 35 words.

Rather than a fixed body-space point, each entry anchors to the dominant hand's own trajectory and
then holds still — so it adapts to how high a given signer works, while still being a static base:

```
1. reduce the dominant WRIST track to one point using `anchor`
   (dominant_median | dominant_lowest | dominant_first | dominant_last)
2. base wrist = anchor + `offset`      (shoulder widths, same axes as the export)
3. hold that position STATIC for the whole clip
4. orient with `palm` + `fingers`, then apply the handshape from handshape_templates.json
5. ignore `passiveWristIndex` for these 35 words - it is the thing being replaced
```

Two honest caveats. **It is hearing-authored from phonology and unvalidated against video** —
same standing as the template anchor words, 22 high confidence / 11 medium / 2 low, and a
reviewer's disagreement is a lexicon fix not a rig bug. And **6 of the 35 are not
handshape-at-a-point problems at all**: `arm`, `table`, `tree`, `flag` and `morning` act on the
passive *forearm*, `time` targets the *wrist*. They carry `kind: forearm|wrist` so they are not
mistaken for solved — a posed limb is not something this schema can express, and those will look
approximate however good the handshape is.

**Why the recorded wrist is wrong at all** — worth stating because it explains why no filter can
rescue it: GISLR recorded **one hand per participant** for an isolated-sign task. For a two-handed
asymmetric sign there was no reason for the signer to form the base at all, and mostly they did
not. The passive arm in these takes is not a badly-placed base; it is an arm doing nothing in
particular. There is no signal to filter for.

So: **you were right to rank this first, and right that correct-shape-wrong-place is still wrong.
The blocker is on my side, it is a lexicon deliverable, and it is 35 words.** Nothing for you to
change until it lands.

---

## 3.5 Your §3: the conclusion holds and is understated. The argument behind it does not.

I did not want to take "the metric can't resolve it" on trust, so it got reproduced from scratch —
your rig and all 250 clips pulled out of the base64 in `avatar-player.html` (lines 3925–3926),
`template-check.mjs` reimplemented independently. **Your numbers reproduce exactly: 8/35, err
0.150, err_worst 0.606.** So the measurement is sound and faithfully reported.

**Your conclusion is right and you undersold it.** Re-scored in **bone-direction space — the
quantity your retargeter actually solves for** — the rendered 2a hand reproduces the requested
template to **0.00 degrees** on all 10 measurable segments for B, C, `1` and A:

```
mean direction error   B 0.00   C 0.00   1 0.00   A 0.00   S 6.59 deg
                       (S: Ring 14-15 clamped at 51.2, Little 18-19 at 14.7)
nearest-in-direction   5/5 shapes = 35/35 words
negative control       rig rest hand -> 14.9 deg from B, nearest is `5`  (so the test can fail)
```

Positional error is fully accounted for by proportion mismatch — measured avatar/template phalanx
ratios 0.77–0.95. **Your placement is not approximately right, it is exact in the space you
control.** Suggestion: make the direction metric the 2a acceptance gate, with the rest-hand
negative control alongside it, and retire 8/35 as the headline.

Four corrections to the argument, because each one matters if either of us reasons from it again:

**① The two numbers you compared aren't on the same landmark set.** Your templates are complete
21-point arrays, so inter-template distances use 20 landmarks. The rendered hand fills only **14** —
the rig has 3 bones per finger with no tip node, so 4/8/12/16/20 come out null, and
`roleBone('ThumbProximal')` resolves to `Thumb2` (your `SEG_OF` uses Metacarpal/Proximal/Distal for
the thumb), which nulls 3 as well. On the 14 the rig can express, **B–C is 0.124, not 0.206**, and
the closest pair is (B,C) not (5,C). So your error exceeds the *entire* gap, not half of it. Worth
recomputing your three §3 numbers restricted to the landmarks the rig can actually fill.

**② "Error is half the gap, so nearest-neighbour flips" doesn't hold in high dimensions.** Simulated
at 4000 trials per condition: isotropic error of 0.150 keeps B nearest **4000/4000**; at 0.206 also
100%; it only starts breaking near 0.400. Across ~42 landmark dimensions a flip needs the error
pointed within ~47° of the B→C direction, which isotropically is ~1e-6. A flip needs a **directed**
error. And your own model — B↔C coin-flip on 26 words, 9 others correct — predicts 22/35 = **63%**.
The observed 8/35 is ~5.5σ below your own explanation, so "the metric lacks resolution" cannot be
the mechanism.

**③ Your effective n is 5, not 35.** The rendered passive pose is byte-identical across every word
requesting the same shape (max within-shape distance 2.4e-08, i.e. float noise). All 26 B rows carry
the same 0.150 / 0.142 / 0.606. So the result is **3/5 shapes**, replicated 35 times — not 35
binomial trials, and "23% vs 14% chance" isn't the right framing either way.

**④ "Every mis-assignment is B→C" is false, and your own script hid it.** There is an **S→A**
mis-assignment on `time` (err 0.248). You never saw it because the output does
`rows.slice(0, 14)`, which hides 21 of 35 rows. Also your stated mechanism is refuted: the rendered
B's PIP flexion is **3.7°, identical to template B's 3.7°** — clamping is not curling B toward C.

**⑤ And one real defect found in passing, unrelated to all of the above: 0 of 35 `2a` clips key the
distal finger bones, while 52 of 52 `2s` clips do.** The fingertips aren't being posed on the
asymmetric path. Please check that one directly — it is the kind of thing that would quietly cap
2a quality no matter what the templates say.

**Provenance, stated plainly:** this whole section is one independent reproduction whose own
adversarial reviewers died on a session limit before they ran. It reproduced your numbers exactly
and carries a working negative control, which is why I'm sending it — but it has not been attacked
the way the §2 bug was, and ⑤ in particular I have not verified myself.

---

## 4. Your §4 items — confirmed, and one is worse in our favour

- **`n_usable: 6`** — confirmed. `1 5 B A S C` usable, `O` not (`agreement_xy` 0.286).
- **`S` is measured** — confirmed, `agreement_xy` 0.1636, n=40. §0.3's "5 measured + `S→A`" was
  stale in both ways you said. Already corrected before your letter arrived, so we agree.
- **`O` is required by no 2a word** — confirmed, and **it is worse than you found in two ways.**
  First, `S→A` never fires either, so *both* documented substitutions are inert. Second, **`5` is
  never requested either** — assignments are B 26, A 3, `1` 3, C 2, S 1 = 35, so only **5 of the 7
  templates are reachable on this vocabulary** and all five are measured. It is **35/35 on measured
  templates with zero live approximations**, which is a stronger statement than the file made, and
  you were right that nobody should have to cross-reference to discover it. Now stated outright in
  `handshape_templates.json` → `vocabulary_coverage`.

- **You were more right than you realised about the staleness, and it was not confined to a doc.**
  Chasing it down found **four** files carrying the dead `S→A` claim, two of which you read:
  `docs/SIGN_ANIMATION_CONTRACT.md` §"Handshape templates" said "five of seven measure cleanly",
  `S→A`, and "**34 of 35** words land on a measured template, one (`time`) on the fallback" — so
  the contract you are implementing against was telling you `time` needs a substitution it does
  not. And `asl_handedness_250.json` → `passive_handshape._fallback` described the resolution map
  as "S->A, O->C" — **a renderer-read data file misdescribing its own sibling.** Also
  `MODEL_250_MVP_REPORT.md`, which went as far as *defending* the S→A substitution on the grounds
  that S and A are both unmarked fists, and `SESSION_HANDOFF.md`, where "34/35" sat **two lines
  below** the bullet that had already corrected it. All four fixed in the attached bundle.

- **One correction pointed the other way — your §3 control is too generous to itself.** You
  compared 8/35 = 23% against ~14% uniform chance over 7 templates. But B is 26 of 35 assignments,
  so a model that ignores the render entirely and always guesses B scores **74%**. Against the
  right baseline your 23% is not "above chance", it is far *below* the majority-class guesser —
  which is consistent with §3.5's finding that the failure is deterministic rather than noisy.
- **The self-disclaimer** — agreed, and §3 above is now the way to tell a lexicon error from a rig
  limit. Your `template-check.mjs` is what makes that separable; thank you for shipping it.

---

## 5. `sourceQuality` — you already have it, and I was wrong to imply otherwise

I had this recorded on my side as *"the meta file and `sourceQuality` never reached him."* Checking
rather than trusting the note: **they did.** All 250 word files in the bundle you already
processed carry `segments[].synthesis.sourceQuality`, and `sign_clips_250.meta.json` is in it too.
Nothing was missing and there is nothing here to catch up on.

Since it may not have been obvious what to do with it, it is relevant to your §3: it marks which
words came from a **single usable take**, which is exactly the population where a shape looks wrong
for a data reason rather than a rig reason.

```
20 words are thin (<= 2 usable takes); 7 have exactly one:
    boat  drop  have  many  quiet  store  tiger
6 words are brief (< 0.53 s):
    bye  tiger  tomorrow  tongue  wet  yourself      (tiger is both)
```

If a Deaf reviewer flags one of those 7, the answer is "one take existed," not "the rig is wrong."

**And a correction:** my v7 letter said `quiet` was the 116-frame word. It is not — `quiet` is
44 frames (1.47 s) and **`puppy`** is the 116-frame one (3.87 s). You used `puppy` correctly in
your v8 without mentioning the discrepancy. The attached copy of `FROM-SALIM-v7.md` is fixed.

---

## 6. Where this leaves us

| | owner | state |
|---|---|---|
| One-handed, 163 words | you | done |
| 2s mirroring, 52 words | you | done, exact |
| 2a handshape, 35 words | you | rendering; ~0.15 fidelity floor, possibly overstated — recheck after §2 |
| **2a side guard** | **you** | **§2 — the one real bug, 666 frames** |
| **2a base placement, 35 words** | **me** | **§3 — lexicon deliverable, needs Deaf review** |
| Corpus / export | me | **FINAL. No further changes.** |
| Blend constants | me | fixed, §1 |

Two bugs traded this round, both the same species as everything else we have found: a condition
that silently matched a case it was not written for, reported as success. Your counter caught
yours. A counter would have caught this one too — `templateHands` summing to 2040 instead of 1374
was visible in your own log the whole time, which is the argument for printing the number you
*expect* next to the number you *got*.

Nothing blocking on your side but the guard.

— Salim
