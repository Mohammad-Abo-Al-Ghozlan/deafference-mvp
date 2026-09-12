# Avatar M1 review — `3D Char deaf.glb`

**To:** the contracted rigger
**From:** Deafference (Mohammed Salim, technical lead)
**Date:** 2026-09-12
**Against:** `docs/AVATAR_BRIEF_COMPLETE.md` **v6.1**, §14 acceptance tests
**Method:** `python avatar/rig_audit.py "3D Char deaf.glb"` — reads the exported `.glb` only,
never a viewport, because §6.11's whole warning is that a rig can look correct in Blender and
export wrong. Re-run it yourself; it needs only Python and numpy.

---

## Summary — the rig is good. The delivery is undeclared.

**Every hard technical thing in this brief, you got right.** The four-nodes-per-finger
requirement that §6.3 exists for, the thumb CMC placement that §6.4 calls "the one people get
wrong", the 4-influence weight limit, the export setting that silently strips weightless
tips — all correct. That is the part that would have been expensive to fix later, and it is
done.

**What blocks M1 is almost entirely paperwork and file hygiene**, plus one missing shape key.
Nothing below asks you to re-rig anything.

| | | |
|---|---|---|
| ✅ **4 tests pass** | 1, 4, 12, 14 | including the two that have historically bitten us |
| ❌ **3 tests fail** | 2, 9, 13 | one is ours to close, two are quick |
| ⏸ **7 not run** | 3, 5, 6, 7, 8, 10, 11 | need a posed rig or our runtime — not your fault, not yet testable |

**One item is a genuine commercial blocker and everything else waits behind it.** Please answer
§1 first, today if you can, even if the rest takes a week.

---

# 🔴 1 · BLOCKER — the base asset is undeclared, and it may be unusable

**What we found.** The skin, material and texture inside the file are all named
`rp_claudia_rigged_002`:

```
skin      rp_claudia_rigged_002
material  rp_claudia_rigged_002_mat
images    rp_claudia_rigged_002_dif  (x2)
```

That is **Renderpeople "Claudia", rigged 002** — a commercial photoscanned asset.

**Using a base is completely fine, and we said so twice.** §18 Q5: *"Starting from scratch, or
from a base mesh or base rig? **A base is fine**."* This is not a complaint about your method.

**The problem is that it was not declared, and the licence question is unanswered.** §16:

> **Declare every base mesh, base rig, texture pack, or scan you use, with its licence.**
> Anything that cannot be redistributed commercially inside an application is unusable to us,
> however good it looks. This matters most for base rigs.

We asked this directly on **2026-09-07** as Q5, one of three questions flagged "answer these
first":

> **Q5 — base mesh, and its licence.** Starting from a base is completely fine. But we need to
> ship the result inside a commercial product, so a base that cannot be redistributed that way
> is unusable to us however good it looks. Much cheaper to find out now than at M4.

**Why this is urgent rather than procedural.** Renderpeople's standard licence permits using
their models in renders and internal work. It does **not**, as we read it, permit shipping the
model itself inside an application where a user can extract the geometry — which is exactly
what a `.glb` served to a browser does. If that reading is right, this asset cannot ship in our
product no matter how good the rig on top of it is, and every hour spent refining it is spent
on something we must later throw away.

**What we need from you, in writing:**

1. **Which Renderpeople product and which licence tier** you hold for it.
2. **Whether that licence permits redistribution inside a commercial web application**, where
   the mesh is downloadable by the end user. If you are not certain, say so — we will ask
   Renderpeople ourselves. An honest "I don't know" today costs nothing.
3. **Whether the rig is yours or theirs.** The bone names are Renderpeople's convention, which
   suggests you kept their skeleton. If the skeleton, weights and hand structure are their work
   rather than yours, we need to know, because §16 gives us *"full commercial rights to the rig
   and the source files, including the right to modify them"* and you cannot grant us rights to
   someone else's rig.

**In the meantime we have NOT committed the file to our repository**, precisely because git
history is permanent and we do not yet know whether we may hold this asset. It is on one
machine only.

> **If the licence does not clear:** this is recoverable and not a disaster. The rig structure
> you built — the hand in particular — is the valuable part, and it is described entirely by
> numbers we can hand you back (`avatar/bone_lengths_measured.json`, attached). Rebuilding the
> same skeleton on a clean base you own is a fraction of the original work. Tell us early and
> we will treat it as a scope change, not a failed delivery.

