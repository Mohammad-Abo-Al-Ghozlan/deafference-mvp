#!/usr/bin/env python3
"""Drive the rigger's skeleton with our 75-landmark motion and bake the result to quaternions.

This is acceptance tests 3 and 7 from AVATAR_BRIEF_COMPLETE.md v6.1 -- the two the M1 audit
could not run because they need a retargeter. §14 is explicit that they "check our retargeter
as much as your rig", so a bad result here is not automatically the rigger's fault, and the
per-bone error numbers printed below are what separate the two.

THE THREE THINGS THAT MAKE THIS NOT A STRAIGHT COORDINATE COPY, all from the brief:

§3.1  We have POSITIONS, not rotations. A skeleton is driven by rotations, so every bone's
      rotation has to be recovered from where its two endpoints ended up.
§3.2  Depth is half-missing. `hello`'s z ranges over 7.7 units where the whole body is ~2 wide
      -- it is noise, not depth. So z is NOT read from the data; it is SOLVED, by requiring
      each bone to keep the rest length it has in the rig. That is §3.2's own prescription:
      "bone length is how we recover it".
§6  A missing hand is null, never [0,0,0], because the origin is mid-sternum and zeros would
      draw the hand inside the chest. `hello` is one-handed: its passive hand is 100% NaN, and
      that hand must therefore HOLD ITS REST POSE rather than be driven to the origin.

Usage:
    python avatar/retarget.py hello mom water            # bake, print per-word error
    python avatar/retarget.py --all-medical --out X.json
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
GLB = REPO / "3D Char deaf [untextured].glb"
WORDS = REPO / "animation_handoff" / "words"

# ── §7 landmark indices. pose 0-32, left hand 33-53, right hand 54-74. ───────────────────
NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 0, 11, 12, 13, 14, 15, 16
HAND0 = {"l": 33, "r": 54}          # wrist landmark of each hand block
# offset of each finger's 4 nodes within a 21-point hand block
FINGER_OFF = {"thumb": 1, "index": 5, "middle": 9, "ring": 13, "pinky": 17}

# Only ever toggled by selftest(), to prove the `front` metric can detect a wrong z axis.
# Nothing else should touch it.
_FLIP_Z = True

# How much of the head's rotation the neck carries. A head that swivels on a rigid neck reads
# as a bobblehead; a third is enough to make the motion come from the body.
NECK_SHARE = 0.35

# One-Euro parameters for the rotation-space filter. Measured, see smooth_quats().
# How far past the shoulder plane an elbow must sit before the in-front prior overrides the
# depth solver, in shoulder widths. Measured below.
FRONT_MARGIN = 0.20

# The per-frame wrist step, in shoulder widths, that a clean clip shows. Clips noisier than
# this get proportionally more smoothing. `hello` measures 0.084.
NOISE_REF = 0.10

Q_MIN_CUTOFF = 3.0
Q_BETA = 0.02

# the landmarks the metrics need, kept per frame so scoring happens AFTER filtering
_METRIC_LM = ([L_WR, R_WR] + [HAND0[x] for x in ("l", "r")]
              + [HAND0[x] + o + 3 for x in ("l", "r") for o in FINGER_OFF.values()])


# ── GLB rest skeleton ────────────────────────────────────────────────────────────────────
def load_skeleton(path):
    raw = path.read_bytes()
    _, _, total = struct.unpack_from("<4sII", raw, 0)
    ch, off = {}, 12
    while off < total:
        clen, ctype = struct.unpack_from("<I4s", raw, off)
        ch[ctype.strip(b"\x00")] = raw[off + 8: off + 8 + clen]
        off += 8 + clen + (-clen % 4)
    G = json.loads(ch[b"JSON"].decode("utf-8"))
    nodes = G["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    name = {i: n.get("name", f"node{i}") for i, n in enumerate(nodes)}
    by = {v: k for k, v in name.items()}
    return G, nodes, parent, name, by


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R):
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, \
            (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, \
            (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, \
            (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, \
            (R[1, 2] + R[2, 1]) / s, 0.25 * s
    q = np.array([x, y, z, w])
    return q / np.linalg.norm(q)


def local_trs(n):
    if "matrix" in n:
        M = np.array(n["matrix"], dtype=float).reshape(4, 4).T
        return M[:3, 3].copy(), M[:3, :3].copy()
    t = np.array(n.get("translation", [0, 0, 0]), dtype=float)
    R = quat_to_mat(np.array(n.get("rotation", [0, 0, 0, 1]), dtype=float))
    s = np.array(n.get("scale", [1, 1, 1]), dtype=float)
    return t, R * s


def align(a, b):
    """Rotation taking unit vector a to unit vector b."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.999999:                       # antiparallel: any perpendicular axis
        axis = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0, 1.0, 0])
        axis /= np.linalg.norm(axis)
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + 2 * K @ K
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


class Rig:
    def __init__(self, path):
        self.G, self.nodes, self.parent, self.name, self.by = load_skeleton(path)
        self.joints = self.G["skins"][0]["joints"]
        self.rest_t, self.rest_R = {}, {}
        for i in range(len(self.nodes)):
            t, R = local_trs(self.nodes[i])
            self.rest_t[i], self.rest_R[i] = t, R
        self.world_rest = {}
        for i in self._order():
            p = self.parent.get(i)
            if p is None:
                self.world_rest[i] = (self.rest_t[i].copy(), self.rest_R[i].copy())
            else:
                pt, pR = self.world_rest[p]
                self.world_rest[i] = (pt + pR @ self.rest_t[i], pR @ self.rest_R[i])

    def _order(self):
        out, seen = [], set()

        def rec(i):
            if i in seen:
                return
            seen.add(i)
            out.append(i)
            for c in self.nodes[i].get("children", []):
                rec(c)
        for i in range(len(self.nodes)):
            if i not in self.parent:
                rec(i)
        return out

    def wp(self, n):
        return self.world_rest[self.by[n]][0]

    def bone_len(self, a, b):
        return float(np.linalg.norm(self.wp(b) - self.wp(a)))


# ── the driven chains: (bone, child-for-direction, from-landmark, to-landmark) ───────────
def build_chains(rig):
    ch = []
    for side, sh, el, wr in (("l", L_SH, L_EL, L_WR), ("r", R_SH, R_EL, R_WR)):
        h0 = HAND0[side]
        ch.append((f"upperarm_{side}", f"lowerarm_{side}", sh, el))
        ch.append((f"lowerarm_{side}", f"hand_{side}", el, wr))
        # the hand's own direction: wrist -> middle MCP, the most stable palm axis
        ch.append((f"hand_{side}", f"middle_01_{side}", h0, h0 + FINGER_OFF["middle"]))
        for f, o in FINGER_OFF.items():
            for k in (1, 2, 3):
                nxt = f"{f}_0{k+1}_{side}" if k < 3 else f"{f}_end_{side}"
                ch.append((f"{f}_0{k}_{side}", nxt, h0 + o + k - 1, h0 + o + k))
    return ch


def build_tree(rig):
    """(landmark, parent landmark, rest length) in solve order, outward from each shoulder.

    An explicit tree, because the first version derived parents from the bone chain list and
    the finger chains then had no parent entry for their MCP -- so every finger silently
    became its own root anchored at the rig's REST position and the hands stayed behind while
    the arms moved. A tree that is written down cannot do that quietly.
    """
    t = []
    for side, sh, el, wr in (("l", L_SH, L_EL, L_WR), ("r", R_SH, R_EL, R_WR)):
        h0 = HAND0[side]
        t.append((el, sh, rig.bone_len(f"upperarm_{side}", f"lowerarm_{side}")))
        t.append((wr, el, rig.bone_len(f"lowerarm_{side}", f"hand_{side}")))
        # NOT the same joint, despite being the same anatomy. MediaPipe Pose's wrist and
        # MediaPipe Hands' wrist are outputs of two SEPARATE models fused into one 75-point
        # frame, and they disagree: measured over the 11 signs, the gap runs 19-66% of a palm
        # length (worst on `dad`, best on `no`). Welding them with L = 0.0 was what destroyed
        # the handshapes -- every finger was then aimed from an origin up to two-thirds of a
        # palm away from the frame its own landmarks live in. retarget_word() now rigidly
        # translates the whole hand block onto the pose wrist before this runs, so by the time
        # we get here the two really are coincident and the zero length is honest.
        t.append((h0, wr, 0.0))
        for f, o in FINGER_OFF.items():
            t.append((h0 + o, h0, rig.bone_len(f"hand_{side}", f"{f}_01_{side}")))
            for k in (1, 2, 3):
                nxt = f"{f}_0{k+1}_{side}" if k < 3 else f"{f}_end_{side}"
                t.append((h0 + o + k, h0 + o + k - 1,
                          rig.bone_len(f"{f}_0{k}_{side}", nxt)))
    return t


