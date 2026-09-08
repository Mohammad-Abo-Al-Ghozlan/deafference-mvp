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

## ✅ RESOLVED 2026-09-04 — the disk was full; you freed ~2 GB and the rest unpacked

```
C:  0.23 GB free of 237.16 GB          <- the only drive
Downloads   22.22 GB                   <- the reclaim target
OneDrive    18.33 GB
```

At 0.23 GB free I could extract only 19.5 MB of the 704 MB `results.zip` — the four
SavedModels and the small reports, which happened to be exactly what stage 5 needed.
Stage 6 was blocked outright: it needs `by_word/` (380 MB) and there was nowhere to put it.

**You freed ~2 GB on 2026-09-04**, I extracted the remaining 415 MB, and stage 6 is now
built (below). `results.zip` is gitignored and can be deleted once you are happy — it
still holds `semlex_medical_landmarks_v2.npz` (384 MB), which nothing currently needs
but which is the source for a re-extract.


---

## ❓ "three signs in a row don't get detected" — measured, 2026-09-04

Not a bug in the model. **The segmenter never sees a boundary.** I replayed three real
exemplars (`pain head help`) through live_demo's exact commit rules, no camera:

```
A. FLUID, no gap  (signing normally)   ->  2 commits for 3 signs   ❌ signs lost
                                            both fired via `maxlen` at exactly 90 frames
B. with a 0.5 s HELD PAUSE between     ->  3 commits for 3 signs   ✅
C. with HANDS DOWN 0.5 s between       ->  3 commits for 3 signs   ✅

longest run of stillness inside a fluid utterance :  10 frames
frames required to end a sign (still_fr)          :  12
```

**It misses the boundary by two frames.** Median hand motion inside an utterance is 0.0158
against a threshold of 0.00467 — 3.4× above it — so `still_count` never reaches 12, no
boundary fires, the segment grows to the 3.0 s ceiling and force-commits a chunk spanning
about one and a half signs. You do not get three wrong words; you get two arbitrary chunks.

### Three causes, in the order they bite

**1. You have to give it a pause.** ~0.5 s held still, or drop your hands. Then it is 3/3.
Do **not** lower `STILL_SEC` to compensate: 10-frame quiet spells occur *inside* single
signs, so a threshold below 12 would start cutting signs in half. The current value is 2
frames above the noise floor — tight, but correct. The gap is the fix, not the threshold.

**2. My safety gate holds 10 of the 55 words** — `no bad big more always pain blood breathe
sick help`. They never auto-commit; they wait for a tap on 1-5. In `topic_medical_symptom`
that is **9 of 18 words**. If your three signs included any of them they were *held*, not
missed — the console prints `[safety] HELD '<word>'` and the video shows
`confirm '<word>' - tap 1-5`. That is deliberate (see `MEDICAL_SAFETY_GATES.md` §2), but it
is the most likely reason a clinical phrase feels unresponsive. Try a non-gated phrase such
as `water drink medicine` to separate this cause from the other two.

**3. It is an ISOLATED-sign classifier, and that is architectural.** Sem-Lex and GISLR are
both prompted isolated signs with dead air trimmed — neither contains co-articulated
signing. The transitions between signs in fluent ASL (movement epenthesis) were never in the
training data, so even with perfect segmentation those frames are out of distribution.
**Continuous ASL recognition is a different model** — CTC/seq2seq over a stream, which is
exactly what the fingerspelling track is building. Nothing tunable here reaches it.

So: sign-pause-sign-pause-sign works today; fluent signing does not, and will not until
there is a sequence model. That limit belongs in any demo you give.

---

## ✅ CLOSED 2026-09-03 — the medical sign→speech demo runs, with clinical safety gates

### ✅ Stage 5 — wired into `live_demo.py`. **Verified, not just written.**

```
python live_demo.py --medical --selftest      # passes: 123 outputs, 41 ms warm, 4-fold
python live_demo.py --medical                 # boots on the 55-word ship mask
```

`--medical` loads `artifacts_medical/savedmodel_fold{0..3}` — **test 0.8383, top-5 0.9512,
on 1,373 clips from 9 held-out signers.** That beats the 250-word model's 0.7755 on three
times as many unseen signers, so **this is now the better recogniser we have**, licence
aside.

