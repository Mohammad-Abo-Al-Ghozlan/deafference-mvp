# What's on Salim — the ordered task list

**Written 2026-09-01 · updated 2026-09-03.** Derived from the cross-track plan of 2026-08-31.

> **Closed since the last revision:** the 16 unpushed commits are **pushed**
> (`97dbc64..1d0a59d` → `origin/Mhmd-Salim`, `main` untouched) · the avatar brief is one
> self-contained file at v6.1, **sent** · the hire's discipline is corrected throughout — **he is a
> 3D avatar animator, not a character artist**, which opened task 2C · **task 5 is done, I read the
> ASL Citizen licence** (§5 below — the wall stands, but it is a *different* wall) · **task 8 has a
> recommendation** with the numbers behind it.

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

### ✅ 2A. Send `AVATAR_BRIEF_COMPLETE.md` — **DONE 2026-09-03**

v6.1 sent, with the reply to his two questions. What follows is kept for the record.

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

### ☐ 2B. Who owns the runtime — **and there is a prerequisite you can do in one minute**

> ## ⚠️ Measured 2026-09-03: the player source is not in this repository
>
> I went looking for it so I could tell you what owning it would cost. It is not here:
>
> ```
> tracked .js / .ts / .jsx / .tsx / .html / .vue files      0
> demo/                                                     6 rendered .mp4 files, no code
> _send/                                                    a staging copy of the handoff data
> package.json                                              ABSENT
> package-lock.json                                         present (413 KB)
> node_modules/                                             present, 510 packages, 1.1 GB
> ```
>
> A lock file and a `node_modules` with **no manifest** is an orphaned install, not a project. Every
> bone name in `§6.2` was read out of *Ghozlan's* player, which lives on his machine or his own
> branch — **we have its outputs and none of its source.**
>
> **So the real question is not "who should own the runtime". It is "do we have the code at all".**
> And that changes the price of every option below by a lot, so answer it first:
>
> > Hi — one small thing. Can you push the avatar player / retargeter source to a branch, or zip it
> > over? Whatever state it is in is fine, including broken. We are not asking you to work on it —
> > we just need the code to exist somewhere other than your machine.
>
> One message. Do it before deciding anything else on this page.

**Once you know whether the code exists, the options are:**

| Option | Cost | When it is right |
|---|---|---|
| **Ghozlan returns for the runtime only** | Lowest — he wrote it | If the source comes back and he is willing. He is off the *avatar*, which is not the same as off the *runtime*. |
| **You own it** | Your time, and your board is already full | You are the sole frontend dev, and it is Three.js + JS. Realistic only if something else comes off the board. |
| **I write it** | GPU/context time, no money | Strongest if the source does **not** come back. I already hold the whole contract — landmark layout, bone names, the depth equation, and failure modes #7–#10 in §6.12 are explicitly mine. A rewrite from spec is tractable; maintaining code I have never seen is not. |
| **Hire a web/3D dev** | Money + lead time | Only if you want it owned by a person rather than a session, long-term. |
| ~~The animator owns it~~ | — | **No.** Wrong craft, and brief §11 and §15 both promise him the runtime is on our side. Do not move this onto him. |

**It needs an answer before P1-M2 — not before P1-M1.**

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

### ☐ 2C. Ask one question: is he a rigger, or an animator? · ~1 min to ask

**New 2026-09-03, and it is the highest-value question on this page** because it is cheap to ask and
expensive to discover late.

He does **3D avatar animation.** Phase 1 contains **no animation at all** — it is a skeleton, a hand
rig, weights, a blockout body, and seven static hand poses. §12 explicitly forbids shipping animation
clips. So the deliverable and his stated craft are adjacent, not the same.

**This is very possibly fine.** Avatar work is rigging-heavy — VRM, VTuber and metaverse avatars live
or die on the rig — so plenty of people who describe themselves as avatar animators rig to a high
standard. His two questions were also *good* questions: the four-nodes one was the correct thing to
push back on given our wording, and it means he is reading properly rather than nodding along.

