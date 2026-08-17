#!/usr/bin/env python3
r"""
Stage 3 (medical MVP): VIDEO -> 75-landmark tensors, in the EXACT convention live_demo.py
uses at inference time.

WHY THIS FILE IS THE RISKIEST ONE: the general 250-word model was trained on GISLR's
*pre-extracted* landmarks. Sem-Lex / ASL Citizen ship *raw video*, so we extract ourselves.
If our extraction differs from what runs live -- landmark slots, handedness, normalization,
resampling -- accuracy degrades SILENTLY instead of failing loudly. Every step below is
therefore copied from live_demo.py rather than re-invented:

  slots       0-32 pose | 33-53 LEFT hand | 54-74 RIGHT hand, NaN when undetected
              (live_demo.extract_75)
  normalize   shoulder-midpoint centered, shoulder-width scaled, x/y ONLY, z untouched;
              a frame whose shoulders aren't both visible is DROPPED, not rescaled
              (live_demo.normalize)
  resample    linear interpolation to exactly 64 frames (live_demo.time_resize)
  MediaPipe   complexity 1, det/trk confidence 0.3, frame downscaled to <=640 px wide
              (live_demo MP_* constants)

Because we train a FRESH medical model on this output, the parity requirement is with
live_demo.py (our own inference path), NOT with GISLR. That is what makes this tractable.
If you ever want to warm-start from the 250-word weights instead, GISLR parity comes back
and must be re-verified separately.

RUN
  # a manifest CSV: one row per clip, columns video,label[,signer]
  python training/medical/extract_landmarks.py --manifest clips.csv --videos ./semlex --out medical_landmarks.npz
  # or a folder laid out as <videos>/<label>/<clip>.mp4
  python training/medical/extract_landmarks.py --videos ./by_label --out medical_landmarks.npz
  # sanity-check the pipeline on a handful of clips first
  python training/medical/extract_landmarks.py --videos ./semlex --manifest clips.csv --limit 20 --report

OUTPUT (.npz)
  X       (N, 64, 75, 3) float32   normalized, resampled clips
  y       (N,) int32               label index
  words   (C,) str                 label names, y indexes into this
  signer  (N,) str                 signer id ('' if unknown) -- REQUIRED for signer-disjoint folds
  clip    (N,) str                 source filename, for tracing a bad sample back
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# ── constants copied from live_demo.py — do not "improve" these ───────────────
N_POINTS, POSE_N, HAND_N = 75, 33, 21
N_RAW_CH = 3
MAX_LEN = 64
L_SHOULDER, R_SHOULDER = 11, 12
MP_COMPLEXITY = 1
MP_DET_CONF = 0.3
MP_TRK_CONF = 0.3
MP_MAX_W = 640
HANDPRESENCE_MIN = 0.35     # live_demo's "poor input" bar — a clip with a hand in fewer than
                            # this fraction of frames carries almost no handshape information.
                            # Rejecting >0 is NOT enough: a hand seen in 1 of 280 frames would
                            # otherwise be accepted and train the model on noise.
MIN_VALID_FRAMES = 8        # normalizable (both shoulders visible) frames required

VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def extract_75(results) -> np.ndarray:
    """(75,3) for one frame; NaN wherever MediaPipe saw nothing. == live_demo.extract_75."""
    pts = np.full((N_POINTS, 3), np.nan, dtype=np.float32)
    if results.pose_landmarks:
        for i, lm in enumerate(results.pose_landmarks.landmark):
            pts[i] = (lm.x, lm.y, lm.z)
    if results.left_hand_landmarks:
        for i, lm in enumerate(results.left_hand_landmarks.landmark):
            pts[POSE_N + i] = (lm.x, lm.y, lm.z)
    if results.right_hand_landmarks:
        for i, lm in enumerate(results.right_hand_landmarks.landmark):
            pts[POSE_N + HAND_N + i] = (lm.x, lm.y, lm.z)
    return pts


def normalize(frame: np.ndarray):
    """Shoulder-centered + shoulder-width scaled on x,y; z untouched. == live_demo.normalize.
    Returns None when the shoulders aren't both visible (frame is dropped, never rescaled)."""
    ls, rs = frame[L_SHOULDER, :2], frame[R_SHOULDER, :2]
    if np.isnan(ls).any() or np.isnan(rs).any():
        return None
    mid = (ls + rs) / 2.0
    width = float(np.linalg.norm(ls - rs))
    if width < 1e-6:
        return None
    out = frame.copy()
    out[:, :2] = (out[:, :2] - mid) / width
    return out


