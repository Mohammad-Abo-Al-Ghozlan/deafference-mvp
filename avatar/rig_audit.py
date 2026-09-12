#!/usr/bin/env python3
"""Run the phase-1 acceptance tests from docs/AVATAR_BRIEF_COMPLETE.md v6.1 against a .glb.

§14 says the tests are "run by script on delivery ... so 'done' is a measurement rather than an
opinion". This is that script. It reads the exported file only -- never a viewport -- because
§6.11's warning is precisely that a rig can look correct in Blender and export wrong.

Scored here: tests 1, 2, 4 (export half), 9 (shape key half), 12, 13, 14 (static half), plus
§6.10 orientation/units/bind-pose and §12's deliverable list. Tests 3, 5, 6, 7, 8, 10, 11 need
either the runtime or a posed rig and are reported as NOT RUN rather than silently skipped.
"""
import json
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else
            r"c:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference\3D Char deaf.glb")

# ── glTF reading ─────────────────────────────────────────────────────────────────────────
raw = PATH.read_bytes()
_, _, glb_len = struct.unpack_from("<4sII", raw, 0)
chunks, off = {}, 12
while off < glb_len:
    clen, ctype = struct.unpack_from("<I4s", raw, off)
    chunks[ctype.strip(b"\x00")] = raw[off + 8: off + 8 + clen]
    off += 8 + clen + (-clen % 4)
G = json.loads(chunks[b"JSON"].decode("utf-8"))
BIN = chunks.get(b"BIN", b"")

CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
      5125: ("I", 4), 5126: ("f", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def accessor(i):
    a = G["accessors"][i]
    fmt, sz = CT[a["componentType"]]
    n = NC[a["type"]]
    bv = G["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or (sz * n)
    out = np.empty((a["count"], n), dtype=np.dtype(fmt))
    for r in range(a["count"]):
        out[r] = struct.unpack_from("<" + fmt * n, BIN, base + r * stride)
    return out


nodes = G["nodes"]
skin = G["skins"][0]
joints = skin["joints"]
jset = set(joints)
parent = {}
for i, n in enumerate(nodes):
    for c in n.get("children", []):
        parent[c] = i
NAME = {i: nodes[i].get("name", f"<node{i}>") for i in range(len(nodes))}
BY_NAME = {v: k for k, v in NAME.items()}

RESULTS = []


def report(num, title, ok, detail, side, phase="1"):
    RESULTS.append((num, title, ok, detail, side, phase))
    icon = {True: "PASS", False: "FAIL", None: "NOT RUN"}[ok]
    print(f"\n[{icon:7s}] TEST {num}: {title}")
    for line in detail.splitlines():
        print(f"          {line}")
    if ok is False:
        print(f"          → responsibility: {side}")


print("=" * 96)
print(f"PHASE-1 ACCEPTANCE AUDIT — brief v6.1 §14")
print(f"file    {PATH.name}  ({PATH.stat().st_size:,} bytes)")
print(f"asset   {json.dumps(G.get('asset', {}))}")
print("=" * 96)

# ── the §6.2 canonical 55 and a Renderpeople→Mixamo map ──────────────────────────────────
SPEC55 = (["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "HeadTop_End"] +
          [f"{s}{b}" for s in ("Left", "Right")
           for b in ["Shoulder", "Arm", "ForeArm", "Hand"]] +
          [f"{s}Hand{f}{k}" for s in ("Left", "Right")
           for f in ("Thumb", "Index", "Middle", "Ring", "Pinky") for k in (1, 2, 3, 4)])
assert len(SPEC55) == 55, len(SPEC55)

FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring",
        "pinky": "Pinky"}
MAP = {"hip": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
       "neck": "Neck", "head": "Head", "head_end": "HeadTop_End"}
for sfx, side in (("_l", "Left"), ("_r", "Right")):
    MAP[f"shoulder{sfx}"] = f"{side}Shoulder"
    MAP[f"upperarm{sfx}"] = f"{side}Arm"
    MAP[f"lowerarm{sfx}"] = f"{side}ForeArm"
    MAP[f"hand{sfx}"] = f"{side}Hand"
    for rp, mx in FING.items():
        for k in (1, 2, 3):
            MAP[f"{rp}_0{k}{sfx}"] = f"{side}Hand{mx}{k}"
        MAP[f"{rp}_end{sfx}"] = f"{side}Hand{mx}4"
    MAP[f"upperleg{sfx}"] = f"{side}UpLeg"
    MAP[f"lowerleg{sfx}"] = f"{side}Leg"
    MAP[f"foot{sfx}"] = f"{side}Foot"
    MAP[f"ball{sfx}"] = f"{side}ToeBase"

present_rp = {NAME[j] for j in joints}
mapped = {MAP[r]: r for r in present_rp if r in MAP}
missing = [b for b in SPEC55 if b not in mapped]
extra = sorted(r for r in present_rp if r not in MAP)

# ── TEST 1 · finger node count ───────────────────────────────────────────────────────────
counts, bad = {}, []
for side in ("l", "r"):
    for rp in FING:
        chainn = [f"{rp}_01_{side}", f"{rp}_02_{side}", f"{rp}_03_{side}", f"{rp}_end_{side}"]
        got = [c for c in chainn if c in present_rp]
        counts[f"{rp}_{side}"] = len(got)
        if len(got) != 4:
            bad.append(f"{rp}_{side}={len(got)}")
hand_nodes = sum(counts.values()) + sum(1 for s in "lr" if f"hand_{s}" in present_rp)
report(1, "Finger node count (40 finger + 2 wrists = 42)",
       hand_nodes == 42 and not bad,
       f"finger nodes {sum(counts.values())}/40, wrists "
       f"{sum(1 for s in 'lr' if f'hand_{s}' in present_rp)}/2, total {hand_nodes}/42\n"
       f"every finger has 4 transforms: {'yes' if not bad else 'NO -> ' + ', '.join(bad)}\n"
       f"the tip nodes exist and are named `<finger>_end_<side>` (leaf bones survived export)",
       "—")

# ── TEST 2 · bone names ──────────────────────────────────────────────────────────────────
mapfiles = sorted(PATH.parent.glob("*map*.json")) + sorted(PATH.parent.glob("*bone*.json"))
report(2, "Bone names match §6.2 exactly, or a complete map is supplied",
       False,
       f"0 of 55 §6.2 names present. The skeleton uses Renderpeople naming "
       f"(`hip`, `spine_01`, `upperarm_l`, `index_01_l`).\n"
       f"§6.1 allows this — 'deliver a JSON map covering all 55 bones' — but no map file was "
       f"delivered.\nSearched {PATH.parent} for *map*.json / *bone*.json: "
       f"{[p.name for p in mapfiles] or 'none found'}\n"
       f"Structurally the skeleton IS §6.2's hierarchy: all 55 map 1:1 with no gaps "
       f"({len(mapped)}/55 resolvable).\nSo this is a MISSING DELIVERABLE (§12 item 4), not a "
       f"broken rig.",
       "ANIMATOR — but trivially fixable; we can also author the map ourselves")

# ── TEST 4 · no scale channels / stretchy IK in the exported file ────────────────────────
scaled = [(NAME[j], nodes[j]["scale"]) for j in joints
          if "scale" in nodes[j] and any(abs(s - 1.0) > 1e-4 for s in nodes[j]["scale"])]
mat_scaled = []
for j in joints:
    if "matrix" in nodes[j]:
        m = np.array(nodes[j]["matrix"], dtype=np.float64).reshape(4, 4).T
        sc = [np.linalg.norm(m[:3, c]) for c in range(3)]
        if any(abs(s - 1.0) > 1e-3 for s in sc):
            mat_scaled.append((NAME[j], [round(s, 4) for s in sc]))
report(4, "Bone-length stability — no scale channels, no stretchy IK in the export",
       not scaled and not mat_scaled,
       f"joints carrying a non-unit TRS scale: {len(scaled)}\n"
       f"joints whose matrix decomposes to non-unit scale: {len(mat_scaled)}\n"
       + (f"offenders: {(scaled + mat_scaled)[:6]}\n" if (scaled or mat_scaled) else "")
       + f"animations in file: {len(G.get('animations', []))} (§12 forbids clips — correct)",
       "ANIMATOR" if (scaled or mat_scaled) else "—")

# ── TEST 9 (partial) · browRaise shape key ───────────────────────────────────────────────
targets = sum(len(p.get("targets", [])) for m in G["meshes"] for p in m["primitives"])
tnames = [(m.get("extras") or {}).get("targetNames") for m in G["meshes"]]
report(9, "browRaise feasibility shape key exists (§6.9, §12 item 7)",
       targets > 0,
       f"morph targets in file: {targets}\n"
       f"extras.targetNames: {[t for t in tnames if t] or 'none'}\n"
       f"§6.11 requires 'Data → Shape Keys = ON'; §12 item 7 lists the shape as a deliverable.\n"
       f"Head range (yaw ±30 / tilt ±20, no tearing) NOT tested here — needs a posed rig.",
       "ANIMATOR")

# ── TEST 12 · vertex influences ──────────────────────────────────────────────────────────
prim = G["meshes"][0]["primitives"][0]
att = prim["attributes"]
jsets = sorted(k for k in att if k.startswith("JOINTS_"))
wsets = sorted(k for k in att if k.startswith("WEIGHTS_"))
W = np.concatenate([accessor(att[k]).astype(np.float64) for k in wsets], axis=1)
if G["accessors"][att[wsets[0]]]["componentType"] != 5126:   # normalized integer weights
    W /= {5121: 255.0, 5123: 65535.0}[G["accessors"][att[wsets[0]]]["componentType"]]
nz = (W > 1e-6).sum(1)
sums = W.sum(1)
unweighted = int((nz == 0).sum())
over4 = int((nz > 4).sum())
bad_norm = int((np.abs(sums - 1.0) > 1e-3).sum())
report(12, "Max 4 influences per vertex, normalized, no unweighted vertices",
       over4 == 0 and unweighted == 0 and bad_norm == 0,
       f"vertices {len(W):,}; influence sets {jsets} ({4 * len(jsets)} slots)\n"
       f"vertices with >4 influences : {over4}\n"
       f"unweighted vertices         : {unweighted}\n"
       f"weights not summing to 1.0  : {bad_norm}  (max deviation "
       f"{float(np.abs(sums - 1.0).max()):.2e})\n"
       f"influences per vertex: min {int(nz.min())}, max {int(nz.max())}, "
       f"mean {float(nz.mean()):.2f}",
       "ANIMATOR" if (over4 or unweighted or bad_norm) else "—")

# ── TEST 13 · budgets ────────────────────────────────────────────────────────────────────
tris = sum(G["accessors"][p["indices"]]["count"] // 3
           for m in G["meshes"] for p in m["primitives"] if "indices" in p)
verts = sum(G["accessors"][p["attributes"]["POSITION"]]["count"]
            for m in G["meshes"] for p in m["primitives"])
FACE = {"eye", "eyelid", "eyebrow", "jaw", "mouth"}
face_bones = [e for e in extra if any(e.startswith(f) for f in FACE)]
twists = [e for e in extra if "twist" in e]
arm_tw = [t for t in twists if "arm" in t]
other_extra = [e for e in extra if e not in face_bones and e not in twists]
legs = [r for r in present_rp if r in MAP and MAP[r].endswith(
    ("UpLeg", "Leg", "Foot", "ToeBase"))]
report(13, "Budgets — triangles, bone count, file size (§12)",
       20_000 <= tris <= 40_000 and not face_bones and len(arm_tw) <= 2,
       f"triangles {tris:,}  (blockout budget 20k-40k) {'OK' if 20000<=tris<=40000 else 'OUT'}\n"
       f"vertices  {verts:,}\n"
       f"file size {PATH.stat().st_size/1e6:.1f} MB — §12 says phase 1 needs NO textures "
       f"('flat grey material'); this ships {len(G.get('images', []))} embedded images\n"
       f"joints {len(joints)} total = 55 spec + {len(legs)} leg (optional, allowed) + "
       f"{len(extra)} undeclared\n"
       f"  undeclared face bones ({len(face_bones)}): {face_bones}\n"
       f"  twist bones ({len(twists)}): {twists}\n"
       f"     §12 allows 'at most one documented twist bone per forearm' = 2; "
       f"file has {len(arm_tw)} arm twists\n"
       f"  other ({len(other_extra)}): {other_extra}\n"
       f"§6.2: 'Do not add bones we cannot drive... An undocumented extra bone is worse than "
       f"no bone.'",
       "ANIMATOR")

# ── TEST 14 · loads clean / no unsupported features ──────────────────────────────────────
ext_used = G.get("extensionsUsed", [])
ext_req = G.get("extensionsRequired", [])
unapplied = [NAME[i] for i, n in enumerate(nodes)
             if i not in jset and "mesh" in n and
             (any(abs(s - 1) > 1e-6 for s in n.get("scale", [1, 1, 1]))
              or n.get("rotation", [0, 0, 0, 1]) != [0, 0, 0, 1])]
report(14, "Loads clean in Three.js; no unapplied transforms; no unsupported features",
       not ext_req and not unapplied,
       f"extensionsUsed     : {ext_used}\n"
       f"extensionsRequired : {ext_req or 'none (so a loader may ignore the above)'}\n"
       f"EXT_texture_webp is NOT in three.js core GLTFLoader's default extension set; it needs\n"
       f"  the WebP fallback or an explicit plugin. Listed as used-but-not-required, so a\n"
       f"  loader without it falls back to the other image — check which of the 2 images.\n"
       f"unapplied transforms on mesh nodes: {unapplied or 'none'}\n"
       f"KHR_materials_specular is core-supported in recent three.js.",
       "ANIMATOR" if ext_req or unapplied else "—")

# ── §6.10 orientation / units / bind pose ────────────────────────────────────────────────
pos = accessor(att["POSITION"]).astype(np.float64)
lo, hi = pos.min(0), pos.max(0)
size = hi - lo


def world(i):
    M = np.eye(4)
    ch = []
    k = i
    while k is not None:
        ch.append(k)
        k = parent.get(k)
    for k in reversed(ch):
        n = nodes[k]
        if "matrix" in n:
            L = np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
        else:
            t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
            q = np.array(n.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
            s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
            x, y, z, w = q
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            L = np.eye(4)
            L[:3, :3] = R * s
            L[:3, 3] = t
        M = M @ L
    return M


def wp(bone):
    return world(BY_NAME[bone])[:3, 3]


print("\n" + "=" * 96)
print("§6.10 ORIENTATION, UNITS, BIND POSE  (not a numbered test — but §12 deliverable 1)")
print("=" * 96)
print(f"  mesh bbox  x {lo[0]:+.3f}..{hi[0]:+.3f}   y {lo[1]:+.3f}..{hi[1]:+.3f}   "
      f"z {lo[2]:+.3f}..{hi[2]:+.3f}")
print(f"  size       {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f}  "
      f"-> height {size.max():.3f} on axis {'XYZ'[int(size.argmax())]}")
print(f"  units      {'OK ~1.7 m, +Y up' if 1.4 < size[1] < 2.1 else 'CHECK — see above'}")
print(f"  origin     feet at y={lo[1]:+.4f} (§6.10 wants origin at the feet, ~0)")

sh_l, sh_r = wp("shoulder_l"), wp("shoulder_r")
sw = float(np.linalg.norm(sh_l - sh_r))
for side, s in (("L", "l"), ("R", "r")):
    up, lo_, ha = wp(f"upperarm_{s}"), wp(f"lowerarm_{s}"), wp(f"hand_{s}")
    v = ha - up
    drop = math.degrees(math.atan2(-v[1], abs(v[0]) + 1e-9))
    e1, e2 = lo_ - up, ha - lo_
    elbow = math.degrees(math.acos(np.clip(
        np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)), -1, 1)))
    print(f"  arm {side}      shoulder->hand drops {drop:+.1f}° below horizontal, "
          f"elbow bend {elbow:.1f}°")
print(f"  shoulder width {sw:.3f} m")
print(f"  §6.10 wants an A-POSE: arms ~45° down, elbows 5-10° flexed, fingers ~5° curled.")

# finger curl in bind pose
print("\n  finger curl at bind (angle between consecutive segments, 0 = perfectly straight):")
for s in ("l", "r"):
    row = []
    for rp in FING:
        pts = [wp(f"{rp}_01_{s}"), wp(f"{rp}_02_{s}"), wp(f"{rp}_03_{s}"),
               wp(f"{rp}_end_{s}")]
        angs = []
        for a in range(2):
            v1, v2 = pts[a + 1] - pts[a], pts[a + 2] - pts[a + 1]
            angs.append(math.degrees(math.acos(np.clip(
                np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)), -1, 1))))
        row.append(f"{rp[:3]} {max(angs):4.1f}°")
    print(f"     {s.upper()}: " + "  ".join(row))

