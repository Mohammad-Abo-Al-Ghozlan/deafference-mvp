# How many clips per sign should a recording session collect?

**Measured 2026-09-08/09.** `training/medical/clips_per_sign_curve.py`, fold 0 of the 123-class
medical data, `--epochs 200 --seed 42 --decimate 0.5`, 10 training runs, ~2 h GPU.

**Read the two caveats first.** They are why this file exists in this shape.

---

## 🔴 CAVEAT 1 — the first write-up of this run was WRONG, and so was its correction

`_scrape_val_acc` reported **peak TRAINING accuracy** for all ten points. It looked for
`report.json` / `history.json` / `metrics.json`, none of which `train.py` writes — it writes
`eval_{tag}_fold{fold}.json` — so the artifact branch never fired and everything fell to a
stdout scraper that took the **max of every float in `[0,1]`** on any line containing
`val_acc`. A Keras epoch line carries both:

```
64/64 - 7s - loss: 0.9 - acc: 0.9012 - val_loss: 2.1 - val_acc: 0.3456
                              ^^^^^^ this is what it returned, maxed over 200 epochs
```

The error **grows as the training set shrinks**, because small sets memorise. So it
manufactured a clean-looking curve out of nothing and *inverted* the strategy comparison.

| n | spread reported / true | clustered reported / true |
|---|---|---|
| 2 | 0.0990 / **0.0029** | 0.0990 / **0.0073** |
| 4 | 0.4888 / **0.2969** | 0.5759 / **0.1659** |
| 8 | 0.5982 / **0.5757** | 0.7266 / **0.4483** |
| 16 | 0.7434 / **0.7213** | 0.8119 / **0.6310** |
| 32 | 0.8375 / **0.7868** | 0.8590 / **0.7525** |

**Two conclusions were published from the bad numbers and are FALSE:**

* ❌ *"62% of the rows beat 100% of them — the pool's class imbalance is costing accuracy."*
  Dead. spread n=32 is 0.7868 against 0.7940 (converged, decimate 0.0) and 0.8020 for the full
  4,149 rows. More data wins, as expected.
* ❌ *"Clustered beats spread — take more takes from fewer signers."* Inverted. Spread leads at
  every n ≥ 4.

Fixed in `d653887`, with six selftest checks. The first is the whole bug in one assertion: a
synthetic Keras line with `acc 0.9012` and `val_acc 0.3456` must return `0.3456`.

## 🔴 CAVEAT 2 — the truncation is worst exactly in the MIDDLE of the curve

7 of 10 points hit the `--epochs 200` cap. That alone is not proof of a large gap — with 1,374
val clips one clip is 0.0007, so trivial noise resets a patience-30 `EarlyStopping` counter.
What matters is how much each point actually moved late. From `history_all250_fold0.csv`:

| n | spread, gain over final 50 epochs | clustered |
|---|---|---|
| 2 | +0.0007 *(fired at 36/38 — converged)* | +0.0007 *(38)* |
| 4 | **+0.1405** | **+0.0590** |
| 8 | +0.0764 | +0.0429 |
| 16 | +0.0255 | +0.0320 |
| 32 | +0.0066 *(fired at 191)* | +0.0073 |

**Monotone decreasing in n: the ends are converged and the middle is starved.** So the measured
curve is depressed in the middle, which distorts its *shape* — the thing a session plan reads.

---

## What the data actually supports

### ✅ 1. Two takes per word is worthless — this one is clean

**0.0029 and 0.0073, against a 1/123 = 0.0081 chance line.** Below chance, on both strategies,
and **both points converged** (EarlyStopping fired at 36 and 38 epochs). At 123 classes, two
takes teaches the model nothing. Do not plan a session around 2 takes.

### ✅ 2. Spread across MORE SIGNERS — and n=32 is the nearly-clean comparison

At n=32 both strategies have ~equal headroom left (+0.0066, +0.0073), so their gap barely moves:

```
spread     0.7868   11.50 signers/word
clustered  0.7525    7.67 signers/word
gap       +0.0343   <- the most trustworthy number in the experiment
```

