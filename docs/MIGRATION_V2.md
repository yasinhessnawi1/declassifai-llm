# Migration of the annotated sets to the v2 taxonomy

**Written for:** the session that owns `data/synthetic/taxonomy.json`, and anyone using
`data/gold_v2/` or `data/slice_v2/`. Sections 3 and 4 need a decision from that session or
the project owner; the rest is a record.

## 1. What was migrated

The 400-document gold set and the 1,000-document relabel slice were annotated against the
17-type spec in `docs/ANNOTATION_SPEC.md`. `tools/migrate_to_v2.py` relabels them into the
59-type v2 taxonomy and writes `data/gold_v2/` and `data/slice_v2/`. The 17-type files are
left untouched as the record.

**Span boundaries were not re-decided.** They were adjudicated under 32 boundary rules; the
migration changes labels only. Eleven legacy types are pure renames (`NO_ADDRESS`→`ADDRESS`,
`NO_PHONE_NUMBER`→`PHONE`, `EMAIL_ADDRESS`→`EMAIL`, `CRIMINAL_RECORD`→`CRIMINAL`, …). Six are
split by rule:

| Legacy | v2 | Spans |
|---|---|---:|
| GOV_ID | CASE_NUMBER 1,586 · NATIONAL_ID 1,069 · ORG_NUMBER 679 · LICENSE_PLATE 14 · DRIVER_LICENSE 9 · PASSPORT 7 · TAX_ID 3 · IDENTITY_CARD 1 | 3,368 |
| HEALTH_INFO | HEALTH 8,420 · MEDICATION 93 | 8,513 |
| DATE_TIME | DATE_TIME 2,723 · DATE_OF_BIRTH 465 · AGE 1 | 3,189 |
| EMPLOYMENT_INFO | EMPLOYMENT 1,216 · ORGANIZATION 776 | 1,992 |
| FAMILY_RELATION | FAMILY_RELATION 1,055 · MARITAL_STATUS 370 | 1,425 |
| FINANCIAL_INFO | FINANCIAL 807 · BANK_ACCOUNT 3 | 810 |

Result: 1,400 documents, 35,125 spans, 30 of 59 v2 types populated, every file valid against
v2 (`validate_labels.py --taxonomy data/synthetic/taxonomy.json`). The only spans not carried
over are the 22 in section 3.

**Every non-default bucket was read before writing, and that changed the rules.** Five
keyword rules produced wrong labels that only reading caught: `lam`/`lammet` (lamb, not
lame) into DISABILITY; `står på` (lights on) and `medisinske` (adjective) into MEDICATION;
and a bare `reg.nr.` sending a rifle and two fishing vessels into LICENSE_PLATE. Each is
fixed in the script with a comment saying why. Treat any future rule the same way: sample
the bucket before trusting the count.

## 2. Contradictions inside v2 itself

These are resolved in the migration so the data is consistent, but the taxonomy should be
amended so the next labeller does not hit them.

1. **FAMILY_RELATION and MARITAL_STATUS both claim a status with a named partner.**
   FAMILY_RELATION includes "marital/partnership status with named spouse/partner";
   MARITAL_STATUS includes "status with named spouse/partner in the same clause". Resolved by
   letting the more specific type win: `gift med Astrid Åsland`, `hans samboer, Astrid Olsen`
   are MARITAL_STATUS. Kinship stays FAMILY_RELATION, and so do `skilsmisse`/`separasjon`,
   which FAMILY_RELATION's include list names explicitly.
2. **ORGANIZATION and EMPLOYMENT both claim the workplace of a named subject.**
   ORGANIZATION's definition includes "the workplace of a named subject"; EMPLOYMENT includes
   "a bare company/employer name when it identifies where the person works". Resolved with a
   learnable line: a bare organisation name is ORGANIZATION, a role or occupation phrase is
   EMPLOYMENT. Whether an organisation is tagged at all was already decided by B19.
3. **DATE_OF_BIRTH says "an explicit calendar date", but birth years are common.**
   `f. 1972` states a birth unambiguously; DATE_TIME would lose that. Migrated to
   DATE_OF_BIRTH. The definition should read "date or year".

## 3. Identifiers v2 has no type for — 22 spans parked

`data/migration_v2_pending.jsonl` holds these with context. They are not lost and not forced
into the nearest-looking type.

- **Firearms licence and card numbers — 16 spans.** `våpenkortnummer`, `lisensnummer`,
  `permit number`, and a rifle's `registreringsnummer`. State-issued by the police, so GOV_ID
  under B20. v2 has DRIVER_LICENSE and MEDICAL_LICENSE but no firearms licence, and weapon
  ownership recurs constantly in the dossier template.
- **Vessel registrations — 6 spans.** `KF-4789`, `SF-4278`, `NO-12345`: a state registration
  mark identifying a fishing vessel's owner. LICENSE_PLATE is defined for vehicles.

Two clean options: add `FIREARMS_LICENSE` and `VESSEL_REGISTRATION`, or broaden
LICENSE_PLATE to "a vehicle or vessel registration mark" and add only the firearms type.

## 4. Still unpopulated — 29 types

Nothing in the annotated sets carries these, because the 17-type spec never asked for them:

CREDIT_CARD, CRYPTO, DEVICE_ID, FAX_NUMBER, IBAN, INSURANCE_NUMBER, IP_ADDRESS,
MEDICAL_LICENSE, MILITARY_ID, PASSWORD, SOCIAL_MEDIA, STUDENT_ID, URL, USERNAME,
VISA_NUMBER, ACADEMIC_RECORD, ANIMAL_INFO, GENDER, LOCATION, NATIONALITY, AGE_INFO,
BIOMETRIC_DATA, CONTEXT_SENSITIVE, DISABILITY, ETHNICITY, GENETIC_DATA,
IDENTIFIABLE_IMAGE, IMMIGRATION_STATUS, TRADE_UNION.

Most of the Tier A ones (IBAN, IP_ADDRESS, URL, CREDIT_CARD) are regex-findable and may
simply be absent from this corpus. The judgement ones need an annotation pass.

**CONTEXT_SENSITIVE and IDENTIFIABLE_IMAGE need an owner decision before that pass.** Both
were cut from the 16-type spec early on — neither identifies a natural person under GDPR
Art. 4(1), and CONTEXT_SENSITIVE was a 24,000-span catch-all in the original corpus. v2
reinstates both. That should be a deliberate choice rather than inherited.
