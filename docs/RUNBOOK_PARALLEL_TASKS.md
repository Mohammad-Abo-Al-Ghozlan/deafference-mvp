# Runbook — the four tasks that need no GPU · 2026-09-04

Ordered by deadline, not by size. Total hands-on time ≈ 50 minutes; two of them are one
message each.

---

## 1. Task 2B — get the player source · **~5 minutes, do this first**

**Why first:** the avatar handoff is built (55 signs), the lexicon is derived, the data is
done — and **nobody can render any of it.** The player source is not in this repo. This is now
the binding constraint on the whole speech→sign track, and it is one message.

**Send to Ghozlan.** Copy-paste:

> Hi Mohammad — quick one. I'm handing the avatar work to the 3D animator we hired and I need
> to know where the sign-player code lives. The repo I have (`deafference-mvp`) is the AI
> pipeline only — it has `gloss_to_motion.py` and the per-word motion JSON it produces, but no
> player/renderer that consumes them.
>
> Three things:
> 1. Is there a player already written, and if so where is the source?
> 2. If there is, can you push it (or grant me access)?
> 3. If there isn't, say so plainly — I'll scope it as new work for the animator rather than
>    assume it exists.
>
> The handoff format is stable and documented (`SIGN_ANIMATION_CONTRACT.md`), so whoever owns
> the player has a fixed target. Thanks.

**Then tell me the answer.** It changes what the animator is asked to build, and the brief
(§16, deliverables) may need a revision either way.

---

## 2. Task 9 — Kezar / Gallaudet · **deadline 2026-09-07, three days**

**The rule already written down:** the commercial-terms email went out 2026-08-29/30. If there
is no reply **by 2026-09-07**, the licence thread is cold, the bundling risk is gone, and the
Deaf-review request goes out on its own merits.

### Step 1 — check whether it is actually cold (2 min)

Open your Sent folder and find the Sem-Lex enquiry. Confirm:
- did `nkc@bu.edu` bounce, or only `lkezar@usc.edu`? A bounce is **per-recipient**, so if only
  the To: failed then Caselli received it and the thread is *delivered but unanswered*.
- any reply at all, including an auto-reply?

### Step 2 — on 2026-09-07, if still nothing, send the review request (5 min)

**To:** `nkc@bu.edu` — the one address in this project demonstrably reachable.
Separate email, new subject, **do not reply into the licence thread** — that is the bundling
risk the plan warns about.

> Subject: Deaf review of a clinical ASL vocabulary — 55 signs, ~1 hour
>
> Dear Professor Caselli,
>
> I wrote in late August about Sem-Lex commercial terms; no rush on that, and this is a
> separate and smaller ask.
>
> I'm building a two-way ASL↔speech tool for clinical settings (Deafference). The recogniser
> is trained on Sem-Lex and scores 0.8383 on 1,373 held-out clips from 9 unseen signers, and
> I've narrowed it to the 55 concepts that each clear 0.80 on ≥5 held-out clips.
>
> Before it goes in front of anyone I need a fluent Deaf reviewer on three specific things,
> and I've written them up so the review is bounded rather than open-ended:
>
> 1. **Clinical safety categories** — I've gated 10 of the 55 words as never-auto-commit
>    (negation, severity, certainty, red-flag symptoms). Those groupings are a hearing
>    engineer's judgement and I have five specific questions about them. The sharpest: the
>    model can say `no` (0.909) but not `yes` (0.714), so it can render a refusal and not a
>    consent — and `fever`, `nausea`, `vomit`, `chest` and `stomach` were dropped for too few
>    clips. Is a clinical tool missing those still a clinical tool?
> 2. **Handedness labels** — 12 rows where ASL-LEX and my own labels disagree, or where the
>    landmark data contradicts the label (`morning`, `day`, `blood`).
> 3. Whether the 55-word list is the right 55 for a clinical exchange at all.
>
> Would you or a student in your group be willing to look at it? I can send a single
> self-contained document, and I'm happy to pay for the time or to acknowledge the
> contribution — whichever is appropriate.
>
> With thanks,
> Mohammad Salim — Deafference

