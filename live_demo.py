#!/usr/bin/env python3
r"""
LIVE camera demo of the ASL model — standalone, NO browser / frontend needed.

Opens the webcam, runs MediaPipe Holistic, normalizes exactly like training
(shoulder-midpoint centered + shoulder-width scaled, per MODEL_CONTRACT.md §3),
buffers 64 frames, runs the trained model, and overlays the recognized word live.

This is the fastest way to let someone "open the camera, sign one of the 30
words, and see the result" — it reuses the real final model and skips the
unbuilt browser pipeline (#14/#22/#25).

Model = the FINAL 5-fold model from fold_all_artifacts.zip (test acc: ensemble
0.9433, best single fold-0 0.9386). We load the exported TF SavedModels
(artifacts/savedmodel_fold*/) and average their softmax — the same ensemble
recipe ensemble_eval.py uses. SavedModel is a pure-TF format: no train.py, no
Keras-version juggling, and it avoids the Windows tf-keras .weights.h5 bug.

──────────────────────────────────────────────────────────────────────────────
PREREQUISITES (exact versions — they matter, see notes below):
  1. pip install "tensorflow==2.17.*" "tf-keras==2.17.*" "mediapipe==0.10.14" \
                 opencv-python numpy pandas
     • mediapipe 0.10.14 — later builds (0.10.35) REMOVED legacy Holistic, which
       produces the exact 75-point layout the model was trained on.
     • TF 2.17 — reads the SavedModels AND keeps protobuf 4.x (mediapipe needs it;
       TF >= 2.18 forces protobuf 5 and breaks mediapipe).
  2. artifacts/savedmodel_fold{0..4}/ present (extract fold_all_artifacts.zip
     into ./artifacts/ — already done).
  3. A webcam + decent lighting. Frame yourself head-and-shoulders, like training.

RUN:
  python live_demo.py --selftest    # NO camera: load model + predict on random
                                     # input. Proves the model half works. Run
                                     # this FIRST to debug without a webcam.
  python live_demo.py                # the live camera demo (press q to quit)
  python live_demo.py --single       # faster: use only fold-0, skip the ensemble

⚠️ HONEST CAVEAT: the one thing that can make this read poorly is a normalization
   mismatch (same risk as frontend #22/#26). This script implements the spec in
   MODEL_CONTRACT.md §3. If predictions look random, that's the first suspect —
   confirm the exact preprocessing with the teammate and tweak `normalize()`.
──────────────────────────────────────────────────────────────────────────────
"""
import os
# We load the exported TF SavedModels (artifacts/savedmodel_fold*/), not the
# .keras/.weights.h5 files. SavedModel is a pure-TF, framework-level format:
# it needs neither train.py/build_model nor a specific Keras version, and it
# sidesteps the Windows tf-keras `.weights.h5` path-separator bug that makes the
# Linux-saved weight files unreadable here. Input=(1,64,75,3), output=logits(30).
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")   # quiet TF startup spam

import sys
import json
import time
import queue
import threading
import argparse
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load_dotenv():
    """Load KEY=VALUE lines from ./.env into the environment (so --ai can read
    GEMINI_API_KEYS from the gitignored .env instead of a hardcoded key). Env
    vars already set win — no dependency on python-dotenv."""
    p = HERE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


# ── optional text-to-speech (offline, Windows SAPI via win32com) ──────────────
class Speaker:
    """Speaks text off the main thread so the video never freezes.

    Uses the Windows SAPI voice directly (win32com), NOT pyttsx3: pyttsx3's
    runAndWait() only fires once per engine in a background thread (it speaks the
    first time, then goes silent), which is the "speaks once" bug. SAPI's Speak()
    works on every call. COM must be initialised inside the worker thread."""

    def __init__(self):
        self.q: "queue.Queue[str|None]" = queue.Queue()
        self.available = False
        try:
            import win32com.client, pythoncom  # noqa: F401  (from pywin32)
            self.available = True
            threading.Thread(target=self._worker, daemon=True).start()
        except Exception as e:
            print(f"[warn] TTS disabled (pywin32/SAPI not available: {e})")

    def _worker(self):
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        while True:
            text = self.q.get()
            if text is None:
                break
            try:
                voice.Speak(str(text))               # blocks this thread only
            except Exception:
                pass

    def say(self, text: str):
        if self.available and text:
            self.q.put(text)

# ── config ──────────────────────────────────────────────────────────────────
ARTIFACTS    = HERE / "artifacts"
VOCAB_PATH   = HERE / "vocab_30.json"
WORD_ACC_PATH = None        # optional {word: test_acc} JSON (set for --vocab250); shown in word panel

# The FINAL 5-fold exported models. Ensemble = all five; --single = fold-0 only.
ENSEMBLE_MODELS = [ARTIFACTS / f"savedmodel_fold{k}" for k in range(5)]
SINGLE_MODELS   = [ARTIFACTS / "savedmodel_fold0"]

MAX_LEN      = 64            # frames per window (matches training)
N_POINTS     = 75
N_RAW_CH     = 3
CONF_GATE    = 0.50         # commit a word only above this. raise toward 0.7 = fewer
                            #   wrong words; lower toward 0.4 = shows more (more
                            #   mistakes). Hard words: look 0.70, go 0.74.

# Margin-based acceptance — the real fix for large vocabularies. At 250 classes a
# CORRECT sign often scores only ~0.45 absolute (probability is split across many
# look-alikes), yet it still beats the runner-up decisively. Judging by the GAP to
# the 2nd guess — not just the absolute score — lets correct low-confidence signs
# commit on the FIRST try, while still rejecting truly ambiguous ones (top≈second).
# This makes the FULL vocabulary usable, not just a curated subset.
DECISIVE_RATIO = 2.2        # commit if top >= this many x the runner-up AND
DECISIVE_MIN   = 0.28       #   top >= this absolute (rejects pure noise), OR
DECISIVE_GAP   = 0.16       # commit if (top - second) >= this AND
DECISIVE_FLOOR = 0.26       #   top >= this absolute
USE_TTA      = True         # average the model over the window + its mirror (the
                            #   model was trained with hflip, so this is free acc).
SHOW_TOPK    = 3            # after each sign, show the top-K candidates as chips so
                            #   a WRONG top-1 can be fixed with one tap (number keys
                            #   1-5 or click) instead of re-signing. With 250
                            #   classes the correct word is almost always in the top
                            #   2-3 even when #1 is wrong — this is the top-k UX that
                            #   keeps a large vocabulary usable. Set 0 to disable.

# ── Commit DECISION ENGINE (Parts 4-6): confidence + margin + quality + stability ──
# Replaces confidence-only / ad-hoc early-commit logic. Three levels:
#   LEVEL 1 (strong)  conf>=L1_CONF & margin>=L1_MARGIN & quality>=Q_STRONG -> INSTANT
#   LEVEL 2 (medium)  conf>=L2_CONF & margin>=L2_MARGIN -> commit once temporally STABLE
#   LEVEL 3 (weak)    otherwise -> never auto-commit (top-K tap / repeat)
# This is what fixes "model said HELLO 0.61 (margin 0.41) but the app refused it":
# 0.61 fails LEVEL 1's 0.70 bar but PASSES LEVEL 2, so it commits after confirmation.
L1_CONF   = 0.70            # LEVEL 1 (strong) — instant, no waiting
L1_MARGIN = 0.30
Q_STRONG  = 0.60            #   quality needed to allow an instant level-1 commit
L2_CONF   = 0.50            # LEVEL 2 (medium) — commit after temporal confirmation
L2_MARGIN = 0.18
L2_STABLE = 2               #   previews the top word must persist for a level-2 commit

# ── sign segmentation (auto-commit): a "sign" = hands active, then a pause ────
# The signer raises hands, signs, then lowers hands / holds still → the word is
# captured, resampled to 64 frames (exactly like training), classified, committed.
# ALL timing is in SECONDS and converted to frame counts each loop from the LIVE
# camera fps (see main loop) — so the feel is identical at 10 fps or 30 fps. It
# auto-adapts per camera; no manual per-machine tuning.
MIN_SEG_SEC   = 0.30       # ignore sign blips shorter than this (0.40->0.30: quick signs survive)
MAX_SEG_SEC   = 5.0        # force-commit if a sign runs longer (generous → slow signing is fine)
END_SEC       = 0.65       # no hand visible this long -> end the sign (long: face-signs lose the hand)
STILL_SEC     = 0.50       # near-zero hand motion this long -> end the sign
MIN_HAND_SEC  = 0.25       # a segment needs a real hand for at least this long
START_SEC     = 0.13       # a hand must persist this long before a NEW segment starts (kills
                           #   twitch-starts from single-frame false hand detections)
MOTION_EPS    = 0.02       # hand movement (shoulder-width units) below = "still"
# Per-commit response-latency samples: (path, detect_ms, infer_ms). Printed as p50/p95 on
# exit. See commit_segment for what the two components mean and why they are kept apart.
LAT_LOG: list[tuple[str, float, float]] = []
PRE_ROLL      = 8          # frames kept from BEFORE the hand appears (captures sign start)
LEAD_SEC      = 0.25       # of that pre-roll, keep only this much ONSET context in the clip we
                           #   CLASSIFY. The full pre-roll is a static hand-up pose; at low fps
                           #   (~7) its fixed frame count is >1s and dominates the 64-frame
                           #   resample, so a MOTION sign (hello) looks like a STATIC one
                           #   (hat/brown). Trimming to a short lead-in makes the clip
                           #   motion-dominated, matching the sign-dominated training clips.

# Hand-QUALITY gate (#1): a SAFETY NET for genuine garbage (the log's 25%-hand
# clips -> bed/fireman), NOT a second confidence threshold. It fires only when the
# hand was barely seen; normal-quality clips fall straight through to CONF_GATE +
# the margin logic. Thresholds are deliberately lenient so mid-confidence signs
# (0.42-0.8) still commit — the earlier, stricter values were rejecting real signs.
HANDPRESENCE_MIN = 0.35    # frames-with-hand / total below this = "poor input"
QUALITY_MIN      = 0.40    # composite quality (segment_quality) below this = "poor input"
POOR_CONF        = 0.45    # on a poor clip, commit only if conf >= this (~= CONF_GATE) ...
POOR_MARGIN      = 0.15    #   ... AND (top - second) >= this (else reject + coach)

