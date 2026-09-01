# Avatar Skeleton Brief — Addendum 1

**2026-09-01** · supplements `AVATAR_SKELETON_BRIEF.md` v4. **Nothing here changes scope or price.**

Forward this alongside the brief. It is six clarifications and one correction — all of them things
you would otherwise have had to ask about, plus reference material we should have sent with the
brief in the first place.

Section numbers refer to the brief.

---

## 1. Your technical contact is Salim, for everything

The brief's "Who does what" table names a developer (Ghozlan) as owner of the runtime. **That
allocation has changed and it does not affect your work** — but so you are not left guessing who to
ask:

> **Send every technical question to Salim.** Rig, data, sign language, acceptance tests, anything.
> There is no question that should go to anyone else.

Nothing about your deliverables in §12 changes.

**One consequence to be aware of.** Three acceptance tests — **3** (distal keying), **4** (bone-length
stability) and **7** (reference-pose retarget) — can only run once the rig is being driven by our
runtime. Those tests check *our* code as much as yours:

- **Test 1** (four nodes per finger, verified on the exported `.glb`) is the requirement that is
  genuinely on you. If it passes, the rig has somewhere for every landmark to go.
- **Test 3** then checks that our retargeter actually *uses* those nodes. If test 1 passes and test 3
  fails, that is our bug, not yours.

So **your P1-M1 gate is unchanged**: tests 1, 2 and 4 as written, where test 4 for you means "no
scale channels on bones and no stretchy IK in the exported file". Tests 3 and 7 move to integration
and are not a gate on your payment.

**The test harness in §11** — the player you were promised for driving your rig under real data at
P1-M3 — is being confirmed. If it is not available in time we will substitute rendered motion
previews and a longer review at P1-M3. **Ask before P1-M2 if you have not heard.**

---

## 2. What "blockout" actually means — please read, it affects your estimate

The brief says "neutral grey blockout" and that is genuinely ambiguous. It does **not** mean a crude
box-man. Several requirements imply real anatomy:

| Requirement | Implies |
|---|---|
| §9 — the hand *slides along* the passive forearm | A forearm with real anatomical form, not a cylinder |
| §6.9 — a `browRaise` shape must be demonstrable | A head with a real brow ridge and enough topology |
| §9 — contact at forehead, chin, chest | Those features must exist and be landable-on |
| §6.4 — joints at centres of rotation | Correct internal anatomy, not eyeballed |
| §10 — seven handshapes legible at 320 px | Hands at essentially final quality |

**So: an anatomically correct, cleanly topologised, properly weighted human body — with no
styling.** No textures, no clothing, no hair, no facial detail beyond the brow ridge, flat grey
material.

The distinction is **untextured and unstyled, not unfinished.** The hands in particular are final
quality in phase 1 — they are not revisited in phase 2.

> **If you priced this as something cruder, say so now.** We would much rather adjust the number at
> the start than argue about it at P1-M3. This is a clarification of what was always intended, not a
> new requirement — but if the brief read as cruder to you, that is our wording's fault and we will
> discuss it.

---

## 3. Handshape reference — we have it, and it is attached

The brief told you to "search for an ASL handshape chart" (§17). That was lazy of us. We have
rendered reference for all seven shapes, **measured from our own corpus**, and it is attached:

```
docs/handshape_review/handshape_B.png     handshape_A.png     handshape_S.png
                      handshape_1.png     handshape_5.png     handshape_C.png
                      handshape_O.png     contact_sheet.png   (all seven together)
```

Each shows the 21-point hand skeleton for that shape, viewed in the palm plane, with the anchor
words it was measured from and how tightly the takes agreed.

**Two things to notice in them:**

1. **Every finger has four points beyond the wrist.** That is §6.3 made visible — the requirement is
   not an abstraction, it is literally what the data contains.
2. **They are 2D projections into the palm plane and they are drawn at different scales.** Do not
   compare two images by eye and conclude anything; we did exactly that this morning and were
   briefly wrong (see §4).

Still worth looking at a real ASL handshape chart as well — the renders show *our measured
average*, not the canonical form.