def one_euro(F, fps=30.0, min_cutoff=2.0, beta=0.4):
    """The filter §6.12 failure mode #9 prescribes, applied to every landmark channel.

    §3.3: "Landmarks jitter... This is a property of the source recordings, not a bug awaiting
    a fix." §6.12 lists "everything buzzes or shimmers, especially the fingers" as failure #9,
    owns it on OUR side, and names the remedy: "One-Euro or moving-average filter at render
    time". This is that filter, and not applying it was simply a step I skipped.

    One-Euro rather than a moving average because its cutoff adapts to speed: it smooths hard
    while a hand is nearly still, where jitter dominates, and barely at all through a fast
    transition, where a fixed window would smear the handshape change that carries the
    meaning. beta is the speed coupling; min_cutoff sets the floor.

    NaN runs are left untouched -- a missing hand must stay missing so it holds rest (§6),
    never be interpolated into existence here.

    THE DEFAULTS ARE MEASURED, not guessed. Smoothing genuinely trades handshape fidelity for
    stability, so one number cannot choose them; both failure modes were scored across a grid,
    over all 11 signs, with fingertip error taken against the RAW landmarks rather than the
    filtered ones (scoring a smoothed result against its own smoothed input is
    self-referential -- more filtering would keep flattering itself while the avatar drifted
    further from what the signer actually did):

        setting                 popping frames    fingertip err vs raw
        no filter                     70                14.7%
        mc 4.5  beta 0.02             26                16.5%
        mc 2.0  beta 0.40             15                19.2%   <- the knee, shipped
        mc 1.2  beta 0.02              9                21.8%
        mc 0.8  beta 0.00              6                24.6%

    Note that the setting which minimises POPPING is the worst for handshape, and the one
    that minimised WRIST error was worst of all -- which is why wrist error alone was never
    enough to tell whether this was working.
    """
    out = F.copy()
    n, m, _ = F.shape
    prev_x = np.full((m, 3), np.nan)
    prev_dx = np.zeros((m, 3))
    for i in range(n):
        x = F[i]
        fresh = np.isnan(prev_x[:, 0]) & ~np.isnan(x[:, 0])
        prev_x[fresh] = x[fresh]
        ok = ~np.isnan(x[:, 0]) & ~np.isnan(prev_x[:, 0])
        if ok.any():
            dx = (x[ok] - prev_x[ok]) * fps
            a_d = 1.0 / (1.0 + fps / (2 * np.pi * 1.0))
            prev_dx[ok] = a_d * dx + (1 - a_d) * prev_dx[ok]
            cutoff = min_cutoff + beta * np.abs(prev_dx[ok])
            a = 1.0 / (1.0 + fps / (2 * np.pi * cutoff))
            sm = a * x[ok] + (1 - a) * prev_x[ok]
            out[i][ok] = sm
            prev_x[ok] = sm
        prev_x[np.isnan(x[:, 0])] = np.nan          # a gap resets the filter state
    return out


