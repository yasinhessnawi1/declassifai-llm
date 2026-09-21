# Data Quality Audit — `combined_data.jsonl`

Audit of the 32,439-document Gemini-labeled Norwegian NER/PII corpus, the
evidence behind the re-annotation decisions, and the resulting plan.

**Date:** 2026-09-21
**Corpus:** `data/combined_data.jsonl` — 32,439 documents, 629,098 labeled spans, 18 entity types
**Verdict:** the labels are well-formed but *not reproducible*. The corpus needs
re-annotation against a written spec, not a cleanup pass.

---

## 1. Summary

The intuition that "the data quality is low" is correct, but the defect is not
where it looks. Labels are overwhelmingly well-formed and verbatim — **99.4% of
spans are exact substrings of their source document**, there are zero malformed
JSON lines, and zero empty outputs.

The real problem is **annotation inconsistency**. The corpus contains 2,548
documents that appear more than once, and **99.7% of those duplicates carry
contradictory labels**. The same labeler, shown the same text twice, produced
different answers almost every time.

That is a reproducibility failure, and it has a cause: the entity definitions
are one-line descriptions that do not specify span boundaries, overlap policy,
or precedence. `ECONOMIC_STATUS: "References to economic hardship or wealth"`
does not tell anyone whether to tag the key phrase or the whole clause.

Re-running a reviewer over the same ambiguous rubric would reproduce the
inconsistency at higher cost. **The specification is the prerequisite**, which is
why [`ANNOTATION_SPEC.md`](ANNOTATION_SPEC.md) was written before any relabeling.

---

## 2. Mechanical defects

Detected by `tools/validate_labels.py`, which enforces the verbatim-substring
invariant. All figures are over 629,098 spans.

| Defect | Count | Share | Disposition |
|---|---:|---:|---|
| Exact verbatim substring | 625,056 | 99.4% | ok |
| Not present in source text | 3,012 | 0.48% | unfixable — dropped |
| Case mismatch only | 822 | 0.13% | auto-repaired |
| Whitespace mismatch only | 208 | 0.03% | auto-repaired |
| Duplicate span within a list | 584 | 0.09% | auto-repaired |
| Unknown entity type | 6 | — | dropped (`ANIMAL_INFO`, `AGE_INFO`, `AGE`) |
| Malformed JSON / empty output | 0 | 0% | — |

The 3,012 unfixable spans are **paraphrases and translations**, not extraction
errors. The labeler summarised instead of quoting:

- `'Hunden blir ofte etterlatt alene i bilen'` — the source reads
  *"...alene i en sølvgrå Volvo stasjonsvogn, registreringsnummer BC 12345"*.
- English output on Norwegian source: `'tax evasion'`, `'undeclared income'`,
  `'firearm discharge'`, `'owner of Sørensen Fisk AS'`.
- Invented punctuation: a closing quotation mark added where the source has none.

Strict verbatim-miss rates concentrate in the subjective types —
`POLITICAL_CASE` 3.68%, `BEHAVIORAL_PATTERN` 2.98%, `CONTEXT_SENSITIVE` 2.70% —
versus `CRIMINAL_RECORD` 0.56% and effectively 0% for `EMAIL_ADDRESS`, `GOV_ID`
and `POSTAL_CODE`. Subjectivity invites summarisation.

---

## 3. The core evidence: contradictory duplicates

2,548 documents appear more than once. **2,541 (99.7%) are labeled
inconsistently across copies.** Comparing the variants yields 20,313 individual
conflicts:

| Conflict class | Count | Share |
|---|---:|---:|
| **Presence** — tagged in one copy, missed in the other | **14,250** | **70.2%** |
| Boundary — one span contains the other | 4,310 | 21.2% |
| Type migration — same span, different type | 1,753 | 8.6% |

