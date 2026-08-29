# Handshape template review — packet + one open measurement

`handshape_templates.json` has said this since 2026-08-12 and it has never happened:

> **review_status:** "Anchor words chosen by a hearing developer from ASL phonology. A Deaf
> reviewer should confirm each anchor forms the handshape claimed before this drives a
> shipped avatar."

This packet makes that review possible. It also surfaced one thing the review cannot settle
and a measurement can — see §3.

## 1. What the reviewer does

Open `docs/handshape_review/contact_sheet.png` (or the per-shape PNGs beside it) and fill
`docs/HANDSHAPE_REVIEW.csv` — 22 rows, one per (handshape, anchor word).

**Two verdict columns, because they have different fixes.** Collapsing them into one
"is this OK?" loses the information that says what to do next:

| column | question | if NO |
|---|---|---|
| `Q1_word_uses_this_handshape` | Does this ASL word really use this handshape? | The anchor is wrong. Re-pick it and re-measure — the template averaged the wrong thing. |
| `Q2_drawn_template_looks_right` | Does the drawn shape look like the handshape it claims? | The anchor is fine, the average is not. Raise thresholds, or fall back to the documented substitute. |

An anchor can pass Q1 and fail Q2, or the reverse.

Regenerate the packet at any time:

```
python training/render_handshape_templates.py
```

## 2. What is already known, so the reviewer is not asked twice

- **`O` is unusable and that is not a measurement problem.** All 250 words were checked on
  2026-08-12: `flower` and `home` are flattened-O (a *different* handshape) and `old` is a
  dynamic C-to-S. No clean O anchor exists in this vocabulary. Review is confirmation only.
- **`S` rests on a single anchor** (`yes`), so its agreement is within-word across takes —
  which can detect an *inconsistent* anchor but never a *wrong* one. `milk` and `orange` were
  dropped as anchors because both squeeze during the sign.
- **Only five shapes are actually load-bearing.** The 35 class-2a words need
  **B 26 · A 3 · 1 3 · C 2 · S 1**. `5` and `O` are emitted but unused, so a bad `5` costs
  nothing today. **A bad `B` costs 26 of 35 words** — start there.

## 3. ⚠️ OPEN: the `usable` flag never checked that two shapes DIFFER

`build_handshape_templates.py:293` sets

```python
good = ag_xy <= 0.20 and meta["conf"] == "high"
```

That is a **within-shape** criterion. It asks whether the takes of one handshape agree with
each other. It never asks whether **B** can be told apart from **5**. A set of templates can
pass it while being mutually indistinguishable, and nothing downstream would notice — the
avatar would render a confident wrong handshape on 26 words.

Measured on the shipped templates, `B` and `5` are the closest pair by every measure tried:

| measure | B/5 | interpretation |
|---|---|---|
| 21-point median distance ÷ within-shape agreement | **0.85** | below 1.0 — but see the caveat |
| fingertip-only mean displacement | **0.178** | the smallest of all 21 pairs |
| lateral spread of index..pinky tips | B 0.480 vs 5 0.732 | *correct direction* — B is tighter, as it should be |

**This is a flag, not a verdict, and the first row is the reason.** The palm frame is
constructed from the wrist, index MCP and middle MCP, so those points are near-identical
between any two templates *by construction* — which deflates every between-shape distance.
The fingertip measure avoids that but has no denominator, because the JSON carries no
within-shape fingertip scatter.

**The test that closes it** needs the raw takes (Kaggle, not in this repo): compute the
within-shape scatter *of the fingertips only*, and compare it to the 0.178 between-shape
fingertip displacement. If within-shape tip scatter is well under 0.178, B and 5 are
genuinely separated and the low ratio was the structural artefact. If it is comparable,
`B` does not carry its contrast and 26 of 35 two-handed words render the wrong handshape.

Until that runs, `Q2` on the `B` rows is the most valuable cell in the sheet: a reviewer
looking at `handshape_B.png` and `handshape_5.png` side by side can say whether they read as
different handshapes, which is the question that actually matters.
