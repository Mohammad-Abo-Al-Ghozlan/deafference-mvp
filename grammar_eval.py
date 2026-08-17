#!/usr/bin/env python3
"""
Phase A10 prototype + eval (standalone — no server, no browser needed).

Runs the ASL gloss buffer through BOTH:
  1. the A9 rule engine (grammar_rules.json) — deterministic, offline, free
  2. the A10 AI model (Claude Haiku 4.5 by default)     — needs an API key

...over the 10 demo sentences + 15 test vectors from GRAMMAR_CONTRACT.md, and
prints them side by side so you can eyeball whether the AI is demo-ready and,
critically, whether it FABRICATES (adds words nobody signed).

Usage:
    pip install anthropic          # once
    setx ANTHROPIC_API_KEY "sk-ant-..."   # once (new terminal after)  -- or export on mac/linux
    python grammar_eval.py

If no API key is set, it still runs the rule engine so you see partial value.
To use a free local model instead of Claude, see the Ollama note at the bottom.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES = json.loads((HERE / "grammar_rules.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# A9 rule engine — the reference implementation of GRAMMAR_CONTRACT.md §2.
# Greedy longest-match, left to right; templates beat rules at equal length.
# ---------------------------------------------------------------------------
def _display(gloss: str) -> str:
    return RULES["display"].get(gloss, gloss)


def _match_at(buf: list[str], i: int):
    """Best (length, text) match starting at buf[i], or None."""
    best = None  # (length, text)

    # 1. exact-sequence templates
    for t in RULES["templates"]:
        g = t["glosses"]
        if buf[i:i + len(g)] == g and (best is None or len(g) > best[0]):
            best = (len(g), t["text"])

    # 2. category / literal-gloss rules  (templates win ties -> strictly-greater)
    cats = RULES["categories"]
    for r in RULES["rules"]:
        pat = r["pattern"]
        if i + len(pat) > len(buf):
            continue
        matched, ok = [], True
        for k, elem in enumerate(pat):
            w = buf[i + k]
            if elem in cats:            # category name
                if w in cats[elem]:
                    matched.append(w)
                else:
                    ok = False; break
            elif w == elem:             # literal gloss
                matched.append(w)
            else:
                ok = False; break
        if ok and (best is None or len(pat) > best[0]):
            text = r["text"]
            for idx, w in enumerate(matched):
                text = text.replace("{" + str(idx) + "}", _display(w))
            best = (len(pat), text)
    return best


def render_rules(buf: list[str]) -> str:
    fb = RULES["fallback"]
    clauses, i = [], 0
    while i < len(buf):
        m = _match_at(buf, i)
        if m:
            clauses.append(m[1]); i += m[0]
        else:
            clauses.append(fb["unknown_word_text"].replace("{word}", _display(buf[i]))); i += 1
    if fb.get("capitalize_clauses"):
        clauses = [c[:1].upper() + c[1:] if c else c for c in clauses]
    return fb.get("clause_join", " ").join(clauses)


# ---------------------------------------------------------------------------
# A10 AI generation — Claude Haiku 4.5, guardrailed (A10.1).
# ---------------------------------------------------------------------------
SYSTEM = """You are the spoken voice of a Deaf ASL signer. You receive the ORDERED
list of ASL signs they just made, and you speak AS them, in the first person.

