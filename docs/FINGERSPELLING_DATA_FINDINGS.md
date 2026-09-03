# Fingerspelling — what the data actually is, and what it forces

**Measured 2026-09-03** from `gap_stats.json`, produced by `training/fingerspelling/subset_landmarks.py`
on the first **4 of 68** shards of the Google ASL Fingerspelling competition corpus.

```
3,997 sequences · 635,755 frames · 92 of 94 participants · 547 MB subsetted
--selftest: ALL CHECKS PASSED  (all 75x3 landmark slots, dominant-hand detection, gap counting)
```

Four shards is 5.9% of the corpus by shard count, so treat proportions as reliable and absolute
counts as one-seventeenth of the whole. Every number below is measured, not estimated.

---

## The seven findings, in order of how much they change what we build

### 1. 🔴 130 sequences will make the CTC loss NaN. Drop them before the first training run.

**`T < phrase_len` in 130 sequences (3.25%).** A CTC model cannot emit more labels than it has
timesteps — the loss is `-inf`, and in practice the run dies or silently produces `nan` gradients.

```
T:           median 6    max 17        <- frames
phrase_len:  median 16   max 30        <- characters to emit
worst case:  T=2, phrase_len=16
```

**Dropping them costs almost nothing: 3.25% of sequences but 0.14% of frames.** These are truncated
recordings, not hard examples.

**And it is not one bad signer.** They spread across **52 of 92** participants, with the top six
holding only 33%. So this is a general property of the corpus — a filter, not a blacklist.

> **This is the single most actionable finding in this document.** It is a crash, it is cheap to
> prevent, and it would have been diagnosed as a model bug.

### 2. Absence must be a first-class input. Interpolation is not defensible here.

```
dominant-hand presence   mean 0.553   median 0.571   p10 0.149
max interior gap         median 16    p90 52         max 270
sequences with a gap >10 frames        64%
gaps are interior        lead==0 in 95.1%   trail==0 in 98.0%
```

**The median sequence has a 16-frame hole — about 0.53 s at 30 fps.** In fingerspelling that is
several letters. Filling it does not recover a letter; it **invents** one.

The gaps are interior (95% have no leading gap, 98% no trailing), so trimming buys nothing. This
closes the question the task list called open: the model learns *"no hand here"* rather than being
fed a fabricated hand. The script's own warning is correct as written.

### 3. 🔴 Shards do not partition signers. A shard-based train/val split leaks.

**92 of the corpus's 94 participants appear in just these 4 shards.** So shard boundaries carry no
signer information at all, and the obvious split — "train on shards 1–60, validate on 61–68" —
**puts the same signers on both sides.**

That matters more here than it would elsewhere. On the 250-word model, per-signer accuracy ranged
**0.31 to 0.82**, and an oracle per-signer mean-shift moved the worst signer by **−0.0018** — i.e.
the spread was real and *not* correctable downstream. A signer-leaking validation split would
therefore report a number the model cannot reproduce on a new signer.

**Split by `participant` explicitly.** It is easy: median **44** sequences per participant, only
**2** participants with fewer than 10, and a **15% holdout is reachable with 24 signers** (597
sequences, 14.9%).

### 4. The signer effect is large — a third of the tracking variance is *who is signing*.

```
per-participant mean hand_rate    worst 0.132  ->  best 0.896     6.78x spread
between-signer share of hand_rate variance                        33.5%
```

Worst: `p122` 0.13 (n=1), `p92` 0.19 (n=44), `p187` 0.22 (n=50), `p233` 0.23 (n=43).
Best: `p188` 0.90 (n=57), `p153` 0.88 (n=53), `p135` 0.88 (n=41).

Those are not tiny samples — 40–60 sequences each — so this is a property of the signer or their
recording conditions, not noise. Two consequences: **the holdout must be signer-stratified by
`hand_rate`**, or a lucky draw of well-tracked signers flatters the model; and **per-signer
reporting is mandatory**, because a pooled number will hide a subgroup the tool fails for.

### 5. Faster spelling tracks worse. The dropout is motion-correlated here too.

On the clean set (`T >= phrase_len`), by spelling-speed quartile:

```
Q1  0.034-0.088 chars/frame   hand_rate 0.619
Q2  0.088-0.111               hand_rate 0.628
Q3  0.111-0.143               hand_rate 0.555
Q4  0.143-1.000               hand_rate 0.443     <- 1.40x worse than Q1

corr(chars/frame, hand_rate) = -0.218
```

Same mechanism as the 250-word corpus — the tracker loses the hand that is moving — and the same
uncomfortable shape: **the corpus is worst exactly where the task is hardest.** Fast spelling is
both the most valuable to recognise and the least visible.

