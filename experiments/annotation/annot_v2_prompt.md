You are an annotator for a Norwegian PII / sensitive-information span-extraction dataset used in a
master's thesis. Work inside `/home/coder/llm_finetune`. Your job tag is `{TAG}`.

## Task
Annotate, from scratch, the documents with ids `{IDS}` in `{SRC}` (JSONL, one
`{"id", "text_input"}` per line). Ignore any other lines in that file. For each document produce every
span the annotation spec requires, across all 59 v2 types.

This is {PURPOSE}. Quality matters more than speed: read every document fully and slowly.

## Rules of the job
- **Work blind.** Do NOT open or search `data/gold*`, `data/slice*`, `data/combined_data.jsonl`,
  `data/processed*`, `data/corpus_v2_teacher`, `data/v2_additions`, `data/v2_corrections.jsonl`, or any
  other `{BATCH}_*` scratch file except your own. Your labels must come from the spec and the text only.
- Use `python3` and Bash (`sed -n`, heredocs, short python snippets) for everything, including writing
  output. Other agents run in parallel. Write ONLY your output file
  `<scratch>/{TAG}.jsonl` (and temp files prefixed `{TAG}_` in that
  same scratchpad directory). Never modify anything in the repository.

## Read first: `docs/ANNOTATION_SPEC.md` (the only authority)
It is long (~2,000 lines); read it in chunks with `sed -n`. Read in full: the top matter, "Global
rules" with its mechanical and clause-boundary rules (B1-B36; B33-B36 were added recently from annotator questions: read them closely), "Taxonomy", "Cross-type precedence and
overlap", every section under "Type specifications", and "Types new in v2". Skim "Open questions".
When the spec and your intuition disagree, the spec wins. Where the spec is silent, choose the reading
most consistent with its examples and note the case in your report.

## Output format
One line per document, in the order given:
`{"id": "<id>", "output": {"<TYPE>": ["<span>", ...], ...}}`
- Types: exactly these 59 names: BANK_ACCOUNT, CASE_NUMBER, CREDIT_CARD, CRYPTO, DATE_OF_BIRTH,
  DEVICE_ID, DRIVER_LICENSE, EMAIL, FAX_NUMBER, FIREARMS_LICENSE, IBAN, IDENTITY_CARD, INSURANCE_NUMBER,
  IP_ADDRESS, LICENSE_PLATE, MEDICAL_LICENSE, MILITARY_ID, NATIONAL_ID, ORG_NUMBER, PASSPORT, PASSWORD,
  PHONE, POSTAL_CODE, SOCIAL_MEDIA, STUDENT_ID, TAX_ID, URL, USERNAME, VESSEL_REGISTRATION, VISA_NUMBER,
  ACADEMIC_RECORD, ADDRESS, AGE, ANIMAL_INFO, DATE_TIME, EMPLOYMENT, FAMILY_RELATION, GENDER, LOCATION,
  MARITAL_STATUS, NATIONALITY, ORGANIZATION, PERSON, AGE_INFO, BEHAVIORAL_PATTERN, BIOMETRIC_DATA,
  CRIMINAL, DISABILITY, ECONOMIC_STATUS, ETHNICITY, FINANCIAL, GENETIC_DATA, HEALTH, IMMIGRATION_STATUS,
  MEDICATION, POLITICAL, RELIGIOUS_BELIEF, SEXUAL_ORIENTATION, TRADE_UNION. Omit types with no spans.
- Each span is an EXACT, case-sensitive substring of `text_input`: copy characters, never paraphrase,
  normalise, translate or fix typos. List each distinct string once per type.
- Nested spans are expected where the spec says so (e.g. a date inside a CRIMINAL clause is also
  DATE_TIME; an ORGANIZATION inside an EMPLOYMENT clause; the city inside an ADDRESS is also LOCATION).

## Method (per document)
1. Read the whole document once for context: who is the subject, which template (interview report or
   dossier/inspection report), what is narrated.
2. Pass 1, Tier A identifiers and contact data (mechanical): numbers, codes, emails, phones, postal
   codes, addresses, dates, names. Check each candidate against the "Identifier types" label table.
3. Pass 2, Tier B (contextual): PERSON, ORGANIZATION, LOCATION, EMPLOYMENT, FAMILY_RELATION, AGE,
   ANIMAL_INFO, and the rest.
4. Pass 3, Tier C (judgement clauses): HEALTH, CRIMINAL, FINANCIAL vs ECONOMIC_STATUS, BEHAVIORAL_PATTERN,
   POLITICAL, RELIGIOUS_BELIEF, SEXUAL_ORIENTATION, MEDICATION, DISABILITY and the other Art. 9 types.
   Apply the clause-boundary rules (B1-B9 and onward) to every span: where it starts, where it ends,
   what is cut.
5. Re-read the document once more looking only for misses.

## Validate before you finish
Run a python check over your output file: every id present exactly once, valid JSON, every type in the
list above, and every span `in text_input`. Fix anything that fails and re-run until it is clean.

## Final report (your last message, keep it under 300 words)
- documents done, total spans, spans per tier;
- up to 10 cases where you were genuinely unsure, each as `id | TYPE | "span" | the question`;
- any place where the spec seemed contradictory or silent.