**Same clip budget, more signers, +0.034.** And the direction is robust rather than marginal: at
n=4 and n=8 spread is *further* from converged than clustered (+0.1405 vs +0.0590), so
correcting for truncation would **widen** its lead there, not close it.

> This reverses the earlier "book fewer signers" claim, which came from the bad scraper. It also
> retires the provenance worry raised against it — that clustered might be selecting
> better-recorded prolific signers — because clustered is the one that *loses*.

### 🟡 3. The curve saturates — estimated, not measured

Adding each point's final-50-epoch gain as a rough headroom proxy (**not a rigorous bound; a run
still moving at +0.14 per 50 epochs has more than +0.14 left**) gives a textbook saturating
series where the measured one was ragged:

```
spread, measured   2->4 +0.2940   4->8 +0.2788   8->16 +0.1456   16->32 +0.0655
spread, corrected  2->4 +0.4338   4->8 +0.2147   8->16 +0.0947   16->32 +0.0466
                                  ^ halves every doubling
```

**Working figure: ~16 clips per word gets most of the available benefit.** The 16→32 doubling is
worth about +0.047 and a further doubling would buy roughly +0.023 — but that extrapolation
rests on one interval, and **n=64 is untestable in this corpus**: only 41 of 123 words even
reach 32 clips.

### 🟡 4. The last 38% of the pool still pays, by about a point

```
spread n=32, drift-corrected   ~0.7934   on 2,570 rows (62%)
ALL 4,149 rows, decimate 0.5    0.8020   itself 200/200 CAPPED -> a FLOOR
```

So **≥ +0.009** for the remaining 38%. Read as a lower bound, since the full-data run had room
too. Suggestive of saturation at the top end; not established.

---

## The session recommendation

1. **Never 2 takes per word.** Below chance, and that is measured on converged runs.
2. **Recruit widely rather than deeply.** +0.034 for the same clip count at n=32, direction
   robust under truncation correction.
3. **Budget ~16 clips per word** as the point where returns have mostly flattened, with 32 as
   the stretch target worth ~+0.047 more.
4. Past 32 is **unknown and unmeasurable here.** If accuracy past ~0.80 is needed, the lever is
   more SIGNERS or more WORDS, not more takes of the same signs.

## Should the 4-hour `--epochs 400` re-run happen?

**Not yet.** It would sharpen the middle points and give a clean shape, but it would not change
any of the four calls above — 1 and 2 rest on converged or near-converged points, and 3 and 4
would move in magnitude, not direction. The session it prices is blocked on **task 10** (a
fluent Deaf signer / medical interpreter), so there is nothing to plan against yet.

**When it does happen:** `--epochs 400`, and 🔴 **re-upload `clips_per_sign_curve.py` to the
Kaggle code dataset first** — the copy there still has the broken scraper. Confirm with
`--selftest`, which must print *"stdout fallback reads val_acc (0.3456), NOT the train acc
0.9012"*. `--strategy spread` alone is 5 runs (~2 h) and spread is the winner, so that is the
cheap version. Steps in `RUNBOOK_FINGERSPELLING.md`-style detail live in the session log, not
here, because the code dataset version is the part that goes stale.

## Design notes worth keeping

* **Only `split=="cv" & fold != 0` rows are ever cut**, asserted per point rather than once. If
  validation shrank with training, accuracy would move for two reasons at once and the curve
  would measure neither.
* **`spread` vs `clustered` hold the clip count IDENTICAL** (246/490/948/1,698/2,570 at every n)
  and vary only *whose* clips they are. That is what makes the gap attributable to signer
  diversity.
* `by_word` is symlinked into each point directory, never copied.
* `--decimate 0.5` on every point: the demo runs at ~7 fps, where this repo measures a
  5.2-point penalty. A curve trained at 30 fps only would price a model we do not ship. **The
  medical decimate A/B is inconclusive on native-rate validation (≥ +0.008, treatment
  truncated) and the deployment-rate effect is unmeasured** — see the session log.
