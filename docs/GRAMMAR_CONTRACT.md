# Grammar Rules → Frontend Contract (Phase A9 / frontend #23)

**How the ordered gloss buffer becomes a natural English caption.**
Companion to [`MODEL_CONTRACT.md`](MODEL_CONTRACT.md) — that doc ends at "the model emitted a word"; this doc starts there.
Data file: [`grammar_rules.json`](grammar_rules.json). Frontend implements the tiny engine below (task #23) and loads the JSON — **no rule content is ever hardcoded.**

Owner: Salim (backend/ML) authors the rules; frontend wires the engine.
Status: `grammar v1` · **DRAFT — pending review by the demo signer (#30)** · voice: **first person** (the app speaks *as* the deaf user; that's the product).

---

## 1. The interface

```
render(glossBuffer: string[]) -> string
```

- **Input:** the debounced gloss buffer (output of frontend #18) — an ordered array of words from `vocab_30.json`, e.g. `["go", "store"]`. Already deduplicated/debounced; this layer does NOT handle repeats or confidence (those are #18/#27's job).
- **Output:** one display string for captions + TTS, e.g. `"I will go to the store."`
- Pure function, deterministic, no state. Safe to re-run on every buffer change.

## 2. The engine (implement once, ~30 lines)

Greedy longest-match, left to right:

```
function render(buffer):
    clauses = []
    i = 0
    while i < buffer.length:
        m = longest match at buffer[i..] among:        # tie-break: templates beat rules
              1. templates  (exact gloss sequences)
              2. rules      (patterns of category names and/or literal glosses)
        if m exists:
            clauses.push(m.text with {k} -> display(matched gloss k))
            i += m.length
        else:                                          # fallback — never crash
            clauses.push(fallback.unknown_word_text with {word} -> display(buffer[i]))
            i += 1
    capitalize first letter of each clause (fallback.capitalize_clauses)
    return clauses.join(fallback.clause_join)
```

- **`display(gloss)`**: look up `display` map first (`thankyou` → "thank you", `bye` → "goodbye"), else the gloss itself.
- **Rule patterns**: each element is either a **category name** (defined in `categories`) or a **literal gloss**. A gloss matches a category element if it's in that category's list. `{0}`, `{1}` = display form of the 1st/2nd matched gloss.
- **Matching priority**: longer match beats shorter; at equal length, `templates` beats `rules`. (Rules within the file are already ordered longest-first — preserve file order on ties.)
- **Unknown words never crash**: anything unmatched renders as the word + period via `fallback`. A new vocab word works day one (just less pretty) — rules are enhancement, not dependency.

## 3. Demo script (A9.4) — ✅ approved by Salim 2026-07-16; ⏳ pending signer review

Ten sentences, all buildable from the 30-word vocab, chosen to show the full pipeline range (greeting → reordering → politeness → feelings → family → farewell). **Every one is covered by `grammar_rules.json` — verified against the test vectors in §4.**

| # | Signer signs (gloss order) | App says |
|---|---|---|
| 1 | `hello` | "Hello!" |
| 2 | `go, store` | "I will go to the store." |
| 3 | `water, please` | "Water, please." |
| 4 | `hungry` | "I am hungry." |
| 5 | `milk, drink` | "I want to drink milk." |
| 6 | `mom, home` | "Mom is home." |
| 7 | `like, cat` | "I like the cat." |
| 8 | `look, dog` | "Look at the dog!" |
| 9 | `sick` | "I am sick." |
| 10 | `thankyou, bye` | "Thank you. Goodbye!" |

**⚠️ Weak-word note (from `MODEL_CONTRACT.md` §5):** `go, car, book, dog, look, hot` are the model's most confusable words. This script uses **go** (#2) and **look/dog** (#8) because they're core demo value — but they carry the 2-consecutive-window rule, so the signer should hold those signs deliberately. If #8 proves flaky in rehearsal, swap to `happy` → "I am happy."

**For the signer's review (before the demo):**
1. Are these gloss *orders* what a fluent signer would naturally produce? (Both orders are covered for most pairs — e.g. `store, go` also works — but confirm.)
2. Do the rendered sentences say what the signer *means*?
3. Any rule in `grammar_rules.json` that renders something misleading? (Especially the single-word assumptions: `food` → "I want some food.", `go` → "I want to go.")

## 4. Test vectors — frontend #23's unit tests

The engine is correct when all of these pass:

| Input buffer | Expected output | Exercises |
|---|---|---|
| `["hello"]` | `Hello!` | single-word template |
| `["go","store"]` | `I will go to the store.` | 2-gloss template |
| `["store","go"]` | `I will go to the store.` | topic-comment order variant |
| `["hungry"]` | `I am hungry.` | category rule (feeling) |
| `["happy","sleepy"]` | `I am happy and sleepy.` | 2-feeling rule beats 2 single rules (longest match) |
| `["milk","drink"]` | `I want to drink milk.` | reversed category rule |
| `["water","please"]` | `Water, please.` | rule + clause capitalization |
| `["thankyou","bye"]` | `Thank you. Goodbye!` | template beats two singles; display map |
| `["thirsty","drink","water"]` | `I am thirsty. I want to drink water.` | 3-gloss template (longest match wins) |
| `["hello","go","store"]` | `Hello! I will go to the store.` | greedy segmentation across clauses |
| `["mom","home","hungry"]` | `Mom is home. I am hungry.` | template + rule mix |
| `["yes","please"]` | `Yes. Please.` | two singles, no false pair-match |
| `["look","dog"]` | `Look at the dog!` | lookable category |
| `["food","hot"]` | `The food is hot.` | noun+hot template beats feeling rule |
| `["car"]` | `The car.` | plain noun single |

## 5. Versioning

- `grammar_version` bumps on any rule change; frontend logs it at load.
- Tied to `vocab_version` — if `vocab_30.json` ever changes (e.g. Phase 6 adds no-sign at index 30), revisit this file. **No-sign glosses must never reach `render()`** — the confidence gate / no-sign class filters them upstream.
