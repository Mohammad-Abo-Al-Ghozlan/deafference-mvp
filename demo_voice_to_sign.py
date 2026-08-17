#!/usr/bin/env python3
r"""
SPEECH (your VOICE) -> SIGN live demo.

You SPEAK -> Whisper transcribes -> the sentence maps to the 250-word vocab -> the 2D
avatar signs it. On screen you see the transcript, the gloss words, and the signing.

Why two files: faster-whisper (mic->text) is installed only in Python 3.14, and OpenCV
(the display) only in 3.11. So THIS runner lives in the OpenCV interpreter and shells out
to 3.14 for ONLY the mic+transcribe step (_asr_worker.py); glossing + 2D playback happen
here. It reuses demo_speech_to_sign.py for the gloss + render logic.

RUN (in the OpenCV interpreter — the one that runs live_demo.py / preview_signs.py):
  python demo_voice_to_sign.py                 # PRESS-TO-TALK: Enter to start, speak, Enter to stop
  python demo_voice_to_sign.py --fixed --seconds 5   # old behaviour: fixed 5s window
  python demo_voice_to_sign.py --online        # Gemini glossing (auto-falls back to offline)
  python demo_voice_to_sign.py --selftest --save demo/voice_selftest.mp4   # plumbing test, no mic

Press-to-talk is the default: you speak for as long as you like and it signs the moment you
stop — no fixed window cutting you off. Use --fixed if the press-to-talk stop key misbehaves.

FIRST TIME (with internet): run one recording so Whisper downloads its model (~140 MB).
Otherwise the first real utterance will stall while it downloads. Rehearse before the meeting.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

try:
    import cv2  # noqa: F401  (only to fail fast if we're in the wrong interpreter)
except ImportError:
    sys.exit("[err] needs OpenCV — run with the interpreter that runs live_demo.py / preview_signs.py")

import demo_speech_to_sign as d   # reuse: load_vocab, to_glosses_*, sentence_to_signs, play_utterance

HERE = Path(__file__).resolve().parent


def transcribe(asr_cmd, seconds, model, selftest, push=False):
    """Run the 3.14 ASR worker as a subprocess. stderr streams live (so 'SPEAK NOW' / 'press
    Enter to stop' show in real time); stdout is captured and the 'TEXT\\t...' line is the
    transcript. In push mode the worker reads Enter from the SAME console stdin (inherited,
    not redirected) — that's why only stdout is piped here."""
    cmd = list(asr_cmd) + [str(HERE / "_asr_worker.py"), "--seconds", str(seconds), "--model", model]
    if selftest:
        cmd.append("--selftest")
    elif push:
        cmd.append("--push")
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)   # stderr inherits -> live console
    except FileNotFoundError:
        print(f"[err] could not launch the ASR interpreter: '{' '.join(asr_cmd)}'\n"
              f"      set it with --asr-python (e.g. --asr-python \"py -3.14\" or a full python.exe path)")
        return None
    if r.returncode != 0:
        print(f"[err] ASR worker exited {r.returncode} (see [asr] message above)")
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("TEXT\t"):
            return line[len("TEXT\t"):].strip()
    print(f"[err] no transcript in ASR output:\n{r.stdout}")
    return None


def main():
    ap = argparse.ArgumentParser(description="Speak -> 2D avatar signs it (250-word vocab)")
    ap.add_argument("--seconds", type=float, default=4.0, help="fixed-mode recording length (see --fixed)")
    ap.add_argument("--model", default="base", help="whisper model (tiny/base/small)")
    ap.add_argument("--asr-python", default="py -3.14", help="interpreter that has faster-whisper")
    ap.add_argument("--fixed", action="store_true",
                    help="record a fixed --seconds window instead of press-to-talk (the default)")
    ap.add_argument("--online", action="store_true", help="Gemini glossing (auto offline fallback)")
    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--transition", type=int, default=8)
    ap.add_argument("--selftest", action="store_true", help="skip mic/ASR, use a canned sentence")
    ap.add_argument("--save", help="selftest/one-shot: render to mp4/png instead of a window")
    args = ap.parse_args()
    push = not args.fixed                            # press-to-talk is the default

    words_dir = Path(args.handoff) / "words"
    if not words_dir.is_dir():
        sys.exit(f"[err] {words_dir} not found — run: python gloss_to_motion.py --per-word")
    vocab_list = d.load_vocab(Path(args.vocab))
    vocab_set = set(vocab_list)
    # A bare path (e.g. C:\Python314\python.exe) must survive intact; only split when it's
    # a command+args like "py -3.14". POSIX shlex eats Windows backslashes, so guard it.
    _raw = args.asr_python.strip().strip('"').strip("'")
    asr_cmd = [_raw] if Path(_raw).is_file() else shlex.split(args.asr_python, posix=(os.name != "nt"))
    print(f"[cfg] {len(vocab_list)} words · ASR via '{' '.join(asr_cmd)}' · "
          f"{'press-to-talk' if push else f'{args.seconds:.0f}s window'} · "
          f"{'ONLINE' if args.online else 'OFFLINE'} glossing")

    def handle(text, save=None):
        if not text:
            print("[warn] empty transcript — speak clearly and try again."); return "n"
        print(f'  heard:  "{text}"')
        r = d.sentence_to_signs(text, vocab_list, vocab_set, words_dir, args.online, args.transition)
        if r is None:
            return "n"
        arr, segments, glosses, dropped, fps = r
        print(f"  signs: {glosses}" + (f"   (skipped: {dropped})" if dropped else ""))
        return d.play_utterance(arr, segments, text, glosses, dropped, fps, Path(save) if save else None)

    if args.selftest or args.save:      # one-shot: canned (selftest) or ONE real recording -> render/save
        handle(transcribe(asr_cmd, args.seconds, args.model, selftest=args.selftest, push=push), args.save)
        if not args.save:
            cv2.destroyAllWindows()
        return

    rec_hint = ("Enter to start recording, speak, then Enter again to stop"
                if push else f"Enter to record a {args.seconds:.0f}s window")
    print(f"\nPress {rec_hint}. Type 'q' + Enter to quit.\n"
          "  In the sign window: [space] pause · [n]/Enter next · [q] quit\n")
    while True:
        try:
            cmd = input("speak > (Enter to record) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd in ("q", "quit", "exit"):
            break
        try:
            if handle(transcribe(asr_cmd, args.seconds, args.model, selftest=False, push=push)) == "q":
                break
        except KeyboardInterrupt:                    # Ctrl-C mid-record/download/play -> cancel, re-prompt
            print("\n[cancelled] — press Enter to try again, or 'q' to quit.")
            continue
    cv2.destroyAllWindows()
    print("bye.")


if __name__ == "__main__":
    main()
