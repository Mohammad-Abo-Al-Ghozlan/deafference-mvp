#!/usr/bin/env python
"""Fingerspelling CTC baseline — 1D-CNN + Transformer encoder over ragged landmark streams.

Reads `fs75.npz` from training/fingerspelling/subset_landmarks.py: frames concatenated
(total, 75, 3) with starts/lengths, plus phrase / participant / sequence_id per sequence.

WHY THIS EXISTS, and why it is not the 250-word pipeline with a different head:

  * The 250-word model resizes every clip to 64 frames. Doing that here destroys letter
    timing — lengths run 21..751 frames, a 36x spread — so sequences stay RAGGED and are
    padded per batch with a mask.
  * It is a sequence-to-sequence problem, so the loss is CTC, not softmax. That brings one
    hard constraint (see MODEL STRIDE below) which is easy to violate silently.
  * Absence is a FEATURE, not something to interpolate away. The median sequence has a
    16-frame hole (~0.53s) in dominant-hand tracking; filling it invents letters. There is an
    explicit `tracked` channel and untracked frames are zeroed AFTER the mask is taken.

Every design choice below is forced by a measurement in docs/FINGERSPELLING_DATA_FINDINGS.md.
Read that first; the numbers are quoted inline where they bind.

MODEL STRIDE — the trap this file exists to avoid
-------------------------------------------------
CTC cannot emit more labels than it has timesteps. Two corrections to what
docs/FINGERSPELLING_DATA_FINDINGS.md finding 1 says, both MEASURED against tf 2.17 here:

  1. It is NOT -inf and the run does NOT die. tf.nn.ctc_loss floors the log-probability and
     returns a large FINITE value — ~707 where a healthy row is ~7-10. So nothing crashes,
     no nan appears, an is_finite() guard never fires, and those rows instead contribute
     ~70-90x the gradient of every real sample. That is worse than a crash, because a crash
     is visible. The guard in CTCTrainer.loss_fn is therefore by LENGTH, not by is_finite.
  2. The requirement is not `T_out >= phrase_len` but `T_out >= phrase_len + repeats`: CTC
     collapses runs, so an adjacent repeat needs a blank wedged between the two. 'll' costs
     three steps. See ctc_required_steps.

The findings doc measures 130 sequences violating the naive form on RAW T. The encoder
downsamples time, so the constraint applies at the OUTPUT resolution and filtering on raw T
is not enough:

    stride   seqs with T_out < phrase_len   median T_out/L   p05 T_out/L
       1              130  (3.25%)               8.86           2.54
       2              170  (4.25%)               4.45           1.28
       4              281  (7.03%)               2.25           0.67   <- unlearnable
       8             1342 (33.58%)                 --             --

p05 headroom below 1.0 means the bottom 5% of sequences physically cannot spell their own
phrase. So TIME_STRIDE is 2, and `ctc_feasible()` computes the filter at
`ceil(T / TIME_STRIDE)` — never on raw T. Change TIME_STRIDE and the filter follows.

RUN
    python train_ctc.py --selftest                     # no data needed, proves the mechanism
    python train_ctc.py --npz /kaggle/input/<ds>/fs75.npz --out /kaggle/working/fs_out
    python train_ctc.py --npz ... --epochs 60 --dim 192 --blocks 4
"""
from __future__ import annotations

import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import argparse
import gc
import glob
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# ── landmark layout (identical to the rest of this project) ───────────────────────────────
N_POINTS = 75
POSE = slice(0, 33)
L_HAND = slice(33, 54)
R_HAND = slice(54, 75)
POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
POSE_L_ELBOW, POSE_R_ELBOW = 13, 14
POSE_L_WRIST, POSE_R_WRIST = 15, 16
POSE_NOSE = 0
# Pose points kept as context. Fingerspelling is produced in neutral space, so gross body
# pose carries little, but the wrist/elbow of the signing arm locate the hand and the
# shoulders give the scale reference.
POSE_KEEP = [POSE_NOSE, POSE_L_SHOULDER, POSE_R_SHOULDER,
             POSE_L_ELBOW, POSE_R_ELBOW, POSE_L_WRIST, POSE_R_WRIST]

TIME_STRIDE = 2          # see MODEL STRIDE above. The filter is derived from this.
BLANK = 0                # CTC blank; real characters are 1..V

# Finding 1: the hard filter. Finding "recommended filter": also drop sequences with fewer
# hand-frames than characters — before it, the worst decile has <1 tracked frame per
# character, so at least one letter was never seen. Costs 6.9% of frames.
MIN_HAND_FRAMES_PER_CHAR = 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════
# character set
# ══════════════════════════════════════════════════════════════════════════════════════════
CHARSET_FILENAME = "character_to_prediction_index.json"     # the competition ships this


def build_charset(phrases) -> dict:
    """Character -> index map from the OBSERVED phrases. Index 0 is the CTC blank.

    ⚠️ Shard-dependent, and that is exactly the hazard. Prefer load_charset().
    """
    chars = sorted({c for p in phrases for c in p})
    return {c: i + 1 for i, c in enumerate(chars)}          # 0 = blank


def find_charset_file(path=None, search=True):
    """The competition's canonical 59-character map, if it is mounted."""
    if path:
        if not Path(path).exists():
            sys.exit(f"[err] --charset {path} does not exist. Omit it to auto-detect under "
                     f"/kaggle/input, or point it at the competition's {CHARSET_FILENAME}.")
        return path
    if not search:                                   # selftest forces the fallback branch
        return None
    hits = sorted(glob.glob(f"/kaggle/input/**/{CHARSET_FILENAME}", recursive=True))
    return hits[0] if hits else None