def time_resize(a: np.ndarray, n: int = MAX_LEN) -> np.ndarray:
    """Linear resample of a (T,75,3) clip to exactly n frames. == live_demo.time_resize."""
    t = a.shape[0]
    if t == n:
        return a.astype(np.float32)
    idx = np.linspace(0.0, t - 1.0, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, t - 1)
    w = (idx - lo).astype(np.float32)[:, None, None]
    return (a[lo] * (1.0 - w) + a[hi] * w).astype(np.float32)


def clip_to_tensor(path: Path, holistic, cv2, min_hand_rate=HANDPRESENCE_MIN,
                   min_frames=MIN_VALID_FRAMES) -> tuple:
    """One video -> ((64,75,3), stats) or (None, stats) if unusable."""
    st = {"frames": 0, "valid": 0, "hand_frames": 0, "reason": ""}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        st["reason"] = "cannot open"
        return None, st
    seq = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            st["frames"] += 1
            if frame.shape[1] > MP_MAX_W:                      # same downscale as live
                s = MP_MAX_W / frame.shape[1]
                frame = cv2.resize(frame, (MP_MAX_W, int(round(frame.shape[0] * s))),
                                   interpolation=cv2.INTER_AREA)
            res = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            pts = extract_75(res)
            if res.left_hand_landmarks or res.right_hand_landmarks:
                st["hand_frames"] += 1
            nrm = normalize(pts)
            if nrm is not None:
                seq.append(nrm)
                st["valid"] += 1
    finally:
        cap.release()
    if st["valid"] < min_frames:
        st["reason"] = f"only {st['valid']} normalizable frames (<{min_frames})"
        return None, st
    st["hand_rate"] = st["hand_frames"] / st["frames"] if st["frames"] else 0.0
    if st["hand_rate"] < min_hand_rate:
        st["reason"] = (f"hand in only {st['hand_rate']:.0%} of frames "
                        f"(<{min_hand_rate:.0%}) — no usable handshape")
        return None, st
    return time_resize(np.stack(seq), MAX_LEN), st


def read_manifest(path: Path, allowed: set | None):
    """CSV with columns video,label[,signer]. Returns [(relpath,label,signer)]."""
    out = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in (rd.fieldnames or [])}
        for need in ("video", "label"):
            if need not in cols:
                raise SystemExit(f"[err] manifest needs a '{need}' column; got {rd.fieldnames}")
        c_v, c_l = cols["video"], cols["label"]
        c_s = cols.get("signer") or cols.get("signer_id")
        for r in rd:
            lab = (r[c_l] or "").strip().lower()
            if not lab or (allowed is not None and lab not in allowed):
                continue
            out.append(((r[c_v] or "").strip(), lab, (r[c_s] or "").strip() if c_s else ""))
    return out


def scan_folder(root: Path, allowed: set | None):
    """<root>/<label>/<clip>.mp4 layout. Signer unknown ('')."""
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        lab = d.name.strip().lower()
        if allowed is not None and lab not in allowed:
            continue
        for v in sorted(d.iterdir()):
            if v.suffix.lower() in VIDEO_EXT:
                out.append((str(v.relative_to(root)), lab, ""))
    return out