def smooth_z(F, win=7):
    """Moving average of the z channel only, NaN-aware.

    z is the noisy channel, and the depth solver has to make a BINARY choice from it: each
    bone's quadratic has two roots, one in front of the image plane and one behind. Taking
    that decision per frame from the raw z meant that every time the noise crossed zero the
    bone snapped through the plane -- measured at 100-178 degrees of rotation in a single
    30 fps frame, on up to 15 frames of a 21-frame clip. Nothing anatomical moves like that;
    it reads as the hand tearing.

    Smoothing first makes the decision follow the sustained trend instead of the noise, while
    still allowing a genuine turn of the hand to flip it. Only the SIGN is taken from this --
    the depth magnitude still comes from bone length (§3.2), never from z.
    """
    Z = F[:, :, 2].copy()
    out = np.full_like(Z, np.nan)
    n = len(Z)
    for i in range(n):
        lo, hi = max(0, i - win // 2), min(n, i + win // 2 + 1)
        seg = Z[lo:hi]
        with np.errstate(invalid="ignore"):
            m = np.nanmean(np.where(np.isnan(seg), np.nan, seg), axis=0)
        out[i] = m
    return out


def solve_depth(tgt, rig, frame, tree, zref=None, prev_sign=None, want_front=None):
    """Recover z by bone length (§3.2), walking the tree outward from each anchored shoulder.

    The data's z is noise -- on `hello` it spans 7.7 units against a 2-unit-wide body -- so it
    is used ONLY to pick between the two roots of the quadratic, never as a position. Where
    the 2D span already exceeds the bone's rest length the quadratic has no real root: the
    limb is foreshortened past what the rig can reach, so we clamp to a fully in-plane bone
    rather than invent depth.

    CHOOSING THE ROOT: the SIDE is reliable even though the MAGNITUDE is not. Measured across
    all 11 signs, the data puts the wrist in front of the shoulder line in 100.0% of frames --
    which is what signing is. So `want_front` carries that per-landmark boolean, read off the
    data in its own space where it is trustworthy, and the root that agrees with it wins.

    That replaces a strictly worse test. The previous rule compared src[b] - src[a]: a
    DIFFERENCE of two noisy values, which is noisier than either, and it produced hands behind
    the body on 46% of `thankyou`'s frames and 33% of `please`'s while the data said in-front
    on every single one. Where both roots agree with the prior, or neither does, it is genuinely
    ambiguous and the old relative-z rule with its hysteresis still decides.
    """
    P = {L_SH: rig.wp("upperarm_l").copy(), R_SH: rig.wp("upperarm_r").copy()}
    ref_z = float((rig.wp("upperarm_l")[2] + rig.wp("upperarm_r")[2]) / 2.0)
    sign_used = {}
    clamped = 0
    for b, a, L in tree:
        pa = P.get(a)
        if pa is None or np.any(np.isnan(tgt[b])):
            P[b] = None
            continue
        if L == 0.0:                                   # coincident landmarks
            P[b] = pa.copy()
            continue
        dx, dy = tgt[b][0] - pa[0], tgt[b][1] - pa[1]
        planar = dx * dx + dy * dy
        if planar > L * L:
            s = L / (np.sqrt(planar) + 1e-12)
            P[b] = np.array([pa[0] + dx * s, pa[1] + dy * s, pa[2]])
            clamped += 1
        else:
            dz = np.sqrt(max(L * L - planar, 0.0))
            # Which root of the quadratic: in front of the image plane, or behind it.
            # Taken from the SMOOTHED z, with hysteresis toward whatever this bone chose on
            # the previous frame. The hysteresis band is what stops a bone that is nearly
            # edge-on -- where the smoothed signal sits near zero and carries almost no
            # information -- from dithering between the two roots every frame.
            wf = want_front.get(b) if want_front else None
            plus_front = (pa[2] + dz) > ref_z
            minus_front = (pa[2] - dz) > ref_z
            if wf is not None and plus_front != minus_front:
                # the prior actually separates the two roots, so let it decide
                sgn = 1.0 if (plus_front == wf) else -1.0
            else:
                src = zref if zref is not None else frame[:, 2]
                rel = (float(src[b] - src[a])
                       if not (np.isnan(src[a]) or np.isnan(src[b])) else 0.0)
                prev = prev_sign.get(b) if prev_sign else None
                if prev is not None and abs(rel) < 0.06:
                    sgn = prev                               # too weak to overturn the past
                else:
                    sgn = 1.0 if rel >= 0 else -1.0
            sign_used[b] = sgn
            P[b] = np.array([pa[0] + dx, pa[1] + dy, pa[2] + sgn * dz])
    return P, clamped, sign_used


def hand_scale(F, side, rig):
    """How much to shrink this signer's hand to fit the avatar's, in shoulder-width units.

    Measured: the data's wrist-to-middle-fingertip runs 1.28-1.61x the rig's, relative to
    shoulder width. That is not a rigging fault -- MediaPipe Pose and MediaPipe Hands are
    SEPARATE models whose outputs are fused into one 75-point frame, and their scales do not
    agree. Retargeting the hand at body scale therefore drives every fingertip past where the
    rig can reach, the depth solver clamps the bone flat into the image plane, and the
    handshape is destroyed -- which is what 32-42% clamping was, and why the signs read as
    mush while the WRIST still landed within 0.4% of target.

    🔴 MEASURE THE PALM, NEVER THE FINGERTIP. The first version of this used wrist-to-middle-
    FINGERTIP, and that distance collapses when the hand closes -- so on a fist the estimate
    came back tiny, the ratio inverted, and the hand was scaled UP instead of down. `yes` is a
    fist and `drink` is a closed C: both ended up with ~100% of every finger bone clamped
    flat, i.e. no handshape at all. Estimating hand size from a quantity that varies with
    handshape is precisely backwards for a sign language, where handshape is the thing being
    communicated.

    The rule that follows from this is not "use the palm", it is USE ONLY RIGID SEGMENTS --
    and there are 20 of them, not one. Every phalanx (MCP->PIP->DIP->tip) is bone, so its
    length is as handshape-invariant as the palm is; only distances that SPAN a joint, like
    wrist-to-fingertip, collapse. So all 20 segments are measured, each gives its own estimate
    of the shrink ratio, and the MEDIAN of those is taken.

    Measured against the previous palm-only version, over all 11 signs (mean handshape error,
    which is what this is for -- clamping is only the mechanism):

        palm only (1 segment)      18.8%      worst case `thankyou` 25.1%
        all 20 segments, median    16.9%      worst case `thankyou`  9.2%

    The win is concentrated exactly where a single measurement was thinnest: `thankyou` and
    `water` hold the hand foreshortened through most of the clip, and `water` is only 22
    frames long, so one distance's 90th percentile never saw the hand face-on and read it as
    smaller than it is. Twenty segments and a median see it. `drink` is the one regression
    (36.4% -> 43.6%) and it is also the sign whose forearm measures 1.24x the rig's, so its
    hand is not the binding constraint.

    The 90th percentile within each segment estimates that segment's true 3D length, because
    projection can only ever SHORTEN a bone -- so the longest projection observed is the
    closest look at the real thing. The mean would systematically under-read it. The median
    ACROSS segments then absorbs the few segments whose p90 is still noise.
    """
    h0 = HAND0[side]
    sh = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    segs = [(h0, h0 + o, f"hand_{side}", f"{f}_01_{side}")
            for f, o in FINGER_OFF.items()]
    for f, o in FINGER_OFF.items():
        for k in (1, 2, 3):
            nxt = f"{f}_0{k+1}_{side}" if k < 3 else f"{f}_end_{side}"
            segs.append((h0 + o + k - 1, h0 + o + k, f"{f}_0{k}_{side}", nxt))
    ratios = []
    for a, b, ra, rb in segs:
        d = np.linalg.norm(F[:, b, :2] - F[:, a, :2], axis=1)
        d = d[~np.isnan(d)]
        if len(d) < 3:
            continue
        est = float(np.percentile(d, 90))
        if est < 1e-6:
            continue
        ratios.append((rig.bone_len(ra, rb) / sh) / est)
    if not ratios:
        return 1.0
    return float(np.median(ratios))


def _unused_palm_scale(F, side, rig):
    """The single-segment estimator this replaced. Kept only as the reference it was measured
    against; nothing calls it."""
    h0 = HAND0[side]
    mcp = h0 + FINGER_OFF["middle"]
    ok = ~np.isnan(F[:, mcp, 0]) & ~np.isnan(F[:, h0, 0])
    if ok.sum() < 3:
        return 1.0
    est = float(np.percentile(
        np.linalg.norm(F[ok][:, mcp, :2] - F[ok][:, h0, :2], axis=1), 90))
    if est < 1e-6:
        return 1.0
    sh = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    rig_norm = float(np.linalg.norm(
        rig.wp(f"middle_01_{side}") - rig.wp(f"hand_{side}"))) / sh
    return rig_norm / est


def head_frames(F, rig):
    """Head orientation per frame, as a world rotation for the `head` bone. None where unknown.

    WHY THIS EXISTS: non-manual markers are one of the five parameters that distinguish one
    ASL sign from another, and we were animating none of them -- 36 of the rig's 88 joints,
    with `neck`, `head` and `jaw` all frozen at rest. A frozen head does not read as neutral,
    it reads as absent. The face landmarks were 100% present in every clip the whole time.

    MEASURED IN THE IMAGE PLANE, NOT FROM z. The obvious construction is a frame from nose and
    both ears, but that leans on the depth channel §3.2 calls noise, and it does not survive
    being checked: yaw taken from the ears' z disagrees with a pure image-plane estimate of the
    same yaw (|r| 0.8 on the signs that genuinely turn, and uncorrelated on the ones that do
    not, where it is reading pure noise). So all three angles come from x/y only:

        yaw    how far the nose sits off the ear midpoint, along the ear line
        roll   the angle of the ear line itself
        pitch  the nose's offset from the ear line, across it

    HONEST LIMIT, so nobody reads more into this than it does: this gives head POSE. It does
    not give eyebrow raise, which is the grammatically loaded non-manual -- brow-up marks
    yes/no questions, brow-down marks wh-questions -- because MediaPipe Pose has no eyebrow
    landmarks at all. Its 11 face points are nose, six eye points, two ears, two mouth corners.
    Recovering brows needs a face-mesh capture we do not have, and no amount of work on these
    landmarks will produce it. The rig HAS eyebrow bones; we have nothing to drive them with.
    """
    EAR_L, EAR_R = 7, 8
    n = len(F)
    raw = []
    for i in range(n):
        el, er, no = F[i, EAR_L, :2], F[i, EAR_R, :2], F[i, NOSE, :2]
        if np.any(np.isnan(el)) or np.any(np.isnan(er)) or np.any(np.isnan(no)):
            raw.append(None)
            continue
        across = el - er                         # toward the signer's left
        span = float(np.linalg.norm(across))
        if span < 1e-6:
            raw.append(None)
            continue
        u = across / span
        v = np.array([u[1], -u[0]])              # perpendicular, pointing UP (data y is down)
        d = (no - (el + er) / 2.0) / (span / 2.0)
        raw.append((float(np.dot(d, u)), float(np.dot(d, v)),
                    float(np.arctan2(-across[1], across[0]))))

    # PITCH IS CALIBRATED TO THIS CLIP'S OWN NEUTRAL, the other two are not. The nose does not
    # sit ON the ear line at rest -- it sits below it, by an amount that is this signer's face,
    # not a head movement. Subtracting the clip median measures the NOD rather than the
    # anatomy. Yaw and roll need no such treatment: both are genuinely zero when the head is
    # level and facing the camera.
    pitch0 = float(np.median([r[1] for r in raw if r is not None])) if any(
        r is not None for r in raw) else 0.0

    out = []
    for r in raw:
        if r is None:
            out.append(None)
            continue
        yaw = float(np.clip(r[0], -1.0, 1.0)) * (np.pi / 3.0)      # +-1 -> +-60 deg
        pitch = float(np.clip(r[1] - pitch0, -1.0, 1.0)) * (np.pi / 6.0)
        roll = r[2]
        cy, sy = np.cos(yaw), np.sin(yaw)
        cp, sp = np.cos(-pitch), np.sin(-pitch)   # nose UP is a NEGATIVE rotation about +x
        cr, sr = np.cos(roll), np.sin(roll)
        Ry = np.array([[cy, 0, sy], [0, 1.0, 0], [-sy, 0, cy]])      # yaw, about up (+y)
        Rp = np.array([[1.0, 0, 0], [0, cp, -sp], [0, sp, cp]])      # pitch, about +x
        Rr = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1.0]])      # roll, about forward
        out.append(Rr @ Ry @ Rp)
    return out


def slerp(q0, q1, t):
    """Shortest-arc interpolation between two xyzw quaternions."""
    d = float(np.dot(q0, q1))
    if d < 0.0:                      # same rotation, opposite hemisphere
        q1, d = -q1, -d
    if d > 0.9995:                   # nearly identical: lerp is exact and numerically safer
        q = q0 + t * (q1 - q0)
        return q / (np.linalg.norm(q) + 1e-12)
    th = np.arccos(np.clip(d, -1.0, 1.0))
    return (np.sin((1 - t) * th) * q0 + np.sin(t * th) * q1) / np.sin(th)


