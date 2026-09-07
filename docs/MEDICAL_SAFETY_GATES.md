# Clinical safety gates — what this model may and may not be trusted to say

**For review by a fluent Deaf signer and/or a certified medical interpreter.**
Everything here is measured on the 123-class Sem-Lex medical ensemble
(`artifacts_medical/savedmodel_fold{0..3}`), scored on **1,373 held-out clips from 9 signers
the model never saw**. Generated 2026-09-03 into `safety_gates_medical.json`; enforced by
`python live_demo.py --medical`.

```
ensemble test accuracy   0.8383      top-5  0.9512
per-word median          0.8421      per-word macro mean  0.7344
shippable vocabulary     55 of 123 concepts, mean 0.9331
```

> **The gates are an engineer's reading of clinical risk. They have had no Deaf or
> interpreter review.** That review is the point of this document. Argue with the
> categories in §5 — they are the one part that is judgement rather than measurement.

> ✅ **Updated 2026-09-04: the confidence gate is now MEASURED, not inherited — see §4b.**
> Two results there change what this document claims. **(1)** All 53 dangerous-confusion
> clips fired *below* confidence 0.80 — the highest reached 0.746 — so the gate suppressed
> every one of them, and `--medical` now runs the measured `L1_CONF 0.80 / L2_CONF 0.70`.
> **(2)** §1's and §2's 0.80 bar is on **recall**, and recall overstates **precision** for 20
> of the 55 shipped words. `no` is 0.909 recall but **0.714 precision** ungated: more than one
> spoken refusal in four is not a refusal.
>
> ✅ **Updated 2026-09-07: §1, §2 and §3 now carry precision INLINE.** The 2026-09-04 pass
> appended §4b without touching them, so every table a reviewer reads first still showed
> recall unlabelled with the correction 170 lines below. Fixed — the columns now say which
> statistic they are, and the four words that move materially (`no`, `more`, `blood`,
> `always`) say so where they are listed. §4b remains the full derivation.
>
> ⚠️ **Two words are not what §2's list implies.** `blood` has precision **0.667 that the
> gate does not improve**, and `always` is **muted entirely** at τ=0.80. Both are flagged in
> §2 and both are open questions for this review.

---

## 1. The finding that matters most: negation is asymmetric

**The model ships `no` — but only behind the confidence gate — and cannot ship `yes`.**

⚠️ **The first column is RECALL**, P(model says X | truth is X). It is the quantity the ship
gate uses and it is **not** the quantity a speaking device needs. See §4b.

| | recall (what the gate uses) | precision, ungated | precision @ τ=0.80 | ships? |
|---|---|---|---|---|
| `no` | **0.909** | **0.714** | **1.000** | ✅ **only gated** — see below |
| `yes` | **0.714** | — | — | ❌ below the 0.80 gate |
| `not` | 0.647 | — | — | ❌ |
| `worse` | 1.000 on **1** test clip | — | — | ❌ unmeasured |
| `better` | 1.000 on **3** test clips | — | — | ❌ unmeasured |

*(`—` means no published precision figure: §4b measures precision only for words that are
actually announced, and these three never clear the ship gate. Absence is not a good number.)*

🔴 **`no` at 0.909 is a recall number, and its ungated precision is 0.714** — **more than one
spoken refusal in four is not a refusal.** At τ=0.80 it reaches 1.000, so the measured gate
does fix it, but the headline does not hold without the gate. Any build that lowers `--conf`
below 0.80 reopens this.

So a patient answering a yes/no question can be rendered as a **refusal** and cannot be
rendered as **consent**. In a clinical setting consent is the direction that carries legal
and ethical weight.

**Required mitigation, already enforced:** `--medical` prints this at startup, and `no` is
on the never-auto-commit list so it cannot reach the speaker without a human tap.
**This build must not be used to obtain or record consent.**

---

## 2. Ten words never auto-commit

These are recognised normally but are **held** before they reach the sentence or the
speaker, whatever the confidence — even at 1.00. A held word falls through to the top-K
chips, so committing it takes one deliberate tap. Enforced in `live_demo.py` immediately
after `decide_commit()` and before `gloss_buf` / `speaker.say`.

⚠️ **Again, `recall` is the column the ship gate used.** The `precision` columns are the ones
that describe what happens when the device *speaks* the word. Four of these ten move
materially; the other six have no published precision figure because they are not in §4b's
>0.10 gap set.

