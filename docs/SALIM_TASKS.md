# What's on Salim — the ordered task list

**Written 2026-09-01.** Derived from the cross-track plan of 2026-08-31, updated for the avatar
designer hire decided on 2026-09-01.

Only **your** tasks are here. What is on me is listed at the end so you can track it, but there is
nothing for you to do in that section.

> ## ⚠️ One correction before you start
>
> The plan told you to *"send `deafference_handoff_FINAL.zip`"* to Ghozlan. **Do not send that
> file.** It is dated **Aug 18** and the export was regenerated **Aug 26**, so it is 8 days stale —
> sending it would hand Ghozlan the old data a second time.
>
> Measured today, comparing the zip against the current working tree:
>
> ```
> word files:  215 identical  |  35 CHANGED  |  0 missing
> asl_2a_base_placement.json   CHANGED
> handshape_templates.json     CHANGED
> asl_handedness_250.json      same
> ```
>
> **Exactly 35 files changed, and they are exactly the 35 class-2a words** — so the "35 files
> changed" claim is now measured, not asserted. Task 2 is therefore **rebuild, then send**, and the
> named list is in it.

---

## ✅ CLOSED on 2026-09-01

### ✅ 1. Rotate the three burned credentials — **DONE**

AWS · Gemini · Supabase. **The only item on the board with unbounded downside, and it is closed.**

One thing to confirm once if you have not: the new values are in the gitignored `.env` only, and
nothing was written into `.env.example` or a notebook cell.

### ✅ 3. Send the skeleton brief to a 3D artist — **DONE, and one is hired**

`AVATAR_SKELETON_BRIEF.md` sent; a designer is engaged. **Ghozlan is no longer responsible for the
avatar** — the designer owns it.

That role change opens one gap, which is now task 2A below. It does **not** block the designer.

---

## NOW — today

### ☐ 2. Rebuild the avatar handoff — and it now goes to the DESIGNER, not Ghozlan · ~15 min

**Changed 2026-09-01.** With Ghozlan off the avatar, this package's recipient is the designer — at
**P1-M2**, per the brief §11, not immediately. So the urgency is gone, but the *rebuild* still
matters: the stale zip must not be the thing anyone reaches for later.

Do it now while the reason is fresh, and park the result.

If Ghozlan is still on the project in any capacity — the runtime, the web app — **he should still get
the corrected files and the note below**, because he built against the superseded export for a week
and deserves to know why his results looked wrong.

Rebuild (see the correction above):

```bash
cd "c:/Users/1mhmd/OneDrive/Desktop/Deaffearance/Deafference"
python - <<'PY'
import zipfile, glob
OUT = "deafference_handoff_2026-09-01.zip"
members = sorted(glob.glob("animation_handoff/words/*.json")) + [
    "animation_handoff/contact_sheet.png",
    "animation_handoff/reference_pose.json",
    "animation_handoff/review_log.json",
    "asl_2a_base_placement.json",
    "asl_handedness_250.json",
    "handshape_templates.json",
    "sign_clips_250.meta.json",
    "docs/AVATAR_LIMITS.md",
    "docs/SIGN_ANIMATION_CONTRACT.md",
    "Fix/FROM-SALIM-v7.md",
    "Fix/REPLY-TO-GHOZLAN-v9.md",
]
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for m in members:
        z.write(m)
print(f"wrote {OUT} with {len(members)} entries")
PY
```

Then tell him **what changed and why**, not just "here's a new zip":

> The 2a reselect A/B landed and it moved 35 files — all 35 class-2a words. `--require-passive-up
> 2s-only` lifted 2a median coverage from 0.432 to 0.829 and cleared all 24 tier-C 2a words. Two
> lexicons changed with it: `asl_2a_base_placement.json` and `handshape_templates.json`.
>
> The 35: after, all, arm, backyard, before, beside, brother, chair, chocolate, clean, closet,
> dance, empty, every, fall, first, flag, garbage, helicopter, hide, into, jump, mitten, morning,
> night, on, pen, pencil, read, ride, table, that, time, touch, tree.
>
> Class 1 and 2s are byte-identical — verified exactly, not on a median.

### ☐ 2A. Send `AVATAR_BRIEF_COMPLETE.md` to the designer · ~2 min