def smooth_quats(out_q, fps, min_cutoff=None, beta=None, bone_cut=None):
    """One-Euro again, this time on the bone rotations rather than the landmarks.

    §6.12 #9's filter is already on the input and it cannot reach this, because most of what
    is left is not IN the landmarks -- it is MANUFACTURED by the solve. Recovering a rotation
    from two nearby points is ill-conditioned exactly when a finger is curled, so noise well
    inside the input filter's tolerance still comes out as a visible angle.

    THE LARGE JUMPS ARE NOT THIS FILTER'S JOB and trying to make them so is a mistake worth
    recording. One-Euro is BUILT to pass fast motion: its beta term widens the cutoff as speed
    rises, so a discontinuity -- the exact thing you want removed -- is what it protects. Swept
    over the 11 signs, no setting bought a smaller maximum without wrecking the handshapes:

        setting            max step   over 30 deg   handshape
        no filter           179.3d        2.5%        12.9%
        mc 5.0 b 0.40       177.2d        2.4%        13.1%
        mc 3.0 b 0.25       176.0d        2.3%        13.1%
        mc 0.8 b 0.00       117.8d        0.9%        23.1%

    The snaps had to be removed where they were made instead: the passive arm is no longer
    driven, and an ill-conditioned palm frame now declines to answer.

    BETA IS NEARLY ZERO HERE AND THAT IS THE POINT. One-Euro's speed term assumes fast means
    INTENDED, and widens the cutoff to protect it. On this signal fast mostly means NOISE -- a
    distal phalanx thrown 100 degrees by a landmark that moved two pixels -- so the speed term
    was opening the filter exactly where it was needed and the default beta made the whole
    thing inert. Re-swept with it small, per bone (see bone_cutoffs):

        mc 3.0 b 0.25 floor 1.00    mean 4.7d   p95 19.0d   1.4%/30d   shape 13.1%
        mc 3.0 b 0.02 floor 0.25    mean 3.8d   p95 14.8d   1.4%/30d   shape 14.5%  <- shipped
        mc 3.0 b 0.00 floor 0.25    mean 2.4d   p95  6.8d   1.0%/30d   shape 21.6%

    The last row is where quieting the fingers starts destroying the handshape they are there
    to make, so the middle row is the knee.

    slerp rather than lerp, hemisphere-aligned first: q and -q are the same rotation and
    averaging them naively lands halfway to nowhere.
    """
    min_cutoff = Q_MIN_CUTOFF if min_cutoff is None else min_cutoff
    beta = Q_BETA if beta is None else beta
    if not out_q or min_cutoff <= 0:
        return out_q
    out = [dict(f) for f in out_q]
    for nm in sorted({k for f in out for k in f}):
        mc = (bone_cut or {}).get(nm, min_cutoff)
        prev, prev_speed = None, 0.0
        for f in out:
            if nm not in f:
                prev = None                 # a gap resets the filter, it never bridges one
                continue
            q = np.array(f[nm], dtype=float)
            if prev is None:
                prev, prev_speed = q, 0.0
                continue
            if float(np.dot(q, prev)) < 0.0:
                q = -q
            speed = np.degrees(2 * np.arccos(
                min(1.0, abs(float(np.dot(q, prev)))))) * fps
            a_d = 1.0 / (1.0 + fps / (2 * np.pi * 1.0))
            prev_speed = a_d * speed + (1 - a_d) * prev_speed
            cutoff = mc + beta * prev_speed
            alpha = 1.0 / (1.0 + fps / (2 * np.pi * cutoff))
            sm = slerp(prev, q, alpha)
            prev = sm / (np.linalg.norm(sm) + 1e-12)
            f[nm] = [round(float(x), 4) for x in prev]
    return out


def clip_noise(F):
    """How jittery is THIS clip, as the 95th-percentile per-frame wrist step in shoulder widths.

    The clips are not equally good and treating them as if they were is why a filter tuned on
    the clean ones leaves the rough ones rough. Measured, wrist step p95:

        hello    0.084      the hand tracked in 96% of frames
        bath     0.154      tracked in 11%
        animal   0.276      tracked in 23%, and the z channel steps by up to 1.17

    `animal`'s landmarks move eleven centimetres between consecutive frames. No fixed cutoff
    is right for both that and `hello`; the filter has to know which one it is looking at.
    """
    vals = []
    for wr in (L_WR, R_WR):
        d = np.linalg.norm(np.diff(F[:, wr, :2], axis=0), axis=1)
        d = d[~np.isnan(d)]
        if len(d) >= 3:
            vals.append(float(np.percentile(d, 95)))
    return max(vals) if vals else NOISE_REF


def bone_cutoffs(rig, chains, noise=None):
    """Per-bone filter cutoff, scaled by bone length. Short bones get smoothed harder.

    One global cutoff is the wrong shape for a hand. The angle a bone has to turn to absorb a
    given positional error goes as error over LENGTH, so the same landmark noise that moves a
    28 cm upper arm by a degree throws a 1.5 cm distal phalanx through twenty. Measured, the
    noisiest bones in the set are exactly the shortest and most occluded ones -- on `yes`,
    a fist, the five worst are pinky_03 (mean 23.5 deg/frame), ring_02, ring_03, pinky_02,
    pinky_01, while the arm bones sit near two.

    So the cutoff scales with rest length, floored so the longest bones are untouched and the
    shortest get four times the smoothing. This buys quiet fingers without softening the arm
    movement that carries the sign.
    """
    lens = {}
    for bone, child, _a, _b in chains:
        if bone in rig.by and child in rig.by:
            lens[bone] = rig.bone_len(bone, child)
    if not lens:
        return {}
    # Normalised by the LONGEST bone, not the median. Two thirds of these chains are finger
    # segments, so the median IS a finger segment: every ratio came out at or above 1.0, the
    # clip flattened them all to 1.0, and a whole parameter sweep moved nothing at all.
    ref = max(lens.values())
    # and scaled again by how noisy this particular clip is, so a rough capture is smoothed
    # harder than a clean one instead of both getting the setting that suited the clean one
    ns = 1.0 if noise is None else float(np.clip(NOISE_REF / max(noise, 1e-6), 0.3, 1.0))
    return {b: Q_MIN_CUTOFF * ns * float(np.clip(L / ref, 0.25, 1.0))
            for b, L in lens.items()}


def bridge_gaps(out_q, held):
    """Interpolate a bone ACROSS a gap instead of holding it and then snapping out.

    Holding the last pose through a gap fixes the flying-open-and-shut, but it leaves a step
    at the far edge: the bone sits still for twenty frames and then jumps to wherever the hand
    reappeared. Measured after the hold alone, `animal` still peaked at 149 degrees in one
    frame and `book` at 133.

    The corpus note says these nulls are frames "you must hold or interpolate through", and
    interpolate is the better half of that where there is something to interpolate TO. A run of
    held frames bracketed by two solved ones is slerped between them, so the hand travels
    across the gap instead of waiting and then leaping. A run with no solved frame after it --
    the hand simply never comes back -- has no target, so it keeps holding.
    """
    n = len(out_q)
    for nm in sorted({k for f in out_q for k in f}):
        solved = [i for i in range(n) if nm in out_q[i] and nm not in held[i]]
        if not solved:
            continue
        # The LEADING run is the same problem mirrored: before the hand is first seen there is
        # no previous pose to hold, so the bone sits at rest and then leaps to wherever the
        # hand turned up -- `animal` peaked at 149 degrees on exactly that frame. Back-fill it
        # with the first pose actually solved. (A hand absent for the WHOLE clip still holds
        # rest, per §6: `solved` is empty there and nothing is written.)
        for i in range(solved[0]):
            out_q[i][nm] = list(out_q[solved[0]][nm])
        for a, b in zip(solved, solved[1:]):
            if b - a < 2:
                continue
            q0 = np.array(out_q[a][nm], dtype=float)
            q1 = np.array(out_q[b][nm], dtype=float)
            for i in range(a + 1, b):
                q = slerp(q0, q1, (i - a) / (b - a))
                out_q[i][nm] = [round(float(x), 4) for x in q]
    return out_q


def fk_world(rig, frame_q):
    """World translation per node index from local quaternions; absent bones hold rest."""
    W, T = {}, {}
    for i in rig._order():
        q = frame_q.get(rig.name[i])
        lR = quat_to_mat(np.array(q, dtype=float)) if q is not None else rig.rest_R[i]
        p = rig.parent.get(i)
        if p is None:
            T[i], W[i] = rig.rest_t[i].copy(), lR.copy()
        else:
            T[i], W[i] = T[p] + W[p] @ rig.rest_t[i], W[p] @ lR
    return T


def scale_rot(R, t):
    """The rotation R, scaled to a fraction t of its angle. t=0 is identity, t=1 is R."""
    q = mat_to_quat(R)
    w = float(np.clip(q[3], -1.0, 1.0))
    ang = 2.0 * np.arccos(abs(w))
    if ang < 1e-9:
        return np.eye(3)
    axis = q[:3] / (np.linalg.norm(q[:3]) + 1e-12)
    if w < 0:
        axis = -axis
    a = ang * t / 2.0
    return quat_to_mat(np.array([*(axis * np.sin(a)), np.cos(a)]))


