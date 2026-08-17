# Deafference — response to the animation-side audit

**To:** animation / retargeting side
**From:** Mohammad Salim (data pipeline)
**Re:** `FOR-SALIM-what-to-fix.md`, contract v3 → v4
**Date:** 2026-08-10

---

## 0. Short version

Your audit found a **real bug on my side**, and it was worse than you diagnosed. Thank you for
`check-export.py` — it is the reason this was findable in an afternoon instead of a week.

| | |
|---|---|
| ✅ **ASK 4a** (zeros → `null`) | **Fixed and re-exported.** 19,002 → **0** zero-blocks, verified with your script |
| ✅ **ASK 4b** (§3 mirroring) | **Fixed.** You were right; the contract line was wrong |
| ✅ **ASK 2** (native duration) | **Partly shipped** — real `segments` extent is in the export now; native frame count needs a rebuild |
| ❌ **ASK 3** (`visibility`/`presence`) | **Not possible.** The field does not exist in our source. Please drop it permanently |
| ⚠️ **ASK 1** (track the moving hand) | **Not fixable the way you propose — but mostly fixable another way.** Read §2 and §3 |

**Re-pull `animation_handoff/` now.** The zeros are gone, `segments` carries the true extent, and
the `note` field states the corrected conventions.

---

## 1. What is already fixed

### ASK 4a — missing hands are `null`

You were exactly right, including the count. Your own script, before and after:

```
BEFORE  [FAIL] no hand block encoded as 21 zeros    19002 zero-blocks (60%)
AFTER   [PASS] no hand block encoded as 21 zeros        0 zero-blocks  (0%)
```

**Root cause, because it explains the rest of this document.** Our recognition corpus encodes a
missing landmark as exact `0.0`, not NaN — it is stated in `training/README.md` and I had not
propagated it. Three separate consumers each assumed NaN:

1. the exemplar selector tested `np.isfinite()`, and `isfinite(0.0)` is `True`;
2. the JSON encoder tested `math.isfinite()`, same blind spot;
3. `normalize_clip()` re-centres by the shoulder midpoint, turning an exact `0.0` into a ~6e-8
   residue, which `round(v, 5)` then snapped back to exactly `0.0`.

So the zeros were not passed through — they were *manufactured* at three points independently.
There is now one function, `sign_landmarks.canonicalize_missing()`, that owns the conversion, and
it runs at every load site. Your point about a contract existing to eliminate exactly this class
of ambiguity was the correct diagnosis.

It runs **on load, not at build time**, so re-exporting repaired the existing deliverable without
re-running the corpus build. That is why you can pull it today.

### ASK 4b — the mirroring line was wrong

Corrected in `SIGN_ANIMATION_CONTRACT.md` §3, with your measurement quoted and a note that the
previous text was wrong. Your instinct to derive the lateral axis from landmarks 11/12 rather than
trust the documented convention is the reason you caught it; I have written that into the contract
as the recommended practice.

### ASK 2 — `segments` now carries the real extent

Every per-word file now has the true sign extent instead of `0–64`, plus `nativeFrames` /
`nativeFps`:

```json
"segments": [{ "gloss": "down", "start": 0, "end": 45 }],
"nativeFrames": 64,
"nativeFps": 30
```

`down` measures **0–45**, which matches your "loses its last 21 frames" independently — good
cross-check on both our methods. **28 of 250** words have an extent shorter than the window.

I am shipping the **full clip plus the extent** rather than a pre-trimmed clip on purpose: you
asked to be able to re-time, and trimming here would hand you my guess instead of the data. The
true *native frame count* is still lost (everything was resampled to 64 upstream of the export);
recovering it requires the rebuild in §4.

---

## 2. Three things that are not possible, and why

This is the part I should have made unmissable in the contract. **There is no video.**

Our corpus is Google's *Isolated Sign Language Recognition* dataset (Kaggle `asl-signs`). It ships
**MediaPipe landmarks only** — the raw recordings were never published. We have never run
MediaPipe ourselves; Google ran it once in 2023 and released the output.

| Your proposal | Why it can't happen |
|---|---|
| Faster shutter / more light / re-shoot | There is no footage to re-shoot and no camera in our pipeline |
| Per-hand ROI tracking | Requires image frames to crop. None exist |
| `model_complexity=2`, lower `min_tracking_confidence` | We do not invoke MediaPipe at any point |
| **ASK 3** — `visibility` / `presence` | The parquet has `x, y, z` only. MediaPipe *computes* them; this dataset does not *carry* them |

This is in the contract's §0 preamble — *"Per-landmark confidence: NOT available… Raw videos: do
not exist (landmark-only dataset)"* — so it is on me for burying two load-bearing constraints in a
preamble rather than putting them where ASK 1 and ASK 3 would run into them.

**Please drop ASK 3 permanently and stop reserving time for tracking work.** Your median-based
statistical test is not a workaround for a missing field — given this dataset, it is the only
method available, and it is the right one. The 51% → 74% it bought is the real number.

---

## 3. The good news: your 30.3% is mostly *my* bug, not a tracking floor

You concluded that handshape is capped by MediaPipe's weakness on fast hands. That effect is real —
your 1.98× measurement is solid and I reproduced it — but it is **not what set the 30.3%.**

`build_sign_clips.py` was supposed to pick the cleanest of roughly **365 candidate clips per word**
(~91,000 clips across 250 words). Its scorer was:

