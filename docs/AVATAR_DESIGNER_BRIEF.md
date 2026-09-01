# Avatar Design Brief — the Deafference signing avatar

**For:** the contracted 3D character artist / rigger
**From:** Deafference (Mohammed Salim, technical lead)
**Version:** 1.0 · 2026-09-01
**Companion documents you do NOT need to read:** `SIGN_ANIMATION_CONTRACT.md`, `AVATAR_LIMITS.md`.
Everything in them that affects your work has been extracted into this file. This brief is
self-contained.

---

## Who does what

| | |
|---|---|
| **You** | The character: model, textures, rig, hand rig, face channels. You own the visual entirely. |
| **Ghozlan** (developer) | The runtime. Loads your rig in Three.js, solves IK, blends between signs, smooths. |
| **Salim** (us) | The motion data. We ship per-word landmark clips; we never touch your rig. |

You are **not** animating. You are building a **puppet that is driven by measured human motion
data**, 30 frames per second, and the constraints below all come from the shape of that data. A
rig that is beautiful and violates §2 will not work at all — it will load, it will look right in
a viewport, and it will be silently wrong in motion. That has already happened to us once and
§2.2 is the scar.

---

## 0. The five things that will silently break the delivery

Read only this section if you read nothing else. Each of these has a measurement behind it, and
each fails **without an error message** — the rig loads, the avatar moves, and the output is
wrong in a way nobody notices for weeks.

| # | Requirement | What happens if missed |
|---|---|---|
| **1** | **Every finger has 4 nodes — 3 bones plus a tip/leaf node.** | The distal phalanx is never posed. On our current rig this left **the dominant hand's fingertips unposed on all 250 words**, including the 163 one-handed signs where that hand *is* the entire sign. It looked fine: a bone left at its bind rotation is anatomically perfect. |
| **2** | **Bone lengths are fixed and documented. No stretchy IK, no scale channels in the skeleton.** | Our depth data carries only the *sign* of z, not its magnitude. The runtime reconstructs out-of-plane depth as `\|dz\| = sqrt(L² − d_2d²)` from known bone length `L`. A bone that can stretch makes that equation unsolvable, and the avatar's arms go flat or inside-out. |
| **3** | **A brow channel and a head-rotation channel exist from day one.** | Four ASL grammatical markers ride on brow and head, not on the hands. Retrofitting a face onto a finished rig costs several times what planning it in costs. Without them the product can only ever "play signs", never produce grammatical sentences. |
| **4** | **The forearms are bare and are clean contact surfaces.** | Six signs in our vocabulary contact the passive **forearm or wrist**, not the hand. Long sleeves or a forearm that reads as a tube make those signs unreadable. |
| **5** | **The hands carry the polygon budget, not the face or the clothes.** | The hands are the entire information channel. A beautiful face and mushy knuckles is exactly backwards for this product. |

---

## 1. What you are building, and why the constraints are strange

A **signing avatar** for a Deaf-accessibility product. A hearing person speaks; we transcribe,
convert to a sequence of signs, and your avatar signs it back. The current target vocabulary is
**250 American Sign Language words**, played one after another, with a medical/clinical
vocabulary planned next.

The motion is **not hand-animated and never will be.** It is measured landmark data from video
of real signers — 75 tracked points per frame (33 upper body, 21 per hand), 30 fps. This has
three consequences that shape everything below:

1. **The data is positions, not rotations.** We give the runtime *where each joint is*, not what
   angle each bone sits at. So your rig is driven as **IK targets** — wrists and fingertips are
   goals, the solver works backwards. Design for that.
2. **The data is imperfect.** Points drop out. On two-handed signs the tracker loses the moving
   hand more than half the time, and the runtime holds or interpolates across the gap. Raw
   landmarks jitter and are smoothed at render time. **Your character must look acceptable under
   imperfect motion** — this is the single strongest argument for a stylized design over a
   realistic one (see §3.3).