**Send `docs/AVATAR_BRIEF_COMPLETE.md` — one file, nothing attached.** It is v6: everything from v5
plus six appendices that fold in the content of every file we used to attach. The PNGs, the reference
pose and the templates are all inline as numbers now, so the designer needs nothing but this
document. Every section number from v4 and v5 is unchanged, so anything they bookmarked resolves.

*(`AVATAR_SKELETON_BRIEF.md` — v5 — is kept as-is for history. Do not send both.)*

**Optional extras if they ask:** `docs/handshape_review/*.png` (eight renders) and
`animation_handoff/contact_sheet.png` (all 250 words as stick figures). Neither is required.

**Three corrections are the reason to send this rather than leave v5 standing.** All three are
numbers we had already given them, and two would have cost real work:

- **§6.8 — a hand sized from our figure would be less than half the right size.** v5's three "sanity
  figures" were all read off the single reference frame it tells you not to model from.
  `wrist→middle-fingertip ≈ 0.19` shoulder-widths is **7.5 cm**; measured over 11,292 frames it is
  **0.45**. A second figure was mislabelled — `0.70` was the distance to the shoulder *joint*, not the
  midpoint (0.41). Corrected, with the measured replacements and the reason each was wrong.
- **§8.4 — the signing space is wider than we said.** `±0.75` shoulder-widths covers only 60% of
  frames; the median is 0.69 and 25% of frames put a wrist above the shoulder line. Real box is
  ~**±1.1** laterally. This is a shoulder-and-clavicle weighting requirement, so it is phase-1 work.
- **§10 — the B/5 requirement is now isolated.** Same finding as v5, but the number that constrains
  the rig is separated out: `5` needs **27°** of knuckle fan where `B` has **1.5°**. That is pure MCP
  abduction with curl removed, which is the thing a rig either can or cannot do.

And two things that are new capability rather than correction:

- **Appendix A — the seven handshapes as numbers**, replacing the PNGs. Wrist-to-fingertip
  signatures, spread, thumb geometry, joint angles, and per-shape provenance. Checkable with a
  ruler. It also flags that **`O` is the one template not to trust** (scatter 0.286, marked unusable),
  and that **`S` rests on a single word**.
- **Appendix B — all 35 passive-hand poses, word by word.** Handshape, the *named surface* the other
  hand lands on, palm and finger orientation. Eleven distinct contact surfaces appear, and **nine of
  the 35 words land on the back, side or underside of the passive hand** — so a hand that only reads
  from the front fails nine words. That was implicit in §9 before; now it is a list.

Still true from v5, and still the one item that may cost money:

- **"Blockout" is defined.** It does *not* mean a crude box-man — §9 needs a forearm the hand slides
  along, §6.9 a real brow ridge, §10 hands legible at 320 px. So: anatomically correct, cleanly
  topologised, properly weighted, **unstyled but not unfinished**, hands at final quality. §5 invites
  them to reprice rather than argue at P1-M3. **Expect that conversation — the ambiguity was our
  wording's fault.**

### ☐ 2B. Decide who owns the runtime · a decision, not a task

**This is the gap the role change opens, and it needs an answer before P1-M2 — not before P1-M1.**

The designer delivers a *rig*. Something has to **drive** it: read our landmark files, solve the IK,
blend between signs, smooth the motion. A 3D artist does not normally write that, and it was
Ghozlan's.

Concretely, two things depend on the answer:

1. **Three acceptance tests need a runtime** — 3 (distal keying), 4 (bone-length stability under
   playback) and 7 (reference-pose retarget). Brief v5 already moves those to integration and
   off the designer's payment gate, so **the hire is not blocked.** But they still have to run
   eventually, and test 3 is the regression test for the entire defect this phase exists to prevent.
2. **The test harness promised in §11** was Ghozlan's player. v5 marks it "being confirmed" rather
   than promising it. If it is gone, the designer loses the ability to watch their own rig move under
   real data at P1-M3 — and per §6.12 that is exactly where motion failure modes **#3, #4 and #5**
   surface. They are invisible in a static pose. Losing the harness means losing the only cheap way
   to catch three of the six errors the designer owns.

