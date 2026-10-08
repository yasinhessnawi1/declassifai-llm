# Taxonomy workstream notes

Scope: `data/synthetic/taxonomy.json`, `types_config.yaml`, `clause_bank.json`. Built from
`docs/PROJECT_SPEC_V2.md` §2 (the 59-type table) and `docs/ANNOTATION_SPEC.md` (16-type
spec, 23 boundary rules), cross-checked against `data/gold/batch_*_gold.jsonl` (read-only)
and `docs/DATA_QUALITY.md`. Nothing under `data/gold/`, `data/slice/`, or
`docs/ANNOTATION_SPEC.md` was modified.


## Owner decision, 2026-10-08: CONTEXT_SENSITIVE and IDENTIFIABLE_IMAGE dropped

The project owner ruled both types out ("no need"). This resolves contradiction 1 below
in favour of ANNOTATION_SPEC.md, which had already cut them with documented reasoning.
The synthetic taxonomy is now **57 types** (Tier A 28, Tier B 13, Tier C 16). Both were
removed from `taxonomy.json`, `types_config.yaml` and `clause_bank.json` (2 clauses and
4 negatives under CONTEXT_SENSITIVE). PROJECT_SPEC_V2.md §2 still lists 59 and is not
edited here.

## 2026-10-08: entries re-derived from the v2 ANNOTATION_SPEC

Every `definition`, `include`, `exclude`, `boundary` and `spec_rules` entry in
`taxonomy.json` was rewritten from the type's own section of `docs/ANNOTATION_SPEC.md`
(the 57-type v2 rulebook, commit 27ddd2e), using v2 type names only and B-rule ids as the
spec now numbers them (B1-B32). Where the two documents disagreed, the spec won. `name`,
`tier`, `gdpr`, `value_kind`, `legacy_type`, `legacy_map`, the type order and `version`
are unchanged. A top-level `legacy_map_note` records that gold and slice are now migrated
to v2 names (commit 87cfb30; `data/gold_v2/`, `data/slice_v2/`), so scoring against
gold_v2 uses v2 names directly and `legacy_map` serves only tools that emit the 17 legacy
names.

**Open question 22 (a)-(f) in the spec is resolved by this rewrite:**

- (a) FAMILY_RELATION no longer includes marital or partnership status; MARITAL_STATUS
  owns it by the lexical test (status word and no kinship noun).
- (b) EMPLOYMENT no longer includes a bare company name; that is ORGANIZATION, which also
  nests inside an EMPLOYMENT clause (B12, B19).
- (c) HEALTH's definition no longer lists disability or medication; DISABILITY and
  MEDICATION are their own types (animals stay HEALTH).
- (d) AGE is its own type, not DATE_TIME; DATE_OF_BIRTH is its own type, not a DATE_TIME span.
- (e) The Tier A entries state their rules directly (B20 issuer and label test) instead of
  mapping to the old single identifier type or claiming a gap in the old schema.
- (f) LOCATION states the rule: a place name inside an organisation's or authority's own
  name is not LOCATION; a city inside an ADDRESS value is LOCATION (nested), and so are
  Poststed, Fylke and Kommune place names.

Not decided by this rewrite: the spec has no `###` section of its own for the Tier A types
with no corpus instances (CREDIT_CARD, CRYPTO, DEVICE_ID, FAX_NUMBER, IBAN,
INSURANCE_NUMBER, IP_ADDRESS, MEDICAL_LICENSE, MILITARY_ID, PASSWORD, SOCIAL_MEDIA,
STUDENT_ID, URL, USERNAME, VISA_NUMBER) or for the other identifier types; they are covered
by the shared "Identifier types" section and its label table, and their entries here
summarise that. Spec open question 23 (generated documents that disagree with the spec) is
a generator task, not a taxonomy one.

## How the legacy_map was derived

Each of the 59 v2 types was checked against ANNOTATION_SPEC's own Include/Exclude lists and
boundary rules (B1–B24), not against name similarity. Three decision principles did most of
the work:

