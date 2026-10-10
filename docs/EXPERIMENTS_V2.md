# v2 experiments — finding the smallest model that does the job

Goal: a model for 59-type Norwegian PII/sensitive-span extraction that is **as small as
possible and runs well on CPU**. Several models at different sizes are fine (a CPU model
for the product, a larger one as teacher/upper bound). Fine-tuning a 9B LLM is a means,
not the goal.

Everything is scored the same way: `tools/score_predictions.py` on the 400 gold documents
(`data/gold_v2`, never trained on), exact and lenient span F1, per type and per tier
(A mechanical, B contextual, C judgement). CPU models also report size, peak RAM and
throughput on this machine's 2 CPU cores.

## Results so far

| ID | Model | Params | Train data | Exact F1 | Lenient F1 | Tier C exact | CPU |
|---|---|---|---|---|---|---|---|
| B0 | Raw Gemini corpus labels (v2-converted) | — | — | 0.521 | 0.705 | 0.166 | — |
| E0 | Qwen3.5-9B QLoRA (teacher) | 9B | D1 | 0.814 | 0.907 | — | no |
| T1 | NorBERT3-small span tagger | 40.6M | D1 | 0.769 | 0.902 | 0.560 | **0.28 s/doc** (6 CPUs) |
| T2 | NorBERT3-xs span tagger | 15M | D1 | 0.760 | 0.899 | — | **0.17 s/doc** (6 CPUs) |

E0: 1 epoch, 10.3 h on the V100; 41 s/doc to evaluate on GPU. Weak types: BEHAVIORAL_PATTERN,
ECONOMIC_STATUS, MEDICATION, CRIMINAL/HEALTH/FAMILY_RELATION boundaries.

## Data

| ID | What | Docs |
|---|---|---|
| D1 | slice_v2 (all 59 types) + corpus for its 8 trusted types | 948 + 6,000 |
| D2 | D1 + the remaining corpus **enhanced**: the E0 teacher labels all 59 types, corpus labels kept for the 8 types where they score ≥0.91 against gold, a reviewed sample checks the teacher against the spec | ~28,000 |
| D3 | D2 + generated documents from the synthetic generator (rare types, new genres) | tbd |

Why enhance with the teacher rather than re-annotate by hand: on gold the teacher is far
closer to the spec than the corpus labels (0.814 vs 0.521 exact), and labelling 28k
documents with annotation agents is ~1,500 agent runs. The slice stays the human-quality
anchor and is up-weighted; gold stays untouched.

## Candidates

Scouted on the Hub 2026-10-09 (incl. lesser-known checkpoints). Ranked by expected value for
"smallest model, CPU first".

| Pri | Track | Model | Size | Licence | Why |
|---|---|---|---|---|---|
| 1 | Encoder tagger | ltg/norbert4-xsmall / -small / -base | 17M / 40M / 149M | Apache-2.0 | NorBERT3's successor (2025): trained from scratch on 600B Norwegian tokens with 16k-token sequences and sliding-window attention, so a whole document fits in one pass (no 512-token windows). Drop-in for `experiments/tagger`. Card asks for FlashAttention2, which the V100 lacks; check the custom code falls back |
| 1 | Encoder tagger | ltg/norbert3-xs / -small / -base | 15M / 40M / 123M | Apache-2.0 | already running (T1/T2) |
| 2 | Span extractor | fastino/gliner2.5-multi-v1 | 287M | Apache-2.0 | mDeBERTa-v3 boundary model: any span length (start/end pairing, no width grid), so long tier-C clauses fit. Fine-tunable, CPU via `gliner2[local]`. Needs its own venv |
| 3 | Encoder from an LLM | perplexity-ai/PII-Tracer | 596M | MIT | Qwen3-0.6B run **bidirectionally** (decoder turned encoder), already PII-tuned, 4k context, ships GGUF. Swap its 37-tag head for our 59×3 heads. Thesis angle: architecture edit of a small LLM. Needs transformers ≥5.2 |
| 4 | Small LLM | NbAiLab/borealis-270m / -1b (Gemma 3, Norwegian SFT); Qwen3.5-0.8B / 2B | 0.27–2B | borealis "other" (check); Qwen Apache | same generative output as E0; LoRA, GGUF int4 for CPU |
| 5 | Encoder tagger | jhu-clsp/mmBERT-small; jonasaise/scandmmBERT-base | ~140M / 308M | MIT / Apache | multilingual ModernBERT (8k context); scand variant continued on Scandinavian text. Comparison point against the Norwegian-native encoders |
| 5 | Encoder tagger | NbAiLab/nb-bert-base | 178M | CC-BY-4.0 | thesis BERT baseline (retry when the GPU is free) |
| — | Zero-shot baselines | knowledgator/gliner-x-large (lists no); saattrupdan/nbailab-base-ner-scandi; bardsai/eu-pii-anonimization-multilang | 865M / 178M / 278M | Apache / MIT / Apache | no training: one gold eval each, to show what off-the-shelf gets |
| — | Second teacher | ltg/normistral-11b-warm, NbAiLab/borealis-12b | 11–12B | Apache / other | optional cross-check of the E0 pseudo-labels |
| — | Teacher | Qwen3.5-9B (E0) | 9B | Apache | upper bound and pseudo-labeller |

