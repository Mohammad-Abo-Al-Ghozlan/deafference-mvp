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
from pathlib import Path

HERE = Path(__file__).resolve().parent
tpl = (HERE / "sign_viewer_template.html").read_text(encoding="utf-8")
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
