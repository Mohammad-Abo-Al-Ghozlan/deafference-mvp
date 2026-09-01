# Avatar Brief — PHASE 1: the skeleton and rig

**For:** the contracted 3D character artist / rigger
**From:** Deafference (Mohammed Salim, technical lead)
**Version:** 3.0 · 2026-09-01 · supersedes `AVATAR_DESIGNER_BRIEF.md`

> ## ⚠️ SCOPE — read this before anything else
>
> **This contract is for the SKELETON AND RIG only.** You are building a working, rigged,
> neutral grey **blockout** body — correct proportions, correct skeleton, correct hand rig,
> correct weights, no styling.
>
> **The character design is a separate later phase.** Style, silhouette, colour, clothing, face,
> textures, hair — none of that is decided yet and none of it is in this contract. We will decide
> it *after* we have a working skeleton, and quote it separately.
>
> **Why this way round:** the hardest and most expensive-to-fix requirement in this whole project
> is a rigging requirement (§6.2), and it has already burned us once. We would rather prove the
> skeleton works before anyone spends a day on how the avatar looks.
>
> §7 lists the design constraints the later phase will have to satisfy. **They are handed to you
> now, not to design against today, but so that nothing in phase 1 forecloses them.**

---

## 0. The message to send with this brief

*(Copy-paste for email or WhatsApp. Delete this section before sending the file itself.)*

> Hi — we're building a signing avatar for a Deaf-accessibility product (speech in, sign language
> out). We need a 3D character artist / rigger.
>
> We're splitting the job in two. **Right now we only want the skeleton and rig** — a working
> rigged blockout body, no styling, no clothing, no face detail. Once that's proven we'll decide
> the character design and quote that separately.
>
> The reason for that order is in the attached brief: the avatar is driven by measured motion-capture
> data, and there's one rigging requirement that is unusual, easy to miss, and expensive to fix
> late. We'd rather get it right before anyone works on how it looks.
>
> The brief is detailed on purpose — it assumes no sign-language knowledge and explains why each
> constraint exists. Please read §0 (scope), §4 (the five things that break it), and §6 (the spec),
> then answer the seven questions in §17 with an estimate.
>
> Happy to answer anything, including whether a requirement is worth what it costs.

---

## Who does what

| | |
|---|---|
| **The artist (you)** | **Phase 1:** the skeleton, the hand rig, the blockout body, the weights, the pose library. **Phase 2 (later, separate):** the character design. |
| **Ghozlan** (developer) | The runtime. Loads your rig in Three.js, solves the IK, blends between signs, smooths the motion. |
| **Salim** (us) | The motion data and the sign linguistics. We ship per-word landmark clips. We never touch your rig. |

You are **not animating.** You are building a **puppet driven by measured human motion** — 30 frames
a second of real Deaf signers' hands, recorded as points in space.

> **The one sentence that matters most.** A rig that looks perfect in your viewport can be
> **silently wrong** under this data. It will load, it will move, and nothing will report an error.
> That has already happened to us once, and §6.2 is the scar.

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
| **blockout** | Here: an unstyled grey body at final proportions. Phase 1's deliverable. Not a throwaway — see §5. |

---

## 2. What the product is

Deafference builds two-way communication between Deaf and hearing people. One direction listens to
speech and **signs it back**. That direction needs an avatar.

The pipeline: a hearing person speaks → we transcribe → we convert the sentence into an ordered list
of signs → we look up recorded motion per sign → **your rig performs them** → a Deaf person reads it.

Current vocabulary is **250 American Sign Language words**, played one after another. A clinical
vocabulary — symptoms, body parts, medication, hospital staff — is next. Our market is Lebanon, and
the eventual users are Deaf patients in clinics.

You do not need to know any of this to build the skeleton. It is here because §7's constraints only
make sense against it.

---

## 3. Why this is not normal rigging work

Three things will be unfamiliar if you have rigged for games or film. They are the source of almost
every requirement in §6.

