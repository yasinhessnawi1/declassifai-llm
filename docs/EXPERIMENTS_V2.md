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

| Track | Model | Size | Why |
|---|---|---|---|
| Encoder tagger | ltg/norbert3-xs / -small / -base | 15M / 40M / 123M | Norwegian-native, CPU-cheap; multi-label per-type tagging handles nested spans |
| Encoder tagger | NbAiLab/nb-bert-base | 178M | Norwegian BERT baseline; the thesis's BERT track |
| Span model | GLiNER multi v2.1 (mDeBERTa) | ~200M | span-level, nested, label-prompted; strong small-model NER |
| Small LLM | Qwen3.5-0.8B / 2B, Qwen2.5-0.5B / 1.5B | 0.5–2B | same generative format as E0; GGUF int4 for CPU |
| Teacher | Qwen3.5-9B (E0) | 9B | upper bound and pseudo-labeller |

Encoder/span models are expected to win on CPU cost; the question is how close they get on
tier C (clauses), where span boundaries are long and judgement-heavy.

## Log

- 2026-10-09 — E0 trained and scored. Scorer and B0 baseline added.
