#!/usr/bin/env python3
r"""
2D preview / review player for the speech->sign handoff (SIGN_ANIMATION_CONTRACT).

This renders the SAME per-word JSON files your friend's avatar consumes
(animation_handoff/words/<word>.json + reference_pose.json), by drawing the 75-point
skeleton with OpenCV. It closes two gaps at once:

  * DEBUG OVERLAY — exactly the "2D landmark overlay" the animator asked for: when a
    pose looks wrong it instantly tells you whether the DATA or his retarget is at fault.
  * DEAF REVIEW  — `--review` steps through all 250 exemplars so a Deaf reviewer can
    mark each sign good/bad (the one quality risk the animator flagged). Verdicts are
    saved to animation_handoff/review_log.json and the run resumes where you left off.

It also acts as a local END-TO-END stand-in: `--words "hello mom hungry"` (or
`--speech "..."`) plays the per-word clips in sequence with blended transitions — the
friend's avatar simulated by the 2D skeleton — so you can watch the whole pipeline
before his rig exists.

Coordinates: the JSON is shoulder-centered, y-DOWN (image space). OpenCV is also
y-down, so — unlike the friend's y-UP engine — this previewer does NOT flip y. z is
dropped (2D). `null` points are held from the last valid frame (contract §6) unless
--raw. Sizes are comparable across words because the data is shoulder-normalized.

RUN (uses the interpreter that has OpenCV — the one that runs live_demo.py):
  python preview_signs.py --word hello                 # one sign, looped
  python preview_signs.py --words "hello mom hungry"   # a stitched sequence
  python preview_signs.py --pose                        # the neutral reference pose
  python preview_signs.py --review                      # Deaf-review all 250, save verdicts
  python preview_signs.py --word snow --save snow.mp4   # export a video (headless; share it)
  python preview_signs.py --contact                     # a 250-thumbnail index PNG (headless)
  python preview_signs.py --speech "hello I am hungry"  # text->gloss->play (needs GEMINI key)

Interactive keys: [q]/Esc quit · [space] pause · [ ] step · [r] restart.
Review keys:      [g] good · [b] bad · [u] unsure · [n] next · [p] prev · [s] skip · [q] save+quit.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("[err] preview_signs needs OpenCV:  pip install opencv-python\n"
             "      (use the same interpreter that runs live_demo.py — it already has cv2)")

HERE = Path(__file__).resolve().parent
N_POINTS = 75
POSE_N, HAND_N = 33, 21           # 33 pose + 21 left hand + 21 right hand
LHAND_BASE, RHAND_BASE = 33, 54

# ── skeleton topology (indices into the 75-point array) ───────────────────────
POSE_EDGES = [
    # coarse head
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    # shoulders / arms / torso
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
]
# standard MediaPipe hand topology (0=wrist .. 20=pinky tip), applied per hand block
HAND_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # palm base
]

# BGR colors
POSE_COLOR = (190, 190, 190)
LHAND_COLOR = (90, 220, 90)       # signer's left hand (green)
RHAND_COLOR = (90, 170, 255)      # signer's right hand (orange)
JOINT_COLOR = (245, 245, 245)
BG_COLOR = (24, 24, 28)
TEXT_COLOR = (240, 240, 240)

CANVAS_W, CANVAS_H = 760, 820
CX, CY = CANVAS_W // 2, int(CANVAS_H * 0.46)
SCALE = 210.0                     # px per shoulder-width unit (fixed → sizes comparable)


# ── loading ───────────────────────────────────────────────────────────────────
def _to_array(frames) -> np.ndarray:
    """[[[x,y,z]|null...]...] -> (T,75,3) float32 with NaN for null/missing."""
    out = np.full((len(frames), N_POINTS, 3), np.nan, dtype=np.float32)
    for t, fr in enumerate(frames):
        for j, pt in enumerate(fr[:N_POINTS]):
            if pt is None:                       # whole landmark null (contract §6) -> leave NaN
                continue
            for k in range(min(3, len(pt))):
                v = pt[k]
                if v is not None and math.isfinite(v):
                    out[t, j, k] = float(v)
    return out


def load_json_clip(path: Path) -> tuple[np.ndarray, list, list, int]:
    """Load a §1 motion JSON OR a reference-pose JSON.
    Returns (frames (T,75,3), segments, glosses, fps)."""
    if not path.exists():
        raise SystemExit(f"[err] no such file: {path}")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"[err] {path.name} is not valid JSON: {e}")
    except OSError as e:
        raise SystemExit(f"[err] cannot read {path}: {e}")
    fps = int(d.get("fps", 30))
    if "frames" in d:
        arr = _to_array(d["frames"])
        segs = d.get("segments", [])
        glosses = d.get("glosses", [])
    elif "pose" in d:                                  # reference_pose.json (single frame)
        arr = _to_array([d["pose"]])
        segs = [{"gloss": "reference_pose", "start": 0, "end": 1}]
        glosses = ["reference_pose"]
    else:
        raise SystemExit(f"[err] {path.name}: not a motion JSON (no 'frames' or 'pose' key)")
    if arr.shape[0] == 0:
        raise SystemExit(f"[err] {path.name}: zero frames")
    return arr, segs, glosses, fps


def word_path(word: str, words_dir: Path) -> Path:
    p = words_dir / f"{word}.json"
    if not p.exists():
        raise SystemExit(f"[err] no clip for '{word}' at {p}")
    return p


def load_word_array(word: str, words_dir: Path) -> np.ndarray:
    arr, _s, _g, _f = load_json_clip(word_path(word, words_dir))
    return arr


def vocab_order(vocab_path: Path, fallback: list[str]) -> list[str]:
    """Frozen 250 order if vocab_250.json is present; else sorted words we actually have."""
    if vocab_path.exists():
        raw = json.loads(vocab_path.read_text(encoding="utf-8"))
        words = raw["words"] if isinstance(raw, dict) else raw
        have = set(fallback)
        ordered = [w for w in words if w in have]
        ordered += sorted(have - set(ordered))          # any extras not in vocab
        return ordered
    return sorted(fallback)


# ── rendering ───────────────────────────────────────────────────────────────
def _project(pt) -> tuple[int, int] | None:
    x, y, _z = pt
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return int(round(CX + x * SCALE)), int(round(CY + y * SCALE))


def _draw_edges(img, pts, edges, base, color):
    for a, b in edges:
        pa, pb = _project(pts[base + a]), _project(pts[base + b])
        if pa is not None and pb is not None:
            cv2.line(img, pa, pb, color, 2, cv2.LINE_AA)


def _draw_joints(img, pts, base, count, color):
    for i in range(count):
        p = _project(pts[base + i])
        if p is not None:
            cv2.circle(img, p, 3, color, -1, cv2.LINE_AA)


def render_frame(pts: np.ndarray, hud: list[tuple[str, tuple]] | None = None) -> np.ndarray:
    """pts: (75,3) already hold-filled. Returns a BGR canvas."""
    img = np.full((CANVAS_H, CANVAS_W, 3), BG_COLOR, dtype=np.uint8)
    # connect pose wrist -> hand-block wrist so the hand visually attaches to the arm
    for pose_w, base in ((15, LHAND_BASE), (16, RHAND_BASE)):
        pa, pb = _project(pts[pose_w]), _project(pts[base])
        if pa is not None and pb is not None:
            cv2.line(img, pa, pb, POSE_COLOR, 1, cv2.LINE_AA)
    _draw_edges(img, pts, POSE_EDGES, 0, POSE_COLOR)
    _draw_edges(img, pts, HAND_EDGES, LHAND_BASE, LHAND_COLOR)
    _draw_edges(img, pts, HAND_EDGES, RHAND_BASE, RHAND_COLOR)
    _draw_joints(img, pts, 0, POSE_N, POSE_COLOR)
    _draw_joints(img, pts, LHAND_BASE, HAND_N, LHAND_COLOR)
    _draw_joints(img, pts, RHAND_BASE, HAND_N, RHAND_COLOR)
    if hud:
        y = 34
        for text, color in hud:
            cv2.putText(img, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
            y += 30
    return img


def hold_fill(arr: np.ndarray, raw: bool) -> np.ndarray:
    """Carry the last finite value forward per point (contract §6). raw=True disables it
    so genuine hand-dropouts are visible (debug)."""
    if raw:
        return arr
    out = arr.copy()
    last = np.full((N_POINTS, 3), np.nan, dtype=np.float32)
    for t in range(out.shape[0]):
        cur = out[t]
        fill = ~np.isfinite(cur) & np.isfinite(last)
        cur[fill] = last[fill]
        finite = np.isfinite(cur)
        last[finite] = cur[finite]
    return out


# ── playback (interactive) ──────────────────────────────────────────────────
def _seg_label(segments, t) -> str:
    for s in segments:
        if s["start"] <= t < s["end"]:
            return s["gloss"]
    return ""


def play_interactive(arr, segments, fps, title, extra_hud=None, handled=("q",)):
    """Loop the clip; return the char of the first HANDLED key pressed (or 'q')."""
    T = arr.shape[0]
    delay = max(1, int(round(1000.0 / max(1, fps))))
    t, paused = 0, False
    handled_codes = {ord(c) for c in handled} | {27}       # 27 = Esc always quits
    win = "preview_signs"
    while True:
        pts = arr[t]
        seg = _seg_label(segments, t)
        hud = [(title, TEXT_COLOR)]
        if seg and seg != title:
            hud.append((f"sign: {seg}", (120, 220, 255)))
        hud.append((f"frame {t + 1}/{T}  @ {fps}fps" + ("  [PAUSED]" if paused else ""), (170, 170, 170)))
        if extra_hud:
            hud.extend(extra_hud)
        cv2.imshow(win, render_frame(pts, hud))
        k = cv2.waitKey(delay) & 0xFF
        if k == 27 or k == ord("q"):
            return "q"
        if k == ord(" "):
            paused = not paused
        elif k == ord("r"):
            t, paused = 0, False
        elif k == ord("]"):
            t, paused = min(T - 1, t + 1), True
        elif k == ord("["):
            t, paused = max(0, t - 1), True
        elif k in handled_codes:
            return chr(k)
        if not paused:
            t = (t + 1) % T


# ── headless export (video / image) ──────────────────────────────────────────
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp"}


def save_clip(arr, segments, fps, out: Path):
    """Write the clip to a video, or a single mid-frame to an image. No GUI → headless."""
    ext = out.suffix.lower()
    out.parent.mkdir(parents=True, exist_ok=True)
    if ext in IMAGE_EXT:
        t = arr.shape[0] // 2
        if not cv2.imwrite(str(out), render_frame(arr[t], [(f"{_seg_label(segments, t) or out.stem}", TEXT_COLOR)])):
            raise SystemExit(f"[err] failed to write {out}")
        print(f"[ok] wrote frame {t} -> {out}")
        return
    if ext not in VIDEO_EXT:
        raise SystemExit(f"[err] --save must end in {sorted(VIDEO_EXT | IMAGE_EXT)}")
    fourcc = cv2.VideoWriter_fourcc(*("mp4v" if ext == ".mp4" else "XVID"))
    vw = cv2.VideoWriter(str(out), fourcc, float(max(1, fps)), (CANVAS_W, CANVAS_H))
    if not vw.isOpened():
        raise SystemExit(f"[err] could not open a video writer for {out} — try a .avi path")
    for t in range(arr.shape[0]):
        seg = _seg_label(segments, t)
        hud = [(seg or out.stem, TEXT_COLOR), (f"{t + 1}/{arr.shape[0]}", (170, 170, 170))]
        vw.write(render_frame(arr[t], hud))
    vw.release()
    print(f"[ok] wrote {arr.shape[0]} frames -> {out}")


def save_contact_sheet(words_dir: Path, order: list[str], out: Path, cols: int = 16):
    """A grid PNG of every word's mid-frame — a quick visual index of all clips."""
    if out.suffix.lower() not in IMAGE_EXT:
        raise SystemExit(f"[err] contact sheet needs an image path {sorted(IMAGE_EXT)} — got '{out.suffix or 'none'}'")
    tile = 150
    rows = math.ceil(len(order) / cols)
    sheet = np.full((rows * tile, cols * tile, 3), BG_COLOR, dtype=np.uint8)
    global CX, CY, SCALE, CANVAS_W, CANVAS_H
    keep = (CX, CY, SCALE, CANVAS_W, CANVAS_H)
    CANVAS_W = CANVAS_H = tile
    CX, CY, SCALE = tile // 2, int(tile * 0.46), tile * 0.30
    for i, w in enumerate(order):
        try:
            arr = hold_fill(load_word_array(w, words_dir), raw=False)
        except SystemExit:
            continue
        img = render_frame(arr[arr.shape[0] // 2])
        cv2.putText(img, w[:12], (4, tile - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36, TEXT_COLOR, 1, cv2.LINE_AA)
        r, c = divmod(i, cols)
        sheet[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = img
    CX, CY, SCALE, CANVAS_W, CANVAS_H = keep
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), sheet):
        raise SystemExit(f"[err] failed to write {out}")
    print(f"[ok] contact sheet ({len(order)} words) -> {out}")


# ── Deaf-review harness ───────────────────────────────────────────────────────
def run_review(words_dir: Path, order: list[str], log_path: Path, start: int | None, redo: bool):
    log = {"verdicts": {}, "updated": None}
    if log_path.exists():
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
            log.setdefault("verdicts", {})
        except Exception:
            pass
    verdicts = log["verdicts"]

    def save():
        log["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    if start is not None:
        idx = max(0, min(len(order) - 1, start - 1))
    elif not redo:                                   # resume at first unrated
        idx = next((i for i, w in enumerate(order) if w not in verdicts), 0)
    else:
        idx = 0
    print(f"[review] {len(order)} words · {sum(1 for w in order if w in verdicts)} already rated · "
          f"starting at #{idx + 1} ({order[idx]})")
    print("[review] keys: [g]ood  [b]ad  [u]nsure  [n]/next  [p]rev  [s]kip  [q]uit+save")

    while 0 <= idx < len(order):
        w = order[idx]
        try:
            arr = hold_fill(load_word_array(w, words_dir), raw=False)
        except (SystemExit, Exception) as e:                 # skip a bad/corrupt file, don't kill the run
            print(f"[skip] {w}: {e}"); idx += 1; continue
        cur = verdicts.get(w, "—")
        vc = {"good": (90, 220, 90), "bad": (80, 80, 255), "unsure": (80, 200, 255)}.get(cur, (170, 170, 170))
        extra = [(f"[{idx + 1}/{len(order)}]  verdict: {cur}", vc),
                 ("g=good  b=bad  u=unsure  n=next  p=prev  q=quit", (150, 150, 150))]
        k = play_interactive(arr, [{"gloss": w, "start": 0, "end": arr.shape[0]}], 30,
                             title=w, extra_hud=extra, handled=("g", "b", "u", "n", "p", "s"))
        if k == "q":
            break
        if k in ("g", "b", "u"):
            verdicts[w] = {"g": "good", "b": "bad", "u": "unsure"}[k]; save(); idx += 1
        elif k == "p":
            idx = max(0, idx - 1)
        else:                                        # n / s
            idx += 1

    save()
    good = [w for w in order if verdicts.get(w) == "good"]
    bad = [w for w in order if verdicts.get(w) == "bad"]
    unsure = [w for w in order if verdicts.get(w) == "unsure"]
    print(f"\n[review] saved -> {log_path}")
    print(f"[review] good {len(good)} · bad {len(bad)} · unsure {len(unsure)} · "
          f"unrated {len(order) - len(good) - len(bad) - len(unsure)}")
    if bad:
        print(f"[review] BAD signs to re-export/fix: {bad}")
    if unsure:
        print(f"[review] UNSURE: {unsure}")


# ── glosses (sequence / speech) ───────────────────────────────────────────────
def build_sequence(words: list[str], words_dir: Path, transition: int):
    """Stitch per-word JSON clips with eased transitions (reuses gloss_to_motion).
    Returns (frames, segments, present, missing, fps) — fps taken from the first present clip."""
    import gloss_to_motion as g2m
    clips, missing, fps, got_fps = {}, [], 30, False
    for w in words:
        p = words_dir / f"{w}.json"
        if not p.exists():
            missing.append(w); continue
        arr_w, _s, _g, f_w = load_json_clip(p)
        clips[w] = arr_w
        if not got_fps:
            fps, got_fps = f_w, True
    # Pass the lexicon: without it make_segment() emits no `synthesis` block at all, so this
    # tool — the one used for Deaf review — could not show which hand is synthesized, what the
    # passive handshape should be, or the exemplar's quality tier. Failing soft on purpose: a
    # missing lexicon degrades the overlay, it does not stop a preview from playing.
    try:
        lex = g2m.attach_source_quality(g2m.load_lexicon())
    except Exception as e:                                   # noqa: BLE001 - advisory only
        print(f"[warn] no synthesis overlay ({type(e).__name__}: {e})")
        lex = None
    arr, segments, present, miss2 = g2m.stitch(words, clips, transition, lex)
    return arr, segments, present, missing + [m for m in miss2 if m not in missing], fps


def glosses_from_speech(text: str, vocab_path: Path) -> list[str]:
    raw = json.loads(vocab_path.read_text(encoding="utf-8")) if vocab_path.exists() else {"words": []}
    vocab = raw["words"] if isinstance(raw, dict) else raw
    try:
        import grammar_eval
    except ImportError:
        sys.exit("[err] --speech needs grammar_eval.py in this folder")
    g = grammar_eval.text_to_gloss(text, vocab)
    if not g:
        sys.exit("[err] no glosses produced — Phase 2 needs GEMINI_API_KEYS in .env + internet")
    return g


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="2D preview / Deaf-review player for the per-word sign JSONs")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--word", help="play one word (animation_handoff/words/<word>.json)")
    src.add_argument("--words", help="play a space-separated sequence, e.g. \"hello mom hungry\"")
    src.add_argument("--speech", help="text -> gloss -> play the sequence (needs GEMINI key)")
    src.add_argument("--file", help="play any §1 motion JSON or a reference_pose.json")
    src.add_argument("--pose", action="store_true", help="show the neutral reference pose (static)")
    src.add_argument("--review", action="store_true", help="Deaf-review all 250; save verdicts")
    src.add_argument("--contact", action="store_true", help="write a 250-thumbnail index PNG (headless)")

    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"),
                    help="handoff dir (has words/ and reference_pose.json)")
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"), help="frozen word order for --review")
    ap.add_argument("--save", help="headless export: <name>.mp4/.avi (clip) or .png (mid-frame)")
    ap.add_argument("--raw", action="store_true", help="show real dropouts (don't hold NaN gaps)")
    ap.add_argument("--fps", type=int, default=None, help="override playback fps")
    ap.add_argument("--transition", type=int, default=8, help="blend frames between signs (--words/--speech)")
    ap.add_argument("--start", type=int, default=None, help="--review: start at this 1-based index")
    ap.add_argument("--redo", action="store_true", help="--review: start at #1 even if already rated")
    args = ap.parse_args()

    handoff = Path(args.handoff)
    words_dir = handoff / "words"

    # modes that don't play a single timeline first
    if args.review or args.contact:
        if not words_dir.is_dir():
            sys.exit(f"[err] {words_dir} not found — run: python gloss_to_motion.py --per-word")
        have = [p.stem for p in words_dir.glob("*.json")]
        if not have:
            sys.exit(f"[err] no <word>.json in {words_dir}")
        order = vocab_order(Path(args.vocab), have)
        if args.contact:
            out = Path(args.save) if args.save else handoff / "contact_sheet.png"
            save_contact_sheet(words_dir, order, out)
        else:
            run_review(words_dir, order, handoff / "review_log.json", args.start, args.redo)
        return

    # resolve a single timeline (arr, segments, fps, title)
    if args.pose:
        arr, segments, _g, fps = load_json_clip(handoff / "reference_pose.json")
        title = "reference_pose"
    elif args.file:
        arr, segments, glosses, fps = load_json_clip(Path(args.file))
        title = Path(args.file).stem
    elif args.word:
        arr, segments, _g, fps = load_json_clip(word_path(args.word, words_dir))
        title = args.word
    elif args.words or args.speech:
        words = args.words.split() if args.words else glosses_from_speech(args.speech, Path(args.vocab))
        print(f"[glosses] {words}")
        arr, segments, present, missing, fps = build_sequence(words, words_dir, args.transition)
        if missing:
            print(f"[warn] no clip for {missing} — skipped")
        if arr.shape[0] == 0:
            sys.exit("[err] nothing to play (no clips matched)")
        title = " ".join(present)
    else:
        ap.error("pick one: --word / --words / --speech / --file / --pose / --review / --contact")

    if args.fps is not None:
        if args.fps < 1:
            ap.error("--fps must be >= 1")
        fps = args.fps
    arr = hold_fill(arr, args.raw)

    if args.save:
        save_clip(arr, segments, fps, Path(args.save))
        return

    print(f"[play] {title}  ·  {arr.shape[0]} frames @ {fps}fps  ·  [q] quit  [space] pause  [ ] step")
    play_interactive(arr, segments, fps, title)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
