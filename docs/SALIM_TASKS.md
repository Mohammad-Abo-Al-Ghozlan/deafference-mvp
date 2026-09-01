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

## NOW — today. All four together are under an hour of your time.

### ☐ 1. Rotate the three burned credentials · ~20 min

**AWS access key · Gemini keys · Supabase DB password.** All three were pasted in chat weeks ago and
none has been rotated.

This is first for one reason: it is **the only item on the whole board with unbounded downside.**
Leaked AWS keys get scraped and used, and the cost is not capped by anything. Everything else on
this list costs time if it slips; this one can cost money.

- Rotate in each provider's console.
- New values go **only** into the gitignored `.env`. Never into `.env.example`, never into a
  notebook cell, never into chat.
- Confirm `.env` is still gitignored before you finish.

### ☐ 2. Rebuild the avatar handoff and send it to Ghozlan · ~15 min

**He is blocked right now** and has been since Aug 26 — he is building his renderer against 35 word
files that no longer exist in that form, plus two lexicons that have changed. Every day this waits
is a day of his work aimed at superseded data.

Rebuild first (see the correction above):

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

Also worth telling him, since it affects his planning: **we are hiring a 3D artist for the avatar
skeleton** (task 3), and the tip-node defect found in his current rig is requirement #1 in that
brief. That is not a criticism of his work — the mechanism was invisible to every check either of us
had.

### ☐ 3. Send the skeleton brief to 3D artist candidates · ~15 min

**Longest lead time on the board.** A hire takes days to weeks to land, so starting it today costs
nothing and starting it in a week costs a week.

- File: **[`docs/AVATAR_SKELETON_BRIEF.md`](AVATAR_SKELETON_BRIEF.md)**
- **§0 is a paste-in covering message.** Delete §0 from the file before attaching it.
- Point them at §4, §6.2 and §6.3 if they are short on time.
- Ask for answers to the eight questions in §18, with an estimate.

**Send it to two or three candidates, not one.** §18 question 7 asks whether they also want phase 2
(the character design), which tells you whether to plan for one artist or two — and comparing two
answers to §18 question 4 (the forearm twist) is the fastest read on who actually knows hand
rigging.

You do **not** need the file bundle (§11) ready to send the brief. That only matters once someone is
hired, and task 2 rebuilds most of it anyway.

### ☐ 4. Fingerspelling `--report` on one real shard · ~5 min

Unblocks **the only licence-clean track that can carry a clinical vocabulary.** Five minutes of your
time buys days of mine.

On Kaggle, with the competition attached and `subset_landmarks.py` uploaded:

```python
!python subset_landmarks.py --base /kaggle/input/asl-fingerspelling --report --limit-files 1
```

It writes nothing. **Paste me the output.** The number that matters is **sequences with a gap > 10
frames** — it settles the CTC design before a line of it is written.

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

### ☐ 11. Decide the designer hire — after quotes come back

Depends on task 3. When the answers to §18 arrive, the two that tell you most:

- **Q4 — the forearm twist.** Weights or a twist bone? Anyone who answers this confidently knows
  hand rigging. Anyone who has not thought about it will discover it at P1-M2.
- **Q5 — base mesh and its licence.** A base is fine, but many bases fail §6.3, and a base that
  cannot be redistributed commercially is unusable to us however good it looks.

---

## DECISIONS ONLY YOU CAN MAKE

No deadline on these, but each gates something.

| Decision | Gates | Status |
|---|---|---|
| **Push the 7 unpushed commits?** | Nothing technical, but the work is only on your machine | Standing rule: I never push without asking. Asked 4 times, still open. |
| The 2s gate (task 8) | The avatar's final quality on 28 words | Priced, waiting on you |
| The designer hire (task 11) | The whole avatar track | Waiting on quotes |
| **Record our own clinical corpus?** | Whether the medical track ever ships | Gated on task 5 **and** on my clips-per-sign curve. Do not decide before both. |

---

## WAITING ON ME — nothing for you to do

Listed so you can track it. All of it is gated only on GPU time you already have, or on task 4.

| What | Cost | Gated on |
|---|---|---|
| **Clips-per-sign learning curve** — prices the recording session, decides weekend vs six months | ~70 min GPU | nothing |
| **Decimate A/B** — tests the mechanism behind the whole collision diagnosis | ~34 min GPU | nothing |
| **Public fingerspelling baseline** — the clean track's first real model | days | your task 4 + 6 |
| **Golden-fixture parity harness** — must exist before any web inference code | ~1 day | nothing |
| **B/5 template separation** — closes the open handshape measurement | hours | you pointing me at the raw takes |

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