def load_charset(phrases, path=None, search=True) -> tuple:
    """Character -> index map, corpus-wide when possible. Index 0 is the CTC blank.

    MEASURED BUG, 2026-09-04. The first run of this file derived the charset from the
    attached shards and reported `n_classes 52` — i.e. **51 characters, not the corpus's
    59.** Because the map is `sorted(observed)`, adding shards does not append the missing
    characters, it INSERTS them and shifts the index of nearly every character after the
    insertion point. Consequences, both silent:

      * a 4-shard model and a 68-shard model are not comparable at all; and
      * loading one run's charset.json against the other run's weights remaps every label.

    That is the 123-class medical vocab trap in a new corpus, and build_charset's own
    docstring warned about it while creating it. So the charset now comes from the
    competition's own `character_to_prediction_index.json` (59 characters) whenever the
    competition is mounted, which makes it shard-independent. Keys are re-sorted rather than
    trusting the file's own indices, so the mapping is a pure function of the key SET.
    """
    src_path = find_charset_file(path, search)
    if src_path:
        keys = json.loads(Path(src_path).read_text(encoding="utf-8")).keys()
        return {c: i + 1 for i, c in enumerate(sorted(keys))}, str(src_path)

    c2i = build_charset(phrases)
    print(f"[charset] ⚠ {CHARSET_FILENAME} not found, so the charset is the {len(c2i)} "
          f"characters\n"
          f"          these shards happen to contain — the corpus has 59. A run on more "
          f"shards will\n"
          f"          see more and `sorted()` will REINDEX them, so that model and this one "
          f"are NOT\n"
          f"          comparable and this charset.json must not be loaded against it.\n"
          f"          Fix: attach the competition to the notebook, or pass --charset.")
    return c2i, f"OBSERVED from these shards only ({len(c2i)} chars) — NOT corpus-wide"


def encode(phrase: str, c2i: dict) -> list:
    return [c2i[c] for c in phrase if c in c2i]


def decode(idxs, i2c: dict) -> str:
    return "".join(i2c.get(int(i), "") for i in idxs if int(i) != BLANK)


# ══════════════════════════════════════════════════════════════════════════════════════════
# features
# ══════════════════════════════════════════════════════════════════════════════════════════
def dominant_side(seq: np.ndarray) -> str:
    """Which hand block is the spelling hand, per SEQUENCE.

    Finding 6: dominance is per-sequence, not per-signer — 30 of 92 participants appear with
    BOTH labels, at a median 5% minority share, and minority-hand sequences track only 1.08x
    worse, so the switching is real rather than detection noise. Deciding it per signer would
    therefore mislabel a real minority.
    """
    l = np.isfinite(seq[:, L_HAND, 0]).any(axis=1).sum()
    r = np.isfinite(seq[:, R_HAND, 0]).any(axis=1).sum()
    return "R" if r >= l else "L"


def features(seq: np.ndarray) -> np.ndarray:
    """(T, 75, 3) raw landmarks -> (T, F) float32 features. NaN never leaves this function.

    Three groups, and the mask is what makes the missing-hand case honest:
      * hand SHAPE  — 21 dominant-hand points, wrist-centred and scaled by hand span, so
                      the handshape is comparable across signers and distances from camera.
      * hand PLACE  — the dominant wrist and kept pose points, shoulder-centred and scaled
                      by shoulder width (the same convention as the rest of this project).
      * MOTION      — frame-to-frame delta of the shape block. Finding 5: faster spelling
                      tracks worse (Q4 hand_rate 0.443 vs Q1 0.619), so speed is signal.
      * tracked     — 1.0 where the dominant hand was actually measured, else 0.0.

    Untracked frames are zeroed AFTER `tracked` records them, so the model can learn "no hand
    here" instead of being fed a fabricated hand. Finding 2: the median sequence has a
    16-frame hole; interpolating it invents letters.
    """
    T = len(seq)
    side = dominant_side(seq)
    hand = seq[:, R_HAND if side == "R" else L_HAND, :2].astype(np.float32)   # (T,21,2)

    # mirror a left-dominant sequence so the model only ever sees a right-shaped hand.
    # Hand topology is identical for both hands, so negating x is the whole operation.
    if side == "L":
        hand = hand.copy()
        hand[..., 0] *= -1.0

    tracked = np.isfinite(hand).all(-1).any(-1).astype(np.float32)            # (T,)

    # ── shape: wrist-centred, hand-span scaled ──
    wrist = hand[:, 0:1, :]                                                   # landmark 0
    shape = hand - wrist
    with np.errstate(invalid="ignore"):
        # a frame with no tracked hand is all-NaN here; that is expected, and the np.where
        # below turns it into a scale of 1.0. Silence only this, not real errors.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            span = np.nanmax(np.linalg.norm(shape, axis=-1), axis=1, keepdims=True)  # (T,1)
    span = np.where(np.isfinite(span) & (span > 1e-6), span, 1.0)
    shape = shape / span[..., None]

    # ── place: shoulder-centred, shoulder-width scaled ──
    pose = seq[:, POSE, :2].astype(np.float32)
    ls, rs = pose[:, POSE_L_SHOULDER, :], pose[:, POSE_R_SHOULDER, :]
    mid = (ls + rs) / 2.0
    width = np.linalg.norm(ls - rs, axis=-1, keepdims=True)
    width = np.where(np.isfinite(width) & (width > 1e-6), width, 1.0)
    keep = pose[:, POSE_KEEP, :]
    if side == "L":
        keep = keep.copy(); keep[..., 0] *= -1.0
        mid = mid.copy(); mid[..., 0] *= -1.0
    place = (keep - mid[:, None, :]) / width[:, None, :]
    wpos = (wrist[:, 0, :] - mid) / width

    # ── motion ──
    motion = np.zeros_like(shape)
    if T > 1:
        motion[1:] = shape[1:] - shape[:-1]

    F = np.concatenate([
        shape.reshape(T, -1),        # 21*2 = 42
        motion.reshape(T, -1),       # 42
        place.reshape(T, -1),        # 7*2 = 14
        wpos.reshape(T, -1),         # 2
        tracked[:, None],            # 1
    ], axis=1).astype(np.float32)

    # zero out every non-finite value; `tracked` already carries the information that the
    # frame was empty, so a zero here is a legible "absent" rather than a fabricated pose.
    F[~np.isfinite(F)] = 0.0
    return F