---

# ❌ 2 · TEST 2 FAILED — bone names, and no map

**Measured:** 0 of 55 §6.2 names present. The skeleton uses Renderpeople naming — `hip`,
`spine_01`, `upperarm_l`, `index_01_l`, `thumb_end_r`.

**This is allowed.** §6.1 is explicit:

> If you would rather keep your own convention, that is acceptable and it is not a concession —
> deliver a JSON map (`{"your_name": "OurName", …}`) covering all 55 bones.

**So the defect is the missing map (§12 deliverable 4), not the names.** We asked about this
too, as Q2 on 2026-09-07.

**✅ We have already written it for you** — `avatar/bone_map_renderpeople_to_mixamo.json`,
generated from your file. All 55 §6.2 bones map 1:1 onto your hierarchy with no gaps, which is
itself a good sign: your skeleton *is* §6.2's structure under different labels.

**All we need is one line back: "confirmed, that map is correct."** One bone is worth actually
looking at before you confirm:

> **`thumb_01_l` / `thumb_01_r` → `LeftHandThumb1` / `RightHandThumb1`.** §6.4 says Thumb1 is
> the **CMC**, deep in the palm near the wrist — not the web joint. If yours were the web
> joint, the map would still look valid and every `A`/`S`/`O`/`C` handshape would retarget
> wrong. **We measured it and it is the CMC** (0.50 of the wrist→index-MCP distance on the
> right, 0.44 on the left), so the map is consistent with your geometry. Confirm it anyway.

---

# ❌ 3 · TEST 9 FAILED — no `browRaise` shape key

**Measured:** `morph targets in file: 0`.

**Required by** §6.9 and §12 deliverable 7: *"Deliver a single crude `browRaise` shape key on
the blockout, purely to prove the topology supports it. Not a full set, not final quality — a
feasibility check."*

**The likely cause is one checkbox.** §6.11 requires **Data → Shape Keys = ON** in the Blender
glTF exporter. If the shape exists in your `.blend` and not in the `.glb`, that setting is off.
Please check that before rebuilding anything.

**Why we ask for it now and not in phase 2.** A raised eyebrow is what turns a statement into a
yes/no question in ASL. Today our system emits identical hand motion for *"you have pain"* and
*"do you have pain?"* — there is no way to tell them apart. The brow channel is grammar, not
decoration. We only want the one crude shape now, to prove the head topology can support the
full set later.

> ### 💡 And a question back to you, because you may have already solved this better
>
> Your file has a **working bone-based face rig** — `eyebrow_l`, `eyebrow_r`, `eyelid_l/r`,
> `jaw`, `mouth_l/r`, all properly weighted and deforming the mesh. We did not ask for that.
>
> §6.9 assumed blendshapes, but its own reasoning was *"Bones survive a mesh change, so this
> work is permanent even though the head geometry is not."* **Bone-driven brows may be strictly
> better for us than blendshapes** — they survive the phase-2 head swap, they are cheaper at
> runtime, and they are drivable by the same retarget path as everything else.
>
> **Tell us what you intended here.** If those brow bones are deliberate and you would rather
> drive the brow channel with them, we are open to changing §6.9 to match — that is a
> conversation, not a defect. What we cannot do is guess, which is the point of §6.2's line
> *"an undocumented extra bone is worse than no bone."*

---

# ❌ 4 · TEST 13 FAILED — file size and undeclared bones

### 4a · 29.2 MB, and 97% of it is one texture shipped twice

| what | bytes | share |
|---|---|---|
| geometry, skinning, bind matrices | 760 KB | 2.6% |
| `rp_claudia_rigged_002_dif` as **WebP** | 7.77 MB | 26.6% |
| `rp_claudia_rigged_002_dif` as **JPEG** | 20.65 MB | **70.7%** |

The same diffuse map is embedded **twice** — a WebP via `EXT_texture_webp` plus a JPEG
fallback. That pattern is correct glTF and we are not asking you to remove the fallback in
general; the issue is that §12 does not ask for a texture at all in phase 1:

