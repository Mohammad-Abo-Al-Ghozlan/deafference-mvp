# Sign-Animation Contract (speech → sign, avatar/animation side)

**Status:** v4 (2026-07-30). The interface between the *pre-animation* stage
(Salim: ASR → gloss → motion data) and the *animation* stage (renderer/avatar).
Same idea as `MODEL_CONTRACT.md`: pin the data hand-off so the two sides don't
discover a mismatch late. **Parts 0–11 = the hand-off contract; PART B (appended)
= the full end-to-end build plan for every phase + the 5-day 250-word plan.**

> ### ⚠️ v3 UPDATE (2026-07-30) — delivery model FINALIZED to PER-WORD  ·  READ THIS FIRST
> **This supersedes the "Salim stitches one stream per utterance" default described in §1 / §8.3 / §10 below.** The agreed model is now:
> - **Salim delivers ONE JSON per word** (~250 files) — each file is a §1 object holding just that one word's `frames` — produced by `gloss_to_motion.py --per-word`. Plus one `reference_pose.json` (see §11.2).
> - **At runtime, Salim sends only the ORDERED WORD LIST** (e.g. `["hello","mom","hungry","please"]`). The 250 per-word files are delivered ONCE, up front.
> - **The animator (you) sequences the per-word clips and BLENDS the transitions** between them — i.e. the §10 *"alternative"* is now the DEFAULT. Salim does **NOT** stitch a per-utterance stream, and does NOT insert transition frames.
> - Everything else below stands unchanged: §2 layout, §3 shoulder-centered + flip-y, §6 `null`=hold/interpolate, §7 face (v2), §11 rig — and especially **§11.3: the data is POSITIONS per frame, NOT bone rotations.**

> ### ⚠️ v4 UPDATE (2026-07-30) — animation-side review resolved (Mohammad)
> - **§4 z-axis:** z is **shipped raw** in every file (each point `[x,y,z]`, never zeroed / smoothed / rescaled). **2D drops z; 3D KEEPS z but uses only its SIGN** per segment — magnitudes are reconstructed from the rig's known bone lengths (`|dz| = sqrt(L² − d_2d²)`). See §4.
> - **Positions vs rotations → POSITIONS (resolved).** Landmarks are **IK targets only** for a skinned rig (placing joints directly would tear the mesh). **No retarget step on Salim's side.** See §11.3.
> - **Per-limb scale:** the animator derives **per-limb scale factors** from `reference_pose.json` (not just a global shoulder-width scale) to absorb signer-vs-avatar proportion differences. See §11.2.
> - **Per-landmark confidence:** NOT available — the source has x,y,z only (no visibility channel). `null` = missing is binary.
> - **Raw videos:** do **not** exist (landmark-only dataset) → no `pose_world_landmarks` re-extraction possible; sign-only z is the path.

---

## 0. Where this sits

```
hearing person speaks
  → [Salim] speech recognition (audio → English text)      \
  → [Salim] text → gloss sequence (LLM, our vocab)           }  PRE-ANIMATION
  → [Salim] resolve glosses → per-word motion clips          /
  → ────────── THIS CONTRACT (the hand-off) ──────────
  → [Teammate] render the motion data onto an avatar        }  ANIMATION
  → Deaf person sees the signing
```

**You build against THIS document + the sample files Salim gives you — you do NOT
need to wait for the full pipeline.** The pre-animation stage will emit exactly the
format below; Salim will hand you 2–3 real sample files now so you can build and
test the renderer immediately.

---

## 1. What the animation consumes — a landmark **keyframe sequence**

One utterance = an ordered list of frames. One frame = the body pose at that moment
= **75 landmarks**, each `(x, y, z)`. This is the SAME 75-point layout used for
recognition — the recognition data format doubles as the animation-driving format.

**Delivered as:** a JSON file (portable for web/Three.js or Python) — and, for long
sequences, an optional `.npy` array `(T, 75, 3)` float32 + a small JSON sidecar.

```json
{
  "schema": "sign-animation/v1",
  "fps": 30,
  "coord_space": "shoulder-centered",
  "glosses": ["hello", "hungry"],
  "segments": [
    { "gloss": "hello",  "start": 0,  "end": 30, "synthesis": { ... see §6.1 ... } },
    { "gloss": "hungry", "start": 38, "end": 70, "synthesis": { ... } }
  ],
  "frames": [
    [ [x,y,z], [x,y,z], ... 75 total ... ],   // frame 0
    [ [x,y,z], ... ],                          // frame 1
    ...
  ]
}
```

