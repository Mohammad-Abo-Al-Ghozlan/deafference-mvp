# Avatar Brief — PHASE 1: the skeleton and rig

**For:** the contracted 3D character artist / rigger
**From:** Deafference (Mohammed Salim, technical lead)
**Version:** 4.0 · 2026-09-01

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
> is a rigging requirement (§6.3), and it has already shipped broken once. We would rather prove
> the skeleton works before anyone spends a day on how the avatar looks.
>
> §8 lists the design constraints the later phase will have to satisfy. **They are handed to you
> now, not to design against today, but so that nothing in phase 1 forecloses them.**

---

## Contents

| | |
|---|---|
| **§0** | The message to send with this brief |
| **§1** | Glossary — our words in your terms |
| **§2** | What the product is |
| **§3** | Why this is not normal rigging work |
| **§4** | Five things that break the delivery silently |
| **§5** | What "the skeleton phase" actually delivers |
| **§6** | **The rig specification** — the technical core |
| | 6.1 Naming rules and the three ways naming fails |
| | 6.2 **The complete bone list — all 55 bones** |
| | 6.3 The hand rig: four nodes per finger |
| | 6.4 Where the joints actually go |
| | 6.5 Required ranges of motion |
| | 6.6 Bone orientation, roll, and symmetry |
| | 6.7 Skinning: weights, the 4-influence limit, and the twist problem |
| | 6.8 Bone lengths |
| | 6.9 The face — bones now, blendshapes in phase 2 |
| | 6.10 Orientation, units, bind pose |
| | 6.11 glTF export settings |
| **§7** | The 21-point hand layout and what drives what |
| **§8** | Constraints the character design will have to satisfy |
| **§9** | What the hands touch |
| **§10** | The seven handshapes |
| **§11** | What we give you |
| **§12** | What you deliver |
| **§13** | Self-check before you send |
| **§14** | Acceptance tests |
| **§15** | Milestones and scope |
| **§16** | Commercial terms to agree |
| **§17** | Reference material |
| **§18** | Questions to answer before you start |
| **§19** | One-page checklist |

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
> The reason for that order is in the attached brief: the avatar is driven by measured
> motion-capture data, and there's one rigging requirement that is unusual, easy to miss, and
> expensive to fix late. We'd rather get it right before anyone works on how it looks.
>
> The brief is long on purpose — it assumes no sign-language knowledge, gives you the complete
> bone list, and explains why each constraint exists. If you're short on time, read §4 (the five
> things that break it), §6.2 (the bone list) and §6.3 (the requirement), then answer the
> questions in §18 with an estimate.
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
> That has already happened to us once, and §6.3 is the scar.

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
| **handshape** | The finger configuration, treated in sign languages as a distinct unit — like a phoneme. ASL has a fixed inventory with names like **B** (flat), **A** (fist), **1** (index pointing). We use seven (§10). |
| **dominant hand** | A signer's main hand. Our data is normalised so **the dominant hand is always the right one.** Do not try to infer it. |
| **passive hand** | The other hand. In two-handed signs it either mirrors the dominant hand or holds still as a "base" the dominant hand acts on. **Usually missing from our recordings** and synthesized — hence §10. |
| **one- / two-handed** | 163 of our 250 words are one-handed, 87 two-handed. The two-handed ones are where all the difficulty lives. |
| **non-manual marker** | Grammar carried on the **face and head** rather than the hands — a raised brow makes a sentence a question, a headshake negates it. Not decoration: a sentence without them is closer to ungrammatical. §6.9. |
| **shoulder width** | Our unit. All measurements are divided by the signer's shoulder width, so they are person-independent. "0.19 shoulder-widths" = 19% of the distance between the shoulder joints. |
| **MCP · PIP · DIP · TIP** | The four joints of a finger, base to tip: knuckle, middle joint, last joint, fingertip. Thumb: CMC, MCP, IP, TIP. **Four positions per finger** — that number is the whole of §6.3. |
| **abduction** | Fingers spreading apart sideways, as opposed to curling. Required, and often missing from quick rigs — §6.5. |
| **pronation / supination** | Forearm twist — turning the palm down / up. A *linguistic* distinction in sign language, so it is a hard requirement — §6.7. |
| **bind rotation** | A bone's rest orientation before animation touches it. A bone nobody animates sits at its bind rotation and **looks anatomically perfect** — which is how our worst bug hid for weeks. |
| **keyed track** | An animation channel that actually contains data for a bone. A bone with no keyed track is not animated at all. Counting these is how we found the §6.3 bug. |
| **blockout** | Here: an unstyled grey body at final proportions. Phase 1's deliverable. Not a throwaway — see §5. |
| **LBS** | Linear blend skinning — the only skinning glTF supports. Relevant to §6.7. |

---

## 2. What the product is

Deafference builds two-way communication between Deaf and hearing people. One direction listens to
speech and **signs it back**. That direction needs an avatar.

The pipeline: a hearing person speaks → we transcribe → we convert the sentence into an ordered list
of signs → we look up recorded motion per sign → **your rig performs them** → a Deaf person reads it.

Current vocabulary is **250 American Sign Language words**, played one after another. A clinical
vocabulary — symptoms, body parts, medication, hospital staff — is next. Our market is Lebanon, and
the eventual users are Deaf patients in clinics.

You do not need to know any of this to build the skeleton. It is here because §8's constraints only
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
here", and solves backwards for the rotations. Three consequences:

- **Bones cannot stretch.** A solver reaching for a target will happily lengthen a bone if allowed,
  which tears the mesh and destroys §3.2. Lock it down.
- **Every point we send needs somewhere to go.** If our data has a fingertip position and your rig
  has no fingertip node, that data is silently discarded. This is §6.3 — the most important section
  in this document, and the reason phase 1 exists as its own contract.
- **Twist is underdetermined.** Aiming a bone at a target fixes two rotational degrees of freedom,
  not three. The roll around the bone's own axis is not determined by the target, which is why
  §6.6's roll conventions matter more here than in a normal rig.

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
only looks right at hand-authored keyframes is not delivered. Our test harness (§11) lets you drive
it with the real, messy data.

---

## 4. Five things that break the delivery silently

Each fails **without an error message.** The rig loads, the avatar moves, and it is wrong in a way
nobody notices for weeks. All five are phase 1.

| # | Requirement | What happens if missed |
|---|---|---|
| **1** | **Every finger has four nodes** — three phalanx bones plus a tip node. | The last finger segment is never posed. On our current rig this left **the dominant hand's fingertips unposed on all 250 words**, including the 163 one-handed signs where that hand *is* the entire sign. Nobody saw it, because a bone at its bind rotation looks anatomically perfect. **§6.3** |
| **2** | **Bone lengths fixed and documented.** No stretchy IK, no scale channels on bones. | Depth is reconstructed from bone length (§3.2). A bone that can stretch makes it unsolvable, and the arms go flat or inside-out. **§6.8** |
| **3** | **Fingers must ABDUCT, not only curl.** | Handshape `B` is fingers *together*; handshape `5` is the same fingers *spread*. If MCP joints only flex, those two handshapes are indistinguishable — and `B` is used by 26 of our 35 two-handed base signs. **§6.5** |
| **4** | **±90° of forearm twist without shearing the elbow.** | Palm-up versus palm-down is a *linguistic* distinction, not a stylistic one. glTF is linear-blend-skinning only, so you cannot solve this by switching skinning mode. **§6.7** |
| **5** | **`Head` and `Neck` bones exist and are properly weighted.** | Two of the four ASL grammar markers are a headshake and a head tilt. Bones survive a mesh change, so this is phase-1 work; the *brow blendshapes* are phase 2. **§6.9** |