> **Textures** — None needed in phase 1. Flat grey material.
> **Deliverable 1** — Rigged blockout character. **Neutral grey, no styling**, final
> proportions, fully skinned.

**Why the budget is real and not fussiness.** This runs in a browser, on phones, **next to a
live camera feed that is already doing MediaPipe hand tracking on the same device**. A 29 MB
download before the first sign appears is not viable, and it competes for memory with the thing
that makes the product work.

**Fix:** re-export with `Data → Material: No export`. Expect roughly **800 KB**. Keep the
textured version for your own renders — we want those for the turnarounds (§12 item 9). We just
cannot have them inside the rig file.

### 4b · 25 bones we did not ask for and cannot drive

88 joints total = **55 spec + 8 optional leg (fine) + 25 undeclared**:

| group | count | bones |
|---|---|---|
| face | 14 | `eye_l/r`, `eye_end_l/r`, `eyebrow_l/r`, `eyelid_l/r`, `eyelid_end_l/r`, `jaw`, `jaw_end`, `mouth_l/r` |
| twist | 8 | `upperarm_twist_l/r`, `lowerarm_twist_l/r`, `upperleg_twist_l/r`, `lowerleg_twist_l/r` |
| other | 3 | `root`, `foot_end_l/r` |

§6.2: *"Do not add bones we cannot drive. No twist chains driven by constraints, no helper or
corrective bones… An undocumented extra bone is worse than no bone, because it sits at bind
rotation forever and nobody knows why the mesh looks slightly wrong."*

**Two of these need a decision, the rest just need a sentence:**

- **The arm twists.** §12 allows *"at most one documented twist bone per forearm"* — two. You
  have **four** (upper arm as well as forearm). This is **Q4 from 2026-09-07**, the one we
  flagged as having *"a hard deadline at M1"*. We need to know: are they driven by constraints
  in your source (forbidden in the export), or are they free bones our runtime must drive? **A
  twist bone we do not know about sits at bind rotation forever, which looks like a rigging
  fault and is not one.** Answer as §12 deliverable 8.
- **The face bones** — see the question in §3 above.
- **`root`, `foot_end_*`, leg twists** — harmless. One line in the readme is enough.

---

# ✅ What passed, and it is the part that mattered

Recorded specifically, because these are the checks that have cost us shipped defects before.

### Test 1 — finger nodes: 42/42

```
finger nodes 40/40   wrists 2/2   every finger has exactly 4 transforms
```

**This is the requirement §6.3 exists for and the one §14 calls a hard fail.** You got it right,
including the ten weightless tip nodes.

And the positive evidence that you had the export setting right: **all 10 finger tips carry zero
weighted vertices** and are still present in the file. That means **"Export Deformation Bones
only" was OFF** — the setting §6.11 calls *"the setting most likely to silently break this
delivery."*

### Test 12 — skinning weights: clean

```
12,143 vertices    >4 influences: 0    unweighted: 0    not normalized: 0
max deviation from sum=1.0: 1.29e-07    influences/vertex: min 1, max 4, mean 1.99
```

### Test 4 — no scale channels, no stretchy IK, no animation clips

```
joints with non-unit scale: 0        animations in file: 0   (§12 forbids clips — correct)
```

### Test 14 — loads clean

No unapplied transforms. Root node rotation is identity. `extensionsRequired` empty, so a
loader without `EXT_texture_webp` falls back cleanly.

### §6.4 joint placement — the thumb, and the arch

| check | measured | verdict |
|---|---|---|
| `thumb_01` at CMC, not the web | 0.50 (R) / 0.44 (L) of wrist→index-MCP | ✅ deep in the palm |
| MCP row is an arch, not a line | 7.4 mm (R) / 5.9 mm (L) out of collinear | ✅ real arch |

§6.4 calls the thumb *"the one people get wrong"* and says the web-joint error *"breaks
handshapes A, S, O and C"* — six of our seven. You avoided it.

### Appendix D.1 finger ratios — within tolerance

| finger | R | L | spec | |
|---|---|---|---|---|
| index | 0.97 | 0.96 | 0.94 | ok |
| middle | 1.00 | 1.00 | 1.00 | ok |
| ring | 0.95 | 0.94 | 0.96 | ok |
| pinky | 0.82 | 0.82 | 0.78–0.80 | slightly long — see note |
| thumb | 0.77 | 0.75 | 0.58 *(ballpark only)* | ok |

