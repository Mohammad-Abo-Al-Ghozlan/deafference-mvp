# Deafference — Session Handoff (2026-07-20 → **updated 2026-09-07**)

> **Purpose of this file.** A complete, self-contained record of what was built,
> decided, and discussed across these working sessions. If you are a new
> assistant/chat: **read §0.8 CURRENT STATE (2026-09-07) FIRST**, then §0.7.
>
> **The rule for this file: the HIGHEST-NUMBERED §0.x is the live picture.** Lower ones are
> kept for the reasoning trail. Supersession is often *partial* — §0.8 replaces §0.7 only on
> the medical gate values and on which statistic the ship list must be gated on; §0.7's corpus
> build, its 0.8383 headline and its lexical-collision diagnosis all still stand, as do §0.5's
> refuted levers and its "Working with Salim" subsection.
>
> ⚠️ **Note the file order: §0.8 and §0.7 sit ABOVE §0.6.** Newest is inserted above the
> previous newest, so the sections after §0.5 read newest-first, not in numeric order.
>
> **Sections §0, §0.1 and §8 are history that has since completed.** They are kept for
> the reasoning trail, not as current status. Where they conflict with §0.2, §0.2 wins.
>
> **Two tracks are active** (§0.8): the **MEDICAL-DOMAIN MVP** — which now has a measured
> safety gate and four ship-list words awaiting Salim's decision — and **FINGERSPELLING**,
> a CTC baseline at 0.3730 val CER with its next rung scoped. The general 250-word work is
> paused, both of its phases being demo-ready.
> Deeper detail lives in the companion docs, chiefly
> [`MEDICAL_MVP_PLAN.md`](MEDICAL_MVP_PLAN.md), [`MEDICAL_SAFETY_GATES.md`](MEDICAL_SAFETY_GATES.md),
> [`FINGERSPELLING_CTC_RESULT.md`](FINGERSPELLING_CTC_RESULT.md) and [`explanation.md`](explanation.md).

---

## 0. TL;DR — what happened this session

1. **Built and hardened `live_demo.py`** — a standalone Python webcam demo that
   recognizes the 30 trained ASL signs live, assembles them into a spoken
   sentence, and speaks it. This was the main deliverable. It exists because the
   **browser app can't do live recognition yet** (frontend MediaPipe pipeline is
   unbuilt), and a supervisor wanted to test the 30-word model on camera.
2. **Solved a painful dependency/loading puzzle** (Windows + Keras version + the
   model file format + mediapipe version). The working stack is pinned in
   `requirements_live_demo.txt`.
3. **Added product-grade UX**: auto-commit sign segmentation, a DONE button to
   finish a sentence, offline text-to-speech, an UNDO/CLEAR/word-list UI,
   fullscreen, and an optional AI sentence generator (`--ai`).
4. **Made key product decisions** (below): continue to 250 words next (data is in
   hand) rather than chase continuous-signing datasets (data-blocked); the moat is
   Lebanese Sign Language.
5. **Rescoped the website backend** (`BACKEND_TASKS.md` Track B) from a
   camera-permission API to the full backend an actual product needs.
6. **Planned the speech → sign (reverse) feature** — a teammate is building the
   avatar/animation now. Wrote the data-hand-off spec `SIGN_ANIMATION_CONTRACT.md`
   and clarified the recognition-vs-animation split (see §11).
7. **Wrote the detailed 250-word training plan** → `TRAIN_250_PLAN.md` (see §8).

---

## 0.1 LATEST UPDATE — 250 training in progress (2026-07-22)

**This is the active work. If you're the next chat, this section is where things
actually stand. The execution doc is [`RESUME_250.md`](RESUME_250.md) — follow it
to continue.**

### Where the 250 training stands
- **Backbone measured:** `backbone_250.weights.h5` = **0.7260** test acc (held-out
  signers 2044/37779/53618) → below 0.80 → proper fold training needed.
- **fold-0 DONE:** warm-started from the backbone (`--init-from`), trained 80 epochs.
  Honest **TEST acc = 0.7576** (beats the backbone). Weights on Drive:
  `/content/drive/MyDrive/asl250_out/weights_all250_fold0_seed42.weights.h5`.
- **fold-1 PARTIAL:** ~epoch 30 when Colab cut out. Resume-checkpoint safe on Drive
  (`backup_all250_fold1/`). It early-stops ~epoch 31 (its val signers are easy for
  the backbone; val peaked at epoch 1, PATIENCE=30) so it barely diverges from the
  backbone — that's expected, per-fold val is noisy; the **ensemble on test** is the
  real number.
- **folds 2–4:** not started. **Goal:** ensemble the folds → **>0.80** on test.
  fold-0 alone (0.7576) is under target; 3–5-fold ensemble is what clears it.

### 🚨 CRITICAL GOTCHA discovered this session — build/load ONLY in a subprocess
On Colab (TF 2.17/2.18 + tf-keras), calling `build_model` **inside the notebook
kernel** decomposes `Dense`/`MultiHeadAttention` into untracked `tf.matmul`/
`tf.nn.bias_add` ops (loud "Variables used in a Lambda layer... not tracked"
warnings). Then `load_weights` silently loads a **random** model → **0.004 accuracy
(= 1/250, pure chance).** The FIX: **always run train / eval / export as a fresh
`!python` subprocess** (`!TF_USE_LEGACY_KERAS=1 python script.py`), never build+load
in a notebook cell. A subprocess sets the env var before importing TF and builds
proper layers. **Confirm with the `>> proper build? classifier: True` line** — if it
says False, you're in the broken path. (This is why fold-0 first read as 0.004, then
0.7576 once run via subprocess.)

### `train.py` was PATCHED this session (re-upload the new one to Colab/Kaggle)
1. **`BackupAndRestore`** callback → snapshots weights+optimizer+epoch to `--out-dir`
   every epoch. Point `--out-dir` at Drive (Colab) and re-running the SAME fold
   command **resumes mid-fold** instead of restarting from zero.
2. **SavedModel export in `--all-words` mode** (it used to skip it) → each fold now
   auto-exports `savedmodel_fold{N}/` when it finishes. SavedModel is the portable
   artifact (avoids the load gotcha above).

### Blocker + compute decision
- **Blocker:** Colab **free-tier GPU usage limit** hit (twice). Colab publishes no
  quota meter; resets in ~12–24h. Only ~**4 GPU-hours** of work remain.
- **Salim wants FREE only** — no EC2 (costs ~$5 but needs a G-instance quota
  increase that can take 1–2 days on a new account), no Colab Pro.
- **Two free paths:** (a) wait for Colab reset, resume via `RESUME_250.md`; or
  (b) **Kaggle Notebooks — 30 GPU-hours/week free, less throttling** (recommended if
  Colab keeps cutting out). Kaggle has no Google Drive → point `--out-dir` at
  `/kaggle/working` and push results to S3; otherwise the workflow is identical.
  *(Salim to pick; a `RESUME_250_KAGGLE.md` was offered but not yet written.)*

### Avatar teammate (Ghozlan) — answered his 5 pre-sample questions
Confirmed against `SIGN_ANIMATION_CONTRACT.md`: (1) sample-files date — deliverable
fast, export is **CPU-only** (no GPU needed); (2) **animator smooths** at render,
Salim does NOT pre-smooth; (3) runtime = one **continuous stitched stream** per
utterance, but the **first samples are per-sign clips** for calibration; (4) MVP z is
**fake/flat frontal** — agreed, real 3D depth is a v2 `pose_world_landmarks` upgrade;
(5) wrist offset is his to calibrate — note there are **two wrist points** (Pose
15/16 vs Hand-block 33/54; anchor the hand to 33/54), calibrate against the neutral
reference pose. **Pending (CPU-only, can run without the GPU quota):**
`export_reference_pose.py` + `export_sign_samples.py` — offered, not yet written.

---

## 0.2 STATE AS OF 2026-08-04 — ⚠️ SUPERSEDED BY §0.3, READ THAT FIRST

Everything in §0, §0.1 and §8 below is **history that has since completed**.

> **⚠️ 2026-08-12: this section is no longer the live picture.** Its "Working with Salim"
> subsection still holds and is still the best summary of how he wants this done — carry it
> over. But its **Phase 2 status is wrong** (the animation export was shipping the wrong hand
> on 249 of 250 words; see the corrected block below and §0.3). Where §0.2 and §0.3 conflict,
> **§0.3 wins.**

### Working with Salim — how he wants it (carry this over)

- He is **team lead + the only frontend dev**; he owns the whole ML/data pipeline and
  wants the assistant as a **pipeline-oversight partner**, not a code vending machine.
- **Verify, don't assert.** He has been burned by numbers that turned out to be
  unmeasured. Run the code, measure it, and quote the real figure — and say plainly
  when something is *not* measured.
- **Never break working functionality.** He has said this explicitly during cleanups.
  When a deletion or refactor risks a working demo, keep the thing and say why.
- **He presents this work to meetings/supervisors.** Docs and numbers must be
  meeting-safe: if a figure is an estimate, label it.
- **Secrets:** only in the gitignored `.env`. Never commit, never paste in chat, never
  put in `.env.example`. The AWS key, Gemini keys, and Supabase password pasted in
  chat earlier are **BURNED — still need rotating.**
- He often writes via voice-to-text, so messages have transcription artifacts —
  read for intent.

### Phase 1 (sign → speech) — done, demo-ready
- `python live_demo.py --vocab250 --debug` runs the 250-word model.
- **Measured accuracy: fold-0 = 0.7576** (`word_acc_250.json` per-word mean 0.7571).
  ⚠️ The **4-fold ensemble number was never actually measured** —
  `docs/MODEL_250_MVP_REPORT.md` says "not yet measured", yet
  `docs/explanation.md:75` claims "≈0.78 (0.7755)". That 0.7755 is an
  **extrapolation**, not a measurement. The 30-word ensemble did gain +1.1 pt
  (`artifacts/ensemble_eval.json`: mean single 0.9319 → ensemble 0.9433), which is
  probably where it came from. **Salim was told; he has not asked to change the line yet.**
- Retrain 0.757 → 0.82 target is **deferred**, not abandoned.

### Phase 2 (speech → sign) — ⚠️ WAS declared complete; it was not. See §0.3
> **Corrected 2026-08-12.** "250/250 clean" was measured with a rule that could not fail.
> The exemplars were selected by maximizing hand-tracking coverage, and coverage is
> anti-correlated with motion because MediaPipe loses the hand that *moves* — so the
> selector picked the **resting** hand on **249 of 250 words** with 99.6% consistency. The
> independent acceptance script scored dominant-hand coverage at **0.4%**. Fixed and
> re-verified at **76.2%**; details in §0.3 and `docs/MODEL_250_MVP_REPORT.md` §2 (R5).
- `sign_clips_250.npz` → `animation_handoff/` (250 per-word JSONs +
  `reference_pose.json`) → an early version was **zipped and sent to Ghozlan** with contract
  **v4**. That copy carries the wrong hand — **a corrected export must replace it.**
- Contract v4 decisions: **positions not rotations**, IK targets only, keep z **raw**,
  per-limb scale from `reference_pose`, animator owns transitions/smoothing, y is DOWN
  (renderer flips). No confidence channel (data is x,y,z only); no raw videos exist.
- **Still open:** the Deaf-review pass of the 250 exemplars
  (`preview_signs.py --review` is built and ready).

### Demo apps built for the meeting (all verified)
| File | What | Notes |
|---|---|---|
| `demo_voice_gui.py` | **The meeting build.** Clickable window: [● Record] → speak → [■ Stop] → transcript + 2D avatar signs it, all in one window | Space toggles, Esc quits |
| `demo_voice_to_sign.py` | Terminal version. **Press-to-talk by default** (Enter starts, Enter stops); `--fixed --seconds N` = old fixed window | fallback if the GUI misbehaves |
| `demo_speech_to_sign.py` | **Type** a sentence → 2D avatar signs it. Offline deterministic glossing | safest fallback |
| `_asr_worker.py` | Runs in **3.14**; `--push` / `--wav` / `--serve` / `--selftest` | see the interpreter split below |
| `preview_signs.py` | 2D skeleton player + Deaf-review harness | `--review`, `--contact` |
| `demo/*.mp4` | Pre-rendered fallback videos | if all else fails |

**🚨 THE INTERPRETER SPLIT (most important environment fact):**
`faster-whisper` is **only in Python 3.14**; `cv2`/`mediapipe` are **only in 3.11**.
So mic→ASR→display cannot run in one process. Run the demos with `py -3.11`
(plain `python`), and they shell out to `py -3.14 _asr_worker.py`. Do not try to
"fix" this by installing everything in one interpreter without checking.

**Performance facts (measured, don't re-derive):**
- ASR model load ≈2.9 s + transcribe ≈1.9 s. One-shot-per-utterance = **~6 s of dead
  air**; `--serve` keeps the model loaded → **~2.2 s end-to-end**. The GUI warms the
  server in a background thread at startup.
- Whisper `base` is **already cached** on Salim's machine (verified with real TTS
  speech) — no first-run download left.
- GUI rendering: Tk **PPM (P6), never PNG** — PNG encode+decode cost ~38 ms/frame
  (7 fps) vs ~7 ms for PPM. Playback is **wall-clock driven with frame skipping** so a
  slow machine keeps the correct sign *duration* instead of slow-motion.
- Tkinter traps already hit: `root.after()` from a worker thread raises
  `RuntimeError("main thread is not in main loop")` → use a `queue.Queue` drained by a
  main-thread pump; a focused Tk Button fires its own command on Space → `takefocus=0`
  or Space double-toggles.

### 🔴 ACTIVE WORK — the MEDICAL-DOMAIN MVP (started 2026-08-01)

Salim **paused everything above** to build a **medical-domain MVP**: same two phases,
new domain, **a new dataset and vocabulary — explicitly NOT a subset of the 250
children's words** (he rejected that approach when it was proposed).

**Plan: [`docs/MEDICAL_MVP_PLAN.md`](MEDICAL_MVP_PLAN.md) — read it.** Findings:

1. **There is no medical ASL dataset.** Medical SL datasets exist only for other
   languages: SignTalk-Gh (Ghanaian, 9,879 videos, 4,031 doctor–patient sentences, on
   Kaggle — but non-commercial, *continuous*, only 5 signers), Mexican MSL/LSM,
   Italian LIS, Brazilian Libras, Arabic ArSL. **For ASL the medical vocabulary must be
   assembled from a general isolated-sign dataset.**
2. **Measured feasibility (real data, not guesswork):** downloaded the actual Sem-Lex
   metadata (91,148 videos, 9,953 labels, **44 signers**) and scored a 145-concept
   clinical vocabulary against it. **129/145 (89%) are trainable** (≥8 unique videos and ≥3
   signers), **8,051 videos**, **0 absent**. *(Corrected 2026-08-27: `build_vocab.py` counted
   CSV rows, but 91,148 rows dedupe to **88,174 unique `video_id`**. `knee` falls to 7 and
   crosses the gate. Also **338 video_ids carry two different labels** — resolve or drop.)* Strong: `hurt` 248v/36s, `sick` 207/37,
   `help` 136/28, `doctor` 115/31, `medicine` 95/29, `breathe` 75/30, `pain` 52/22.
3. **16 thin words, and they matter clinically:** `fever`(6v) `chest`(4v) `stomach`(5v)
   `nausea`(2v) `rash`(2v) `cramp`(2v) `infection`(5v) `sneeze`(4v) `neck`(7v)
   `shot`(6v) `wheelchair`(7v) `patient`(2v) `stand`(5v) `very`(3v) `never`(7v)
   **`knee`(7v) — new to this list after the dedupe fix.**
   Must be supplemented from **ASL Citizen** (a different 2,731-sign selection) or
   recorded with a Deaf signer. Treat as required, not optional.
4. **Four numbers that will shape training** (revised 2026-08-27):
   - class imbalance **49×** (8 → 393 videos/class, median 38) → class weighting/capping;
   - **62 videos/class vs GISLR's ~376 — 6× less**, so expect accuracy **below 0.7576**.
     Do not promise 0.78.
   - **⚠️ "44 signers" is not the win it looked like.** Only **41** appear in the clinical
     subset and the **top 10 hold 58%** of it (max/min **330×**). Per-signer variance is the
     risk, not class count — the 250-word spread was 0.314–0.823 and nothing downstream of
     the feature extractor fixed it.
   - **⚠️ Sem-Lex's `val` is NOT held out**: train∩test = 0 and val∩test = 0 signers, but
     **train∩val = 31 of 32**, and 995 video_ids sit in both archives (zero in train+test).
     **Score on `split == "test"` only** — 9 signers, 1,468 clinical clips.
   - **⚠️ ~25% of Sem-Lex signers are left-dominant** (GISLR ~10%) → train `--canonical-hand`.