### 3.1 We send positions, not rotations

Normally a rig receives *rotations* — an animator or a mocap solve tells each bone what angle to sit
at. **Our data has no angles in it at all.** It is a cloud of 75 point positions per frame, measured
off video.

So the runtime treats those points as **IK targets**: "put the wrist here, put the index fingertip
here", and solves backwards for the rotations. Two consequences:

- **Bones cannot stretch.** A solver reaching for a target will happily lengthen a bone if allowed,
  which tears the mesh and destroys §3.2. Lock it down.
- **Every point we send needs somewhere to go.** If our data has a fingertip position and your rig
  has no fingertip node, that data is silently discarded. This is §6.2 — the most important
  paragraph in this document, and the reason phase 1 exists as its own contract.

### 3.2 Depth is half-missing, and bone length is how we recover it

MediaPipe's depth (`z`) is unreliable as a *value*. What it gets right is the *sign* — whether a hand
is in front of or behind the plane. So the runtime reads one bit from `z` and reconstructs the
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

For phase 1 this means: **test your rig under bad input, not only under clean poses.** A rig that
only looks right at hand-authored keyframes is not delivered. Our test harness (§10) lets you drive
it with the real, messy data.

---

## 4. Five things that break the delivery silently

Each fails **without an error message.** The rig loads, the avatar moves, and it is wrong in a way
nobody notices for weeks. Four of the five are phase 1.

| # | Requirement | Phase | What happens if missed |
|---|---|---|---|
| **1** | **Every finger has four nodes** — three phalanx bones plus a tip node. | **1** | The last finger segment is never posed. On our current rig this left **the dominant hand's fingertips unposed on all 250 words**, including the 163 one-handed signs where that hand *is* the entire sign. Nobody saw it, because a bone at its bind rotation looks anatomically perfect. **§6.2** |
| **2** | **Bone lengths fixed and documented.** No stretchy IK, no scale channels on bones. | **1** | Depth is reconstructed from bone length (§3.2). A bone that can stretch makes it unsolvable, and the arms go flat or inside-out. **§6.3** |
| **3** | **`Head` and `Neck` bones exist and are properly weighted.** | **1** | Two of the four ASL grammar markers are a headshake and a head tilt. Bones survive a mesh change, so this is phase-1 work; the *brow blendshapes* are phase 2. **§6.4** |
| **4** | **Bare forearms with real anatomical form.** | **1** | Six signs contact the passive **forearm or wrist**, not the hand. A forearm modelled as a plain cylinder makes that contact read as a collision. **§8** |
| **5** | **The hands carry the polygon budget** — not the face, not the body. | **1** | The hands are the entire information channel. Even in a blockout, hand topology is where the quality has to be. **§11** |

---

## 5. What "the skeleton phase" actually delivers

The deliverable is **a rigged, skinned, neutral grey blockout human at final proportions** — not a
bare armature. Here is why, and why it is not throwaway work.

A bare armature with no mesh can only be tested for two things: node count and hierarchy. It cannot
be tested for **skinning, tearing at extremes, handshape legibility, or contact-zone behaviour** —
and those are half of what we need proven. So the blockout carries just enough geometry to test all
of it.

**Phase 2 dresses and details this body. It does not replace it.** The proportions, the skeleton,
and the hand topology you deliver in phase 1 are the foundation the final character is built on. So
build them at final quality.

### ⚠️ The one design decision phase 1 cannot defer

**How stylized the final character will be affects its proportions** — and proportions are exactly
what phase 1 locks. If we defer that decision entirely and later choose a heavily stylized look,
part of your phase-1 work becomes disposable.

So we are pinning it now, and only it:

> **The character will be a normally proportioned adult human, roughly 1.7 m, with hands 5–10%
> larger than photoreal.** Not chibi, not heroic, not heavily stylized in proportion.

That protects phase 1 while leaving every genuinely aesthetic choice — surfacing style, colour,
clothing, face, hair, gender presentation, regional read — fully open for phase 2. Hands are
oversized for a functional reason, not an aesthetic one: legibility at phone size (§7.2).

