# Finish the 250-word model → live demo (COMPLETE runbook, v2)

## 0. The aim (why we're doing this)
**Deafference** is a two-way sign-language ↔ speech accessibility product. The current
milestone is the **250-word ASL recognition model** that powers the live demo
(`live_demo.py`) — camera → landmarks → this model → recognized words → AI sentence →
speech. Phase 2 is Lebanese Sign Language (the real moat). Recognition runs
**client-side** (biometric data never leaves the device).

**This task:** push the 250-word model's held-out **TEST accuracy** from the current
best **0.7576** toward **0.82–0.85** (honest range), so the demo recognizes 250 signs
reliably. We do it with a properly-engineered `train.py` + a 5-fold ensemble.

---

## 1. What changed in `train.py` (already applied + syntax-checked)
A multi-agent design pass + adversarial verification produced these. **The safe stack
is ON by default; two levers are gated OFF.**

**On by default (the "safe stack"):**
1. **LR warmup** before cosine decay — makes the never-run from-scratch recipe stable.
2. **Gradient clipping** (`global_clipnorm=1.0`) — no loss spikes on the long run.
3. **Hand-shape distance + velocity features** in `PreprocessLayer` — +200
   rotation/mirror-invariant features (per-hand joint distances AND their
   d/dt). *Highest-confidence lever; velocity targets the confusable tail.*
