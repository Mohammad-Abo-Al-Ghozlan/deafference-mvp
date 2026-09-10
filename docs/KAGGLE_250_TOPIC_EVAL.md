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

### 🔴 WHICH WEIGHTS — read this before attaching anything

There are **two** 250-word ensembles and the repo default is the weaker one:

| | corpus | 30 fps | **7 fps (what the demo runs at)** | needs |
|---|---|---|---|---|
| `artifacts_250/` (the `--vocab250` default) | legacy | 0.7755 | **never measured** | must run WITHOUT `--canonical` |
| **`artifacts_250_canonical/`** | canonical + `--decimate 0.5` | **0.7787** | **0.7628** | **REQUIRES `--canonical`** |

`artifacts_250_canonical/PROVENANCE.json`, 2026-08-27: *"supersedes: legacy 4-fold ensemble
0.7755 (30 fps only)"*. All four folds beat their legacy counterparts and the paired fold-0 A/B
measured **+0.0218 at 7 fps**, cutting the frame-rate penalty from 5.13 to 2.64 points.

**Score the canonical ensemble.** Which fixes the corpus question too: those weights *never saw
a hand in the L block*, so they need the **canonical** corpus — exactly what
`extract_canonical.py --dominance geometric` produces. Mixing the two silently destroys
left-dominant signers (17.8% of this corpus), which is why `live_demo` warns on the pairing.

