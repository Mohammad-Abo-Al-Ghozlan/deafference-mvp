# Deafference — How the Two Phases Work (Technical Explanation)

**Purpose:** a meeting-ready, technical explanation of the two directions we built —
**Sign → Speech** (recognition) and **Speech → Sign** (avatar) — plus the honest
roadmap to continuous (sentence-level) signing.

**One-line summary:** Deafference is a two-way ASL translator. One direction turns a
Deaf person's **signing into spoken English**; the other turns a hearing person's
**speech into sign animation**. Both run on the **same 75-point MediaPipe landmark
representation**, and both are built around a frozen **250-word vocabulary**.

---

## The shared foundation (both phases use this)

We do **not** work on raw video. Every frame of camera/clip is reduced by **MediaPipe
Holistic** to **75 body/hand landmarks**:

| Landmarks | Count | What                                        |
| --------- | ----- | ------------------------------------------- |
| `0–32`    | 33    | body pose (shoulders, elbows, wrists, head) |
| `33–53`   | 21    | left hand                                   |
| `54–74`   | 21    | right hand                                  |

Each landmark is `(x, y, z)`. We normalize to a **shoulder-centered space** (origin =
midpoint of the shoulders, scale = shoulder width) so the system is independent of the
person's size and position in frame. This landmark stack is cheap, privacy-preserving
(no video stored), and robust to lighting/background — and it is the same input the
research literature uses for pose-based sign recognition.

**Dataset:** the **GISLR / PopSign** set (Google/Kaggle) — **250 signs, 21 signers,
MediaPipe landmarks only (no video)**. This is both our recognition training data _and_
our animation source (see Phase 2).

---

# PHASE 1 — Sign → Speech (recognition)

**Goal:** a Deaf person signs to the webcam → the app recognizes the signs → speaks a
natural English sentence.
python live_demo.py --vocab250 --debug ------------------------------------------------------------------

### The pipeline, stage by stage

```
webcam frame                        1280x720 capture, downscaled to <=640 px wide for tracking
  → MediaPipe Holistic            → 75 landmarks x (x,y,z) = 225 numbers per frame
                                     (33 pose + 21 left hand + 21 right hand)
  → motion-based SEGMENTATION      → isolate ONE sign: 0.30 s min, 5.0 s max; ends after
                                     0.65 s with no hand OR 0.50 s of stillness (motion
                                     < 0.02 shoulder-widths); 8 pre-roll frames keep the
                                     sign's onset; 0.40 s cooldown before the next sign
  → NORMALIZE (shoulder-centered)  → origin = midpoint of landmarks 11 & 12; identical to
                                     training (no distribution drift)
  → RESAMPLE to 64 frames          → fixed-length tensor (64, 75, 3) = 14,400 floats
  → 4-FOLD ENSEMBLE (TF SavedModels) → 4 models x 2 (mirror TTA) = 8 forward passes,
                                     averaged softmax over 250 classes
  → DECISION ENGINE (3 gates)      → L1: conf >=0.70 & margin >=0.30 & quality >=0.60 -> commit NOW
                                     L2: conf >=0.50 & margin >=0.18 -> commit after 2 agreeing previews
                                     L3: otherwise -> never auto-commit; show top-3 candidates
  → GLOSS BUFFER + GRAMMAR         → assemble committed words into a sentence
  → TEXT-TO-SPEECH                 → spoken English
```

All segmentation timings are in **seconds** and converted to frame counts from the live
camera fps each loop — so the feel is identical at 10 fps or 30 fps, with no per-machine tuning.

### The model

- **Task type:** ISLR — _Isolated_ Sign Language Recognition. One segmented clip → one
  of 250 labels. It is a **classification** model, not a sequence model.
- **Architecture:** a **1D-CNN + Transformer** over the landmark sequence.
- **Ensemble:** 4 independently-trained folds; at inference we **average their softmax**
  (more robust than any single fold).
- **Accuracy:** **0.7755 4-fold ensemble** on held-out _unseen signers_ — the honest,
  deploy-relevant number. **Directly measured 2026-08-06** on the test split (13,998
  samples, 3 unseen participants), not estimated: per-fold 0.7544 / 0.7570 / 0.7545 /
  0.7615, mean single 0.7569, so **ensembling is worth +1.86 points**.