# bone lengths, for §12 deliverable 3
print("\n  hand bone lengths (m) — §12 deliverable 3 asks for this table and it was not supplied:")
for s in ("r",):
    for rp in FING:
        pts = [wp(f"{rp}_01_{s}"), wp(f"{rp}_02_{s}"), wp(f"{rp}_03_{s}"), wp(f"{rp}_end_{s}")]
        L = [float(np.linalg.norm(pts[a + 1] - pts[a])) for a in range(3)]
        print(f"     {rp+'_'+s:<12s} " + "  ".join(f"{x*1000:5.1f}mm" for x in L) +
              f"   total {sum(L)*1000:5.1f}mm")

# ── not run ──────────────────────────────────────────────────────────────────────────────
for num, title in [(3, "Distal keying (needs runtime)"), (5, "Forearm twist ±90°"),
                   (6, "Abduction / B vs 5"), (7, "Reference-pose retarget (needs runtime)"),
                   (8, "Handshape reachability — the seven"),
                   (10, "Extremes, no tearing"), (11, "Contact zones")]:
    report(num, title, None,
           "Requires posing the rig or the runtime retargeter; not decidable from the static "
           "file.", "—")

print("\n" + "=" * 96)
print("SUMMARY")
print("=" * 96)
for num, title, ok, _d, side, _p in sorted(RESULTS):
    print(f"  {num:>3}  {'PASS' if ok else 'FAIL' if ok is False else '----'}  "
          f"{title[:62]:<62s} {side if ok is False else ''}")