**Artifacts created (all in the repo):**
| File | What |
|---|---|
| `docs/MEDICAL_MVP_PLAN.md` | The staged plan, dataset comparison table, risks, sources |
| `vocab_medical.json` | The **129 trainable clinical words** (130 before the 2026-08-27 dedupe fix) |
| `vocab_medical_analysis.json` | Per-word video/signer counts + tier A/B/C |
| `training/medical/build_vocab.py` | Reproduces the coverage analysis from Sem-Lex metadata |
| `training/medical/semlex_med.py` | The trainability scan |
| `training/medical/extract_landmarks.py` | **video → (64,75,3) landmark tensors** |
| `training/medical/test_parity.py` | **Proves the extractor matches `live_demo.py` bit-for-bit** |

**`extract_landmarks.py` — the thing that de-risks this.** It copies
`extract_75` / `normalize` / `time_resize` and the MediaPipe settings from
`live_demo.py` verbatim. `test_parity.py` proves **0.000e+00 difference** across all
functions, constants and edge cases (including the drop-frame and all-NaN paths).
**Run it after ANY change to either file** — this is the guard against the silent
drift that would otherwise wreck a trained model.
Also: the quality gate rejects a clip with a hand in <35% of frames
(`HANDPRESENCE_MIN`, same bar as live_demo). A first version only rejected
*zero*-hand clips and accepted a clip with a hand in 1 of 280 frames — that would
have trained the model on noise. Don't loosen it.

**Confirmed by reading the code (don't re-derive):** `train.py`'s `PreprocessLayer`
does **NOT** normalize — it masks NaN, drops z, and computes velocity/handshape
features. Normalization therefore happens **outside** the model (which is why
`live_demo.normalize()` exists and why the extractor pre-normalizes). This is correct
and consistent — no double-normalization.

**🚧 NEXT STEPS, in order:**
1. **BLOCKED — needs Salim, not the assistant:** resolve licensing. Sem-Lex has a
   **terms-of-use gate** (the HuggingFace mirror is tagged `apache-2.0` but *a
   mirror's tag is not the original licence*); ASL Citizen needs
   `ASL_Citizen@microsoft.com` for **commercial** use. Salim rejected How2Sign over
   exactly this, so settle it **before** the data shapes the product.
2. **Write the adapter** `extraction .npz → train.py`'s expected layout:
   `by_word/<word>/sequences.npz` (keys `"{participant_id}_{sequence_id}"`) plus
   `split_manifest.parquet` with columns `word, participant_id, sequence_id, split,
   fold, is_outlier`. Folds must be **signer-disjoint** (group by `signer_id`).
   ⚠️ *Unverified:* whether this environment has `pandas`/`pyarrow`/`sklearn` — the
   check was interrupted. Confirm before relying on parquet.
3. ✅ **DONE 2026-08-27** — downloaded the **poses** release (13.3 GB, not 53.6 GB of video);
   8,064 of 8,103 clinical clips present.
4. ✅ **DONE** — `training/medical/semlex_poses_to_75.py` (no MediaPipe needed, ~20 s on CPU).
   ⚠️ Sem-Lex poses are **553 landmarks, not 543** (face mesh + 10 iris), so every index after
   the face block shifts +10; and clips are **raw recordings** whose lead-in/lead-out is 61.5%
   of all frames, so the adapter trims to the tracked span first.
5. Train with `train.py` (vocab-size agnostic) + class weighting for the 49× imbalance,
   `--canonical-hand`, and scoring on `split == "test"` only.
6. Wire Phase 1 (`live_demo.py` + clinical grammar) and Phase 2
   (`build_sign_clips` → `sign_clips_medical.npz` → `gloss_to_motion --per-word`).
7. **Clinical safety gates (non-negotiable):** critical terms (pain, severity,
   negation, body part) **never auto-commit** — force the L2 confirm path even at high
   confidence; **always show the recognized gloss for correction before speaking it**;
   the grammar layer must be **constrained to recognized glosses** so an LLM can never
   invent clinical content that wasn't signed.

**Scope limits to state out loud:** no fingerspelling (drug names/conditions are
fingerspelled — an isolated-sign classifier cannot read them); no diagnosis, consent,
or dosage; **not a replacement for a qualified medical interpreter.**

---

## 0.3 STATE AS OF 2026-08-12 — ⚠️ SUPERSEDED IN PART BY §0.4, READ THAT FIRST

Everything in this section about the **animation export** is current and correct. Everything
about the **recognition model** — the `0.7590` headline and the masking lever — was overtaken
on 2026-08-13; see **§0.4**. §0.2's "Working with Salim" subsection is still accurate and still
worth reading.

**Full write-up: `docs/MODEL_250_MVP_REPORT.md`.** Outgoing letter to the animation side:
`Fix/FROM-SALIM-v7.md`. Do not re-derive what those two contain.

### The one thing to understand about this session

The recognition model and the animation export are **two separate products off one corpus**,
and only one of them was broken. Recognition is fine at **0.7590 top-1** on a
participant-held-out split. The animation export was shipping the **resting hand** — the hand
that is *not* doing the sign — on **249 of 250 words**.

Cause chain (root cause **R5**, all measured):

1. MediaPipe preferentially loses the hand that **moves** (median wrist speed 0.0317
   sh.w./frame in hand-missing frames vs 0.0208 in hand-present ones).
2. So the populated 21-point block is disproportionately the **still** hand.
3. `extract_canonical.canonicalize()` chose dominance from hand-block frame counts →
   canonicalized on the resting hand.
4. The exemplar selector then **maximized hand coverage**, and coverage is anti-correlated
   with motion: `r = −0.464`, negative for **100%** of 250 words. Maximizing coverage *is*
   selecting for stillness.
5. Net: the wrong hand chosen with **99.6% precision against a 44.9% base rate**.

The evidence was in the export all along — every word's meta had `"required_hand": "R"` next
to `"dominant": "L"` and nothing compared them. What settled it was **geometry**: hand
landmark 0 *is* a wrist, so co-location with a pose wrist identifies the limb regardless of
naming — median **0.088** shoulder-widths to its own limb vs **1.783** to the other.

**The corpus was never the problem.** 55.1% of takes have the tracked hand on the moving arm
and all 250 words have ≥55 such takes (median 178). Selection bug, selection fix, no retraining.

### Verified fixed

| criterion (their `Fix/check-export3.py`) | before | now |
|---|---|---|
| dominant-hand coverage | 0.4% FAIL | **76.2% PASS** |
| words missing the dominant hand | 249 | **1** (`finish`, a tie-break artifact — not a hole) |
| exemplars carrying the signing hand | 0.4% | **250/250** |
| exemplars carrying the resting hand | 96.9% | **0.1%** |
| tracker-drop ratio | 4.06× | 1.52× |

`finish` is fine: its right hand is present in 10 of 22 frames. The two sides derive dominance
differently (absolute wrist travel vs shoulder-relative with an elbow gate) and disagree on
**exactly 1 of 250 words**, whose travel ratio is **1.00** — a perfect tie. The export now
asserts `dominantHand: "R"` so it is never re-derived.

### The remaining ceiling is two-handed words only

| class | n | dominant coverage | valid takes (median) |
|---|---|---|---|
| one-handed | 163 | **0.829** | 138 |
| 2s | 52 | 0.412 | **3** |
| 2a | 35 | 0.422 | 5 |

One-handed signs are done. The 87 two-handed words are limited by **pool size, not
selection**: validity passes 48% of one-handed candidates but **1% of 2s** and 2% of 2a. 20
words have ≤2 valid takes, 7 have exactly one, 6 exemplars are under 0.53 s. Structural — a
two-handed take needs both motion and coverage, and those trade against each other. **The
lever is at the render layer** (declared hold/interpolate via `dominantCoverage`), not better
selection. Loosening validity buys coverage by re-admitting hanging arms: worse, and harder to
detect.

### What changed in the code (all tested)

- **`sign_landmarks.hand_arm_alignment()`** — the geometric signing-hand test.
- **`build_sign_clips.py --require-signing-hand`** (default `on`) — gate 0, before every class
  rule. Warns on words with no aligned take anywhere; **aborts** only if it picked an unaligned
  take when an aligned one existed (that would be a selector bug, not a data limit).
- **`gloss_to_motion.py`** — each segment now carries a `synthesis` block: class, rule,
  `dominantHand`, `passiveWristIndex`, the assigned `passiveHandshape` for 2a words, and
  `dominantCoverage`. Purely additive: verified 0 words with changed motion data.
- **`train.py --mask-resting-hand {off,train,all}`** (default `off`) — was expected to be the
  next accuracy lever. **It is not. The A/B ran 2026-08-13 and masking LOSES on both
  yardsticks — see §0.4.** The flag stays in the code as documented negative evidence; do not
  enable it. It NaNs the hand block on the ~42% of clips where the alignment rule says the
  tracked hand sits on the still arm.
- **`build_handshape_templates.py`** — S anchor fixed (dropped the dynamic `milk`/`orange`);
  added a `resolution` map so all 7 unmarked shapes resolve. Corrected 2026-08-13 against the
  shipped file: it carries **7** handshape entries with `n_usable: 6` — `S` IS measured (the
  anchor fix landed), and only `O` falls back, to `C`. There is no `S→A` fallback.
- **`asl_handedness_250.json`** — new `passive_handshape` block: all 35 `2a` words assigned a
  shape *and* a contact target. **35/35** land on a measured template. **NOT DEAF-REVIEWED.**
  *(Corrected 2026-08-14: read "34/35" until then — the same stale fact the bullet two lines above
  had already refuted, surviving inside the block that corrected it. Two lines apart.)*
- **`docs/SIGN_ANIMATION_CONTRACT.md` §6.1** — the full renderer spec for the above.
- **`docs/HANDEDNESS_REVIEW_SHEET.md` Part 2** — the 35 passive handshapes, ordered so the
  doubtful rows come first.

### Immediate next actions

1. **Upload `~/Downloads/asl250_code.zip` as `asl250-code-v16`.** (v13 is what last ran on
   Kaggle; v14/v15 were superseded before upload. `train.py` changed, so the number moved.)
2. **Kaggle CPU notebook: re-run Cell 0 first** — staging lives there, and re-running only the
   later cells silently reuses old code. That already cost one wasted run. Then Cells 3, 4, 5.
   Cell 2 is skippable *only* while `build_sign_clips.py` is unchanged — check
   `/kaggle/working/out/sign_clips_250.npz` survived the kernel restart first.
3. ~~**GPU: the masking A/B**~~ — **DONE 2026-08-13. Masking lost. See §0.4.** The one note
   from this item that still matters: `CosineDecay(decay_steps=epochs*steps − warmup)` ties the
   whole LR schedule to `--epochs`, so changing the epoch count is a *different experiment*,
   not a continuation. Any two arms being compared must be passed the same `--epochs`.
4. **Send `Fix/FROM-SALIM-v7.md`** plus the corrected `animation_handoff/`,
   `handshape_templates.json` and `asl_handedness_250.json` to Ghozlan. The copy he has now
   carries the wrong hand.
5. **Still outstanding from earlier sessions:** rotate the burned AWS/Gemini/Supabase keys;
   free disk on C: (was 1.1 GB of 237 GB free).

### Two methodological rules this session earned

**A check that cannot fail is indistinguishable from a check that passes.** It happened three
times: the original `pres > best` selector could never fire; a corpus-layout probe compared two
corpora that had the *same* layout and reported "no regression"; a staleness guard listed only
symbols the *old* code also contained, so a stale build ran and produced byte-identical output
that read as a successful re-run. Run every new assertion once against the case it is meant to
catch.

**Prefer geometry to labels.** Every naming-convention question here — which hand is dominant,
which block is left, whether the image is mirrored — collapsed the moment someone measured a
distance instead of trusting a field name.

---

## 0.4 STATE AS OF 2026-08-13 — ⚠️ SUPERSEDED IN PART BY §0.5, READ THAT FIRST

Wins over §0.3 and everything below **for the recognition model**. §0.3 remains correct for the
animation export. Two results, and the second one is much bigger than the first.

> **§0.5 (2026-08-14) overturns the *conclusion* of item 2 below.** The per-signer measurements
> in the table are correct and still stand. The *causal* claim — that hand-block layout produces
> the spread — was tested directly and **refuted**. Read §0.5 before acting on item 2 or on the
> next actions in item 6.

### 1. The resting-hand mask is refuted. Do not revisit it.

Both arms, one commit, legacy corpus, one variable (`epochs=120 run=120 seed=42` on both;
`masked_clips=0` vs `39369`):

| arm | TEST (13,998 clips, signer-disjoint) | val fold 0 (16,202) | train acc |
|---|---|---|---|
| control `mask=off` | **0.7658** | 0.5791 | 0.7673 |
| masked `mask=train` | 0.7346 | 0.5376 | 0.4983 |
| delta | **−0.0312 (−6.0σ)** | −0.0415 (−7.5σ) | −0.269 |

`train`-only masking creates a train/eval mismatch, so the val and test deltas alone do not
prove information loss. **The train-accuracy column does**: 0.767 → 0.498 on the distribution
the model actually trained on. The deleted block carries class-discriminative signal.

Mechanism, from the per-arm confusion matrices: predictions collapse onto signs sharing a **body
location**, because the handshape that separated them is gone. `tongue` → `say` (both at the
mouth); `awake` → `wake` + `moon` (all at the eyes); `water` → `fine` (W-at-chin vs 5-at-chest,
a handshape-only distinction); `mouse` → `toothbrush`/`doll` (all at the nose).

**There is no selective version to salvage.** Per-word: 48 helped / 177 hurt / 25 tied, but at
2σ only **3 helped** against **~6 expected from chance** across 250 tests — below the noise
floor. Every apparent winner is either noise or the other half of a zero-sum shift inside a
confusion cluster (`wake` +0.197 *is* `awake` −0.250). Damage is broad and shallow: ~66 clips
per word makes a −0.04 shift −0.67σ per word and invisible, yet −7.5σ pooled.

### 2. Per-signer variance dwarfs everything, and it is handedness

The fold-0 control model over its **7 honest held-out signers** (4 val-fold + 3 test):

| pid | L-block | R-block | acc | layout |
|---|---|---|---|---|
| 26734 (val) | 0.02 | 1.00 | **0.823** | pure R |
| 2044 (test) | 0.01 | 1.00 | 0.806 | pure R |
| 37779 (test) | 0.00 | 1.00 | 0.780 | pure R |
| 53618 (test) | 0.13 | 0.88 | 0.707 | R + contamination |
| 32319 (val) | **1.00** | 0.04 | 0.614 | pure **L** |
| 34503 (val) | **1.00** | 0.08 | 0.577 | pure **L** |
| 29302 (val) | **0.48** | **0.99** | **0.314** | **both blocks** |

**Spread 0.509.** Both pooled numbers reconcile exactly from these rows (val 0.5791, test
0.7658), so this is arithmetic, not an artifact. Two distinct failure modes:

- **Recorded on the left → ~−20 points** (0.577, 0.614 vs 0.78–0.82).
- **Both blocks populated → −50 points.** 29302 has R in 99% of clips *and* L in 48%. The model
  trained on clips carrying essentially one hand block; this input has a different shape.
  Accuracy is flat ~0.80 while L-contamination ≤0.02, then 0.13 → 0.707, 0.48 → 0.314.

### 3. The consequence: the test split cannot see the problem

Test holds only R-dominant signers (0.13 / 0.00 / 0.01) — **not one left-recorded signer.** val
fold 0 holds three of the four pathological ones. So:

- **`0.7658` is structurally optimistic**, not merely lucky. It measures the layout the model
  already handles.
- **The honest new-signer estimate is `0.666` pooled over all 7**, median 0.707, with an
  observed 1-in-7 chance of ~0.31. And that is if anything generous — the val fold was used for
  model selection (EMA keeps best-`val_acc` weights), so those four are not pristine.
- **Canonicalization was never refuted.** §0.3 and `MODEL_250_MVP_REPORT.md` §1.1 said arm B's
  canonical 0.7590 vs shipped 0.7576 proved the layout "did not buy accuracy." That comparison
  was **blind by construction**: the test split had no left-recorded and no both-blocks signer,
  so canonicalization had nothing to fix there and paid only its preprocessing cost. It is now
  the highest-value lever, aimed at a 20–50 point hole rather than a 2-point one.
- **val fold 0 is the sensitive endpoint, pooled test is the blind one.** Judge any future
  layout A/B per-signer on **34503, 32319, 29302**. Never on pooled test accuracy.

### 4. Also closed: epochs

Control's val_acc is flat from ~epoch 93 (0.5781 / 0.5786 / 0.5788 / 0.5783 / **0.5791** peak
at 99) and drifts to 0.5774 by 120. 120 epochs is enough; more buys nothing. Arm B's
best-at-115-of-120 was a canonical-corpus artifact, not a general signal.

### 5. The animation export was only fixed ON KAGGLE — that got closed 2026-08-13

§0.3 recorded the export as fixed and verified at 76.2%. It was — **in the Kaggle CPU
notebook.** The corrected artifacts were downloaded to `~/Downloads/cpu_session_out_v16/` on
2026-08-12 and never copied into the repo, so for a day the repo held the *broken* export and
`demo_voice_gui.py` rendered it. Measured on disk before the fix:

| | on disk (repo) | after copying the corrected clips |
|---|---|---|
| dominant-hand coverage | 28.8% FAIL | **76.2% PASS** |
| words missing the dominant hand | **137** | **1** (`finish`, the documented tie) |
| signing / resting hand | 28.8% / **51.5%** | **76.2% / 0.1%** |
| native clip duration | FAIL — all 250 forced to 64 frames | **PASS — 9 to 116 frames** |
| no limb longer than itself | FAIL, 2 words | **PASS** |
| synthesis blocks | 0/250 | **250/250** |

Root cause was mundane and worth remembering: **`sign_clips_250.npz` in the repo was the Jul 30
build**, carrying the resting hand on 150/250 words (40% signing). The corrected npz existed
only in Downloads. Two independent runs of `gloss_to_motion.py` — one on Kaggle, one local —
produced **byte-identical** word files from it, so the exporter is deterministic and the only
variable was which npz was on disk.

Also added 2026-08-13: **`synthesis.sourceQuality`** per word — `validTakes` (corpus median
114), `thin` (≤2 takes: 20 words, 7 of them single-take), `brief` (<0.53 s: 6 words), and
`sourceClip` for provenance. `tiger` is both thin and brief: one take, nine frames. Verified
purely additive — frames and segment timing byte-identical with and without the metadata.

The send bundle is built at `_send/` and zipped as `deafference_handoff_v7_CORRECTED.zip`
(7.3 MB, 250 word files + 8 support files). `Fix/FROM-SALIM-v7.md` gained a "read first" block
covering the three rig changes Ghozlan must make (variable clip length is the breaking one),
plus the `finish` tie-break proposal and a request to drop per-landmark confidence from the
contract.

### 6. Next actions (decided 2026-08-13)

1. ~~**Rebuild the canonical corpus and retrain.**~~ ✅ **RUN 2026-08-14 — REFUTED, see §0.5.**
   The bar below was not met: mean delta on the affected signers was **−0.0064**. Do not re-run
   this, and do not try `--unaligned hand` — §0.5 explains why that retry is not worth 3 h 45 m.
   Original plan text kept for provenance: — run it per
   **`docs/KAGGLE_CANONICAL_REBUILD.md`** (~3 h 45 m, one commit, no AWS/S3 needed: raw from the
   `asl-signs` competition mount, manifest from `asl250-mask-ab-v1`).
   - `extract_canonical.canonicalize()` now takes `--dominance geometric` (default): the signing
     block is the one whose landmark 0 co-locates with the **moving** arm's pose wrist.
     `--dominance frames` keeps the old frame-count rule for comparison only.
   - 29302's both-blocks case has an explicit policy: `--unaligned {moving,hand}`, default
     `moving`. Keeping the resting hand rather than dropping it is not a guess — dropping it is
     what §0.4 §1 measured and refuted.
   - `training/test_canonical_geometry.py` — 41 checks incl. the R5 ablation (asserts the OLD
     rule picks the resting hand) and a branch-reachability test. Run it as a Kaggle preflight.
   - `training/per_signer.py` — the acceptance test, with the legacy per-signer baseline
     hard-coded so a regression is visible without hunting the old log. **Bar: mean delta on
     34503 / 32319 / 29302 above +0.02.** Judge on that, never on pooled test accuracy.
2. **Deploy recipe is `--mask-resting-hand off`.** Unchanged.
3. 5-fold CV + ensemble (`--fold all`, `ensemble_eval.py`) is worth ~+1.5–3 pooled points and is
   **blind to the handedness holes** — do it after the layout question, not before.
4. Everything in §0.3's "Immediate next actions" items 2, 4 and 5 still stands (CPU re-export,
   send `Fix/FROM-SALIM-v7.md` to Ghozlan, rotate the burned keys).