---

## 5. What "the skeleton phase" actually delivers

The deliverable is **a rigged, skinned, neutral grey blockout human at final proportions** — not a
bare armature. Here is why, and why it is not throwaway work.

A bare armature with no mesh can only be tested for two things: node count and hierarchy. It cannot
be tested for **skinning, tearing at extremes, handshape legibility, twist behaviour, or
contact-zone form** — and those are most of what we need proven. So the blockout carries just enough
geometry to test all of it.

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
oversized for a functional reason, not an aesthetic one: legibility at phone size (§8.2).

### What is locked in phase 1 · what is deferred

| Locked now | Why it cannot wait |
|---|---|
| Skeleton hierarchy and **exact bone names** | The runtime already drives these names (§6.2). |
| **4 nodes per finger** | The defect. §6.3. |
| Joint placement, roll conventions, symmetry | Everything downstream inherits them. §6.4, §6.6. |
| Ranges of motion, including abduction and twist | Handshape distinctions depend on them. §6.5. |
| Bone lengths, fixed and documented | Depth reconstruction. §6.8. |
| Overall proportions, ~1.7 m adult human | Phase 2 builds on them; changing them later is rework. |
| Hands 5–10% oversized | Functional legibility, not style. |
| Hand topology and weights | Half the project's quality lives here. |
| `Head` / `Neck` bones and their weights | Bones survive a mesh change; blendshapes do not. |
| Bare forearms with anatomical form | Contact zones. §9. |
| A-pose bind + a neutral signing rest pose | Both are structural. §6.10. |

**Deferred to phase 2:** style · silhouette · colour palette · clothing and costume · face design ·
hair · skin and material treatment · textures · gender presentation · regional read · **brow
blendshapes** (they are per-mesh, so building them on a blockout head would be wasted) · the
ARKit-52 set.

**§8 constrains all of it.** Read §8 now even though you are not designing yet — it exists so phase 1
does not paint phase 2 into a corner.

---

## 6. The rig specification

Pass/fail, and checked by script (§14).

### 6.1 Naming rules, and the three ways naming fails

Use **Mixamo naming**, exactly as spelled in §6.2. This is not a preference: we extracted every
animated bone name from the existing runtime, and these are the names it already drives. A mismatch
means either a mapping table or a silent failure.

**The rules:**

- **Exact case.** `LeftHandIndex1`. Not `leftHandIndex1`, not `LEFTHANDINDEX1`.
- **No prefix.** `LeftArm`, **not** `mixamorig:LeftArm`. Blender's FBX importer adds that prefix —
  strip it.
- **No separators.** No underscores, no spaces, no dots, no hyphens. `LeftHandIndex1`, not
  `Left_Hand_Index_01` or `Left.Hand.Index.1`.
- **`Left`/`Right` as a prefix**, not an `.L`/`.R` suffix.

**Three specific traps, all of which we would rather you hit now than at delivery:**

1. **Blender's `.001` suffix.** Duplicating a bone gives `LeftHandIndex1.001`. That does *not* match
   `LeftHandIndex1`, and nothing will warn you. Search your armature for `.00` before exporting.
2. **Blender's mirror convention is `.L` / `.R`.** If you build one hand and use Symmetrize or
   `Ctrl+M`, you will get `HandIndex1.L` / `HandIndex1.R`, which is the wrong scheme entirely.
   Mirror first, rename after — or script the rename.
3. **Auto-rig / Rigify output names differ.** Rigify produces `DEF-`/`ORG-`/`MCH-` prefixed bones
   and its own finger naming (`f_index.01.L`). If you rig with Rigify, you must produce a clean
   export skeleton with our names. Budget for it, and say so in your estimate.

**If you would rather keep your own convention**, that is acceptable — deliver a JSON map
(`{"your_name": "OurName", …}`) covering all 55 bones. Say so at §18 question 2 so we plan for it.

### 6.2 The complete bone list — all 55 bones

Every bone, its parent, and the landmark index that drives it. **This is the checklist. Nothing here
is optional except the legs.**

The **landmark** column is the index in our 75-point data (see §7). A dash means the bone is not
driven directly by a landmark — it is either structural or solved by the IK chain.

#### Torso, neck and head — 7 bones

| # | bone | parent | landmark | note |
|---|---|---|---|---|
| 1 | `Hips` | *(root)* | — | Scene root. Not driven. |
| 2 | `Spine` | `Hips` | — | Not driven directly. |
| 3 | `Spine1` | `Spine` | — | Not driven directly. |
| 4 | `Spine2` | `Spine1` | — | Both clavicles hang from here. |
| 5 | `Neck` | `Spine2` | — | Carries part of the head rotation. |
| 6 | `Head` | `Neck` | `0` (nose) | **GRAMMAR CHANNEL** — shake and tilt. §6.9. |
| 7 | `HeadTop_End` | `Head` | — | Leaf node. Orientation reference. |

#### Left arm and hand — 24 bones

| # | bone | parent | landmark | note |
|---|---|---|---|---|
| 8 | `LeftShoulder` | `Spine2` | — | Clavicle. No landmark; absorbs overhead and cross-body reach. |
| 9 | `LeftArm` | `LeftShoulder` | `11` (L shoulder) | Upper arm. IK chain root. |
| 10 | `LeftForeArm` | `LeftArm` | `13` (L elbow) | IK mid-chain. **Also a contact surface** — §9. |
| 11 | `LeftHand` | `LeftForeArm` | `15` (L wrist) + `33` | **PRIMARY IK TARGET.** |
| 12 | `LeftHandThumb1` | `LeftHand` | `34` | Thumb CMC — **deep in the palm, see §6.4.** |
| 13 | `LeftHandThumb2` | `LeftHandThumb1` | `35` | Thumb MCP |
| 14 | `LeftHandThumb3` | `LeftHandThumb2` | `36` | Thumb IP |
| 15 | `LeftHandThumb4` | `LeftHandThumb3` | `37` | **TIP NODE — the one missing today** |
| 16 | `LeftHandIndex1` | `LeftHand` | `38` | Index MCP (knuckle) |
| 17 | `LeftHandIndex2` | `LeftHandIndex1` | `39` | Index PIP |
| 18 | `LeftHandIndex3` | `LeftHandIndex2` | `40` | Index DIP |
| 19 | `LeftHandIndex4` | `LeftHandIndex3` | `41` | **TIP NODE — the one missing today** |
| 20 | `LeftHandMiddle1` | `LeftHand` | `42` | Middle MCP |
| 21 | `LeftHandMiddle2` | `LeftHandMiddle1` | `43` | Middle PIP |
| 22 | `LeftHandMiddle3` | `LeftHandMiddle2` | `44` | Middle DIP |
| 23 | `LeftHandMiddle4` | `LeftHandMiddle3` | `45` | **TIP NODE — the one missing today** |
| 24 | `LeftHandRing1` | `LeftHand` | `46` | Ring MCP |
| 25 | `LeftHandRing2` | `LeftHandRing1` | `47` | Ring PIP |
| 26 | `LeftHandRing3` | `LeftHandRing2` | `48` | Ring DIP |
| 27 | `LeftHandRing4` | `LeftHandRing3` | `49` | **TIP NODE — the one missing today** |
| 28 | `LeftHandPinky1` | `LeftHand` | `50` | Pinky MCP |
| 29 | `LeftHandPinky2` | `LeftHandPinky1` | `51` | Pinky PIP |
| 30 | `LeftHandPinky3` | `LeftHandPinky2` | `52` | Pinky DIP |
| 31 | `LeftHandPinky4` | `LeftHandPinky3` | `53` | **TIP NODE — the one missing today** |

