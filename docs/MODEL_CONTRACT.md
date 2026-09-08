# Model → Frontend Handoff Contract

**The trained sign-recognition model and everything the frontend needs to run it.**
Backend Track A (dataset → train → export) is **complete**. This is the interface. If the frontend follows this exactly, live inference will match the ~0.88–0.94 accuracy we measured. The single most common way to break it is a normalization mismatch — see §3.

Owner: Salim (backend/ML). Questions on landmark layout/normalization → also loop in the preprocessing teammate (they own §3).
Model version: `mvp30 v1` · exported 2026-07-15 · single model (fold 0, 0.9386 on unseen test signers).

---

## 1. The files
From Google Drive → `web_model.zip` (~4 MB unzipped):
```
model.json              # graph topology  (~197 KB)
group1-shard1of1.bin    # weights         (~4 MB)
```
It's a **TF.js graph model**. *Part* of the feature engineering is **baked into the model** as its first layer (`PreprocessLayer`) — you do NOT reimplement these:
- **z-drop** — the model uses only x,y internally (you still send 3 channels; see §2).
- **velocity + acceleration** — the model derives frame-to-frame motion itself. Just feed positions.
- **NaN / padding masking** — see §2.

> ⚠️ **What is NOT baked in: the shoulder-midpoint normalization (§3).** That runs in preprocessing *before* the model, so **the frontend must do it.** Where this doc says "feed the model landmark coordinates," it means coordinates you have **already normalized per §3** — NOT raw MediaPipe/pixel coordinates. Skipping §3 because "the model handles preprocessing" is the #1 silent accuracy killer.

Load it:
```js
import * as tf from '@tensorflow/tfjs';
const model = await tf.loadGraphModel('/models/mvp30/model.json');
```

---

## 2. Input tensor — shape `[1, 64, 75, 3]`, dtype `float32`

| Dim | Size | Meaning |
|---|---|---|
| batch | 1 | one window at a time |
| **frames** | **64** | sliding window length — **this is frontend task #20's window size.** Buffer the last 64 MediaPipe frames. |

