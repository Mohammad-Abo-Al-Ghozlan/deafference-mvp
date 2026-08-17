# Dataset research — real / continuous signing (2026-07-17)

**Honest headline:** openly-licensed **commercial** continuous-signing data barely
exists — this is a known hard wall in the field. It's exactly why the current
"**isolated words → AI assembles the sentence**" approach is a *reasonable
workaround, not a hack*: we don't have to own continuous-signing data to produce
natural sentences today.

## Continuous / sentence-level datasets

| Dataset | What | Size | License — the catch |
|---|---|---|---|
| **How2Sign** | Continuous ASL, sentence-aligned, multimodal (RGB, depth, speech, transcripts) | 80h, 35k sentences | **CC BY-NC 4.0 → non-commercial. Can't use** (same trap as the rehosted Kaggle copy we already rejected) |
| **YouTube-ASL** | Open-domain ASL from YouTube (video IDs + English captions) | 984h, 2,500+ signers | Per-video **YouTube licensing is murky** for commercial use; it's a list of IDs, not owned clips |
| **OpenASL** | Web-sourced ASL | ~1,000h | Research-oriented; annotations corrected only on val/test |
| **RWTH-PHOENIX-Weather 2014T** | Continuous German SL (weather broadcasts) — the classic SLT benchmark | ~11h | German SL, research license |
| **ArabSign** | **Continuous Arabic SL** | 9,335 clips, 50 sentences | Relevant to the Arabic/LSL wedge — **license needs confirming** |
| **Isharah** | **Continuous Arabic**, real-world **smartphone** video (unconstrained) | 30,000 clips, 18 signers | Newest + closest to real deployment conditions — **worth investigating** |
| **KArSL** | Isolated Arabic (Kinect: RGB+depth+skeleton) | 502 signs | Isolated, not continuous |

## Recommendation

- **Don't chase commercial continuous *ASL* data** — it's a dead end right now,
  and we'd lose to Big Tech on ASL anyway.
- **The moat is Arabic → Lebanese Sign Language (LSL).** No one has data there.
  - Investigate **ArabSign** and **Isharah** for licensing (both from KFUPM).
    Contact: **Hamzah Luqman — hluqman@kfupm.edu.sa**.
  - Our **own LSL collection** (with signed consent) is the asset nobody can copy.
- **Signing video is biometric** — the consent + data-governance strategy is both
  the legal requirement *and* part of the moat story for investors.

## Next steps (open)
- [ ] Email ArabSign/Isharah authors about **commercial** licensing terms.
- [ ] Decide: license an Arabic set vs. collect our own LSL data first.
- [ ] Keep the isolated-words + AI-sentence approach as the shipping path meanwhile.

## Sources
- How2Sign — https://how2sign.github.io/
- YouTube-ASL (arXiv) — https://arxiv.org/html/2306.15162v1
- ArabSign — https://hamzah-luqman.github.io/ArabSign/
- Isharah / CSLRConformer (arXiv) — https://arxiv.org/pdf/2508.01791
- KArSL — https://hamzah-luqman.github.io/KArSL/
