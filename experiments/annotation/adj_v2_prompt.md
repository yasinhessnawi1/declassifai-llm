You are the adjudicator for a GOLD-standard batch of a Norwegian PII / sensitive-information
span-extraction dataset (master's thesis; the gold set is the measuring stick for every model). Work inside
`/home/coder/llm_finetune`. Your job tag is `{TAG}`.

## Inputs
- Documents: `{SRC}`, ids `{IDS}` (`{"id", "text_input"}` per line; ignore other ids).
- Two annotators labelled these documents blind and independently against the spec.
  - `{AGREED}`: the (type, span) pairs both annotators produced exactly. These pass into gold unchanged
    unless one is a clear spec violation (rare; justify each removal).
  - `{DISPUTES}`: every disagreement, per document: `BOUNDARY` (same type, overlapping spans, different
    extent), `A-only`, `B-only`.

## Your job
For every dispute line, rule against `docs/ANNOTATION_SPEC.md` (the only authority) by reading the
document text around the span:
- BOUNDARY → choose A's extent, B's extent, or a third extent the spec requires (must be an exact substring).
- A-only / B-only → keep (the spec requires it) or drop (it does not).
Then do ONE final read of each document looking only for spans the spec clearly requires that NEITHER
annotator produced; add those (mark them in the rulings as `ADDED`). Do not re-litigate agreed spans
beyond clear violations.

Read the spec first, in chunks with `sed -n`: top matter, "Global rules" (B1-B30), "Taxonomy",
"Cross-type precedence and overlap", "Type specifications", "Types new in v2". Do NOT open
`data/gold*`, `data/slice*`, `data/combined_data.jsonl`, `data/corpus_v2_teacher`, or the annotators'
raw files; the worksheet is all you need.

## Outputs (write only these, using python/Bash heredocs; never modify the repository)
1. `<scratch>/{TAG}_gold.jsonl`: one line per document, in id order:
   `{"id": ..., "output": {TYPE: [distinct exact spans]}}`, using only the 59 v2 type names, every span an
   exact case-sensitive substring of `text_input`. Agreed + kept + chosen + added spans.
2. `<scratch>/{TAG}_rulings.md`: one line per dispute, in the
   worksheet's order: `id | TYPE | ruling (A / B / third: "…" / keep / drop / ADDED / REMOVED) | spec rule cited`.

Validate output 1 with python before finishing (all ids present once, type names valid, every span
in its text) and fix until clean.

## Final message (under 250 words)
Counts (agreed kept, disputes ruled A / B / third / keep / drop, added, removed), the 5 most common
dispute patterns with the rule that settled them, and any place the spec was genuinely silent or
contradictory (these become spec open questions).

## Rulings in force (read these in the spec before you start)
The spec gained three rules on 2026-10-10 that settle the most frequent disputes in this batch:
B33 (CRIMINAL/FINANCIAL absorb their elaborating parenthetical; date-only parentheticals split
out under B4), B34 (regulatory breaches are not CRIMINAL unless framed as criminal), B35 (Eier/
Eieren → EMPLOYMENT; year range one span, year list one per year; quotes outside ORGANIZATION;
11-digit after `f.` → NATIONAL_ID). Also: B31 (same-sex spouse/partner → SEXUAL_ORIENTATION) and
B12's role-word rule for named professionals. Apply them to agreed spans too: an agreed span that
violates B33/B34/B35 is corrected (log it as REMOVED or third: "…").