Run artifacts: Kaggle dataset **`asl250-mask-ab-v1`** (Private) — both arms' weights,
savedmodels, `eval_all250_fold0.json` with `per_word_acc`, confusion matrices, histories, and
`data/split_manifest.parquet`. Splits verified signer-disjoint: **18 cv / 3 test / 0 overlap**,
`0 / 14245` test clips from a cv participant.

### The methodological rule this session earned

**A pooled metric can be blind to the failure it is supposed to measure.** 0.7658 looked like a
new best — it is the best *single-fold* test number, though the 4-fold ensemble measured 0.7755
on 2026-08-06 (`explanation.md`), so it is not the best number overall. It was also incapable of
detecting a 50-point per-signer collapse, because the
split that produced it contained none of the affected configuration. This is the same lesson as
"a check that cannot fail is indistinguishable from a check that passes," one level up: before
trusting an aggregate, ask which subpopulations it contains — and disaggregate by the variable
you suspect. Three under-powered checks were shipped this session before the per-clip
set-identity test finally discriminated; the per-signer breakdown is that test's equivalent for
accuracy.

---

## 0.5 CURRENT STATE (2026-08-14) — READ THIS FIRST IF YOU ARE A NEW CHAT

**The handedness/layout theory is refuted. The recognition track is closed. The shipping number
is the 4-fold ensemble at 0.7755 pooled test, unchanged since 2026-08-06.**

### 1. Canonicalization was tested properly and it does not work

Ran per `KAGGLE_CANONICAL_REBUILD.md`, one commit, geometric dominance, `--unaligned moving`.
The corpus itself was clean: `left_dead 1.000`, `hand_nan 0.307`, `aligned 60.0%` (vs a ~55%
expectation), `both_blocks 4.2%`, all 41 geometry checks green on Kaggle, smoke line
`layout = CANONICAL | hflip swaps hands = False | hand-drop blocks = 1`. So this is not a
plumbing failure — the intervention was applied exactly as designed.

`per_signer.py` on fold-0 weights, all 7 honest held-out signers:

| pid | legacy | canonical | delta | |
|---|---|---|---|---|
| 29302 | 0.3141 | 0.3139 | **−0.0002** | affected, both-blocks |
| 34503 | 0.5774 | 0.5692 | −0.0082 | affected, pure L |
| 32319 | 0.6143 | 0.6035 | −0.0108 | affected, pure L |
| 53618 | 0.7069 | 0.7022 | −0.0047 | |
| 37779 | 0.7796 | 0.7653 | −0.0143 | |
| 2044 | 0.8062 | 0.8056 | −0.0006 | |
| 26734 | 0.8231 | 0.8158 | −0.0073 | |

**Affected signers −0.0064. Unaffected signers −0.0067.** That single comparison is the result:
an intervention built to help three specific signers hurt all seven by the same amount. There is
no differential effect — not a weak one, none. Pooled 0.6591 vs 0.6656 (−0.0065). Spread
0.5019 vs 0.5090, and it narrowed only because everything drifted down together.

**The sharpest number is 29302's −0.0002.** That signer is why the run existed: 0.48 L-block *and*
0.99 R-block, 50 points below the pure-R signers. Canonicalization put his signing hand in one
block on every clip, and `both_aligned_tie_by_distance` fired on only 138 of 94,198 clips
corpus-wide — so the picker was not hedging on his data, it was making confident unambiguous
choices. It made them, and he did not move measurably.

**Conclusion: hand-block layout is a *proxy* for whatever drives the 0.31–0.82 spread, not its
cause.** Both correlate with something about how those sessions were recorded. Remove the layout
difference and the spread survives intact.

**The confound, stated honestly:** this was not a clean single-variable A/B. On canonical data
`hflip` no longer swaps hands and hand-drop has 1 block instead of 2, so augmentation changed
too; train acc fell 0.767 → 0.710, so the corpus also genuinely lost fittable signal (the 33–53
block was carrying something). Either explains the uniform −0.0066. **Neither can manufacture a
differential gain, and the differential gain is what was on trial.** The refutation holds.

### 2. What this cancels

| item | status |
|---|---|
| Face landmarks into the freed 33–53 block | **cancelled** — `per_signer.py`'s coded verdict says so |
| Folds 1–3 + ensemble on the canonical corpus | **cancelled** — do not ensemble a corpus 0.0065 worse |
| `--unaligned hand` retry | **cancelled** — see below |
| Any further recognition GPU work | none queued; quota free |

`KAGGLE_CANONICAL_REBUILD.md`'s decision table pre-committed to trying `--unaligned hand` if the
affected signers went down. **That pre-commitment assumed some differential signal to chase.**
Zero was measured. The flag only re-orients the 39.8% `unaligned_orient_by_moving` clips and
barely touches 29302 at all. Overridden deliberately, by the author of that line.

### 3. ⚠️ What was NOT refuted — do not over-generalize this

Two separate claims were on trial and only one died:

- *"Canonicalizing the training corpus raises recognition accuracy"* → **dead.**
- *"The geometric rule identifies the correct signing hand"* → **alive, and independently
  verified by direct measurement, not by an accuracy proxy.** The animation export went from
  137/250 words rendering the **resting** hand to 1 (`finish`), signing/resting coverage
  28.8/51.5 → **76.2/0.1**.

**The animation export is correct and is now FINAL.** No new corpus is coming. Anyone reading
§0.5 as "the handedness work was wrong" would be discarding a verified product fix on the
strength of an unrelated null result.

### 4. Per-user variance is a product fact now, not a bug to chase

0.31–0.82 across seven held-out signers is a measured property of this model that layout
canonicalization does not fix. Quote **0.6–0.8** for a single new user. The remaining lever on
sign quality is the Deaf review sheets, not GPU.

One cheap lead survives, unpursued: 29302 may have the tracker switching hands *within* a clip,
while `limb_assignment` takes one median distance and picks one block per clip — wrong
granularity if so. ~20 min locally, no GPU. It is diagnosis, not a fix.

### 5. Code fixes shipped 2026-08-14

**`gloss_to_motion.blend_len()` — the 2.13 s constant, on our side.** Ghozlan warned that
anything calibrated when every clip was 64 frames needed re-checking. Ours was
`DEFAULT_TRANSITION = 8`, inserted between signs by `stitch()`. At 64 frames that is 12% of a
clip; with native durations, `tiger` (9 frames) with a neighbour on each side got 16 blend frames
around 9 sign frames — **64% of the word's span was morph**. Nothing raised. Now scaled:
`max(1, min(cap, round(0.15 × min(len_a, len_b))))`. `tiger` 64% → 18.2%; `puppy` (116f)
unchanged at 12.1%; returns `cap` unchanged for any pair ≥ ~53 frames, so it is a no-op on
everything that was already fine. `--transition 0` still disables blending. **One fix covers five
entry points** — `preview_signs.py`, `demo_speech_to_sign.py`, `demo_voice_gui.py`,
`demo_voice_to_sign.py` and `gloss_to_motion.py` all route through `stitch()`.

**A bug in Ghozlan's `retarget.mjs`, verified before reporting.** The 2s branch (line 990) is
guarded by `e[other(s)].hpts` — the other side must have data. The 2a branch (line 1042) has no
such guard, so on a frame where the *dominant* hand is untracked, `!H` is true for the dominant
side too and it receives the **passive** base handshape. Measured from
`animation_handoff/words/`: the dominant hand is absent on **666 of 1374 frames across the 35 2a
words (48.5%)** — worst are `arm` (18.2% present), `chocolate` (22.2%), `hide` (25.6%),
`night` (28.6%). Falsifiable prediction he can check in one line: his `report.templateHands`
counter should read **1374**; if it reads ~**2040** the dominant side is being templated. Patch:
add `&& s !== DOM_SIDE` (derive `DOM_SIDE` from `DOMINANT` at line 567) so the dominant side
falls through to the relax branch at 1081.

### 5.5 The avatar track, where all the remaining headroom now is

With recognition closed, this is the whole product surface. Quality tiers on dominant-hand
coverage, measured over the shipped 250:

| class | words | 🟢 A ≥80% | 🟡 B 50–80% | 🔴 C <50% |
|---|---|---|---|---|
| 1 one-handed | 163 | **144** | 19 | **0** |
| 2s symmetric | 52 | 3 | 26 | 23 |
| 2a asymmetric | 35 | **0** | 19 | 16 |

**One-handed words work. The 87 two-handed words are the entire problem.** Same R5 mechanism:
the tracker loses the hand that moves, and two-handed signs are where the hands occlude. Measured
on this export, median wrist speed is 0.0208 sh.w./frame when the hand block is present vs 0.0317
when missing — **1.52×**.

**🔴 The biggest single finding, and it is not the 2a contact problem.** The dominant hand is
missing on 2595 of 10956 frames (23.7%) in **776 gaps, 751 of them interior**. But **550 of 776
gaps are 1–3 frames** — 33–100 ms of tracker dropout where the hand did not go anywhere.
`retarget.mjs`'s relax branch (line 1081) sets the hand to a relaxed pose there, so the handshape
visibly collapses and re-forms **550 times across the vocabulary**. Contract §6 already says a
null landmark is the renderer's to hold. **1177 frames (45.4% of all missing frames) are
recoverable by holding across gaps ≤4.** This is a third instance of the 2.13 s pattern: the relax
branch was written against the *broken* export where the signing hand was often absent entirely.

**🟠 The 2a contact problem — confirmed, larger than reported, and the diagnosis inverts.** Measured
over all 35 2a words: the passive wrist sits a median **1.56 shoulder widths** from the dominant
wrist (range 0.80–2.22); only 1 of 35 is inside the 45–55 cm band the animation side reported. But
the arm is **not hanging** — median 0.34 sh.w. below its own shoulder, never past 0.75, versus
~1.1–1.3 for a hanging arm. It is raised and on its own side of the body. So a proximity filter
strands **35/35** and cannot ship. Fix: `asl_2a_base_placement.json` (new), anchoring the base to
the dominant hand's own trajectory then holding static. Hearing-authored, unreviewed, 22 high /
11 medium / 2 low, and 6 words (`arm`, `table`, `tree`, `flag`, `morning`, `time`) act on the
forearm or wrist rather than a hand — flagged `kind`, not solved.

**🟠 Exemplar selection is starved by its own validity filter.** `require_passive_up` is the sole
cause, and class 1 returns before it: class 1 keeps **49.0%** of takes (median 138 valid), 2s keeps
**1.2%** (median 3), 2a **2.1%** (median 5). **For 2a the gate is pure loss**: it sacrifices ~98% of
the pool to protect a passive wrist position that `asl_2a_base_placement.json` now overwrites.
`--require-passive-up 2s-only` added; **untested — see §6.**

⚠️ **A correction to this same section, made the same day.** It first cited a pooled
`corr(valid_candidates, coverage) = +0.804` as evidence that starvation *causes* the low coverage.
Disaggregated, that collapses: **+0.218** within class 1 (n=163), **+0.244** within 2s, **+0.443**
within 2a. Class-1 words never fall below **73** valid takes and still span **0.56–1.00** coverage,
so pool size does not buy coverage; 2a's valid range is **2–9**, which cannot extrapolate to 130.
The pooled figure mostly restates "two-handed signs have fewer valid takes *and* worse coverage" —
both consequences of two-handedness. **The re-selection run is justified by mechanism (the gate
cannot be buying anything on 2a), not by that correlation, and its outcome is a genuine unknown.**

This is the **third** time a pooled metric has misled this project in the same direction: §0.4's
per-signer collapse invisible in pooled test accuracy, the masking A/B, and now this — and this one
was written into four files and a commit message *in the same session that documented the rule
against it*. The rule is not "distrust aggregates when you remember to"; it is **disaggregate by the
grouping variable before quoting any correlation**, because between-group contrast masquerades as
within-group causation every time.

