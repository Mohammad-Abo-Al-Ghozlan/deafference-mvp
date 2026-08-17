# CPU-only Kaggle session — test eval, selector v7.1, handshape templates

No GPU quota needed. Everything here is inference or numpy.

**Attach these datasets** (Add Input, right panel):

| Dataset | Holds |
|---|---|
| `asl250-armAB-v1` | the two trained fold-0 models from the A/B run |
| `asl250-code-v12` | the scripts |
| `asl250-canon-v1` | the canonical corpus (and whatever arm A trained on) |

**Accelerator: None.** Settings → Accelerator → None. A GPU here is wasted quota.

Cell 0 discovers every path, fingerprints every corpus, and refuses to continue if
anything is ambiguous — so a wrong path fails in 20 seconds instead of after an hour.

---

## Cell 0 — discover, stage, fingerprint. Stops on any problem.

```python
# ═══════════════════════════════════════════════════════════════════════════
# CELL 0 — resolve every path, stage the code, prove the inputs are what we
# think they are. Nothing expensive runs here. If this cell prints CELL 0 OK
# then no later cell can fail on a path.
# ═══════════════════════════════════════════════════════════════════════════
import os, sys, json, shutil
from pathlib import Path
import numpy as np

os.environ["TF_USE_LEGACY_KERAS"] = "1"      # train.py is Keras-2 code
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

IN, WORK = Path("/kaggle/input"), Path("/kaggle/working")
CODE, OUT = WORK / "code", WORK / "out"
for d in (CODE, OUT):
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)

print("attached inputs:", [p.name for p in sorted(IN.iterdir())])

# Kaggle sometimes mounts inputs NESTED (/kaggle/input/datasets/<owner>/<slug>/...)
# and sometimes flat (/kaggle/input/<slug>/). Never assume — show the tree, then
# find everything by CONTENT below.
def tree(d, depth=0, maxd=4, cap=12):
    if depth > maxd: return
    try: kids = sorted(x for x in d.iterdir() if x.is_dir())
    except Exception: return
    for k in kids[:cap]:
        print("   " * depth + "└ " + k.name)
        tree(k, depth + 1, maxd, cap)
    if len(kids) > cap: print("   " * depth + f"  ... +{len(kids)-cap} more dirs")
print("\n── /kaggle/input (dirs, depth<=4) ──"); tree(IN); print()

# ── 1. stage the code FLAT (inputs are read-only; the scripts import each other) ──
# located by the files it must contain, so a nested mount or a renamed dataset
# cannot break it
cds = sorted({p.parent for p in IN.glob("**/train.py")
              if (p.parent / "build_sign_clips.py").exists()})
assert cds, ("no code dataset found (looked for a dir holding train.py + "
             f"build_sign_clips.py). Attach the newest asl250-code-v*. Tree above.")
# This used to be `src = cds[-1]`, i.e. pick the last in STRING order. That silently
# selects the WRONG dataset whenever version numbers differ in digit count — "v16" sorts
# BEFORE "v9", so attaching both would have staged v9 and trained on stale code. Rather
# than guess, refuse: exactly one code dataset, chosen by the human.
if len(cds) > 1:
    for c in cds:
        print(f"   candidate: {c}")
    raise SystemExit(
        f"{len(cds)} code datasets are attached (listed above). Detach the old ones "
        f"(right panel -> the '...' next to each input -> Remove) and keep ONLY the newest, "
        f"then re-run this cell. Picking automatically is how a stale stage ships.")
src = cds[0]
for f in src.rglob("*"):
    if f.is_file(): shutil.copy2(f, CODE / f.name)
sys.path.insert(0, str(CODE))

NEED = ["train.py", "build_sign_clips.py", "build_handshape_templates.py",
        "sign_landmarks.py", "gloss_to_motion.py",
        "vocab_250.json", "asl_handedness_250.json"]
miss = [n for n in NEED if not (CODE / n).exists()]
assert not miss, f"code zip missing {miss}"

# Staleness check. It must name symbols from the NEWEST change, not just old ones —
# a marker list that every past revision also satisfies cannot detect a stale stage,
# and on 2026-08-12 exactly that let a v12 selector run while v13 was attached.
STAMPS = {
    "train.py":            ("FLIP_MAP_CANON", "canonical-hand", "TF_USE_LEGACY_KERAS",
                            "mask_resting_hand"),           # v16 resting-hand mask
    "build_sign_clips.py": ("require_signing_hand", "signing_hand_verified",
                            "hand_arm_alignment"),          # v13 signing-hand gate
    "sign_landmarks.py":   ("hand_arm_alignment", "mirror_match"),
    # v15 synthesis block. Every file a cell EXECUTES needs an entry — gloss_to_motion.py
    # was missing here, so a stale copy could have written 250 word files with no synthesis
    # block and Cell 2 would still have printed "250". Same bug class as the v12 selector.
    "gloss_to_motion.py":  ("load_lexicon", "make_segment", "dominant_coverage",
                            "passiveWristIndex", "synthesisNote"),
    "build_handshape_templates.py": ("resolution", "single_anchor", "fallback_handshape"),
}
for fn, marks in STAMPS.items():
    s = (CODE / fn).read_text(encoding="utf-8")
    miss = [m for m in marks if m not in s]
    assert not miss, (f"staged {fn} is STALE — missing {miss}. Attach the newest "
                      f"asl250-code-v* dataset and RE-RUN THIS CELL (staging lives here, "
                      f"so re-running only Cells 2+ keeps the old code).")
print(f"[code] {src}\n       {len(list(CODE.iterdir()))} files staged, "
      f"train.py carries the canonical patches\n")

# ── 2. FINGERPRINT every corpus from the data, never from its directory name ──
#   left_dead : clips whose left-hand block 33-53 is entirely NaN
#               ~1.00 = canonical layout (dominant hand always parked at 54-74)
#               ~0.45 = legacy layout    (hand sits in whichever slot was recorded)
#   hand_nan  : mean fraction of frames with a NaN dominant hand
#               ~0.00 = gap-filled (ffill/bfill ran — fabricated coordinates)
#               >0.20 = raw missingness preserved
def fingerprint(root: Path, probe: int = 150):
    npzs = sorted(root.glob("by_word/*/sequences.npz"))[:probe]
    dead = tot = 0; nanfrac = []
    for p in npzs:
        z = np.load(p)
        for k in z.files[:2]:
            a = z[k]
            if a.ndim != 3 or a.shape[1] != 75: continue
            tot += 1
            l_dead = bool(np.isnan(a[:, 33:54, :2]).all())
            dead += l_dead
            blk = slice(54, 75) if l_dead else (
                  slice(54, 75) if np.isnan(a[:, 33:54, :2]).mean() >
                                   np.isnan(a[:, 54:75, :2]).mean() else slice(33, 54))
            nanfrac.append(float(np.isnan(a[:, blk, :2]).all(axis=(1, 2)).mean()))
    return dead / max(tot, 1), float(np.mean(nanfrac or [0.0])), tot

rows = []
for man in sorted(IN.glob("**/split_manifest.parquet")):
    root = man.parent
    ld, hn, n = fingerprint(root)
    layout = "canonical" if ld > 0.99 else "legacy"
    fill   = "gap-filled" if hn < 0.02 else "raw-missing"
    rows.append((root, layout, fill, ld, hn))
    print(f"[corpus] {layout:9} {fill:11} left_dead={ld:5.1%} hand_nan={hn:5.1%} "
          f"({n} clips probed)\n          {root}")
assert rows, "no split_manifest.parquet under /kaggle/input — no corpus attached"

# ── 3. map corpora to arms ────────────────────────────────────────────────────
# Arm A = whatever reproduces the OLD pipeline. Arm B = canonical + raw missingness.
# If auto-resolution is ambiguous, set these two by hand from the table above.
def pick(*want):                 # first (layout, fill) preference that exists
    for lay_w, fl_w in want:
        for r, lay, fl, *_ in rows:
            if (lay_w in (None, lay)) and (fl_w in (None, fl)):
                return str(r)
    return None

CANON  = pick(("canonical", "raw-missing"), ("canonical", None))
# arm A reproduces the OLD pipeline = legacy layout WITH gap-fill. Fall back in
# order of decreasing similarity to it; never fall back to whatever CANON is.
LEGACY = pick(("legacy", "gap-filled"), ("legacy", None), (None, "gap-filled"))

if not CANON:
    for i, (r, lay, fl, *_ ) in enumerate(rows): print(f"      [{i}] {lay:9} {fl:11} {r}")
    raise SystemExit("no canonical corpus — attach asl250-canon-v1, or set CANON by hand")
if not LEGACY or LEGACY == CANON:
    LEGACY = ""
    print("\n[warn] only ONE corpus attached. Cell 1 (the A/B test eval) needs both and"
          "\n       will stop with a message. Cells 2-5 run fine without it.")

# ── 4. find the SavedModels ───────────────────────────────────────────────────
sms = [p for p in sorted(IN.glob("**/savedmodel_fold*")) if (p / "saved_model.pb").exists()]
print("\nsavedmodels found:"); [print(f"   {p}") for p in sms]
def arm_of(p):
    s = f"{p.parent.name}/{p.name}".lower()
    if any(t in s for t in ("armb", "arm_b", "canon", "_b")): return "B"
    if any(t in s for t in ("arma", "arm_a", "legacy", "base", "_a")): return "A"
    return None
models = {}
for p in sms:
    a = arm_of(p)
    if a: models.setdefault(a, str(p))
if len(models) != 2:
    print(f"\n[warn] could not label 2 arms (got {list(models)}). Cell 1 needs both."
          f"\n       Set by hand, then re-run this cell's last block:"
          f"\n       models = {{'A': '<legacy savedmodel>', 'B': '<canonical savedmodel>'}}")

os.environ.update(CODE=str(CODE), OUT=str(OUT), CANON=CANON, LEGACY=LEGACY,
                  MODEL_A=models.get("A", ""), MODEL_B=models.get("B", ""),
                  VOCAB=str(CODE / "vocab_250.json"),
                  LEX=str(CODE / "asl_handedness_250.json"))
print(f"\n  CANON  (arm B) = {CANON}\n  LEGACY (arm A) = {LEGACY or '(none attached)'}"
      f"\n  model A = {models.get('A') or '(unlabelled)'}"
      f"\n  model B = {models.get('B') or '(unlabelled)'}\n\nCELL 0 OK")
```

