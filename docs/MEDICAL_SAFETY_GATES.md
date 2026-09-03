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

---

## 1. The finding that matters most: negation is asymmetric

**The model ships `no` and cannot ship `yes`.**

| | test acc | ships? |
|---|---|---|
| `no` | **0.909** | ✅ |
| `yes` | **0.714** | ❌ below the 0.80 gate |
| `not` | 0.647 | ❌ |
| `worse` | 1.000 on **1** test clip | ❌ unmeasured |
| `better` | 1.000 on **3** test clips | ❌ unmeasured |

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

| word | test acc | why it is gated |
|---|---|---|
| `no` | 0.909 | negation — inverts meaning |
| `bad` | 0.952 | severity |
| `big` | 0.967 | severity |
| `more` | 0.857 | severity |
| `always` | 0.800 | certainty |
| `pain` | 0.971 | red-flag symptom |
| `blood` | 0.889 | red-flag symptom |
| `breathe` | 1.000 | red-flag symptom |
| `sick` | 1.000 | red-flag symptom |
| `help` | 0.966 | red-flag symptom |

**Note the accuracies are high.** The gate is not there because these words are weak — most
are among the best in the vocabulary. It is there because they are the words where being
wrong changes clinical meaning rather than just sounding odd. Confidence is not authority.

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
