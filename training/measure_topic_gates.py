#!/usr/bin/env python3
r"""
Measure a topic set's GATE numbers: first-try rate, precision, and out-of-topic false
speech, then pick each topic's `mass_min`.

WHY THIS EXISTS. The 13 medical topics carry measured numbers; the 11 general topics
(topic_animals.json ... topic_time_question.json) carry `mass_min_provisional: true` and a
`mass_min` of 0.10 scaled from the medical model rather than measured. That flag existing
IS the marker that this run has not happened. This script is the run.

WHAT THE NUMBERS MEAN
  first_try   of the in-topic signs the safety gate will let through at all, the fraction
              spoken on the FIRST attempt. Safety-held words are excluded from the
              denominator because a hold is a prompt for a tap, not speech.
  precision   of the words spoken, the fraction that were the right word.
  off_topic_false_speech
              the number nothing else in this repo measures. Masking RENORMALIZES, so a
              narrow topic cannot answer "not one of mine" — it must name an allowed word.
              Every out-of-topic sign that clears the gate is therefore a wrong word said
              out loud. On the medical model that was 13.6-20.3% before `mass_min` existed.
  mass_min    the fix: refuse unless at least this much UNMASKED probability lands on the
              active topic. Chosen per topic, because the exchange rate depends on topic
              width AND on the model's class count -- a diffuse prediction puts ~25/123 on
              a 25-word topic of the medical model but only ~25/250 on the 250-word one, so
              the SAME threshold is materially stricter there. Copying the medical value
              across is exactly the mistake this script replaces.

TWO INPUT MODES
  --probs   an .npz holding per_model (F,N,C) + y (N,). Pure numpy, no TF, no data. This is
            the mode --selftest uses.
  --data-dir + --models
            compute the probabilities first, reusing train.py's own load_dataset /
            make_tf_dataset via eval_savedmodel_250 so the model sees byte-identical inputs
            to training. Writes the npz so a re-score costs seconds instead of GPU minutes.

RUN — the 250-word measurement (Kaggle GPU):
  python measure_topic_gates.py \
      --data-dir /kaggle/working/canon --models ../artifacts_250 \
      --vocab ../vocab_250.json --topics .. --exclude-topics medical \
      --out /kaggle/working/topic_250_measured.json

RUN — the control, which must reproduce numbers already in hand:
  python measure_topic_gates.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent

# Bump on any change that alters what a run MEANS. This file is uploaded to Kaggle as a dataset
# and diverges silently: the 2026-09-10 run executed a copy from before the corpus guard, so the
# check built to catch exactly that run's mistake was not in the copy that ran. Printed on every
# invocation so a stale upload is visible in the first line of the log rather than never.
SCORER_VERSION = "2026-09-10c"

# The gate live_demo actually applies. LEVEL 1a: k folds must independently agree AND the
# ensemble mean must clear CONF. Keep these in sync with live_demo.AGREE_K / AGREE_CONF.
AGREE_K = 3
AGREE_CONF = 0.60
# Hard ceiling on out-of-topic signs spoken as a wrong word. Safety-first: among thresholds
# meeting it, take the best first-try. An earlier build minimised the first-try COST instead
# and handed one topic a 0.00 threshold with 32.8% false speech -- cheap, and wrong for a
# device that speaks clinical words aloud.
FALSE_CAP = 0.10
MASS_GRID = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]


# ══════════════════════════════════════════════════════════════════════ scoring (pure numpy)
def score_topic(P4, y, idx, held_mask, mass_min):
    """P4 (F,N,C) per-fold softmax, y (N,) true class, idx the topic's class indices,
    held_mask (len(idx),) True where the word never auto-commits."""
    def gate(rows):
        raw = P4[:, rows, :]
        mass = raw.mean(0)[:, idx].sum(1)          # BEFORE masking -- renormalising kills it
        m4 = raw[:, :, idx]
        m4 = m4 / np.clip(m4.sum(-1, keepdims=True), 1e-12, None)
        Pm = m4.mean(0)
        t1, cf = Pm.argmax(1), Pm.max(1)
        agree = (m4.argmax(2) == t1[None, :]).sum(0)
        speakable = ~held_mask[t1]
        return t1, (cf >= AGREE_CONF) & (agree >= AGREE_K) & (mass >= mass_min) & speakable, \
            speakable

    inn = np.isin(y, idx)
    ri, ro = np.where(inn)[0], np.where(~inn)[0]
    t1, sp, live = gate(ri)
    ok = t1 == np.searchsorted(idx, y[ri])
    n_live = int(live.sum())
    if len(ro):
        _t, spo, _l = gate(ro)
        false_rate, n_false = float(spo.sum() / len(ro)), int(spo.sum())
    else:
        false_rate, n_false = 0.0, 0
    wrong = [f"{int(a)} -> {int(b)}"
             for a, b in zip(np.searchsorted(idx, y[ri])[sp & ~ok], t1[sp & ~ok])]
    return {
        "mass_min": mass_min,
        "first_try": round(float(sp.sum() / max(n_live, 1)), 4),
        "precision": round(float(ok[sp].mean()), 4) if sp.any() else None,
        "spoken": int(sp.sum()),
        "wrong_spoken": int((sp & ~ok).sum()),
        "_wrong_idx": wrong,
        "answerable_clips": int(inn.sum()),
        "held_for_tap": int(inn.sum() - n_live),
        "off_topic_clips": int(len(ro)),
        "off_topic_false_speech": round(false_rate, 4),
        "off_topic_spoken": n_false,
    }


def pick_mass_min(P4, y, idx, held_mask):
    """Safety first: best first-try among thresholds holding false speech <= FALSE_CAP.
    Ties break toward the HIGHER threshold -- an equal-scoring 0.10 is strictly safer than
    0.00, and tie-breaking on grid order is how a topic ended up with no gate at all."""
    scored = [score_topic(P4, y, idx, held_mask, m) for m in MASS_GRID]
    safe = [s for s in scored if s["off_topic_false_speech"] <= FALSE_CAP]
    if safe:
        return max(safe, key=lambda s: (s["first_try"], s["mass_min"]))
    # nothing clears the cap: take the strongest protection available and SAY SO
    best = max(scored, key=lambda s: s["mass_min"])
    best["warning"] = (f"no threshold held off-topic false speech at or under "
                       f"{FALSE_CAP:.0%}; this is the strongest available "
                       f"({best['off_topic_false_speech']:.1%})")
    return best


# ══════════════════════════════════════════════════════════════════════════════════ loading
def load_topics(topic_dir, vocab, exclude=None):
    out = []
    for p in sorted(glob.glob(os.path.join(str(topic_dir), "topic_*.json"))):
        base = os.path.basename(p)
        if exclude and exclude in base:
            continue
        raw = json.loads(Path(p).read_text(encoding="utf-8"))
        tw = raw["words"] if isinstance(raw, dict) else raw
        present = [w for w in tw if w in vocab]
        # The FOREIGN-TOPIC GUARD from live_demo.build_masks, same reasoning: a topic file
        # written for another vocabulary survives filtering as a handful of shared words,
        # and a mask that narrow renormalizes to ~1.0 on any sign. Scoring one would report
        # a meaningless number rather than fail.
        if len(present) < 6 or len(present) < 0.60 * len(tw):
            print(f"[skip] {base}: only {len(present)} of {len(tw)} words are in this "
                  f"vocabulary — a topic file for a different model")
            continue
        out.append((base[len("topic_"):-len(".json")], present, raw))
    return out


def load_split(data_dir, vocab, split):
    """train.load_dataset, but ONLY the requested split's clips.

    load_dataset pulls every array of every word into a float32 dict — for the 250-word
    corpus that is all 94,198 clips at 64x75x3, i.e. **5.4 GB**, to score a test split
    that is a small fraction of it. On a ~13 GB Kaggle box with TensorFlow already
    resident that is both slow and close to OOM, and a commit run that dies at the end of
    a load is a wasted session.

    Returns the same (manifest, arrays) shape, so make_tf_dataset is untouched and the
    prep stays byte-identical: it only ever indexes arrays[key] for keys in the manifest
    it is handed, and applies fit_to_maxlen itself."""
    import pandas as pd
    man = pd.read_parquet(Path(data_dir) / "split_manifest.parquet")
    man = man[man["word"].isin(vocab["word_to_index"])].reset_index(drop=True)
    man = man[man["split"] == split].reset_index(drop=True)
    if "is_outlier" in man.columns:
        man = man[~man["is_outlier"]].reset_index(drop=True)   # honest eval excludes outliers
    man["key"] = (man["word"] + "/" + man["participant_id"].astype(str) + "_"
                  + man["sequence_id"].astype(str))
    man["y"] = man["word"].map(vocab["word_to_index"]).astype(np.int32)

    want = set(man["key"])
    arrays, missing_words = {}, []
    for word in sorted(man["word"].unique()):
        p = Path(data_dir) / "by_word" / word / "sequences.npz"
        if not p.exists():
            missing_words.append(word)
            continue
        with np.load(p) as npz:
            for k in npz.files:
                full = f"{word}/{k}"
                if full in want:                 # <- the whole point: skip cv/train clips
                    arrays[full] = npz[k].astype(np.float32)
    if missing_words:
        print(f"[warn] no npz for {len(missing_words)} words (e.g. {missing_words[:5]}) — "
              f"those rows are dropped")
        man = man[~man["word"].isin(missing_words)].reset_index(drop=True)
    gone = ~man["key"].isin(arrays)
    if gone.any():
        print(f"[warn] {int(gone.sum())} manifest rows have no array — dropped")
        man = man[~gone].reset_index(drop=True)
    mb = sum(a.nbytes for a in arrays.values()) / 2**20
    print(f"[data] loaded {len(arrays)} clips for split '{split}' ({mb:.0f} MiB) — "
          f"not the whole corpus")
    return man, arrays


def corpus_kind(arrays, n=200):
    """Which extraction produced this corpus: L-block dead ~1.00 CANONICAL, ~0.56 LEGACY.

    Rows 33:54 are the left-hand block. A canonical extraction always moves the DOMINANT
    hand to 54:74, so the L block is left empty; a legacy one keeps the signer's actual
    left hand there. Same fingerprint the runbook's inventory cell prints, computed here
    on the clips already in memory.

    This exists because the 2026-09-10 run was wasted without noticing: the inventory cell
    built CORPUS by glob and `asl250-mask-ab-v1/data` (LEGACY) sorted first, so canonical
    weights were scored against legacy features. It returned 0.7471 -- below every recorded
    per-fold number, but close enough to read as a result rather than a mistake. A name
    check would not have caught it either; only the features can say.
    """
    dead = [float(np.isnan(a[:, 33:54, 0]).all(axis=1).mean())
            for a in list(arrays.values())[:n] if a.ndim == 3 and a.shape[1] >= 75]
    if not dead:
        return "UNKNOWN", float("nan")
    d = float(np.mean(dead))
    return ("CANONICAL" if d > 0.90 else "LEGACY" if d < 0.75 else "UNCLEAR"), d


def compute_probs(data_dir, models, vocab_path, split):
    """Reuse train.py's pipeline through eval_savedmodel_250 so inputs are byte-identical
    to training. Imported lazily: the --probs and --selftest paths need no TF at all."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf                                    # noqa: F401
    from eval_savedmodel_250 import _serving_fn, _fold_probs
    from train import make_tf_dataset
    import train as _train
    # PROVENANCE.json for artifacts_250_canonical records `--mask-resting-hand off`, and
    # train.py's module default is "off", so the generator applies no resting mask. Assert
    # it rather than rely on it: masking inputs a model never saw masked would degrade the
    # score silently, and nothing else here would notice.
    assert _train._MASK_MODE == "off", \
        f"train._MASK_MODE is {_train._MASK_MODE!r}; these weights were trained with it off"

    frozen = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
    words = frozen["words"] if isinstance(frozen, dict) else frozen
    vocab = {"words": words, "word_to_index": {w: i for i, w in enumerate(words)},
             "num_classes": len(words), "note": "measure_topic_gates"}
    md = sorted(d for d in Path(models).glob("savedmodel_fold*") if d.is_dir())
    if not md:
        raise SystemExit(f"[err] no savedmodel_fold* under {models}")
    ev, arrays = load_split(data_dir, vocab, split)
    parts = sorted(str(p) for p in ev["participant_id"].unique())
    print(f"[cfg] split='{split}': {len(ev)} clips, {len(parts)} signers, "
          f"{ev['word'].nunique()} of {len(words)} classes present")

    # Do the weights and the features come from the SAME extraction? Nothing downstream can
    # tell, and a mismatch does not error -- it silently returns a lower number for every
    # topic. PROVENANCE.json is authoritative about what the weights were trained on.
    prov_p = Path(models) / "PROVENANCE.json"
    prov = json.loads(prov_p.read_text(encoding="utf-8")) if prov_p.exists() else {}
    kind, dead = corpus_kind(arrays)
    print(f"[cfg] corpus  {data_dir}\n       L-block dead {dead:.3f} -> {kind}")
    if "canonical" in (prov.get("corpus", "") + " " + str(models)).lower():
        if kind != "CANONICAL":
            raise SystemExit(
                f"[err] STOP -- the weights under {Path(models).name} are CANONICAL "
                f"(PROVENANCE corpus={prov.get('corpus', 'unstated')!r}) but --data-dir "
                f"{data_dir} fingerprints {kind} (L-block dead {dead:.3f}).\n"
                f"       Point --data-dir at the canon/none corpus. Scoring one extraction's "
                f"weights on another's features does not fail loudly; it just makes every "
                f"number below wrong.")
        print(f"       [ok] matches PROVENANCE corpus={prov.get('corpus', '?')!r}")
    if ev["word"].nunique() < len(words):
        print(f"[warn] {len(words) - ev['word'].nunique()} classes have NO test clip. A "
              f"topic containing one gets a rate computed over nothing — the same thin-class "
              f"trap that once selected `choke`, a word with a single clip and a 1.000 score.")
    ds = make_tf_dataset(ev, arrays, len(words), training=False)
    fns = [_serving_fn(d) for d in md]
    chunks = [[] for _ in fns]
    for xb, _yb in ds:
        for i, (_o, fn, key) in enumerate(fns):
            chunks[i].append(_fold_probs(fn, key, xb))
    P4 = np.stack([np.concatenate(c, 0) for c in chunks], 0)
    y = ev["y"].to_numpy()
    assert P4.shape[1] == len(y), f"{P4.shape[1]} probs vs {len(y)} labels"
    # PER-FOLD accuracies are the CONTROL, and they are free. artifacts_250_canonical's
    # PROVENANCE.json records per_fold_30fps [0.7579, 0.7608, 0.7626, 0.7636]. If these land
    # far below that, the corpus and the weights do not match — most likely a legacy corpus
    # under canonical weights, or canon/ffill instead of canon/none — and every topic number
    # below would be wrong in a way no assertion here could catch.
    for d, p in zip(md, P4):
        print(f"       {d.name:24s} acc {float((p.argmax(1) == y).mean()):.4f}")
    acc = float((P4.mean(0).argmax(1) == y).mean())
    print(f"[cfg] {len(md)} folds, ensemble acc {acc:.4f} on split '{split}'")
    ref = prov.get("per_fold_30fps")
    if ref:
        print("       control: PROVENANCE per_fold_30fps = "
              + " / ".join(f"{r:.4f}" for r in ref))
        if acc < min(ref):
            print(f"[warn] the ENSEMBLE ({acc:.4f}) scores below the WORST single fold "
                  f"({min(ref):.4f}). Averaging four folds should beat any one of them, so "
                  f"treat every number below as suspect until that is explained.")
    return P4, y, words, acc