# EARLY COMMIT — commit without waiting for the pause.
PREVIEW_SEC   = 0.35       # run the live preview about this often
EARLY_MIN_SEC = 0.85       # don't early-commit before the sign is at least this long
EARLY_CONF     = 0.80      # preview confidence needed (same word twice in a row)
EARLY_SURE     = 0.999     # single-preview instant commit if this confident (≈off by default;
                           #   --vocab250 lowers it so a strong sign commits on the 1st preview)
COOLDOWN_SEC  = 0.40       # pause after a commit before a new sign may start (0.70->0.40: don't block natural cadence)
DUP_SECONDS    = 0.8       # ignore the same word re-committing within this time (2.0->0.8: allow deliberate repeats + re-attempts)

# MediaPipe pose model complexity: 1 = training-parity quality (default — the
# hand detector depends on good pose, and face-signs like "hello" need it);
# run with --fast to use 0 (≈2x fps, worse hand detection near the face).
MP_COMPLEXITY  = 1
MP_MAX_W       = 640       # feed MediaPipe a frame no wider than this. 768->640 buys ~1.4x fps
                           #   are more pixels on the hand (better landmarks near the face).
                           #   Lower (e.g. 480/640) = more fps but weaker hands.
MP_DET_CONF    = 0.3       # min_detection_confidence — LOWER than the 0.5 default so a hand in
                           #   poor light is still ACQUIRED (the quality gate filters the junk).
MP_TRK_CONF    = 0.3       # min_tracking_confidence — hold the hand track through motion blur.

# In-app capture-quality coach (#1 — landmark quality is the #1 live bottleneck).
# The model only ever sees MediaPipe landmarks, so a dark frame or an undetected
# hand silently feeds it corrupted data → wrong word / "sign it many times". We
# measure the CENTER (signer) brightness and the recent hand-detection rate and
# warn ON-SCREEN so the user fixes lighting/framing — the highest-ROI fix there is.
DARK_LUMA      = 80        # mean brightness (0-255) of the center region below this = "too dark"
HANDRATE_WARN  = 0.30      # while signing, a hand seen in < this fraction of recent frames = warn

# MediaPipe Holistic landmark counts → the 75-point layout (pose, left, right).
POSE_N, HAND_N = 33, 21     # 33 + 21 + 21 = 75
L_SHOULDER, R_SHOULDER = 11, 12   # pose indices, used for normalization

# Horizontal-flip map for mirror TTA (from train.py FLIP_MAP): swaps L/R pose
# pairs and the whole left-hand block <-> right-hand block. Mirror = negate x.
FLIP_MAP = np.array([
    0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
    22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31,
    54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74,
    33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
], dtype=np.int32)


# ── model ─────────────────────────────────────────────────────────────────────
def load_models(model_dirs):
    """Load each exported SavedModel and return its serving function.

    For the ensemble we hold all 5 resident and average their softmax at
    inference — exactly what ensemble_eval.py does. We keep the loaded objects
    alive alongside the signature fns so TF doesn't garbage-collect them."""
    import tensorflow as tf
    loaded, fns = [], []
    for d in model_dirs:
        if not d.exists():
            sys.exit(f"[err] missing model dir: {d}\n"
                     f"      download the savedmodel_fold* folders into its parent dir")
        obj = tf.saved_model.load(str(d))
        loaded.append(obj)
        # model.export() names the serving endpoint "serving_default" on some TF
        # builds and "serve" on others — take serving_default if present, else the
        # first available signature (keeps 30-word and 250-word exports both working).
        sigs = obj.signatures
        key = "serving_default" if "serving_default" in sigs else list(sigs.keys())[0]
        fns.append(sigs[key])
        print(f"[ok] loaded {d.name}")
    print(f"[ok] {len(fns)} model(s) ready "
          f"({'ENSEMBLE' if len(fns) > 1 else 'single fold-0'})")
    return loaded, fns


def predict(fns, x):
    """x: (1, 64, 75, 3) float32 -> averaged softmax probs (30,)."""
    import tensorflow as tf
    probs = None
    for f in fns:
        out = f(landmarks=x)
        logits = out["output_0"] if "output_0" in out else list(out.values())[0]
        p = tf.nn.softmax(logits, axis=1).numpy()[0]
        probs = p if probs is None else probs + p
    return probs / len(fns)


def time_resize(a: np.ndarray, n: int = MAX_LEN) -> np.ndarray:
    """Resample a (T,75,3) sequence to exactly n frames by linear interpolation.
    This is what training did to every isolated-sign clip (train.time_resize) —
    so classifying a resampled sign matches the training distribution."""
    t = a.shape[0]
    if t == n:
        return a.astype(np.float32)
    idx = np.linspace(0.0, t - 1.0, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, t - 1)
    w = (idx - lo).astype(np.float32)[:, None, None]
    return (a[lo] * (1.0 - w) + a[hi] * w).astype(np.float32)


# FLIP_MAP swaps the two hand blocks, which is right for a LEGACY model and actively wrong for
# a CANONICAL one: there the dominant hand always sits at 54-74 and 33-53 is reserved/NaN, so
# swapping moves the only hand into the empty block. train.py:127 builds the canonical map the
# same way — pose flipped, hand slots identity — and trains with it (`hflip swaps hands = False`).
FLIP_MAP_CANON = np.concatenate([FLIP_MAP[:POSE_N],
                                 np.arange(POSE_N, N_POINTS, dtype=FLIP_MAP.dtype)])
assert sorted(FLIP_MAP_CANON.tolist()) == list(range(N_POINTS))

CANONICAL_HAND = False        # set by --canonical; selects the mirror map AND enables canonicalize


def _mirror(x: np.ndarray) -> np.ndarray:
    """Horizontal flip of a (1,T,75,3) normalized clip: reorder L/R and negate x
    (coords are shoulder-centered, so mirror is x -> -x).

    The map MUST match the one the weights were trained with. classify_commit averages a clip
    with its mirror, so using the hand-swapping map on canonical weights would feed half the
    views a clip whose only hand sits in the reserved block."""
    m = x[:, :, FLIP_MAP_CANON if CANONICAL_HAND else FLIP_MAP, :].copy()
    m[..., 0] *= -1.0
    return m


def canonicalize_seg(seg: list) -> list:
    """Mirror a segment so the signing arm reads as right, hand parked at 54-74.

    Canonical weights (train.py --canonical-hand) never see a hand in the 33-53 block: the
    corpus they were built from measures L-block occupancy 0.000 across all seven signers. But
    live_demo.normalize() does no such thing — a left-dominant signer's hand stays where
    MediaPipe put it, in a block the model has never seen once. Without this, canonical weights
    work for right-dominant signers and fail completely for left-dominant ones.

    Delegates to training/extract_canonical.canonicalize, the SAME function that built the
    corpus, rather than reimplementing the rule. That matters twice over: parity is exact, and
    the naive rule is known-bad — extract_canonical.py:259-261 records that "most tracked frames
    wins" is what put the RESTING hand in the dominant slot, because MediaPipe preferentially
    drops the hand that moves (root cause R5). Its default `dominance="geometric"` is the fix.

    Safe to apply to already-normalized frames: canonicalize() begins with normalize_xy(), which
    centers on the shoulder midpoint and scales by shoulder width — on normalized input that is
    mid=0, width=1, i.e. the identity. Verified against live_demo.normalize(): same convention,
    x/y only, z untouched, NaN preserved."""
    try:
        from training.extract_canonical import canonicalize
    except ImportError:
        from extract_canonical import canonicalize          # training/ on sys.path
    arr, _meta = canonicalize(np.stack(seg).astype(np.float32))
    return list(arr)


# Restrict recognition to a curated subset of words (set via --words). With 250
# classes the winning probability is spread thin across many look-alikes, so a
# correct sign often scores only ~0.45 and sits under the commit gate → retries.
# Masking to an allowed subset and re-normalizing == softmax over ONLY those
# words, so the same sign now scores ~0.80 and commits first try. None = all words.
ALLOWED_IDX = None            # np.ndarray of allowed class indices, or None
DEMO_WORDS_PATH = None        # path to a JSON list/{"words":[...]} of allowed words


def _mask_probs(probs: np.ndarray) -> np.ndarray:
    """Zero out non-allowed classes and re-normalize (subset softmax)."""
    if ALLOWED_IDX is None:
        return probs
    m = np.zeros_like(probs)
    m[ALLOWED_IDX] = probs[ALLOWED_IDX]
    s = m.sum()
    return m / s if s > 0 else probs


