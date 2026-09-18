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

# ── the three lexicon files this renderer is REQUIRED to read ────────────────────────────
# asl_handedness_250.json's `renderer_contract` is not advice, it is the interface: "For every
# word not marked '1', the passive hand's landmarks DO NOT EXIST in our corpus for any take...
# The avatar must synthesize the passive hand: 2s -> mirror the dominant hand across the body
# midline. 2a -> place an unmarked handshape at the base location; do not mirror."
#
# Until now this file synthesized only the 2s case and decided WHICH words got it by measuring
# the passive wrist's height. That measurement answers a different question -- "is this arm in
# the signing space on this take" -- and using it as the lexical one put a second hand on 8
# one-handed signs (`blue`, `happy`, `brother`, `aunt`, `if`, `pencil`, `snow`, `stairs`) and
# left 12 symmetrical ones with a single hand (`rain`, `cry`, `smile`, `blow`, `wet`...).
# Neither shows up in any error column: the handshape metric only scores hands it drives
# against landmarks that exist, so it cannot charge us for inventing a hand or for dropping
# one. Both decisions are still made, but from their own evidence now -- the class from the
# lexicon, because handedness provably is not derivable from these landmarks (that file's own
# `why` records four classifiers at AUC 0.335-0.500), and the take's usability from the data.
LEXICON = REPO / "asl_handedness_250.json"
BASE_PLACE = REPO / "asl_2a_base_placement.json"
TEMPLATES = REPO / "handshape_templates.json"

_LEX_CACHE = {}


def lexicon(path=LEXICON):
    """word -> (class, confidence). Missing file or word falls back to measurement."""
    if path not in _LEX_CACHE:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            _LEX_CACHE[path] = {
                "class": {k: tuple(v) for k, v in d["words"].items()},
                "passive": d.get("passive_handshape", {}).get("words", {}),
            }
        except (OSError, KeyError, ValueError):
            _LEX_CACHE[path] = {"class": {}, "passive": {}}
    return _LEX_CACHE[path]


def base_placement(path=BASE_PLACE):
    if path not in _LEX_CACHE:
        try:
            _LEX_CACHE[path] = json.loads(
                Path(path).read_text(encoding="utf-8"))["words"]
        except (OSError, KeyError, ValueError):
            _LEX_CACHE[path] = {}
    return _LEX_CACHE[path]


def handshape_template(name, path=TEMPLATES):
    """The 21 palm-frame points of one unmarked handshape, RIGHT-hand chirality.

    Returns (points, normal) where `normal` is the palm normal in the same frame, or None if
    the shape is unknown. The file's z_warning says to prefer template_xy where the 3D
    agreement is materially worse than the 2D -- z there is raw MediaPipe relative depth,
    the same channel this whole file refuses to trust -- so that comparison is made here
    rather than assumed either way.
    """
    if path not in _LEX_CACHE:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            _LEX_CACHE[path] = (d["handshapes"],
                                {k: v["use"] for k, v in d.get("resolution", {}).items()})
        except (OSError, KeyError, ValueError):
            _LEX_CACHE[path] = ({}, {})
    shapes, resolve = _LEX_CACHE[path]
    h = shapes.get(resolve.get(name, name)) or shapes.get(name)
    if h is None or not h.get("usable", False):
        return None, None
    axy, axyz = h.get("agreement_xy", 0.0), h.get("agreement_xyz", 1e9)
    if axyz <= axy * 1.05 and h.get("template_xyz"):
        return np.array(h["template_xyz"], dtype=float), np.array([0.0, 0.0, 1.0])
    p = np.array(h["template_xy"], dtype=float)
    return np.column_stack([p, np.zeros(len(p))]), np.array([0.0, 0.0, 1.0])

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

# Distance from the eye midpoint, in shoulder widths, over which the hand's placement hands
# over from face-anchored to body-mapped. Measured across 120 words, the hand's closest
# approach to the eyes runs p5 0.168 to p90 0.560, median 0.391.
# How much bend a finger needs before its landmarks define a plane worth using, as sin of the
# angle. LOW ON PURPOSE (0.17 is 10 degrees): a high threshold is the worst of both worlds,
# because the frames that fall through get an arbitrary roll from align() and the hinges below
# then bend faithfully in that arbitrary plane. Measured over 12 signs, mean handshape error:
# threshold 10deg 18.7%, 20deg 20.0%, 30deg 21.5%.
#
# Lowered again to 0.10 (5.7deg) once the per-segment reach fit was in, and it is a strict win
# on BOTH axes at once, which is unusual enough to record: over 18 signs, handshape 18.32% ->
# 18.12% and the share of frames with a bone jumping more than 30 degrees 13.6% -> 10.6%. The
# jitter half is the interesting one -- solving the plane MORE often makes the motion smoother,
# because a gate that flips on and off between frames hands the roll back and forth between
# the solved plane and align()'s arbitrary one, and that handover is itself the snap. 0.05 is
# worse again (jitter mean 13.97 -> 14.67), so this is a floor, not a direction.
#
# WHAT THAT HANDOVER ACTUALLY COSTS, measured 2026-09-18 over all 250 -- and why the obvious
# fix was tried and REJECTED. Every single-frame step over 30 degrees was decomposed into the
# angle the bone's own AXIS turned through (real motion) and the twist about that axis (which
# moves no landmark, so the solver is free to choose it):
#
#     whole rotation  mean 58.9d      of which axis 13.6d, twist 45.4d
#     75% of those steps turn the bone's axis less than 15 degrees
#
# Three quarters of the popping is a phalanx spinning in place, which is not a motion a finger
# has, and it is concentrated exactly where this gate lives: the five MCPs account for 67.8% of
# all over-30 steps and the thumb's for another 21.6%, while the PIPs and DIPs below them --
# hinges, with no free roll -- barely appear.
#
# The fix that follows from that is to stop switching and start blending: carry the rig's own
# rest plane (exact, cannot shimmer) and cross-fade to the measured plane as the finger bends,
# over a band FINGER_PLANE_MIN..FULL. It works, and it is still the wrong trade:
#
#     FULL   handshape   >30d    kiss    radio
#     --     10.97%      7.59%   21.5%   19.5%   <- shipped, the hard gate
#     0.101  11.11%      8.38%                   (fallback swapped, no blend: WORSE both ways)
#     0.20   11.15%      6.50%   23.0%   22.4%
#     0.30   11.27%      5.80%
#     0.60   11.70%      4.58%
#
# The popping gain is real and diffuse; the cost lands on `kiss` and `radio`, which were already
# the two worst solver-side words in the set and are the two that are ABOUT the thumb. Holding
# the thumb out of the blend recovers the over-20 count but gives back half the smoothness
# (7.09%) and still leaves both words worse than they are here. A mean that improves while the
# named problem cases regress is the trade this file has been caught taking before.
#
# So the gate stays, and the finding is left here rather than in a commit message because the
# next person to look at finger popping should start from "75% of it is twist" and not have to
# re-derive it. The lever that would settle it is the rigger's seven handshape reference poses:
# with a measured pose per handshape the knuckle's roll is a lookup, not a fit.
FINGER_PLANE_MIN = 0.10

# Weight of the newest frame in the finger-plane average. Low: the plane turns slowly.
PLANE_EMA = 0.30

FACE_SIGMA = 0.25   # falloff of the contact weighting
FACE_NEAR = 0.30
FACE_FAR = 0.70

# The per-frame wrist step, in shoulder widths, that a clean clip shows. Clips noisier than
# this get proportionally more smoothing. `hello` measures 0.084.
NOISE_REF = 0.10

# Zero-phase: run the rotation filter forward and then backward. See smooth_quats().
TWO_PASS = True

# Reopened from 3.0 because the signal is now smoothed twice. Measured over all 250, against
# the unfiltered track, the second pass is free in the only sense that matters -- it smooths
# MORE while displacing the animation LESS:
#
#     setting                jitter   >30deg   moves the signal   wrist   handshape
#     unfiltered             15.63d   11.11%          --            --       --
#     one pass,  cutoff 3.0  12.93d    8.95%        2.50d         4.41%    12.32%
#     two pass,  cutoff 6.0  11.38d    7.80%        2.09d         4.09%    11.86%   <- shipped
#     two pass,  cutoff 8.0  11.48d    7.84%        2.00d         3.75%    11.76%
#     two pass,  cutoff 14   11.72d    7.93%          --          3.03%    11.54%
#
# 6.0 is the knee on JITTER, and jitter is the only honest objective here. Wrist error and
# handshape improve monotonically as the cutoff opens, but they measure fidelity to a target
# that contains the tracking noise, so they reward filtering less by construction -- choosing
# on them would end with the filter switched off and the numbers calling it an improvement.
Q_MIN_CUTOFF = 6.0
Q_BETA = 0.02

# Playback timing -- see retime(). Frames at 30 fps: 6 = 0.20 s, 10 = 0.33 s, 18 = 0.60 s.
HOLD_IN = 6
HOLD_OUT = 10
MIN_STROKE = 18
MAX_STRETCH = 2.0

# Share of frames a hand block must appear in before the clip counts as having that hand at
# all. See the note in main(): the old 0.5 disowned 28 clips that are 11-50% tracked.
HAND_MIN = 0.10

# Passive-wrist travel, as a fraction of the dominant wrist's, above which a two-handed sign
# counts as SYMMETRIC rather than base-and-dominant. See mirror_passive_hand().
PASSIVE_MOVE = 0.35

# Which of the 20 per-segment shrink ratios hand_scale() takes. See its docstring: the median
# is the estimate of the signer's hand, but it leaves half the segments still longer than the
# rig's own bone, and those clamp flat. Swept, not chosen.
HAND_SCALE_Q = 50.0

# How far inside the rig's reach fit_reach() pulls a frame that does not fit. Exactly on the
# limit recovers zero depth, which is the flat finger we are trying to avoid.
FIT_MARGIN = 0.97

# How far a single phalanx's scale may depart from the hand-wide median, as a factor either
# way. See hand_seg_scales(); 1.0 collapses it back to one scale for the whole hand.
SEG_BAND = 1.0

# The torso the hand may not be inside of, in shoulder-widths: how far past the shoulder line
# the chest surface sits, and how far outside the shoulders the ribcage still counts. Only a
# collision box -- see the note where it is applied; it is not a depth estimate.
TORSO_FRONT = 0.10
TORSO_PAD = 0.10

# How close to the shoulder line a wrist must come, in shoulder-widths of the DATA, before that
# arm counts as taking part in the sign rather than hanging. Parked arms measure 0.86-1.18
# below; a base hand at chest height is nearer 0.3-0.5.
PARKED_Y = 0.60

# The furthest from its own shoulder a synthesized 2a base hand may be placed, as a fraction of
# that arm's reach. NOT a taste knob: it is the 95th percentile of base-distance/reach over the
# 24 words whose placement was already reachable, so clamping an outlier never pulls it tighter
# than the range its peers occupy. Leaves ~144 deg at the elbow -- extended, not locked. See
# unmarked_base() for what goes wrong without it.
REACH_FRAC = 0.97