#### Right arm and hand — 24 bones

Identical structure. **The right hand is the dominant hand in all our data**, so it carries the
lexical content of every one-handed sign — but build both to the same standard.

| # | bone | parent | landmark | note |
|---|---|---|---|---|
| 32 | `RightShoulder` | `Spine2` | — | Clavicle. |
| 33 | `RightArm` | `RightShoulder` | `12` (R shoulder) | Upper arm. IK chain root. |
| 34 | `RightForeArm` | `RightArm` | `14` (R elbow) | IK mid-chain. Contact surface. |
| 35 | `RightHand` | `RightForeArm` | `16` (R wrist) + `54` | **PRIMARY IK TARGET.** |
| 36 | `RightHandThumb1` | `RightHand` | `55` | Thumb CMC — §6.4 |
| 37 | `RightHandThumb2` | `RightHandThumb1` | `56` | Thumb MCP |
| 38 | `RightHandThumb3` | `RightHandThumb2` | `57` | Thumb IP |
| 39 | `RightHandThumb4` | `RightHandThumb3` | `58` | **TIP NODE** |
| 40 | `RightHandIndex1` | `RightHand` | `59` | Index MCP |
| 41 | `RightHandIndex2` | `RightHandIndex1` | `60` | Index PIP |
| 42 | `RightHandIndex3` | `RightHandIndex2` | `61` | Index DIP |
| 43 | `RightHandIndex4` | `RightHandIndex3` | `62` | **TIP NODE** |
| 44 | `RightHandMiddle1` | `RightHand` | `63` | Middle MCP |
| 45 | `RightHandMiddle2` | `RightHandMiddle1` | `64` | Middle PIP |
| 46 | `RightHandMiddle3` | `RightHandMiddle2` | `65` | Middle DIP |
| 47 | `RightHandMiddle4` | `RightHandMiddle3` | `66` | **TIP NODE** |
| 48 | `RightHandRing1` | `RightHand` | `67` | Ring MCP |
| 49 | `RightHandRing2` | `RightHandRing1` | `68` | Ring PIP |
| 50 | `RightHandRing3` | `RightHandRing2` | `69` | Ring DIP |
| 51 | `RightHandRing4` | `RightHandRing3` | `70` | **TIP NODE** |
| 52 | `RightHandPinky1` | `RightHand` | `71` | Pinky MCP |
| 53 | `RightHandPinky2` | `RightHandPinky1` | `72` | Pinky PIP |
| 54 | `RightHandPinky3` | `RightHandPinky2` | `73` | Pinky DIP |
| 55 | `RightHandPinky4` | `RightHandPinky3` | `74` | **TIP NODE** |

#### The counts we test against

```
TOTAL BONES                                55   (+ legs if you include them)
Hand nodes (2 wrists + 40 finger nodes)    42   <- acceptance test 1
  finger nodes                             40
  wrists                                    2
Nodes per finger                            4   <- acceptance test 1, per finger
Fingers                                    10   (5 per hand)
```

**Optional legs.** If you include them, use `LeftUpLeg`/`LeftLeg`/`LeftFoot`/`LeftToeBase` and the
right-side equivalents. They are never driven. Framing is waist-up (§8.4), so a simple leg chain is
enough — do not spend budget there.

**Do not add bones we cannot drive.** No twist chains driven by constraints, no helper or corrective
bones, no IK/FK switch rigs in the exported file. If you believe an extra bone is genuinely needed —
the forearm twist in §6.7 is the one plausible case — **tell us and we will add it to the runtime
deliberately.** An undocumented extra bone is worse than no bone, because it sits at bind rotation
forever and nobody knows why the mesh looks slightly wrong.

### 6.3 The hand rig — four nodes per finger

This requirement has already cost us a shipped defect, so it gets the full explanation.

Our data gives **four positions per finger** (that is why the landmark column in §6.2 has four
entries per finger). Three bones span those four positions. **A retargeter poses a bone by aiming it
at its child.** So the third bone can only be posed if something exists at the fingertip to aim at.

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
> **with no vertex weights**. It carries no deformation — it exists so the exported file has a node
> at the fingertip.
>
> Two ways to do it, both fine:
> - Name it explicitly `LeftHandIndex4` (recommended — unambiguous, matches §6.2).
> - Let Blender's `_end` leaf-bone convention through, and enable **"Include → Leaf Bones"** in the
>   glTF exporter. Verify the names it produces.
>
> **The tip bone should be short** — roughly 20–30% of the distal phalanx. Long enough to have a
> stable direction, short enough not to look like a claw if it ever gets weighted by accident.
>
> **Verify on the exported file, not in the viewport.** §13 has a paste-in check.

### 6.4 Where the joints actually go

Joint *placement* is as important as joint *count*, and one of these is a classic error that would
break four of our seven handshapes.

**Fingers.** Place each joint at the centre of rotation, not on the skin surface:

- **MCP** — at the knuckle, the visible bump when you make a fist. Slightly *below* and *behind* the
  surface bump, at the centre of the joint capsule.
- **PIP / DIP** — the same rule at the middle and last joints.
- **The MCP row is an arch, not a line.** The index MCP sits higher and further forward than the
  pinky MCP. A straight MCP row makes every closed handshape read wrong.
- **Finger lengths are not equal.** Middle longest, then index ≈ ring, then pinky. Do not
  copy-paste one finger four times and only change the length uniformly.

> **🚨 The thumb is the one people get wrong.**
> `Thumb1` is the **CMC** joint, and it is **not at the base of the visible thumb** — it is deep in
> the palm, near the wrist, roughly under the middle of the palm's heel. The thumb has a long
> metacarpal that most people mistake for part of the palm.
>
> Put `Thumb1` at the web between thumb and index and the thumb can no longer **oppose across the
> palm** — which breaks handshapes `A`, `S`, `O` and `C` (six of our seven), and those are exactly
> the shapes where the thumb *is* the distinguishing feature. `A` and `S` differ from each other
> **only** in where the thumb goes.
>
> Check it by making a fist on your own hand and feeling where the thumb actually pivots from.

**The palm: keep it rigid.** Our bone list parents each MCP directly to `Hand`, so the MCP row does
not move relative to the wrist and the palm cannot arch or cup. **This is deliberate for v1** —
simpler, more robust, and cupping is not what distinguishes any of our seven handshapes. `C` and `O`
are achievable with flexion alone.