def build_masks(words, demo_path=None, demo_idx=None) -> list:
    """[(name, idx|None)] — the vocabulary masks the T key cycles through.

    Narrowing is the only lever that measured large: masking to a ~34-word topic takes the
    commit rate from 12% to 68% at gate 0.90 at the same precision (measure_conf_gate.py).
    But a conversation changes subject, and a mask fixed at startup cannot follow it — which
    is exactly how a live run of the 43-word clinical mask "detected nothing": hello, mom and
    hungry were simply not in that list. Cycling at runtime is what makes a mask a feature
    rather than a trap. Module-level so it is testable without a camera."""
    def _of(path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        allow = raw["words"] if isinstance(raw, dict) else raw
        idx = sorted({words.index(w) for w in allow if w in words})
        return np.array(idx, dtype=np.int64) if idx else None

    out = [(f"ALL {len(words)}", None)]
    if demo_path is not None and demo_idx is not None:
        # Same label whether the mask arrived via --words or was discovered on disk; the name
        # is shown on the debug overlay, so "topic_everyday" vs "everyday" would read as two.
        out.append((demo_path.stem.replace("topic_", ""), demo_idx))
    for p in sorted(HERE.glob("topic_*.json")):
        if demo_path is None or p.name != demo_path.name:
            m = _of(p)
            if m is not None:
                out.append((p.stem.replace("topic_", ""), m))
    return out


def trim_preroll(seq, preroll_n, lead_fr):
    """Drop the STATIC pre-roll lead-in, keeping only `lead_fr` frames of onset
    context right before the active signing. `preroll_n` is how many frames at the
    FRONT of `seq` came from the pre-roll buffer (captured before the hand appeared).

    Why: at low fps the fixed ~12-frame pre-roll is >1s of a still hand-up pose. Fed
    whole to the 64-frame resample it drowns out the few motion frames, so a moving
    sign (hello) resamples to look like a static one (hat/brown) — the log's
    hello/hat/brown collision. Keeping just a short onset lead-in makes the clip
    motion-dominated, which is what the model was trained on (sign-dominated clips)."""
    start = max(0, min(preroll_n, len(seq)) - max(0, lead_fr))
    return seq[start:] if start < len(seq) else seq


def classify_segment(fns, seg) -> np.ndarray:
    """seg: list of (75,3) normalized frames for one sign -> softmax probs.
    Resamples to 64 frames (training parity) and, if USE_TTA, averages the clip
    with its mirror (the model was trained with hflip)."""
    if CANONICAL_HAND:
        seg = canonicalize_seg(seg)
    arr = time_resize(np.stack(seg), MAX_LEN)[None].astype(np.float32)   # (1,64,75,3)
    probs = predict(fns, arr)
    if USE_TTA:
        probs = (probs + predict(fns, _mirror(arr))) / 2.0
    return _mask_probs(probs)


def classify_commit(fns, seg) -> np.ndarray:
    """Robust prediction used ONLY at commit (not for the live preview).

    Averages the model over several VIEWS of the same sign — the full clip and a
    centered 80% crop, each together with its mirror. Averaging independent views
    smooths out a single bad resample / noisy boundary, so a correctly-signed word
    comes back with higher, steadier confidence and clears CONF_GATE on the FIRST
    attempt. That's what removes the "sign it three times" feel. Cost is a short
    burst of extra forward passes at commit only — the per-frame preview stays the
    cheap single-model path."""
    if CANONICAL_HAND:
        seg = canonicalize_seg(seg)
    base = np.stack(seg)                                  # (T,75,3)
    views = [base]                                        # crop view dropped: on a short low-fps
    #   clip it trims only ~1-2 frames but DOUBLES the commit passes (16->8), which was freezing
    #   capture ~0.3-0.8s at every commit and reading as "it missed my sign".
    probs = None
    for v in views:
        arr = time_resize(v, MAX_LEN)[None].astype(np.float32)
        p = predict(fns, arr) + predict(fns, _mirror(arr))   # view + its mirror
        probs = p if probs is None else probs + p
    return _mask_probs(probs / (2.0 * len(views)))


def segment_quality(seg) -> tuple:
    """Score a captured segment BEFORE trusting its prediction → (score, hand_presence).

    The model only sees landmarks, so a clip where the hand was rarely detected is
    near-NaN and the network collapses onto priors (the live log: 25%-hand -> junk,
    64%-hand -> correct). hand_presence is measured DIRECTLY from the clip (fraction
    of frames with any finite hand landmark) — not from the seg_hands counter, which
    the pre-roll would dilute and wrongly reject short signs. Used by commit_segment
    to refuse to commit garbage."""
    n = len(seg)
    if n == 0:
        return 0.0, 0.0
    arr = np.stack(seg)                                   # (n,75,3)
    hand_xy = arr[:, POSE_N:N_POINTS, :2]                 # both-hand blocks (n,42,2)
    finite_pt = np.isfinite(hand_xy).all(axis=-1)         # (n,42) both x,y present
    hand_presence = float(finite_pt.any(axis=1).mean())   # frames with ANY hand point
    finite = hand_xy[finite_pt]                           # detected hand points only
    motion = float(finite.std()) if finite.size else 0.0
    motion_completeness = min(1.0, motion / 0.15)         # ~0.15 su spread = a real sign
    # NB: do NOT weight "both hands present" — most ASL signs are ONE-handed, so the
    # other hand is legitimately NaN and must not be treated as poor quality.
    score = 0.70 * hand_presence + 0.30 * motion_completeness
    return score, hand_presence


def decide_commit(conf, second, quality, stable) -> tuple:
    """The 3-level commit DECISION ENGINE (Parts 4/5/6). Returns (action, level, reason).

      action: 'commit'  -> add the word now
              'confirm' -> right word, but wait for more temporal agreement
              'reject'  -> too weak/ambiguous; show top-K, don't commit
      LEVEL 1 strong  : high conf AND wide margin AND decent quality -> INSTANT
      LEVEL 2 medium  : moderate conf + margin -> commit once the word is STABLE
                        (`stable` = consecutive previews agreeing on this word)
      LEVEL 3 weak    : small margin / low conf -> never auto-commit

    This replaces confidence-only gating: HELLO 0.61 / HAT 0.20 (margin 0.41) is
    LEVEL 2 and commits after confirmation, instead of being rejected by a 0.78 wall."""
    margin = conf - second
    if conf >= L1_CONF and margin >= L1_MARGIN and quality >= Q_STRONG:
        return "commit", 1, f"strong c{conf:.2f} m{margin:.2f}"
    if conf >= L2_CONF and margin >= L2_MARGIN:
        if stable >= L2_STABLE:
            return "commit", 2, f"medium c{conf:.2f} m{margin:.2f} stable x{stable}"
        return "confirm", 2, f"medium: need {L2_STABLE} agree (have {stable})"
    return "reject", 3, f"weak c{conf:.2f} m{margin:.2f}"


class Camera:
    """Threaded webcam: a worker thread keeps grabbing frames so we always read
    the freshest one (removes capture buffer lag; keeps the UI responsive)."""

    def __init__(self, index=0):
        import cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.opened = self.cap.isOpened()
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        if self.opened:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._running:
            ok, f = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = f

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def release(self):
        self._running = False
        self.cap.release()


def load_vocab():
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))["words"]


# ── grammar: gloss buffer -> spoken sentence (A9 rules, GRAMMAR_CONTRACT.md) ──
# Self-contained copy of grammar_eval.render_rules so the demo stays standalone.
# Greedy longest-match, left to right; templates beat rules at equal length.
GRAMMAR_PATH = HERE / "grammar_rules.json"


def load_grammar():
    try:
        return json.loads(GRAMMAR_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] grammar_rules.json not loaded ({e}); showing raw words only")
        return None


def render_sentence(rules, buf) -> str:
    """Turn the ordered gloss buffer (e.g. ['hello','mom']) into a spoken
    sentence (e.g. 'Hello, Mom!'). Falls back to space-joined words if the
    grammar file is missing."""
    if not buf:
        return ""
    if rules is None:
        return " ".join(buf)

    disp = lambda g: rules["display"].get(g, g)
    cats = rules["categories"]

    def match_at(i):
        best = None                                    # (length, text)
        for t in rules["templates"]:                   # exact-sequence templates
            g = t["glosses"]
            if buf[i:i + len(g)] == g and (best is None or len(g) > best[0]):
                best = (len(g), t["text"])
        for r in rules["rules"]:                       # category / literal rules
            pat = r["pattern"]
            if i + len(pat) > len(buf):
                continue
            matched, ok = [], True
            for k, elem in enumerate(pat):
                w = buf[i + k]
                if elem in cats:
                    if w in cats[elem]: matched.append(w)
                    else: ok = False; break
                elif w == elem: matched.append(w)
                else: ok = False; break
            if ok and (best is None or len(pat) > best[0]):
                text = r["text"]
                for idx, w in enumerate(matched):
                    text = text.replace("{" + str(idx) + "}", disp(w))
                best = (len(pat), text)
        return best

    fb = rules["fallback"]
    clauses, i = [], 0
    while i < len(buf):
        m = match_at(i)
        if m:
            clauses.append(m[1]); i += m[0]
        else:
            clauses.append(fb["unknown_word_text"].replace("{word}", disp(buf[i]))); i += 1
    if fb.get("capitalize_clauses"):
        clauses = [c[:1].upper() + c[1:] if c else c for c in clauses]
    return fb.get("clause_join", " ").join(clauses)


# ── landmark extraction → (75, 3), NaN for anything undetected ────────────────
def extract_75(results) -> np.ndarray:
    pts = np.full((N_POINTS, 3), np.nan, dtype=np.float32)
    if results.pose_landmarks:
        for i, lm in enumerate(results.pose_landmarks.landmark):
            pts[i] = (lm.x, lm.y, lm.z)                 # slots 0–32
    if results.left_hand_landmarks:
        for i, lm in enumerate(results.left_hand_landmarks.landmark):
            pts[POSE_N + i] = (lm.x, lm.y, lm.z)        # slots 33–53
    if results.right_hand_landmarks:
        for i, lm in enumerate(results.right_hand_landmarks.landmark):
            pts[POSE_N + HAND_N + i] = (lm.x, lm.y, lm.z)  # slots 54–74
    return pts


# ── normalization — MUST match training (MODEL_CONTRACT.md §3) ────────────────
def normalize(frame: np.ndarray):
    """Shoulder-midpoint centered + shoulder-width scaled on x,y.

    Returns the normalized (75,3) frame, or None if the shoulders aren't both
    visible — in that case the frame can't be placed in the training coord space,
    so we DROP it rather than feed a differently-scaled frame into the window.
    (z is left as-is; the model drops z via PreprocessLayer(keep_z=False).)"""
    ls, rs = frame[L_SHOULDER, :2], frame[R_SHOULDER, :2]
    if np.isnan(ls).any() or np.isnan(rs).any():
        return None
    mid = (ls + rs) / 2.0
    width = np.linalg.norm(ls - rs)
    if width < 1e-6:
        return None
    out = frame.copy()
    out[:, :2] = (out[:, :2] - mid) / width             # center + scale x,y
    return out


# ── headless self-test — proves the model loads + runs, no camera needed ──────
def selftest(single: bool):
    print("=== SELFTEST (no camera) ===")
    words = load_vocab()
    n = len(words)
    print(f"[ok] vocab: {n} words ({VOCAB_PATH.name})")
    _, fns = load_models(SINGLE_MODELS if single else ENSEMBLE_MODELS)

    rng = np.random.default_rng(0)
    x = rng.standard_normal((1, MAX_LEN, N_POINTS, N_RAW_CH)).astype(np.float32)

    t0 = time.time(); probs = predict(fns, x); dt = (time.time() - t0) * 1000
    t1 = time.time(); probs = predict(fns, x); dt2 = (time.time() - t1) * 1000  # warm

    assert probs.shape == (n,), f"bad output shape {probs.shape} (expected ({n},))"
    assert abs(probs.sum() - 1.0) < 1e-3, f"softmax doesn't sum to 1: {probs.sum()}"
    top = probs.argsort()[::-1][:3]
    print(f"[ok] output shape ({n},), sums to {probs.sum():.4f}")
    print(f"[ok] inference latency: {dt:.0f} ms cold, {dt2:.0f} ms warm "
          f"({len(fns)} model(s))")
    print(f"[ok] top-3 on random input (should be ~uniform/meaningless): "
          f"{[(words[i], round(float(probs[i]), 3)) for i in top]}")
    print("\nSELFTEST PASSED — model loads and predicts. "
          "Now run `python live_demo.py` with a webcam.")
    if dt2 > 250 and not single:
        print("\n⚠️ warm latency is high for a live feed; consider `--single` "
              "(fold-0 only, still 0.9386 test acc) for smoother video.")


