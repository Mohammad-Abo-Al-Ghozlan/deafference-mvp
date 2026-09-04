# Fingerspelling CTC baseline — the first run, measured

> ## ✅ RUN 2 · 2026-09-05 · 16 shards · **CER 0.4703 → 0.3730**
>
> **The data hypothesis is confirmed, and it was a controlled experiment.** Same 13 held-out
> signers (`val_signers_pinned: true`), same architecture to within **1,544 params** — which
> is exactly `8 extra classes × (192 dim + 1 bias)`, i.e. the charset fix and nothing else,
> 0.1% of the model. One variable: **4× the training data.**
>
> ```
> best val CER   0.4703 -> 0.3730    -0.0973   (-20.7% relative)
> exact phrase   0.0174 -> 0.0445    2.6x
> n_train         2,999 -> 11,924    n_val 459 -> 1,844 (same PEOPLE, more clips each)
> n_classes          52 -> 60        charset from the competition file ✅
> non-finite          0 -> 0         the length guard held again
> ```
>
> **The 16-shard set provably contains the 4-shard set** — the subset log's 4th shard reads
> `3,997 sequences, 635,755 frames`, identical to the first run's totals to the digit, because
> `--limit-files N` takes the first N of a *sorted* list.
>
> **All 13 signers improved**, mean **−0.0953** (sd 0.032, range −0.023 … −0.135). No signer
> regressed, so this is not a lucky draw.
>
> ### The equity picture, read carefully
>
> The **ratio** widened 2.77× → 3.06×, which looks like bad news and is not the right
> statistic. `corr(old CER, absolute gain) = −0.547`: **harder signers gained *more* in
> absolute CER**, so the absolute gap **narrowed** 0.4399 → 0.3945. A ratio widens whenever
> near-equal absolute gains land on unequal bases.
>
> **What actually binds is the floor, and it is unmoved in kind:** p203 went from 31% to
> **41% of characters right**, p161 from 70% to **81%**. Another 4× data would put p203 near
> 50%. **Data alone will not make the worst-served signer usable** — the same conclusion the
> 250-word model reached when an oracle per-signer mean-shift moved its worst signer −0.0018.
>
> ### The filter scaled linearly — except the repeat rule
>
> ```
> fewer hand-frames than chars    367 -> 1497   x4.1
> T_out < phrase_len              170 ->  701   x4.1
> ONLY repeated characters          2 ->   15   x7.5   <- linear would be x4.0
> kept                                  86.15%  (was 86.51%)
> ```
> 15 rows at ~7.5× rather than 4× is about 2.5σ on Poisson counts this small, so treat it as
> noise around a real effect — but the correction that "earned 2 rows" now earns 15, each of
> which would have carried ~90× the gradient of a real sample.
>
> ### Next: 34 shards, predicted **0.320**
>
> One observation gives **−0.0487 CER per doubling of data**. Extrapolated: 34 shards → 0.320,
> 68 → 0.272. Weak (n=1) but testable. **34 shards peaks at 7.03 GB and is safe; 68 peaks at
> 14.07 GB against a Kaggle GPU notebook's ~13 GB and still OOMs.**
>
> Going past 34 needs `subset_landmarks.py` to write `frames.npy` *separately* from the
> metadata, so the trainer can `np.load(..., mmap_mode="r")` and never make the raw landmarks
> resident. `np.load` cannot mmap a member of an `.npz`. That is the one blocking change for
> the full corpus, and it is small.



**Run 2026-09-04.** `train_ctc.py --epochs 40` on `fs75.npz` (4 of 68 shards). Source of every
number below: `report.txt` at the repo root, the run's own `report.json`.

```
best val CER   0.4703   (epoch 39)     ·   final 0.4773 (epoch 40)
exact phrase   0.0174                  ·   n = 459 held-out sequences, 13 unseen signers
non-finite     0   in all 40 epochs, train AND val
wall time      39 min   (58 s/epoch)
params         1,340,980
```

**This is a real baseline.** It landed inside the 0.3–0.6 CER band the runbook called a result,
on **2.9% of the available data**, in 39 minutes.

---

## 1. The guard held. That is the headline, not the CER.