**Also shipped:** `quality` block on all 250 word files (tier + gap runs; frames byte-identical,
verified by diff); `check-export3.py` now **reads** `dominantHand` instead of deriving it from
wrist travel — which is what `finish` had been failing on all along, with a zero-counter guard so
it cannot regress silently; the "per-landmark confidence present" criterion retired by both sides
(null *is* not-visible, so a 4th component was a constant function of the first three — a check
that could not fail, failing a clean export); `preview_signs.build_sequence` now passes the
lexicon, so the Deaf-review overlay can show class, tier and passive handshape.

**🔵 A 2a shape claim that was WITHDRAWN the same day it was written.** An earlier version of
`docs/AVATAR_LIMITS.md` accepted the animation side's ~0.150 "shape fidelity floor" and concluded
~26 words render a cupped hand instead of a flat B. An independent reproduction — their rig and all
250 clips extracted from the base64 in `Fix/avatar-player.html`, `template-check.mjs` reimplemented
from scratch, their exact numbers reproduced — found that in **bone-direction space, the space the
retargeter actually solves for, the error is 0.00° for B, C, `1` and A**, with a rest-hand negative
control that fails. Their 0.150 and their 0.206 template gap were also computed on **different
landmark sets** (20 vs the 14 the rig can fill; the real gap is 0.124), the "half the gap so it
flips" arithmetic fails in simulation at 4000 trials, and effective n is **5, not 35** (the rendered
pose is float-identical across all words of a shape). Do not quote ~0.15 as a floor. **Caveat: that
reproduction's own adversarial reviewers died on a session limit, so it is one strong pass, not
settled.** It also turned up a defect nobody had seen: **0 of 35 2a clips key the distal finger
bones, while 52 of 52 2s clips do.**

**🟢 Four files were carrying a dead `S→A` fallback**, two of them shipped: the contract told the
animation side that `time` needs a substitution it does not, and `asl_handedness_250.json`'s
`_fallback` misdescribed its own sibling's `resolution` map. It is **35/35 on measured templates**,
both map entries inert, and only **5 of 7 templates reachable** (`5` and `O` are requested by no
word). Corrected in `SIGN_ANIMATION_CONTRACT.md`, `asl_handedness_250.json`,
`MODEL_250_MVP_REPORT.md`, `HANDEDNESS_REVIEW_SHEET.md` and §0.4 of this file — where "34/35" had
been sitting **two lines below** the bullet that already refuted it.

### 6. Next actions (2026-08-14)

**Ours, and the only open experiment:**

1. **Run `docs/KAGGLE_EXEMPLAR_RESELECT.md`** — `build_sign_clips.py --require-passive-up 2s-only`.
   **CPU, ~30 min, does NOT consume GPU quota.** Tests whether the 39 tier-C words are recoverable.
   Acceptance: 2a median valid candidates 5 → ~130 and coverage following. It would change the 35
   2a word files, so decide before or after the animation side acts on the current bundle.
   The same doc carries a second cheap cell for the 29302 intra-clip question (§4 below).
2. **Send the bundle** — `deafference_handoff_FINAL.zip`. Frame arrays byte-identical to the copy
   already processed; what is new is the `quality` block, `asl_2a_base_placement.json`,
   `AVATAR_LIMITS.md` and `Fix/REPLY-TO-GHOZLAN-v9.md`.

**Theirs (in the letter, ranked):** the 2a side-guard bug (666 of 1374 frames give the dominant hand
the passive handshape); hold across short gaps instead of relaxing (1177 frames); the distal-bone
defect on the 2a path; re-run `template-check.mjs` in direction space with the negative control.

**Salim's:** Deaf review — and it is **three** reviews, not one: (a) the 250 exemplars *(sheets
ready)*, (b) the 7 handshape template anchors *(never done; the file itself asks for it)*, (c) the
35 2a base placements *(new, never reviewed)*. Plus rotate the burned AWS / Gemini / Supabase keys,
outstanding since 2026-08-12.

**Not fixable, and now written down** — `docs/AVATAR_LIMITS.md`. Headline: the export carries 75
points, 33 pose + 42 hand, and **no face**. ASL grammar lives in eyebrows, mouth morphemes, head
tilt and gaze. For isolated words that is acceptable; for sentences it is a correctness gap, not a
polish item, and it should block any claim that the system "produces ASL" rather than "plays ASL
signs."

### The methodological rule this session earned

**A correlation strong enough to explain every data point is still not a cause.** The layout
table in §0.4 was clean: three pure-R signers on top, two pure-L in the middle, the both-blocks
signer alone at the bottom. It reconciled arithmetically with both pooled numbers. It predicted
the right intervention. And the intervention moved the target signer by −0.0002. The table was
never wrong — the inference from it was. §0.4's rule was "disaggregate before trusting an
aggregate"; this one is its sequel: **once disaggregation hands you a mechanism, the next step is
an intervention that would fail if the mechanism were false, not more description of it.**

---

## 0.8 CURRENT STATE (2026-09-07) — READ THIS FIRST IF YOU ARE A NEW CHAT

Supersedes §0.7 on **two** things: the medical safety gate is now measured rather than
inherited, and §0.7's ship list gates on the wrong statistic. Everything else in §0.7 — the
corpus build, the 0.8383 headline, the lexical-collision diagnosis — is unchanged and still
governs. **The fingerspelling track below is not in §0.7 at all.**

Two tracks moved since §0.7: the **medical MVP** now has a measured gate, and
**fingerspelling** went from nothing to a working CTC baseline in two runs.

---

### ✅ THE MEDICAL GATE IS MEASURED (`5c091dc`, 2026-09-04) — and it refuted its own framing

`measure_medical_gate.py`, on the **1,373 held-out clips from 9 unseen signers**. It **refuses to
print a gate figure until it reproduces the published 0.8383** — it does, exactly, and all four
per-fold accuracies match to 4dp, so the clip loading and the 123-class order are confirmed.

§0.7's open question was: *if the dangerous confusions fire at HIGH confidence, no threshold can
stop them and the never-auto-commit list is the only defence.* **They don't.**

```
53 clips where a dangerous confusion actually fired
 0 of them reached confidence 0.80
    highest any reached: 0.746 (ear -> skin), 0.054 of headroom
```

A 0.80 gate suppressed **every** enumerated dangerous confusion in the test split, including both
non-artefact rows (`hot`→`bad` max 0.673). So `--medical` now runs the **measured L1_CONF 0.80 /
L2_CONF 0.70** instead of the 250-word model's inherited values, and no longer prints the
`UNMEASURED` warning. An explicit `--conf` still overrides.

⚠️ **0 of 53 bounds the true rate at ~5.7% by the rule of three, not at zero.** The direction is
unambiguous; the magnitude is not established.

⚠️ **`measure_conf_gate.py` is superseded for this question.** It scored the per-word **exemplar**
clips, which are *training data*, so it reported precision 1.000 at every threshold — pinned at
the ceiling, carrying no information. Do not resurrect it to answer a gate question.

### 🚨 §0.7's SHIP LIST GATES ON RECALL. A SPEAKING DEVICE NEEDS PRECISION.

This is the most dangerous thing found since §0.7, and it is a flaw in our own safety doc.

The 0.80 ship gate is on **recall** — P(says X | truth X). But when the tool says "pain", the
clinician acts on "pain". That is **precision** — P(truth X | says X).

| word | recall | precision (ungated) | |
|---|---|---|---|
| `who` | 1.000 | **0.455** | wrong 55% of the times it is spoken |
| `no` | 0.909 | **0.714** | §0.7's own headline word — >1 spoken refusal in 4 is not a refusal |

**Recall overstates precision by >0.10 for 20 of the 55 shipped words.**

The gate mostly fixes it. Re-cut on precision at tau=0.80: **11 of 13 failing words rescued, 9 to
1.000** (`no` reaches 1.000). But four words do not clear:

| word | ungated | @ τ=0.80 | **n said @ τ** |
|---|---|---|---|
| `blood` | 0.667 *(n=12)* | 0.667 | **3** |
| `father` | 0.800 *(n=15)* | 0.750 | **4** |
| `always` | 0.800 *(n=5)* | undefined | **0** |
| `tell` | **1.000** *(n=4)* | undefined | **0** |

🚨 **REVISED 2026-09-07 — these are NOT de-ship candidates, and this section said they were.**
The `n` column was missing. At τ=0.80 the four are announced **3, 4, 0 and 0** times: two are
never spoken, the others are 2-of-3 and 3-of-4. **`tell`'s ungated precision is 1.000** — its
only failure is that the gate mutes it. `blood`'s sweep *collapses* rather than converging
(0.667 n=12 → 0.875 n=8 at τ=0.4 → 0.667 n=3 → 1.000 **n=1**), so no operating point is
readable from it. This is a **measurement gap, not a vocabulary decision**; `blood` has 9 true
clips in the whole test split. The safety position is unchanged and independent of the number:
`blood` is never-auto-commit, so a human tap gates it.

**The one finding that survives:** `always` and `tell` are shipping words that **cannot be spoken
at the default τ**. The list should not claim 55 words when two are muted.

⚠️ **Per-word figures rest on 3–23 clips each** and are labelled as such in the report. The solid
number is the aggregate: **0.9872 precision on 702 spoken clips**.

**Also measured, and it is reassuring:** corr(per-signer mean confidence, per-signer accuracy) =
**0.914** — the gate throttles itself on the signers it handles worst rather than failing
confidently on them. Per-signer spread is **1.31×** here against the 250-word model's 2.65×.
`p49` alone is 45% of the test split, at 0.7634.

**A `selftest` asserts that recall and precision DISAGREE on a hand-built case**, so the
distinction this file exists for cannot rot. 9 checks, no models needed.

### ✅ FINGERSPELLING: A WORKING CTC BASELINE, 0.4703 → 0.3730 IN TWO RUNS

Not covered in §0.7. Full analysis in [`FINGERSPELLING_CTC_RESULT.md`](FINGERSPELLING_CTC_RESULT.md),
click-paths in [`RUNBOOK_FINGERSPELLING.md`](RUNBOOK_FINGERSPELLING.md).

| | run 1 (4 shards, `fc6d23c`) | run 2 (16 shards, `5929cbe`) | **run 3 (34 shards, 2026-09-08)** |
|---|---|---|---|
| val CER | 0.4703 *(best, **truncated** at 39/40)* | **0.3730** *(best — the only **converged** run)* | **0.3302** *(best == final at 20/20, **truncated**)* |
| exact phrase | 0.0174 | 0.0445 (2.6×) | **0.084** (1.9×) |
| n_classes | 52 *(bug)* | 60 | 60 ✅ *(TensorSpec `(None,None,60)`)* |
| val sequences | 459 | — | **4,085** |
| per-signer ratio | 2.77× | 3.06× | 3.71× *(wrong statistic — see below)* |
| **absolute gap** | **0.4399** | **0.3945** | **0.3916** |

### 🔴 RUN 3 WAS TRUNCATED, NOT CONVERGED — read this before the analysis below it

`report.json`, read 2026-09-08 **after** the first write-up:

```
best_val_cer        0.33020183699102
final.cer           0.33020183699102
history[20].val_cer 0.33020183699102     identical
final.loss          26.743098199367523 == history[20].val_loss
```

**The best epoch was the last epoch. The run hit its `--epochs 20` cap while still improving.**
0.3302 is a **floor, not a converged value.**

And that refutes the reasoning that chose 20. I had written *"the optimum moves earlier as data
grows: 4 shards peaked at 39/40, 16 before 25."* **39/40 was also a cap.**

| run | cap | best at | verdict |
|---|---|---|---|
| 4 shards | 40 | 39 | truncated |
| 16 shards | 25 | <25 | **the only converged run we have** |
| 34 shards | 20 | **20** | truncated |

**Two of three points were misread, and only run 2 ever converged.**

### ⚠️ WHAT THAT COSTS THE TWO HEADLINE FINDINGS — both are weakened

Everything below was written against `final` figures from a truncated run and is kept for the
reasoning trail, but **neither conclusion is established**:

**1. "The scaling law holds / the curve is flattening 80.9%."** Not established. The
−0.0394/doubling compares a *converged* run 2 with a *truncated* run 3, so the true rate is
**at least** that — the apparent decay could be entirely the missing epochs.

```
 4 -> 16 shards   per doubling -0.0487    (truncated -> converged)
16 -> 34 shards   per doubling -0.0394    (converged -> TRUNCATED, so understated)
```

The direction — more data, lower CER — is solid. The *rate* is not, and **0.291–0.298 at 68
shards is now a conservative ceiling rather than a centre estimate.**

**2. "Data has stopped buying equity."** Also not established, and this was the more strongly
worded of the two. The gap and p203 figures are from an under-trained model, so the flattening
of both could be truncation:

```
absolute gap   0.4399 -> 0.3945 -> 0.3916      closed by -0.0454, then -0.0029
p203 chars right  31.0% -> 41.0% -> 46.4%      +10.0pt, then +5.4pt
```

**What survives is the *existence* of the gap, not its trend.** p203 at 0.5361 against p161's
0.1444 is a 3.71× spread on the same model, and that is real and large whatever the epoch count.
The claim that *the remaining corpus buys p203 only ~+2.7 points* is withdrawn — it extrapolated
a halving that may not be there.

⚠️ **The per-signer ratio (2.77 → 3.06 → 3.71) is still the wrong statistic** regardless — it
widens whenever near-equal absolute gains land on unequal bases. Use the absolute gap.

**A properly converged 68-shard run is the first clean second point we would have**, which is
why the runbook now says `--epochs 25`, not 15.

### What run 3 does confirm, cleanly

| | |
|---|---|
| `n_classes` | **60** — competition charset, `charset_source` names the competition file |
| `val_signers_pinned` | **true**, all 13 — the comparison is controlled |
| `nonfinite_train` / `_val` | **0 / 0** — the length guard held a third time |
| filter | 29,236 kept + 4,723 dropped = **33,959** seqs, **86.1%** (86.5% at 4 shards) |
| `params` | 1,342,524 — unchanged from run 2, so data really was the only variable |
| epoch cost | **6.6 min measured**, against the 8.2 I predicted |

### ⚠️ Level-setting: this model is not usable yet, and the trend does not hide that

CER 0.3302 means **a third of characters are wrong**, and exact-phrase 0.084 means **8 whole
phrases in 100 come out right**. Fingerspelling exists in this product for patient names, drug
names and dosages — where a near-miss is a wrong answer, not a typo. Three rungs of clean
scaling is a real result about the *method*; it is not yet a result about the *product*.

✅ **Both outstanding numbers arrived 2026-09-08, and one of them inverted the conclusion.**

* **`best_val_cer` is 0.3302 — *equal* to `final`, not below it.** That equality is what
  revealed the truncation. I had guessed run 3's best would come in *lower* than its final, by
  analogy with run 2; it came in **equal**, which means the opposite of what the guess implied —
  not "the gain was understated by a best/final mismatch" but "the run never finished."
* **`val_loss` fell 81.16 → 26.74 across the 20 epochs with no rise, so there is no
  overfitting.** Run 1's epoch-23 lesson (CER hid a 39% loss rise) does not apply here — this
  run never got far enough to overfit, which is the same fact as the truncation seen from the
  loss side.

Also note run 1's 0.4703 rested on **459** val sequences against run 3's **4,085** — same 13
pinned signers, but the early figures were noisier than they looked.

**`--val-signers` (`dc7873e`) made run 2 a controlled experiment.** `val_signers_pinned: true`,
and the architecture differs by exactly **1,544 params** = 8 extra classes × (192 dim + 1 bias) —
the charset fix and nothing else, 0.1% of the model. **One variable: 4× data.** The superset claim
is empirical, not inferred: the subset log's 4th shard reads 3,997 sequences / 635,755 frames,
identical to run 1's totals to the digit.

**All 13 signers improved**, mean −0.0953, sd 0.032, no regressions.

⚠️ **The equity statistic was misread once — the correction matters.** corr(old CER, absolute
gain) = **−0.547**, so *harder* signers gained *more*: the absolute gap **narrowed** 0.4399 →
0.3945. The ratio widened 2.77× → 3.06×, but **a ratio widens whenever near-equal absolute gains
land on unequal bases** — it is the wrong statistic here. Use the absolute gap.