- `frames[t][i]` = landmark `i` at frame `t`. `x,y,z` are floats (see §3/§4).
- `glosses` / `segments` carry per-word timing **and** `synthesis` — the instructions for
  the hand that is absent from the data. For the 87 two-handed words, `frames` alone is
  **not** sufficient to draw the sign; see **§6.1**.
- `synthesisNote` appears at the file root whenever any segment carries a `synthesis` block.
  Its absence means the exporter had no lexicon and the file is under-specified.
- **Optional:** when facial expression is available, an extra `has_face: true` +
  parallel `face_frames` block (468 FaceMesh points/frame) — full spec in §7.

---

## 2. Landmark layout (the 75 points)

| Index range | Body part | Source |
|---|---|---|
| **0–32** | Pose (upper body) | MediaPipe Pose |
| **33–53** | **Left** hand (21 pts) | MediaPipe Hand |
| **54–74** | **Right** hand (21 pts) | MediaPipe Hand |

Within the pose block, the useful joints for arms:
- **11 = left shoulder, 12 = right shoulder** (also define the coord space, §3)
- **13 = left elbow, 14 = right elbow**
- **15 = left wrist, 16 = right wrist** (connect to the hand blocks)

Pose points **0–10** are coarse face *positions* (nose, eyes, ears, mouth corners)
— use them only to place the head, **NOT** for expression (see §7).

Hand landmarks follow MediaPipe's standard 21-point hand topology (wrist=0,
thumb=1–4, index=5–8, middle=9–12, ring=13–16, pinky=17–20), offset by 33 / 54.

**Drawing the skeleton (which points connect):** use MediaPipe's standard connection
sets — `POSE_CONNECTIONS` (arms/torso) and `HAND_CONNECTIONS` (finger bones), the
same ones `live_demo.py` draws with. Don't hand-invent the bone list; import
MediaPipe's, remembering the +33 / +54 offsets for the two hands.

---

## 3. Coordinate space

- **`coord_space: "shoulder-centered"`** — origin = midpoint of shoulders (11,12),
  scale = shoulder width. So a hand at the shoulder line sits around x ≈ ±0.5.
  Person-independent and size-stable → the avatar won't drift or resize.
- ⚠️ **AXIS WARNING:** these come from image coordinates, so **y points DOWN**
  (smaller y = higher up). Most avatar/3D engines use **y UP** → **flip y**
  (`y_render = -y`) or the avatar signs upside-down.
- x: left/right, in **RAW CAMERA orientation — NOT selfie-mirrored.** The signer's
  **right shoulder sits at SMALLER x** (measured: 100% of 15,877 valid frames).
  > **Corrected 2026-08-10.** This line previously claimed the data was mirrored to
  > selfie view. It was wrong and it cost the animation side debugging time. Derive
  > the lateral axis from landmarks 11/12 rather than trusting a documented sign
  > convention — that is what caught the error.

---

## 4. The z axis (read before doing anything 3D)

- z is MediaPipe's **relative depth — noisy and low-quality as a VALUE.** But it is
  **shipped raw** in every file (each point is `[x, y, z]`); it is never zeroed,
  smoothed, or rescaled. Do not ask Salim to pre-process it.
- **2D avatar (the MVP): DROP z.** Use only (x, y).
- **3D avatar: KEEP z — but use only its SIGN, not its value.** With known rig bone
  lengths the out-of-plane magnitude is determined (`|dz| = sqrt(L² − d_2d²)`); the
  only thing 2D projection loses is the *sign* per segment. Read that one bit from z,
  reconstruct magnitudes from bone lengths. (Measured animation-side: sign-only z beats
  a flat z=0 by 4–20× on toward-camera signs; a fixed anatomical prior does not help.)
- ⚠️ **Scale note:** x,y are shoulder-width-normalized (origin = shoulder midpoint);
  **z is RAW MediaPipe units, NOT normalized** — smaller z = closer to camera
  (origin ≈ hip midpoint). Fine for sign-only use; don't compare z magnitude to x/y.
- `pose_world_landmarks` (metric 3D) would remove the sign ambiguity, but the raw
  videos do **not** exist (landmark-only dataset) — so it is not available.

---

## 5. Timing

- `fps` (default **30**) — render one frame per `1/fps` seconds.
- Total duration = `len(frames) / fps`. Keep it real-time; don't drop/duplicate
  frames unless you resample cleanly.

---

## 6. Missing points

- A landmark that wasn't detected is **`NaN`** (or `null` in JSON). Hands are often
  missing between signs / when lowered.
- **Do not draw a NaN point.** Recommended: **hold the last valid pose or
  interpolate** across the gap so the avatar doesn't blink/jump.