Do **not** add metacarpal bones to enable cupping without telling us. Our data does contain MCP
positions, so a movable-MCP rig is possible in principle — but it changes the retarget, so it is a
decision to make together, not a silent improvement.

**Arm.** `LeftArm` at the shoulder's centre of rotation (inside the deltoid, not on the surface);
`LeftForeArm` at the elbow's hinge axis; `LeftHand` at the wrist's centre, between the two wrist
bumps.

### 6.5 Required ranges of motion

The runtime will drive your rig to these ranges. **All of them must look correct** — no tearing, no
interpenetration, no collapse. There are no joint limits in glTF, so the rig cannot refuse a pose; it
can only handle it well or badly.

| Joint | Range that must look correct | Why it matters here |
|---|---|---|
| Finger **MCP flexion** | 0° (straight) → **90°** | Fists: handshapes `A`, `S`. |
| Finger MCP **hyperextension** | up to **−20°** | Flat hands over-straighten. Handshape `B`. |
| **Finger MCP abduction (spread)** | **±20°** | 🚨 **`B` vs `5` is entirely this.** See below. |
| Finger **PIP flexion** | 0° → **110°** | Full curl. |
| Finger **DIP flexion** | 0° → **80°** | The segment that is currently never posed. |
| **Thumb opposition** | across the palm to touch the ring finger | `A`, `S`, `O`, `C`. |
| Wrist **flexion / extension** | **±70°** | Many signs flick at the wrist. |
| Wrist **radial / ulnar deviation** | **±25°** | |
| **Forearm pronation / supination** | **±90° from neutral** (180° total) | 🚨 Palm up vs palm down is *linguistic*. §6.7. |
| Elbow **flexion** | 0° → **145°** | Signs at the chest and face fully flex the elbow. |
| Shoulder | full overhead, and across the body to the opposite shoulder | The signing space is large. §8.4. |
| `Neck` + `Head` **yaw** | **±30°** | Headshake = negation. §6.9. |
| `Head` **tilt** | **±20°** | Wh-question marker. |

> **🚨 Finger abduction is a hard requirement, and quick rigs often lack it.**
> Handshape **`B`** is four fingers extended and held **together**. Handshape **`5`** is the same
> four fingers extended and **spread wide**. If your MCP joints only flex and cannot abduct, those
> two handshapes are *geometrically identical* and the rig cannot express the difference.
>
> `B` is the passive handshape for **26 of our 35** two-handed base signs, so this is not an edge
> case. And we have an open measurement suggesting our own `B`/`5` templates may be
> insufficiently distinct (§10) — a rig that cannot separate them would make that impossible to
> diagnose.

### 6.6 Bone orientation, roll, and symmetry

Because aiming a bone at a target fixes only two of three rotational degrees of freedom (§3.1), the
**roll** — rotation around the bone's own length — is not determined by the data. It comes from your
rest pose. Inconsistent roll produces fingers that twist unpredictably as they curl.

- **Bone axis along the bone.** Blender's convention (local **+Y** points from head to tail) is fine
  and is what we assume. Just be consistent.
- **Roll must be consistent down each finger chain.** All three phalanges of a finger should share
  the same roll, so the finger curls in one clean plane. Blender: select the chain and use
  **Armature → Bone Roll → Recalculate Roll → Global +Z Axis** (or align to the palm normal), then
  verify visually by rotating each bone on its local X and watching for sideways drift.
- **Fingers curl around local X.** With +Y along the bone, flexion should be a single-axis rotation.
  If curling a finger needs two axes, the roll is wrong.
- **Perfect left/right mirror symmetry.** Same joint positions, same lengths, same rolls, mirrored.
  Asymmetry here shows up as one hand looking subtly wrong on symmetric signs — and 52 of our words
  are symmetric two-handed signs where both hands do the same thing at once, so it is immediately
  visible.
- **Zero unapplied rotation on the armature object itself.** Rotate bones, never the armature.

### 6.7 Skinning: weights, the 4-influence limit, and the twist problem

**Skinning method: linear blend skinning only.** glTF 2.0 has no dual-quaternion skinning, and
neither does Three.js by default. So every classic LBS artefact — the candy-wrapper twist collapse,
volume loss on bend — must be solved with **topology and weights**, not by switching skinning mode.
If your usual workflow relies on DQ skinning for the forearm, you need a different plan here.

**Maximum 4 bone influences per vertex.** glTF's default vertex layout carries four joints and four
weights. Blender's exporter will silently drop the smallest influences beyond four, so a mesh
weighted with 6–8 influences deforms differently after export than it did in your viewport.

- Limit to 4 in Blender: **Weight Paint → Weights → Limit Total → 4**, then **Normalize All**.
- Weights must sum to 1.0 per vertex.
- No zero-weight vertices, no vertices weighted only to `Hips`.

> **🚨 The forearm twist problem — plan for it, do not discover it.**
> Palm-up versus palm-down is a **linguistic** distinction in sign language, not a stylistic one.
> §10's orientation vocabulary requires palm up, palm down, palm toward the signer, and palm away —
> which needs roughly **180° of total forearm rotation**.
>
> Under LBS, rotating a single `ForeArm` bone 180° shears the elbow into the classic candy-wrapper
> collapse. There is no skinning-mode escape (see above). Your options:
>
> 1. **Weight-based** — distribute the twist across enough loops between elbow and wrist that no
>    single loop takes more than ~45°. Needs 6–10 loops along the forearm. **No extra bones, so
>    this is the option that needs no coordination with us — preferred if you can make it work.**
> 2. **A twist bone** — one extra bone taking half the roll. This works, but it is an extra bone the
>    runtime must drive explicitly (§6.2: no constraints in the export). **If you choose this,
>    tell us at P1-M1** and name it clearly, e.g. `LeftForeArmTwist`. We will add it to the runtime
>    deliberately. Do not ship it undocumented.
>
> Either way, **acceptance test 5 checks ±90° from neutral with no visible shear.**

**Other weighting notes:**

- **Shoulders and clavicle.** Signs reach fully overhead and across the body. Weight the deltoid and
  trapezius so both extremes hold. This is why `LeftShoulder` is mandatory in §6.2.
- **Keep finger weights tight.** A fingertip that drags neighbouring geometry blurs the handshape,
  which is the one thing that must stay legible.
- **The tip bones carry zero weights** (§6.3). Confirm they are not accidentally painted.

### 6.8 Bone lengths: fixed, documented, non-uniform

Deliver a small JSON or CSV listing every bone's rest length in the rig's own units. The runtime
needs it for §3.2. Format is up to you; a flat `{"LeftHandIndex1": 0.0412, …}` is ideal.

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

### 6.9 The face — bones now, blendshapes in phase 2

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

**Phase 1 requirement — the head and neck bones.** `Head` and `Neck` must be freely rotatable and
weighted to survive a **±30° yaw** and a **±20° tilt** with no collar tearing and no neck pinching.
Bones survive a mesh change, so this work is permanent even though the head geometry is not.
Distribute the yaw between `Neck` and `Head` rather than putting it all on one.