**But do not infer it.** Ask directly, and make both honest answers safe:

> Quick one so we schedule this right: how much of your work is **rigging and skinning** versus
> animating? Phase 1 is entirely the former — you never key a frame. If rigging is not the part you
> are strongest at, that is completely fine and much better said now: we can stretch the P1-M1 and
> P1-M2 reviews, or you can bring in a rigger for phase 1 and stay on the parts you are best at.
> No wrong answer, and it does not change whether we work together.

§18 Q3 now asks this in the brief, so sending v6.1 (task 2A) asks it for you. **Do both.**

If the answer is "mostly animation": the schedule changes, not the plan. Move the P1-M1 gate earlier
and make it a working session rather than a script run — the whole point of P1-M1 is that it is a
`.glb` and four scripted tests, which is the cheapest possible place to find a rigging gap.

### ☐ 2D. Confirm §16 is actually agreed · ~2 min, or a conversation

I have flagged this three times and it has never landed, so it is now a task rather than a note.

**Brief §16 is a checklist of commercial terms with no figures in it** — I cannot invent them. If you
settled these when you hired him, this takes ten seconds to tick off and you can ignore the rest.

If you did **not**, these are the ones that cause arguments later, in order of how much:

| | Why it bites |
|---|---|
| **Fee, and how it splits across the four P1 milestones** | Milestone-linked payment is what makes §15's "four cheap gates" work. A single end-payment turns every gate into a negotiation. |
| **What happens if a gate fails and needs rework** | P1-M1 is a pass/fail script. Agree now whether a re-submit is included. |
| **Revision rounds per milestone**, and what counts as a new request | The "blockout" ambiguity is exactly the kind of thing that becomes a scope fight. |
| **IP: full commercial rights to rig + source, right to modify, right to have phase 2 done by someone else** | The last clause matters most and is the one people object to. Better a "no" now. |
| **Third-party assets and their licences** | A base rig that cannot be redistributed commercially inside an app is unusable however good it looks. This is the same class of problem as the Sem-Lex licence wall — do not repeat it on the avatar. |

The last row is the one I would not skip. Everything else is money; that one is whether the work is
usable at all.

### ☐ 4. Fingerspelling `--report` on one real shard · ~15 min, mostly waiting

Unblocks **the only licence-clean track that can carry a clinical vocabulary.** Fifteen minutes of
your time buys days of mine.

Fingerspelling matters more than "26 letters" sounds. Twenty-six letters is the only thing that makes
**vocabulary size stop mattering** — patient names, street names, drug names, dosages. No lexicon
will ever contain them, the current system has zero single-letter entries, and in a clinic that is
not a nice-to-have.

**This is a CPU job.** Do not turn the GPU on; it does nothing here and burns your 30-hour budget.

---

#### Step 1 - accept the competition rules *(one time only)*

| | |
|---|---|
| **Exact title** | **Google - American Sign Language Fingerspelling Recognition** |
| **Direct link** | `https://www.kaggle.com/competitions/asl-fingerspelling` |
| **Slug** | `asl-fingerspelling` - which is why the script's `--base` defaults to `/kaggle/input/asl-fingerspelling` |

1. Open the link above (faster than searching - there are several similarly named ASL competitions
   on Kaggle, including the *other* Google one, **isolated-sign-language-recognition**, which is
   GISLR and is where the 250-word model came from. **You want the fingerspelling one.**)
2. **Rules** tab -> **I Understand and Accept**.

Competition data stays available after a competition closes; accepting the rules is what unlocks it.
**No email, no negotiation, no licence problem** - this is the clean track. The data is landmarks
only, never video: >3 million fingerspelled characters from 100+ Deaf signers, captured on phone
selfie cameras, already run through MediaPipe.

