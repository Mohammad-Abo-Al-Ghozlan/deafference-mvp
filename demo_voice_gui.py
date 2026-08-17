#!/usr/bin/env python3
r"""
SPEECH -> SIGN — clickable GUI (meeting build).

A single window: click [Record], speak, click [Stop]. It transcribes your voice, maps the
sentence to the 250-word vocab, and the 2D avatar signs it right inside the window.

Why it can be one clean window (no Enter-key hack): the mic recording (sounddevice) and the
display (OpenCV drawing + Tkinter) both live in the 3.11 interpreter, so THIS process records
the audio itself. Only Whisper is 3.14-only, so we hand it just the recorded WAV file:
    3.11 GUI:  mic -> record -> clip.wav ---> (subprocess) py -3.14 _asr_worker.py --wav clip.wav
    3.14:      clip.wav -> Whisper -> transcript ---> back to 3.11 -> gloss -> 2D avatar
Glossing + rendering reuse demo_speech_to_sign.py / preview_signs.py unchanged.

RUN (in the OpenCV / 3.11 interpreter — the one that runs live_demo.py):
  python demo_voice_gui.py
  python demo_voice_gui.py --model small     # more accurate ASR (slower)
  python demo_voice_gui.py --online          # Gemini glossing (auto-falls back to offline)

SPEED: the Whisper model loads ONCE into a persistent 3.14 helper at startup (~4 s, in the
background — the window is usable immediately, and the status line turns to "Ready"). After
that each utterance costs only the transcribe: ~2 s from clicking Stop to the avatar signing.
Without that helper it would reload the model every time (~6 s of dead air per sentence).

FIRST RUN needs internet to fetch the model (~140 MB for 'base'), cached from then on.

Shortcuts: [Space] = Record / Stop · [Esc] = quit.
The terminal version demo_voice_to_sign.py still exists as a fallback if the GUI ever misbehaves.
"""
from __future__ import annotations

import argparse
import os
import queue
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("[err] needs OpenCV — run with the interpreter that runs live_demo.py / preview_signs.py")
try:
    import tkinter as tk
    from tkinter import font as tkfont
except Exception as e:                                # pragma: no cover
    sys.exit(f"[err] Tkinter unavailable: {e}")

import demo_speech_to_sign as d     # reuse: load_vocab, sentence_to_signs, make_hud, _seg_index
import preview_signs as ps          # reuse: render_frame, CANVAS_W/H

HERE = Path(__file__).resolve().parent
SR = 16000                                            # Whisper wants 16 kHz mono
TARGET_H = 680                                        # displayed avatar height (fits a laptop screen)
SCALE = TARGET_H / ps.CANVAS_H
DISP_W, DISP_H = int(ps.CANVAS_W * SCALE), TARGET_H

BG = "#14171a"
FG = "#e6e6e6"
GREEN = "#1f9d55"
RED = "#d64545"
GREY = "#555b61"