3. **The passive hand is often invented.** Our source corpus recorded one hand per signer, so on
   two-handed signs the non-dominant handshape is *synthesized* from a small library of shapes
   (§4.2). Your hand rig has to be able to hit those shapes crisply.

---

## 2. The rig specification

This is the contractual part. §2.1–§2.5 are pass/fail and are checked by script (§7).

### 2.1 Skeleton — required drivable joints

Use **Mixamo naming** (`LeftArm`, `LeftForeArm`, `LeftHand`, `LeftHandIndex1…`). Our tooling and
the existing runtime already key off those names; a different convention costs us a mapping
table and a class of silent bugs. If you must deviate, deliver a JSON mapping file.

Minimum hierarchy:

```
Hips
└── Spine → Spine1 → Spine2
    ├── Neck → Head → HeadTop_End
    ├── LeftShoulder  → LeftArm  → LeftForeArm  → LeftHand  → [5 fingers]
    └── RightShoulder → RightArm → RightForeArm → RightHand → [5 fingers]
```

| Joint | Required | Note |
|---|---|---|
| `Hips`, `Spine`, `Spine1`, `Spine2` | yes | Torso lean is small but real; do not weld the spine into one bone. |
| `Neck`, `Head` | yes | **Head rotation is a grammatical channel** — see §2.4. |
| `LeftShoulder` / `RightShoulder` | yes | Clavicle. Signs reach above the head and across the body; without a clavicle the deltoid tears. |
| `LeftArm` / `RightArm` (upper arm) | yes | IK chain root. |
| `LeftForeArm` / `RightForeArm` | yes | IK mid. Must be a clean contact surface (§4.1). |
| `LeftHand` / `RightHand` (wrist) | yes | **Primary IK target.** |
| 5 fingers × 4 nodes, per hand | yes | **§2.2 — read it.** |
| Legs | optional | Framing is waist-up (§3.4). Include them if it costs nothing; they are never driven. |

**Both arms must be fully drivable.** Do not optimise for a single dominant hand — our data is
normalised so the dominant hand is always the right one, but the left is a real articulated hand
on 87 of 250 words.

### 2.2 The hand rig — exactly 21 nodes per hand

This is the requirement that has already cost us a shipped defect, so it is stated in full.

Our data uses **MediaPipe's 21-point hand topology**: a wrist, plus 4 points per finger.

```
wrist                       0
thumb    CMC  MCP  IP  TIP  1  2  3  4
index    MCP  PIP  DIP TIP  5  6  7  8
middle   MCP  PIP  DIP TIP  9 10 11 12
ring     MCP  PIP  DIP TIP 13 14 15 16
pinky    MCP  PIP  DIP TIP 17 18 19 20
```

Four points per finger means the rig needs **four transform nodes per finger**: three bones plus
a **terminating tip node** (`LeftHandIndex4` / an `_end` leaf — the name matters less than its
existence). Mixamo's `Index1/2/3` is the correct *bone* count; the fourth node is the leaf at the
fingertip. Some export paths and base rigs drop leaf nodes as "empty" — **ours behaves as though
it has none**, and that is the defect below. Please verify explicitly rather than assuming your
package preserved them.

> **Why this is not pedantry.** The retargeter aims each bone at its child. The third segment has
> no child unless a tip node exists, so it is never aimed and stays at its bind rotation. We
> counted the keyed bone tracks across all 250 exported clips:
>
> ```
> distal (segment-3) tracks, across 250 clips:
>   LeftHandIndex3 / Middle3 / Ring3 / Pinky3 / Thumb3    52 clips each
>   RightHandIndex3 / Middle3 / Ring3 / Pinky3 / Thumb3    0 clips  — never, on any word
> ```
>
> The right hand is the dominant hand. **Its fingertips were never posed on a single word.** The
> only reason the left hand escaped is that it is driven by a different code path that copies
> rotations wholesale and never asks for a child. Nothing caught this for weeks because every
> quality check we had scored poses that *were* produced — none of them asked whether a bone had
> been keyed at all.

