# Live ASL demo — run guide (for the 30-word model test)

Standalone camera → sign → word demo. **No website/frontend needed.** Uses the
final 5-fold model (test accuracy: ensemble **0.9433**, best single fold 0.9386).

Verified working end-to-end on this machine on **2026-07-17** (model loads,
predicts, camera + MediaPipe pipeline runs — see "What's verified" below).

## Run it

```bash
# 1. (already installed) if you ever need to rebuild the environment:
pip install -r requirements_live_demo.txt
pip uninstall -y jax jaxlib          # pulled in by mediapipe, breaks TF — remove

# 2. sanity check WITHOUT a camera (proves the model loads + predicts):
python live_demo.py --selftest

# 3. the live demo (a window opens; press q to quit):
python live_demo.py                  # 5-fold ensemble, rules sentences (safe default)
python live_demo.py --single         # fold-0 only, a bit faster
python live_demo.py --ai             # build sentences with AI on DONE (see below)
```

## The flow: sign → (auto-commit) → DONE → speak

1. **Sign a word.** If the model is confident it commits **instantly, mid-sign**
   (early commit — no waiting). Otherwise finish and **lower your hands or hold
   still ~½ s** and it commits then. A red "capturing sign…" shows while your
   hands are moving; `~ word (0.xx)` is the live guess as you sign.
   If it says **"not sure — try again"**, just re-sign the word.
2. Repeat for each word: `signs: hello  hungry`.
3. Press **DONE (Enter / green button)** when the sentence is finished → it builds
   the full sentence and **speaks it** (`hello, hungry` → "Hello! I am hungry.").
4. Sign again to start a fresh sentence, or **CLEAR / `c`** to reset. Wrong word?
   **UNDO / backspace** removes the last one.

**Why auto-commit:** each finished sign is resampled to 64 frames — exactly how
the model was trained — which is both more accurate and more responsive than a
fixed timer. If it commits too early/late, the thresholds are tunable constants
at the top of `live_demo.py` (`STILL_FRAMES`, `END_FRAMES`, `MOTION_EPS`).

### Rules vs AI (the `--ai` flag)

- **Default (no flag):** DONE builds the sentence from `grammar_rules.json` —
  offline, instant, can't fail. Best for the supervisor demo.
- **`--ai`:** the sentence is built **entirely by the AI** (Gemini by default) —
  **no rule fallback**, so it proves the AI (not a script) is doing the work. If
  the AI can't be reached it shows the error instead of a sentence.
  - **Keys live in `.env`** (`GEMINI_API_KEYS="key1,key2,..."`) — the demo loads
    them automatically. `.env` is gitignored; never commit real keys.
  - ⚠️ The keys currently in `.env` were pasted in chat and are **burned** —
    make fresh ones at https://aistudio.google.com/apikey before any real use.
  - Switch to Claude with `SENTENCE_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` in
    `.env`. The AI runs off-thread, so the video never freezes while it thinks.

## What you'll see

- A camera window with your pose + hand skeleton drawn on you.
- **Top (green): the sentence** — a live preview as you sign, then the final
  spoken sentence after you press DONE. Sign `hello` then `mom` → **"Hello, Mom!"**.
- Just below: `signs: hello  mom` — the raw list of words you've signed so far,
  and `top guesses:` (small, for debugging).
- **Bottom bar — four buttons** (click or use the key):
  - **DONE (Enter)** — finish the sentence and speak it.
  - **UNDO (backspace)** — remove the last word if it was misread.
  - **CLEAR (c)** — reset and start over.
  - **SPEAK ON/off (s)** — when ON, also speaks each word live as you sign it.
- Bottom-right: the last recognized word + a **confidence bar** (green if it
  passed the threshold, orange if it was too low to commit).
- A faint **"frame yourself here"** guide appears when idle to help positioning.
- **`w`** toggles an on-screen list of the 30 words (handy for the tester).
- **Keys:** `Enter` = DONE · `backspace` = undo last word · `space` = say the
  sentence now · `s` = toggle speak · `w` = word list · `c` = clear · `q` = quit.

The window opens **full-screen**. Audio uses the **built-in Windows voice
(SAPI)** — offline, no internet, and it speaks on every DONE (fixed the
"speaks once" bug). The **word list shows by default** in the right margin;
toggle it with the **WORDS** button or `w`.

## Which words work best (this is the model, not the camera)

Per-word accuracy on held-out test signers (5-fold ensemble):

- **Strong 93–100% (23 words):** hello, bye, yes, no, please, thankyou, store,
  home, wait, water, milk, drink, food, hungry, thirsty, mom, dad, happy, sad,
  sick, sleepy, potty, like — these are reliable, lead the demo with them.
- **Weaker 84–89%:** dog, book, hot, car, cat — usually work, sign clearly.
- **Hard 70–74%:** **look, go** — the model genuinely confuses these ~1 in 4;
  even perfect camera/lighting won't fully fix it. Demo them last, or skip.

Tips if a word won't show: hold it a full 1–2 s, keep both hands in frame, good
lighting. The confidence gate is 0.50 (`CONF_GATE` at the top of `live_demo.py`)
— lower it to ~0.4 to surface more (with more mistakes), raise it for fewer.

The words → sentence step uses `grammar_rules.json` (e.g. `go store` →
"I will go to the store."). If a word has no rule it's just shown plainly. The
same sign held for a second only appears once (no spam).

## How to sign so it reads well

- Sit **head-and-shoulders** in frame, decent lighting, plain-ish background.
- Both shoulders must be visible — the model is centered/scaled on them.
- Hold each sign clearly for ~1 second; the model reads a rolling 64-frame window.
- Only the **30 trained words** are recognized (printed when the demo starts):
  hello, bye, yes, no, please, thankyou, go, store, home, wait, water, milk,
  drink, food, hungry, thirsty, mom, dad, happy, sad, sick, hot, sleepy, potty,
  book, dog, cat, car, like, look.
- Weak words (go, car, book, dog, look, hot) need 2 agreeing windows before
  they show — this suppresses flicker, so give them an extra beat.

## What's verified vs. what the test proves

**Verified mechanically (done tonight):** model loads, output is 30 logits →
softmax, 46 ms/inference; camera opens, MediaPipe extracts the 75 landmarks,
normalization + windowing + prediction all run without error.

**What only a live signer can confirm (this test):** that the recognized words
are actually *correct*. The one real risk is a **normalization mismatch** — this
script reproduces the training preprocessing (shoulder-midpoint centered +
shoulder-width scaled) from the spec in `MODEL_CONTRACT.md §3`, not from the
preprocessing teammate's exact code (which isn't in the repo). If signs read as
**random/wrong across the board**, that's the first suspect — get the teammate's
exact normalization and adjust `normalize()` in `live_demo.py`. If most signs
read correctly, we're good.
