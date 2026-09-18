#!/usr/bin/env python3
"""Inline the payload into the viewer template to produce a single self-contained HTML file.

Kept as a build step rather than one committed HTML file because the payload is ~800 KB of
base64 geometry derived from the rigger's Renderpeople base: the TEMPLATE is readable and
tracked, the BUILT file is gitignored alongside the .glb it comes from. Same reasoning as
.gitignore's — we may not have the right to redistribute that geometry until the licence
question in docs/AVATAR_M1_REVIEW_2026-09-12.md is answered, and a built viewer is a copy of
it. Open the output locally; do not host it.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check_syntax(template):
    """Refuse to build a viewer whose script does not parse.

    A stray quote in the footnote string once took the whole page down -- not the footnote,
    the WHOLE page, because one syntax error means the browser never runs any of the file.
    It loaded to "loading rig..." with no signs and no stats, and it shipped that way because
    the build happily wrote it and I reported the numbers instead of opening it.

    node --check costs milliseconds and catches the entire class. Skipped, loudly, if node is
    not installed -- a missing checker must not silently become a passing check.
    """
    if not shutil.which("node"):
        print("[warn] node not found -- viewer script NOT syntax-checked")
        return
    blocks = re.findall(r"<script>(.*?)</script>", template, re.S)
    if not blocks:
        raise SystemExit("[err] no inline <script> block found in the template")
    src = max(blocks, key=len).replace("__PAYLOAD__", "{}").replace("__STATS__", "{}")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    tmp.write(src)
    tmp.close()
    try:
        r = subprocess.run(["node", "--check", tmp.name], capture_output=True, text=True)
    finally:
        os.unlink(tmp.name)
    if r.returncode != 0:
        raise SystemExit("[err] the viewer script does not parse -- not writing it.\n"
                         + (r.stderr or r.stdout))
    print("[ok] viewer script parses")


tpl = (HERE / "sign_viewer_template.html").read_text(encoding="utf-8")
check_syntax(tpl)
pay_path, bake_path = HERE / "viewer_payload.json", HERE / "baked_signs.json"

# A STALENESS CHECK, because the alternative is a confident lie. This script only inlines the
# payload -- it never reads the bake -- so a rebake followed by a rebuild used to print
# "[ok] 250 signs" off a payload from before the rebake, and the viewer silently showed the
# previous numbers. Nothing in the output could distinguish that from success. It happened on
# 2026-09-18 and cost a round of "why has nothing changed". mtime is the crude check; the
# per-word comparison below is the real one, since a touched file can be stale and a rewritten
# one can be identical.
if bake_path.exists():
    bake = json.loads(bake_path.read_text(encoding="utf-8"))["signs"]
    pay = json.loads(pay_path.read_text(encoding="utf-8"))["signs"]
    drift = [w for w in bake.keys() & pay.keys()
             if bake[w].get("shape") != pay[w].get("shape")
             or len(bake[w].get("frames", ())) != len(pay[w].get("frames", ()))]
    gone = (bake.keys() | pay.keys()) - (bake.keys() & pay.keys())
    if drift or gone:
        raise SystemExit(
            f"[err] viewer_payload.json does not match baked_signs.json -- "
            f"{len(drift)} words differ" + (f", {len(gone)} only in one of them" if gone else "")
            + f"\n      e.g. {sorted(drift or gone)[:6]}"
            f"\n      Run:  python avatar/export_viewer_payload.py   then build again.")

payload = json.loads(pay_path.read_text(encoding="utf-8"))

# `synth` travels with the stats and not with the geometry on purpose: it is the same kind of
# fact as the error columns -- how far to trust what is on screen -- and it is the only one
# that covers the passive hand, which no error column can see.
stats = {w: {"err": s.get("err"), "p95": s.get("p95"), "shape": s.get("shape"),
             "front": s.get("front"), "clamp": s.get("clamp"), "synth": s.get("synth")}
         for w, s in payload["signs"].items()}

# The </script> sequence inside a JSON string would close the host <script> tag early. It
# cannot occur in base64 or in these numbers, but escaping it is one character and removes
# the whole class of bug.
blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
html = tpl.replace("__PAYLOAD__", blob).replace("__STATS__",
                                                json.dumps(stats, separators=(",", ":")))
assert "__PAYLOAD__" not in html and "__STATS__" not in html
out = HERE / "sign_viewer.html"
out.write_text(html, encoding="utf-8")
print(f"[ok] {out}")
mb = out.stat().st_size / 1e6
print(f"     {mb:.2f} MB, {len(payload['signs'])} signs, {payload['nb']} bones")
if mb > 24:
    print("     [warn] this is getting large for one file — the sign list is the growth, "
          "not the mesh")
print(f"     open it directly in a browser — it fetches nothing but three.js")