**`nonfinite_train` and `nonfinite_val` are 0 on every one of the 40 epochs.** The whole reason
`train_ctc.py` exists rather than a stock CTC recipe is that `tf.nn.ctc_loss` returns **~707,
finite**, for an infeasible row instead of `-inf` — so `is_finite()` never fires and those rows
contribute ~70–90× the gradient of a real sample, invisibly. The length-based filter caught all
of them before epoch 1 and nothing leaked afterwards.

### What each of the three corrections actually bought

| correction | rows it saved | verdict |
|---|---|---|
| **filter at the MODEL's stride**, not raw `T` | **40** (170 at stride 2 vs 130 at stride 1) | the big one — filtering raw `T` would have poisoned 40 rows |
| **`T_out >= L + adjacent_repeats`** | **2** | real, and honestly tiny. 2 rows in 3,997 |
| guard by **length**, not `is_finite` | all 539 | without it none of the above is detectable |

The repeat rule earning 2 rows is worth stating plainly: it was the correction I spent the most
words on and it is the smallest of the three. It is still right — those 2 rows would each have
carried ~90× weight — but the stride correction is the one that mattered.

### The filter matched the prediction almost exactly

```
kept 3,458 / 3,997 = 86.51%          predicted 86.6%   (3462/3997)
  367  fewer hand-frames than characters
  170  T_out < phrase_len
    2  infeasible ONLY because of repeated characters
```

---

## 2. 🔴 The charset was wrong, and it is the medical vocab trap again

**`n_classes: 52`.** I predicted ~60. The corpus has **59 characters**; four shards contain
**51**.

`build_charset()` was `sorted({c for p in phrases for c in p})` over the *attached* shards.
Because it sorts the observed **set**, adding shards does not append the eight missing
characters — it **inserts** them and shifts the index of nearly every character after each
insertion point. Two silent consequences:

- a 4-shard model and a 68-shard model **share no label space**, so their CER numbers are not
  comparable; and
- loading one run's `charset.json` against the other's weights **remaps every character**.

`build_charset`'s own docstring warned about exactly this hazard while creating it. This run's
numbers are internally valid — one charset, start to finish — but **its `charset.json` must not
be carried to any run with a different shard mix.**

**Fixed** (`de7504e`): `load_charset()` prefers the competition's own
`character_to_prediction_index.json` (59 characters), auto-detected under `/kaggle/input` and
overridable with `--charset`; the fallback prints a five-line warning and records
`charset_source` in both `charset.json` and `report.json`; and `train()` now **aborts** if any
character in the data is missing from the charset, because `encode()` silently drops unknowns
and would train against a truncated phrase. A selftest check demonstrates the reindex directly.

> **So attach the competition to the training notebook.** I earlier suggested detaching it as
> optional cleanup — that was wrong for this reason. It is where the canonical charset lives.

---

## 3. The learning curve: 12 epochs of nothing, then a cliff

```
ep  1-12   val CER exactly 1.0000     train loss 84.9 -> 24.3
ep 13      0.9996                     <- first crack
ep 17      0.9200
ep 19      0.7776                     <- the cliff. val loss 94.9 -> 70.1
ep 22      0.5506
ep 25      0.4960
ep 27      0.4738
ep 39      0.4703                     <- best
```

**CER pinned at exactly 1.0 for 12 epochs while train loss fell 3.5× is normal CTC behaviour,
not a broken run** — the model first learns to emit all-blank (which deletes everything, CER
1.0), and only then learns to emit characters. The runbook's "CER should be clearly under 0.9
by epoch 10" was **too optimistic**: it crossed 0.9 at epoch **19**. Anyone watching epoch 10
under the old guidance would have killed a run that was about to work.

---

## 4. 🔴 It overfits from epoch 23 — and CER hid it completely

| | epoch 23 | epoch 40 | |
|---|---|---|---|
| **val loss** | **48.67** ← minimum | **67.58** | **+39%** |
| train loss | 11.81 | 4.93 | 2.40× **lower** |
| val CER | 0.5226 | 0.4773 | still improving |

Train loss halving while val loss rises 39% is textbook memorisation. **CER did not show it** —
it drifted only 0.0151 across epochs 27–40 and its best value is epoch 39, the second-to-last.
Greedy CTC decode is robust to confidence miscalibration, so the argmax path stays roughly right
while the probabilities rot.

