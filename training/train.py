#!/usr/bin/env python3
"""
ASL MVP — training script (Track A, Phase 4, P4.2 — accuracy-push revision).

Trains a 1D CNN + Transformer sign classifier on the preprocessed Kaggle
`asl-signs` data. Two modes:

  1. 30-word MVP training (default) — classes from vocab_30.json.
  2. --all-words pretraining — trains on ALL words in the manifest (250
     classes, ~80k sequences). Save its weights, then fine-tune the 30-word
     model from them with --init-from. This is the single biggest accuracy
     lever we own: 8x more data teaches the backbone what signing looks like
     before it specializes. (External datasets like WLASL/MS-ASL are
     research-only licenses — NOT usable for this commercial product.)

Accuracy levers in this revision (vs. the first fold-0 run at 0.688):
  * Label smoothing 0.1 RESTORED (first run silently fell back to plain CCE —
    sparse CCE has no label_smoothing arg; now one-hot + CategoricalCrossentropy).
  * Stronger augmentation: temporal crop + resample, affine with shear,
    landmark dropout (random points NaN'd -> zeroed in-model), temporal cutout.
  * LateDropout raised 0.5 -> 0.7 (safe now that AWP is off; the observed
    train 0.98 / val 0.69 gap says regularize harder).
  * Weight decay 1e-5 -> 1e-4.
  * Longer patience (30) — heavier augmentation needs more epochs to converge.
  * 250-class pretraining + fine-tune flow (--all-words / --init-from).
  * hflip: ON (2026-07-15) — mirror left<->right via FLIP_MAP (received from
    the preprocessing teammate for the exact 75-point layout). p=0.5, negates
    x in the shoulder-centered coord space. The biggest remaining lever;
    expected +2-4%.

Key design decisions (locked, see BACKEND_TASKS.md Phase 4):
  * Feature engineering (z-drop + dx/dx2) EMBEDDED as the model's first layer.
  * MAX_LEN = 64 frames — also frontend #20's sliding-window length.
  * NaN = padding sentinel (real frames contain no NaN; browser windows are
    always full so padding never occurs at inference).
  * AWP: OFF by default — hand-rolled version destabilized training
    (collapse at epoch 15, 2026-07-14). Behind --awp until properly fixed.

Usage:
  # standard 30-word fold-0
  python train.py --data-dir ./data --fold 0

  # the accuracy-push path:
  python train.py --data-dir ./data --all-words --fold 0 --epochs 80 \
      --save-weights backbone_250.weights.h5
  python train.py --data-dir ./data --fold 0 --init-from artifacts/backbone_250.weights.h5 \
      --lr 2e-4

  # full 5-fold CV (after fold 0 looks good)
  python train.py --data-dir ./data --fold all --init-from artifacts/backbone_250.weights.h5
"""
from __future__ import annotations

import argparse
import json
import os

# MUST precede `import tensorflow` — the flag is read at import time.
# This file is written against Keras 2. On Keras 3 (TF >= 2.16, which is what Kaggle ships)
# transformer_block() dies with "A KerasTensor cannot be used as input to a TensorFlow
# function" at tf.matmul(mask, mask) — symbolic KerasTensors no longer accept raw tf ops.
# Every successful run so far happened to be invoked as `TF_USE_LEGACY_KERAS=1 python
# train.py`, so the dependency was real but invisible; a plain `python train.py` failed
# 3 minutes in. build_sign_clips.py has always set this itself — now train.py does too,
# so correctness no longer depends on how the caller happens to invoke it.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

# --mask-resting-hand needs the SAME alignment test the exemplar selector uses. Importing it
# rather than reimplementing it is deliberate: two sides computing "which hand is signing"
# from separate code is exactly how the 249-of-250 wrong-hand export happened (root cause R4
# in docs/MODEL_250_MVP_REPORT.md). Kaggle stages the code flat, a local checkout has this
# file in training/, so both layouts are put on the path — same pattern as build_sign_clips.py.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))
try:
    from sign_landmarks import canonicalize_missing, hand_arm_alignment  # noqa: E402
except ImportError:                     # training still runs; only the mask is unavailable
    canonicalize_missing = hand_arm_alignment = None

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
MAX_LEN = 64          # frames per window — HANDOFF NUMBER for frontend #20
N_POINTS = 75         # landmark points per frame (preprocessing output)
N_RAW_CH = 3          # x, y, z as stored in the .npz files

# Horizontal-flip (mirror) map for hflip augmentation. Ground truth from the
# preprocessing teammate's exact 75-point layout (2026-07-15):
#   slots  0-32  = MediaPipe Holistic POSE   (indices 0-20 -> 0-32)
#   slots 33-53  = LEFT hand  (MediaPipe left_hand  0-20)
#   slots 54-74  = RIGHT hand (MediaPipe right_hand 0-20)
# Coords are shoulder-midpoint centered + shoulder-width scaled, so a mirror is
# x -> -x (NOT 1-x). FLIP_MAP[i] = slot i becomes after mirroring; self-inverse.
# Verified: valid permutation, pose L/R pairs anatomically correct, whole
# left-hand block <-> right-hand block. See BACKEND_TASKS.md P4.6.
FLIP_MAP = np.array([
    0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
    22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31,          # pose 0-32
    54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67,  # left hand -> right
    68, 69, 70, 71, 72, 73, 74,
    33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46,  # right hand -> left
    47, 48, 49, 50, 51, 52, 53,
], dtype=np.int32)
assert FLIP_MAP.shape[0] == N_POINTS and sorted(FLIP_MAP.tolist()) == list(range(N_POINTS))

# ── CANONICAL-HAND layout (--canonical-hand, data from extract_canonical.py) ───
# Measured 2026-08-11 against raw GISLR: the corpus records ONE hand per
# participant (BOTH hands live in 1.7% of clips, both-hand frames mean 0.1%).
# extract_canonical.py therefore parks the DOMINANT hand at 54-74 always, mirroring
# left-dominant signers, and leaves 33-53 reserved/NaN (Phase 1 face landmarks).
#
# On that layout FLIP_MAP above is actively WRONG: swapping the hand blocks would
# move the only hand into the empty reserved block on half of all augmented samples
# and undo the canonicalization. This map mirrors pose L/R and negates x — the same
# geometric mirror — while leaving both hand blocks where they are.
FLIP_MAP_CANON = np.concatenate([FLIP_MAP[:33], np.arange(33, N_POINTS, dtype=np.int32)])
assert (FLIP_MAP_CANON.shape[0] == N_POINTS
        and sorted(FLIP_MAP_CANON.tolist()) == list(range(N_POINTS)))

# Selected in main() from --canonical-hand. augment() reads these, never the
# constants directly, so the legacy recipe is reproducible bit-for-bit.
_FLIP = FLIP_MAP
_DROP_BLOCKS = (slice(33, 54), slice(54, N_POINTS))   # hand blocks HAND_DROP may blank