**A useful way to split it:** test 1 (42 nodes in the exported `.glb`) is the *designer's*
obligation and is fully checkable from the file. Test 3 checks whether *our* retargeter uses those
nodes — that is our bug surface, not theirs. So the rig can be accepted on file-level evidence, and
the runtime question bites at integration.

Tell me which way this lands and I will write whatever fills the gap — including a standalone
file-level verifier that covers tests 1, 2, 6, 12, 13 and 14 with no runtime at all.

### ☐ 4. Fingerspelling `--report` on one real shard · ~15 min, mostly waiting

Unblocks **the only licence-clean track that can carry a clinical vocabulary.** Fifteen minutes of
your time buys days of mine.

Fingerspelling matters more than "26 letters" sounds. Twenty-six letters is the only thing that makes
**vocabulary size stop mattering** — patient names, street names, drug names, dosages. No lexicon
will ever contain them, the current system has zero single-letter entries, and in a clinic that is
not a nice-to-have.

**This is a CPU job.** Do not turn the GPU on; it does nothing here and burns your 30-hour budget.

---

#### Step 1 — accept the competition rules *(one time only)*

1. Open Kaggle → search **"Google — American Sign Language Fingerspelling Recognition"**.
2. **Rules** tab → **I Understand and Accept**.

Competition data stays available after a competition closes; accepting the rules is what unlocks it.
**No email, no negotiation, no licence problem** — this is the clean track.

#### Step 2 — put `subset_landmarks.py` where Kaggle can see it

Create a **new private dataset** with that one file:

1. Kaggle → **Datasets** → **New Dataset**.
2. Drag **only** `training/fingerspelling/subset_landmarks.py`.
3. Name it something like `deafference-fs-code`. **Visibility: Private.**

> ⚠️ **Drag the single file, not the folder and never the repo root.** The repo contains `.env`, and
> a public Kaggle dataset would publish it.

#### Step 3 — new notebook, attach both inputs

New Notebook → right panel → **Add Input**:

- **Competitions** → the fingerspelling competition
- **Datasets** → `deafference-fs-code`

Accelerator: **None**. Persistence: off.

#### Step 4 — find the real paths *(do this before anything else)*

The folder slug may not be what I guessed. Run this first:

```python
import os, glob
for r in sorted(glob.glob("/kaggle/input/*")):
    print(r)
    for sub in sorted(glob.glob(r + "/*"))[:8]:
        n = len(glob.glob(sub + "/*")) if os.path.isdir(sub) else ""
        print(f"    {os.path.basename(sub)}   {n}")
```

You are looking for a directory holding **`train.csv`** and **`train_landmarks/`** with a few hundred
`.parquet` files. Whatever its full path is, that is your `--base`.

#### Step 5 — prove the script works *before* touching real data

```python
!cp /kaggle/input/deafference-fs-code/subset_landmarks.py .
!python subset_landmarks.py --selftest
```

Must end with **`ALL CHECKS PASSED`**. This takes about a second and validates that every one of the
75×3 landmarks lands in the right slot — each test value encodes its own point and axis, so a
transposed reshape cannot pass. If this fails, stop and send me the output; nothing downstream is
trustworthy.

#### Step 6 — the measurement *(writes nothing)*

Substitute the `--base` you found in step 4:

```python
!python subset_landmarks.py \
    --base /kaggle/input/asl-fingerspelling \
    --report --limit-files 1
```

One shard, read-only, a few minutes. **Paste me the whole output.**

---

#### What I am looking for, and why

The single number that decides the model design:

> **How many sequences have a dominant-hand gap longer than 10 frames.**

We know **45% of frames have no tracked hand**, that dropout is **3.6× motion-correlated**, and that
interpolation recovers only **12%**. What we do not know is the *shape* of the loss:

| If the gaps are | Then |
|---|---|
| **many short gaps** (1–3 frames) | Interpolation is defensible and the model can treat the hand as continuous. |
| **fewer long gaps** (>10 frames) | Absence must be a **first-class input** — the model has to learn "no hand here" rather than be fed an invented one. That is a different architecture, and knowing it now saves building the wrong one. |

Also in the output and worth having: per-sequence length distribution, dominant-hand presence rate,
and how many sequences are left-dominant.

**Then, and only then, task 6** subsets four shards for real. Do not skip step 6 to save time — a
`--report` that reveals long gaps changes what task 6 is even for.

