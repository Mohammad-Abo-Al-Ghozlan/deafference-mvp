# Avatar Design Brief — the Deafference signing avatar

**For:** the contracted 3D character artist / rigger
**From:** Deafference (Mohammed Salim, technical lead)
**Version:** 2.0 · 2026-09-01

> **This file is the source of truth.** A formatted web version with the three diagrams — the
> finger-chain defect, the depth reconstruction, and the signing-space / contact-zone map — is what
> gets sent to the designer. Update this file first, then republish.
>
> **No prior sign-language or machine-learning knowledge is assumed.** §1 is a glossary; the rest of
> the brief uses it. Companion documents `SIGN_ANIMATION_CONTRACT.md` and `AVATAR_LIMITS.md` do
> **not** need to be read — everything in them that affects the artist's work is extracted here.

---

## Who does what

| | |
|---|---|
| **The artist (you)** | The character: model, textures, skeleton, hand rig, face channels, pose library. You own the visual entirely — style, silhouette, colour, materials. |
| **Ghozlan** (developer) | The runtime. Loads your rig in Three.js, solves the IK, blends between signs, smooths the motion, drives the face channels. |
| **Salim** (us) | The motion data and the sign linguistics. We ship per-word landmark clips. We never touch your rig or your mesh. |

You are **not animating.** You are building a **puppet driven by measured human motion** — 30 frames
a second of real Deaf signers' hands, recorded as points in space.

> **The one sentence that matters most.** A rig that is beautiful and violates §6 **will not work at
> all** — and it will not announce itself. It will load, it will look right in your viewport, it
> will move, and it will be silently wrong. That has already happened to us once, and §6.2 is the
> scar.

---

## 1. Glossary — our words in your terms

This brief mixes sign-language linguistics with motion-capture engineering. Every term you will
meet, translated:

| term | what it means here |
|---|---|
| **landmark** | One tracked point in space, `(x, y, z)`. Our motion data is nothing but landmarks: **75 per frame** — 33 on the upper body, 21 on each hand. Very cheap, very noisy markerless mocap. |
| **MediaPipe** | Google's free body/hand tracking library. It watched videos of signers and produced our landmarks. Its conventions are why 33, 21 and 75 keep appearing. |
| **retarget** | Making *your* rig reproduce *a real person's* motion despite different proportions. Ghozlan writes this; you just need the rig to be retargetable. |
| **IK target** | A point in space a solver drives a limb toward. We give positions, not angles, so wrists and fingertips are goals and the solver finds the rotations. See §3.1. |
| **gloss** | The written name of a sign — `hello`, `pain`. A label for a sign, not a translation of it. |
| **handshape** | The finger configuration, treated in sign languages as a distinct unit — like a phoneme. ASL has a fixed inventory with names like **B** (flat), **A** (fist), **1** (index pointing). We use seven (§9). |
| **dominant hand** | A signer's main hand. Our data is normalised so **the dominant hand is always the right one.** Do not try to infer it. |
| **passive hand** | The other hand. In two-handed signs it either mirrors the dominant hand or holds still as a "base" the dominant hand acts on. **Usually missing from our recordings** and synthesized — hence §9. |
| **one- / two-handed** | 163 of our 250 words are one-handed, 87 two-handed. The two-handed ones are where all the difficulty lives. |
| **non-manual marker** | Grammar carried on the **face and head** rather than the hands — a raised brow makes a sentence a question, a headshake negates it. Not decoration: a sentence without them is closer to ungrammatical. §6.4. |
| **shoulder width** | Our unit. All measurements are divided by the signer's shoulder width, so they are person-independent. "0.19 shoulder-widths" = 19% of the distance between the shoulder joints. |
| **MCP · PIP · DIP · TIP** | The four joints of a finger, base to tip: knuckle, middle joint, last joint, fingertip. Thumb: CMC, MCP, IP, TIP. **Four positions per finger** — that number is the whole of §6.2. |
| **bind rotation** | A bone's rest orientation before animation touches it. A bone nobody animates sits at its bind rotation and **looks anatomically perfect** — which is how our worst bug hid for weeks. |
| **keyed track** | An animation channel that actually contains data for a bone. A bone with no keyed track is not animated at all. Counting these is how we found the §6.2 bug. |
| **tier A / B / C** | Our internal grade for how well each of the 250 words was captured. A is clean, C is barely usable. Referenced for context; you cannot affect it. |

---

## 2. What the job is

Deafference builds two-way communication between Deaf and hearing people. One direction listens to
speech and **signs it back**. That direction needs an avatar.

The pipeline: a hearing person speaks → we transcribe → we convert the sentence to an ordered list
of signs → we look up recorded motion per sign → **your avatar performs them** → a Deaf person
reads it.

Current vocabulary is **250 American Sign Language words**, played one after another. A clinical
vocabulary — symptoms, body parts, medication, hospital staff — is next. Our market is Lebanon.

---

## 3. Why this is not normal character work

Three things here will be unfamiliar if you have rigged for games or film. They are the source of
almost every requirement in §6.

### 3.1 We send positions, not rotations