#### Step 2 - put `subset_landmarks.py` where Kaggle can see it

> **This dataset does not exist yet. You are creating it here.** Wherever the rest of this file
> writes `deafference-fs-code`, that is **a name you choose in this step**, not something to go and
> find. Nothing on Kaggle has it until you make it.
>
> A Kaggle notebook cannot read a file off your laptop. Attaching a dataset is the only way to get
> your own code into a session, which is why this step exists at all.

1. Kaggle -> **Datasets** -> **New Dataset**.
2. Drag **only** `training/fingerspelling/subset_landmarks.py`.
3. Title it `deafference-fs-code`. **Visibility: Private.** Create.

> ### The path is built from the SLUG, not the title
>
> Kaggle lower-cases your title and replaces spaces with hyphens to make a **slug**, and the input
> path is `/kaggle/input/<slug>/`. So:
>
> ```
> title "deafference-fs-code"   ->  /kaggle/input/deafference-fs-code/subset_landmarks.py
> title "Deafference FS Code"   ->  /kaggle/input/deafference-fs-code/subset_landmarks.py
> title "FS code v2"            ->  /kaggle/input/fs-code-v2/subset_landmarks.py       <- different!
> ```
>
> **Type the title exactly as `deafference-fs-code`** and every command in tasks 4 and 6 works
> unchanged. If you name it anything else, step 4's path-explorer will print the real path - use
> that instead.

> WARNING: **Drag the single file, not the folder and never the repo root.** The repo contains
> `.env`, and a public Kaggle dataset would publish it.

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

