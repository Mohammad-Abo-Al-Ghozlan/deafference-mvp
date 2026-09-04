# Runbook — the fingerspelling CTC baseline, step by step

**Written 2026-09-04.** Everything below is a click-path or a cell. The code is committed and
its `--selftest` passes 26 checks, so nothing here is waiting on me.

```
training/fingerspelling/train_ctc.py     the model  (committed, selftest green)
training/fingerspelling/subset_landmarks.py   the data prep (already run, 4 shards)
docs/FINGERSPELLING_DATA_FINDINGS.md     why every design choice is what it is
```

---

## Part 1 — `fs75.npz` has to become a Kaggle **dataset** · ~10 min, no GPU

Right now `fs75.npz` (≈547 MB) is **notebook output**. Kaggle cannot attach notebook output as
an input to another notebook; only a *dataset* can be an input. So it has to be promoted once.

1. **kaggle.com → your avatar → Your Work → Code**
2. Open the notebook where you ran the 4-shard subset (the one with the competition attached
   and `deafference-fs-code`). Its Output tab should contain **`fs75.npz`** and
   `gap_stats.json`.
3. **Output** tab → the **⋮** menu at the top of the Output panel → **New Dataset**
4. Title: **`deafference-fs75`**
5. Visibility: **Private** ← the competition data is licensed; a public copy is redistribution.
6. **Create**

> ⚠️ **A brand-new dataset name, never an existing one.** Your standing rule, and it exists
> because creating a dataset from notebook output *onto* an existing dataset can replace what
> is already there.

**If `fs75.npz` is NOT in that Output tab**, the run wasn't committed with Save & Run All and
the file died with the session. Re-run it — Part 1b below — it is ~20 minutes of CPU.

<details>
<summary><b>Part 1b — only if you need to regenerate <code>fs75.npz</code></b></summary>

> 🛑 **STOP — is `deafference-fs75` already in your notebook's Input panel?** Then Part 1 is
> done and this whole section is ~20 minutes of CPU to rebuild a file you already have. Skip
> to **Part 3**. This section exists only for the case where the Output tab has no `fs75.npz`
> because the run was never committed with Save & Run All.

New notebook, **accelerator OFF** (this is CPU work; the GPU would burn quota for nothing).
Attach the competition **and** `deafference-fs-code`. Then:

```python
# cell 1 — find the real paths. Kaggle mounts inputs NAMESPACED, so a one-level
# glob finds nothing and the script's --base default never resolves.
import glob, os
hits = glob.glob('/kaggle/input/**/train_landmarks', recursive=True)
BASE = os.path.dirname(hits[0]); print('BASE =', BASE)
CODE = os.path.dirname(glob.glob('/kaggle/input/**/subset_landmarks.py', recursive=True)[0])
print('CODE =', CODE)
```

```python
# cell 2 — prove the write path in seconds before touching real data
!python {CODE}/subset_landmarks.py --selftest
!python {CODE}/subset_landmarks.py --base {BASE} --out /kaggle/working/smoke --limit-files 1 --limit-seq 5
```

```python
# cell 3 — the real run, 4 shards
!python {CODE}/subset_landmarks.py --base {BASE} --out /kaggle/working --limit-files 4
!ls -la /kaggle/working
```

Then **Save & Run All (Commit)** so `/kaggle/working` is captured as the version Output, and
come back to Part 1 step 3.
</details>

---

## Part 2 — put `train_ctc.py` next to the other script · ~3 min

`deafference-fs-code` already holds `subset_landmarks.py`. Add the trainer beside it.

1. **kaggle.com/datasets/mohammedsalim1/deafference-fs-code**
2. **⋮** (top right) → **New Version**
3. Drag in **`training/fingerspelling/train_ctc.py`** from your machine
4. Leave the existing `subset_landmarks.py` in place
5. Version notes: `add train_ctc.py` → **Create**

> This is a *file upload*, not a dataset-from-notebook-output, so the standing rule about
> brand-new names does not apply here. Drag the **single file**, never the repo folder — the
> repo contains `.env`.

---

## Part 3 — the training notebook · ~3–5 h GPU

**New notebook. Accelerator: `GPU P100`** — not T4 ×2. `train_ctc.py` has no
`MirroredStrategy` and no `mixed_precision`, so it uses **one** card and stays in FP32: the
second T4 would sit idle for the whole run, and on FP32 a single P100 (~9.3 TFLOPS) beats a
single T4 (~8.1). Same quota cost either way, so P100 is a free ~15%.
**Add data:** `deafference-fs75`, `deafference-fs-code`, **and the competition itself.**