Four label-shift traps found and closed on the way, each of which would have failed silently:

| what I found | why it mattered |
|---|---|
| `vocab_medical.json` has **128** words; the model has **123** classes | `words[i]` resolves fine for i<123 and *every label is wrong*. `--medical` now compares the vocabulary against the SavedModel's own output dim and refuses. Verified by pointing `--medical` at `artifacts_250` — it exits. |
| the committed `clinical_ship_vocab.json` was **v1 (124 classes)** and named `hurt` | v2 merged `hurt`→`pain`. The v1 list against v2 weights would have quietly become a 54-word mask. Replaced with v2; the diff is recorded inside the file. |
| the class order was nowhere on disk | It is `sorted(split_manifest.parquet['word'].unique())` — exactly `train.py:582`. Cross-checked: the two `<unnamed-class-NN>` entries resolve to indices 51 and 81, which are `how` and `sharp`, the two concepts `PROVENANCE.json` records as having no test clips. Frozen into `vocab_medical_123.json`. |
| `canonical_hand` was unknown | **`false` in all four folds** (`eval_all250_fold*.json`). `--medical --canonical` is now *refused*, not warned about — that pairing fails silently on left-dominant signers. |

**One thing I did NOT do:** invent gate thresholds. `L1_CONF`/`L2_CONF` are carried over
from the 250-word model and are **unmeasured at 123 classes**; `--medical` says so at
startup and names `measure_conf_gate.py`. Guessing one silently is how this project lost
three months.

**AI sentence-building is OFF for `--medical`**, unlike `--vocab250`. An LLM tidying
"me hungry" is harmless; an LLM rephrasing clinical glosses can change meaning. Opt in
with `--ai`.

### ✅ Stage 7 — safety gates, built from measurement. **Needs a human reviewer, not code.**

`safety_gates_medical.json` + **`docs/MEDICAL_SAFETY_GATES.md`** ← this is the document to
put in front of a Deaf signer or medical interpreter.

**The finding that matters:** the model ships `no` (0.909) and **cannot** ship `yes`
(0.714). It can render a refusal and cannot render a consent. **This build must not be used
to obtain or record consent** — it prints that at startup.

- **10 words never auto-commit** (`no bad big more always pain blood breathe sick help`) —
  held before the sentence and the speaker whatever the confidence, released by one tap.
  Note they are among the *most* accurate words: the gate is about consequence, not
  weakness.
- **16 clinically critical concepts cannot be expressed** — incl. `not` 0.647, `heart`
  0.333, `hot` 0.781 (*fever*), and `choke` which scored 1.000 **on a single clip**.
- **45 measured safety-crossing confusions**, 15 reachable from the 55. Worst two are real
  rates, not single-clip noise: **`hot`→`bad` 16% of the class** and **`ear`→`skin` 60%**.

⚠️ **The five risk categories in §5 of that doc are my judgement, not measurement.** It
lists five specific questions for the reviewer. The sharpest one: **`fever`, `nausea`,
`vomit`, `chest` and `stomach` were pruned before training** for too few clips — a clinical
tool without `fever` may not be a clinical tool.

### ✅ Stage 6 — the medical avatar handoff is BUILT. 55 signs, 7.5 MB.

Once you freed the disk I extracted the rest and ran the whole pipeline.
**`animation_handoff_medical/`** — 55 per-word motion files + `reference_pose.json`, same
`sign-animation/v1` contract as the 250-word handoff. Full write-up:
**[docs/MEDICAL_AVATAR_HANDOFF.md](MEDICAL_AVATAR_HANDOFF.md)**.

#### 🔑 The finding that changes the rig: the passive hand is REAL

The 250-word contract tells the animator, verbatim, that *"for every word not marked '1', the
passive hand's landmarks DO NOT EXIST in our corpus for any take"* — so he must synthesize it.
That is true of GISLR. **It is false of Sem-Lex.**

```
GISLR   (250-word)  2s+2a  87 words  passive hand present:  0.000  in every single word
Sem-Lex (clinical)  2s     18 words                        81.7%  of frames
Sem-Lex (clinical)  2a     12 words                        81.1%
```