### What is locked in phase 1

| Locked now | Why it cannot wait |
|---|---|
| Skeleton hierarchy and bone names | The runtime already drives these names (§6.1). |
| **4 nodes per finger** | The defect. §6.2. |
| Bone lengths, fixed and documented | Depth reconstruction. §6.3. |
| Overall proportions, ~1.7 m adult human | Phase 2 builds on them; changing them later is rework. |
| Hands 5–10% oversized | Functional legibility, not style. |
| Hand topology and weights | Half the project's quality lives here. |
| `Head` / `Neck` bones and their weights | Bones survive a mesh change; blendshapes do not. |
| Bare forearms with anatomical form | Contact zones. §8. |
| A-pose bind + a neutral signing rest pose | Both are structural. §6.5. |

### What is deferred to phase 2

Style · silhouette · colour palette · clothing and costume · face design · hair · skin and material
treatment · textures · gender presentation · regional read · **brow blendshapes** (they are per-mesh,
so building them on a blockout head would be wasted) · the ARKit-52 set.

**§7 constrains all of it.** Read §7 now even though you are not designing yet — it exists so phase 1
does not paint phase 2 into a corner.

---

## 6. The rig specification

Pass/fail, and checked by script (§13).

### 6.1 Skeleton — required joints

Use **Mixamo naming**. This is not a preference: we extracted every animated bone name from the
existing runtime, and these are the names it already drives.

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
| Legs | optional | Framing is waist-up. Include if free; they are never driven. |

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
> In Blender a finger of **3 bones** already gives 4 joint *positions* (three bone heads plus the
> last bone's tail), so it looks correct while you work. But **glTF export writes one node per
> bone.** The final tail is not a bone, so it does not become a node, and the exported `.glb` has
> only three.
>
> **The fix: give every finger a fourth bone.** A short tip bone, parented to the distal phalanx,
> with no vertex weights. It carries no deformation — it exists so the exported file has a node at
> the fingertip. Name it `…Index4`, or let Blender's `…Index3_end` convention through, and confirm
> it survives export.
>
> **Verify on the exported file, not in the viewport.** §12 has a paste-in check.

**Topology and weighting, hands.** This is the highest-value work in phase 1 — spend the time here.

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
> **Build a normally proportioned human** (§5). The reference pose exists to *test the retarget*,
> not to model from. Proportion mismatch between our signers and your character is expected and
> handled — the runtime derives per-limb scale factors at load. Your job is to be internally
> consistent and documented.
>
> Sanity figures only, in shoulder-widths: shoulder→hip ≈ **1.00** · nose→shoulder-midpoint ≈
> **0.70** · wrist→middle-fingertip ≈ **0.19**.

### 6.4 The face — bones now, blendshapes in phase 2

**Why the face matters at all.** ASL grammar is not carried by the hands alone. A raised eyebrow
turns a statement into a yes/no question. A headshake is how you negate. Held *across* the sign,
simultaneously with it. Today our system emits the **identical** hand motion for "you have pain" and
"do you have pain?", and there is no way to tell them apart.

| marker | grammar | rendered as | phase |
|---|---|---|---|
| `q` | yes/no question | brow raise, held for the whole sign | 2 |
| `wh` | wh-question — who, what, where, why | brow furrow + slight head tilt | 2 + **1** |
| `neg` | negation | **headshake** across the sign | **1** |
| `top` | topic marker | brow raise on the topicalised sign only | 2 |

**Phase 1 requirement — the head and neck bones.**

`Head` and `Neck` must be freely rotatable and weighted to survive a **±30° shake** and a **±20°
tilt** with no collar tearing and no neck pinching. Bones survive a mesh change, so this work is
permanent even though the head geometry is not.

**Phase 2 requirement — the brow channel.** Blendshapes are per-mesh, so building them on a blockout
head would be wasted. They get built natively on the final head. Two things phase 1 must not
foreclose:

1. **The blockout head must have brow geometry** — enough of a brow ridge and enough topology that a
   raise and a furrow are demonstrably achievable. A featureless egg head fails this.
2. **A one-shape proof.** Deliver a single crude `browRaise` shape on the blockout, purely to prove
   the topology supports it. Not a full set, not final quality — a feasibility check.

> **Carried forward as a locked constraint on phase 2:** the final head ships at minimum
> `browInnerUp`, `browDownLeft`, `browDownRight`, and preferably the full **ARKit 52** set. And the
> brows must be **visible** — no fringe over the forehead, no glasses, no brow-obscuring hair. A brow
> channel nobody can see is not a channel, and it is easy to design one away without noticing.

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
| **Mesh** | Single skinned mesh preferred. No modifiers left unapplied except the armature. |

---

## 7. Constraints the character design will have to satisfy

**You are not designing yet.** This section exists so that phase 1 does not foreclose phase 2, and
so you know the box the design will have to fit inside when we get there. Read it; do not act on it
beyond §5's locked proportions.

### 7.1 Who the character is for

A **Deaf or hard-of-hearing person, in a clinic or hospital, possibly frightened, trying to
understand a doctor.** Our market is Lebanon. The near-term vocabulary is clinical.

The eventual design will need to be: **trustworthy and calm** (this character delivers medical
information — not cute, not a mascot); **professionally plausible** without implying a specific real
hospital or credential; **regionally plausible** for a Levantine audience; and **respectful of the
Deaf community**, whose language this is.

### 7.2 Legibility rules — these will override aesthetics

The hands carry **100% of the lexical content.** Anything that reduces hand legibility is a
functional defect, not a style choice. These bind phase 2:

- **Hands must contrast strongly against the torso.** Very many signs are performed directly in
  front of the chest, so a skin-toned top makes those signs vanish. Mid-to-dark, **solid,
  unpatterned** torso. No stripes, no logos, no busy texture.
- **Sleeves end at or above the elbow.** Six signs contact the passive forearm or wrist (§8).
- **No jewellery, watch, rings, gloves, bracelets, or long nails.** All of it occludes handshape.
- **Hands 5–10% larger than photoreal.** Already locked in §5 — functional, not aesthetic.
- **Face clear:** brows visible, no glasses, hair off the forehead, no beard obscuring the chin —
  several signs contact the chin (§8).
- **Everything must read at 320 px tall.** Roughly the real size on a phone.

### 7.3 Style: stylized, not realistic — and this is a technical argument

When we get to phase 2 the recommendation will be **stylized-realistic**: clean, appealing,
recognisably human, clearly not photoreal. Think a well-made explainer character rather than a game
hero or a MetaHuman.

The reason is not taste. Re-read §3.3: our motion is jittery, drops out, and is interpolated. A
*photorealistic* human moving with those artefacts sits squarely in the uncanny valley and reads as
unsettling — the worst possible register for a medical tool used by someone already anxious. A
stylized character with identical motion reads as *animated*, and the same artefacts become
stylistic instead of disturbing.

**This is why §5 pins proportions but not surfacing.** Stylized-realistic keeps human proportions,
so phase 1's blockout stays valid.

### 7.4 Framing and the signing space

- The camera sees roughly **top of head to waist**, front-on.
- The **signing space** extends about **±0.75 shoulder-widths** either side of body centre, and from
  just above the head to the waist — a box about 1.5 shoulder-widths wide. Signs go above the head
  and out to the sides; **the rig must work with a hand anywhere in that box**, which is a phase-1
  concern, not just a framing one.
- Plain background supplied by the app. No environment, ever.

---

## 8. What the hands touch

ASL signs make contact with the signer's **own body** — at speed, repeatedly, driven by an IK solver
with **no collision handling whatsoever.** This is a phase-1 concern because it constrains the
blockout's *form*, not just its styling.

| Target | Example signs | What the blockout must support |
|---|---|---|
| **Forehead** | man, father | Clean forehead surface; the hand arrives flat against it. |
| **Chin / lower face** | woman, mother | Reachable chin, not sunk into the neck. |
| **Mouth area** | eat, drink, tongue | The hand comes very close. Keep it unobstructed. |
| **Chest / sternum** | heart, feel, lungs, tired, sick | A broad, clean, near-flat chest plane. |
| **Passive forearm** | arm, table, tree, flag, morning | **Bare forearm with real anatomical form.** The dominant hand *slides along* it — a plain cylinder reads as a collision. |
| **Passive wrist** | time | Precise contact on a small target. Readable wrist form. |
| **Passive hand** | 29 of the 35 asymmetric signs | Hand-on-hand contact — palms and knuckles meet. |
| **Ear · nose · eye · head** | ear, nose, eye, head | Reachable, with enough form to land on. |

Note the orientation: the dominant hand is always the **right** one, so the passive forearm and
wrist it acts on are on the signer's **left** — the viewer's right in a front view.

We are **not** asking for collision solving. We are asking for a body whose contact surfaces are
forgiving when a hand lands on them approximately. **Phase 2 must not undo this** — that is why
sleeves and hair are constrained in §7.2.

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

**Phase-1 deliverable: hand-pose all seven, as named poses.** Save them as named pose assets in the
source file and deliver reference renders (front and side of the hand). Two reasons: it proves the
hand rig can hit them crisply, and it gives us a human-authored reference to check our measured
templates against.

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
| 250 per-word clips | Real landmark motion, one file per word. This is what will drive your rig. |
| `contact_sheet.png` | Rendered stick-figure previews of the whole vocabulary. **Look at this early** — it shows the real range of motion better than any description. |
| A test harness | Ghozlan's existing player. Load your rig and watch it move under real data *before* final delivery. **Use it at P1-M3, not at the end.** |
| Us | Ask early and often. A question answered in week one is free; a rebuild in week four is not. |

**Ask for anything else you need.** Especially: if you want video reference of real signers
performing these signs, say so and we will point you at it. **Do not guess at what a sign looks
like** — specifying that is our job, not yours to invent.

---

## 11. What you deliver in phase 1

| # | Deliverable | Format & notes |
|---|---|---|
| 1 | **Rigged blockout character** | **glTF 2.0 `.glb`**, single file. Neutral grey, no styling, final proportions, fully skinned. |
| 2 | Editable source | `.blend` preferred, or `.ma`/`.mb`, with the full rig stack intact and nothing collapsed. |
| 3 | **Bone length table** | JSON or CSV — every bone, rest length, in rig units (§6.3). |
| 4 | Bone name map | JSON. *Only* if you deviated from the §6.1 names. |
| 5 | **Seven handshape poses** | Named pose assets in the source + front/side reference renders (§9). |
| 6 | Neutral signing rest pose | A named pose, plus a render (§6.5). |
| 7 | **`browRaise` feasibility shape** | One crude blendshape on the blockout head, proving the topology supports a brow channel (§6.4). |
| 8 | Turnaround renders | Front, side, back, plus hand close-ups at full curl and full extension. |
| 9 | A short readme | Rig setup, constraints used, known limits, and **anything phase 2 must not break**. |

**Budgets** — this runs in a browser, on phones, next to a live camera feed:

| | |
|---|---|
| **Triangles** | **Blockout: 20k–40k.** Final character will be 30k–60k. **Weight it toward the hands** — spending a quarter of the budget on two hands that are 3% of the volume is *correct* here. |
| **Textures** | None needed in phase 1. Flat grey material. |
| **`.glb` size** | Trivially small without textures. Keep it clean. |
| **Blendshapes** | One (`browRaise`, item 7). Nothing else. |
| **Bones** | No hard cap, but every bone costs. No twist chains or helper bones the runtime cannot drive. |
| **Forbidden** | **No** rigid-body, cloth, hair, or physics. **No** drivers or constraints in the exported file. Everything deterministic under IK. |

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
correctly reports `*** FAIL ***` on that finger and `OK` on the other nine, so the check can
actually fail.)*

