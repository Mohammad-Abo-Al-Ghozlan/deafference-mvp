# Medical-Domain MVP — Plan (2026-08-01)

**Goal:** a two-way ASL translator for a **clinical** setting — a Deaf patient signs
symptoms → spoken English for the clinician (Phase 1); the clinician's speech → sign
animation for the patient (Phase 2). Same two-phase architecture as the general MVP, new
domain, **new dataset and new vocabulary** (not a subset of the 250 children's words).

---

## 1. Dataset research — what actually exists

### There is no medical **ASL** dataset

I searched specifically for one. Medical sign-language datasets **do** exist — but for other
sign languages:

| Dataset | Language | Content | Verdict |
|---|---|---|---|
| **SignTalk-Gh** ([Kaggle](https://www.kaggle.com/datasets/responsibleailab/signtalk-ghana)) | Ghanaian | 9,879 videos, 4,031 doctor–patient **sentences**, 2,877 medical terms, 23.15 GB | Closest to "a medical SL dataset." **But:** non-commercial academic license, **continuous** (our pipeline is isolated), and only **5 signers** — the paper itself reports weak generalization |
| **MSL healthcare** | Mexican | 150 health signs, 800 *synthetic* sequences/word, 35 GB | Synthetic augmentation; wrong language |
| **LSM medical corpus** | Mexican | 121 signs, emergency/accident lexicon, validated with a Deaf association | Wrong language; small |
| **SignIT / LIS** | Italian | 126 signs (100 medical + 26 letters) | Wrong language; small |
| **Captar-Libras** | Brazilian | Medical-term corpus, bidirectional, collected 2024–2025 | Wrong language |
| **ArSL healthcare** | Arabic | 36 static + 92 dynamic medical signs | Wrong language for this MVP — **but see the Arabic/LSL moat in `DATASET_RESEARCH.md`** |

**Conclusion: for ASL, the medical vocabulary has to be assembled from a general
large-vocabulary isolated-sign dataset.** That is the whole strategy.

### The general ASL isolated-sign candidates

| Dataset | Size | Vocab | Signers | Data | Licence |
|---|---|---|---|---|---|
| **Sem-Lex** | 91,148 videos | **9,953 labels** | **44** | RGB video (pose "coming soon") | Terms-of-use gate — **must be verified** |
| **ASL Citizen** (Microsoft) | 83,399 videos | 2,731 signs | 52 | RGB video, 42.8 GB | Consented; **commercial use requires contacting `ASL_Citizen@microsoft.com`** |
| **ASL-LEX 2.0** | lexicon only (no video) | 2,723 signs | — | phonological metadata CSV | Open — useful as a vocabulary/phonology reference, not training data |
| WLASL / MS-ASL | ~2,000 / 1,000 | — | — | YouTube-sourced | Murky licensing, link rot — **avoid** |

---

## 2. The measured result — 90% of a clinical vocabulary is trainable today

I defined a **145-concept clinical vocabulary** for a patient↔clinician encounter (body
parts, symptoms, severity, time/duration, people/places, actions, objects, core function
words) and measured it against the real Sem-Lex metadata. Gate for "trainable" =
**≥8 videos AND ≥3 signers**.

| Tier | Count | Meaning |
|---|---|---|
| **A — trainable now** | **130 (90%)** | 8,324 videos available |
| **B — thin** | 15 (10%) | present but too few examples |
| **C — absent** | **0** | — |

Reproduce: `training/medical/build_vocab.py` → `vocab_medical.json`, `vocab_medical_analysis.json`.

**Strong clinical coverage** (videos/signers): `hurt` 248/36 · `sick` 207/37 · `help` 136/28 ·
`doctor` 115/31 · `medicine` 95/29 · `breathe` 75/30 · `hospital` 60/22 · `blood` 53/26 ·
`pain` 52/22 · `nurse` 33/21 · `cough` 31/19 · `bleed` 29/17 · `water` 408/38.

**Tier B — thin, and unfortunately clinically important:**
```
fever(6v/5s)  chest(4v/3s)  stomach(5v/4s)  nausea(2v/2s)  rash(2v/2s)  cramp(2v/2s)
infection(5v/4s)  sneeze(4v/3s)  neck(7v/7s)  shot(6v/5s)  wheelchair(7v/7s)
patient(2v/2s)  stand(5v/3s)  very(3v/3s)  never(7v/7s)
```
These must be supplemented from **ASL Citizen** (a different 2,731-sign selection) or recorded
with a Deaf signer. **`fever`, `chest`, `stomach`, and `nausea` are not optional in a triage
vocabulary** — treat closing this gap as required, not nice-to-have.

### Two numbers that will shape training

- **Class imbalance is 51×** (min 8 videos, median 39, max 408). Needs class weighting,
  capping, or balanced sampling — otherwise `water` and `hurt` dominate and `leg` never learns.
- **~64 videos/class mean, vs ~376/class in GISLR.** Expect **lower** accuracy than the
  general model's 0.7576 at first. Offsetting this: **44 signers vs GISLR's 21**, which is
  *better* for generalizing to unseen signers — the number that actually matters clinically.

---

## 3. Scope — one clinical scenario

> **Adult intake / triage:** where does it hurt, how bad, how long, what do you need,
> plus the clinician's basic instructions back.

### Hard limits (say these out loud)
- **No fingerspelling.** Drug names, conditions, and proper nouns are fingerspelled in real
  ASL; an isolated-sign classifier cannot read them. Out of scope — flag it, don't fake it.
- **No diagnosis, no consent, no dosage instructions.**
- **Not a replacement for a qualified medical interpreter** — a bridge for the minutes before
  one arrives, and a fallback when none is available.

---

## 4. Stages

| # | Stage | Output | Status |
|---|---|---|---|
| 0 | Dataset research + vocabulary validation | `vocab_medical.json` (130 words, measured) | **done** |
| 1 | **Resolve licensing** — Sem-Lex terms of use; email Microsoft re ASL Citizen commercial | written confirmation | **BLOCKED — needs you** |
| 2 | Download Sem-Lex; pull only the 130 Tier-A classes (~8,324 clips, not all 91k) | raw clips | after 1 |
| 3 | **Preprocess:** video → MediaPipe Holistic → `(T,75,3)` in the *exact* GISLR convention | `medical_landmarks.npz` | can build now |
| 4 | Train — reuse `training/train.py` (vocab-size agnostic), **signer-disjoint** folds, class weighting | `artifacts_medical/savedmodel_fold0..3` | after 3 |
| 5 | Phase 1 wiring: `live_demo.py` on the medical model + clinical grammar | sign→speech medical demo | after 4 |
| 6 | Phase 2 wiring: `build_sign_clips` → `sign_clips_medical.npz` → `gloss_to_motion --per-word` | speech→sign medical demo | after 4 |
| 7 | Safety gates + Deaf/interpreter review | reviewed demo | last |

---

## 5. Risks, honestly

1. **Licensing is the gating item, not the ML.** The HF mirror of Sem-Lex is tagged
   `apache-2.0`, but **a mirror's tag is not the original licence** — the official Sem-Lex
   distribution has a terms-of-use gate, and I cannot accept terms on your behalf. Resolve
   this *before* the data shapes the product. (You rejected How2Sign over exactly this.)

2. **Preprocessing parity — the #1 technical risk.** Sem-Lex ships **raw video**; our model
   was trained on GISLR's **pre-extracted** landmarks. If our extraction differs in landmark
   subset, ordering, handedness, normalization, or resampling, accuracy degrades *silently*.
   **Mitigation:** extract signs that exist in *both* GISLR and Sem-Lex and numerically diff
   the tensors before training anything.

3. **Medical stakes change the design, not just the disclaimer.**
   - Critical terms (pain, severity, negation, body part) **never auto-commit** — force the
     L2 confirm path or an explicit tap, even at high confidence.
   - **Always show the recognized gloss for correction before speaking it.**
   - The grammar layer must be **constrained to recognized glosses** — an LLM must never be
     able to invent clinical content that wasn't signed.

4. **Compute:** MediaPipe over ~8,300 videos is hours, not minutes. Extract only Tier A.

5. **Accuracy expectation:** with ~64 videos/class, do not promise 0.78. Measure first, then
   quote. The honest framing is "44 signers, unseen-signer evaluation."

---

## 6. Sources

- Sem-Lex — https://github.com/leekezar/SemLex · paper https://arxiv.org/abs/2310.00196
- ASL Citizen — https://www.microsoft.com/en-us/research/project/asl-citizen/ · paper https://arxiv.org/pdf/2304.05934
- ASL-LEX 2.0 — https://osf.io/zpha4/ · https://asl-lex.org/
- SignTalk-Gh (Ghanaian, medical) — https://www.nature.com/articles/s41598-026-43478-9
- Medical-term SL corpus design (Captar-Libras) — https://humanfactors.jmir.org/2026/1/e72789
- ArSL healthcare recognition — https://www.mdpi.com/2504-2289/9/11/281
- Deaf healthcare SLR systematic review — https://www.jmir.org/2026/1/e70417
- Prior licensing work — [DATASET_RESEARCH.md](DATASET_RESEARCH.md)
