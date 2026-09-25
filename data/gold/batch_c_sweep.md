# Batch C Recall Sweep Log

Annotator 1's baseline: 518 spans across 21 documents (`batch_c_annotator1.jsonl`).
This sweep applied the new B14/B15 rules and did a systematic per-document,
per-category recall check per the spec (docs/ANNOTATION_SPEC.md, B1-B15 and all
16 type sections). Result: **33 spans added, 1 span removed/retyped, 550 spans
in the final gold file.** Validator (`tools/validate_labels.py`) reports
`violations: 0`, exit 0.

## Additions, grouped by pattern

### Pattern 1 — B14 food/water/veterinary-care deprivation missed entirely (18 spans)
This is by far the largest and most serious gap, exactly matching the task's stated
recall failure mode. The annotator consistently tagged animal *symptom* descriptions
(thin, dull coat, lame, apathetic, etc.) but frequently missed adjacent sentences
stating the animal was denied food, water, or veterinary care — even though these
sit right next to the symptom sentences they did tag.

- C002 HEALTH_INFO `Det er lite ferskvann tilgjengelig for kattene` — water deprivation, "Vann/Matskåler" section, no tag existed at all for this sentence.
- C002 HEALTH_INFO `Matskålene er nesten tomme` — food deprivation, same section.
- C007 HEALTH_INFO `jeg har aldri sett rent vann tilgjengelig for hesten` — B15 negation-wraps-subject case (dropping the witness clause would invert the meaning), kept whole per B15's own instruction.
- C007 HEALTH_INFO `mangler tilgang på både tilstrekkelig plass, ly og vann` — coordinated deprivation clause; tagged whole because "vann" is the qualifying B14 trigger inside a contiguous span (structural items "plass"/"ly" are along for the ride, matching the spec's own `Utilstrekkelig fôring, vanning, og stell` precedent of keeping a mixed list together).
- C010 HEALTH_INFO `utilstrekkelig tilgang på fôr og vann for dyrene` — direct B14 match, completely untagged in the source sentence.
- C010 HEALTH_INFO `utilstrekkelig tilgang på rent vann og fôr` — same fact restated verbatim differently in the `Vi har observert` bullet; distinct substring, added separately.
- C010 HEALTH_INFO `symptomer på munn- og klovsyke` — restatement of the already-tagged `tegn på munn- og klovsyke` finding, different exact text in the observation bullet.
- C011 HEALTH_INFO `Jeg har aldri sett at den har tilgang til vann` — same B15 negation-wraps-subject pattern as C007.
- C012 HEALTH_INFO `utilstrekkelig tilgang på vann og artstilpasset fôr` (×2, two distinct sentences/exact strings — main narrative and observation bullet).
- C015 HEALTH_INFO `mangelfull tilgang på rent vann` — matches spec's own literal Include example almost verbatim; present in two sentences, one span entry covers both occurrences.
- C015 HEALTH_INFO `utilstrekkelig fôr` — matches spec's own literal Include example (`Utilstrekkelig fôr og vann`) almost exactly.
- C015 HEALTH_INFO `tegn på sykdom, inkludert oppkast og diaré` — vomiting/diarrhea symptom bullet, completely untagged.
- C015 HEALTH_INFO `Manglende helsekontroll og vaksinasjon` — direct match to the task's own cited example of a previously-missed span (`manglende vaksinasjon`); this phrasing asserts the health check/vaccination itself is missing (not just paperwork about it, which I did NOT tag — see Non-additions below).
- C020 HEALTH_INFO `det ser ikke ut som om de får den stell og pleie de trenger` — B15 negation-wraps-subject; "stell" is explicitly one of B14's three Include nouns.
- C021 HEALTH_INFO `Jeg kunne ikke se noe for eller vann tilgjengelig for dem` — direct food+water deprivation, B15 negation-wraps-subject.
- C021 HEALTH_INFO `Mangelen på mat og vann er den største bekymringen, spesielt med tanke på vinterkulden` — direct food+water deprivation statement, kept as one clause since the deprivation noun phrase is the grammatical subject and stripping it per strict B1 would leave a meaningless fragment.
- C010 (retype) — see Removal below.

### Pattern 2 — CRIMINAL_RECORD bare-offense-noun restatements in "Vi har observert" bullets or intro/evaluation fields, distinct verbatim text from an already-tagged sentence elsewhere in the same document (13 spans)
Several documents state the same offense twice: once in flowing prose (already tagged)
and once as a short, differently-worded restatement in the `Inspeksjonen omfattet:`
intro, a `Vi har observert:` bullet, or the `Mattilsynet vurderer det slik:` evaluation
paragraph. Per B6 these findings are tagged like running prose, and per CRIMINAL_RECORD's
own rule a bare offense noun is sufficient — the second, differently-worded occurrence
was consistently left untagged by the annotator.

- C001 `Ulovlig oppbevaring av våpen` (restates the earlier, longer weapon-possession sentence).
- C003 `mistanke om økonomisk kriminalitet, dyremishandling, og manipulasjon av inspeksjonsresultater` (intro scope field, precedes the detailed findings).
- C003 `mistenker også brudd på straffeloven knyttet til økonomisk kriminalitet` (evaluation paragraph).
- C004 `Forfalskning av importdokumentasjon` (bullet restatement of the forged-documents admission).
- C005 `forfalskede skattedokumenter` (bullet; different word form, "forfalskede" vs. the earlier "forfalsket").
- C006 `ulovlig politisk aktivitet` (intro scope field).
- C006 `Dokumentasjon på ulovlige donasjoner og forfalskning av regnskap` (bullet).
- C008 `mistenkes det også å være knyttet til økonomisk kriminalitet` (evaluation paragraph; different exact wording from the earlier `mistenkt å være knyttet til...`).
- C009 `mistanke om ulovlig import av kjemikalier` (intro scope field).
- C009 `Import og oppbevaring av kosmetiske produkter inneholdende hydrokinon og kvikksølv` (bullet).
- C014 `Forfalskede veterinærattester for transport av sau og geit` (bullet).
- C014 `Forfalskning av veterinærattester` (evaluation paragraph; third distinct wording of the same underlying fact).
- C015 `observerte uregelmessighetene gir grunn til mistanke om økonomisk kriminalitet` (evaluation paragraph, ties back to the "Mistanke om økonomisk kriminalitet" section heading).

### Pattern 3 — short, easily-skimmed-over descriptor missed once, tagged elsewhere in longer form (1 span)
- C018 HEALTH_INFO `magre` — the parenthetical `(magre, matt pels, rennende øyne)` restates three symptoms in short form; `matt pels` and `rennende øyne` were already tagged, but the bare `magre` (distinct from the earlier `litt magre`) was missed.

### Removal / retype (1 span, B14-driven correction)
- C010: moved `uten at Olsen hadde kontaktet veterinær` from BEHAVIORAL_PATTERN to
  HEALTH_INFO. This exact phrase is the spec's own worked example under B15/B14
  (failure to seek veterinary care for sick sheep = denial of veterinary care, a
  HEALTH_INFO deprivation fact, not owner "conduct"). The annotator tagged it
  reasonably under the old rules (no B14 to guide them) but B14 explicitly reclassifies
  this pattern; HEALTH_INFO and BEHAVIORAL_PATTERN are mutually exclusive on identical
  spans, so the old type was removed rather than duplicated.

## Non-additions (deliberately left alone — B14 structural exclusion confirmed correct)
Every document in this batch had multiple sentences describing dirty/small/overcrowded
enclosures, poor fence condition, lack of shelter ("ly"), muddy ground, algae, uneaten
food floating in water, etc. Per B14 these are structural/cleanliness findings, not
food/water/vet-care deprivation, and the annotator correctly left essentially all of
them untagged already (e.g. `Dårlig hygiene i fjøset` appears near-verbatim in C003
and C010 and matches B14's own untagged example exactly). I did not add any of these.
I also did not tag purely administrative "documentation is missing/incomplete" findings
(e.g. C003 `Ufullstendig dokumentasjon av medisinering av dyr`, C014/C015 vaccination
*paperwork* gaps) since these assert a records gap, not that the underlying care itself
was withheld — distinct from `Manglende helsekontroll og vaksinasjon` (C015), which I
did add because that phrasing asserts the check/vaccination itself, not just its
paperwork, was missing. Uncertain/hedged non-findings (`Det er uklart om...`, `jeg er
usikker på om den får nok mat`) were left untagged per B15 (uncertainty is neither an
incriminating nor a reassuring disclosure). Confirmed-reassuring negatives (`ingen
synlige skader`, `Jeg så ingen lam`, `Det ble ikke funnet våpen`) were already correctly
left untagged by the annotator, matching B15 exactly.

## Totals
- Starting spans (annotator 1): 518
- Added: 33
- Removed: 1 (retyped BEHAVIORAL_PATTERN -> HEALTH_INFO, same text)
- Final total: 550
- Validator: `tools/validate_labels.py data/gold/batch_c_gold.jsonl --config configs/config.yaml` -> `violations: 0`, exit 0

## Per-type counts (final)
BEHAVIORAL_PATTERN 21, CRIMINAL_RECORD 61, DATE_TIME 55, ECONOMIC_STATUS 5,
EMAIL_ADDRESS 21, EMPLOYMENT_INFO 31, FAMILY_RELATION 30, FINANCIAL_INFO 15,
GOV_ID 69, HEALTH_INFO 93, NO_ADDRESS 27, NO_PHONE_NUMBER 22, PERSON 53,
POLITICAL_CASE 14, POSTAL_CODE 24, SEXUAL_ORIENTATION 9