def body_map(F, rig, origin, scale):
    """Height in the signer's body -> height in the rig's, as an affine map (shy, a, b).

    Everything else here is normalised by shoulder width, which is right horizontally and
    WRONG vertically, because the rig is not built to these signers' proportions. Measured, in
    shoulder widths:

                 shoulder->hip     shoulder->eye/ear     upper+forearm
        rig          1.200              0.763                1.592
        data         0.974              ~0.47                ~1.40
        ratio        1.23               1.62                 1.14

    The rig is consistently taller-bodied per unit shoulder width, so a hand held at the
    SIGNER's forehead arrives at the RIG's chin. Measured on `dad`, an open 5-hand whose thumb
    touches the forehead: the thumb reached 0.334 above the shoulder line where the rig's jaw
    is at 0.610 and its eyes at 0.763. Fourteen centimetres low, sitting at the neck. That is a
    LOCATION error, and location is one of the five parameters that distinguish one ASL sign
    from another.

    Two anchors present in both bodies -- the hip line and the ear/eye line -- give two
    equations for two unknowns, so both land exactly and everything between is interpolated.
    Fitted per clip, not once, because these are different signers: the slope runs 1.14 to 1.48
    across the eleven that were checked by hand.
    """
    # A HIGH PERCENTILE, NOT THE MEAN, for the same reason hand_scale uses one: projection can
    # only ever SHORTEN a distance, so the largest value observed is the closest look at the
    # real one. It matters here because the anchors are on the HEAD and the head moves. Fitted
    # on means across all 250 words the slope ran 1.08 to 1.76, and the extremes were exactly
    # the signs where the head tilts -- `nap`, `down`, `lion`, `elephant` -- where a tilt
    # shortens the apparent shoulder-to-ear distance and the fit reads it as a short signer.
    shy = np.nanmean(F[:, [L_SH, R_SH], 1], axis=1)
    with np.errstate(invalid="ignore"):
        ear = shy - (F[:, 7, 1] + F[:, 8, 1]) / 2.0
        hip = shy - (F[:, 23, 1] + F[:, 24, 1]) / 2.0
    ear_h = float(np.nanpercentile(ear, 90)) if np.isfinite(ear).any() else np.nan
    hip_h = float(np.nanpercentile(hip, 10)) if np.isfinite(hip).any() else np.nan
    if not (np.isfinite(ear_h) and np.isfinite(hip_h)) or abs(ear_h - hip_h) < 1e-6:
        return shy, 1.0, 0.0
    rig_eye = float((rig.wp("eye_r")[1] - origin[1]) / scale)
    rig_hip = float((rig.wp("hip")[1] - origin[1]) / scale)
    a = (rig_eye - rig_hip) / (ear_h - hip_h)
    # Clamped, because past these bounds the fit is reading a bad anchor rather than an
    # unusual signer. The ratio is known directly from the two bodies -- torso 1.23, head 1.62,
    # arm 1.14 -- so the truth sits near 1.1-1.4, and across all 250 words the fit lands
    # median 1.25 with p5-p95 of 1.15-1.39. The handful outside (`down` 1.68, `white` 1.67,
    # `lion` 1.65) are signs where the head leaves neutral for most of the clip, so even a 90th
    # percentile never catches it upright. Below 1.0 would mean the rig is the SHORTER-bodied
    # one, which contradicts the direct measurement outright.
    a = float(np.clip(a, 1.0, 1.5))
    return shy, a, rig_eye - a * ear_h


def two_bone_ik(S, W, L1, L2, pole):
    """Place the elbow so the arm reaches W exactly, with both bones at their rig lengths.

    THIS IS THE THIRD ATTEMPT AT THE HEIGHT PROBLEM AND THE FIRST THAT WORKS. The two that
    failed are worth recording, because both failed the same way:

      1. Scale the targets vertically by the body map. That puts the elbow target further from
         the shoulder than the rig's upper arm is long, so the depth solver clamps -- and a
         clamped bone is flattened into the image plane, discarding the depth solve for itself
         and everything below it. Handshape error 12.9% -> 17.6%, clamping 15.9% -> 20.3%.
      2. Rotate the solved arm about the shoulder to the target elevation. Preserves lengths,
         but a rotation has only two degrees of freedom to spend and cannot put the wrist at an
         arbitrary point, so it overshoots azimuth to buy elevation. Wrist error 0.4% -> 43.6%.

    The thing both lack is the elbow's freedom. An arm reaching a point is a two-bone chain
    with one degree of freedom left over -- the elbow swings on a circle about the
    shoulder-wrist axis -- and that is exactly the slack needed to absorb a body of different
    proportions. Solving for it puts the wrist EXACTLY on target with both bones at their
    rig lengths, so there is nothing to clamp and nothing to stretch.

    `pole` picks which point on the circle: the elbow keeps pointing the way the signer's did.
    """
    d = W - S
    dist = float(np.linalg.norm(d))
    if dist < 1e-9:
        return None, W
    lo, hi = abs(L1 - L2) + 1e-6, L1 + L2 - 1e-6
    if dist > hi or dist < lo:                 # out of reach: pull the target to the boundary
        dist = float(np.clip(dist, lo, hi))
        W = S + d / float(np.linalg.norm(d)) * dist
        d = W - S
    u = d / dist
    a = (L1 * L1 - L2 * L2 + dist * dist) / (2.0 * dist)
    h = np.sqrt(max(L1 * L1 - a * a, 0.0))
    n = pole - u * float(np.dot(pole, u))
    if np.linalg.norm(n) < 1e-9:               # pole degenerate: any perpendicular will do
        n = np.cross(u, np.array([0.0, 1.0, 0.0]))
        if np.linalg.norm(n) < 1e-9:
            n = np.cross(u, np.array([1.0, 0.0, 0.0]))
    n = n / (np.linalg.norm(n) + 1e-12)
    return S + u * a + n * h, W


def arm_scale(F, side, rig):
    """How much to shrink this signer's arm to fit the avatar's, in shoulder-width units.

    The same measurement as hand_scale, one level up the chain, and for the same reason: the
    upper arm and forearm are rigid, so their lengths are posture-invariant and a high
    percentile of the observed 2D length is the best available look at the true 3D one.

    Measured p90 against the rig, right arm, over the 11 signs:

        forearm   0.66x (`no`) .. 1.24x (`drink`)      upperarm  0.74x .. 1.01x

    Both segments get one shared scale -- the median of the two ratios -- rather than one
    each, because scaling them independently would change the ELBOW's position relative to
    the shoulder-wrist line, and that is a posture change, not a proportion correction.
    """
    sh, el, wr = ((L_SH, L_EL, L_WR) if side == "l" else (R_SH, R_EL, R_WR))
    shw = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    ratios = []
    for a, b, ra, rb in ((sh, el, f"upperarm_{side}", f"lowerarm_{side}"),
                         (el, wr, f"lowerarm_{side}", f"hand_{side}")):
        d = np.linalg.norm(F[:, b, :2] - F[:, a, :2], axis=1)
        d = d[~np.isnan(d)]
        if len(d) < 3:
            continue
        est = float(np.percentile(d, 90))
        if est < 1e-6:
            continue
        ratios.append((rig.bone_len(ra, rb) / shw) / est)
    if not ratios:
        return 1.0
    # Only ever shrink toward the rig; never stretch the signer's arm to fill a longer one,
    # which would push the hand outside the signing space to no benefit.
    return float(min(np.median(ratios), 1.0))


def frame_from(origin, fwd, across):
    """Orthonormal basis from a long axis and an across axis. Returns columns [x, y, z]."""
    x = fwd / (np.linalg.norm(fwd) + 1e-12)
    a = across - x * float(np.dot(across, x))          # Gram-Schmidt
    na = np.linalg.norm(a)
    # ILL-CONDITIONED MEANS NO ANSWER, NOT A BAD ONE. When `across` lies nearly along `fwd`,
    # what survives Gram-Schmidt is almost entirely noise, and its DIRECTION can reverse
    # between consecutive frames -- which flips the whole frame by 180 degrees. That is the
    # single worst artefact in the set: `drink`, hand_r, frame 33, a 179.3 degree step in one
    # frame at 30 fps. The palm's across-vector is index MCP to pinky MCP, which collapses in
    # projection exactly when the hand turns edge-on, so this is common rather than exotic.
    # Returning None drops the caller back to the minimal-rotation path, which pins two axes
    # from the parent and cannot flip.
    if na < 0.15 * (np.linalg.norm(across) + 1e-12) or na < 1e-9:
        return None
    y = a / na
    return np.column_stack([x, y, np.cross(x, y)])


