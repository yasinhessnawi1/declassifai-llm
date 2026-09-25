# Batch J Recall Sweep Log

Reviewer pass over `batch_j_annotator1.jsonl` (16 docs, 400 spans) applying the
three post-annotation rule changes (B17 completeness, B18 confirmation, gambling
routing) plus a full recall sweep against `ANNOTATION_SPEC.md` rules B1-B18.

Starting spans: 400. Final spans: 406. Net: +6 (6 added, 0 removed, 3 boundary/retype fixes).

---

## Group 1 — B6 restatement misses (opening `Oppsummering` sentences)

Both J003 and J004 open with a summary sentence that names specific offenses
in wording that never recurs verbatim later in the document. Per B6
("A restatement is its own span... skipping the second as redundant was the
single largest genuine recall gap"), and in two of five cases the offense noun
is a straight *presence* miss (it is never named anywhere else in the doc), not
merely a duplicate restatement.

| Doc | Added span | Type | Basis |
|---|---|---|---|
| J003 | `mistanke om økonomisk kriminalitet` | CRIMINAL_RECORD | B6 restatement of the later `forfalskning av dokumenter og unndragelse av skatt` clause |
| J003 | `dyremishandling` | CRIMINAL_RECORD | Presence miss — bare offense noun named only here, no verb required (CRIMINAL_RECORD precedence rule) |
| J003 | `manipulasjon av tidligere inspeksjonsresultater ved Magnusson Gård` | CRIMINAL_RECORD | B6 restatement of the later `forsøkt å påvirke tidligere inspeksjonsresultater gjennom å tilby gaver til inspektører`; B16 (org conduct = named principal Leif Magnusson's conduct) |
| J004 | `dokumentasjonsforfalskning` | CRIMINAL_RECORD | Presence miss — this exact compound-word offense noun appears only in the opening sentence |
| J004 | `økonomisk kriminalitet` | CRIMINAL_RECORD | B6 restatement of the later `mistanke om økonomisk kriminalitet, herunder unndragelse av skatt og moms` |

Totals: **5 added**, all CRIMINAL_RECORD, all genuine annotator misses (not
forced by the three rule changes).

---

## Group 2 — Discovery-verb retention inconsistency

The annotator correctly kept discovery/evidentiary verbs (`avdekket`, `viste
tegn på`, `oppviser tegn på`, `tyder på`) inside spans in the large majority of
cases (verified against every occurrence of these four verbs across all 16
docs — 27 occurrences checked). Two occurrences of `tyder på` were stripped
inconsistently with the annotator's own practice elsewhere in the same
documents:

| Doc | Old span | New span | Basis |
|---|---|---|---|
| J005 | `ikke får den omsorgen de trenger` | `tyder på at de ikke får den omsorgen de trenger` | Same verb kept in J009 (`tyder på skatteunndragelse...`) and J011 (`tyder på mulig underernæring...`) |
| J011 | `stress og mistrivsel` | `tyder på stress og mistrivsel` | Same verb kept two sentences later in the same document (`tyder på mulig underernæring og manglende stell`) |

Totals: **2 boundary fixes**, both HEALTH_INFO, genuine annotator misses
(consistency errors, not forced by the three rule changes — though the
task's explicit note about not stripping discovery verbs guided the fix).

---

## Group 3 — Forced by rule change (3): gambling routing

J007: `Johansen innrømmet under inspeksjonen at han sliter med type 2
diabetes, kronisk depresjon og en spilleavhengighet som har ført til
betydelig gjeld (over 700 000 NOK).`

The annotator had filed `en spilleavhengighet` (the gambling *habit* itself)
under HEALTH_INFO, alongside the diabetes/depression diagnoses. Per the
project owner's gambling ruling: the habit is BEHAVIORAL_PATTERN (no clinical
diagnosis frame is present — only self-report `sliter med`), and the resulting
`betydelig gjeld (over 700 000 NOK)` correctly stays FINANCIAL_INFO as the
quantified outcome (ECONOMIC_STATUS would apply only if unquantified).

| Doc | Span | Old type | New type |
|---|---|---|---|
| J007 | `en spilleavhengighet` | HEALTH_INFO | BEHAVIORAL_PATTERN |

Totals: **1 retype**, forced entirely by rule change (3).

No other gambling-related spans exist anywhere in the batch (`spill` occurs
exactly once across all 16 documents), so this is the only gambling-routing
correction needed.

---

## Group 4 — Other genuine presence miss

J007: `Johansen eier et registrert haglegevær, som han hevder er til
jaktbruk, men det ble funnet usikret i stuen innen rekkevidde for barna (fra
et tidligere forhold) som av og til besøker ham.`

The rifle's *ownership* is lawful (registered) and correctly untagged, but the
fact that it was found unsecured within reach of children is a separate,
distinct storage-law violation (Norwegian firearms law requires secure
storage) that was missed entirely.

| Doc | Added span | Type | Basis |
|---|---|---|---|
| J007 | `funnet usikret i stuen innen rekkevidde for barna` | CRIMINAL_RECORD | Presence miss. Subject `det` (rifle referent) and auxiliary `ble` dropped per B1; span stops before the `(fra et tidligere forhold)` parenthetical (B4 — already separately tagged FAMILY_RELATION) |

Totals: **1 added**, genuine annotator miss.

---

## B17 / B18 consistency audit (no changes required)

Both rules were checked for consistency across all 16 documents rather than
just the one document the annotator had already anticipated them in:

- **B17** (nominalised-action subject kept, e.g. `Forfalskede veterinærattester ble
  funnet...` in J014): verified consistently applied in J003 (`Uregelmessigheter
  i regnskapet som tyder på forfalskning...`), J004 (`mangelfull og viste tegn
  på forfalskning`), J009 (`mangelfulle og viste tegn på forfalskning`), J013
  (`Mangelen på mat og rent vann` — evaluative tail `er også bekymringsverdig`
  correctly dropped, matching the spec's own worked example almost verbatim).
  No fixes needed.
- **B18** (BEHAVIORAL_PATTERN keeps its subject): verified consistently applied
  in J001 (`eieren bruker fjernkontrollen...`), J008 (`Mr. Olsen fremviste en
  uvanlig likegyldighet...`), J002 (dropping the subject before the
  no-reporting-wrapper predicate for Bjørn's school expulsion, correctly not
  extended across the B4 fødselsnummer-parenthetical boundary). No fixes
  needed.

## Other categories swept with no changes needed

Checked exhaustively and found already correct/consistent: NO_ADDRESS /
POSTAL_CODE field-conditioned nesting in all 16 docs; `Referanse:` never
tagged (7 bekymringsmelding docs); `Deres ref:`/blank-placeholder handling (6
inspeksjonsrapport docs); all B13 nested-date opportunities (verified by
script against every bare 1900s/2000s year in every document — all remaining
uncovered years are legitimately part of case-number/reference-number strings
and correctly excluded); B14 welfare-need vs. structural/cleanliness line for
every animal-condition sentence in J001, J005, J008, J010, J011, J013, J015,
J016; B16 organisation-conduct-to-named-principal attribution in J002, J003,
J004, J006, J014, J016; FAMILY_RELATION never applied to `nabo`/`venn`/
`kollega`/`eieren`; no duplicate spans within any type.

---

## Totals

- Starting spans: 400
- Added: 6
- Fixed (boundary or retype): 3
- Removed: 0
- Final spans: 406

Per-type final counts: HEALTH_INFO 100, CRIMINAL_RECORD 49, GOV_ID 48, PERSON
43, DATE_TIME 30, NO_ADDRESS 17, NO_PHONE_NUMBER 17, EMAIL_ADDRESS 17,
FAMILY_RELATION 17, POSTAL_CODE 16, EMPLOYMENT_INFO 15, FINANCIAL_INFO 9,
SEXUAL_ORIENTATION 9, POLITICAL_CASE 8, BEHAVIORAL_PATTERN 6, ECONOMIC_STATUS 5.

Validator: `violations: 0`, exit 0.
