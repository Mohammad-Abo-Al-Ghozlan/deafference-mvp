# Live ASL-250 — Senior Solution Design

_Grounded in the actual pipeline: `live_demo.py` (segmentation + commit + MediaPipe config), `train.py` (`build_model`, `PreprocessLayer` NaN mask), and the live log (hand-presence 25% → garbage, 64% → correct)._

**The whole design rests on one measured fact:** the classifier is fine (food 0.77, airplane 0.58, brown 0.60 when the hand is seen). The failure is that MediaPipe delivered a hand in only ~20–40% of frames, so `PreprocessLayer` fed the Transformer a mostly-`NaN` clip and it collapsed onto high-prior classes (bed/fireman/hat/tree). **Every decision below is ranked by how much it raises hand-presence and how well it makes the model behave when hand-presence is still imperfect.**

---

## PART 1 — Immediate fixes (1–2 days)

### A) Camera setup
- **Lighting (the single biggest lever):** a light source *in front* of the signer (ring light or a lamp bounced off a wall), not a window/lamp behind. Target the hands specifically — dark hands are why MediaPipe drops them. Goal: push hand-presence from ~30% to ~70%+ before touching any code.
- **Camera position:** at chest/shoulder height, signer framed head-to-mid-torso so both shoulders (pose 11/12 — your `normalize()` anchor) are always visible. If shoulders drop out, `normalize()` returns `None` and the frame is discarded entirely.
- **Resolution:** capture 1280×720 (you already request it). But you downscale to `MP_MAX_W=640` before MediaPipe — for hand-near-face signs raise this to **800–960** when not in `--fast` (more pixels on the hand = better landmarks). Only trim it back if fps < 12.
- **Background:** matte, non-skin-toned, uncluttered. Skin-toned/complex backgrounds cause false hand locks and identity confusion near the face.

### B) MediaPipe configuration — concrete values
Your current call: `Holistic(model_complexity=0 if fast else 1, min_detection_confidence=0.5, min_tracking_confidence=0.5)`.

Change to (for `--vocab250`, **not** `--fast`):
| Param | Now | Recommend | Why |
|---|---|---|---|
| `model_complexity` | 0 (fast) | **1** | complexity-0 is the main reason hands vanish near the face |
| `min_detection_confidence` | 0.5 | **0.3** | lower bar to *acquire* a hand in poor light (the gate filters junk downstream) |
| `min_tracking_confidence` | 0.5 | **0.3** | hold the track through motion blur / fast signs |
| `smooth_landmarks` | default(True) | **True** | reduces frame-to-frame jitter → steadier clips |
| `refine_face_landmarks` | default(False) | **False** | not used; costs fps |
| `MP_MAX_W` | 640 | **800** (if fps≥12) | more hand detail |

**When `--fast` (complexity 0) is acceptable:** only the 30-word distinct set, or a fps-starved machine, where hand-near-face precision isn't needed. **Never for 250** — the words that fail (hello/food/hat) are exactly the hand-at-face signs complexity-0 can't hold. Make `--fast` *off* by default for `--vocab250`.

### C) Landmark quality score (compute per segment, before classifying)
Combine the signals your pipeline already produces:

```
quality =  0.45 * hand_presence          # seg_hands / len(seg)      (dominant term)
         + 0.20 * valid_landmark_ratio    # non-NaN hand coords across frames
         + 0.15 * shoulder_visibility      # frames where normalize() != None
         + 0.10 * motion_completeness      # hand travelled a real range (not a twitch)
         + 0.10 * fps_ok                   # fps_ema >= 10 ? 1 : fps/10
```
**Thresholds (from the log — 25% junk vs 64% good, so the knee is ~0.5 presence):**
- `hand_presence < 0.50` **or** `seg_hands < 8` (at ~15 fps) → **reject, do not classify.**
- `quality < 0.55` → reject with coach text: *"Please improve lighting or bring your hands into view."*
- `0.55–0.70` → classify but flag "low quality" (widen the commit margin — see Part 2.4).
- `> 0.70` → classify normally.

The point: **never let the Transformer see a clip you already know is degenerate.** A rejected clip with a helpful message beats a confident "bed".

---

## PART 2 — Code-level improvements

