"""
ASL dataset cleaning script — Person 1's task (S3-aware version)

What this does, in plain terms:
1. Downloads train.csv from S3 (tiny file, has the index of all 94,477 signs)
2. Filters to OUR target vocabulary only (~20-30 words, not all 250)
3. For each kept row, downloads ONLY that specific parquet file from S3
   (not the whole 56GB dataset) and checks it for missing/broken values
   (NaN = "MediaPipe couldn't see this landmark in this frame")
4. Fixes small gaps, drops files that are too broken to use
5. Saves cleaned files + a new smaller manifest locally
6. Uploads the cleaned/ folder back to S3 for the preprocessor to use next

Requirements (install once):
    pip install pandas pyarrow boto3

Before running:
- Make sure `aws configure` has already been run on this machine
  (needs the IAM credentials from earlier — same ones used for S3 sync)
- Edit TARGET_SIGNS below to your real vocabulary list
"""

import pandas as pd
import numpy as np
import boto3
from pathlib import Path
from io import BytesIO

# ── CONFIG — edit these for your setup ────────────────────────────────────

BUCKET_NAME = "asl-mvp-dataset"
RAW_PREFIX = "raw/"                     # where the official Kaggle data lives in S3
CLEANED_PREFIX = "cleaned/"             # where cleaned output goes in S3

LOCAL_CLEANED_DIR = Path("cleaned")     # local working folder before upload
LOCAL_CLEANED_CSV = LOCAL_CLEANED_DIR / "train_cleaned.csv"

# Your team's target vocabulary — REPLACE with your real ~20-30 word list.
# These must be the exact words as they appear in train.csv's "sign" column.
TARGET_SIGNS = [
    "apple", "water", "please", "thankyou", "yes", "no",
    # ... add the rest of your vocabulary here
]

# If a clip is missing too many frames' worth of data, we throw it out
# rather than trying to salvage it.
MAX_MISSING_FRACTION = 0.5

s3 = boto3.client("s3")

# ── STEP 1: Download train.csv from S3 and filter ─────────────────────────

def load_and_filter_manifest():
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=f"{RAW_PREFIX}train.csv")
    df = pd.read_csv(BytesIO(obj["Body"].read()))
    print(f"Full dataset: {len(df)} rows, {df['sign'].nunique()} unique signs")

    filtered = df[df["sign"].isin(TARGET_SIGNS)].copy()
    print(f"After filtering to our vocabulary: {len(filtered)} rows, "
          f"{filtered['sign'].nunique()} unique signs")

    missing_signs = set(TARGET_SIGNS) - set(filtered["sign"].unique())
    if missing_signs:
        print(f"WARNING: these target signs were not found in the dataset "
              f"at all — check spelling: {missing_signs}")

    return filtered


# ── STEP 2: Download and clean a single landmark file ─────────────────────

def fetch_and_clean_one(s3_path):
    """
    Downloads one sign's landmark data directly from S3 (not the whole
    dataset), checks how much is missing, and either fixes small gaps
    or flags the file as too broken to use.

    Returns: (cleaned_dataframe, was_usable: bool)
    """
    key = f"{RAW_PREFIX}{s3_path}"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        data = pd.read_parquet(BytesIO(obj["Body"].read()))
    except s3.exceptions.NoSuchKey:
        print(f"MISSING FILE in S3, skipping: {key}")
        return None, False

    total_values = len(data)
    missing_values = data[["x", "y", "z"]].isna().sum().sum()
    missing_fraction = missing_values / (total_values * 3) if total_values else 1.0

    if missing_fraction > MAX_MISSING_FRACTION:
        return None, False  # too broken, don't use this clip

    # Patch small gaps: forward-fill then back-fill within each landmark
    # point's own timeline (carries the last known good position forward)
    data = data.sort_values(["frame", "type", "landmark_index"])
    data[["x", "y", "z"]] = (
        data.groupby(["type", "landmark_index"])[["x", "y", "z"]]
        .transform(lambda col: col.ffill().bfill())
    )

    # Anything still NaN (a landmark NEVER detected in the whole clip)
    # gets filled with 0 as a last resort
    data[["x", "y", "z"]] = data[["x", "y", "z"]].fillna(0.0)

    return data, True


# ── STEP 3: Run cleaning across all filtered rows ─────────────────────────

def clean_all():
    LOCAL_CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_and_filter_manifest()

    kept_rows = []
    dropped_count = 0

    for i, row in manifest.iterrows():
        cleaned_data, usable = fetch_and_clean_one(row["path"])

        if not usable:
            dropped_count += 1
            continue

        # Save cleaned file locally, mirroring the original folder structure
        dest_path = LOCAL_CLEANED_DIR / row["path"]
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_data.to_parquet(dest_path)

        kept_rows.append(row)

        if len(kept_rows) % 50 == 0:
            print(f"Cleaned {len(kept_rows)} files so far...")

    # Save the new, smaller manifest that Person 2 will read next
    cleaned_manifest = pd.DataFrame(kept_rows)
    cleaned_manifest.to_csv(LOCAL_CLEANED_CSV, index=False)

    print(f"\nDone cleaning.")
    print(f"Kept: {len(kept_rows)} clips")
    print(f"Dropped (too broken or missing): {dropped_count} clips")
    print(f"Cleaned manifest saved to: {LOCAL_CLEANED_CSV}")


# ── STEP 4: Upload cleaned results back to S3 ──────────────────────────────

def upload_cleaned_to_s3():
    print("\nUploading cleaned data to S3...")
    for local_file in LOCAL_CLEANED_DIR.rglob("*"):
        if local_file.is_file():
            relative_path = local_file.relative_to(LOCAL_CLEANED_DIR)
            s3_key = f"{CLEANED_PREFIX}{relative_path.as_posix()}"
            s3.upload_file(str(local_file), BUCKET_NAME, s3_key)

    print(f"Upload complete: s3://{BUCKET_NAME}/{CLEANED_PREFIX}")


if __name__ == "__main__":
    clean_all()
    upload_cleaned_to_s3()