The same code measures 0.000 on one corpus and 0.81 on the other, so it is the data, not the
measurement. **30 of 30 two-handed clinical exemplars carry a real passive hand.** Every file
now ships `synthesis.passiveHandRecorded` and tells him to branch on it — synthesizing over
recorded landmarks would throw away the best data in the file, and nothing would raise.

And it corroborates itself: the handedness labels come from ASL-LEX, the hand rates from
MediaPipe tracking. Class 1 sits at 4.1% both-hand frames, two-handed classes at 41.8% — a
**10× separation neither number was derived from.**

#### The handoff is also just *better* than the 250-word one

| | 250-word | clinical 55 |
|---|---|---|
| tier A (coverage ≥0.80) | 146/250 = 58% | **52/55 = 95%** |
| tier C | 45 | **0** |
| words with ≤2 valid takes | 20 | **0** |
| words under 0.53 s | 6 | **0** |

Studio-recorded prompted signing vs crowd-sourced phone video. It shows.

#### Two bugs found and fixed on the way

- **20 of 55 exemplars were LEFT-dominant** while the contract promises every file is
  right-dominant. Sem-Lex was extracted without `--canonical-hand` (matching
  `canonical_hand: false` in the training config), so 5 words shipped
  `dominantCoverage: 0.000` and 20 named the wrong hand — silently. `--canonicalize auto` is
  now the default and mirrors them **preserving the passive hand**. Coverage went to mean
  0.940, **exactly matching `build_sign_clips`' own independent number** — which is what says
  the fix is right rather than merely different.
- **The medical clips were being paired with the 250-word metadata**, so 15 words got another
  corpus's take counts and 40 got none. `--meta` now derives from `--clips`. 15/55 → 55/55.

#### The lexicon: ASL-LEX, not hand-written

`asl_handedness_medical.json` — 25 one-handed / 18 2s / 12 2a, of which **53 come from
ASL-LEX**, 1 from the 250-word lexicon (`eye`), 1 hand-labelled (`hand`). All 12 2a passive
handshapes resolve to **measured** templates, zero approximations.

**Free cross-check: 86% agreement (12 of 14) with your hand-written 250-word lexicon.** The
two disagreements are both real and both worth a reviewer:

| word | 250 said | ASL-LEX | tracking | reading |
|---|---|---|---|---|
| `sick` | `1` (med) | `2s`, 183 takes | 35% | ASL-LEX + tracking agree; the 250 row was already flagged uncertain |
| `morning` | `2a` (high) | `1`, 80 takes | **62% in the exemplar** | **unresolved — don't assume ASL-LEX wins** |

`morning` matters beyond itself: ASL-LEX appears to treat the **passive forearm as a body
location, not a second articulator** — the same phenomenon your 250-word audit found from the
other side. `day` (62%) and `blood` (48%) look identical. The avatar must still pose that
forearm whatever the sign is *called*, so these three are the first rows for a Deaf reviewer.

#### Still open on stage 6

- **Every clip is exactly 64 frames** — the medical tensors were time-resized at extraction, so
  every sign plays for 2.13 s. `semlex_metadata.csv` has a `duration` column in ms, so this is
  recoverable; it just isn't done.
- `hand` and `sit` can't be drawn by *synthesis* — but both have a recorded passive hand, so
  per the finding above it isn't blocking.
- The rig is still not delivered, and the runtime owner is still unknown (**task 2B**).

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

#### Step 4 - find the real paths *(do this before anything else)*

> ## MEASURED 2026-09-03: Kaggle mounts inputs NAMESPACED, not flat
>
> Every `/kaggle/input/<slug>/` path in this repo's older docs is wrong for a current session. The
> real layout, read off a live session:
>
> ```
> /kaggle/input/competitions/asl-fingerspelling/          <- competitions/<slug>/
>       character_to_prediction_index.json
>       supplemental_landmarks           53 shards
>       supplemental_metadata.csv
>       train.csv
>       train_landmarks                  68 shards        <- what --base must point ABOVE
>
> /kaggle/input/datasets/mohammedsalim1/deafference-fs-code/   <- datasets/<user>/<slug>/
>       subset_landmarks.py
> ```
>
> **Consequences:**
>
> - `subset_landmarks.py`'s `--base` default of `/kaggle/input/asl-fingerspelling` **will not
>   resolve.** Always pass `--base` explicitly. The script fails loudly rather than silently, which
>   is correct behaviour - `[err] not found: None - attach the competition or pass --base`.
> - A one-level glob finds nothing. **Search recursively**, as the cell below now does.
> - `FINISH_250.md` line 147 already had the datasets form
>   (`/kaggle/input/datasets/mohammedsalim1/asl250-weights`), so this is consistent, not new -
>   just never written down as a rule.
>
> **The rule: never hand-write a `/kaggle/input/...` path again. Detect it.**

