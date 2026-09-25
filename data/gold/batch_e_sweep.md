# Batch E Recall Sweep Log

Starting spans (annotator1): 450
Added: 17
Removed: 2
Final total: 465

## REMOVALS (2) — Rule change 2: FAMILY_RELATION no longer covers non-kinship social ties

Both are the two spans explicitly named in the task brief; no further non-kinship
FAMILY_RELATION spans were found elsewhere in the batch (checked all 18 docs' FAMILY_RELATION
arrays for "nabo"/"venn"/"kolleg*").

- E001: FAMILY_RELATION `nabo til Hanne-Lill Olsen` — neighbour, not kinship.
- E009: FAMILY_RELATION `nabo til Frank Eriksen` — neighbour, not kinship.

## ADDITIONS FORCED BY WIDENED B14 (basic-welfare-need deprivation) — 11 spans

These are cases where the annotator, reading B14 literally (pre-widening: food/water/vet-care
only), correctly left the span untagged because the clause was phrased as a property of the
enclosure/environment rather than of the animal. Under the new rule the same clauses are
HEALTH_INFO because a need of the animal (shelter, exercise/stimulation) goes unmet regardless
of grammatical subject.

- E001 HEALTH_INFO `Det er få muligheter for klatring eller annen berikelse` — lack of
  climbing/enrichment opportunity = stimulation/exercise need unmet.
- E001 HEALTH_INFO `Burstørrelsen er utilstrekkelig for så aktive dyr som aper` — cage size
  explicitly tied to the animals' activity level (contrast with the spec's own untagged
  example `Innhegningene er små og virker skitne`, which has no such need-linkage and was
  correctly left untagged here too). Borderline call, flagged below.
- E001 HEALTH_INFO `Mangelen på berikelse` — restatement of the enrichment-deprivation finding
  in the "gir grunn til bekymring" sentence (B6 restatement).
- E009 HEALTH_INFO `Mangelen på frisk luft og det at de tilsynelatende holdes innendørs
  mesteparten av tiden` — dogs kept indoors most of the time = exercise/movement need unmet.
  Moderate-confidence call, flagged below.
- E011 HEALTH_INFO `Ingen form for overdekning eller beskyttelse mot vær og vind` — near-exact
  match to the widened rule's own worked example (`ingen beskyttelse mot vær og vind`).
  Highest-confidence addition in the batch.
- E012 HEALTH_INFO `ingen naturlig skygge` — near-exact match to the widened rule's own
  example `lite skygge`.
- E012 HEALTH_INFO `søke ly under noen få busker som står der` — sheep's coping behaviour
  evidencing the same shade/shelter deprivation, same sentence as the above.
- E015 HEALTH_INFO `utilstrekkelig berikelse` — enrichment deprivation, direct match to
  "stimulering" in the widened need list.
- E008 HEALTH_INFO `i dårlig forfatning, med tegn på underernæring og manglende stell`
  (see next section — this one is mixed: `underernæring` was already in old B14's scope,
  `manglende stell` is the widened-rule component).

