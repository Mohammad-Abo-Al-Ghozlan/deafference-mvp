# The medical avatar handoff — 55 clinical signs, and one finding that changes the rig

**Built 2026-09-04.** `animation_handoff_medical/` — 55 per-word motion files + `reference_pose.json`,
7.5 MB. Same `sign-animation/v1` contract as the 250-word handoff, so nothing in
`SIGN_ANIMATION_CONTRACT.md` or `AVATAR_BRIEF_COMPLETE.md` needs re-reading — **except §6/§9,
which this document amends.**

```
python training/build_sign_clips.py --data-dir data_medical \
    --vocab vocab_medical_ship55.json --lexicon asl_handedness_medical.json \
    --out sign_clips_medical.npz
python gloss_to_motion.py --clips sign_clips_medical.npz \
    --lexicon asl_handedness_medical.json --per-word --out-dir animation_handoff_medical
```

---

## 1. 🔑 The passive hand is REAL here. Do not synthesize over it.

The 250-word `renderer_contract` says, verbatim:

> "For every word not marked '1', the passive hand's landmarks **DO NOT EXIST** in our corpus
> for any take. The exported clip carries the dominant hand only. The avatar must synthesize
> the passive hand."

That is a true statement about **GISLR**, which records one hand per participant. It is **false
about Sem-Lex**, which is what the clinical model is built from. Measured on the shipped
exemplars, `synthesis.passiveHandRecorded` per word:

| corpus | class | words | passive hand present |
|---|---|---|---|
| GISLR (250-word) | 2s + 2a | 87 | **0.000 in every single word** |
| Sem-Lex (clinical) | 2s | 18 | **81.7%** of frames |
| Sem-Lex (clinical) | 2a | 12 | **81.1%** of frames |

Two-handed clinical exemplars average **73.8%**, minimum 6.2%, and **30 of 30 carry a real
passive hand**. The same code measures 0.000 on GISLR and 0.81 here, so this is a property of
the corpus, not of the measurement.

**What the animator must do:** read `segments[].synthesis.passiveHandRecorded` first.

- `> 0` → the passive hand is in `frames[]`. **Use it.** Fall back to the synthesis rule only
  on frames where it is `null`.
- `== 0` → synthesize as the original contract says (mirror for 2s, unmarked base for 2a).

Synthesizing whenever `twoHanded` is true would overwrite recorded landmarks with a guess, and
nothing would raise. `SYNTH_NOTE` in every file now says this.

**Independent corroboration.** The handedness labels come from ASL-LEX, the passive-hand rates
from MediaPipe tracking — two unrelated sources. Class 1 sits at 4.1% both-hand frames while
two-handed classes sit at 41.8% corpus-wide, a **10× separation neither number was derived
from**. The labels and the landmarks agree.

---

## 2. Quality — this handoff is much cleaner than the 250-word one

| | 250-word | clinical 55 |
|---|---|---|
| tier A (dominant coverage ≥0.80) | 146 / 250 = **58%** | **52 / 55 = 95%** |
| tier B | 59 | 3 |
| tier C | 45 | **0** |
| dominant coverage, mean | — | **0.940** (median 0.969, min 0.547) |
| words with ≤2 valid takes | 20 | **0** |
| words under 0.53 s | 6 | **0** |

Per class: 1 → 0.962 (25 words, all tier A) · 2s → 0.935 · 2a → 0.902.
Weakest five: `hand` 0.55, `walk` 0.73, `week` 0.73, `always` 0.81, `day` 0.81.

Sem-Lex is studio-recorded prompted signing; GISLR is crowd-sourced caretaker signing on
phones. That difference shows up here more clearly than anywhere else in the project.

---

## 3. Two bugs this build found and fixed

**(a) 20 of 55 exemplars were LEFT-dominant, and the contract promised they weren't.**

`SIGN_ANIMATION_CONTRACT` guarantees *"dominantHand is 'R' in every file BY CONSTRUCTION"*.
True for the 250-word clips (`all_exemplars_right_dominant: true`), **false** for the clinical
ones — Sem-Lex was extracted **without** `--canonical-hand`, matching the training config
(`canonical_hand: false` in all four folds), so its meta says `false` and 20 exemplars have the
signing hand in the 33-53 block.

Exported unmirrored, those 20 words told the animator the hand was at 54-74 when it was at
33-53, and **five words reported `dominantCoverage: 0.000`** because their R block is entirely
empty. Nothing raised. It is the same failure the `DOMINANT_HAND` comment records costing us
`finish`, arriving from the other direction.

`gloss_to_motion.py --canonicalize auto` (now the default) mirrors left-dominant exemplars
using the recorded per-word dominance from `build_sign_clips`. Result: 0 words at 0.000, tiers
A52/B3/C0, and `dominantCoverage` mean 0.940 — **exactly matching `build_sign_clips`' own
independent figure**, which is the check that says the mirroring is right rather than merely
different.

> ⚠️ It mirrors with a **hand-swapping** map, deliberately NOT
> `training/extract_canonical.canonicalize`. That function does
> `a[:, RESERVED_BLOCK, :] = np.nan` — it destroys the non-dominant block. Correct for the
> recognition corpus; here it would erase the passive hand, which is the whole point of §1.

**(b) The medical clips were being paired with the 250-word metadata.**

`--meta` defaulted to a fixed `sign_clips_250.meta.json`, so the clinical run attached the
250-word corpus's take counts to whichever 15 words the two vocabularies share — and silently
gave the other 40 no `sourceQuality` at all. The default is now derived from `--clips`
(`sign_clips_X.npz` → `sign_clips_X.meta.json`). Coverage went 15/55 → 55/55.