def retarget_word(rig, word, chains):
    d = json.loads((WORDS / f"{word}.json").read_text(encoding="utf-8"))
    F = np.array(d["frames"], dtype=float)

    # 🔴 Z POINTS THE OTHER WAY IN THE DATA THAN IT DOES IN THE RIG. Flipped ONCE, here, at
    # the boundary, so that everything downstream -- to_rig, smooth_z, solve_depth's root
    # choice -- is speaking the rig's convention. Flipping it in two places instead would let
    # the position and the depth-sign decision drift out of step.
    #
    # Established from anatomy, not from doctrine, because a convention you looked up is a
    # convention you can misremember. Two landmarks have a known side:
    #   - the NOSE is in front of the shoulder line. Measured: -0.90 to -1.42 in every clip.
    #   - the WRIST, during signing, is in front of the torso. Measured: -1.1 to -2.8.
    # Both negative, so in this data NEGATIVE z means TOWARD THE CAMERA, i.e. in front.
    # The rig faces +z: its toes sit +0.09 forward of the ankles and its eyes +0.08 forward
    # of the head joint. Opposite conventions.
    #
    # Unflipped, every hand the signer held in FRONT of their body was placed BEHIND the
    # avatar's -- which is exactly what "the hand is from the back" was. Neither wrist error
    # nor handshape error could see it: both are measured in the image plane, and this error
    # is purely along the axis they discard. See the `front` metric below, which exists
    # because of this.
    F[:, :, 2] = -F[:, :, 2] if _FLIP_Z else F[:, :, 2]

    F = one_euro(F, fps=float(d.get("fps", 30)))     # §6.12 #9, ours to apply
    n = len(F)

    # data is shoulder-centred with shoulder width == 1.0, y DOWN (§ note in every file).
    rig_sh_l, rig_sh_r = rig.wp("upperarm_l"), rig.wp("upperarm_r")
    scale = float(np.linalg.norm(rig_sh_l - rig_sh_r))
    origin = (rig_sh_l + rig_sh_r) / 2.0
    # x already agrees: the signer's right shoulder is at smaller x in the data, and the rig's
    # right arm is at negative x. No mirroring. y is flipped because the data is image space.
    # z is NOT flipped here -- it was already flipped above, on the whole array.
    def to_rig(p):
        return origin + np.array([p[0], -p[1], p[2]]) * scale

    # DO NOT DRIVE THE PASSIVE ARM ON A ONE-HANDED SIGN. The corpus records one hand per
    # participant, so on these clips the passive HAND is 100% absent and §6 already has that
    # arm holding rest. Its pose landmarks still exist, though, so the passive upper arm and
    # forearm were being driven from them -- and measured, they jump over 30 degrees in a
    # single frame on 4.8% of frames against 1.5% for the signing arm, three times worse on
    # the arm that carries no meaning at all. A nearly straight limb is ill-conditioned: with
    # shoulder, elbow and wrist almost collinear, small landmark noise spins the arm about its
    # own axis. There is nothing to preserve there, so it holds rest with the hand it carries.
    two_handed = bool(d.get("segments", [{}])[0]
                      .get("synthesis", {}).get("twoHanded", True))
    dom = str(d.get("segments", [{}])[0]
              .get("synthesis", {}).get("dominantHand", "R")).lower()
    passive = "l" if dom == "r" else "r"
    if not two_handed:
        chains = [c for c in chains if not c[0].endswith(f"_{passive}")]

    HS = {s: hand_scale(F, s, rig) for s in ("l", "r")}
    AS = {s: arm_scale(F, s, rig) for s in ("l", "r")}
    SHY, VA, VB = body_map(F, rig, origin, scale)   # signer height -> rig height
    HR = head_frames(F, rig)          # non-manual: head pose, one of the five ASL parameters
    ZS = smooth_z(F)
    tree = build_tree(rig)

    # WHICH SIDE OF THE SHOULDER LINE IS THIS LANDMARK ON? Read in the data's own space, where
    # the SIGN of z is trustworthy even though its magnitude is not: across all 11 signs the
    # data puts the wrist in front on 100.0% of frames. solve_depth uses this to pick the root
    # of the depth quadratic; see its docstring for why it beats the relative-z test it
    # replaced. Only the two arm landmarks and the hand blocks need it.
    # THE ELBOW ONLY, which is not where I expected it to help. The reliable measurement was
    # about the WRIST -- in front on 100.0% of frames -- so the obvious move was to apply the
    # prior there, and to every landmark while we were at it. Measured, that is worse than not
    # applying it at all:
    #
    #     prior applied to      mean `front`
    #     nothing                  89.9%
    #     the wrist                85.0%     <- the landmark the 100% claim was about
    #     the elbow only           92.4%     <- shipped, better or equal on every word
    #
    # The wrist is the landmark whose side we know, but it is also the landmark whose depth is
    # already pinned by its parent: by the time the chain reaches it, the elbow's root has
    # fixed where it can be, so forcing it produces a root that contradicts the arm above it.
    # The elbow is the joint where the choice is genuinely free, so that is where a prior buys
    # anything. Nothing else moved: handshape and clamping are identical in all variants.
    sh_z = np.nanmean(F[:, [L_SH, R_SH], 2], axis=1)
    want_front = [{} for _ in range(n)]
    for fi in range(n):
        if np.isnan(sh_z[fi]):
            continue
        for lm in (L_EL, R_EL):
            # ONLY WHEN IT IS SURE. The prior is a hard override with no hysteresis behind it,
            # so an elbow hovering near the shoulder plane flips side every frame and swings
            # the forearm through 145 degrees -- which is exactly what `animal` and `bath` were
            # doing, at regular intervals, in frames where the hand was not even present. Below
            # the margin the answer is not "behind", it is "unknown", and solve_depth's
            # relative-z rule with its own hysteresis is better placed to keep the peace.
            m = F[fi, lm, 2] - sh_z[fi]
            if not np.isnan(m) and abs(m) > FRONT_MARGIN:
                want_front[fi][lm] = bool(m > 0)

    prev_sign, last_q, held = {}, {}, []
    out_q, err, shp, front, keep, clamps, total = [], [], [], [], [], 0, 0
    by_bone = {c[0]: c for c in chains}
    driven = [c[0] for c in chains] + ["neck", "head"]
    for fi in range(n):
        tgt = {}
        for lm in range(75):
            tgt[lm] = to_rig(F[fi, lm]) if not np.any(np.isnan(F[fi, lm])) else \
                np.array([np.nan] * 3)

        # Bring the arm inside the rig's reach, by scaling the elbow and wrist about the
        # SHOULDER. Exactly the same argument as hand_scale, one level up: the signer's arm is
        # not the rig's arm. Measured p90 forearm length against the rig's, over the 11 signs,
        # the ratio runs 0.66x (`no`) to 1.24x (`drink`) -- and `drink` is the worst sign we
        # have on every axis, with 34.9% of its bones clamped flat.
        #
        # Scaling rather than clamping, because clamping is the destructive option. A clamped
        # bone is flattened into the image plane, which throws away the depth solve for that
        # bone and every bone downstream of it. Scaling preserves the whole arm's posture and
        # only changes how far from the body it reaches -- and since everything here is already
        # normalised to shoulder width, reaching to the RIG's proportions is the correct
        # target anyway. Sign location is phonological, but it is location relative to the
        # signer's own body, which is what this preserves.
        for s in ("l", "r"):
            sh, el, wr = ((L_SH, L_EL, L_WR) if s == "l" else (R_SH, R_EL, R_WR))
            if np.any(np.isnan(tgt[sh])) or abs(AS[s] - 1.0) < 1e-6:
                continue
            a0 = tgt[sh].copy()
            for lm in (el, wr):
                if not np.any(np.isnan(tgt[lm])):
                    tgt[lm] = a0 + (tgt[lm] - a0) * AS[s]
        # Shrink each hand about its own wrist to the rig's hand size, THEN move the whole
        # block onto the pose wrist. Both steps happen in rig space, after conversion.
        #
        # The translation is the load-bearing one and it was missing. The 21 hand landmarks
        # come from MediaPipe Hands; the arm that carries them is solved from MediaPipe Pose;
        # the two models put "the wrist" in measurably different places (19-66% of a palm
        # apart across these 11 signs). Without this the finger targets were expressed
        # relative to the hand model's wrist but reconstructed outward from the pose model's,
        # so a rigid offset of up to two-thirds of a palm was silently baked into every
        # fingertip -- which is what made the handshapes unreadable while wrist placement
        # looked perfect.
        #
        # Rigid, not a re-fit: translating the block moves every finger by the same vector,
        # so it cannot change the handshape, only where the hand is attached.
        for s in ("l", "r"):
            h0, wr = HAND0[s], (L_WR if s == "l" else R_WR)
            if np.any(np.isnan(tgt[h0])):
                continue
            w0 = tgt[h0].copy()
            if abs(HS[s] - 1.0) > 1e-6:
                for k in range(1, 21):
                    if not np.any(np.isnan(tgt[h0 + k])):
                        tgt[h0 + k] = w0 + (tgt[h0 + k] - w0) * HS[s]
            if not np.any(np.isnan(tgt[wr])):
                shift = tgt[wr] - tgt[h0]
                for k in range(21):
                    if not np.any(np.isnan(tgt[h0 + k])):
                        tgt[h0 + k] = tgt[h0 + k] + shift
        P, cl, used = solve_depth(tgt, rig, F[fi], tree, zref=ZS[fi],
                                  prev_sign=prev_sign, want_front=want_front[fi])
        prev_sign.update(used)

        # PUT THE HAND WHERE THE SIGN IS MADE ON THIS BODY. The solve above reproduces the
        # signer's arm ANGLES faithfully, which on a differently proportioned body lands the
        # hand in the wrong place -- see body_map() for the measurement. Only the height is
        # corrected: x is already right (both bodies are normalised on shoulder width) and z
        # comes from the depth solve, which is the one thing the data cannot supply.
        #
        # The elbow is then re-solved by IK so the wrist lands exactly there with both bones
        # at their rig lengths. Nothing is scaled, so nothing can clamp. The hand block is
        # carried along by the same translation the wrist made, which moves the handshape
        # without touching it.
        for s_ in ("l", "r"):
            sh_, el_, wr_ = ((L_SH, L_EL, L_WR) if s_ == "l" else (R_SH, R_EL, R_WR))
            if f"hand_{s_}" not in by_bone or P.get(wr_) is None or P.get(el_) is None:
                continue
            if not np.isfinite(SHY[fi]) or np.any(np.isnan(F[fi, wr_])):
                continue
            S_ = P[sh_]
            # MATCH THE HAND, NOT THE WRIST. Mapping the wrist's height left the fingers short
            # on exactly the signs that reach highest -- `dad` (thumb to the forehead) came out
            # 16.5 cm low even with the wrist landing exactly on target -- because the rig's
            # hand is far smaller relative to its shoulders than the signer's, so everything
            # past the wrist falls behind. The rig CAN touch its own forehead; it just has to
            # raise the arm further to do it with a shorter hand.
            #
            # We cannot put all 21 hand landmarks at their mapped heights at once, since the
            # two hands are different sizes. The translation that minimises the squared error
            # over all of them is the one that matches their MEAN, so the target is the hand's
            # centroid. That is a least-squares answer, not a preference, and it needs no
            # per-sign lexicon -- which matters because no such lexicon exists for one-handed
            # signs.
            h0_ = HAND0[s_]
            ks = [h0_ + k for k in range(21)]
            have = [k for k in ks if P.get(k) is not None and not np.any(np.isnan(F[fi, k]))]
            if have:
                cen_rig = float(np.mean([P[k][1] for k in have]))
                cen_dat = float(np.mean([float(SHY[fi]) - F[fi, k, 1] for k in have]))
                want_y = P[wr_][1] + (origin[1] + (VA * cen_dat + VB) * scale - cen_rig)
            else:
                want_y = origin[1] + (VA * (float(SHY[fi]) - F[fi, wr_, 1]) + VB) * scale
            want = np.array([P[wr_][0], want_y, P[wr_][2]])
            L1 = rig.bone_len(f"upperarm_{s_}", f"lowerarm_{s_}")
            L2 = rig.bone_len(f"lowerarm_{s_}", f"hand_{s_}")
            E, W = two_bone_ik(S_, want, L1, L2, P[el_] - S_)
            if E is None:
                continue
            moved = W - P[wr_]
            P[el_], P[wr_] = E, W
            for k in range(21):
                if P.get(h0_ + k) is not None:
                    P[h0_ + k] = P[h0_ + k] + moved
                if not np.any(np.isnan(tgt[h0_ + k])):
                    tgt[h0_ + k] = tgt[h0_ + k] + moved
            tgt[wr_] = tgt[wr_] + moved
        clamps += cl
        total += len(tree)

        # Hierarchical direction match. Walk the rig's own node order so a parent's solved
        # world rotation is always available before its children are solved in it.
        world_R, world_T, local_q, held_now = {}, {}, {}, set()
        for bi in rig._order():
            nm = rig.name[bi]
            p = rig.parent.get(bi)
            world_T[bi] = (world_T[p] + world_R[p] @ rig.rest_t[bi]) if p is not None \
                else rig.rest_t[bi].copy()
            pR = world_R.get(p) if p is not None else None
            if pR is None:
                pR = rig.world_rest[p][1] if p is not None else np.eye(3)
            c = by_bone.get(nm)
            if c is None:
                # The head is not a direction chain -- a bone pointing the right way still has
                # a free roll, and for the head roll IS the tilt. So it takes a full rotation,
                # built in head_frames() from the face landmarks, applied over its rest frame.
                # The neck carries a third of it: a head that turns while the neck stays rigid
                # reads as a bobblehead, and the extra third has to come off somewhere.
                if HR is not None and HR[fi] is not None and nm in ("neck", "head"):
                    delta = HR[fi] if nm == "head" else scale_rot(HR[fi], NECK_SHARE)
                    world_R[bi] = delta @ rig.world_rest[bi][1]
                    local_q[nm] = mat_to_quat(np.linalg.inv(pR) @ world_R[bi])
                    continue
                world_R[bi] = pR @ rig.rest_R[bi]
                continue
            _bone, child, a, b = c
            if P.get(b) is None or P.get(a) is None:
                # HOLD, and hold the LAST POSE rather than the rest pose wherever there is
                # one. §6's "a missing hand holds rest" is about a hand that is absent for the
                # whole clip -- the passive hand, which was never formed. A GAP is a different
                # thing, and the corpus note is explicit that the nulls inside a clip are
                # frames "you must hold or interpolate through". Snapping to rest and back is
                # neither: it reads as the hand flying open and shut, and it is not rare --
                # 28 of the 250 words have their dominant hand measured in under half their
                # frames, some as low as 11%.
                if nm in last_q:
                    world_R[bi] = pR @ quat_to_mat(np.array(last_q[nm], dtype=float))
                    local_q[nm] = last_q[nm]
                    held_now.add(nm)
                else:
                    world_R[bi] = pR @ rig.rest_R[bi]  # never solved yet: rest is all we have
                continue
            want = P[b] - P[a]
            if np.linalg.norm(want) < 1e-9:
                world_R[bi] = pR @ rig.rest_R[bi]
                continue
            want /= np.linalg.norm(want)
            R_rest_parent = rig.world_rest[p][1] if p is not None else np.eye(3)

            # THE HAND GETS A FULL FRAME, NOT A DIRECTION.
            #
            # align() returns the MINIMAL rotation between two vectors, which pins only 2 of
            # 3 rotational degrees of freedom -- the third, roll about the bone's own axis,
            # is left at whatever the parent happened to give. For every other bone that is
            # fine or nearly so. For the hand it is not: roll about the forearm axis IS palm
            # orientation, and palm orientation is one of the five parameters that distinguish
            # one ASL sign from another, alongside handshape, location, movement and
            # non-manual markers. Leaving it unsolved meant the wrist arrived in exactly the
            # right place with the palm facing an arbitrary direction -- correct by every
            # number I was measuring, and unreadable as language.
            #
            # The across-palm vector (index MCP -> pinky MCP) pins it. Both landmarks were in
            # the data all along; nothing here needs anything new from the rigger.
            hand_side = nm[-1] if nm.startswith("hand_") else None
            solved = False
            if hand_side in ("l", "r"):
                h0 = HAND0[hand_side]
                iM, pM = h0 + FINGER_OFF["index"], h0 + FINGER_OFF["pinky"]
                if P.get(iM) is not None and P.get(pM) is not None:
                    Ft = frame_from(P[a], want, P[pM] - P[iM])
                    Fr = frame_from(rig.wp(nm), rig.wp(child) - rig.wp(nm),
                                    rig.wp(f"pinky_01_{hand_side}")
                                    - rig.wp(f"index_01_{hand_side}"))
                    if Ft is not None and Fr is not None:
                        world_R[bi] = (Ft @ Fr.T) @ rig.world_rest[bi][1]
                        solved = True
            if not solved:
                # where this bone points at REST, carried into the parent's CURRENT frame
                rest_dir = rig.wp(child) - rig.wp(nm)
                rest_dir /= np.linalg.norm(rest_dir) + 1e-12
                cur = pR @ np.linalg.inv(R_rest_parent) @ rest_dir
                world_R[bi] = align(cur, want) @ (pR @ rig.rest_R[bi])
            local_q[nm] = mat_to_quat(np.linalg.inv(pR) @ world_R[bi])
        last_q.update(local_q)
        held.append(held_now)
        out_q.append({k: [round(float(x), 4) for x in v] for k, v in local_q.items()})

        # Metric targets are STORED here, not scored. Scoring happens after the rotation
        # filter, because the filtered animation is what ships and a number describing the
        # unfiltered one describes something nobody will ever see.
        keep.append({lm: tgt[lm].copy() for lm in _METRIC_LM
                     if lm in tgt and not np.any(np.isnan(tgt[lm]))})

    out_q = bridge_gaps(out_q, held)
    out_q = smooth_quats(out_q, fps=float(d.get("fps", 30)),
                         bone_cut=bone_cutoffs(rig, chains, clip_noise(F)))

    # SECOND PASS: score the animation exactly as it ships, filter included.
    for fq, tg in zip(out_q, keep):
        WT = fk_world(rig, fq)
        for side, wr in (("l", L_WR), ("r", R_WR)):
            # only score an arm we actually drive; see the passive-arm note above
            if f"hand_{side}" not in by_bone or wr not in tg:
                continue
            got = WT[rig.by[f"hand_{side}"]]
            err.append(float(np.linalg.norm(got[:2] - tg[wr][:2])) / scale)
            front.append(float(got[2] > rig.wp(f"upperarm_{side}")[2]))
            h0 = HAND0[side]
            if h0 not in tg:
                continue
            hl = float(np.linalg.norm(rig.wp(f"middle_01_{side}") - rig.wp(f"hand_{side}")))
            for fname, off in FINGER_OFF.items():
                tip = h0 + off + 3
                if tip in tg:
                    g = WT[rig.by[f"{fname}_end_{side}"]] - got
                    t_ = tg[tip] - tg[h0]
                    shp.append(float(np.linalg.norm(g[:2] - t_[:2])) / hl)
    return d, out_q, np.array(err), np.array(shp), np.array(front), clamps, total, driven