### 1. Hand-quality gate (drop-in for `commit_segment`, before `classify_commit`)
```python
def segment_quality(s, seg_hands):
    """Quality of a captured segment BEFORE classifying. Returns (score, reason)."""
    n = len(s)
    if n == 0:
        return 0.0, "empty"
    arr = np.stack(s)                                   # (n,75,3)
    hand_xy = arr[:, POSE_N:N_POINTS, :2]               # both-hand blocks (n,42,2)
    hand_presence = seg_hands / n                       # you already track seg_hands
    valid_landmark_ratio = float(np.mean(~np.isnan(hand_xy)))
    # motion range of the detected hand (shoulder-width units): a real sign moves
    finite = hand_xy[np.isfinite(hand_xy).all(-1)]
    motion = float(finite.std()) if finite.size else 0.0
    motion_completeness = min(1.0, motion / 0.15)       # 0.15 su ≈ a real sign
    score = (0.55 * hand_presence
             + 0.25 * valid_landmark_ratio
             + 0.20 * motion_completeness)
    if hand_presence < 0.50 or seg_hands < 8:
        return score, "hand"                            # the log's failure mode
    return score, "ok"

# in commit_segment, replacing the current blip check:
q, why = segment_quality(s, seg_hands)
if why != "ok" or q < 0.55:
    now_line = "didn't see your hands - more light / hands in frame"
    state["candidates"] = []                            # don't offer junk chips
    return
```
**Logic:** it kills exactly the segments your log showed committing garbage (`16f/4hand`, `12f/4hand`), and it never produces a top-3 of junk — so tap-to-fix stays meaningful.

### 2. Better segmentation (fixes early cuts + split "food")
Your current cut is triggered by `END_SEC`/`STILL_SEC` on *any* hand dropout — MediaPipe flicker looks like "sign ended".

Design:
- **Start:** begin a segment only after a hand is present for `START_FRAMES` (~3), not on the first hand frame — kills twitch-starts. Keep your `PRE_ROLL` (raise 8→12 for 250 to catch the onset).
- **End = debounced:** require **continuous** no-hand for `END_SEC`, but if the hand *re-acquires within a short grace* (`REACQUIRE_SEC≈0.35`) treat it as the same sign — this stops flicker and repeated-motion signs (food, please) from splitting. You already keep collecting NaN frames on flicker; add the re-acquire grace so you don't commit during it.
- **Min duration:** `min_seg_fr` *and* `seg_hands ≥ 8` (from the gate) — reject stubs.
- **Motion-based end (not just stillness):** end when hand velocity drops below `MOTION_EPS` for `STILL_SEC` **and** the hand has returned toward a rest zone — avoids cutting mid-hold.
```
raise PRE_ROLL 8 -> 12 (vocab250);  END_SEC 0.50 -> 0.60;  add REACQUIRE_SEC 0.35
add START_FRAMES 3;  keep MAX_SEG_SEC 5.0
```

### 3. Adaptive temporal smoothing (you have the seed; formalize it)
You already early-commit ("same preview word twice at `EARLY_CONF`"). Make the required agreement a **function of margin**:
```python
margin = top1 - top2
need = 1 if (top1 >= 0.75 and margin >= 0.35) else \
       2 if (top1 >= 0.55 and margin >= 0.20) else 3      # frames of agreement
if stable_count(top1_word) >= need and quality_ok:
    commit()
```
High-confidence, high-margin → commit on 1 preview (instant). Ambiguous → require 3 agreeing previews (patient). This gives the 30-word "snappy" feel back on the easy signs while staying safe on the hard ones.

### 4. Margin-based commit — **already implemented; refine**
You already replaced pure-threshold with margin gating (`DECISIVE_RATIO=2.2`, `DECISIVE_GAP=0.16`, `DECISIVE_FLOOR=0.26`). Refinements:
- Make the margin **quality-aware**: when `quality < 0.70`, require a bigger gap (`DECISIVE_GAP*1.5`) — don't commit an uncertain word off a marginal clip.
- Use **subset masking** (`--words`) so the margin is computed over the relevant vocabulary, not all 250 (your log ran full-250, which is why max prob was often ~0.3).

---

## PART 3 — Model improvements (ranked by impact on YOUR failure)

### 1. Missing-hand augmentation — **#1 model fix, specific to your gap**
Your offline clips have hands present nearly 100% of the time; your live clips have hands **25–75%** of the time (the log). The model never learned the live `NaN` distribution — even though `PreprocessLayer` already produces a NaN mask, so the architecture *can* handle it; it was just never trained on it.
**Do:** during training, randomly set hand-landmark blocks to `NaN` for random frame spans so the training presence distribution matches live (sample presence ∈ [0.4, 1.0]). Also drop one hand entirely sometimes. This directly teaches the model to stay calm on the exact input that currently produces "bed/fireman". **Expected: the biggest single reduction in the wrong-word-on-bad-clip behavior.**

### 2. Personalization (biggest *live* accuracy gain after capture)
- **Collect:** a recorder that reuses this exact pipeline (MediaPipe → `normalize()` → 64-frame resample) and saves `(64,75,3)` clips per word. Same preprocessing = zero train/serve skew.
- **How many:** **8–10 clips/word**, varied speed/angle. Start with the ~42-word demo subset → ~350 clips, ~30–45 min.
- **Fine-tune:** freeze conv+transformer backbone; retrain **classifier head + last transformer block**, LR 1e-4, 10–20 epochs, WITH the missing-hand augmentation above. (Or logit-calibration / prototype blending if you want zero-retrain.)
- **Expected:** closes most of the sim-to-real gap on the personalized words — the "when *I* sign it, it detects it" fix.