Normally a rig receives *rotations* — an animator or mocap solve tells each bone what angle to sit
at. **Our data has no angles in it at all.** It is a cloud of 75 point positions per frame, measured
off video.

So the runtime treats those points as **IK targets**: "put the wrist here, put the index fingertip
here", and solves backwards for rotations. Two consequences:

- **Bones cannot stretch.** A solver reaching for a target will happily lengthen a bone if allowed,
  which tears the mesh and destroys §3.2. Lock it down.
- **Every point we send needs somewhere to go.** If our data has a fingertip position and your rig
  has no fingertip node, that data is silently discarded. This is §6.2, the most important paragraph
  in this document.

### 3.2 Depth is half-missing, and bone length is how we recover it

MediaPipe's depth (`z`) is unreliable as a *value*. What it gets right is the *sign* — whether a
hand is in front of or behind the plane. So the runtime reads one bit from `z` and reconstructs the
magnitude from your rig's known bone length:

```
|dz| = sqrt(L² − d_2d²)

  L      the bone's length — FIXED, and known from your rig
  d_2d   the flat distance the camera actually measured, in x and y
  dz     the out-of-plane offset, solved
```

Let the solver stretch that bone and the equation has no unique answer — the arm flattens or
inverts. **This is the entire reason requirement #2 exists.**

### 3.3 The motion is imperfect, and that is permanent

Landmarks jitter. Points drop out — on two-handed signs the tracker loses the moving hand **more
than half the time**, and the runtime holds or interpolates across the gap. This is a property of
the source recordings, not a bug awaiting a fix.

So your character must look acceptable *under imperfect motion*. This is the strongest argument for
a stylized design over a photorealistic one; §7.3 makes the case properly.

---

## 4. Five things that break the delivery silently

Each fails **without an error message.** The rig loads, the avatar moves, and it is wrong in a way
nobody notices for weeks.

| # | Requirement | What happens if missed |
|---|---|---|
| **1** | **Every finger has four nodes** — three phalanx bones plus a tip node. | The last finger segment is never posed. On our current rig this left **the dominant hand's fingertips unposed on all 250 words**, including the 163 one-handed signs where that hand *is* the entire sign. Nobody saw it, because a bone at its bind rotation looks anatomically perfect. **§6.2** |
| **2** | **Bone lengths fixed and documented.** No stretchy IK, no scale channels on bones. | Depth is reconstructed from bone length (§3.2). A bone that can stretch makes it unsolvable, and the arms go flat or inside-out. **§6.3** |
| **3** | **A brow channel and a head-rotation channel from day one.** | Four grammatical markers ride on brow and head, not on the hands — a statement and a yes/no question are *identical* on the hands. Retrofitting a face onto a finished character costs several times what including it now costs. **§6.4** |
| **4** | **Bare forearms, as clean contact surfaces.** | Six signs contact the passive **forearm or wrist**, not the hand. Long sleeves hide the target; a forearm modelled as a plain tube makes the contact read as a collision. **§8** |
| **5** | **The hands carry the polygon budget** — not the face, not the clothing. | The hands are the entire information channel. A beautiful face with mushy knuckles is exactly backwards for this product. **§11** |

---

## 5. One sign, start to finish

Abstract requirements are hard to build against, so here is the whole chain for one word. Take
**`pain`** — the most important sign in a clinical vocabulary. In ASL it is two index fingers
pointing at each other, jabbed toward each other near the part of the body that hurts. A
*two-handed symmetric* sign.

1. **We send one file:** `pain.json`. Inside is a list of frames — say 34 of them at 30 fps, so just
   over a second. Each frame is 75 `(x, y, z)` points.
2. **Some points are missing.** The hands move toward each other and occlude, so the tracker loses
   one. A missing point arrives as `null`, and the runtime holds the last good value across the gap.
3. **The passive hand is missing entirely.** Our corpus recorded one hand per signer. So the file
   carries an instruction: *this is a symmetric sign — mirror the dominant handshape onto the
   passive hand.* The passive **wrist** position is real; only its shape is synthesized.
4. **The runtime flips the vertical axis** (our y points down, yours up), scales our signer's
   proportions onto yours, and sets IK targets: right wrist here, each right fingertip here, left
   wrist here.
5. **Your rig solves it.** Both index fingers must end up crisply extended with the other fingers
   closed — handshape **`1`** — and *the fingertips must actually point at each other.* If your
   index finger's last segment is unposed (failure #1), both hands render with a slightly bent,
   vague index and the sign becomes unreadable.
6. **The face does nothing here** — unless the sentence was a question, in which case the brow is
   raised for the whole duration. A separate channel, driven by rule, not by data.
7. **Then the next word starts** and the runtime blends between poses. Your rig has to look correct
   in the interpolated middle too, not only at the keyframes.

**What this asks of you, concretely:** a hand that can hold a crisp, unambiguous handshape `1`
(index fully straight, other three fully curled, thumb closed over them) with a **fully posed
fingertip**, while the wrist is driven to an arbitrary position near the chest, without the mesh
tearing at the knuckles — and that still reads correctly when the motion driving it is jittery and
partly interpolated.