**Phase 2 requirement — the brow channel.** Blendshapes are per-mesh, so building them on a blockout
head would be wasted. They get built natively on the final head. Two things phase 1 must not
foreclose:

1. **The blockout head must have brow geometry** — a real brow ridge and enough topology that a
   raise and a furrow are demonstrably achievable. A featureless egg head fails this.
2. **A one-shape proof.** Deliver a single crude `browRaise` shape key on the blockout, purely to
   prove the topology supports it. Not a full set, not final quality — a feasibility check.

> **Carried forward as a locked constraint on phase 2:** the final head ships at minimum
> `browInnerUp`, `browDownLeft`, `browDownRight`, and preferably the full **ARKit 52** set. And the
> brows must be **visible** — no fringe over the forehead, no glasses, no brow-obscuring hair. A brow
> channel nobody can see is not a channel, and it is easy to design one away without noticing.

### 6.10 Orientation, units, bind pose

| | |
|---|---|
| **Up axis** | **+Y up.** Standard. Our data has y pointing *down* and the runtime flips it — not your problem, and do not compensate for it. |
| **Facing** | **+Z toward the viewer.** The avatar faces the camera. |
| **Units** | Metres, real-world scale, ~1.7 m tall. The runtime normalises, but a sane scale prevents a class of solver problems. |
| **Bind pose** | **A-pose**, arms ~45° down, **palms facing the body**, fingers straight and slightly separated. Better shoulder weights than a T-pose and closer to a signer's rest. |
| **Rest / idle pose** | A separate **neutral signing rest pose** — arms down, hands relaxed and slightly open, in front of the body. Where the avatar sits between utterances, so the pose people see most. Deliver as a named pose, not as the bind pose. |
| **Origin** | At the feet, centred between them. |
| **Transforms** | No unapplied scale or rotation on the armature or any mesh. Apply everything before export. |
| **Mesh** | Single skinned mesh preferred. No modifiers left unapplied except the armature. |

### 6.11 glTF export settings

For Blender's **glTF 2.0** exporter. Deviate if you know better, but tell us what you changed.

| Setting | Value | Why |
|---|---|---|
| Format | **glTF Binary (`.glb`)** | Single file, embedded. |
| Include → Limit to | Selected objects (armature + mesh) | Keeps cameras and lights out. |
| Include → **Leaf Bones** | **ON** *if* you rely on `_end` bones for the tips | §6.3. Not needed if you named them `…4` explicitly. |
| Transform → +Y Up | **ON** | §6.10. |
| Data → Mesh → Apply Modifiers | ON | But not the armature modifier. |
| Data → Mesh → **Tangents** | OFF | Not needed in phase 1. |
| Data → Material | No export / flat | Phase 1 is untextured. |
| Data → **Shape Keys** | **ON** | Carries the `browRaise` proof (§6.9). |
| Data → Skinning | **ON** | |
| Data → Armature → **Export Deformation Bones only** | **OFF** | Would strip the weightless tip bones — **exactly the failure this brief exists to prevent.** |
| Animation | **OFF** | You deliver poses, never clips. |
| Compression (Draco) | **OFF** | Keep it simple and inspectable. |

> **⚠️ "Export Deformation Bones only" is the setting most likely to silently break this
> delivery.** The tip bones have no weights by design (§6.3), so that option removes them — and the
> export looks clean, loads clean, and is wrong. Confirm with §13-B every single time.

---

## 7. The 21-point hand layout and what drives what

Context for §6.2's landmark column. Our data is a flat array of 75 points per frame:

| indices | body part | source |
|---|---|---|
| **0–32** | Upper body — face positions, shoulders, elbows, wrists, hips | MediaPipe Pose |
| **33–53** | **Left** hand, 21 points | MediaPipe Hands |
| **54–74** | **Right** hand, 21 points | MediaPipe Hands |

The useful pose points: `0` nose · `11` left shoulder · `12` right shoulder · `13` left elbow ·
`14` right elbow · `15` left wrist · `16` right wrist.

Each hand block is MediaPipe's standard 21-point topology, offset by 33 or 54:

```
offset +0            wrist
offset +1  +2  +3  +4    thumb    CMC  MCP  IP   TIP
offset +5  +6  +7  +8    index    MCP  PIP  DIP  TIP
offset +9  +10 +11 +12   middle   MCP  PIP  DIP  TIP
offset +13 +14 +15 +16   ring     MCP  PIP  DIP  TIP
offset +17 +18 +19 +20   pinky    MCP  PIP  DIP  TIP
```

**This is where the four-nodes-per-finger requirement comes from.** There are literally four
landmark indices per finger. A rig with three nodes per finger has nowhere to put the fourth, so it
is discarded — and the DIP→TIP bone is never aimed (§6.3).

Note also: the **wrist appears twice** — once as a pose landmark (`15`/`16`) and once as the hand
block's own point 0 (`33`/`54`). The runtime reconciles them; you only need one `Hand` bone.

**Missing points arrive as `null`, never as `[0,0,0]`.** You will not see this in phase 1, but it is
why §3.3 says to test under real data: the runtime holds or interpolates across gaps, and your rig
has to look right during a hold.

---

## 8. Constraints the character design will have to satisfy

**You are not designing yet.** This section exists so that phase 1 does not foreclose phase 2, and
so you know the box the design will fit inside. Read it; do not act on it beyond §5's locked
proportions.

### 8.1 Who the character is for

A **Deaf or hard-of-hearing person, in a clinic or hospital, possibly frightened, trying to
understand a doctor.** Our market is Lebanon. The near-term vocabulary is clinical.

The eventual design will need to be: **trustworthy and calm** (this character delivers medical
information — not cute, not a mascot); **professionally plausible** without implying a specific real
hospital or credential; **regionally plausible** for a Levantine audience; and **respectful of the
Deaf community**, whose language this is.

### 8.2 Legibility rules — these will override aesthetics

The hands carry **100% of the lexical content.** Anything that reduces hand legibility is a
functional defect, not a style choice. These bind phase 2:

- **Hands must contrast strongly against the torso.** Very many signs are performed directly in
  front of the chest, so a skin-toned top makes those signs vanish. Mid-to-dark, **solid,
  unpatterned** torso. No stripes, no logos, no busy texture.
- **Sleeves end at or above the elbow.** Six signs contact the passive forearm or wrist (§9).
- **No jewellery, watch, rings, gloves, bracelets, or long nails.** All of it occludes handshape.
- **Hands 5–10% larger than photoreal.** Already locked in §5 — functional, not aesthetic.
- **Face clear:** brows visible, no glasses, hair off the forehead, no beard obscuring the chin —
  several signs contact the chin (§9).
- **Everything must read at 320 px tall.** Roughly the real size on a phone.

### 8.3 Style: stylized, not realistic — and this is a technical argument

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

### 8.4 Framing and the signing space

- The camera sees roughly **top of head to waist**, front-on.
- The **signing space** extends about **±0.75 shoulder-widths** either side of body centre, and from
  just above the head to the waist — a box about 1.5 shoulder-widths wide. Signs go above the head
  and out to the sides; **the rig must work with a hand anywhere in that box**, which is a phase-1
  concern, not just a framing one.