N_FEAT = 21 * 2 + 21 * 2 + len(POSE_KEEP) * 2 + 2 + 1


# ══════════════════════════════════════════════════════════════════════════════════════════
# filtering + splitting
# ══════════════════════════════════════════════════════════════════════════════════════════
def t_out(T, stride: int = TIME_STRIDE) -> int:
    """Timesteps the encoder emits for an input of length T. Must match the model exactly."""
    return int(math.ceil(T / stride))


def ctc_required_steps(labels) -> int:
    """Minimum timesteps CTC needs to emit this label sequence.

    NOT len(labels). CTC collapses runs of the same symbol, so an adjacent repeat can only be
    emitted with a blank wedged between the two — 'll' costs three steps, not two.

    MEASURED against tf.nn.ctc_loss 2.17 rather than taken from the paper:
        labels [3,2,1] (no repeat)  T=3 -> loss   4.28   feasible
        labels [3,3,1] (one repeat) T=3 -> loss 710.01   INFEASIBLE
        labels [3,3,1] (one repeat) T=4 -> loss   6.99   feasible
    """
    labels = list(labels)
    reps = sum(1 for a, b in zip(labels, labels[1:]) if a == b)
    return len(labels) + reps


def ctc_feasible(T, labels, hand_frames, stride: int = TIME_STRIDE) -> bool:
    """Can this sequence physically spell its own phrase at the MODEL's time resolution?

    `labels` is the ENCODED sequence, not its length, because the repeat correction above
    needs to see the symbols. Passing an int still works and is treated as a repeat-free
    label of that length.
    """
    if isinstance(labels, (int, np.integer)):
        need, n_chars = int(labels), int(labels)
    else:
        need, n_chars = ctc_required_steps(labels), len(labels)
    return (t_out(T, stride) >= need
            and hand_frames >= MIN_HAND_FRAMES_PER_CHAR * n_chars)


def signer_split(parts, hand_rate, val_frac=0.15, seed=42, force=None):
    """Signer-DISJOINT split, stratified by tracking quality.

    `force` pins the held-out signers to an explicit list, which is what makes a scale-up
    comparison MEAN anything. `--limit-files N` takes the first N of a sorted shard list, so
    16 shards is a strict superset of 4 — but the automatic split would deal a DIFFERENT set
    of val signers out of the larger pool, and then a CER change could be more data or could
    be easier held-out people. Pinning the 13 signers from the 4-shard run (report.json ->
    val_signers) turns it into one controlled variable: same people, 4x the training data.

    Finding 3: shards do NOT partition signers — 92 of 94 participants appear in just 4
    shards — so the obvious 'train on shards 1..60, validate on 61..68' puts the same signers
    on both sides and reports a number the model cannot reproduce on a new signer.

    Finding 4: 33.5% of hand_rate variance is BETWEEN signers, worst 0.132 vs best 0.896 (a
    6.78x spread). An unstratified draw of well-tracked signers therefore flatters the model,
    so signers are ordered by mean hand_rate and dealt round-robin into train/val.
    """
    rng = np.random.default_rng(seed)
    by = defaultdict(list)
    for i, p in enumerate(parts):
        by[int(p)].append(i)
    rate = {p: float(np.mean([hand_rate[i] for i in idx])) for p, idx in by.items()}
    order = sorted(by, key=lambda p: rate[p])
    target = val_frac * len(parts)

    if force:
        force = [int(p) for p in force]
        val_signers = [p for p in force if p in by]
        absent = [p for p in force if p not in by]
        if absent:
            print(f"[split] ⚠ {len(absent)} forced val signer(s) absent from this shard mix "
                  f"and IGNORED: {absent}\n        The comparison is no longer over an "
                  f"identical signer set — say so when quoting the delta.")
        if not val_signers:
            sys.exit(f"[err] none of the forced val signers {force} appear in this data. "
                     f"Available: {sorted(by)[:20]}...")
        print(f"[split] val signers PINNED to {len(val_signers)} of {len(force)} requested — "
              f"stratification skipped on purpose")
    else:
        val_signers, n = [], 0
        # walk the quality-ordered list and take every k-th signer, so val spans the full
        # tracking-quality range rather than clustering at one end
        k = max(2, int(round(1.0 / val_frac)))
        for j, p in enumerate(order):
            if j % k == k // 2 and n + len(by[p]) <= target * 1.25:
                val_signers.append(p); n += len(by[p])
        if not val_signers:                              # tiny corpora (selftest)
            val_signers = [order[0]]
    val = np.array(sorted(i for p in val_signers for i in by[p]), dtype=np.int64)
    mask = np.ones(len(parts), bool); mask[val] = False
    return np.where(mask)[0], val, val_signers