### C · The rest of the list

- **Curl and extend every finger fully**, one at a time and all together. Look for tearing at the
  knuckles, palm ballooning, finger interpenetration.
- **Pose all seven handshapes** (§9) and check each reads unmistakably at 320 px tall.
- **Reach the extremes:** a hand fully overhead, a hand across the body to the opposite shoulder,
  elbow fully flexed, both hands meeting at the chest.
- **Put a hand on every contact zone in §8.** No gross interpenetration.
- **Rotate the head:** shake ±30°, tilt ±20°. No collar tearing, no neck pinch.
- **Drive it with our real data** in the test harness. Not just hand-authored poses — §3.3.
- **Check for unapplied transforms** on the armature and every mesh.
- **Load the `.glb` in a viewer** and confirm zero warnings.

---

## 13. Acceptance tests

Run by script on delivery. They exist so "done" is a measurement rather than an opinion — which
protects you as much as us, because payment is not held up by subjective back-and-forth.

| # | Test | Pass condition | Phase |
|---|---|---|---|
| 1 | **Finger node count** | Every finger, both hands, has **4 transform nodes in the exported `.glb`**. 40 finger nodes + 2 wrists = **42**. Hard fail if any finger has 3. | **1** |
| 2 | **Distal keying** | Driven with a real clip, **every third-segment bone on both hands is actually posed.** The §6.2 regression test. | **1** |
| 3 | **Bone-length stability** | Every bone within 0.1% of rest length across a full 250-word playback. Catches stretchy IK. | **1** |
| 4 | Reference-pose retarget | Driven with `reference_pose.json`, wrists land within 5% of a shoulder-width of target. | **1** |
| 5 | Handshape reachability | All seven reachable and legible; **`B` and `5` measurably distinct** in bone-direction space. | **1** |
| 6 | Head range | Shake ±30°, tilt ±20°, no tearing. Plus the `browRaise` feasibility shape exists. | **1** |
| 7 | Extremes, no tearing | Full curl, full extension, arm overhead, hand to opposite shoulder, elbow fully flexed. | **1** |
| 8 | Contact zones | A hand at each §8 target: no gross interpenetration. | **1** |
| 9 | Budgets | Triangles and file size within §11. | **1** |
| 10 | Loads clean | Loads in Three.js with no warnings; no unapplied transforms; no unsupported features. | **1** |
| 11 | Brow blendshape set | Minimum three brow shapes, ARKit-52 preferred. | 2 |
| 12 | Legibility rules | Every rule in §7.2 satisfied. | 2 |

