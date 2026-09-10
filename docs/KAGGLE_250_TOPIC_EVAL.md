# Measuring the 250-word topic set — the one number set we do not have

**Written 2026-09-10.** The 11 general topics (`topic_animals.json` … `topic_time_question.json`)
cover all 206 of the 250 classes scoring ≥ 0.60 on held-out test. Their **per-word** accuracy is
real. Their **gate** numbers are not measured, and this file is the run that fixes that.

---

## What is missing, and exactly why

| number | medical (123-class) | 250-word |
|---|---|---|
| per-word held-out accuracy | measured | ✅ **measured** — `word_acc_250.json` |
| topic first-try rate | measured | ❌ |
| topic precision | measured | ❌ |
| off-topic false speech | measured | ❌ |
| `mass_min` | measured, per topic | 🟡 **provisional 0.10** |
| confusable-pair split into `_a`/`_b` | measured, done | ❌ impossible |

**The blocker is a missing test SET, not missing code.** This repo has the four savedmodels,
`vocab_250.json` and `word_acc_250.json` — but the only clips it holds are
`sign_clips_250.npz`, which are the **per-word exemplar clips used for the demo's reference
poses**. Those are training data. Scoring a confidence gate on them returns **precision 1.000
at every threshold**, which is not a good result — it is *no information*, and it is the exact
trap `measure_conf_gate.py` is documented as falling into.

> ⚠️ `artifacts_medical/confusion_all250_fold*.csv` looks like it should help. It does not —
> `all250` is the **medical** run's tag. Those four files are the 123-class model. There is no
> confusion matrix for the 250-word model anywhere in the repo, which is why its topics could
> not be split into `_a`/`_b` halves the way the medical ones were.

### Why the medical numbers must not simply be copied over

`mass_min` is a threshold on **how much unmasked probability lands on the active topic.** That
quantity depends on how many classes are competing:

```
a diffuse prediction over 123 classes, 25-word topic  ->  ~25/123 = 0.20 on the topic
a diffuse prediction over 250 classes, 25-word topic  ->  ~25/250 = 0.10
```

So **the same threshold is materially stricter on the 250-word model.** The shipped 0.10 is the
class-count-scaled equivalent of the 0.20 that measured *free* on medical — a defensible
starting point, not a measurement. Every topic file says so in `mass_min_provisional: true`.

---

## The run

> ### ⚠️ CORRECTED 2026-09-10 — the first draft of this section was wrong three ways
>
> It told you to attach `extract_landmarks.py`, which **only exists under `training/medical/`
> and is the Sem-Lex extractor** — nothing to do with GISLR. The GISLR → 75-point code is
> **`training/extract_canonical.py`**.
>
> It also had you invent a fresh signer-disjoint split in cell 2. **Do not.** The 250 model's
> own split already exists — `split_manifest.parquet`, 94,198 rows, 250 words, in the Kaggle
> dataset `asl250-mask-ab-v1` (see `KAGGLE_CANONICAL_REBUILD.md` cell 3, which asserts both
> figures). `word_acc_250.json` came from that split, so reusing it is the only way the new
> numbers are comparable to the per-word accuracy already in the topic files. A different
> split silently changes what "held-out" means.
>
> And it claimed 15–25 min. **That is only true if an extracted corpus already exists.**
> Extraction from raw parquet is ~1 h.

**Accelerator: GPU.** **Internet: off.** Two paths — check for path A first, it saves an hour.

### Path A (~20 min) — an extracted corpus dataset already exists

Look in **Add Input → Your Datasets / notebook outputs** for anything holding `by_word/`
alongside `split_manifest.parquet` — the output of the canonical rebuild. If it's there,
attach it and skip straight to "Cell 2".

### Path B (~1 h 20) — extract first

| kind | what | why |
|---|---|---|
| **Competition** | **Google - Isolated Sign Language Recognition** (`asl-signs`) | the raw landmark parquet. **This is GISLR, not the fingerspelling competition** — accept its rules once. |
| **Dataset** | `asl250-mask-ab-v1` (holds `data/split_manifest.parquet`) | 🔴 **the original split.** Do not generate a new one. |
| **Dataset** | the output holding `artifacts_250/savedmodel_fold{0..3}` | the four folds |
| **Dataset** | a new private dataset: `vocab_250.json`, the 11 `topic_*.json` files, `training/measure_topic_gates.py`, `training/eval_savedmodel_250.py`, `training/train.py`, `training/extract_canonical.py`, `sign_landmarks.py` | the scorer and the masks |

> 🔴 Drag **the individual files**, never the repo folder — it contains `.env`. Visibility
> **Private**: the competition licence forbids redistribution.

### Cell 1 — find everything, never hand-write a path