1. **B20's issuer test collapses 11 Tier-A identifier types into GOV_ID.** `CASE_NUMBER`,
   `DRIVER_LICENSE`, `IDENTITY_CARD`, `LICENSE_PLATE`, `MEDICAL_LICENSE`, `MILITARY_ID`,
   `NATIONAL_ID`, `ORG_NUMBER`, `PASSPORT`, `TAX_ID`, `VISA_NUMBER` are all issued by a public
   authority (politiet, Skatteetaten, Statens vegvesen, Forsvaret, Helsedirektoratet, UDI),
   which is GOV_ID's entire test. Conversely `INSURANCE_NUMBER` and `STUDENT_ID` are
   private/institutional issuers (parallel to B20's own excluded examples `lånenummer`,
   `medlemsnummer`) and map to `null` even though they look identical in shape to a
   government ID.
2. **FINANCIAL_INFO's "account/loan number, named creditor, named instrument" language
   absorbs the payment-identifier cluster.** `BANK_ACCOUNT`, `CREDIT_CARD`, `IBAN` are account
   identifiers under FINANCIAL_INFO's own Include list. `CRYPTO` is mapped there too, but with
   lower confidence — ANNOTATION_SPEC never anticipated crypto wallets, so this is an
   extrapolation from "named financial instrument," not a direct textual match; flagged below.
3. **Everything with no textual anchor in ANNOTATION_SPEC gets `null`, even where a name
   looks similar.** `RELIGIOUS_BELIEF`, `TRADE_UNION`, `ETHNICITY`, `BIOMETRIC_DATA`,
   `GENETIC_DATA`, `IMMIGRATION_STATUS`, `NATIONALITY`, `GENDER`, `LOCATION`, `ACADEMIC_RECORD`,
   `ANIMAL_INFO`, `DEVICE_ID`, `IP_ADDRESS`, `PASSWORD`, `SOCIAL_MEDIA`, `URL`, `USERNAME`,
   `FAX_NUMBER` have no Include-list anchor and no boundary rule at all in the 16-type spec —
   these will never score against the gold set no matter how they are generated, because
   nothing in gold was ever tagged that way. `CONTEXT_SENSITIVE` and `IDENTIFIABLE_IMAGE` are
   `null` for a different reason: ANNOTATION_SPEC explicitly **cut** both (see Contradiction 1
   below), so there is no legacy span population to map to even though the names exist.

Full `legacy_map` (grouped by destination):

| Legacy type | v2 types that map to it |
|---|---|
| GOV_ID | CASE_NUMBER, DRIVER_LICENSE, IDENTITY_CARD, LICENSE_PLATE, MEDICAL_LICENSE, MILITARY_ID, NATIONAL_ID, ORG_NUMBER, PASSPORT, TAX_ID, VISA_NUMBER |
| FINANCIAL_INFO | BANK_ACCOUNT, CREDIT_CARD, CRYPTO, FINANCIAL, IBAN |
| HEALTH_INFO | DISABILITY, HEALTH, MEDICATION |
| DATE_TIME | AGE, DATE_OF_BIRTH, DATE_TIME |
| FAMILY_RELATION | FAMILY_RELATION, MARITAL_STATUS |
| EMPLOYMENT_INFO | EMPLOYMENT, ORGANIZATION |
| EMAIL_ADDRESS | EMAIL |
| NO_PHONE_NUMBER | PHONE |
| NO_ADDRESS | ADDRESS |
| POSTAL_CODE | POSTAL_CODE |
| PERSON | PERSON |
| CRIMINAL_RECORD | CRIMINAL |
| POLITICAL_CASE | POLITICAL |
| BEHAVIORAL_PATTERN | BEHAVIORAL_PATTERN |
| ECONOMIC_STATUS | ECONOMIC_STATUS |
| SEXUAL_ORIENTATION | SEXUAL_ORIENTATION |
| **null** (22 types) | ACADEMIC_RECORD, AGE_INFO, ANIMAL_INFO, BIOMETRIC_DATA, CONTEXT_SENSITIVE, DEVICE_ID, ETHNICITY, FAX_NUMBER, GENDER, GENETIC_DATA, IDENTIFIABLE_IMAGE, IMMIGRATION_STATUS, INSURANCE_NUMBER, IP_ADDRESS, LOCATION, NATIONALITY, PASSWORD, SOCIAL_MEDIA, STUDENT_ID, TRADE_UNION, URL, USERNAME |
| RELIGIOUS_BELIEF | RELIGIOUS_BELIEF — added to ANNOTATION_SPEC.md as its 17th type (commit aef6e15), so this one now maps one-to-one. |

