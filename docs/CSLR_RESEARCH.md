# Continuous Sign Language Recognition (CSLR) — Research Brief

**For:** Deafference (ASL↔speech accessibility).
**Status:** Research brief, 2026-07-24. Owner: Salim (ML). Context: we have an
**isolated** 250-sign recognizer (GISLR landmarks, 1D-CNN+Transformer, ~0.7755
4-fold ensemble). This doc scopes what it would take to reach **continuous** ASL.
**Datasets section is ASL-only, by request.**

---

## TL;DR
Going from our isolated 250-sign recognizer to **continuous ASL** is **not blocked
by models or compute — it's blocked by DATA.** There is **no large, public,
continuous *ASL* corpus with gloss annotations** (the label type classic CSLR needs).
So:

- **Demo-quality multi-sign (now):** sliding-window "sign spotting" over our 250 signs
  + a grammar layer — which is essentially what `live_demo.py` already does.
- **Product-quality continuous ASL (later):** do **not** build gloss-based CSLR for
  ASL. Instead **fine-tune a pose-based foundation model on gloss-free ASL translation
  data** (YouTube-ASL / OpenASL / How2Sign). That is where the field is going.

---

## 1. CSLR vs what we have (ISLR)
- **ISLR (what we have):** one pre-segmented clip → one label. A *classification*
  task. Solved-ish (our 0.7755).
- **CSLR:** a continuous video of many signs run together → an ordered *sequence* of
  **glosses** (a gloss = the written label for one sign, in signing order — not spoken
  grammar). A *sequence-to-sequence* task, and much harder.
- **SLT (Sign Language Translation):** video → fluent English sentence (reordering +
  grammar). A further step beyond CSLR.

## 2. Why CSLR is much harder
- **No boundaries.** Signs blur together with no clear start/end. Chicken-and-egg:
  can't segment without recognizing, can't recognize without segmenting → treated as
  **weakly-supervised alignment** (only sentence-level labels, no frame timing).
- **Coarticulation / "movement epenthesis."** The hands insert *non-lexical*
  transitional motion between signs, and each sign's shape bends toward its neighbors.
  So **models trained on clean isolated clips degrade on connected signing** — the core
  reason naive transfer underperforms.
- **Standard fix = CTC loss** (borrowed from speech recognition): learns the
  frame→gloss alignment implicitly from sentence-level gloss labels only. But it
  *requires those gloss labels* — which is exactly the ASL problem (see §4).

## 3. Where the field is (the ceiling)
- Best CSLR hits **~17–18% word error rate (WER)** on the German benchmark
  PHOENIX-2014 (TwoStream-SLR, SlowFastSign, SignVTCL; 2022–2024) — and that's a narrow
  weather-forecast vocabulary (~1–2k glosses). *(Exact numbers vary a few points across
  papers.)*
- **Pose/landmark-based CSLR works** and is a strong 2022–2025 trend — a few WER points
  behind heavy RGB-video models, but far cheaper, privacy-preserving, and robust to
  background/lighting. **Our MediaPipe-landmark stack is a legitimate foundation.**
  - Known weak spots that matter for us: dropped/jittery hand tracking under **fast
    signing and hand-face / hand-hand occlusion**; normalization + missing-keypoint
    handling materially affect accuracy.
- **Pose foundation models fit our stack directly:** **Uni-Sign** (ICLR 2025, pose-based,
  does ISLR + CSLR + translation) and **SignBERT+** (TPAMI 2023, self-supervised
  hand-pose pretraining — add a CTC head).

## 4. ASL datasets (ASL-only)
**The critical finding:** the only ASL corpora that are BOTH continuous AND
gloss-annotated are tiny/linguistics-scale. Every large continuous ASL corpus is
**translation-only (no gloss).** *(For contrast: the clean gloss+continuous benchmarks
CSLR papers actually train on — PHOENIX-2014/T, CSL-Daily — are German and Chinese, not
ASL. That absence is the whole problem.)*

