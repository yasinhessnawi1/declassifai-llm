# Batch B Adjudication — Ruling Log

118 disputes across 21 documents resolved against `docs/ANNOTATION_SPEC.md`. Recurring
patterns are grouped rather than repeated per-document. B13 (nested DATE_TIME) was applied
project-wide as a separate pass (see bottom section).

## Recurring pattern rulings (apply everywhere)

| # | Pattern | Governing rule | Ruling |
|---|---|---|---|
| P1 | `bevis for X` / `evidence of X` / `evidence suggests X` leading an offense clause | Additional Mechanical Rules ("verbs of diagnosis/accusation sit inside the clause"), by analogy to the explicitly-kept `mistanke om` hedge | Treat as an evidentiary hedge that stays **inside** the CRIMINAL_RECORD span (choose the longer option). Applies B003-0/1, B009-2/3, B010-0, B015-1. |
| P2 | `avvik ... som gir mistanke om X` (discrepancy that *gives rise to* suspicion) | Reporting/evidentiary-frame distinction | The circumstantial lead-in is dropped; only `mistanke om X` itself is tagged (the lead-in is the cause, not the fact). B004-1. |
| P3 | `X har/var/ble [tidligere] vaert/blitt PARTICIPLE ...` (subject + aux chain before a fact-carrying participle) | B1 (drop subject + leading aux, keep the participle/verb that carries the fact) | Drop the whole subject+aux(+vague adverb) chain down to the participle (`domt`, `involvert`, `truet`, `suspected`, `rapportert`...). B004-0, B013-0 (=spec's own worked example), B015-0, B018-0, B019-1, B020-0/1, B021 POLITICAL_CASE boundary "kjent for..." (P6). |
| P4 | Multi-symptom sentences joined by "og" (`X ser Y ut, og Z`) | B1 "one clause, one fact" / multi-clause split worked example | Split into one HEALTH_INFO span per symptom, stripping the discontinuous `ser...ut`/`virker` hedge from each. B008-1/3, B012 (all 4), B014-0/1/2/5/8/9, B016-0/1. |
| P5 | Section headings inside the numbered "Skriftlig veiledning" list (`N. Forfalskning av X:`) vs. the same fact stated in running prose elsewhere | B6 (agency findings are taggable; boilerplate/labels are not) | The numbered category **heading** is treated like a structural label (excluded), the same fact restated as a sentence elsewhere in the document is tagged normally. B004-5, B009-8, B019-4 excluded; B019-2 (prose sentence) included. |
| P6 | `kjent for a vaere/sin X` before an actual affiliation verb (`tilknyttet`, `aktivisme i`) | Reporting/reputation-frame distinction (analogous to `hevder`, `ifolge`) | `kjent for ...` is a reputation-attribution frame, dropped; span starts at the real affiliation word. B018-1, B020-2. |
| P7 | Quoted business/organisation names preceded by a generic category noun (`Restaurant "X"`, `gardsbruk "X"`) | Global Rule 1 (verbatim) + POLITICAL_CASE's explicit quote-preservation rule, extended | Keep the genuine source quotation marks around the proper name; drop the generic category noun. B001-2 -> `"Sjomatdrommen"`; B003-2, B015-2 -> option already matched this. |
| P8 | A quoted name whose closing quote sits **after** a trailing comma in the source (`"Norges Frihet,"` / `"Nasjonal Renessanse,"`) | POLITICAL_CASE Extraction-not-summarisation rule (`"Nordisk Samhold` worked example) | Stop before the comma; do not synthesize a closing quote the source places elsewhere. B015-3, B021-2. |
| P9 | A concrete quantified financial/offense fact embedded in a sentence that also states a separate criminal offense, joined by "and"/"og" (`undeclared income, inflated expenses, and tax evasion`) | B11 one-clause-one-fact + FINANCIAL_INFO/CRIMINAL_RECORD precedence | Split: the offense noun alone is CRIMINAL_RECORD; the concrete financial figures are their own FINANCIAL_INFO span (nested inside or adjacent to the criminal clause). B009-0/3/10/11, B019-0/3/5, B021-0/6. |
| P10 | Second/later in-document occurrence of an address, family collective, disease name, or political-affiliation fact that only one annotator caught | "tag every valid occurrence, not just the first" (implied by presence-recall orientation throughout the spec) | Tagged, consistent with the first occurrence. B004-4, B007-1, B011-4, B015-6, B018-5/7, B021-4. |
| P11 | Title/honorific + bare surname referring anaphorically to an already-fully-named person (`Fru Hansen`, `Dr. Bjorgen`, `Mr. Askeland`) | PERSON Include's own example `Fru Berglund`/`Mr. Halvorsen` (title+surname, no given name, is a valid "full referring expression") | Included as PERSON. B009-7, B010-4, B013-3, B021-3. See question (d) below for the *bare* (no-title) surname case, which is excluded. |

## (a)-(d) recurring-question rulings

**(a) Negated hedge constructions** (`ser ikke ut til a vaere vann tilgjengelig`): B1's
`ser ... ut` stripping instruction was written for the affirmative case and would delete the
negation and invert the finding if applied literally. **Ruling: tag the fact, but keep the
negator inside the span rather than stripping the discontinuous `ser...ut` frame** -- drop only
the leading grammatical subject (`Det`), keeping `ser ikke ut til a ...` intact as one
contiguous, meaning-preserving span. Applied at B008-2 (`ser ikke ut til a vaere vann
tilgjengelig for hunden`, HEALTH_INFO). Where *both* annotators had already silently agreed
to skip a negated-hedge sentence elsewhere (e.g. B014's "Det ser ikke ut som den har noe
form for ly eller hus" / "Jeg har ikke sett noe vannskal"), that silent agreement was left
undisturbed -- resolving the 118 flagged disputes does not license relitigating spans neither
annotator raised.

**(b) Facility/environment conditions vs. the animal's own body** (dirty cage, no shelter,
chained to a tree, dirty barn): **Ruling, split in two:**
- Pure structural/housing facts with **no stated human actor** (`lenket til et tre i hagen`,
  `Darlig hygiene i fjoset`, `Manglende isolering av syke dyr`, `Manglende renhold i dyrenes
  oppholdsomrade`) are **not BEHAVIORAL_PATTERN** (BEHAVIORAL_PATTERN's own 4.2%
  animal-subject exclusion applies: the grammatical subject of these bare nominal findings,
  before any tagging, is the facility/animal, not an identified person performing an
  action) -- and they are **not HEALTH_INFO** either, since they describe the premises, not a
  physical/medical symptom of the animal. Left **untagged**, matching the "no home in the
  taxonomy" treatment the spec already gives the dropped CONTEXT_SENSITIVE animal-condition
  bucket.
- **Sustenance/resource-access deprivation directly affecting the animal** (no food, no
  water, "Utilstrekkelig for og vann") is treated as **HEALTH_INFO**, not BEHAVIORAL_PATTERN
  and not untagged -- this matches this batch's *own already-agreed* precedent (`mangle
  tilgang til vann`, `mangle tilstrekkelig mat, vann og passende leveomrader` in B005 were
  agreed HEALTH_INFO by both annotators already) and the animal-welfare threat model's
  express purpose (symptoms/conditions "evidencing the owner's negligence").
Rejected: B006-4/5, B014-3/4/7, B018-2/3/4. Accepted as HEALTH_INFO: B006-8, B014-6, B017-1/2,
B018-6.

**(c) Commercial food-hygiene/business-inspection findings vs. structurally identical
animal-husbandry findings**: **Ruling: apply exactly the same rule symmetrically, regardless
of domain.** BEHAVIORAL_PATTERN's definition of "conduct of an identifiable person" has no
textual carve-out for animals vs. commerce; both annotators already (silently, consistently)
declined to tag bare commercial-inspection bullet findings ("Mangelfull handhygiene blant de
ansatte", "Rotter i kjokkenomradet") as BEHAVIORAL_PATTERN in every restaurant/bakery/
kindergarten document in this batch. Rule (b)'s exclusion of animal-husbandry facility
findings with no named human actor simply extends that same, already-unanimous commercial
practice to the animal-welfare documents, rather than creating a double standard where an
identical inspection-bullet finding is tagged only when the premises house animals.

**(d) Bare anaphoric surnames / non-enumerated identifier labels**:
- *Bare surname alone* (no honorific, no given name) used anaphorically after the full name
  was already introduced: **not tagged PERSON.** It fails PERSON's "full referring
  expression" requirement, and no example in the spec supports tagging a bare surname as
  anaphora (the one enumerated exception, `Familien X`, is a household label, not an
  individual reference). This batch's own agreed data is unanimous on this (repeated bare
  "Hansen" mentions in B001/B013 were never agreed-tagged).
- *Honorific + bare surname* (`Fru Hansen`, `Dr. Bjorgen`, `Mr. Askeland`): **tagged
  PERSON**, per the spec's own Include example `Fru Berglund`/`Mr. Halvorsen` (title+surname
  with no given name is an explicitly valid "full referring expression").
- *Non-enumerated identifier labels*: **extend GOV_ID to any label naming a
  government/state-issued permit or licence** (`lisensnummer` for a firearms licence -- same
  logic the spec already uses to add `Forerkortnummer` outside the original 6-label
  enumeration). **Do not extend GOV_ID to an institution's internal record locator**
  (`journalnummer` for a hospital case file) -- this is treated like `Referanse:`, excluded
  as the institution's own administrative routing metadata, not a government-conferred
  identifier. (`lisensnummer: HG123456` in B011 was a live dispute, resolved GOV_ID;
  `journalnummer H1234567` in B001 was never actually disputed by either annotator -- both
  had already silently excluded it, consistent with this ruling.)

## B13 -- nested DATE_TIME additions (new rule, applied project-wide)

B13 was applied to every CRIMINAL_RECORD/HEALTH_INFO/FAMILY_RELATION/BEHAVIORAL_PATTERN/
ECONOMIC_STATUS/FINANCIAL_INFO/EMPLOYMENT_INFO/POLITICAL_CASE/SEXUAL_ORIENTATION span in the
final gold set (agreed spans included, not just disputes), by scanning for a calendar date or
bare year appearing as its own token, and cross-checking it against every GOV_ID span in the
same document so that a date-shaped digit run that is structurally part of a case number or
fodselsnummer (`TOSLO-2018-12345`, `sak nr. 2010/12345`, `2023/45678`) is never additionally
tagged. **17 DATE_TIME spans were added:**

- Nested inside the final CRIMINAL_RECORD span (15): B003 `2021`, `2018`; B004 `2017`; B006
  `2019`, `2022`; B010 `2010`; B013 `2020`, `2022` (from the `2020-2022` range); B015 `2018`;
  B018 `2021`, `2022`, `2020`; B019 `2022`; B020 `2017`; B021 `2015`.
- Recovered per B13's own worked example, where B1's contiguity rule forces the year out of
  the final narrative span (`I 2018 var hun involvert...` / `det ble i 2019 rapportert en
  hendelse...`) (2): B013 `2018`, B020 `2019`.

No additions were made to HEALTH_INFO, FAMILY_RELATION, ECONOMIC_STATUS, FINANCIAL_INFO,
EMPLOYMENT_INFO, POLITICAL_CASE, or SEXUAL_ORIENTATION spans -- none of the final spans in
those types contained a standalone calendar date/year in this batch.

## One-off boundary calls (not part of a recurring pattern)

- **B009-4** HEALTH_INFO `"currently undergoing treatment for Type 2 diabetes"` vs
  `"undergoing treatment for Type 2 diabetes"`: kept `"currently"` (Global Rule 2, full
  clause -- a leading adverb that is part of the same fact, not a droppable subject/aux).

## Notes on genuinely close calls

- **B006 "hans kroniske depresjon og type 2 diabetes har forverret seg"**: two diagnoses
  share one trailing verb (`har forverret seg`), which the HEALTH_INFO split-conjoined-
  diagnoses precedent would normally divide into two spans, but the verb cannot be
  duplicated across two contiguous substrings without inventing text. Resolved by keeping
  the single combined span (option with the possessive `hans` kept per B10) rather than
  fabricating an unsupported split.
- **B015 "hatefulle ytringer og trusler rettet mot minoriteter" / "historie av hatefulle
  ytringer og trusler rettet mot minoriteter"**: the two annotators disagreed on both type
  (BEHAVIORAL_PATTERN vs. CRIMINAL_RECORD) and extent for the same underlying fact. Resolved
  as CRIMINAL_RECORD (hate speech and threats are themselves per-se offenses under the
  CRIMINAL_RECORD precedence rule, not mere conduct) at the fuller extent (`historie av ...`),
  since "historie av" is a pattern/recurrence qualifier the spec's own boundary language
  treats as load-bearing.
- **B021 "the presence of unregistered firearms on the premises, although this was not
  confirmed during the inspection"**: kept the trailing disconfirming clause rather than
  truncating to a bare (falsely more-confirmed-sounding) allegation, consistent with Global
  Rule 4's "extraction, not summarization" and the batch's own precedent (SEXUAL_ORIENTATION)
  that an unconfirmed/alleged fact is still tagged in full, including its own hedge.