> ⚠️ `word_acc_250.json` is **fold-0 of the LEGACY model** (per-word mean 0.7571 against
> fold-0's 0.7576). So the `mean_test_acc` in every topic file, and the ≥0.60 floor that chose
> which 206 words to include, both describe the legacy model. The canonical one is better, so a
> word above the floor there is very likely still above it — but the floor was not re-derived.

### Path A (~20 min) — an extracted CANONICAL corpus already exists

**Do not hunt through your datasets by name.** Attach every plausible candidate at once and let
this cell identify them by content. Names are unreliable here — `asl250-canon-v1-REFUTED` was
named for a verdict that `SESSION_HANDOFF.md` later overturned (*"Canonicalization was never
refuted... that comparison was blind by construction"*), so its name is actively misleading.

```python
import glob, os, numpy as np, random

def fingerprint(root, n_words=30, per_word=4):
    """left_dead ~1.00 = CANONICAL | ~0.56 = LEGACY. The L block is empty in a canonical
    corpus because the dominant hand is always moved to 54-74."""
    fs = sorted(glob.glob(os.path.join(root, "by_word", "*", "sequences.npz")))
    if not fs:
        return None
    random.seed(0); random.shuffle(fs)
    dead = []
    for f in fs[:n_words]:
        try:
            z = np.load(f, allow_pickle=False)
        except Exception:
            continue
        for k in list(z.files)[:per_word]:
            a = z[k]
            if a.ndim == 3 and a.shape[1] >= 75:
                dead.append(float(np.isnan(a[:, 33:54, 0]).all(axis=1).mean()))
    return (len(fs), float(np.mean(dead)) if dead else float("nan"))

for p in sorted(glob.glob("/kaggle/input/*")):
    fp = fingerprint(p)
    if fp is None:
        sub = [d for d in glob.glob(p + "/*") if os.path.isdir(d)]
        fp = next((f for f in (fingerprint(d) for d in sub) if f), None)
    if fp:
        n, dead = fp
        kind = "CANONICAL" if dead > 0.90 else ("LEGACY" if dead < 0.75 else "UNCLEAR")
        print(f"  {os.path.basename(p):<34s} {n:4d} word dirs  L-block dead {dead:.3f}  {kind}")
    else:
        print(f"  {os.path.basename(p):<34s} no by_word/")
```

**Take the one printing `CANONICAL` with ~250 word dirs** and skip Cell 3. If nothing prints
`CANONICAL`, you are on Path B.

### Path B (~1 h 20) — extract first

| kind | what | why |
|---|---|---|
| **Competition** | **Google - Isolated Sign Language Recognition** (`asl-signs`) | the raw landmark parquet. **This is GISLR, not the fingerspelling competition** — accept its rules once. |
| **Dataset** | `asl250-mask-ab-v1` (holds `data/split_manifest.parquet`) | 🔴 **the original split.** Do not generate a new one. |
| **Dataset** | **one new private dataset from `kaggle_250_topic_gates.zip`** | 🔴 weights + scorer + masks in a single upload. Build it with the snippet below; Kaggle unzips it for you. |

**Build the upload, locally, in the repo root:**

```bash
python - <<'PY'
import zipfile, glob, os
OUT = "kaggle_250_topic_gates.zip"
members  = [(f, f) for f in sorted(glob.glob("artifacts_250_canonical/**/*", recursive=True))
            if os.path.isfile(f)]
members += [(f, os.path.basename(f)) for f in
            ["training/measure_topic_gates.py", "training/eval_savedmodel_250.py",
             "training/train.py", "training/extract_canonical.py",
             "sign_landmarks.py", "vocab_250.json"]]
members += [(f, os.path.basename(f)) for f in sorted(glob.glob("topic_*.json"))
            if "medical" not in f]
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for src, arc in members:
        z.write(src, arc.replace("\\", "/"))     # the ZIP spec requires forward slashes;
                                                 # PowerShell's Compress-Archive writes
                                                 # BACKSLASHES, which Linux then treats as
                                                 # part of the filename. Do not use it here.
with zipfile.ZipFile(OUT) as z:
    ns = z.namelist()
    assert not any("\\" in n for n in ns) and not any(".env" in n for n in ns)
    print(f"{OUT}: {os.path.getsize(OUT)/1e6:.1f} MB, {len(ns)} entries, "
          f"{sum(n.startswith('topic_') for n in ns)} topics, "
          f"{sum('saved_model.pb' in n for n in ns)} savedmodels")
PY
```

Expect **18.6 MB, 35 entries, 11 topics, 4 savedmodels.** Then Kaggle → Datasets → New Dataset
→ drag that **one zip** → title **`deafference-250-topic-gates-code`** → **Private** → Create.
Kaggle expands the archive on upload, so `artifacts_250_canonical/savedmodel_fold0/` survives as
a directory.

> 🔴 **Never drag the repo folder** — it contains `.env`. The zip above is built from an explicit
> file list for that reason, and asserts no `.env` entry before you upload it. **Private** is
> also required: the competition licence forbids redistribution.

### Cell 1 — find everything, never hand-write a path

```python
import glob, os, json
for a in sorted(glob.glob("/kaggle/input/*")):
    print(a)
    for b in sorted(glob.glob(a + "/*"))[:14]:
        print("   ", os.path.basename(b))

CODE   = glob.glob("/kaggle/input/**/measure_topic_gates.py", recursive=True)
ALLMOD = sorted(glob.glob("/kaggle/input/**/savedmodel_fold*", recursive=True))
# Prefer the CANONICAL folds and never mix the two ensembles. If asl250-weights is also
# attached, ALLMOD holds 8 dirs from two different corpora; averaging across them would be
# meaningless and nothing would raise. Selecting by path keeps that impossible.
CANON  = [d for d in ALLMOD if "canonical" in d.lower()]
MODELS = CANON or ALLMOD
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
print("models  =", len(MODELS), "(expect 4)",
      "CANONICAL" if CANON else "*** LEGACY — these have no 7fps number; "
                                "attach artifacts_250_canonical ***")
if len(ALLMOD) > 4:
    print(f"        NOTE {len(ALLMOD)} fold dirs attached; using the {len(MODELS)} canonical "
          f"ones. Do NOT average across corpora.")
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
# Pick the manifest BY ITS CONTENT, not by glob order. More than one may be attached and
# MAN[0] is whichever sorted first — a different manifest is a different split, which
# silently redefines "held-out" and makes these numbers incomparable to word_acc_250.json.
USE_MAN = None
for c in MAN:
    try:
        _m = pd.read_parquet(c)
    except Exception as e:
        print(f"  {c}: unreadable ({type(e).__name__})"); continue
    ok = _m["word"].nunique() == 250 and len(_m) == 94198
    print(f"  {c}: {len(_m)} rows, {_m['word'].nunique()} words {'<- USE THIS' if ok else ''}")
    if ok:
        USE_MAN = c
assert USE_MAN, "no manifest with 94,198 rows / 250 words — attach asl250-mask-ab-v1"
print("splits:", dict(pd.read_parquet(USE_MAN)["split"].value_counts()))
```

```python
!rm -rf /kaggle/working/canon
!python extract_canonical.py --raw {RAW[0]} --manifest {USE_MAN} --out /kaggle/working/canon --variants none --dominance geometric --unaligned moving --workers 8
```

```python
CORPUS = ["/kaggle/working/canon"]
assert os.path.isdir(CORPUS[0] + "/by_word"), "extraction produced no by_word/ — read the log"
print("corpus ready:", len(glob.glob(CORPUS[0] + "/by_word/*")), "word dirs (expect 250)")
```

Watch the report card: **`aligned` should land near 55%.** Far from it means the geometry is
not resolving and the corpus should not be scored.

### Cell 4 — the measurement (~15 min)

```python
# Resolve the models DIR in Python. `$(dirname ...)` inside an IPython ! line mixes shell
# substitution with {} interpolation and breaks on any path containing a space.
MODELS_DIR = os.path.dirname(MODELS[0])
print("models dir:", MODELS_DIR, "->", sorted(os.path.basename(d) for d in MODELS))
assert len(MODELS) == 4 and all(os.path.dirname(d) == MODELS_DIR for d in MODELS), \
    "the four folds must live in ONE directory; two model datasets are attached"
```

```python
!python measure_topic_gates.py --data-dir {CORPUS[0]} --models {MODELS_DIR} --vocab vocab_250.json --topics . --exclude-topics medical --split test --save-probs /kaggle/working/probs_250_test.npz --out /kaggle/working/topic_250_measured.json
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
