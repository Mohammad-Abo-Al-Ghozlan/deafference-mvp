# Re: v7 CORRECTED — all three rig changes done, §6.1 implemented, and one limit I can measure

**To:** Mohammad Salim
**From:** animation / retargeting
**Attached:** `template-check.mjs`, rebuilt player (250 signs, native durations)

---

## 0. Your three changes

| | |
|---|---|
| **① read `dominantHand`, stop re-deriving** | **Done** — landed last round, verified on this export |
| **② read `len(frames)` per word** | **Was already correct — but it exposed a real bug of mine** — §1 |
| **③ implement §6.1** | **Done. 2s mirroring + 2a templates, 87/87 words** — §2 |

Full pipeline on the corrected export: **250/250 anatomy gate**, 0 hyperextended joints,
jitter 0.28–0.58 vs the signer's 0.909, rig suite 60/60. Player rebuilt on the original
`model.glb`, byte-identical embed, native durations throughout.

Your acceptance script reads as you predicted — everything passes except `finish`, which we've
agreed is a tie-break definition and not a hole.

---

## 1. ② — duration was already right, and that hid a bug

The retargeter derives duration from `F.length` and the last key, never from a constant, so
the switch to native lengths worked with no change. I verified rather than read the code:
`tiger` 9 frames → 0.30 s, `puppy` 116 → 3.87 s, both correct.

**But something else was tuned against 2.13 s and broke silently.** My rest lead-in and
lead-out were fixed at 0.25 s each — 12% of a 64-frame clip, invisible. On `tiger` at 0.30 s
that's a 0.50 s approach around a 0.30 s sign: **the lead was 61% of the clip** and the sign
read as a brief event inside a long ease.

Nothing errored. The clip just stopped being a sign. Now scaled: `min(0.25 s, 15% of the
clip)`.

```
          sign     clip     lead as % of clip
  tiger   0.30s    0.35s    13%      (was 61%)
  puppy   3.87s    4.33s    11%
```

Worth flagging to whoever else consumes this: **"read `len(frames)`" is necessary but not
sufficient.** Anything calibrated when every clip was 2.13 s needs re-checking — leads,
smoothing windows, minimum-duration assumptions. Reading the field correctly and then applying
a constant tuned for the old length is the failure that won't announce itself. Mine was the
lead; I'd guess a captions or playback layer has a similar constant.

---

## 2. ③ — §6.1 implemented, both classes

```
words using 2s mirroring (mirror_dominant_handshape) : 52
words using 2a template  (unmarked_handshape_at_base): 35
                                                        87/87
```

**2a placement.** The template is read into the canonical palm frame you documented — origin
at the wrist, x toward the index MCP, z = index × pinky, scaled by |wrist → middle MCP|,
reflected in z for the left hand — and applied by aiming phalanges. Aiming is safe here for
exactly the reason it wasn't for 2s: the wrist keeps its own orientation from the pose-block
knuckles, so chirality is carried by the wrist rather than by the finger directions. It's the
same path the real-landmark solver uses and inherits the same hinge clamps.

I used `template_xyz` rather than `template_xy` despite your z warning. `agreement_xyz` is
slightly worse for every shape (B 0.143 vs 0.131), but `template_xy` is planar, and a planar C
is not a C — it's a flat hand. Small extra noise beats a shape that doesn't exist in 3D.

**A bug worth repeating back to you**, since it's the same species as the ones we've been
trading: I wrote a second finger→landmark-index table next to the one that already existed,
and keyed the pinky `Pinky`. This rig names it `Little`. The lookup returned undefined, the
2a branch never fired, and the log said nothing — a relaxed hand where a template should have
been. No error, no warning, and the "template applied" counter simply stayed at zero. I only
caught it because the counter was zero, not because anything failed.

---

## 3. 🟡 What the 2a hands actually render as — measured, and it has a ceiling

"Template applied" is a check with no power, so I read the rendered hand back out of the clip,
expressed it in your palm frame, and scored it against **all seven** templates.

```
requested shape is the NEAREST of 7 templates : 8/35 = 23%   (chance ~14%)
```

That looked bad, so I measured the templates against each other in the same metric before
concluding anything:

```
inter-template distances:  closest pair 0.183   median pair 0.432
B vs C specifically        0.206
rendered-hand error vs its target   ~0.150
```

**The placement is working; the metric can't resolve it.** The rendered hand sits ~0.150 from
its requested shape against a median of 0.432 to a random shape and 0.606 to the worst — so
it's clearly in the right family. But B and C are only 0.206 apart, and a 0.150 reconstruction
error exceeds half that gap, so nearest-neighbour flips between them. Every mis-assignment in
the table is B→C. None is B→S or B→A.

**Why the ~0.150 exists, and why it won't go to zero:** I match bone *directions*, not joint
positions. The signer's finger proportions aren't the avatar's, so matching every phalanx
direction still accumulates positional drift by the fingertip. Hinge clamps add to it — 70
clamped on `tree` alone, and clamping a flat B curls it, which is precisely the direction of C.

**Practical consequence:** B is 26 of your 35 assignments and C is 2, and B↔C is the confusable
pair. So ~26 words render a *slightly cupped flat hand* rather than a crisp flat B. For a
static passive base that is acceptable and reads as a hand; it is not a crisp handshape, and I
don't want it recorded as one.

This bounds what the 2a path can deliver on this rig, independent of your template quality. If
a Deaf reviewer says a base hand looks wrong, the first question is whether it's the
assignment (yours) or this ~0.15 reconstruction floor (mine) — `template-check.mjs` is attached
so we can tell those apart rather than guess.

---

## 4. On `handshape_templates.json`

Confirming what you'll want confirmed, from the file rather than the summary:

- **`n_usable: 6`** — `1 5 B A S C` usable, `O` not (`agreement_xy` 0.286, flagged
  `usable: false`), resolved to `C`.
- **`S` is measured**, `agreement_xy` 0.1636, n=40, `usable: true`. So the doc's §0.3 line
  describing "5 measured + `S→A`, `O→C`" is stale in two ways: `S` is measured, and the count
  is 6. Worth correcting since it understates what you shipped.
- **`O` is required by no 2a word.** Assignments are B 26, A 3, 1 3, C 2, S 1 = 35. **The O→C
  substitution never fires**, so the one unmeasurable shape costs us nothing on the current
  vocabulary. Worth stating plainly in the file — as written, a reader has to cross-reference
  the assignments to discover the only documented approximation is inert.
- **The self-disclaimer is the right call** and I've taken it as written: the 2a passive shapes
  are provisional, so a wrong-looking shape is a lexicon fix on your side, not a rig bug on
  mine. §3 gives us a way to tell which.

---

## 5. Where things stand

One-handed (163): done. 2s (52): done, handshape mirroring exact.
2a (35): rendering, with the ~0.15 shape-fidelity floor in §3 **and** the contact problem from
my last message — the base hand is placed at the recorded passive wrist, which in 33 of 35
takes is 45–55 cm from where the sign needs it. Correct shape, wrong place, is still wrong.

So my ordering is unchanged: **the 2a contact filter is worth more than any further work on
handshape fidelity.** A crisp B in the wrong location reads worse than a soft B in the right
one, and right now we have a soft B in the wrong location.

Nothing blocking. Player is rebuilt and current if you want to look at `tree` or `table`.

---

On the pattern: my `Pinky`/`Little` bug and your gap-fill probe are the same shape — a lookup
that silently returns nothing, reported as success. The thing that caught mine was a counter
reading zero when it should have read 35. Counters that should be non-zero are cheap, and
they're the only reason I noticed at all.