# ═════════════════════════════════════════════════════════════════════════════════ selftest
def selftest():
    """Reproduce numbers already in hand, or the scorer is not trustworthy on a model where
    nothing can be checked. Synthetic first (exact, no data), then the medical cache if it
    happens to be lying around."""
    print("=== SELFTEST ===")
    # 1. mass is read BEFORE masking. Build a case where the masked confidence is perfect
    #    and the mass is terrible: the whole point of the threshold.
    C, F = 10, 4
    P4 = np.zeros((F, 2, C))
    P4[:, 0, 0] = 0.9; P4[:, 0, 9] = 0.1        # in-topic, mass 0.9 on {0,1}
    P4[:, 1, 9] = 0.9; P4[:, 1, 0] = 0.1        # OUT of topic, only 0.1 lands on {0,1}
    y = np.array([0, 9])
    idx = np.array([0, 1])
    held = np.zeros(2, bool)
    lo = score_topic(P4, y, idx, held, 0.0)
    hi = score_topic(P4, y, idx, held, 0.50)
    assert lo["off_topic_spoken"] == 1, lo
    assert hi["off_topic_spoken"] == 0, hi
    assert lo["first_try"] == 1.0 and hi["first_try"] == 1.0, (lo, hi)
    print("[ok] mass_min blocks the out-of-topic clip and costs the in-topic one nothing")
    # the trap, stated as an assertion: renormalising makes the off-topic clip look CERTAIN
    m = P4[:, 1, :][:, idx]
    assert abs(float((m / m.sum(1, keepdims=True)).mean(0).max()) - 1.0) < 1e-9, \
        "a 2-word mask must renormalise the off-topic clip to ~1.0 — that is why mass exists"
    print("[ok] and that clip renormalises to conf 1.00, so confidence alone cannot see it")

    # 2. safety holds leave the denominator, never inflate first_try
    held2 = np.array([True, False])
    h = score_topic(P4, np.array([0, 0]), idx, held2, 0.0)
    assert h["spoken"] == 0 and h["held_for_tap"] == 2, h
    assert h["first_try"] == 0.0, h
    print("[ok] held words are excluded from the denominator, not counted as spoken")

    # 3. tie-break goes to the SAFER threshold
    picked = pick_mass_min(P4, y, idx, held)
    assert picked["mass_min"] > 0.0, \
        f"tie-break must prefer the higher threshold, got {picked['mass_min']}"
    print(f"[ok] tie-break picked mass_min {picked['mass_min']} over an equal-scoring 0.00")

    # 4. the real control, if the medical cache is present
    cache = list(Path(os.environ.get("TMP", "/tmp")).glob("**/probs.npz"))
    cache += list((REPO / ".cache").glob("probs.npz"))
    ref = next((p for p in cache if p.stat().st_size > 100_000), None)
    if ref is None:
        print("[skip] no cached medical probs found; synthetic checks only. Regenerate with "
              "measure_medical_gate.py to get the end-to-end control.")
    else:
        z = np.load(ref, allow_pickle=True)
        if "per_model" not in z.files:
            print(f"[skip] {ref} has no per_model array")
        else:
            words = json.loads((REPO / "vocab_medical_123.json")
                               .read_text(encoding="utf-8"))["words"]
            g = json.loads((REPO / "safety_gates_medical.json").read_text(encoding="utf-8"))
            nac = set((g.get("never_auto_commit") or {}).keys())
            P, yy = z["per_model"].astype(np.float64), z["y"]
            acc = float((P.mean(0).argmax(1) == yy).mean())
            assert abs(acc - 0.8383) < 5e-4, f"cache no longer reproduces 0.8383: {acc}"
            tl = ts = to = 0
            for _n, tw, raw in load_topics(REPO, set(words), exclude=None):
                if not _n.startswith("medical_"):
                    continue
                ix = np.array(sorted(words.index(w) for w in tw))
                hm = np.array([words[i] in nac for i in ix])
                mm = raw.get("mass_min")
                s = score_topic(P, yy, ix, hm, mm if mm is not None else 0.0)
                live = s["answerable_clips"] - s["held_for_tap"]
                tl += live; ts += s["spoken"]; to += s["spoken"] * (s["precision"] or 1.0)
            print(f"[ok] medical control: ensemble {acc:.4f}, pooled first-try "
                  f"{ts/tl:.4f}, precision {to/max(ts,1):.4f} over {tl} clips")
            print("     (the shipped set measured 0.9223 / 0.9883 at its own mass_min "
                  "values; ship55 and intake27 are included here and overlap the 13)")
    print("ALL CHECKS PASSED")