class VoiceSignApp:
    def __init__(self, root, args):
        self.root = root
        self.model = args.model
        self.online = args.online
        self.transition = args.transition
        self.words_dir = Path(args.handoff) / "words"
        self.vocab_list = d.load_vocab(Path(args.vocab))
        self.vocab_set = set(self.vocab_list)

        _raw = args.asr_python.strip().strip('"').strip("'")
        self.asr_cmd = [_raw] if Path(_raw).is_file() else shlex.split(args.asr_python, posix=(os.name != "nt"))

        self.state = "idle"
        self.stream = None
        self.rec_frames: list = []
        self._play = None                              # active playback context, if any
        self._closed = False                           # set on exit so worker threads stop posting back
        self._srv = None                               # persistent ASR process (model stays loaded)
        self._srv_lock = threading.Lock()              # one request at a time on the pipe
        self._srv_dead = False                         # spawn failed -> stop retrying, use one-shot
        self._q = queue.Queue()                        # worker threads -> Tk main thread

        self._build_ui()
        self._set_state("idle", status="Loading speech model…  (you can click Record already)")
        self._pump()                                   # main-thread drain loop for _post()
        threading.Thread(target=self._warm_server, daemon=True).start()
        self._show(self._placeholder([
            ("Deafference", (120, 220, 255)),
            ("Speech  ->  Sign", (200, 255, 200)),
            ("Click Record and speak", (200, 200, 200)),
        ]))

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.root.title("Deafference — Speech to Sign")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        big = tkfont.Font(family="Segoe UI", size=13)
        huge = tkfont.Font(family="Segoe UI", size=17, weight="bold")

        tk.Label(self.root, text="Deafference  ·  Speech → Sign  (250 words)",
                 bg=BG, fg="#78c8ff", font=huge).pack(pady=(12, 6))

        self.canvas_label = tk.Label(self.root, bg=BG, bd=0)
        self.canvas_label.pack(padx=16)

        self.status = tk.Label(self.root, text="", bg=BG, fg=FG, font=big, wraplength=DISP_W)
        self.status.pack(pady=(8, 4))

        # takefocus=0: a focused Tk button fires its own command on Space, which would
        # double-toggle against the <space> binding below (start + instant stop).
        self.btn = tk.Button(self.root, text="●  Record", command=self._toggle,
                             font=huge, fg="white", bg=GREEN, activeforeground="white",
                             activebackground=GREEN, bd=0, relief="flat", padx=28, pady=12,
                             cursor="hand2", takefocus=0)
        self.btn.pack(pady=(4, 16))

        self.root.bind("<space>", lambda _e: self._toggle())
        self.root.bind("<Escape>", lambda _e: self._on_close())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # Tkinter is not thread-safe, and root.after() from a worker thread raises RuntimeError
    # ("main thread is not in main loop") — which would silently drop a finished transcript.
    # So worker threads only ever _post() a callable, and the Tk thread runs it in _pump().
    def _post(self, fn):
        self._q.put(fn)

    def _pump(self):
        if self._closed:
            return
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:                     # never let one callback kill the pump
                print(f"[warn] UI callback failed: {e}")
        self.root.after(40, self._pump)

    def _set_state(self, state, status=None):
        self.state = state
        label, color, enabled = {
            "idle":      ("●  Record",       GREEN, True),
            "recording": ("■  Stop",         RED,   True),
            "busy":      ("…  Transcribing", GREY,  False),
            "playing":   ("●  Record again", GREEN, True),
        }[state]
        self.btn.config(text=label, bg=color, activebackground=color,
                        state=("normal" if enabled else "disabled"))
        if status is not None:
            self.status.config(text=status)

    def _placeholder(self, lines):
        img = np.full((DISP_H, DISP_W, 3), (26, 23, 20), np.uint8)
        y = DISP_H // 2 - (len(lines) * 34) // 2
        for i, (txt, col) in enumerate(lines):
            (tw, _th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
            cv2.putText(img, txt, ((DISP_W - tw) // 2, y + i * 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2, cv2.LINE_AA)
        return img

    def _show(self, frame_bgr):
        """Blit a BGR frame into the Tkinter label.

        Uses an UNCOMPRESSED PPM (P6) buffer, not PNG. Measured on this machine: PNG encode
        + Tk's PNG decode cost ~38 ms/frame (≈7 fps — a slideshow), while PPM costs ~7 ms.
        Likewise INTER_LINEAR instead of INTER_AREA for the downscale (~17 ms -> ~5 ms).
        Together that's what makes the avatar play at full speed inside the window.
        """
        if frame_bgr.shape[:2] != (DISP_H, DISP_W):
            frame_bgr = cv2.resize(frame_bgr, (DISP_W, DISP_H), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)   # Tk expects RGB; OpenCV gives BGR
        h, w = rgb.shape[:2]
        photo = tk.PhotoImage(data=b"P6 %d %d 255 " % (w, h) + rgb.tobytes())
        self.canvas_label.config(image=photo)
        self.canvas_label.image = photo               # keep a ref so Tk doesn't GC it

    # ── record ──────────────────────────────────────────────────────────────────
    def _toggle(self):
        if self.state in ("idle", "playing"):
            self._start_recording()
        elif self.state == "recording":
            self._stop_recording()

    def _start_recording(self):
        try:
            import sounddevice as sd
        except Exception as e:
            self._set_state("idle", status=f"No audio backend: {e}"); return
        self._play = None                              # cancel any looping playback
        self.rec_frames = []
        try:
            self.stream = sd.InputStream(
                samplerate=SR, channels=1, dtype="float32",
                callback=lambda indata, _n, _t, _s: self.rec_frames.append(indata.copy()))
            self.stream.start()
        except Exception as e:
            self.stream = None
            self._set_state("idle", status=f"Mic error: {e}"); return
        self._set_state("recording", status="Recording…  click Stop (or Space) when you finish.")

    def _stop_recording(self):
        try:
            if self.stream is not None:
                self.stream.stop(); self.stream.close()
        except Exception:
            pass
        self.stream = None
        audio = np.concatenate(self.rec_frames).reshape(-1) if self.rec_frames else np.zeros(0, np.float32)
        if audio.size < int(SR * 0.25):                # under ~0.25 s of audio
            self._set_state("idle", status="Too short — click Record, speak, then Stop."); return
        self._set_state("busy", status="Transcribing…")
        wav_path = self._write_wav(audio)
        self._start_transcribe(wav_path)

    def _write_wav(self, audio):
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="deaf_voice_")
        os.close(fd)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return path

    # ── transcribe (background thread) ───────────────────────────────────────────
    def _start_transcribe(self, wav_path):
        def work():
            try:
                text, err = self._run_worker(wav_path)
            except Exception as e:
                text, err = None, str(e)
            # hop back to the Tk thread — never touch widgets from here. If the window was
            # closed while Whisper was running, drop the result instead of poking a dead root.
            if not self._closed:
                self._post(lambda: self._on_transcript(text, err, wav_path))
        threading.Thread(target=work, daemon=True).start()

    # The ASR model lives in the 3.14 interpreter and takes ~3 s to load. A one-shot process
    # per utterance pays that every time (~5.5 s of dead air); a persistent server pays it once
    # at startup, so each utterance costs only the transcribe (~1.9 s). One-shot stays as the
    # fallback path if the server cannot start or dies mid-demo.
    def _warm_server(self):
        """Background: start the ASR server so the model is loaded before the first utterance."""
        with self._srv_lock:
            ok, reason = self._spawn_server()
        msg = {
            "ok": "Ready — click Record and speak a sentence.",
            # honest about which half failed, since the fixes are different
            "model": "Speech model didn't load (see console) — will retry when you record.",
            "nostart": f"Can't start the speech engine ('{' '.join(self.asr_cmd)}') — check --asr-python.",
        }[reason if not ok else "ok"]
        self._post(lambda: self.status.config(text=msg) if self.state == "idle" else None)

    def _spawn_server(self):
        """Start `_asr_worker.py --serve` and block until it reports READY. Caller holds the lock.
        Returns (ok, reason) where reason is 'ok' | 'model' (loaded failed) | 'nostart' (no process)."""
        if self._srv_dead:
            return False, "nostart"
        cmd = list(self.asr_cmd) + [str(HERE / "_asr_worker.py"), "--serve", "--model", self.model]
        try:
            # stderr is inherited on purpose: first-run model download progress shows in the console.
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 text=True, bufsize=1)
        except (OSError, ValueError):
            self._srv_dead = True
            return False, "nostart"
        while True:                                   # wait for READY (or death / an ERR line)
            line = p.stdout.readline()
            if line == "":                            # process exited without READY
                self._srv_dead = True                 # bad interpreter / missing deps: don't retry
                return False, "nostart"
            line = line.strip()
            if line == "READY":
                self._srv = p
                return True, "ok"
            if line.startswith("ERR\t"):              # interpreter fine, model load failed
                try:
                    p.kill()
                except OSError:
                    pass
                return False, "model"

    def _server_transcribe(self, wav_path):
        """One request on the persistent pipe. Returns (text, err) or None if the server is gone."""
        with self._srv_lock:
            if self._srv is None or self._srv.poll() is not None:
                if not self._spawn_server()[0]:
                    return None
            try:
                self._srv.stdin.write(wav_path + "\n")
                self._srv.stdin.flush()
                line = self._srv.stdout.readline()
            except (OSError, ValueError):
                self._srv = None
                return None
            if line == "":                            # server died mid-request
                self._srv = None
                return None
            line = line.rstrip("\n")
            if line.startswith("TEXT\t"):
                return line[len("TEXT\t"):].strip(), None
            if line.startswith("ERR\t"):
                return None, line[len("ERR\t"):].strip()
            return None, f"unexpected ASR reply: {line[:80]}"

    def _run_worker(self, wav_path):
        """Transcribe via the persistent server; fall back to a one-shot process if unavailable."""
        got = self._server_transcribe(wav_path)
        if got is not None:
            return got
        cmd = list(self.asr_cmd) + [str(HERE / "_asr_worker.py"), "--wav", wav_path, "--model", self.model]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except (FileNotFoundError, OSError):
            return None, f"could not launch ASR: {' '.join(self.asr_cmd)} (set --asr-python)"
        if r.returncode != 0:
            tail = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            return None, (tail[-1] if tail else f"ASR worker exited {r.returncode}")
        for line in (r.stdout or "").splitlines():
            if line.startswith("TEXT\t"):
                return line[len("TEXT\t"):].strip(), None
        return None, "ASR produced no transcript"

    def _on_transcript(self, text, err, wav_path):
        try:
            os.remove(wav_path)
        except OSError:
            pass
        if err:
            self._set_state("idle", status=f"ASR error: {err}"); return
        if not text:
            self._set_state("idle", status="Didn't catch that — try again."); return
        r = d.sentence_to_signs(text, self.vocab_list, self.vocab_set,
                                self.words_dir, self.online, self.transition)
        if r is None:
            self._set_state("idle", status=f'Heard: "{text}"  — but no signable words in the 250 vocab.')
            return
        arr, segments, glosses, dropped, fps = r
        self._begin_play(arr, segments, text, glosses, dropped, fps)

    # ── play (main-thread frame loop) ────────────────────────────────────────────
    def _begin_play(self, arr, segments, sentence, glosses, dropped, fps):
        self._play = {
            "arr": arr, "seg": segments, "sentence": sentence, "glosses": glosses,
            "dropped": dropped, "T": arr.shape[0],
            "fps": float(max(1, fps)), "t0": time.perf_counter(), "shown": -1,
        }
        self._set_state("playing", status=f'Signing: "{sentence}"   →   {glosses}'
                        + (f"    (skipped: {dropped})" if dropped else ""))
        self._tick()

    def _tick(self):
        """Wall-clock driven playback (loops so the sign keeps repeating).

        The frame index comes from ELAPSED TIME, not from a counter, and after() waits only
        until the next frame's due time. So the sign always takes its correct real duration:
        a fast machine shows every frame, a slow one silently drops frames instead of playing
        the whole sign in slow motion — which would misrepresent the signing speed.
        """
        p = self._play
        if p is None or self.state != "playing":       # a new recording cancelled the loop
            return
        elapsed = time.perf_counter() - p["t0"]
        n = int(elapsed * p["fps"])                    # frames that should have elapsed by now
        idx = n % p["T"]
        if idx != p["shown"]:                          # skip redraw if we're still on the same frame
            hud = d.make_hud(p["sentence"], p["glosses"], p["dropped"], d._seg_index(p["seg"], idx))
            self._show(ps.render_frame(p["arr"][idx], hud))
            p["shown"] = idx
        due = (n + 1) / p["fps"]                        # when the NEXT frame is owed
        wait_ms = int((due - (time.perf_counter() - p["t0"])) * 1000.0)
        self.root.after(max(1, wait_ms), self._tick)

    # ── shutdown ─────────────────────────────────────────────────────────────────
    def _on_close(self):
        self._closed = True
        self._play = None
        try:
            if self.stream is not None:
                self.stream.stop(); self.stream.close()
        except Exception:
            pass
        srv = self._srv                               # ask the ASR server to exit, then insist
        self._srv = None
        if srv is not None and srv.poll() is None:
            try:
                srv.stdin.write("QUIT\n"); srv.stdin.flush()
                srv.wait(timeout=2)
            except Exception:
                try:
                    srv.kill()
                except OSError:
                    pass
        self.root.destroy()


def main():
    ap = argparse.ArgumentParser(description="Clickable Speak -> 2D avatar signs it (250-word vocab)")
    ap.add_argument("--model", default="base", help="whisper model (tiny/base/small)")
    ap.add_argument("--asr-python", default="py -3.14", help="interpreter that has faster-whisper")
    ap.add_argument("--online", action="store_true", help="Gemini glossing (auto offline fallback)")
    ap.add_argument("--handoff", default=str(HERE / "animation_handoff"))
    ap.add_argument("--vocab", default=str(HERE / "vocab_250.json"))
    ap.add_argument("--transition", type=int, default=8)
    args = ap.parse_args()

    words_dir = Path(args.handoff) / "words"
    if not words_dir.is_dir():
        sys.exit(f"[err] {words_dir} not found — run: python gloss_to_motion.py --per-word")

    root = tk.Tk()
    VoiceSignApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