*(The 250-word figure was a 3.6× dropout ratio on wrist speed. Different measurement, so the two
numbers are not comparable — only the direction is.)*

### 6. Dominance is per-sequence, not per-signer. 17.8% are left-dominant.

```
R-dominant  3,286 (82.2%)      L-dominant  711 (17.8%)
single-hand participants  62   (52 R-only, 10 L-only)
participants appearing as BOTH  30 of 92
```

**A model that assumes right-dominance discards one sequence in six.** And normalisation cannot be
done per *signer*: **30 of 92 participants appear with both labels**, at a median 5% minority share.

Is that real switching or detection error? **The data says it is probably real.** If the minority
label were noise fired by bad tracking, minority sequences would track much worse. They barely do:
majority-hand `hand_rate` 0.515 against minority 0.475 — a **1.08×** gap. So no red flag, and
`subset_landmarks.py` detecting dominance **per sequence** is the correct design. `--selftest`
confirms it reads a left-dominant sequence as `L`.

### 7. The left/right tracking gap is small — a fairness concern that did not bear out.

```
R-dominant   hand_rate mean 0.558   median 0.578   p10 0.143   max_gap med 15
L-dominant   hand_rate mean 0.533   median 0.534   p10 0.157   max_gap med 17
```

**−0.025 mean, about 4.5% relative.** I raised the possibility that the 17.8% left-dominant minority
would also be tracked worse — doubly disadvantaged in a Deaf-accessibility tool. It is not, in any
material way. Worth re-checking on the full corpus, but nothing to design around.

---

## The recommended filter, and exactly what it costs

Drop `T < phrase_len` **and** `hand-frames < phrase_len`:

| | before | after |
|---|---|---|
| sequences | 3,997 | **3,462 (86.6%)** |
| frames | 635,755 | **591,786 (93.1%)** |
| participants | 92 | **91** |
| `hand_rate` median | 0.571 | **0.638** |
| `max_gap` median | 16 | 15 |
| hand-frames per character, median | 4.81 | **5.60** |
| hand-frames per character, **p10** | **0.69** | **1.83** |

**The p10 row is the reason to do it.** Before the filter, the worst decile of sequences has **fewer
than one frame in which the hand is visible per character it is supposed to spell** — at least one
letter was never seen, so it is unlearnable from the hand channel. After, the floor is 1.83.

**Cost: 6.9% of frames. One participant lost entirely** — `p122`, who has a single sequence at
`hand_rate` 0.132.

The second condition is a judgement call and can be relaxed; **the first is not optional** (finding 1).

---

## What this forces in the model

| Decision | Forced by | Why it is not a choice |
|---|---|---|
| **Filter `T < phrase_len` first** | #1 | CTC loss is `-inf` otherwise |
| **Ragged sequences, no fixed-frame resize** | length median 146, max 751 | 5× spread; the 250-word pipeline's 64-frame resize would destroy letter timing |
| **Explicit missing-hand channel**, not interpolation | #2 | median hole is half a second; filling it invents letters |
| **Signer-disjoint splits by `participant`** | #3 | shards do not partition signers |
| **Signer-stratified holdout + per-signer reporting** | #4 | 33.5% of tracking variance is between-signer |
| **Per-sequence dominance normalisation** | #6 | 30 of 92 signers appear as both |
| Expect worst accuracy on fast spelling | #5 | the corpus is thinnest where the task is hardest |

**Not forced, and deliberately left open:** the encoder architecture, whether to use the 53
`supplemental_landmarks` shards, and whether to scale past 4 shards — all 68 subset to roughly
**9.3 GB**, under Kaggle's 20 GB output cap, so no sharding strategy is needed when we want the rest.

---

## Provenance

Every figure above comes from `gap_stats.json` — 3,997 records carrying `T`, `dominant`,
`hand_rate`, `n_gaps`, `max_gap`, `median_gap`, `lead`, `trail`, `sequence_id`, `participant`,
`phrase_len`. No landmark coordinates and no phrase text are involved in any of it.

**The raw file is deliberately not committed.** It is per-sequence derived metadata from a licensed
competition corpus, and this repository's visibility could not be verified at the time of writing.
The aggregate statistics in this document are safe to hold; the per-sequence dump is a
redistribution judgement that belongs to Salim, not to me. Regenerate it any time with:

```
python subset_landmarks.py --base <competition-root> --out <dir> --limit-files 4
```

**Kaggle path note:** inputs are mounted **namespaced** — `/kaggle/input/competitions/<slug>/` and
`/kaggle/input/datasets/<user>/<slug>/` — so the script's `--base` default of
`/kaggle/input/asl-fingerspelling` never resolves. Always pass `--base`, and detect it rather than
typing it. See `SALIM_TASKS.md` task 4 step 4.