**Recall instability dominates by 3×.** The most damaging example is `GOV_ID`,
with 1,485 presence conflicts: an organisation number such as `'987654321'` is
tagged in one copy and silently dropped in another. There is no ambiguity to
blame — that is attention failure, and it is why the spec enumerates GOV_ID
surface forms mechanically rather than describing them.

Boundary conflicts concentrate in three types (73% of all of them):

| Type | Conflicts | Example |
|---|---:|---|
| `CRIMINAL_RECORD` | 1,091 | `'trusler'` ↔ `'trusler mot en journalist'` |
| `FAMILY_RELATION` | 1,032 | `'barn'` ↔ `'to barn'` |
| `POLITICAL_CASE` | 1,018 | `'Norges Renhet'` ↔ `'medlem av den høyreekstreme organisasjonen "Norges Renhet"'` |

These are resolved by the FULL CLAUSE rule (global rule 2 in the spec).

### Type definitions that genuinely overlap

`'skatteunndragelse'` (tax evasion) appears **1,418 times, split across five
types with no majority**:

`CRIMINAL_RECORD 680` · `FINANCIAL_INFO 456` · `CONTEXT_SENSITIVE 144` · `ECONOMIC_STATUS 131` · `POLITICAL_CASE 7`

One unambiguous Norwegian word, labeled five ways. This is a schema defect, not
a labeling slip, and it is why the spec defines an explicit precedence chain.

---

## 4. Config/data mismatch

`configs/config.yaml` defines **15** entity types. The corpus and `README.md`
have **18**. `prompt_builder.build_chat_messages` filters output to the config's
list, so three types were **silently discarded at training time**:

| Discarded type | Spans | Documents |
|---|---:|---:|
| `CONTEXT_SENSITIVE` | 24,277 | 10,314 |
| `BEHAVIORAL_PATTERN` | 16,431 | 9,346 |
| `IDENTIFIABLE_IMAGE` | 15,019 | 13,934 |

**55,727 spans — 8.9% of all labels — never reached the model.** Every previous
training run used less data than the README claims.

---

## 5. Much of the "PII" is not personal data

The corpus is two document templates in roughly equal measure: **16,536
animal-welfare interview reports** and **15,903 dossiers about a named human**.
A large share of the sensitive labels in the former describe animals, not people
— and an animal is not a natural person under GDPR Art. 4(1).

| Finding | Evidence |
|---|---|
| 29.9% of `HEALTH_INFO` spans (15,769 of 52,778) sit in animal-welfare docs | describing lameness, matted coats, parasites in livestock |
| `IDENTIFIABLE_IMAGE` references essentially no identifiable person | top spans: `'bilder av dyrene'` 560×, `'bilder'` 395×, `'video tatt fra offentlig vei'` 198×, `'video'` 110× |
| `CONTEXT_SENSITIVE` has no coherent category | largest keyword bucket is animal/disease at 10.6%; weapons 9.9%, financial-crime 7.6%, org names 3.9% |
| Animal names tagged as `PERSON` | `Luna` 106×, `Balder` 25×, `Odin` 22×, `Pus` 16×, `Rex` 15× — source: *"schæferen tror jeg heter «Rex»"* |

The practical consequence: **the current training data teaches the model that
dogs, sheep and photo attachments are sensitive personal data.**

### Where the animal line actually falls

`BEHAVIORAL_PATTERN` looks animal-heavy but mostly is not. Classifying its
15,941 verbatim spans by *grammatical subject*, not by whether an animal is
mentioned:

| Category | Spans | Share | Disposition |
|---|---:|---:|---|
| No animal mentioned | 12,172 | 76.4% | keep |
| **Human acts on animal** — `'sparke og slå hundene'`, `'Har sett eieren bli sint på hunden'` | 1,538 | 9.6% | **keep — owner conduct is real PII** |
| Ambiguous — `'kaste gjenstander etter hundene'`, `'sløve og apatiske'` | 1,565 | 9.8% | flag for review |
| **Animal is the subject** — `'Hunden bjeffer ofte'` | 666 | 4.2% | **exclude** |