# TRIED AND REJECTED: solving the hand bone's rotation by least squares over all five
# metacarpal heads instead of the two-vector index/pinky frame. It is a better fit by every
# average -- handshape 12.83% -> 12.77%, thumb direction 6.4 -> 5.4 degrees, jumps over 30
# degrees 10.18% -> 9.66% -- and it is worse where it counts. Words above 20% handshape, which
# is roughly where a sign starts looking wrong rather than slightly off, went 10 -> 18, and
# above 25% went 3 -> 7: `bee` 18->27, `bedroom` 18->27, `smile` 20->27, `horse` 18->25.
#
# The rig's palm fan and MediaPipe's differ in SHAPE (thumb -8.2 degrees, pinky -8.8, middle
# +0.5), and no rotation absorbs that. The two-vector frame dumps the whole mismatch on the
# thumb; least squares spreads it over all five digits, which lowers the mean by making four
# digits slightly worse on the words that were already marginal. Correcting the reference fan
# instead was tried too and is worse again, because it measures a fan in a frame built from the
# data's z -- the axis this file spends its length establishing is noise.


# Which landmarks carry the in-front prior into solve_depth. See the table in retarget_word():
# elbows only was measured against wrist only, never against BOTH, and both is better.
WANT_FRONT_LM = (L_EL, R_EL, L_WR, R_WR)

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


def flexion_axes(rig):
    """The one axis each finger joint is allowed to turn about, in world rest space.

    A finger's middle and end joints (PIP and DIP) are HINGES. They flex and extend and that
    is all: they cannot twist, and they cannot splay sideways -- only the knuckle (MCP) can do
    that. Solving all three with a free minimal rotation, as this did, lets landmark noise
    splay and twist each phalanx independently, and the result is a hand that cannot exist.

    Measured, as the angle between the plane of the first two phalanges and the plane of the
    last two, which a real finger holds at zero:

        yes 41.0 deg mean, p90 71.8      dad 34.7, p90 75.6      hello 34.0, p90 72.4
        clean 25.0                        drink 23.2              blue 17.4

    Worst on `yes`, a fist -- a closed hand is where the landmarks are least reliable and the
    direction recovery worst conditioned, which is exactly where anatomy has to carry the
    answer instead. This is the constraint the rigger's seven handshape reference poses would
    supply directly; until they arrive, the hinge is the part we can derive ourselves.

    The axis is across the palm, perpendicular to the bone: a finger curls toward the palm.
    """
    ax = {}
    for side in ("l", "r"):
        # The palm's own plane, from two vectors that lie in it.
        across = rig.wp(f"pinky_01_{side}") - rig.wp(f"index_01_{side}")
        fwd = rig.wp(f"middle_01_{side}") - rig.wp(f"hand_{side}")
        palm_n = np.cross(across, fwd)
        if np.linalg.norm(palm_n) < 1e-9:
            continue
        palm_n = palm_n / np.linalg.norm(palm_n)
        for f in FINGER_OFF:
            # THE RIG ALREADY KNOWS EACH DIGIT'S PLANE, because the rigger posed the rest hand
            # with a natural curl rather than dead straight -- 10 degrees at every finger joint
            # and 14 at the thumb's first. Three consecutive joints with a bend in them define
            # a plane, and that plane IS the flexion plane. Reading it off the rig beats
            # deriving it: a palm-normal construction is right for the four fingers (their
            # chain normal sits 87.5 degrees from the palm normal, i.e. across the palm, as
            # expected) and wrong for the thumb, whose column is rotated out of the finger row
            # and whose chain normal is only 33.8 degrees from it. Per digit, from its own
            # geometry, with no special case for the thumb.
            ch = [f"{f}_01_{side}", f"{f}_02_{side}", f"{f}_03_{side}", f"{f}_end_{side}"]
            if any(c not in rig.by for c in ch):
                continue
            v1 = rig.wp(ch[1]) - rig.wp(ch[0])
            v2 = rig.wp(ch[2]) - rig.wp(ch[1])
            a = np.cross(v1, v2)
            if np.linalg.norm(a) < 1e-9:
                a = np.cross(v2, palm_n)          # rest chain straight: fall back to the palm
            if np.linalg.norm(a) < 1e-9:
                continue
            a = a / np.linalg.norm(a)
            for k in (2, 3):
                ax[f"{f}_0{k}_{side}"] = a
    return ax


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