### 3. Hard-negative training (targeted, after you have a confusion matrix)
`eval_savedmodel_250.py` / `ensemble_eval.py` write a confusion CSV. Take the top-N confused pairs (hello/hat, go/there, look/see) and: oversample those classes, and add a **supervised-contrastive term** on the pooled embedding (pull same-class together, push confusable pairs apart). Cheaper alternative: confusion-weighted sampling + reduced label smoothing on those pairs. Expected: fixes specific recurring swaps, not overall noise.

### 4. Data augmentation (why each matters here)
| Aug | Simulates | Ties to your log |
|---|---|---|
| **hand dropout → NaN** | MediaPipe losing the hand | the core failure (25% presence) |
| speed 0.7–1.3× (you resample) | fast/slow signers | short 10–16f segments |
| small rotation/scale jitter | camera angle/distance | framing variation |
| landmark Gaussian noise | jitter in poor light | unstable confidence |
| one-hand drop | occlusion / off-frame hand | hand-at-face occlusion |
| mirror (you do hflip) | handedness | already in |

### 5. Hybrid model (landmarks + RGB hand crops) — highest ceiling, park it
**Benefit:** recovers handshape when landmarks are noisy/missing — the SOTA approach, and it would attack your exact bottleneck from the other side. **Cost:** you'd need RGB in the training set (you stored landmarks only → re-collect), ~2× compute, a second encoder, and a re-architecture. **Verdict:** real long-term ceiling-raiser, but *not* the 1–2 week move. Cheaper interim: feed **hand-presence/confidence as an extra input channel** so the model explicitly knows a hand is missing rather than inferring it from NaN.

---

## PART 4 — Production architecture

```
Camera (front-lit, shoulders in frame, 720p)
   ↓
[Quality assessment]  ← heuristic gate now (Part 2.1); learned quality head later
   ↓ (reject + coach if low; never classify garbage)
MediaPipe Holistic (complexity 1, det/track conf 0.3, smoothing on)
   ↓
Segmentation (debounced start/end + re-acquire grace, Part 2.2)
   ↓
normalize() (shoulder-center/scale) → 64-frame resample
   ↓
Landmark encoder (your 1D-conv + Transformer, PreprocessLayer NaN-mask)
   [+ optional RGB hand encoder — future hybrid]
   ↓
Top-K (K=3) + quality-aware adaptive commit (Parts 2.3/2.4)
   ↓
LM correction / rescoring  (grammar_eval.ai_generate_rescore — implemented)
   ↓
Sentence generation (AI, word-preserving prompt — Part 5)
```
Each component maps to code you already have; the **only new box is the quality gate**, which is where the biggest reliability win comes from.

---

## PART 5 — AI sentence generation (implemented this session; final strategy)
The old prompt was anti-fabrication only → it dropped "please". Fixed by: (a) a hard rule to **preserve every signed word, especially please/thank-you/yes-no/question words**, collapse only true duplicates; (b) **rescoring** — send the per-sign **top-K candidate sets** and let the LM pick the coherent reading (context fixes hat→hello, foot→food) while forbidden from choosing words not in a position's list or adding/removing positions.
**Prompt contract:**
- Select exactly one word per position, from that position's candidate list only.
- Preserve intent words; never delete please/thank-you/question words.
- Correct grammar only; never invent people/objects/intent.
- Keep it to what was signed; when unsure, stay literal and short.

Optional next: pass the **confidence** with each candidate and let the LM flag low-certainty output ("Did you mean …?") instead of committing silently.

---

## PART 6 — Roadmap

| Phase | Goal | Tools | Expected improvement | Difficulty |
|---|---|---|---|---|
| **1. Make ASL-250 live-reliable** | Stop garbage; commit right word first try in good light | capture fixes, MediaPipe complexity-1, quality gate, debounced segmentation, subset masking | **Largest** — recovers most of the offline↔live gap for ~0 model work | **Easy** (days) |
| **2. Personalization** | "When *I* sign it, it detects it" | recorder (reuse pipeline) + head fine-tune + missing-hand aug | Big on personalized words | **Medium** (1–2 wk) |
| **3. Improve vocabulary/robustness** | Fewer confusions, wider vocab | confusion-mining, hard-negative + contrastive, more data/signers, multi-seed ensemble | Steady; ceiling ~0.85–0.88 | **Hard** |
| **4. LSL data collection** | Own the LSL dataset (the moat) | recording protocol, annotation, storage/preprocess (S3 + T4) | Enables LSL words → later sentences | **Very hard** (ongoing) |