# ══════════════════════════════════════════════════════════════════════════════════════════
# model
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_model(n_feat: int, n_classes: int, dim=192, blocks=4, heads=4, kernel=17,
                drop=0.1):
    """Depthwise-separable Conv1D stem (one stride-2) + Transformer encoder + CTC head.

    The stem does the local work — a handshape is a short-window pattern — and the encoder
    does the long-range work, which is what a CTC alignment over ~150 timesteps needs.
    Masking is explicit: the stem's stride-2 halves the length, so the mask is recomputed at
    the new resolution rather than assumed.
    """
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers as L

    inp = keras.Input((None, n_feat), name="feats", dtype="float32")
    x = L.Masking(mask_value=0.0)(inp) if False else inp        # mask handled via lengths
    x = L.Dense(dim, use_bias=False)(x)
    x = L.BatchNormalization()(x)
    x = L.Activation("swish")(x)

    def sep_block(y, stride=1):
        r = y
        y = L.DepthwiseConv1D(kernel, strides=stride, padding="same", use_bias=False)(y)
        y = L.BatchNormalization()(y)
        y = L.Activation("swish")(y)
        y = L.Conv1D(dim, 1, use_bias=False)(y)
        y = L.BatchNormalization()(y)
        if stride == 1:
            y = L.Add()([r, y])
        return L.Activation("swish")(y)

    x = sep_block(x, 1)
    x = sep_block(x, TIME_STRIDE)          # THE downsample. t_out() must mirror this.
    x = sep_block(x, 1)

    for _ in range(blocks):
        h = L.LayerNormalization()(x)
        h = L.MultiHeadAttention(num_heads=heads, key_dim=dim // heads, dropout=drop)(h, h)
        x = L.Add()([x, h])
        h = L.LayerNormalization()(x)
        h = L.Dense(dim * 2, activation="swish")(h)
        h = L.Dropout(drop)(h)
        h = L.Dense(dim)(h)
        x = L.Add()([x, h])

    x = L.LayerNormalization()(x)
    logits = L.Dense(n_classes, name="logits")(x)              # (B, T/stride, V+1)
    return keras.Model(inp, logits, name="fs_ctc")


class CTCTrainer:
    """Thin training driver. A custom loop rather than model.fit, because CTC needs
    logit_length and label_length per sample and threading those through fit's y_true is
    where CTC implementations usually go wrong."""

    def __init__(self, model, lr=1e-3, wd=1e-4, clip=1.0):
        import tensorflow as tf
        from tensorflow import keras
        self.tf = tf
        self.model = model
        try:
            self.opt = keras.optimizers.AdamW(learning_rate=lr, weight_decay=wd,
                                              clipnorm=clip)
        except (AttributeError, TypeError):
            self.opt = keras.optimizers.Adam(learning_rate=lr, clipnorm=clip)

    def loss_fn(self, logits, labels, logit_len, label_len, required_len=None):
        """CTC loss, with infeasible rows detected by LENGTH rather than by is_finite().

        ⚠️ Do not guard this with tf.math.is_finite. MEASURED on tf 2.17: an infeasible row
        does NOT produce inf or nan — tf.nn.ctc_loss floors the log-probability and returns a
        large FINITE value, ~707 where a healthy row is ~7-10. So an is_finite guard never
        fires, and those rows instead contribute ~90x the gradient of every real sample and
        quietly steer the model at nothing learnable. That is worse than a crash, because a
        crash is visible. (docs/FINGERSPELLING_DATA_FINDINGS.md finding 1 said -inf; it is
        wrong for TensorFlow and has been corrected.)

        `required_len` is label_length plus its adjacent repeats — see ctc_required_steps.
        Absent, it falls back to label_length, which under-counts repeats.
        """
        tf = self.tf
        loss = tf.nn.ctc_loss(labels=tf.cast(labels, tf.int32), logits=logits,
                              label_length=tf.cast(label_len, tf.int32),
                              logit_length=tf.cast(logit_len, tf.int32),
                              logits_time_major=False, blank_index=BLANK)
        need = label_len if required_len is None else required_len
        ok = tf.cast(logit_len, tf.int32) >= tf.cast(need, tf.int32)
        ok &= tf.math.is_finite(loss)                    # belt and braces, costs nothing
        safe = tf.where(ok, loss, tf.zeros_like(loss))
        return (tf.reduce_sum(safe) / tf.maximum(
            tf.reduce_sum(tf.cast(ok, tf.float32)), 1.0),
            tf.reduce_sum(tf.cast(~ok, tf.int32)))

    def step(self, feats, labels, logit_len, label_len, train=True, required_len=None):
        tf = self.tf
        with tf.GradientTape() as tape:
            logits = self.model(feats, training=train)
            loss, bad = self.loss_fn(logits, labels, logit_len, label_len, required_len)
        if train:
            g = tape.gradient(loss, self.model.trainable_variables)
            self.opt.apply_gradients(zip(g, self.model.trainable_variables))
        return loss, bad


# ══════════════════════════════════════════════════════════════════════════════════════════
# batching
# ══════════════════════════════════════════════════════════════════════════════════════════
def make_batches(idx, lengths, batch_frames=24000, shuffle=True, seed=0):
    """Length-bucketed batches with a FRAME budget rather than a fixed sample count.

    Lengths span 21..751 frames. A fixed batch size either wastes most of the padded tensor
    on short sequences or runs out of memory on long ones, so batches are grown until the
    padded frame count hits a budget. Sorting by length first keeps the padding small.
    """
    idx = np.asarray(idx)
    order = idx[np.argsort(lengths[idx], kind="stable")]
    batches, cur, mx = [], [], 0
    for i in order:
        m = max(mx, int(lengths[i]))
        if cur and m * (len(cur) + 1) > batch_frames:
            batches.append(np.array(cur)); cur, mx = [i], int(lengths[i])
        else:
            cur.append(i); mx = m
    if cur:
        batches.append(np.array(cur))
    if shuffle:
        np.random.default_rng(seed).shuffle(batches)
    return batches


def collate(batch_idx, feats_list, labels_list):
    T = max(len(feats_list[i]) for i in batch_idx)
    Lm = max(len(labels_list[i]) for i in batch_idx)
    B = len(batch_idx)
    X = np.zeros((B, T, N_FEAT), np.float32)
    Y = np.zeros((B, Lm), np.int32)                   # pad with BLANK; label_length gates it
    tl = np.zeros(B, np.int32)
    ll = np.zeros(B, np.int32)
    rl = np.zeros(B, np.int32)                        # required steps incl. repeat blanks
    for b, i in enumerate(batch_idx):
        f, y = feats_list[i], labels_list[i]
        X[b, :len(f)] = f
        Y[b, :len(y)] = y
        tl[b] = t_out(len(f))
        ll[b] = len(y)
        rl[b] = ctc_required_steps(y)
    return X, Y, tl, ll, rl


# ══════════════════════════════════════════════════════════════════════════════════════════
# evaluation
# ══════════════════════════════════════════════════════════════════════════════════════════
def cer(pred: str, gold: str) -> float:
    """Character error rate by Levenshtein distance, normalised by the gold length."""
    if not gold:
        return float(len(pred) > 0)
    prev = list(range(len(gold) + 1))
    for i, pc in enumerate(pred, 1):
        cur = [i]
        for j, gc in enumerate(gold, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (pc != gc)))
        prev = cur
    return prev[-1] / len(gold)