🚨 **The floor is unmoved in kind.** `p203` went from 31% to 41% of characters right. Another 4×
would put it near 50%. **Data alone will not make the worst-served signer usable** — which is the
same conclusion the 250-word model reached when an oracle mean-shift moved its worst signer
−0.0018 (§0.5).

### 🚨 THE CHARSET WAS SHARD-DERIVED — 51 chars, not the corpus's 59 (`de7504e`)

Run 1 reported `n_classes 52` against a predicted ~60. **That gap was a bug, and it is the
123-class medical vocab trap wearing a new hat.**

`build_charset()` did `sorted({c for p in phrases for c in p})` over the **attached** shards. Four
shards contain 51 of the corpus's 59 characters. Because the map is a sort of the *observed set*,
adding shards does not append the missing eight — it **inserts** them and shifts the index of
nearly every character after each insertion point. Two silent consequences:

* a 4-shard model and a 68-shard model **share no label space**, so their CER numbers are not comparable; and
* loading one run's `charset.json` against the other's weights **remaps every character**.

`build_charset`'s own docstring warned about precisely this while doing it. Fixed:

* `load_charset()` prefers the competition's own `character_to_prediction_index.json` (59 chars),
  auto-detected under `/kaggle/input`, overridable with `--charset`. **Keys are re-sorted rather
  than trusting the file's indices**, so the mapping is a pure function of the key set.
* the fallback still works but prints a five-line warning naming the hazard, and records
  `charset_source` in **both** `charset.json` and `report.json` so a stale run identifies itself.
* `train()` now **aborts** if any character in the data is missing from the charset. `encode()`
  drops unknown chars, which truncates the label and trains against a phrase nobody wrote.
* Selftest 26 → 32 checks, including one that demonstrates the reindex directly (`c: 2 → 3` when a
  character is added), so the finding cannot rot.

**Also fixed there:** `frames` is freed after the feature pass — it is 2.2× the size of the
features (measured 0.57 vs 0.26 GB at 4 shards). At 68 shards that is **9.7 GB held for nothing**.

### ⛔ THE MEMORY CEILING, AND THE ONE BLOCKING CHANGE FOR THE FULL CORPUS

```
34 shards   peaks 7.03 GB    safe
68 shards   peaks 14.07 GB   OOMs against ~13 GB of GPU-notebook host RAM
```

**Next rung is 34 shards, predicted CER 0.320** from −0.0487 per doubling (n=1 — weak, but
testable). Runbook part 5b (`9a15f75`) has the click-path, and **20 epochs, not 25**.

Going past 34 needs `subset_landmarks.py` to write `frames.npy` **separately** from the metadata
so the trainer can mmap it — **`np.load` cannot mmap a member of an `.npz`.** That is the single
blocking change for the full corpus.

### ✅ Avatar: the medical handoff is built, and the passive hand is REAL here (`bd924d9`)

The medical avatar handoff exists — **55 signs**, [`MEDICAL_AVATAR_HANDOFF.md`](MEDICAL_AVATAR_HANDOFF.md).

🚨 **The passive hand is recorded in 81% of Sem-Lex frames, against GISLR's 0.000.** So the
250-word `renderer_contract` is **corpus-specific** and must not be reused as-is — **branch on
`passiveHandRecorded`**. An avatar animator was hired 2026-09-01 and holds brief v6.1.

⚠️ **The player source is not in this repo.** Runtime owner still unknown.

### ✅ DECIDED 2026-09-07 — the 2s gate is OFF, and the SHIPPED clips were a third configuration

Task 8 asked: passive-wrist gate `off` or `2s-only`? **Off**, and it is not close in either
direction it was tested. But answering it surfaced something bigger.

**The shipped `sign_clips_250.meta.json` was neither arm.** Its gate scope reads
`['2a','2s']` — the gate was on for **both** classes, a third setting nobody had written down,
and it is the worst of the three. All 250 words select a different source clip from either arm.

```
off  vs  2s-only     IMPROVED   0   unchanged 199   regressed 51   (25 fell into tier C)
off  vs  SHIPPED     IMPROVED 237   unchanged   7   regressed  6

tier movement, shipped -> off      C -> A  x56      B -> A  x35      C -> B  x6

median VALID CANDIDATES        shipped -> off
  class 1                          138 -> 143
  class 2s                           3 ->  74        25x
  class 2a                           5 -> 162        32x
```

🚨 **The mechanism is candidate starvation, and it explains both comparisons.** With a median of
3 valid takes for 2s the selector has no choice; with 74 it does. That is why the gate regresses
words *at full coverage* — a hanging passive wrist renders a wrong pose while scoring well.
**56 words were sitting in tier C (unusable) purely because of it.**

The 6 regressions are all class 1, all stay in tier A, and the largest is `hesheit` at −0.138
(then `blow` −0.066, `lips` −0.042, `duck` −0.036, `carrot` −0.019, `talk` −0.009).

⚠️ **Two arms, two CSVs — do not conflate them.** `docs/RESELECT_DIFF.csv` is `off` vs `2s-only`
(cited by `SALIM_TASKS.md` §8); `docs/RESELECT_DIFF_shipped_vs_off.csv` is the new one.

**The handoff was regenerated** from `clips_off.npz` + `clips_off.meta.json`
(`gloss_to_motion.py --per-word`, contact sheet via `preview_signs.py --contact`) →
`deafference_handoff_2026-09-07.zip`, 250 words + 11 files. The generator confirms the same
finding from its own side: **`0 thin-pool (<=2 takes)`**, where the starved arm was built from
pools of 3–5.

⚠️ **`review_log.json` is deliberately omitted from the new package.** It held 28 verdicts, **all
`"unsure"`**, recorded 2026-07-30 against exemplars that have since all been replaced. It carried
no judgement even when current, and shipping it would imply a review of clips it never saw.

⛔ **The zip and `animation_handoff_off/` are gitignored, so they are NOT backed up by git.** The
source of truth for a rebuild is `clips_off.npz` plus the tracked lexicons — same rule as the
`.gitignore` note on `animation_handoff/`.

### ✅ BUILT 2026-09-08 — the golden-fixture parity harness (`golden_parity.py`)

`MODEL_CONTRACT.md` §3 has said *"Do not skip #26"* since 2026-07-15 without providing any way
to do it. It now has one, and #26 is no longer a prose instruction.

The failure it guards is **silent**: a normalization mismatch feeds the model out-of-distribution
input and the model answers anyway — no exception, just quietly wrong predictions. Every wrong
variant below is a *reasonable* reading of the prose spec, which is why the spec was never enough.

**The design rule: stages are separate, and so are their tolerances.**

```
stage 1  normalize      atol 1e-6    pure arithmetic — no excuse for drift
stage 2  NaN semantics  exact        dropped / preserved / padding
stage 3  model logits   atol 2e-3    different kernels — but ARGMAX must match, conf within 5e-3
```

Held under one loose tolerance, a real normalization bug hides inside "the model is only
approximate". Separated, a failure says which stage broke.

**Measured: the JS reference agrees with Python to max 2.44e-7 against a 1e-6 budget** — that gap
is float32-vs-float64 and nothing else, so a genuine logic error lands orders of magnitude above
it. Four plausible-but-wrong implementations were verified to **fail**, each with a diagnostic
naming the actual mistake:

| mistake | verdict |
|---|---|
| centre on the nose, not the shoulder midpoint | `FAIL shoulder midpoint is the origin` |
| centre but never scale | `FAIL shoulder distance is exactly 1` |
| substitute 0 for a missing landmark | `FAIL nan_hand_is_PRESERVED — 42 NaN mismatches` |
| keep a shoulder-less frame instead of dropping it | `FAIL ..._DROPS_the_frame — NOT dropped` |

*(42 = 21 hand landmarks × 2 channels, with z correctly still NaN in both — the diagnostic is
precise, not merely red.)*

⚠️ **Fixtures are generated from the SHIPPING `live_demo.normalize`, not reimplemented here** —
the discipline `verify_fingerspelling_parity.py` established. A harness that restates the spec
tests itself and passes while the demo is wrong.

📌 **Two invariants need no fixture at all:** after normalization the shoulder midpoint is `(0,0)`
and the shoulder distance is exactly `1`. Normalization is **idempotent**, so a double call is
harmless — do not "fix" it by deleting a needed one.

⚠️ **NaN crosses the wire as `null`.** JSON cannot carry NaN, and Python's `allow_nan=True`
emits a bare `NaN` token that `JSON.parse` rejects. NaN is the contract's value for *not
detected*, and the `[0,0,0]` bug was exactly a NaN becoming a zero in transit.

**Noted, not yet resolved — two implementations of §3 differ on the same condition.**
`live_demo.normalize` returns `None` (caller **drops** the frame); `build_sign_clips.normalize_clip`
does `continue` (**keeps** it, un-normalized). Both are defensible *for their own inputs* —
the clip builder's corpus is already normalized, so a skip leaves an already-correct frame
alone, whereas the live path gets raw MediaPipe and must not pass raw coords through. **Written
down so nobody "aligns" one to the other without re-reading which input it takes.**

### Licence position (`f3c2123`) — unchanged in substance, sharper in detail

| corpus | terms | consequence |
|---|---|---|
| Sem-Lex | CC BY-NC-SA | non-commercial **and** share-alike |
| ASL Citizen | non-commercial, **no share-alike** | a **free** release is clean on it; the commercial alias is dead |

Still **licence-blocked for commercial shipping**. A free/research release is not blocked.

### Next actions (2026-09-07)

1. ✅ **RESOLVED 2026-09-07 — the ship list needs no de-shipping, and the question was malformed.**
   Pulling the announcement counts out of `medical_gate_test.json` dissolved it: at τ=0.80 the
   four words are said **3, 4, 0 and 0** times, and `tell`'s ungated precision is **1.000**. No
   word is shown to be bad. **What remains is a measurement ask, not a decision** — `blood` has
   9 true clips in the test split, `always` and `tell` 5 each. **The one real defect: the ship
   list claims 55 words while `always` and `tell` are muted at the default τ.** Fixing that is
   arithmetic on the list, not a clinical judgement.
2. ✅ **DONE 2026-09-07 — `MEDICAL_SAFETY_GATES.md` now carries precision inline.** The
   precision re-cut itself already existed: `5c091dc` was **110 insertions, 0 deletions**, so it
   *appended* §4b and a top banner but never touched §1, §2 or §3. Every table a reviewer meets
   first still showed recall unlabelled, with the correction 170 lines below — in a document
   whose stated purpose (line 3) is review by a Deaf signer or a medical interpreter. §1/§2 now
   label the statistic and name the four words that move (`no`, `more`, `blood`, `always`); §3
   records that its exclusions were *conservative*, because recall overstates precision, so no
   word leaves the cannot-express list.
3. ⚠️ **DONE but TRUNCATED 2026-09-08 — 0.3302 at epoch 20 of 20, still improving.** Not a
   converged number. `report.json` received; no overfitting (val_loss 81.16 → 26.74, monotone).
   **Re-running 34 shards is not worth the quota — go straight to 68 at `--epochs 25`.**
4. ✅ **DONE 2026-09-08 (`6c6e9a6`) — `frames.npy` is a sidecar and 68 shards is reachable.**
   `np.load` cannot mmap a member of an `.npz`; it now can, and both layouts load so the three
   existing baselines stay readable. Runbook **Part 5c** has the click-path: `--epochs 25`,
   ~5.6 h CPU + ~5.5 h GPU. **0.291–0.298 is a conservative ceiling, not a centre estimate.**
5. ⚠️ **WEAKENED, not established — the equity trend.** The gap and p203 figures came from a
   truncated run, so their flattening may be truncation. **What is solid is the SIZE of the
   gap** (p203 0.5361 vs p161 0.1444, 3.71x on one model), not that data has stopped closing it.
   Re-measure on the converged 68-shard run before concluding anything. My earlier "+2.7 points
   and no more" is withdrawn.

### The methodological rule this session earned

**Name the statistic the product needs, then check the doc measures that one.** The gate work was
sound and the ship list was gated — on recall, which reads like safety and is not. `who` at recall
1.000 is wrong more than half the times it speaks. A measured number against the wrong definition
is more dangerous than an unmeasured one, because it stops the question being asked.

---

## 0.7 STATE AS OF 2026-08-27 (later) — ⚠️ SUPERSEDED IN PART BY §0.8, READ THAT FIRST

Supersedes §0.6 **only** on the medical track. §0.6's recognition-model numbers and its
fold-ensemble evaluation rule are unchanged and still govern.
⚠️ **§0.8 supersedes this section's gate values (now measured) and its ship list's gating
statistic (recall, where the product needs precision).**

### The medical corpus is now buildable end to end

Three defects found and fixed by measurement, not inspection:

| what | was | is |
|---|---|---|
| `--canonical-hand` on Sem-Lex | assumed to be the fix | **would delete a real hand in 41.2% of clips** |
| the 338 double-glossed videos | last CSV row silently won | resolved by policy; 17 quarantined |
| `.npz` → `train.py` | did not exist | built, verified through `train.py`'s own loader |

**1. `--canonical-hand` is refused; `--canonical` (mirror only) replaces it.**
`extract_canonical.py`'s header states the measurement it was designed around — GISLR has BOTH
hands live in 1.7% of clips, so reserving block 33-53 costs nothing. Sem-Lex measures **41.2%**
(3,000 clinical clips). `canonicalize()` ends with `a[:, RESERVED_BLOCK, :] = np.nan`, so on this
corpus it deletes a genuinely recorded passive hand in two clips in five — and masking that hand
on GISLR, where it was the *only* hand, already cost **0.0312 test / 0.0415 val**
(`pick_signing_block` docstring, 2026-08-13).

The real discriminator is **between corpora, not within signers**: GISLR's L-share of one-handed
clips is 42% — near chance, uncorrelated with handedness, an arbitrary recording convention.
Sem-Lex's is **23.5%**, tracking its measured **19.5% (8/41)** left-dominant signer rate. The
blocks mean what they say. (A per-signer "one-handed clips split L/R" flag was tried first and
was the wrong axis — it fires at 70/30 splits, which is MediaPipe L/R label noise plus dropout.)

But the mirror half is still wanted, for parity: `live_demo.py --canonical` mirrors every live
segment. Train un-mirrored and the medical model must run *without* `--canonical` while the
250-word model runs *with* it. So `semlex_poses_to_75.py --canonical` means **mirror only** —
negate x, `POSE_FLIP`, and **swap** the hand blocks. Opt-in, default OFF.

**And the mirror decision is PER SIGNER, not per clip — the tripwire caught the first version.**
Deciding per clip by `wrist_travel` (which arm moved more) mirrored **3,587/6,996 = 51.3%** of a
corpus with only **18.4%** left-dominant clips. A coin flip, because 41.2% of clips are genuinely
two-handed *and* the trimmed span includes the bilateral hand-raise, so both wrists travel
comparably and the sign of the difference is noise — and path length, being a sum of `|diffs|`,
accumulates noise instead of cancelling it.

Handedness is a property of a person. Aggregating block presence per signer is **bimodal with a
0.100 gap between 0.463 and 0.563** across 41 signers, so any threshold in 0.50–0.60 picks the
same 8 signers = 18.4% of clips. `--canonical-mode signer` is the default; `--canonical-mode
clip` reproduces the refuted rule, kept like `--no-trim`.

⚠️ The inversion is the transferable lesson: on GISLR block presence was a recording artifact and
useless for handedness, while per-clip motion was decisive. Here both hands are recorded, so
presence becomes the reliable signal and motion the unreliable one. **Same two statistics,
opposite verdicts, because the corpora were collected differently.** Never port a dominance rule
between corpora without re-measuring it.

### ❌ AND THEN CANONICALIZATION ITSELF WAS REFUTED (2026-08-28). Train on `data_medical_landmarks`.

The A/B ran on **fold 2**, chosen because it is the only split with the power to measure this:

| split | val clips | left-dominant signers in it | share | power |
|---|---|---|---|---|
| fold 0 | 1,374 | — none — | 0.0% | ⛔ cannot measure it |
| fold 1 | 1,385 | — none — | 0.0% | ⛔ cannot measure it |
| **fold 2** | **1,391** | **57(438), 46(380), 61(152), 76(26)** | **71.6%** | ← the one to run |
| fold 3 | 1,373 | 53(59), 47(4) | 4.6% | too thin |
| test | 1,373 | 11(170), 23(58), 24(4) | 16.9% | usable, 6× diluted |

Whole-signer splitting put both big left-dominant signers in one bucket. **Running fold 0 would
have returned a null by construction** and it would have read as "canonicalization doesn't help."
Always check which held-out split contains the population an intervention targets.