Tests **1, 2 and 3** are the ones that have actually bitten us. Expect them first, and expect test 1
at **P1-M1** rather than at delivery.

---

## 14. Phase 1 milestones

Each gate is cheap to fix at that point and expensive to fix later. We would rather review four
times than once, and we will turn reviews around quickly.

| M | You deliver | We check |
|---|---|---|
| **P1-M1** | **Skeleton only.** Full hierarchy, all 42 hand nodes, bone length table, proportions agreed. **Exported as `.glb`.** | **Tests 1 and 3.** The cheapest possible moment to catch §6.2 — and the whole reason we want a `.glb` this early, before any mesh work. |
| **P1-M2** | Blockout body at locked proportions, skinned, with the arms and torso weighted. | Tests 4 and 7. Contact-zone form (§8). |
| **P1-M3** | **Hands: final topology and weights, all seven handshapes posed.** Loaded in our test harness under real motion. | Tests 5 and 8. **The most important review in the project.** |
| **P1-M4** | Head/neck weights, `browRaise` shape, rest pose, final `.glb` + source + all nine deliverables from §11. | Tests 6, 9, 10, and a re-run of everything. Sign-off. |

**Phase 2 is quoted separately** once P1-M4 is signed off and we have decided the design direction.

### Out of scope for phase 1