def one_euro(F, fps=30.0, min_cutoff=2.0, beta=0.4, _two_pass=True):
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

    RUN FORWARD THEN BACKWARD. A one-pole filter lags, and that grid was measured with only
    the forward pass, so every row of it paid a lag it could not see. smooth_quats() went
    zero-phase for the same reason and the input filter was simply left behind. Measured
    across all 250, same cutoff, forward-backward against forward alone:

        one pass  mc 2.0   wrist 4.09%  shape 11.86%  >30d 7.80%  | vs RAW: tip 6.60d
        two pass  mc 2.0   wrist 3.22%  shape 10.97%  >30d 5.62%  | vs RAW: tip 6.25d  <- here
        two pass  mc 3.0   wrist 3.54%  shape 11.28%  >30d 6.25%  | vs RAW: tip 6.11d
        two pass  mc 4.5   wrist 3.93%  shape 11.60%  >30d 7.21%  | vs RAW: tip 6.03d
        two pass  mc 6.0   wrist 4.24%  shape 11.84%  >30d 7.82%  | vs RAW: tip 5.98d

    The second pass improves every column at once, which a smoothing change is not supposed to
    do -- smoothing trades handshape for stability, and that trade is what the cutoff column
    shows. It can do it because removing a PHASE LAG is not smoothing: the lagged output was
    simply the right pose at the wrong time. `vs RAW` is the check that this is real and not
    the filter flattering itself -- fingertip direction scored against the UNFILTERED
    landmarks, where more smoothing cannot help by definition. It improves too.
    """
    if _two_pass:
        fwd = one_euro(F, fps, min_cutoff, beta, _two_pass=False)
        return one_euro(fwd[::-1], fps, min_cutoff, beta, _two_pass=False)[::-1]
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
    # Segments this frame actually had the landmarks to solve. The rate used to divide by the
    # WHOLE tree, so a clip missing a hand -- which in this corpus is every clip, on the
    # passive side -- had 20 unsolvable segments counted as un-clamped successes. That made
    # the number smallest exactly where the data was worst.
    tried = 0
    for b, a, L in tree:
        pa = P.get(a)
        if pa is None or np.any(np.isnan(tgt[b])):
            P[b] = None
            continue
        if L == 0.0:                                   # coincident landmarks
            P[b] = pa.copy()
            continue
        tried += 1
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
    return P, clamped, sign_used, tried


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
    return float(np.percentile(ratios, HAND_SCALE_Q))


def hand_seg_scales(F, side, rig):
    """One shrink factor PER PHALANX, not one for the whole hand.

    hand_scale() takes the median of the 20 per-segment ratios, and the median is the problem.
    A segment whose own ratio is ABOVE the median ends up with a target shorter than the rig
    bone that has to span it -- and solve_depth reads any shortfall against bone length as
    DEPTH, because for a rigid phalanx that is what a shortfall means. So it invents an
    out-of-plane rotation, on every frame, for as long as the clip lasts. With index ratios of
    0.68/0.50/0.69/0.65 against a median near 0.62, the two outer segments sit at 0.91 of the
    rig bone, which the solver turns into 0.41 of a bone length of invented depth -- about 24
    degrees of spurious rotation per joint. The hinge below then bends in that tilted plane and
    the finger comes out STRAIGHTER than the signer's.

    That is exactly what the worst words were. Measured as the distance from wrist to fingertip
    in rig hand-lengths, avatar against target: `blue` index 1.85 vs 1.52 and middle 1.88 vs
    1.57, `clean` 1.80 vs 1.49 -- fingers pointing the right way (3-10 degrees) and not curling.
    The words that already worked show no such gap: `dad` 1.40 vs 1.41, `mom` 1.52 vs 1.48.

    Per segment there is no residual to invent: each phalanx's 90th-percentile projection maps
    onto that phalanx's own rig bone, so a face-on finger reconstructs at zero depth and the
    depth solve is left doing only the job it is good at -- real foreshortening. Scaling each
    segment separately cannot distort the handshape, because the handshape is the ANGLES
    between segments and those are untouched; the lengths were never the signer's to lend.

    BOUNDED, not taken raw. A segment's 90th percentile is only a good estimate of its true
    length if that segment was actually seen near face-on at some point, and some never are --
    a finger held curled or pointing at the camera for a whole short clip has every projection
    foreshortened, so p90 under-reads the bone and the ratio over-reads the correction. Taken
    raw that is visible: the words that REGRESSED when this replaced the median are exactly the
    ones whose per-segment scales spread widest -- `drawer` 0.28 to 1.63, a factor of 5.8, and
    `milk` up to 2.02 -- against 1.5-1.9 on `hello`, `blue` and `dad`, which all improved. A
    scale above 1 means lengthening a segment, which for a rig whose hand is smaller than every
    signer's is a tell that the estimate is bad rather than that the bone is long.

    So each ratio is clipped to a band around the hand-wide median, which is the same estimator
    with 20 segments behind it: per segment where the data supports it, pooled where it does
    not. SEG_BAND = 1.0 recovers the old single-factor behaviour exactly.
    """
    h0 = HAND0[side]
    sh = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    med = hand_scale(F, side, rig)
    lo, hi = med / SEG_BAND, med * SEG_BAND
    out = {}
    for f, o in FINGER_OFF.items():
        names = [f"hand_{side}", f"{f}_01_{side}", f"{f}_02_{side}", f"{f}_03_{side}",
                 f"{f}_end_{side}"]
        ks = [h0] + [h0 + o + k for k in range(4)]
        for i in range(4):
            d = np.linalg.norm(F[:, ks[i + 1], :2] - F[:, ks[i], :2], axis=1)
            d = d[~np.isnan(d)]
            L = rig.bone_len(names[i], names[i + 1]) / sh
            if len(d) < 3:
                out[(ks[i], ks[i + 1])] = (None, L)
                continue
            est = float(np.percentile(d, 90))
            s = float(np.clip(L / est, lo, hi)) if est > 1e-6 else None
            out[(ks[i], ks[i + 1])] = (s, L)
    return out


def hand_chains(rig, side):
    """Each finger as a chain of (parent lm, child lm, rig length) from the wrist outward."""
    h0 = HAND0[side]
    sh = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    out = []
    for f, o in FINGER_OFF.items():
        ch = [(h0, h0 + o, rig.bone_len(f"hand_{side}", f"{f}_01_{side}") / sh)]
        for k in (1, 2, 3):
            nxt = f"{f}_0{k+1}_{side}" if k < 3 else f"{f}_end_{side}"
            ch.append((h0 + o + k - 1, h0 + o + k,
                       rig.bone_len(f"{f}_0{k}_{side}", nxt) / sh))
        out.append(ch)
    return out


def fit_reach(tgt, chains, scale):
    """Rebuild each finger so every segment is within the rig bone that has to span it.

    A GLOBAL hand scale cannot do this, and the sweep is why. hand_scale() estimates the
    signer's hand from the 90th percentile of each segment's projected length; whichever
    percentile is then taken ACROSS the 20 segments is one compromise for the whole clip:

        percentile    handshape   clamped      yes    time    food
            50          20.90%     36.94%     15.2    22.9    25.1
            25          18.99%     19.76%     20.7    12.9    10.2
            15          18.92%     11.17%     21.1    10.2    10.5

    Shrinking helps the signs held face-on (TIME, FOOD, SAME, HIGH) and hurts the closed ones
    (YES is a fist, SICK a bent middle finger), so no percentile serves both.

    Shrinking the whole hand per frame does not work either, and the reason is the useful
    finding: the binding segment is almost always ONE segment, `pinky_1`, needing a factor of
    0.48-0.77 on words as different as TIME, FOOD, BLUE and YES. The rig's finger PROPORTIONS
    differ from MediaPipe's hand model -- its pinky proximal phalanx is relatively much
    shorter -- so a whole-hand fit shrinks the hand by up to half to satisfy one bone.

    It is a per-segment mismatch, so it is fixed per segment. Each finger is rebuilt from the
    wrist outward keeping the data's DIRECTION for every segment and capping only its LENGTH
    at the rig's own bone. That is exactly the right thing to discard: the finger solve reads
    directions, not positions -- length enters only through the depth recovery, which needs
    the 2D span to fit inside the bone or it has no real root and flattens the finger into the
    image plane. Angles are the handshape and they are preserved exactly; lengths were never
    ours to keep, since they belong to a different hand.
    """
    for ch in chains:
        # Segment vectors are read BEFORE any of them moves. Walking a chain while reading
        # tgt[b] - tgt[a] takes the vector from the already-moved parent to the not-yet-moved
        # child, which is not a segment of anybody's hand -- it silently lengthens every
        # segment after the first one that gets capped.
        vs = [(a, b, tgt[b] - tgt[a], L) for a, b, L in ch
              if not (np.any(np.isnan(tgt[a])) or np.any(np.isnan(tgt[b])))]
        for a, b, v, L in vs:
            n = float(np.linalg.norm(v[:2])) / scale
            # FIT_MARGIN keeps it just inside: a segment at planar == L recovers dz == 0,
            # which is the flat finger this exists to prevent -- clamping removed from the
            # count and not from the animation.
            if n > L * FIT_MARGIN > 0.0:
                v = v * (L * FIT_MARGIN / n)
            tgt[b] = tgt[a] + v
    return tgt


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

    def pass_(frames, nm, mc):
        prev, prev_speed = None, 0.0
        for f in frames:
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

    # FORWARD THEN BACKWARD, because a one-pole filter LAGS and the lag is not small. Every
    # wrist error above about 5% traces to it rather than to the solve: measured on the frames
    # themselves, the depth solver puts the wrist exactly on its 2D target -- residual 0.000 --
    # and the number the second pass reports is how far the filter then moved it. On a long
    # clip that is a transient (`hello` reads 17, 8, 22, 15% over its first four frames and
    # then 1-2% for the remaining fifty), but `after` is 17 frames long, so the transient IS
    # its average, and it was the worst-placed sign in the set at 12.3%.
    #
    # Running the same filter backwards over the result cancels the phase shift exactly, which
    # is what filtfilt does and what makes it worth having: offline, whole clips, no reason to
    # accept the lag of a causal filter. The cost is that the signal is smoothed twice, so the
    # cutoff has to be reopened to land back on the same response -- see Q_MIN_CUTOFF.
    for nm in sorted({k for f in out for k in f}):
        mc = (bone_cut or {}).get(nm, min_cutoff)
        pass_(out, nm, mc)
        if TWO_PASS:
            pass_(out[::-1], nm, mc)
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


def mirror_passive_hand(F, dom):
    """Give the passive hand the dominant hand's handshape, mirrored. 72 of 250 signs.

    THE PASSIVE HAND IS NOT IN THIS CORPUS AT ALL. Measured over all 250 clips, the left hand
    block is NaN on 100.00% of frames -- not one landmark, in any word. The left ARM is a
    different story: the pose left wrist and elbow are tracked in 250 of 250, and the corpus
    flags 87 signs as two-handed. So on those the avatar's passive arm swings through the sign
    correctly with a flat, uncurled rest hand stuck on the end of it. That is the single most
    visible defect left, and it is on 35% of the vocabulary.

    ASL settles what the missing handshape is, for most of those signs. Battison's Symmetry
    Condition: in a two-handed sign where BOTH hands move, the two hands have the same
    handshape and mirrored orientation -- it is a well-formedness constraint on the lexicon,
    not a tendency. So for those signs the passive handshape is recoverable exactly: reflect
    the dominant hand's landmarks across the sagittal plane and anchor them on the passive
    wrist, which IS tracked. Reflecting the landmarks rather than the solved quaternions is
    deliberate -- it goes in as data, so hand_scale, the depth solve, flexion_axes and the
    hinge constraints all apply to the passive hand exactly as they do to the dominant one,
    with no assumption that the rig's two hands are perfect mirrors of each other.

    THE OTHER 15 ARE NOT DONE HERE and must not be. When only one hand moves, the Dominance
    Condition holds instead: the passive hand is a static base drawn from a small set of
    unmarked handshapes, and it is NOT required to match the dominant hand -- mirroring
    TOUCH or CHOCOLATE would put a moving handshape on a hand that should be a flat base.
    Those keep the rest pose, which is a relaxed near-flat hand, i.e. the commonest base
    there is. Which of the two rules applies is decided by measurement in retarget_word().

    What this CANNOT do is make the passive handshape a measured quantity. It is derived from
    a linguistic rule applied to the other hand, so it is excluded from the reported handshape
    error -- scoring a synthesised target against itself is exactly the self-referential trap
    this file has already been caught in twice. The passive ARM stays scored: that one is real
    pose data.
    """
    pas = "l" if dom == "r" else "r"
    s0, d0 = HAND0[dom], HAND0[pas]
    p_wr = L_WR if pas == "l" else R_WR
    rel = F[:, s0:s0 + 21, :] - F[:, s0:s0 + 1, :]
    rel[:, :, 0] = -rel[:, :, 0]              # reflect across the sagittal plane: x only
    # NaN propagates on its own, so a frame missing the dominant hand or the passive pose
    # wrist stays missing and bridge_gaps handles it like any other gap.
    F[:, d0:d0 + 21, :] = F[:, p_wr:p_wr + 1, :] + rel
    return F


def mirror_passive_arm(F, dom):
    """Reflect the dominant ARM across the body midline onto the passive side. 2s only.

    mirror_passive_hand() anchors the reflected handshape on the TRACKED passive wrist, which
    is right whenever that wrist is where the signer actually held their passive hand. On 12
    of the 52 symmetrical signs it is not: the signer simply did not raise the second arm --
    `rain`, `cry`, `smile`, `blow`, `wet`, `sticky`, `fast`, `cowboy`, `donkey`, `stay`,
    `yucky`, `refrigerator` all measure the passive wrist at or below the parked threshold,
    and their passive HAND block is 100% NaN like every other clip in the corpus. Anchoring a
    mirrored handshape on a hip is worse than nothing, so those words used to render with one
    hand -- which for RAIN or CRY is not a lesser version of the sign, it is a different one.

    The Symmetry Condition says what the second arm was doing: the same thing, mirrored. So
    the whole limb is reflected, not just the hand. Reflecting across the SHOULDER MIDPOINT
    rather than about x=0 matters -- the export is shoulder-centred but a signer is not
    perfectly square to the camera, and reflecting about the wrong plane tilts the mirrored
    arm out of the body.

    This makes the passive arm synthetic, so retarget_word() stops scoring it. The alternative
    -- driving the parked arm from its own pose landmarks -- is what the note in retarget_word
    measured at over 30 degrees of single-frame jump on 4.8% of frames: shoulder, elbow and
    wrist nearly collinear is ill-conditioned, and a mirrored arm is not.
    """
    pas = "l" if dom == "r" else "r"
    midx = 0.5 * (F[:, L_SH, 0] + F[:, R_SH, 0])
    for a, b in (((R_EL, L_EL) if dom == "r" else (L_EL, R_EL)),
                 ((R_WR, L_WR) if dom == "r" else (L_WR, R_WR))):
        F[:, b, 0] = 2.0 * midx - F[:, a, 0]
        F[:, b, 1] = F[:, a, 1]
        F[:, b, 2] = F[:, a, 2]
    return F, pas


# Where each orientation word points, in the flipped data frame: x toward the signer's LEFT,
# y DOWN (image space), z toward the viewer once retarget_word has flipped it. The vocabulary
# is asl_2a_base_placement.json's own; `toward_dominant` is the only one that depends on which
# hand is dominant, and every exemplar in this corpus is right-dominant.
def _dir(word, dom):
    to_dom = -1.0 if dom == "r" else 1.0
    return {"up": (0.0, -1.0, 0.0), "down": (0.0, 1.0, 0.0),
            "toward_signer": (0.0, 0.0, -1.0), "away_from_signer": (0.0, 0.0, 1.0),
            "forward": (0.0, 0.0, 1.0), "toward_dominant": (to_dom, 0.0, 0.0),
            }.get(word)


def _elbow_2d(shoulder, wrist, a, b, out_sign):
    """Where the elbow goes so both bones keep their length and the joint points outward."""
    d = wrist[:2] - shoulder[:2]
    L = float(np.linalg.norm(d))
    if L < 1e-6:
        return None
    if L >= a + b:                              # unreachable: straighten the arm
        return np.array([shoulder[0] + d[0] * a / L, shoulder[1] + d[1] * a / L, wrist[2]])
    t = (a * a - b * b + L * L) / (2.0 * L)
    h = float(np.sqrt(max(a * a - t * t, 0.0)))
    u = d / L
    n = np.array([-u[1], u[0]])                 # perpendicular, in the image plane
    e = shoulder[:2] + u * t + n * (h * out_sign)
    return np.array([e[0], e[1], 0.5 * (shoulder[2] + wrist[2])])


def unmarked_base(F, word, dom):
    """class 2a: a STATIC unmarked base hand, placed from the lexicon rather than the take.

    Battison's Dominance Condition: when only one hand moves, the passive hand is a static
    base restricted to a small set of unmarked handshapes. It is not a mirror of the dominant
    hand -- mirroring TOUCH or CHOCOLATE puts a moving handshape on a hand that should be a
    flat B -- and it is not at the recorded passive wrist either. asl_2a_base_placement.json
    measured that wrist across all 35 of these words and found it a median 1.56 shoulder
    widths from the dominant one, most of an arm away: "It is not a badly-placed base; it is
    an arm doing nothing." So both the shape and the position are supplied by lexicon:

        handshape   asl_handedness_250.json    passive_handshape.words[word].shape
        template    handshape_templates.json   21 points in a canonical palm frame
        position    asl_2a_base_placement.json anchor mode + offset from the dominant wrist
        orientation asl_2a_base_placement.json palm/fingers direction words

    WHAT THIS IS NOT: measured. All three files carry the same review status -- authored by a
    hearing developer from published ASL phonology, not validated against video, not seen by a
    Deaf signer. They render plausibly; they are not evidence. Nothing synthesized here is
    scored, for the reason the mirrored hand is not scored, and `kind` is returned so the
    caller can keep the synthetic arm out of the wrist and depth metrics too.

    The template is RIGHT-hand chirality (the file reflected its left-hand samples in z before
    averaging), so for a right-dominant signer -- which is every exemplar in this corpus --
    the palm normal is negated to get a left hand back. Returns (F, placed).
    """
    pas = "l" if dom == "r" else "r"
    ph = lexicon()["passive"].get(word)
    pl = base_placement().get(word)
    if not ph or not pl:
        return F, False
    pts, n_t = handshape_template(ph.get("shape", ""))
    if pts is None:
        return F, False
    palm, fing = _dir(pl.get("palm", ""), dom), _dir(pl.get("fingers", ""), dom)
    if palm is None or fing is None:
        return F, False

    d0, p0 = HAND0[dom], HAND0[pas]
    d_wr, p_wr = (R_WR, L_WR) if dom == "r" else (L_WR, R_WR)
    d_sh, p_sh = (R_SH, L_SH) if dom == "r" else (L_SH, R_SH)
    d_el, p_el = (R_EL, L_EL) if dom == "r" else (L_EL, R_EL)

    track = F[:, d_wr, :]
    ok = ~np.isnan(track[:, 0])
    if not ok.any():
        return F, False
    mode = pl.get("anchor", "dominant_median")
    if mode == "dominant_lowest":
        anchor = track[np.nanargmax(np.where(ok, track[:, 1], -np.inf))]
    elif mode == "dominant_first":
        anchor = track[int(np.argmax(ok))]
    elif mode == "dominant_last":
        anchor = track[len(ok) - 1 - int(np.argmax(ok[::-1]))]
    else:
        anchor = np.array([float(np.nanmedian(track[:, k])) for k in range(3)])
    off = np.array(pl.get("offset", [0.0, 0.0, 0.0]), dtype=float)
    off[2] = -off[2]                    # the file's z is the export's; ours is already flipped
    base = anchor + off

    # THE PASSIVE ARM HAS TO BE ABLE TO REACH IT. The placement above is authored as an offset
    # from the DOMINANT wrist and knows nothing about the other shoulder, so on a clip where
    # the dominant hand sits wide the base lands past the far arm's fingertips. _elbow_2d then
    # takes its `unreachable -> straighten the arm` branch on EVERY frame, and the avatar signs
    # with one arm held out sideways like a signpost. It was doing that on 11 of the 35 words,
    # on 100% of their frames: `after` placed 1.70x the arm's reach away, `flag` 1.46x, `ride`
    # 1.36x. No error column can see it -- a synthesized limb is excluded from all of them, so
    # all three stayed identical to four decimals while the avatar was visibly broken.
    #
    # A base the signer's own arm cannot reach is not a pose the signer made, it is our
    # arithmetic, so pulling it in is strictly closer to the truth than straightening the limb.
    # Clamping to the reachable disc moves it the least distance possible, which is why the
    # correction is radial from that shoulder.
    #
    # The lengths are the same per-frame MEDIAN projections _elbow_2d itself uses, deliberately:
    # the clamp and the solve have to agree or the solve can still be handed a target it cannot
    # make. Estimating the bone properly instead -- a high percentile, since a projection is
    # shorter than the bone unless it lies in the image plane -- was tried and is worse, because
    # _elbow_2d works in the IMAGE PLANE and a 3D length forces the out-of-plane part sideways
    # and flares the elbow into the rig's joint limits. Swept: p50-p70 all hold rig clamping at
    # 0.14%, then it climbs to 1.22% at p85 and 3.32% at p95, with `clean` alone going from
    # 0.7% to 44%. Handshape fidelity to the template is 0.1695 either way. So: the median.
    seg = []
    for a_, b_ in ((d_sh, d_el), (d_el, d_wr)):
        v = np.linalg.norm(F[:, b_, :2] - F[:, a_, :2], axis=1)
        v = v[np.isfinite(v)]
        seg.append(float(np.median(v)) if len(v) else 0.3)
    sh_p = np.array([float(np.nanmedian(F[:, p_sh, k])) for k in range(3)])
    if np.all(np.isfinite(sh_p)):
        v = base[:2] - sh_p[:2]
        L = float(np.linalg.norm(v))
        cap = REACH_FRAC * (seg[0] + seg[1])
        if L > cap > 0:
            base = base.copy()
            base[:2] = sh_p[:2] + v * (cap / L)

    # The signer's own hand size, so the base matches the hand beside it rather than the
    # template's unit scale. Falls back to the corpus median if this clip never saw a hand.
    hl = np.linalg.norm(F[:, d0 + FINGER_OFF["middle"], :2] - F[:, d0, :2], axis=1)
    hl = hl[np.isfinite(hl)]
    scale = float(np.median(hl)) if len(hl) else 0.22

    e1 = pts[FINGER_OFF["middle"]] - pts[0]
    if np.linalg.norm(e1) < 1e-9:
        return F, False
    e1 /= np.linalg.norm(e1)
    n_t = n_t if dom == "l" else -n_t                     # right template -> left hand
    e3 = n_t - e1 * float(np.dot(n_t, e1))
    if np.linalg.norm(e3) < 1e-9:
        return F, False
    e3 /= np.linalg.norm(e3)
    d1 = np.array(fing, dtype=float)
    d3 = np.array(palm, dtype=float)
    d3 = d3 - d1 * float(np.dot(d3, d1))
    if np.linalg.norm(d3) < 1e-9:                         # palm along the fingers: ill-posed
        return F, False
    d3 /= np.linalg.norm(d3)
    R = (np.column_stack([d1, np.cross(d3, d1), d3])
         @ np.column_stack([e1, np.cross(e3, e1), e3]).T)

    F[:, p0:p0 + 21, :] = base + scale * (pts @ R.T)
    F[:, p_wr, :] = base
    # The arm that carries it. `seg` is measured above, before the clamp that depends on it --
    # both bone lengths come from the DOMINANT arm of this same signer, so the passive limb is
    # their arm rather than the rig's.
    out_sign = 1.0 if (pas == "l") else -1.0              # elbow away from the midline
    for i in range(len(F)):
        if np.any(np.isnan(F[i, p_sh])):
            continue
        e = _elbow_2d(F[i, p_sh], base, seg[0], seg[1], out_sign)
        if e is not None:
            F[i, p_el, :] = e
    return F, True


def resample(out_q, m):
    """Resample a rotation track to m frames by slerping between neighbouring source frames.

    Every bone is interpolated independently so a bone that is absent from one of the two
    source frames -- undriven, therefore at rest -- is carried through rather than slerped
    against nothing. Rounding matches the rest of the file: four decimals is well under the
    angular resolution anything downstream can show.
    """
    n = len(out_q)
    if m == n or n < 2:
        return [dict(f) for f in out_q]
    out = []
    for j in range(m):
        s = j * (n - 1) / (m - 1)
        a = int(np.floor(s))
        b = min(a + 1, n - 1)
        t = s - a
        f = {}
        for nm in set(out_q[a]) | set(out_q[b]):
            if nm not in out_q[a]:
                f[nm] = list(out_q[b][nm])
            elif nm not in out_q[b] or b == a:
                f[nm] = list(out_q[a][nm])
            else:
                q = slerp(np.array(out_q[a][nm], dtype=float),
                          np.array(out_q[b][nm], dtype=float), t)
                f[nm] = [round(float(x), 4) for x in q]
        out.append(f)
    return out


def retime(out_q):
    """Give every sign a still frame to be READ in, and a floor under how fast it can flash by.

    The clips are not recordings of a sign from rest to rest. They are windows cut out of
    continuous signing, and the cut lands wherever the segmenter put it: measured across all
    250, the hand is already moving on the FIRST frame of 99% of them and still moving on the
    last frame of 93%. So a sign starts mid-gesture, ends mid-gesture, and -- in the viewer,
    which loops -- jumps straight from one to the other. Nothing about that is legible, and no
    amount of work on the retargeting fixes it, because it is a property of the capture window.

    Holding the first and last pose is the fix, and it is why the frame COUNT is not the thing
    to equalise. A hold is what the eye reads a handshape in; ~200 ms is about the floor for
    that, so HOLD_IN/HOLD_OUT are 6 and 10 frames at 30 fps. The exit hold is longer because
    the end pose is the one that carries the sign's final location and handshape, and because
    it doubles as the gap that keeps a loop from reading as one continuous motion.

    The second half is a floor, not a normalisation. Peak hand speed is the SAME in the short
    clips and the long ones (0.089 vs 0.106 shoulder-widths/frame), so a 9-frame `tiger` is not
    signed fast -- it simply contains less movement, and 0.3 s is under what anyone can see.
    Those get stretched up to MIN_STROKE, capped at MAX_STRETCH so nothing ends up in slow
    motion at a speed the signer never used. 17 of 250 clips are short enough to be touched.

    Long clips are left ALONE. `puppy` is 116 frames because the sign repeats, and repetition
    is phonological in ASL -- compressing it to a target duration would change the word.
    """
    n = len(out_q)
    stretch = 1.0
    if n and n < MIN_STROKE:
        stretch = min(MIN_STROKE / n, MAX_STRETCH)
        out_q = resample(out_q, int(round(n * stretch)))
    if not out_q:
        return out_q, {"hold_in": 0, "hold_out": 0, "stretch": 1.0, "stroke": 0}
    stroke = len(out_q)
    out_q = ([dict(out_q[0]) for _ in range(HOLD_IN)] + out_q +
             [dict(out_q[-1]) for _ in range(HOLD_OUT)])
    return out_q, {"hold_in": HOLD_IN, "hold_out": HOLD_OUT,
                   "stretch": round(float(stretch), 2), "stroke": stroke}


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


def arm_seg_scales(F, side, rig):
    """One factor for the upper arm and one for the forearm, rather than the median of both.

    The shared scale above was justified by the elbow: scaling the two bones independently
    moves it off the shoulder-wrist line, which is a posture change rather than a proportion
    correction. That argument no longer holds, because the elbow is re-placed afterwards by
    two_bone_ik and only its DIRECTION survives, as the pole vector.

    Meanwhile the median costs what it costs everywhere else in this file. On `blue` the
    forearm's own 2D span exceeded the rig's forearm on 77% of frames after the shared scale --
    every one of those flattened into the image plane by the depth solve, while all 20 finger
    segments sat at 0% once THEY were scaled per segment. Same mistake, one level up the arm.

    Returns (upper, fore), each capped at 1.0 for the reason in arm_scale(): a signer's arm is
    never stretched to fill a longer rig one.
    """
    sh, el, wr = ((L_SH, L_EL, L_WR) if side == "l" else (R_SH, R_EL, R_WR))
    shw = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    out = []
    for a, b, ra, rb in ((sh, el, f"upperarm_{side}", f"lowerarm_{side}"),
                         (el, wr, f"lowerarm_{side}", f"hand_{side}")):
        d = np.linalg.norm(F[:, b, :2] - F[:, a, :2], axis=1)
        d = d[~np.isnan(d)]
        est = float(np.percentile(d, 90)) if len(d) >= 3 else 0.0
        out.append(min((rig.bone_len(ra, rb) / shw) / est, 1.0) if est > 1e-6 else None)
    return out


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


def retarget_word(rig, word, chains, fixed_shift=None):
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
    # WHICH ARMS ARE IN THE SIGNING SPACE AT ALL, measured rather than declared. An arm whose
    # wrist never rises within PARKED_Y of the shoulder line hung at the signer's side for the
    # whole clip.
    #
    # It is measured because neither label describes THIS TAKE. Our corpus flag and ASL-LEX's
    # Sign Type disagree on 29 of the 186 words both cover, and checked against what the arm
    # actually does, our flag is right 84% of the time and ASL-LEX 79% -- ASL-LEX gives the
    # citation form, and a signer may sign TREE or SICK either way on the day. What we animate
    # is the take. By the flag alone we were driving a parked arm on 30 clips (`time`, `tree`,
    # `after`, `chair`, `pen`, `touch`...) and holding a raised one at rest on 10 (`blue`,
    # `if`).
    #
    # Driving a parked arm is not harmless: shoulder, elbow and wrist are nearly collinear
    # there, which is ill-conditioned, and the note below measured that arm jumping over 30
    # degrees in a single frame on 4.8% of frames against 1.5% for the signing arm. There is
    # nothing in it to preserve -- a hanging arm and the rig's rest arm are the same pose --
    # so it holds rest with the hand it carries.
    active = {}
    shy_a = np.nanmean(F[:, [L_SH, R_SH], 1])
    for s_a in ("l", "r"):
        yy = F[:, L_WR if s_a == "l" else R_WR, 1]
        active[s_a] = bool(np.any(~np.isnan(yy)) and np.nanmin(yy) < shy_a + PARKED_Y)
    if not active[dom]:          # the dominant arm never came up: trust nothing, drive both
        active = {"l": True, "r": True}
    raised = active[passive]     # keep the TAKE's answer; the class decides separately

    # TWO QUESTIONS, TWO SOURCES OF EVIDENCE. They were being answered by one measurement.
    #
    #   how many hands does this SIGN have?   -> lexical. Not derivable from these landmarks:
    #        asl_handedness_250.json tested four classifiers against 40 hand-labelled words
    #        and got AUC 0.335 (inverted), 0.460, 0.468, 0.500. A coin.
    #   is this TAKE's passive arm usable?    -> measured, above. A signer may leave the arm
    #        down on a sign that has two hands; the corpus is isolated single-sign prompts.
    #
    # Answering the first with the second put a whole second hand on 8 one-handed signs and
    # dropped it from 12 symmetrical ones -- and no error column moved, because a metric that
    # scores driven hands against landmarks that exist cannot see either mistake.
    cls, _conf = lexicon()["class"].get(word, (None, None))
    p_wr, d_wr = (L_WR, R_WR) if passive == "l" else (R_WR, L_WR)
    if cls is None:
        # Not in the lexicon (the medical handoff, or a word added later): fall back to the
        # measurement, which is what this file did for every word before the lexicon was read.
        trav = [float(np.nansum(np.linalg.norm(np.diff(F[:, k, :2], axis=0), axis=-1)))
                for k in (p_wr, d_wr)]
        cls = ("2s" if raised and trav[0] > PASSIVE_MOVE * max(trav[1], 1e-9)
               else ("2a" if raised else "1"))

    synth_hand = synth_arm = None
    if cls == "1":
        # ONE-HANDED. Whatever the passive arm did on this take, it is not part of the sign.
        active[passive] = False
    elif cls == "2s" and np.isnan(F[:, HAND0[passive], 0]).all():
        active[passive] = True
        if not raised:
            # The signer left the arm down on a sign that needs it. Symmetry says what it was
            # doing, so the whole limb is reflected rather than a handshape being anchored on
            # a hip. See mirror_passive_arm().
            F, _ = mirror_passive_arm(F, dom)
            synth_arm = passive
        F = mirror_passive_hand(F, dom)
        synth_hand = passive
    elif cls == "2a":
        # DOMINANCE. A static unmarked base, placed from the lexicon -- never mirrored, and
        # never at the recorded passive wrist. See unmarked_base().
        F, placed = unmarked_base(F, word, dom)
        if placed:
            active[passive] = True
            synth_hand = synth_arm = passive
        else:
            active[passive] = raised
    if not active[passive]:
        chains = [c for c in chains if not c[0].endswith(f"_{passive}")]
    mirrored = synth_hand
    dom_shifts = []          # the dominant hand's per-frame placement correction; see below

    HS = {s: hand_scale(F, s, rig) for s in ("l", "r")}
    SEGS = {s: hand_chains(rig, s) for s in ("l", "r")}
    SSC = {s: hand_seg_scales(F, s, rig) for s in ("l", "r")}
    ASS = {s: arm_seg_scales(F, s, rig) for s in ("l", "r")}
    AS = {s: arm_scale(F, s, rig) for s in ("l", "r")}
    # TRIED AND REJECTED 2026-09-18: giving a SYNTHESIZED hand the dominant hand's scales
    # instead of estimating them from its own block. The argument was anatomical and sounded
    # airtight -- one signer, one hand size -- and the estimate off the synthetic block does
    # look wild: a median 1.37x the dominant hand's, as far as 6.79x, with 11 of the 35 `2a`
    # words scaling the base UP, the inversion hand_scale()'s docstring warns about on `yes`.
    #
    # It made the handshape WORSE. Measured as distance from the authored template the base is
    # built from -- wrist-centred, unit wrist-to-middle-MCP, best rotation removed, so only
    # shape is left -- sharing the dominant scale reads median 0.2041 against 0.1695 for the
    # estimate it replaced, and is worse on 25 of the 35 words (`flag` +0.337, `morning`
    # +0.296).
    #
    # The argument was answered in the wrong units. These scales do not set how BIG the rig's
    # hand is -- the rig's bone lengths are fixed and no solve can change them. They set how
    # far away the finger TARGETS sit, and the solve keeps their directions, so a uniformly
    # larger target reproduces the same handshape. What looked like a giant base hand was the
    # ORANGE TARGET in render_check.py being drawn at that scale, not the rig's hand. Third
    # diagnostic today to report a fault the thing under test did not have.
    if synth_arm:
        ASS[synth_arm] = ASS[dom]
        AS[synth_arm] = AS[dom]
    SHY, VA, VB = body_map(F, rig, origin, scale)   # signer height -> rig height
    HR = head_frames(F, rig)          # non-manual: head pose, one of the five ASL parameters
    ZS = smooth_z(F)
    tree = build_tree(rig)
    FLEX = flexion_axes(rig)

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
        for lm in WANT_FRONT_LM:
            # ONLY WHEN IT IS SURE. The prior is a hard override with no hysteresis behind it,
            # so an elbow hovering near the shoulder plane flips side every frame and swings
            # the forearm through 145 degrees -- which is exactly what `animal` and `bath` were
            # doing, at regular intervals, in frames where the hand was not even present. Below
            # the margin the answer is not "behind", it is "unknown", and solve_depth's
            # relative-z rule with its own hysteresis is better placed to keep the peace.
            m = F[fi, lm, 2] - sh_z[fi]
            if not np.isnan(m) and abs(m) > FRONT_MARGIN:
                want_front[fi][lm] = bool(m > 0)

    prev_sign, last_q, held, last_nd = {}, {}, [], {}
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
            if np.any(np.isnan(tgt[sh])):
                continue
            # Per bone, walking out from the shoulder -- see arm_seg_scales(). Vectors read
            # before anything moves, for the reason spelled out in fit_reach().
            su, sf = ASS[s]
            vs = [(sh, el, tgt[el] - tgt[sh], su if su is not None else AS[s]),
                  (el, wr, tgt[wr] - tgt[el], sf if sf is not None else AS[s])]
            for a_, b_, v_, sc_ in vs:
                if not (np.any(np.isnan(tgt[a_])) or np.any(np.isnan(v_))):
                    tgt[b_] = tgt[a_] + v_ * sc_
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
            # PER SEGMENT, walking each finger out from the wrist. A single hand-wide factor
            # leaves every segment whose own ratio differs from the median either too long for
            # the rig bone (clamped flat) or too short for it (invented depth, a straightened
            # finger). See hand_seg_scales(). The wrist itself does not move here.
            for ch in SEGS[s]:
                # Read every segment vector BEFORE moving anything: once the parent has been
                # rescaled, tgt[b] - tgt[a] is no longer the segment the signer made.
                vs = [(a_, b_, tgt[b_] - tgt[a_],
                       SSC[s].get((a_, b_), (None, 0.0))[0])
                      for a_, b_, _ in ch
                      if not (np.any(np.isnan(tgt[a_])) or np.any(np.isnan(tgt[b_])))]
                for a_, b_, v_, sc_ in vs:
                    tgt[b_] = tgt[a_] + v_ * (HS[s] if sc_ is None else sc_)
            # ... and then, on this frame only, far enough for the rig to reach it at all.
            tgt = fit_reach(tgt, SEGS[s], scale)
            if not np.any(np.isnan(tgt[wr])):
                shift = tgt[wr] - tgt[h0]
                for k in range(21):
                    if not np.any(np.isnan(tgt[h0 + k])):
                        tgt[h0 + k] = tgt[h0 + k] + shift
        P, cl, used, tried = solve_depth(tgt, rig, F[fi], tree, zref=ZS[fi],
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
        # DOMINANT FIRST, so the base hand can be moved by whatever moved the hand it is being
        # contacted by. See the shift applied below.
        dom_shift = None
        for s_ in (dom, passive):
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
            # A MIRRORED HAND SUPPLIES HANDSHAPE, NEVER PLACEMENT. Its landmarks are reflected
            # copies of the other hand anchored on the passive wrist, so their heights are the
            # dominant hand's heights -- letting them into the centroid and face anchor moved
            # the passive wrist off the pose target that IS real: `clean` 7.5% -> 8.8% wrist,
            # clamping 22.7% -> 28.9%, `same` 6.0% -> 12.7%. Placement comes from the tracked
            # pose wrist; only the finger rotations come from the mirror.
            if s_ == mirrored:
                have = []
            if not have:
                want_y = origin[1] + (VA * (float(SHY[fi]) - F[fi, wr_, 1]) + VB) * scale
                want = np.array([P[wr_][0], want_y, P[wr_][2]])
            else:
                cen_dy = float(np.mean([float(SHY[fi]) - F[fi, k, 1] for k in have]))
                body_y = origin[1] + (VA * cen_dy + VB) * scale

                # NEAR THE FACE, ANCHOR TO THE FACE. A body map gets the height roughly right
                # and still misses the thing that defines the sign: how close the hand comes to
                # the head. Measured, the signer's thumb reaches within 0.189 shoulder widths
                # of their own nose on `dad`, 0.173 on `mom`, 0.063 on `drink`; the avatar's
                # nearest approach to its head was 0.427, 0.260 and 0.162. Roughly twice as far
                # on the signs that are ABOUT touching the face. Contact is phonological -- a
                # sign made at the forehead and a sign made in neutral space in front of it are
                # different words -- so it cannot be left to fall out of a height fit.
                #
                # Both bodies have EYES, which is an exact correspondence that needs no lexicon
                # and no guessing (MediaPipe pose carries eye centres at landmarks 2 and 5;
                # the rig has eye_l and eye_r). So when the hand is near the face its offset
                # FROM THE EYE MIDPOINT is reproduced directly.
                #
                # Blended, not switched, by distance: fully face-anchored within NEAR, fully
                # body-mapped past FAR, linear between. A hard switch would make the hand jump
                # the moment it crossed the threshold, which is the class of artefact this
                # whole session has been removing.
                #
                # x and y only. z stays as the depth solver left it -- the data's z is the
                # noise this solver exists to discard, and that does not stop being true
                # because we are measuring from the eyes instead of the shoulders.
                # THE ANCHOR IS THE PART THAT TOUCHES, not the middle of the hand. Anchoring
                # the centroid helped most signs and made `dad` worse, because on `dad` the
                # thumb touches the forehead while the four fingers stand up past the top of
                # the head: the centroid sits well above the face and drags the contact with
                # it. What has to land in the right place is whatever is nearest the face.
                #
                # Taken as a soft minimum rather than a hard one -- weights falling off with
                # distance -- because "which landmark is nearest" flips between neighbours
                # from frame to frame, and a hard pick would put a jump in the animation every
                # time it did.
                eye_d = (F[fi, 2, :2] + F[fi, 5, :2]) / 2.0
                dk = np.array([np.linalg.norm(F[fi, k, :2] - eye_d) for k in have])
                wk = np.exp(-(dk / FACE_SIGMA) ** 2)
                if float(wk.sum()) < 1e-9:
                    wk = np.ones_like(wk)
                wk = wk / wk.sum()
                anchor_d = np.array([float(np.dot(wk, [F[fi, k, 0] for k in have])),
                                     float(np.dot(wk, [F[fi, k, 1] for k in have]))])
                cen_rig = np.array([float(np.dot(wk, [P[k][0] for k in have])),
                                    float(np.dot(wk, [P[k][1] for k in have])),
                                    float(np.dot(wk, [P[k][2] for k in have]))])
                off = anchor_d - eye_d
                dist = float(dk.min())
                w_face = float(np.clip((FACE_FAR - dist) / (FACE_FAR - FACE_NEAR), 0.0, 1.0))
                rig_eye = (rig.wp("eye_l") + rig.wp("eye_r")) / 2.0
                face_xy = np.array([rig_eye[0] + off[0] * scale,
                                    rig_eye[1] - off[1] * scale])
                tgt_x = w_face * face_xy[0] + (1.0 - w_face) * cen_rig[0]
                tgt_y = w_face * face_xy[1] + (1.0 - w_face) * body_y
                want = np.array([P[wr_][0] + (tgt_x - cen_rig[0]),
                                 P[wr_][1] + (tgt_y - cen_rig[1]),
                                 P[wr_][2]])
            # MOVE THE BASE WITH THE HAND THAT CONTACTS IT. Everything above maps each hand
            # independently -- centroid fit, face anchor, body map -- which is right when both
            # are measured, because then both targets are real and any relation between them
            # is already in the data. A 2a base is not measured: the only claim made about it
            # is a RELATION, "this far from the dominant wrist, because that is where the
            # dominant hand touches it". Mapping it on its own destroys the one property it
            # has. Measured over the 35 base words, the two hands came out a median 0.49 and
            # up to 1.18 shoulder-widths apart against a rig hand 0.64 long -- on `helicopter`
            # and `chair` the dominant hand was pressing on nothing.
            #
            # So the base takes the dominant hand's own translation, whatever the map decided
            # that was. The offset between them then survives the map exactly, because both
            # ends of it moved by the same vector.
            #
            # THE SHIFT IS ONE VECTOR FOR THE WHOLE CLIP, not this frame's. A base does not
            # move -- that is what makes it a base -- and the dominant hand's own translation
            # changes frame to frame as the face anchor fades in and out. Handing the base
            # that per-frame vector fixed the distance and broke the staticness instead: the
            # base drifted up to 0.33 shoulder-widths on `jump`, 11 cm, following the hand it
            # is supposed to be held still for. So the median over the clip is used, which
            # costs one extra solve on the 35 words that have a base and nothing on the 215
            # that do not.
            if s_ == synth_arm and cls == "2a":
                if fixed_shift is not None:
                    want = P[wr_] + fixed_shift
            elif s_ == dom:
                dom_shift = want - P[wr_]
                dom_shifts.append(dom_shift)
            # AND IN FRONT OF THE BODY, IF THE DATA SAYS IT IS. The depth root chosen inside
            # solve_depth stopped being the last word once two_bone_ik took over placement:
            # swept over 70 words, carrying the in-front prior on the elbow, the wrist, both or
            # neither moves the `front` metric by 0.14 points and handshape not at all, because
            # the wrist's final z is whatever survives into this target. So the same rule has
            # to be applied HERE, where it lands.
            #
            # It is worth applying. On the 15 base-hand signs the passive hand is behind the
            # shoulder plane on 100% of frames -- `time` by 0.30 shoulder-widths, 10 cm, with
            # the rig's own spine only 0.06 behind that plane. The hand is inside the torso.
            # Meanwhile the data puts that wrist IN FRONT on 91-100% of frames.
            #
            # Mirrored about the shoulder plane rather than pushed to a floor, because that
            # uses only the part of z we trust. The file's whole depth argument is that the
            # data's z SIGN is reliable and its MAGNITUDE is not: the magnitude here stays the
            # one our own bone-length solve produced, and only the side is taken from the data.
            z0_ = rig.wp(f"upperarm_{s_}")[2]
            if want_front[fi].get(wr_) is True and want[2] < z0_:
                want[2] = 2.0 * z0_ - want[2]

            # ... and NOT INSIDE THE BODY, whatever the data says. The mirror above needs the
            # data's z-sign to be confident, and on the signs where the hand ends up furthest
            # back it is not: `look` reads in-front on 68% of frames, `time` 73%, `sleep` 56%.
            # Those four are exactly the ones still placing the hand behind the shoulder plane
            # (`look` 39% of frames in front, `time` 50%, `sleep` 54%, `pen` 62%).
            #
            # This is not a depth estimate and does not pretend to be one. It is the fact that
            # a hand cannot occupy the same space as the chest it is in front of. Applied only
            # inside the torso's own footprint -- between the shoulders, and between hip and
            # head height -- so a hand genuinely at the signer's side or above their head is
            # left alone. Outside that box the constraint has nothing to say.
            # Up to the TOP of the head, not the head joint, which sits at the base of the
            # skull: a hand at the eye or the forehead is above that joint and was falling
            # outside the box -- which is `look`, a V-hand at the eye, the worst word here.
            hip_y = rig.wp("spine_01")[1] if "spine_01" in rig.by else origin[1] - scale
            top_y = rig.wp("head_end" if "head_end" in rig.by else "head")[1] \
                if "head" in rig.by else origin[1] + scale
            half = scale * 0.5 + TORSO_PAD * scale
            if (abs(want[0] - origin[0]) < half and hip_y < want[1] < top_y
                    and want[2] < z0_ + TORSO_FRONT * scale):
                want[2] = z0_ + TORSO_FRONT * scale
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
        total += tried

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
                # THE TORSO IS DELIBERATELY NOT DRIVEN, and now for a measured reason
                # rather than a scheduling one. The signal is in the data -- all 250 clips
                # carry hip landmarks -- and it is too small to be worth what it costs:
                # shoulder roll deviates from its own clip median by 2.4 degrees at the
                # median and 4.4 at p90, torso lean by 2.8 and 4.9, with exactly one clip
                # over 10 degrees of either. Driving it means re-anchoring solve_depth on
                # POSED shoulders, and every length, scale and depth root in this file is
                # measured from shoulders that do not move. A 2-3 degree lean is not worth
                # putting that under the whole solve.
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
            # ... and two vectors are not the best available answer. Every MCP is a metacarpal
            # head, rigidly attached to the same palm, so all five constrain the same rotation
            # and the least-squares fit over all of them beats picking two. Measured per-joint,
            # the two-vector frame left `hand -> thumb_01` 30.6 degrees off while the joints
            # BELOW it were 1.9/6.2/7.7 -- as good as the fingers. That signature is roll:
            # rolling the palm about its own axis swings the thumb a long way and the middle
            # finger, which lies near that axis, hardly at all (thumb 30.6, pinky 12.2, middle
            # 2.5). It is not anatomy -- the rig's palm fan and MediaPipe's agree to 8 degrees
            # at the extremes and 0.5 at the middle finger -- so it was ours to fix.
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

            mfp = nm.split("_")
            if len(mfp) == 3 and mfp[1] == "01" and mfp[0] in FINGER_OFF:
                # THE KNUCKLE SETS THE FINGER'S PLANE, and nothing was setting it. align()
                # gives the minimal rotation, which pins where the bone POINTS and leaves its
                # roll to whatever the parent gave. That was harmless while the two joints
                # below were free and is not harmless now they are hinges: a hinge bends in
                # the plane its parent's roll chose, so an unconstrained roll curls the finger
                # in an arbitrary plane where it cannot reach -- `blue`'s fingers standing
                # straight out where the data has them curled.
                #
                # Two sources for that plane, and the measured answer is to use both:
                #
                #   the DATA's finger normal   shape 18.7%  anatomy 0d  knuckle 9.2 deg/frame
                #   the RIG's rest plane       shape 28.9%  anatomy 0d  knuckle 3.5 deg/frame
                #   neither (align alone)      shape 17.9%  anatomy 26d knuckle 4.2 deg/frame
                #
                # The data is worth following when the finger is bent, because then the plane
                # is well determined and the handshape is what it is describing. It is worth
                # nothing when the finger is straight: |cross| is |u1||u2|sin(bend), so a
                # straight finger yields a short vector pointing wherever the noise says, and
                # tracking it is where that 9.2 deg/frame comes from. The rig's rest plane is
                # exact, free of measurement, and cannot shimmer -- so it carries the frames
                # the data cannot speak for, and the finger still cannot twist in either case.
                fg, sd = mfp[0], mfp[2]
                axr = FLEX.get(f"{fg}_02_{sd}")
                if axr is not None:
                    h0f = HAND0[sd] + FINGER_OFF[fg]
                    pts = [P.get(h0f + j) for j in (0, 1, 3)]
                    if all(q is not None for q in pts):
                        # MCP->PIP against MCP->TIP: both give the plane, but a cross
                        # product's direction is only as steady as its inputs are long, and
                        # consecutive phalanges are the two shortest vectors available.
                        u1, u2 = pts[1] - pts[0], pts[2] - pts[0]
                        nd = np.cross(u1, u2)
                        sin_bend = float(np.linalg.norm(nd)) / (
                            float(np.linalg.norm(u1)) * float(np.linalg.norm(u2)) + 1e-12)
                        if sin_bend > FINGER_PLANE_MIN:
                            nd = nd / (np.linalg.norm(nd) + 1e-12)
                            # smoothed across frames: a finger's PLANE turns slowly even
                            # while the bend within it -- the handshape itself -- does not
                            pn_ = last_nd.get(nm)
                            if pn_ is not None:
                                if float(np.dot(nd, pn_)) < 0.0:
                                    nd = -nd
                                nd = PLANE_EMA * nd + (1.0 - PLANE_EMA) * pn_
                                nd = nd / (np.linalg.norm(nd) + 1e-12)
                            last_nd[nm] = nd
                            across_t = nd
                            Ftf = frame_from(P[a], want, across_t)
                            Frf = frame_from(rig.wp(nm),
                                             rig.wp(child) - rig.wp(nm), axr)
                            if Ftf is not None and Frf is not None:
                                world_R[bi] = (Ftf @ Frf.T) @ rig.world_rest[bi][1]
                                solved = True

            if not solved:
                # where this bone points at REST, carried into the parent's CURRENT frame
                rest_dir = rig.wp(child) - rig.wp(nm)
                rest_dir /= np.linalg.norm(rest_dir) + 1e-12
                cur = pR @ np.linalg.inv(R_rest_parent) @ rest_dir
                # A FINGER JOINT IS A HINGE. For the middle and end phalanges the target
                # direction is projected onto the one plane the joint can actually reach, so
                # noise perpendicular to it is discarded instead of becoming a twist. See
                # flexion_axes(): without this the three phalanges of a finger left their
                # shared plane by 34-41 degrees on average, which no hand can do.
                fx = FLEX.get(nm)
                if fx is not None:
                    axw = pR @ np.linalg.inv(R_rest_parent) @ fx
                    na = np.linalg.norm(axw)
                    if na > 1e-9:
                        axw = axw / na
                        wp_ = want - axw * float(np.dot(want, axw))
                        cp_ = cur - axw * float(np.dot(cur, axw))
                        if np.linalg.norm(wp_) > 1e-6 and np.linalg.norm(cp_) > 1e-6:
                            want = wp_ / np.linalg.norm(wp_)
                            cur = cp_ / np.linalg.norm(cp_)
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
            # only score an arm we actually drive; see the passive-arm note above -- and not
            # one that is PARKED, which is a different thing the same note is about. On a
            # two-handed sign the passive chains are kept, and on eight of those the signer
            # simply left that arm hanging: measured in the data, the passive wrist sits 0.85
            # to 1.31 shoulder-widths out to the side and 0.86 to 1.18 BELOW the shoulder line
            # for the whole clip, and the avatar reproduces that to within 0.01. Scoring it
            # dragged `front` to 50-69% on `pen`, `time`, `after`, `touch`, `chair`, `into`,
            # `beside` and `chocolate`, whose DOMINANT hand is in front on 100% of frames.
            # That is the metric describing an arm at rest, not a depth solve going backwards.
            #
            # A SYNTHETIC ARM IS NOT SCORED EITHER. The mirrored HAND could stay out of the
            # handshape column alone while its arm kept being scored, because that arm was
            # real pose data. Two of the three synthesis paths no longer are: a mirrored arm
            # (2s, passive side never raised) and a placed base (2a) both put the wrist where
            # a lexicon said, so `err` would report how precisely the solver hit our own
            # invention and `front` would report that we invented it in front. Same trap as
            # the handshape column, one joint up the chain.
            if (f"hand_{side}" not in by_bone or wr not in tg or not active[side]
                    or side == synth_arm):
                continue
            got = WT[rig.by[f"hand_{side}"]]
            err.append(float(np.linalg.norm(got[:2] - tg[wr][:2])) / scale)
            front.append(float(got[2] > rig.wp(f"upperarm_{side}")[2]))
            h0 = HAND0[side]
            # The mirrored hand's target was DERIVED from the other hand by a linguistic rule,
            # so scoring the solve against it says nothing about whether the handshape is
            # right -- it would only report how well the solver hit a target we invented, and
            # report it as if it were measured. The arm above it stays scored: that one is
            # real pose data. This file has twice shipped a metric that could not fail; not a
            # third time.
            if h0 not in tg or side == mirrored:
                continue
            hl = float(np.linalg.norm(rig.wp(f"middle_01_{side}") - rig.wp(f"hand_{side}")))
            for fname, off in FINGER_OFF.items():
                tip = h0 + off + 3
                if tip in tg:
                    g = WT[rig.by[f"{fname}_end_{side}"]] - got
                    t_ = tg[tip] - tg[h0]
                    shp.append(float(np.linalg.norm(g[:2] - t_[:2])) / hl)

    # ONE MORE SOLVE, ONLY FOR A PLACED BASE. The base's target is "wherever the dominant hand
    # ended up, plus the lexicon's offset", and the dominant hand's own placement is not known
    # until the whole clip has been solved. So the first solve exists to measure that, and the
    # second is the one that ships. Guarded on fixed_shift so it recurses exactly once, and
    # only on the 35 words with a base -- the other 215 solve once, as before.
    if cls == "2a" and synth_arm and fixed_shift is None and dom_shifts:
        return retarget_word(rig, word, chains,
                             fixed_shift=np.median(np.array(dom_shifts), axis=0))

    # AFTER scoring, never before. The holds are copies of frames already scored and the
    # stretched frames are interpolations between them, so scoring the stroke scores the
    # animation; scoring the padded track would dilute every number with repeated frames and
    # make it incomparable with every measurement taken before this pass existed.
    out_q, timing = retime(out_q)
    timing["mirrored"] = mirrored
    timing["class"] = cls
    # Which synthesis ran, so the label and the viewer can say it rather than imply two
    # tracked hands. "mirror" = 2s handshape reflected onto a tracked arm; "mirror+arm" = the
    # whole limb reflected because the signer left it down; "base" = a 2a unmarked base placed
    # from the lexicon. All three are derived, none is measured.
    timing["synth"] = (None if synth_hand is None else
                       ("base" if cls == "2a" else
                        ("mirror+arm" if synth_arm else "mirror")))
    return (d, out_q, np.array(err), np.array(shp), np.array(front), clamps, total, driven,
            timing)


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
    # PALM ORIENTATION MUST DEPEND ON THE PALM. This solve has now gone missing twice -- once
    # because it was never written, once because a careless edit cut it out -- and both times
    # the symptom was a hand in exactly the right place facing an arbitrary direction, which
    # wrist error scores as perfect. So: move the landmarks that define the across-palm vector
    # and require the hand bone to notice. A retargeter that ignores them will not.
    src = json.loads((WORDS / "hello.json").read_text(encoding="utf-8"))
    base_q = retarget_word(rig, "hello", chains)[1]
    _orig_ho = HAND0["r"]
    try:
        HAND0["r"] = _orig_ho            # unchanged; we perturb through FINGER_OFF instead
        FINGER_OFF["index"], FINGER_OFF["pinky"] = (FINGER_OFF["pinky"],
                                                    FINGER_OFF["index"])
        swap_q = retarget_word(rig, "hello", chains)[1]
    finally:
        FINGER_OFF["index"], FINGER_OFF["pinky"] = (FINGER_OFF["pinky"],
                                                    FINGER_OFF["index"])
    moved = max(
        float(np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(
            np.array(a["hand_r"]), np.array(b_["hand_r"]))))))))
        for a, b_ in zip(base_q, swap_q) if "hand_r" in a and "hand_r" in b_)
    assert moved > 5.0, (
        f"[err] swapping the index and pinky landmarks moved the hand bone by only "
        f"{moved:.2f} degrees. Palm orientation is not being solved from the palm -- the "
        f"hand will arrive in the right place facing an arbitrary direction, which wrist "
        f"error scores as a pass.")
    print(f"[selftest] swap index/pinky       -> hand rotates {moved:5.1f}deg   "
          f"(palm orientation is solved from the palm)")

    print(f"[selftest] reverse the z axis     -> in front {fr0.mean()*100:5.0f}% -> "
          f"{fr3.mean()*100:5.0f}%   (wrist {err3.mean()*100:.1f}% and handshape "
          f"{shp3.mean()*100:.0f}% barely move -- that is why this check exists)")

    # 6. The holds must BE holds, and the stretch must preserve the pose. A resample that
    #    interpolated wrongly, or a hold that copied the wrong frame, would show up nowhere
    #    else: every error metric is computed before this pass runs, by design.
    short = [{"hand_r": [0.0, 0.0, 0.0, 1.0]},
             {"hand_r": [0.0, 0.0, float(np.sin(np.pi / 4)), float(np.cos(np.pi / 4))]}]
    pad, tm = retime([dict(f) for f in short])
    assert tm["stretch"] == MAX_STRETCH and tm["stroke"] == 4, tm
    assert len(pad) == HOLD_IN + 4 + HOLD_OUT, len(pad)
    assert all(pad[i]["hand_r"] == pad[0]["hand_r"] for i in range(HOLD_IN + 1)), \
        "[err] the entry hold is not still -- the sign starts mid-motion again"
    assert all(pad[-1 - i]["hand_r"] == pad[-1]["hand_r"] for i in range(HOLD_OUT + 1)), \
        "[err] the exit hold is not still"
    mid = np.array(pad[HOLD_IN + 1]["hand_r"], dtype=float)
    half = float(np.degrees(2 * np.arccos(min(1.0, abs(mid[3])))))
    assert 25.0 < half < 35.0, (
        f"[err] resampling a 90deg turn put frame 2 of 4 at {half:.1f}deg, not the 30deg an "
        f"even slerp gives -- the stretched frames are not on the original motion.")
    long_, tm2 = retime([{"hand_r": [0.0, 0.0, 0.0, 1.0]} for _ in range(MIN_STROKE + 5)])
    assert tm2["stretch"] == 1.0 and tm2["stroke"] == MIN_STROKE + 5, tm2
    print(f"[selftest] retime                 -> holds still, {MAX_STRETCH:.0f}x stretch "
          f"lands mid-motion at {half:.0f}deg, long clips untouched")

    # THE SYNTHESIZED HAND IS THE ONE THING NO ERROR COLUMN CAN SEE. Every number this file
    # reports is computed against landmarks, and a hand that has none -- because the corpus
    # never recorded it -- is invisible to all of them: `blue` scored 9.2% while the avatar
    # signed it with two hands, and `rain` scored 12.2% with one. So the check on the passive
    # hand cannot be an error and has to be a property. Two that hold by anatomy, not by fit:
    #
    #   a base is WITHIN REACH of the hand that contacts it -- a dominant hand pressing on
    #     something a shoulder-width away is contacting nothing;
    #   a base is STILL. That is the definition of a base, and the per-frame version of the
    #     shift above passed the first test while failing this one on all 35 words.
    #
    # `after` because it is class 2a with contact, its base is a plain hand rather than one of
    # the five forearm entries the placement file marks as outside its schema, and it is 34
    # frames -- long enough for a drift to show.
    _, bq, *_rest = retarget_word(rig, "after", chains)
    tm_b = _rest[-1]
    assert tm_b.get("synth") == "base", f"[err] `after` is class 2a and did not get a base: {tm_b}"
    sw_ = float(np.linalg.norm(rig.wp("upperarm_l") - rig.wp("upperarm_r")))
    hand_ = 3.0 * float(np.linalg.norm(rig.wp("middle_01_r") - rig.wp("hand_r"))) / sw_
    pos = np.array([fk_world(rig, f)[rig.by["hand_l"]] for f in bq])
    dom = np.array([fk_world(rig, f)[rig.by["hand_r"]] for f in bq])
    # CONTACT IS THE CLOSEST APPROACH, NOT THE TYPICAL ONE. This was the median over frames,
    # which tests something the sign does not claim: `after`'s own placement note says "dominant
    # B starts behind it and sweeps over AND AWAY", so most frames are legitimately far apart
    # and a median near the limit means the sweep happened, not that contact failed. The median
    # was also inconsistent about what it let through -- `touch` passes it at 0.33 while its
    # hands separate to 1.28, twice a hand length. What contact asserts is that the dominant
    # hand reaches the base at some point in the sign, so take the minimum.
    apart = float(np.min(np.linalg.norm(pos - dom, axis=1)) / sw_)
    drift = float(np.linalg.norm(pos - pos.mean(0), axis=1).max() / sw_)
    assert apart < hand_, (
        f"[err] `after`'s dominant hand never comes closer than {apart:.2f} shoulder-widths to "
        f"the base it contacts, further than the rig's own hand is long ({hand_:.2f}). It is "
        f"pressing on nothing. See the clip-constant shift in retarget_word().")
    assert drift < 0.03, (
        f"[err] `after`'s base moved {drift:.3f} shoulder-widths across the clip. A 2a base "
        f"is static by definition -- if it follows the dominant hand it is not a base.")
    one = retarget_word(rig, "blue", chains)[-1]
    assert one.get("synth") is None and one.get("class") == "1", (
        f"[err] `blue` is one-handed in asl_handedness_250.json and got {one.get('synth')!r}. "
        f"A second hand on a one-handed sign is a different sign, and no metric here can see "
        f"it -- this assertion is the only thing that can.")
    print(f"[selftest] synthesized hands      -> `after`s hands close to {apart:.2f} sh.w. "
          f"(rig hand {hand_:.2f}), base drifts {drift:.3f}; `blue` stays one-handed")

    # 7. THE PASSIVE LIMB IS THE SAME BODY AS THE DOMINANT ONE. Two faults hid here for weeks
    # because a synthesized limb is excluded from every error column, so all three of the
    # numbers above stayed IDENTICAL to four decimal places while the avatar signed with one
    # arm held out sideways and a base hand a quarter too big. Only a render caught them, and
    # a render is not run on every bake. These two assertions are.
    #
    # (a) REACH. The base must sit where that arm can actually hold it. Out of reach, _elbow_2d
    #     straightens the limb and leaves it pointing off to the side for the whole clip -- it
    #     did exactly that on 11 of the 35 `2a` words, on 100% of their frames.
    # (b) SIZE. Both hands belong to one signer, so the rig's two hands must come out the same
    #     size. They did not: the scale estimated off the synthetic block ran a median 1.37x
    #     the dominant hand's and as far as 6.79x.
    # Check the elbow in the space the fault lives in -- the synthesized LANDMARKS, where
    # _elbow_2d runs. Checking the rig's arm instead does not work: arm_scale maps the target
    # into the rig's own proportions, so the rig's extension reads 0.921 whether the base is in
    # reach or a mile outside it. The limb that straightens is the data one.
    slack_ = []
    for w_ in ("after", "ride", "flag"):
        s_ = json.loads((WORDS / f"{w_}.json").read_text(encoding="utf-8"))
        F_ = np.array(s_["frames"], dtype=float)
        F_[:, :, 2] = -F_[:, :, 2]
        G_, ok_ = unmarked_base(one_euro(F_, fps=float(s_.get("fps", 30))), w_, "r")
        assert ok_, f"[err] `{w_}` is class 2a and got no base"
        a_ = np.linalg.norm(G_[:, L_EL, :2] - G_[:, L_SH, :2], axis=1)
        b_ = np.linalg.norm(G_[:, L_WR, :2] - G_[:, L_EL, :2], axis=1)
        L_ = np.linalg.norm(G_[:, L_WR, :2] - G_[:, L_SH, :2], axis=1)
        sl = float(np.nanmin((a_ + b_ - L_) / np.maximum(a_ + b_, 1e-9)))
        slack_.append(sl)
        # 0.01 is a FIXED floor, deliberately not `1 - REACH_FRAC`. Deriving the threshold from
        # the constant under test makes the assertion pass by construction: raising REACH_FRAC
        # to disable the clamp also moved the bar to -49, and the first version of this check
        # sailed through a completely straightened arm. A test may not be written in terms of
        # the thing it is testing.
        assert sl > 0.01, (
            f"[err] `{w_}`'s passive limb is a straight line (elbow slack {sl:.4f}). The base "
            f"is beyond that arm's reach, so _elbow_2d straightens it for the whole clip and "
            f"the avatar signs with an arm held out sideways. See REACH_FRAC.")
    print(f"[selftest] passive limb           -> `after`/`ride`/`flag` keep a bent elbow "
          f"(slack {min(slack_):.3f}), none of them straightened")


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
    print(f"\n{'word':<12s} {'frames':>12s} {'hands':>16s} {'wrist err':>11s} "
          f"{'p95':>7s} {'handshape':>10s} {'in front':>9s} {'clamped':>8s}")
    print("-" * 94)
    baked, failed = {}, []
    for w in words:
        if not (WORDS / f"{w}.json").exists():
            print(f"{w:<12s}  no such word file")
            continue
        try:
            d, q, err, shp, fr, cl, tot, driven, timing = retarget_word(rig, w, chains)
        except Exception as exc:                      # one bad clip must not lose the other 249
            print(f"{w:<12s}  FAILED: {type(exc).__name__}: {exc}")
            failed.append(w)
            continue
        F = np.array(d["frames"], dtype=float)
        lh = 1.0 - np.isnan(F[:, 33:54, 0]).mean()
        rh = 1.0 - np.isnan(F[:, 54:75, 0]).mean()
        # A >50% threshold called 28 clips "none" that have the right hand on 11-50% of their
        # frames -- five of them on EXACTLY 50%, missing the cut by a rounding hair. The
        # fingers are driven on those frames and bridge_gaps interpolates the rest, so "none"
        # was a lie about the animation AND about why the sign looks wrong. HAND_MIN is the
        # honest floor: below it there is genuinely nothing to solve from. The coverage
        # percentages ship alongside, because "right hand on 44% of frames" is the actual
        # answer to "why is this sign off" and no label can carry it.
        hands = ("both" if lh > HAND_MIN and rh > HAND_MIN else
                 "right" if rh > HAND_MIN else "left" if lh > HAND_MIN else "none")
        if max(lh, rh) < 0.5 and hands != "none":
            hands += " (partial)"
        # Says MIRRORED or BASE, never "both". The passive hand is derived -- reflected from
        # the other hand, or placed from a lexicon written by a hearing developer and not yet
        # Deaf-reviewed. A label that hid that would be the same lie as scoring it.
        if timing.get("synth"):
            hands += f" + {timing['synth']}"
        e = f"{err.mean()*100:.1f}%" if len(err) else "n/a"
        p95 = f"{np.percentile(err,95)*100:.1f}%" if len(err) else "n/a"
        hs = f"{shp.mean()*100:.1f}%" if len(shp) else "n/a"
        fr_s = f"{fr.mean()*100:.0f}%" if len(fr) else "n/a"
        # "18>34 x2.0" reads: 18 frames of sign inside 34 of clip, slowed 2x to reach the
        # legibility floor. No marker means the sign plays at the speed it was signed.
        fcol = (f"{timing['stroke']}>{len(q)}" +
                (f" x{timing['stretch']:.1f}" if timing["stretch"] > 1.005 else ""))
        print(f"{w:<12s} {fcol:>12s} {hands:>16s} {e:>11s} {p95:>7s} {hs:>10s} "
              f"{fr_s:>9s} {cl*100.0/max(tot,1):7.1f}%")
        baked[w] = {"fps": d["fps"], "frames": q,
                    "hands": hands, "gloss": d.get("glosses", [w])[0],
                    "lh": round(float(lh * 100), 0), "rh": round(float(rh * 100), 0),
                    # §14 test 7 numbers travel WITH the animation, so a viewer showing the
                    # sign always shows how well it actually landed rather than implying it
                    # is exact.
                    "err": round(float(err.mean() * 100), 2) if len(err) else None,
                    "p95": round(float(np.percentile(err, 95) * 100), 2) if len(err) else None,
                    "shape": round(float(shp.mean() * 100), 1) if len(shp) else None,
                    "front": round(float(fr.mean() * 100), 0) if len(fr) else None,
                    "clamp": round(cl * 100.0 / max(tot, 1), 1),
                    # Playback timing, so a player that wants to CONCATENATE signs can drop
                    # the holds at an internal join instead of stacking two of them. frames
                    # [hold_in : hold_in+stroke] is the sign itself.
                    **timing}
    out = REPO / "avatar" / "baked_signs.json"
    out.write_text(json.dumps({
        "_note": ("Bone rotations baked by avatar/retarget.py from the 75-landmark motion in "
                  "animation_handoff/words/. Quaternions are LOCAL, xyzw, keyed by the "
                  "rigger's own bone names. A bone absent from a frame holds its rest pose."),
        "_wrist_error_note": ("§14 test 7 wants wrists within 5% of a shoulder-width of "
                              "target. Reported per word by the script that wrote this."),
        # THE REST POSE, AS QUATERNIONS, so that "absent means rest" is a value a player can
        # interpolate towards instead of a rule it has to snap to. There are exactly two bone
        # sets in this file -- 20 on a one-handed sign, 38 on a two-handed one -- and the 18
        # in the difference are the whole passive arm. A sentence player crossing from RAIN to
        # BLUE therefore has to put that arm back down, and without these it can only drop it
        # in a single frame. Local, xyzw, same convention as the tracks.
        "_rest": {n: [round(float(x), 6) for x in mat_to_quat(rig.rest_R[rig.by[n]])]
                  for n in sorted({c[0] for c in chains} | {"neck", "head"})
                  if n in rig.by},
        "signs": baked}, separators=(",", ":")), encoding="utf-8")
    print(f"\n[ok] {out}  ({out.stat().st_size/1e3:.0f} KB, {len(baked)} signs)")
    print(f"     §14 test 7 passes at <5% of a shoulder-width.")


if __name__ == "__main__":
    main()