> 🔴 **Keep the competition attached.** I earlier said detaching it was harmless cleanup —
> **that was wrong.** `character_to_prediction_index.json` lives there and it is the only
> shard-independent source of the corpus's **59-character** charset. Without it the trainer
> falls back to whatever the attached shards contain — the first run got **51** — and because
> the map is `sorted(observed)`, adding shards later *reindexes* the characters instead of
> appending them. Two runs with different shard mixes then share no label space, and neither
> one's `charset.json` can be loaded against the other. Same failure as the 123-class medical
> vocab. Confirm it worked: `report.json` must show `"n_classes": 60`.

> **Do not copy the ``` fence lines** into a cell. A stray `python` on line 1 is
> `NameError: name 'python' is not defined`, and every later cell then dies on
> `NameError: name 'CODE' is not defined` — three broken cells from one paste.

```python
# cell 1 — go/no-go. Names the missing prerequisite instead of throwing IndexError.
import glob, os
import tensorflow as tf

npz  = glob.glob('/kaggle/input/**/fs75.npz',     recursive=True)
code = glob.glob('/kaggle/input/**/train_ctc.py', recursive=True)
gpus = tf.config.list_physical_devices('GPU')

print('fs75.npz    :', f'{npz[0]}  {os.path.getsize(npz[0])/1e6:.0f} MB' if npz
      else 'MISSING  <- Part 1 not done, or the dataset is empty')
print('train_ctc.py:', code[0] if code else 'MISSING  <- Part 2 not done')
print('GPU         :', gpus if gpus else 'NONE  <- Settings > Accelerator > GPU')