4. **Mean+Max pooling** head (was mean-only) — keeps the peak-handshape frame.
5. **EMA** (weight averaging), model-selected on validation, graph-fused, and
   **resume-safe** (state persisted so a disconnect can't lose the best weights).
6. **Tighter temporal resample** (0.7–1.4×) — less train/inference motion mismatch.

*(A second adversarial review of the composed file caught + fixed: EMA-on-resume,
`--mixup` .keras save, SavedModel fallback signature, misleading mixup metric. The
model was then built + forward-passed on the real TF 2.17 stack — output [*,250], all
finite — so it's verified, not just syntax-checked.)*

**Gated OFF (opt-in only, for step 4):**
7. `--mixup` — manifold mixup at the pooled embedding (regularizer; validate on 1 fold).
8. `--late-dropout X` — A/B the dropout (default 0.7).

**Deferred (NOT applied):** the AWP rewrite — its verifier crashed and it's high-risk;
not needed to hit target.

> ⚠️ **The architecture changed (feature dim 450→550, pool width doubled).** So the OLD
> `weights_all250_fold0` (0.7576) and the old backbone **cannot be loaded into the new
> model** and are **not** part of the new ensemble. 0.7576 is now just the **number to
> beat**. We train a clean-slate 5-fold from-scratch set (NO `--init-from`).

---

## 2. CRITICAL first action — re-upload the new `train.py` to Kaggle
Your Kaggle Dataset `asl250-weights` still has the OLD `train.py`. **Replace it:**
1. kaggle.com → your dataset **asl250-weights** → **New Version** (or ⋮ → Update).
2. Remove the old `train.py`, drag in the new one from
   `Deafference\training\train.py`, and **Create Version**.
3. (Leave `backbone_250.weights.h5` and the old fold-0 weights — harmless; we just
   won't use them.)

*(You do NOT need to re-upload the weights. We're training fresh.)*

---

## 3. The step-by-step (each STEP = do it, then tell me the result)

> ### ⚠️ 2026-08-13 — STEP 1's rehydrate cell is superseded for any masking run
>
> STEP 1 below copies `train.py` from the **`asl250-weights`** dataset. That dataset has no
> `sign_landmarks.py`, and `--mask-resting-hand` cannot run without it — the flag refuses
> rather than silently no-op. Use the cell in **§3.0** instead. STEP 1 is still correct for a
> plain unmasked run.

### 3.0 Rehydrate for a masking run — code from `asl250-code-v*`

Selecting the code dataset by filename is not enough. An **output** dataset from a previous
run (e.g. `asl250-armab-v1`) is a snapshot of `/kaggle/working`, so it carries its own
`train.py` and `sign_landmarks.py`. Both directories look like "the code"; only one has the
mask. And you need the old output attached anyway, to read the baseline's config. So select on
**version markers** and print what was rejected:

```python
import os, glob
os.environ["TF_USE_LEGACY_KERAS"] = "1"
!pip -q install tf-keras awscli
from kaggle_secrets import UserSecretsClient
us = UserSecretsClient()
os.environ["AWS_ACCESS_KEY_ID"]     = us.get_secret("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = us.get_secret("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"

TRAIN_MARKS = ("mask_resting_hand", "scan_resting_hands", "apply_resting_mask",
               "canonicalize_missing(a)")   # last one = the 2026-08-13 sentinel fix
SL_MARKS    = ("hand_arm_alignment", "canonicalize_missing")

def missing_marks(d):
    try:
        t = open(os.path.join(d, "train.py"), encoding="utf-8").read()
        s = open(os.path.join(d, "sign_landmarks.py"), encoding="utf-8").read()
    except OSError:
        return None
    return [m for m in TRAIN_MARKS if m not in t] + [m for m in SL_MARKS if m not in s]

cands = sorted({os.path.dirname(p) for p in glob.glob("/kaggle/input/**/train.py", recursive=True)
                if os.path.exists(os.path.join(os.path.dirname(p), "sign_landmarks.py"))})
good = []
for d in cands:
    miss = missing_marks(d)
    if miss == []:
        good.append(d); print(f"  [current] {d}")
    else:
        print(f"  [reject ] {d}  missing {miss}")
assert len(good) == 1, (
    f"need exactly 1 CURRENT code dataset, found {len(good)}. Attach the newest "
    f"asl250-code-v* — train.py must contain 'canonicalize_missing(a)'.")
C = good[0]

!cp {C}/train.py {C}/sign_landmarks.py .
!mkdir -p data
!aws s3 cp   s3://asl-mvp-dataset/splits/split_manifest.parquet data/split_manifest.parquet
!aws s3 sync s3://asl-mvp-dataset/preprocessed/by_word data/by_word --quiet
print("\ntrain.py:", os.path.exists("train.py"),
      "| sign_landmarks.py:", os.path.exists("sign_landmarks.py"),
      "| data:", os.path.exists("data/by_word"))
```

**If BOTH datasets are rejected for `canonicalize_missing(a)`**, the attached code predates the
sentinel fix. Re-upload `asl250_code.zip` and attach the new version. Do not work around the
assertion: without that line the mask decision is a constant (`block="L"` for every clip) and
the run would mask nearly the whole corpus while printing a believable percentage.

**Why the marker list ends with `canonicalize_missing(a)`:** the corpus stores a missing
landmark as exact `0.0`, `np.isfinite(0.0)` is `True`, and `hand_arm_alignment` is NaN-based.
An intermediate upload with the flag but not the conversion looks identical from the outside.
A marker list that every past revision also satisfies cannot detect a stale stage.

### STEP 1 — new Kaggle session + rehydrate  *(unmasked runs only — see §3.0)*
New notebook (or reopen), **GPU T4 x2** + **Internet On**, dataset attached, secrets set.
Run this cell (fixes the dataset path we found, and re-syncs data):
```python
import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"
!pip -q install tf-keras awscli
from kaggle_secrets import UserSecretsClient
us = UserSecretsClient()
os.environ["AWS_ACCESS_KEY_ID"]     = us.get_secret("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = us.get_secret("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"]    = "eu-north-1"

D = "/kaggle/input/datasets/mohammedsalim1/asl250-weights"   # verify with !ls /kaggle/input
!cp {D}/train.py .
!mkdir -p data
!aws s3 cp   s3://asl-mvp-dataset/splits/split_manifest.parquet data/split_manifest.parquet
!aws s3 sync s3://asl-mvp-dataset/preprocessed/by_word          data/by_word --quiet
print("train.py:", os.path.exists("train.py"), "| data:", os.path.exists("data/by_word"))
```
Expect both `True`. If the path is wrong, run `!ls -R /kaggle/input/ | head` and fix `D`.

### STEP 2 — VALIDATE the recipe on ONE from-scratch fold (~2–2.5 h)
This is the make-or-break gate. **No `--init-from` = from scratch.**
```python
!TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 0 \
  --epochs 200 --lr 4e-4 --seed 42 --out-dir /kaggle/working/asl250_scratch
```
**What to watch (this looks DIFFERENT from before):**
- First ~10 epochs = **warmup**: LR ramps up; loss should fall steadily, **no NaN**.
- val_acc **starts LOW (~0.2–0.4) and CLIMBS** over dozens of epochs — from-scratch is
  supposed to look like this. Don't panic.
- It early-stops when val plateaus (likely epoch ~80–130).
- **To avoid losing it to a disconnect: use "Save Version → Save & Run All"** so Kaggle
  runs it detached and keeps `/kaggle/working`. (Or keep the tab active.)

### STEP 3 — score that one fold on TEST (vs 0.7576)
```python
%%writefile eval_one.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS","1")
import sys; sys.path.insert(0,".")
import glob, numpy as np
from pathlib import Path
import tensorflow as tf
from train import build_model, load_vocab, load_dataset, make_tf_dataset
data=Path("data"); vocab=load_vocab(all_words=True,data_dir=data); words=vocab["words"]
man,arrays=load_dataset(data,vocab)
ev=man[(man["split"]=="test")&(~man["is_outlier"])].reset_index(drop=True)
ds=make_tf_dataset(ev,arrays,len(words),training=False); y=ev["y"].to_numpy()
wf=sorted(glob.glob("/kaggle/working/asl250_scratch/weights_all250_fold0_seed42.weights.h5"))[0]
m=build_model(num_classes=len(words)); m.load_weights(wf)
p=tf.nn.softmax(m.predict(ds,verbose=0),axis=1).numpy()
print(">> proper build? classifier:", any("classifier" in w.name for w in m.weights))
print("FROM-SCRATCH fold-0 TEST acc: %.4f   (beat 0.7576?)" % float((p.argmax(1)==y).mean()))
```
```python
!TF_USE_LEGACY_KERAS=1 python eval_one.py
```
**GO / NO-GO:**
- **≥ ~0.78** → the recipe works, go to STEP 4.
- **~0.76 or below the 0.726 backbone** → something regressed; tell me the number and
  we debug (likely feature-dim or pooling). Don't spend the budget yet.

### STEP 4 — train folds 1–4 (same command, change `--fold`)
```python
!TF_USE_LEGACY_KERAS=1 python train.py --data-dir data --all-words --fold 1 \
  --epochs 200 --lr 4e-4 --seed 42 --out-dir /kaggle/working/asl250_scratch
```
Repeat for `--fold 2`, `3`, `4`. Each ~2–2.5 h; all land in the same folder.
**Save/download after each** (Save Version, or the zip in STEP 7).

### STEP 5 — the ensemble (this is the big lever: +2–4%)
```python
%%writefile ensemble_eval_250.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS","1")
import sys; sys.path.insert(0,".")
import re, glob, json, numpy as np
from pathlib import Path
import tensorflow as tf
from train import build_model, load_vocab, load_dataset, make_tf_dataset

DATA=Path("data"); OUT="/kaggle/working/asl250_scratch"
TTA=4; CALIBRATE=True
vocab=load_vocab(all_words=True,data_dir=DATA); words=vocab["words"]; C=len(words)
man,arrays=load_dataset(DATA,vocab)
ev=man[(man["split"]=="test")&(~man["is_outlier"])].reset_index(drop=True); y=ev["y"].to_numpy()

def crop_affine(a,rng):
    if a.shape[0]>12:
        keep=rng.uniform(0.85,1.0); w=max(8,int(a.shape[0]*keep))
        s=int(rng.integers(0,a.shape[0]-w+1)); a=a[s:s+w]
    th=np.deg2rad(rng.uniform(-8,8)); sc=rng.uniform(0.95,1.05)
    R=np.array([[np.cos(th),-np.sin(th)],[np.sin(th),np.cos(th)]],np.float32)*sc
    return np.concatenate([a[...,:2]@R.T, a[...,2:]],-1)

def fit_T(logits,yt):
    lT=tf.Variable(0.0,dtype=tf.float32); lg=tf.constant(logits,tf.float32); yy=tf.constant(yt.astype(np.int32))
    opt=tf.optimizers.Adam(0.05)
    for _ in range(300):
        with tf.GradientTape() as tp:
            loss=tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(yy, lg/tf.exp(lT)))
        opt.apply_gradients(zip(tp.gradient(loss,[lT]),[lT]))
    return float(tf.exp(lT).numpy())

folds=sorted(glob.glob(OUT+"/weights_all250_fold*_seed*.weights.h5"))
print("members:",[Path(f).name for f in folds])
m=build_model(num_classes=C); psum=None
for wf in folds:
    m.load_weights(wf); T=1.0
    if CALIBRATE:
        g=re.search(r"fold(\d+)",Path(wf).name)
        if g:
            k=int(g.group(1)); valk=man[(man["split"]=="cv")&(man["fold"]==k)&(~man["is_outlier"])]
            vds=make_tf_dataset(valk,arrays,C,training=False)
            T=fit_T(m.predict(vds,verbose=0), valk["y"].to_numpy())
    ds=make_tf_dataset(ev,arrays,C,training=False)
    P=tf.nn.softmax(m.predict(ds,verbose=0)/T,axis=1).numpy()
    if TTA:
        rng=np.random.default_rng(0)
        for _ in range(TTA):
            view={k:crop_affine(arrays[k],rng) for k in ev["key"]}
            dv=make_tf_dataset(ev,{**arrays,**view},C,training=False)
            P=P+tf.nn.softmax(m.predict(dv,verbose=0)/T,axis=1).numpy()
        P=P/(TTA+1)
    print("  %-42s T=%.2f acc %.4f"%(Path(wf).name,T,float((P.argmax(1)==y).mean())))
    psum=P if psum is None else psum+P
ens=psum/len(folds); acc=float((ens.argmax(1)==y).mean())
per={words[c]:float((ens.argmax(1)[y==c]==c).mean()) for c in np.unique(y)}
print("=== ENSEMBLE (%d) TEST: %.4f ==="%(len(folds),acc))
print("worst 20:",[(w,round(per[w],2)) for w in sorted(per,key=per.get)[:20]])
json.dump({"ensemble_acc":acc,"n":len(folds),"per_word":per},open(OUT+"/ensemble_eval_250.json","w"),indent=2)
```
```python
!TF_USE_LEGACY_KERAS=1 python ensemble_eval_250.py
```
**Read the `=== ENSEMBLE … TEST ===` line — that's your headline number vs 0.7576.**
- ≥ 0.82 → 🎉 go to STEP 6.
- 0.79–0.81 → optionally STEP 4b (gated levers) for the last point.

### STEP 4b (only if short of target) — the gated levers, one at a time
- **Late-dropout A/B** (cheap): rerun fold 0 with `--late-dropout 0.5` and `0.8`, keep best.
- **Mixup** (validate first): `... --fold 0 --mixup ...`; if TEST ≥ your STEP-3 number
  and ≥10 stable epochs, retrain 1–4 with `--mixup` and re-ensemble.

### STEP 6 — freeze vocab + export SavedModels
```python
%%writefile finalize_250.py
import os; os.environ.setdefault("TF_USE_LEGACY_KERAS","1")
import sys; sys.path.insert(0,".")
import json, glob, re
import tensorflow as tf
from pathlib import Path
from train import build_model, load_vocab
data=Path("data"); vocab=load_vocab(all_words=True,data_dir=data); words=vocab["words"]
OUT="/kaggle/working/asl250_scratch"
json.dump({"vocab_version":"v1-all250","num_classes":len(words),
           "words":words,"word_to_index":vocab["word_to_index"]},
          open(OUT+"/vocab_250.json","w"),indent=2)
print("froze vocab_250.json:",len(words),"words")
for wf in sorted(glob.glob(OUT+"/weights_all250_fold*_seed*.weights.h5")):
    n=re.search(r"fold(\d+)",wf).group(1)
    m=build_model(num_classes=len(words)); m.load_weights(wf)
    d=f"{OUT}/savedmodel_fold{n}"
    try: m.export(d)
    except AttributeError: tf.saved_model.save(m,d)
    print("exported",d)
```
```python
!TF_USE_LEGACY_KERAS=1 python finalize_250.py
```

### STEP 7 — download everything
```python
!cd /kaggle/working && zip -r asl250_final.zip asl250_scratch -x "*/backup_*" "*/ema_*" >/dev/null && ls -lh asl250_final.zip
```
Download `asl250_final.zip` (Output panel → ⋮ → Download). Extract into the repo as
`artifacts_250/` (should contain `savedmodel_fold*/`, `vocab_250.json`, `ensemble_eval_250.json`).

### STEP 8 — wire into the demo + test (Claude does the code)
1. I add a `--vocab250` flag to `live_demo.py` (points at `artifacts_250`).
2. `python live_demo.py --vocab250 --selftest` → expect output shape `[250]`.
3. `python live_demo.py --vocab250 --ai` → live camera, 250 words, AI sentences.

---

## 4. Rules that keep biting us (don't skip)
- **Re-upload the NEW train.py** to the Kaggle Dataset (section 2) — the old one is stale.
- **From-scratch = NO `--init-from`.** val starts low and climbs; that's correct.
- **Run everything as `!TF_USE_LEGACY_KERAS=1 python …`** (subprocess). If eval reads
  ~0.004, you built in a notebook cell.
- **Save/download after each fold** (Save Version or STEP 7 zip) — `/kaggle/working` wipes.
- **Old fold-0 (0.7576) and old backbone are NOT reusable** with the new architecture —
  they're just the baseline to beat.
- **Rotate the AWS key** you pasted in chat (IAM → new key) once done.

## 5. Deliverables
- [ ] New `train.py` uploaded to Kaggle Dataset
- [ ] From-scratch fold-0 TEST ≥ ~0.78 (STEP 3 gate)
- [ ] 5 from-scratch folds trained
- [ ] `ensemble_eval_250.json` TEST ≥ 0.82
- [ ] `vocab_250.json` + `artifacts_250/savedmodel_fold*/` on Windows
- [ ] `live_demo.py --vocab250` recognizes 250 words live