36 non-null mappings, 23 null. This means 23/59 v2 types — including 9 of the 10 Article 9
categories (only HEALTH-derived types and SEXUAL_ORIENTATION and POLITICAL have a home) —
generate data that **cannot** currently be scored against the 400-doc gold set. That is
itself the central finding of PROJECT_SPEC_V2 §1 restated at the taxonomy level: the schema
gap is exactly why RELIGIOUS_BELIEF/TRADE_UNION/ETHNICITY read as zero in gold.

### Low-confidence mappings (flagged, not resolved)

- **CRYPTO → FINANCIAL_INFO.** Extrapolated from "named debt/financial instrument," not a
  literal match — ANNOTATION_SPEC has zero crypto examples anywhere. If gold scoring shows
  this doesn't behave like other FINANCIAL_INFO content, this is the mapping to revisit first.
- **[RESOLVED: the spec makes FAX_NUMBER its own type under a Faks/Fax label] FAX_NUMBER → null, not NO_PHONE_NUMBER.** NO_PHONE_NUMBER's definition and Boundary rule
  are both keyed strictly to the Telefon/Tlf/Telefonnummer label family; a Faks/Fax label is
  never mentioned. Treated as excluded by the same field-label-authority logic that
  distinguishes NO_PHONE_NUMBER from GOV_ID. An alternative reading (fax is "the same kind of
  fact as phone") would map it to NO_PHONE_NUMBER instead — flagged as a judgement call.
  Likely moot in practice: fax numbers are close to absent from the corpus.
- **[RESOLVED: the spec makes GENDER a plain demographic value and puts a gender-identity disclosure in SEXUAL_ORIENTATION] GENDER → null, not SEXUAL_ORIENTATION.** SEXUAL_ORIENTATION's own definition explicitly
  covers "gender identity," but that is the *disclosure of being transgender/non-binary as a
  sensitive fact*, not the neutral `Kjønn: Mann/Kvinne` demographic field the v2 GENDER type
  actually describes (it sits in Tier B, "contextual, not contentious," alongside PERSON and
  ADDRESS — a data type ANNOTATION_SPEC never tags at all, similar to `Fylke:`/`Kommune:`
  bare fields). If v2's GENDER is intended to mean gender-identity disclosure instead, the
  mapping should move to SEXUAL_ORIENTATION.

## Contradictions found (report only, not resolved in ANNOTATION_SPEC or gold)

1. **[RESOLVED 2026-10-08: owner dropped both types; spec and taxonomy agree] v2 reinstates two types ANNOTATION_SPEC explicitly cut, with the cut's own reasoning
   still standing.** `CONTEXT_SENSITIVE` was removed for having "no positive membership
   test" and behaving as a dumping ground (3,345 presence conflicts, 338 type migrations,
   no keyword bucket over ~11% of its own content — see ANNOTATION_SPEC "Removed types").
   `IDENTIFIABLE_IMAGE` was removed because a targeted check for person-identifying image
   spans found **zero genuine hits** in the whole corpus. PROJECT_SPEC_V2 §2 lists both as
   **NEW** Tier C types with no acknowledgment that they were tried and removed one document
   over. Per this workstream's brief ("report contradictions, don't resolve them"),
   `taxonomy.json` keeps both types with `legacy_type: null` and a definition that quotes the
   removal reasoning; `clause_bank.json` deliberately gives `CONTEXT_SENSITIVE` only 2 seed
   examples (instead of the ~25 target) rather than manufacturing content for a type whose
   own removal rationale was "a spec that cannot state a positive rule for a residual case
   must not force an annotation." `IDENTIFIABLE_IMAGE` was set to `value_kind: "value"` and
   excluded from the clause bank entirely — if it is generated at all, it should be the
   pre-cut type's own short noun-phrase style (`bilder av dyrene`), not a judgement clause.