| word | recall | precision, ungated | precision @ τ=0.80 | why it is gated |
|---|---|---|---|---|
| `no` | 0.909 | **0.714** | 1.000 | negation — inverts meaning |
| `bad` | 0.952 | — | — | severity |
| `big` | 0.967 | — | — | severity |
| `more` | 0.857 | **0.750** | 1.000 | severity |
| `always` | 0.800 | — | 🔴 **muted** | certainty |
| `pain` | 0.971 | — | — | red-flag symptom |
| `blood` | 0.889 | **0.667** | 🔴 **0.667** | red-flag symptom |
| `breathe` | 1.000 | — | — | red-flag symptom |
| `sick` | 1.000 | — | — | red-flag symptom |
| `help` | 0.966 | — | — | red-flag symptom |

**Note the recall figures are high.** The gate is not there because these words are weak — most
are among the best in the vocabulary. It is there because they are the words where being
wrong changes clinical meaning rather than just sounding odd. Confidence is not authority.

🔴 **But two rows above are not reassuring, and both are on this list for a reason:**

- **`blood` — precision 0.667, and the confidence gate does not improve it.** A red-flag word
  that is wrong one time in three when spoken. The never-auto-commit hold *is* the live
  defence here; nothing else is. **§4b asks whether to ship it at all.**
- **`always` — muted entirely at τ=0.80.** It is never announced, so its precision is
  undefined. A word that cannot be spoken in the recommended configuration is not a shipped
  word, and listing it as gated overstates what the build does.

**UX consequence, stated plainly:** in `topic_medical_symptom` (18 words) **9 are held**, so
half of that topic needs a tap. That is the intended trade and a reviewer may disagree with
it.

---

## 3. Sixteen clinically critical concepts this model CANNOT express

A system that silently lacks a concept is worse than one that says so. This list is printed
at startup and must be surfaced in any UI built on top.

| | words | why |
|---|---|---|
| **too inaccurate to ship** | `yes` 0.714 · `not` 0.647 · `much` 0.600 · `maybe` 0.533 · `all` 0.444 · `weak` 0.429 · `some` 0.429 · `strong` 0.400 · `faint` 0.400 · `heart` 0.333 · `sometimes` 0.200 · `hot` 0.781 | trained, measured, below the 0.80 gate |
| **unmeasured (<5 test clips)** | `choke` · `worse` · `better` · `bleed` | scored 1.00 / 1.00 / 1.00 / 0.75 on 1–4 clips — that measures nothing |

✅ **These are recall figures too — but here that error runs in the SAFE direction.** Recall
*overstates* precision (§4b), so a word already failing on recall would fail at least as badly
on precision. **Excluding a word for low recall is conservative.** It was *including* one for
high recall that was the mistake, which is why §1 and §2 needed re-cutting and this list did
not. No word leaves the cannot-express list because of §4b.

Three of these deserve naming individually:

- **`choke`** — 1.000, on a single test clip. A choking emergency is exactly the case where
  a demo must not imply capability it cannot evidence.
- **`hot`** — 0.781, just under the gate. In a clinical register this is *fever*. It is also
  the single worst confusion in the whole matrix (§4).
- **`heart`** — 0.333, and it scatters into four different wrong words, every one a missed
  red flag.

---

## 4. The measured safety-crossing confusions

45 confusions on the test split cross a safety line; **15 are reachable with the 55-word
ship vocabulary**. These are observed errors on unseen signers, not predictions.

| true → predicted | clips | share of class | kind |
|---|---|---|---|
| `hot` → `bad` | **5** | **16%** | red flag MISSED — a fever reported as "bad" |
| `ear` → `skin` | 3 | **60%** | wrong body site, most of the time |
| `faint` → `close` | 2 | 40% | red flag MISSED |
| `why` → `sick` | 2 | 40% | false alarm |
| `heart` → `big` / `feel` / `tired` / `water` | 1 each | 17% each | red flag MISSED, four ways |
| `blood` → `hospital` | 1 | 11% | red flag MISSED — **ship word** |
| `baby` → `blood` | 1 | 3% | false alarm — **ship word** |
| `cold` → `pain` | 1 | 3% | false alarm — **ship word** |
| `hand` → `bleed` | 1 | 14% | false alarm — **ship word** |
| `headache` → `pain` | 1 | 50% | false alarm (arguably benign) |

**Read the single-clip rows as existence proofs, not rates.** With 1,373 clips over 9
signers, a pair seen once tells you it can happen and nothing about how often.

The two rows that are *not* single-clip artefacts are `hot → bad` (5 clips, 16% of the
class) and `ear → skin` (3 clips, 60%). Both are in the cannot-express set, so neither is
reachable in the shipping configuration — but both would return the moment someone widens
the vocabulary past the 55.