- **Any character design** — style, colour, clothing, face design, hair, textures, materials.
- **Brow blendshapes beyond the single feasibility shape** (§6.4).
- **The retargeting solver, the runtime, transitions, smoothing** — Ghozlan's.
- **Which signs exist, what they look like, ASL linguistics** — ours. Ask.
- **Animating anything.** You deliver poses, never animation clips.
- **Full 468-point face-mesh driving.** Not in either phase yet.
- **Lip sync and mouth shapes.** Later.
- **Legs, walking, locomotion, sitting.** Framing is waist-up.
- **Environments, lighting rigs, backgrounds, UI.**

---

## 15. Commercial terms to agree

Listed so nothing is discovered late. Figures are to be agreed — this is a checklist, not an offer.

| | |
|---|---|
| **Phase 1 fee & schedule** | Total for phase 1, and how it splits across the four milestones in §14. |
| **Phase 2** | Indicative range only, so we can budget. Not committed on either side yet. |
| **Timeline** | Target date per milestone, and what happens if a gate fails and needs rework. |
| **Revisions** | How many rounds are included per milestone, and what counts as a new request rather than a revision. |
| **IP & ownership** | We need full commercial rights to the rig and the source files, including the right to modify them and ship them inside a commercial product — **and the right to have phase 2 done by someone else if we choose.** Say now if that is not your normal arrangement. |
| **Third-party assets** | **Declare every base mesh, rig, texture pack, or scan you use, with its licence.** Anything that cannot be redistributed commercially inside an application is unusable to us, however good it looks. This matters most for base rigs. |
| **Credit** | Whether you want to be credited, and how. |
| **Handover** | How files are transferred, and where they live afterwards. |

