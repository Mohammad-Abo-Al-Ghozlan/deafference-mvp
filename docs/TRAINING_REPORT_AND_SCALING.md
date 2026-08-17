# 250-Word Training — Full Report, the Live Gap, and the Path to Scale

_2026-07-28. Grounded in the actual artifacts and eval files on disk._

---

## PART 1 — What the training actually produced

### The run
- **Model:** 1D conv + Transformer, 250 classes, input = 64 frames × 75 landmarks × 3 (MediaPipe pose + both hands). Small variant (DIM 192).
- **Data:** the S3 ASL isolated-sign set — participant-grouped 5-fold CV + 3 held-out **test signers** the model never saw.
- **Recipe:** warm-started from a 250-class backbone, label smoothing + augmentation (incl. horizontal flip), 80 epochs/fold.

### The real numbers (measured on held-out signers — the honest metric)
| Metric | Value |
|---|---|
| **Fold-0 TEST accuracy** | **0.7576 (75.8%)** |
| Fold-0 validation | 0.5723 (fold-0 is the *hardest* fold) |
| Backbone (pretraining) | 0.7260 |
| 30-word model (for comparison) | ~0.94 |

**Per-word (fold-0 on test, all 250):** median **0.786** · 65 words ≥0.90 · **121 words ≥0.80** · 206 ≥0.60 · only **14 words <0.40**.
- Near-perfect: brown, cow, drink, food, have, horse, nose, shirt, water (~1.0).
- Weak: nap 0.11, give 0.15, go 0.22, look 0.35, ride 0.36, there 0.37.

### ⚠️ The critical finding
The SavedModels the live demo actually runs (`artifacts_250/`) are a **different, larger (768-dim), UNVERIFIED training run — NOT the 0.7576 model.** The 0.7576 belongs to a smaller (384-dim) run whose weights we have but can't cleanly load into the current code. **So the model in your demo has never had its accuracy measured.** You've been testing an unknown-quality model.

---

## PART 2 — Why 30 words is easy live but 250 is hard

Four compounding causes:

**1. Confidence spread (pure math of 250 classes).**
The model outputs a probability split across all classes. At 30 words a correct sign scores ~0.90; at 250 the *same* correct sign scores ~0.45 because 249 other options (and several look-alikes) each take a slice. A fixed confidence gate then rejects correct-but-low-confidence signs → "sign it again."

**2. Look-alike confusion (genuinely harder classification).**
250 signs contain many visually near-identical pairs (nap/sleep, go/there, look/see-family). More classes = exponentially more confusable pairs = the model is genuinely wrong more often. 30 distinct signs simply don't collide.