- Plain background supplied by the app. No environment, ever.

---

## 9. What the hands touch

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
sleeves and hair are constrained in §8.2.

---

## 10. The seven handshapes

In sign languages the finger configuration is a distinct linguistic unit with a fixed inventory and
standard names. Our synthesized passive hand uses seven. On the current vocabulary five are used:

| Shape | How it is formed | The joints that make it | Words |
|---|---|---|---|
| **B** | Flat hand. All four fingers extended and held **together**, thumb folded across or alongside the palm. A flat paddle. | MCP/PIP/DIP ≈ 0°, **abduction 0°**, thumb adducted | **26** |
| **A** | Closed fist with the thumb **alongside** the index finger, pointing up — not tucked inside, not crossed over. | full flexion, thumb extended alongside | 3 |
| **1** | Index fully extended and straight, other three curled into the palm, thumb closed over them. | index 0°, others full flexion | 3 |
| **C** | Fingers held together and curved, thumb curved opposite, forming a clear C-shaped gap. Not a fist, not flat. | ~45–60° at every finger joint, thumb opposed | 2 |
| **S** | Closed fist with the thumb **crossed over** the front of the folded fingers. Distinct from `A` only in the thumb. | as `A`, thumb flexed across | 1 |
| **5** | All five fingers extended and **spread wide apart**. The spread is the point. | MCP/PIP/DIP ≈ 0°, **abduction MAX** | not used yet |
| **O** | Fingertips and thumb tip meeting to form a closed round O. | ~60–70° flexion, thumb opposed to meet the index tip | not used yet |

Note how the "joints that make it" column maps onto §6.5: `A` and `S` differ **only** in the thumb,
and `B` and `5` differ **only** in abduction. Both distinctions are rig capabilities, not styling.

**Phase-1 deliverable: hand-pose all seven, as named poses.** Save them as named pose assets in the
source file and deliver reference renders (front and side of the hand). Two reasons: it proves the
hand rig can hit them crisply, and it gives us a human-authored reference to check our measured
templates against.

**Look at real reference, not just our descriptions** (§17). These are real linguistic forms with
correct and incorrect versions.

> **⚠️ A specific open question you can settle for us.**
> Our automatically-measured templates for **`B` (flat, together) and `5` (extended, spread)** may
> not be as distinct from each other as they should be. We measured a fingertip displacement of
> **0.178** between them — the *smallest* of all 21 shape pairs — and we could not resolve whether
> that is a genuine problem in our data or an artefact of how we measure it.
>
> **Your hand-posed `B` and `5` would give us the clean reference we lack.** Please form them
> deliberately and unmistakably distinct: `B` with fingers pressed together and flat, `5` with
> fingers splayed as wide as the hand goes. This is also the direct test of the abduction
> requirement in §6.5.

The synthesized hand is also placed at a specific **orientation** per word. Your rig must reach all
of these comfortably, at the wrist, without the forearm twisting past anatomical limits (§6.7):

- **Palm faces:** up · down · toward the signer · away from the signer · toward the other hand
- **Fingers point:** forward · toward the other hand · up · toward the signer

---

## 11. What we give you

| Item | What it is, and what to do with it |
|---|---|
| `reference_pose.json` | One neutral frame, 75 points, in our coordinate space. **For testing your retarget, not for modelling proportions** — see §6.8. |
| `handshape_templates.json` | 21-point measured templates for the seven handshapes. Numeric reference for what the shapes should be. |
| 250 per-word clips | Real landmark motion, one file per word. This is what will drive your rig. |
| `contact_sheet.png` | Rendered stick-figure previews of the whole vocabulary. **Look at this early** — it shows the real range of motion better than any description. |
| A test harness | Ghozlan's existing player. Load your rig and watch it move under real data *before* final delivery. **Use it at P1-M3, not at the end.** |
| Us | Ask early and often. A question answered in week one is free; a rebuild in week four is not. |

**Ask for anything else you need.** Especially: if you want video reference of real signers
performing these signs, say so and we will point you at it. **Do not guess at what a sign looks
like** — specifying that is our job, not yours to invent.

---

## 12. What you deliver in phase 1

| # | Deliverable | Format & notes |
|---|---|---|
| 1 | **Rigged blockout character** | **glTF 2.0 `.glb`**, single file. Neutral grey, no styling, final proportions, fully skinned. |
| 2 | Editable source | `.blend` preferred, or `.ma`/`.mb`, full rig stack intact, nothing collapsed. |
| 3 | **Bone length table** | JSON or CSV — every bone, rest length, rig units (§6.8). |
| 4 | Bone name map | JSON. *Only* if you deviated from §6.2's names. |
| 5 | **Seven handshape poses** | Named pose assets + front/side reference renders (§10). |
| 6 | Neutral signing rest pose | A named pose, plus a render (§6.10). |
| 7 | **`browRaise` feasibility shape** | One crude shape key on the blockout head (§6.9). |
| 8 | **Twist-solution note** | Which §6.7 option you took. If you added a twist bone, its name and how it should be driven. |
| 9 | Turnaround renders | Front, side, back, plus hand close-ups at full curl, full extension, and full spread. |
| 10 | A short readme | Rig setup, constraints used, export settings changed, known limits, and **anything phase 2 must not break**. |

**Budgets** — this runs in a browser, on phones, next to a live camera feed:

| | |
|---|---|
| **Triangles** | **Blockout: 20k–40k.** Final character will be 30k–60k. **Weight it toward the hands** — spending a quarter of the budget on two hands that are 3% of the volume is *correct* here. |
| **Textures** | None needed in phase 1. Flat grey material. |
| **Bone influences** | **Maximum 4 per vertex**, normalized (§6.7). |
| **Blendshapes** | One (`browRaise`). Nothing else. |
| **Bones** | 55, plus optional legs, plus at most one documented twist bone per forearm. |
| **Forbidden** | **No** rigid-body, cloth, hair, or physics. **No** drivers or constraints in the exported file. **No** animation clips. Everything deterministic under IK. |

---

## 13. Self-check before you send

These are the checks we will run. Running them yourself first turns a failed delivery into a
five-minute fix.

### A · Count the finger nodes in Blender

Paste into the Scripting workspace with the armature selected. Every line must read `4 nodes`.

```python
import bpy

arm = bpy.context.object          # select your armature first
bad = 0
for side in ('Left', 'Right'):
    for finger in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
        names = sorted(b.name for b in arm.data.bones
                       if b.name.startswith(side + 'Hand' + finger))
        ok = len(names) == 4
        bad += 0 if ok else 1
        print(f'{side}Hand{finger}: {len(names)} nodes  '
              f'{"OK" if ok else "*** FAIL - need 4 ***"}  {names}')

# the three naming traps from S6.1
dots = [b.name for b in arm.data.bones if '.00' in b.name]
suff = [b.name for b in arm.data.bones if b.name.endswith(('.L', '.R'))]
pref = [b.name for b in arm.data.bones if b.name.startswith('mixamorig')]
print(f'\ntotal bones: {len(arm.data.bones)}   (expect 55, or 63 with legs)')
print(f'".00" duplicates : {len(dots)} {dots[:5]}')
print(f'".L/.R" suffixes : {len(suff)} {suff[:5]}')
print(f'"mixamorig" prefix: {len(pref)} {pref[:5]}')
print('\nRESULT:', 'PASS' if not (bad or dots or suff or pref) else 'FAIL')
```

