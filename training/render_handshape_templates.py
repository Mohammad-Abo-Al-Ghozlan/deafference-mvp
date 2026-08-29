#!/usr/bin/env python3
"""
Render the measured handshape templates so a Deaf reviewer can actually see them.

`handshape_templates.json` says it plainly:

    review_status: "Anchor words chosen by a hearing developer from ASL phonology.
                    A Deaf reviewer should confirm each anchor forms the handshape
                    claimed before this drives a shipped avatar."

That review has never happened, and it cannot happen from a JSON file — a reviewer
needs to LOOK at the shape. This script draws each template's 21-point hand skeleton
in its palm frame and writes one PNG per handshape plus a contact sheet.

There are TWO separate questions, and the review sheet keeps them apart because they
have different fixes:

  Q1  LINGUISTIC — does the anchor word really use this handshape in ASL?
      A wrong anchor means the template averaged the wrong thing. Fix = re-pick the
      anchor and re-measure.
  Q2  MEASUREMENT — does the drawn template LOOK like the handshape it claims?
      A right anchor can still average badly if MediaPipe tracked it poorly. Fix =
      raise thresholds or drop the shape to its documented fallback.

An anchor can pass Q1 and fail Q2, or the reverse. Collapsing them into one
"is this OK?" column loses the information that tells you what to do next.

The `agreement_*` numbers are mean within-shape distance in palm-frame units (LOWER
is better; the file's own `usable` flag is the author's threshold call). They are
printed on each panel so a reviewer's visual verdict can be read against the
measurement instead of in place of it.

Usage:
  python training/render_handshape_templates.py                    # -> docs/handshape_review/
  python training/render_handshape_templates.py --xyz              # use the 3D template
  python training/render_handshape_templates.py --out somewhere/
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # no display on a headless/Kaggle run
import matplotlib.pyplot as plt

# MediaPipe's 21-point hand topology. Index 0 is the wrist; each finger is a chain
# from its MCP out to the tip; the palm arc closes MCP to MCP.
FINGERS = {
    "thumb":  [0, 1, 2, 3, 4],
    "index":  [0, 5, 6, 7, 8],
    "middle": [0, 9, 10, 11, 12],
    "ring":   [0, 13, 14, 15, 16],
    "pinky":  [0, 17, 18, 19, 20],
}
PALM = [5, 9, 13, 17]
COLORS = {"thumb": "#d1495b", "index": "#00798c", "middle": "#edae49",
          "ring": "#66a182", "pinky": "#8f2d56"}


def draw(ax, pts, shape, meta, key):
    for name, chain in FINGERS.items():
        xs = [pts[i][0] for i in chain]
        ys = [pts[i][1] for i in chain]
        ax.plot(xs, ys, "-o", color=COLORS[name], lw=2.2, ms=4.5, zorder=3)
    ax.plot([pts[i][0] for i in PALM], [pts[i][1] for i in PALM],
            "-", color="#9aa0a6", lw=1.4, zorder=2)
    ax.plot(pts[0][0], pts[0][1], "s", color="#202124", ms=7, zorder=4)   # wrist

    usable = "USABLE" if meta.get("usable") else "NOT USABLE"
    conf = meta.get("anchor_confidence", "?")
    agr = meta.get(f"agreement_{key.split('_')[1]}", meta.get("agreement_xy"))
    ax.set_title(f"{shape}   [{usable}, anchor confidence {conf}]\n"
                 f"{meta['description'][:70]}", fontsize=9, pad=8)
    ax.text(0.02, 0.02,
            f"anchors: {', '.join(meta['anchor_words'])}\n"
            f"{meta['n_takes']} takes   agreement {agr}  (lower = tighter)",
            transform=ax.transAxes, fontsize=7.5, va="bottom", color="#3c4043")
    ax.set_aspect("equal")
    ax.invert_yaxis()          # palm-frame y is DOWN, same convention as the contract
    ax.axis("off")


TIPS = [4, 8, 12, 16, 20]           # thumb, index, middle, ring, pinky fingertips


def separation_report(shapes):
    """Are two DIFFERENT handshapes actually distinguishable from each other?

    `build_handshape_templates.py:293` sets usable as `ag_xy <= 0.20 and conf == 'high'`.
    That is a WITHIN-shape criterion: it asks whether the takes of one shape agree, never
    whether two shapes differ. A set of templates can pass it while being mutually
    indistinguishable, and nothing downstream would notice — the avatar would render a
    confident wrong handshape.

    Two measures, because each has a flaw the other does not:

      all-21-point median, vs the shape's own agreement_xy — same statistic as the file's,
        but DEFLATED: the palm frame is constructed from wrist + index MCP + middle MCP, so
        those points are near-identical between any two templates by construction.
      fingertip-only mean — immune to that, since handshape lives in the tips. But there is
        no matching within-shape fingertip scatter in the JSON, so it has no denominator.

    Neither closes the question alone. What closes it is the fingertip scatter WITHIN each
    shape, which needs the raw takes (Kaggle, not in this repo) — see docs/HANDSHAPE_REVIEW.md.
    """
    import itertools

    import numpy as np

    full = {s: np.array(m["template_xy"], float) for s, m in shapes.items()}
    tips = {s: v[TIPS] for s, v in full.items()}
    within = {s: m["agreement_xy"] for s, m in shapes.items()}

    print("\nSEPARATION — can two different handshapes be told apart?")
    print(f"{'pair':10}{'21pt med':>10}{'ratio':>8}{'tips':>8}   (ratio <1 = closer than "
          f"one shape's own scatter)")
    rows = []
    for a, b in itertools.combinations(full, 2):
        m21 = float(np.median(np.linalg.norm(full[a] - full[b], axis=1)))
        mt = float(np.linalg.norm(tips[a] - tips[b], axis=1).mean())
        rows.append((m21 / max(within[a], within[b]), a, b, m21, mt))
    for r, a, b, m21, mt in sorted(rows)[:6]:
        print(f"{a}/{b:<8}{m21:10.4f}{r:8.2f}{mt:8.3f}")
    print("⚠️  The ratio column is DEFLATED (structural points) — read it as a flag to check, "
          "not a verdict.")


def main():
    ap = argparse.ArgumentParser(description="render handshape templates for Deaf review")
    ap.add_argument("--templates", type=Path, default=Path("handshape_templates.json"))
    ap.add_argument("--out", type=Path, default=Path("docs/handshape_review"))
    ap.add_argument("--xyz", action="store_true",
                    help="draw template_xyz instead of template_xy (z is noisy — see z_warning)")
    args = ap.parse_args()

    doc = json.loads(args.templates.read_text(encoding="utf-8"))
    key = "template_xyz" if args.xyz else "template_xy"
    shapes = doc["handshapes"]
    args.out.mkdir(parents=True, exist_ok=True)

    # one panel per shape
    for shape, meta in shapes.items():
        fig, ax = plt.subplots(figsize=(3.4, 3.8), dpi=170)
        draw(ax, meta[key], shape, meta, key)
        fig.tight_layout()
        safe = shape.replace("/", "_")
        fig.savefig(args.out / f"handshape_{safe}.png", bbox_inches="tight")
        plt.close(fig)

    # contact sheet
    n = len(shapes)
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.4 * cols, 3.8 * rows), dpi=150)
    for ax, (shape, meta) in zip(axes.ravel(), shapes.items()):
        draw(ax, meta[key], shape, meta, key)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.suptitle(f"ASL handshape templates — measured, {doc['date']}   "
                 f"({'3D' if args.xyz else '2D'} palm frame)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(args.out / "contact_sheet.png", bbox_inches="tight")
    plt.close(fig)

    # the review sheet — one row per (handshape, anchor word), two verdict columns
    sheet = args.out.parent / "HANDSHAPE_REVIEW.csv"
    with open(sheet, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["handshape", "description", "anchor_word", "n_takes",
                    "author_confidence", "usable", "agreement_xy",
                    "Q1_word_uses_this_handshape", "Q2_drawn_template_looks_right",
                    "reviewer", "notes"])
        for shape, meta in shapes.items():
            for word in meta["anchor_words"]:
                w.writerow([shape, meta["description"], word,
                            meta.get("takes_per_word", {}).get(word, ""),
                            meta.get("anchor_confidence", ""),
                            "yes" if meta.get("usable") else "NO",
                            meta.get("agreement_xy", ""), "", "", "", ""])

    separation_report(shapes)

    print(f"wrote {len(shapes)} panels + contact_sheet.png -> {args.out}")
    print(f"wrote review sheet -> {sheet}")
    print("\nFill Q1 and Q2 with YES / NO. They are different questions:")
    print("  Q1 NO -> the anchor is wrong; re-pick it and re-measure the template.")
    print("  Q2 NO -> the anchor is fine but the average is bad; raise thresholds or")
    print("           fall back to the documented substitute handshape.")
    unusable = [s for s, m in shapes.items() if not m.get("usable")]
    if unusable:
        print(f"\n⚠️  already known unusable, review is confirmation only: {', '.join(unusable)}")


if __name__ == "__main__":
    main()