Pattern: every widened-B14 addition follows the same shape the task predicted — a finding
phrased as a property of the cage/pasture/house ("ingen beskyttelse...", "ingen naturlig
skygge...", "få muligheter for...") that the annotator skipped because the grammatical
subject wasn't the animal. Structural/cleanliness-only findings in the same documents
(`Fjøset var skittent`, `Innhegningene er små`, `mangelfull ventilasjon`, `Dårlig hygiene`,
`manglende renhold`) were correctly left untagged throughout and were NOT touched.

## GENUINE ANNOTATOR MISSES (recall gaps unrelated to either rule change) — 6 spans

- E003 BEHAVIORAL_PATTERN `gitt uriktige opplysninger om sin familiesituasjon og bakgrunn i
  tidligere kommunikasjon med Mattilsynet` — deceptive conduct toward Mattilsynet, a clean
  BEHAVIORAL_PATTERN fact (per spec's own "deceptive conduct" example) that was skipped
  entirely.
- E004 EMPLOYMENT_INFO `Den Hellige Åpenbarings Menighet` — bare employer/organisation name
  for the person identified as "menighetens leder" (Astrid Eide). See recurring pattern below.
- E005 CRIMINAL_RECORD `dokumentforfalskning` — a bare offense noun (document forgery) named
  in the inspection-scope sentence as one of the reasons for the inspection; per spec a bare
  offense noun is sufficient on its own and this one was never picked up (the parallel
  `bruk av forbudte plantevernmidler` in the same list was correctly left untagged elsewhere
  in the doc as non-criminal/regulatory, so this isn't a blanket omission — just the forgery
  noun specifically).
- E006 EMPLOYMENT_INFO `Lødingen Gårdsdrift` — same recurring pattern, see below.
- E007 CRIMINAL_RECORD `involvert i en våpenhendelse i 2018` — a named partner's (Lars
  Eriksen's) weapon incident, the sole reference to it in the document; the DATE_TIME `2018`
  nested inside it was already tagged, but the enclosing CRIMINAL_RECORD clause itself was
  missed entirely.
- E008 EMPLOYMENT_INFO `Fjellgård Olsen` — same recurring pattern, see below.
- E016 ECONOMIC_STATUS `økonomiske problemer` — the first of two identical hardship
  declarations in the document; the second occurrence (`hans økonomiske problemer`, later in
  the same doc) was correctly tagged, this earlier one was skipped.

### Recurring pattern: bare employer/org name from an "Org.nr.: NNN (Business Name)" field

Four documents in this batch open with `Org.nr.: NNNNNNNNN (Business Name)`, associating a
named business with the inspected person as their farm/company. The annotator tagged the
bare business name as EMPLOYMENT_INFO correctly in E005 (`Halvorsen Gartneri AS`), E007
(`Hansen Transport AS`) and E018 (`Gundersen Gårdsdrift`), but missed the identical pattern
in E004 (`Den Hellige Åpenbarings Menighet`), E006 (`Lødingen Gårdsdrift`) and E008
(`Fjellgård Olsen`). This is a genuine, inconsistent recall gap — the annotator clearly knows
the rule (applies it correctly 3 of 6 times) but missed it in the other 3.

## PLACES THE SPEC LEFT ME GUESSING

1. **"Access to natural light" for caged animals** (E001: `De har også begrenset tilgang til
   naturlig lys`; E013: `lite lys`). Not one of the 7 enumerated needs (food, water, vet care,
   shelter/weather, stell, exercise, social contact). I left both untagged, but a case could be
   made that restricted light for housed animals is a welfare-relevant environmental factor.
2. **Speculative/future health risk framed as a possible consequence, not a current finding**
   (E008: `Dette kan føre til helseproblemer for dyrene`; E012: `Det kan føre til
   overoppheting, stress og ubehag` / `Jeg er redd de kan få heteslag`). I treated these as
   too hedged/hypothetical to count as "a finding that a need is going unmet" and left them
   untagged, analogous to B15's treatment of reassuring negatives, but B14/B15 don't directly
   address forward-looking risk language.
3. **Bare regulatory/legal enclosure-size violations with no explicit tie to an animal need**
   (E015: `Elgene holdes i et innhegning som er mindre enn minstekravet angitt i forskrift om
   hold av hjortedyr`). I left this untagged as structural (parallel to the spec's own
   `Innhegningene er små` example), but it's arguably closer to "exercise" deprivation than
   that example is, since it cites a species-specific minimum-size regulation. I tagged the
   more explicit E001 analogue (`Burstørrelsen er utilstrekkelig for så aktive dyr som aper`,
   which names the animals' activity level directly) but not this one; the line between the
   two is a judgment call, not a bright rule.
4. **A registered/lawful weapon "involved in an accident" with no stated legal process**
   (E014: Bjørn Olsen's rifle "involvert i en uhellshendelse i 2019"). No accusation, no
   police report, no "anmeldt"/"henlagt" language — contrasted with E006's near-identical
   scenario which explicitly says "rapportert" and "saken ble henlagt" (tagged CRIMINAL_RECORD
   there). I left the E014 instance untagged as an accident to a lawfully registered weapon,
   but the boundary between "reportable incident" and "mere accident" isn't spelled out in the
   spec.
5. **Whether a clause naming a criminal offense but attributed only to a company/congregation
   (not a named natural person)** should be tagged. E004 (`indikasjoner på ulovlig politisk
   aktivitet i menighetens lokaler...`, `menigheten skjuler ulovlige midler...`) and E016
   (fine/closure imposed on the business) were all left untagged on the theory that
   CRIMINAL_RECORD and FINANCIAL_INFO require an identified natural person and an
   organisation doesn't qualify — but these organisations each have one clearly identified
   human leader/owner in the same document, so a stricter reading could attribute the acts to
   that person.