```python
per_frame = np.isfinite(hand_xy).all(axis=-1).any(axis=1)   # hand_xy = clip[:, 33:75, :2]
```

Two independent defects in one line:

**It could not see missing hands.** `isfinite(0.0)` is `True`, so a hand collapsed at the origin
scored as fully tracked. Measured across the shipped clips:

```
hand_presence() as shipped : mean 0.9923   exactly 1.0 for 238 of 250 words
true per-hand coverage     : left 0.392    right 0.420    worst-of-both 0.018
```

Selection was `if pres > best[word]` — strictly greater. With 238 clips tied at a perfect 1.0,
**the comparison never fired.** The "cleanest exemplar per word" selector was, in effect,
*"whichever clip appears first in manifest order."* We shipped you a near-random draw.

It also means the build's reassuring `250/250 clean, no weak-clip warnings` was a **false
all-clear** — the `presence < 0.5` warning was mathematically unable to trigger.

**It OR-ed both hands together.** `clip[:, 33:75]` spans left *and* right, so one tracked resting
hand marked the frame as covered. Combined with your 1.98× finding this inverts the objective:
because the tracker keeps the *still* hand, maximizing presence actively prefers the clip where
the signer moved **least**. Your §3.4 warning — *"if anything on your side keys off hand-block
presence… it is getting the answer backwards"* — was precisely correct, and it was.

### This also explains `hello`

`hello` is not a mis-segmented take. It is the arbitrary first clip, and both wrists stay low
because a barely-moving take is exactly what a presence-maximizing selector prefers for a sign
whose hand travels fast to the forehead. Same root cause. I expect a meaningful share of your
164 to be selection artifacts rather than corpus limits.

### The new selector

Scored on **required-hand coverage**, using your handedness split — one-handed signs need the
signing hand, two-handed need `min(left, right)`. I deliberately optimize the same quantity your
`check-export.py` reports so we are not tuning against different numbers.

Reproducing your audit with it, from our side of the pipeline:

| | yours | ours |
|---|---|---|
| one-handed / two-handed | 195 / 55 | 194 / 56 |
| MISSING / partial / ok | 164 / 53 / 33 | 165 / 53 / 32 |

Off-by-one on tie-breaking. Same measurement.

**Honest caveat:** I do not yet know how much re-selection recovers. Hands *are* tracked ~40% of
the time, and picking the best of ~365 instead of the first should improve substantially — but if
the loss is roughly uniform across candidates, it improves without necessarily reaching your 70%.
I will send you the measured number, not an estimate.

---

## 4. What I'm doing next

| # | Work | Status |
|---|---|---|
| 1 | Zeros → `null`, contract §3/§6 corrected, real `segments` extent | ✅ **done — pull it** |
| 2 | Rebuild exemplars with the corrected selector | ⏳ blocked ~1 day |
| 3 | Ship true native frame counts (same rebuild) | ⏳ same |
| 4 | Spot-check the 250 for wrong takes, then Deaf review | after 2 |

**The blocker on 2 and 3:** the preprocessed corpus was accidentally overwritten on our training
host yesterday. Nothing is lost — it is intact in an earlier dataset version — but restoring
~2.1 GB is a day of plumbing. Re-selection needs all ~91,000 candidate clips, not just the 250 we
shipped, so it cannot run until then.

On **`wake`**: its 42 geometrically-impossible frames are consistent with a mistracked source clip,
and the fix is the same as everything else here — pick a different candidate. I will confirm it
clears rather than special-casing it.

I will re-run your `check-export.py` before sending anything, and quote its output verbatim.

---

## 5. What I need from you

1. **Re-pull `animation_handoff/`.** Zeros are gone — you can delete the zero-sniffing path and
   use `null` + interpolation as the contract always intended. This should also retire the
   phantom-wrist-offset class of bug that cost you a day.
2. **Stop reserving time for tracking work.** Nothing in §2 is achievable. If handshape must
   improve beyond what re-selection yields, the honest options are a different corpus or recording
   our own — a product decision, not a pipeline one.
3. **Confirm the objective.** I now maximize `min(left, right)` coverage for two-handed signs. If
   your renderer degrades more gracefully with, say, one strong hand and one weak than with two
   mediocre ones, tell me and I will change what the selector optimizes. You know the failure
   modes on your side better than I do.
4. **One number to reconcile.** Your CSV's `requiredHand` column reads 171 right / 24 left, but
   dominance computed over the corpus — by your method and by mine, which agree at 118R/132L and
   119R/131L — is majority *left*. Your earlier audit's 131 left / 119 right matches that too. If
   the CSV column came from an earlier revision, the re-record list may be ordered on a stale
   dominance call. Worth a look before we prioritize off it.

---

## 6. On the boundary

Your closing framing was generous and I want to answer it plainly rather than trade reassurances.

Two of your four asks were impossible and I had documented that badly enough that you spent effort
planning around them. Meanwhile the number you attributed to a model weakness was substantially my
bug — a selector that had never selected anything, reporting a clean bill of health while doing it.
You found it with a 167-line dependency-free script that I should have written and run myself
before shipping 250 files.

The specific thing I will take from this: `check-export.py` runs on *my* side from now on, before
any export leaves. And your habit of testing a checker against a synthetic *clean* input — because
a checker that can only print FAIL is indistinguishable from a broken one — is going into our
practice generally.

Agreed on where the next two weeks go, with one correction to the target: it is data **selection**,
not data capture.
