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
payload = json.loads((HERE / "viewer_payload.json").read_text(encoding="utf-8"))

stats = {w: {"err": s.get("err"), "p95": s.get("p95"), "shape": s.get("shape"),
             "front": s.get("front"), "clamp": s.get("clamp")}
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
print(f"     {out.stat().st_size/1e6:.2f} MB, {len(payload['signs'])} signs, "
      f"{payload['nb']} bones")
print(f"     open it directly in a browser — it fetches nothing but three.js")