**Topology and weighting requirements for the hands:**

- **Minimum 3 edge loops per finger segment**, more at the knuckles. Fingers reach full extension
  and full curl in the same second, repeatedly.
- **Clean creasing at MCP and PIP.** Handshapes `A` and `S` are full fists; `B` is fully flat.
  Both extremes are common (see §4.2) and both are where bad weights show.
- **Thumb needs its own attention.** It opposes across the palm in `A`, `S`, `O` and `C`, and sits
  flat against the index in `B`. The thumb is the most-deformed part of a signing hand and the
  most frequently botched.
- **No finger-to-finger interpenetration** when adjacent fingers are fully curled.
- Spend triangles here. Mushy hands are a product failure; a slightly simple shirt is not.

### 2.3 Bone lengths: fixed, documented, and non-uniform

Deliver a small JSON/CSV listing every bone's rest length in the rig's own units. The runtime
needs it for the depth reconstruction described in §0 item 2.

- **No stretch-to-fit IK. No scale animation on skeleton nodes.** Uniform scaling of the whole
  character at load is fine; per-bone scaling is not.
- Build a **normally proportioned human.** ⚠️ **Do NOT derive proportions from our
  `reference_pose.json`.** That file is one 2D camera frame and its limbs are foreshortened — we
  measure the right forearm at **0.258 shoulder-widths** against the left at **0.412** *in the
  same frame*, because the right arm was angled toward the lens. A rig built to those numbers
  would be visibly deformed. The reference pose exists to **test your retarget**, not to model
  from.
- Useful real figures from that pose, in shoulder-widths, for sanity only: shoulder→hip ≈
  **1.00**, nose→shoulder-midpoint ≈ **0.70**, wrist→middle-fingertip ≈ **0.19**.
- Proportion mismatch between our signers and your character is **expected and handled** — the
  runtime derives per-limb scale factors at load. Your job is to be internally consistent and
  documented, not to match a specific human.

### 2.4 Face — two channels, required for v1

Four ASL grammatical markers ride entirely on the face and head. They are not decoration; a
statement and a yes/no question are **identical** on the hands, and the brow is the only thing
that distinguishes them.

| Marker | Meaning | Rendered as |
|---|---|---|
| `q` | yes/no question | **brow raise**, held across the whole sign |
| `wh` | wh-question (who/what/where/why) | **brow furrow** + slight head tilt |
| `neg` | negation | **headshake** across the sign |
| `top` | topic marker | brow raise on the topicalised sign only |

**Minimum deliverable: two independently drivable channels.**

1. **Brow** — raise and furrow, as blendshapes. The absolute minimum is three:
   `browInnerUp`, `browDownLeft`, `browDownRight`. If you are already building a face, deliver
   the **ARKit 52** set; it is a superset, it is what Three.js tooling expects, and it future-proofs
   the mouth morphemes we will need later.
2. **Head rotation** — the `Head` and `Neck` bones, freely rotatable, with weights that survive
   a ±30° shake and a ±20° tilt without the collar tearing.

⚠️ **This is time-critical and it is why it appears in §0.** Retrofitting a face rig onto a
finished character costs several times what including it now costs. If v1 ships without these
two channels, grammatical signing is dead for a year.

**Also required, and easy to miss:** the brows must be **visible**. No fringe over the forehead,
no glasses, no heavy brow-obscuring hair. A brow channel nobody can see is not a channel.

### 2.5 Orientation, units, bind pose