Rejected: iiiorg/piiranha-v1 (CC-BY-NC-ND), OpenMed-PII (English clinical),
knowledgator/gliner-pii-edge (English only), fastino gliner2-privacy-filter (no Nordic languages).

Encoder/span models are expected to win on CPU cost; the question is how close they get on
tier C (clauses), where span boundaries are long and judgement-heavy.

## Log

- 2026-10-09 — E0 trained and scored. Scorer and B0 baseline added.
- 2026-10-09 — T1: a 40M-parameter NorBERT3-small tagger (4 epochs, batch 8, lr 1e-4, slice x3,
  ~1 h on a shared GPU) reaches 0.769 exact / 0.902 lenient, within 0.5 pt of the 9B teacher on
  lenient. Tier A 0.984 exact (mechanical types solved), tier B 0.876, tier C 0.560 exact /
  0.827 lenient: it finds the clauses but misplaces their boundaries (CRIMINAL 0.459,
  BEHAVIORAL_PATTERN 0.225, ECONOMIC_STATUS 0.344 exact). ANIMAL_INFO and ORGANIZATION lose
  precision (0.67, 0.72). The format's own ceiling is 0.962 exact.
- 2026-10-09 — T2 (xs) scored. CPU latency measured on 20 gold docs after capping torch threads at the
  cgroup quota (6 CPUs): torch defaulted to 96 threads (host count) and was ~400x slower. HF scouting →
  Candidates table; NorBERT4 (16k context) is the top new find.
- 2026-10-09 — D2 relabelling started (E0 teacher, 4-bit), split by digest across two V100s (this box +
  anward/tm-to-llm). Paused ~12-15 h for B3 training. QA on the first 2,136 docs (`tools/qa_teacher_labels.py`;
  shortest-first, so interview template only): spans/doc within ±10% of length-matched slice for every
  major type; under-recall on ECONOMIC_STATUS (0.69x) and CRIMINAL (0.70x), matching E0's weak types;
  0.7% of spans dropped as non-verbatim; template conventions (e.g. `Referanse:` numbers untagged)
  match gold. Re-run when the dossier template (longer docs) comes through.
- 2026-10-10 — Sonnet annotation pilot. gold2 (40 docs, dossier-weighted): two blind annotators,
  inter-annotator strict 0.948 / relaxed 0.983, then adjudicated → `data/gold2_v2/batch_g2a_gold.jsonl`
  (1,448 spans). slice2 (60 docs, one annotator) → `data/slice2_v2/` (1,803 spans; per-type rates
  within ~10% of slice_v2). Calibration: single agents re-annotating 20 existing gold docs blind score
  strict 0.795 / relaxed 0.922 against gold (old human-protocol IAA was 0.85 / 0.94); the strict gap is
  Tier C boundaries (HEALTH 0.58, CRIMINAL 0.56), mostly leading evidential verbs on which gold itself
  is split (→ spec B36). Spec B33-B36 added from the annotators' questions.