# ── main loop ─────────────────────────────────────────────────────────────────
def main(single: bool, ai_enabled: bool, fast: bool = False, debug: bool = False):
    import cv2
    import mediapipe as mp

    words = load_vocab()

    # --words: restrict recognition to a curated subset (concentrates confidence).
    global ALLOWED_IDX
    if DEMO_WORDS_PATH is not None:
        if not DEMO_WORDS_PATH.exists():
            sys.exit(f"[err] --words file not found: {DEMO_WORDS_PATH}")
        raw = json.loads(DEMO_WORDS_PATH.read_text(encoding="utf-8"))
        allow = raw["words"] if isinstance(raw, dict) else raw
        idx = [words.index(w) for w in allow if w in words]
        unknown = [w for w in allow if w not in words]
        if unknown:
            print(f"[warn] {len(unknown)} --words not in the model vocab (ignored): {unknown[:8]}")
        if not idx:
            sys.exit("[err] none of the --words matched the model vocab")
        ALLOWED_IDX = np.array(sorted(set(idx)), dtype=np.int64)
        allowed_words = [words[i] for i in ALLOWED_IDX]
        print(f"[cfg] recognition restricted to {len(ALLOWED_IDX)} words "
              f"(confidence concentrated → faster commits)")
        print("  sign any of: " + ", ".join(allowed_words))

    # ── runtime topic switching (press T) ────────────────────────────────────
    MASKS = build_masks(words, DEMO_WORDS_PATH, ALLOWED_IDX)
    mask_i = 1 if len(MASKS) > 1 and DEMO_WORDS_PATH is not None else 0
    print(f"[cfg] {len(MASKS)} masks loaded — press T to cycle: "
          + " / ".join(f"{n}({'all' if m is None else len(m)})" for n, m in MASKS))

    # An INDEX, not the tuple: MASKS.index(tuple_with_ndarray) compares arrays elementwise
    # and raises "truth value of an array is ambiguous".
    _active = [mask_i]

    def cycle_topic():
        """Next mask. NOTE the gate is NOT rescaled: _mask_probs renormalizes, so a narrower
        mask makes the same threshold looser (measured: 35% out-of-domain false accepts at
        L2_CONF 0.40 on a 43-word mask vs 2% at 0.90). Switching to a much smaller topic
        without raising --conf trades precision for throughput."""
        _active[0] = (_active[0] + 1) % len(MASKS)
        name, m = MASKS[_active[0]]
        globals()["ALLOWED_IDX"] = m            # what _mask_probs reads, at module scope
        n = len(words) if m is None else len(m)
        print(f"[topic] {name}  ({n} words)")
        if m is not None:
            print("   " + ", ".join(words[i] for i in m))
        return name, n

    def active_topic():
        name, m = MASKS[_active[0]]
        return name, (len(words) if m is None else len(m))

    ALLOWED_IDX = MASKS[mask_i][1]

    rules = load_grammar()
    word_acc = {}
    if WORD_ACC_PATH is not None and WORD_ACC_PATH.exists():
        try:
            word_acc = {k: v for k, v in json.loads(WORD_ACC_PATH.read_text(encoding="utf-8")).items()
                        if isinstance(v, (int, float))}
            print(f"[ok] per-word accuracy loaded ({len(word_acc)} words)")
        except Exception as e:
            print(f"[warn] {WORD_ACC_PATH.name} not loaded ({e})")
    _keep, fns = load_models(SINGLE_MODELS if single else ENSEMBLE_MODELS)
    predict(fns, np.zeros((1, MAX_LEN, N_POINTS, N_RAW_CH), np.float32))  # warm the graph
    if len(words) <= 40:
        print(f"\n{len(words)} words you can sign:\n  " + ", ".join(words) + "\n")
    else:
        print(f"\n{len(words)} words loaded (list hidden — too many to display).\n")

    holistic = mp.solutions.holistic.Holistic(
        model_complexity=0 if fast else MP_COMPLEXITY,
        min_detection_confidence=MP_DET_CONF, min_tracking_confidence=MP_TRK_CONF,
        smooth_landmarks=False)                      # OFF: at ~7fps the smoother lags the sign
                                                     #   ONSET (the motion the model keys on) more
                                                     #   than jitter hurts; resample+normalize
                                                     #   already suppress jitter downstream.
    drawer = mp.solutions.drawing_utils

    gloss_buf: list[str] = []       # the words signed so far, in order
    cand_buf: list[list[str]] = []  # per position: top-K candidate words (LM rescoring on DONE)
    sentence = ""                   # gloss_buf rendered to a spoken sentence
    now_line = "sign a word"
    last_conf = 0.0                 # confidence of the last committed word
    # sign-segmentation state (auto-commit)
    seg: list = []                  # normalized frames of the sign in progress
    seg_active = False
    seg_hands = 0                   # frames in seg with a detected hand
    still_count = 0
    seg_moved = False               # did real motion (mv > MOTION_EPS) happen this segment?
    nohand_count = 0
    prev_norm = None
    cooldown = 0                    # frames left before a new sign may start
    prev_preview = None             # last confident preview word (early commit)
    preview_run = 0                 # consecutive identical previews (adaptive commit)
    hand_run = 0                    # consecutive hand frames while idle (start debounce)
    last_commit = ("", 0.0)         # (word, time) — duplicate suppression
    vote_hist = deque(maxlen=8)     # recent top-1 preview words — temporal voting (Part 5)
    # developer dashboard state (Part 13) — updated each preview/commit, drawn if --debug
    dbg = {"word": "-", "conf": 0.0, "second_word": "-", "second": 0.0, "margin": 0.0,
           "quality": 0.0, "frames": 0, "decision": "-", "level": 0, "reason": "idle"}
    preroll = deque(maxlen=PRE_ROLL)  # recent frames from before the hand appears
    hand_hist = deque(maxlen=24)    # recent hand-detected flags (capture-quality coach)
    center_luma = 255.0             # brightness of the signer region (capture-quality coach)

    speaker = Speaker()
    # UI state shared with the mouse callback. *_box = (x1,y1,x2,y2) click regions,
    # refreshed each frame. finalized = a sentence has been committed via DONE.
    state = {"speak": False, "sentence": "", "final": "", "finalized": False,
             "thinking": False, "clear_req": False, "done_req": False,
             "undo_req": False, "show_words": len(words) <= 40,  # word list ON for small vocab
             "done_box": (0, 0, 0, 0), "undo_box": (0, 0, 0, 0),
             "clear_box": (0, 0, 0, 0), "speak_box": (0, 0, 0, 0),
             "words_box": (0, 0, 0, 0),
             # top-K "pick to fix" candidates from the last sign
             "candidates": [],          # [(word, prob), ...] top-K of the last sign
             "cand_committed": False,    # was top-1 auto-appended? (pick => replace vs append)
             "cand_boxes": [],           # click regions for the candidate chips
             "pick_req": None}           # index (0-based) a click requested; handled in the loop
    WINDOW = "Deafference - live ASL demo"

    # full-screen canvas size (physical pixels — SetProcessDPIAware so OpenCV's
    # fullscreen maps 1:1 and the button click-regions line up with the mouse).
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
        SCREEN_W = ctypes.windll.user32.GetSystemMetrics(0)
        SCREEN_H = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        SCREEN_W, SCREEN_H = 1600, 900
    TOP_H, BOT_H = 120, 78                                    # bar heights

    def finalize(glosses, cands=None):
        """Finished gloss buffer -> a spoken sentence.

        --ai  : the sentence is built ENTIRELY by the AI (Gemini/Claude). No rule
                fallback — if the AI can't be reached we surface the error so it's
                obvious the AI (not a script) is doing the work. When per-sign
                top-K candidates are available we use LM RESCORING (#12): the AI
                picks the most coherent reading per position, so sentence context
                can fix a wrong top-1 (hat->hello, foot->food).
        default: the offline rule engine (grammar_rules.json)."""
        if ai_enabled:
            try:
                import grammar_eval
                if (cands and len(cands) == len(glosses)
                        and hasattr(grammar_eval, "ai_generate_rescore")):
                    return grammar_eval.ai_generate_rescore([list(c) for c in cands])
                return grammar_eval.ai_generate(list(glosses))   # AI only, verbatim
            except Exception as e:
                return f"(AI unavailable: {type(e).__name__})"
        return render_sentence(rules, list(glosses))

    def do_done():
        """Commit the current signs into a spoken sentence. The AI path runs off
        the main thread so the video never freezes while it thinks."""
        snap = list(gloss_buf)
        cand_snap = [list(c) for c in cand_buf]      # per-position top-K, for LM rescoring
        if not snap or state["thinking"]:
            return
        if ai_enabled:
            state["thinking"] = True

            def work():
                out = finalize(snap, cand_snap)
                state["final"] = out; state["sentence"] = out
                state["finalized"] = True; state["thinking"] = False
                speaker.say(out)

            threading.Thread(target=work, daemon=True).start()
        else:
            out = finalize(snap, cand_snap)
            state["final"] = out; state["sentence"] = out; state["finalized"] = True
            speaker.say(out)

    def commit_segment(pre_probs=None):
        """Classify the just-finished sign (resampled to 64 frames + mirror TTA)
        and, if confident, add the word to the sentence + speak it live.
        pre_probs: if given (early commit), TRUST the preview's probs instead of
        re-running the ensemble — keeps the approve/commit decision consistent."""
        nonlocal seg, seg_active, sentence, now_line, last_conf
        nonlocal nohand_count, cooldown, prev_preview, last_commit, seg_hands
        # RESPONSE LATENCY (#lat). Two components, deliberately reported apart:
        #   detect_ms — the wait before we even know the sign ended: still_fr frames at the live
        #               rate. Deterministic, and ZERO on the early-commit path, which fires while
        #               the hand is still moving.
        #   infer_ms  — everything after that: classification, the gates, TTS dispatch.
        # Without this there is no way to tell whether a threshold change helped, and an
        # unfalsifiable change is the one mistake this project has paid for most.
        _t_enter = time.time()
        _detect_ms = 0.0 if pre_probs is not None else (still_fr / max(_fps, 1.0)) * 1000.0
        _lat_path = "early" if pre_probs is not None else "still"
        s, seg, seg_active = seg, [], False
        if nohand_count:                                 # drop the hands-down tail
            s = s[:max(0, len(s) - nohand_count)]
        nohand_count = 0
        cooldown = cooldown_fr
        prev_preview = None
        active = max(0, len(s) - preroll_n)              # frames of ACTUAL signing (excl pre-roll)
        if active < min_seg_fr or seg_hands < min_hand_fr:  # blip, not a real sign
            now_line = "sign a word"
            return
        sig = trim_preroll(s, preroll_n, lead_fr)   # motion-dominated clip (drop static pre-roll)
        # Early commit trusts the preview probs (the fold-0 preview already APPROVED); pause
        # commits (pre_probs=None) use the robust multi-view ensemble. This removes the
        # "preview locks on the right word but the ensemble re-scores and rejects it" retry.
        probs = pre_probs if pre_probs is not None else classify_commit(fns, sig)
        order = probs.argsort()[::-1]
        idx = int(order[0]); conf = float(probs[idx]); word = words[idx]
        second = float(probs[order[1]]) if len(order) > 1 else 0.0
        last_conf = conf
        q, hp = segment_quality(sig)                 # quality on the signing (not the pre-roll)
        print(f"[seg] {len(s):3d}f act{active} sig{len(sig)} hp{hp * 100:.0f}% q{q:.2f} -> "
              + "  ".join(f"{words[i]}:{probs[i]:.2f}" for i in order[:3]))
        # QUALITY GATE (#1): a clip where the hand was rarely seen is near-NaN, so the
        # model collapses onto priors (the log's bed/fireman on 25%-hand clips). Refuse
        # to commit such junk — accept only a VERY confident+decisive guess (this keeps
        # genuine quick signs like a distinct 'uncle'), else coach the user to fix capture.
        if q < QUALITY_MIN or hp < HANDPRESENCE_MIN:
            if not (conf >= POOR_CONF and (conf - second) >= POOR_MARGIN):
                now_line = f"didn't see your hands ({hp * 100:.0f}%) - more light / hands in frame"
                state["candidates"] = []; state["cand_committed"] = False
                return
        # top-K candidates for the pick-to-fix UI (only for clips we might commit).
        k = min(SHOW_TOPK, len(order)) if SHOW_TOPK else 0
        state["candidates"] = [(words[int(order[j])], float(probs[int(order[j])]))
                               for j in range(k)]
        # DECISION ENGINE at the pause: the sign is FINISHED, so temporal confirmation
        # is already satisfied (stable=L2_STABLE) -> accept LEVEL 1 & 2, reject only
        # LEVEL 3 (weak/ambiguous). This is exactly where HELLO 0.61 / HAT 0.20 (a
        # LEVEL-2 prediction the old 0.78 gate rejected) now commits.
        action, level, reason = decide_commit(conf, second, q, stable=L2_STABLE)
        dbg.update(word=word, second_word=words[int(order[1])] if len(order) > 1 else "-",
                   conf=conf, second=second, margin=conf - second, quality=q,
                   frames=len(s), decision=action.upper(), level=level, reason=reason)
        if action == "reject" and pre_probs is None:
            # weak/ambiguous: DON'T force a wrong word — surface the top-K so the
            # signer taps the right one (1-5) instead of re-signing (solution #6).
            now_line = "not sure - tap 1-5 below, or sign again"
            state["cand_committed"] = False          # nothing appended; chips are choices
            return
        w, t = last_commit                               # same word twice within DUP_SECONDS =
        if word == w and time.time() - t < DUP_SECONDS:  # one held sign, not two -> do NOT
            return                                       #   paint it committed (was a bug)
        now_line = f"{word}  ({conf:.2f})"
        state["cand_committed"] = True               # top-1 appended -> a pick REPLACES it
        last_commit = (word, time.time())
        LAT_LOG.append((_lat_path, _detect_ms, (time.time() - _t_enter) * 1000.0))
        if state["finalized"]:                           # new sign after DONE = fresh sentence
            gloss_buf.clear(); cand_buf.clear(); sentence = ""
            state["final"] = ""; state["finalized"] = False
        gloss_buf.append(word)
        cand_buf.append([w for (w, _p) in state["candidates"]])   # top-K for LM rescoring
        sentence = "" if ai_enabled else render_sentence(rules, gloss_buf)
        state["sentence"] = sentence
        if state["speak"]:
            speaker.say(rules["display"].get(word, word) if rules else word)

    def pick_candidate(i: int):
        """Signer picked candidate i (0-based) from the last sign's top-K chips —
        commit it, or CORRECT the last word to it. This is the top-k fix
        (solution #6): with 250 classes the right word is nearly always in the
        top 2-3 even when #1 is wrong, so one tap beats re-signing."""
        nonlocal sentence, last_commit, now_line
        cands = state["candidates"]
        if not cands or i < 0 or i >= len(cands):
            return
        chosen = cands[i][0]
        if state["cand_committed"]:                  # top-1 was appended -> replace it
            if gloss_buf and gloss_buf[-1] == chosen:
                return                               # already the chosen word
            if gloss_buf:
                gloss_buf[-1] = chosen
                if cand_buf:
                    cand_buf[-1] = [chosen]          # user picked -> lock it (rescoring won't override)
        else:                                        # was "not sure" -> append the pick
            if state["finalized"]:                   # first sign after DONE = fresh sentence
                gloss_buf.clear(); cand_buf.clear()
                state["final"] = ""; state["finalized"] = False
            gloss_buf.append(chosen)
            cand_buf.append([chosen])                # locked single choice
            state["cand_committed"] = True
        last_commit = (chosen, time.time())
        LAT_LOG.append((_lat_path, _detect_ms, (time.time() - _t_enter) * 1000.0))
        now_line = f"{chosen}  (picked)"
        sentence = "" if ai_enabled else render_sentence(rules, gloss_buf)
        state["sentence"] = sentence
        if state["speak"]:
            speaker.say(rules["display"].get(chosen, chosen) if rules else chosen)

    def _inside(box, mx, my):
        x1, y1, x2, y2 = box
        return x1 <= mx <= x2 and y1 <= my <= y2

    def on_mouse(event, mx, my, flags, _param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for ci, box in enumerate(state["cand_boxes"]):   # top-K "pick to fix" chips
            if _inside(box, mx, my):
                state["pick_req"] = ci
                return
        if _inside(state["done_box"], mx, my):
            state["done_req"] = True
        elif _inside(state["undo_box"], mx, my):
            state["undo_req"] = True
        elif _inside(state["clear_box"], mx, my):
            state["clear_req"] = True
        elif _inside(state["speak_box"], mx, my):
            state["speak"] = not state["speak"]
        elif _inside(state["words_box"], mx, my):
            state["show_words"] = not state["show_words"]

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(WINDOW, on_mouse)

    camera = Camera(0)                               # threaded capture (fresh frames)
    if not camera.opened:
        sys.exit("[err] no webcam found (VideoCapture(0) failed)")
    tts = "on (SAPI)" if speaker.available else "UNAVAILABLE"
    gen = "AI ONLY (Gemini/Claude)" if ai_enabled else "rules (offline script)"
    print(f"[ok] webcam open. Sign a word, then lower your hands / hold still — the "
          f"word is captured automatically. If the guess is wrong, tap 1-5 (or "
          f"click a chip) to fix it to the right candidate — no re-signing. Press "
          f"DONE (Enter) to speak the whole sentence. Generator: {gen}. TTS: {tts}. "
          f"bksp=undo, c=clear, q=quit.")

    def aa(img, s, org, sc, col, th=2):              # anti-aliased text helper
        cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, cv2.LINE_AA)

    _tprev = time.time(); fps_ema = 8.0          # seed ~real rate so frame-1 thresholds are sane
    # frame-count thresholds derived from fps each loop (initialized for the
    # commit_segment closure; recomputed at the top of every iteration below).
    min_seg_fr = max_seg_fr = end_fr = still_fr = min_hand_fr = preview_fr = early_min_fr = cooldown_fr = 6
    start_fr = 2
    lead_fr = 2                     # onset frames kept from pre-roll (recomputed each iter)
    preroll_n = 0                   # how many pre-roll frames are at the FRONT of seg
                                    #   (so length gates count ACTIVE signing, not pre-roll)
    mp_fail = 0                     # consecutive MediaPipe process() failures (crash guard)
    while True:
        image = camera.read()
        if image is None:                            # camera warming up
            if (cv2.waitKey(20) & 0xFF) == ord("q"):
                break
            continue
        _now = time.time(); _dt = _now - _tprev; _tprev = _now
        if _dt > 0:
            fps_ema = 1.0 / _dt if fps_ema == 0.0 else 0.8 * fps_ema + 0.2 / _dt   # faster convergence
        # convert the time-based thresholds to frame counts using the live fps
        _fps = fps_ema if fps_ema > 1.0 else 7.0     # fallback = observed rate, not 12
        min_seg_fr   = max(2,  round(MIN_SEG_SEC   * _fps))
        max_seg_fr   = max(24, round(MAX_SEG_SEC   * _fps))
        end_fr       = max(3,  round(END_SEC       * _fps))
        still_fr     = max(2,  round(STILL_SEC     * _fps))
        min_hand_fr  = max(1,  round(MIN_HAND_SEC  * _fps))
        start_fr     = max(2,  round(START_SEC     * _fps))
        preview_fr   = max(2,  round(PREVIEW_SEC   * _fps))   # never every-frame (starves fps)
        early_min_fr = max(4,  round(EARLY_MIN_SEC * _fps))
        cooldown_fr  = max(2,  round(COOLDOWN_SEC  * _fps))
        lead_fr      = max(2,  round(LEAD_SEC      * _fps))   # onset frames kept from pre-roll
        # ...and the VELOCITY threshold, which the original code left unscaled. `mv` is a
        # per-frame displacement, so at 30 fps the same hand speed yields ~1/4 the value it
        # does at 7 fps -- so the demo calls 'still' far sooner on fast hardware. Measured
        # (measure_still_runs.py): 37 words truncated mid-sign at 7 fps, 56 at 30 fps. 0.02
        # was tuned at ~7 fps, hence the anchor. OFF by default -- it changes segmentation and
        # this project does not ship untested behaviour changes. Enable with --scale-eps.
        motion_eps   = MOTION_EPS * (7.0 / _fps) if args.scale_eps else MOTION_EPS
        image = cv2.flip(image, 1)                   # mirror (selfie view)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if rgb.shape[1] > MP_MAX_W:                  # smaller frame for MediaPipe (normalized
            r = MP_MAX_W / rgb.shape[1]              # landmarks → coords unchanged), trims cost
            rgb = cv2.resize(rgb, (MP_MAX_W, int(round(rgb.shape[0] * r))))
        # MediaPipe's C++ graph can throw from wait_until_idle on an odd frame; a single
        # hiccup must DROP that frame, not crash the whole session. Skip it and continue.
        try:
            results = holistic.process(np.ascontiguousarray(rgb))
            mp_fail = 0
        except Exception as e:
            mp_fail += 1
            if mp_fail <= 3 or mp_fail % 60 == 0:
                print(f"[warn] MediaPipe dropped a frame ({mp_fail}x): {e}")
            if mp_fail >= 300:                       # persistent failure -> bail cleanly
                print("[err] MediaPipe keeps failing; ending session. Restart the demo.")
                break
            if (cv2.waitKey(5) & 0xFF) == ord("q"):  # keep quit responsive while dropping
                break
            continue

        # capture-quality coach (#1): brightness of the signer's center region +
        # rolling hand-detection rate. Cheap (mean of a small crop, once/frame).
        h_, w_ = rgb.shape[:2]
        cregion = rgb[int(h_ * 0.15):int(h_ * 0.75), int(w_ * 0.30):int(w_ * 0.70)]
        center_luma = float(cregion.mean()) if cregion.size else 255.0

        pts = extract_75(results)
        norm = normalize(pts)                        # None if no shoulders
        hand = (results.left_hand_landmarks is not None or
                results.right_hand_landmarks is not None)
        hand_hist.append(1 if hand else 0)

        # hand motion vs the previous normalized frame (shoulder-width units)
        mv = None
        if norm is not None and prev_norm is not None:
            a, b = norm[POSE_N:N_POINTS, :2], prev_norm[POSE_N:N_POINTS, :2]
            m = ~(np.isnan(a).any(1) | np.isnan(b).any(1))
            if m.any():
                mv = float(np.mean(np.abs(a[m] - b[m])))
        prev_norm = norm

        # ── sign segmentation: hands active -> collect; pause/lower -> commit ──
        if cooldown > 0:
            cooldown -= 1
        if norm is not None and hand:
            hand_run += 1                            # consecutive hand frames (start debounce)
            if not seg_active and cooldown == 0 and hand_run >= start_fr:
                seg_active = True                    # start only after the hand PERSISTS,
                seg = list(preroll)                  #   not on a single-frame flicker;
                preroll_n = len(seg)                 #   remember the pre-roll size so the
                seg_hands = 0                        #   length gates count ACTIVE signing only
                still_count = 0; nohand_count = 0    # face-signs (hello) get their
                seg_moved = False                    #   hand detected late; no motion seen yet
                prev_preview = None; preview_run = 0  #   hand detected late
                vote_hist.clear()                    # fresh temporal vote for this sign
            if seg_active:
                seg.append(norm)
                seg_hands += 1
                nohand_count = max(0, nohand_count - 1)   # decay, not hard-reset (tolerate a 1-frame flicker)
                if mv is not None and mv > motion_eps:
                    seg_moved = True                      # a real motion happened this segment
                if mv is not None and mv < motion_eps:
                    still_count += 1                      # genuinely still
                elif mv is not None:
                    still_count = 0                       # real movement -> reset the still timer
                # else mv is None (NaN-hand frame): CARRY still_count — for face-signs the hand
                #   flickers out, and a hard reset meant the hold-still commit NEVER fired,
                #   forcing a full hands-down between every sign.
                if len(seg) >= max_seg_fr:
                    commit_segment()
        else:
            hand_run = 0                             # reset the start-debounce run
            if seg_active:
                nohand_count += 1
                if norm is not None:                 # hand-detection flicker: keep
                    seg.append(norm)                 # collecting; hands are NaN in
                                                     # these frames (like training)
        if norm is not None:
            preroll.append(norm)                     # rolling pre-sign context
        if seg_active and (len(seg) - preroll_n) >= early_min_fr and len(seg) % preview_fr == 0:
            # PREVIEW + DECISION ENGINE (Parts 4-6): a cheap single-model preview
            # feeds the 3-level decision. LEVEL 1 (strong) commits instantly; LEVEL 2
            # (medium — e.g. HELLO 0.61 / HAT 0.20) commits once the word is temporally
            # STABLE; LEVEL 3 (weak) waits. Adaptive waiting falls straight out of this:
            # easy signs are instant, ambiguous ones need a couple of agreeing previews.
            sig_prev = trim_preroll(seg, preroll_n, lead_fr)   # same motion-dominated clip as commit
            p = classify_segment(fns[:1], sig_prev)
            order = p.argsort()[::-1]
            pi = int(order[0]); pc = float(p[pi]); pw = words[pi]
            p2 = float(p[order[1]]) if len(order) > 1 else 0.0
            pw2 = words[int(order[1])] if len(order) > 1 else "-"
            vote_hist.append(pw)                         # temporal voting buffer (Part 5)
            stable = 0                                   # consecutive trailing agreement
            for vw in reversed(vote_hist):
                if vw == pw:
                    stable += 1
                else:
                    break
            q_prev, _hp = segment_quality(sig_prev)
            action, level, reason = decide_commit(pc, p2, q_prev, stable)
            now_line = f"~ {pw} ({pc:.2f})"
            dbg.update(word=pw, conf=pc, second_word=pw2, second=p2, margin=pc - p2,
                       quality=q_prev, frames=len(seg), decision=action.upper(),
                       level=level, reason=reason)
            if action == "commit":
                commit_segment(pre_probs=p)          # trust the preview that just approved
        if seg_active and seg_moved and still_count >= still_fr and (len(seg) - preroll_n) >= min_seg_fr:
            commit_segment()                         # real motion + THEN hold still -> word
        elif seg_active and nohand_count >= end_fr:
            commit_segment()                         # hands lowered -> word

        # draw skeleton on the raw camera frame
        drawer.draw_landmarks(image, results.pose_landmarks,
                              mp.solutions.holistic.POSE_CONNECTIONS)
        drawer.draw_landmarks(image, results.left_hand_landmarks,
                              mp.solutions.holistic.HAND_CONNECTIONS)
        drawer.draw_landmarks(image, results.right_hand_landmarks,
                              mp.solutions.holistic.HAND_CONNECTIONS)

        # compose a FULL-SCREEN canvas: camera centered between top & bottom bars
        W, H = SCREEN_W, SCREEN_H
        cam_h = H - TOP_H - BOT_H
        s = min(W / image.shape[1], cam_h / image.shape[0])
        cw, ch = int(image.shape[1] * s), int(image.shape[0] * s)
        cam = cv2.resize(image, (cw, ch))
        image = np.zeros((H, W, 3), np.uint8)
        ox, oy = (W - cw) // 2, TOP_H + (cam_h - ch) // 2
        image[oy:oy + ch, ox:ox + cw] = cam

        # framing guide + capture indicator, drawn over the camera area
        if not seg_active and not gloss_buf and not state["finalized"]:
            gx1, gy1 = ox + int(cw * 0.30), oy + int(ch * 0.06)
            gx2, gy2 = ox + int(cw * 0.70), oy + int(ch * 0.92)
            cv2.rectangle(image, (gx1, gy1), (gx2, gy2), (90, 90, 90), 1, cv2.LINE_AA)
            aa(image, "frame yourself here", (gx1, gy1 - 10), 0.55, (120, 120, 120), 1)
        if seg_active:                               # red REC + capture progress
            cv2.circle(image, (ox + 26, oy + 30), 9, (0, 0, 255), -1, cv2.LINE_AA)
            aa(image, "capturing sign...", (ox + 44, oy + 38), 0.7, (0, 0, 255))
            fillw = int(min(1.0, len(seg) / max_seg_fr) * 240)
            cv2.rectangle(image, (ox + 24, oy + 52), (ox + 24 + fillw, oy + 62), (0, 0, 255), -1)

        # capture-quality coach (#1): warn on dark frame / undetected hand while
        # signing — the model only sees landmarks, so these silently wreck accuracy.
        hrate = (sum(hand_hist) / len(hand_hist)) if hand_hist else 1.0
        warns = []
        if center_luma < DARK_LUMA:
            warns.append("LOW LIGHT - put a lamp in FRONT of you (light your face + hands)")
        if seg_active and hrate < HANDRATE_WARN:
            warns.append("HAND NOT DETECTED - brighter light / keep hands in frame")
        for wi, wtxt in enumerate(warns):
            msg = "! " + wtxt
            (tw, _th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
            tx = ox + max(20, (cw - tw) // 2)
            ty = oy + 42 + wi * 34
            cv2.rectangle(image, (tx - 10, ty - 24), (tx + tw + 10, ty + 8), (0, 0, 0), -1)
            aa(image, msg, (tx, ty), 0.62, (0, 200, 255), 2)

        # ── TOP bar: the sentence (product output) ───────────────────────────
        cv2.rectangle(image, (0, 0), (W, TOP_H), (0, 0, 0), -1)
        aa(image, "DEAFFERENCE", (16, 34), 0.75, (0, 180, 255))
        if state["thinking"]:
            top_txt, top_col = "... building sentence (AI) ...", (0, 220, 220)
        elif state["finalized"] and state["final"]:
            top_txt, top_col = state["final"], (0, 255, 0)          # spoken result
        elif gloss_buf:
            top_txt = sentence or "(press DONE to build the sentence)"
            top_col = (0, 210, 130)
        else:
            top_txt, top_col = "sign a word", (150, 150, 150)
        aa(image, top_txt, (16, 82), 1.1, top_col)
        aa(image, "signs: " + ("   ".join(gloss_buf) if gloss_buf else "-"),
           (16, 112), 0.7, (180, 220, 255))

        # ── word-list panel in the right margin (toggle: 'w' / WORDS button) ──
        # Show ONLY the words recognition can actually output. With a --words mask
        # active, the full 250 list would advertise words the mask removes (e.g.
        # black/sleep) and the signer expects words the model can never return.
        if state["show_words"]:
            shown = [words[i] for i in ALLOWED_IDX] if ALLOWED_IDX is not None else words
            subset = ALLOWED_IDX is not None
            sfx = " (subset — only these are recognized)" if subset else ""
        if state["show_words"] and len(shown) <= 40:
            px = W - 330
            roi = image[TOP_H:H - BOT_H, px:W]
            image[TOP_H:H - BOT_H, px:W] = (roi * 0.30).astype(np.uint8)
            aa(image, f"THE {len(shown)} WORDS" + sfx, (px + 16, TOP_H + 34), 0.6, (0, 220, 255))
            for i, wd in enumerate(shown):
                cx = px + 18 + (i // 15) * 160
                cy = TOP_H + 70 + (i % 15) * 34
                lbl = f"{wd} {word_acc[wd]:.2f}" if wd in word_acc else wd
                aa(image, lbl, (cx, cy), 0.6, (235, 235, 235), 1)
        elif state["show_words"]:
            # large vocab (250): dense full-width overlay grid. If per-word accuracy
            # is available, sort best-first and color by reliability (green→red).
            roi = image[TOP_H:H - BOT_H, 0:W]
            image[TOP_H:H - BOT_H, 0:W] = (roi * 0.20).astype(np.uint8)
            order = sorted(shown, key=lambda w: word_acc.get(w, -1.0), reverse=True) if word_acc else shown
            hdr = (f"{len(shown)} WORDS{sfx} — sorted by accuracy (green=strong, red=weak) · W to hide"
                   if word_acc else f"{len(shown)} WORDS{sfx} · press W to hide")
            aa(image, hdr, (24, TOP_H + 30), 0.6, (0, 220, 255))
            y0, rowh = TOP_H + 56, 24
            rows = max(1, (H - BOT_H - y0 - 8) // rowh)
            colw = (W - 40) // int(np.ceil(len(order) / rows))
            for i, wd in enumerate(order):
                cx = 24 + (i // rows) * colw
                cy = y0 + (i % rows) * rowh + 14
                if wd in word_acc:
                    a = word_acc[wd]
                    col = ((0, 220, 0) if a >= 0.8 else (0, 220, 220) if a >= 0.6
                           else (0, 150, 255) if a >= 0.4 else (60, 90, 240))
                    aa(image, f"{wd} {a:.2f}", (cx, cy), 0.42, col, 1)
                else:
                    aa(image, wd, (cx, cy), 0.44, (225, 225, 225), 1)

        # ── top-K candidate chips ("pick to fix"): tap 1/2/3 or click to set the
        #    last word without re-signing. The green chip = the current pick; the
        #    others let you correct a wrong top-1 in one tap (solution #6). ──────
        state["cand_boxes"] = []
        cands = state["candidates"]
        if cands and not state["thinking"]:
            cy2 = H - BOT_H - 10
            cy1 = cy2 - 40
            cx = 16
            aa(image, "pick:", (cx, cy2 - 12), 0.6, (170, 170, 170), 1)
            cx += 78
            for j, (wd, pr) in enumerate(cands):
                label = f"{j + 1}. {wd} {pr:.2f}"
                wpx = 26 + int(len(label) * 13)
                sel = state["cand_committed"] and gloss_buf and gloss_buf[-1] == wd
                fill = (0, 120, 0) if sel else (55, 55, 55)
                cv2.rectangle(image, (cx, cy1), (cx + wpx, cy2), fill, -1)
                cv2.rectangle(image, (cx, cy1), (cx + wpx, cy2), (255, 255, 255), 1, cv2.LINE_AA)
                aa(image, label, (cx + 12, cy2 - 12), 0.6, (255, 255, 255), 1)
                state["cand_boxes"].append((cx, cy1, cx + wpx, cy2))
                cx += wpx + 10

        # ── BOTTOM bar: buttons (left) + live word + confidence (right) ──────
        cv2.rectangle(image, (0, H - BOT_H), (W, H), (0, 0, 0), -1)
        by1, by2 = H - BOT_H + 12, H - 18
        on = state["speak"]

        def button(x1, x2, label, fill):
            cv2.rectangle(image, (x1, by1), (x2, by2), fill, -1)
            cv2.rectangle(image, (x1, by1), (x2, by2), (255, 255, 255), 2, cv2.LINE_AA)
            aa(image, label, (x1 + 12, by2 - 14), 0.6, (255, 255, 255))
            return (x1, by1, x2, by2)

        state["done_box"]  = button(12, 140, "DONE", (0, 150, 0))
        state["undo_box"]  = button(150, 278, "UNDO", (150, 90, 0))
        state["clear_box"] = button(288, 416, "CLEAR", (40, 40, 200))
        state["speak_box"] = button(426, 596, f"SPEAK {'ON' if on else 'off'}",
                                    (0, 150, 0) if on else (70, 70, 70))
        state["words_box"] = button(606, 734, "WORDS", (90, 90, 90))

        aa(image, now_line, (770, H - BOT_H + 34), 0.85, (0, 255, 0))
        # confidence bar for the last committed word
        cv2.rectangle(image, (770, H - 30), (770 + 300, H - 16), (60, 60, 60), 1)
        bar_col = (0, 200, 0) if last_conf >= CONF_GATE else (0, 165, 255)
        cv2.rectangle(image, (770, H - 30), (770 + int(300 * last_conf), H - 16), bar_col, -1)
        aa(image, f"{last_conf:.2f}", (770 + 310, H - 18), 0.5, (200, 200, 200), 1)
        aa(image, f"{fps_ema:.0f} fps   1-5=fix  Enter=say  bksp=undo  q=quit", (W - 620, H - 20), 0.55, (170, 170, 170), 1)

        # ── developer dashboard (Part 13): live decision internals, for tuning ──
        if debug:
            dx, dy, dw, dh = W - 372, TOP_H + 16, 356, 250
            roi = image[dy:dy + dh, dx:dx + dw]
            if roi.size:
                image[dy:dy + dh, dx:dx + dw] = (roi * 0.25).astype(np.uint8)
            lvl_col = ((0, 220, 0) if dbg["level"] == 1 else (0, 210, 210)
                       if dbg["level"] == 2 else (0, 140, 255))
            lines = [
                ("DEBUG  (decision engine)", (0, 200, 255)),
                (f"word    : {dbg['word']}  {dbg['conf']:.2f}", (235, 235, 235)),
                (f"2nd     : {dbg['second_word']}  {dbg['second']:.2f}", (200, 200, 200)),
                (f"margin  : {dbg['margin']:.2f}", (200, 200, 200)),
                (f"quality : {dbg['quality'] * 100:.0f}%", (200, 200, 200)),
                (f"frames  : {dbg['frames']}", (200, 200, 200)),
                (f"decision: {dbg['decision']}  (LEVEL {dbg['level']})", lvl_col),
                (f"reason  : {dbg['reason']}", (170, 210, 170)),
                (f"topic   : {active_topic()[0]}  ({active_topic()[1]} words)  [T]",
                 (0, 200, 255)),
            ]
            for i, (txt, col) in enumerate(lines):
                aa(image, txt, (dx + 12, dy + 28 + i * 27), 0.5, col, 1)

        cv2.imshow(WINDOW, image)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if state["pick_req"] is not None:                # a candidate chip was clicked
            pick_candidate(state["pick_req"]); state["pick_req"] = None
        if key in (ord("1"), ord("2"), ord("3"), ord("4"), ord("5")):  # pick candidate 1-5 (fix top-1)
            pick_candidate(key - ord("1"))
        if key in (13, 10) or state["done_req"]:         # Enter / DONE button
            state["done_req"] = False; state["candidates"] = []; do_done()
        if key in (8, ord("z")) or state["undo_req"]:    # backspace / UNDO button
            state["undo_req"] = False
            if gloss_buf:
                gloss_buf.pop()
                if cand_buf:
                    cand_buf.pop()                       # keep per-sign candidates aligned
                sentence = "" if ai_enabled else render_sentence(rules, gloss_buf)
                state["sentence"] = sentence
                state["final"] = ""; state["finalized"] = False
                state["candidates"] = []; state["cand_committed"] = False
        if key == ord("t"):
            tname, tn = cycle_topic()
            now_line = f"topic: {tname} ({tn} words)"
            state["candidates"] = []                     # stale: scored under the old mask
        if key == ord("s"):
            state["speak"] = not state["speak"]
        if key == ord("w"):
            state["show_words"] = not state["show_words"]
        if key == ord(" "):
            say_now = state["final"] or sentence
            if say_now:
                speaker.say(say_now)
        if key == ord("c") or state["clear_req"]:
            gloss_buf.clear(); cand_buf.clear(); sentence = ""; now_line = "sign a word"; last_conf = 0.0
            seg = []; seg_active = False
            state["sentence"] = ""; state["final"] = ""
            state["finalized"] = False; state["clear_req"] = False
            state["candidates"] = []; state["cand_committed"] = False

    camera.release(); cv2.destroyAllWindows(); holistic.close()

    # ── response latency, measured (#lat) ────────────────────────────────────────────────
    # The number to compare against a latency target. Reported per PATH because the two are
    # different products: an early commit lands while the hand is still moving (detect_ms = 0),
    # a still commit must first wait out still_fr frames. A mean over both hides that.
    if LAT_LOG:
        import statistics as _st

        def _pct(xs, q):
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(round(q / 100.0 * (len(xs) - 1))))]

        print("")
        print(f"[lat] {len(LAT_LOG)} commits   path      n   detect_ms      infer_ms       total")
        for path in ("early", "still"):
            rows = [(d, i) for p_, d, i in LAT_LOG if p_ == path]
            if not rows:
                continue
            det = [d for d, _ in rows]; inf = [i for _, i in rows]
            tot = [d + i for d, i in rows]
            print(f"[lat] {'':16s}{path:<7s}{len(rows):>4}  "
                  f"{_st.median(det):>6.0f}       {_st.median(inf):>6.0f}  "
                  f"p50 {_st.median(tot):>6.0f}  p95 {_pct(tot, 95):>6.0f}")
        allt = [d + i for _p, d, i in LAT_LOG]
        print(f"[lat] overall p50 {_st.median(allt):.0f} ms   p95 {_pct(allt, 95):.0f} ms   "
              f"(target from review: 200-500 ms)")
        slow = sum(1 for t in allt if t > 500)
        print(f"[lat] {slow}/{len(allt)} commits over 500 ms "
              f"({slow / len(allt) * 100:.0f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live ASL demo (30- or 250-word)")
    ap.add_argument("--selftest", action="store_true",
                    help="no camera: load model + predict on random input")
    ap.add_argument("--no-scale-eps", dest="scale_eps", action="store_false",
                    help="revert to the fps-INVARIANT MOTION_EPS. Only for comparing against the "
                         "pre-2026-08-25 behaviour; it truncates 37 words mid-sign at 7fps and 56 "
                         "at 30fps (measure_still_runs.py).")
    ap.set_defaults(scale_eps=True)
    ap.add_argument("--single", action="store_true",
                    help="use only fold-0 (faster) instead of the ensemble")
    ap.add_argument("--vocab250", action="store_true",
                    help="use the 250-word model (artifacts_250/ + vocab_250.json) "
                         "instead of the default 30-word demo")
    ap.add_argument("--conf", type=float, default=None,
                    help="override the commit confidence gate (sets BOTH L1_CONF and L2_CONF, "
                         "the thresholds decide_commit actually reads). Measured on the 250 "
                         "ensemble (measure_conf_gate.py): 0.40 -> 64%% commit / 0.950 prec, "
                         "0.58 -> 52%% / 0.977, and precision is FLAT above 0.58 while "
                         "throughput keeps falling. Raising it past 0.58 buys nothing.")
    ap.add_argument("--ai", action="store_true",
                    help="build sentences with the AI (Gemini) on DONE, falling "
                         "back to rules. Needs GEMINI_API_KEYS set + internet.")
    ap.add_argument("--fast", action="store_true",
                    help="lighter MediaPipe pose model (~2x fps, but MUCH weaker hand "
                         "detection near the face — hello/food/hat suffer). NOT "
                         "recommended for --vocab250; prefer good lighting instead.")
    ap.add_argument("--canonical", action="store_true",
                    help="the weights were trained with train.py --canonical-hand (dominant "
                         "hand always at 54-74, 33-53 reserved). Mirrors each segment so the "
                         "signing arm reads as right, and switches mirror TTA to the pose-only "
                         "map. REQUIRED for canonical weights: without it a left-dominant "
                         "signer's hand stays in a block the model has never seen. Must NOT be "
                         "set for the legacy artifacts_250 weights.")
    ap.add_argument("--words", default=None,
                    help="path to a JSON list of words to restrict recognition to "
                         "(e.g. demo_vocab_250.json). Concentrates confidence onto "
                         "the allowed words so they commit on the first try.")
    ap.add_argument("--debug", action="store_true",
                    help="developer dashboard overlay: live conf / 2nd / margin / "
                         "hand-quality / frames / decision + reason (Part 13). For tuning.")
    args = ap.parse_args()
    if args.words:
        DEMO_WORDS_PATH = Path(args.words)
    if args.vocab250:                      # switch to the 250-word ensemble (folds 0-3)
        ARTIFACTS = HERE / "artifacts_250"
        VOCAB_PATH = HERE / "vocab_250.json"
        WORD_ACC_PATH = HERE / "word_acc_250.json"   # optional; shown in word panel if present
        ENSEMBLE_MODELS = [ARTIFACTS / f"savedmodel_fold{k}" for k in range(4)]
        SINGLE_MODELS = [ARTIFACTS / "savedmodel_fold0"]
        # 250-class confidence runs lower than 30-class; make committing fast + forgiving:
        CONF_GATE     = 0.42   # gentler gate for 250 (robust multi-view commit keeps
                               #   quality up); override with --conf
        EARLY_CONF    = 0.42   # min preview conf to early-commit (= CONF_GATE) — was 0.55
        EARLY_SURE    = 0.72   # sure on ONE preview -> instant commit — was 0.78 (the ~0.8 "wall")
        PREVIEW_SEC   = 0.20   # preview more often
        # MEASURED trade, not a preference (measure_prefix_accuracy.py, 7fps sim):
        #   0.45s -> 3 frames -> 0.372 top-1   (81 of 250 words lost vs the full clip)
        #   0.80s -> 6 frames -> 0.532 top-1   (39 lost)      <- +16 points
        #   1.00s -> 7 frames -> 0.600 top-1   (26 lost)      diminishing past here
        # The instrumented run (28 commits) had p50 latency 0ms and p95 447ms against a
        # 500ms target, so 0.45 was buying speed nobody needed with accuracy that mattered.
        # 0.80 keeps the early path inside the target (~350ms) and recovers 42 of 81 words.
        EARLY_MIN_SEC = 0.80
        STILL_SEC     = 0.40   # commit a bit sooner once you hold still
        END_SEC       = 0.60   # tolerate brief hand-detection gaps (was 0.50) -> fewer early cuts
        MAX_SEG_SEC   = 3.0    # force-commit ceiling (5.0->3.0: a stuck segment recovers faster)
        PRE_ROLL      = 12     # more onset context for face-signs (was 8)
        SHOW_TOPK     = 5      # full 250: top-1 is unreliable (0.76 mean) but the right
                               #   word is almost always in the top-5 -> tap 1-5 to fix.
                               #   This is the PRIMARY interaction at 250, not a fallback.
        # THE decisive gate fix. decide_commit() reads L1_*/L2_*/Q_STRONG. CONF_GATE is NOT a
        # decision threshold — only the bottom-bar bar colour compares against it — and neither
        # is EARLY_SURE's sibling CONF_GATE below. `--conf` used to write CONF_GATE alone and so
        # changed nothing; it now retargets L1_CONF/L2_CONF (see the --conf handler).
        # At 250 classes a CORRECT sign often scores only ~0.45 with a narrow margin; the 30-word
        # thresholds rejected it -> "sign it again". Lower the gates decide_commit ACTUALLY uses:
        #
        # MEASURED (measure_conf_gate.py, 2026-08-25, 4-fold ensemble, 250 exemplars @ 7 fps,
        # ungated ceiling 0.696 — read as a SHAPE, absolutes are inflated by training data):
        #   gate  accept  precision        These settings are AT THE KNEE. Precision saturates
        #   0.40    64%     0.950          at 0.58 and is FLAT or worse above it (0.976 / 0.972
        #   0.50    59%     0.959          / 0.976 / 0.961 at 0.60 / 0.70 / 0.80 / 0.90) while
        #   0.58    52%     0.977  <- L1   throughput keeps collapsing to 20%. Raising the gate
        #   0.70    42%     0.972          past 0.58 buys NOTHING. L2 0.40 -> 0.50 is +0.009 at
        #   0.90    20%     0.961          -5 pts accept, inside the n=250 SE (~0.03): no change.
        # Level split at the shipped values: L1 131 accepts @ 0.977, L2 30 @ 0.833 — the confirm
        # path is the weaker half. 89 words never commit; 21 of them had the CORRECT top-1, so
        # the gate spends 21 right words to remove 68 wrong ones. Those 89 fall through to the
        # top-K tap, which SHOW_TOPK below documents as the PRIMARY 250-word interaction.
        L1_CONF   = 0.58       # instant-commit conf (was 0.70 — never reached at 250)
        L1_MARGIN = 0.18       # instant-commit margin (was 0.30 — mass is spread at 250)
        Q_STRONG  = 0.45       # let face-signs (hand_presence ~0.5) reach instant commit
        L2_CONF   = 0.40       # confirm-commit floor (was 0.50 — sat ABOVE the ~0.45 mode)
        L2_MARGIN = 0.10       # a narrow-but-decisive win is enough at 250 (was 0.18)
        # DO NOT "tune" the two margins for accuracy. Ablating them to 0.0 reproduces the accept
        # set EXACTLY at every gate from 0.40 up (0.950 / 0.959 / 0.977 / 0.976 / 0.972 / 0.976
        # / 0.961 — identical columns), because at 250 classes anything clearing conf 0.40 has
        # already won by more than 0.10. They still do real work, just not on precision: they
        # route a word between LEVEL 1 (instant) and LEVEL 2 (wait for L2_STABLE previews), so
        # they are a LATENCY control. Margins only affect *whether* a word commits below 0.40.
        L2_STABLE = 2          # two agreeing previews. Was 1 because a 4-frame window at
                               #   ~7fps had no room for a second; EARLY_MIN_SEC 0.80 with
                               #   PREVIEW_SEC 0.20 leaves room for four.
        USE_TTA       = False  # live PREVIEW stays single-pass; the COMMIT does its
                               #   own multi-view+mirror averaging (classify_commit)
        # The 30-word rule grammar can't cover 250 words, so the sentence on DONE is
        # built by the AI. Auto-enable it here → `--vocab250` alone gives DONE->AI.
        args.ai = True
        if args.fast:
            print("[warn] --fast (pose complexity 0) cripples hand-at-face detection "
                  "(hello/food/hat) at 250 words. Strongly recommend running WITHOUT --fast.")
        print(f"[cfg] 250-word model from {ARTIFACTS} "
              f"(complexity-1 MediaPipe, hand-quality gate, robust commit, AI on DONE)")
    if args.canonical:
        CANONICAL_HAND = True
        print("[cfg] CANONICAL weights: segments mirrored so the signing arm reads as right "
              "(hand -> 54-74),\n      mirror TTA uses the pose-only map. Do NOT use this with "
              "the legacy artifacts_250.")
    if args.conf is not None:
        # THE FIX. This used to set CONF_GATE alone — which the comment at the top of the
        # --vocab250 branch above already calls dead, because decide_commit() reads L1_CONF /
        # L2_CONF and never looks at CONF_GATE. So `--conf 0.7` changed the colour of the UI
        # bar and NOTHING about which words committed. Point it at the real gates.
        # CONF_GATE is still assigned because the bottom-bar bar colour compares against it.
        L1_CONF = L2_CONF = CONF_GATE = args.conf
        print(f"[cfg] commit gate: L1_CONF = L2_CONF = {args.conf} "
              f"(margins unchanged: L1 {L1_MARGIN}, L2 {L2_MARGIN})")
    elif args.words:
        # A footgun worth shouting about. _mask_probs RENORMALIZES over the allowed classes, so
        # narrowing inflates every confidence and the SAME gate becomes much looser. Measured
        # (measure_conf_gate.py --words vocab_clinical_43.json): with 43 of 250 classes allowed,
        # the 207 masked-out words still commit 35% of the time at L2_CONF 0.40 -- and every one
        # of those is wrong by construction, because the true class was masked away. At 0.90 it
        # is 2%, and narrowed precision is flat from 0.30 to 0.90, so the gate is nearly free to
        # raise. No formula is applied here on purpose: the right value depends on how far you
        # narrowed, and guessing one silently is how this project lost three months.
        print("[warn] --words without --conf. Narrowing RENORMALIZES the softmax, so the "
              "default gate\n       is effectively much looser: a 43-word mask commits 35% of "
              "out-of-domain signs\n       at L2_CONF 0.40 vs 2% at 0.90. Strongly consider "
              "--conf 0.85-0.90.")
    if args.selftest:
        selftest(args.single)
    else:
        main(args.single, args.ai, args.fast, args.debug)