# ── RESTING-HAND MASK (--mask-resting-hand) ───────────────────────────────────
# Root cause R5, measured 2026-08-12: MediaPipe preferentially loses the hand that MOVES
# (median wrist speed 0.0317 sh.w./frame in hand-missing frames vs 0.0208 in hand-present
# ones). So on ~45% of clips the populated 21-point block belongs to the STILL arm — it is
# a resting hand wearing the label of a sign. That is not missing data, it is WRONG data:
# the handshape channel carries a confident value that has nothing to do with the gloss.
#
# NaN-ing that block turns wrong data into absent data. Nothing is dropped — all 80,647
# samples are kept, and the model already handles a NaN hand (that is what HAND_DROP
# trains for), so this removes noise without shrinking the corpus.
#
# THREE MODES, because they answer different questions and conflating them would produce a
# number that looks like the baseline but is not comparable to it:
#   off   : unchanged. The default, so no existing run changes behaviour.
#   train : mask TRAIN samples only. Validation stays untouched, so val_acc is directly
#           comparable to the unmasked baseline. THIS IS THE ONE TO RUN for the A/B.
#   all   : also mask VALIDATION. Useful only to see the ceiling on clean inputs; val_acc
#           from this mode must NOT be quoted against the baseline, because the yardstick
#           moved rather than the model improving.
#
# Neither mode touches the held-out TEST split, and that is not an oversight of this flag:
# run_fold only ever reads split == "cv". The test set is scored afterwards by
# eval_savedmodel_250.py, a separate script with no mask of its own. So a test number from
# EITHER mode is measured on unmasked data and stays comparable to 0.7590 — which is what we
# want for the A/B, but it also means this flag alone does not make inference deploy-matched.
# Doing that would need the same check in the live path (feasible — hand_arm_alignment needs
# only the pose wrists and the hand block) plus the same masking inside the eval script.
_MASK_MODE = "off"                 # off | train | all   — set in main()
_RESTING: dict[str, str] = {}      # manifest key -> block letter ("L"/"R") to NaN
_RESTING_FOR = None                # key set the cached scan was computed from
L_HAND_BLOCK, R_HAND_BLOCK = slice(33, 54), slice(54, N_POINTS)


def scan_resting_hands(arrays: dict) -> dict:
    """key -> block letter, for clips whose tracked hand sits on the STILL arm.

    Only clips with a DEFINITE verdict are listed. hand_arm_alignment reports
    aligned=False both for "the tracked hand is on the still arm" and for "could not tell"
    (no finite wrist, degenerate geometry), and masking the second kind would destroy
    usable data to no purpose — so `belongs` and `moving` must both be resolved.
    """
    if hand_arm_alignment is None:
        raise SystemExit("[err] --mask-resting-hand needs sign_landmarks.py beside train.py")
    out, undecided = {}, 0
    for k, a in arrays.items():
        # canonicalize_missing FIRST, and never skip it. This corpus encodes a missing
        # landmark as exact 0.0 (training/README.md), while hand_arm_alignment is NaN-based
        # — and np.isfinite(0.0) is True. Fed a raw array it reports block="L", d_L=3.72,
        # d_R=4.31 for EVERY clip regardless of where the hand actually is, so the aligned
        # verdict becomes a constant and the mask would blank nearly the whole corpus while
        # printing a believable percentage. build_sign_clips.py converts at both its load
        # sites; load_dataset() deliberately does not, because the model's PreprocessLayer
        # treats NaN as the PADDING sentinel and would read a NaN pose point as end-of-clip.
        # So convert here, for the decision only — never for the array handed to the model.
        al = hand_arm_alignment(canonicalize_missing(a))
        if al["block"] is None:
            continue                                   # no hand tracked at all: nothing to mask
        if al["belongs"] is None or al["moving"] is None:
            undecided += 1
            continue
        if not al["aligned"]:
            out[k] = al["block"]
    if undecided:
        print(f"[mask] {undecided} clips had no decidable signing hand — left untouched")
    return out


def apply_resting_mask(a: np.ndarray, key: str) -> np.ndarray:
    """NaN the hand block on `a` if that block is the resting hand's. Copy-on-write:
    `arrays` is shared across epochs and both datasets, so mutating in place would
    silently mask val/test too and make --mask-resting-hand=train a lie."""
    blk = _RESTING.get(key)
    if blk is None:
        return a
    a = a.copy()
    a[:, L_HAND_BLOCK if blk == "L" else R_HAND_BLOCK, :] = np.nan
    return a
DIM = 192             # model width (hoyso's small variant)
KSIZE = 17            # depthwise conv kernel size
DROP_PATH = 0.2
LATE_DROPOUT = 0.7    # after GAP, from LATE_START_EPOCH (raised from 0.5: fold-0 showed a 29-pt overfit gap)
AWP_LAMBDA = 0.2
LATE_START_EPOCH = 15

# ── DEPLOY-MATCHED augmentation (added 2026-08-05) ────────────────────────────
# These three close train/deploy MISMATCHES rather than just adding variety, which
# is why they are separated from the older knobs and individually switchable —
# set any probability to 0.0 to ablate it and A/B against the previous recipe.
#
# 1) HAND_DROP: the pre-existing landmark dropout NaNs 1-8 *scattered* points, but
#    MediaPipe does not fail that way in the field — it loses a WHOLE HAND for a
#    run of frames (exactly what live_demo's HANDPRESENCE_MIN watches for). Without
#    this, the model never trains on its most common real failure mode.
# 2) JITTER: the affine below is ONE transform for the whole clip, so trajectories
#    stay unnaturally smooth. Real landmarks jitter frame to frame; a model that
#    has only seen smooth input over-trusts fine velocity/acceleration cues (dx/dx2).
# 3) FRAME_DROP: live_demo runs at whatever fps the camera gives (10-30). Uniform
#    resampling models a different *speed*, not *dropped/irregular* frames.
HAND_DROP_P      = 0.30   # probability of blanking one hand for a contiguous span
HAND_DROP_MIN    = 3      # min span, frames
HAND_DROP_FRAC   = 0.34   # max span as a fraction of clip length
JITTER_P         = 0.50   # probability of applying per-frame coordinate noise
JITTER_SIGMA     = 0.015  # noise sd in SHOULDER-WIDTH units (coords are normalized)
FRAME_DROP_P     = 0.25   # probability of dropping scattered frames pre-resample
FRAME_DROP_MAX   = 0.15   # max fraction of frames removed
BATCH_SIZE = 64
DEFAULT_EPOCHS = 200
BASE_LR = 4e-4
WEIGHT_DECAY = 1e-4
LABEL_SMOOTHING = 0.1
PATIENCE = 30