### Continuous ASL
| Dataset | Size | Gloss? | Translation? | Domain / notes |
|---|---|---|---|---|
| **YouTube-ASL** | ~984h, 11,093 videos, 610k captions, 2,500+ signers | ❌ | ✅ English | Open-domain, web-mined. **Largest open ASL corpus.** [arXiv:2306.15162](https://arxiv.org/abs/2306.15162) |
| **OpenASL** | ~288h, 200+ signers, 98,417 pairs, 33.5k vocab | ❌ | ✅ English | Web (news/vlogs). Largest pre-YouTube ASL translation set. [EMNLP 2022](https://aclanthology.org/2022.emnlp-main.427/) |
| **How2Sign** | ~80h, 2,500+ videos, 35k+ sentences, 11 signers, multiview+depth | ❌ (none public)¹ | ✅ English | Instructional/how-to. [how2sign.github.io](https://how2sign.github.io/) |
| **NCSLGR / ASLLRP** (Boston) | ~1,000+ sentences, ~11k sign tokens | ✅ manual, rich | partial | **The only glossed continuous ASL — but tiny, old, linguistics-scale.** Usable for eval/prototyping, NOT for training modern CSLR. [bu.edu/asllrp](https://www.bu.edu/asllrp/) |

### Isolated ASL (single sign per clip — no sequences)
| Dataset | Size | Type | Notes |
|---|---|---|---|
| **GISLR / "asl-signs"** | 250 signs, 21 signers, MediaPipe landmarks (no video) | word labels | **← our current dataset** (PopSign/Google, Kaggle) |
| **PopSign** | 250 signs, 200k+ clips, ~128h | word labels | Game-collected (video) |
| **WLASL** | 2,000 signs, ~21k clips | word labels | Common ISLR benchmark |
| **MS-ASL** | 1,000 signs, ~25k samples | word labels | Common ISLR benchmark |
| **ASLLVD** | 1,866 signs, ~9,800 tokens | citation-form labels | Isolated lexicon (Boston) |

¹ *How2Sign gloss: sources conflict; the CVPR paper mentioned glosses but there is no
usable public gloss release — treat as translation-only unless verified against the
current distribution.*

**Consequence — the 3 (only) routes to CTC-gloss CSLR for ASL:**
1. Train CTC on **non-ASL** gloss data (PHOENIX/CSL-Daily) — wrong language.
2. Go **gloss-free** on large ASL translation corpora (YouTube-ASL/OpenASL/How2Sign) — **recommended**.
3. Auto-generate **pseudo-glosses**. There is no clean fourth option — which is why
   gloss-free is the field's direction.

## 5. Our realistic path
### Tier 1 — multi-sign *demo* (now; we're already here)
`live_demo.py`'s sliding-window + confidence-gate + gloss-buffer + grammar **is** the
recommended demo approach ("constrained sliding-window spotting"). Honest limits (from
[EMNLP 2024, arXiv:2401.05336](https://arxiv.org/html/2401.05336v1), which tried exactly
this): naive sliding-window scored **31.6% WER vs 18.8% offline**. To make it feel good:
1. add a **"background"/no-sign class** to suppress transition frames *(highest-value
   upgrade for us; cheap — negatives are easy to sample)*,
2. **duplicate/false-positive suppression** across overlapping windows *(we have this)*,
3. **grammar/context** to fix sequence errors *(we have the rule engine)*.
→ Great for "sign known words in a row → sentence." Not sentence-accurate translation.
**Good enough for the MVP.**

### Tier 2 — real continuous ASL (Phase-2 research track)
Fine-tune **Uni-Sign** (pose-native, matches our MediaPipe stack) on **YouTube-ASL /
OpenASL / How2Sign** for **gloss-free translation**. Compute is modest (~days on one
GPU); leverage comes from starting from a pretrained pose model, not scratch. Build on:
[Uni-Sign](https://arxiv.org/abs/2501.15187) · [SignBERT+](https://arxiv.org/abs/2305.04868) ·
[VAC_CSLR](https://github.com/VIPL-SLP/VAC_CSLR) · [CorrNet](https://github.com/hulianyuyy/CorrNet) ·
index: [Awesome-Sign-Language](https://github.com/ZechengLi19/Awesome-Sign-Language).

## 6. Recommendation for Deafference
1. **Ship the Tier-1 demo now** (existing pipeline + the 250 model). The research
   *validates* our current architecture as the correct pragmatic choice.
2. **Add a "no-sign/background" class** at the next retrain — single highest-value
   upgrade for clean multi-sign flow (kills transition false-positives), and cheap.
3. **Frame continuous ASL as Phase-2**, not an MVP feature — and when we start it,
   **fine-tune Uni-Sign on YouTube-ASL (gloss-free)**; do NOT chase gloss-CSLR for ASL.

---

## Sources (key)
- Alyami & Luqman 2024, *A Comparative Study of CSLR Techniques* — [arXiv:2406.12369](https://arxiv.org/html/2406.12369v1)
- Koller et al. 2015, PHOENIX / *Continuous SLR* — [i6 RWTH](https://www-i6.informatik.rwth-aachen.de/~koller/RWTH-PHOENIX/)
- Min et al. 2021, *Visual Alignment Constraint for CSLR* (VAC, CTC) — [arXiv:2104.02330](https://arxiv.org/abs/2104.02330)
- Camgöz et al. 2018, *Neural Sign Language Translation* (CSLR vs SLT, PHOENIX-2014T) — [CVPR 2018](https://openaccess.thecvf.com/content_cvpr_2018/html/Camgoz_Neural_Sign_Language_CVPR_2018_paper.html)
- *Towards Online CSLR and Translation* — [EMNLP 2024, arXiv:2401.05336](https://arxiv.org/html/2401.05336v1) (sliding-window reality check)
- Uni-Sign (Li et al., ICLR 2025) — [arXiv:2501.15187](https://arxiv.org/abs/2501.15187)
- SignBERT+ (Hu et al., TPAMI 2023) — [arXiv:2305.04868](https://arxiv.org/abs/2305.04868)
- YouTube-ASL (Uthus et al. 2023) — [arXiv:2306.15162](https://arxiv.org/abs/2306.15162)
- OpenASL (Shi et al., EMNLP 2022) — [aclanthology 2022.emnlp-main.427](https://aclanthology.org/2022.emnlp-main.427/)
- How2Sign (Duarte et al., CVPR 2021) — [how2sign.github.io](https://how2sign.github.io/)
- NCSLGR / ASLLRP (Boston University) — [bu.edu/asllrp](https://www.bu.edu/asllrp/)