**Window stride (frontend #20):** don't re-run the model every frame. Keep a rolling 64-frame buffer and run inference **every ~8–16 frames** (≈2–4 predictions/sec at 30 fps). The gloss buffer + debounce (frontend #18) collapses the repeated predictions of a held sign into one emission. Smaller stride = snappier but more CPU; 12 is a fine default.


| **points** | **75** | landmark layout, fixed order — see below |
| **coords** | **3** | `x, y, z` per point |

### The 75-point layout (exact order — must match)
| Slots | Landmarks (MediaPipe Holistic) |
|---|---|
| `0–32` | **Pose** — pose landmarks 0–32 |
| `33–53` | **Left hand** — left_hand 0–20 |
| `54–74` | **Right hand** — right_hand 0–20 |

- **Face/lips are NOT used.** Only pose + both hands.
- The `z` channel is included in the tensor but the model **ignores it internally** (it uses x,y only). Send the real `z` from MediaPipe, or zeros — either works. Just keep the 3-channel shape.
- **Missing/undetected landmarks** (e.g. a hand out of frame): set those points to **`NaN`**. Internally the model builds a detection mask, then replaces NaN with 0 — exactly as in training (landmark-dropout augmentation NaN'd points the same way). So NaN is the value it expects for "not detected"; don't hand-substitute 0 yourself.
  - **Sharp edge — pose point 0 (the nose) is special.** The per-frame mask is keyed off point 0: if point 0 is NaN, the model treats that **entire frame as empty padding**. So only NaN point 0 when the *whole frame* is genuinely absent — never on a real frame where just the nose landmark is missing.
- **Keep the window full of real frames.** Training only ever saw NaN as *end-padding* on clips shorter than 64. A live buffer should be **64 detected frames** — don't run inference until you have 64 real frames, and don't inject NaN-only padding frames mid-stream.

---

## 3. Normalization — ⚠️ THE CRITICAL STEP (frontend #22 / #26)

Before stacking frames into the tensor, apply the **exact same normalization the preprocessing pipeline used**. If this doesn't match training, the model gets out-of-distribution input and accuracy collapses silently (no error, just wrong predictions).

**The spec (confirmed with the preprocessing teammate, 2026-07-15):**
1. **Center** every landmark on the **shoulder midpoint** — i.e. `(left_shoulder + right_shoulder) / 2` (pose slots 11 & 12). Subtract that point from all landmarks each frame.
2. **Scale** by the **shoulder width** (distance between pose 11 and 12).
   > NOT nose-centered, NOT raw 0–1 pixel coords. Shoulder-midpoint center + shoulder-width scale.

**Action for frontend:** get the teammate's exact normalization code/formula and port it 1:1 to JS. Task **#26** (verify live == training normalization) is the checkpoint — test by feeding a known recorded clip through both and confirming identical arrays. **Do not skip #26.**

### ✅ #26 now has a tool — `golden_parity.py` (built 2026-09-08)

You no longer have to invent the test. The fixtures are generated from the **shipping**
`live_demo.normalize`, so passing them means matching the code that trained the model.

```bash
python golden_parity.py --emit      # golden_fixtures.json  (committed — 10 cases + 2 invariants)
python golden_parity.py --emit-js   # golden_parity.mjs     (the frontend half)
node golden_parity.mjs              # run it
```

**Point `golden_parity.mjs` at your real `normalize` — an `import`, not the placeholder copy
inside it.** Editing that copy until it passes tests the harness against itself.

**Measured:** the JS reference implementation agrees with Python to **max 2.44e-7**, against a
tolerance of 1e-6. That gap is float32-vs-float64, and it is the whole budget you have — a
genuine logic difference lands orders of magnitude above it.

**Four wrong-but-plausible implementations were checked to FAIL**, because a parity test that
cannot fail is decoration:

| the plausible mistake | what the harness says |
|---|---|
| centre on the **nose** (pose 0) instead of the shoulder midpoint | `FAIL shoulder midpoint is the origin` |
| centre correctly but **never scale** | `FAIL shoulder distance is exactly 1` |
| substitute **0** for a missing landmark | `FAIL nan_hand_is_PRESERVED_not_zeroed — 42 NaN mismatches` |
| **keep** a frame whose shoulders are missing instead of dropping it | `FAIL left_shoulder_nan_DROPS_the_frame — NOT dropped` |

⚠️ **The third and fourth are the ones prose cannot convey.** A missing hand must stay `NaN`
through normalization — writing 0 places it at the shoulder midpoint, a real and plausible
position, which is how **19,002 hand blocks once shipped as `[0,0,0]`**. And a frame with either
shoulder missing must be **dropped entirely**, not passed through in raw 0–1 pixel coords.

📌 **Two invariants you can assert on your own output with no fixture at all:** after
normalization the shoulder midpoint is `(0,0)` and the shoulder distance is exactly `1`.
Normalization is also **idempotent**, so applying it twice is harmless — don't "fix" a double
call by deleting a needed one.

*(`--with-model` adds a stage-3 fixture through the real SavedModel. Logits are compared at
atol 2e-3 because TF.js kernels differ, but the **argmax must match exactly** and the
confidence within 5e-3 — logits agreeing while the prediction flips would pass nothing.)*

---

## 4. Output tensor — shape `[1, 30]`, **raw logits**

The model outputs **logits, not probabilities.** You must apply softmax:
```js
const logits = model.predict(input);          // [1, 30]
const probs  = tf.softmax(logits, -1);         // [1, 30]
const data   = await probs.data();
const idx    = probs.argMax(-1).dataSync()[0]; // 0–29
const conf   = data[idx];                      // confidence 0–1
```

### Label order (index → word) — from `vocab_30.json`
```
0 hello   1 bye     2 yes     3 no      4 please   5 thankyou
6 go      7 store   8 home    9 wait
10 water  11 milk   12 drink  13 food   14 hungry  15 thirsty
16 mom    17 dad    18 happy  19 sad    20 sick    21 hot   22 sleepy  23 potty
24 book   25 dog    26 cat    27 car    28 like    29 look
```

---

## 5. Confidence gate (frontend #27)

Per-window raw accuracy is ~0.88; the gate is what turns that into a clean user experience by dropping shaky windows.

- **Global threshold: emit a word only if `conf ≥ 0.60`.** Below that → treat as "no confident sign," show nothing.
- **Weak words — extra caution:** `go, car, book, dog, look, hot` are the most confusable (consistently lowest per-word accuracy). For these, require **2 consecutive windows** to agree on the same word before emitting.
- Tune these against live video (#27). 0.60 is the validated starting point, not a magic number.

---

## 6. What this model is and isn't

- It's an **isolated-sign classifier** over a sliding window — it names the single sign in the current 64-frame window. It is NOT continuous sentence recognition.
- The "sentence" feel comes from the **downstream gloss buffer + grammar reordering** (separate frontend tasks) — e.g. buffered `go, store` → "I will go to the store." That layer sits *after* this model.
- **No-sign/background class** is not in this model yet (that's backend Phase 6, index 30 when added). Until then, the confidence gate in §5 is what suppresses no-sign windows.

---

## 7. Handoff checklist for the frontend team
- [ ] Load `model.json` + `.bin`, confirm `model.predict(zeros([1,64,75,3]))` returns `[1,30]`.
- [ ] Buffer 64 frames of MediaPipe Holistic pose + both hands in the §2 layout.
- [ ] Port the §3 normalization from the preprocessing teammate's code, 1:1.
- [ ] **Run task #26**: feed one recorded clip through browser + training pipeline, assert identical input arrays. ← gate before trusting any live number.
- [ ] Apply softmax, argmax, map via §4 label order.
- [ ] Implement the §5 confidence gate.
- [ ] Wire output into the gloss buffer / grammar layer.