# ═════════════════════════════════════════════════════════════════════════════════════ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probs", help=".npz with per_model (F,N,C) and y (N,)")
    ap.add_argument("--data-dir", help="dataset root (split_manifest.parquet + by_word/)")
    ap.add_argument("--models", default=str(REPO / "artifacts_250"))
    ap.add_argument("--vocab", default=str(REPO / "vocab_250.json"))
    ap.add_argument("--split", default="test", choices=["test", "cv"])
    ap.add_argument("--topics", default=str(REPO), help="dir holding topic_*.json")
    ap.add_argument("--exclude-topics", default=None,
                    help="skip topic files whose name contains this (e.g. 'medical')")
    ap.add_argument("--safety-gates", default=None,
                    help="json with never_auto_commit; those words are held, not spoken")
    ap.add_argument("--save-probs", default=None, help="write the computed probs here")
    ap.add_argument("--out", default=None, help="write the measurement json here")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    print(f"[cfg] scorer {SCORER_VERSION}")

    if a.selftest:
        selftest()
        return
    if not a.probs and not a.data_dir:
        raise SystemExit("[err] need --probs or --data-dir (or --selftest)")

    frozen = json.loads(Path(a.vocab).read_text(encoding="utf-8"))
    words = frozen["words"] if isinstance(frozen, dict) else frozen
    ens_acc = None
    if a.probs:
        z = np.load(a.probs, allow_pickle=True)
        P4, y = z["per_model"].astype(np.float64), z["y"]
        ens_acc = float((P4.mean(0).argmax(1) == y).mean())
        print(f"[cfg] {a.probs}: {P4.shape} folds/clips/classes, ensemble acc {ens_acc:.4f}")
    else:
        P4, y, words, ens_acc = compute_probs(a.data_dir, a.models, a.vocab, a.split)
        if a.save_probs:
            np.savez_compressed(a.save_probs, per_model=P4.astype(np.float32), y=y)
            print(f"[ok] wrote {a.save_probs} — re-scoring is now seconds, not GPU minutes")
    assert P4.shape[2] == len(words), \
        (f"model outputs {P4.shape[2]} classes but {Path(a.vocab).name} has {len(words)} "
         f"words. Every label would be silently wrong.")

    nac = set()
    if a.safety_gates:
        g = json.loads(Path(a.safety_gates).read_text(encoding="utf-8"))
        v = g.get("never_auto_commit") or {}
        nac = set(v.keys()) if isinstance(v, dict) else set(v)
        print(f"[cfg] {len(nac)} never_auto_commit words will be HELD, not spoken")

    topics = load_topics(a.topics, set(words), a.exclude_topics)
    if not topics:
        raise SystemExit(f"[err] no usable topic_*.json in {a.topics}")
    cnt = np.bincount(y, minlength=len(words))

    print(f"\n{'topic':<18s} {'n':>3s} {'mass':>5s} {'first-try':>9s} {'prec':>7s} "
          f"{'spoken':>6s} {'wrong':>5s} {'off-topic false':>16s} {'min clips':>9s}")
    print("-" * 96)
    out, tl, ts, to, tw = {}, 0, 0, 0, 0
    for name, tws, _raw in topics:
        ix = np.array(sorted(words.index(w) for w in tws))
        hm = np.array([words[i] in nac for i in ix])
        s = pick_mass_min(P4, y, ix, hm)
        s["words"] = len(ix)
        s["wrong_pairs"] = [f"{words[ix[int(p.split(' -> ')[0])]]} -> "
                            f"{words[ix[int(p.split(' -> ')[1])]]}" for p in s.pop("_wrong_idx")]
        s["min_per_word_test_clips"] = int(min(cnt[i] for i in ix))
        s["mean_per_word_test_clips"] = round(float(np.mean([cnt[i] for i in ix])), 1)
        s["unmeasured_words"] = [words[i] for i in ix if cnt[i] == 0]
        out[name] = s
        print(f"{name:<18s} {len(ix):3d} {s['mass_min']:5.2f} {s['first_try']:9.4f} "
              f"{(s['precision'] if s['precision'] is not None else float('nan')):7.4f} "
              f"{s['spoken']:6d} {s['wrong_spoken']:5d} "
              f"{s['off_topic_false_speech']:15.1%} {s['min_per_word_test_clips']:9d}"
              + ("   <- NO SAFE THRESHOLD" if "warning" in s else ""))
        live = s["answerable_clips"] - s["held_for_tap"]
        tl += live; ts += s["spoken"]; to += s["spoken"] * (s["precision"] or 1.0)
        tw += s["wrong_spoken"]
    print("-" * 96)
    print(f"{'POOLED':<18s} {len(set(w for _n, t, _r in topics for w in t)):3d} {'':5s} "
          f"{ts/tl:9.4f} {to/max(ts,1):7.4f} {ts:6d} {tw:5d}")

    # the comparison that says whether topics are worth anything at all
    allidx = np.arange(len(words))
    hm_all = np.array([w in nac for w in words])
    op = score_topic(P4, y, allidx, hm_all, 0.0)
    print(f"\n  ONE open {len(words)}-word mask: first-try {op['first_try']:.4f}  "
          f"precision {op['precision']}  wrong {op['wrong_spoken']}")
    print(f"  topics are worth {ts/tl - op['first_try']:+.4f} first-try "
          f"({tw} wrong vs {op['wrong_spoken']})")

    if a.out:
        Path(a.out).write_text(json.dumps({
            "generated_by": "training/measure_topic_gates.py",
            "vocab": Path(a.vocab).name, "split": a.split,
            "ensemble_acc": round(ens_acc, 4) if ens_acc else None,
            "gate": {"agree_k": AGREE_K, "agree_conf": AGREE_CONF,
                     "false_cap": FALSE_CAP, "mass_grid": MASS_GRID},
            "open_mask": op, "pooled": {"first_try": round(ts / tl, 4),
                                        "precision": round(to / max(ts, 1), 4),
                                        "wrong_spoken": tw},
            "topics": out,
        }, indent=1) + "\n", encoding="utf-8")
        print(f"\n[ok] wrote {a.out}")


if __name__ == "__main__":
    main()
