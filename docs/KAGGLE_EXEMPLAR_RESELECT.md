# CPU notebook — exemplar re-selection, and the 29302 question

**Written 2026-08-14.** Two cheap experiments in one session. **CPU only — this does NOT consume
GPU quota.** ~35 minutes total.

> **This is the only open experiment in the project.** Recognition is closed (`SESSION_HANDOFF.md`
> §0.5). Both cells below are about the *avatar*, which is where all remaining headroom is.

---

## Part A — is the 39 tier-C words' degradation recoverable? (~30 min)

### The finding this tests

Exemplar selection is starved by its own validity filter. Measured 2026-08-14:

| class | median candidates | median **valid** | survival | median coverage |
|---|---|---|---|---|
| 1 one-handed | 292 | 138 | **49.0%** | **90.0%** |
| 2s symmetric | 274 | **3** | **1.2%** | 50.0% |
| 2a asymmetric | 254 | **5** | **2.1%** | 51.4% |

### ⚠️ Read this before deciding the run is likely to succeed

An earlier version of this doc quoted `corr(valid_candidates, coverage) = **+0.804**` across all
250 words and treated it as evidence that starvation *causes* low coverage. **It is mostly a
between-class artifact.** Disaggregated:

| | pooled | class 1 | class 2s | class 2a |
|---|---|---|---|---|
| corr(valid_candidates, coverage) | **+0.804** | +0.218 | +0.244 | +0.443 |
| valid-take range | — | 73–214 | 1–8 | 2–9 |
| coverage range | — | 0.56–1.00 | 0.10–0.82 | 0.15–0.75 |

Within class the relationship is weak. **Class-1 words never fall below 73 valid takes and still
span 0.56–1.00 coverage**, so a large pool does not buy good coverage. And 2a's valid range is only
**2–9** — a 7-take span cannot tell you what happens at 130. The pooled figure is largely
restating "two-handed signs have both fewer valid takes and worse coverage", which is two
consequences of two-handedness rather than one causing the other.

This is the same pooled-metric trap this project has now hit three times (§0.4's per-signer
collapse hidden by pooled test accuracy; the masking A/B; this). It is recorded here rather than
quietly fixed because the run's expected value changed with it.

**So why run it at all?** Because the justification is **mechanism, not correlation**: on 2a the
gate protects the recorded passive wrist, and `asl_2a_base_placement.json` now *discards* that
wrist. The gate cannot be buying anything on 2a, so dropping it is free — the only question is
whether a bigger pool happens to contain a better-tracked take. **Treat the outcome as a genuine
unknown, not a likely win.** It is 35 CPU-minutes and it is the only way to find out.