---

## Professional conclusion

**Biggest bottleneck:** not the Transformer, not the 250 classes, not the code — it's **upstream landmark quality (hand-presence)**, proven by your own log: 25% presence → garbage, 64% → correct with high confidence. The model is being starved of hand data and defaulting to priors.

**Implement first (this week), in this order:**
1. **Front lighting + complexity-1 (drop `--fast`) + `--words` subset** — free, and alone should move most signs from "junk" to "works".
2. **Hand-quality gate** (Part 2.1) — never classify a <50%-presence clip; coach instead. Converts every "bed" into an honest signal.
3. **Debounced segmentation** (Part 2.2) — stop cutting signs short / splitting food.

**Highest accuracy increase, in order of ROI:**
1. **Capture + quality gate** — recovers the bulk of the offline→live gap immediately (you're measuring 75% offline; good input should get live *close* to that on distinct signs).
2. **Missing-hand augmentation retrain** — makes the model robust to the residual dropout that lighting can't fully remove; the highest-impact *model* change and it's specific to your NaN pipeline.
3. **Personalization** — closes the sim-to-real gap on the signs you actually demo.
4. Hard-negative/contrastive and hybrid RGB — diminishing returns / research; later.

**The one decision that matters most:** put a quality gate between MediaPipe and the Transformer, and retrain with the missing-hand distribution your live system actually produces. Everything else is tuning around those two.

---

## UPDATE — Decision Engine v2 (the bottleneck moved; now rebuilt)

After the capture fixes (lighting, complexity-1, quality gate) landed, the bottleneck **moved from input to the commit decision engine**: the model produced strong predictions (`HELLO 0.61 / HAT 0.20`, margin 0.41) that a confidence-only / 0.78 gate rejected. Rebuilt as an explicit **3-level engine + temporal voting + adaptive waiting + debug dashboard**, all in `live_demo.py`.

### Levels (`decide_commit()`)
| Level | Condition | Action | Latency |
|---|---|---|---|
| **1 strong** | `conf≥0.70 & margin≥0.30 & quality≥0.60` | **commit now** | instant |
| **2 medium** | `conf≥0.50 & margin≥0.18` | commit once **temporally stable** (`≥2` agreeing previews); at the pause it's auto-confirmed | ~300–500 ms |
| **3 weak** | otherwise | **reject** → show top-K, ask to repeat | n/a |

- **Temporal voting (Part 5):** `vote_hist` deque; `stable` = consecutive previews agreeing on the top word. Flicker → `stable` resets → no premature commit.
- **Adaptive waiting (Part 6):** falls straight out of the levels — L1 instant, L2 waits for confirmation, L3 never.
- **Top-K (Part 7):** already shipped (candidate chips + `cand_buf` → LM rescoring on DONE).
- **Debug dashboard (Part 13):** `--debug` overlay — word/conf, 2nd/conf, margin, hand-quality, frames, decision + LEVEL + reason.

### Final requirements

**1. Exact engineering changes** — `decide_commit()` (3-level), `segment_quality()` gate (one-handed-safe), debounced segmentation (`start_fr`, `PRE_ROLL 12`, `END_SEC 0.60`), MediaPipe complexity-1 + det/track 0.3, temporal `vote_hist`, `--debug` dashboard, word-preserving + rescoring LLM prompt.

**2. Priority order** — (1) capture + quality gate ✅, (2) decision engine v2 ✅, (3) LLM prompt/rescore ✅ — *all done*; then (4) missing-hand-aug retrain, (5) personalization, (6) hard-negative, (7) hybrid RGB.

**3. Expected improvement** — 1–3 recover most of the offline→live gap on distinct signs (no model change). 4 removes residual dropout collapse. 5 closes the sim-to-real gap on the signer. Realistic isolated-sign live ceiling ≈ 0.85.

**4. Difficulty** — 1–3 Easy (shipped). 4/6 Medium (retrain). 5 Medium (record + fine-tune). 7 Hard (re-architecture + re-collect).

**5. Testing plan** — run with `--debug`; for each of ~20 target signs log LEVEL + decision + margin + hand-quality. Metrics: first-try commit rate, wrong-commit rate, median time-to-commit. Accept: ≥80% first-try on the reliable-42 subset, <5% wrong-commit, <1 s median. Regression-guard: the `[seg]` log line (hand-%, q, top-3) + `segment_quality`/`decide_commit` unit checks.

**6. Modules changed** — `live_demo.py` (segmentation, `segment_quality`, `decide_commit`, dashboard), `grammar_eval.py` (prompt + `ai_generate_rescore`), `training/eval_savedmodel_250.py` (verify deployed model). Retrain modules (future): `training/train.py` (augmentation), new `record_me.py` + fine-tune script.