```python
import glob, os, json
for a in sorted(glob.glob("/kaggle/input/*")):
    print(a)
    for b in sorted(glob.glob(a + "/*"))[:14]:
        print("   ", os.path.basename(b))

CODE   = glob.glob("/kaggle/input/**/measure_topic_gates.py", recursive=True)
MODELS = sorted(glob.glob("/kaggle/input/**/savedmodel_fold*", recursive=True))
VOCAB  = glob.glob("/kaggle/input/**/vocab_250.json", recursive=True)
TOPICS = [p for p in glob.glob("/kaggle/input/**/topic_*.json", recursive=True)
          if "medical" not in os.path.basename(p)]
CORPUS = [os.path.dirname(p) for p in
          glob.glob("/kaggle/input/**/split_manifest.parquet", recursive=True)
          if os.path.isdir(os.path.join(os.path.dirname(p), "by_word"))]
MAN    = glob.glob("/kaggle/input/**/split_manifest.parquet", recursive=True)
RAW    = [os.path.dirname(p) for p in glob.glob("/kaggle/input/**/train.csv", recursive=True)
          if os.path.isdir(os.path.join(os.path.dirname(p), "train_landmark_files"))]

print()
print("scorer  =", CODE or "*** attach the code dataset ***")
print("models  =", len(MODELS), "(expect 4)")
print("vocab   =", VOCAB or "*** missing ***")
print("topics  =", len(TOPICS), "(expect 11)")
print("corpus  =", CORPUS or "none -> PATH B, extract first")
print("manifest=", MAN or "*** attach asl250-mask-ab-v1 ***")
print("raw     =", RAW or "none (fine on PATH A)")
assert CODE and len(MODELS) == 4 and VOCAB and len(TOPICS) == 11
```

### Cell 2 — stage the code, and prove the scorer works before spending GPU

`--selftest` needs no data and no model. It asserts the thing the whole run is about: that a
2-word mask renormalises an out-of-topic clip to confidence **1.00**, so confidence alone
cannot detect it and `mass_min` is the only signal that can. If this fails, nothing below
means anything.

```python
import shutil
NEED = ["measure_topic_gates.py", "eval_savedmodel_250.py", "train.py",
        "extract_canonical.py", "sign_landmarks.py"]
for nm in NEED:
    hits = glob.glob(f"/kaggle/input/**/{nm}", recursive=True)
    assert hits, f"*** {nm} not in any attached dataset — add it and re-run ***"
    shutil.copy(hits[0], nm)
    print("staged", nm)
shutil.copy(VOCAB[0], "vocab_250.json")
for t in TOPICS:
    shutil.copy(t, os.path.basename(t))
print(f"staged vocab + {len(TOPICS)} topic files")
```

```python
!python measure_topic_gates.py --selftest
```

Must end **`ALL CHECKS PASSED`**.

### Cell 3 — PATH B ONLY: extract (~1 h). Skip on path A.

Reuses the ORIGINAL manifest, so the test signers are the same ones `word_acc_250.json` was
measured on.

```python
import pandas as pd
_m = pd.read_parquet(MAN[0])
assert _m["word"].nunique() == 250, f"{_m['word'].nunique()} words, expected 250"
assert len(_m) == 94198, f"{len(_m)} rows, expected 94198 — that is a DIFFERENT split"
print("splits:", dict(_m["split"].value_counts()))

!rm -rf /kaggle/working/canon
!python extract_canonical.py --raw {RAW[0]} --manifest {MAN[0]}     --out /kaggle/working/canon --variants none --dominance geometric     --unaligned moving --workers 8
CORPUS = ["/kaggle/working/canon"]
```

Watch the report card: **`aligned` should land near 55%.** Far from it means the geometry is
not resolving and the corpus should not be scored.

### Cell 4 — the measurement (~15 min)

```python
!python measure_topic_gates.py     --data-dir {CORPUS[0]} --models $(dirname {MODELS[0]})     --vocab vocab_250.json --topics . --exclude-topics medical     --split test     --save-probs /kaggle/working/probs_250_test.npz     --out /kaggle/working/topic_250_measured.json
```

It prints a row per topic, a POOLED line, and the comparison that decides whether topics are
worth anything: **one open 250-word mask vs the topic set.** `--save-probs` means re-scoring
with a different threshold grid later costs seconds instead of GPU minutes — keep that file.

### What to send back

`topic_250_measured.json`, plus cell 2's signer/class counts. Each topic file's
`mass_min` / `mass_min_provisional` and a new `measured_*` block get filled from it, and
`mass_min_provisional` is deleted — that flag existing is the marker that this run has not
happened.

---

## What the answer will probably look like, and the honest uncertainty

The 123-class model gave **0.6534 first-try open → 0.9223 across 13 measured topics**. The
250-word model starts weaker (macro per-word 0.7571 against medical's 0.8383 on three times as
many unseen signers) and has twice the competitors, so expect the topic figures to land
**below** the medical ones. The union of these 11 topics averages **0.8241** per-word accuracy
against **0.7571** for all 250, purely from excluding the 44 words under the 0.60 floor.

**Two things this run cannot fix:**

1. **No `_a`/`_b` confusability split.** It needs a confusion matrix, which needs this run to
   have happened first. Once `topic_250_measured.json` exists, a second pass can split the
   worst topics the way the medical set was split — measured worth 35 → 14 wrong words there.
2. **`owie` is not recoverable by masking.** It scores **0.32**, so it sits below the floor and
   is unreachable. In a child-language corpus `owie` means *hurt*, which is arguably the single
   most load-bearing word in the whole 250 for anything clinical. Also excluded and worth
   knowing: `mouth` 0.30, `give` 0.15, `go` 0.22, `nap` 0.11, `after` 0.27, `person` 0.23.
   That is a **data** problem — more signers per word, per `docs/CLIPS_PER_SIGN_CURVE.md` —
   not a gate problem.
