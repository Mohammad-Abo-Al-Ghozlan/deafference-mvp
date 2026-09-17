# Base-hand review — 35 two-handed signs the avatar now draws from a lexicon

**Written 2026-09-18.** Companion to `HANDSHAPE_REVIEW.md` (which shape) and
`HANDEDNESS_REVIEW_SHEET.md` (how many hands). This one is **where the second hand goes and
which way it faces**, and it is reviewable for the first time because the avatar now actually
draws it.

## Why this needs a Deaf reviewer and cannot be settled any other way

On these 35 signs the second hand is a **static base**: it holds still while the dominant hand
acts on it. TOUCH, CHAIR, PEN, CHOCOLATE, AFTER. In the recordings that hand does not exist —
the corpus captured one hand per signer — so every part of it is supplied by us:

| what | from | reviewed by a Deaf signer? |
| --- | --- | --- |
| how many hands | `asl_handedness_250.json` | **no** |
| which handshape | `handshape_templates.json` | **no** |
| where it sits | `asl_2a_base_placement.json` | **no** |
| which way it faces | `asl_2a_base_placement.json` | **no** |

All four files say so themselves. `asl_2a_base_placement.json`:

> AUTHORED BY A HEARING DEVELOPER FROM ASL PHONOLOGY, NOT BY A DEAF SIGNER, AND NOT VALIDATED
> AGAINST VIDEO. [...] Every entry marked medium or low should be treated as a placeholder that
> renders plausibly rather than a claim about the language.

There is no measurement that can check this. Every error number the avatar reports is computed
against recorded landmarks, and this hand has none — so a base in completely the wrong place
scores exactly as well as a correct one. **A reviewer's eye is the only instrument that
works here.**

## What the reviewer does

Open `avatar/sign_viewer.html`, type the word in the filter box, and watch. Use the **½×** or
**¼×** speed selector — a sign lasting 0.6 s is legible to a fluent signer and not to anyone
checking a detail. The sidebar shows `passive hand: placed base (2a)` on exactly these 35.

Then fill `docs/BASE_HAND_REVIEW.csv`. **Three verdict columns, because they have three
different fixes** — collapsing them into one "does it look right?" loses what to do next:

| column | question | if NO, the fix is |
| --- | --- | --- |
| `Q1_shape_right` | Is the base hand the right handshape? | `asl_handedness_250.json` → `passive_handshape.words[word].shape` |
| `Q2_place_right` | Is it in the right place relative to the moving hand? | `asl_2a_base_placement.json` → `offset` and `anchor` |
| `Q3_orientation_right` | Is the palm facing the right way, fingers pointing the right way? | `asl_2a_base_placement.json` → `palm` and `fingers` |

A base can be the right shape in the wrong place, or the right place facing backwards. Each is
a one-line change to a lexicon file, and **none of them is a rig bug** — please do not report
them as "the avatar is broken", report which of the three is wrong.

## Start here — the 13 the author was least sure of

Two marked `low` and eleven `medium`, from the file's own `confidence` field:

- **low**: `backyard`, `closet`
- **medium**: `after`, `all`, `arm`, `before`, `empty`, `first`, `hide`, `mitten`, `morning`,
  `night`, `read`

## Six that are known to be wrong in a way the review cannot fix

`asl_2a_base_placement.json` marks these `not_plain_handshape_placement`: **`arm`, `flag`,
`morning`, `table`, `tree`, `time`**. On these the dominant hand acts on the passive
**forearm or wrist**, not on the hand — so the base's handshape barely matters and what has to
be right is the whole limb's pose, which the placement file's schema cannot express. Expect
them to look wrong. Say *how* they look wrong if you can; that is what tells us what schema to
build. Do not spend time on the handshape there.

## What we measured ourselves, so the reviewer doesn't have to

Two properties are checkable without knowing ASL, and both are checked automatically on every
bake (`selftest` in `avatar/retarget.py`):

- **the base is within reach of the hand that contacts it** — a dominant hand pressing on
  something a shoulder-width away is contacting nothing. Median 0.36 shoulder-widths apart
  against a rig hand 0.64 long.
- **the base does not move** — that is what makes it a base. Drift across a clip: 0.002
  shoulder-widths.

One word still fails the first test: **`helicopter`**, at 0.92. Three more (`flag`, `table`,
`tree`) fail it because they are forearm signs, above.

## What a "yes" here does and does not mean

A yes means *this is a recognisable form of the sign*. It does not mean the animation is good —
the movement, timing and dominant handshape are scored separately and reported in the viewer.
And it does not clear the sign for shipping: the rig this is drawn on is still blocked on the
Renderpeople licence question (`AVATAR_M1_REVIEW_2026-09-12.md` §Q5), and the corpus is
CC BY-NC-SA (`LICENCE_REQUESTS.md`).