**Expected**: one `canonical raw-missing` row, one other row, two savedmodels, `CELL 0 OK`.

If it prints `AMBIGUOUS`, paste me the table — it's a one-line fix, not a rerun.
The `hand_nan` column is worth reading regardless: it's the direct measurement of
the gap-fill defect (R2). A corpus showing `hand_nan=0.0%` has fabricated
coordinates in it.

---

## Cell 1 — test-set eval, both arms. **The number that matters.**

Each model is scored on its own corpus (full test split) and probed on the other
one (512 random samples). The diagonal must win by a mile — if it doesn't, Cell 0
paired them wrong and no conclusion is safe. Corpora are loaded one at a time and
freed; holding both would be ~7 GB.

```python
# ═══════════════════════════════════════════════════════════════════════════
# CELL 1 — held-out-signer TEST accuracy for arm A and arm B.
# Same protocol that produced the shipped numbers: train.py's own pipeline,
# no augmentation, outliers excluded, class order pinned to the frozen vocab.
# ~15-25 min on CPU.
# ═══════════════════════════════════════════════════════════════════════════
import gc, json
import numpy as np, tensorflow as tf
from pathlib import Path
from train import load_dataset, make_tf_dataset

assert os.environ.get("LEGACY") and os.environ.get("MODEL_A") and os.environ.get("MODEL_B"), (
    "Cell 1 needs BOTH corpora and both savedmodels. Attach the corpus arm A trained on "
    "(re-run Cell 0 after), or skip to Cell 2 — the selector only needs the canonical one.")

W = json.loads(Path(os.environ["VOCAB"]).read_text())
W = W["words"] if isinstance(W, dict) else W
VOC = {"words": W, "word_to_index": {w: i for i, w in enumerate(W)}, "num_classes": len(W)}
print(f"[cfg] {len(W)} classes pinned to vocab_250.json")

def serving(d):
    obj = tf.saved_model.load(d)
    k = "serving_default" if "serving_default" in obj.signatures else list(obj.signatures)[0]
    fn = obj.signatures[k]
    try:    ik = list(fn.structured_input_signature[1].keys())[0]
    except Exception: ik = "landmarks"
    return obj, fn, ik                      # keep obj alive or TF collects the graph

def score(model_dir, ev, arr):
    ds = make_tf_dataset(ev, arr, len(W), training=False)     # order == ev, no aug
    _keep, fn, ik = serving(model_dir)
    probs, seen = [], 0
    for xb, _ in ds:
        out = fn(**{ik: tf.cast(xb, tf.float32)})
        lg = out["output_0"] if "output_0" in out else list(out.values())[0]
        probs.append(tf.nn.softmax(lg, 1).numpy()); seen += int(xb.shape[0])
    p = np.concatenate(probs, 0); y = ev["y"].to_numpy()
    assert len(p) == len(y) == seen, f"count mismatch {len(p)}/{len(y)}/{seen}"
    pw = {W[c]: round(float((p.argmax(1)[y == c] == c).mean()), 3) for c in np.unique(y)}
    return float((p.argmax(1) == y).mean()), pw

# one corpus resident at a time: full eval for its own arm, 512-probe for the other
PLAN = [("A", os.environ["LEGACY"], "B"), ("B", os.environ["CANON"], "A")]
res, cross = {}, {}
for own, root, other in PLAN:
    man, arr = load_dataset(Path(root), VOC)
    ev = man[man["split"] == "test"]
    if "is_outlier" in ev.columns: ev = ev[~ev["is_outlier"]]
    ev = ev.reset_index(drop=True)
    print(f"\n[data] {Path(root).name}: test n={len(ev)}  "
          f"participants={sorted(int(p) for p in ev.participant_id.unique())}")
    acc, pw = score(os.environ[f"MODEL_{own}"], ev, arr)
    res[own] = {"acc": acc, "per_word": pw, "n": len(ev), "corpus": root}
    print(f"  arm {own} (matched)  test acc {acc:.4f}   n={len(ev)}")
    probe = ev.sample(min(512, len(ev)), random_state=0).reset_index(drop=True)
    cross[other], _ = score(os.environ[f"MODEL_{other}"], probe, arr)
    print(f"  arm {other} (crossed, n={len(probe)})      {cross[other]:.4f}")
    del man, arr, ev, probe; gc.collect()

for a in ("A", "B"):
    if cross[a] >= res[a]["acc"]:
        print(f"\n*** arm {a} scores no worse on the other layout — Cell 0 paired "
              f"the corpora wrong. STOP and fix before reading anything below. ***")

d = res["B"]["acc"] - res["A"]["acc"]
print(f"""
╔══════════════════════════════════════════════════════════════════╗
   arm A  legacy      TEST acc  {res['A']['acc']:.4f}   (crossed {cross['A']:.4f})
   arm B  canonical   TEST acc  {res['B']['acc']:.4f}   (crossed {cross['B']:.4f})
                                {d:+.4f}  =  {d*100:+.2f} pts

   val-split delta was +1.56 pts — does TEST agree?

   historical fold-0 legacy TEST = 0.7576  <- arm A should land near this
   shipped 4-fold ensemble       = 0.7755  <- NOT comparable (1 fold here)
╚══════════════════════════════════════════════════════════════════╝""")

both = sorted(set(res["A"]["per_word"]) & set(res["B"]["per_word"]))
dl = sorted((res["B"]["per_word"][w] - res["A"]["per_word"][w], w) for w in both)
print("\nworst regressions :", [f"{w} {v:+.2f}" for v, w in dl[:10]])
print("best improvements :", [f"{w} {v:+.2f}" for v, w in dl[-10:][::-1]])
print("dead in both <0.20:", [w for w in both
      if max(res['A']['per_word'][w], res['B']['per_word'][w]) < 0.20])

Path(os.environ["OUT"], "test_eval_AB.json").write_text(json.dumps(
    {"armA": res["A"], "armB": res["B"], "crossed": cross, "delta": d,
     "note": "fold0 only; historical fold0 legacy=0.7576, shipped 4-fold ens=0.7755"},
    indent=2))
print(f"\nwritten: {os.environ['OUT']}/test_eval_AB.json")
```

