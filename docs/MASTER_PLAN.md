# Deafference — Master Plan, Timeline & Kaggle Guide

**Updated 2026-07-30.** All training/data runs on **Kaggle** (GPU notebook), NOT Google Colab.
This is the single "what do I do, what does my friend do, and when" document.

---

## 0. Where we are right now

| Track | State |
|---|---|
| **Direction 1 — ASL sign → speech** (the live recognition demo) | ✅ **Demo-ready.** The "many tries to commit" bugs are fixed; all 250 words load; tap 1–5 fixes the weak ones. |
| **Direction 2 — ASL speech → sign** (the avatar) | ✅ **Fixed on disk 2026-08-13; zip built, not yet sent.** The "250/250 clean" that closed this out came from a check that could not fail; the export carried the **resting** hand (root cause R5 — the tracker loses the hand that *moves*, so selecting on tracking coverage selected for stillness). The 2026-08-12 fix was real but lived only in Kaggle output — the repo still held the broken export (28.8% coverage, 137 words missing the dominant hand) and `demo_voice_gui.py` was rendering it. Corrected clips copied in and re-exported 2026-08-13: coverage **76.2%**, resting hand **0.1%**, synthesis blocks **250/250**, native durations restored (was all-64). Bundle: `deafference_handoff_v7_CORRECTED.zip`. **Still to do: send it.** See `SESSION_HANDOFF.md` §0.4 §5. |
| **Retrain the 250 model** | ✅ **REOPENED AND WON 2026-08-27.** `--decimate 0.5` was the one positive after fourteen refutations. New shipping number: **0.7787 @ 30 fps / 0.7628 @ 7 fps** (4-fold canonical ensemble, test split) vs the legacy **0.7755**. The 30 fps gain is noise-level; the win is at **7 fps**, where the paired fold-0 A/B gave **+0.0218** and halved the frame-rate penalty (5.13 → 2.64 pts). **Requires `live_demo.py --canonical`.** Still refuted: more epochs, resting-hand masking, and canonicalization-for-accuracy (per-signer 0.314–0.823 is real but not caused by layout; 29302 remains **0.319** honestly). **GPU work now genuinely done; quota free.** See `SESSION_HANDOFF.md` §0.6. |

**Two people, two lanes:**
- **You (Salim):** the whole *data + pipeline* side — recognition, the per-word motion JSONs, the runtime glue, and (optionally) the retrain.
- **Your friend:** the *avatar only* — a rig that is **driven by** the per-word JSON you produce (position-driven puppet).

**✅ finished · 🟡 in progress · ⬜ not started · ⏳ later (2026-07-30):**
- ✅ Sign→speech live demo (tuned; all 250 words load)
- ✅ Speech→sign pipeline code (ASR → gloss → per-word motion)
- ⚠️ `sign_clips_250.npz` built on Kaggle — the original "250/250 clean" was wrong (see above);
  rebuilt 2026-08-12 with a signing-hand gate, now 250/250 verified on geometry
- ⚠️ 250 per-word JSONs + `reference_pose.json` exported → zipped
  (`deafference_animation_handoff.zip`) → sent to friend. **That copy carries the wrong hand
  and no `synthesis` block; a corrected export has to replace it.**
