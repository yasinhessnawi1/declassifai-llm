# Batch K Recall Sweep Log

Starting spans (annotator1): 379
Final spans (gold): 403
Net additions: 24 | Boundary fixes (count-neutral): 4 | Retypes (count-neutral): 1 | Pure removals: 0

Validator: `tools/validate_labels.py` → `violations: 0`, 403 labeled spans, 0 conflicting dupes, exit 0.

---

## 1. B17 fixes — "nominalised action er ulovlig/brudd" pattern

The spec's own worked example (`Oppbevaring av uregistrert våpen er ulovlig` → CRIMINAL_RECORD
`Oppbevaring av uregistrert våpen`) requires dropping the evaluative tail (`er ulovlig`, `er et
alvorlig brudd/lovbrudd`) and keeping only the nominalised offense noun phrase. The annotator
applied this correctly in some `Mattilsynet vurderer det slik:` bullets (e.g. K008's `Brudd på
karantenebestemmelsene`, K012's `har vist manglende vilje...`) but inconsistently kept the tail
in four others. Fixed all four to the canonical (subject-only) form:

- **K006** CRIMINAL_RECORD: `Oppbevaring av uregistrert våpen er ulovlig` → `Oppbevaring av
  uregistrert våpen` (this is the literal sentence the spec's B17 example is drawn from).
- **K008** CRIMINAL_RECORD: `Forfalskning av importdokumentasjon er et alvorlig lovbrudd` →
  `Forfalskning av importdokumentasjon`.
- **K015** CRIMINAL_RECORD: `Forfalskning av dokumenter er et alvorlig brudd på regelverket` →
  `Forfalskning av dokumenter`.
- **K016** CRIMINAL_RECORD: `Forfalskning av dokumentasjon er et alvorlig brudd på regelverket`
  → `Forfalskning av dokumentasjon`.

Two more B17-pattern **restatements** (B6) of already-established offenses were entirely missed
(the nominalised-action sentence itself was never tagged, not just tagged too long):

- **K012** CRIMINAL_RECORD added: `Alvorlige brudd på dyrevelferdsloven` (bare nominalised
  restatement bullet, no evaluative tail even present — a pure presence miss of the B17 pattern).
- **K014** CRIMINAL_RECORD added: `forfalskning av dokumenter` (from the `Mattilsynet vurderer
  det slik: Eriksens manglende åpenhet og forfalskning av dokumenter er svært alvorlig.` sentence
  — split per "one clause, one fact" into this CRIMINAL_RECORD half and a BEHAVIORAL_PATTERN half,
  below).

Sentences checked and correctly left alone (subject is a redundant referent like `De observerte
forholdene/bruddene/avvikene`, not a nominalised action — B1 default applies, nothing left to
tag): K003, K005, K006-bullet-1, K009 (both), K015 (hygiene/documentation bullets), K016-bullet-2.
K012's "Stor risiko for matforgiftning" and "Alvorlig brudd på tilliten til Mattilsynet" were also
checked and left untagged — neither names a specific offense (see Open items below for the second).

## 2. B18 — BEHAVIORAL_PATTERN keeps its subject (non-compliance pattern)

The annotator already applies this correctly in K012 (`har vist manglende vilje til å rette opp
forholdene`, kept with "Holm" established immediately before). Sweeping the other inspection
reports for the same "repeated warnings/non-disclosure ignored" pattern found two clean, previously
untagged matches, keeping the named subject per B18:

- **K003** BEHAVIORAL_PATTERN added: `Hansen har tidligere mottatt advarsler fra Mattilsynet
  angående mangelfull hygiene og plantesykdommer i 2022 og 2023, men har ikke fulgt opp
  anbefalingene` (matches the spec's own `resistant to previous guidance and exhibits a pattern
  of non-compliance` example almost exactly).
- **K014** BEHAVIORAL_PATTERN added: `Lars Magnus Eriksen, eier og daglig leder, har gjentatte
  ganger unnlatt å opplyse om sin kriminelle fortid` (repeated non-disclosure, explicit `gjentatte
  ganger` marker).
- **K014** BEHAVIORAL_PATTERN added (restatement, same B17/B6 logic as above): `Eriksens
  manglende åpenhet` (from the `Mattilsynet vurderer det slik:` sentence, split from the
  CRIMINAL_RECORD half `forfalskning av dokumenter`).

A second, longer restatement of the K014 non-disclosure pattern also appears inside the `Vi har
observert:` bullet (`...har unnlatt å opplyse om tidligere domfellelser for bedrageri og vold`),
but it is interleaved with several already-independently-tagged facts (health, political) with no
clean contiguous boundary — left untagged, flagged below rather than forced.

## 3. Gambling routing

Only one gambling-related span exists in the batch. It did not match any of the three prescribed
buckets (outcome→ECONOMIC_STATUS / habit→BEHAVIORAL_PATTERN / clinical→HEALTH_INFO):

- **K008**: `gjeld på over 700.000 NOK, delvis pådratt gjennom gambling og delvis arv fra farens
  virksomhet` was tagged FINANCIAL_INFO (matching the general "quantified amount" default).
  Retyped to **ECONOMIC_STATUS** per the explicit ruling that a debt/loss outcome attributable to
  gambling routes to ECONOMIC_STATUS even when quantified.

## 4. samboerforhold / forhold split — verified, not changed

Grepped every `forhold`/`samboer` occurrence in the batch. The annotator's split is already fully
consistent: `i et forhold med Bjørn Hansen` (K005) and `i et forhold med Bjørn Ironside` (K009) →
SEXUAL_ORIENTATION; `i et samboerforhold med Lars Magnus Olsen` (K016) → FAMILY_RELATION. No
changes needed.

## 5. Genuine annotator misses — identifiers and addresses

Mechanical cross-check of every `Adresse:`/`Address:`, `Postnummer:`/`Postal Code:`/`Poststed:`,
`Telefon:`/`Tlf:`, `E-post:`, `Org.nr.:`, `Fødselsnummer:`/`D-nummer:`/`ID-nummer:`, `Vår ref:`,
`Deres ref:` field against the tagged spans. Phone/email/org-number/fødselsnummer fields were 100%
covered already. Four documents were missing the **primary subject's own street address and its
embedded postal code** entirely or partially (all in the English-labelled `Name:`/`Address:`
report template):

- **K005** NO_ADDRESS added: `Fjordveien 12B, 5020 Bergen` (field-value long form; the existing
  short `Fjordveien 12B` from the later prose mention is kept as its own separate span). POSTAL_CODE
  added: `5020`.
- **K006** NO_ADDRESS added: `Fjellstien 12B, 5020 Bergen` (NO_ADDRESS was missing from this
  document entirely). POSTAL_CODE added: `5020` (also entirely missing).
- **K008** NO_ADDRESS added: `Fjellveien 12, 5020 Bergen` (only Lars Olsen's secondary address,
  `Strandgaten 5, 5013 Bergen`, had been tagged — the primary subject's own address field was
  skipped). POSTAL_CODE added: `5020`.
- **K014** NO_ADDRESS added: `Fjellstien 12B, 5020 Bergen` (NO_ADDRESS was missing from this
  document entirely). POSTAL_CODE added: `5020` (also entirely missing).

Reference-number fields (`Vår ref:`/`Deres ref:` — GOV_ID by field-label authority):

- **K005** GOV_ID added: `LM-2023-11-08` (Deres ref) and `MT-2023-4789-LO` (Vår ref) — both
  populated values, neither had been tagged.
- **K006** GOV_ID added: `2024-475-8923` (Vår ref; the blank `Deres ref: -` was correctly left
  untagged).

Standalone date:

- **K005** DATE_TIME added: `2015` (`...registrert eier av et haglgevær, tillatelse gitt i
  2015...` — a standalone administrative date, not part of any ID string; the surrounding clause
  isn't itself tagged since the weapon is lawfully registered, but B13's "standalone dates are
  DATE_TIME regardless" still applies to the bare year).

## 6. Genuine misses — welfare-need deprivation (B14) and restatements (B6)

- **K012** HEALTH_INFO added: `overbefolkning` (first prose mention) and `overbefolkning i bur`
  (restatement in the `Vi har observert:` bullet) — overcrowding is a welfare-need deprivation
  (space/movement), on the same footing as the spec's own `mangle tilstrekkelig bevegelse`
  example; adjacent list items (`syke og skadde dyr`, `manglende tilgang til rent vann og fôr`)
  were already tagged but these two were skipped in the same lists.
- **K013** HEALTH_INFO added: `relativt lite for en papegøye av den størrelsen`, `trangt` (first
  mention, cage size) and `trange buret` (restatement) — cage-size/space deprivation for the
  parrot, same basic-need logic as above; the adjacent, later-listed `manglende leker eller
  stimuli` in the same sentence had already been tagged but `det trange buret` right next to it
  was skipped.
- **K016** HEALTH_INFO added: `utilstrekkelig plass til dyrene` (from the `Vi har observert:`
  transport-conditions bullet — insufficient space explicitly "for the animals" during transport).
- **K004** ECONOMIC_STATUS added: `sliter med å ta seg av kattene som hun ønsker på grunn av
  økonomiske vanskeligheter` — a B6 restatement of the economic-hardship fact already tagged
  earlier in the document (`økonomiske problemer den siste tiden`), appearing later in different
  words in the interview answer; the whole cause+effect clause is kept as one span per the
  ECONOMIC_STATUS boundary rule's own precedent (`sliter økonomisk og ikke har råd til for til
  sauene`).

## Totals by change type

| Change type | Count |
|---|---|
| Net new spans added | 24 |
| Boundary fixes (B17 tail-trim, count-neutral) | 4 |
| Retypes (gambling, count-neutral) | 1 |
| Pure removals | 0 |
| **Final span total** | **403** |

## Final per-type counts (gold)

| Type | Count |
|---|---|
| PERSON | 38 |
| DATE_TIME | 39 |
| HEALTH_INFO | 89 |
| GOV_ID | 40 |
| NO_ADDRESS | 22 |
| CRIMINAL_RECORD | 66 |
| POSTAL_CODE | 18 |
| NO_PHONE_NUMBER | 14 |
| EMAIL_ADDRESS | 14 |
| FAMILY_RELATION | 14 |
| FINANCIAL_INFO | 7 |
| EMPLOYMENT_INFO | 11 |
| POLITICAL_CASE | 9 |
| BEHAVIORAL_PATTERN | 5 |
| ECONOMIC_STATUS | 9 |
| SEXUAL_ORIENTATION | 8 |
| **Total** | **403** |

## Still-guessing / flagged for the project owner (not changed)

1. **K001**: `hunden er ofte alene der, bundet fast med en lang line` — possible social-contact/
   exercise deprivation, but "lang line" + "relativt stor" hage read as mitigating, not clearly a
   deprivation. Left untagged.
2. **K002**: `jeg har flere ganger prøvd å snakke med henne om det, men hun avviser meg` — a
   possible repeated-denial BEHAVIORAL_PATTERN by the data subject, but the `flere ganger`
   frequency marker grammatically attaches to the witness's own attempts, not cleanly to her
   denial clause. Left untagged.
3. **K012**: `Alvorlig brudd på tilliten til Mattilsynet` — "breach of trust" is evaluative/
   reputational, not a named statute/offense the way `brudd på dyrevelferdsloven` is. Left
   untagged; a project owner call on whether generic "breach of trust" language should count as
   CRIMINAL_RECORD would be useful.
4. **K014**: the second, longer restatement of the non-disclosure pattern inside `Vi har
   observert: Eier Lars Magnus Eriksen (...), diagnostisert med..., aktiv i..., har unnlatt å
   opplyse om tidligere domfellelser for bedrageri og vold` is a genuine B6 candidate but has no
   clean contiguous boundary that doesn't swallow already-independently-tagged HEALTH_INFO/
   POLITICAL_CASE facts. Left untagged.
5. **K016**: `manglet tilstrekkelig ventilasjon og desinfeksjon` (transport conditions) —
   ventilation during live-animal transport is arguably a shelter/weather-protection welfare need,
   but is worded jointly with "desinfeksjon" (hygiene, structural/excluded). Left untagged pending
   a clearer rule on transport-specific welfare needs.
6. **Systemic, not fixed**: the bare business name inside `Org.nr.: NNNNNNNNN (Company Name)`
   parentheticals (e.g. K006 `Catering "Smak av Fjordene"`, K009 `Restaurant Valhalla AS`, K012
   `Fjærkre AS`) is never tagged EMPLOYMENT_INFO on its own anywhere in the batch, even where B12
   would arguably support it as the named owner's bare employer name. This looks like a
   consistent, deliberate annotator convention rather than a one-off miss, so it was left alone,
   but it's worth a project-owner ruling since it recurs across most of the inspection-report
   documents.
7. **Boundary style inconsistency, not fixed**: evidentiary/hedge verbs like `tyder på` /
   `indikerer` are kept inside the CRIMINAL_RECORD clause in K003 (`tyder på forfalskning av
   regnskap`) but dropped in K005 (`Dokumentene indikerer` cut, leaving just `systematisk
   forfalskning av...`). Neither violates a stated rule; not adjusted since it's a boundary
   preference, not a spec violation.