**3. Sim-to-real gap (your signing vs the dataset's).**
The model learned *one specific way* each sign was performed by the dataset signers. Your speed / handshape / angle differ, so live accuracy is always **below** the clean-data test score. At 30 words the signs are distinct enough to survive this; at 250 the gap tips many words into the wrong bucket. This is why even a "1.0" word like brown can miss live.

**4. The deployed model was never verified** (Part 1) — some of the "it just doesn't work" may be a weak/mystery export, not the model's true capability.

**Net:** 30 words survives all four because the signs are few and distinct and confidence stays high. 250 gets hit by all four at once.

---

## PART 3 — What we've already done about it (levers applied)

| Lever | What it fixes |
|---|---|
| **Margin-based gating** | Commits a sign when it's *decisively* ahead of the runner-up, not just above an absolute score → rescues correct low-confidence signs (cause #1). Helps all 250. |
| **Robust multi-view commit** | Averages several views + mirror of each sign → steadier, higher confidence. |
| **Subset masking (`--words`)** | Restricts recognition to a curated word list → confidence concentrates → those words commit first-try. The MVP-demo fix. |
| **Data-driven demo vocab + `word_acc` panel** | 42 intuitive words that also score ≥0.80; UI shows each word's reliability green→red. |

These make the *demo* good on strong words. They cannot invent accuracy the model doesn't have.

---

## PART 4 — Solutions to make 250 (and more) work well

### Short-term — make the current 250 genuinely good
1. **Finish + VERIFY the ensemble.** Train the missing folds, **measure the ensemble on the test signers**, and export SavedModels *correctly* (the current deployed one is unverified). Expected ~0.80–0.83. This is the single most important fix — right now you're flying blind.
2. **Personalization / calibration (biggest LIVE gain).** Record yourself signing each word a few times and fine-tune on *your* examples. This directly closes the sim-to-real gap — the thing most likely to make "when I sign it, it detects it" true for you.
3. **Better live segmentation.** Cleaner start/end detection of each sign → the model sees well-formed clips → live accuracy rises toward the test score for every word.

### Medium-term — scale to many more words
4. **More data per sign + a bigger model + multi-seed ensembles.** Isolated-sign accuracy scales with data and model size. Realistic ceiling stays ~0.85–0.88 even for well-resourced systems.
5. **Top-k / candidate UX for large vocab.** Above a few hundred signs, "one instant answer" stops being realistic — show the top 2–3 candidates and let context/AI pick. This is how large-vocab systems stay usable.

---

## PART 5 — The honest truth about "words → sentences"

This is the most important strategic point, so I'm being blunt:

**Recognizing sentences is NOT "more words." It's a different, much harder system.**

- What we have = **isolated-sign recognition**: one clear sign at a time, with pauses. This is the easy end.
- Sentences = **continuous signing**, which needs one of:
  - **CSLR** (Continuous Sign Language Recognition) — read an unbroken stream of signs with no pauses/boundaries → sequence models (CTC / transformers), not our one-sign classifier.
  - **SLT** (Sign Language Translation) — sign video → a natural spoken-language sentence (with grammar, not just glued glosses). This is an active research frontier; nobody has "solved" it.
- **These need continuous datasets** (signed sentences with transcripts) — which barely exist even for ASL, and are **entangled in licensing** (How2Sign is non-commercial, YouTube-ASL is murky).

**For LSL specifically, this is your moat AND your bottleneck:** there is essentially **no public LSL dataset** — not for isolated words, and definitely not for sentences. To do LSL words *and* sentences you will have to **collect and label the data yourselves.** That data is the actual asset; the model is comparatively commoditized.

### Realistic staged roadmap
1. **Now:** isolated words (ASL 250) → prove the pipeline + UX.
2. **Next:** a curated set of high-value **whole phrases** treated as single units (like the previous MVP's quick-phrases) — this fakes "sentences" cheaply and is genuinely useful for restaurant/clinic/reception contexts.
3. **LSL isolated words:** collect + label an LSL isolated-sign dataset (the moat), train the same pipeline on it.
4. **Later / R&D:** continuous LSL (CSLR/SLT) — only once you have continuous LSL recordings with transcripts. This is a multi-year, data-gated research effort, not a next-sprint feature.

---

## PART 6 — Recommended next steps (in order)

1. **Verify the deployed model** — measure the `artifacts_250` ensemble on the test signers. We may be shipping a weak export; we must know. *(Needs the S3 data + a short eval run.)*
2. **If it's weak → retrain + export properly** (folds + ensemble + SavedModel), with Drive-checkpointing so Colab disconnects don't cost you.
3. **Ship the demo on the verified strong words** (subset + margin gating) — an honest, reliable MVP.
4. **Prototype personalization** — even 3–5 recordings of you per word, fine-tuned, would tell us how much the sim-to-real gap is costing.
5. **Treat data collection (ASL edge cases + all of LSL) as the real product investment** — it's the moat and the gate on everything above, especially sentences.

### One-line summary
> The 250 model is a legitimate ~0.76 (fold-0) isolated-word recognizer, but the demo runs an unverified export, and 250-class live recognition is inherently harder than 30 (confidence spread + look-alikes + sim-to-real). Fix it by verifying/retraining the ensemble and personalizing to the signer. **Sentences are a different, data-gated problem — and for LSL, collecting the data is the whole game.**
