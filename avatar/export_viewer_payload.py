#!/usr/bin/env python3
"""Pack the untextured rig + baked signs into one base64 payload for a self-contained viewer.

The viewer has to be a single HTML file with no fetches, so the mesh travels inline. Quantised
to keep it small: positions to Int16 against the mesh bbox (~0.03 mm resolution on a 1.84 m
figure, far below anything visible), skin weights to Uint8. Indices stay Uint16 because 12,143
vertices fit. Normals are NOT shipped -- three.js recomputes them, and they are the single
largest array.
"""
import base64
import json
import struct
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
GLB = REPO / "3D Char deaf [untextured].glb"

raw = GLB.read_bytes()
_, _, total = struct.unpack_from("<4sII", raw, 0)
ch, off = {}, 12
while off < total:
    clen, ctype = struct.unpack_from("<I4s", raw, off)
    ch[ctype.strip(b"\x00")] = raw[off + 8: off + 8 + clen]
    off += 8 + clen + (-clen % 4)
G = json.loads(ch[b"JSON"].decode("utf-8"))
BIN = ch[b"BIN"]

CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
      5125: ("I", 4), 5126: ("f", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def acc(i):
    a = G["accessors"][i]
    f, s = CT[a["componentType"]]
    n = NC[a["type"]]
    bv = G["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    st = bv.get("byteStride") or s * n
    return np.array([struct.unpack_from("<" + f * n, BIN, base + r * st)
                     for r in range(a["count"])])


prim = G["meshes"][0]["primitives"][0]
att = prim["attributes"]
P = acc(att["POSITION"]).astype(np.float64)
J = acc(att["JOINTS_0"]).astype(np.int32)
W = acc(att["WEIGHTS_0"]).astype(np.float64)
ctw = G["accessors"][att["WEIGHTS_0"]]["componentType"]
if ctw != 5126:
    W /= {5121: 255.0, 5123: 65535.0}[ctw]
IDX = acc(prim["indices"]).astype(np.int64).reshape(-1)
IBM = acc(G["skins"][0]["inverseBindMatrices"]).astype(np.float32)
joints = G["skins"][0]["joints"]
nodes = G["nodes"]
name = {i: n.get("name", f"n{i}") for i, n in enumerate(nodes)}

lo, hi = P.min(0), P.max(0)
span = (hi - lo)
Pq = np.clip(np.round((P - lo) / span * 65535.0), 0, 65535).astype("<u2")
Wq = np.round(W / np.clip(W.sum(1, keepdims=True), 1e-9, None) * 255.0).astype("<u1")

blob = (Pq.tobytes() + IDX.astype("<u2").tobytes() +
        J.astype("<u1").tobytes() + Wq.tobytes() + IBM.astype("<f4").tobytes())

# node hierarchy: every joint's parent index (within the joints array) and local rest TRS
parent = {}
for i, n in enumerate(nodes):
    for c in n.get("children", []):
        parent[c] = i
jpos = {j: k for k, j in enumerate(joints)}


def trs(n):
    if "matrix" in n:
        M = np.array(n["matrix"], dtype=float).reshape(4, 4).T
        t = M[:3, 3]
        R = M[:3, :3]
        x = np.sqrt(max(0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
        q = [(R[2, 1] - R[1, 2]) / (4 * x), (R[0, 2] - R[2, 0]) / (4 * x),
             (R[1, 0] - R[0, 1]) / (4 * x), x]
        return list(t), q
    return (list(n.get("translation", [0, 0, 0])), list(n.get("rotation", [0, 0, 0, 1])))


bones = []
for k, j in enumerate(joints):
    t, q = trs(nodes[j])
    p = parent.get(j)
    bones.append({"n": name[j], "p": jpos.get(p, -1) if p is not None else -1,
                  "t": [round(v, 6) for v in t], "q": [round(v, 6) for v in q]})

signs = json.loads((REPO / "avatar" / "baked_signs.json").read_text(encoding="utf-8"))

payload = {
    "nv": len(P), "ni": len(IDX), "nb": len(joints),
    "lo": [round(v, 6) for v in lo], "span": [round(v, 6) for v in span],
    "bones": bones,
    "blob": base64.b64encode(blob).decode("ascii"),
    "signs": signs["signs"],
}
out = REPO / "avatar" / "viewer_payload.json"
out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
print(f"vertices {len(P):,}  tris {len(IDX)//3:,}  bones {len(joints)}  "
      f"signs {len(signs['signs'])}")
print(f"blob {len(blob)/1024:.0f} KB raw -> {len(payload['blob'])/1024:.0f} KB base64")
print(f"[ok] {out}  {out.stat().st_size/1024:.0f} KB total")