def selftest(rig, chains):
    """Prove the reported error CAN fail. It could not, and that shipped a broken avatar.

    The previous wrist metric compared solve_depth's output to solve_depth's own input. Those
    agree in x/y by construction, so it printed 0.00% on six of eleven signs no matter what
    the skeleton was doing -- while the fingertips sat a whole hand-length out of place. The
    same self-referential trap had already been caught once, scoring fingertip error against
    SMOOTHED data; catching it twice by eye is not a control.

    So: break the rig on purpose and require the number to notice. Rotating the elbow by 30
    degrees must move the reported wrist error. A metric that survives this unchanged is
    measuring its own input again.
    """
    base, _, err0, shp0, fr0, *_ = retarget_word(rig, "hello", chains)
    rest = rig.rest_R[rig.by["lowerarm_r"]].copy()
    th = np.radians(30.0)
    rig.rest_R[rig.by["lowerarm_r"]] = rest @ np.array(
        [[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1.0]])
    try:
        _, _, err1, shp1, *_ = retarget_word(rig, "hello", chains)
    finally:
        rig.rest_R[rig.by["lowerarm_r"]] = rest
    moved = abs(float(err1.mean()) - float(err0.mean()))
    assert moved > 1e-4, (
        f"[err] the wrist metric did not react to a 30-degree elbow break "
        f"({err0.mean()*100:.4f}% -> {err1.mean()*100:.4f}%). It is measuring its own input, "
        f"not the rig. Score it from world_T (forward kinematics), never from P.")

    # Handshape is measured relative to the wrist ON PURPOSE, so it must NOT react to the
    # elbow -- that is what lets the two numbers separate placement from shape instead of
    # masking each other. Which means the elbow break proves nothing about it, and it needs
    # its own break, at a knuckle.
    # RELATIVE, not exact. Exact equality was right until the rotation filter went in, and is
    # wrong now: a TEMPORAL filter's output at each frame depends on the whole preceding
    # sequence, so perturbing the elbow leaks a rounding-sized amount everywhere. What matters
    # is that the leak is negligible beside the signal, not that it is zero.
    leak = abs(float(shp1.mean()) - float(shp0.mean()))
    signal = abs(float(err1.mean()) - float(err0.mean()))
    assert leak < 0.01 * signal, (
        f"[err] handshape moved {leak*100:.3f} points when only the ELBOW changed, against "
        f"{signal*100:.2f} points of wrist error. It is supposed to be wrist-relative; if the "
        f"elbow leaks in, the two metrics are not independent and neither means what it says.")
    rest_f = rig.rest_R[rig.by["index_02_r"]].copy()
    rig.rest_R[rig.by["index_02_r"]] = rest_f @ np.array(
        [[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1.0]])
    try:
        _, _, err2, shp2, *_ = retarget_word(rig, "hello", chains)
    finally:
        rig.rest_R[rig.by["index_02_r"]] = rest_f
    assert abs(float(shp2.mean()) - float(shp0.mean())) > 1e-4, (
        f"[err] the handshape metric did not react to a 30-degree knuckle break "
        f"({shp0.mean()*100:.4f}% -> {shp2.mean()*100:.4f}%). Score it from world_T, never "
        f"from the targets it was solved against.")
    print(f"[selftest] break the elbow 30deg   -> wrist {err0.mean()*100:5.2f}% -> "
          f"{err1.mean()*100:5.2f}%   handshape unchanged (wrist-relative, as intended)")
    print(f"[selftest] break a knuckle 30deg   -> handshape {shp0.mean()*100:5.1f}% -> "
          f"{shp2.mean()*100:5.1f}%   (both metrics can fail)")

    # And the one neither of them can see. Put the depth axis back the wrong way round and
    # require `front` to collapse. This is the check that would have caught an avatar signing
    # behind its own back on day one -- wrist error and handshape error both scored it clean,
    # because both live in the image plane and the fault was on the axis they discard.
    global _FLIP_Z
    _FLIP_Z = False
    try:
        _, _, err3, shp3, fr3, *_ = retarget_word(rig, "hello", chains)
    finally:
        _FLIP_Z = True
    assert fr0.mean() > 0.9 and fr3.mean() < 0.5, (
        f"[err] the `front` metric cannot tell a correct depth axis from a reversed one "
        f"({fr0.mean()*100:.0f}% correct vs {fr3.mean()*100:.0f}% reversed). It is the only "
        f"check that sees z at all -- wrist and handshape error are both image-plane.")
    print(f"[selftest] reverse the z axis     -> in front {fr0.mean()*100:5.0f}% -> "
          f"{fr3.mean()*100:5.0f}%   (wrist {err3.mean()*100:.1f}% and handshape "
          f"{shp3.mean()*100:.0f}% barely move -- that is why this check exists)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all" in sys.argv:
        words = sorted(p.stem for p in WORDS.glob("*.json"))
    else:
        words = args or ["hello", "mom", "water"]
    rig = Rig(GLB if GLB.exists() else REPO / "3D Char deaf.glb")
    chains = build_chains(rig)
    selftest(rig, chains)
    missing = [c[0] for c in chains if c[0] not in rig.by] + \
              [c[1] for c in chains if c[1] not in rig.by]
    assert not missing, f"rig has no bone named {sorted(set(missing))}"
    print(f"rig    {len(rig.joints)} joints, {len(chains)} driven bones "
          f"(shoulder width {np.linalg.norm(rig.wp('upperarm_l')-rig.wp('upperarm_r')):.3f} m)")
    print(f"\n{'word':<12s} {'frames':>6s} {'hands':>12s} {'wrist err':>11s} "
          f"{'p95':>7s} {'handshape':>10s} {'in front':>9s} {'clamped':>8s}")
    print("-" * 84)
    baked, failed = {}, []
    for w in words:
        if not (WORDS / f"{w}.json").exists():
            print(f"{w:<12s}  no such word file")
            continue
        try:
            d, q, err, shp, fr, cl, tot, driven = retarget_word(rig, w, chains)
        except Exception as exc:                      # one bad clip must not lose the other 249
            print(f"{w:<12s}  FAILED: {type(exc).__name__}: {exc}")
            failed.append(w)
            continue
        F = np.array(d["frames"], dtype=float)
        lh = 1.0 - np.isnan(F[:, 33:54, 0]).mean()
        rh = 1.0 - np.isnan(F[:, 54:75, 0]).mean()
        hands = ("both" if lh > .5 and rh > .5 else "right" if rh > .5 else
                 "left" if lh > .5 else "none")
        e = f"{err.mean()*100:.1f}%" if len(err) else "n/a"
        p95 = f"{np.percentile(err,95)*100:.1f}%" if len(err) else "n/a"
        hs = f"{shp.mean()*100:.1f}%" if len(shp) else "n/a"
        fr_s = f"{fr.mean()*100:.0f}%" if len(fr) else "n/a"
        print(f"{w:<12s} {len(q):6d} {hands:>12s} {e:>11s} {p95:>7s} {hs:>10s} "
              f"{fr_s:>9s} {cl*100.0/max(tot,1):7.1f}%")
        baked[w] = {"fps": d["fps"], "frames": q,
                    "hands": hands, "gloss": d.get("glosses", [w])[0],
                    # §14 test 7 numbers travel WITH the animation, so a viewer showing the
                    # sign always shows how well it actually landed rather than implying it
                    # is exact.
                    "err": round(float(err.mean() * 100), 2) if len(err) else None,
                    "p95": round(float(np.percentile(err, 95) * 100), 2) if len(err) else None,
                    "shape": round(float(shp.mean() * 100), 1) if len(shp) else None,
                    "front": round(float(fr.mean() * 100), 0) if len(fr) else None,
                    "clamp": round(cl * 100.0 / max(tot, 1), 1)}
    out = REPO / "avatar" / "baked_signs.json"
    out.write_text(json.dumps({
        "_note": ("Bone rotations baked by avatar/retarget.py from the 75-landmark motion in "
                  "animation_handoff/words/. Quaternions are LOCAL, xyzw, keyed by the "
                  "rigger's own bone names. A bone absent from a frame holds its rest pose."),
        "_wrist_error_note": ("§14 test 7 wants wrists within 5% of a shoulder-width of "
                              "target. Reported per word by the script that wrote this."),
        "signs": baked}, separators=(",", ":")), encoding="utf-8")
    print(f"\n[ok] {out}  ({out.stat().st_size/1e3:.0f} KB, {len(baked)} signs)")
    print(f"     §14 test 7 passes at <5% of a shoulder-width.")


if __name__ == "__main__":
    main()