- ⚠️ **NEVER `[0,0,0]`.** The origin is **mid-sternum** in this coordinate space, so a
  zero-filled point is a *valid-looking* position that draws the hand inside the chest.
  A consumer must never have to sniff for zeros to find absence.
  > **Regression fixed 2026-08-10.** Exports before this date shipped **19,002 hand
  > blocks (59.4%) as 21×`[0,0,0]`** instead of `null`. Root cause: the recognition
  > corpus encodes a missing landmark as exact `0.0`, not NaN, and three separate
  > consumers each assumed NaN. `sign_landmarks.canonicalize_missing()` is now the
  > single place that converts the sentinel, and it runs on every load. If you are
  > reading an old export, re-run `gloss_to_motion.py --per-word` — the repair happens
  > at load time, so no rebuild is needed.

---

## 6.1 The `synthesis` block — the hand that is NOT in the data

> **Added 2026-08-12.** This section supersedes any earlier statement that `frames` alone is
> enough to draw a sign. For 87 of 250 words it is not, and the reason is a property of the
> corpus rather than a bug we can fix.

**The corpus records ONE hand per participant.** Both hands appear in 1.7% of clips and
both-hand *frames* average 0.1%. So on every two-handed sign, the passive **hand** is absent
from *every take* — this is not selectable around and never will be. What *is* present in
every frame is the passive **wrist**, because that is a pose landmark. Position is given; only
the handshape must be synthesized.

Every segment therefore carries what the renderer needs to make that decision:

```json
"synthesis": {
  "class": "2a",                        // "1" | "2s" | "2a"
  "rule": "unmarked_handshape_at_base", // "none" | "mirror_dominant_handshape" | "unmarked_handshape_at_base"
  "dominantHand": "R",                  // ALWAYS "R" — see below
  "twoHanded": true,
  "labelConfidence": "high",            // confidence in the CLASS, from the lexicon
  "passiveHand": "L",                   // two-handed words only
  "passiveWristIndex": 15,              // pose landmark carrying the passive wrist
  "passiveHandshape": {                 // 2a only
    "shape": "S",                       // key into handshape_templates.json
    "contact": "wrist",                 // WHERE the dominant hand meets it
    "conf": "med",                      // confidence in the SHAPE, not the class
    "note": "dominant 1 taps the BACK OF THE PASSIVE WRIST"
  },
  "dominantCoverage": 0.6923            // fraction of frames with a MEASURED dominant hand
}
```

### The three rules

| `class` | `rule` | n | what to do |
|---|---|---|---|
| `1` | `none` | 163 | One-handed. Nothing to synthesize. **No passive fields are present at all** — if you see `passiveWristIndex`, the sign genuinely has a second hand. |
| `2s` | `mirror_dominant_handshape` | 52 | Copy the dominant handshape to the passive hand. Exact, not a guess — Battison's Symmetry Condition. Copy **local** joint rotations, not world-space directions (a reflection has determinant −1; mirroring directions yields a correct curl on a backwards palm). |
| `2a` | `unmarked_handshape_at_base` | 35 | The passive hand is a still base. Use `passiveHandshape.shape` at `passiveHandshape.contact`. |

### `dominantHand` is `"R"` by construction — do not re-derive it

Left-dominant signers are mirrored during extraction, so the tracked hand is *always* at
landmarks 54–74 and block 33–53 is empty in all 250 words. **Read this field; never infer
dominance from wrist travel.** On a symmetric sign the two wrists tie — `finish` measures a
ratio of exactly 1.00 — and whichever way the tie breaks, half the time you read the empty
block and conclude the sign has no dominant hand. That single re-derivation produced a
false "unrecoverable hole" verdict on an otherwise healthy word.

### `dominantCoverage`: how much of the word you are inventing

The fraction of frames in which the dominant hand is actually measured. The remainder are
`null` and must be held or interpolated (§6). It is **not** uniform across classes:

| class | `dominantCoverage` (what this field reports) | inside the sign extent only |
|---|---|---|
| one-handed | **0.888** | 0.829 |
| `2s` | **0.494** | 0.412 |
| `2a` | **0.504** | 0.422 |
| pooled | **0.752** | 0.685 |

**Use the bold column** — it is what `segments[].synthesis.dominantCoverage` contains, measured
over the whole exported clip. The right-hand column is `dominant_hand_coverage` from
`sign_clips_250.meta.json`, measured only between `sign_start` and `sign_end`; it is stricter
because the trimmed core is where the hand is moving fastest and therefore most often lost.
Both are correct about different windows. Quoting one against the other is how the same word
appears to have two coverage values — and the acceptance script's headline **76.2%** is a third
thing again, pooled over frames rather than averaged over words.