HARD RULES (a person's actual words depend on this):
- Use ONLY the meaning of the signs given. NEVER add people, objects, actions,
  ownership, or intent that were not signed. When unsure, stay literal and short.
- NEVER attribute a feeling or state to the wrong person. A feeling sign
  (hungry, sad, sick, ...) refers to the SIGNER unless another person is its
  clear grammatical subject. Naming someone else does NOT transfer the feeling.
- If the signs express two separate ideas, keep them as TWO short sentences.
  Do not merge unrelated signs into one clause.
- Do not invent possession or relationships. A single noun signed alone is
  stated plainly ("The car."), never expanded ("I have a car.").
- PRESERVE what was signed — do NOT silently drop a signed word. ALWAYS keep
  politeness and intent words ("please", "thank you", "sorry", "yes", "no") and
  question words (what/where/who/why/when/how). If "please" is signed, phrase the
  sentence as a polite request; never omit it.
- You MAY collapse an immediately-repeated duplicate (the SAME sign twice in a
  row, from one long-held sign) into a single mention — that is not dropping.
- Output one or two short natural sentences. No preamble, no alternatives.
- First person ("I", "my") when the signer refers to themselves.

Examples (note the fabrication ones — do NOT fabricate like the wrong answers —
and the "please" ones — the polite word must survive):
  ["go","store"]          -> "I will go to the store."
  ["milk","drink"]        -> "I want to drink milk."
  ["hungry"]              -> "I am hungry."
  ["thankyou","bye"]      -> "Thank you. Goodbye!"
  ["look","dog"]          -> "Look at the dog!"
  ["mom","home","hungry"] -> "Mom is home. I am hungry."   (NOT "Mom is hungry.")
  ["car"]                 -> "The car."                    (NOT "I have a car.")
  ["water","please"]      -> "Water, please."              (keep "please")
  ["mom","please","food"] -> "Mom, can I please have some food?"   (keep "please")
  ["hello","mom","please","hungry","food"]
      -> "Hello, Mom. I'm hungry — please, can I have some food?"  (keep "please")
"""

_SCHEMA = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}},
    "required": ["sentence"],
    "additionalProperties": False,
}
# anthropic schema for the RESCORING path: a chosen word per position + sentence
_RESCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen": {"type": "array", "items": {"type": "string"}},
        "sentence": {"type": "string"},
    },
    "required": ["sentence"],
    "additionalProperties": False,
}
# gemini schema variants (uppercase type names, no additionalProperties key)
_G_SENTENCE_SCHEMA = {"type": "OBJECT",
                      "properties": {"sentence": {"type": "STRING"}},
                      "required": ["sentence"]}
_G_RESCORE_SCHEMA = {"type": "OBJECT",
                     "properties": {"chosen": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "sentence": {"type": "STRING"}},
                     "required": ["sentence"]}

# Language-model RESCORING prompt (A10.2). Instead of one guess per sign, the
# recognizer hands over each sign's TOP-K candidates and the model picks the
# reading that makes the whole sentence coherent, then speaks it. This is what
# lets context override a wrong top-1 (e.g. "hat" -> "hello" starting a greeting,
# or "foot" -> "food" after "hungry"). Same anti-fabrication rules as SYSTEM.
RESCORE_SYSTEM = """You are the spoken voice of a Deaf ASL signer. Sign
recognition is uncertain, so for EACH sign you receive its TOP candidate words,
best guess first — e.g. [["hat","hello","help"], ["mom"], ["food","foot"]].

Do TWO things:
1) SELECT exactly one word per position FROM THAT position's list. Prefer the
   first (top) candidate. Choose a lower-ranked candidate ONLY when it clearly
   makes the whole sentence more coherent (e.g. after "I am ___ food", "hungry"
   beats a look-alike). NEVER pick a word not in that position's list. NEVER add
   or drop positions.
2) SPEAK the selected words AS the signer, first person. Same hard rules:
   - Use ONLY the meaning of the selected signs. Never add people/objects/intent
     nobody signed. When unsure, stay literal and short.
   - A feeling sign (hungry, sad, sick, ...) refers to the SIGNER unless another
     person is its clear subject. Naming someone else does NOT transfer it.
   - ALWAYS keep politeness/intent words (please, thank you, sorry, yes, no) and
     question words (what/where/who/why/when/how). If "please" is selected,
     phrase it as a polite request.
   - Collapse an immediately-repeated duplicate into one mention.
   - One or two short natural sentences. No preamble, no alternatives.

Return JSON: {"chosen": [one selected word per position], "sentence": "..."}
Example: [["hat","hello"],["mom"],["please"],["hungry"],["food","foot"]]
  -> {"chosen":["hello","mom","please","hungry","food"],
      "sentence":"Hello, Mom. I'm hungry — please, can I have some food?"}