| | |
|---|---|
| **Up axis** | **+Y up.** Standard. Our data is y-down and the runtime flips it — not your problem. |
| **Facing** | **+Z toward the viewer.** The avatar faces the camera. |
| **Units** | Metres, real-world scale (~1.7 m tall). The runtime normalises. |
| **Bind pose** | **A-pose** (arms ~45° down). Better shoulder weights than a T-pose and closer to a signer's rest. |
| **Rest / idle pose** | Also deliver a **neutral signing rest pose** — arms down, hands relaxed and open, in front of the body. This is what the avatar returns to between utterances, and it is the first thing anyone sees. |
| **Origin** | At the feet, centred between them. |
| **Applied transforms** | No unapplied scale or rotation on the armature or meshes. |

---

## 3. The character

Everything above is engineering. This is where your judgement matters, so here is the context
you need to exercise it.

### 3.1 Who is watching

A **Deaf or hard-of-hearing person, in a clinic or hospital, possibly frightened, trying to
understand a doctor.** Our market is Lebanon; the near-term vocabulary is clinical (symptoms,
body parts, medication, staff).

That audience sets the tone precisely:

- **Trustworthy and calm.** This character delivers medical information. Not cute, not cool, not
  a mascot.
- **Professionally plausible.** Reading as clinic-appropriate is right. A uniform or scrubs is a
  reasonable direction and conveniently solves the sleeve problem (§3.2) — but do **not** imply a
  specific real hospital, employer, or credential.
- **Regionally plausible.** A character that reads as Levantine/regional will land better with
  our users than a generic Western default. Your call on execution; flag your intent early.
- **Respectful of the Deaf community.** This is their language. Nothing that reads as mimicry or
  caricature.

### 3.2 Legibility rules — these override aesthetics

The hands carry 100% of the lexical content. Anything that reduces hand legibility is a
functional defect, not a style choice.

- **Hands must contrast strongly against the torso and against each other's background.** Many
  signs are performed directly in front of the chest. A skin-toned top makes those signs vanish.
  Use a mid-to-dark, **solid, unpatterned** torso.
- **Sleeves end at or above the elbow.** Six signs contact the passive forearm or wrist; long
  sleeves hide the target. Short sleeves, or none.
- **No jewellery, no watch, no rings, no gloves, no long nails.** All of it occludes handshape
  and adds silhouette noise.
- **Hands slightly larger than photoreal** — around 5–10% up. Standard practice for signing
  avatars and it buys real legibility at normal viewing size. Do not overdo it into cartoon.
- **Face clear:** brows visible, no glasses, hair off the forehead, no beard obscuring the chin
  (several signs contact the chin — §4.1).
- **Fingertips distinguishable.** Consider very subtle value separation at the fingertips or nails.
  Test it at the real viewing size before committing.

### 3.3 Style: stylized, not realistic — and this is a technical decision

**Recommended: stylized-realistic.** Clean, appealing, human, clearly not photoreal.

The reason is not taste. Our motion data is **jittery, has dropouts, and is interpolated across
gaps** — the runtime holds a handshape through more than half the frames on two-handed signs. A
photorealistic human moving with those artefacts sits squarely in the uncanny valley and reads
as unsettling, which is the worst possible register for a medical accessibility tool. A stylized
character with the same motion reads as *animated*, and the artefacts become stylistic rather
than disturbing.

Avoid: chibi/childish proportions (undermines the clinical register), and any style whose appeal
depends on precise micro-motion we cannot supply.

### 3.4 Framing

- The camera sees roughly **top of head to waist**, front-on.
- The **signing space** extends about **±0.75 shoulder-widths** either side of the body centre and
  from just above the head to the waist. Signs go above the head and out to the sides — the
  character must read well when a hand is at the edge of that box, not just at rest.
- Design for a **portrait-ish or square** crop as well as landscape; this will run on phones.
- Assume a plain background supplied by the app. Do not build an environment.

---

## 4. Signs touch the body — the contact zones

This is the part a generic character brief would miss entirely, and it is where mesh quality
gets tested.

### 4.1 Self-contact targets

ASL signs make **contact with the signer's own body**. These surfaces will be touched, at speed,
repeatedly, with an IK solver that has no collision handling. They must not visibly
interpenetrate or crumple.

