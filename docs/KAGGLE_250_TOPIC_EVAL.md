# Measuring the 250-word topic set — the one number set we do not have

**Written 2026-09-10.** The 11 general topics (`topic_animals.json` … `topic_time_question.json`)
cover all 206 of the 250 classes scoring ≥ 0.60 on held-out test. Their **per-word** accuracy is
real. Their **gate** numbers are not measured, and this file is the run that fixes that.

---

## What is missing, and exactly why

| number | medical (123-class) | 250-word |
|---|---|---|
| per-word held-out accuracy | measured | ✅ **measured** — `word_acc_250.json` |
| topic first-try rate | measured | ❌ |
| topic precision | measured | ❌ |
| off-topic false speech | measured | ❌ |
| `mass_min` | measured, per topic | 🟡 **provisional 0.10** |
| confusable-pair split into `_a`/`_b` | measured, done | ❌ impossible |

**The blocker is a missing test SET, not missing code.** This repo has the four savedmodels,
`vocab_250.json` and `word_acc_250.json` — but the only clips it holds are
`sign_clips_250.npz`, which are the **per-word exemplar clips used for the demo's reference
poses**. Those are training data. Scoring a confidence gate on them returns **precision 1.000
at every threshold**, which is not a good result — it is *no information*, and it is the exact
trap `measure_conf_gate.py` is documented as falling into.

> ⚠️ `artifacts_medical/confusion_all250_fold*.csv` looks like it should help. It does not —
> `all250` is the **medical** run's tag. Those four files are the 123-class model. There is no
> confusion matrix for the 250-word model anywhere in the repo, which is why its topics could
> not be split into `_a`/`_b` halves the way the medical ones were.

### Why the medical numbers must not simply be copied over

`mass_min` is a threshold on **how much unmasked probability lands on the active topic.** That
quantity depends on how many classes are competing:

```
a diffuse prediction over 123 classes, 25-word topic  ->  ~25/123 = 0.20 on the topic
a diffuse prediction over 250 classes, 25-word topic  ->  ~25/250 = 0.10
```

So **the same threshold is materially stricter on the 250-word model.** The shipped 0.10 is the
class-count-scaled equivalent of the 0.20 that measured *free* on medical — a defensible
starting point, not a measurement. Every topic file says so in `mass_min_provisional: true`.

---

## The run

**Accelerator: GPU** (inference over ~4k clips × 4 folds). **Internet: off.** Expect **15–25
min**, which is inside a single interactive session — no Save & Run All needed, because nothing
needs to be persisted except the JSON you paste back.

### Inputs to attach

| kind | what | why |
|---|---|---|
| **Competition** | **Google - Isolated Sign Language Recognition** (`asl-signs`) | the held-out clips. **This is GISLR, not the fingerspelling competition** — accept its rules once. |
| **Dataset** | the notebook output holding `artifacts_250/savedmodel_fold{0..3}` | the four folds |
| **Dataset** | a new private dataset with `vocab_250.json` + the 11 `topic_*.json` files | the masks to score |

> 🔴 Drag **the individual files**, never the repo folder — it contains `.env`. Visibility
> **Private**: the competition licence forbids redistribution.

### Cell 1 — find everything, never hand-write a path

```python
import glob, os, json
for a in sorted(glob.glob("/kaggle/input/*")):
    print(a)
    for b in sorted(glob.glob(a + "/*"))[:14]:
        print("   ", os.path.basename(b))

MODELS = sorted(glob.glob("/kaggle/input/**/savedmodel_fold*", recursive=True))
VOCAB  = glob.glob("/kaggle/input/**/vocab_250.json", recursive=True)
TOPICS = [p for p in glob.glob("/kaggle/input/**/topic_*.json", recursive=True)
          if "medical" not in os.path.basename(p)]
TRAIN  = glob.glob("/kaggle/input/**/train.csv", recursive=True)

print("\nmodels =", len(MODELS), "(expect 4)")
print("vocab  =", VOCAB or "*** attach the code dataset ***")
print("topics =", len(TOPICS), "(expect 11)")
print("train  =", TRAIN or "*** competition not attached: accept the rules FIRST ***")
assert len(MODELS) == 4 and VOCAB and TOPICS and TRAIN, "fix the inputs before continuing"
```

### Cell 2 — the split must be SIGNER-DISJOINT, and prove it

This is the cell that decides whether the whole run means anything. `word_acc_250.json` came
from a signer-disjoint split; if this one is not, the numbers are inflated and not comparable.

```python
import pandas as pd, numpy as np
BASE = os.path.dirname(TRAIN[0])
df = pd.read_csv(TRAIN[0])
print(df.columns.tolist(), len(df), "rows,", df.participant_id.nunique(), "signers")

# hold out whole signers, the largest few, deterministically
sig = sorted(df.participant_id.unique())
rng = np.random.default_rng(42)
HOLD = set(rng.permutation(sig)[:max(3, len(sig)//5)].tolist())
te = df[df.participant_id.isin(HOLD)]
tr = df[~df.participant_id.isin(HOLD)]
assert not (set(te.participant_id) & set(tr.participant_id)), "SIGNER LEAK — stop"
print(f"held-out {len(HOLD)} signers, {len(te)} clips; NO signer appears in both")
print("classes present in test:", te.sign.nunique(), "of 250")
```