That is the job. Everything in §6 is a restatement of it.

---

## 6. The rig specification

Pass/fail, and checked by script (§13).

### 6.1 Skeleton — required joints

Use **Mixamo naming**. Not a preference: we extracted every animated bone name from the existing
runtime, and these are the names it already drives.

```
Spine  Spine1  Spine2  Neck  Head
{Left,Right}Shoulder  {Left,Right}Arm  {Left,Right}ForeArm  {Left,Right}Hand
{Left,Right}Hand{Thumb,Index,Middle,Ring,Pinky}{1,2,3}
```

Un-prefixed — no `mixamorig:`. **Note what is absent from that list: there is no `4` or `_end` node
on any finger.** That absence is the defect. Yours must have one.

Required hierarchy:

```
Hips
└── Spine → Spine1 → Spine2
    ├── Neck → Head → HeadTop_End
    ├── LeftShoulder  → LeftArm  → LeftForeArm  → LeftHand  → [5 fingers]
    └── RightShoulder → RightArm → RightForeArm → RightHand → [5 fingers]
```

| Joint | Required | Why |
|---|---|---|
| `Hips` `Spine` `Spine1` `Spine2` | yes | Torso lean is small but real. Do not weld the spine into one bone. |
| `Neck` `Head` | yes | Head rotation is a *grammatical* channel, not a flourish — §6.4. |
| `Left/RightShoulder` | yes | Clavicle. Signs reach above the head and across the body; without a clavicle the deltoid tears at those extremes. |
| `Left/RightArm` | yes | Upper arm. Root of the IK chain. |
| `Left/RightForeArm` | yes | IK mid-chain, and a contact surface in its own right — §8. |
| `Left/RightHand` | yes | Wrist. The primary IK target. |
| 5 fingers × 4 nodes, both hands | yes | **§6.2 — the one to get right.** |
| Legs | optional | Framing is waist-up. Include if free; never driven. |

**Both arms must be fully articulated and drivable.** Do not optimise for a single dominant hand —
the passive hand is a fully posed hand on 87 of 250 words.

### 6.2 The hand rig — four nodes per finger

Our data gives **four positions per finger**: knuckle, middle joint, last joint, fingertip. Three
bones span those four positions. **A retargeter poses a bone by aiming it at its child.** So the
third bone can only be posed if something exists at the fingertip to aim at.

```
✓ YOUR RIG — 4 nodes, 3 bones, every bone has a child to aim at

   MCP ──────── PIP ──────── DIP ──────── TIP
  Index1       Index2       Index3     Index4/_end
        aimed ✓      aimed ✓      aimed ✓


✗ OUR CURRENT RIG — 3 nodes. The last bone has nothing to aim at.

   MCP ──────── PIP ──────── DIP - - - - -  ✗ no node
  Index1       Index2       Index3
        aimed ✓      aimed ✓      NEVER aimed — stays at bind rotation
```

**The measurement, per bone.** We counted the keyed animation tracks across all 250 exported clips:

```
LeftHandIndex1  250 clips     RightHandIndex1  250 clips   <- has a child, gets aimed
LeftHandIndex2  250 clips     RightHandIndex2  250 clips   <- has a child, gets aimed
LeftHandIndex3   52 clips     RightHandIndex3    0 clips   <- needs a TIP node

(identical pattern on Middle, Ring, Pinky and Thumb)
```

The right hand is the dominant hand — **its fingertips were never posed on a single word.** The left
escaped only on the 52 symmetric signs, where a different code path copies rotations wholesale and
never asks for a child.

Nothing caught this for weeks, because every quality check we had scored the poses that *were*
produced. None of them asked whether a bone had been keyed at all.