- ✅ Contract updated to **v4** (friend's review resolved)
- 🟡 Friend building the avatar (rig + JSON parser + IK)
- ✅ 2D preview / review tool (`preview_signs.py`) — animator's debug overlay + Deaf-review harness + local end-to-end stand-in (adversarially reviewed, 9 bugs fixed)
- 🟡 Deaf review of the 250 exemplars — tool ready (`preview_signs.py --review`); the review pass itself is pending
- ⬜ End-to-end integration with the friend's avatar (2D stand-in already works via `preview_signs.py --words`)
- ⏳ 250-model retrain (later, optional; §5)

---

## 1. Confirm with your friend NOW ✅ — yes, today

**Should you confirm something now? YES.** He's about to build the rig, and these points decide *how* he builds it — agreeing now avoids a rebuild later. None of it blocks you; you build the clips in parallel.

### A. The one that matters most — positions vs rotations
Your JSON gives **75 joint POSITIONS per frame `(x, y, z)`** — **not** bone rotations. Ask him:
> "Does your avatar animate from joint **positions** (place joints / IK targets), or does it need bone **rotation** curves?"
- **positions** → drop the files straight in. ✅
- **rotations** → he needs a retarget step (positions → angles via IK). Better he knows now than after wiring 250 files.

> ✅ **RESOLVED (2026-07-30):** he confirmed **positions** — landmarks used as **IK targets** (a skinned rig can't place joints directly). **No retarget step on your side.** (Contract v4 §11.3.)

### B. The format of each `<word>.json` he'll receive
- **75 points per frame**, layout: `0–32` body · `33–53` left hand · `54–74` right hand.
- **flip y** in the renderer (`y_render = -y`) — image coords are y-down, or the avatar signs upside-down.
- **drop z** for a 2D avatar (z is noisy); keep only x, y.
- **`null` = missing joint** (hands between/under signs) → hold the last pose or interpolate, never blink.
- **coordinate space = shoulder-centered** (origin = mid-shoulders, scale = shoulder width) — person/size-independent.
- **fps = 30.**

### C. The handoff model — agree on this
- **Once:** you give him the **250 per-word JSON files** + `reference_pose.json` + `SIGN_ANIMATION_CONTRACT.md`.
- **At runtime:** you send only the **ordered word list** `["hello","mom",…]`; his avatar plays `hello.json → mom.json → …`.

### D. Who owns what between the clips
- **Transitions between signs = HIS side** — he blends between consecutive per-word clips (this flips the old contract's "Salim stitches" default).
- **Smoothing = HIS side** — at render time (One-Euro / moving-average filter).

### E. He can start TODAY (he's not blocked waiting for you)
He can build the avatar's **skeleton/rig right now** from **`SIGN_ANIMATION_CONTRACT.md`** — its **§2** lists every joint + how they connect, its **§11** is a rig-building guide. He needs **zero** sign motions to build the puppet. To **test** that the rig bends correctly he needs the **reference pose** (one static frame), which you export the instant your Kaggle build finishes (Day 1–2). So: skeleton now from the contract → test retargeting once you hand him `reference_pose.json` → drop in the 250 motions when ready.

> **Note on "§" numbers:** in THIS file (`MASTER_PLAN.md`), *(§1)…(§6)* mean this file's own sections. When a section names the contract — *"`SIGN_ANIMATION_CONTRACT.md` §2/§11"*, *"contract §1"* — those are sections in the **contract** file (0–11), which is what your friend builds against.

---

## 2. The parallel timeline (your lane vs your friend's lane)

> Days are "working sessions," not calendar-locked. The point is what runs **in parallel** so nobody waits.

### Now (before Day 1)
- **You:** confirm the §1 checklist with your friend. (Sign→speech demo already works — nothing to do there.)
- **Friend:** start building the avatar rig from `SIGN_ANIMATION_CONTRACT.md` §2/§11 — he needs almost nothing from you to begin.

### Day 1
- **You:** on Kaggle, run `build_sign_clips.py` → `sign_clips_250.npz` → download it to the project root (§4).
- **Friend:** write the JSON parser against contract §1; keep building the rig.

### Day 2
- **You:** `python gloss_to_motion.py --word hello` → send him **one** file to confirm the format works; then `python gloss_to_motion.py --per-word` → hand him the **full 250-word library + `reference_pose.json`**.
- **Friend:** retarget — drive the rig from `hello.json` and confirm it signs "hello" correctly.

### Day 3
- **You:** wire the runtime — `speech_to_sign.py` (mic → ASR → gloss → ordered word list); sanity-check the motion with the 2D preview.
- **Friend:** play a **sequence** of per-word JSONs in order + blend transitions + smoothing.

### Day 4
- **You:** integration — speech in → your gloss list → his avatar plays it; end-to-end test together.
- **Friend:** join your gloss-list output to his player.

### Day 5
- **You:** demo polish — captions, fallback, and the sign→speech side.
- **Friend:** visual polish (style, camera, timing).

**Critical path = your Day 1 → Day 2.** Once your friend has the library, both lanes run independently until integration on Day 4. **The retrain (§5) is NOT on this timeline — it's a separate, later, optional task.**

---

## 3. The runtime data flow — what's DONE vs STILL TO DO

**Legend:** ✅ done & tested · 🟡 code done, runs for real once the Kaggle clip-build (§4) is done · ⬜ not built yet

```
[mic] → speech_to_sign.py
   Phase 1  ASR (faster-whisper)   audio → "hello mom I am hungry please"    ✅ DONE
   Phase 2  text → gloss (LLM)     → ["hello","mom","hungry","please"]       ✅ DONE
   Phase 3  gloss → per-word motion JSON  (gloss_to_motion.py)               ✅ DONE — sign_clips_250.npz built; 250 JSONs exported
                 ↓  hand friend the 250 JSONs once; at runtime send the ordered word list
   [friend's avatar]  plays hello.json → mom.json → …  + blends transitions  ⬜ FRIEND'S SIDE — not built
                 → Deaf viewer sees signing
```

**So, concretely:**
- ✅ **Done (you):** Phase 1 ASR, Phase 2 text→gloss, Phase 3 exporter — all tested.
- ⚠️ **Redone (you), needs re-sending:** `sign_clips_250.npz` and the 250 per-word JSONs. The
  first export's "250/250 clean" was a check that could not fail (R5 — wrong hand on 249/250).
  Rebuilt and verified; the zip the animator has must be replaced with the new one.
- ✅ **Preview/review (you):** `preview_signs.py` renders any word/sequence and runs the Deaf-review pass (`--review`) — the friend's debug overlay + a local end-to-end stand-in.
- 🟡 **In progress (friend):** the avatar that plays the JSONs (rig + IK + transition blending).

- **One-time handoff:** you give him `animation_handoff/words/*.json` (250 files) + `reference_pose.json` + the contract.
- **Every utterance at runtime:** you send only the **ordered word list**; his avatar already has the motions.

---

## 4. KAGGLE — build the per-word clips (`sign_clips_250.npz`)  ·  ~30 min, one time

This is the only Kaggle step the **animation** side needs.

### One-time account setup
1. Go to **kaggle.com** and sign in (Google account is fine).
2. **Verify your phone** (unlocks GPU + Internet): top-right **avatar → Settings → scroll to "Phone Verification" → enter number → enter the SMS code.**
3. That's it for the account.

### Create the GPU notebook
4. Top-left **"+ Create" → "New Notebook"** (or go to **kaggle.com/code → "New Notebook"**).
5. Open the right-hand **settings panel** (the "⋮" / "Notebook options" on the right):
   - **Accelerator → "GPU T4 x2"** (or P100).
   - **Internet → On.** (Greyed out? Your phone isn't verified — do step 2.)
6. Top menu **"Add-ons" → "Secrets" → "Add a new secret"** twice:
   - name `AWS_ACCESS_KEY_ID`, value = your key
   - name `AWS_SECRET_ACCESS_KEY`, value = your secret
   - make sure both are **attached** (toggle on) to this notebook.
7. Get your code into the notebook: put **`train.py`, `build_sign_clips.py`, `vocab_250.json`** where the notebook can see them — either upload them as a **Kaggle Dataset** ("+ Add Input → Datasets → Upload") and add it, or `aws s3 cp` them in (next step).

### Run it (paste as one cell, press ▶ / Shift+Enter)
```python
import os; os.environ["TF_USE_LEGACY_KERAS"] = "1"
!pip -q install tf-keras awscli
from kaggle_secrets import UserSecretsClient; us = UserSecretsClient()
os.environ["AWS_ACCESS_KEY_ID"]     = us.get_secret("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = us.get_secret("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"

# pull the dataset next to train.py (same layout your retrain uses)
!mkdir -p data
!aws s3 cp   s3://asl-mvp-dataset/splits/split_manifest.parquet data/split_manifest.parquet
!aws s3 sync s3://asl-mvp-dataset/preprocessed/by_word          data/by_word --quiet

# build the per-word clip dictionary (train.py + vocab_250.json must be importable here)
!python build_sign_clips.py --data-dir data
```
> It reuses `train.py`'s loader, so run it **the same way you run `train.py`** (same folder / paths). If it can't find `train.py` or `vocab_250.json`, put them in the working dir first.

### Download the result
8. Right sidebar → **"Output"** (or the `/kaggle/working` file list) → download **`sign_clips_250.npz`** → drop it into your project root on Windows.

**Done →** locally run `python gloss_to_motion.py --per-word` to make your friend's 250 JSON files.

---

## 5. ⏳ LATER (skip for now) — KAGGLE: retrain the 250 model  ·  0.757 → ~0.82–0.85, ~11–13 GPU-h

> **NOT NOW — you decided to skip this for the demo (correct call).** This section stays here for **later**, when you harden recognition. It only improves **sign→speech** accuracy on the mid-tier words; it does **not** make anything faster and won't rescue the dead tail (`nap`, `give`…). Same notebook setup as §4 (GPU + Internet + Secrets).

> ⚠️ **Rotate the AWS key** you pasted in chat earlier before/after this (IAM → new key → put the new one in Kaggle Secrets). The old one is burned.

### 5.0 🛑 READ FIRST — this whole section is CLOSED (2026-08-14)

**Do not run anything below.** The plan (folds 0–4 → ensemble → 0.82–0.85) has a misstated target
and every lever in it has now been tested and closed by measurement:

- **More epochs: closed.** Fold-0 val_acc is flat from ~epoch 93 and drifts down by 120. The
  `--epochs 200` in step 3 below is wrong; 120 is sufficient and 120 is what actually ran.
- **Resting-hand masking: refuted.** −0.0312 test / −0.0415 val, and −0.269 *train* accuracy.
  See `KAGGLE_GPU_MASK_AB.md`.
- **Canonicalization / handedness: refuted 2026-08-14.** This was the recommended next step in
  the previous version of this section. It ran, cleanly (`left_dead 1.000`, `aligned 60.0%`, all
  41 geometry checks green), and produced **−0.0064** on the three signers it targeted versus
  **−0.0067** on the four it did not. No differential effect. 29302 — the signer the whole theory
  was built to rescue — moved **−0.0002**. Hand-block layout correlates with the per-signer
  spread but does not cause it. See `SESSION_HANDOFF.md` §0.5.

**What replaces them: nothing on GPU.** The per-signer spread (0.314–0.823) is real and is now a
documented property of the model rather than a bug with a known fix. Ensembling would buy ~1.5–3
pooled points on a number that is already the one being quoted, and it is blind to the per-signer
holes by construction. The remaining lever on end-to-end quality is the **Deaf review sheets**.

**⚠️ Do not read this as "the handedness work was wrong."** Two separate claims were tested and
only one died. *"Canonicalizing the corpus raises accuracy"* is dead. *"The geometric rule picks
the correct signing hand"* is **alive and independently verified**: the animation export went from
137/250 words rendering the resting hand to 1, coverage 28.8% → 76.2%. That fix ships and the
export is final.

**And restate the target.** "0.82–0.85" was never measured. The real numbers, updated
**2026-08-27**: **0.7787 @ 30 fps / 0.7707 @ 15 fps / 0.7628 @ 7 fps** — 4-fold ensemble on the
canonical corpus trained with `--decimate`, test split, mean over signers. That supersedes the
legacy ensemble's **0.7755** (30 fps only; its 7 fps accuracy was never measured on this pool).
Best single fold **0.7658**.

The 30 fps gain is **+0.0032, which is inside the noise on three signers — do not sell it.** The
win is at **7 fps**, the rate the demo actually runs: the paired fold-0 A/B measured **+0.0218**
there and halved the frame-rate penalty (5.13 → 2.64 pts). Supporting evidence: **all four folds**
beat their counterparts (0.7579/0.7608/0.7626/0.7636 vs 0.7544/0.7570/0.7545/0.7615), and fold 0
reproduced the shipped model to **0.0003**.

These are *means over signers*, not a promise to any one user — tell a new user **0.70–0.82**.
**Requires `live_demo.py --canonical`.** Full detail: `MODEL_250_MVP_REPORT.md` §1.0b and
`SESSION_HANDOFF.md` §0.6.

### The steps (run every `train.py`/eval as `!python`, NEVER in a bare cell — see gotchas)
1. **Upload the CURRENT `train.py` fresh** to Kaggle (the copy already there is stale/old-architecture). — 5 min
2. **Rehydrate** (the §4 cell: install + secrets + `aws s3 sync` the data). — 15–25 min
3. **Train fold 0 from scratch:**
   ```python
   !TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 0 \
     --epochs 200 --lr 4e-4 --seed 42 --out-dir /kaggle/working/asl250_scratch
   ```
   ~2–2.5 GPU-h. *(val_acc starts low ~0.2–0.4 and climbs — that's correct for from-scratch.)*
4. **Eval fold 0 vs 0.7576** as a subprocess (`!python eval_one.py`) — GO if ≥ ~0.78; must print `classifier: True`. — 5–10 min
5. **Train folds 1–4** (same command, `--fold 1 … 4`); `aws s3 sync` each to S3 so a disconnect doesn't lose it. — 8–10 GPU-h
6. **Ensemble eval + temperature calibration + TTA** (`!python ensemble_eval_250.py`) → the real headline number. — 20–40 min
7. *(only if 0.79–0.81)* late-dropout / mixup A/B.
8. **Freeze `vocab_250.json` + export the 5 SavedModels** (`!python finalize_250.py`). — 5–10 min
9. **Zip + download → `artifacts_250/`** on Windows. — 10–15 min
10. **Verify:** `python live_demo.py --vocab250 --selftest` (expects shape `[250]`), then run it live.

### Long runs without babysitting
Use **top-right "Save Version" → "Save & Run All (Commit)"** — it runs **detached** and keeps `/kaggle/working`, so you can close the tab. A single session/commit caps ~12h, so split into ~2 commits (folds 0–2, then 3–4 + ensemble).

### The 3 gotchas that waste a day if missed
1. **From-scratch is mandatory** (`no --init-from`) — the architecture changed (650 features); old weights won't load.
2. **Run as `!python script.py`, never in a notebook cell** — a TF 2.17 + tf-keras bug otherwise silently loads a random model → **0.004 accuracy**.
3. **Ship SavedModels, not `.weights.h5`** — the `.h5` doesn't reload reliably on Windows.

### Total & honest result
~11–13 GPU-hours, **1–2 days wall-clock**. Expect ~0.82–0.85 ensemble, ~130–160 words ≥0.80. **Not 100%** — some look-alikes and the abstract tail stay weak; that's the isolated-sign ceiling.

---

## 6. Open decisions / risks

- [x] **Positions vs rotations** — RESOLVED: positions as IK targets; no retarget step on your side. (Contract v4 §11.3.)
- [x] **Transitions between signs** — RESOLVED: animator blends per-word clips. (Contract v4 §10.)
- [ ] **Deaf review of the 250 exemplars** — tool built (`preview_signs.py --review`); run the pass and re-export any BAD signs. Risk flagged by the animator.
- [x] **Retrain — DEFERRED to later** (decided: not for the demo; §5 kept for when you harden recognition).
- [ ] **AWS key rotation** — the key pasted in chat is burned; rotate before broad use.
- [ ] **Face / non-manuals** — deferred to v2 (dataset faces are neutral, not grammatical).
- [ ] **LSL** — a whole separate effort gated on recording an LSL dataset (~25–30 signers). Not part of this ASL MVP.