assert npz and code and gpus, 'fix the MISSING line above before anything else'
NPZ, CODE = npz[0], os.path.dirname(code[0])
print('\nNPZ  =', NPZ, '\nCODE =', CODE)
```

Expect `fs75.npz  547 MB`. A much smaller number means the dataset captured a smoke
run (`--limit-seq`) rather than the 4-shard run.

```python
# cell 2 — SELFTEST FIRST. 26 checks, no data, ~30 s. If this fails, stop.
!python {CODE}/train_ctc.py --selftest
```

```python
# cell 3 — the run
!python {CODE}/train_ctc.py --npz {NPZ} --out /kaggle/working/fs_out --epochs 40
```

Then **Save & Run All (Commit)** so the weights survive the session.

### What good looks like — ✅ MEASURED 2026-09-04, no longer estimated

The 4-shard run completed. **Full analysis: `docs/FINGERSPELLING_CTC_RESULT.md`.** These are the
actual numbers, replacing the guesses that were here:

```
[charset]  60 classes  <- ONLY if the competition is attached. 52 means the charset came
                          from the shards (51 of the corpus's 59 chars) — see below
[filter]   kept 3,458/3,997 (86.5%)      367 hand-frames · 170 T_out · 2 repeats
[split]    2,999 train / 459 val, 13 held-out signers, NO overlap
[model]    1.34M params   (I had said 2-4M)
[ep   1]   train 84.9 | val 79.9 CER 1.0000 | 58s
[ep  12]   CER still EXACTLY 1.0000        <- NORMAL. all-blank comes before characters
[ep  19]   CER 0.7776                      <- the cliff
[ep  39]   CER 0.4703  <- best. total wall time 39 MIN, not the 3-5 h I predicted
```

| my earlier estimate | actual |
|---|---|
| `~2-4M params` | **1.34M** |
| `~59 chars -> 60 classes` | **52** — a bug, now fixed |
| `~3-5 h GPU` | **39 min** |
| "CER clearly under 0.9 by epoch 10" | **epoch 19** — the old line would have killed a working run |

**Stop the run and tell me if you see any of these:**

| symptom | what it means |
|---|---|
| the run **exits** with `[err] non-finite training loss` | the filter leaked. Deliberate `sys.exit`. Most valuable output the run could give me |
| `⚠ N non-finite` on an epoch line | same bug class, caught by the length guard. Send me N |
| `[err] N character occurrences ... not in the charset` | wrong `--charset` for this data. Do not work around it — the labels would be truncated |
| `[charset] source: OBSERVED ...` | the competition isn't attached, so the charset is shard-derived and **not comparable to any other run** |
| `[filter] kept` below ~80% | expected **86.5%** |
| `SIGNER LEAK` assertion | the split broke; every number after it is meaningless |
| CER flat at 1.000 **past epoch 20** | not learning. Epochs 1–12 at exactly 1.0 are expected |

> 🔴 **Watch `val_loss`, not `val_cer`, for overfitting.** Measured on this run: val loss
> bottomed at **epoch 23 (48.67)** then rose **39%** to 67.58 by epoch 40, while train loss fell
> **2.4×** — textbook memorisation. **CER never showed it**, drifting 0.0151 across epochs 27–40
> with its best value at epoch 39. Greedy CTC decode keeps the argmax path roughly right while
> the probabilities rot, so the old "val CER falling then rising" line would never have fired.

### What to send me

`/kaggle/working/fs_out/report.json` — it carries the history, the per-signer CER, the filter
breakdown and the val signer list. That one file is enough; don't bother with the weights yet.

The run writes five things, and two of them are safety nets:

| file | when | why it matters |
|---|---|---|
| `report.json` | at the end | **this is the one to send me** |
| `history.json` | **rewritten every epoch** | survives a crash or a timeout — if the run dies at epoch 23 this still holds 22 rows |
| `charset.json` | before epoch 1 | the FROZEN char→index map. Inference must load it, never recompute it |
| `fs_ctc.weights.h5` | on each new best val CER | best-CER checkpoint, not last-epoch |
| `savedmodel_fs_ctc/` | same | wrapped in try/except, so a failed export warns and does not kill the run |

**A non-finite training loss now kills the run on purpose** (`sys.exit`) rather than limping
on — so if the process stops early with `[err] non-finite training loss at epoch N batch M`,
that is the feasibility filter having let something through, and it is the single most
valuable thing you could send me.

---

## Part 4 — the two cheap add-ons

### 4a. `measure_conf_gate` on the medical model — ❌ **I tried this and it cannot answer**

Don't spend a session on it. I ran it locally today:

```
in-domain precision   1.000 at EVERY gate from 0.30 to 0.90, ungated 1.000
out-of-domain leakage SKIPPED — every clip was inside the mask (and it crashed; fixed)
```

The exemplar clips **are** training data, so accuracy is pinned at the ceiling and the numbers
carry no information. A trustworthy gate needs the **held-out test split** — 1,373 clips from
9 unseen signers, already sitting in `data_medical/` — which is a different script. It is
fully local, no GPU, no Kaggle. **On me, not you.** Until then `--medical` keeps announcing its
gates as inherited-and-unmeasured, which is the honest state.

### 4b. The medical re-extract for native duration — ⚠️ **cost unknown, one question first**

I said "~40 min CPU". **I need to check something before you spend a session on it:** the
re-extract reads the *raw Sem-Lex pose files*, and the notes say those were downloaded from
Google Drive one archive at a time and `os.remove`d as it went — i.e. they may not exist as a
persistent Kaggle dataset at all.

**Answer this and I'll price it properly:** do you have a Kaggle dataset holding the Sem-Lex
`*-poses` files (or the extracted `.npy` per video)? If yes it is ~40 min of CPU. If no, it is
the original 8 GB download again and it is not a "cheap add-on".

The patch is already committed either way — `semlex_poses_to_75.py` now carries
`span`/`raw_frames`/`lead`/`trail` into the `.npz`, so whenever the re-extract happens the
native durations come with it.

---

## Part 5 — the 16-shard scale-up · ~80 min CPU (free) + ~1.6 h GPU

**Why 16 and not 68.** The 4-shard model overfits (val loss +39% from epoch 23) on 3,458
sequences with 1.34M params — a data-starvation signature, so data is the lever, not the
architecture. But **68 shards peaks at 14.1 GB of host RAM against a Kaggle GPU notebook's
~13 GB** and would OOM *after* a ~6 h subset job. 16 shards is 4× the data at 3.3 GB peak.

| shards | seqs | peak RAM | GPU h @25 ep | |
|---|---|---|---|---|
| 4 | 3,997 | 0.83 GB | 0.4 | done — CER 0.4703 |
| **16** | **15,988** | **3.32 GB** | **1.6** | ← this part |
| 34 | 33,974 | 7.05 GB | 3.4 | later, if 16 pays off |
| 68 | 67,949 | 14.09 GB | 6.8 | **OOMs** — needs a feature-store rewrite first |

### 🔴 Three traps, all avoidable

1. **Re-upload `train_ctc.py` first.** The copy in `deafference-fs-code` predates `de7504e`
   and `dc7873e`; it has no `--charset` and no `--val-signers`, so it would silently rebuild
   a shard-derived charset and deal a fresh holdout.
2. **Attach ONLY the new npz.** `subset_landmarks.py` always writes the filename `fs75.npz`,
   so with both datasets mounted `glob(...)[0]` resolves to the **4-shard** one — the run
   would "show no improvement" because it retrained on the old data. Cell 1 below refuses.
3. **Pin the val signers.** `--limit-files N` takes the first N of a *sorted* list, so 16
   shards is a strict superset of 4 — but the automatic split would draw a different holdout
   from the bigger pool, and a CER change could then be data *or* easier people.

### Step 1 — upload the new trainer (~3 min)

`kaggle.com/datasets/mohammedsalim1/deafference-fs-code` → **⋮ → New Version** → drag
`training/fingerspelling/train_ctc.py` → confirm `subset_landmarks.py` is still listed →
notes `charset from competition + --val-signers` → **Create**.

### Step 2 — the subset, on CPU (~80 min, zero GPU quota)

New notebook **`deafference-fs-subset-16`**. **Accelerator: None.** Attach the **competition**
and **`deafference-fs-code`**.

```python
import glob, os
BASE = os.path.dirname(glob.glob('/kaggle/input/**/train_landmarks', recursive=True)[0])
CODE = os.path.dirname(glob.glob('/kaggle/input/**/subset_landmarks.py', recursive=True)[0])
print('BASE =', BASE, '\nCODE =', CODE)
```

```python
!python {CODE}/subset_landmarks.py --base {BASE} --out /kaggle/working --limit-files 16
!ls -la /kaggle/working
```

Then **Save Version → Save & Run All (Commit)**, or `/kaggle/working` dies with the session.

Expect `~15,988 sequences · ~2,543,000 frames · ~2.2 GB`. Peak RAM ~4.6 GB (the concatenate
holds the list and the result at once) against ~30 GB on CPU — comfortable.

### Step 3 — promote to a **Private** dataset (~5 min)

Output tab → **⋮ → New Dataset** → title **`deafference-fs75-16`** → **Private** → Create.
**A brand-new name — never onto `deafference-fs75`.** Keep the 4-shard dataset; it is the
baseline.

### Step 4 — train (~1.6 h GPU)

New notebook **`deafference-fs-ctc-16`**. **Accelerator: GPU P100.**
Attach **`deafference-fs75-16`**, **`deafference-fs-code`**, and **the competition**.
**Do NOT attach `deafference-fs75`.**

```python
# cell 1 — go/no-go. Refuses if two fs75.npz are mounted (trap 2).
import glob, os
import tensorflow as tf

npz  = sorted(glob.glob('/kaggle/input/**/fs75.npz',     recursive=True))
code = glob.glob('/kaggle/input/**/train_ctc.py',        recursive=True)
chs  = glob.glob('/kaggle/input/**/character_to_prediction_index.json', recursive=True)
gpus = tf.config.list_physical_devices('GPU')

for p in npz: print(f'  fs75.npz  {os.path.getsize(p)/1e6:>7.0f} MB   {p}')
assert len(npz) == 1, 'detach deafference-fs75 — the 4-shard npz would win the glob'
assert os.path.getsize(npz[0]) > 1.5e9, 'that is the 4-shard file; expected ~2.2 GB'
assert code, 'train_ctc.py MISSING'
assert chs,  'competition NOT attached — the charset would be shard-derived'
assert gpus, 'no GPU — Settings > Accelerator'
NPZ, CODE = npz[0], os.path.dirname(code[0])
print('\nNPZ  =', NPZ, '\nCODE =', CODE, '\nGPU  =', gpus)
```

```python
# cell 2 — selftest: 35 checks, ~30 s. If it fails, stop.
!python {CODE}/train_ctc.py --selftest
```

```python
# cell 3 — the run. The pinned signers are the 4-shard holdout, so the ONLY variable is data.
!python {CODE}/train_ctc.py --npz {NPZ} --out /kaggle/working/fs_out --epochs 25 \
    --val-signers 1,15,56,73,89,128,147,154,158,161,196,203,225
```

Then **Save & Run All (Commit)**.

### What to expect, and why

| line | expected | why |
|---|---|---|
| `[charset] source:` | ends `character_to_prediction_index.json` | competition attached |
| `[charset] 59 characters -> 60 classes` | **60**, not 52 | the corpus charset, not the shard one |
| `[split] val signers PINNED to 13 of 13` | 13 | trap 3 avoided |
| `[filter] kept` | ~86% | 86.51% at 4 shards |
| `[mem] released ~2.3 GB` | ~2.3 GB | the `frames` free |
| `[ep 1] ... | ~230s` | ~4 min/epoch | 58 s at 4 shards × 4 |

**CER should leave 1.0 far earlier than epoch 13.** The all-blank phase is measured in
*optimizer steps*, and 4× data is 4× steps per epoch — so expect the crack around **epoch
3–5** and the cliff by **7–8**. **If CER is still 1.000 at epoch 10, stop and tell me** — that
would mean the phase is not step-bound and my reasoning is wrong.

**Read `val_loss`, not `val_cer`, for the stopping point** — that is the epoch-23 lesson.
25 epochs here ≈ 2.5× the optimizer steps of the 40-epoch 4-shard run.

**The number to beat is `best_val_cer` 0.4703**, on the same 13 people.

---

## Ordering, if you only have one session

1. **Part 1** — promote `fs75.npz` (10 min, and nothing else can start without it)
2. **Part 2** — upload `train_ctc.py` (3 min)
3. **Part 3 cell 2** — the selftest (30 s; it is the go/no-go)
4. **Part 3 cell 3** — Save & Run All and walk away (3–5 h)

Parts 4a and 4b need no Kaggle session at all.
