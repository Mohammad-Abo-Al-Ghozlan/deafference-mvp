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

**New notebook. Accelerator: GPU** (T4 ×2 or P100, either is fine).
**Add data:** `deafference-fs75` **and** `deafference-fs-code`.

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

### What good looks like, and what to stop for

```
[charset]  ~59 characters -> 60 classes with blank
[filter]   kept ~86% of sequences        <- 3462/3997 is the expected figure
[split]    train ~85% / val ~15%, NO shared signer
           hand_rate train ~0.57  val ~0.57   <- close, because it is stratified
[model]    ~2-4M params
[ep   1]   train 40-90 | val ... CER 0.9-1.0     <- CER near 1.0 at first is NORMAL
[ep  10]   CER should be clearly under 0.9
[ep  40]   a first baseline in the 0.3-0.6 CER band is a real result
```

**Stop the run and tell me if you see any of these:**

| symptom | what it means |
|---|---|
| `⚠ N non-finite` on any epoch | a row slipped the feasibility filter — a real bug, I want the number |
| `[filter] kept` below ~80% | the charset or the lengths are not what we measured |
| `SIGNER LEAK` assertion | the split broke; the number would be meaningless |
| CER flat at 1.000 past epoch 10 | not learning — send me `history.json` |
| val CER falling then rising | overfitting; we cut epochs or raise dropout |

### What to send me

`/kaggle/working/fs_out/report.json` — it carries the history, the per-signer CER, the filter
breakdown and the val signer list. That one file is enough; don't bother with the weights yet.

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

## Ordering, if you only have one session

1. **Part 1** — promote `fs75.npz` (10 min, and nothing else can start without it)
2. **Part 2** — upload `train_ctc.py` (3 min)
3. **Part 3 cell 2** — the selftest (30 s; it is the go/no-go)
4. **Part 3 cell 3** — Save & Run All and walk away (3–5 h)

Parts 4a and 4b need no Kaggle session at all.