> **⚙️ Blender specifics — this is where the trap is.**
> In Blender a finger of **3 bones** already gives 4 joint *positions* (three heads plus the last
> bone's tail), so it looks correct while you work. But **glTF export writes one node per bone.**
> The final tail is not a bone, so it does not become a node, and the exported `.glb` has only
> three.
>
> **The fix: give every finger a fourth bone.** A short tip bone, parented to the distal phalanx,
> with no vertex weights. It carries no deformation — it exists so the exported file has a node at
> the fingertip. Name it `…Index4`, or let Blender's `…Index3_end` convention through, and confirm
> it survives export.
>
> **Verify on the exported file, not in the viewport.** §12 has a paste-in check.

**Topology and weighting, hands:**

- **At least 3 edge loops per finger segment, 4+ across each knuckle.** Fingers reach full extension
  and full curl within the same second, repeatedly, all day.
- **Clean creasing at MCP and PIP.** Handshapes `A` and `S` are full fists; `B` is fully flat. Both
  extremes are common (§9), and both are where sloppy weights show first.
- **The thumb deserves disproportionate attention.** It opposes across the palm in `A`, `S`, `O` and
  `C`, and lies flat along the index in `B`. Most-deformed part of a signing hand, most commonly
  botched.
- **No finger-to-finger interpenetration** with all four fingers fully curled, and no webbing
  collapse when they spread fully (handshape `5`).
- **The palm must not balloon.** Check the closed fist from the side.
- Keep weights tight — a fingertip that drags neighbouring geometry blurs the handshape, which is
  the one thing that must stay legible.

### 6.3 Bone lengths: fixed, documented, non-uniform

Deliver a small JSON or CSV listing every bone's rest length in the rig's own units. The runtime
needs it for §3.2.

- **No stretch-to-fit IK. No scale animation on skeleton nodes.** Uniform scaling of the whole
  character at load is fine; per-bone scaling is not.
- IK constraints in your DCC for posing convenience are fine — but the *exported* skeleton must be
  plain FK bones with stable lengths. Bake anything clever.

> **⚠️ Do NOT model your proportions from our reference pose.**
> We give you `reference_pose.json` and it is tempting to treat it as a proportion target. It is
> **one frame of 2D camera footage**, so its limbs are foreshortened. We measure the right forearm at
> **0.258** shoulder-widths against the left at **0.412** *in that same frame*, because the right
> arm happened to be angled toward the lens. A rig built to those numbers would be visibly
> deformed.
>
> **Build a normally proportioned human.** The reference pose exists to *test the retarget*, not to
> model from. Proportion mismatch is expected and handled — the runtime derives per-limb scale
> factors at load. Your job is to be internally consistent and documented.
>
> Sanity figures only, in shoulder-widths: shoulder→hip ≈ **1.00** · nose→shoulder-midpoint ≈
> **0.70** · wrist→middle-fingertip ≈ **0.19**.

### 6.4 Face — two channels, required in v1

**ASL grammar is not carried by the hands alone.** A raised eyebrow turns a statement into a yes/no
question. A headshake is how you negate. Held *across* the sign, simultaneously with it. Today our
system emits the **identical** hand motion for "you have pain" and "do you have pain?", and there is
no way to tell them apart. The brow is the only thing that would.

| marker | grammar | rendered as |
|---|---|---|
| `q` | yes/no question | **brow raise**, held for the whole sign |
| `wh` | wh-question — who, what, where, why | **brow furrow** + slight head tilt |
| `neg` | negation | **headshake** across the sign |
| `top` | topic marker | brow raise on the topicalised sign only |

All four are covered by two independently drivable channels:

1. **Brow — raise and furrow, as blendshapes.** Absolute minimum three: `browInnerUp`,
   `browDownLeft`, `browDownRight`. If you are building a face anyway, deliver the **ARKit 52** set
   — a superset, what Three.js tooling expects, and it future-proofs the mouth shapes we need later.
2. **Head rotation — the `Head` and `Neck` bones**, freely rotatable, weighted to survive a ±30°
   shake and a ±20° tilt with no collar tearing and no neck pinching.

> **Two easy ways to fail this.**
> **Timing** — retrofitting a face rig onto a finished character costs several times what including
> it now costs. If v1 ships without these channels, grammatical signing is dead for a year.
> **Visibility** — the brows must be *visible*. No fringe over the forehead, no glasses, no
> brow-obscuring hair. A brow channel nobody can see is not a channel, and it is easy to design one
> away without noticing.

### 6.5 Orientation, units, bind pose

| | |
|---|---|
| **Up axis** | **+Y up.** Standard. Our data has y pointing *down* and the runtime flips it — not your problem, and do not compensate for it. |
| **Facing** | **+Z toward the viewer.** The avatar faces the camera. |
| **Units** | Metres, real-world scale, ~1.7 m tall. The runtime normalises, but a sane scale prevents a class of solver problems. |
| **Bind pose** | **A-pose**, arms ~45° down. Better shoulder weights than a T-pose, closer to a signer's rest. |
| **Rest / idle pose** | A separate **neutral signing rest pose** — arms down, hands relaxed and slightly open, in front of the body. Where the avatar sits between utterances, so the pose people see most. |
| **Origin** | At the feet, centred between them. |
| **Transforms** | No unapplied scale or rotation on the armature or any mesh. Apply everything before export. |
| **Mesh** | Single skinned mesh preferred, or as few as possible. No modifiers left unapplied except the armature. |

---

## 7. The character

Everything above is engineering. This is where your judgement is what we are paying for.

### 7.1 Who is watching

A **Deaf or hard-of-hearing person, in a clinic or hospital, possibly frightened, trying to
understand a doctor.** Our market is Lebanon. The near-term vocabulary is clinical.

- **Trustworthy and calm.** This character delivers medical information. Not cute, not cool, not a
  mascot, no personality quirks.
- **Professionally plausible.** Clinic-appropriate is right, and scrubs or a simple uniform is a
  good direction that conveniently solves the sleeve problem in §7.2. But do **not** imply a
  specific real hospital, employer, or credential.
- **Regionally plausible.** A character that reads as Levantine will land better with our users than
  a generic Western default. Execution is yours — flag your intent at M1 so we can react early.
- **Respectful of the Deaf community.** This is their language and they are the users. Nothing that
  reads as mimicry, caricature, or novelty.
- **Adult. Gender is your call** — but say which and why. We have no fixed requirement and would
  rather hear your reasoning.

### 7.2 Legibility rules — these override aesthetics

The hands carry **100% of the lexical content.** Anything that reduces hand legibility is a
functional defect, not a style choice. If one of these conflicts with a design you like, the rule
wins — or you make the case to us and we decide together.

- **Hands must contrast strongly against the torso.** Very many signs are performed directly in
  front of the chest, so a skin-toned top makes those signs vanish. Use a mid-to-dark, **solid,
  unpatterned** torso. No stripes, no logos, no busy texture.
- **Sleeves end at or above the elbow.** Six signs contact the passive forearm or wrist (§8).
- **No jewellery, watch, rings, gloves, bracelets, or long nails.** All of it occludes handshape and
  adds silhouette noise.
- **Hands slightly larger than photoreal** — about 5–10%. Standard for signing avatars, and it buys
  real legibility at phone size. Do not push into cartoon proportions.
- **Face clear:** brows visible, no glasses, hair off the forehead, no beard obscuring the chin —
  several signs contact the chin (§8).
- **Fingertips subtly distinguishable** — a slight value shift at the tips or nails helps handshape
  read. Test at real viewing size; overdone, it looks diseased.
- **Test everything at 320 px tall.** Roughly the real size on a phone. A design that only works at
  4K is not delivered.

### 7.3 Style: stylized, not realistic — and this is a technical decision

**Recommended: stylized-realistic.** Clean, appealing, recognisably human, clearly not photoreal.
Think a well-made explainer character rather than a game hero or a MetaHuman.

The reason is not taste. Re-read §3.3: our motion is jittery, drops out, and is interpolated. A
*photorealistic* human moving with those artefacts sits squarely in the uncanny valley and reads as
unsettling — the worst possible register for a medical accessibility tool used by someone already
anxious. A stylized character with identical motion reads as *animated*, and the same artefacts
become stylistic instead of disturbing.

Avoid chibi or childish proportions, which undermine the clinical register; and any style whose
appeal depends on micro-expression or subtle secondary motion we cannot supply.

### 7.4 Framing and the signing space

- The camera sees roughly **top of head to waist**, front-on.
- The **signing space** extends about **±0.75 shoulder-widths** either side of body centre, and from
  just above the head to the waist — a box about 1.5 shoulder-widths wide. Signs go above the head
  and out to the sides; the character must read well with a hand anywhere in that box, not only in
  the A-pose.
- Design for a portrait-ish or square crop as well as landscape. This will run on phones.
- Assume a plain background supplied by the app. Do not build an environment.

---

## 8. What the hands touch

ASL signs make contact with the signer's **own body** — at speed, repeatedly, driven by an IK solver
with **no collision handling whatsoever.**

| Target | Example signs | What you must ensure |
|---|---|---|
| **Forehead** | man, father | Clean forehead surface; hair not in the way; the hand arrives flat against it. |
| **Chin / lower face** | woman, mother | Reachable chin, not sunk into a collar; no obscuring beard. |
| **Mouth / teeth** | eat, drink, tongue, teeth | The hand comes very close to the mouth. Keep the area clean and unobstructed. |
| **Chest / sternum** | heart, feel, lungs, tired, sick | A broad, clean, near-flat chest plane. Keep clothing folds shallow here. |
| **Passive forearm** | arm, table, tree, flag, morning | **Bare, anatomical forearm.** The dominant hand *slides along* it — a plain cylinder reads as a collision. |
| **Passive wrist** | time | Precise contact on a small target. Keep the wrist form readable. |
| **Passive hand** | 29 of the 35 asymmetric signs | Hand-on-hand contact — palms and knuckles meet, one hand rests on the other. |
| **Ear · nose · eye · head** | ear, nose, eye, head | Reachable, and not buried in hair volume. |

Note the front-view orientation: since the dominant hand is always the **right** one, the passive
forearm and wrist the dominant hand acts on are on the signer's **left** — the viewer's right.

**Practical consequence.** Avoid geometry that makes contact look broken: deep chest folds, a collar
the chin sinks into, sleeves that bunch at the elbow, hair volumes a hand passes through, a forearm
with no anatomical landmarks. Where a small design change makes a contact zone cleaner, take it —
and tell us, so we know it was deliberate.

We are **not** asking for collision solving. We are asking for a body whose contact surfaces are
forgiving when a hand lands on them approximately.

---

## 9. The seven handshapes

In sign languages the finger configuration is a distinct linguistic unit with a fixed inventory and
standard names. Our synthesized passive hand uses seven. On the current vocabulary five are used:

| Shape | How it is formed | Words using it |
|---|---|---|
| **B** | Flat hand. All four fingers extended and held **together**, thumb folded across or alongside the palm. A flat paddle. | **26** |
| **A** | Closed fist with the thumb **alongside** the index finger, pointing up — not tucked inside, not crossed over. | 3 |
| **1** | Index finger fully extended and straight, other three curled into the palm, thumb closed over them. | 3 |
| **C** | Fingers held together and curved, thumb curved opposite, forming a clear C-shaped gap. Not a fist, not flat. | 2 |
| **S** | Closed fist with the thumb **crossed over** the front of the folded fingers. Distinct from `A` only in the thumb. | 1 |
| **5** | All five fingers extended and **spread wide apart**. The spread is the point. | not used yet |
| **O** | Fingertips and thumb tip meeting to form a closed round O. | not used yet |

**Deliverable: hand-pose all seven, as named poses.** Save them as named pose assets in the source
file and deliver reference renders (front and side of the hand). Two reasons: it proves the hand rig
can hit them crisply, and it gives us a human-authored reference to check our measured templates
against.

**Look at real reference, not just our descriptions** (§16). These are real linguistic forms with
correct and incorrect versions — the difference between `A` and `S` is only where the thumb goes,
and it is a real difference.

> **⚠️ A specific open question you can settle for us.**
> Our automatically-measured templates for **`B` (flat, together) and `5` (extended, spread)** may
> not be as distinct from each other as they should be. We measured a fingertip displacement of
> **0.178** between them — the *smallest* of all 21 shape pairs — and we could not resolve whether
> that is a genuine problem in our data or an artefact of how we measure it.
>
> **Your hand-posed `B` and `5` would give us the clean reference we lack.** Please form them
> deliberately and unmistakably distinct: `B` with fingers pressed together and flat, `5` with
> fingers splayed as wide as the hand goes.

The synthesized hand is also placed at a specific **orientation** per word. Your rig must reach all
of these comfortably, at the wrist, without the forearm twisting past anatomical limits:

- **Palm faces:** up · down · toward the signer · away from the signer · toward the other hand
- **Fingers point:** forward · toward the other hand · up · toward the signer

---

## 10. What we give you

| Item | What it is, and what to do with it |
|---|---|
| `reference_pose.json` | One neutral frame, 75 points, in our coordinate space. **For testing your retarget, not for modelling proportions** — see §6.3. |
| `handshape_templates.json` | 21-point measured templates for the seven handshapes. Numeric reference for what the shapes should be. |
| 250 per-word clips | Real landmark motion, one file per word. This is what will drive your rig, so Ghozlan can test it the day you deliver. |
| `contact_sheet.png` | Rendered stick-figure previews of the whole vocabulary. **Look at this early** — it shows the real range of motion better than any description. |
| A test harness | Ghozlan's existing player. Load your own rig and watch it move under real data *before* final delivery. Use it at M3, not M5. |
| Us | Ask early and often. A question answered in week one is free; a rebuild in week four is not. |

**Ask for anything else you need.** Especially: if you want video reference of real signers
performing these signs, say so and we will point you at it. **Do not guess at what a sign looks
like** — specifying that is our job, not yours to invent.

---

## 11. What you deliver

| # | Deliverable | Format & notes |
|---|---|---|
| 1 | **Rigged character** | **glTF 2.0 `.glb`**, single file, embedded textures. The production asset — loads directly in Three.js. |
| 2 | Editable source | `.blend` preferred, or `.ma`/`.mb`, with the full rig stack intact and nothing collapsed. |
| 3 | **Bone length table** | JSON or CSV — every bone, rest length, in rig units (§6.3). |
| 4 | Bone name map | JSON. *Only* if you deviated from the §6.1 names. |
| 5 | **Seven handshape poses** | Named pose assets in the source + front/side reference renders (§9). |
| 6 | Neutral rest pose | A named pose, plus a render (§6.5). |
| 7 | Face channel list | The blendshape names you shipped, and which drive brow raise vs furrow. |
| 8 | Texture sources | Layered source files at working resolution. |
| 9 | Turnaround renders | Front, side, back, plus hand close-ups. For documentation and supervisor review. |
| 10 | A short readme | Anything non-obvious: rig setup, constraints, correctives, known limits, what you would fix with more time. |

**Budgets** — this runs in a browser, on phones, next to a live camera feed:

| | |
|---|---|
| **Triangles** | **30k–60k** for the whole character. **Weight it toward the hands** — spending a quarter of the budget on two hands that are 3% of the volume is *correct* here, not a mistake. |
| **Textures** | 2K maximum. Fewer materials is better; one skin + one clothing is ideal. Avoid a material per body part. |
| **`.glb` size** | Under ~15 MB. Under 8 MB is better. |
| **Blendshapes** | Brow minimum, ARKit-52 preferred. No hundreds of correctives. |
| **Bones** | No hard cap, but every bone costs. No twist chains or helper bones the runtime cannot drive. |
| **Forbidden** | **No** rigid-body, cloth, hair, or physics of any kind. **No** drivers or constraints in the exported file. Everything deterministic under IK. |

---

## 12. Self-check before you send

These are the checks we will run. Running them yourself first turns a failed delivery into a
five-minute fix.

### A · Count the finger nodes in Blender

Paste into the Scripting workspace with the armature selected. Every line must read `4 nodes`.

```python
import bpy

arm = bpy.context.object          # select your armature first
for side in ('Left', 'Right'):
    for finger in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
        names = sorted(b.name for b in arm.data.bones
                       if b.name.startswith(side + 'Hand' + finger))
        flag = 'OK' if len(names) == 4 else '*** FAIL — need 4 ***'
        print(f'{side}Hand{finger}: {len(names)} nodes  {flag}  {names}')
```

### B · Confirm the nodes survived glTF export

**This is the check that matters**, because Blender can look right while the export drops the tips
(§6.2). Export the `.glb`, then either inspect the node tree in a glTF viewer, or run:

```python
python -c "
import json, struct, sys
f = open(sys.argv[1], 'rb'); f.read(12)
n, t = struct.unpack('<II', f.read(8))
g = json.loads(f.read(n))
names = [x.get('name','') for x in g['nodes']]
for side in ('Left','Right'):
    for fg in ('Thumb','Index','Middle','Ring','Pinky'):
        k = [x for x in names if x.startswith(side+'Hand'+fg)]
        print(side+'Hand'+fg, len(k), 'OK' if len(k)==4 else '*** FAIL ***', sorted(k))
" your_avatar.glb
```

*(Verified 2026-09-01 against a synthetic `.glb` with one finger deliberately at 3 nodes — it
correctly reports `*** FAIL ***` on that finger and `OK` on the rest, so the check can actually
fail.)*

### C · The rest of the list

- **Curl and extend every finger fully**, one at a time and all together. Look for tearing at the
  knuckles, palm ballooning, finger interpenetration.
- **Pose all seven handshapes** (§9) and check each reads unmistakably at 320 px tall.
- **Reach the extremes:** a hand fully overhead, a hand across the body to the opposite shoulder,
  elbow fully flexed, both hands meeting at the chest.
- **Put a hand on every contact zone in §8.** No gross interpenetration.
- **Drive the face:** brow full raise, full furrow, head shake ±30°, head tilt ±20°. No collar
  tearing, no neck pinch.
- **Check for unapplied transforms** on the armature and every mesh.
- **Load the `.glb` in a viewer** and confirm zero warnings.
- **Check the budgets** in §11.
- **View it at 320 px tall** against a plain background — how users will actually see it.

---

## 13. Acceptance tests

Run by script on delivery. They exist so "done" is a measurement rather than an opinion — which
protects you as much as us, because payment is not held up by subjective back-and-forth.

| # | Test | Pass condition |
|---|---|---|
| 1 | **Finger node count** | Every finger, both hands, has **4 transform nodes in the exported `.glb`**. 40 finger nodes + 2 wrists = **42**. Hard fail if any finger has 3. |
| 2 | **Distal keying** | Driven with a real clip, **every third-segment bone on both hands is actually posed.** The §6.2 regression test. |
| 3 | **Bone-length stability** | Every bone within 0.1% of rest length across a full 250-word playback. Catches stretchy IK. |
| 4 | Reference-pose retarget | Driven with `reference_pose.json`, wrists land within 5% of a shoulder-width of target. |
| 5 | Handshape reachability | All seven reachable and legible; **`B` and `5` measurably distinct** in bone-direction space. |
| 6 | Face channels | Brow raise, brow furrow, head shake ±30°, head tilt ±20° — all drivable, no tearing. |
| 7 | Extremes, no tearing | Full curl, full extension, arm overhead, hand to opposite shoulder, elbow fully flexed. |
| 8 | Contact zones | A hand at each §8 target: no gross interpenetration. |
| 9 | Budgets | Triangles, textures, file size within §11. |
| 10 | Loads clean | Loads in Three.js with no warnings; no unapplied transforms; no unsupported features. |

Tests **1, 2 and 3** are the ones that have actually bitten us. Expect them first, and expect test 1
at M2 rather than at delivery.

---

## 14. Milestones and scope

| M | You deliver | We check |
|---|---|---|
| **M1** | Concept: 2–3 style directions, silhouette, palette, your reasoning on §7.1. Blockout at correct proportions. | Register, legibility (§7.2), regional read. **Before any detailed modelling.** |
| **M2** | Skeleton only, no mesh detail. Full hierarchy, all 42 hand nodes, bone length table, **exported as `.glb`**. | **Tests 1 and 3.** The cheapest possible moment to catch §6.2 — and the reason we want a `.glb` this early. |
| **M3** | Hands: final topology, weights, all seven handshapes posed. Loaded in our test harness under real motion. | Tests 5 and 7. Hand quality review — the most important review in the project. |
| **M4** | Body, clothing, textures, face channels, rest pose. | Tests 6 and 8, plus every rule in §7.2. |
| **M5** | Final `.glb`, source, all ten deliverables from §11. | All ten tests. Sign-off. |

### Out of scope

- **The retargeting solver, the runtime, transitions, smoothing** — Ghozlan's.
- **Which signs exist, what they look like, ASL linguistics** — ours. Ask.
- **Animating anything.** You deliver poses, never animation clips.
- **Full 468-point face-mesh driving.** v2. Build the two channels in §6.4 and stop.
- **Lip sync and mouth shapes.** v2 — though ARKit-52 gets us there for free.
- **Legs, walking, locomotion, sitting.** Framing is waist-up.
- **Environments, lighting rigs, backgrounds, UI.**
- **Multiple characters, outfits, or customisation.** One character, done well.

---

## 15. Commercial terms to agree

Listed so nothing is discovered late. Figures are to be agreed — this is a checklist, not an offer.

| | |
|---|---|
| **Fee & schedule** | Total, and how it splits across the five milestones in §14. |
| **Timeline** | Target date per milestone, and what happens if a gate fails and needs rework. |
| **Revisions** | How many rounds are included per milestone, and what counts as a new request rather than a revision. |
| **IP & ownership** | We need full commercial rights to the character and the source files, including the right to modify them and ship them inside a commercial product. Say now if that is not your normal arrangement. |
| **Third-party assets** | **Declare every base mesh, texture pack, brush set, HDRI, or scan you use, with its licence.** Anything that cannot be redistributed commercially inside an application is unusable to us, however good it looks. |
| **Credit** | Whether you want to be credited, and how. |
| **Handover** | How files are transferred, and where they live afterwards. |

---

## 16. Reference material

You do not need to learn ASL. You do need to see enough that the requirements stop being abstract.

- **Watch real signing.** Search "ASL dictionary" and watch any twenty signs. Notice how much
  happens at the fingertips, how often the hands touch the face and chest, and how much the eyebrows
  move. That last one is §6.4 becoming obvious.
- **ASL handshape charts.** Search "ASL handshape chart" or "ASL manual alphabet" for the canonical
  forms of `A`, `B`, `C`, `O`, `S`, `1` and `5`. These are the shapes in §9, and they have correct
  and incorrect versions.
- **Existing signing avatars.** Search "signing avatar" — look at both the good and the
  widely-criticised ones. The common complaints are exactly our §7.3 concern: stiff, expressionless,
  uncanny.
- **The glTF viewer** — `gltf-viewer.donmccurdy.com`. Drop your `.glb` in and inspect the node tree.
  This is where §12-B happens.
- **Ask us for video reference on specific signs.** If a contact zone or a handshape is unclear,
  that is a question for us, not something to guess.

---

## 17. Before you start — please answer these

1. Which package do you work in, and can you deliver clean glTF 2.0 from it?
2. Are you comfortable with the **Mixamo naming convention** in §6.1, or would you rather deliver a
   name map?
3. Have you rigged hands for **IK-driven, position-target** animation before? If not, say so — it is
   learnable, and we would much rather plan for it than discover it at M3.
4. Can you deliver **ARKit-52 blendshapes**, or is the three-shape brow minimum more realistic for
   your pipeline?
5. Starting from scratch, or from a base mesh or commercial base (Avaturn, Ready Player Me,
   MetaHuman, Character Creator)? **A base is fine** — but many bases fail §6.2, so if you use one,
   **test 1 must pass at M2**, not at delivery. And confirm the base's licence permits commercial
   use and redistribution inside an application (§15).
6. Your estimate and rate against the five milestones in §14.
7. **Anything in this brief that looks wrong, unusual, or more expensive than it needs to be.** You
   will know things about rigging that we do not. Say so early — we would rather change the brief
   than pay for a workaround.

---

## Appendix — why the constraints are shaped this way

Not required reading. Here because a designer who understands the *why* makes better decisions on
the hundred things a brief cannot cover.

**Our source data recorded one hand per signer.** In the corpus behind the 250-word vocabulary, both
hands are present in **1.7%** of clips. So on every two-handed sign the passive hand is absent from
*every single take*, and its handshape must be synthesized from the seven-shape library in §9. What
*is* recorded in every frame is the passive **wrist**, because that is a body landmark rather than a
hand landmark. Hence the split that runs through this brief: position is given, shape is invented.

**The tracker loses the hand that moves.** Measured on our own export: median wrist speed is
**0.0208** shoulder-widths per frame when the hand *is* tracked, and **0.0317** when it is missing —
a 1.5× ratio. Two-handed signs are exactly where the hands cross and occlude each other, so the
dominant hand drops out most on the words that need it most. Of 87 two-handed words, **3 reach our
top quality tier and 39 fall to the bottom one.** Of 163 one-handed words, **zero** fall to the
bottom tier. This is a property of the source recordings, not of unfinished work — and it is the
concrete reason your character must look acceptable under interpolated, imperfect motion (§7.3).

**The face channel does not exist in our data.** We could recover 468 face landmarks from the
original video, but the corpus is *isolated single words* — signers performing one word at a time —
so their expressions are neutral and inconsistent rather than grammatical. A face rig driven by that
data would move without meaning anything. So the non-manual markers in §6.4 are **generated from
rules on our side**, keyed off the sentence we already parse. That needs no data at all — only a
rule and a rig. It is the one place in this entire system where we can add real linguistic structure
rather than replay recorded motion, and it is gated entirely on your rig having the two channels.
That is why §6.4 is a v1 requirement and not a v2 nice-to-have.

**Two of our lexicons are unreviewed by a Deaf signer.** The handshape templates and the
passive-hand placements were written from published phonology by a hearing developer. They are
honest about it in their own metadata, and a fluent reviewer will eventually disagree with some of
them. When that happens, **the fix is our lexicon, not your rig** — which is exactly why §9 asks for
clean, deliberate, separable handshapes. A crisp rig lets us tell a data error from a rig error. A
mushy one does not, and then every disagreement costs a week of argument.