---

## THIS WEEK

### ☐ 5. Read the ASL Citizen licence · ~30 min

**The single highest-leverage thing on this list**, and nobody has ever done it.

83,399 videos · 2,731 signs · **52 signers** (Sem-Lex has 41, and signer count is one of the few
dataset properties we have *measured* to matter). Commercial use routes through
`ASL_Citizen@microsoft.com` — already a better shape than Sem-Lex's flat no.

Read for four things, in order:

1. Does it permit **commercial** use or deployment?
2. Is there a **share-alike-equivalent** clause? That is the one that bit us on Sem-Lex and it is
   easy to skim past while reading for "non-commercial".
3. Any constraint on **distributing model weights** trained on it?
4. Clinical coverage — specifically the 16 words Sem-Lex could not supply: fever, chest, stomach,
   nausea, rash, cramp, infection, sneeze, neck, shot, wheelchair, patient, stand, very, never.

**If it is permissive, the medical track stops being a feasibility study and becomes the product
again.** That is why this is worth 30 minutes before anything else on this section.

### ☐ 6. Subset four fingerspelling shards · ~20 min

After task 4, same notebook:

```python
!python subset_landmarks.py --base /kaggle/input/asl-fingerspelling \
    --out /kaggle/working/fs75 --limit-files 4
```

Four shards is baseline-sized — enough to train something real, small enough to iterate.

### ☐ 7. Re-upload `ensemble_eval.py` to the Kaggle code dataset · ~5 min

The version on Kaggle predates commit `1c9a2fa`, which added `class_names` to the report. Without
it, the next confusion CSV is unreadable without guessing the label order — and guessing it wrong is
exactly the bug that nearly made me hand you confidently mislabelled output.

Same rule as always: **a brand-new dataset name, never overwriting an existing one.** Keep it
Private.

### ☐ 8. Decide the 2s gate · ~30 min of reading, then a call

From **`docs/RESELECT_DIFF.csv`**. The trade is priced per word, so this is a product judgement, not
a measurement — which makes it yours and not mine.

| Option | You get | You pay |
|---|---|---|
| `require_passive_up = 2s-only` | A passive wrist that is actually raised, so the mirrored handshape lands somewhere real | 51 words regress, **28 fall into tier C**, median valid candidates collapse 74 → 6 |
| `require_passive_up = off` | Coverage holds on all 250 | Some 2s signs render a correct-looking hand at a wrong wrist |

Both are defensible. The 28 words that would fall to tier C are named in the CSV — read them and
decide whether any are load-bearing for the demo.

### ☐ 9. Kezar / Gallaudet — put a date on it · 2026-09-07

The commercial-terms email went out 2026-08-29/30. No reply.

`LICENCE_REQUESTS.md` argues correctly that bundling a licence request with an unpaid-review request
risks losing both answers — but **an indefinite hold means never asking.** So:

> **If there is no reply by 2026-09-07**, the licence thread is cold, the bundling risk is gone, and
> the Deaf-review note goes out on its own merits.

That lab builds sign-language AI for Deaf students. A clinical accessibility application is a
natural fit, and the ask stands on its own.

---

## ONGOING — start now, finishes later

### ☐ 10. Find a route to a fluent reviewer

**This is the highest-leverage single action in the whole project and it is not on anyone's task
list.** Three blockers that have been tracked separately for weeks are largely one unmet need:

- the fluent reviewer that **5 items / 67 rows** are waiting on,
- the signers for a **licence-clean clinical corpus** (101 concepts — see the plan),
- the **Lebanese Sign Language moat** this company has already named as its differentiator.

One relationship with a Deaf community organisation supplies all three.

**Two things that make this easier than it has looked:**

1. **It is unstaffed, not waiting.** You said plainly that we do not have a reviewer, so the task is
   *route-finding*, not review. It needs an owner and a date, not a standing entry on a blocked
   list.
2. **For most of the backlog, fluency is the requirement — not Deaf-native status.** The handshape
   and handedness questions are geometry. A certified interpreter or a university ASL program can
   adjudicate them. That widens the search considerably.