**Consequence for the runbook:** "val CER falling then rising → overfitting" is the wrong
instrument. **Watch `val_loss`.** On this run CER would have told you to train longer and the
loss would have told you to stop 17 epochs earlier.

---

## 5. Per-signer CER — 2.77× spread, and the pooled number lies

```
p89    0.2481  ############
p161   0.2964  ##############
p147   0.4107  ####################
p196   0.4170  ####################
p154   0.4735  #######################
p73    0.4741  #######################
p225   0.4907  ########################
p15    0.5109  #########################
p158   0.5480  ###########################
p56    0.5905  #############################
p128   0.6343  ###############################
p1     0.6864  ##################################
p203   0.6880  ##################################
```

**Pooled 0.4773 hides p203 at 0.6880.** For that signer roughly 31% of characters survive,
against ~75% for p89.

This is the **third independent corpus** in which this project has measured a large per-signer
spread: the 250-word model spanned 0.31–0.82 accuracy (2.65×), the fingerspelling *tracking*
rate spans 6.78× between signers, and now the CER of a completely different architecture on a
different corpus spans 2.77×. On the 250-word model an oracle per-signer mean-shift moved the
worst signer by **−0.0018**, i.e. it was not correctable downstream. Treat per-signer reporting
as load-bearing, not a courtesy.

The split held: 13 val signers, **zero shared with train**, 459 sequences (13.3% against a 15%
target — signer-disjointness quantises the split).

---

## 6. Two of my own estimates were wrong

| I said | actual | note |
|---|---|---|
| `~59 characters -> 60 classes` | **52 classes** | the charset bug above |
| `~2-4M params` | **1.34M** | below the band I gave |
| `~3-5 h GPU` | **39 min** | **6× too high**, and it changes the plan |
| CER `< 0.9` by epoch 10 | epoch **19** | would have killed a working run |
| `kept ~86.6%` | **86.51%** | correct |
| CER `0.3-0.6` is a real result | **0.4703** | correct |

The runtime miss is the useful one: at 58 s/epoch, scaling the data is affordable.

---

## 7. What to do next — more data, and the evidence says so

The model overfits at **3,458 sequences with 1.34M params**. That is a data-starvation
signature, not an architecture problem. Do **not** tune the model yet. Available: 67,208 train
+ 52,958 supplemental sequences — this run used **2.9%** of the train split alone.

### Go to 16 shards, not 68

| shards | seqs | peak host RAM | GPU h (25 ep) | |
|---|---|---|---|---|
| 4 (this run) | 3,997 | 0.83 GB | 0.4 | done |
| **16** | **15,988** | **3.32 GB** | **1.6** | ← **next** |
| 34 | 33,974 | 7.05 GB | 3.4 | fine |
| 68 | 67,949 | **14.09 GB** | 6.8 | **OOMs a Kaggle GPU notebook (~13 GB)** |

**68 shards in one bite would run out of host RAM**, and it would do so *after* a ~6-hour CPU
subset job. 16 shards is 4× the data, costs ~1.6 h of the 30 h weekly quota, and needs no memory
engineering. It answers the only question that matters right now — *does CER fall with data?* —
for about 5% of the budget.

`frames` is now freed after the feature pass (`de7504e`), which drops steady-state RAM during
training from ~14 GB to ~4.4 GB at 68 shards. The remaining 14.1 GB **peak** is the feature pass
itself holding both arrays at once; going past ~34 shards needs `subset_landmarks.py` to write
features instead of raw landmarks, or a float16 frame store. Not needed yet.

### The next run, concretely

1. **CPU** notebook, competition + `deafference-fs-code`, `--limit-files 16` → ~80 min, free
2. promote to a new **Private** dataset `deafference-fs75-16` (brand-new name)
3. **GPU** notebook, attach **the competition too** — that is where the 59-character charset is
4. `--epochs 25`; check `report.json` for `"charset_source"` ending in
   `character_to_prediction_index.json` and `"n_classes": 60`
5. compare against **0.4703**, and read `val_loss` for the stopping point, not `val_cer`

**If CER falls materially at 4× data, the answer is more shards and the architecture is fine.
If it barely moves, the architecture is the constraint and that is when tuning earns its keep.**