### How to read it

| arm A lands at | Means |
|---|---|
| **0.74 – 0.78** | The harness reproduces history. Arm B's number is trustworthy — the outcome to hope for. |
| **much lower** | Something in the rewritten `train.py` or the re-extracted arm-A corpus changed. Arm B is still valid as a *relative* comparison; the absolute is not comparable to 0.7576. |
| **much higher** | Suspect a leak. Check the `[data] participants=` line matches the historical test signers. |

`dead in both <0.20` is the word-level data-quality worklist. `chin`, `napkin`,
`finger`, `go` were bottom-5 in both arms on val, so expect them to show here.

---

## Cell 2 — selector v7.1 on the canonical corpus

```python
# ═══════════════════════════════════════════════════════════════════════════
# CELL 2 — pick the animation exemplars with the LEXICON driving handedness
# instead of the travel-ratio guess (which measured AUC 0.335 — inverted).
# ~10-15 min. Read the VALIDITY FILTER and RENDERER CONTRACT blocks it prints.
# ═══════════════════════════════════════════════════════════════════════════
!cd $CODE && python build_sign_clips.py \
    --data-dir $CANON \
    --vocab    $VOCAB \
    --lexicon  $LEX \
    --out      $OUT/sign_clips_250.npz \
    --validity on --require-passive-up on --contiguity 0.3
```