---

## 4. The lexicon — ASL-LEX rather than hand-written

`asl_handedness_medical.json`: **25 one-handed · 18 2s · 12 2a**.

Sources: **ASL-LEX 53**, `asl_handedness_250.json` 1 (`eye`, no ASL-LEX row), hand-labelled 1
(`hand`). Confidence: high 51, med 2, low 2. Every annotated word is **unanimous across its
takes** — which is what a per-*sign* annotation should look like, and a check that the join is
sound.

**All 12 2a passive handshapes resolve to measured templates** — `B`×8, `1`, `5`, plus 2
unresolved. Zero live approximations, same as the 250-word set.

### Free cross-check: 86% agreement with the hand-written 250-word lexicon

14 ship words appear in both. **12 agree.** The two that don't:

| word | 250-word said | ASL-LEX says | both-hand tracking | reading |
|---|---|---|---|---|
| `sick` | `1` (conf **med**) | `2s` over 183 takes | 35.4% | ASL-LEX + tracking agree it is two-handed; the 250 label was already flagged uncertain |
| `morning` | `2a` (conf **high**) | `1` over 80 takes | 17.4% corpus / **62% in the exemplar** | **unresolved — do not assume ASL-LEX wins** |

`morning` is worth the attention. Its ASL form is a classic 2a: the passive forearm lies
horizontal and the dominant forearm rises beneath it. ASL-LEX calling it One Handed is
consistent with a pattern the 250-word audit already found from the other side — **ASL-LEX
treats the passive forearm as a body *location*, not a second articulator.** `day` (62%
both-hand on a class-1 label) and `blood` (48%) look like the same phenomenon.

**For the renderer the distinction matters even when the linguistics is arguable:** the avatar
must still pose the forearm, whatever the sign is called. These three are the first rows for a
Deaf reviewer.

---

## 5. What is NOT done

- **`hand` and `sit` cannot be drawn by synthesis.** `sit` records `Dominance Condition
  Violation` in ASL-LEX's handshape field — a category, not a shape; `hand` has no ASL-LEX row
  at all. **Both have a recorded passive hand** (24% and 46%), so per §1 the renderer can use
  the real one and the gap is not blocking.
- **Every clip is exactly 64 frames, and every sign plays ≈2.4–3.6× too slow.** See §7 — this
  is worse than "uniform duration", and my first note on how to fix it was wrong.
- **No Deaf review**, of the lexicon or of anything else.
- The rig is not delivered, and the runtime owner is still unknown (task 2B).

## 6. Licence

Sem-Lex is **CC BY-NC-SA**: non-commercial, and share-alike arguably reaches derived work. The
class labels are ASL-LEX annotations redistributed through Sem-Lex. The clinical model is
already non-commercial for the same reason, so **this changes nothing about this track's
shippability** — it becomes a live question only if these labels are reused for the 250-word
commercial track. A Deaf reviewer must be the one who *sets* a shipped label; ASL-LEX only says
where to look.

---

## 7. Native duration: the avatar plays every sign ~3× too slow

**Correction.** §5 first said the durations were "recoverable — `semlex_metadata.csv` has a
`duration` column in milliseconds". **That is wrong**, and building on it would have made the
timing worse rather than better. Measured over the 54 ship words that have metadata:

```
per-word MEDIAN raw video duration   1543 – 2474 ms   spread 1.60x   CV 0.10
in frames @30fps                     46 – 74          (every clip is 64 today)
GISLR 250-word clips, for contrast   9 – 116 frames   spread 12.9x
```

Sem-Lex is a **prompted studio protocol**: a participant hits record, signs, hits stop. Every
recording is ~1.8 s because that is the protocol, not because the signs are the same length.
CV 0.10 is protocol noise. Retiming from it would have added ±28% of *invented* variation.

### What the real number is

The extractor trims to the tracked span, and its own measurements say what that costs:

```
LEADING untracked 30.9%  +  TRAILING 30.6%   ->  61.5% of raw frames are lead-in/lead-out
trimmed span (= the sign)   18 – 27 frames
raw recording               38 – 52 frames
```

So the actual sign is **≈18–27 frames, 0.6–0.9 s** — and it is resized up to 64. **Every
clinical sign on the avatar is playing at roughly a third of natural speed.** That is a real
defect, not a cosmetic one: at 2.13 s per sign a three-sign phrase takes 6.4 s.

It is also genuine signal — 18 vs 27 frames is a 1.5× spread *across buckets*, and more per
clip. The information exists; it was simply never written down.

### The fix, ready for the next Kaggle run

`semlex_poses_to_75.py` computes `st["span"]` three lines before it appends the tensor, and
then dropped it. It now carries `span`, `raw_frames`, `lead` and `trail` into the `.npz`
alongside `X`, and prints the median slow-down factor at the end of a run.
`npz_to_train_format.py` tests `need <= set(d.files)`, so the extra arrays are
backward-compatible and nothing downstream needed changing.

**This does not retime the current handoff** — the existing `.npz` predates the patch and
`X` cannot be un-resized. Recovering it needs one CPU re-extract on Kaggle (no GPU), after
which `build_sign_clips.py --fixed-frames 0` and `gloss_to_motion` will carry true durations
through `nativeFrames` with no further changes.

Until then, treat the handoff as **correct in pose and uniform in timing** — the animator can
build and rig against it, and only the playback rate changes afterwards.