**Pinky runs ~0.02–0.04 long.** D.1 told you to build it shorter than our own corpus figure of
0.83 because our pinky landmark is MediaPipe's noisiest. Yours is 0.82. **Not worth re-rigging
for**, but if the hand is ever revisited, shortening it is free.

### §6.6 left/right symmetry — excellent

Largest asymmetry anywhere is **2.2%** (upper arm). Fingers are within 1.8%. For a scanned base
that is better than we expected.

### §6.10 orientation, units, bind pose

| | measured | required | |
|---|---|---|---|
| up axis | +Y, height 1.840 m | +Y, ~1.7 m | ✅ |
| origin | feet at y = −0.007 | at the feet | ✅ |
| bind pose | arms **45.0°** below horizontal, both sides | A-pose, ~45° down | ✅ |
| palms | face the body, both hands | facing the body | ✅ |
| finger curl at bind | 10.0° per joint, thumbs 14.4° | ~5°, nothing straight | ✅ |
| elbow flex at bind | **25.0°** | 5–10° | ⚠️ more than asked |

**The elbow bend is the only deviation and we are not asking you to change it.** §6.10's reason
for wanting a bend at all is that a perfectly straight chain has an ill-conditioned roll
reference. 25° satisfies that more than 10° does. Noted only so it is on the record.

---

# ⏸ What we could not test, and why

| # | test | why not |
|---|---|---|
| 3 | Distal keying | needs our runtime. §14: *not a payment gate* — it tests our retargeter as much as your rig |
| 5 | Forearm twist ±90° | needs a posed rig |
| 6 | Abduction, `B` vs `5` | needs a posed rig |
| 7 | Reference-pose retarget | needs our runtime. *Not a payment gate* |
| 8 | The seven handshapes | §12 deliverable 5 not supplied |
| 10 | Extremes, no tearing | needs a posed rig |
| 11 | Contact zones | needs a posed rig |

**Five of these seven unblock the moment you send §12 deliverable 5** (the seven handshape
poses) **and deliverable 2** (the editable source). Please prioritise those two — they convert
half this table from "unknown" to "measured".

---

# 📦 §12 deliverables checklist

| # | deliverable | status |
|---|---|---|
| 1 | Rigged blockout `.glb` | ⚠️ received, but textured photoscan rather than neutral-grey blockout |
| 2 | Editable source (`.blend`) | ❌ not received |
| 3 | Bone length table | ❌ not received — **we generated it**, `avatar/bone_lengths_measured.json` |
| 4 | Bone name map | ❌ not received — **we generated it**, please confirm |
| 5 | Seven handshape poses + renders | ❌ not received — blocks 5 acceptance tests |
| 6 | Neutral signing rest pose | ❌ not received |
| 7 | `browRaise` shape key | ❌ not received (test 9) |
| 8 | Twist-solution note | ❌ not received — **Q4, hard deadline at M1** |
| 9 | Turnaround renders | ❌ not received |
| 10 | Readme | ❌ not received |

---

# ✅ The short list — what to send back

In priority order. Items 1–3 are the ones that block.

1. **The Renderpeople licence answer** (§1). Even a partial answer today is better than a
   complete one next week.
2. **"Confirmed"** on `avatar/bone_map_renderpeople_to_mixamo.json` — one line, closes test 2.
3. **The twist-solution note** (Q4, §12 item 8) — constraints or free bones, and which of the
   four arm twists we should drive.
4. **Re-export with `Material: No export`** — one checkbox, 29.2 MB → ~800 KB.
5. **Re-export with `Shape Keys: ON`** plus one crude `browRaise` — closes test 9.
6. **The `.blend` source and the seven handshape poses** — unblocks five acceptance tests.
7. **A readme**, including what you intended with the face bones.

Items 4 and 5 are the same re-export. Nothing here asks you to re-rig.

---

**Re-run the audit yourself at any point:**

```bash
python avatar/rig_audit.py "3D Char deaf.glb"          # score it
python avatar/rig_audit.py "3D Char deaf.glb" --emit    # regenerate map + length table
```

It reads only the exported file, so it will tell you what we will see before you send it.