---

## 16. Reference material

You do not need to learn ASL. You do need to see enough that the requirements stop being abstract.
An hour here is well spent.

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
   learnable, and we would much rather plan for it than discover it at P1-M3.
4. Starting from scratch, or from a base mesh or base rig (Avaturn, Ready Player Me, MetaHuman,
   Character Creator, Rigify)? **A base is fine** — but many bases fail §6.2, so if you use one,
   **test 1 must pass at P1-M1.** And confirm the licence permits commercial use and redistribution
   inside an application (§15).
5. **Your estimate and rate for phase 1**, against the four milestones in §14.
6. **Do you also want phase 2** (the character design), and roughly what would that cost? Not a
   commitment — we want to know whether to plan for one artist or two.
7. **Anything in this brief that looks wrong, unusual, or more expensive than it needs to be.** You
   will know things about rigging that we do not. Say so early — we would rather change the brief
   than pay for a workaround.

---

## Appendix — why the constraints are shaped this way

Not required reading. Here because someone who understands the *why* makes better decisions on the
hundred things a brief cannot cover.

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
concrete reason the rig must be tested under real, messy data (§3.3) rather than hand-authored poses.

**The face channel does not exist in our data.** We could recover 468 face landmarks from the
original video, but the corpus is *isolated single words* — signers performing one word at a time —
so their expressions are neutral and inconsistent rather than grammatical. A face rig driven by that
data would move without meaning anything. So the non-manual markers in §6.4 are **generated from
rules on our side**, keyed off the sentence we already parse. That needs no data at all — only a rule
and a rig. It is the one place in this entire system where we can add real linguistic structure
rather than replay recorded motion, which is why the head bones are a phase-1 requirement even
though the face design is deferred.

**Two of our lexicons are unreviewed by a Deaf signer.** The handshape templates and the
passive-hand placements were written from published phonology by a hearing developer. They are
honest about it in their own metadata, and a fluent reviewer will eventually disagree with some of
them. When that happens, **the fix is our lexicon, not your rig** — which is exactly why §9 asks for
clean, deliberate, separable handshapes. A crisp rig lets us tell a data error from a rig error. A
mushy one does not, and then every disagreement costs a week of argument.
