#!/usr/bin/env python3
"""Train an LSL classifier on the landmark arrays extract_lsl_landmarks.py produced.

THE SPLIT IS THE WHOLE POINT OF THIS FILE
-----------------------------------------
This corpus is ~6 samples per class from ONE signer, with no signer IDs. Every accuracy
number it can produce is therefore about a person, not about a language, and the only
question worth engineering is how badly it will flatter itself.

A RANDOM split would be a lie. Within one label the 6 takes come from 3-4 recording
sessions, and takes from the same session share lighting, clothing, camera placement,
distance, and that day's articulation. Put two takes from one session on opposite sides of
a random split and the model can match on the session instead of the sign -- the same
class of leak as a non-signer-disjoint split, which is the error that made the 250-word
ASL model unmeasurable.

So the split here is DATE-DISJOINT, leave-one-date-out. 97% of labels in this corpus span
>=2 dates and 91% span >=3, so it is actually available. It is not as strong as
signer-disjoint -- nothing here can be, with one signer -- but it is the strongest split
the data supports, and the gap between it and a random split is the size of the lie
avoided.

WHY LEAVE-ONE-DATE-OUT AND NOT A SINGLE HOLDOUT
-----------------------------------------------
At 6 samples per class a single held-out date puts 1-4 test samples on each class. One
draw from that is noise, not a measurement. Every date is held out in turn and the spread
across folds is reported next to the mean, because with a test set this small the spread
IS the result: a mean of 0.80 that ranges 0.55-0.95 across folds is not an 0.80 model.

WHY IT FINE-TUNES INSTEAD OF TRAINING FROM SCRATCH
--------------------------------------------------
~100 clips cannot train a transformer backbone. The ASL 30-word model in artifacts/ was
trained on the same 75-point layout in the same normalised coordinate space, so its
backbone is a landmark encoder that already knows what hands doing signs look like; only
the classifier head is language-specific. `by_name=True, skip_mismatch=True` is the same
transfer path train.py already uses for its 250 -> 30 step, and the head is the one layer
whose shape deliberately mismatches.

    python training/train_lsl.py --npz lsl_lesson1.npz --eval     # honest number
    python training/train_lsl.py --npz lsl_lesson1.npz --final    # ship the demo model
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "training"))

import tensorflow as tf                                             # noqa: E402
from tensorflow import keras                                        # noqa: E402
import train as T                                                   # noqa: E402

SEED = 42


def transfer_backbone(model, h5_path) -> int:
    """Copy the ASL backbone into `model` layer by layer, and RETURN HOW MANY LANDED.

    `model.load_weights(h5, by_name=True, skip_mismatch=True)` -- the call train.py:928
    uses -- is a NO-OP on Keras 3 and says nothing. `by_name` is a Keras 2 argument; Keras 3
    swallows it in **kwargs and matches structurally instead, and `skip_mismatch=True` then
    silently swallows every mismatch. Measured on this exact pair: it reported success and
    changed 0 of 93 tensors, while 27 of 31 layer names in the file match the model's. A
    whole fine-tune would have run from scratch and been reported as a transfer.

    So the copy is explicit, matched by name AND shape, counted, and the count is returned
    so the caller can refuse to continue on zero. A transfer step that cannot report failure
    is the same defect as a metric that cannot fail.
    """
    import h5py
    n_layers = n_tensors = 0
    with h5py.File(h5_path, "r") as f:
        src = f["layers"]
        for layer in model.layers:
            if not layer.weights or layer.name not in src:
                continue
            g = src[layer.name].get("vars")
            if g is None:
                continue
            vals = [g[k][()] for k in sorted(g.keys(), key=int)]
            if len(vals) != len(layer.weights):
                continue
            if any(tuple(v.shape) != tuple(w.shape) for v, w in zip(vals, layer.weights)):
                continue                      # the classifier head, legitimately: 30 != 18
            for w, v in zip(layer.weights, vals):
                w.assign(v)
            n_layers += 1
            n_tensors += len(vals)
    return n_layers, n_tensors


def init_backbone(model, init):
    """Apply the transfer and FAIL LOUDLY if it did nothing."""
    if not init:
        print("[init] FROM SCRATCH (no backbone)")
        return
    nl, nt = transfer_backbone(model, init)
    if nl == 0:
        raise SystemExit(
            f"[err] transfer from {Path(init).name} copied NOTHING. Training would run from "
            f"scratch and be reported as a fine-tune. Check that the checkpoint was written "
            f"by this same build_model().")
    print(f"[init] fine-tuning from {Path(init).name}: "
          f"{nl} layers / {nt} tensors copied, classifier head left fresh")


def trim_to_sign(x: np.ndarray, pad: int = 2) -> np.ndarray:
    """Cut a clip down to the part where a hand is actually in shot.

    THIS IS THE DIFFERENCE BETWEEN CHANCE AND A MODEL. These recordings are whole takes:
    the signer signs and then lowers their hands, and the camera keeps rolling. Measured
    over all 108 lesson-1 clips, dominant-hand presence by decile of clip runs

        62% 70% 69% 61% 40% 29% 18% 11% 7% 1%

    -- the last detection sits at a median 40% of the way in, so roughly 60% of every clip
    is a person standing still. `fit_to_maxlen` then resizes the WHOLE take into 64 frames,
    which spends ~38 of them on dead air and compresses the sign itself into ~26.

    Inside the active span, hand detection is 97%. So the corpus is not sparse at all; the
    sparsity was entirely an artifact of including the tail. Trimming to the span turns
    61.6% hand-free frames into ~3%.

    Done HERE and not in the extractor on purpose: the .npz keeps the whole take, so this
    threshold stays a training-time decision that can be changed without re-running 15
    minutes of MediaPipe over the videos, and nothing is destroyed at write time.

    Either hand counts. Handedness is not annotated in this corpus, and a two-handed sign
    can start with the non-dominant hand, so keying on the right hand alone would clip the
    front off those.
    """
    lh = ~np.isnan(x[:, 33, 0])
    rh = ~np.isnan(x[:, 54, 0])
    live = np.flatnonzero(lh | rh)
    if len(live) < 2:
        return x                                  # no hand anywhere: leave it for the caller
    a = max(0, live[0] - pad)
    b = min(len(x), live[-1] + 1 + pad)
    return x[a:b]


def load(npz: Path, trim: bool = True):
    d = np.load(npz, allow_pickle=True)
    X, y, date = list(d["X"]), list(d["y"]), list(d["date"])
    if trim:
        X = [trim_to_sign(np.asarray(x, np.float32)) if len(x) else x for x in X]
    keep = [i for i in range(len(X)) if len(X[i]) > 0]
    if len(keep) < len(X):
        print(f"[warn] dropping {len(X)-len(keep)} clip(s) with no usable frame")
    X = [np.asarray(X[i], np.float32) for i in keep]
    y = [y[i] for i in keep]
    date = [date[i] for i in keep]
    labels = sorted(set(y))
    idx = {w: i for i, w in enumerate(labels)}
    return X, np.array([idx[w] for w in y]), np.array(date), labels


def batches(X, y, order, rng, n_classes, training: bool, bs: int):
    """(B,64,75,3) float32 batches. Augmentation ONLY on the training side.

    fit_to_maxlen, not time_resize: short clips are NaN-PADDED and long ones resized. That
    asymmetry is train.py's and live_demo's shared convention and the model's mask depends
    on it -- stretching a short clip instead would hand the model a slowed-down sign.
    """
    for s in range(0, len(order), bs):
        ids = order[s:s + bs]
        xb = np.stack([T.fit_to_maxlen(T.augment(X[i], rng) if training else X[i])
                       for i in ids]).astype(np.float32)
        yield xb, keras.utils.to_categorical(y[ids], n_classes).astype(np.float32)


def run_fold(X, y, date, labels, held, init_from, epochs, bs, lr, quiet=True):
    n = len(labels)
    tr = np.flatnonzero(date != held)
    te = np.flatnonzero(date == held)
    # A fold is only meaningful if the held-out date actually tests classes the model was
    # trained on. Classes missing from train cannot be predicted and classes missing from
    # test are simply unexamined; both are reported so a high score cannot come from a
    # fold that quietly tested three classes.
    tr_c, te_c = set(y[tr]), set(y[te])
    usable = sorted(tr_c & te_c)
    # A DEGENERATE FOLD IS NOT A DATA POINT. This corpus is one bulk session plus a few
    # single-take ones -- lesson 1 is 70 clips on 20260730, 20 on 20260729, 17 on 20260711
    # and exactly 1 on 20260830 -- so plain leave-one-date-out produces folds that cannot
    # mean anything: holding out 20260830 tests ONE class with one clip, and holding out
    # 20260730 leaves 2 training samples per class. Averaging those into the headline number
    # would let the arithmetic hide that only two folds were real.
    #
    # So a fold has to test at least half the classes and keep at least half the clips for
    # training, and the ones that fail are named rather than dropped quietly.
    if not usable:
        return {"date": held, "skipped": "no class both trained and tested"}
    if len(usable) < n / 2:
        return {"date": held, "skipped": f"tests only {len(usable)}/{n} classes"}
    if len(tr) < 0.5 * len(y):
        return {"date": held,
                "skipped": f"only {len(tr)} of {len(y)} clips left to train on"}
    model = T.build_model(num_classes=n)
    init_backbone(model, init_from)
    model.compile(optimizer=keras.optimizers.Adam(lr),
                  # from_logits=True is NOT optional: build_model's `classifier` is a bare
                  # Dense with no softmax, so the head emits LOGITS. Compiled without this
                  # the loss treats logits as probabilities, and it does not crash -- it
                  # trains to a dead stop. Measured: loss stuck at ~8.0, train accuracy
                  # pinned at 0.0655 (chance is 0.056) for 15 epochs, and predictions
                  # collapsed onto 7 of 18 classes. The tell was `mean max-prob 12.452`,
                  # which is impossible for a probability. train.py:956 does the same.
                  loss=keras.losses.CategoricalCrossentropy(
                      from_logits=True, label_smoothing=0.1),
                  metrics=["accuracy"])
    rng = np.random.default_rng(SEED)
    for ep in range(epochs):
        order = rng.permutation(tr)
        for xb, yb in batches(X, y, order, rng, n, True, bs):
            model.train_on_batch(xb, yb)
    # Score ONLY the classes this fold could actually decide.
    mask = np.array([i for i in te if y[i] in usable])
    probs = []
    for xb, _ in batches(X, y, mask, rng, n, False, bs):
        probs.append(model.predict(xb, verbose=0))
    p = np.concatenate(probs)
    acc = float((p.argmax(1) == y[mask]).mean())
    top3 = float(np.mean([y[mask][k] in np.argsort(-p[k])[:3] for k in range(len(mask))]))
    del model
    keras.backend.clear_session()
    return {"date": held, "n_test": len(mask), "n_train": len(tr),
            "classes_tested": len(usable), "acc": acc, "top3": top3}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz", type=Path, required=True)
    ap.add_argument("--eval", action="store_true", help="leave-one-date-out CV")
    ap.add_argument("--final", action="store_true", help="train on ALL data and export")
    # DEFAULT IS SCRATCH, and that is a finding, not a preference.
    #
    # artifacts/weights_mvp30_fold0_seed42.weights.h5 does NOT match today's build_model().
    # Checked layer by layer: `stem_dense`, `stem_bn`, `top_dense` and `classifier` are absent
    # from the file under those names; `multi_head_attention*` store their weights nested, so
    # a flat read finds 0 of 8; and `dense_3/4/5/8/9` mismatch on SHAPE -- (192,192) against
    # (192,384) -- which is the signature of Keras auto-names (`dense_N`) lining up against
    # different layers in the two builds. The checkpoint is from an earlier architecture
    # revision.
    #
    # That makes name-based transfer from it actively dangerous rather than merely useless:
    # the 21 layers that DO match by name and shape might be the same layers or might be
    # coincidences, and nothing in the copy can tell which. Loading a wrong tensor is worse
    # than loading none, because it trains and reports a number either way.
    #
    # Pass --init explicitly once a checkpoint written by THIS build_model() exists.
    ap.add_argument("--init", type=Path, default=None,
                    help="backbone checkpoint to fine-tune from. Must come from the same "
                         "build_model() as this run -- see the note in the source.")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--out", type=Path, default=REPO / "artifacts_lsl")
    args = ap.parse_args()

    X, y, date, labels = load(args.npz)
    print(f"[data] {len(X)} clips, {len(labels)} classes, {len(set(date))} recording dates")
    print(f"[data] samples/class: {dict(sorted(Counter(Counter(y).values()).items()))}")
    init = str(args.init) if args.init and Path(args.init).exists() else None

    if args.eval:
        rows, skipped = [], []
        for held in sorted(set(date)):
            r = run_fold(X, y, date, labels, held, init, args.epochs, args.batch, args.lr)
            if r.get("skipped"):
                skipped.append(r)
                print(f"  hold out {held}: SKIPPED -- {r['skipped']}")
                continue
            rows.append(r)
            print(f"  hold out {held}: train {r['n_train']:3d} / test {r['n_test']:3d} "
                  f"over {r['classes_tested']:2d} classes -> acc {r['acc']:.3f}  "
                  f"top3 {r['top3']:.3f}", flush=True)
        if rows:
            a = np.array([r["acc"] for r in rows])
            t = np.array([r["top3"] for r in rows])
            w = np.array([r["n_test"] for r in rows], float)
            print(f"\n[LEAVE-ONE-DATE-OUT, {len(rows)} folds]")
            print(f"  top-1  mean {a.mean():.3f}  weighted {np.average(a, weights=w):.3f}  "
                  f"range {a.min():.3f}-{a.max():.3f}  sd {a.std():.3f}")
            print(f"  top-3  mean {t.mean():.3f}  range {t.min():.3f}-{t.max():.3f}")
            if skipped:
                print(f"  {len(skipped)} of {len(rows)+len(skipped)} dates were NOT usable "
                      f"as folds: " + "; ".join(f"{r['date']} ({r['skipped']})"
                                                for r in skipped))
            # The spread is not a footnote. Say so where it will be read.
            print(f"\n  NOTE: single signer, no signer IDs. This measures held-out SESSIONS "
                  f"of one\n  person, not held-out people. It is an upper bound on what a "
                  f"stranger would get.")
            (args.out).mkdir(parents=True, exist_ok=True)
            (args.out / "eval_lsl.json").write_text(json.dumps(
                {"folds": rows, "mean_acc": float(a.mean()), "sd": float(a.std()),
                 "mean_top3": float(t.mean()), "labels": labels,
                 "split": "leave-one-date-out (date-disjoint)",
                 "caveat": "single signer, no signer IDs -- not signer-disjoint",
                 "skipped_folds": skipped},
                ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  wrote {args.out / 'eval_lsl.json'}")

    if args.final:
        n = len(labels)
        model = T.build_model(num_classes=n)
        init_backbone(model, init)
        model.compile(optimizer=keras.optimizers.Adam(args.lr),
                      # from_logits=True is NOT optional: build_model's `classifier` is a bare
                  # Dense with no softmax, so the head emits LOGITS. Compiled without this
                  # the loss treats logits as probabilities, and it does not crash -- it
                  # trains to a dead stop. Measured: loss stuck at ~8.0, train accuracy
                  # pinned at 0.0655 (chance is 0.056) for 15 epochs, and predictions
                  # collapsed onto 7 of 18 classes. The tell was `mean max-prob 12.452`,
                  # which is impossible for a probability. train.py:956 does the same.
                  loss=keras.losses.CategoricalCrossentropy(
                      from_logits=True, label_smoothing=0.1),
                      metrics=["accuracy"])
        rng = np.random.default_rng(SEED)
        allid = np.arange(len(X))
        for ep in range(args.epochs):
            order = rng.permutation(allid)
            loss = []
            for xb, yb in batches(X, y, order, rng, n, True, args.batch):
                loss.append(model.train_on_batch(xb, yb)[0])
            if (ep + 1) % 10 == 0:
                print(f"  epoch {ep+1:3d}/{args.epochs}  loss {np.mean(loss):.4f}", flush=True)
        args.out.mkdir(parents=True, exist_ok=True)
        model.export(args.out / "savedmodel_fold0")
        # live_demo reads ["words"] and uses list position as the class index, so this file
        # and the model's output order are the same fact written twice. Written here, from
        # the same `labels` the model was trained on, so they cannot disagree.
        (args.out / "vocab_lsl.json").write_text(json.dumps(
            {"vocab_version": "lsl-v1", "num_classes": n, "words": labels,
             "source": str(args.npz.name),
             "note": "Index = training label = position in `words`. Arabic glosses, LSL."},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ok] exported {args.out/'savedmodel_fold0'} + vocab_lsl.json ({n} words)")


if __name__ == "__main__":
    main()