Run this first:

```python
import glob, os, shutil

for a in sorted(glob.glob("/kaggle/input/*")):
    print(a)
    for b in sorted(glob.glob(a + "/*"))[:12]:
        print("   ", os.path.basename(b))
        for c in sorted(glob.glob(b + "/*"))[:12]:
            k = len(glob.glob(c + "/*")) if os.path.isdir(c) else ""
            print("        ", os.path.basename(c), ("(%s entries)" % k) if k != "" else "")

# recursive, so it works on either mount layout
hits   = glob.glob("/kaggle/input/**/train_landmarks", recursive=True)
script = glob.glob("/kaggle/input/**/subset_landmarks.py", recursive=True)
BASE   = os.path.dirname(hits[0]) if hits else None

print("\nBASE   =", BASE)
print("script =", script or "*** NOT FOUND - create + ATTACH the dataset, step 2 ***")
if script:
    shutil.copy(script[0], "/kaggle/working/subset_landmarks.py")
if BASE:
    print("shards =", len(glob.glob(BASE + "/train_landmarks/*.parquet")), "(expect 68)")
else:
    print("*** competition not attached: accept the rules first, THEN Add Input ***")
```

`BASE` is now a Python variable, so every later cell can use **`$BASE`** and there is no path to
hand-edit. Expect **68** parquet shards. Two failure modes and what they mean:

| symptom | cause |
|---|---|
| `script = NOT FOUND` | the dataset is not **attached**. Creating it is not attaching it - Add Input -> Datasets -> Your Datasets. |
| `BASE = None` | the competition is not attached. **If it does not appear in Add Input at all, you have not accepted the rules** (step 1) - it is invisible until you do. |

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

### ✅ 6. Subset four fingerspelling shards — **RUN 2026-09-03**

> ## The result, and it settles the architecture
>
> ```
> 4 shards -> 3,997 sequences, 635,755 frames, 547 MB     (68 shards total => ~9.3 GB, under the cap)
> --selftest                                              ALL CHECKS PASSED
>
> sequence length        median 146    p90 269    max 751      <- 5x spread: ragged/CTC is right
> dominant-hand present  mean 0.553  median 0.571  p10 0.149   <- confirms the 45% figure
> max interior gap       median  16    p90  52    max 270      <- ~0.53 s hole in a TYPICAL sequence
> sequences w/ gap >10f  64%
> dominant hand          R 3,286   L 711                       <- 17.8% LEFT-dominant
> ```
>
> **The median sequence has a half-second hole with no spelling hand.** In fingerspelling that is
> several letters. Interpolation is dead; **absence must be a first-class input.** No longer an open
> question.
>
> **17.8% left-dominant** is higher than expected and load-bearing: a model that assumes
> right-dominance discards one sequence in six. `--selftest` verified dominance detection works
> (`left-dominant sequence reads as L`), so the script already handles it.
>
> **`gap_stats.json` is richer than its name** — 3,997 records carrying `T`, `dominant`, `hand_rate`,
> `n_gaps`, `max_gap`, `median_gap`, `lead`, `trail`, `sequence_id`, **`participant`** and
> **`phrase_len`**. The last two are the prize: `participant` allows signer-disjoint splits, and
> `phrase_len` allows the **CTC feasibility check** — whether a sequence has enough *hand-present*
> frames to spell its own phrase. The first record already looks marginal: `T=127`,
> `hand_rate=0.165`, `phrase_len=11` — about 21 usable frames for 11 characters, under 2 frames per
> letter.

Four shards is baseline-sized - enough to train something real, small enough to iterate.

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

### ☐ 7. Upload `ensemble_eval.py` — **REOPENED 2026-09-03, my error**

