#!/usr/bin/env python3
r"""
SPEECH -> SIGN pipeline harness (Days 1-3), ASL-250.

Runs and PRINTS each phase so you can validate the front half before building the
avatar renderer (Day 4):

  Phase 1  ASR      : audio -> spoken text        (Whisper; or --text to skip)
  Phase 2  TEXT->GLOSS : text -> ASL glosses       (grammar_eval.text_to_gloss, vocab-locked)
  Phase 3  RESOLVE  : glosses -> playable clips     (check against sign_clips_250.npz)

Day 4 (the 2D avatar renderer) plugs onto Phase 3's output.

RUN — test with typed text first (NO mic / NO install needed):
  python speech_to_sign.py --text "hello mom I am hungry please"
  python speech_to_sign.py --text "thank you, goodbye" --words demo_vocab_250.json

RUN — with speech (needs `pip install faster-whisper sounddevice`):
  python speech_to_sign.py --mic --seconds 4          # record 4s from the mic
  python speech_to_sign.py --audio clip.wav           # transcribe a file

Phase 2 needs GEMINI_API_KEYS in .env (same key the live demo uses).
Phase 3 needs sign_clips_250.npz (built by training/build_sign_clips.py on Kaggle);
if it's absent, Phase 3 still validates glosses against the vocab so Days 1-2 test.
"""
import os
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_dotenv():
    """Load KEY=VALUE from ./.env so Phase 2 can read GEMINI_API_KEYS (same as live_demo)."""
    p = HERE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


# ── Phase 1 — ASR (speech -> text) ────────────────────────────────────────────
def record_mic(seconds: float, samplerate: int = 16000):
    """Record `seconds` of mono audio from the default mic -> float32 numpy (or None)."""
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("[err] --mic needs sounddevice:  pip install sounddevice")
    import numpy as np
    print(f"[1 ASR] recording {seconds:.0f}s from mic — speak now...")
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="float32")
    sd.wait()
    return audio.reshape(-1), samplerate


def transcribe(audio, samplerate, lang):
    """Whisper transcription of a float32 waveform (or a file path). Returns text."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("[err] ASR needs faster-whisper:  pip install faster-whisper\n"
                 "      (or use --text \"...\" to skip ASR and test Phases 2-3)")
    model_size = os.environ.get("WHISPER_MODEL", "base")
    print(f"[1 ASR] loading Whisper '{model_size}' (first run downloads it)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, info = model.transcribe(audio, language=lang, beam_size=1)
    text = " ".join(s.text.strip() for s in segs).strip()
    return text


# ── Phase 3 — resolve glosses to playable clips ───────────────────────────────
def load_clip_words(clips_path: Path):
    """Return the set of words that have an animation clip, or None if the dict is absent."""
    if not clips_path.exists():
        return None
    import numpy as np
    with np.load(clips_path) as z:
        return set(z.files)


def main():
    ap = argparse.ArgumentParser(description="Speech->Sign pipeline test (Days 1-3)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="skip ASR: use this typed sentence (Phases 2-3 only)")
    src.add_argument("--mic", action="store_true", help="record from the microphone (Phase 1)")
    src.add_argument("--audio", help="transcribe this audio file (Phase 1)")
    ap.add_argument("--seconds", type=float, default=4.0, help="--mic record length")
    ap.add_argument("--lang", default="en", help="ASR language (en; ar for Arabic)")
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"),
                    help="full class vocab (glosses are restricted to this)")
    ap.add_argument("--words", default=None,
                    help="optional subset JSON (e.g. demo_vocab_250.json) to further restrict")
    ap.add_argument("--clips", default=str(HERE / "sign_clips_250.npz"),
                    help="animation clip dictionary (from build_sign_clips.py)")
    ap.add_argument("--out", default=None,
                    help="write the stitched §1 motion JSON here (Phase 3; needs the clip dict)")
    args = ap.parse_args()

    # allowed vocabulary for Phase 2 (full 250, optionally narrowed to a subset)
    raw = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
    vocab = raw["words"] if isinstance(raw, dict) else raw
    allowed = vocab
    if args.words:
        sub = json.loads(Path(args.words).read_text(encoding="utf-8"))
        sub = sub["words"] if isinstance(sub, dict) else sub
        allowed = [w for w in vocab if w in set(sub)]
    print(f"[cfg] {len(allowed)} allowed glosses"
          + (f" (subset {Path(args.words).name})" if args.words else " (full 250)"))

    # ── Phase 1 ──
    if args.text is not None:
        text = args.text.strip()
        print(f"[1 ASR] (skipped — typed) text: \"{text}\"")
    elif args.mic:
        audio, sr = record_mic(args.seconds)
        text = transcribe(audio, sr, args.lang)
        print(f"[1 ASR] transcript: \"{text}\"")
    else:
        text = transcribe(args.audio, 16000, args.lang)
        print(f"[1 ASR] transcript ({args.audio}): \"{text}\"")
    if not text:
        sys.exit("[err] empty transcript — nothing to translate")

    # ── Phase 2 ──
    import grammar_eval
    glosses = grammar_eval.text_to_gloss(text, allowed)
    print(f"[2 GLOSS] glosses: {glosses or '(none — check GEMINI_API_KEYS / rephrasing)'}")
    if not glosses:
        sys.exit("[err] no glosses produced — Phase 2 needs GEMINI_API_KEYS set + internet")

    # ── Phase 3 — resolve glosses to a stitched landmark MOTION STREAM (contract §1) ──
    clips_path = Path(args.clips)
    if not clips_path.exists():
        print(f"[3 RESOLVE] clip dict not found ({clips_path.name}) — validating vs vocab only.")
        ok = [g for g in glosses if g in set(allowed)]
        missing = [g for g in glosses if g not in set(allowed)]
        print(f"[3 RESOLVE] in-vocab: {ok}" + (f"   MISSING: {missing}" if missing else ""))
        print("\n→ Phases 1-2 OK. Build sign_clips_250.npz (training/build_sign_clips.py on Kaggle) "
              "to complete Phase 3 — then this step emits the animation stream.")
        return
    import gloss_to_motion
    contract, present, missing = gloss_to_motion.glosses_to_contract(glosses, clips_path)
    nfr = len(contract["frames"])
    print(f"[3 STITCH] {len(present)}/{len(glosses)} glosses have clips -> "
          f"{nfr} frames ({nfr / contract['fps']:.1f}s @ {contract['fps']}fps)")
    if missing:
        print(f"[3 STITCH] NO CLIP for: {missing} (skipped)")
    out = Path(args.out) if args.out else HERE / "motion_stream.json"
    gloss_to_motion.write_json(contract, out)
    print(f"[3 STITCH] wrote animation stream -> {out.name}  (SIGN_ANIMATION_CONTRACT §1)")
    print(f"\n→ Phase 3 DONE. Hand {out.name} to the renderer, or run "
          "`python gloss_to_motion.py --samples` for the teammate starter-pack.")


if __name__ == "__main__":
    main()