### B · Confirm the nodes survived glTF export

**This is the check that matters**, because Blender can look right while the export drops the tips
(§6.3, §6.11). Export the `.glb`, then either inspect the node tree in a glTF viewer, or run:

```python
python -c "
import json, struct, sys
f = open(sys.argv[1], 'rb'); f.read(12)
n, t = struct.unpack('<II', f.read(8))
g = json.loads(f.read(n))
names = [x.get('name','') for x in g['nodes']]
bad = 0
for side in ('Left','Right'):
    for fg in ('Thumb','Index','Middle','Ring','Pinky'):
        k = [x for x in names if x.startswith(side+'Hand'+fg)]
        bad += 0 if len(k)==4 else 1
        print(side+'Hand'+fg, len(k), 'OK' if len(k)==4 else '*** FAIL ***', sorted(k))
print()
print('total nodes:', len(names))
print('RESULT:', 'PASS' if bad==0 else 'FAIL - ' + str(bad) + ' finger(s) short')
" your_avatar.glb
```

*(Verified 2026-09-01 against a synthetic `.glb` with one finger deliberately at 3 nodes — it
correctly reports `*** FAIL ***` on that finger and `OK` on the other nine, so the check can
actually fail.)*

### C · The rest of the list

- **Curl and extend every finger fully**, one at a time and all together. Look for tearing at the
  knuckles, palm ballooning, finger interpenetration.
- **Spread the fingers fully** and check `B` versus `5` are unmistakably different (§6.5).
- **Twist each forearm ±90°** and look for candy-wrapper shear at the elbow (§6.7).
- **Pose all seven handshapes** (§10) and check each reads at 320 px tall.
- **Reach the extremes:** a hand fully overhead, a hand across the body to the opposite shoulder,
  elbow fully flexed, both hands meeting at the chest.
- **Put a hand on every contact zone in §9.** No gross interpenetration.
- **Rotate the head:** yaw ±30°, tilt ±20°. No collar tearing, no neck pinch.
- **Verify weights:** Limit Total = 4, Normalize All, no zero-weight vertices, tip bones unweighted.
- **Drive it with our real data** in the test harness. Not just hand-authored poses — §3.3.
- **Check for unapplied transforms** on the armature and every mesh.
- **Load the `.glb` in a viewer** and confirm zero warnings.

---

## 14. Acceptance tests

Run by script on delivery. They exist so "done" is a measurement rather than an opinion — which
protects you as much as us, because payment is not held up by subjective back-and-forth.

| # | Test | Pass condition | Phase |
|---|---|---|---|
| 1 | **Finger node count** | Every finger, both hands, has **4 transform nodes in the exported `.glb`**. 40 finger nodes + 2 wrists = **42**. Hard fail if any finger has 3. | **1** |
| 2 | **Bone names** | All 55 names match §6.2 exactly. No `.001`, no `.L`/`.R`, no `mixamorig:` — or a complete map is supplied. | **1** |
| 3 | **Distal keying** | Driven with a real clip, **every third-segment bone on both hands is actually posed.** The §6.3 regression test. | **1** |
| 4 | **Bone-length stability** | Every bone within 0.1% of rest length across a full 250-word playback. Catches stretchy IK. | **1** |
| 5 | **Forearm twist** | ±90° from neutral, no visible shear at the elbow. | **1** |
| 6 | **Abduction / `B` vs `5`** | Fingers abduct ≥20°; `B` and `5` measurably distinct in bone-direction space. | **1** |
| 7 | Reference-pose retarget | Driven with `reference_pose.json`, wrists land within 5% of a shoulder-width of target. | **1** |
| 8 | Handshape reachability | All seven reachable and legible. | **1** |
| 9 | Head range | Yaw ±30°, tilt ±20°, no tearing. Plus the `browRaise` shape exists. | **1** |
| 10 | Extremes, no tearing | Full curl, full extension, arm overhead, hand to opposite shoulder, elbow fully flexed. | **1** |
| 11 | Contact zones | A hand at each §9 target: no gross interpenetration. | **1** |
| 12 | Vertex influences | Max 4 per vertex, weights normalized, no unweighted vertices. | **1** |
| 13 | Budgets | Triangles, bone count, file size within §12. | **1** |
| 14 | Loads clean | Loads in Three.js with no warnings; no unapplied transforms; no unsupported features. | **1** |
| 15 | Brow blendshape set | Minimum three brow shapes, ARKit-52 preferred. | 2 |
| 16 | Legibility rules | Every rule in §8.2 satisfied. | 2 |

Tests **1, 3 and 4** are the ones that have actually bitten us. Expect them first, and expect tests
1 and 2 at **P1-M1** rather than at delivery.

---

## 15. Phase 1 milestones

Each gate is cheap to fix at that point and expensive to fix later. We would rather review four
times than once, and we will turn reviews around quickly.

| M | You deliver | We check |
|---|---|---|
| **P1-M1** | **Skeleton only.** All 55 bones per §6.2, correct hierarchy and names, all 42 hand nodes, joint placement, roll conventions, bone length table, proportions agreed. **Exported as `.glb`.** Plus your §6.7 twist decision. | **Tests 1, 2 and 4.** The cheapest possible moment to catch §6.3 — and the whole reason we want a `.glb` this early, before any mesh work. |
| **P1-M2** | Blockout body at locked proportions, skinned, arms and torso weighted, forearm twist solved. | Tests 5, 7, 10, 12. Contact-zone form (§9). |
| **P1-M3** | **Hands: final topology and weights, all seven handshapes posed.** Loaded in our test harness under real motion. | Tests 6, 8, 11. **The most important review in the project.** |
| **P1-M4** | Head/neck weights, `browRaise` shape, rest pose, final `.glb` + source + all ten deliverables from §12. | Tests 9, 13, 14, and a re-run of everything. Sign-off. |

**Phase 2 is quoted separately** once P1-M4 is signed off and we have decided the design direction.

### Out of scope for phase 1

- **Any character design** — style, colour, clothing, face design, hair, textures, materials.
- **Brow blendshapes beyond the single feasibility shape** (§6.9).
- **The retargeting solver, the runtime, transitions, smoothing** — Ghozlan's.
- **Which signs exist, what they look like, ASL linguistics** — ours. Ask.
- **Animating anything.** You deliver poses, never animation clips.
- **Full 468-point face-mesh driving.** Not in either phase yet.
- **Lip sync and mouth shapes.** Later.
- **Legs, walking, locomotion, sitting.** Framing is waist-up.
- **Environments, lighting rigs, backgrounds, UI.**

---

## 16. Commercial terms to agree

Listed so nothing is discovered late. Figures are to be agreed — this is a checklist, not an offer.

