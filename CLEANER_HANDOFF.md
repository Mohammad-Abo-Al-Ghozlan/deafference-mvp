# Cleaner's handoff doc — everything you and your AI need to know

This is written for whoever is doing the "Clean" stage of the ASL MVP data pipeline, and for any AI assistant helping them. Read this fully before writing or running anything.

---

## 1. Your job, in one sentence

Take the raw official ASL dataset sitting in S3, filter it down to our team's target vocabulary, fix or remove broken/missing landmark data, and produce a clean output that the preprocessing person builds on next.

---

## 2. What you're working with — the dataset, in full detail

### Source and legitimacy
- This data comes from Kaggle's **"Google - Isolated Sign Language Recognition"** competition (`kaggle.com/competitions/asl-signs`)
- Underlying data: the "Isolated Sign Language Recognition Corpus v1.0" by Georgia Tech / DPAN / NTID-RIT
- **License is fully verified**: CC-BY 4.0, and the Kaggle competition rules (Section 7.A) explicitly permit commercial use. Already downloaded properly through Kaggle by the team — you don't need to worry about licensing, just don't redistribute it outside the team.
- It's already sitting in our private S3 bucket (`s3://asl-mvp-dataset/raw/`) — you should be pulling from there, not re-downloading from Kaggle yourself

### Scale and structure
- **94,477 total sequences** (individual recorded sign clips), across **250 unique signs**, from **21 different Deaf signers**
- **`train.csv`** — the index file. Every row = one recorded clip. Columns:
  - `path` — where to find that clip's landmark file, e.g. `train_landmark_files/16069/1000035562.parquet`
  - `participant_id` — which of the 21 signers recorded it (e.g. `16069`)
  - `sequence_id` — unique ID for that specific clip
  - `sign` — the word/label, in plain English text (e.g. `"apple"`, `"blow"`, `"cloud"`)
- **`sign_to_prediction_index_map.json`** — maps each of the 250 sign words to an official numeric label (0-249). Not needed for your cleaning step directly, but good to know it exists — the preprocessing/training people will use it.
- **`train_landmark_files/`** — the actual data. Organized as `{participant_id}/{sequence_id}.parquet` — one file per recorded clip. There are 21 folders (one per signer), each containing hundreds to thousands of files (all their recorded signs mixed together, not separated by word).

### What's inside each parquet file
Each file is a table of individual landmark readings, one row per (frame, landmark point). Columns:
- `frame` — which frame number in the sequence
- `type` — category of landmark (`face`, `pose`, `left_hand`, `right_hand`)
- `landmark_index` — which specific point within that category
- `x`, `y`, `z` — the coordinate values (normalized 0-1 range, `z` is depth)

A single clip has **543 landmarks per frame** (all types combined) × however many frames the clip runs for (variable length — clips are NOT all the same duration).

### Known data quality issues (documented by the dataset's own creators, not just us)
- Coarsely reviewed only — poor recordings were removed, but no correctness judgment on individual signs was made
- Some signers made sign variants, occasionally fingerspelled instead of signing, sometimes missed/wrong signs entirely
- Extraneous movement sometimes included (scratching, transition motion from the sign before/after)
- Some clips are cropped (button pressed too early/released too late during recording)
- Some signers are left-handed, some right-handed, a few switch mid-dataset
- **`x`, `y`, `z` will contain `NaN` (missing) values** whenever MediaPipe failed to detect that specific landmark in that specific frame — this is normal and expected, not a sign the file is corrupted. Your job is to handle this, not be alarmed by it.

---

## 3. Your target vocabulary

**[TEAM: fill in the actual locked-in ~20-30 word list here before running anything for real. Do not guess or proceed with a placeholder list.]**

Every word here must be spelled exactly as it appears in `train.csv`'s `sign` column (case-sensitive, no typos) — a mismatch here silently means zero clips get found for that word, and the script will only warn you about it, not stop.

---

## 4. AWS access you need

- **You need your own IAM user and access keys** — ask the team lead if you don't have these yet. Do not use anyone else's credentials.
- Install the AWS CLI and run `aws configure` once on your machine, entering:
  - Your Access Key ID
  - Your Secret Access Key
  - Region: match the bucket's region (`eu-north-1` — Stockholm, confirmed from the console)
  - Output format: press Enter to skip
- This only needs to be done once per machine — after that, `aws s3` and `boto3` commands on that machine use these credentials automatically
- **Bucket name**: `asl-mvp-dataset`
- **Never make the bucket public.** It should stay private/team-only — this is a legal requirement from Kaggle's rules (data can't be shared with non-participants), not just a preference.

---

## 5. The actual work — step by step

### 5a. Install requirements
```bash
pip install pandas pyarrow boto3
```

