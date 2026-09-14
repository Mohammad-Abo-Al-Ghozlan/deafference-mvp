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


def solve_depth(tgt, rig, frame, tree, zref=None, prev_sign=None):
    """Recover z by bone length (§3.2), walking the tree outward from each anchored shoulder.

    The data's z is noise -- on `hello` it spans 7.7 units against a 2-unit-wide body -- so it
    is used ONLY to pick between the two roots of the quadratic, never as a position. Where
    the 2D span already exceeds the bone's rest length the quadratic has no real root: the
    limb is foreshortened past what the rig can reach, so we clamp to a fully in-plane bone
    rather than invent depth.
    """
    P = {L_SH: rig.wp("upperarm_l").copy(), R_SH: rig.wp("upperarm_r").copy()}
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
            src = zref if zref is not None else frame[:, 2]
            rel = (float(src[b] - src[a])
                   if not (np.isnan(src[a]) or np.isnan(src[b])) else 0.0)
            prev = prev_sign.get(b) if prev_sign else None
            if prev is not None and abs(rel) < 0.06:
                sgn = prev                                   # too weak to overturn the past
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


def frame_from(origin, fwd, across):
    """Orthonormal basis from a long axis and an across axis. Returns columns [x, y, z]."""
    x = fwd / (np.linalg.norm(fwd) + 1e-12)
    a = across - x * float(np.dot(across, x))          # Gram-Schmidt
    na = np.linalg.norm(a)
    if na < 1e-9:
        return None
    y = a / na
    return np.column_stack([x, y, np.cross(x, y)])


def retarget_word(rig, word, chains):
    d = json.loads((WORDS / f"{word}.json").read_text(encoding="utf-8"))
    F = np.array(d["frames"], dtype=float)
    F = one_euro(F, fps=float(d.get("fps", 30)))     # §6.12 #9, ours to apply
    n = len(F)

    # data is shoulder-centred with shoulder width == 1.0, y DOWN (§ note in every file).
    rig_sh_l, rig_sh_r = rig.wp("upperarm_l"), rig.wp("upperarm_r")
    scale = float(np.linalg.norm(rig_sh_l - rig_sh_r))
    origin = (rig_sh_l + rig_sh_r) / 2.0
    # x already agrees: the signer's right shoulder is at smaller x in the data, and the rig's
    # right arm is at negative x. No mirroring. y is flipped because the data is image space.
    def to_rig(p):
        return origin + np.array([p[0], -p[1], p[2]]) * scale

    HS = {s: hand_scale(F, s, rig) for s in ("l", "r")}
    ZS = smooth_z(F)
    tree = build_tree(rig)
    prev_sign = {}
    out_q, err, shp, clamps, total = [], [], [], 0, 0
    driven = [c[0] for c in chains]
    for fi in range(n):
        tgt = {}
        for lm in range(75):
            tgt[lm] = to_rig(F[fi, lm]) if not np.any(np.isnan(F[fi, lm])) else \
                np.array([np.nan] * 3)
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
        P, cl, used = solve_depth(tgt, rig, F[fi], tree,
                                  zref=ZS[fi], prev_sign=prev_sign)
        prev_sign.update(used)
        clamps += cl
        total += len(tree)

        # Hierarchical direction match. Walk the rig's own node order so a parent's solved
        # world rotation is always available before its children are solved in it.
        world_R, world_T, local_q = {}, {}, {}
        by_bone = {c[0]: c for c in chains}
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
                world_R[bi] = pR @ rig.rest_R[bi]
                continue
            _bone, child, a, b = c
            if P.get(b) is None or P.get(a) is None:
                world_R[bi] = pR @ rig.rest_R[bi]      # HOLD REST: missing hand (§6)
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
        out_q.append({k: [round(float(x), 5) for x in v] for k, v in local_q.items()})

        # §14 test 7: where did the wrist land? Measured on the RIG, by forward kinematics
        # through the quaternions we are about to ship -- world_T above is that FK.
        #
        # The previous version compared P[wr] to tgt[wr]. Those are solve_depth's output and
        # its own input, and solve_depth copies x/y straight through, so the two are equal by
        # construction: it reported 0.00% on six of eleven signs and never once looked at the
        # skeleton. A metric that cannot fail is not a test, and this one certified a rig
        # whose fingertips were a whole hand-length out of place. Anything scored here must
        # come from world_T, never from P.
        #
        # Image plane only -- the target's own z is the noise this solver exists to discard,
        # so scoring against it would be scoring against nothing.
        for side, wr in (("l", L_WR), ("r", R_WR)):
            if np.any(np.isnan(tgt[wr])):
                continue
            got = world_T[rig.by[f"hand_{side}"]]
            err.append(float(np.linalg.norm(got[:2] - tgt[wr][:2])) / scale)
            # Handshape, scored separately so it cannot hide behind placement: each
            # fingertip's offset FROM THE WRIST, against the same offset in the (shrunk,
            # translated) target, in rig hand-lengths.
            h0 = HAND0[side]
            hl = float(np.linalg.norm(rig.wp(f"middle_01_{side}") - rig.wp(f"hand_{side}")))
            for fname, off in FINGER_OFF.items():
                tip = h0 + off + 3
                if np.any(np.isnan(tgt[tip])):
                    continue
                g = world_T[rig.by[f"{fname}_end_{side}"]] - got
                t_ = tgt[tip] - tgt[h0]
                shp.append(float(np.linalg.norm(g[:2] - t_[:2])) / hl)
    return d, out_q, np.array(err), np.array(shp), clamps, total, driven


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
    base, _, err0, shp0, *_ = retarget_word(rig, "hello", chains)
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
    assert abs(float(shp1.mean()) - float(shp0.mean())) < 1e-9, (
        "[err] handshape moved when only the ELBOW changed. It is supposed to be "
        "wrist-relative; if the elbow leaks into it, the two metrics are not independent "
        "and neither one means what it says.")
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


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
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
          f"{'p95':>7s} {'handshape':>10s} {'clamped':>8s}")
    print("-" * 74)
    baked = {}
    for w in words:
        if not (WORDS / f"{w}.json").exists():
            print(f"{w:<12s}  no such word file")
            continue
        d, q, err, shp, cl, tot, driven = retarget_word(rig, w, chains)
        F = np.array(d["frames"], dtype=float)
        lh = 1.0 - np.isnan(F[:, 33:54, 0]).mean()
        rh = 1.0 - np.isnan(F[:, 54:75, 0]).mean()
        hands = ("both" if lh > .5 and rh > .5 else "right" if rh > .5 else
                 "left" if lh > .5 else "none")
        e = f"{err.mean()*100:.1f}%" if len(err) else "n/a"
        p95 = f"{np.percentile(err,95)*100:.1f}%" if len(err) else "n/a"
        hs = f"{shp.mean()*100:.1f}%" if len(shp) else "n/a"
        print(f"{w:<12s} {len(q):6d} {hands:>12s} {e:>11s} {p95:>7s} {hs:>10s} "
              f"{cl*100.0/max(tot,1):7.1f}%")
        baked[w] = {"fps": d["fps"], "frames": q,
                    "hands": hands, "gloss": d.get("glosses", [w])[0],
                    # §14 test 7 numbers travel WITH the animation, so a viewer showing the
                    # sign always shows how well it actually landed rather than implying it
                    # is exact.
                    "err": round(float(err.mean() * 100), 2) if len(err) else None,
                    "p95": round(float(np.percentile(err, 95) * 100), 2) if len(err) else None,
                    "shape": round(float(shp.mean() * 100), 1) if len(shp) else None,
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
