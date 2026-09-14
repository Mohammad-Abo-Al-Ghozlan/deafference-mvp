"""Look at the handshapes. The numbers in retarget.py say how far off they are; this says
what that looks like, which is the only way to tell whether a number is good enough.

Every metric in this project has been wrong at least once -- twice self-referentially, once
blind to the axis the fault was on -- so a rendering that a person can look at is not a
nicety, it is the check that does not share their failure mode.

Compares against the target the solver actually aimed at (hand_scale applied, translated onto
the pose wrist), not the raw landmarks: those are the signer's larger hand at the hand model's
wrist, and correcting both of those is the point.

    python avatar/render_check.py dad drink        # writes avatar/_check_<word>.png

Blue is the avatar's rig by forward kinematics through the shipped quaternions. Orange is the
target. Where they sit on top of each other the sign is being reproduced.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(r"C:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference")
sys.path.insert(0, str(REPO / "avatar"))
import retarget as R  # noqa: E402

rig = R.Rig(R.GLB)
baked = json.loads((REPO / "avatar" / "baked_signs.json").read_text(encoding="utf-8"))
scale = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
origin = (rig.wp("upperarm_l") + rig.wp("upperarm_r")) / 2.0
to_rig = lambda p: origin + np.array([p[0], -p[1], p[2]]) * scale


def fk(fq):
    W = {}
    for i in rig._order():
        q = fq.get(rig.name[i])
        lR = R.quat_to_mat(np.array(q, dtype=float)) if q is not None else rig.rest_R[i]
        p = rig.parent.get(i)
        W[i] = (rig.rest_t[i].copy(), lR.copy()) if p is None else \
            (W[p][0] + W[p][1] @ rig.rest_t[i], W[p][1] @ lR)
    return W


words = sys.argv[1:] or ["dad"]
NF = 5
for word in words:
    sign = baked["signs"][word]
    src = json.loads((R.WORDS / f"{word}.json").read_text(encoding="utf-8"))
    F = np.array(src["frames"], dtype=float)
    F[:, :, 2] = -F[:, :, 2]
    F = R.one_euro(F, fps=float(src.get("fps", 30)))
    HS = R.hand_scale(F, "r", rig)
    frames = sign["frames"]
    picks = np.linspace(0, len(frames) - 1, NF).astype(int)
    h0 = R.HAND0["r"]

    fig, axes = plt.subplots(1, NF, figsize=(3.0 * NF, 3.4), facecolor="#0d1218")
    for col, fi in enumerate(picks):
        ax = axes[col]
        ax.set_facecolor("#0d1218")
        W = fk(frames[fi])
        wrist = W[rig.by["hand_r"]][0]
        # avatar fingers, drawn wrist-relative
        for f in R.FINGER_OFF:
            ch = ["hand_r", f"{f}_01_r", f"{f}_02_r", f"{f}_03_r", f"{f}_end_r"]
            pt = np.array([W[rig.by[c]][0] - wrist for c in ch])
            ax.plot(pt[:, 0], pt[:, 1], "-o", color="#4fc3f7", lw=2, ms=3, zorder=3)
        # target: scale about its own wrist, then wrist-relative (the translation onto the
        # pose wrist cancels once both are drawn relative to their own wrist)
        if not np.any(np.isnan(F[fi, h0])):
            w0 = to_rig(F[fi, h0])
            for f, o in R.FINGER_OFF.items():
                ch = [h0] + [h0 + o + k for k in range(4)]
                pt = []
                for c in ch:
                    if np.any(np.isnan(F[fi, c])):
                        pt = []
                        break
                    pt.append((to_rig(F[fi, c]) - w0) * HS)
                if pt:
                    pt = np.array(pt)
                    ax.plot(pt[:, 0], pt[:, 1], "-o", color="#d29922", lw=1.4, ms=2.4,
                            alpha=.85, zorder=2)
        r = 0.115
        ax.set_xlim(-r, r); ax.set_ylim(-r, r)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#26313b")
        ax.set_title(f"frame {fi}", color="#7f8c98", fontsize=9)
    fig.suptitle(f"{word}   handshape error {sign['shape']}%      "
                 f"blue = avatar rig   orange = target (scaled to the rig's hand)",
                 color="#dbe4ee", fontsize=11)
    out = REPO / "avatar" / f"_check_{word}.png"
    fig.savefig(out, dpi=100, facecolor="#0d1218", bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")