Result, same split, same seed, `--decimate 0.5` on both arms:

```
landmarks  val acc 0.7477   (epochs_run 200)
canonical  val acc 0.7484   (epochs_run 187)
CANONICAL - LANDMARKS = +0.0007        <- one clip out of 1,391
```

**Flat, on the most favourable split that exists.** And the mechanism is printed in both runs' own
config line:

```
[cfg] layout = LEGACY (L@33-53, R@54-74) | hflip swaps hands = True
```

`train.py`'s hflip augmentation already mirrors the clip **and swaps the hand blocks** on 50% of
samples every epoch — the identical operation `--canonical` performs, applied stochastically at
train time instead of statically at extraction. The model was already handedness-invariant, so
pre-canonicalizing the input is redundant.

This also retro-explains §0.6: canonical-vs-legacy on the 250-word model was **+0.0032 at 30 fps**,
likewise nothing. The measured win there was **`--decimate`** (+0.0218 paired at 7 fps), never
canonicalization. Two corpora, two null results, one conclusion: **as long as hflip swaps hands,
static canonicalization buys nothing.** It is only worth reaching for if that augmentation is
turned off.

`--canonical` stays in the adapter as a measured-neutral option (like `--no-trim`), not a
recommendation. The medical model trains on **`data_medical_landmarks`** — fewer steps, no mirror,
and it runs on `live_demo.py` *without* `--canonical`.

### ✅ v2 (2026-08-29): 0.8383 test — and the two ASL-LEX predictions both landed

`semlex-medical-v2`, 123 classes (pain absorbs hurt), **same 9 test signers / 1,373 clips** as
the 0.8245 run, so this is a paired comparison, not a fresh draw.

```
fold0 0.8099  fold1 0.7946  fold2 0.8208  fold3 0.7997   mean single 0.8063
ENSEMBLE  0.8383  (+0.0321 vs mean single)      top-5  0.9512
MACRO     0.7344      median 0.8421     buckets >=0.9: 50  >=0.8: 67  >=0.7: 75
```

**`pain` 0.222 -> 0.971.** The merge did exactly what the confusion matrix said it would, and
the merged class beats what `hurt` scored alone (0.923). **`today` 0.10, `now` 0.667** — still
confused, exactly as predicted when MERGE-02 was reverted. Two pre-registered predictions from
one ASL-LEX lookup, both confirmed.

⚠️ **Do NOT credit the merge with the whole +0.0138 micro.** Account for it honestly:
old `pain` 9 clips @0.222 (2 right) + `hurt` 26 @0.923 (24 right) = **26 of 35**; new `pain`
35 @0.971 = **34 of 35**. That is **+8 clips = +0.006 micro**. The measured gain is +19 clips,
so ~11 clips came from retraining variance and one fewer competing class. The merge is real,
worth about half a point, and the rest is noise.

🔬 **`today` is now a clean natural experiment.** It and `now` differ in exactly ONE of 17
ASL-LEX features — Repeated Movement — and the model scores 0.10 vs 0.667 on them. If
`--decimate 0.5` plus the 64-frame resize is what erases repetition, turning decimate OFF
should lift `today` specifically **even if overall accuracy falls** (decimate measured +0.0218
on the 250-word model, so it should fall). That is a pre-registered, falsifiable A/B and it now
costs **34 minutes**, not a day.

⏱️ **Training is 16-17 min/fold on a T4 x2, ~70 min for all four** — not the 4 h estimated.
Both A/Bs on this corpus are lunch-break experiments; scope experiments accordingly.

### 🏆 THE CLINICAL MODEL SHIPS A NUMBER (2026-08-28): 0.8245 test on 9 unseen signers

4-fold ensemble, `data_medical_landmarks`, `--decimate 0.5`, scored on **`split == "test"` only**:

```
savedmodel_fold0  0.7961      mean single-model  0.7948
savedmodel_fold1  0.7932      ENSEMBLE           0.8245   (+0.0296 vs mean, +0.0175 vs best single)
savedmodel_fold2  0.8070      ENSEMBLE top-5     0.9512
savedmodel_fold3  0.7830      per-word MACRO     0.7202   <- QUOTE THIS
                              per-word median    0.8377
```

**This beats the 250-word model — 0.8245 vs 0.7787 — and on 9 held-out signers instead of 3.**
Predicted "well below 0.7576" twice and was wrong twice: 124 classes instead of 250, studio-recorded
prompted signs instead of in-the-wild GISLR, and the dead-air trim are each worth more than expected.

**Quote the MACRO — but say WHICH macro.** 0.7202 averages 122 classes of which **15 have ≤2 test
clips**, and a class with one test clip scores exactly 0.00 or exactly 1.00. It measures nothing.

```
test-n per class            macro restricted by evidence
n  1-1  :  7 classes  0.286      n>= 1 : 122 classes  0.7202
n  2-2  :  8 classes  0.438      n>= 3 : 107 classes  0.7697
n  3-4  : 17 classes  0.789      n>= 5 :  90 classes  0.7660
n  5-9  : 39 classes  0.660      n>= 8 :  56 classes  0.8263
n 10-19 : 29 classes  0.800      n>=10 :  51 classes  0.8474
n 20+   : 22 classes  0.910
```

⚠️ **Do NOT read the rising right-hand column as "the model is really 0.85."** Test is a 22%
whole-signer split, so test-n is proportional to *training* n: a thin class is both **unmeasured and
undertrained**, and this table cannot separate the two. That `n 3-4` (0.789) sits *above* `n 5-9`
(0.660) is proof the small buckets are variance, not signal.

**The defensible product claim: 55 concepts at ≥0.80, each on ≥5 test clips.**
Of the 90 measurable classes: **39 ≥0.90 · 55 ≥0.80 · 61 ≥0.70.** The earlier "50/66/75" counted
noise at both ends — some of those words earned 1.000 on a single clip. The other **32 classes have
<5 test clips and are unquotable in either direction** (afternoon, arm, ask, better, bleed, bone,
can, child, choke, close, dizzy, eat, face, feet, headache, interpreter, itch, light, look, mouth,
muscle, nose, nurse, please, thankyou, throat, tongue, touch, what, when, worse, yesterday).

**micro 0.8245 is unaffected by any of this** — it is clip-weighted, and it is the right number for
stream accuracy. Quote **top-5 0.9512** for the UX ceiling: `live_demo` ships 1–5 fix keys.

**Do not hand-curate that list.** `training/medical/select_ship_vocab.py` applies both gates
(`n >= --min-test-clips` AND `acc >= --min-acc`) to `ensemble_test.json` + its confusion matrix and
emits a `topic_*.json`-shaped file that `live_demo.py --words` reads directly. It separates
*unmeasured* from *weak*, which is the distinction the first hand-made list got wrong, and it refuses
to run if the confusion matrix and the report disagree.

```
python training/medical/select_ship_vocab.py \
    --report .../art_medical/ensemble_test.json --out clinical_ship_vocab.json
```

### ✅ DIAGNOSED 2026-08-29: the failures are LEXICAL COLLISIONS — not landmarks, not imbalance

Read from `ensemble_test.confusion.csv`. **Both standing hypotheses are refuted.**

*Not imbalance.* If the 170× skew were eating small classes, `water` (341 train clips) would top the
over-prediction list. It is not on it at all. Worst absorber is `who` at **+12 of 1,373** — the model
is not collapsing onto frequent classes.

*Not missing face landmarks.* The only face-location confusion in the whole matrix is
`tongue → teeth/mouth`, at **n=2**. The 75-point layout is not the bottleneck. This kills a proposed
re-extract at 100+ points.

Every confusion with enough clips to mean anything is a **near-minimal pair or a true synonym**:

| pair | clips | why |
|---|---|---|
| `today → now` | **7/10** | near-identical citation form |
| `pain → hurt` | **6/9** | the same sign — see below |
| `where → ask` / `where → who` | 4 + 3 | one-index wh-questions |
| `sometimes → show` | 4 | |
| `maybe → want` | 4 | two-handed, palms up, alternating |
| `man → woman` / `man → father` | 3 + 3 | forehead vs chin, same handshape |
| `lungs → tired` | 3 | two-handed chest |
| `heart → feel` | 3 | middle finger on chest |

And the genuinely weak list (n≥5, so it is real) is dominated by **function words and directional
verbs, NOT clinical content**: take 0.00, today 0.10, sometimes 0.20, strong 0.40, why 0.40,
some 0.43, all 0.44, maybe 0.47, come 0.50, long 0.50, give 0.54, go 0.59, not 0.59. Only 8 of the 21
are clinical (heart 0.17, ear 0.20, pain 0.22, burn 0.40, faint 0.40, weak 0.43, back 0.50,
lungs 0.50). **For a medical MVP that is the good failure mode** — the symptom and object nouns hold.

GIVE / TAKE / COME / GO are **directional verbs**: their form carries spatial agreement, so
within-class form variance stays high even in citation recordings. Plausible mechanism, **NOT tested**.

### 🚨 `not` scores 0.59 — a negation error INVERTS a medical statement

`not` (n=17, 0.59) plus the polarity/quantity words `all` 0.44, `some` 0.43, `maybe` 0.47 are exactly
the words where being wrong is far worse than being silent ("I am *not* allergic"). The L2-confirm
rule above (line ~285) already lists negation as never-auto-commit — **that gate is now backed by a
measurement rather than a hunch. Do not ship `not` on the auto-commit path at any confidence.**

### ⚠️ RETRACTED: "body parts are the weakest category" (claimed 2026-08-28)

That table read `arm 0.00 / throat 0.00 / tongue 0.00` as a category weakness. **It was sample size:**
arm n=2, throat n=1, tongue n=2, itch n=1, child n=1, close n=1, headache n=2. `take n=6` produced six
*different* wrong answers — noise with no structure. Nothing about body-part signs is established.
Line 985's warning about `interpreter` having 1 val clip was the right instinct, not applied to test.

Several apparent zeros still trace to gloss ambiguities quarantined at manifest time — `close`
(vs NEAR), `take` (vs STEAL), `light` (weight / lamp / bright). Those are vocabulary defects, not
model defects, but they are also all thin classes now.

### ⚠️ `pain` 0.222 while `hurt` 0.923 — THE SAME SIGN. Merge them. (`today`/`now` too.)

Confirmed by the matrix: **6 of 9 `pain` clips are predicted `hurt`.** The most important word in a
clinical vocabulary cannot separate from its synonym, so it collapses onto the more frequent gloss.
`build_clinical_manifest.py` already caught the evidence — video `PBiQBaqwWVoYJYuio4u0` carries *both*
glosses and was quarantined for exactly this. **`today → now` is the same mechanism, 7 of 10.**

**Fix in `build_vocab.py`'s CONCEPTS map**, the same way `knee` absorbs `knees`:
`"pain": ["pain", "hurt"]` and `"now": ["now", "today"]`. Free, and each turns two half-broken
classes into one strong one.

⚠️ **Put both in front of a Deaf reviewer first**, alongside the 17 in `docs/CLINICAL_GLOSS_REVIEW.csv`.
Merging two signs a native signer distinguishes is worse than the confusion it fixes.

### ⚠️ 0.7477 is a MICRO average and must not be quoted as the model's accuracy

```
worst 5 words: {'burn': 0.0, 'ear': 0.0, 'face': 0.0, 'faint': 0.0, 'heart': 0.0}
```

Five classes at **exactly zero**, and `heart` / `ear` / `face` are core clinical vocabulary. With
**170× class imbalance** (`water` 341 clips vs 8-clip classes) the micro average is carried by a
handful of frequent words. The macro average — mean over the 124 words — is the honest figure and
is not yet measured; the `eval_*.json` files were lost twice to Kaggle save failures.

Per-word numbers in the tail are also near-meaningless: `interpreter` has **1** val clip, so its
"1.000 → 0.000" in the A/B is a single clip flipping, not evidence.

⚠️ **Kaggle operational lesson, learned twice:** a commit that finishes its cells can still hang
for hours in the output-save step and report `Output 0 B` — losing every artifact while the printed
numbers survive in the Logs. **Print results into the log** (`json.dumps(report)`), never rely on
`/kaggle/working` being saved.

**2. The 338 double-glossed videos are resolved by policy** (`build_clinical_manifest.py`).
Three facts drive it, and the first invalidates the priority order quoted in `build_vocab.py`:

* all **6,192 `signbank` rows carry a bare integer** in `label` — a SignBank reference id, not a
  gloss (`heart` vs `3369`). So "asllex > signbank > freetext" would have labelled a video
  `1117` over `drawn`. signbank is **dropped**, not ranked. Resolves 90 with no judgement.
* `asllex` (curated ASL-LEX) beats `freetext` (submitter typing). Resolves 96 more — and often
  that is the point: `NetqYFVxLCOaSt37hO7V` is `close` (freetext) / `near` (asllex), which are
  different signs, so the asllex gloss correctly removes it from the clinical set.
* a **tie inside one `label_type` is a real ambiguity** → quarantined, never guessed. All 17 are
  the linguistically dangerous set: `sick`/`very_sick`, `sick`/`upset`, `tired`/`not_tired`,
  `bad`/`badass`, `not`/`slide`, `cold`/`refrigerator`, `head`/`kiss`, `show`/`example`,
  `strong`/`dominant`, `sneeze`/`sneeze_2`, and `hurt`/`pain` (two of OUR classes on one video —
  no neutral choice exists). 17 of 8,102 is 0.21%; being careful is free.
  → `docs/CLINICAL_GLOSS_REVIEW.csv`, **verdict column empty** (Sem-Lex is CC BY-NC-SA).

Result: **8,102 clips / 145 concepts / 41 signers**, deterministic. Also measured: `duration` is
**milliseconds** (median 1,936); 915 videos appear under two Sem-Lex splits; **0 videos have two
signer_ids**, so `signer_id` is safe.

**3. `npz_to_train_format.py` writes what `train.py` reads**, whole-signer, and it is verified by
calling `train.py`'s own `load_vocab`/`load_dataset` rather than by re-implementing the contract:

```
125 classes, 6,906 rows, 6,906 arrays, 0 dropped
fold 0..3: signer overlap 0        test: 8 signers, overlap with any fold's train 0
```

The whole-signer rule is not tidiness — `train_man = cv[cv["fold"] != fold]` means a signer in
two folds is in fold k's *training* set while also in its val set. That is exactly the §0.6 leak.
Buckets are filled **largest-first into the lightest bucket**, which holds 19.8-20.2% per bucket
despite the corpus's 330× signer concentration. `is_outlier` is all False — Sem-Lex has no
measured outlier flag and inventing one would be a hidden modelling decision.

⚠️ **Scoping decision still open, and it is Salim's:** at `--min-clips 8 --min-signers 2`,
**20 of 145 concepts are pruned**, leaving 125. Three more (`how`, `light`, `shoulder`) survive
but land with **no test clips**, so they cannot be scored at all. Drop them, or supplement from
ASL Citizen / a recording session.

---

## 0.6 STATE AS OF 2026-08-27 — ⚠️ SUPERSEDED IN PART BY §0.7, READ THAT FIRST

Supersedes §0.5 **only** on the recognition model's headline number and on how to evaluate a
fold-ensemble. Everything else in §0.5 — the refuted levers, the per-signer variance being a
product fact, "Working with Salim" — still stands.

### 🏆 The 250-word recognition track has a new best, and it ships

4-fold ensemble on the **canonical** corpus trained with **`--decimate 0.5`**, scored on the test
split, mean over signers:

| rate | ensemble | fold 0 alone | ensemble gain |
|---|---|---|---|
| **30 fps** | **0.7787** | 0.7579 | +0.0208 |
| 15 fps | 0.7707 | 0.7528 | +0.0179 |
| **7 fps — the demo's real rate** | **0.7628** | 0.7442 | +0.0186 |

Beats the legacy ensemble's **0.7755** — but **+0.0032 at 30 fps is inside the noise on three
signers, so do not sell the win on it.** Three stronger facts:

1. **All four folds beat their counterparts:** 0.7579 / 0.7608 / 0.7626 / 0.7636 vs
   0.7544 / 0.7570 / 0.7545 / 0.7615.
2. **7 fps is the real win.** The paired fold-0 A/B measured **+0.0218** there and cut the
   frame-rate penalty from **5.13 to 2.64 points**. The legacy ensemble has **no** measured 7 fps
   number on this pool, which is why recording ours matters.