### Cell 2b — the handoff the animation side actually consumes

**This is a separate block and it must be run even when 2a is skipped**, because
`gloss_to_motion.py` is what writes the per-segment `synthesis` block (contract §6.1).

```python
!cd $CODE && python gloss_to_motion.py \
    --clips $OUT/sign_clips_250.npz \
    --per-word --out-dir $OUT/animation_handoff
!ls $OUT/animation_handoff/words | wc -l          # expect 250
```

Expect `synthesis block for 250/250 words (87 two-handed ...)` and **no** `[warn]` lines.

Counting 250 files proves only that files exist. Verify the CONTENT — a stale
`gloss_to_motion.py` writes exactly 250 valid-looking files with no synthesis block:

```python
# ── verify the export, don't just count it ────────────────────────────────────
import json, os, glob
W = os.path.join(os.environ["OUT"], "animation_handoff", "words")
files = sorted(glob.glob(os.path.join(W, "*.json")))
assert len(files) == 250, f"{len(files)} word files, expected 250"
n2 = miss = 0
for fp in files:
    d = json.load(open(fp))
    seg = d["segments"][0]
    assert "synthesis" in seg, (f"{os.path.basename(fp)} has NO synthesis block — staged "
                                f"gloss_to_motion.py is STALE. Re-run Cell 0.")
    s = seg["synthesis"]
    assert s["dominantHand"] == "R", f"{fp}: dominantHand={s['dominantHand']}, expected R"
    if s["twoHanded"]:
        n2 += 1
        assert s["passiveWristIndex"] == 15
        if s["class"] == "2a" and not s.get("passiveHandshape"):
            miss += 1
    else:
        assert "passiveWristIndex" not in s, f"{fp}: passive field on a one-handed word"
assert n2 == 87, f"{n2} two-handed words, expected 87"
assert miss == 0, f"{miss} 2a words have no passive handshape — the renderer cannot draw them"
print(f"EXPORT OK: 250 words, {n2} two-handed, every synthesis block present")
```

