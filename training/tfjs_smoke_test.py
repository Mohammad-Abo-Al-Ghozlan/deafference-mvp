#!/usr/bin/env python3
"""
P4.3 — TF.js conversion smoke test on the UNTRAINED model.

Purpose: prove the architecture (including the embedded PreprocessLayer)
survives TF.js conversion BEFORE any GPU money/time is spent training it.
Runs on any CPU in ~2-5 minutes.

What it does:
  1. build_model() with random weights
  2. sanity-check a forward pass in Python (batch of NaN-padded dummy input)
  3. export as SavedModel
  4. run tensorflowjs_converter --input_format=tf_saved_model
     (graph model — avoids custom-layer registration in JS)
  5. verify model.json + weight shards exist, print the op list so any
     exotic op is visible at a glance

Pass = "SMOKE TEST PASSED" and a tfjs_model/ folder you could load in a
browser. Fail = fix the architecture NOW, before P4.4/P4.5.

Usage:  python tfjs_smoke_test.py [--keep-z]
Needs:  pip install tensorflowjs  (see requirements.txt)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import tensorflow as tf

from train import MAX_LEN, N_POINTS, N_RAW_CH, build_model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-z", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("artifacts/tfjs_smoke"))
    args = ap.parse_args()

    print("1/5 building untrained model...")
    model = build_model(keep_z=args.keep_z)
    model.summary(line_length=100)

    print("2/5 python forward pass on dummy NaN-padded input...")
    dummy = np.random.randn(2, MAX_LEN, N_POINTS, N_RAW_CH).astype(np.float32)
    dummy[:, 40:] = np.nan  # simulate padding
    logits = model(dummy, training=False).numpy()
    assert logits.shape == (2, 30), f"unexpected output shape {logits.shape}"
    assert np.isfinite(logits).all(), "NaN/inf leaked into the logits!"
    print(f"    ok — output shape {logits.shape}, finite ✓")

    with tempfile.TemporaryDirectory() as tmp:
        saved = Path(tmp) / "savedmodel"
        print("3/5 exporting SavedModel...")
        try:
            model.export(str(saved))
        except AttributeError:
            tf.saved_model.save(model, str(saved))

        print("4/5 running tensorflowjs_converter...")
        if args.out.exists():
            shutil.rmtree(args.out)
        args.out.mkdir(parents=True)
        cmd = [
            sys.executable, "-m", "tensorflowjs.converters.converter",
            "--input_format=tf_saved_model",
            "--output_format=tfjs_graph_model",
            str(saved), str(args.out),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("CONVERSION FAILED:\n", res.stdout[-3000:], res.stderr[-3000:])
            return 1

    print("5/5 verifying artifacts + op inventory...")
    mj = args.out / "model.json"
    assert mj.exists(), "model.json missing"
    shards = list(args.out.glob("*.bin"))
    graph = json.loads(mj.read_text())
    ops = sorted({n.get("op", "?") for n in graph["modelTopology"]["node"]})
    print(f"    model.json ✓  weight shards: {len(shards)} ✓")
    print(f"    ops used ({len(ops)}): {', '.join(ops)}")

    print("\nSMOKE TEST PASSED — the architecture converts to TF.js. "
          "Safe to proceed to P4.4 (GPU) / P4.5 (fold 0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