| | |
|---|---|
| **Phase 1 fee & schedule** | Total for phase 1, and how it splits across the four milestones in §15. |
| **Phase 2** | Indicative range only, so we can budget. Not committed on either side yet. |
| **Timeline** | Target date per milestone, and what happens if a gate fails and needs rework. |
| **Revisions** | How many rounds are included per milestone, and what counts as a new request rather than a revision. |
| **IP & ownership** | We need full commercial rights to the rig and the source files, including the right to modify them and ship them inside a commercial product — **and the right to have phase 2 done by someone else if we choose.** Say now if that is not your normal arrangement. |
| **Third-party assets** | **Declare every base mesh, base rig, texture pack, or scan you use, with its licence.** Anything that cannot be redistributed commercially inside an application is unusable to us, however good it looks. This matters most for base rigs. |
| **Credit** | Whether you want to be credited, and how. |
| **Handover** | How files are transferred, and where they live afterwards. |

---

## 17. Reference material

You do not need to learn ASL. You do need to see enough that the requirements stop being abstract.
An hour here is well spent.

- **Watch real signing.** Search "ASL dictionary" and watch any twenty signs. Notice how much
  happens at the fingertips, how often the hands touch the face and chest, how often the palm turns
  over, and how much the eyebrows move. Those are §6.3, §9, §6.7 and §6.9 becoming obvious.
- **ASL handshape charts.** Search "ASL handshape chart" or "ASL manual alphabet" for the canonical
  forms of `A`, `B`, `C`, `O`, `S`, `1` and `5` (§10). Note how little separates `A` from `S`.
- **Hand anatomy reference** for §6.4 — specifically where the **thumb CMC joint** sits relative to
  the palm. This is the single most common rigging error on hands.
- **Existing signing avatars.** Search "signing avatar" — look at both the good and the
  widely-criticised ones. The common complaints are exactly our §8.3 concern: stiff, expressionless,
  uncanny.
- **The glTF viewer** — `gltf-viewer.donmccurdy.com`. Drop your `.glb` in and inspect the node tree.
  This is where §13-B happens.
- **Ask us for video reference on specific signs.** If a contact zone or a handshape is unclear,
  that is a question for us, not something to guess.

---

## 18. Before you start — please answer these

1. Which package do you work in, and can you deliver clean glTF 2.0 from it?
2. Are you comfortable with the **exact bone names in §6.2**, or would you rather deliver a name map?
   If you rig with Rigify or an auto-rigger, how will you produce the clean export skeleton?
3. Have you rigged hands for **IK-driven, position-target** animation before? If not, say so — it is
   learnable, and we would much rather plan for it than discover it at P1-M3.
4. **How will you solve the forearm twist** (§6.7) — weights, or a twist bone? If a twist bone, we
   need to know at P1-M1 so the runtime can drive it.
5. Starting from scratch, or from a base mesh or base rig (Avaturn, Ready Player Me, MetaHuman,
   Character Creator, Rigify)? **A base is fine** — but many bases fail §6.3, so if you use one,
   **tests 1 and 2 must pass at P1-M1.** And confirm the licence permits commercial use and
   redistribution inside an application (§16).
6. **Your estimate and rate for phase 1**, against the four milestones in §15.
7. **Do you also want phase 2** (the character design), and roughly what would that cost? Not a
   commitment — we want to know whether to plan for one artist or two.
8. **Anything in this brief that looks wrong, unusual, or more expensive than it needs to be.** You
   will know things about rigging that we do not. Say so early — we would rather change the brief
   than pay for a workaround.

---

## 19. One-page checklist

Print this. Everything below is pass/fail.

**Skeleton**
- [ ] All 55 bones present, named exactly as §6.2
- [ ] Correct parent for every bone
- [ ] **4 nodes per finger** — 42 hand nodes total
- [ ] Tip bones present, short, **unweighted**
- [ ] No `.001`, no `.L`/`.R`, no `mixamorig:` prefix
- [ ] `LeftShoulder` / `RightShoulder` clavicles present
- [ ] Spine is 3 bones, not welded
- [ ] No undocumented extra bones

**Joints and orientation**
- [ ] Joints at centres of rotation, not on the skin surface
- [ ] **Thumb CMC deep in the palm**, not at the web
- [ ] MCP row forms an arch, not a straight line
- [ ] Finger lengths anatomically unequal
- [ ] Roll consistent down each finger chain; fingers curl on one axis
- [ ] Perfect left/right mirror symmetry
- [ ] Palm rigid — no metacarpal bones (unless agreed with us)

**Ranges**
- [ ] Finger MCP 0→90° flexion, −20° hyperextension
- [ ] **Finger abduction ±20° — `B` vs `5` distinguishable**
- [ ] PIP 0→110°, DIP 0→80°
- [ ] Thumb opposes across the palm
- [ ] Wrist ±70° flexion/extension, ±25° deviation
- [ ] **Forearm ±90° twist with no elbow shear**
- [ ] Elbow 0→145°
- [ ] Shoulder full overhead and cross-body
- [ ] Head yaw ±30°, tilt ±20°

**Skinning**
- [ ] Max **4** bone influences per vertex, normalized
- [ ] No zero-weight vertices
- [ ] No tearing at any range above
- [ ] Palm does not balloon on a closed fist
- [ ] Fingers do not interpenetrate when fully curled

**Export**
- [ ] `.glb`, +Y up, no unapplied transforms
- [ ] **"Export Deformation Bones only" is OFF**
- [ ] Shape Keys ON (carries `browRaise`)
- [ ] Animation OFF, no Draco, no constraints, no drivers
- [ ] Loads in a glTF viewer with zero warnings
- [ ] **§13-B passes on the exported file**

**Deliverables** (§12)
- [ ] `.glb` · source file · bone length table · name map if needed
- [ ] Seven handshape poses + renders
- [ ] Neutral signing rest pose + render
- [ ] `browRaise` shape key
- [ ] Twist-solution note
- [ ] Turnarounds + hand close-ups
- [ ] Readme

---

## Appendix — why the constraints are shaped this way

Not required reading. Here because someone who understands the *why* makes better decisions on the
hundred things a brief cannot cover.

**Our source data recorded one hand per signer.** In the corpus behind the 250-word vocabulary, both
hands are present in **1.7%** of clips. So on every two-handed sign the passive hand is absent from
*every single take*, and its handshape must be synthesized from the seven-shape library in §10. What
*is* recorded in every frame is the passive **wrist**, because that is a body landmark rather than a
hand landmark. Hence the split that runs through this brief: position is given, shape is invented —
and hence why a rig that can hit those seven shapes crisply matters so much.

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
data would move without meaning anything. So the non-manual markers in §6.9 are **generated from
rules on our side**, keyed off the sentence we already parse. That needs no data at all — only a rule
and a rig. It is the one place in this entire system where we can add real linguistic structure
rather than replay recorded motion, which is why the head bones are a phase-1 requirement even
though the face design is deferred.

**Two of our lexicons are unreviewed by a Deaf signer.** The handshape templates and the
passive-hand placements were written from published phonology by a hearing developer. They are
honest about it in their own metadata, and a fluent reviewer will eventually disagree with some of
them. When that happens, **the fix is our lexicon, not your rig** — which is exactly why §10 asks for
clean, deliberate, separable handshapes. A crisp rig lets us tell a data error from a rig error. A
mushy one does not, and then every disagreement costs a week of argument.