"""

# Which backend fills the AI column:
#   "gemini"    = free Google tier (TESTING ONLY — results won't fully transfer)
#   "anthropic" = Claude Haiku 4.5 (the production choice for A10)
# Override with:  setx SENTENCE_PROVIDER "anthropic"
PROVIDER = os.environ.get("SENTENCE_PROVIDER", "gemini").lower()

_client = None
_gemini_idx = 0  # rotating index into the GEMINI_API_KEYS list


def _anthropic_call(system: str, user_text: str, schema: dict, max_tokens: int):
    """Generic Claude Haiku 4.5 JSON call. Returns the parsed dict, or a
    '(...)' status string on failure (never raises — must not crash the demo)."""
    global _client
    try:
        import anthropic
    except ImportError:
        return "(skipped: run `pip install anthropic`)"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "(skipped: set ANTHROPIC_API_KEY)"
    try:
        if _client is None:
            _client = anthropic.Anthropic()
        res = _client.messages.create(
            model="claude-haiku-4-5",       # production choice; swap to claude-sonnet-5 if needed
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in res.content if b.type == "text"), "{}")
        return json.loads(text)
    except Exception as e:  # network / auth / quota — don't crash the eval
        return f"(error: {type(e).__name__}: {e})"


def _gemini_call(system: str, user_text: str, schema: dict, max_tokens: int):
    """Generic Gemini Flash JSON call with GEMINI_API_KEYS rotation. Returns the
    parsed dict, or a '(...)' status string on failure (never raises)."""
    import urllib.request
    import urllib.error
    import time
    global _gemini_idx
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        return "(skipped: set GEMINI_API_KEY or GEMINI_API_KEYS)"
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    payload = json.dumps(body).encode("utf-8")
    for _ in range(len(keys) * 2):                # cycle every key twice before giving up
        key = keys[_gemini_idx % len(keys)]
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 404):         # quota / busy / model-not-on-this-key
                _gemini_idx += 1                  # rotate to the next key
                time.sleep(1)
                continue
            return f"(error: HTTP {e.code}: {e.read().decode('utf-8')[:150]})"
        except Exception as e:
            return f"(error: {type(e).__name__}: {e})"
    return "(error: all keys quota-exhausted — wait ~1 min and retry)"


def _sentence_of(res, field: str = "sentence"):
    """Pull the sentence from a provider result (dict), or pass an error/status
    string through unchanged so the caller can surface it."""
    if isinstance(res, str):
        return res
    return res.get(field) or "(error: no sentence in response)"


def ai_generate(buf: list[str]) -> str:
    """Sign list -> one spoken sentence (or '(skipped/error: ...)')."""
    if PROVIDER == "gemini":
        return _sentence_of(_gemini_call(SYSTEM, json.dumps(buf), _G_SENTENCE_SCHEMA, 80))
    return _sentence_of(_anthropic_call(SYSTEM, json.dumps(buf), _SCHEMA, 60))


def ai_generate_rescore(candidates: list[list[str]]) -> str:
    """Language-model rescoring. candidates[i] = the top-K recognized words for
    sign position i (best first). The model picks the most coherent reading using
    whole-sentence context, then speaks it — so a wrong top-1 can be corrected by
    context (hat->hello, foot->food). Empty -> defers to ai_generate."""
    if not candidates:
        return ai_generate([])
    if PROVIDER == "gemini":
        return _sentence_of(_gemini_call(RESCORE_SYSTEM, json.dumps(candidates), _G_RESCORE_SCHEMA, 120))
    return _sentence_of(_anthropic_call(RESCORE_SYSTEM, json.dumps(candidates), _RESCORE_SCHEMA, 120))


# ---------------------------------------------------------------------------
# SPEECH -> SIGN (Phase 2): reverse of ai_generate. Spoken sentence -> an ordered
# list of ASL glosses drawn ONLY from the avatar's vocabulary, in signing order.
# Feeds the gloss->motion stage (canonical clips + stitcher, SIGN_ANIMATION_CONTRACT).
# ---------------------------------------------------------------------------
T2G_SYSTEM = """You translate a spoken English sentence into a sequence of ASL
GLOSSES for an avatar to sign. Use ONLY glosses from the ALLOWED list provided in
the user message. Hard rules:
- Output ASL SIGN ORDER (topic-comment), not English word order.
- DROP English function words that have no sign (the, a, an, is, am, are, be, to,
  of, do, does) — sign languages omit them.