---

## 4. The B / 5 question, now measured — with a target for you

The brief (§10) said our `B` and `5` templates "may not be as distinct as they should be" and asked
you to hand-pose them unmistakably differently. **We have now measured it properly, and the picture
is better than the brief implies.** Correcting it because you should not be chasing a problem that
is smaller than described.

```
B   index-to-pinky fan  18.7°    mean gap between adjacent fingertips  0.129 hand-lengths
5   index-to-pinky fan  31.4°    mean gap between adjacent fingertips  0.192 hand-lengths
                        +12.7°                                         +48%
```

So the templates **do** carry the together-versus-spread distinction, in the right direction, by a
real margin. What remains true is that `B` and `5` are the **second-closest of all 21 shape pairs**
(0.135 against a 0.353 median across pairs) — so they are close, but they are separable.

**Your target, as a number rather than an adjective:**

> **`B`** — adjacent fingertips **touching or nearly touching**. Gap under ~0.05 hand-lengths.
> **`5`** — adjacent fingertip gaps **at least 50% wider than your `B`**, and ideally more. Splay as
> wide as the hand comfortably goes.

This is still worth doing carefully, because it is the direct test of the **finger abduction**
requirement in §6.5 — if your MCP joints cannot abduct, these two poses come out identical and the
rig cannot express a distinction our vocabulary depends on 26 times.

*(A separate note for completeness: `5` and `C` measure even closer than `5` and `B`, at 0.125.
Neither `5` nor `O` is requested by any word in the current vocabulary, so this is not load-bearing
— just be aware `C` should read as a clear curve, not a slightly-cupped flat hand.)*

---

## 5. Software and versions

| | |
|---|---|
| **Blender** | **3.6 LTS or 4.x.** The glTF exporter's leaf-bone and shape-key handling differs in older versions, and §6.11's settings assume 3.6+. |
| **Maya** | 2022+ with a glTF exporter you have validated. Tell us which one. |
| **Anything else** | Fine, provided you can produce clean glTF 2.0 and confirm §13-B passes. |

Whatever you use, **§13-B must be run on the exported `.glb`** — the check that matters cannot be
done in the viewport.

---

## 6. Files, and when you get them

Available now, on request — ask and we send them the same day:

| File | For |
|---|---|
| `docs/handshape_review/*.png` | §10 — attached with this addendum |
| `reference_pose.json` | §6.8 — testing your retarget. **Not for modelling proportions.** |
| `handshape_templates.json` | §10 — the numeric templates behind those renders |
| `contact_sheet.png` | The vocabulary's real range of motion. Worth an early look. |
| 250 per-word motion clips | Only useful once you have something to drive. Ask at P1-M2. |

**You do not need any of these to start P1-M1.** The skeleton is fully specified by §6.2's bone table
— names, parents, and the landmark driving each one. Start there.

---

## 7. Review cadence

- **Send milestones as they are ready**, not on a schedule. We would rather see four rough gates than
  one polished delivery.
- **We respond within one working day.** If we take longer, chase us.
- **P1-M1 will get same-day turnaround** — it is a script, and it is the cheapest possible moment to
  catch the one defect this whole phase exists to prevent. Do not build a mesh before it passes.
- **Ask questions at any point, about anything, including whether a requirement is worth its cost.**
  A question in week one is free; a rebuild in week four is not.

---

## Summary of what changed

| # | What | Affects scope? |
|---|---|---|
| 1 | All technical questions go to Salim. Tests 3 and 7 move to integration. | No |
| 2 | "Blockout" = anatomically correct and unstyled, **not** crude. Hands are final quality. | **Possibly your estimate — tell us now** |
| 3 | Seven handshape reference renders attached. | No — this helps you |
| 4 | B/5 measured; the concern is smaller than the brief said. Numeric target given. | No — this reduces work |
| 5 | Blender 3.6+ / 4.x. | No |
| 6 | File list and when to ask for each. | No |
| 7 | Review cadence; P1-M1 gets same-day turnaround. | No |