def _find_vocab() -> Path:
    """Locate vocab_30.json across the layouts we actually run in
    (repo checkout, or files dropped flat into Colab's /content)."""
    here = Path(__file__).resolve().parent
    candidates = [
        os.environ.get("ASL_VOCAB"),
        here / "vocab_30.json",          # same dir as train.py (Colab flat upload)
        here.parent / "vocab_30.json",   # repo root (repo checkout)
        Path.cwd() / "vocab_30.json",    # current working dir
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    raise FileNotFoundError(
        "vocab_30.json not found. Put it next to train.py, or set ASL_VOCAB=/path/to/vocab_30.json"
    )


# ----------------------------------------------------------------------------
# Embedded feature layer — z-drop + dx/dx2, fixed length, no tf.cond.
# This layer ships inside the exported model: browser runs the same math.
# ----------------------------------------------------------------------------
class PreprocessLayer(layers.Layer):
    """(B, MAX_LEN, 75, 3) raw padded input -> (B, MAX_LEN, F) features + mask."""

    def __init__(self, keep_z: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.keep_z = keep_z
        # Rotation/translation/mirror-invariant HANDSHAPE features (no face data
        # available). Per-hand pairwise distances between 10 key landmarks
        # (wrist, 5 fingertips, 4 MCP knuckles) = 45 pairs/hand, plus 10
        # left-vs-right distances (one- vs two-handed structure). 100 extra dims.
        # Recomputed from constants in __init__, so get_config stays keep_z-only.
        CUR = [0, 4, 8, 12, 16, 20, 5, 9, 13, 17]
        self.lh_idx = tf.constant([33 + i for i in CUR], tf.int32)   # left hand 33-53
        self.rh_idx = tf.constant([54 + i for i in CUR], tf.int32)   # right hand 54-74
        iu = np.triu_indices(len(CUR), k=1)                          # 45 unordered pairs
        self.pi = tf.constant(iu[0], tf.int32)
        self.pj = tf.constant(iu[1], tf.int32)

    def call(self, x):
        # mask: (B, T, 1) 1.0 for real frames, 0.0 for NaN padding
        mask = tf.cast(~tf.math.is_nan(x[:, :, 0, 0]), x.dtype)[..., None]
        x = tf.where(tf.math.is_nan(x), tf.zeros_like(x), x)

        pos = x if self.keep_z else x[..., :2]          # (B, T, P, C)
        c = pos.shape[-1]

        nxt = tf.concat([pos[:, 1:], tf.zeros_like(pos[:, :1])], axis=1)
        m1 = tf.concat([mask[:, 1:], tf.zeros_like(mask[:, :1])], axis=1)
        dx = (nxt - pos) * m1[..., None]

        nxt2 = tf.concat([pos[:, 2:], tf.zeros_like(pos[:, :2])], axis=1)
        m2 = tf.concat([mask[:, 2:], tf.zeros_like(mask[:, :2])], axis=1)
        dx2 = (nxt2 - pos) * m2[..., None]

        # invariant handshape distances (see __init__). x is already NaN->0, so a
        # dropped/missing hand collapses to the origin -> ~0 distances (consistent
        # with the landmark-dropout augmentation). sqrt(sum+eps) is grad-safe at 0.
        xy = x[..., :2]

        def _pdist(idx):
            p = tf.gather(xy, idx, axis=2)                          # (B,T,10,2)
            a = tf.gather(p, self.pi, axis=2)
            b = tf.gather(p, self.pj, axis=2)
            return tf.sqrt(tf.reduce_sum((a - b) ** 2, -1) + 1e-6)  # (B,T,45)

        pl = tf.gather(xy, self.lh_idx, axis=2)
        pr = tf.gather(xy, self.rh_idx, axis=2)
        dlr = tf.sqrt(tf.reduce_sum((pl - pr) ** 2, -1) + 1e-6)     # (B,T,10)
        extra = tf.concat([_pdist(self.lh_idx), _pdist(self.rh_idx), dlr], -1)  # (B,T,100)

        # velocity of those distances (how the handshape opens/closes over time) —
        # same one-step temporal diff + mask as dx. Targets the confusable tail
        # (signs with a similar static shape but different motion, e.g. go/there).
        extra_nxt = tf.concat([extra[:, 1:], tf.zeros_like(extra[:, :1])], axis=1)
        d_extra = (extra_nxt - extra) * m1                         # (B,T,100)

        t = tf.shape(pos)[1]
        feat = tf.concat(
            [
                tf.reshape(pos, (-1, t, N_POINTS * c)),
                tf.reshape(dx, (-1, t, N_POINTS * c)),
                tf.reshape(dx2, (-1, t, N_POINTS * c)),
                extra,
                d_extra,
            ],
            axis=-1,
        )
        feat = feat * mask
        return feat, mask

    def get_config(self):
        return {**super().get_config(), "keep_z": self.keep_z}


class DropPath(layers.Layer):
    """Stochastic depth: drop the whole residual branch per-sample."""

    def __init__(self, rate: float = DROP_PATH, **kwargs):
        super().__init__(**kwargs)
        self.rate = rate

    def call(self, x, training=None):
        if not training or self.rate == 0.0:
            return x
        keep = 1.0 - self.rate
        shape = (tf.shape(x)[0],) + (1,) * (len(x.shape) - 1)
        gate = tf.floor(keep + tf.random.uniform(shape, dtype=x.dtype))
        return x / keep * gate

    def get_config(self):
        return {**super().get_config(), "rate": self.rate}


class LateDropout(layers.Layer):
    """Dropout that only activates once `self.active` is flipped on (epoch 15)."""

    def __init__(self, rate: float = LATE_DROPOUT, **kwargs):
        super().__init__(**kwargs)
        self.rate = rate

    def build(self, input_shape):
        self.active = tf.Variable(False, trainable=False, name="late_dropout_on")
        self.drop = layers.Dropout(self.rate)
        super().build(input_shape)

    def call(self, x, training=None):
        if not training:
            return x
        return tf.cond(self.active, lambda: self.drop(x, training=True), lambda: x)

    def get_config(self):
        return {**super().get_config(), "rate": self.rate}


def conv1d_block(x, mask, dim=DIM, ksize=KSIZE, drop=DROP_PATH):
    """Depthwise-causal conv block with residual + DropPath (hoyso-style)."""
    skip = x
    h = layers.ZeroPadding1D((ksize - 1, 0))(x)           # causal left-pad
    h = layers.DepthwiseConv1D(ksize, padding="valid", use_bias=False)(h)
    h = layers.BatchNormalization(momentum=0.95)(h)
    h = layers.Activation("swish")(h)
    h = layers.Dense(dim, use_bias=True)(h)
    h = h * mask
    h = DropPath(drop)(h)
    return layers.Add()([skip, h])


def transformer_block(x, mask, dim=DIM, heads=4, expand=2, drop=DROP_PATH):
    """MHSA + MLP block, BatchNorm+swish flavor, padding-aware attention."""
    attn_mask = tf.matmul(mask, mask, transpose_b=True)   # (B, T, T)
    skip = x
    h = layers.BatchNormalization(momentum=0.95)(x)
    h = layers.MultiHeadAttention(num_heads=heads, key_dim=dim // heads)(
        h, h, attention_mask=attn_mask
    )
    h = h * mask
    h = DropPath(drop)(h)
    x = layers.Add()([skip, h])

    skip = x
    h = layers.BatchNormalization(momentum=0.95)(x)
    h = layers.Dense(dim * expand, activation="swish")(h)
    h = layers.Dense(dim)(h)
    h = h * mask
    h = DropPath(drop)(h)
    return layers.Add()([skip, h])


class MaskedMeanMax(layers.Layer):
    """Concat of masked mean-pool and masked max-pool over time.

    Plain masked GAP averages the peak-handshape frame together with neutral
    transition frames; adding a masked max-pool keeps the per-channel key-pose
    peak alongside the mean trajectory. Padding rows are pushed to -1e9 in the
    max (float32-safe; a real frame always exists so the result is finite).
    Output width is 2x the input (mean || max)."""

    def call(self, inputs):
        x, mask = inputs
        s = tf.reduce_sum(x * mask, axis=1)
        n = tf.reduce_sum(mask, axis=1)
        mean = s / tf.maximum(n, 1.0)
        mx = tf.reduce_max(x + (1.0 - mask) * (-1e9), axis=1)
        return tf.concat([mean, mx], axis=-1)

    def get_config(self):
        return super().get_config()


class AWPModel(keras.Model):
    """keras.Model with an optional Adversarial Weight Perturbation train step.

    WARNING: EXPERIMENTAL — observed total collapse to below-random accuracy
    when enabled at epoch 15 on the 30-word fold-0 run (2026-07-14). OFF by
    default. Fix and re-validate before ever passing --awp.
    """

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.awp_on = tf.Variable(False, trainable=False, name="awp_on")
        # >0 activates manifold mixup in train_step (set by --mixup). Sub-models
        # feat_ext/head are attached in build_model when mixup is requested.
        self.mixup_alpha = 0.0

    def train_step(self, data):
        x, y = data

        # Manifold mixup (off unless --mixup sets mixup_alpha > 0; mutually
        # exclusive with AWP). Input-space mixup is unsafe here (it corrupts the
        # NaN padding mask and the dx/dx2 motion features), so we mix the pooled,
        # fixed-size embedding. feat_ext MUST run INSIDE the tape or the backbone
        # receives no gradient.
        if self.mixup_alpha > 0.0:
            a = self.mixup_alpha
            g1 = tf.random.gamma([], a)
            g2 = tf.random.gamma([], a)
            lam = g1 / (g1 + g2)
            with tf.GradientTape() as tape:
                pooled = self.feat_ext(x, training=True)
                idx = tf.random.shuffle(tf.range(tf.shape(pooled)[0]))
                pooled_mix = lam * pooled + (1.0 - lam) * tf.gather(pooled, idx)
                y2 = lam * y + (1.0 - lam) * tf.gather(y, idx)
                logits = self.head(pooled_mix, training=True)
                loss = self.compiled_loss(y2, logits)
            grads = tape.gradient(loss, self.trainable_variables)
            self.optimizer.apply_gradients(
                [(g, v) for g, v in zip(grads, self.trainable_variables)
                 if g is not None])
            # no train-acc here: logits come from mixed embeddings vs unmixed y, so
            # CategoricalAccuracy would read misleadingly low. val_acc (default
            # test_step on unmixed data) still drives selection.
            return {"loss": loss}

        def plain_step():
            with tf.GradientTape() as tape:
                pred = self(x, training=True)
                loss = self.compiled_loss(y, pred)
            grads = tape.gradient(loss, self.trainable_variables)
            return loss, pred, grads

        def awp_step():
            with tf.GradientTape() as tape:
                pred = self(x, training=True)
                loss = self.compiled_loss(y, pred)
            grads = tape.gradient(loss, self.trainable_variables)
            deltas = []
            for v, g in zip(self.trainable_variables, grads):
                if g is None:
                    deltas.append(None)
                    continue
                d = AWP_LAMBDA * tf.norm(v) * g / (tf.norm(g) + 1e-12)
                v.assign_add(d)
                deltas.append(d)
            with tf.GradientTape() as tape:
                pred2 = self(x, training=True)
                loss2 = self.compiled_loss(y, pred2)
            grads2 = tape.gradient(loss2, self.trainable_variables)
            for v, d in zip(self.trainable_variables, deltas):
                if d is not None:
                    v.assign_sub(d)
            return loss2, pred2, grads2

        loss, pred, grads = tf.cond(self.awp_on, awp_step, plain_step)
        self.optimizer.apply_gradients(
            [(g, v) for g, v in zip(grads, self.trainable_variables) if g is not None]
        )
        self.compiled_metrics.update_state(y, pred)
        out = {m.name: m.result() for m in self.metrics}
        out["loss"] = loss
        return out


def build_model(num_classes: int, keep_z: bool = False, mixup: bool = False,
                late_dropout: float = LATE_DROPOUT) -> keras.Model:
    inp = keras.Input((MAX_LEN, N_POINTS, N_RAW_CH), name="landmarks")
    feat, mask = PreprocessLayer(keep_z=keep_z, name="preprocess")(inp)

    x = layers.Dense(DIM, use_bias=False, name="stem_dense")(feat)
    x = layers.BatchNormalization(momentum=0.95, name="stem_bn")(x)
    x = x * mask

    for _ in range(2):                                    # (3 conv + 1 xfmr) x 2
        for _ in range(3):
            x = conv1d_block(x, mask)
        x = transformer_block(x, mask)

    x = layers.Dense(DIM * 2, name="top_dense")(x)
    x = MaskedMeanMax(name="pool")([x, mask])             # mean||max pool -> DIM*4
    x = LateDropout(late_dropout, name="late_dropout")(x)
    out = layers.Dense(num_classes, name="classifier")(x)

    model = AWPModel(inp, out, name="asl_mvp_cnn_transformer")
    model.mixup_alpha = 0.0

    if mixup:
        # Shared-weight split for manifold mixup: feat_ext = inp -> pooled vector
        # (the input to late_dropout), head = pooled -> (late_dropout) -> classifier.
        # The exported inference graph (inp -> classifier) is byte-identical; the
        # split exists only so train_step can mix the pooled embedding.
        pooled_t = model.get_layer("late_dropout").input     # (B, DIM*4)
        model.feat_ext = keras.Model(model.input, pooled_t)
        h_in = keras.Input(pooled_t.shape[1:])
        h = model.get_layer("classifier")(model.get_layer("late_dropout")(h_in))
        model.head = keras.Model(h_in, h)
        assert model.head.get_layer("classifier") is model.get_layer("classifier")
    return model


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
def load_vocab(all_words: bool, data_dir: Path) -> dict:
    """30-word vocab from vocab_30.json, or a dynamic all-words (250) vocab."""
    if not all_words:
        with open(_find_vocab()) as f:
            return json.load(f)
    man = pd.read_parquet(data_dir / "split_manifest.parquet")
    words = sorted(man["word"].unique())
    return {
        "words": words,
        "word_to_index": {w: i for i, w in enumerate(words)},
        "num_classes": len(words),
        "note": "dynamic all-words vocab for 250-class pretraining",
    }


def load_dataset(data_dir: Path, vocab: dict):
    man = pd.read_parquet(data_dir / "split_manifest.parquet")
    man = man[man["word"].isin(vocab["word_to_index"])].reset_index(drop=True)

    arrays: dict[str, np.ndarray] = {}
    missing_words = []
    for word in sorted(man["word"].unique()):
        npz_path = data_dir / "by_word" / word / "sequences.npz"
        if not npz_path.exists():
            missing_words.append(word)
            continue
        npz = np.load(npz_path)
        for key in npz.files:
            arrays[f"{word}/{key}"] = npz[key].astype(np.float32)
    if missing_words:
        print(f"WARNING: no npz on disk for {len(missing_words)} words "
              f"(e.g. {missing_words[:5]}) — those rows are dropped. "
              f"Did you download the full word set for this mode?")
        man = man[~man["word"].isin(missing_words)].reset_index(drop=True)

    man["key"] = man["word"] + "/" + man["participant_id"].astype(str) + "_" + man["sequence_id"].astype(str)
    man["y"] = man["word"].map(vocab["word_to_index"]).astype(np.int32)
    missing = ~man["key"].isin(arrays)
    if missing.any():
        print(f"WARNING: {missing.sum()} manifest rows have no npz array — dropped")
        man = man[~missing].reset_index(drop=True)
    return man, arrays


def time_resize(a: np.ndarray, new_len: int) -> np.ndarray:
    t = a.shape[0]
    if t == new_len:
        return a
    idx = np.linspace(0.0, t - 1.0, new_len)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, t - 1)
    w = (idx - lo).astype(np.float32)[:, None, None]
    return a[lo] * (1.0 - w) + a[hi] * w


def fit_to_maxlen(a: np.ndarray) -> np.ndarray:
    if a.shape[0] > MAX_LEN:
        a = time_resize(a, MAX_LEN)
    if a.shape[0] < MAX_LEN:
        pad = np.full((MAX_LEN - a.shape[0], N_POINTS, N_RAW_CH), np.nan, np.float32)
        a = np.concatenate([a, pad], axis=0)
    return a


def augment(a: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Train-time augmentation on the raw (T, 75, 3) sequence."""
    # horizontal flip: mirror left<->right. Swap hand/pose slots via FLIP_MAP,
    # then negate x (coords are shoulder-centered, so mirror is x -> -x). A
    # signer's handedness is not meaning-bearing, so this ~doubles usable data.
    if rng.uniform() < 0.5:
        a = a[:, _FLIP, :].copy()
        a[..., 0] *= -1.0

    # temporal crop: keep a random contiguous 80-100% window
    if a.shape[0] > 12 and rng.uniform() < 0.5:
        keep = rng.uniform(0.8, 1.0)
        w = max(8, int(a.shape[0] * keep))
        s = rng.integers(0, a.shape[0] - w + 1)
        a = a[s : s + w]

    # frame drop: remove scattered frames BEFORE resampling. This is deliberately
    # different from the resample below — resampling changes signing SPEED uniformly,
    # whereas a laggy webcam drops frames irregularly and leaves the speed intact.
    # Done pre-resample so the clip still lands on a normal length afterwards.
    if FRAME_DROP_P > 0.0 and a.shape[0] > 16 and rng.uniform() < FRAME_DROP_P:
        n_drop = int(a.shape[0] * rng.uniform(0.05, FRAME_DROP_MAX))
        if n_drop > 0:
            keep = np.setdiff1d(np.arange(a.shape[0]),
                                rng.choice(a.shape[0], size=n_drop, replace=False))
            a = a[keep]

    # temporal resample 0.7x–1.4x (narrowed: extreme resample distorts dx/dx2 vs deploy)
    factor = rng.uniform(0.7, 1.4)
    a = time_resize(a, max(4, int(round(a.shape[0] * factor))))

    # affine on x,y: rotate / shear / scale / shift — z untouched
    theta = np.deg2rad(rng.uniform(-15.0, 15.0))
    shear = np.tan(np.deg2rad(rng.uniform(-8.0, 8.0)))
    scale = rng.uniform(0.85, 1.15)
    shift = rng.uniform(-0.1, 0.1, size=2).astype(np.float32)
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float32,
    )
    sh = np.array([[1.0, shear], [0.0, 1.0]], dtype=np.float32)
    m = (rot @ sh) * scale
    xy = a[..., :2] @ m.T + shift
    a = np.concatenate([xy, a[..., 2:]], axis=-1)

    # per-frame jitter: small independent noise per frame, applied AFTER the affine
    # (so it is not scaled/rotated with it) and BEFORE any NaN'ing (NaN + noise is
    # still NaN, but keeping this order makes the intent obvious). Only x,y are
    # jittered — z is untouched everywhere else in this function, so keep it so.
    if JITTER_P > 0.0 and rng.uniform() < JITTER_P:
        a = a.copy()
        a[..., :2] += rng.normal(0.0, JITTER_SIGMA, size=a[..., :2].shape).astype(np.float32)

    # landmark dropout: NaN 1-8 random points for the whole clip (never point 0,
    # which anchors the frame mask). PreprocessLayer zeroes them in-model.
    if rng.uniform() < 0.5:
        k = rng.integers(1, 9)
        pts = rng.choice(np.arange(1, N_POINTS), size=k, replace=False)
        a = a.copy()
        a[:, pts, :] = np.nan

    # whole-hand dropout: blank ONE hand block for a contiguous run of frames.
    # This is the real MediaPipe failure mode (a hand leaves frame / is occluded /
    # loses tracking), unlike the scattered-point dropout above. Slots 33-53 = left
    # hand, 54-74 = right hand; point 0 is never touched, so the frame mask survives
    # and the model learns "keep classifying with one hand missing" instead of
    # treating the frame as padding.
    # On the canonical layout _DROP_BLOCKS holds only 54-74: blanking the reserved
    # 33-53 block is a no-op, so leaving it in the choice would silently halve this
    # augmentation's rate — the one that models MediaPipe's real failure mode.
    if HAND_DROP_P > 0.0 and a.shape[0] >= HAND_DROP_MIN + 1 and rng.uniform() < HAND_DROP_P:
        blk = _DROP_BLOCKS[int(rng.integers(0, len(_DROP_BLOCKS)))]
        w = int(rng.integers(HAND_DROP_MIN,
                             max(HAND_DROP_MIN + 1, int(a.shape[0] * HAND_DROP_FRAC)) + 1))
        w = min(w, a.shape[0])
        s = int(rng.integers(0, a.shape[0] - w + 1))
        a = a.copy()
        a[s : s + w, blk, :] = np.nan

    # temporal cutout: NaN a small random window of whole frames
    if rng.uniform() < 0.5 and a.shape[0] > 8:
        w = rng.integers(2, max(3, a.shape[0] // 5))
        s = rng.integers(0, a.shape[0] - w)
        a = a.copy()
        a[s : s + w] = np.nan
    return a


def make_tf_dataset(man: pd.DataFrame, arrays: dict, num_classes: int,
                    training: bool, seed: int = 42):
    keys = man["key"].to_numpy()
    ys = man["y"].to_numpy()
    rng = np.random.default_rng(seed)
    eye = np.eye(num_classes, dtype=np.float32)

    # mask BEFORE augment: augment's hflip can move a block, and HAND_DROP may blank one,
    # so masking afterwards would target whichever block the augmentation happened to leave
    # there rather than the one the alignment test actually judged.
    masking = _MASK_MODE == "all" or (training and _MASK_MODE == "train")

    def gen():
        order = np.arange(len(keys))
        if training:
            rng.shuffle(order)
        for i in order:
            a = arrays[keys[i]]
            if masking:
                a = apply_resting_mask(a, keys[i])
            if training:
                a = augment(a, rng)
            yield fit_to_maxlen(a), eye[ys[i]]

    ds = tf.data.Dataset.from_generator(
        gen,
        output_signature=(
            tf.TensorSpec((MAX_LEN, N_POINTS, N_RAW_CH), tf.float32),
            tf.TensorSpec((num_classes,), tf.float32),
        ),
    )
    if training:
        ds = ds.repeat()
    return ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)


# ----------------------------------------------------------------------------
# Training / evaluation
# ----------------------------------------------------------------------------
class LatePhaseSwitch(keras.callbacks.Callback):
    """At LATE_START_EPOCH turn on LateDropout, and AWP only if explicitly enabled."""

    def __init__(self, enable_awp: bool = False):
        super().__init__()
        self.enable_awp = enable_awp

    def on_epoch_begin(self, epoch, logs=None):
        if epoch == LATE_START_EPOCH:
            self.model.get_layer("late_dropout").active.assign(True)
            if self.enable_awp:
                self.model.awp_on.assign(True)
            extra = " + AWP(0.2)" if self.enable_awp else ""
            print(f"\n[epoch {epoch}] LateDropout({LATE_DROPOUT}){extra} enabled")


class EMA(keras.callbacks.Callback):
    """Model-selected weight EMA (hoyso48's winning recipe used EMA).

    Naive AdamW(use_ema=True) keeps the EMA inside the optimizer and never
    validates on it, so EarlyStopping ships the RAW weights. Instead we swap the
    EMA weights in AROUND fit's validation pass (so the logged val_acc that drives
    selection IS the EMA number), snapshot the best EMA, and write it back at
    train-end so save_weights / model.export / ensemble_eval all ship EMA.
    The per-batch update is graph-fused (one dispatch/batch) to protect the GPU
    budget; an eager Python loop over ~90 vars would roughly double train time.
    Pair with EarlyStopping(restore_best_weights=False) so they don't fight.

    Resume-safe: the EMA shadow + running best are persisted to `state_dir` (a
    tf.train.Checkpoint) each epoch, because BackupAndRestore does NOT cover
    callback state. Without this, a resumed fold would lose the global-best EMA
    and could export a worse-than-peak model."""

    def __init__(self, decay=0.999, monitor="val_acc", mode="max", state_dir=None):
        super().__init__()
        self.decay = decay
        self.monitor = monitor
        self.mode = mode
        self.better = (lambda a, b: a > b) if mode == "max" else (lambda a, b: a < b)
        self.state_dir = Path(state_dir) if state_dir else None
        self.manager = None

    def _track(self):
        # float vars only: skips the bool control Variables late_dropout_on / awp_on.
        # BN moving stats (float) are harmlessly smoothed.
        return [w for w in self.model.weights if w.dtype.is_floating]

    def on_train_begin(self, logs=None):
        self.vars = self._track()
        self.ema = [tf.Variable(w, trainable=False) for w in self.vars]
        self.best_ema = [tf.Variable(w, trainable=False) for w in self.vars]
        self.best = tf.Variable(-np.inf if self.mode == "max" else np.inf,
                                trainable=False, dtype=tf.float32)
        self.has_best = tf.Variable(False, trainable=False)
        d = self.decay

        @tf.function
        def _update():
            for e, w in zip(self.ema, self.vars):
                e.assign(e * d + (1.0 - d) * w)
        self._update = _update

        # BackupAndRestore (first in cbs) already restored the raw weights; layer
        # the persisted EMA state on top so a resumed fold keeps its global best.
        if self.state_dir is not None:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            ckpt = tf.train.Checkpoint(ema=self.ema, best_ema=self.best_ema,
                                       best=self.best, has_best=self.has_best)
            self.manager = tf.train.CheckpointManager(
                ckpt, str(self.state_dir), max_to_keep=1)
            if self.manager.latest_checkpoint:
                ckpt.restore(self.manager.latest_checkpoint).expect_partial()
                print(f"[EMA] resumed EMA state from {self.manager.latest_checkpoint}")

    def on_train_batch_end(self, batch, logs=None):
        self._update()

    def on_test_begin(self, logs=None):      # fires around fit's validation pass
        self._raw = [tf.identity(w) for w in self.vars]
        for w, e in zip(self.vars, self.ema):
            w.assign(e)

    def on_test_end(self, logs=None):        # restore the raw training trajectory
        for w, r in zip(self.vars, self._raw):
            w.assign(r)

    def on_epoch_end(self, epoch, logs=None):
        cur = logs.get(self.monitor) if logs else None
        if cur is not None and (not bool(self.has_best) or self.better(cur, float(self.best))):
            self.best.assign(cur)
            self.has_best.assign(True)
            for b, e in zip(self.best_ema, self.ema):
                b.assign(e)
        if self.manager is not None:
            self.manager.save()

    def on_train_end(self, logs=None):
        if bool(self.has_best):
            for w, b in zip(self.vars, self.best_ema):
                w.assign(b)


def run_fold(fold: int, data_dir: Path, out_dir: Path, *, all_words: bool,
             keep_z: bool, awp: bool, init_from: str | None,
             lr: float, epochs: int, save_weights: str | None, seed: int = 42,
             mixup: bool = False, late_dropout: float = LATE_DROPOUT):
    vocab = load_vocab(all_words, data_dir)
    num_classes = len(vocab["words"])
    man, arrays = load_dataset(data_dir, vocab)

    if _MASK_MODE != "off":
        # --fold all calls run_fold 5x. The folds differ only in the manifest split, never in
        # `arrays`, so the scan result is identical — cache it rather than walking 80k clips
        # five times. Keyed on the actual key set, so a genuinely different corpus rescans.
        global _RESTING, _RESTING_FOR
        sig = frozenset(arrays)
        if _RESTING_FOR != sig:
            _RESTING, _RESTING_FOR = scan_resting_hands(arrays), sig
        else:
            print(f"[mask] reusing the scan from the previous fold ({len(_RESTING)} clips)")
        n = len(_RESTING)
        print(f"[mask] --mask-resting-hand={_MASK_MODE}: {n}/{len(arrays)} clips "
              f"({100.0 * n / max(1, len(arrays)):.1f}%) have the tracked hand on the STILL "
              f"arm; their hand block is NaN-ed"
              + ("" if _MASK_MODE == "all" else " in TRAIN only — validation untouched, so "
                 "val_acc stays comparable to the unmasked baseline"))
        if _MASK_MODE == "all":
            print("[mask] NOTE: 'all' masks VALIDATION too, so val_acc from this run is NOT "
                  "comparable to the unmasked baseline — the yardstick moved. The held-out "
                  "test split is unaffected either way (scored by eval_savedmodel_250.py).")
        # A mask that touches nothing is a silent no-op, and this project has already lost a
        # run to a check that could not fail. Refuse rather than train a misleading arm.
        if n == 0:
            raise SystemExit("[err] --mask-resting-hand matched 0 clips. Either the corpus is "
                             "already clean (unexpected: ~45% is the measured rate) or the "
                             "alignment test is silently failing. Do not train this arm.")

    cv = man[man["split"] == "cv"]
    train_man = cv[cv["fold"] != fold]
    val_man = cv[(cv["fold"] == fold) & (~cv["is_outlier"])]

    tag = "all250" if all_words else "mvp30"
    print(f"[{tag}] fold {fold}: classes={num_classes} train={len(train_man)} "
          f"val={len(val_man)} (val participants: {sorted(int(p) for p in val_man['participant_id'].unique())})")

    model = build_model(num_classes=num_classes, keep_z=keep_z, mixup=mixup,
                        late_dropout=late_dropout)

    if init_from:
        # Transfer from the 250-class pretrain: every layer matches by name
        # except the classifier head (shape mismatch -> skipped).
        model.load_weights(init_from, by_name=True, skip_mismatch=True)
        print(f"initialized backbone from {init_from} (classifier head fresh)")

    # manifold mixup lives in AWPModel.train_step; off unless --mixup requested
    model.mixup_alpha = 0.3 if mixup else 0.0

    steps = max(1, len(train_man) // BATCH_SIZE)
    total = epochs * steps
    # LR warmup prepended to the cosine decay. A long warmup only for the risky,
    # never-run from-scratch recipe (no backbone); a short one when fine-tuning.
    # Keyed on init_from (NOT epochs) so the 80-epoch fine-tune isn't given an
    # over-long ramp. Total horizon (warmup + decay) == epochs*steps, alpha=0 so
    # it still ends at LR 0 like the original schedule.
    warmup_frac = 0.05 if init_from is None else 0.02
    warmup = max(steps, int(round(warmup_frac * total)))      # >= 1 epoch of warmup
    schedule = keras.optimizers.schedules.CosineDecay(
        initial_learning_rate=lr * 0.02,   # near-zero start of the ramp
        decay_steps=max(1, total - warmup),
        warmup_target=lr,                  # peak LR reached at end of warmup
        warmup_steps=warmup,
        alpha=0.0,
    )
    model.compile(
        # global_clipnorm guards the high-LR from-scratch run (and any future AWP)
        # against loss spikes; it applies inside AWPModel.train_step's apply_gradients.
        optimizer=keras.optimizers.AdamW(
            learning_rate=schedule, weight_decay=WEIGHT_DECAY, global_clipnorm=1.0),
        loss=keras.losses.CategoricalCrossentropy(
            from_logits=True, label_smoothing=LABEL_SMOOTHING
        ),
        metrics=[keras.metrics.CategoricalAccuracy(name="acc")],
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    cbs = [
        # resume-safe: snapshots weights+optimizer+epoch to out-dir each epoch so a
        # Colab disconnect resumes mid-fold instead of restarting from zero. Put it
        # first so it restores state before the other callbacks run. Point out-dir
        # at Drive (or any persistent disk) and re-running the SAME command resumes.
        keras.callbacks.BackupAndRestore(
            backup_dir=str(out_dir / f"backup_{tag}_fold{fold}")
        ),
        # weight EMA, model-selected on the validation pass (see EMA docstring).
        # decay keyed on total BATCHES (not epochs) so tiny-step fine-tunes aren't
        # over-smoothed; state persisted (state_dir) to survive a resume.
        EMA(decay=0.9995 if epochs * steps >= 50000 else 0.999,
            state_dir=out_dir / f"ema_{tag}_fold{fold}"),
        LatePhaseSwitch(enable_awp=awp),
        # restore_best_weights=False: EMA writes the best-EMA weights at train-end,
        # so early stopping must NOT overwrite them with the raw best.
        keras.callbacks.EarlyStopping(
            monitor="val_acc", mode="max", patience=PATIENCE, restore_best_weights=False
        ),
        keras.callbacks.CSVLogger(out_dir / f"history_{tag}_fold{fold}.csv"),
    ]

    hist = model.fit(
        make_tf_dataset(train_man, arrays, num_classes, training=True, seed=seed),
        steps_per_epoch=steps,
        epochs=epochs,
        validation_data=make_tf_dataset(val_man, arrays, num_classes, training=False),
        callbacks=cbs,
        verbose=2,
    )

    # ---- evaluation ----------------------------------------------------------
    val_ds = make_tf_dataset(val_man, arrays, num_classes, training=False)
    logits = model.predict(val_ds, verbose=0)
    y_true = val_man["y"].to_numpy()
    y_pred = logits.argmax(axis=1)

    words = vocab["words"]
    overall = float((y_true == y_pred).mean())
    per_word = {
        words[c]: float((y_pred[y_true == c] == c).mean())
        for c in np.unique(y_true)
    }
    conf = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        conf[t, p] += 1

    report = {
        "mode": tag, "fold": fold, "keep_z": keep_z, "init_from": init_from,
        # Record the KNOBS, not just the score. Two earlier numbers (0.7755 and 0.7544) are
        # uncomparable because nobody wrote down that they used a different LR and a broken
        # --init-from, and the config was only ever in a notebook cell that got overwritten.
        # `epochs` here is the FLAG value, which is what fixes the CosineDecay schedule —
        # `epochs_run` is where EarlyStopping actually fired. An A/B is only valid when the
        # flag matches; the run length differing is expected and is not a confound.
        "config": {
            "epochs": epochs,
            "epochs_run": len(hist.history.get("loss", [])) if hist is not None else None,
            "lr": lr, "seed": seed, "all_words": all_words,
            "canonical_hand": _FLIP is FLIP_MAP_CANON,
            "mask_resting_hand": _MASK_MODE,
            "masked_clips": len(_RESTING) if _MASK_MODE != "off" else 0,
            "awp": awp, "mixup": mixup, "late_dropout": late_dropout,
        },
        "overall_acc": overall,
        "per_word_acc": per_word,
        "worst_words": sorted(per_word, key=per_word.get)[:5],
    }
    with open(out_dir / f"eval_{tag}_fold{fold}.json", "w") as f:
        json.dump(report, f, indent=2)
    np.savetxt(out_dir / f"confusion_{tag}_fold{fold}.csv", conf, fmt="%d", delimiter=",")

    print(f"\n=== [{tag}] fold {fold}: overall val acc {overall:.4f} ===")
    print("worst 5 words:", {w: round(per_word[w], 3) for w in report["worst_words"]})

    # ---- save -----------------------------------------------------------------
    # weights (h5) always — this is what --init-from and ensemble_eval consume.
    # Seed in the default name so multi-seed runs don't overwrite each other.
    wpath = out_dir / (save_weights or f"weights_{tag}_fold{fold}_seed{seed}.weights.h5")
    model.save_weights(wpath)
    print(f"weights saved: {wpath}")

    # SavedModel export for EVERY mode (incl. --all-words). This is the portable
    # artifact that loads cleanly on any machine — reloading .weights.h5 can
    # silently mis-map layers (Dense/attention decompose to untracked ops on some
    # TF builds), so the 250 model ships as a SavedModel like the 30-word one.
    try:
        model.export(out_dir / f"savedmodel_fold{fold}")
    except AttributeError:
        # fallback for TF builds without Model.export: attach an explicit
        # serving_default so live_demo (reads signatures['serving_default']) loads it.
        @tf.function(input_signature=[tf.TensorSpec(
            (None, MAX_LEN, N_POINTS, N_RAW_CH), tf.float32, name="landmarks")])
        def _serve(z):
            return model(z, training=False)
        tf.saved_model.save(
            model, str(out_dir / f"savedmodel_fold{fold}"),
            signatures={"serving_default": _serve.get_concrete_function()})
    print(f"savedmodel exported: {out_dir / f'savedmodel_fold{fold}'}")

    if not all_words:  # full .keras only for the MVP model
        # a --mixup build tracks feat_ext/head as attributes, which the .keras
        # trackable-walk would re-serialize; clone the functional graph (same
        # trained layer objects) so the saved tree carries no sub-models.
        save_model = keras.Model(model.inputs, model.outputs, name="asl_mvp_export")
        save_model.save(out_dir / f"model_fold{fold}.keras")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts"))
    ap.add_argument("--fold", default="0", help="0-4 or 'all'")
    ap.add_argument("--all-words", action="store_true",
                    help="250-class pretraining mode (needs all words downloaded)")
    ap.add_argument("--init-from", default=None,
                    help="path to .weights.h5 from an --all-words pretrain run")
    ap.add_argument("--save-weights", default=None,
                    help="filename (within out-dir) for saved weights")
    ap.add_argument("--lr", type=float, default=BASE_LR,
                    help="peak LR (use ~2e-4 when fine-tuning from --init-from)")
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    ap.add_argument("--keep-z", action="store_true", help="A/B: keep z channel")
    ap.add_argument("--awp", action="store_true",
                    help="enable AWP (EXPERIMENTAL — destabilized training; off by default)")
    ap.add_argument("--seed", type=int, default=42,
                    help="random seed — vary it (e.g. 42/43/44) for a multi-seed ensemble")
    ap.add_argument("--mixup", action="store_true",
                    help="manifold mixup at the pooled embedding (mutually exclusive with --awp)")
    ap.add_argument("--late-dropout", type=float, default=LATE_DROPOUT,
                    help="dropout before the classifier; A/B this (default 0.7)")
    ap.add_argument("--canonical-hand", action="store_true",
                    help="data came from extract_canonical.py: the DOMINANT hand is always "
                         "at 54-74 and 33-53 is reserved/NaN. Switches hflip to a pose-only "
                         "mirror (FLIP_MAP would swap the hand into the empty block) and "
                         "restricts HAND_DROP to the block that actually holds a hand. "
                         "MUST be set for canonical data and MUST NOT be set for the old "
                         "corpus — the flag is the difference between the two recipes.")
    ap.add_argument("--mask-resting-hand", choices=("off", "train", "all"), default="off",
                    help="NaN the 21-point hand block on clips where the tracked hand sits on "
                         "the STILL arm (~45%% of the corpus — root cause R5: MediaPipe loses "
                         "the hand that moves, so the block often holds a resting hand under a "
                         "sign's label). 'train' masks training samples only, leaving "
                         "validation comparable to the unmasked baseline — use this for the "
                         "A/B. 'all' also masks validation, so its val_acc is NOT comparable "
                         "to the baseline. Neither mode touches the held-out test split, "
                         "which is scored separately by eval_savedmodel_250.py.")
    args = ap.parse_args()
    if args.mixup and args.awp:
        ap.error("--mixup and --awp are mutually exclusive (both rewrite train_step)")

    global _FLIP, _DROP_BLOCKS, _MASK_MODE
    if args.canonical_hand:
        _FLIP = FLIP_MAP_CANON
        _DROP_BLOCKS = (slice(54, N_POINTS),)
    _MASK_MODE = args.mask_resting_hand
    if _MASK_MODE != "off" and hand_arm_alignment is None:
        ap.error("--mask-resting-hand needs sign_landmarks.py importable (put it beside "
                 "train.py or in the repo root); refusing to run the mask as a silent no-op")
    print(f"[cfg] layout = {'CANONICAL (dominant hand @54-74)' if args.canonical_hand else 'LEGACY (L@33-53, R@54-74)'}"
          f" | hflip swaps hands = {not args.canonical_hand}"
          f" | hand-drop blocks = {len(_DROP_BLOCKS)}"
          f" | resting-hand mask = {_MASK_MODE}")

    tf.random.set_seed(args.seed)
    np.random.seed(args.seed)

    folds = range(5) if args.fold == "all" else [int(args.fold)]
    for k in folds:
        run_fold(k, args.data_dir, args.out_dir,
                 all_words=args.all_words, keep_z=args.keep_z, awp=args.awp,
                 init_from=args.init_from, lr=args.lr, epochs=args.epochs,
                 save_weights=args.save_weights, seed=args.seed,
                 mixup=args.mixup, late_dropout=args.late_dropout)


if __name__ == "__main__":
    main()
