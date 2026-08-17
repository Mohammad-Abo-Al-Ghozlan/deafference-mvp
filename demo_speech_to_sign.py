#!/usr/bin/env python3
r"""
SPEECH -> SIGN live demo (meeting build).  Type any sentence -> see the TEXT -> the 2D
avatar signs it, using the 250-word vocabulary.

Pipeline shown on screen:  sentence (English)  ->  GLOSS words (our 250 vocab)  ->  2D signing.

Two text->gloss modes:
  * OFFLINE (default) — deterministic: keep the sentence's words that exist in the 250
    vocab (with light normalization: plurals, a few synonyms; ASL function words dropped).
    NO internet, NO API key -> it CANNOT fail live. Use this for the meeting.
  * ONLINE (--online) — sends the sentence to Gemini for proper ASL glossing/reordering
    (needs internet + GEMINI_API_KEYS). Falls back to OFFLINE automatically on any error.

RUN (use the interpreter that has OpenCV — the one that runs live_demo.py / preview_signs.py):
  python demo_speech_to_sign.py                          # interactive: type sentences in a loop
  python demo_speech_to_sign.py --text "hello mom I am hungry please"
  python demo_speech_to_sign.py --text "thank you" --online
  python demo_speech_to_sign.py --text "I am thirsty" --save thirsty.mp4   # headless -> shareable video

Keys while a sign plays:  [space] pause · [n]/Enter next sentence · [q]/Esc quit · [X] close = next.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("[err] needs OpenCV:  pip install opencv-python  (use the interpreter that runs live_demo.py)")

import preview_signs as ps   # reuse clip loading / stitching / rendering

HERE = Path(__file__).resolve().parent

# ASL commonly omits these; dropping them silently is correct, not an error.
# (In-vocab words like "on"/"that"/"will" are NOT here — they are signed, see to_glosses_offline.)
STOPWORDS = {
    "i", "me", "my", "you", "he", "she", "they", "am", "is", "are", "was", "were", "be",
    "been", "a", "an", "the", "to", "of", "do", "does", "did", "would", "and", "at",
    # contraction forms (the apostrophe is stripped before this check, so match the bare form)
    "im", "ive", "ill", "id", "dont", "cant", "wont", "its", "youre", "theyre", "hes",
    "shes", "lets", "thats",
}
# tiny, safe synonym map into the 250 vocab (children's-sign set)
SYNONYMS = {
    "hi": "hello", "hey": "hello", "mommy": "mom", "mama": "mom", "mum": "mom",
    "daddy": "dad", "papa": "dad", "thanks": "thankyou", "thank": "thankyou",
    "tired": "sleepy", "bathroom": "potty", "toilet": "potty", "kitten": "kitty",
    "doggy": "dog", "doggie": "dog", "birdie": "bird", "cellphone": "callonphone",
    "fries": "frenchfries",
}


def load_vocab(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"[err] vocab not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"[err] {path.name} is not valid JSON: {e}")
    except OSError as e:
        raise SystemExit(f"[err] cannot read {path}: {e}")
    return raw["words"] if isinstance(raw, dict) else raw


def _singular_candidates(w: str) -> list[str]:
    """Plural -> singular guesses, most-reliable first (caller keeps the first in vocab)."""
    c = []
    if w.endswith("s") and len(w) > 1:
        c.append(w[:-1])                    # cats->cat, trees->tree
    if w.endswith("ies") and len(w) > 3:
        c.append(w[:-3] + "y")              # kitties->kitty, puppies->puppy
    if w.endswith("es") and len(w) > 2:
        c.append(w[:-2])                    # dishes->dish
    return c


def to_glosses_offline(sentence: str, vocab: set[str]):
    """Deterministic sentence -> in-vocab gloss list. Returns (glosses, dropped_content_words)."""
    toks = re.findall(r"[a-zA-Z']+", sentence.lower())
    glosses, dropped = [], []
    for t in toks:
        w = t.replace("'", "")                       # don't -> dont, thank's -> thanks
        if not w:
            continue
        if w in vocab:                               # an in-vocab word ALWAYS wins (on/that/will/...)
            glosses.append(w); continue
        if w in STOPWORDS:                           # ASL drops these — silent, not an error
            continue
        if w in SYNONYMS and SYNONYMS[w] in vocab:
            glosses.append(SYNONYMS[w]); continue
        cand = next((c for c in _singular_candidates(w) if c in vocab), None)
        if cand:
            glosses.append(cand); continue
        dropped.append(t)                            # a real content word we can't sign
    return glosses, dropped


def to_glosses_online(sentence: str, vocab_list: list[str]):
    """Gemini glossing; returns None on any failure so the caller falls back to offline."""
    try:
        import grammar_eval
        g = grammar_eval.text_to_gloss(sentence, vocab_list)
        g = [w for w in (g or []) if w in set(vocab_list)]
        return g or None
    except Exception as e:
        print(f"[online] gloss failed ({e}) -> using offline")
        return None


# ── on-screen presentation ────────────────────────────────────────────────────
def _seg_index(segments, t) -> int:
    """Index of the segment (word) whose frame range contains t, else -1 (a transition)."""
    for i, s in enumerate(segments):
        if s["start"] <= t < s["end"]:
            return i
    return -1


def make_hud(sentence: str, glosses: list[str], dropped: list[str], cur_idx: int):
    lines = [("Deafference  |  SPEECH -> SIGN", (120, 220, 255))]
    lines.append((f'You said:  "{sentence}"', (240, 240, 240)))
    if glosses:                                      # highlight by POSITION, so repeats don't all light up
        row = "Signs:  " + "  ".join((f"[{g}]" if i == cur_idx else g) for i, g in enumerate(glosses))
        lines.append((row, (200, 255, 200)))
    if 0 <= cur_idx < len(glosses):
        lines.append((f">> {glosses[cur_idx].upper()}", (90, 220, 90)))
    if dropped:
        lines.append((f"(not in 250 vocab, skipped: {', '.join(dropped)})", (140, 140, 140)))
    return lines


def play_utterance(arr, segments, sentence, glosses, dropped, fps, save: Path | None):
    """Render the signing with the sentence+gloss HUD. Headless if `save`, else a window.
    Returns 'q' to quit the whole demo, else 'n' for next."""
    T = arr.shape[0]
    if save is not None:
        ext = save.suffix.lower()
        if ext in ps.VIDEO_EXT:
            vw = cv2.VideoWriter(str(save), cv2.VideoWriter_fourcc(*("mp4v" if ext == ".mp4" else "XVID")),
                                 float(max(1, fps)), (ps.CANVAS_W, ps.CANVAS_H))
            if not vw.isOpened():
                raise SystemExit(f"[err] could not open video writer for {save}")
            for t in range(T):
                vw.write(ps.render_frame(arr[t], make_hud(sentence, glosses, dropped, _seg_index(segments, t))))
            vw.release(); print(f"[ok] wrote {T} frames -> {save}")
        elif ext in ps.IMAGE_EXT:
            t = T // 2
            if not cv2.imwrite(str(save), ps.render_frame(arr[t], make_hud(sentence, glosses, dropped, _seg_index(segments, t)))):
                raise SystemExit(f"[err] failed to write {save}")
            print(f"[ok] wrote frame {t} -> {save}")
        else:
            raise SystemExit(f"[err] --save must be a video or image path (got '{save.suffix or 'none'}')")
        return "n"

    delay = max(1, int(round(1000.0 / max(1, fps))))
    t, paused = 0, False
    win = "deafference-demo"
    while True:
        cv2.imshow(win, ps.render_frame(arr[t], make_hud(sentence, glosses, dropped, _seg_index(segments, t))))
        k = cv2.waitKey(delay) & 0xFF
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:   # user clicked the window's [X]
            return "n"
        if k in (ord("q"), 27):
            cv2.destroyWindow(win); return "q"
        if k in (ord("n"), 13, 10):                 # n / Enter -> next sentence
            cv2.destroyWindow(win); return "n"
        if k == ord(" "):
            paused = not paused
        if not paused:
            t = (t + 1) % T


def sentence_to_signs(sentence, vocab_list, vocab_set, words_dir, online, transition):
    """Full text -> gloss -> stitched motion. Returns (arr, segments, glosses, dropped, fps) or None."""
    # Always compute the offline "dropped" list so unsignable content words are shown on
    # screen in BOTH modes (the online path used to hide them).
    off_glosses, dropped = to_glosses_offline(sentence, vocab_set)
    glosses = to_glosses_online(sentence, vocab_list) if online else None
    if glosses is None:                              # offline (default, or online fallback)
        glosses = off_glosses
    if not glosses:
        print("[warn] no signable words in that sentence (nothing in the 250 vocab).")
        return None
    arr, segments, present, missing, fps = ps.build_sequence(glosses, words_dir, transition)
    if missing:
        print(f"[warn] no clip for {missing} (skipped)")
    if arr.shape[0] == 0:
        print("[warn] nothing to play."); return None
    return ps.hold_fill(arr, raw=False), segments, present, dropped, fps


def main():
    ap = argparse.ArgumentParser(description="Type a sentence -> 2D avatar signs it (250-word vocab)")
    ap.add_argument("--text", help="one sentence to sign; omit for an interactive loop")
    ap.add_argument("--online", action="store_true", help="use Gemini for glossing (falls back to offline)")
    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"), help="dir with words/*.json")
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--save", help="headless: write the signing to <name>.mp4 / .png instead of a window")
    ap.add_argument("--transition", type=int, default=8, help="blend frames between signs")
    args = ap.parse_args()

    words_dir = Path(args.handoff) / "words"
    if not words_dir.is_dir():
        sys.exit(f"[err] {words_dir} not found — run: python gloss_to_motion.py --per-word")
    vocab_list = load_vocab(Path(args.vocab))
    vocab_set = set(vocab_list)
    print(f"[cfg] {len(vocab_list)} words · {'ONLINE (Gemini, offline fallback)' if args.online else 'OFFLINE (deterministic)'}")

    def run_one(sentence, save=None):
        r = sentence_to_signs(sentence, vocab_list, vocab_set, words_dir, args.online, args.transition)
        if r is None:
            return "n"
        arr, segments, glosses, dropped, fps = r
        print(f'  "{sentence}"  ->  signs: {glosses}' + (f"   (skipped: {dropped})" if dropped else ""))
        return play_utterance(arr, segments, sentence, glosses, dropped, fps, Path(save) if save else None)

    if args.text is not None:
        run_one(args.text, args.save)
        if not args.save:
            cv2.destroyAllWindows()
        return

    # interactive loop — type sentences until 'q'
    print("\nType a sentence (words from the 250 vocab). 'q' to quit.\n"
          "  In the sign window: [space] pause · [n]/Enter next · [q] quit\n")
    while True:
        try:
            sentence = input("speak > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if sentence.lower() in ("q", "quit", "exit"):
            break
        if not sentence:
            continue
        if run_one(sentence) == "q":
            break
    cv2.destroyAllWindows()
    print("bye.")


if __name__ == "__main__":
    main()
