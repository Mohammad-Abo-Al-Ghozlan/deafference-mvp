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


words = [w for w in sys.argv[1:] if not w.startswith("-")] or ["dad"]
# --body draws both whole arms instead of one hand close up. That is the only view in which a
# synthesized passive hand can be checked at all: its error is WHERE it is and which way it
# faces, and a wrist-relative close-up throws both of those away.
BODY = "--body" in sys.argv[1:]
NF = 5
for word in words:
    sign = baked["signs"][word]
    src = json.loads((R.WORDS / f"{word}.json").read_text(encoding="utf-8"))
    F = np.array(src["frames"], dtype=float)
    F[:, :, 2] = -F[:, :, 2]
    F = R.one_euro(F, fps=float(src.get("fps", 30)))
    # REPRODUCE THE SYNTHESIS THE BAKE ACTUALLY DID, all of it. This used to apply only the
    # HAND mirror, so on a `mirror+arm` word the orange target hand was drawn at the signer's
    # PARKED passive wrist -- down by the hip -- while the rig showed the correctly mirrored
    # limb up in signing space. The two were a foot apart on screen and the bake was right
    # both times. A diagnostic that reports a fault the thing under test does not have is
    # worse than no diagnostic; `synth` names which branch ran, so read it instead of guessing.
    synth = sign.get("synth")
    if synth == "base":
        F, _placed = R.unmarked_base(F, word, "r")
    elif synth:                                   # "mirror" or "mirror+arm"
        if synth.endswith("+arm"):
            F, _ = R.mirror_passive_arm(F, "r")
        F = R.mirror_passive_hand(F, "r")
    HS = {s: R.hand_scale(F, s, rig) for s in ("l", "r")}
    # NOTE, because it misled me once: on a synthesized hand this can come back several times
    # the dominant hand's, so the ORANGE TARGET below is drawn far longer than the rig's hand.
    # That is the target's drawn size, not the rig's -- the solve keeps the finger DIRECTIONS
    # and the rig's bone lengths are fixed, so the handshape is unaffected. Do not "fix" it by
    # sharing the dominant scale: measured against the authored template that is worse on 25
    # of 35 words. See the TRIED AND REJECTED note in retarget.retarget_word.
    frames = sign["frames"]
    # THE BAKED TRACK IS NOT THE SOURCE TRACK. retime() prepends hold_in copies of the first
    # frame and appends hold_out of the last, and may stretch the stroke, so baked frame i
    # corresponds to source frame (i - hold_in) / stretch. Indexing the source with a baked
    # index read past the end of short clips, which is how this script broke.
    hi, st = sign.get("hold_in", 0), float(sign.get("stretch", 1.0) or 1.0)
    picks = np.linspace(0, len(frames) - 1, NF).astype(int)
    sides = ("r",) if not sign.get("synth") else ("r", "l")

    fig, axes = plt.subplots(1, NF, figsize=(3.0 * NF, 3.4), facecolor="#0d1218")
    for col, fi in enumerate(picks):
        ax = axes[col]
        ax.set_facecolor("#0d1218")
        W = fk(frames[fi])
        si = int(np.clip(round((fi - hi) / max(st, 1e-6)), 0, len(F) - 1))
        anchor = np.zeros(3) if BODY else W[rig.by["hand_r"]][0]
        for s_ in (("l", "r") if BODY else sides[:1]):
            h0 = R.HAND0[s_]
            if BODY:
                arm = [f"upperarm_{s_}", f"lowerarm_{s_}", f"hand_{s_}"]
                pt = np.array([W[rig.by[c]][0] - anchor for c in arm])
                ax.plot(pt[:, 0], pt[:, 1], "-o", color="#4fc3f7", lw=2, ms=4, zorder=3)
            for f in R.FINGER_OFF:
                ch = [f"hand_{s_}", f"{f}_01_{s_}", f"{f}_02_{s_}", f"{f}_03_{s_}",
                      f"{f}_end_{s_}"]
                pt = np.array([W[rig.by[c]][0] - anchor for c in ch])
                ax.plot(pt[:, 0], pt[:, 1], "-o", color="#4fc3f7", lw=2, ms=3, zorder=3)
            # target: scale about its own wrist, then wrist-relative (the translation onto the
            # pose wrist cancels once both are drawn relative to their own wrist)
            if np.any(np.isnan(F[si, h0])):
                continue
            w0 = to_rig(F[si, h0])
            base = (w0 - anchor) if BODY else np.zeros(3)
            for f, o in R.FINGER_OFF.items():
                ch = [h0] + [h0 + o + k for k in range(4)]
                pt = []
                for c in ch:
                    if np.any(np.isnan(F[si, c])):
                        pt = []
                        break
                    pt.append(base + (to_rig(F[si, c]) - w0) * HS[s_])
                if pt:
                    pt = np.array(pt)
                    ax.plot(pt[:, 0], pt[:, 1], "-o", color="#d29922", lw=1.4, ms=2.4,
                            alpha=.85, zorder=2)
        if BODY:
            ax.set_xlim(-0.45, 0.45); ax.set_ylim(1.05, 1.75)
        else:
            r = 0.115
            ax.set_xlim(-r, r); ax.set_ylim(-r, r)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#26313b")
        ax.set_title(f"frame {fi}", color="#7f8c98", fontsize=9)
    fig.suptitle(f"{word}   handshape error {sign['shape']}%   "
                 f"{sign.get('class', '?')} {sign.get('synth') or 'tracked'}      "
                 f"blue = avatar rig   orange = target (scaled to the rig's hand)",
                 color="#dbe4ee", fontsize=11)
    out = REPO / "avatar" / f"_check_{word}.png"
    fig.savefig(out, dpi=100, facecolor="#0d1218", bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {out}")