Filtering on "mentions an animal" would have deleted 3,667 spans, including
1,538 spans of genuine owner-misconduct evidence. The distinction between *the
animal acting* and *a human acting on the animal* is load-bearing.

---

## 6. Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Span boundary = FULL CLAUSE** | Resolves the 4,310 boundary conflicts; richer context for a human reviewing a redaction. One exception: `POSTAL_CODE` (4 digits). |
| 2 | **Taxonomy = 16 types** | Cut `CONTEXT_SENSITIVE` (catch-all, no category >11%, worst conflict rate) and `IDENTIFIABLE_IMAGE` (identifies nobody). Survivors = the config's 15 **+ `BEHAVIORAL_PATTERN`**. |
| 3 | **Animal health stays in `HEALTH_INFO`** | Overrides the recommendation to cut it. In this domain an animal's condition is evidence of the owner's negligence and is treated as sensitive in the product's threat model. |
| 4 | **Exclude animal-subject conduct only** | 666 spans, not 3,667. Human-acts-on-animal spans are kept. |
| 5 | **`GOV_ID` nests inside `CRIMINAL_RECORD`** | Consistent with FULL CLAUSE and with existing practice (95% of `FAMILY_RELATION` spans containing a name already nest `PERSON`). |
| 6 | **Field-conditioned `NO_ADDRESS`/`POSTAL_CODE`** | Deliberately reverses the old majority (`'5000 Bergen'` was NO_ADDRESS 622× vs POSTAL_CODE 21×) because that majority contradicts both type definitions. |
| 7 | **Offense noun alone ⇒ `CRIMINAL_RECORD`** | No accusation verb required. Precedence: `CRIMINAL_RECORD` > `FINANCIAL_INFO` > `ECONOMIC_STATUS`. |

---

## 7. Projected impact

| | Spans |
|---|---:|
| Current | 629,098 |
| − non-verbatim (after auto-repair) | −3,012 |
| − `CONTEXT_SENSITIVE` (type cut) | −23,621 |
| − `IDENTIFIABLE_IMAGE` (type cut) | −15,016 |
| − `BEHAVIORAL_PATTERN` animal-subject | −666 |
| − unknown types | −11 |
| **Resulting** | **586,772** (−6.7%) |

Retyped rather than deleted: `ECONOMIC_STATUS` → `FINANCIAL_INFO` 3,805;
`ECONOMIC_STATUS` → `CRIMINAL_RECORD` 868. Flagged for model review: 1,565.

Entity types: **18 → 16**.

---

## 8. Tooling

`tools/validate_labels.py` — validates and repairs label files.

```bash
# audit
python tools/validate_labels.py data/combined_data.jsonl --all-types

# audit against the training config's type list
python tools/validate_labels.py data/combined_data.jsonl --config configs/config.yaml

# write a mechanically repaired copy
python tools/validate_labels.py data/combined_data.jsonl --all-types --fix data/clean.jsonl
```

Repairs case and whitespace mismatches by snapping the span to the document's
real characters, drops duplicates, unknown types and unrecoverable spans. Exits
non-zero when unrepairable violations remain, so it can gate a pipeline. Output
is idempotent: re-validating a repaired file reports zero violations.

---

## 9. Remaining work

1. **Gold set** — 300–500 documents annotated to the spec and adjudicated.
   Without it, "100% correct" is unverifiable and there is no way to prove the
   re-annotation improved anything.
2. **Deduplicate** the 2,548 repeated documents to a single authoritative label
   before training; contradictory copies are direct label noise.
3. **Relabel** against `ANNOTATION_SPEC.md`, with `validate_labels.py` as a hard
   gate on every batch. The corpus is ~22.6M tokens of source text, so this runs
   incrementally rather than in one pass.
4. **Fix the config** — add `BEHAVIORAL_PATTERN`, remove the two cut types, and
   correct the `README.md` 18-type table to 16.
5. **Measure** the old and new datasets against the gold set, then compare
   models trained on each.