def evaluate(trainer, batches, feats_list, labels_list, phrases, parts, i2c):
    """Overall CER + per-signer CER.

    Finding 4 makes per-signer reporting mandatory, not optional: 33.5% of tracking variance
    is between signers, so a pooled number can hide a subgroup the tool simply fails for.
    """
    tf = trainer.tf
    tot_cer, tot_exact, n = 0.0, 0, 0
    by_signer = defaultdict(lambda: [0.0, 0])
    losses, bads = [], 0
    for b in batches:
        X, Y, tl, ll, rl = collate(b, feats_list, labels_list)
        logits = trainer.model(X, training=False)
        loss, bad = trainer.loss_fn(logits, Y, tl, ll, rl)
        losses.append(float(loss)); bads += int(bad)
        # greedy decode: time-major, collapse repeats, drop blanks
        dec, _ = tf.nn.ctc_greedy_decoder(
            tf.transpose(logits, [1, 0, 2]), tf.cast(tl, tf.int32), blank_index=BLANK)
        dense = tf.sparse.to_dense(dec[0], default_value=-1).numpy()
        for k, i in enumerate(b):
            hyp = decode([c for c in dense[k] if c >= 0], i2c)
            gold = phrases[i]
            e = cer(hyp, gold)
            tot_cer += e; tot_exact += (hyp == gold); n += 1
            s = by_signer[int(parts[i])]
            s[0] += e; s[1] += 1
    per = {p: v[0] / v[1] for p, v in by_signer.items()}
    return {"loss": float(np.mean(losses)) if losses else float("nan"),
            "cer": tot_cer / max(n, 1), "exact": tot_exact / max(n, 1), "n": n,
            "nonfinite": bads, "per_signer_cer": per}