---

## Cell 3 — mine the unmarked handshape templates

The last piece the animation side is missing. Until this lands, all 35 `2a` words
render their passive hand with a relaxed curl instead of the correct unmarked
handshape.

```python
# ═══════════════════════════════════════════════════════════════════════════
# CELL 3 — median palm-frame geometry for the 7 unmarked handshapes
# (B A S 1 5 C O), mined from one-handed anchor signs. ~2 min.
# ═══════════════════════════════════════════════════════════════════════════
!cd $CODE && python build_handshape_templates.py \
    --data-dir $CANON \
    --vocab    $VOCAB \
    --out      $OUT/handshape_templates.json
```

Read `agreement_xy` per handshape. **> 0.20 is unusable** and is reported as such
rather than shipped. `O` is expected to be weak — there is no clean O anchor in a
250-word children's vocabulary, and flattened-O is a *different* handshape.

---

## Cell 4 — package for download

```python
import shutil, os
z = shutil.make_archive("/kaggle/working/cpu_session_out", "zip", os.environ["OUT"])
print(z, os.path.getsize(z) / 1e6, "MB")
```

Download `cpu_session_out.zip` from the Output panel. It holds `test_eval_AB.json`,
`sign_clips_250.npz`, `handshape_templates.json`, and `animation_handoff/words/*.json`.

---

## Then, locally — run their v3 acceptance script

The `check-export.py` inside the code zip is their **old v1/v2 criterion** (the one
their own v3 doc calls backwards). Run the real v3 on your own machine — pure
stdlib, no TensorFlow:

```powershell
cd c:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference
python Fix\check-export3.py <unzipped>\animation_handoff\words
```

Its dominant-hand-coverage verdict is what goes into the reply.