⚠️ **If `classes present in test` is well under 250, say so when you paste the output.** A topic
containing a class with no test clips gets a first-try rate computed over nothing, which is the
same thin-class trap that made an earlier medical selection pick `choke` — a word with **one**
test clip and a 1.000 score.

### Cell 3 — landmarks → the model's input, using the shipped code path

```python
# 250-word extraction is the repo's own; reuse it rather than re-deriving the 75-point layout.
# If extract_landmarks.py is in the code dataset, prefer it:
EX = glob.glob("/kaggle/input/**/extract_landmarks.py", recursive=True)
print("extractor:", EX or "NOT FOUND — attach it, do not reimplement the point layout")
assert EX, "the 75-point slot order is not something to guess; attach extract_landmarks.py"
!cp {EX[0]} .
```

### Cell 4 — score every topic

```python
import tensorflow as tf, numpy as np, json

words = json.load(open(VOCAB[0]))
words = words["words"] if isinstance(words, dict) else words

def masked_probs(raw, idx):
    m = raw[:, idx]
    return m / np.clip(m.sum(1, keepdims=True), 1e-12, None), raw[:, idx].sum(1)

fns = []
for d in MODELS:
    o = tf.saved_model.load(d); s = o.signatures
    fns.append((o, s["serving_default" if "serving_default" in s else list(s)[0]]))

def per_fold(X):                     # (4, N, 250)
    out = []
    for _keep, fn in fns:
        acc = []
        for i in range(0, len(X), 128):
            b = tf.constant(X[i:i+128])
            try:    r = fn(landmarks=b)
            except TypeError: r = fn(b)
            lg = r["output_0"] if "output_0" in r else list(r.values())[0]
            acc.append(tf.nn.softmax(lg, axis=1).numpy())
        out.append(np.concatenate(acc, 0))
    return np.stack(out, 0)

P4 = per_fold(X_test)               # X_test / y_test from cell 3
rows = {}
for tp in sorted(TOPICS):
    name = os.path.basename(tp)[len("topic_"):-len(".json")]
    tw = json.load(open(tp))["words"]
    idx = np.array(sorted(words.index(w) for w in tw if w in words))
    inn = np.isin(y_test, idx)
    best = None
    for mass_min in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40):
        def gate(rows_):
            m4 = P4[:, rows_, :][:, :, idx]
            mass = P4[:, rows_, :].mean(0)[:, idx].sum(1)
            m4 = m4 / np.clip(m4.sum(-1, keepdims=True), 1e-12, None)
            Pm = m4.mean(0); t1, cf = Pm.argmax(1), Pm.max(1)
            ag = (m4.argmax(2) == t1[None, :]).sum(0)
            return t1, (cf >= 0.60) & (ag >= 3) & (mass >= mass_min)
        t1, sp = gate(np.where(inn)[0])
        ok = t1 == np.searchsorted(idx, y_test[inn])
        _t, spo = gate(np.where(~inn)[0])
        r = dict(mass_min=mass_min,
                 first_try=round(float(sp.mean()), 4),
                 precision=round(float(ok[sp].mean()), 4) if sp.any() else None,
                 wrong=int((sp & ~ok).sum()),
                 off_topic_false=round(float(spo.mean()), 4))
        # SAFETY FIRST, and break ties toward the HIGHER threshold — the medical build
        # picked 0.00 over an equally-scoring 0.10 by tie-breaking on grid order, giving
        # that topic no out-of-topic gate at all.
        if r["off_topic_false"] <= 0.10:
            if best is None or (r["first_try"], mass_min) > (best["first_try"], best["mass_min"]):
                best = r
    rows[name] = best or r
    print(f"{name:<16s} n={len(idx):3d} {json.dumps(best)}")

json.dump(rows, open("/kaggle/working/topic_250_measured.json", "w"), indent=1)
print("\nPASTE topic_250_measured.json BACK")
```

### What to send back

`topic_250_measured.json`, plus cell 2's signer/class counts. Each topic file's
`mass_min` / `mass_min_provisional` and a new `measured_*` block get filled from it, and
`mass_min_provisional` is deleted — that flag existing is the marker that this run has not
happened.

---

## What the answer will probably look like, and the honest uncertainty

The 123-class model gave **0.6534 first-try open → 0.9223 across 13 measured topics**. The
250-word model starts weaker (macro per-word 0.7571 against medical's 0.8383 on three times as
many unseen signers) and has twice the competitors, so expect the topic figures to land
**below** the medical ones. The union of these 11 topics averages **0.8241** per-word accuracy
against **0.7571** for all 250, purely from excluding the 44 words under the 0.60 floor.

**Two things this run cannot fix:**

1. **No `_a`/`_b` confusability split.** It needs a confusion matrix, which needs this run to
   have happened first. Once `topic_250_measured.json` exists, a second pass can split the
   worst topics the way the medical set was split — measured worth 35 → 14 wrong words there.
2. **`owie` is not recoverable by masking.** It scores **0.32**, so it sits below the floor and
   is unreachable. In a child-language corpus `owie` means *hurt*, which is arguably the single
   most load-bearing word in the whole 250 for anything clinical. Also excluded and worth
   knowing: `mouth` 0.30, `give` 0.15, `go` 0.22, `nap` 0.11, `after` 0.27, `person` 0.23.
   That is a **data** problem — more signers per word, per `docs/CLIPS_PER_SIGN_CURVE.md` —
   not a gate problem.
