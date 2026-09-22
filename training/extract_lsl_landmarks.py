#!/usr/bin/env python3
"""LSL video -> the same 75-point landmark arrays the ASL models are trained on.

WHY THIS IMPORTS live_demo INSTEAD OF REIMPLEMENTING
----------------------------------------------------
The corpus in s3://lsldataset is VIDEO. `processed-v1` is normalised h264 (592x1280,
30 fps CFR, rotation baked in) -- excellent video preprocessing, but nothing a model can
consume. This is the missing step between the bucket and a trainable tensor.

MODEL_CONTRACT.md 3 is blunt about the one way this goes wrong: if the landmark
extraction and normalisation here do not match what the live demo does, the model gets
out-of-distribution input and accuracy collapses SILENTLY -- no error, just wrong
predictions. The repo already carries a parity harness (`golden_parity.py`) built because
that exact bug cost the frontend twice.

So this file does not contain a normalisation function. It imports `extract_75`,
`normalize`, `MP_COMPLEXITY`, `MP_DET_CONF` and `MP_TRK_CONF` from `live_demo` -- the
module that actually runs at demo time. There is only one implementation, so there is
nothing for a second copy to drift from, and a parity test between them would be
self-referential by construction.

THE MISSING-LANDMARK CONVENTION
-------------------------------
`extract_75` returns NaN for anything MediaPipe did not see, and `normalize` returns None
for a frame without both shoulders (it cannot be placed in the training coordinate space,
so the live demo DROPS it -- we drop it too). NaN, never 0.0: see sign_landmarks.py for
the three separate defects that 0.0-as-missing produced last time. 0.0 in this space is
mid-sternum, which is a real coordinate.

WHAT IS SAVED
-------------
Variable-length (T,75,3) float32 per clip, NOT resampled to 64 here. `fit_to_maxlen` is a
training/inference-time decision (NaN-pad short, resize long) and baking it in would throw
away the true clip length, which the animation side already learned to regret.

Every row also carries its RECORDING DATE, parsed from the filename. That is not metadata
bookkeeping -- it is the only session signal this corpus has, and the split depends on it.
The corpus has NO signer IDs and was captured from a single signer, so signer-disjoint
validation is impossible; date-disjoint is the nearest honest substitute. 97% of labels
span >=2 dates and 91% span >=3, so it is actually available. A random split would leak
lighting, clothing, camera placement and that day's articulation into the test set and
report a number that does not survive contact with a new recording.

    python training/extract_lsl_landmarks.py --lesson "lesson 1" --out lsl_lesson1.npz
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import mediapipe as mp                                              # noqa: E402
from live_demo import (extract_75, normalize, MP_COMPLEXITY,        # noqa: E402
                       MP_DET_CONF, MP_TRK_CONF, N_POINTS)

BUCKET = "lsldataset"
PROCESSED = "datasets/asl/processed-v1"
DATE_RE = re.compile(r"(\d{8})_(\d{6})")


def clip_rows(manifest: Path, lesson: str | None, collection: str = "vocabulary"):
    """Rows of the production run manifest that actually produced an output.

    Reads the manifest rather than listing S3: the manifest is what the preprocessing run
    itself recorded, so `status` and `verified` come from the process that wrote the files
    instead of being inferred from their existence. 8 rows are `duplicate` and 2 are
    `unsupported`; both are excluded here, and a listing could not tell.
    """
    import json
    out = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("collection") != collection or r.get("status") != "ok":
            continue
        if not r.get("verified"):
            continue
        parts = r["relative_path"].split("/")
        if len(parts) < 3:                       # collection-level file, not lesson/label/clip
            continue
        les, label, fname = parts[0], parts[1], parts[2]
        if lesson and les != lesson:
            continue
        m = DATE_RE.search(fname)
        out.append({"lesson": les, "label": label, "file": fname,
                    "date": m.group(1) if m else "unknown",
                    "key": r["output_key"], "frames": r.get("output_nb_frames")})
    return out


def landmarks_for(path: Path, holistic) -> np.ndarray:
    """(T,75,3) normalised, dropping frames the demo would also drop.

    The video is already upright: the preprocessing baked `rotate=90` into the pixels and
    stripped the display matrix, so no rotation is applied here. Applying one would put
    the signer on their side, and MediaPipe would still return plausible-looking garbage
    rather than failing -- which is why this is a comment and not an assumption.
    """
    cap = cv2.VideoCapture(str(path))
    frames, seen, dropped = [], 0, 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        seen += 1
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        res = holistic.process(np.ascontiguousarray(rgb))
        n = normalize(extract_75(res))
        if n is None:                            # no shoulders -> not placeable, same as live
            dropped += 1
            continue
        frames.append(n)
    cap.release()
    if not frames:
        return np.zeros((0, N_POINTS, 3), np.float32), seen, dropped
    return np.stack(frames).astype(np.float32), seen, dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="run-standard-PROD-*.manifest.jsonl from _reports/runs/")
    ap.add_argument("--lesson", default=None, help="e.g. 'lesson 1'; omit for all")
    # NOT under the repo: the repo lives in OneDrive, and OneDrive grabs a lock on each new
    # file to sync it. boto3 downloads to a temp name and renames, and the rename loses that
    # race -- `PermissionError: [WinError 32] ... being used by another process`, 70 clips
    # into a 108-clip run. The same trap already ate an `mv` of animation_handoff/.
    ap.add_argument("--cache", type=Path,
                    default=Path(os.environ.get("TEMP", "/tmp")) / "lsl_cache",
                    help="local mirror of the processed clips (downloaded once). Keep it "
                         "OUT of any synced folder.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0, help="stop after N clips (smoke test)")
    args = ap.parse_args()

    rows = clip_rows(args.manifest, args.lesson)
    if args.limit:
        rows = rows[:args.limit]
    labels = sorted({r["label"] for r in rows})
    dates = sorted({r["date"] for r in rows})
    print(f"[cfg] {len(rows)} clips, {len(labels)} labels, {len(dates)} recording dates")
    if not rows:
        raise SystemExit("[err] no clips matched -- check --lesson spelling")

    args.cache.mkdir(parents=True, exist_ok=True)
    holistic = mp.solutions.holistic.Holistic(
        model_complexity=MP_COMPLEXITY,
        min_detection_confidence=MP_DET_CONF, min_tracking_confidence=MP_TRK_CONF)

    import boto3
    s3 = boto3.client("s3")

    X, y, d, keys, stats = [], [], [], [], []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        local = args.cache / r["key"].replace(PROCESSED + "/", "").replace("/", "__")
        if not local.exists():
            s3.download_file(BUCKET, r["key"], str(local))
        arr, seen, dropped = landmarks_for(local, holistic)
        X.append(arr)
        y.append(r["label"])
        d.append(r["date"])
        keys.append(r["key"])
        stats.append((seen, dropped, len(arr)))
        if i % 10 == 0 or i == len(rows):
            el = time.time() - t0
            print(f"  {i:4d}/{len(rows)}  {el:6.1f}s  "
                  f"({el/i:.2f}s/clip, eta {(len(rows)-i)*el/i/60:.1f} min)", flush=True)
    holistic.close()

    st = np.array(stats)
    kept = st[:, 2].sum()
    # A clip whose shoulders were never found yields ZERO frames. It is not a bad clip and
    # it is not an error -- it is a clip the live demo would also refuse -- but it cannot
    # be a training example either, so it is counted out loud rather than silently stored
    # as an empty row for a loader to trip over later.
    empty = [keys[i] for i in range(len(X)) if len(X[i]) == 0]
    print(f"\n[ok] frames: {st[:, 0].sum()} decoded, {st[:, 1].sum()} dropped "
          f"(no shoulders), {kept} kept -- {100*kept/max(st[:, 0].sum(),1):.1f}%")
    if empty:
        print(f"[warn] {len(empty)} clip(s) produced NO usable frame: {empty[:5]}")

    np.savez_compressed(
        args.out,
        X=np.array(X, dtype=object), y=np.array(y), date=np.array(d),
        key=np.array(keys), labels=np.array(labels),
        # Recorded so a later reader can prove these arrays came from the same code the
        # demo runs, instead of trusting that they did.
        provenance=np.array([f"live_demo.extract_75+normalize",
                             f"complexity={MP_COMPLEXITY}",
                             f"det={MP_DET_CONF}", f"trk={MP_TRK_CONF}"]))
    print(f"[ok] {args.out}  ({args.out.stat().st_size/1e6:.1f} MB, {len(X)} clips, "
          f"{len(labels)} labels)")


if __name__ == "__main__":
    main()
