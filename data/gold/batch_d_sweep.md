# Batch D recall sweep log

Starting spans: 483. Added: 20. Removed: 0. Final: 503.
Validator: `violations: 0`, exit 0.

## Removals

None. A full scan of every FAMILY_RELATION span in the batch (grep for
"nabo"/"venn"/"kollega") found zero non-kinship social-tie spans to begin
with — the annotator never tagged a "nabo til X" / "venn av X" pattern as
FAMILY_RELATION in this batch, so Rule Change 2 required no removals here.
D013's `familien Hansen` and D018's `... til en nabo` were checked
specifically (the exact shape the rule change targets) and are both fine:
D013 correctly excludes "nabo til" from the span and only tags the
household-collective name `familien Hansen` itself (consistent with the
`Familien Eriksen` convention, not a relationship tag); D018's "en nabo" is
embedded inside a CRIMINAL_RECORD clause (illegal weapon sale), never
tagged FAMILY_RELATION at all.

## Additions forced by the widened B14 (animal welfare needs) — 8 spans

All eight are cases where the deprived need is exercise/stimulation or
shelter/shade — the two categories the widening explicitly added (food,
water and vet-care deprivation were already in scope for this annotator
under the old rule, so misses in those categories are counted as genuine
misses below, not rule-change casualties).

- D008 HEALTH_INFO `ingen synlige klatrestrukturer, steiner, eller andre
  former for miljøberikelse` — lack of climbing structures/enrichment for
  goats; direct match to the widened rule's "stimulering" need.
- D008 HEALTH_INFO `ingen mulighet til å utøve sin naturlige atferd` —
  natural-behaviour/exercise deprivation, grammatical subject is "geitene"
  but still the animal's own need.
- D008 HEALTH_INFO `ingen klatremuligheter eller noe som helst form for
  berikelse i innhegningen, noe som kan føre til kjedsomhet og frustrasjon`
  — B6 restatement of the same enrichment deprivation in different words.
- D011 HEALTH_INFO `ser ikke ut til å få noe særlig oppmerksomhet eller
  mosjon` — exercise/attention deprivation stated about the dogs earlier in
  the document; a near-identical restatement later in the same doc
  (`får ikke den mosjonen og omsorgen de trenger`) WAS already tagged, this
  earlier one was missed.
- D012 HEALTH_INFO `begrenset tilgang til skygge` — matches the widened
  rule's own "lite skygge" example almost verbatim; the field's shade
  access, phrased as a property of the pasture, not the sheep.
- D014 HEALTH_INFO `lite skygge` — exact string match to the widened rule's
  worked example; property of the kennel yard ("Luftegårdene"), not the
  dogs, which is exactly the "test is whether a need is unmet, not who the
  grammatical subject is" case the rule change calls out.
- D015 HEALTH_INFO `lite plass til bevegelse, lek og naturlig atferd for
  disse aktive valpene` — exercise-space deprivation for the puppies,
  restated later in the doc in different words (`mangle tilstrekkelig
  bevegelse, stimulering og omsorg`, which was already tagged).
- D015 HEALTH_INFO `hindrer dem i å utfolde seg naturlig` — grammatical
  subject is "De små, trange kennelene" (the kennels), predicate denies the
  dogs' natural behaviour; this is the paradigm case of the rule's own test
  ("even when phrased as a property of the enclosure").

## Additions that are genuine annotator misses — 12 spans

### B6 restatement misses (same fact stated twice, second occurrence untagged)

- D007 HEALTH_INFO `synlige sår` — restates the earlier `åpne sår` (wound)
  finding in a "Vi har observert:" bullet, different wording.
- D007 HEALTH_INFO `tegn på infeksjon` — restates `tegn på infeksjoner`
  (singular vs. plural, different literal string) in the same bullet.
- D007 HEALTH_INFO `underernæring` — restates `tegn på underernæring` in
  the same bullet, bare noun this time.
- D011 (see widened-B14 list above; also partly a restatement miss)

### New findings the annotator simply missed (food/water — already in old B14 scope)

- D007 HEALTH_INFO `Manglende tilgang til rent vann` — a "Vi har
  observert:" bullet stating lack of clean water access; never mentioned
  elsewhere in the doc, plainly missed.