def main():
    ap = argparse.ArgumentParser(description="video -> (64,75,3) landmark tensors (live_demo parity)")
    ap.add_argument("--videos", required=True, help="root dir holding the clips")
    ap.add_argument("--manifest", help="CSV video,label[,signer]; omit to scan <videos>/<label>/*.mp4")
    ap.add_argument("--vocab", help="JSON {'words':[...]} — keep only these labels (e.g. vocab_medical.json)")
    ap.add_argument("--out", default="medical_landmarks.npz")
    ap.add_argument("--limit", type=int, help="process at most N clips (smoke test)")
    ap.add_argument("--min-hand-rate", type=float, default=HANDPRESENCE_MIN,
                    help="reject a clip with a hand in fewer than this fraction of frames")
    ap.add_argument("--min-frames", type=int, default=MIN_VALID_FRAMES,
                    help="reject a clip with fewer normalizable frames than this")
    ap.add_argument("--report", action="store_true", help="print per-clip tracking stats")
    ap.add_argument("--resume", action="store_true", help="skip clips already in --out and append")
    args = ap.parse_args()

    root = Path(args.videos)
    if not root.is_dir():
        sys.exit(f"[err] --videos not a directory: {root}")
    allowed = None
    if args.vocab:
        raw = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
        allowed = {w.lower() for w in (raw["words"] if isinstance(raw, dict) else raw)}
        print(f"[cfg] restricting to {len(allowed)} labels from {Path(args.vocab).name}")

    items = (read_manifest(Path(args.manifest), allowed) if args.manifest
             else scan_folder(root, allowed))
    if not items:
        sys.exit("[err] no clips matched — check --videos / --manifest / --vocab")

    done = set()
    prev = {}
    if args.resume and Path(args.out).exists():
        with np.load(args.out, allow_pickle=True) as z:
            prev = {k: z[k] for k in z.files}
        done = set(prev["clip"].tolist())
        print(f"[resume] {len(done)} clips already extracted")

    items = [it for it in items if it[0] not in done]
    if args.limit:
        items = items[:args.limit]
    print(f"[cfg] {len(items)} clips to extract -> {args.out}")

    os.environ.setdefault("GLOG_minloglevel", "2")
    import cv2
    import mediapipe as mp

    X, y, signer, clip = [], [], [], []
    words = sorted({lab for _, lab, _ in items} | set(prev.get("words", np.array([])).tolist()))
    widx = {w: i for i, w in enumerate(words)}
    skipped, t0 = [], time.perf_counter()

    with mp.solutions.holistic.Holistic(static_image_mode=False,
                                        model_complexity=MP_COMPLEXITY,
                                        min_detection_confidence=MP_DET_CONF,
                                        min_tracking_confidence=MP_TRK_CONF) as hol:
        for n, (rel, lab, sg) in enumerate(items, 1):
            arr, st = clip_to_tensor(root / rel, hol, cv2,
                                     min_hand_rate=args.min_hand_rate, min_frames=args.min_frames)
            if arr is None:
                skipped.append((rel, lab, st["reason"]))
            else:
                X.append(arr); y.append(widx[lab]); signer.append(sg); clip.append(rel)
            if args.report:
                hr = st["hand_frames"] / st["frames"] if st["frames"] else 0.0
                print(f"  {rel:52} {lab:12} frames={st['frames']:3} valid={st['valid']:3} "
                      f"hand={hr:4.0%} {'SKIP: ' + st['reason'] if arr is None else 'ok'}")
            if n % 50 == 0 or n == len(items):
                el = time.perf_counter() - t0
                print(f"[{n}/{len(items)}] kept={len(X)} skipped={len(skipped)} "
                      f"{el:.0f}s ({n/max(el,1e-9):.1f} clips/s, eta {(len(items)-n)/max(n/el,1e-9):.0f}s)")

    if not X and not prev:
        sys.exit("[err] nothing extracted — every clip failed (see reasons above)")

    Xn = np.stack(X).astype(np.float32) if X else np.zeros((0, MAX_LEN, N_POINTS, N_RAW_CH), np.float32)
    yn = np.array(y, np.int32)
    sn = np.array(signer, dtype=object).astype(str)
    cn = np.array(clip, dtype=object).astype(str)
    if prev:                                    # remap old label ids onto the merged word list
        old = prev["words"].tolist()
        remap = np.array([widx[w] for w in old], np.int32)
        Xn = np.concatenate([prev["X"], Xn]) if Xn.size else prev["X"]
        yn = np.concatenate([remap[prev["y"]], yn])
        sn = np.concatenate([prev["signer"].astype(str), sn])
        cn = np.concatenate([prev["clip"].astype(str), cn])

    np.savez_compressed(args.out, X=Xn, y=yn, words=np.array(words), signer=sn, clip=cn)
    print(f"\n[ok] wrote {args.out}: X={Xn.shape} classes={len(words)} "
          f"signers={len(set(sn.tolist()) - {''})}")

    # a quick honesty report: which classes are underpopulated after extraction failures
    if len(yn):
        cnt = np.bincount(yn, minlength=len(words))
        weak = [(words[i], int(c)) for i, c in enumerate(cnt) if c < 8]
        print(f"[stats] videos/class: min={cnt.min()} median={int(np.median(cnt))} max={cnt.max()}")
        if weak:
            print(f"[warn] {len(weak)} classes under 8 clips AFTER extraction: {weak[:20]}")
    if skipped:
        print(f"[warn] skipped {len(skipped)} clips; first few:")
        for rel, lab, why in skipped[:10]:
            print(f"        {rel} ({lab}): {why}")


if __name__ == "__main__":
    main()