| Target | Example signs | What you must ensure |
|---|---|---|
| **Forehead** | `man`, `father` | Clean forehead surface; hair not in the way. |
| **Chin / lower face** | `woman`, `mother` | Reachable chin; no obscuring beard. |
| **Mouth / teeth area** | `eat`, `drink`, `tongue`, `teeth` | Hand approaches the mouth closely. |
| **Chest / sternum** | `heart`, `feel`, `lungs`, `tired`, `sick` | A broad, clean chest plane. Flat clothing folds here. |
| **Passive forearm** | `arm`, `table`, `tree`, `flag`, `morning` | **A clean, bare, cylindrical-but-anatomical forearm.** The dominant hand *slides along* it. |
| **Passive wrist** | `time` | Precise wrist contact — the target is small. |
| **Passive hand** | 29 of the 35 asymmetric signs | Hand-on-hand contact; palms and knuckles meet. |
| **Ear, nose, eye, head** | `ear`, `nose`, `eye`, `head` | Reachable, and not buried in hair. |

**Practical consequence:** avoid geometry that makes contact look broken — deep clothing folds on
the chest, a collar the chin sinks into, sleeves that bunch at the elbow, hair volumes the hand
passes through. Where a small design change makes a contact zone cleaner, take it.

### 4.2 The seven handshapes — please deliver these as named poses

The synthesized passive hand uses a fixed library of seven ASL handshapes. On the current
vocabulary five of them are used, with this frequency:

| Shape | Description | Words using it |
|---|---|---|
| **B** | flat hand, fingers together and extended, thumb alongside | **26** |
| **A** | closed fist, thumb alongside the index | 3 |
| **1** | index extended, rest closed | 3 |
| **C** | fingers and thumb curved into a C | 2 |
| **S** | fist with the thumb crossed over the fingers | 1 |
| **5** | all fingers spread and extended | (not used yet) |
| **O** | fingers and thumb forming a closed O | (not used yet) |

**Deliverable request:** hand-pose all seven on your rig and save them as named pose assets (and
deliver reference renders). Two reasons: it proves the hand rig can hit them crisply, and it
gives us a human-authored reference to check our measured templates against.

> **A specific open question you can help settle.** Our automatically-measured templates for
> **`B` (flat) and `5` (spread)** may not be as distinct from each other as they should be — we
> measured a fingertip displacement of 0.178 between them, the smallest of all 21 shape pairs, and
> we could not resolve whether that is a real problem or an artefact of how we measure. **Your
> hand-posed `B` and `5` would give us the clean reference we lack.** Please make them
> deliberately, clearly distinct, the way a fluent signer would form them.

The base hand is also placed at a specific **orientation** per word. The vocabulary of
orientations your rig must be able to reach comfortably:

- **Palm faces:** up · down · toward the signer · away from the signer · toward the dominant hand
- **Fingers point:** forward · toward the dominant hand · up · toward the signer

---

## 5. What we give you

| Item | What it is |
|---|---|
| `reference_pose.json` | One neutral frame, 75 points, in our coordinate space. **For testing the retarget, not for modelling proportions** (§2.3). |
| `handshape_templates.json` | 21-point measured templates for the seven handshapes. |
| 250 per-word motion clips | Real landmark data, so Ghozlan can drive your rig the day you deliver it. |
| `contact_sheet.png` | Rendered stick-figure previews of the vocabulary — see the actual motion range. |
| A test harness | Ghozlan's existing player, so you can watch your rig move under real data before final delivery. |
| Access to us | Ask early and often. A question answered in week one is free; a rebuild in week four is not. |

**Ask us for anything else you need.** Specifically: if you want video reference of real signers
performing these signs, say so — we will point you at public ASL dictionaries. Do not guess at
what a sign looks like; that is our job to specify, not yours to invent.

---

## 6. What you deliver