- D008 HEALTH_INFO `lite vegetasjon igjen` — little grazing vegetation left
  for the goats (food-source deprivation).
- D008 HEALTH_INFO `tilsynelatende mangelen på tilstrekkelig beite` —
  restates the same grazing/food shortage later in the same interview, in
  different words ("mangelen på tilstrekkelig beite").
- D011 HEALTH_INFO `lite gress der` — little grass left in the sheep's
  pasture, same food-deprivation logic as D008.
- D012 HEALTH_INFO `ser ut til å være forurenset av avføring` — the
  sheep's only waterhole appears contaminated by faeces; borderline against
  the cleanliness/structure carve-out, but this is about the drinking-water
  source's safety specifically, not general area hygiene, so it reads as a
  water-need fact rather than "Manglende renhold" boilerplate. Flagged
  below as a judgment call.

### Other genuine misses (non-HEALTH_INFO)

- D001 DATE_TIME `2021` — bare year inside the FAMILY_RELATION clause
  `Separert fra kona i 2021`; B13 requires nesting a DATE_TIME tag on any
  bare calendar year inside a narrative-type clause, and this one was
  never tagged even though the doc's other `2018` years were caught
  correctly.
- D001 EMPLOYMENT_INFO `Hordaland Dyretransport AS` — the company Lars
  Magnus Olsen owns ("firmaets eiers" was tagged, but the bare employer
  name itself, per B12, is tagged separately and was missed).
- D002 EMPLOYMENT_INFO `local fisherman` — Kjell Magnusson's occupation,
  mentioned only in passing as part of an affair description; a real,
  specific occupation tied to a named person, so it qualifies under
  EMPLOYMENT_INFO's own definition even though he's a minor character.
  Flagged below as a judgment call.
- D004 PERSON `Solveig Olsen` — Lars Kristian Olsen's wife, named inside
  the FAMILY_RELATION clause `gift med Solveig Olsen`; every other named
  individual in the corpus's FAMILY_RELATION clauses is nested-tagged
  PERSON (94% rule) and this one was the sole exception in this batch.

## Per-type counts (final gold file)

| Type | Count |
|---|---|
| BEHAVIORAL_PATTERN | 8 |
| CRIMINAL_RECORD | 61 |
| DATE_TIME | 47 |
| ECONOMIC_STATUS | 8 |
| EMAIL_ADDRESS | 18 |
| EMPLOYMENT_INFO | 24 |
| FAMILY_RELATION | 23 |
| FINANCIAL_INFO | 10 |
| GOV_ID | 52 |
| HEALTH_INFO | 133 |
| NO_ADDRESS | 21 |
| NO_PHONE_NUMBER | 18 |
| PERSON | 44 |
| POLITICAL_CASE | 9 |
| POSTAL_CODE | 18 |
| SEXUAL_ORIENTATION | 9 |
| **TOTAL** | **503** |

## Things checked and explicitly left alone (to document discipline, not misses)

- "Referanse: NNNNNN" — never tagged anywhere in the batch, confirmed by
  automated scan; correct per spec.
- Commercial/human hygiene findings (`Dårlig hygiene i fjøset`, `Manglende
  hygiene i produksjonslokalene`, `Innhegningene er små og virker skitne`,
  `Stallen er skitten og i dårlig forfatning`, and equivalents) — left
  untagged everywhere they occurred (D001, D005, D006, D009, D010, D016,
  D018), consistent with B14's explicit structure/cleanliness carve-out.
- Plant diseases in D005 (Citrus tristeza virus, Phytophthora ramorum) —
  correctly outside HEALTH_INFO's animal/human-only scope; left untagged.
- Bare political party names with no affiliation verb (D004 `Politisk
  tilhørighet: Høyre.`) — correctly untagged per POLITICAL_CASE's own
  exclude rule.
- Religious affiliations throughout (Jehovas Vitner, Den Norske Kirke,
  åsatru, pinsemenigheten, katolikk, etc.) — no home in the 16-type
  taxonomy, correctly left untagged everywhere.
- Hypothetical/future sanctions ("kan medføre politianmeldelse", "vil
  vurdere ytterligere tiltak") — not yet-established facts, correctly
  untagged.