**Attach nothing on the first email.** Ask first, send `docs/MEDICAL_SAFETY_GATES.md` when
they say yes.

---

## 3. Task 10 — a fluent Deaf reviewer, more than one route · **~30 min, start now**

**Highest-leverage item in the project, and the longest lead time.** Five separate blockers
across three tracks are all the same unmet need. Do not make Caselli the single point of
failure — send three or four of these in the same sitting.

| route | how | what to say |
|---|---|---|
| **Gallaudet University** | their Department of ASL & Deaf Studies, or the Deaf Health Communication centre | the clinical angle is the hook — this is their subject |
| **Your local Deaf association** | national/regional Deaf association in your country | ask for a *paid* consultant, not a favour; it is faster and cleaner |
| **A certified medical interpreter** | RID (rid.org) member directory, or the equivalent national registry | they know the clinical register specifically, which is what §5 of the safety doc needs |
| **ASL-LEX / Sem-Lex authors** | Caselli (task 9) | already in flight |
| **A university with an ASL programme near you** | email the programme coordinator | students often want applied projects |

**The ask, kept to a paragraph so it is easy to say yes to:**

> I'm building an ASL↔speech tool for clinical settings and I need a fluent Deaf reviewer for a
> bounded, one-hour review: a 55-word clinical vocabulary, 10 safety-gated words, and 12
> handedness labels where my sources disagree. Everything is written up in one document with
> specific questions — I'm not asking anyone to design the system, only to tell me where a
> hearing engineer got it wrong. Paid, or acknowledged, whichever you prefer.

**Say "paid" out loud.** Unpaid requests to Deaf communities for language expertise are a
known sore point, and the budget for this is small next to the GPU spend.

---

## 4. Task 7 — upload `ensemble_eval.py` · **~5 minutes**

Now has a **measured** payoff, not just tidiness. I diffed the scripts that actually ran on
Kaggle (they came back inside `results.zip`) against this repo, comparing code only and
ignoring comments:

```
train.py, extract_landmarks.py, npz_to_train_format.py,
select_ship_vocab.py, test_semlex_adapter.py    IDENTICAL
semlex_poses_to_75.py                           IDENTICAL CODE (repo docstring is newer)
ensemble_eval.py                                CODE DIFFERS  <- one missing line
```

The missing line is `"class_names": list(words)` in the report. **That is exactly why
`clinical_ship_vocab.json` came back naming `<unnamed-class-51>` and `<unnamed-class-81>`**, and
why the 123-class order had to be reconstructed by hand from `split_manifest.parquet`. Upload it
and the next run is self-describing.

**Steps:**
1. **kaggle.com/datasets/mohammedsalim1/deafference-fs-code** — or whichever code dataset the
   medical notebook attaches; if the medical run has its own code dataset, use that one.
2. **⋮ → New Version**
3. Drag **`training/ensemble_eval.py`** from your machine (the single file)
4. Notes: `add class_names to the report` → **Create**

If you would rather not touch an existing dataset, a brand-new `deafference-medical-code`
holding the current `training/` scripts is equally fine and matches your standing rule more
closely.

---

## The one-page version

| # | task | time | blocking what |
|---|---|---|---|
| 1 | **message Ghozlan** about the player source | 5 min | the entire avatar track |
| 2 | check Sent, then the Caselli review email on **2026-09-07** | 7 min | safety review, licence |
| 3 | three or four reviewer routes in one sitting | 30 min | 5 items across 3 tracks |
| 4 | upload `ensemble_eval.py` | 5 min | self-describing future runs |

Nothing here is waiting on Microsoft. **The licence is a shipping blocker, not a building
blocker** — don't let the email thread set the pace.