The cause is physical, not a selection failure: MediaPipe preferentially loses the hand that
**moves** (median wrist speed 0.0317 sh.w./frame in hand-missing frames vs 0.0208 in
hand-present frames), and two-handed signs move both arms. Selecting for coverage would
therefore select for stillness — measured at `r = −0.464`, negative for 100% of 250 words.
So the export deliberately does **not** maximize coverage, and on two-handed words the
renderer must expect to hold a handshape through more than half the frames.

**Interpolate openly.** Holding a handshape across a gap is legitimate; the reason
`dominantCoverage` is in the file at all is so that the gap is visible to you rather than
hidden. An earlier upstream cleaner forward-filled missing landmarks silently, which made
every coverage metric read high and mean nothing (§6 regression note). Declared
interpolation is the opposite of that.

### Trajectory: play the passive wrist, don't mirror it

Only the *handshape* is missing. Both wrists are real pose data in every frame, so play the
recorded passive wrist as it is. Do **not** synthesize the passive trajectory by mirroring
the dominant one: the Symmetry Condition constrains **handshape**, not movement phase.
Symmetric two-handed signs are well-formed moving in phase, out of phase, or mirrored, and
measurement bears this out — of the 13 `2s` words where both arms clearly move (travel ratio
> 0.85), **12 of 13** score under 50% on a per-frame sagittal-mirror test. (The exception is
`now`, at ≥ 80% — so in-phase mirroring does happen; it just isn't the rule.) Mirroring the
trajectory would replace real data with a guess that is usually wrong.

For the same reason, **a low mirror score is not a weak-hand detector.** Use the arm travel
ratio to indict a take; `rain` scores 1% on mirroring while its passive arm travels 97.8% as
far as the dominant one — that arm is working.

### Handshape templates and the `resolution` map

`handshape_templates.json` carries 21-point templates for the unmarked set, measured from the
corpus rather than authored. **Six of seven measure cleanly** (`1 5 B A S C`); only `O` does not
(`agreement_xy` 0.286). The file carries an explicit `resolution` map — **`S→S`, `O→C`** — and you
should follow it rather than a rig default so both sides substitute identically.

**On this vocabulary the map never fires at all.** The 35 `2a` words request exactly
`B 26, A 3, 1 3, C 2, S 1 = 35`, and all five of those shapes are measured. So it is
**35 of 35 on measured templates, with zero live approximations.** Templates `5` and `O` are
requested by no word — only 5 of the 7 are reachable here.

> **Corrected 2026-08-14.** This section previously said five of seven measure cleanly, that the
> map was `S→A`, and that **34 of 35** words land on a measured template with `time` falling back.
> All three were stale: the `S` anchor fix landed (`agreement_xy` 0.1636, n=40, `usable: true`), so
> `S` resolves to itself and `time` is on a measured template like everything else. Adding new
> vocabulary can re-activate `O→C`; nothing on the current 250 does.

### Status of the 2a assignments

`asl_handedness_250.json` → `passive_handshape` is **NOT DEAF-REVIEWED**. It is written from
published descriptions to unblock the rig. Three things need a reviewer, and they are flagged
in the data rather than smoothed over:

- **5 words contact the FOREARM, not a hand**: `arm`, `flag`, `morning`, `table`, `tree`. A
  handshape template does not say which surface is the target; base-location logic that
  assumes a hand will place these wrong.
- **`chair` and `helicopter` carry passive handshapes outside the unmarked set** (H and 3),
  marked `outside_unmarked_set`. Either casual signing violates the Dominance Condition there
  or the `2a` class label is wrong for those two.
- **6 rows are `conf: "low"`.** That is confidence in the *shape*, tracked separately from the
  lexicon's confidence in the *class* — a word can be confidently `2a` with a guessed shape.

If a `2a` word ever lacks an assignment, its block carries
`passiveHandshapeMissing: true` and the exporter warns. There are currently none.

---

## 7. Facial expression — the 468-point face stream (optional block)

The 75 body/hand points carry **no facial expression** (only ~11 coarse face
*positions*). Real non-manual grammar (eyebrows, mouth morphemes) needs MediaPipe's
**468-point FaceMesh** (`face_landmarks`) — a **separate stream.**

**It's recoverable WITHOUT retraining.** Recognition preprocessing dropped the face,
but the raw Kaggle source (and the S3 `cleaned/by_word/` parquet, before the
75-subset) still holds all 468 face points. The animation replays landmark motion —
it does **not** use the recognition model — so the face is purely a *data-extraction*
task on Salim's side, independent of the 30/250 training.

When face is included, each frame carries a parallel `face` block:

```json
"has_face": true,
"face_frames": [ [ [x,y,z], ... 468 total ... ], ... ]   // MediaPipe FaceMesh topology
```

- Same **y-down → flip** rule as §3.
- Coordinate space: face points are image-normalized. Decide together whether to
  keep them in the shared shoulder-centered space (face sits correctly above the
  shoulders) or renormalize to the head/face box for driving a dedicated face rig.
- ⚠️ **HONEST CAVEAT:** the dataset's **isolated-word** clips were signers performing
  single words — their facial expression is likely **neutral / inconsistent, NOT
  grammatical.** A face rig driven by this data will *move* but won't convey ASL
  facial grammar. **Build the rig against this format now; swap in intentionally-
  expressive face clips later.**
- Recognition stays face-free regardless — this block exists only for the avatar.

---

## 8. What Salim delivers (pre-animation → you)

1. **This contract.**
2. **Sample files now** — 2–3 real signs exported to the format in §1, so you can
   build + test the renderer today without the full pipeline.
3. **Later, at runtime:** just the **ordered word list** (e.g. `["hello","mom"]`). You already
   hold the per-word files, so you play `<word>.json` in that order and **blend the transitions
   yourself** (see the v3 banner up top). *(The old "Salim stitches one continuous stream" default is retired.)*
4. The per-word canonical clips are curated by Salim (one clean exemplar per word) — you
   never deal with picking clips or the raw noisy dataset.
   > **Corrected 2026-08-12.** This used to read "auto-selected by hand-tracking quality",
   > and that selection rule was itself the defect. Tracking quality is anti-correlated with
   > motion (`r = −0.464`, negative for 100% of words) because MediaPipe loses the hand that
   > moves, so maximizing it selected the RESTING hand on **249 of 250 words**. Selection is
   > now gated on the tracked hand being geometrically co-located with the *travelling* pose
   > wrist (median 0.088 shoulder-widths to its own limb vs 1.783 to the other), verified for
   > 250/250 exemplars. Coverage is deliberately **not** maximized — see §6.1.
   ⚠️ **Deaf review is still PENDING:** exemplars are verified to carry the signing hand, NOT
   verified as correct *signs*. A 2D overlay is being built so a Deaf reviewer can check the
   250; until then a mislabeled or odd exemplar renders faithfully. The `2a` passive
   handshapes (§6.1) are likewise unreviewed.

## 9. What you (animation) build

1. Read `frames` + `fps`, **and `segments[].synthesis`** — for the 87 two-handed words that
   block is required, not optional (§6.1). `segments` is only "for captions" on the 163
   one-handed words.
2. For each frame: **flip y**, (drop z for 2D), map the 75 landmarks onto your
   avatar's arm + hand rig, draw.
3. Handle NaN gaps (§6) — hold/interpolate, never blink. Expect to do this for **more than
   half the frames on two-handed words**; `synthesis.dominantCoverage` tells you how much.
4. **Smooth** the motion (moving-average or One-Euro filter) — raw landmarks jitter.
5. Play back at `fps`, loop/queue utterances.
6. (Owns the visual entirely: rig, style, colors, camera.)

## 10. Ownership of transitions & smoothing (v3: FINALIZED)

- **Transitions between signs = ANIMATOR (you).** You hold the per-word clips and blend
  interpolation frames between the end of one sign and the start of the next. *(This is the v3
  model — the old "Salim stitches one continuous stream" default is retired.)*
- **Smoothing = ANIMATOR (you)**, at render time (One-Euro / moving-average). Salim does not pre-smooth.

---

## 11. Building the avatar/rig itself (do this FIRST, in parallel)

*Building the character + rig is separate from the motion pipeline and can start
now — it needs almost no data from Salim. The motion stream (§1) only DRIVES the
finished rig later.*

To build the avatar you need just three things:
1. **This contract** — the joint layout (§2), connections, and the 468 face mesh (§7)
   define what bones/verts your rig must have.
2. **One neutral REFERENCE POSE** — a single static frame (75 body/hand points, +468
   face if rigging expression) in the coordinate space of §3. Model the proportions,
   build the skeleton + face rig, and test your retargeting against this static pose
   before any animation exists. *(Salim exports this from the dataset.)* **Derive
   per-limb scale factors from this pose** (not just a global shoulder-width scale) —
   real signers' arm-to-shoulder proportions differ from the avatar's, so the depth
   reconstruction (§4) needs per-limb calibration.
3. **Know the data is POSITIONS, not rotations.** The stream gives you point
   *positions* per frame — NOT bone angles. For a **skinned 3D avatar these are IK
   targets ONLY** (wrists, fingertips) — placing joints at arbitrary positions would
   change bone length and tear the mesh; only a simple stick-skeleton may place points
   directly. Fixed bone lengths are exactly why the z *sign* matters (§4). Architect the
   rig for position-driven IK. *(Resolved v4: positions, IK targets — no retarget on Salim's side.)*

The rig must expose (at minimum) these drivable joints: shoulders (11,12), elbows
(13,14), wrists (15,16), the 21 joints per hand (×2), and — for expression — the 468
face verts. Everything else (style, materials, camera, retarget solver) is yours.

## Worked example

Speech `"hello, I'm hungry"`:
1. ASR → text `"hello i'm hungry"`
2. text → glosses `["hello", "hungry"]`
3. resolve → `hello` clip (30 frames) + 8 transition frames + `hungry` clip (32) →
   `frames` of length 70
4. → you render 70 frames @ 30 fps (~2.3 s) of the avatar signing hello then hungry.

---

## Open decisions to settle together
- [x] **Delivery unit = PER-WORD JSON files** (v3 finalized — see banner). Encoding = JSON.
- [x] **Transitions + smoothing = ANIMATOR** (v3 finalized — see §10). ← resolved
- [x] **2D debug overlay first, then 3D** — animator builds a 2D landmark overlay as a debug view (isolates data-vs-retarget bugs), then drives the existing 3D Avaturn rig (54 joints, 72 ARKit blendshapes).
- [x] **Passive-hand synthesis for two-handed signs = per-segment `synthesis` block** (§6.1,
      2026-08-12). `2s` mirrors the dominant handshape; `2a` uses an assigned unmarked
      handshape at a named contact target. 21-point templates ship in
      `handshape_templates.json` with a `S→S`, `O→C` `resolution` map — **neither entry fires on
      the current 250** (corrected 2026-08-14; this line read `S→A` until then).
- [ ] ⚠️ **Passive TRAJECTORY is never synthesized — REOPENED 2026-08-14 for class `2a`.** This
      said both wrists are real pose data, so play the recorded passive wrist and mirror only the
      handshape. That holds for `2s`. It does **not** hold for `2a`: measured across all 35 `2a`
      words, the recorded passive wrist sits a median **1.56 shoulder widths** from the dominant
      wrist (range 0.80–2.22), and only 1 of 35 is within 1.38. The arm is not hanging — it is a
      median 0.34 sh.w. below its own shoulder, never past 0.75 — it is raised on its own side of
      the body, because GISLR recorded one hand per participant and the signer had no reason to
      form a base. A proximity filter therefore strands 35/35. For `2a`, **ignore
      `passiveWristIndex` and place the base from `asl_2a_base_placement.json`** (anchor to the
      dominant hand's own trajectory, then hold static). `2s` is unchanged.
- [ ] Avatar style — abstract skeleton/hands vs a stylized character?
- [ ] v2: add the 468-point face stream for expression — in or out of scope?
- [ ] Do the 5 forearm-contact `2a` words (`arm`, `flag`, `morning`, `table`, `tree`) need a
      forearm target surface in the rig, or can they be approximated at the wrist? (§6.1)

---

## 12. The extended gloss — where ASL grammar enters (NEW 2026-08-24)

### The problem this fixes

A gloss has been a bare English word: `"sick"`. That is enough to select a sign and nothing more.
But **ASL grammar is not carried by word order alone.** Questions, negation and topicalisation are
marked on the **face**, *simultaneously* with the manual sign. A flat list of English words cannot
express any of them — which is why the honest description of the current system is that it
**plays ASL signs; it does not produce ASL** (see `AVATAR_LIMITS.md` §1).

Concretely, today a statement and a yes/no question are the **identical** gloss sequence. There is
no way to tell them apart in our output.

### Why this can't come from data — and doesn't need to

§7 explains that the 468-point face stream is recoverable upstream (recognition dropped it; the
raw source still has it). **That gives a face channel, not face grammar.** §7's own caveat is the
reason: the corpus is *isolated-word* clips, so the signers' expressions are neutral and
inconsistent rather than grammatical. Recovering all 468 points yields a face that **moves without
meaning anything.** No amount of retraining changes that — the grammar was never performed.

So the non-manuals have to be **generated from rules on the production side**, keyed off the input
sentence we already parse. That needs **no data at all** — only a rule and a rig. This is the one
place in the project where the production direction can carry linguistic structure that the
recognition direction cannot.

### The format — additive, a bare string stays valid forever

```json
"glosses": [
  "hello",
  {"gloss": "sick", "nonmanual": "q"},
  {"gloss": "please", "hold": 0.25}
]
```

Each `segments[]` entry gains the same optional keys:

```json
{"gloss": "sick", "start": 57, "end": 75, "nonmanual": "q", "synthesis": { ... }}
```

| Key | Type | Meaning |
|---|---|---|
| `gloss` | string | **required.** The sign, as in `vocab_250.json` |
| `nonmanual` | string \| absent | `q` · `wh` · `neg` · `top` — see below |
| `hold` | number \| absent | extra **seconds** frozen on the final pose (prosody / emphasis) |

| `nonmanual` | Render as |
|---|---|
| `q` | yes/no question — **brow raise**, held for the whole marked span |
| `wh` | wh-question — **brow furrow** + slight head tilt |
| `neg` | negation — **headshake** across the marked span |
| `top` | topic — brow raise on the topicalised element **only** |

### Rules for consumers

1. **A bare string is valid input, permanently.** `["hello","sick"]` must never stop working.
2. **Absent means absent.** When no non-manual is set, the keys are **omitted entirely** — not
   emitted as `null`. A bare-gloss run produces byte-identical output to the pre-§12 format;
   verified by direct comparison, frames and segments both.
3. **Ignoring the keys is legal.** A renderer with no face rig drops them and behaves exactly as
   before. Nothing breaks; the sentence is simply ungrammatical, as it is today.
4. **An unknown `nonmanual` is an ERROR, not a fallback.** `parse_gloss` raises. A typo'd marker
   that silently renders as neutral is a sentence that quietly means something *else* — worse than
   a crash, because nothing downstream can detect it.
5. **A non-manual spans its segment**, from `start` to `end`. Multi-sign spans (a headshake across
   a whole clause) are **not yet expressible** — mark each affected gloss. Noted as a known gap.

### What this asks of the rig — decide before finalising it

**Two channels: brow (raise / furrow) and head rotation (shake, tilt).** That is all four
non-manuals above.

⚠️ **This is time-critical.** Retrofitting a face onto a finished rig costs far more than planning
two channels into it now. If the rig is finalised without them, §12 is dead for a year and the
system stays at "plays signs."

- [ ] **Ghozlan:** can the rig carry a brow channel and head-rotation channel? If not, what would it take?
- [ ] **Deaf review:** are these four markers the right first set, and are the renderings correct?
- [ ] Multi-sign non-manual spans — needed for v2?

**Implementation:** `parse_gloss()` / `NONMANUALS` in `gloss_to_motion.py`. Accepts both forms in
one list; `stitch()` carries the extras through to each segment.

---

# PART B — FULL SPEECH → SIGN PIPELINE: every phase in detail

_Added 2026-07-28. Parts 0–11 above pin the animation hand-off. This part details EVERY phase end-to-end — goal, input/output, tools, how, effort, gotchas — plus a 5-day plan for the 250-word demo._

## The complete data flow
```
[mic] → Phase 0 CAPTURE → Phase 1 ASR (speech→text) → Phase 2 TEXT→GLOSS →
        Phase 3 GLOSS→MOTION (landmark stream) → Phase 4 RENDER avatar → Deaf viewer
        (Phase 5 face / non-manuals = optional v2)
```

## The asset you ALREADY have (this is why the demo is fast)
You already own **landmark sequences for all 250 signs** — `cleaned/by_word/<word>/sequences.npz`, produced for recognition training. Because the avatar is **driven by landmark playback** (§1), the animation source for **ASL-250 already exists** — no recording needed for the demo.
⚠️ **For LSL there is NO such data** — you must record it first (see the signer-count note Salim keeps separately). The 5-day plan below is the ASL-250 demo using existing data; LSL is gated on data collection.

## Phase 0 — Audio capture
- **Goal:** mic → discrete spoken utterances. **In:** microphone. **Out:** one audio buffer per utterance.
- **Tools:** browser **Web Audio API** + a VAD, or Python `sounddevice` + `webrtcvad`.
- **How:** stream audio; detect speech start/end with a voice-activity detector (or energy + ~0.6 s silence = utterance end); emit the chunk.
- **Effort:** ~0.5 day. **Gotcha:** background noise, mic latency, where to cut utterances.

## Phase 1 — ASR (speech → text)
- **Goal:** audio → spoken-language text. **In:** audio. **Out:** transcript (+ confidence).
- **Tools:** **Whisper** (`faster-whisper`, local, best quality, **supports Arabic** — key for Lebanese-Arabic → LSL), or the **Web Speech API** (free, real-time, `ar-LB` / `en-US`), or cloud ASR.
- **How:** feed the utterance to the recognizer; take transcript + word confidences.
- **Effort:** ~1 day. **Gotcha:** Lebanese-Arabic dialect accuracy — Whisper-large is the safe bet; test on real speakers.

## Phase 2 — Text → gloss sequence (the linguistic step)
- **Goal:** spoken sentence → ordered **glosses restricted to your vocab**. **In:** text. **Out:** JSON gloss list (+ per-gloss confidence).
- **Tools:** an LLM (Gemini/Claude) — the SAME infra as `grammar_eval.py`, just **reversed** (sentence → glosses instead of glosses → sentence).
- **How:** prompt the LLM to emit glosses that exist in the vocab, in sign order (topic-comment; drop "the/is/am"; map synonyms to the nearest in-vocab gloss; out-of-vocab → fingerspell or nearest concept). Constrain output to the vocab list.
- **Effort:** 1–2 days. **Gotcha:** this is reverse-SLT and is linguistically hard — an LLM gives a good *demo*, not correct grammar. **LSL grammar ≠ ASL grammar ≠ Arabic grammar** → needs LSL rules + Deaf review for real quality.

## Phase 3 — Gloss → motion data
> **v3 note:** Salim's side now STOPS at the **per-word clip dictionary** (`build_sign_clips.py` → `gloss_to_motion.py --per-word`). The concatenation + transition frames are the **ANIMATOR's** job (top banner), NOT Salim's. The "stitcher" described below is the RETIRED per-utterance model — kept only for reference.
- **Goal:** gloss list → one continuous landmark stream (the §1 format). **Out:** §1 JSON.
- **Tools:** a **canonical-clip dictionary** (one clean landmark exemplar per gloss) + a **stitcher**.
- **How:** (1) build the dictionary — for ASL-250 pick one clean `(T,75,3)` exemplar per word from your existing `by_word/` data (Deaf-reviewed ideally); for LSL use YOUR recorded clips. (2) concatenate each gloss's clip with **interpolated transition frames** (~8, ease-in/out — co-articulation). (3) normalize to shoulder-centered space (§3), drop/keep z per §4.
- **Effort:** 2–3 days. **Gotcha:** isolated-word clips have neutral faces + no co-articulation; transitions must be smoothed; the dictionary needs Deaf review for correctness.

## Phase 4 — Animation / rendering
- **Goal:** landmark stream → visible signing avatar.
- **Tools:** **2D skeleton** (Canvas / OpenCV / SVG) for the MVP; **3D rigged avatar** (Three.js) later.
- **How:** per frame — **flip y** (§3), drop z for 2D (§4), place the 75 joints, draw MediaPipe `POSE_CONNECTIONS` + `HAND_CONNECTIONS` (§2), **smooth** (One-Euro / moving average), **hold or interpolate NaN gaps** (§6). Play back at `fps`.
- **Effort:** 2D skeleton ~1–2 days (reuse `live_demo.py`'s drawing code); **3D rigged avatar = weeks**.
- **Gotcha:** y-flip (or the avatar signs upside-down), jitter, NaN blink.

## Phase 5 — Face / non-manuals (v2, optional)
- The 468-point FaceMesh stream (§7). Recoverable from raw data without retraining — **but** the isolated-word clips have neutral/inconsistent faces, so a face rig will *move* without conveying grammar. **Defer to v2.**

## Can we do 250-word speech → sign in 5 days?
**Yes — for a landmark-driven 2D-avatar DEMO that reuses the existing ASL-250 landmark data.**

| Day | Deliverable |
|---|---|
| 1 | Audio capture + ASR (Whisper or Web Speech) + utterance segmentation |
| 2 | Text→gloss LLM (vocab-constrained to the 250; reversed `grammar_eval`) |
| 3 | Per-word clip dictionary from `by_word/` (`--per-word`) → hand the 250 JSONs to the animator |
| 4 | 2D skeleton renderer (reuse `live_demo.py` drawing) + smoothing + NaN handling |
| 5 | End-to-end wire-up (speech → avatar) + test + polish |

**NOT possible in 5 days:** a rigged 3D / photorealistic avatar; correct LSL grammar; facial non-manuals; and **anything LSL** — that's gated on recording the LSL dataset first. The 5-day demo runs on your existing **ASL-250** landmarks.