What is waiting: 16 gloss rows (`docs/CLINICAL_GLOSS_REVIEW.csv`) · 22 handshape rows
(`docs/HANDSHAPE_REVIEW.csv` + contact sheet) · 29 handedness disagreements
(`docs/HANDEDNESS_CROSSCHECK.csv`) · `asl_2a_base_placement.json`, which is **blocking Ghozlan** ·
the 250 exemplars.

### ☐ 11. Get the designer's answers to §18 — even though they are hired

The hire is done, but **§18's eight questions are still worth collecting**, because three of them
change what happens next rather than whether to hire:

- **Q4 — the forearm twist.** Weights, or a twist bone? If a twist bone, **we must know at P1-M1**,
  because the runtime has to drive it explicitly and an undocumented extra bone sits at bind
  rotation forever. This is the one answer with a hard deadline.
- **Q5 — base mesh and its licence.** A base is fine, but many bases fail §6.3, and a base that
  cannot be redistributed commercially inside an application is unusable to us however good it
  looks. Cheaper to learn at P1-M1 than at P1-M4.
- **Q2 — naming and auto-riggers.** If they use Rigify or an auto-rigger, producing our exact 55
  names is extra work they need to have budgeted (see §6.1's three naming traps).

Q4 and Q5 are also the fastest read on whether they have actually rigged hands for position-driven
IK before — which §18 Q3 asks directly, and which is worth knowing kindly and early rather than
discovering at P1-M3.

---

## DECISIONS ONLY YOU CAN MAKE

No deadline on these, but each gates something.

| Decision | Gates | Status |
|---|---|---|
| **Push the 8 unpushed commits?** | Nothing technical, but the work is only on your machine | Standing rule: I never push without asking. Asked 5 times, still open. |
| **Who owns the runtime** (task 2B) | 3 acceptance tests, the designer's test harness, and whether the rig can be driven at all | **New today.** Needed before P1-M2, not P1-M1. |
| The 2s gate (task 8) | The avatar's final quality on 28 words | Priced, waiting on you |
| **Record our own clinical corpus?** | Whether the medical track ever ships | Gated on task 5 **and** on my clips-per-sign curve. Do not decide before both. |
| **The blockout price conversation** (task 2A) | Possibly the designer's estimate | The brief's word "blockout" was ambiguous; v5 §5 resolves it and invites them to reprice. Our wording, our problem. |

---

## WAITING ON ME — nothing for you to do

Listed so you can track it. All of it is gated only on GPU time you already have, or on task 4.

| What | Cost | Gated on |
|---|---|---|
| **Clips-per-sign learning curve** — prices the recording session, decides weekend vs six months | ~70 min GPU | nothing |
| **Decimate A/B** — tests the mechanism behind the whole collision diagnosis | ~34 min GPU | nothing |
| **Public fingerspelling baseline** — the clean track's first real model | days | your task 4 + 6 |
| **Golden-fixture parity harness** — must exist before any web inference code | ~1 day | nothing |
| ~~**B/5 template separation**~~ — **CLOSED 2026-09-01.** Measured from the templates directly, no raw takes needed: `B` fan 18.7° / tip gap 0.129 vs `5` fan 31.4° / tip gap 0.192 — **they separate, by 48%.** Still the 2nd-closest of 21 pairs, so worth the designer's care, but not the defect I flagged. Corrected in the brief §10. | done | — |

---

## Why this order

1. **Unbounded downside first.** Task 1 is the only item that can cost money rather than time.
2. **Then whoever is blocked on you.** Ghozlan is actively building against stale data (task 2), and
   a hire has the longest lead time on the board (task 3). Both are cheap for you and expensive to
   delay.
3. **Then the cheap thing that unblocks the most of my work.** Task 4 is five minutes.
4. **Then the thing that could change the plan.** Task 5 is 30 minutes and could dissolve the
   licence wall entirely — which is why it sits above the tasks that merely make progress.
5. **Then progress.** 6, 7, 8.
6. **Long-lead items run in parallel**, they do not queue: 9, 10, 11.

**Deliberately not on this list:** further accuracy work on the 250-word model · the
prototype-gallery leave-classes-out test (queued behind fingerspelling) · any re-extract at more
than 75 points — the confusion matrix refuted the landmark hypothesis, and the only face-location
confusion in the entire matrix sits at n=2.