3. **Fold 0 reproduced the shipped model to 0.0003** (0.7579 vs 0.7576) — canonical + decimate
   costs nothing at 30 fps, so the ensemble gain is pure profit.

`--decimate 0.5` was the **one** positive result after fourteen refuted hypotheses. The
monotone dose-response across three rates *is* the result, not the point estimate.

### ⚠️ DEPLOYMENT REQUIREMENT

These weights are trained on the **canonical** corpus (L-block 0.000). **`live_demo.py` must run
with `--canonical`.** Without it a left-dominant signer's hand stays in the 33–53 block, which
this model has never seen. Ship into a **new** `artifacts_250_canonical/`; leave `artifacts_250/`
in place as the rollback.

### ⛔ THE EVALUATION RULE THIS SESSION EARNED

**Score a fold-ensemble on the TEST split only. Never on any fold's val.**

`per_signer.py`'s 7-signer pool is fold-0 val + test. It is honest for **fold 0's model alone** —
`train.py:915` is `train_man = cv[cv["fold"] != fold]`, so folds 1/2/3 **trained on fold-0's val
participants**. Per-signer @ 30 fps proves it directly: on the 3 clean signers all four folds
agree within ~0.01 (53618: .7033 / .7063 / .7031 / .7051); on the 4 leaked signers fold 0 is the
lone outlier (32319: **.6114** vs .8930 / .8910 / .8959 — a 28-point gap). Note too that the
ensemble beats every member on clean signers and sits *below* folds 1–3 on leaked ones, because
fold 0's honest prediction drags the average down.

**The all-7 figures (0.7810 / 0.7731 / 0.7529) are inflated. Do not quote them.**

**🚫 29302 WAS NOT FIXED.** Its only honest number is fold 0's **0.3190** (legacy control 0.3141 —
statistically the same). The **0.5568** in the ensemble column is memorization. This project has
been misled by a pooled number three times (§0.4, §0.5, and the 2s reselect); that cell is the
fourth trap and it is the most tempting one yet, because it lands on exactly the signer the
canonicalization programme existed to rescue.

**Structural limit to record:** no honest ensemble number for 29302 / 34503 / 32319 is obtainable
under the current split, because they sit in fold-0 val and therefore in folds 1–3's training
data. Fixing that needs the folds re-assigned so an L-dominant signer sits in `test`, or
leave-one-signer-out. Until then, fold 0 alone is the only honest read on them.

**Product number for a new user: 0.70–0.82 @ 30 fps.** 53618 is the floor (0.72) and is the test
signer with 0.13 L-block contamination — the layout effect leaking faintly into a split §1.0 of
`MODEL_250_MVP_REPORT.md` says cannot measure it.

### Also settled this session

- **Sem-Lex licence: CC BY-NC-SA 4.0 — no commercial use, and Share-Alike would bind derived
  weights.** Access is a Google Form, not an email negotiation. Feasibility study is still legal.
- **Sem-Lex poses are 553 landmarks, not 543** (face mesh + 10 iris; every index after the face
  block shifts +10). `training/medical/semlex_poses_to_75.py` + `test_semlex_adapter.py` handle
  it; the offsets were verified geometrically, not assumed. `test_parity.py` cannot catch this —
  it compares functions, and the functions were right.
- **Clinical tier A is 129, not 130** (`knee` has 7 deduped videos against a ≥8 gate). Sem-Lex's
  own `val` shares 31/32 signers with `train` — score on `split == "test"` only.
- **The 2a exemplar reselect shipped** (+0.397 coverage, 24 tier-C words → 0, relaxFrames −82%),
  35 files replaced surgically. `docs/HANDEDNESS_REVIEW_29.csv` is the Deaf-review shortlist that
  Sem-Lex's `Sign Type` annotations identified.
- **Fingerspelling landmark parity verified 13/13**, but ~45% of frames have no tracked hand,
  dropout is 3.6× motion-correlated, and interpolation recovers only 12.4% of lost frames. Start
  from a public competition baseline. The pose wrist survives, so feed pose + hands, never hands
  alone.

---

## 1. The project in one page

**Deafference** is a sign-language → speech product. Pipeline:

`camera → MediaPipe landmark extraction → normalize → sliding window / sign
segmentation → sequence model (classifies ONE isolated sign) → confidence gate →
gloss buffer → grammar/AI turns glosses into a sentence → captions + text-to-speech`

- **Phase 1 = ASL** (current): ~30-word MVP vocabulary, being expanded to 250.
- **Phase 2 = LSL** (Lebanese Sign Language): reuses the architecture; the real
  differentiator/moat (no big-tech competition, RTL/Arabic).
- **Privacy stance:** sign recognition runs **client-side** (TF.js in the browser).
  Video/landmarks are **biometric and never leave the device.** Only the recognized
  *words* (glosses — plain text, not biometric) may go to a cloud LLM for sentence
  generation. This is the core architectural constraint — respect it everywhere.

**Critical nuance the model has:** it recognizes **one isolated sign per window.**
It is NOT continuous sentence recognition. The "sentence" comes entirely from a
post-processing layer (grammar rules, or an AI) that takes the ordered list of
recognized words and phrases them. This is why the AI sentence step matters.

---

## 2. Team & roles

- **Salim** (`salim@deafference.com`) — team lead + backend/ML + dataset owner. Ran
  the train→validate→export pipeline. Drives the demo and the strategic calls.
- One other backend teammate (owns Clean+Preprocess and the Track B website API
  tasks BE-1…BE-9).
- Two frontend devs (the camera→speech browser app).

---

## 3. `live_demo.py` — the main deliverable (full detail)

### 3.1 What it is
A single standalone Python script at the repo root. Opens the webcam, runs
MediaPipe Holistic, and does the whole pipeline **without the browser/frontend**.
It is the bridge for demoing the model until the browser pipeline is built.

### 3.2 How it works (pipeline inside the script)
1. **Threaded camera** (`Camera` class) grabs the freshest frame (no capture lag).
2. **Mirror + MediaPipe Holistic** → landmarks.
3. **`extract_75()`** builds the 75-point layout: pose 0–32, left hand 33–53,
   right hand 54–74 (NaN for anything undetected).
4. **`normalize()`** — shoulder-midpoint centered + shoulder-width scaled on x,y
   (MUST match training preprocessing; see §7). Returns `None` if both shoulders
   aren't visible (frame dropped rather than mis-scaled).
5. **Sign segmentation (auto-commit)** — see §3.4. Collects a sign's frames.
6. **`classify_segment()`** — resamples the collected frames to exactly 64
   (`time_resize`, matching training) → runs the model → softmax. With `USE_TTA`
   it also averages the mirror of the clip (the model was trained with hflip).
7. **Confidence gate (0.50)** → append the word to the gloss buffer.
8. **DONE** → `finalize()` turns the gloss buffer into a sentence (rules or AI) →
   **speaks it** (Windows SAPI).

### 3.3 The model it loads — and WHY SavedModel
It loads the **exported TF SavedModels** from `artifacts/savedmodel_fold{0..4}/`
via `tf.saved_model.load(...)`, and averages their softmax (5-fold ensemble).

> ⚠️ **Do NOT switch to the `.weights.h5` files.** They were saved on Linux and do
> **not load on Windows** (a tf-keras path-separator bug: it looks up
> `layers\stem_dense` with a backslash and finds 0 variables). SavedModel is a
> pure-TF format with no Keras-version dependency and sidesteps this entirely.
> Also: `train.build_model` uses raw `tf.matmul` on symbolic tensors, which only
> works under the **Keras 2 API (tf-keras)**, NOT Keras 3 — another reason we load
> the SavedModel graph directly instead of rebuilding the architecture.

Input `[1,64,75,3]` (raw x,y,z), output `[1,30]` **logits** → we apply softmax.
The z channel and motion features are handled by the model's embedded
`PreprocessLayer` (see §7).

### 3.4 Sign segmentation & the "make it fast" work
The naive approach (a rolling 64-frame window fed continuously) was **slow**: a new
sign had to "outvote" ~4–5 seconds of stale history before it dominated. We
replaced it with **segment-then-classify**, which also matches training (each
training clip was one isolated sign resampled to 64 frames):

- **Start a sign** when hands appear (after a cooldown). A **pre-roll** of the last
  8 frames *before* hands are detected is prepended — critical for signs performed
  **at the face** (e.g. `hello` = forehead salute) where MediaPipe's hand detector
  kicks in late but the pose still tracks the arm.
- **End a sign** when hands lower (`END_FRAMES`) or hold still (`STILL_FRAMES` +
  `MOTION_EPS`), then classify + commit.
- **Early commit** — while signing, a cheap single-model preview runs every
  `PREVIEW_STRIDE` frames; if it's confident (`EARLY_CONF=0.80`) about the same
  word twice in a row, the word commits **instantly, mid-sign** (this is what makes
  strong signs feel snappy). Live guess shows as `~ word (0.87)`.
- **Flicker tolerance** — if hand detection drops mid-sign, capture keeps going
  (those frames just have NaN hands, exactly like training padding).
- **Guards:** a post-commit `COOLDOWN` and same-word suppression within
  `DUP_SECONDS` prevent one held sign from committing twice.
- Below-gate segments show **"not sure (word 0.42) — try again"** instead of
  silently doing nothing.
- Every committed segment prints a diagnostic to the terminal:
  `[seg]  28 frames (19 with hand) -> hello:0.91  bye:0.04  wait:0.02` — use this
  to tell whether a failure is capture (too few frames/hands) or the model.

### 3.5 Sentence generation: rules vs AI
- **Default (`python live_demo.py`)** — offline **rule engine** (`grammar_rules.json`,
  copied self-contained into the script as `render_sentence`). Instant, can't fail,
  but only knows the ~44 authored gloss combos. Shows a live preview while signing.
