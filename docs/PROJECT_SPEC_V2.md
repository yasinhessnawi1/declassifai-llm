# Project spec v2 — taxonomy, generation, and model selection

**Written for:** the session building the synthetic document generator and running model
selection, working in parallel with an ongoing re-annotation effort. Supersedes
`docs/SYNTHETIC_DATA_SPEC.md` where the two disagree; that document's §2 (measured V100
constraints) and §6 (labels by construction) still stand and are not repeated here.

**You own:** `data/synthetic/`, `tools/generate_documents.py`, `docs/MODEL_SELECTION.md`.
**Do not touch:** `data/gold/`, `data/slice/`, `docs/ANNOTATION_SPEC.md`. Another session is
actively writing them. Report contradictions you find; do not fix them.

---

## 1. What changed

Three measurements from 2026-09-26 drive this revision.

**The corpus labels are unusable for the types that matter.** Scored against a
400-document adjudicated gold set, the existing Gemini labels reach 0.966 relaxed F1 on
seven mechanical types and **0.26–0.55 on five judgement types** — EMPLOYMENT_INFO,
CRIMINAL_RECORD, HEALTH_INFO, ECONOMIC_STATUS, BEHAVIORAL_PATTERN. It is a recall failure,
not a boundary one: 33% of HEALTH_INFO and 40% of CRIMINAL_RECORD spans are simply absent.
That is 42% of all spans. `docs/DATA_QUALITY.md` has the detail.

**The corpus is two document templates.** 32,439 documents, 55% animal-welfare interview
and 45% person dossier. Surface wording varies; genre does not.

**The taxonomy has a GDPR hole.** The current 16-type spec covers **three of the eight**
Article 9 special categories. Measured across the 400-document gold set:

```
religion      present in 148 / 400 documents    tagged as belief:   0
              present in 13,008 / 32,439 corpus documents
trade union   present in   0 real instances  (all "LO" hits are case-reference numbers)
ethnicity     present in   0
```

Religion is excluded by an open question in the annotation spec that has never been
resolved. For a project framed on Article 9, the category appearing in 40% of the corpus
is not optional. Trade union and ethnicity at zero cannot be fixed by sampling — only by
generating them, which is the strongest argument for this whole effort.

---

## 2. The taxonomy — 59 types in three tiers

The product's entity list carries 116 tiered entries (`_F` / `_A` / `_S` suffixes plus a
lowercase set). Collapsing the tier suffixes gives 78 stems; merging synonyms across tiers
(`NO_PHONE_NUMBER`/`PHONE`, `GOV_ID`/`NATIONAL_ID`/`NO_FODSELSNUMMER`, `VEHICLE_REG`/
`LICENSE_PLATE`, and so on) gives **59 distinct concepts**: 16 already in the annotation
spec, **43 new**.

Do not train one flat 59-way model. Split by how the type is actually decided:

- **Tier A — mechanical (28 types).** Decided by surface form and a field label. A regex or
  a checksum settles them; Presidio already does most. A model adds nothing and each extra
  class costs the judgement types capacity. Generate them, validate them, but resolve them
  deterministically at inference.
- **Tier B — contextual (13 types).** Need context but are not contentious: who is a
  PERSON, which string is the ADDRESS, whether an ORGANIZATION is the subject. The corpus
  is already good here (0.91–1.00 relaxed F1).
- **Tier C — judgement (18 types).** Clause-level, boundary-sensitive, and where the corpus
  collapses. This is the whole difficulty of the project and where the generated data has
  to be best. Ten of the Article 9 categories live here.