> ## ✅ 2026-09-04 — task 7 now has a MEASURED payoff, not just tidiness
>
> I compared the copies of the scripts that actually ran on Kaggle (they came back inside
> `results.zip`) against this repo, stripping comments and docstrings so only real code
> counted:
>
> ```
> train.py                 IDENTICAL
> extract_landmarks.py     IDENTICAL
> npz_to_train_format.py   IDENTICAL
> select_ship_vocab.py     IDENTICAL
> test_semlex_adapter.py   IDENTICAL
> semlex_poses_to_75.py    IDENTICAL CODE  (only the docstring differs — the repo's is NEWER
>                                           and records the +0.0007 canonicalization A/B)
> ensemble_eval.py         CODE DIFFERS    <- the repo adds "class_names": list(words)
> ```
>
> **That one missing line is why `clinical_ship_vocab.json` came back naming
> `<unnamed-class-51>` and `<unnamed-class-81>`.** Without `class_names` in the report,
> `select_ship_vocab.py` cannot recover the label for a class that has no test clips, so
> `how` and `sharp` came back as placeholders — and I had to reconstruct the whole 123-class
> order by hand from `split_manifest.parquet` to be sure the model's labels were right.
>
> So the upload is not housekeeping. **It makes the next run self-describing** and removes a
> manual reconstruction step that is easy to get silently wrong. Everything else on Kaggle is
> already current, which is the good news.


I closed this on 2026-09-03 on the strength of *"task 7 done i create the dataset"*. **The dataset
that got created was `deafference-fs-code`, holding `subset_landmarks.py`** — that is **task 4
step 2**, for the fingerspelling subset. Confirmed from the screenshot: one file, `subset_landmarks.py`,
12.86 kB.

**`ensemble_eval.py` has not been uploaded.** Two datasets are needed and I put both sets of
instructions in front of you at once, which is what caused the mix-up:

| task | file to drag | dataset title | status |
|---|---|---|---|
| 4 step 2 | `training/fingerspelling/subset_landmarks.py` | `deafference-fs-code` | ✅ **done** — `mohammedsalim1/deafference-fs-code` |
| **7** | **`training/ensemble_eval.py`** | `deafference-eval-code-20260903` | ☐ **still to do** |

**This is not urgent and nothing is blocked on it.** Nothing is running an ensemble eval today; the
consumers are the decimate A/B and the clips-per-sign curve, both mine. Do it when convenient.

#### ✅ DONE 2026-09-08 — uploaded as `deafference-eval-code-1c9a2fa`

Kept for the record. The steps were:

1. Kaggle -> **Datasets** -> **New Dataset**.
2. Drag **one file**: `training/ensemble_eval.py`. *(Not `subset_landmarks.py` — that one is done.)*
3. **Visibility: Private.** Create.

**The title does not matter and no cell should depend on it.** I had specified
`deafference-eval-code-20260903`; Salim used **`deafference-eval-code-1c9a2fa`**, which is
better — it names the commit that made the file worth uploading rather than the day it went up,
so the dataset identifies *which version* it holds. Every cell here locates files by recursive
glob (`/kaggle/input/**/ensemble_eval.py`), so a rename breaks nothing.

#### Why it matters at all

The Kaggle copy predates commit `1c9a2fa` — *"the confusion CSV was unreadable without the vocab -
carry class_names in the report"*. Without it the next confusion CSV cannot be read without guessing
label order, and guessing it wrong is the bug that nearly made me hand you confidently mislabelled
output. The check, once it is up:

```python
# Glob, never a hardcoded dataset path — the name is yours to choose and Kaggle mounts
# inputs NAMESPACED, so a literal path breaks the moment the dataset is named anything else.
import glob
p = glob.glob('/kaggle/input/**/ensemble_eval.py', recursive=True)
print(p)
!grep -c class_names {p[0]}
```

**Non-zero = the fixed version.**

✅ **Uploaded 2026-09-08 as `deafference-eval-code-1c9a2fa`** — named for the commit rather than
the date, which is the better choice: it pins *which version* of the file is in the dataset, where
a date only records the day it went up. Nothing depends on the name, because every notebook cell
in these runbooks locates files by recursive glob. *(This snippet was the one exception and was
hardcoded to the old name — fixed above.)*

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