---

## 4b. ✅ MEASURED 2026-09-04 — the confidence gate, and it works on the errors that matter

Everything in 4b comes from `measure_medical_gate.py` on the **same 1,373 held-out clips**,
written to `medical_gate_test.json`. The script **refuses to print a single gate figure until
it reproduces the published 0.8383** — it does, exactly, along with all four per-fold
accuracies, so the clip loading and the 123-class order are confirmed right.

*(A previous attempt, `measure_conf_gate.py`, scored the per-word **exemplar** clips. Those
are training data, so it reported precision **1.000 at every threshold** — pinned at the
ceiling, no information. That file cannot answer this question and should not be used for it.)*

### What a confidence threshold buys

| τ | you speak | precision | wrong things spoken |
|---|---|---|---|
| 0.00 (ungated) | 100% | 0.8383 | **222** |
| 0.50 | 75.2% | 0.9448 | 57 |
| 0.70 | 59.4% | 0.9791 | 17 |
| **0.80** | **51.1%** | **0.9872** | **9** ← 25× fewer |
| 0.90 | 36.2% | 0.9940 | 3 |

### 🔴 The decisive result: dangerous confusions all fire at LOW confidence

I expected the opposite, and wrote the test to find out: *if* the §4 confusions fire at high
confidence, then no threshold can stop them and the never-auto-commit list is the only
defence. **They don't.**

```
53 clips in which a §4 dangerous confusion actually fired
 0 of them reached confidence 0.80
highest confidence ANY dangerous confusion reached:  0.746   (ear -> skin)
headroom to the gate:                                0.054
```

**A 0.80 gate suppressed every enumerated dangerous confusion in the test split** — all 53,
including both non-artefact rows (`hot → bad` max 0.673, `ear → skin` max 0.746). Zero of 53
bounds the true rate at about **5.7%** by the rule of three; it does not bound it at zero. But
the direction is unambiguous and it is the strongest safety finding in this document.

**So `--medical` now runs `L1_CONF 0.80 / L2_CONF 0.70`, measured, not inherited.** The cost is
real: only ~51% of single clips clear 0.80, so expect to repeat signs more than on
`--vocab250`. Temporal accumulation raises the true commit rate above 51%.

### 🔴 And a flaw in this document: §2 and the ship list gate on the wrong quantity

The 0.80 ship gate is on **recall** — P(model says X | truth is X). A speaking device needs
**precision** — P(truth is X | model says X). When the tool says "pain" the clinician acts on
"pain"; what matters is whether that utterance is trustworthy, not whether pain is usually
caught. **Over the 55 shipped words, recall overstates precision by more than 0.10 for 20 of
them.** The worst:

| word | recall (the gate) | **precision** | times announced |
|---|---|---|---|
| `who` | **1.000** | **0.455** | 22 |
| `skin` | **1.000** | 0.545 | 11 |
| `eye` | **1.000** | 0.625 | 8 |
| `blood` | 0.889 | 0.667 | 12 |
| `no` | **0.909** | **0.714** | 14 |

**`who` passes the gate at perfect recall and is wrong 55% of the time it is spoken.**

**This sharpens §1.** The headline "the model ships `no` at 0.909" is a *recall* number. Its
ungated precision is **0.714** — **more than one spoken refusal in four is not a refusal.** At
τ=0.80 it becomes 1.000, so the gate fixes it; ungated, it does not hold.

### The ship list re-cut on precision at τ=0.80

**Rescued — 11 of 13 failing words pass, 9 of them at 1.000:**
`eye` 0.625→1.000 · `skin` 0.545→1.000 · `no` 0.714→1.000 · `woman` 0.692→1.000 ·
`want` 0.714→1.000 · `show` 0.741→1.000 · `tired` 0.769→1.000 · `hand` 0.750→1.000 ·
`more` 0.750→1.000 · `wait` 0.774→0.913 · `who` 0.455→**0.875**

**🔴 Still failing at τ=0.80 — the two de-ship candidates:**

| word | ungated → at τ | note |
|---|---|---|
| `blood` | 0.667 → **0.667** | a **red-flag** word the gate does not help. Already never-auto-commit, so the human tap is the live defence. **Question for review: ship it at all?** |
| `father` | 0.800 → **0.750** | gets *worse* under the gate. Not clinically critical |

**Silenced, not passed — `always` and `tell` are never announced at τ=0.80 at all.** Their
precision is undefined because the gate mutes them. That is not a pass; it means two shipped
words cannot be spoken in the recommended configuration.

