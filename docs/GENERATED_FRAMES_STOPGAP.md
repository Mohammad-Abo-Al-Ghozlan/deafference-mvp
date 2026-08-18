# Generated frames as a demo stand-in, until the 3D avatar lands

**Written 2026-08-14.** A temporary presentation path, not a deliverable. The 3D avatar is still
being built; this makes the speech→sign direction *look* finished for a pitch or stakeholder demo in
the meantime, and gets thrown away when the rig arrives.

---

## The one rule that makes this defensible

**Drive the model with our recorded landmarks. Never prompt it from the word.**

| | |
|---|---|
| ❌ *"generate a person signing HELLO"* | The model invents the hands. In ASL the handshape **is** the word — `B` and `C` templates sit **0.124** apart in our own measurements, and a "roughly correct" hand is a different sign or no sign. |
| ✅ *"render this pose sequence as a person"* | Handshape, movement and location come from a real human take in the corpus. The model supplies **appearance only.** |

Hands are the known failure mode of generative image models, and they are also the highest-information
channel in the language. Pose-conditioning is what makes the difference between a demo that is a
stylised view of real signing and one that is confident nonsense.

**Therefore, before spending anything, check one thing:** does the Higgsfield MCP expose an
**image-to-video / reference-pose / driving-video** input, or is it **text-to-video only**?

- **Pose input available** → feed it `driving_video/tierA/<word>.mp4`. Proceed.
- **Text-only** → the output cannot carry a correct handshape. Use it for **one hero shot** on a
  slide and keep the 2D player for the actual words. Do not generate a vocabulary.

---

## Connecting Higgsfield to Claude

It is listed as a **claude.ai connector**, so it is authorised on claude.ai rather than in the CLI.
The OAuth flow cannot be run from a non-interactive Claude Code session.

1. Open **claude.ai** in a browser and sign in as `salim@deafference.com`.
2. Click your profile / initials (bottom-left) → **Settings**.
3. Open **Connectors**. Higgsfield may already be listed; if not, use **Browse connectors** /
   the connector directory and find it.
4. Click **Connect**.
5. A Higgsfield authorisation window opens. Sign in to your Higgsfield account and **Authorize**.
6. Confirm it now reads **Connected**.
7. Back in Claude Code, run **`/mcp`** to check status. **If it still shows unauthenticated,
   restart the session** — the connector list is read once at session start and is cached.

**Security, non-negotiable:**

- The OAuth flow handles credentials. **Never paste a Higgsfield API key or token into chat.**
- If Higgsfield offers key-based auth instead of OAuth, that key goes into the **connector config on
  claude.ai only** — never into `.env.example`, never into the repo, never into a notebook cell.
- The AWS / Gemini / Supabase keys pasted into a chat in an earlier session are still **burned and
  unrotated**. Do not add a fourth.

---

## The driving videos

Produced by `python export_driving_video.py` → `driving_video/`, split by quality tier, with
`manifest.json` listing every word's tier, class, frame count, duration, coverage and file path.

```
driving_video/
  tierA/<word>.mp4     coverage >= 80%   spend credits here first
  tierB/<word>.mp4     50-80%            usable; eyeball each one
  tierC/<word>.mp4     < 50%             see the warning below
  manifest.json
```

These are **clean renders** — `render_frame(pts, hud=None)`, no word label burned in.
`preview_signs.py --save` bakes a text label into every frame, which a generator would render
*into* the output; that is why this is a separate script.

Frames are **hold-filled**: a landmark missing for 1–3 frames carries its last value forward rather
than vanishing. 550 of the 776 gaps in this corpus are that short and are tracker dropout rather
than movement, so holding is the correct reading of contract §6. `--raw` disables it.

### ⚠️ Do not generate tier C

39 words have the dominant hand missing on **more than half** their frames. `bath` has 84 frames, 9
with a dominant hand, and one 51-frame hole. A generative model will happily fill that in and
produce a smooth, confident video of a sign **that is not in the data**. That is the worst possible
failure here: it looks more correct than the honest render, and nothing downstream can detect it.

Tier A is **147 words** — far more than any demo script needs.

---

## Prompt config — keep it identical across every word

The single biggest quality risk after handshape is **appearance drift**: generate 20 words with 20
prompts and you get 20 different people. Fix the subject once and vary only the driving video.

```
SUBJECT   A single adult person, plain mid-grey long-sleeved top, no patterns, no jewellery,
          hands and forearms fully visible, neutral facial expression.
FRAMING   Waist-up, centred, camera at chest height, static shot, no zoom, no camera movement.
BACKGROUND Flat neutral light-grey studio backdrop, soft even lighting, no shadows on the hands.
STYLE     Photographic realism, natural skin tones, sharp on the hands.
MOTION    Follow the driving pose exactly. Do not add gestures, do not add head movement,
          do not stylise or smooth the hand motion.
NEGATIVE  extra fingers, fused fingers, missing fingers, blurred hands, motion blur on hands,
          text, watermark, captions, subtitles, second person, cropped hands, hands out of frame
```

**Long sleeves and no jewellery** are deliberate: bare forearms and bracelets both give the model
more room to hallucinate around the wrist, which is where our data is weakest.

**Aspect ratio:** the driving videos are **760 × 820** (portrait-ish). Match it if the tool allows a
custom size; otherwise pick the nearest portrait preset and accept letterboxing rather than a crop —
**a crop that clips a hand destroys the sign.**

**Duration:** take it from `manifest.json` → `seconds`, per word. Range is **0.30 s (`tiger`) to
3.87 s (`puppy`)**, median ~1.4 s. Do not let a tool default to a fixed length; a 5-second clip of a
0.3-second sign is 94% invented motion.

---

## Where the line is

| Use | Verdict |
|---|---|
| Pitch deck, investor demo, landing-page video | ✅ Fine |
| Showing the concept end-to-end before the rig lands | ✅ Fine, that is the point |
| Style reference for the rigger | ✅ Useful |
| **Deaf review of the 250 exemplars** | ❌ **No** |
| Anything presented as a reference for how to sign | ❌ No |

**Why the review is excluded:** that pass exists to judge whether *our* signs are correct. If the
frames are model-generated, a reviewer's "this looks wrong" cannot be traced to the lexicon, the
data, or the generator — the review becomes unable to fail, which is the single pattern that has
cost this project the most (see `SESSION_HANDOFF.md` §0.5). Deaf review runs on the 2D player
against real landmarks: `python preview_signs.py --review`.

## When the avatar lands

Delete `driving_video/`, and delete every generated clip. Its only job is to make a demo look
finished for a few weeks. Keeping it around invites someone to ship it.