- Map inflections / close synonyms to the nearest ALLOWED gloss (e.g. "running" ->
  "run" only if "run" is allowed; "kids" -> "child" if allowed).
- If a content word has NO reasonable match in ALLOWED, SKIP it — never invent a
  gloss and never output a word that is not in ALLOWED.
- KEEP meaning-critical words when they are allowed: please, thankyou, no, yes, and
  question words (what/where/who/why/when/how).
- Return JSON: {"glosses": [ ...allowed glosses, in signing order... ]}."""

_G_T2G_SCHEMA = {"type": "OBJECT",
                 "properties": {"glosses": {"type": "ARRAY", "items": {"type": "STRING"}}},
                 "required": ["glosses"]}
_T2G_SCHEMA = {"type": "object",
               "properties": {"glosses": {"type": "array", "items": {"type": "string"}}},
               "required": ["glosses"],
               "additionalProperties": False}


def text_to_gloss(text: str, allowed: list[str]) -> list[str]:
    """Spoken sentence -> ordered ASL glosses restricted to `allowed` (Phase 2 of
    speech->sign). The reverse of ai_generate. The vocabulary constraint is enforced
    twice: in the prompt AND by filtering the model's output, so the gloss->motion
    stage never receives a word it has no clip for. Returns [] on failure/empty."""
    if not text or not text.strip() or not allowed:
        return []
    allow_set = set(allowed)
    user = json.dumps({"sentence": text.strip(), "allowed": allowed})
    if PROVIDER == "gemini":
        res = _gemini_call(T2G_SYSTEM, user, _G_T2G_SCHEMA, 200)
    else:
        res = _anthropic_call(T2G_SYSTEM, user, _T2G_SCHEMA, 200)
    if isinstance(res, str):                       # provider error/skip string
        return []
    glosses = res.get("glosses") or []
    return [g for g in glosses if g in allow_set]  # hard vocab enforcement


# ---------------------------------------------------------------------------
# The suites (from GRAMMAR_CONTRACT.md §3 demo script + §4 test vectors).
# ---------------------------------------------------------------------------
DEMO = [
    ["hello"], ["go", "store"], ["water", "please"], ["hungry"], ["milk", "drink"],
    ["mom", "home"], ["like", "cat"], ["look", "dog"], ["sick"], ["thankyou", "bye"],
]
TEST_VECTORS = [
    ["hello"], ["go", "store"], ["store", "go"], ["hungry"], ["happy", "sleepy"],
    ["milk", "drink"], ["water", "please"], ["thankyou", "bye"],
    ["thirsty", "drink", "water"], ["hello", "go", "store"], ["mom", "home", "hungry"],
    ["yes", "please"], ["look", "dog"], ["food", "hot"], ["car"],
]


import time

# Seconds to wait between AI calls — spaces requests under the Gemini free-tier
# per-minute quota. Set to 0 on paid tiers (setx SENTENCE_DELAY "0").
DELAY = float(os.environ.get("SENTENCE_DELAY", "6" if PROVIDER == "gemini" else "0"))


def _run(title: str, suite: list[list[str]]) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}", flush=True)
    for buf in suite:
        gloss = ", ".join(buf)
        print(f"\n  signs : {gloss}", flush=True)
        print(f"  rules : {render_rules(buf)}", flush=True)
        print(f"  AI    : {ai_generate(buf)}", flush=True)
        if DELAY:
            time.sleep(DELAY)


if __name__ == "__main__":
    _run("DEMO SCRIPT (10 sentences the live demo will show)", DEMO)
    _run("TEST VECTORS (15 — the frontend #23 unit tests)", TEST_VECTORS)
    print("\nDone. Compare 'rules' vs 'AI'. Watch for the AI adding words nobody signed.")

# ---------------------------------------------------------------------------
# Zero-cost local alternative (Ollama): install ollama, `ollama pull llama3.2`,
# then replace ai_generate's body with an HTTP POST to http://localhost:11434
# /api/chat using the same SYSTEM prompt. Note: quality is lower and results
# will NOT transfer to Haiku, so re-test on Haiku before shipping.
# ---------------------------------------------------------------------------