> ⚠️ **Sample sizes.** At τ=0.80 only 702 of 1,373 clips are spoken across 55+ words, so the
> per-word figures above rest on **3–23 clips each**. The aggregate (0.9872 on 702) is solid;
> read the individual 1.000s as "no errors seen in a handful", not as certainty.

### The gate knows when it is out of its depth

```
corr(per-signer mean confidence, per-signer accuracy) = 0.914     (7 signers with n>=50)
worst signer p49: accuracy 0.7634 on 617 clips (45% of the test set), mean confidence 0.631
```

Per-signer accuracy spans only **1.31×** here (0.763 → 1.000), far tighter than the 250-word
model's 2.65×. More usefully, **confidence tracks signer difficulty at r=0.914**, so the gate
throttles itself on the signers it handles worst instead of failing confidently on them. That
is the behaviour a safety gate needs and it was not designed in — it is worth confirming it
survives on a wider signer pool before relying on it.

---

## 5. The categories — this is the part to argue with

Five groupings decide everything above. They are a domain judgement, written down so a
reviewer can reject them:

```
negation_affirmation   no, not, yes
severity_change        bad, better, big, more, much, strong, weak, worse
certainty              all, always, maybe, some, sometimes
red_flag               bleed, blood, breathe, choke, faint, heart, help, hot, pain, sick
body_site              arm, back, bone, ear, eye, face, feet, hand, head, heart,
                       lungs, mouth, muscle, nose, skin, teeth, throat, tongue
```

A word in the first four groups that is **shippable** goes on the never-auto-commit list.
A word in the first four that is **not** shippable goes on the cannot-express list.
Body-site words drive the wrong-site confusion analysis only.

**Questions for the reviewer:**

1. Is `big` really a severity word in ASL clinical register, or is gating it noise? It has
   the second-highest accuracy in the list (0.967) and gating it costs throughput.
2. Should `pain` be held at all? At 0.971 it is nearly the best word in the vocabulary, and
   holding the single most useful clinical sign may make the tool feel broken.
3. `always` (certainty) vs `again` (0.867, not gated) — is that the right line for
   frequency-of-symptom questions?
4. Are there concepts **missing from the 55 entirely** that a clinical exchange cannot do
   without? The pruned list is in `data_medical/PROVENANCE.json`: chest, cramp, fever,
   infection, knee, leg, nausea, neck, needle, patient, rash, shot, shoulder, sneeze,
   stomach, vomit, wheelchair — 21 concepts dropped before training for too few clips.
   **`fever`, `nausea`, `vomit`, `chest` and `stomach` being absent looks serious.**
5. Is one tap the right confirmation, or should a held word require a distinct gesture /
   second modality?

---

## 6. What is enforced in code, and where

| gate | file | line |
|---|---|---|
| never-auto-commit hold | `live_demo.py` | in the commit path, right after `decide_commit()` |
| gate list loaded | `live_demo.py` | the `--medical` branch |
| AI sentence-building **off** by default | `live_demo.py` | `--medical` does *not* set `args.ai`, unlike `--vocab250` — an LLM rephrasing clinical glosses can change meaning |
| `--canonical` refused | `live_demo.py` | the medical weights record `canonical_hand: false` in all four folds |
| vocab/model class-count check | `live_demo.py` | compares the loaded vocabulary against the SavedModel's own output dim |
| the gate data | `safety_gates_medical.json` | regenerate after any vocabulary change |

**Regenerate the gates after any retrain or vocabulary merge.** Every number here is
measured on this specific 123-class model. The v1 model (124 classes) shipped `yes` and
`hurt`; v2 merged `hurt`→`pain` and demoted `yes`. A stale gate file is a silent safety
failure, which is why `--medical` warns loudly if the file is missing.

---

## 7. Limits

- **34 of 123 classes have fewer than 5 test clips and are UNMEASURED.** Absence from §4 is
  therefore not evidence of safety for those words.
- 9 held-out signers is a small sample for a fairness claim. Per-signer accuracy on the
  250-word model ranged **0.31–0.82**, and an oracle per-signer correction moved the worst
  signer by only −0.0018 — the spread was real and not fixable downstream.
- The macro accuracy rises with test-n (0.7202 at n≥1 to 0.8474 at n≥10) but that is
  **confounded**: test is a ~22% whole-signer split, so a thin test class is also a thin
  *training* class. Undertrained and unmeasured cannot be separated from this data.
- 🔴 **Licence.** Sem-Lex is **CC BY-NC-SA**: non-commercial, and share-alike arguably
  reaches these weights. This is a demo and a research artifact, not a shippable product.
  See `docs/LICENCE_REQUESTS.md`.