2. **[RESOLVED: v2 spec uses the v2 names and lists the renames] PROJECT_SPEC_V2's "16 already in the annotation spec" count doesn't reconcile 1:1 by
   name.** The table marks 16 v2 rows "yes" (in spec): `EMAIL`, `NATIONAL_ID`, `PHONE`,
   `POSTAL_CODE`, `ADDRESS`, `DATE_TIME`, `EMPLOYMENT`, `FAMILY_RELATION`, `PERSON`,
   `BEHAVIORAL_PATTERN`, `CRIMINAL`, `ECONOMIC_STATUS`, `FINANCIAL`, `HEALTH`, `POLITICAL`,
   `SEXUAL_ORIENTATION` — but the 16-type ANNOTATION_SPEC taxonomy table uses different surface
   names for most of these (`GOV_ID` not `NATIONAL_ID`, `NO_PHONE_NUMBER` not `PHONE`,
   `NO_ADDRESS` not `ADDRESS`, `EMPLOYMENT_INFO` not `EMPLOYMENT`, `CRIMINAL_RECORD` not
   `CRIMINAL`, `FINANCIAL_INFO` not `FINANCIAL`, `HEALTH_INFO` not `HEALTH`, `POLITICAL_CASE`
   not `POLITICAL`). The "yes" column is true only under a synonym merge PROJECT_SPEC_V2's own
   prose describes ("merging synonyms across tiers... `NO_PHONE_NUMBER`/`PHONE`... gives 59
   distinct concepts") but the table itself never states the synonym pairing explicitly. This
   `legacy_map` is exactly that missing explicit pairing.
3. **[RESOLVED: the v2 spec has an AGE_INFO section (B1, B17)] AGE_INFO (v2 Tier C, "NEW") already existed in the pre-spec corpus and was dropped as an
   unknown type**, per `docs/DATA_QUALITY.md` §2: `ANIMAL_INFO`, `AGE_INFO`, and `AGE` (6
   spans total) were mechanically dropped by `tools/validate_labels.py` as "Unknown entity
   type" before ANNOTATION_SPEC was even written. PROJECT_SPEC_V2 calling it "NEW" is only
   true relative to the 16-type spec, not relative to the raw corpus's own label vocabulary —
   worth knowing before assuming AGE_INFO synthetic data is testing genuinely novel ground.
4. **[RESOLVED: AGE is its own type with a boundary rule; a detached age is no longer DATE_TIME] Tier B `AGE` vs. Tier C `AGE_INFO` split has no boundary precedent to inherit.** The only
   thing ANNOTATION_SPEC says about a bare age number is embedded in FAMILY_RELATION's own
   resolved-conflicts note: a detached `10 år` is DATE_TIME, and an age is only kept when it
   is a family-member's parenthetical (per B4). Nothing in the spec anticipates a *judgement*
   use of age (vulnerability, incapacity, being a minor) as its own sensitive fact — this
   workstream invented `AGE_INFO`'s clause-boundary treatment from B1/B17 by analogy, not from
   an existing rule, and it has the thinnest gold precedent of any Tier C type in this bank.
5. **[RESOLVED by the annotation session, commit aef6e15]** RELIGIOUS_BELIEF is now ANNOTATION_SPEC.md's 17th type, so it maps one-to-one in `legacy_map`. The original note follows for the record.

   **RELIGIOUS_BELIEF is exactly ANNOTATION_SPEC's own Open Question 17, unresolved for over
   500 lines of spec.** ANNOTATION_SPEC states plainly: "the fixed 16-type taxonomy has no
   religion/belief type, roughly 300+ spans will go untagged unless the project owner decides
   religion should get its own type." PROJECT_SPEC_V2 §1 independently measures religion
   present in 148/400 gold documents (40% of corpus) and tagged as belief zero times, and
   frames this as the strongest argument for the whole generation effort. v2 answers Open
   Question 17 by simply adding the type — but that answer lives in a different document than
   the one authorized to change ANNOTATION_SPEC, so the 400-doc gold set will still show zero
   RELIGIOUS_BELIEF spans no matter how good the synthetic data is, until someone re-opens
   ANNOTATION_SPEC itself. Flagged, not fixed, per this workstream's mandate.
6. **[RESOLVED: the spec states a case number containing `LO` is never TRADE_UNION] TRADE_UNION's own justification is an artifact, not a population.** PROJECT_SPEC_V2 §1:
   "trade union present in 0 real instances (all 'LO' hits are case-reference numbers)." That
   is evidence the *string* "LO" appears in the corpus, not evidence that trade-union content
   exists to be captured. The clause bank's TRADE_UNION negatives section documents this
   explicitly (`Saksnummer 2019/LO-4521` as the canonical false positive) so generation doesn't
   quietly reintroduce the same artifact PROJECT_SPEC_V2 diagnosed.
7. **[RESOLVED: the v2 spec tables CRIMINAL as Art. 10] CRIMINAL is Art. 10, not Art. 9 — both source documents agree, but the table layout
   invites the opposite reading.** PROJECT_SPEC_V2's own §2 table lists `CRIMINAL` in the same
   GDPR column as the Art. 9 types with only the row text distinguishing "Art. 10" from "Art.
   9," and §7 separately flags that the *research proposal* PDF mislabels a table the same
   way ("Table 2.1 is mislabelled... Only Health Information is Art. 9"). `taxonomy.json`
   keeps `CRIMINAL`'s `gdpr` field as the literal string `"Art. 10 — criminal convictions and
   offences"` rather than folding it under a generic `Art. 9` bucket, to avoid reproducing
   that exact, already-diagnosed error a third time.
8. **[RESOLVED: B19 now tags the subject organisation as ORGANIZATION] B19's organisation rule complicates the clean `ORGANIZATION → EMPLOYMENT_INFO` mapping.**
   B19 only tags an organisation as EMPLOYMENT_INFO "when the organisation is a subject of the
   document" — an incidentally-mentioned company (a reporter's own employer, a neighbour's
   workplace) is explicitly *not* tagged. `ORGANIZATION` as a v2 Tier B type ("whether an
   ORGANIZATION is the subject," per PROJECT_SPEC_V2's own Tier B description) is actually
   narrower than "any organisation name" — generated data must encode the subject-vs-incidental
   distinction or it will systematically over-generate compared to what the gold set would
   ever tag.
9. **[RESOLVED for scoring: gold_v2 separates the three types; only the legacy detector still pools them] DISABILITY, HEALTH, and MEDICATION all collapse to the single legacy type HEALTH_INFO**,
   which means the v2 taxonomy is finer-grained than what can be scored: a synthetic
   DISABILITY span and a synthetic MEDICATION span are indistinguishable once compared against
   gold. This is intentional per the task brief (collapse tiered variants), but it means
   per-v2-type precision/recall against gold is not obtainable for these three — only the
   pooled HEALTH_INFO number is.

## Other decisions worth flagging

- `value_kind` was set to `"clause"` for all 17 Tier C types except `IDENTIFIABLE_IMAGE`
  (kept `"value"`, matching its pre-cut short-noun-phrase examples in ANNOTATION_SPEC) and
  for the 3 Tier-B types the task named as clause-like (`EMPLOYMENT`, `FAMILY_RELATION`) plus
  `ACADEMIC_RECORD` (judgement call — no ANNOTATION_SPEC precedent exists for it, but it reads
  naturally as a full-clause fact in the same style as EMPLOYMENT_INFO's own B12 boundary
  rule, not a bare token).
- **[RESOLVED 2026-10-08: spec_rules now cite B1-B32 as the spec numbers them, and boundary text states the rules directly]** `spec_rules` cited only literal B1–B24 rule IDs. Several types are governed by unlettered,
  type-specific rules instead (e.g. HEALTH_INFO's own (a)/(b)/(c)/(d) subcategory rules,
  POSTAL_CODE's "4 digits only" exception, the FINANCIAL_INFO/ECONOMIC_STATUS precedence
  chain) — those are described in prose in each type's `boundary` field rather than forced
  into a B-code that doesn't exist for them.