`--require-passive-up` is the sole cause. Class 1 returns at
[`build_sign_clips.py:336`](../training/build_sign_clips.py#L336) *before* the gate is reached,
which is exactly why class 1 keeps 49% and the two-handed classes keep ~1–2%.

**Why dropping it for 2a is not a trade at all:** the gate exists to guarantee the recorded passive
wrist is held in signing space rather than hanging. But that wrist is measured at a median **1.56
shoulder widths** from the dominant wrist, is unusable as a base, and is now *replaced* by
`asl_2a_base_placement.json`. So on 2a the gate sacrifices ~98% of the pool to preserve a quantity
that is discarded downstream.

**For 2s it IS a real trade** and is deliberately left alone: there the passive handshape is
mirrored onto a *recorded* wrist, so wrist position still matters. `--require-passive-up off` would
test that too, but it wants a render comparison and a Deaf reviewer, not just a coverage number.

### What would make this a failure

**Success:** 2a median valid candidates rises 5 → ~130, and median 2a coverage rises materially
(51.4% → 80%+ would move ~16 words out of tier C).
**Failure:** valid candidates rise but coverage does not. That means the corpus genuinely has no
better take, tier C is real, and `asl_2a_base_placement.json` plus the short-gap hold are the only
levers left. **That is a useful answer too** — it closes the question rather than leaving it open.

### Inputs to attach

| dataset | why |
|---|---|
| **`asl250-canon-v1-REFUTED`** | the corpus. Yes, that one — canonicalization was refuted as an *accuracy* lever, not as hand identification, and `build_sign_clips.py:243` requires `left_dead > 0.99` to see a canonical layout. This corpus measures 1.000. It also carries `split_manifest.parquet` + `by_word/`, which is exactly what `--data-dir` wants. |
| **a new code dataset** (see below) | `build_sign_clips.py` is **not** in `asl250-code-v19` |

**The code dataset needs four files.** Name it `asl250-anim-v1`, Private, two files at a time —
**never drag a folder, the repo contains `.env`:**

```
training/build_sign_clips.py     the builder, with --require-passive-up 2s-only
sign_landmarks.py                its only local import (repo root, NOT training/)
vocab_250.json                   frozen class order
asl_handedness_250.json          the handedness lexicon -> --lexicon
```

Settings: **CPU** (no accelerator), Internet **off**.

### Cell 1 — stage and verify the code has the new flag

```python
import os, glob, sys, shutil, subprocess, json
NEED = {
    "build_sign_clips.py":     ("2s-only", "gate_on", "passive_up_gate_note"),
    "sign_landmarks.py":       ("hand_arm_alignment", "required_hand_coverage", "mirror_match"),
    "vocab_250.json":          (),
    "asl_handedness_250.json": ("passive_handshape",),
}
def missing(d):
    out = []
    for f, marks in NEED.items():
        p = os.path.join(d, f)
        if not os.path.exists(p):
            return None
        t = open(p, encoding="utf-8", errors="ignore").read()
        out += [f"{f}:{m}" for m in marks if m not in t]
    return out

cands = sorted({os.path.dirname(p)
                for p in glob.glob("/kaggle/input/**/build_sign_clips.py", recursive=True)})
good = []
for d in cands:
    m = missing(d)
    print(("  [current] " if m == [] else "  [reject ] ") + d, "" if m == [] else m)
    if m == []: good.append(d)
assert len(good) == 1, ("need exactly 1 code dataset containing all 4 files with the NEW flag. "
                        "'2s-only' must appear in build_sign_clips.py — if it does not, you "
                        "uploaded the pre-2026-08-14 builder.")
CODE = good[0]
for f in NEED: shutil.copy(os.path.join(CODE, f), f)
sys.path.insert(0, ".")
print("\nstaged:", sorted(NEED))
```

### Cell 2 — find the corpus and assert it is the canonical one

```python
import numpy as np, random
from sign_landmarks import canonicalize_missing

roots = sorted({os.path.dirname(p)
                for p in glob.glob("/kaggle/input/**/split_manifest.parquet", recursive=True)})
roots = [r for r in roots if os.path.isdir(os.path.join(r, "by_word"))]
print("corpus candidates:", roots)
assert len(roots) == 1, "need exactly 1 corpus with split_manifest.parquet + by_word/"
DATA = roots[0]

fs = sorted(glob.glob(os.path.join(DATA, "by_word", "*", "sequences.npz")))
random.seed(0); random.shuffle(fs)
ld = []
for f in fs[:40]:
    z = np.load(f)
    for k in list(z.keys())[:5]:
        a = canonicalize_missing(z[k].astype("float32"))
        if a.shape[1] < 75: continue
        ld.append(float(not np.isfinite(a[:, 33:54, :2]).all(-1).any()))
print(f"{DATA}\n  left_dead {np.mean(ld):.3f}   (build_sign_clips needs > 0.99 to see CANONICAL)")
assert np.mean(ld) > 0.99, "not the canonical corpus — the builder will read it as LEGACY"
```

### Cell 3 — the control arm, so the comparison is against a re-run and not against a memory

```python
!python build_sign_clips.py --data-dir {DATA} --vocab vocab_250.json \
    --lexicon asl_handedness_250.json --require-passive-up on \
    --out /kaggle/working/clips_control.npz
```

Do not skip this. The shipped `sign_clips_250.meta.json` was built on a different day from a
corpus that no longer exists; comparing the new arm against it would confound the flag with
whatever else differed. **Two arms, one session, one variable.**

### Cell 4 — the test arm

```python
!python build_sign_clips.py --data-dir {DATA} --vocab vocab_250.json \
    --lexicon asl_handedness_250.json --require-passive-up 2s-only \
    --out /kaggle/working/clips_2sonly.npz
```

### Cell 5 — the acceptance test

```python
import statistics as st
def load(p):
    return {w["word"]: w for w in json.load(open(p, encoding="utf-8"))["words"]}
A = load("/kaggle/working/clips_control.meta.json")
B = load("/kaggle/working/clips_2sonly.meta.json")

print(f"{'class':<5}{'arm':<9}{'n':>4}{'med valid':>11}{'med cov':>9}{'tierC':>7}")
rows = []
for cls in ("1", "2s", "2a"):
    for name, M in (("control", A), ("2s-only", B)):
        r = [v for v in M.values() if v["handedness_class"] == cls]
        vc = st.median([v["valid_candidates"] for v in r])
        cv = st.median([v["dominant_hand_coverage"] for v in r])
        c  = sum(1 for v in r if v["dominant_hand_coverage"] < 0.50)
        print(f"{cls:<5}{name:<9}{len(r):>4}{vc:>11.0f}{cv:>9.3f}{c:>7}")
        rows.append((cls, name, vc, cv, c))

a2 = next(r for r in rows if r[:2] == ("2a", "control"))
b2 = next(r for r in rows if r[:2] == ("2a", "2s-only"))
print(f"\n2a valid candidates : {a2[2]:.0f} -> {b2[2]:.0f}")
print(f"2a median coverage  : {a2[3]:.3f} -> {b2[3]:.3f}   ({b2[3]-a2[3]:+.3f})")
print(f"2a tier-C words     : {a2[4]} -> {b2[4]}")

# 2s must be untouched: the gate still applies there, so any movement means the flag leaked.
s_a = next(r for r in rows if r[:2] == ("2s", "control"))
s_b = next(r for r in rows if r[:2] == ("2s", "2s-only"))
assert abs(s_a[3] - s_b[3]) < 1e-6, (
    f"2s coverage moved {s_a[3]:.4f} -> {s_b[3]:.4f}. The flag is supposed to be a NO-OP on 2s; "
    f"if 2s changed, the gate is not being applied per-class and the 2a result is not clean.")
print("\n2s unchanged (flag correctly scoped)")

verdict = ("RECOVERABLE — re-export the 2a words" if b2[3] - a2[3] > 0.15 else
           "NOT recoverable — tier C is real; the corpus has no better take")
print(f"VERDICT: {verdict}")
```

The `2s` assertion is the load-bearing one. `2s-only` must change **nothing** for 2s — if it does,
the gate is not scoped per class and the 2a number cannot be trusted.

### Cell 6 — save

**Version → Output → New Dataset → `asl250-anim-reselect-v1` → Private.** Brand-new name, never
onto an existing dataset. Both `.npz` files and both `.meta.json` files are in the output; if the
verdict is RECOVERABLE, the `2s-only` npz is what a re-export runs from.

### If it says RECOVERABLE

⚠️ **It changes the 35 2a word files, which breaks the "byte-identical" promise in
`Fix/REPLY-TO-GHOZLAN-v9.md` §0.1.** Tell the animation side *before* they build on it. The
re-export itself is local and takes a minute:
`python gloss_to_motion.py --per-word --out-dir animation_handoff`.

---

## Part B — the 29302 question (~5 min, same session)

The last unpursued lead from the refuted canonicalization work. 29302 scores **0.314** against
0.78–0.82 for the pure-R signers and did not move when the corpus was canonicalized
(**−0.0002**). One hypothesis was never tested: `limb_assignment` takes **one** median distance and
picks **one** block for a whole clip, so if the tracker alternates hands *within* a clip, the
decision is at the wrong granularity.

This is **diagnosis, not a fix** — and the honest prior is that the answer is "that signer's
recording is just different." Run it because it is five minutes and closes a loop, not because a
fix depends on it.

```python
import pandas as pd, numpy as np, glob, os
from sign_landmarks import canonicalize_missing

man = pd.read_parquet(os.path.join(DATA, "split_manifest.parquet"))
print("participants:", sorted(man["participant_id"].unique())[:25])

def switch_rate(pid, cap=300):
    rows = man[man["participant_id"] == pid]
    flips = kept = 0
    for w in rows["word"].unique():
        f = os.path.join(DATA, "by_word", str(w), "sequences.npz")
        if not os.path.exists(f): continue
        z = np.load(f)
        for k in list(z.keys())[:3]:
            a = canonicalize_missing(z[k].astype("float32"))
            if a.shape[1] < 75: continue
            L = np.isfinite(a[:, 33:54, :2]).all(-1).any(-1)
            R = np.isfinite(a[:, 54:75, :2]).all(-1).any(-1)
            # which block is populated, frame by frame; count changes of state
            state = np.where(L & ~R, 0, np.where(R & ~L, 1, 2))
            s = state[state != 2]
            if s.size > 1:
                flips += int((np.diff(s) != 0).sum()); kept += 1
            if kept >= cap: break
        if kept >= cap: break
    return flips / max(kept, 1), kept

for pid in (29302, 34503, 32319, 26734, 2044):
    r, n = switch_rate(pid)
    print(f"  {pid}: {r:6.2f} intra-clip block switches per clip   (n={n})")
```

**Read:** if 29302 is an order of magnitude above the pure-R signers, per-clip block selection is
the wrong granularity for that signer and per-*frame* assignment is worth considering. If it is
comparable, the 0.314 is not about block layout at any granularity and the question is closed —
which, given canonicalization moved that signer by −0.0002, is what to expect.

**Either way, do not reopen recognition on this alone.** It would need its own A/B and the
pooled-metric trap in §0.4 applies unchanged.
