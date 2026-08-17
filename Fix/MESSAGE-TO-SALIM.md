Salim —

Animation side is finished and I've audited all 250 words individually. Short version: **body
motion is solved, handshape is blocked, and the block is in the tracking.**

Full detail in `FOR-SALIM-what-to-fix.md` (attached), plus a script you can run yourself
(`check-export.py`) and the per-word breakdown (`coverage-per-word.csv`).

**Where we are**

- The avatar reproduces **74.4%** of the signer's real wrist travel — which is **100.5% of
  what this avatar's arm can physically reach**, so the solver is saturated
- **250 of 250** clips pass the anatomical gate — no clipping, no impossible joints
- Zero frames move faster than the signer's own p99, so nothing reads as a glitch
- Smoothness 0.43–0.52 against the signer's own raw 0.909, i.e. cleaner than the source

**What's blocked, and the measurement behind it**

Splitting every frame by whether a 21-point hand block came back, then measuring how fast that
hand was moving at that moment:

- hand block present → median wrist speed **0.016** shoulder-widths/frame
- hand block missing → median wrist speed **0.032**

**MediaPipe is dropping the hand precisely when it MOVES** — the untracked hand is twice as
fast. In a one-handed sign that is the signing hand. Coverage per word bears it out: **28.8%
on the hand doing the sign vs 51.5% on the resting hand.**

Scoring that properly meant splitting the corpus by handedness first, since a one-handed sign
needs handshape on one hand and a two-handed sign needs it on both — 195 one-handed / 55
two-handed. On that basis:

**164 of 250 words are missing a hand the sign phonemically requires.** Coverage over required
hands only: **30.3%**. Only 33 words are currently clean on every hand they need.

One detail that pins this on tracking rather than on the signer or the segmentation: of the 55
two-handed signs, **50 are missing one hand and none are missing both.** If hands were out of
frame you'd lose them together. Losing exactly one, almost every time, is the detector holding
the slower hand and dropping the faster one.

Handshape is one of the five phonemic parameters — CAT and FATHER share location and movement
and differ only by handshape. So for two-thirds of the vocabulary the distinguishing feature
isn't in the data at any effort on my side. I can make those hands look plausible (they now
rest in a relaxed curl instead of the rig's splayed reference pose, which is what was making
them look like claws) — but plausible isn't correct.

**What I need, in priority order**

1. **Fix hand tracking on the moving hand.** The only item that blocks the product.
   - **Check the source parquet first** — a 70% loss looks as much like an export bug as a
     tracking limit, and that would be far cheaper than re-shooting. Worth ruling out before
     anything else.
   - Config first since it's free: `model_complexity=2`, and **lower**
     `min_tracking_confidence` / `min_detection_confidence`. Please bias hard toward returning
     *something* — I can filter a noisy hand, I cannot invent a missing one.
   - Then per-hand ROI tracking: crop to the previous frame's predicted hand region and run the
     hand model on that crop, rather than one Holistic pass over the full frame. Standard remedy
     for exactly this failure.
   - Faster shutter at capture if the footage can be re-shot — motion blur is the likely primary
     cause and no post-processing beats fixing it at source.

2. **Ship native clip length.** All 250 are resampled to exactly 64 frames / 2.133 s, so every
   sign plays at the same speed — and duration carries meaning (aspect, emphasis, repetition).
   You already emit `segments` and it currently just spans 0–64; marking the real sign extent
   inside the window would be nearly free.

3. **Add `visibility` and `presence` per landmark.** MediaPipe computes them and the schema
   drops them. I currently infer which samples to distrust with a statistical median test — it
   works, but it's guessing at something you already know. Worth ~4 points of motion, and it
   removes a real failure mode: my spike detector bails out entirely on badly-tracked clips
   rather than risk over-rejecting, so the worst clips get no cleaning at all.

4. **Two small schema fixes.**
   - Missing hand blocks arrive as 21 exact `[0,0,0]` rather than `null` (19,002 blocks, 60%).
     In shoulder-centred space the origin is mid-sternum, so anything following §6 draws the
     hand collapsed into the chest. `null` I can bridge; zeros I have to sniff for. This one
     cost me a day chasing a phantom 32 cm wrist offset that was really 4 cm.
   - §3 says the data is selfie-mirrored. It isn't — the signer's right shoulder is at smaller
     x in **100% of 15,877 frames**. Doesn't break my renderer, but it will bite the next
     person who trusts the doc.

**Two clips to re-check**

- `wake` — 42 of its 64 frames project a limb *longer* than the signer's own p99 limb length
  (1.08 shoulder-widths against 0.87). A projection can't exceed the true length, so those
  frames are mistracked. Only clip that resisted every fix on our side.
- `hello` — both wrists stay below the shoulders for all 64 frames with neither hand near the
  head, and HELLO is a salute at the forehead. Looks like a wrongly-segmented take. Given
  exemplars are auto-picked by tracking quality and not yet Deaf-reviewed, probably worth a
  spot-check pass over the 250 before review — a reviewer flagging mistracked takes wastes
  their time and yours.

**Verifying a fix**

`check-export.py` runs on your export directory with no dependencies and prints pass/fail
against all of the above, plus the re-record list:

```
python3 check-export.py path/to/words     # exit 0 = critical criteria pass
```

The number to move is **required-hand coverage: 30.3% now, ≥70% is the target.** It also
prints the moving-vs-still tracking ratio, currently **1.98×** — that should come down toward
1.0.

Items 2, 3 and 4 are schema changes and should be quick, and item 3 helps me immediately even
before the tracking work lands. **Item 1 is the whole game.** Body motion is at 100% of what
our avatar allows; handshape is at 30.3% on the hands the signs need. Until the tracking
changes, two-thirds of the dictionary can't be made correct no matter what I do on the
animation side.

To be clear about the boundary: none of this is a complaint about your work. Holistic dropping
fast hands is a known weakness of the model, not a mistake you made, and the schema items are
the kind of thing that only surfaces once two systems meet. What I do want to be unambiguous
about is that the animation side has stopped being the bottleneck — so if we're deciding where
the next two weeks go, it should be here.

Happy to jump on a call about the ROI-tracking approach, or to look at the raw parquet directly
if that's faster than describing it.
