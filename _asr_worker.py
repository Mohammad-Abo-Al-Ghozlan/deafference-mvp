#!/usr/bin/env python3
r"""
ASR worker — runs in the Python 3.14 interpreter (the one with faster-whisper).

Records N seconds from the microphone, transcribes with Whisper, and prints the
transcript on a single line prefixed 'TEXT\t'. All progress/errors go to STDERR so
STDOUT carries only the transcript. Invoked as a subprocess by demo_voice_to_sign.py
(which runs in the OpenCV / 3.11 interpreter and cannot import faster-whisper).

  py -3.14 _asr_worker.py --push          # press-to-talk: record until Enter is pressed
  py -3.14 _asr_worker.py --seconds 4     # fixed-length window
  py -3.14 _asr_worker.py --wav clip.wav  # transcribe a WAV (the GUI records it in 3.11)
  py -3.14 _asr_worker.py --serve         # stay alive: load the model ONCE, transcribe on demand
  py -3.14 _asr_worker.py --selftest      # no mic / no model — prints a canned transcript

--serve protocol (used by demo_voice_gui.py): loading the model costs ~3 s, and a one-shot
process pays that on EVERY utterance (~5.5 s total). Serving keeps it in memory so each
utterance costs only the transcribe (~1.9 s). stdin: one WAV path per line, or 'QUIT'.
stdout: 'READY' once loaded, then one 'TEXT\t<transcript>' or 'ERR\t<message>' per request.
"""
import argparse
import sys


def load_wav(path, want_sr=16000):
    """Read a 16-bit PCM WAV into a 1-D float32 array in [-1, 1] at `want_sr`.

    Stereo is averaged to mono. The GUI always writes 16 kHz mono (what Whisper wants), but a
    WAV from anywhere else may not — feeding Whisper the wrong rate makes it transcribe
    gibberish rather than fail loudly, so resample instead of trusting the caller.
    """
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        nframes, channels, width, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(nframes)
    if width != 2:
        raise ValueError(f"expected 16-bit PCM WAV, got {width * 8}-bit")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        a = a.reshape(-1, channels).mean(axis=1)
    if sr != want_sr and a.size:                     # linear resample — fine for speech ASR
        n_out = int(round(a.size * want_sr / float(sr)))
        a = np.interp(np.linspace(0, a.size - 1, n_out, dtype=np.float64),
                      np.arange(a.size, dtype=np.float64), a).astype(np.float32)
        print(f"[asr] resampled {sr} Hz -> {want_sr} Hz", file=sys.stderr)
    return a


def _one_line(text):
    """Collapse to a single line — the protocol is one response per line."""
    return " ".join(str(text).split())


def serve(model_name, lang):
    """Persistent mode: load the model once, then transcribe a WAV per stdin line.
    Any failure is reported as 'ERR\\t...' and the loop continues, so one bad clip does not
    kill the server (the parent falls back to one-shot mode only if the process actually dies)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as e:
        print("ERR\tmodel load failed: " + _one_line(e), flush=True)
        sys.exit(5)
    print("READY", flush=True)

    for line in sys.stdin:
        path = line.strip()
        if not path or path == "QUIT":
            break
        try:
            audio = load_wav(path)
            if audio.size == 0:
                print("TEXT\t", flush=True); continue
            segs, _info = model.transcribe(audio, language=lang, beam_size=1)
            print("TEXT\t" + _one_line(" ".join(s.text.strip() for s in segs)), flush=True)
        except Exception as e:
            print("ERR\t" + _one_line(e), flush=True)


def record_push(sd, samplerate):
    """Press-to-talk: open a mic stream and record until the user presses Enter, however long
    that takes. Returns a float32 array shaped (N, 1). The InputStream callback fills `frames`
    on PortAudio's thread while the main thread blocks on input(); leaving the `with` stops it."""
    import numpy as np
    frames = []

    def _cb(indata, _n, _t, _status):
        frames.append(indata.copy())

    print("[asr] SPEAK NOW — press Enter to stop.", file=sys.stderr, flush=True)
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", callback=_cb):
        try:
            input()                      # blocks here until the user hits Enter
        except EOFError:
            pass
    return np.concatenate(frames, axis=0) if frames else np.zeros((0, 1), dtype="float32")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--samplerate", type=int, default=16000)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--model", default="base", help="whisper size: tiny/base/small")
    ap.add_argument("--push", action="store_true",
                    help="press-to-talk: record until Enter is pressed (ignores --seconds)")
    ap.add_argument("--wav", help="transcribe this 16 kHz PCM WAV instead of recording from a mic")
    ap.add_argument("--serve", action="store_true",
                    help="stay alive: load the model once, read WAV paths from stdin (see protocol above)")
    ap.add_argument("--selftest", action="store_true", help="skip mic+ASR, print a canned transcript")
    args = ap.parse_args()

    if args.selftest:
        print("TEXT\thello mom I am hungry please")
        return

    if args.serve:
        serve(args.model, args.lang)
        return

    if args.wav:                                     # GUI path: audio already captured to a file
        try:
            audio = load_wav(args.wav)
        except Exception as e:
            print(f"[asr] could not read WAV '{args.wav}': {e}", file=sys.stderr); sys.exit(6)
    else:
        try:
            import sounddevice as sd
        except Exception as e:
            print(f"[asr] sounddevice import failed: {e}", file=sys.stderr); sys.exit(3)
        try:
            if args.push:
                audio = record_push(sd, args.samplerate)
            else:
                print(f"[asr] SPEAK NOW — recording {args.seconds:.0f}s...", file=sys.stderr, flush=True)
                audio = sd.rec(int(args.seconds * args.samplerate), samplerate=args.samplerate,
                               channels=1, dtype="float32")
                sd.wait()
        except Exception as e:
            print(f"[asr] recording failed ({e}) — is a microphone connected?", file=sys.stderr); sys.exit(4)
        audio = audio.reshape(-1)

    if audio.size == 0:                              # push mode, Enter pressed before any speech
        print("[asr] nothing recorded — stopped too quickly.", file=sys.stderr)
        print("TEXT\t")
        return

    print("[asr] transcribing...", file=sys.stderr, flush=True)
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        segs, _info = model.transcribe(audio, language=args.lang, beam_size=1)
        text = " ".join(s.text.strip() for s in segs).strip()
    except Exception as e:
        print(f"[asr] transcription failed: {e}", file=sys.stderr); sys.exit(5)

    print("TEXT\t" + text)


if __name__ == "__main__":
    main()