| # | Deliverable | Format |
|---|---|---|
| 1 | **Rigged character** | **glTF 2.0 / `.glb`**, single file, embedded textures. This is the production asset — it loads in Three.js. |
| 2 | Editable source | `.blend` (preferred) or `.ma`/`.mb`, with the full modifier/rig stack intact. |
| 3 | **Bone length table** | JSON or CSV — every bone, rest length, in rig units (§2.3). |
| 4 | **Bone name map** | JSON, only if you deviated from Mixamo naming (§2.1). |
| 5 | **Seven handshape poses** | Pose assets in the source file + reference renders (§4.2). |
| 6 | **Neutral rest pose** | As a named pose, plus a render (§2.5). |
| 7 | Face channel list | The blendshape names you shipped, and which ones drive brow raise vs furrow. |
| 8 | Texture sources | Layered source files at working resolution. |
| 9 | A short readme | Anything non-obvious about the rig: IK setup, constraints, corrective shapes, known limits. |

**Budgets** (this runs in a browser, on phones, alongside a live camera feed):

- **Triangles:** 30k–60k for the whole character. **Weight it toward the hands** — spending 25% of
  the budget on two hands that are 3% of the volume is correct here.
- **Textures:** 2K maximum, fewer materials is better. One material for skin, one for clothing is
  ideal.
- **`.glb` file size:** under ~15 MB. Under 8 MB is better.
- **Blendshapes:** brow minimum, ARKit-52 preferred. Do not ship hundreds of correctives.
- **No** rigid-body sim, cloth sim, hair sim, or physics of any kind. Everything must be
  deterministic under IK.

---

## 7. Acceptance tests

These are run by script on delivery, so you can self-check before sending. They exist so that
"done" is a measurement rather than an opinion — and so that payment is not held up by
subjective back-and-forth.

| # | Test | Pass condition |
|---|---|---|
| 1 | **Finger node count** | Every finger, both hands, has **4 transform nodes**. 40 finger nodes + 2 wrists = **42**. Hard fail if any finger has 3. |
| 2 | **Distal keying** | Drive the rig with a real clip; count keyed tracks. **Every segment-3 bone on both hands must be posed.** This is the §2.2 regression test. |
| 3 | **Bone-length stability** | Every bone's length is within 0.1% of its rest length across a full 250-word playback. Catches stretchy IK. |
| 4 | **Reference-pose retarget** | Driven with `reference_pose.json`, wrists land within 5% of a shoulder-width of target. |
| 5 | **Handshape reachability** | All 7 shapes reachable; **`B` and `5` measurably distinct** in bone direction space. |
| 6 | **Face channels** | Brow raise, brow furrow, head shake ±30°, head tilt ±20° — all drivable, no tearing. |
| 7 | **Extremes, no tearing** | Full finger curl, full extension, arm fully overhead, hand across the body to the opposite shoulder, elbow fully flexed. No visible tearing or interpenetration. |
| 8 | **Contact zones** | Hand placed at each §4.1 target: no gross interpenetration. |
| 9 | **Budget** | Triangles, textures, file size within §6. |
| 10 | **Loads clean** | Loads in Three.js with no warnings; no unapplied transforms. |

Tests 1, 2 and 3 are the ones that have actually bitten us. Expect them to be run first.

---

## 8. Out of scope

So you neither over- nor under-deliver:

- **The retargeting solver, the runtime, transitions, smoothing** — Ghozlan's.
- **Which signs exist, what they look like, ASL linguistics** — ours.
- **Full 468-point face mesh driving.** v2. Build the two channels in §2.4 and stop.
- **Lip sync / mouth morphemes.** v2 — but ARKit-52 gets us there for free, which is why it is
  recommended.
- **Legs, walking, locomotion, sitting.** Framing is waist-up.
- **Environments, lighting rigs, backgrounds, UI.**
- **Multiple characters, outfits, or customisation.** One character, done well.