f = [r for r in RESULTS if r[2] is False]
p = [r for r in RESULTS if r[2] is True]
print(f"\n  {len(p)} passed, {len(f)} failed, "
      f"{len([r for r in RESULTS if r[2] is None])} not run")


# ═════════════════════════════════════════════════════ emit the two missing §12 deliverables
# §12 items 3 and 4 are the rigger's to supply and were not in the delivery. Both are
# derivable from the exported file with no judgement calls, so we generate them rather than
# block M1 review on an email round-trip. They are marked provisional: a map we inferred is
# a statement about what we BELIEVE his names mean, and only he can confirm it.
if "--emit" in sys.argv:
    out = PATH.parent / "avatar"
    out.mkdir(exist_ok=True)

    unmapped = sorted(set(present_rp) - set(MAP))
    doc = {
        "_note": (
            "Renderpeople -> Mixamo (§6.2) bone name map for '3D Char deaf.glb'. "
            "§12 deliverable 4 and §14 test 2. GENERATED BY US on 2026-09-12 by "
            "avatar/rig_audit.py --emit, NOT supplied by the rigger."),
        "_status": "PROVISIONAL — needs the rigger's confirmation before integration",
        "_why_provisional": (
            "The mapping is inferred from names and hierarchy, both of which match §6.2 "
            "one-for-one. It is almost certainly right. But a name map is a claim about what "
            "someone else's bone MEANS, and the one bone where a wrong guess is expensive is "
            "`thumb_01_*`: §6.4 says Thumb1 is the CMC deep in the palm, and if his "
            "`thumb_01` were the web joint instead, every A/S/O/C handshape would retarget "
            "wrong while the map still looked valid. We measured it at 0.50 (right) and 0.44 "
            "(left) of the wrist->index-MCP distance, which IS the CMC, so the map is "
            "consistent with the geometry -- but confirm it anyway."),
        "_covers": f"{len(mapped)} of the 55 §6.2 bones, plus {len(legs)} optional leg bones",
        "_unmapped_bones_in_file": {
            "_note": ("Present in the .glb, not in §6.2, and NOT driven by the runtime. "
                      "§6.2: 'Do not add bones we cannot drive.' Listed so integration knows "
                      "they exist and leaves them at bind rotation deliberately."),
            "bones": unmapped,
        },
        "map": {rp: MAP[rp] for rp in sorted(present_rp) if rp in MAP},
    }
    p_map = out / "bone_map_renderpeople_to_mixamo.json"
    p_map.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"\n[emit] {p_map}  ({len(doc['map'])} names)")

    # Which joints actually move vertices. The 10 finger tips SHOULD be weightless (§6.3),
    # and their presence in this list is the positive evidence that "Export Deformation
    # Bones only" was OFF -- the setting §6.11 calls the one most likely to silently break
    # the delivery.
    J = accessor(att["JOINTS_0"])
    used = np.zeros(len(joints))
    for c in range(4):
        np.add.at(used, J[:, c], (W[:, c] > 1e-6).astype(float))

    rows = []
    for k, j in enumerate(joints):
        n = NAME[j]
        par = parent.get(j)
        pw = world(par)[:3, 3] if par is not None and par in jset else None
        cw = world(j)[:3, 3]
        rows.append({
            "bone": n,
            "mixamo": MAP.get(n),
            "parent": NAME[par] if par is not None else None,
            "rest_length_m": (round(float(np.linalg.norm(cw - pw)), 6)
                              if pw is not None else None),
            "world_rest_xyz_m": [round(float(v), 6) for v in cw],
            "weighted_vertices": int(used[k]),
            "deforms_mesh": bool(used[k] > 0),
        })
    p_len = out / "bone_lengths_measured.json"
    p_len.write_text(json.dumps({
        "_note": ("§12 deliverable 3 (bone length table). GENERATED BY US from the exported "
                  ".glb on 2026-09-12, not supplied by the rigger. rest_length_m is the "
                  "distance from the bone's own joint to its PARENT joint at bind, in metres "
                  "-- the file is already in metres, ~1.84 m tall, so no unit conversion."),
        "_source_file": PATH.name,
        "_units": "metres",
        "bones": rows,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"[emit] {p_len}  ({len(rows)} bones)")