# ══════════════════════════════════════════════════════════════════════════════════════════
# selftest
# ══════════════════════════════════════════════════════════════════════════════════════════
def selftest() -> int:
    print("=== SELFTEST (no data, no GPU needed) ===")
    ok = True

    def check(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")

    rng = np.random.default_rng(0)

    # 1. the feasibility filter must use the MODEL's stride, not raw T
    check(t_out(10, 2) == 5 and t_out(11, 2) == 6, "t_out = ceil(T/stride)")
    # a repeat-FREE label of length 20; [1]*20 would need 39 steps, not 20
    check(ctc_feasible(40, [(i % 5) + 1 for i in range(20)], 40),
          "T/2=20 >= L=20 (repeat-free) is feasible")
    check(not ctc_feasible(30, list(range(1, 21)), 30),
          "T/2=15 < L=20 is REJECTED (raw T=30 >= 20 would have passed)")
    check(not ctc_feasible(400, list(range(1, 21)), 5),
          "too few hand-frames per character is rejected")
    # the repeat rule, measured against tf.nn.ctc_loss (see ctc_required_steps)
    check(ctc_required_steps([1, 2, 3]) == 3, "no repeats -> L steps")
    check(ctc_required_steps([3, 3, 1]) == 4, "one adjacent repeat -> L+1 steps")
    check(ctc_required_steps([1, 1, 1]) == 5, "two adjacent repeats -> L+2 steps")
    # T=8 -> t_out=4. [3,3,1] needs 4 (fits); [1,1,1] needs 5 (does not). Same length-3
    # label, opposite verdicts -- which only the repeat rule can produce.
    check(ctc_feasible(8, [3, 3, 1], 8) and not ctc_feasible(8, [1, 1, 1], 8),
          "at T_out=4, [3,3,1] fits and [1,1,1] does not — same L, repeat rule decides")

    # 2. features: NaN in, no NaN out, and the tracked channel tells the truth
    seq = rng.standard_normal((12, N_POINTS, 3)).astype(np.float32)
    seq[:, L_HAND, :] = np.nan                       # right-dominant
    seq[3:6, R_HAND, :] = np.nan                     # a 3-frame hole
    F = features(seq)
    check(F.shape == (12, N_FEAT), f"feature shape {F.shape} == (12,{N_FEAT})")
    check(np.isfinite(F).all(), "no NaN or inf survives features()")
    check(F[:, -1].tolist() == [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
          "tracked channel marks exactly the untracked frames")
    check(np.abs(F[3:6, :84]).max() == 0.0, "untracked frames are ZEROED, not interpolated")

    # 3. dominance is per-sequence, and a left-dominant sequence is mirrored
    lseq = rng.standard_normal((8, N_POINTS, 3)).astype(np.float32)
    lseq[:, R_HAND, :] = np.nan
    check(dominant_side(lseq) == "L", "left-dominant sequence reads as L")
    check(dominant_side(seq) == "R", "right-dominant sequence reads as R")
    # mirroring must make a left hand's SHAPE match the same hand seen as right
    a = rng.standard_normal((6, N_POINTS, 3)).astype(np.float32)
    b = a.copy()
    a[:, L_HAND, :] = np.nan                                   # right-dominant
    b[:, R_HAND, :] = a[:, R_HAND, :].copy()
    b[:, L_HAND, :] = a[:, R_HAND, :].copy()
    b[:, L_HAND, 0] *= -1.0                                    # a mirrored left hand
    b[:, R_HAND, :] = np.nan                                   # ... presented as L-dominant
    fa, fb = features(a), features(b)
    check(np.allclose(fa[:, :42], fb[:, :42], atol=1e-5),
          "a mirrored left hand yields the SAME shape features as the right hand")

    # 4. charset round-trip
    c2i = build_charset(["abc", "cba x"])
    i2c = {v: k for k, v in c2i.items()}
    check(BLANK not in c2i.values(), "index 0 is reserved for the CTC blank")
    check(decode(encode("cab", c2i), i2c) == "cab", "charset round-trips")

    # 4b. the measured 2026-09-04 bug: an OBSERVED charset reindexes when shards are added.
    # The 4-shard run produced n_classes 52 (51 chars); the corpus has 59.
    few, many = build_charset(["ac"]), build_charset(["abc"])
    check(few["c"] != many["c"],
          f"an observed charset REINDEXES on a bigger shard mix (c: {few['c']} -> {many['c']}) "
          f"— this is why --charset exists")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / CHARSET_FILENAME
        p.write_text(json.dumps({c: i for i, c in enumerate("cba")}), encoding="utf-8")
        frozen, src = load_charset(["a"], str(p))            # data has 1 char, file has 3
        check(len(frozen) == 3 and frozen == {"a": 1, "b": 2, "c": 3},
              "a frozen charset beats the observed one AND is re-sorted, not file-ordered")
        check(src.endswith(CHARSET_FILENAME), "charset_source records the file it came from")
    obs, src = load_charset(["zz"], None, search=False)      # deterministic on Kaggle too
    check(len(obs) == 1 and "NOT corpus-wide" in src,
          "a missing charset file falls back to observed and SAYS SO in charset_source")
    check(encode("ab", {"a": 1}) == [1],
          "encode() drops unknown characters — which is why train() aborts on any")

    # 5. signer-disjoint split
    parts = np.array([1] * 20 + [2] * 20 + [3] * 20 + [4] * 20 + [5] * 20)
    hr = np.concatenate([np.full(20, 0.2 * i) for i in range(1, 6)])
    tr, va, vs = signer_split(parts, hr, val_frac=0.2)
    check(len(set(parts[tr]) & set(parts[va])) == 0, "train and val share NO signer")
    check(len(va) > 0 and len(tr) > 0, "both splits are non-empty")

    # 5b. pinning the val signers is what makes a scale-up comparison controlled
    tr2, va2, vs2 = signer_split(parts, hr, force=[2, 4])
    check(sorted(vs2) == [2, 4], f"--val-signers pins the holdout exactly (got {sorted(vs2)})")
    check(set(parts[va2].tolist()) == {2, 4} and 2 not in set(parts[tr2].tolist()),
          "a pinned holdout is still signer-DISJOINT")
    tr3, va3, vs3 = signer_split(parts, hr, force=[4, 999])     # 999 does not exist
    check(sorted(vs3) == [4], "an absent forced signer is dropped, not silently accepted")

    # 6. batching respects the frame budget
    lens = np.array([10, 12, 400, 410, 11])
    bs = make_batches(np.arange(5), lens, batch_frames=1000, shuffle=False)
    check(all(max(lens[b]) * len(b) <= 1000 or len(b) == 1 for b in bs),
          "every batch fits the frame budget (or is a single long sequence)")

    # 7. CER
    check(cer("abc", "abc") == 0.0 and abs(cer("abd", "abc") - 1 / 3) < 1e-9, "CER is correct")

    # 8. a real forward+backward pass, and the loss must be FINITE
    try:
        import tensorflow as tf
        m = build_model(N_FEAT, len(c2i) + 1, dim=32, blocks=1, heads=2, kernel=5)
        tr_ = CTCTrainer(m, lr=1e-3)
        T = 40
        X = rng.standard_normal((3, T, N_FEAT)).astype(np.float32)
        Y = np.array([[1, 2, 3], [2, 1, 0], [3, 3, 1]], np.int32)
        tl = np.full(3, t_out(T), np.int32)
        ll = np.array([3, 2, 3], np.int32)
        out = m(X, training=False)
        check(out.shape[1] == t_out(T),
              f"model emits t_out(T)={t_out(T)} steps for T={T} (got {out.shape[1]}) "
              f"-- this is the check that keeps the filter and the architecture in step")
        rl = np.array([ctc_required_steps(y) for y in Y.tolist()], np.int32)
        l0, bad0 = tr_.step(X, Y, tl, ll, required_len=rl)
        check(np.isfinite(float(l0)) and int(bad0) == 0, f"CTC loss is finite ({float(l0):.3f})")
        l1, _ = tr_.step(X, Y, tl, ll, required_len=rl)
        check(np.isfinite(float(l1)), "a second step stays finite (no nan blow-up)")
        # ⚠️ THE check this file exists for. An infeasible row does NOT give inf/nan — tf
        # returns ~707 where healthy rows are ~7-10, so an is_finite guard never fires and
        # those rows silently dominate the gradient. The guard must be by LENGTH.
        bad_tl = np.array([1, t_out(T), t_out(T)], np.int32)
        raw = tf.nn.ctc_loss(labels=Y, logits=m(X, training=False),
                             label_length=ll, logit_length=bad_tl,
                             logits_time_major=False, blank_index=BLANK).numpy()
        # thresholds kept loose: the model is randomly initialised here, so the healthy
        # losses move run to run. What must hold is that the bad row is FINITE (so is_finite
        # cannot catch it) and an order of magnitude larger (so it dominates the gradient).
        check(np.isfinite(raw).all() and raw[0] > 300
              and raw[0] > 5 * max(raw[1], raw[2]),
              f"an infeasible row returns a LARGE FINITE loss ({raw[0]:.0f} vs "
              f"{raw[1]:.1f}/{raw[2]:.1f} = {raw[0]/max(raw[1], raw[2]):.0f}x) — "
              f"is_finite would NOT catch it")
        l2, bad2 = tr_.step(X, Y, bad_tl, ll, train=False, required_len=rl)
        check(int(bad2) == 1 and np.isfinite(float(l2)) and float(l2) < 20 * float(l0),
              f"the length guard excludes it: {int(bad2)} row dropped, batch loss "
              f"{float(l2):.2f} stays near the healthy {float(l0):.2f}")
    except ImportError:
        print("  skip  TensorFlow not installed — model checks skipped")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOMETHING FAILED — see above"))
    return 0 if ok else 1


# ══════════════════════════════════════════════════════════════════════════════════════════
def train(args) -> int:
    import tensorflow as tf

    npz = Path(args.npz)
    if not npz.exists():
        sys.exit(f"[err] {npz} not found. Build it with subset_landmarks.py, then attach the "
                 f"output as a Kaggle DATASET (notebook output is not an input).")
    print(f"[load] {npz}")
    z = np.load(npz, allow_pickle=False)
    frames = z["frames"]
    starts, lengths = z["starts"], z["lengths"]
    phrases = [str(p) for p in z["phrase"]]
    parts = z["participant"]
    print(f"[load] {len(lengths):,} sequences, {len(frames):,} frames, "
          f"{len(set(parts.tolist()))} participants, {frames.nbytes/1e9:.2f} GB")

    # ── features + the feasibility filter, in one pass ────────────────────────────────────
    t0 = time.time()
    feats_list, labels_list, keep, hand_rates = [], [], [], []
    c2i, charset_source = load_charset(phrases, args.charset)
    i2c = {v: k for k, v in c2i.items()}
    print(f"[charset] {len(c2i)} characters -> {len(c2i)+1} classes with blank: "
          f"{''.join(sorted(c2i))!r}")
    print(f"[charset] source: {charset_source}")

    # A character present in the data but absent from the charset is dropped by encode(),
    # which silently TRUNCATES the label and trains the model against a phrase nobody wrote.
    # Refuse rather than report a number built on corrupted labels.
    unknown = Counter(c for p in phrases for c in p if c not in c2i)
    if unknown:
        sys.exit(f"[err] {sum(unknown.values())} character occurrences in the data are not in "
                 f"the charset: {dict(unknown.most_common(20))}\n"
                 f"      encode() would drop them and every phrase containing one would train "
                 f"against a truncated\n      label. Pass the matching --charset "
                 f"({CHARSET_FILENAME}) instead.")

    dropped = Counter()
    for i in range(len(lengths)):
        s, n = int(starts[i]), int(lengths[i])
        seq = frames[s:s + n]
        F = features(seq)
        hf = float(F[:, -1].sum())
        hand_rates.append(hf / max(n, 1))
        y = encode(phrases[i], c2i)
        if not y:
            dropped["empty phrase"] += 1
        elif not ctc_feasible(n, y, hf):
            # separate the two reasons: the repeat correction is a finding, not a detail
            if t_out(n) >= len(y) and t_out(n) < ctc_required_steps(y):
                dropped["infeasible ONLY because of repeated characters"] += 1
            elif t_out(n) < len(y):
                dropped["infeasible: T_out < phrase_len"] += 1
            else:
                dropped["infeasible: fewer hand-frames than characters"] += 1
        else:
            keep.append(i)
        feats_list.append(F)
        labels_list.append(y)
    hand_rates = np.array(hand_rates)
    keep = np.array(keep, np.int64)

    # `frames` is the single largest object in the process and NOTHING reads it after this
    # pass — features_list holds everything the model sees. Measured on the 4-shard subset:
    # frames 0.57 GB vs features 0.26 GB, i.e. raw landmarks are 2.2x the derived features.
    # Scaled to all 68 shards that is 9.7 GB held for no reason against a Kaggle GPU
    # notebook's ~13 GB of host RAM, so the training loop would OOM on memory it does not
    # use. Freeing it drops steady-state from ~14 GB to ~4.4 GB at 68 shards.
    held = frames.nbytes / 1e9
    del frames, z
    gc.collect()
    print(f"[mem] released {held:.2f} GB of raw landmarks — features_list "
          f"({sum(f.nbytes for f in feats_list)/1e9:.2f} GB) is all the model reads")

    print(f"[filter] kept {len(keep):,}/{len(lengths):,} ({100*len(keep)/len(lengths):.1f}%) "
          f"in {time.time()-t0:.0f}s")
    for k, v in dropped.most_common():
        print(f"          dropped {v:5} — {k}")
    if not len(keep):
        sys.exit("[err] the filter removed everything — check the charset and lengths")

    # ── signer-disjoint, quality-stratified split ─────────────────────────────────────────
    forced = ([int(s) for s in args.val_signers.replace(",", " ").split()]
              if args.val_signers else None)
    tr_i, va_i, val_signers = signer_split(parts[keep], hand_rates[keep],
                                           val_frac=args.val_frac, seed=args.seed,
                                           force=forced)
    tr_i, va_i = keep[tr_i], keep[va_i]
    print(f"[split] train {len(tr_i):,} seq / {len(set(parts[tr_i].tolist()))} signers | "
          f"val {len(va_i):,} seq / {len(val_signers)} signers")
    print(f"        val signers {sorted(val_signers)}")
    print(f"        hand_rate  train {hand_rates[tr_i].mean():.3f}  val {hand_rates[va_i].mean():.3f}"
          f"   (stratified, so these should be close)")
    assert not (set(parts[tr_i].tolist()) & set(parts[va_i].tolist())), "SIGNER LEAK"

    # ── model ─────────────────────────────────────────────────────────────────────────────
    model = build_model(N_FEAT, len(c2i) + 1, dim=args.dim, blocks=args.blocks,
                        heads=args.heads, kernel=args.kernel, drop=args.dropout)
    n_par = int(sum(np.prod(v.shape) for v in model.trainable_variables))
    print(f"[model] {n_par/1e6:.2f}M params | features {N_FEAT} | classes {len(c2i)+1} | "
          f"TIME_STRIDE {TIME_STRIDE}")
    trainer = CTCTrainer(model, lr=args.lr, wd=args.wd)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "charset.json").write_text(json.dumps({
        "note": "FROZEN character->index map. index 0 is the CTC blank. Load this at "
                "inference; recomputing it from a different shard mix silently remaps "
                "every label.",
        "time_stride": TIME_STRIDE, "n_classes": len(c2i) + 1, "char_to_index": c2i,
        "charset_source": charset_source,
    }, indent=1), encoding="utf-8")

    va_batches = make_batches(va_i, lengths, args.batch_frames, shuffle=False)
    hist, best = [], float("inf")
    for ep in range(1, args.epochs + 1):
        tb = make_batches(tr_i, lengths, args.batch_frames, shuffle=True, seed=args.seed + ep)
        losses, bads, t1 = [], 0, time.time()
        for bi, b in enumerate(tb):
            X, Y, tl, ll, rl = collate(b, feats_list, labels_list)
            loss, bad = trainer.step(X, Y, tl, ll, train=True, required_len=rl)
            losses.append(float(loss)); bads += int(bad)
            if not np.isfinite(losses[-1]):
                sys.exit(f"[err] non-finite training loss at epoch {ep} batch {bi} — the "
                         f"feasibility filter let something through")
        ev = evaluate(trainer, va_batches, feats_list, labels_list, phrases, parts, i2c)
        row = {"epoch": ep, "train_loss": float(np.mean(losses)), "val_loss": ev["loss"],
               "val_cer": ev["cer"], "val_exact": ev["exact"],
               "nonfinite_train": bads, "nonfinite_val": ev["nonfinite"],
               "sec": round(time.time() - t1, 1)}
        hist.append(row)
        print(f"[ep {ep:3}] train {row['train_loss']:7.3f} | val {ev['loss']:7.3f} "
              f"CER {ev['cer']:.4f} exact {ev['exact']:.3f} | {row['sec']:.0f}s"
              + (f" | ⚠ {bads} non-finite" if bads else ""))
        if ev["cer"] < best:
            best = ev["cer"]
            model.save_weights(str(out / "fs_ctc.weights.h5"))
            try:
                model.export(str(out / "savedmodel_fs_ctc"))
            except Exception as e:
                print(f"        [warn] SavedModel export failed ({type(e).__name__})")
        (out / "history.json").write_text(json.dumps(hist, indent=1), encoding="utf-8")

    ev = evaluate(trainer, va_batches, feats_list, labels_list, phrases, parts, i2c)
    per = ev["per_signer_cer"]
    print(f"\n[final] val CER {ev['cer']:.4f}  exact-phrase {ev['exact']:.3f}  n={ev['n']}")
    print(f"[per-signer CER] {len(per)} held-out signers — MANDATORY, not optional "
          f"(33.5% of tracking variance is between signers)")
    for p, c in sorted(per.items(), key=lambda kv: kv[1]):
        print(f"    p{p:<5} CER {c:.4f}")
    if per:
        print(f"    spread: best {min(per.values()):.4f}  worst {max(per.values()):.4f}  "
              f"ratio {max(per.values())/max(min(per.values()),1e-9):.2f}x")
    (out / "report.json").write_text(json.dumps({
        "best_val_cer": best, "final": {k: v for k, v in ev.items()},
        "val_signers": sorted(int(p) for p in val_signers),
        "val_signers_pinned": forced is not None,
        "n_train": int(len(tr_i)), "n_val": int(len(va_i)),
        "time_stride": TIME_STRIDE, "n_classes": len(c2i) + 1, "features": N_FEAT,
        "charset_source": charset_source,
        "params": n_par, "history": hist,
        "filter": {k: v for k, v in dropped.items()},
    }, indent=1), encoding="utf-8")
    print(f"\n[ok] {out}/report.json  charset.json  fs_ctc.weights.h5  savedmodel_fs_ctc/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz", default="/kaggle/input/deafference-fs75/fs75.npz")
    ap.add_argument("--charset", default=None,
                    help=f"the competition's {CHARSET_FILENAME} (59 characters). Auto-detected "
                         f"under /kaggle/input if the competition is attached. WITHOUT it the "
                         f"charset is derived from the attached shards only — the first run "
                         f"got 51 characters, not 59, and indices shift when shards are added.")
    ap.add_argument("--out", default="/kaggle/working/fs_out")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--dim", type=int, default=192)
    ap.add_argument("--blocks", type=int, default=4)
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--kernel", type=int, default=17)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--batch-frames", type=int, default=24000,
                    help="padded frames per batch (a budget, not a sample count — lengths "
                         "span 21..751 so a fixed batch size either wastes the tensor or OOMs)")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--val-signers", default=None,
                    help="comma-separated participant ids to hold out, overriding the "
                         "stratified draw. Use it to pin the SAME signers across a scale-up "
                         "so a CER delta is attributable to data and not to an easier split. "
                         "The 4-shard run held out: "
                         "1,15,56,73,89,128,147,154,158,161,196,203,225")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--selftest", action="store_true",
                    help="prove the mechanism with no data and no GPU")
    args = ap.parse_args()
    return selftest() if args.selftest else train(args)


if __name__ == "__main__":
    raise SystemExit(main())