- **Top-5 accuracy: 0.9395.** With 250 classes the correct word is in the top 5 **94%**
  of the time. This is the ceiling of the tap-to-fix UX below — which is why the L3
  "show the top candidates" gate is a design decision, not a workaround.
- **The distribution matters more than the mean:** per-word **median 0.8246** (5 points
  *above* the mean), **133 of 250 words ≥0.80**, 182 ≥0.70, and only **16 below 0.40**.
  Half the vocabulary is above 82%; a small tail drags the average down.
- **The weak tail has two causes, and one is fixable:** `nap / awake / mouth / owie` are
  **face-region signs**, and our 75-point layout carries **no face landmarks** (33 pose +
  42 hands; MediaPipe's 468 face points are discarded). The rest — `give / go / there /
  person` — are simple deictic signs that look alike without fine detail. Adding face
  landmarks targets the first group specifically.
- ⚠️ **All of the above are POOLED over 3 test signers. Read the next bullet before quoting
  any of them.**
- **The mean hides a 51-point spread, and it is not signer skill — it is a recording artifact.**
  Measured 2026-08-13 on one fold-0 model over the **7 signers it never trained on** (the 4
  val-fold participants plus the 3 test ones):

  | signer | L-block | R-block | acc | layout |
  |---|---|---|---|---|
  | 26734 | 0.02 | 1.00 | **0.823** | pure R |
  | 2044 | 0.01 | 1.00 | 0.806 | pure R |
  | 37779 | 0.00 | 1.00 | 0.780 | pure R |
  | 53618 | 0.13 | 0.88 | 0.707 | R + contamination |
  | 32319 | **1.00** | 0.04 | 0.614 | pure **L** |
  | 34503 | **1.00** | 0.08 | 0.577 | pure **L** |
  | 29302 | **0.48** | **0.99** | **0.314** | **both blocks** |

  Pooled over all seven: **0.666**. Left-recorded signers lose ~20 points; the one signer whose
  clips populate *both* hand blocks loses ~50. **The test split contains only R-dominant signers
  (L-contamination 0.13 / 0.00 / 0.01), so no test-set number — including 0.7755 — can see
  either penalty.** For a new user the honest expectation is **0.6–0.8**, not 77.5%.

  Caveat on scope: the per-signer breakdown was run on a single fold-0 model, not on the
  4-fold ensemble, so the ensemble's own spread is unmeasured. Treat the spread as applying until
  someone measures otherwise.

- **🛑 The layout explanation was tested and refuted (2026-08-14) — the spread is real, its cause
  is unknown.** An earlier version of this section named canonicalization as the fix. The corpus
  was rebuilt canonically (every signing hand in one block) and fold 0 retrained identically:
  the three signers the fix targeted moved **−0.0064**, the four it did not target moved
  **−0.0067**, and 29302 — the 0.314 signer the whole theory existed to rescue — moved
  **−0.0002**. No differential effect. Layout *correlates* with the spread; it does not cause it.
  So **there is no known fix, and the 0.6–0.8 expectation above is the number to quote** rather
  than a temporary state pending a retrain. Detail: `SESSION_HANDOFF.md` §0.5.

  Do not over-read this: the *same* geometry, used to choose which hand the **avatar** animates,
  is separately verified and correct (137/250 words were rendering the resting hand; now 1). Only
  the accuracy claim died.
- Reproduce any of these: `training/ensemble_eval.py --all-words` → `ensemble_eval_250.json`
  (not currently in the repo — the 0.7755 run was Kaggle-side and its JSON was never
  downloaded, so the four per-fold figures above cannot be re-checked locally; the four
  SavedModels in `artifacts_250/` are what the demo actually loads).
  Per-signer: `training/per_signer.py --data-dir <corpus> --weights <fold0 .h5>`.
- **Trained on Kaggle** (GPU); the demo ships the exported **TF SavedModels**
  (`artifacts_250/savedmodel_fold0..3`).

### The engineering that makes it usable live

- **Segmentation:** we watch hand motion to detect a sign's start/end (motion threshold,
  min/max duration, hand-presence, cooldown between signs).
- **Pre-roll trim:** we drop the static "wind-up" frames so the classified clip is
  motion-dominated (this materially improved accuracy on the live feed).
- **3-level decision engine (`decide_commit`):** L1 = strong & instant (high confidence +
  margin + quality), L2 = medium (commit once stable across frames), L3 = reject → show
  the **top-5** so the signer can **tap 1–5 to correct**. This is why weak words are still
  usable in the demo.
- **Capture-quality coach:** on-screen warnings for dark frames / undetected hands, because
  the model only ever sees landmarks — bad tracking silently wrecks accuracy.

### How we produce _sentences_ today (important)

The recognizer classifies **one sign at a time**; a **grammar layer** then assembles the
committed signs into a first-person English sentence (gloss buffer → rule/LLM grammar →
speech). In the CSLR literature this is called **"constrained sliding-window sign
spotting + grammar,"** and it is the **recommended pragmatic approach** for a demo — it is
essentially what `live_demo.py` already does. It gives "sign known words in a row → a
sentence," which is good enough for the MVP.

### Status

**Demo-ready.** All 250 words load and are detectable (including the weak ones, via
tap-to-fix). The commit-latency bugs are fixed. This is currently our **one fully
working end-to-end demo.**

---

# PHASE 2 — Speech → Sign (avatar)

**Goal:** a hearing person speaks → the app produces **sign-language animation** a Deaf
person can read.
python demo_voice_to_sign.py ---------------------------------------------------------------------
python demo_voice_gui.py -------------------------------------------------------------------------

### The key idea (why we didn't need to record anything)

The avatar is driven by **landmark playback** ("Approach A"): our recognition training
data — landmark sequences for every sign — **doubles as the animation source.** We pick
one clean exemplar clip per word and replay its landmarks to drive an avatar. No new
motion-capture, no new recording.

### The pipeline, stage by stage

```
microphone                            16 kHz mono, press-to-talk (any length)
  → ASR (faster-whisper / Whisper)   → English text. 'base' model ~140 MB; loads ONCE
                                       (~2.9 s), then ~1.9 s per utterance
  → TEXT → GLOSS (Gemini, vocab-locked) → ordered ASL gloss list ["hello","mom",…],
                                       locked to the 250-word vocabulary
  → GLOSS → MOTION (gloss_to_motion.py) → per-word clip: 64 frames @ 30 fps = 2.13 s per
                                       sign, + 8 interpolated transition frames (0.27 s)
  → per-word JSON (75 positions/frame) → 225 floats per frame; ~122 KB per word;
                                       250 files = 31 MB total handoff
  → [friend's 3D avatar]              → renders the signing character
```'

**Measured end-to-end latency: ~2.2 s** from the moment you stop speaking to the avatar
signing (~1.9 s ASR + ~0.3 s gloss/clip-load/render), verified over three spoken sentences.

### The components we built

- **`sign_clips_250.npz`** — the per-word motion dictionary. Built on Kaggle from the
  GISLR landmarks: for each of the 250 words we select the **cleanest exemplar** (highest
  hand-tracking presence), normalized to the shoulder-centered space. Verified **250/250
  clean**.
- **`gloss_to_motion.py`** — turns a gloss list into motion. `--per-word` exports all 250
  words as individual JSON files + a `reference_pose.json`.
- **`speech_to_sign.py`** — the ASR → gloss → motion harness (Phases 1–3 of this
  direction).
- **`preview_signs.py`** — a 2D skeleton player to preview/QA the clips (debug overlay +
  Deaf-review harness). _(Note: a flat 2D preview cannot show depth motion — signs that
  move toward/away from the camera look flat in it but are correct in the data.)_

### The hand-off contract (v4) — what the avatar consumes

Each word is one JSON: **75 joint POSITIONS per frame** (not bone rotations),
shoulder-centered, `y` is image-down (the renderer flips it), missing joints = `null`.
Agreed division of labor with the animator:

- **We deliver:** 250 per-word JSON files (once) + `reference_pose.json` + the contract.
  At runtime we send only the **ordered gloss list**.
- **The animator builds:** the 3D avatar (Avaturn rig, ~54 joints). Landmarks are used as
  **IK targets** (a skinned rig can't just place joints). He **keeps our raw `z`** and uses
  its _sign_ to reconstruct out-of-plane (toward/away-camera) motion from known bone
  lengths — which is why depth-heavy signs render correctly in 3D even though `z` is noisy.
- **The animator also owns** transition-blending between signs and motion smoothing.

### Status

**Our side is DONE and handed off** (dictionary built, 250 JSONs + reference pose exported,
contract v4 sent). The animator is building the 3D avatar. Remaining joint step: connect
our runtime gloss list to his finished avatar.

---

# ROADMAP — from isolated words to real continuous signing

This is the part worth being precise about, because it's a common misconception.

### It is NOT "characters → words → sentences"

Those are **three separate tasks**, not a training ladder:

- **Characters** = _fingerspelling_ (the manual alphabet). A separate, optional module —
  useful only as a fallback for words outside our vocabulary. **Not a prerequisite.**
- **Words** = **ISLR** — what we have (the 250-sign classifier).
- **Sentences** = **CSLR** (Continuous Sign Language Recognition) — a **sequence-to-sequence**
  task on _connected_ signing, and a genuinely different, harder model.

### Why continuous is hard (and what actually blocks it)

- In real signing there are **no boundaries** — signs blur together, and the hands add
  non-lexical transition motion between them. Models trained on clean isolated clips
  **degrade** on connected signing.
- The classic fix (CTC loss, borrowed from speech recognition) needs **gloss-labeled
  continuous data** — and **for ASL that data essentially does not exist at scale.** The
  clean glossed continuous benchmarks (PHOENIX, CSL-Daily) are German and Chinese. The
  large continuous **ASL** corpora (YouTube-ASL ~984h, OpenASL, How2Sign) are
  **translation-only, no gloss.**
- **So the bottleneck is DATA, not models or compute.**

### Our two realistic tiers

- **Tier 1 (now):** what we already ship — sliding-window spotting over the 250 signs +
  grammar. Field-validated as the correct pragmatic demo approach. Cheapest highest-value
  upgrade: **add a "no-sign / background" class** at the next retrain to suppress
  transition-frame false positives.
- **Tier 2 (Phase-2 research):** do **not** build gloss-CSLR for ASL. Instead **fine-tune a
  pose-based foundation model (e.g. Uni-Sign) on gloss-free ASL translation data
  (YouTube-ASL / OpenASL / How2Sign)**. This matches our MediaPipe stack, needs only modest
  compute (~days on one GPU), and is where the field is heading.

### Deferred / parallel tracks

- **Recognition retrain** 0.757 → ~0.82–0.85 (independent quality lift; not required for
  the demo).
- **Deaf review** of the 250 animation exemplars (correctness QA).
- **LSL / Arabic** continuous data (ArabSign, Isharah) — the licensing/collection play that
  is our real long-term moat, since open commercial _ASL_ continuous data is a dead end.

---

## Meeting talking points (the short version)

1. **Two working directions**, both on one 75-landmark representation, one 250-word vocab.
2. **Sign → Speech:** MediaPipe → segment → 4-fold 1D-CNN+Transformer ensemble
   (**0.7755 pooled, top-5 0.9395**, unseen signers) → 3-gate decision engine → grammar
   → speech. **Demo-ready today.** If asked what a *single new user* should expect, say
   **0.6–0.8**: per-signer accuracy spans 0.314–0.823 depending on how the tracker recorded
   their hands, and the 3-signer test split only contains the easy configuration. Quoting
   77.5% as a per-user number is the one claim in this deck that would not survive a demo.
3. **Speech → Sign:** Whisper → gloss → replay per-word landmark clips → 3D avatar. **Our
   side done + handed off; animator building the rig.**
4. **Sentences today** = isolated words + grammar assembly (the validated pragmatic
   approach). **True continuous ASL is Phase-2**, blocked by data, solved by fine-tuning a
   pose foundation model on gloss-free ASL translation corpora — **not** by a
   characters→words→sentences ladder.