### 5b. Get the cleaning script
Use `clean_dataset_s3.py` (already written and provided by the team). It:
1. Downloads `train.csv` from S3
2. Filters to your target vocabulary
3. For each matching row, downloads *only that specific file* from S3 (not the whole 56GB dataset — efficient by design)
4. Checks each file's percentage of missing (`NaN`) landmark values
5. If more than 50% missing → drops the file entirely (too broken to use)
6. If some missing but under 50% → patches gaps using forward-fill then back-fill (carries the last known good position across the gap — a standard, simple, defensible way to handle brief tracking dropouts)
7. Saves cleaned files locally, then uploads them to `s3://asl-mvp-dataset/cleaned/`
8. Also produces `train_cleaned.csv` — the new manifest, listing only the kept/cleaned files

### 5c. Edit the config section at the top of the script
- Set `TARGET_SIGNS` to the real vocabulary list (Section 3 above)
- Everything else in the config should already be correct (bucket name, prefixes) — double check against what's actually in the AWS console if unsure

### 5d. TEST FIRST — do not run on the full vocabulary immediately
Before running with your real 20-30 word list:
1. Temporarily set `TARGET_SIGNS` to just 3-5 words
2. Run the script: `python clean_dataset_s3.py`
3. Check the printed output — does the row count look reasonable? Any warnings about missing signs?
4. Check `s3://asl-mvp-dataset/cleaned/` in the AWS console — are files actually there?
5. Only once this small test looks correct, expand `TARGET_SIGNS` to the full real list and re-run

This matters because the whole team's plan depends on you being able to hand off a *small, verified* sample early so the preprocessing person can start their own work in parallel without waiting for your full run to finish.

### 5e. Run the full job
Once the small test is verified, run again with the complete vocabulary list. This will take longer since it's touching more files — that's expected. Let it finish.

---

## 6. What "done" looks like — the handoff contract

When you're finished, these must all be true:

1. **`s3://asl-mvp-dataset/cleaned/`** contains cleaned parquet files, organized the same way as raw (`{participant_id}/{sequence_id}.parquet`), but only for your target vocabulary's signs
2. **`s3://asl-mvp-dataset/cleaned/train_cleaned.csv`** (or wherever your script puts it — make sure it ends up in S3, not just locally) exists and lists exactly the files you kept, with their `sign`, `participant_id`, and `path`
3. **You can state, in plain numbers**: how many clips you started with (after vocabulary filtering), how many were dropped as too broken, and how many were kept and patched
4. **The preprocessing person should be able to work from `cleaned/` alone** — they should never need to touch `raw/` directly

This — the cleaned parquet files + the manifest — is the actual handoff. A stats/QC report (counts, percentages, etc.) is a nice-to-have alongside this, not a substitute for it.

---

## 7. Things that will trip you up if you don't know them in advance

- **The 21 folders are signers, not words.** Every signer recorded many different signs. Don't try to manually pick "one folder" for your vocabulary — the script filters across all 21 automatically using `train.csv`, and that's the only correct way to do it.
- **`NaN` values in the data are normal, not corruption.** Don't panic and discard everything with any missing values — only discard files where *more than half* the data is missing (the script's `MAX_MISSING_FRACTION` threshold already handles this).
- **A file with very low hand-detection presence can still technically "pass"** if it's under the missing-value threshold but the tracked hand simply wasn't visible much. Worth spot-checking a few kept files' `left_hand`/`right_hand` presence percentages, not just trusting the pass/fail count blindly — a sequence with almost no hand data isn't useful even if it "counts" as kept.
- **If your `TARGET_SIGNS` word doesn't match `train.csv` exactly (spelling/case), you'll silently get zero clips for that word** — the script prints a warning for this, don't ignore it.
- **Don't sync the entire `raw/` folder to your laptop just to filter it down to 30 words.** That's 56GB for data you'll mostly throw away. The provided script avoids this by fetching only the specific files needed — use it as-is rather than writing your own full-sync-then-filter version.
- **Long-running AWS operations can get interrupted by SSH disconnects if you're working on a remote EC2 instance rather than locally.** If you go that route, run your script inside `tmux` (`tmux new -s cleaning`, run the script, `tmux attach -t cleaning` to reconnect if disconnected) — this already caused a real problem earlier in this project during the initial dataset download and cost hours of repeated re-downloads before it was diagnosed.

---

## 8. Who to ask if something's ambiguous

If `train.csv`'s `sign` column doesn't contain a word you expected, or a large fraction of your vocabulary's clips are getting dropped as too broken, don't guess or quietly work around it — report the actual numbers to the team lead before proceeding. These are exactly the kind of findings that might mean the vocabulary list itself needs revisiting, not something to solve unilaterally at the cleaning stage.