---

## 9. Milestones

Each gate is small and cheap to fix at that point, and expensive to fix later. We would rather
review five times than once.

| M | Deliverable | We check |
|---|---|---|
| **M1** | Concept: 2–3 style directions, silhouette, palette. Blockout with correct proportions. | Register, legibility (§3.2), regional read. **Before any detailed modelling.** |
| **M2** | Skeleton, no mesh detail. Full hierarchy, all 42 hand nodes, bone length table. | **Acceptance tests 1 and 3.** This is the cheapest possible moment to catch §2.2. |
| **M3** | Hands: final topology, weights, all 7 handshapes posed. | Tests 5 and 7. Hand quality review. |
| **M4** | Body, clothing, textures, face channels. | Tests 6 and 8, plus §3.2. |
| **M5** | Final `.glb`, source, all docs. Driven with real motion data. | All ten tests. Sign-off. |

---

## 10. Before you start — please answer these

1. Which package, and can you deliver clean glTF 2.0 from it?
2. Are you comfortable with the **Mixamo naming convention**, or do you want to deliver a map?
3. Have you rigged hands for **IK-driven, position-target** animation before? (If not, say so —
   it is learnable and we would rather plan for it than discover it at M3.)
4. Can you deliver **ARKit-52 blendshapes**, or is the three-shape brow minimum more realistic?
5. Are you starting from scratch, or from a base mesh / commercial base (Avaturn, Ready Player
   Me, MetaHuman, Character Creator)? **A base is fine** — but many bases fail §2.2, and if you
   use one, test 1 must pass at **M2**, not at delivery. Also confirm the base's licence permits
   commercial use and redistribution inside an application.
6. Your estimate and rate against the milestones in §9.
7. Anything in this brief that looks wrong, unusual, or more expensive than it needs to be. You
   will know things about rigging that we do not — say so early.

---

## Appendix — why the constraints are shaped this way

Not required reading; here because a designer who understands the *why* makes better decisions on
the hundred things a brief cannot cover.

**Our source data records one hand per signer.** In the corpus behind the 250-word vocabulary,
both hands are present in **1.7%** of clips. So on every two-handed sign the passive hand is
absent from *every take*, and its handshape must be synthesized from the seven-shape library
(§4.2). What *is* recorded in every frame is the passive **wrist**, because that is a body
landmark rather than a hand landmark. Hence the split: position is given, shape is invented.

**The tracker loses the hand that moves.** Measured on our export: median wrist speed is
**0.0208** shoulder-widths per frame when the hand is tracked and **0.0317** when it is missing —
a 1.5× ratio. Two-handed signs are exactly where the hands cross and occlude, so the dominant
hand drops out most on the words that need it most. Of 87 two-handed words, **3 reach our top
quality tier; 39 fall to the bottom one.** Of 163 one-handed words, **zero** fall to the bottom
tier. This is a property of the source data, not of unfinished work — and it is the concrete
reason your character must look acceptable under interpolated, imperfect motion (§3.3).

**The face channel does not exist in our data.** We can recover 468 face landmarks upstream, but
the corpus is *isolated single words*, so the signers' expressions are neutral and inconsistent
rather than grammatical. A face rig driven by that data would move without meaning anything. So
the non-manual markers in §2.4 are **generated from rules on our side** — which needs no data at
all, only a rule and a rig. That is why §2.4 asks for two clean channels rather than a
data-driven face: it is the one place in this system where we can add real linguistic structure,
and it is gated entirely on your rig having the channels.

**Two of our lexicons are unreviewed by a Deaf signer.** The handshape templates and the passive-hand
placements were written from published phonology by a hearing developer. Where a fluent reviewer
eventually disagrees, **the fix is our lexicon, not your rig** — which is precisely why §4.2 asks
for clean, deliberate, separable handshapes. A crisp rig lets us tell a data error from a rig
error. A mushy one does not.