- **`--ai`** — the sentence is built **entirely by the AI** (Gemini by default),
  **no rules fallback** (Salim's explicit choice: prove the AI is doing the work).
  Runs off-thread so the video never freezes. On error it shows the error, not a
  rules sentence. In `--ai` mode there is no rules preview — the sentence only
  appears on DONE.

### 3.6 Text-to-speech
Uses the **Windows SAPI voice directly via `win32com`** (from pywin32), NOT
pyttsx3. Reason: pyttsx3's `runAndWait()` in a background thread **only fires once**
("speaks the first time, then silent" — the bug we hit). SAPI's `Speak()` works
every time. Runs in a worker thread with `pythoncom.CoInitialize()`.

### 3.7 UI / controls
Fullscreen canvas: camera centered, top bar shows the sentence + `signs:` list,
bottom bar has buttons, right margin shows the optional word list.

| Control | Key | Does |
|---|---|---|
| DONE | Enter | finish sentence → build + speak it |
| UNDO | Backspace | remove last committed word |
| CLEAR | c | reset the sentence |
| SPEAK | s | toggle live per-word speech (also speaks on DONE regardless) |
| WORDS | w | toggle the on-screen 30-word list (on by default) |
| say now | space | speak the current sentence immediately |
| quit | q | exit |

DONE/UNDO/CLEAR/SPEAK/WORDS are also **clickable buttons** (mouse works because the
canvas is rendered 1:1 at screen resolution with `SetProcessDPIAware`).

### 3.8 Flags & modes
- `python live_demo.py --selftest` — **no camera**; loads the model and predicts on
  random input. Proves the model half works. Prints latency (ensemble ~46 ms warm).
- `--single` — fold-0 only (faster, 0.9386 vs 0.9433).
- `--fast` — MediaPipe pose complexity 0 (~2× fps, but weaker hand detection near
  the face — `hello` may suffer). Default is complexity 1.
- `--ai` — AI sentence generation (see §3.5).

### 3.9 Config knobs (top of the file, all commented)
`MAX_LEN=64`, `CONF_GATE=0.50`, `USE_TTA=True`, `MIN_SEG=6`, `MAX_SEG=84`,
`END_FRAMES=10`, `STILL_FRAMES=7`, `MOTION_EPS=0.02`, `PRE_ROLL=8`,
`MIN_HAND_FR=4`, `PREVIEW_STRIDE=6`, `EARLY_MIN=14`, `EARLY_CONF=0.80`,
`COOLDOWN=12`, `DUP_SECONDS=2.0`, `MP_COMPLEXITY=1`.
Raise `EARLY_CONF` if early commits feel trigger-happy; lower it if slow. Raise
`CONF_GATE` for fewer wrong words, lower to surface more.

The full end-user run guide is **`RUN_LIVE_DEMO.md`**.

---

## 4. Environment (the hard-won stack — do not "upgrade" casually)

Windows / Python 3.11. Pinned in **`requirements_live_demo.txt`**. The constraints
interlock:

| Package | Version | Why this exact version |
|---|---|---|
| tensorflow | **2.17.1** | Reads the SavedModels AND keeps **protobuf 4.x**. TF ≥2.18 forces protobuf 5 → breaks mediapipe. |
| tf-keras | 2.17.0 | Installed for compatibility; live_demo loads SavedModels so Keras version is moot at runtime. |
| mediapipe | **0.10.14** | Has the legacy **Holistic** solution (75-point pose+hands). **0.10.35 REMOVED it.** |
| numpy | **1.26.4** | TF needs `<2.0`; scipy (pulled by mediapipe) needs `>=1.26.4`. Only 1.26.4 satisfies both. |
| ml-dtypes | 0.3.2 | TF 2.17 needs `<0.5`. |
| protobuf | 4.25.9 | mediapipe needs 4.x. |
| opencv-python | 4.11 | — |
| pandas | any | `train.py` imports it at module top. |
| pywin32 | (with pyttsx3) | provides `win32com` for SAPI TTS. |

> ⚠️ **After installing, you MUST `pip uninstall -y jax jaxlib`.** mediapipe pulls
> them in, but they require numpy ≥2 and break TF's tflite import path. They are
> not needed for Holistic.

Rebuild from scratch:
```
pip install -r requirements_live_demo.txt
pip uninstall -y jax jaxlib
```

---

## 5. Bugs found & fixed this session

1. **`.weights.h5` won't load on Windows** ("expected N variables, received 0") —
   tf-keras path-separator bug on the Linux-saved file → **load SavedModel instead.**
2. **Keras 3 can't build the model** (raw `tf.matmul` on symbolic KerasTensors) —
   moot once we load SavedModel directly (no `build_model`).
3. **mediapipe 0.10.35 has no `solutions.holistic`** → downgraded to 0.10.14.
4. **jax → numpy 2 → TF import crash** → uninstall jax/jaxlib.
5. **TTS spoke once then went silent** (pyttsx3 `runAndWait` in a thread) → switched
   to Windows SAPI via win32com.
6. **Window too small / bottom buttons cut off by taskbar / overlapping text** →
   full-screen canvas rendered at screen resolution, camera centered, bars sized.
7. **Recognition slow** → segment-then-classify + early-commit + resample-to-64.
8. **`hello` never detected** — hand-at-forehead defeats MediaPipe's hand detector;
   the sign got chopped → **pre-roll** (keep frames before hands appear) + longer
   `END_FRAMES` + back to pose complexity 1.

---

## 6. Key decisions taken this session

- **Model loading = SavedModel**, not weights (Windows + Keras reasons above).
- **Ensemble (5-fold) is the default** (~46 ms warm, best accuracy 0.9433);
  `--single`/`--fast` are the speed options.
- **DONE button stays** — it lets the *signer* decide when a sentence is finished,
  which is the clean solution to "when does a sentence end?". Not a throwaway.
- **`--ai` is AI-only** (no rules fallback) — Salim wants it to prove the AI itself
  works; the default (no flag) stays fully on the offline rules/script.
- **AI provider:** **Gemini 2.5-flash-lite** (free) for testing; **Claude Haiku
  4.5** (paid) is the production alternative. Same guardrailed prompt; switch via
  `SENTENCE_PROVIDER=anthropic`. Guardrails validated: 25-case suite, zero
  fabrications after prompt hardening.
- **Next ML milestone = expand to 250 words** (data already in S3, low risk, reuses
  everything) — NOT continuous-signing recognition (see §8, §9).
- **Continuous signing is a post-funding, LSL-focused bet**, unblocked now only by a
  licensing email — not a build.
- **Track B backend rescoped** to the full website backend (see §10).

---

## 7. The 30-word model — facts a new session needs

- **Architecture:** 1D CNN + Transformer on landmarks (own code, hoyso-style).
- **Input:** `[1,64,75,3]` raw x,y,z. Embedded `PreprocessLayer` (first layer):
  builds a NaN mask keyed off pose point 0 (nose), **drops z**, adds velocity
  (dx) + acceleration (dx2), masks padding. Output = **logits `[1,30]`** (consumer
  applies softmax).
- **Normalization is NOT baked into the model.** The training `.npz` were already
  **shoulder-midpoint centered + shoulder-width scaled** by the preprocessing
  teammate. So `live_demo.normalize()` must replicate that (and does, per
  `MODEL_CONTRACT.md §3`). Only x,y matter (z is dropped in-model). ⚠️ This is the
  #1 silent-failure risk (frontend #22/#26 too) — the exact preprocessing code is
  NOT in the repo; live_demo reproduces the documented spec. If live signs read as
  random across the board, suspect this first.
- **75-point layout:** pose 0–32, left hand 33–53, right hand 54–74.
- **Window:** 64 frames. **Confidence gate:** start 0.60 in the contract (live_demo
  uses 0.50 to surface more). Mirror = `x → -x` (shoulder-centered space); FLIP_MAP
  is in `train.py` and copied into `live_demo.py`.
- **Accuracy:** 5-fold CV **0.882** (honest headline), ensemble on 3 held-out test
  signers **0.9433**, best single fold-0 **0.9386**.
- **Per-word accuracy (test):** look **0.70**, go **0.74**, dog 0.84, book/hot 0.86,
  car/cat 0.89, the other 23 words 0.93–1.00. `look`/`go` are genuinely hard — no
  camera setting fixes a 70% sign. Lead demos with the strong 23.
- **Vocab order is load-bearing:** `words[i]` must equal class `i`. Frozen in
  `vocab_30.json`. (For 250, this ordering MUST be frozen on the training machine —
  see §8.)
- Full contract: **`MODEL_CONTRACT.md`**. Training code: **`training/train.py`**.

---

## 8. The 250-word expansion — the agreed plan

Goal: same deliverables as the 30-word model (trained model, per-word eval JSON,
exported SavedModels, wired into `live_demo.py`), target **>0.8** (accuracy will
drop from 0.94 — more classes, more confusable pairs; Kaggle top solutions ~0.87–
0.89 on 250, which is fine).

Data is already in S3 (`s3://asl-mvp-dataset/preprocessed/`, `split_manifest.parquet`,
`by_word/<word>/sequences.npz`), and a **250-class backbone already exists**
(`backbone_250.weights.h5`, from `train.py --all-words`).

**Where work runs:** training/eval/export on **Colab or EC2 GPU (Linux)** — required
for GPU and because `.weights.h5` export/load must happen on Linux. Salim's Windows
machine only *runs* the exported SavedModel.

- **Phase 1 — measure the existing backbone first (fast).** Eval `backbone_250` on
  the held-out test signers. If **>0.8 → skip to export.** (`ensemble_eval.py`
  hardcodes the 30-word vocab; needs an `--all-words` variant — small script to write
  on Colab.)
- **Phase 2 — only if <0.8:** proper 5-fold training
  (`train.py --all-words --fold all --init-from artifacts/backbone_250.weights.h5`).
- **Phase 3 — export + FREEZE THE VOCAB.** Export `savedmodel_fold*/` (250-class;
  `train.py` currently skips SavedModel export in `--all-words` mode — add it) AND
  **dump `vocab_250.json` on the training machine at the same time** — the model's
  output index → word map is `sorted(manifest words)`; regenerating it later from a
  different manifest would silently mislabel everything.
- **Phase 4 — wire into `live_demo.py`:** add a `--vocab250` flag pointing at the
  250 SavedModels + `vocab_250.json`. The recognition pipeline is class-count-
  agnostic (`words[idx]`), so no other changes. **Sentences:** rules only cover the
  30 words → for 250, `--ai` is the real path.
- **Phase 5 — verify:** `--selftest` (output shape `[250]`), then live.

> 📋 **Full step-by-step (commands, gotchas, deliverables) is in
> [`TRAIN_250_PLAN.md`](TRAIN_250_PLAN.md).** Read that for the overall plan.
>
> ⚡ **STATUS (2026-07-22): this plan is mid-execution — see §0.1.** Phase 1 done
> (backbone = 0.726), Phase 2 in progress (fold-0 = **0.7576** test, folds 1–4
> pending), blocked on free Colab GPU quota. **The live execution doc is
> [`RESUME_250.md`](RESUME_250.md)** (exact resume commands, the subprocess gotcha,
> the ensemble-eval script). Follow RESUME_250.md, not the abstract plan, to
> continue.

---

## 9. Dataset research — continuous / sentence-level signing

Full detail in **`DATASET_RESEARCH.md`**. Headline: **commercially-licensed
continuous-signing data barely exists** — which is why the "isolated words → AI
sentence" approach is a reasonable workaround, not a hack.

- **How2Sign** (80h ASL, sentence-aligned) — **CC BY-NC, non-commercial, unusable.**
- **YouTube-ASL** (984h) — per-video licensing murky for commercial.
- **ArabSign / Isharah** (continuous Arabic) — relevant to the LSL/Arabic wedge;
  **license needs confirming** (email `hluqman@kfupm.edu.sa`).
- **Recommendation:** don't chase commercial continuous ASL (lose to big tech). The
  moat is **Arabic → LSL**; collect your own LSL data (with consent). Continuous
  recognition is a different, harder ML paradigm (seq2seq/CTC) — a post-funding bet.

---

## 10. Website backend (Track B) — rescope

`BACKEND_TASKS.md` Track B was scoped to just the camera-permission API. Rescoped
this session to the full website backend. **Architecture guardrail:** recognition
is client-side → **no inference endpoint on the server.** The backend does: (1) AI
sentence service, (2) identity + persistence, (3) deployment/security/privacy.

New tasks **BE-10…BE-30**, priority-tagged. MVP-critical path:
- **BE-10…BE-13** — `POST /api/sentence` (the AI sentence endpoint — the core
  feature, currently has NO server; port `grammar_eval.py` into Express, keys
  server-side, never-silent rules fallback, return glosses).
- **BE-14…BE-16** — identity (recommend anonymous device IDs for MVP; resolves BE-7).
- **BE-20** — serve + version the TF.js model (frontend #25 is blocked on this).
- **BE-21…BE-25** — deployment/infra (the API only runs on `localhost:4000` today).
- **BE-6** — wire the frontend camera-permission flow.

Done + verified earlier: BE-1…BE-5 (Prisma↔Supabase, server boots on :4000,
`/health` ok). Fresh-clone gotcha: run `prisma generate` (generated client not
committed).

---

## 11. Speech → Sign (the reverse pipeline — the next big feature)

The product's other half: a hearing person speaks, a Deaf person sees signing.
This closes the loop to **two-way communication.** A backend teammate is building it
**now** — specifically the **avatar and its animation** — while Salim finishes 250,
after which Salim builds the steps *before* the animation.

**Pipeline (mirror of the recognition side):**
```
speech → [ASR: audio→text] → [text→gloss sequence, LLM] → [gloss→motion data]  (Salim)
       → ─── SIGN_ANIMATION_CONTRACT.md (the hand-off) ───
       → [render motion onto an avatar]  (teammate)
```

**Division of labor:**
- **Salim (pre-animation):** ASR (off-the-shelf — Web Speech API / Whisper),
  text→gloss (reuse the LLM, reversed prompt), curate one clean canonical landmark
  clip per word, resolve glosses→clips + stitch transitions → emit the keyframe
  stream.
- **Teammate (animation):** the avatar model + rig (fingers, shoulders, hands, and
  a facial-expression rig) + the retarget/render.

**The hand-off is specified in [`SIGN_ANIMATION_CONTRACT.md`](SIGN_ANIMATION_CONTRACT.md)** —
what the animation consumes: a time-ordered sequence of **75-point landmark frames**
(same layout as recognition), shoulder-centered coords, fps, NaN convention, plus an
optional **468-point face block**. Key points captured there:
- The animation **replays landmark motion — it does NOT use the recognition model.**
- Data is **point POSITIONS, not bone rotations** → the rig is position-driven (place
  joints / IK targets), y is **down** (flip for the avatar).
- To **build the avatar/rig now**, the teammate needs only: the contract + **one
  neutral reference pose** (a static frame) + that "positions-not-rotations" fact.
  He does NOT need the motion pipeline or dataset to build the avatar.

**Facial expression — the key clarification:**
- The 75 points have **no usable facial expression** (only ~11 coarse face
  *positions*). The **30/250 recognition models are trained face-free on purpose** —
  words are identified by the hands; the Kaggle winner dropped face too. Do **not**
  retrain the 250 with face.
- Real expression needs MediaPipe's **468-point FaceMesh**, which preprocessing
  dropped — **but it still exists in the raw Kaggle source + S3 `cleaned/`.** So the
  teammate's face rig is fed by **extracting the 468 face points from the source
  (a data task) — NOT by retraining.** Caveat: the dataset's isolated-word clips have
  **neutral/non-grammatical** faces, so the face moves but won't sign grammar until
  fed intentionally-expressive clips.

**Full-MVP reality:** fluent conversation = continuous signing = the hard,
data-blocked, post-funding/LSL bet. The legitimate **near-term MVP** is isolated
words + AI sentences, **both directions** — genuinely useful for real exchanges.

**Next artifact to unblock the teammate:** `export_reference_pose.py` (+ a few motion
samples) — pulls a neutral pose (75, optionally +468 face) from the data in the
contract format. Not written yet; write it when starting this.

---

## 12. Security notes (important)

- **Secrets live only in the local, gitignored `.env`** — never in code, never in
  `.env.example`, never committed. Verified `.env` is gitignored.
- `.env` contains: the shared **Supabase `DATABASE_URL`** (password percent-encoded:
  `&`→`%26`, `!`→`%21`), and **`GEMINI_API_KEYS`** (comma-separated, rotated on 429).
- `live_demo.py` reads `.env` via a tiny built-in loader (`_load_dotenv`) so `--ai`
  picks up the keys.
- ⚠️ **The Gemini keys (and the DB password) were pasted in chat this session →
  treat them as burned. Rotate before any production use** (new Gemini keys:
  https://aistudio.google.com/apikey). This is noted inline in `.env`.
- ⚠️ **AWS S3 access key exposed in chat (2026-07-20)** while setting up Colab for
  the 250 training → **rotate it** (IAM → delete the old key, create a new one) and
  set a billing alarm on the AWS account.

---

## 13. Open items / suggested next steps

- [ ] **Rehearse the live demo** with the strong 23 words; treat `look`/`go` as
      known-hard. Read `[seg]` terminal lines if a word fails.
- [ ] **Rotate the exposed secrets: Gemini keys, DB password, AND the AWS S3 access
      key** (all pasted in chat) + set an AWS billing alarm.
- [ ] **250-word model — IN PROGRESS (see §0.1 + [`RESUME_250.md`](RESUME_250.md)).**
      Backbone measured (0.726), fold-0 done (**0.7576** test). Next: finish folds
      1–4 + ensemble → >0.80. Blocked on free GPU (Colab quota / consider Kaggle).
      Remember: **run train/eval/export as a `!python` subprocess** (notebook-kernel
      build → chance accuracy). `train.py` already patched (BackupAndRestore +
      SavedModel export) — re-upload it.
- [ ] **(optional) write `RESUME_250_KAGGLE.md`** if Salim moves to Kaggle for free
      GPU (30h/week; `--out-dir=/kaggle/working`, push to S3, no Drive).
- [ ] **Email ArabSign/Isharah** (`hluqman@kfupm.edu.sa`) re: commercial licensing.
- [ ] **BE-10** — build `/api/sentence` (highest-value backend item; mostly porting
      `grammar_eval.py` into the running Express server).
- [ ] Get `grammar_rules.json` + `GRAMMAR_CONTRACT.md` and the `web_model/` TF.js
      files onto `main` for the frontend (currently on a branch / in Drive).
- [ ] Demo-signer review of the grammar rules (A9.5b).
- [ ] **Speech→sign:** write `export_reference_pose.py` to unblock the teammate's
      avatar/rig build (needs: body-only 75, or 75+468 face?).

---

## 14. File map

| File | What |
|---|---|
| `live_demo.py` | **The live camera demo** (this session's main work). |
| `RUN_LIVE_DEMO.md` | End-user run guide for the demo. |
| `requirements_live_demo.txt` | Pinned, verified dependency stack (+ the jax uninstall note). |
| `DATASET_RESEARCH.md` | Continuous-signing dataset options + licensing. |
| `SIGN_ANIMATION_CONTRACT.md` | Speech→sign hand-off spec (what the avatar/animation consumes). |
| `TRAIN_250_PLAN.md` | Overall plan to train + ship the 250-word model. |
| `RESUME_250.md` | **Live execution doc for the 250 training** — exact resume commands, the subprocess-build gotcha, ensemble-eval script. Follow this to continue (see §0.1). |
| `SESSION_HANDOFF.md` | **This file.** |
| `vocab_30.json` | The 30-word list; index = class id (load-bearing order). |
| `artifacts/savedmodel_fold{0..4}/` | The 5-fold SavedModels the demo loads. |
| `artifacts/weights_mvp30_fold*_seed42.weights.h5` | The weights (⚠️ don't load on Windows — use the SavedModels). |
| `grammar_rules.json` | A9 grammar data (templates/rules/fallback). |
| `GRAMMAR_CONTRACT.md` | `render()` spec + 15 test vectors + demo script. |
| `grammar_eval.py` | Standalone rules+AI eval; `--ai` in live_demo imports its `ai_generate`. |
| `MODEL_CONTRACT.md` | Frontend handoff contract (input/normalization/output/gate). |
| `training/train.py` | Model + training script (30-word and `--all-words`/250). |
| `training/ensemble_eval.py` | Ensemble eval (30-word; needs `--all-words` variant for 250). |
| `BACKEND_TASKS.md` | Backend plan (Track A pipeline done; Track B rescoped). |
| `FRONTEND_TASKS.md` | Frontend plan (live-demo critical path). |
| `.env` | **Local secrets (gitignored):** Supabase URL, Gemini keys. |

**Added since 2026-07-22 (see §0.2):**

| Path | Purpose |
| --- | --- |
| `docs/explanation.md` | Meeting doc: both phases explained technically, with real numbers. |
| `docs/MEDICAL_MVP_PLAN.md` | **The active project.** Medical MVP plan, dataset comparison, risks. |
| `vocab_medical.json` | The 130 trainable clinical words. |
| `vocab_medical_analysis.json` | Per-word video/signer counts, tiers A/B/C. |
| `training/medical/extract_landmarks.py` | video → `(64,75,3)` tensors, live_demo-parity. |
| `training/medical/test_parity.py` | **Run after touching the extractor or live_demo.** |
| `training/medical/build_vocab.py` | Rebuilds the vocabulary from Sem-Lex metadata. |
| `training/medical/semlex_med.py` | Trainability scan of the clinical word list. |
| `demo_voice_gui.py` | Clickable Record/Stop speech→sign window (the meeting build). |
| `demo_voice_to_sign.py` | Terminal press-to-talk speech→sign. |
| `demo_speech_to_sign.py` | Typed sentence → 2D avatar. |
| `_asr_worker.py` | 3.14 ASR worker: `--push` / `--wav` / `--serve` / `--selftest`. |
| `preview_signs.py` | 2D skeleton player + Deaf-review harness. |
| `sign_clips_250.npz` · `animation_handoff/` | Phase-2 motion dictionary + the 250-word handoff sent to Ghozlan. |
| `demo/*.mp4` | Pre-rendered fallback demo videos. |

---

*Written 2026-07-20; updated 2026-07-22 (250 training — §0.1); updated **2026-08-04**
(both phases demo-ready, demo apps built, and the **medical-domain MVP** started — §0.2).*

*If anything here conflicts with the current code, **the code wins** — verify against the
file before asserting. Salim would rather hear "I checked and it's X" than a confident
guess.*

**Quick starts:**
- General demos — `python live_demo.py --vocab250 --debug` (sign→speech) ·
  `python demo_voice_gui.py` (speech→sign, clickable)
- Sanity checks with no camera/mic — `python live_demo.py --selftest` ·
  `python demo_voice_to_sign.py --selftest`
- **Medical MVP (active)** — read [`MEDICAL_MVP_PLAN.md`](MEDICAL_MVP_PLAN.md), then
  `python training/medical/test_parity.py` to confirm the extractor is still in sync.
  The next real move is **licensing (Salim's call)**, then the `train.py` adapter.
- 250-word retrain (deferred) — [`RESUME_250.md`](RESUME_250.md)