| Type | Tier | In spec? | GDPR |
|---|:--:|:--:|---|
| `BANK_ACCOUNT` | A | **NEW** |  |
| `CASE_NUMBER` | A | **NEW** |  |
| `CREDIT_CARD` | A | **NEW** |  |
| `CRYPTO` | A | **NEW** |  |
| `DATE_OF_BIRTH` | A | **NEW** |  |
| `DEVICE_ID` | A | **NEW** |  |
| `DRIVER_LICENSE` | A | **NEW** |  |
| `EMAIL` | A | yes |  |
| `FAX_NUMBER` | A | **NEW** |  |
| `IBAN` | A | **NEW** |  |
| `IDENTITY_CARD` | A | **NEW** |  |
| `INSURANCE_NUMBER` | A | **NEW** |  |
| `IP_ADDRESS` | A | **NEW** |  |
| `LICENSE_PLATE` | A | **NEW** |  |
| `MEDICAL_LICENSE` | A | **NEW** |  |
| `MILITARY_ID` | A | **NEW** |  |
| `NATIONAL_ID` | A | yes |  |
| `ORG_NUMBER` | A | **NEW** |  |
| `PASSPORT` | A | **NEW** |  |
| `PASSWORD` | A | **NEW** |  |
| `PHONE` | A | yes |  |
| `POSTAL_CODE` | A | yes |  |
| `SOCIAL_MEDIA` | A | **NEW** |  |
| `STUDENT_ID` | A | **NEW** |  |
| `TAX_ID` | A | **NEW** |  |
| `URL` | A | **NEW** |  |
| `USERNAME` | A | **NEW** |  |
| `VISA_NUMBER` | A | **NEW** |  |
| `ACADEMIC_RECORD` | B | **NEW** |  |
| `ADDRESS` | B | yes |  |
| `AGE` | B | **NEW** |  |
| `ANIMAL_INFO` | B | **NEW** |  |
| `DATE_TIME` | B | yes |  |
| `EMPLOYMENT` | B | yes |  |
| `FAMILY_RELATION` | B | yes |  |
| `GENDER` | B | **NEW** |  |
| `LOCATION` | B | **NEW** |  |
| `MARITAL_STATUS` | B | **NEW** |  |
| `NATIONALITY` | B | **NEW** |  |
| `ORGANIZATION` | B | **NEW** |  |
| `PERSON` | B | yes |  |
| `AGE_INFO` | C | **NEW** |  |
| `BEHAVIORAL_PATTERN` | C | yes |  |
| `BIOMETRIC_DATA` | C | **NEW** | **Art. 9** — biometric data |
| `CONTEXT_SENSITIVE` | C | **NEW** |  |
| `CRIMINAL` | C | yes | Art. 10 — criminal convictions and offences |
| `DISABILITY` | C | **NEW** | **Art. 9** — health |
| `ECONOMIC_STATUS` | C | yes |  |
| `ETHNICITY` | C | **NEW** | **Art. 9** — racial or ethnic origin |
| `FINANCIAL` | C | yes |  |
| `GENETIC_DATA` | C | **NEW** | **Art. 9** — genetic data |
| `HEALTH` | C | yes | **Art. 9** — health |
| `IDENTIFIABLE_IMAGE` | C | **NEW** |  |
| `IMMIGRATION_STATUS` | C | **NEW** |  |
| `MEDICATION` | C | **NEW** | **Art. 9** — health |
| `POLITICAL` | C | yes | **Art. 9** — political opinions |
| `RELIGIOUS_BELIEF` | C | **NEW** | **Art. 9** — religious or philosophical beliefs |
| `SEXUAL_ORIENTATION` | C | yes | **Art. 9** — sex life / sexual orientation |
| `TRADE_UNION` | C | **NEW** | **Art. 9** — trade union membership |

**Totals: 59 types — Tier A 28, Tier B 13, Tier C 18. 43 new. 10 are Article 9 categories.**

Note `CRIMINAL` is **Article 10** (criminal convictions and offences), not Article 9. The
research proposal conflates the two; keep them distinct in any writing.

Before adding a Tier C type, read how `docs/ANNOTATION_SPEC.md` handles the ones that
exist. Its 23 boundary rules were derived from adjudicating ~10,600 spans and most of the
hard cases you will hit are already decided there.

---

## 3. Generation: the guarantee and its limits

The design in `SYNTHETIC_DATA_SPEC.md` §6 stands and is the point of the whole approach:
**sample a typed record first, have the model realise it in a genre, locate labels by exact
string search, and discard any document where a planned value did not appear verbatim.**
That gives labels that are correct by construction rather than guessed.

Two things to be precise about, because the phrase "100% correct labelling guarantee" can
mean more than it does.

**What is guaranteed:** every emitted span is a real substring at a known position, of the
type the record said it was. No hallucinated spans, no boundary drift, no annotator
disagreement. This is a genuine and unusual property and it is worth building for.

**What is not guaranteed:** that the *set* of spans is complete, or that the document is
hard. Two specific failure modes to design against:

1. **Unplanned PII.** The model, writing naturally, invents a name or a date that was not
   in the record. It is real PII, it is unlabelled, and it teaches the detector to stay
   silent. Mitigation: after generation, run a mechanical sweep (Tier A regexes plus a
   capitalised-token pass) over the document and flag anything found that is not in the
   record. Either label it or regenerate. This check is not optional — it is the difference
   between "correct labels" and "complete labels".
2. **Slot learning.** If PII always sits in the same structural position, a model learns
   positions rather than language, and reports a score that will not survive contact with a
   real document. Vary slot position, sentence structure, whether a value appears in a
   field or mid-prose, and how often the same entity is restated.

---

## 4. Two datasets, not one

Keep these separate and never let them mix.

**The benchmark.** Held out, never trained on, published. Its job is to be *hard* and
*honest*: full genre spread, adversarial cases, ambiguity deliberately introduced,
including the linguistic ambiguity H3 is about. Size is not the point — a 2,000-document
benchmark that discriminates between models is worth more than 15,000 that everything
scores 0.99 on.

