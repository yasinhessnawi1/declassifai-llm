# Agent annotation pipeline (gold2 / slice2)

Sonnet subagents annotate corpus documents against `docs/ANNOTATION_SPEC.md`.

- `annot_v2_prompt.md`: annotator instructions. Fill `{TAG} {BATCH} {SRC} {IDS} {PURPOSE}`; 10 docs per agent.
  Agents work blind (no gold/slice/corpus labels) and write `<scratch>/{TAG}.jsonl`.
- gold2: two independent annotators per chunk → `make_adj_diff.py ann1 ann2 docs out_prefix` builds an
  agreed file + dispute worksheet → `adj_v2_prompt.md` adjudicator → `{TAG}_gold.jsonl` + rulings.
- slice2: one annotator per chunk, used as training data.
- Docs are sampled with `tools/sample_gold.py --exclude <all existing sets>` and relabelled with fresh
  ids (G2A…, S2A…); the original corpus labels are stripped so annotators cannot see them.

Results and calibration: `docs/EXPERIMENTS_V2.md` (2026-10-10 entry).
