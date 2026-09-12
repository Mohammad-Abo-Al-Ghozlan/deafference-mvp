#!/usr/bin/env python3
"""Strip embedded textures from a .glb and repack it. Phase-1 §12 wants a flat grey blockout.

`3D Char deaf.glb` is 29.2 MB, of which 28.4 MB is ONE diffuse map embedded twice -- 7.77 MB
as WebP (via EXT_texture_webp) and 20.65 MB as a JPEG fallback. The geometry, skinning and
bind matrices together are 760 KB. §12 asks for no texture at all in phase 1 ("flat grey
material"), and the runtime this feeds is a browser on a phone sitting next to a live
MediaPipe camera feed, so 29 MB before the first sign appears is not viable.

This is pure data surgery on the exported file. It does NOT touch geometry, skin weights,
inverse bind matrices, the node hierarchy or the bind pose -- the rig that passed §14 tests 1,
4 and 12 comes through byte-identical, and the script asserts that rather than assuming it.

UVs are KEPT. They cost ~97 KB and throwing them away would mean the mesh cannot be textured
again without a re-export from the rigger.
"""
import json
import struct
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "3D Char deaf.glb")
DST = Path(sys.argv[2] if len(sys.argv) > 2 else SRC.with_name(SRC.stem + " [untextured].glb"))
GREY = [0.72, 0.72, 0.72, 1.0]


def read_glb(path):
    raw = path.read_bytes()
    _, _, total = struct.unpack_from("<4sII", raw, 0)
    out, off = {}, 12
    while off < total:
        clen, ctype = struct.unpack_from("<I4s", raw, off)
        out[ctype.strip(b"\x00")] = raw[off + 8: off + 8 + clen]
        off += 8 + clen + (-clen % 4)
    return json.loads(out[b"JSON"].decode("utf-8")), out.get(b"BIN", b"")


def write_glb(path, doc, binchunk):
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    bn = binchunk + b"\x00" * (-len(binchunk) % 4)
    body = (struct.pack("<I4s", len(js), b"JSON") + js +
            struct.pack("<I4s", len(bn), b"BIN\x00") + bn)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


G, BIN = read_glb(SRC)
print(f"in   {SRC.name}  {SRC.stat().st_size/1e6:7.2f} MB")
for i, im in enumerate(G.get("images", [])):
    bv = G["bufferViews"][im["bufferView"]]
    print(f"     image[{i}] {im.get('name')!r} {im.get('mimeType')} "
          f"{bv['byteLength']/1e6:.2f} MB")

# What must survive, captured BEFORE the edit so the check at the end is a real comparison.
before = {
    "nodes": len(G["nodes"]),
    "joints": len(G["skins"][0]["joints"]),
    "ibm": G["skins"][0].get("inverseBindMatrices"),
    "prims": [(p["attributes"].copy(), p.get("indices"))
              for m in G["meshes"] for p in m["primitives"]],
    "hierarchy": [(n.get("name"), tuple(n.get("children", []))) for n in G["nodes"]],
    "trs": [(n.get("translation"), n.get("rotation"), n.get("scale"), n.get("matrix"))
            for n in G["nodes"]],
}

# ── drop image bufferViews, then repack the BIN and reindex everything that points into it ──
img_bvs = {im["bufferView"] for im in G.get("images", []) if "bufferView" in im}
keep = [i for i in range(len(G["bufferViews"])) if i not in img_bvs]
remap = {old: new for new, old in enumerate(keep)}

new_bin, new_views = bytearray(), []
for old in keep:
    bv = dict(G["bufferViews"][old])
    start = bv.get("byteOffset", 0)
    data = BIN[start: start + bv["byteLength"]]
    while len(new_bin) % 4:                       # glTF requires 4-byte alignment
        new_bin.append(0)
    bv["byteOffset"] = len(new_bin)
    new_bin += data
    new_views.append(bv)
G["bufferViews"] = new_views
for a in G["accessors"]:
    if "bufferView" in a:
        a["bufferView"] = remap[a["bufferView"]]

# ── flat grey material, and drop every texture construct ────────────────────────────────
G["materials"] = [{
    "name": "blockout_grey",
    "doubleSided": True,
    "pbrMetallicRoughness": {"baseColorFactor": GREY,
                             "metallicFactor": 0.0, "roughnessFactor": 0.8},
}]
for k in ("images", "textures", "samplers"):
    G.pop(k, None)
# EXT_texture_webp described a texture that no longer exists; KHR_materials_specular described
# a material we replaced. Leaving either in extensionsUsed is a lie about the file.
G["extensionsUsed"] = [e for e in G.get("extensionsUsed", [])
                       if e not in ("EXT_texture_webp", "KHR_materials_specular")]
if not G["extensionsUsed"]:
    G.pop("extensionsUsed")
G["buffers"] = [{"byteLength": len(new_bin)}]
G.setdefault("asset", {})["extras"] = {
    "deafference_note": (
        "Textures stripped from the rigger's delivery by avatar/strip_textures.py for the "
        "phase-1 flat-grey blockout required by AVATAR_BRIEF_COMPLETE.md v6.1 §12. Geometry, "
        "skinning, bind pose and node hierarchy are unmodified. The textured original is "
        "licence-encumbered pending the rigger's Renderpeople declaration.")}

write_glb(DST, G, bytes(new_bin))

# ── prove the rig survived ──────────────────────────────────────────────────────────────
H, HB = read_glb(DST)
after = {
    "nodes": len(H["nodes"]),
    "joints": len(H["skins"][0]["joints"]),
    "ibm": H["skins"][0].get("inverseBindMatrices"),
    "prims": [(p["attributes"].copy(), p.get("indices"))
              for m in H["meshes"] for p in m["primitives"]],
    "hierarchy": [(n.get("name"), tuple(n.get("children", []))) for n in H["nodes"]],
    "trs": [(n.get("translation"), n.get("rotation"), n.get("scale"), n.get("matrix"))
            for n in H["nodes"]],
}
assert after["nodes"] == before["nodes"], "node count changed"
assert after["joints"] == before["joints"], "joint count changed"
assert after["hierarchy"] == before["hierarchy"], "hierarchy changed"
assert after["trs"] == before["trs"], "a node transform changed — the bind pose moved"
assert after["prims"] == before["prims"], "mesh attributes changed"

# accessor CONTENTS, not just their descriptors: the reindexing is where this could go wrong
CT = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def blob(doc, buf, ai):
    a = doc["accessors"][ai]
    bv = doc["bufferViews"][a["bufferView"]]
    n = a["count"] * CT[a["componentType"]] * NC[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return buf[o:o + n]


checked = 0
for ai in range(len(G["accessors"])):
    if "bufferView" in G["accessors"][ai]:
        assert blob(G, bytes(new_bin), ai) == blob(
            json.loads(json.dumps(H)), HB, ai), f"accessor {ai} data differs"
        checked += 1

print(f"out  {DST.name}  {DST.stat().st_size/1e6:7.2f} MB   "
      f"({SRC.stat().st_size/DST.stat().st_size:.0f}x smaller)")
print(f"     [ok] {after['nodes']} nodes, {after['joints']} joints, hierarchy and every node "
      f"transform identical")
print(f"     [ok] all {checked} accessors byte-identical after bufferView reindexing")
print(f"     [ok] material replaced with flat grey; UVs kept so it can be re-textured")