> ### WARNING - correction 2026-09-03: the headline question is already answered
>
> I called the >10-frame gap count "the single number that decides the model design". It is already
> on record. `subset_landmarks.py`'s own docstring states it, and `SESSION_HANDOFF.md` around line
> 1209 carries the same family of figures:
>
> ```
> 55% of gaps are <=3 frames  ...  but hold only 12.4% of lost frames
> ~64% of lost frames sit in gaps >10 frames
> ```
>
> **Long gaps dominate. So the architecture decision is made: absence is a first-class input** - the
> model learns "no hand here" rather than being fed an invented one. Interpolation is not defensible
> on this corpus, and filling those gaps would fabricate handshapes, i.e. invent letters.
>
> **What task 4 is still worth** is smaller and honest: it verifies *our own code path* on real data
> (step 5's `--selftest` covers most of that), and it gives the per-sequence distribution rather than
> pooled percentages. Useful, not blocking.
>
> **The practical consequence is good news: run 4 and 6 back-to-back in one session.** There is no
> longer a decision to make in between, so the old warning here no longer applies.

**Then task 6** subsets four shards for real - and see its own section for which Kaggle run mode to
use, because it differs from task 4.

---

## THIS WEEK

### ✅ 5. Read the ASL Citizen licence — **DONE 2026-09-03, I read it**

**The verdict: the wall stands. But it is a different wall, and the difference is worth having.**

Quoted from Microsoft Research's dataset licence page:

| Question | Answer | The words |
|---|---|---|
| Commercial use? | **No** | rights "to use the Materials solely for **non-commercial, non-revenue generating**, research purposes" |
| Share-alike / copyleft? | **NO — and this is the finding** | No such clause anywhere in the licence. |
| Redistribute the data? | **No** | "you may not distribute the data or your modifications to the data"; "you will not … share, publish, distribute or lend the Materials" |
| Publish results? | **Yes, conditionally** | "You may publish (or present papers or articles) on your results from using the Materials provided that no material or substantial portion of the Materials is included" |
| Named commercial contact? | **Not on the licence page** | `MEDICAL_MVP_PLAN.md` cites `ASL_Citizen@microsoft.com`; that came from the download page or the paper, not the licence, so treat it as a plausible route rather than a stated one. |

### What this changes, and what it does not

**It does not dissolve the licence wall.** "Non-revenue generating" is *stricter* than plain
non-commercial — it plausibly rules out ad-supported and freemium too, not just paid. A commercial
Deafference cannot be built on ASL Citizen any more than on Sem-Lex.

**But the two walls are shaped differently, and that matters:**

```
Sem-Lex  (CC BY-NC-SA)   NC blocks commercial  +  SA arguably infects the trained weights,
                                                  which forecloses even a FREE release
ASL Citizen  (MSR)       NC blocks commercial  +  NO share-alike at all
```

So **if the product were ever a free, non-revenue accessibility tool, ASL Citizen is the cleaner
base** — the share-alike problem that made me say a free Sem-Lex release was also foreclosed simply
does not exist here. That is a genuinely new option on the board, and it was not visible before
reading the text.

Two things carry over unchanged: **redistribution is forbidden**, so the private-Kaggle-dataset rule
applies to ASL Citizen exactly as it does to Sem-Lex; and **52 signers against Sem-Lex's 41** is
still the reason to want it, since signer count is one of the very few dataset properties this
project has *proved* matters.

### The one thing left, and it is not reading

**Email Microsoft and ask for commercial terms.** The licence does not offer them, which is not the
same as refusing them — an accessibility application for Deaf patients is exactly the ask a research
group is most likely to entertain. Route: `ASL_Citizen@microsoft.com`, unverified but plausible;
otherwise the contact on the project page or the paper. **Do not guess an address.**

**And the corpus decision is now unblocked.** "Record our own clinical corpus?" was gated on this
task *and* on my clips-per-sign curve. This half is answered — both public options are non-commercial
— so it now waits only on my curve, which prices the recording session.

### ☐ 6. Subset four fingerspelling shards · ~20 min

Four shards is baseline-sized - enough to train something real, small enough to iterate.

> ## The one thing that differs from task 4: **run mode**
>
> | | task 4 (`--report`) | **task 6 (`--out`)** |
> |---|---|---|
> | writes files? | **no** - measures only | **yes** - that is the entire point |
> | run as | **Interactive**, read the output | **Save & Run All (Commit)** |
> | why | you only need stdout | `/kaggle/working` is captured as the notebook's **Output** only on a saved version. An interactive session's files **die with the session.** |
>
> **This is the mistake to avoid:** running it interactively, seeing "wrote fs75.npz", closing the
> tab, and finding nothing. Interactive `/kaggle/working` is scratch space.

#### Setup - same two inputs as task 4

The same notebook is fine. Right panel -> **Add Input**: the **competition**
(`asl-fingerspelling`), and your `deafference-fs-code` dataset - **the one you created in task 4
step 2.** It does not exist before that; if you have not done task 4 yet, start there.

Then:

| Setting | Value | Why |
|---|---|---|
| **Accelerator** | **None (CPU)** | Pure parquet I/O. A GPU does nothing here and burns your 30-hour budget. |
| **Internet** | **Off** | Not needed, and off starts faster. |
| **Persistence** | irrelevant on a commit run | The Output is captured either way. |

#### Step 1 - smoke-test the *write* path in seconds

`--report` never exercised writing at all, so prove it separately before spending twenty minutes:

```python
!cp /kaggle/input/deafference-fs-code/subset_landmarks.py .
!python subset_landmarks.py --selftest
!python subset_landmarks.py --base YOUR_BASE_FROM_TASK_4 \
    --out /kaggle/working/smoke --limit-files 1 --limit-seq 20
!ls -la /kaggle/working/smoke
```

You want `fs75.npz` **and** `gap_stats.json` present and non-zero. `--limit-seq 20` makes this take
seconds instead of minutes.

#### Step 2 - the real run

```python
!rm -rf /kaggle/working/smoke
!python subset_landmarks.py --base YOUR_BASE_FROM_TASK_4 \
    --out /kaggle/working/fs75 --limit-files 4
!du -sh /kaggle/working/fs75 && ls -la /kaggle/working/fs75
```

**Check the printed size.** Kaggle's output cap is **20 GB**. Four shards subsetted to 75 points
should land around **1-2 GB** - the whole point of the subset is that 225 of 1,631 columns is 13.8%
of the I/O. If it comes out anywhere near 20 GB, stop and send me the number; something is wrong.

#### Step 3 - persist it

**Save Version** -> and there are two valid choices:

- **Save & Run All (Commit)** - re-runs the notebook top to bottom, headless, and captures
  `/kaggle/working` as the Output. **This is the one I would use**: it is reproducible, and it puts
  the `--selftest` result in the permanent record right next to the data it produced. CPU commits get
  12 hours; this needs minutes. You can close the tab - it finishes without you.
- **Quick Save** - snapshots the notebook *and the files already sitting in* `/kaggle/working` from
  your interactive run, without re-running. Faster, and it does keep the output. Fine if you have
  already run step 2 and only want the file kept.

Either way, when it finishes: notebook -> **Output** tab. The files are downloadable there, and - the
part that actually matters - **that notebook can now be added as an Input to the next notebook**,
which is how the training run reads `fs75.npz` without re-subsetting.

**Do not** create a dataset from the notebook output onto an existing dataset. New name every time.

#### What to send me

`gap_stats.json`, plus the stdout from step 2. That is the per-sequence gap structure, and it is what
the CTC model's absence handling gets designed against.

### ☐ 7. Re-upload `ensemble_eval.py` to the Kaggle code dataset · ~5 min

**This one is not a notebook at all** - it is a Datasets upload, so there is no Interactive vs
Save & Run All question. No code runs.

The Kaggle copy predates commit `1c9a2fa` - *"the confusion CSV was unreadable without the vocab -
carry class_names in the report"*. Without it the next confusion CSV cannot be read without guessing
label order, and guessing it wrong is exactly the bug that nearly made me hand you confidently
mislabelled output.

#### The steps

1. Kaggle -> **Datasets** -> **New Dataset**.
2. Drag **one file**: `training/ensemble_eval.py`.
3. **Title:** date- or commit-stamped so it is unambiguous later - e.g.
   `deafference-eval-code-20260903` or `deafference-eval-code-1c9a2fa`.
4. **Visibility: Private.** Create.
5. In whichever notebook consumes it: **remove the old input, add the new one.** This is the step
   people forget - a stale input silently keeps running the old code.

#### The three rules, and why each one exists

> - **Drag the single file. Never the folder, never the repo root.** The repo contains `.env`, and a
>   public Kaggle dataset would publish it.
> - **A brand-new dataset name every time. Never overwrite, and never create a dataset from notebook
>   output onto an existing dataset.** An overwritten dataset silently changes what every earlier
>   notebook run was using, which makes an old result impossible to reproduce or trust.
> - **Private.** Habit, and here it costs nothing.

#### The check that this actually worked

Old and new are impossible to tell apart by eye. In the notebook, after switching the input:

```python
!grep -c class_names /kaggle/input/YOUR-NEW-DATASET-SLUG/ensemble_eval.py
```

**Non-zero means you have the new one.** Zero means the old file is still attached - go back to
step 5.

### ☐ 8. Decide the 2s gate — **I have a recommendation: `off`, and it is not close**

You asked me to make this one. I measured all 250 rows of `docs/RESELECT_DIFF.csv` rather than the
summary, and the picture is clearer than the task originally described.

**First, the thing that was not obvious: classes 1 and 2a are IDENTICAL on both sides.**

```
class    n   median cov (off)   median cov (2s-only)   regressed   improved
1      163       0.901               0.901                0           0
2a      35       0.829               0.829                0           0
2s      52       0.877               0.468               51           0
```

Median valid candidates for 2a: **162 → 162, unchanged.** So the 2a win is already baked into *both*
options — **`off` does not cost you the 2a gains.** I had assumed it might; it does not. The decision
is purely about the 52 class-2s words and nothing else.

**And on those 52, one option loses on every measured axis:**

| | `off` | `2s-only` |
|---|---|---|
| words in tier C | **0** | **28** |
| 2s median coverage | **0.877** | 0.468 |
| 2s median valid candidates | **74** | **6** |
| words regressed / improved | — | **51 / 0** |

**51 of 52 words get worse and not one gets better.** That is not a fix with a price; it is a trade
where only one side has anything on it.

### Three reasons I would not pay it

**1. The candidate collapse is a hidden loss the tiers do not show.** 74 → 6 median means even the
six words that *stay* in tier A are now selected from a handful of takes instead of seventy. `drop`
is down to **1 valid candidate** — that is not selection, it is whatever survived. Quality loss on
the survivors is real and invisible in the tier column.

**2. `owie` falls A → C.** In a child-language corpus `owie` means *hurt*. For a clinical demo that
is arguably the single most load-bearing word in the entire 250, and `cry` goes with it. Also on the
casualty list: `hate`, `quiet`, `loud`, `finish`, `can`, `open`, `close`, `many`, `same`, `person`,
`room`, `bath`, `book`.

**3. The problem it fixes is smaller on 2s than on 2a.** 2s words are *symmetric* — the passive hand
is a **mirror copy of the dominant hand**, not a shape invented from the seven-template library. The
wrist-placement error that made the 2a fix worth having (a median 1.56 shoulder-widths off) is a much
weaker effect when the hand you are placing is derived from a hand whose position you measured.

### The honest caveat

**What `2s-only` buys is not in the CSV.** It buys a passive wrist that is genuinely raised, and
"some 2s signs render a correct-looking hand at a wrong wrist" is a *visual* defect I cannot measure
from here. If you look at four of the 52 in the player and the wrong-wrist artefact is glaring, that
outweighs my table.

**So: 15 minutes, not 30.** Open the player, watch `store`, `book`, `cry` and `owie` with the gate
`off`. If they read fine, set `off` and close this. That is what I would do.

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

### ☐ 11. Get his answers to §18 — even though he is hired

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
| ~~**Push the unpushed commits?**~~ | — | ✅ **CLOSED 2026-09-03.** 16 commits pushed to `origin/Mhmd-Salim`. |
| **Who owns the runtime** (task 2B) | 3 acceptance tests, the animator's test harness, and whether the rig can be driven at all | **Prerequisite found 2026-09-03: the player source is not in this repo.** Ask Ghozlan for it first — one message — then decide. |
| **Is he a rigger?** (task 2C) | Whether phase 1's deliverable matches his craft at all | **New 2026-09-03.** He does avatar *animation*; phase 1 is 100% rigging and skinning, with animation explicitly forbidden. Not a problem yet — but the answer changes how we schedule and review. |
| The 2s gate (task 8) | The avatar's final quality on 28 words | **Recommendation ready: `off`.** 51 of 52 words regress, zero improve, and classes 1 and 2a are unaffected either way. 15 min of looking, then a call. |
| **Record our own clinical corpus?** | Whether the medical track ever ships | **Half-unblocked 2026-09-03.** Task 5 is answered: ASL Citizen is non-commercial too, so no public corpus permits a paid product. Now waits only on my clips-per-sign curve, which prices the session. |
| **The blockout price conversation** (task 2A) | Possibly his estimate | The brief's word "blockout" was ambiguous; §5 resolves it and invites him to reprice. Our wording, our problem. |
| **A free, non-revenue release?** | Whether ASL Citizen is usable at all | **New 2026-09-03.** ASL Citizen has **no share-alike**, unlike Sem-Lex — so a free non-revenue tool is licence-clean on it where it was arguably not on Sem-Lex. Only worth deciding if the commercial route is genuinely closed. |

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