**The training set.** Large, varied, and allowed to be easier. This is where volume helps.

There is also a third set you already have and should not confuse with either: the
**400-document adjudicated gold set** in `data/gold/`. It is human-arbitrated annotation
over corpus documents, and it is the only evaluation material in this project that was not
produced by the same pipeline that produced the training data. That independence is its
entire value. Report against it separately, always.

---

## 5. Where Jev and Laya actually fit

Both were checked on 2026-09-26. Neither is a detector.

**Jev** (TypeSafe AI, released 2026-09-15) is a "System One" decision model: typed
structured output, sub-second, roughly $0.042/M input tokens. Its own documentation states
it **cannot tell you where PII is, cannot redact, and cannot replace a detector** — it
answers a yes/no/which-one question about a chunk of text. **Laya** is the open-source
Jev-compatible equivalent: a ModernBERT encoder with a decision head, served through ONNX
Runtime.

So: **no amount of fine-tuning makes either produce spans**, because neither has a span
head. Near-perfect span F1 is not on the table for them as shipped.

What they are good for:

- **Both are exactly the H2 pre-filter.** "Document likely contains PII vs. unlikely" is
  the job Jev is built for. This matters for the thesis in both directions: a cheap
  commercial model that does the pre-filter task is a **baseline the Tsetlin Machine now
  has to be compared against**, and ignoring it would be a visible gap. Benchmarking
  against it turns a threat into a result.
- **Laya's backbone is the interesting part.** ModernBERT fine-tuned for token
  classification *would* emit spans, which makes it a legitimate H1 candidate next to
  NorBERT. The open question is Norwegian coverage — ModernBERT is English-centric, so
  check for a Norwegian or multilingual variant and measure before committing. If Norwegian
  is weak, NorBERT-3 remains the better backbone regardless of Laya's other merits.
- **Jev is genuinely useful to you as a cheap screen during generation**: a fast
  "does this document contain PII of type X at all" check over thousands of candidates,
  before the expensive verification. Use it there.

---

## 6. Evaluation

Use `tools/score_agreement.py`; relaxed F1 is the project's primary metric and `--keys`
compares two label sets. Report strict alongside it — the gap between them *is* the
boundary disagreement, which is what sank the original corpus.

Three rules learned expensively during the annotation effort:

1. **A suspiciously high score is a finding, not a success.** If a detector reaches 0.98 on
   your benchmark, the first hypothesis is that the benchmark is template-shaped.
2. **Always report per type, split by document genre.** An aggregate over a mixture of
   genres describes neither. During the relabel, per-type rates computed against a mixture
   mean produced three false "outliers" that dissolved once conditioned on template.
3. **A keyword or regex count over documents is not evidence about spans.** Three separate
   rules in this project were derived from such counts and all three were wrong — the
   honorific `Dr.` count, the B19 principal test, and the B14 cramped-space rule. Read the
   matches before concluding anything. This is the single most repeated mistake in the
   project's history.

---

## 7. Corrections to carry into the research proposal

Two errors in the current proposal PDF, both worth fixing before submission.

**Table 2.1 is mislabelled.** It is titled "GDPR Article 9 Special Category Personal Data"
but four of its five rows are not Article 9: Personal Names, Identification Numbers,
Contact Information and Financial Data are ordinary personal data under Art. 4(1). Only
Health Information is Art. 9. The eight Art. 9 categories are racial or ethnic origin,
political opinions, religious or philosophical beliefs, trade union membership, genetic
data, biometric data for unique identification, health, and sex life or sexual orientation.

**Figure 4.1's worked example contains the label errors the thesis exists to fix.**
`Hunden bjeffer utrøstelig i mange timer` is tagged BEHAVIORAL_PATTERN, but that type
excludes animal subjects and the gold set puts welfare-framed animal vocalisation in
HEALTH_INFO. Separately, `jobber lange skift og virker stresset` (BEHAVIORAL_PATTERN)
overlaps `Eier jobber lange skift` (EMPLOYMENT_INFO) on the same text. Replace the figure
with an example drawn from `data/gold/`.

---

## 8. Ground rules

- `myenv/bin/python` for anything touching torch; `python3` otherwise. If `myenv/bin/python`
  vanishes after a workspace rebuild, repoint `myenv/bin/python3` at
  `/home/coder/.local/bin/python3.12` and fix `home`/`executable` in `myenv/pyvenv.cfg`.
- The Write/Read/Edit tools time out constantly here. Work through Bash.
- Start with 50 documents across 5 genres, run every validation gate, and report before
  scaling. A generator that runs overnight and produces 10,000 unusable documents is the
  expensive failure mode.
- Report measurements, not impressions, and say plainly when something did not work.
