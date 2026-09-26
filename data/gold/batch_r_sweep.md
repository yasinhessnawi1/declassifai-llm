# Batch R recall sweep log

Second pass over `batch_r_annotator1.jsonl` (549 spans, 19 docs), applying the batch-specific
PERSON direction, the five settled conventions, and a full B1–B20 sweep.
Output: `batch_r_gold.jsonl` (551 spans). 13 removals, 15 additions.

Per-type totals after the sweep (spans/doc): HEALTH_INFO 127 (6.68), CRIMINAL_RECORD 76 (4.00),
GOV_ID 54, PERSON 53, DATE_TIME 51, EMPLOYMENT_INFO 29, NO_ADDRESS 24, FAMILY_RELATION 22,
POSTAL_CODE 20, NO_PHONE_NUMBER 19, EMAIL_ADDRESS 18, FINANCIAL_INFO 16, ECONOMIC_STATUS 13,
POLITICAL_CASE 11, BEHAVIORAL_PATTERN 10 (0.53), SEXUAL_ORIENTATION 8.

## (a) The 12 bare-surname PERSON removals — all applied, all full names intact

Removed, matched **exactly** (not by substring — three of these surnames also occur inside a
company name that must survive: `Johansen Gårdsdrift AS`, `Halvorsen Gårdsdrift AS`,
`Sæther Gårdsdrift AS`, plus `Lars Magnus Bergers gård` and `Sæthers tillatelse` in prose):

| doc | removed | full name(s) still tagged in the same doc |
|---|---|---|
| R001 | `Halvorsen` | `Bjørnar Halvorsen` |
| R002 | `Eriksen` | `Lars Magnus Eriksen` |
| R004 | `Olsen` | `Bjørn Magnus Olsen`, `Astrid Olsen` |
| R006 | `Hansen` | `Torbjørn Hansen`, `Anne Lise Hansen` |
| R008 | `Berg` | `Kjell Ivar Berg` |
| R008 | `Olsen` | `Astrid Birgitta Olsen`, `Line Olsen` |
| R012 | `Eriksen` | `Magnus Eriksen` |
| R014 | `Johansen` | `Bjørn Ivar Johansen` |
| R015 | `Berger` | `Lars Magnus Berger` |
| R016 | `Sæther` | `Magnus Sæther`, `Astrid Sæther` |
| R018 | `Halvorsen` | `Torbjørn Halvorsen`, `Torbjørn "Tor" Halvorsen` |
| R019 | `Haugen` | `Bjørnar Haugen` |

The build script asserts both directions (exact removal landed; every listed full name still
present) and fails loudly otherwise.

### One PERSON addition that is *not* a bare sub-token
- R009 `Fru Olsen` — ADD PERSON. This is an honorific-plus-surname referring expression, which
  PERSON's own Include list names explicitly (`Fru Berglund`, `Mr. Halvorsen`), not a bare
  surname. Committed gold tags this form in 7 batches even when the full name is separately
  tagged in the same document (`Fru Berg` a, `Fru Hansen` b, `Mr. Askeland` b, `Mr. Pedersen` d,
  `Mr. Kværner` g, `Mr. Eriksen` i, `Fru Olsen`/`Mr. Olsen` j, `Fru Ellingsen` k); three
  documents leave it untagged (e, m, n), so the convention is ~10:3, not unanimous. Recorded
  here so the minority is visible.

## (b) HEALTH_INFO 6.42 vs BEHAVIORAL_PATTERN 0.32 — answered

**Conclusion: the two deviations have two unrelated causes. Human conduct was *not* absorbed
into HEALTH_INFO spans, but BEHAVIORAL_PATTERN was genuinely under-tagged by 4 spans.**

Evidence 1 — the HEALTH_INFO excess is entirely a document-mix effect, and it sits in the
documents that contain no human conduct to absorb. Splitting by template against the 287-doc
committed gold:

| | docs | HEALTH_INFO/doc | BEHAVIORAL_PATTERN/doc |
|---|---|---|---|
| gold, dossier documents | 182 | 3.32 | 0.53 |
| gold, welfare-interview documents | 123 | 8.11 | 0.63 |
| R (annotator1), dossier | 11 | 3.36 | 0.36 |
| R (annotator1), interview | 8 | 10.62 | 0.25 |

R's dossier documents — the ones that actually narrate owner conduct — sit at 3.36 HEALTH_INFO
against a gold dossier mean of 3.32. The whole excess is in the 8 interview documents, which
are unusually condition-dense (R009 17 spans, R007 14, R013 14, R010 13, all animal
pelage/weight/gait/wound findings). That is a welfare-heavy batch, not absorption.

Evidence 2 — I checked every HEALTH_INFO span in the batch for a human actor. Only two have a
human grammatical subject: R007 `Det virker heller ikke som om bonden har tilkalt veterinær`
and R003 `ikke har råd til nødvendig veterinærbehandling`. Both are correctly HEALTH_INFO:
B14's test is explicitly "whether a need of the animal is going unmet, not whether the
grammatical subject is the animal or the enclosure", and vet-care deprivation is on B14's own
Include list. Neither states a *recurring* pattern, so neither is a BEHAVIORAL_PATTERN
candidate. No HEALTH_INFO span in this batch was re-typed.

Evidence 3 — the BEHAVIORAL_PATTERN gap is real and is a B18/B1 failure, not a type collision.
I grepped all 19 documents for conduct/repetition markers (`gjentat`, `unnlatt`, `advarsl`,
`samarbeid`, `nektet`, `krangl`, `ofte`, `systematisk`, `flere ganger/anledninger`, …) and
ruled on every hit. Four clauses were missed, all of them cases where the actor sits behind a
reporting lead-in or a job-title appositive — exactly the shape B1 tells an annotator to cut
and B18 tells them to keep. All four have near-verbatim precedent in committed gold:

- R018 — ADD `ved gjentatte anledninger unnlatt å fremlegge nødvendig helsedokumentasjon for
  seg selv og en ansatt, til tross for flere advarsler`.
- R019 — ADD `gjentatte ganger unnlatt å fremlegge nødvendig helsedokumentasjon for seg selv og
  sine ansatte, som kreves for håndtering av næringsmidler`.
  Both mirror batch_a's `gjentatte ganger unnlatt å fremlegge nødvendig helsedokumentasjon for
  seg selv og ansatte, som kreves for håndtering av næringsmidler`, whose source sentence has
  the identical `<Name>, eier av <Farm>, har …` shape. Following that precedent the span starts
  at the predicate and does **not** swallow the name or the `eier og driver av …` appositive
  (which stays EMPLOYMENT_INFO). Gold also contains the longer, name-initial variant
  (`Lars Magnus Olsen, eier av L.M. Olsen Økologisk Gårdsdrift, har gjentatte ganger unnlatt …`);
  the closer wording match decided it.
- R010 — ADD `høylytt krangling fra adressen`. batch_d contains the same sentence with
  `fra leiligheten` and tags exactly that span, confirming both the type and the boundary (the
  `Naboer har tidligere klaget på` lead-in is a reporting frame and is cut).
- R006 — ADD `alvorlige og gjentatte brudd på dyrevelferdsloven, hygieneforskrifter og krav til
  dokumentasjon`. Precedent: batch_p `Gjentatte brudd på dyrevelferdsloven, til tross for
  tidligere advarsler og veiledning` (BEHAVIORAL_PATTERN). `gjentatte` is what makes it a
  pattern rather than the plain regulatory finding that R015's CRIMINAL_RECORD
  `alvorlige brudd på dyrevelferdsloven` records.

After these four, BEHAVIORAL_PATTERN is 0.53/doc (dossier 0.64, interview 0.38) against gold's
0.53/0.63. The residual interview-side gap is genuine: in R's interview documents the owners
are largely absent or frail, so there is little owner conduct to describe.

## Other recall additions

### B14 — overcrowding / cramped space (settled convention 2)
Three documents state overcrowding and none of it was tagged. Committed gold tags this shape
directly: `overfylt` (batch_d, of a transport truck), `overbefolkning` and `overbefolkning i
bur` (batch_k), `trangt` / `trange buret` (batch_k), `like trange, med minimal plass til
bevegelse` (batch_h).
- R005 `overfylte` — ADD HEALTH_INFO. B1 drops the subject and the hedge `virker`, giving the
  bare adjective, exactly as batch_d's `Lastebilen var overfylt.` → `overfylt`.
- R006 `overfylte bur med dårlig ventilasjon` — ADD HEALTH_INFO. Kept as one noun phrase
  (global rule 2: trailing qualifier of the same fact), following batch_m's
  `… (utilstrekkelig ventilasjon og overbefolkning)`.
- R011 `overbefolkede` and `Overbefolkning` — ADD HEALTH_INFO, two spans per B6 (the finding is
  stated once about the tanks and restated in the evaluation sentence). `skitne og` is dropped
  from the first: cleanliness is untagged under B14 and the two are separate facts under B11.

### B14 + B6 — water and space restatements missed in the same R011 sentence
- R011 `dårlig vannkvalitet` — ADD HEALTH_INFO. Water is a B14 need (settled convention 3); this
  restates the already-tagged `grumsete og misfarget`.
- R011 `mangel på tilstrekkelig plass` — ADD HEALTH_INFO. Restates the already-tagged
  `ikke tilstrekkelig plass for fiskene å svømme fritt`.

### B6 / B11 — R004's observation bullets
- R004 `Manipulerte dokumenter knyttet til plantevernmiddelbruk` — ADD CRIMINAL_RECORD. The
  document tags its prose statement (`viste tegn til manipulasjon`) but not the bullet
  restatement; R006 and R016 in this same batch do tag the equivalent bullet
  (`Manipulerte registreringer av Salmonella-utbrudd`, `Manipulerte helsejournaler`).
- R004 `manglende betaling til kreditorer` — ADD FINANCIAL_INFO. Second fact of the bullet
  `Tegn på unndragelse av merverdiavgift og manglende betaling til kreditorer`, split per B11;
  FINANCIAL_INFO by the bare-instrument tie-break (cf. `ubetalte fakturaer`).

### FAMILY_RELATION
- R014 `for tiden i et forhold med Kåre Hansen` — ADD. R019's structurally identical sentence
  (`åpent homofil og har for tiden et turbulent forhold til sin partner, Lars Olsen`) is tagged
  FAMILY_RELATION; R014's was not. Kept FAMILY_RELATION rather than SEXUAL_ORIENTATION: the
  orientation adjective sits in a *separate* clause, and FAMILY_RELATION's own resolved-conflict
  list mandates FAMILY_RELATION only for a plain partnership clause (`husband` → FAMILY_RELATION
  only). `Kåre Hansen` is already tagged PERSON, so the nesting is in place. Consistent with
  R008/R012/R018, which all tag the marriage/partnership clause FAMILY_RELATION and the
  orientation word SEXUAL_ORIENTATION separately.

### B12
- R018 `ansatt` — ADD EMPLOYMENT_INFO. `ansatt, Kari Nordmann` names an employee and states her
  work situation; `Kari Nordmann` is already PERSON. Bare `ansatt` has 3 precedents in committed
  gold, and R001 in this batch already tags the identical bare role word.

## Precision removals

- R009 `Kattens kattetoalett er overfylt` — REMOVE HEALTH_INFO. An overflowing litter tray is a
  cleanliness finding about the premises, which B14 lists as untagged (`Manglende renhold i
  dyrenes oppholdsområde`, `Burene er skitne`). The same document correctly leaves
  `Hundens seng er skitten …`, the ammonia smell and the general untidiness untagged, so the tag
  was also internally inconsistent; it additionally kept the subject and the copula against B1.
  Note this `overfylt` means *overflowing*, not *overcrowded* — it is not the batch_d precedent
  cited above, which is why the two `overfylt`-shaped calls in this sweep go opposite ways.

## B19 — the rest of the batch re-checked against the tightened test

The three pre-applied removals (R001 `Slakteriet Vest AS`, R002 `Smaksopplevelser AS`,
R015 `Gårdsdrift`) were **not** reinstated. Every remaining company/organisation name in an
employer field was re-tested; all five identify a principal and stay tagged:

- R004 `Agder Frukt og Grønt AS` — `Bjørn Magnus Olsen, daglig leder og eier`.
- R006 `Hansen Fjærkre AS` — `Torbjørn Hansen … eier og daglig leder`.
- R008 `Det Hellige Lys samfunn` — `Astrid Birgitta Olsen … er registrert leder`.
- R012 `Eriksen Meieri AS` — `Magnus Eriksen, eier og daglig leder`.
- R014 `Johansen Gårdsdrift AS`, R016 `Sæther Gårdsdrift AS`, R018 `Halvorsen Gårdsdrift AS`,
  R019 `eier av geitegården "Fjellgeita"` — owner/daglig leder named in each.
- R017 `"Smaksopplevelser Catering"` — correctly tagged: the field value itself reads
  `(driftet av Randi Bjørklund)`, so a principal is named. This is the contrast case that makes
  the R002 removal load-bearing rather than arbitrary.

`check_coverage.py` reports the two pre-applied removals as `orgnr_company` candidates. Ruled
on and left flagged, per the tool's own header.

## Reviewed, deliberately left alone

- **R002 `Smaksopplevelser AS` (B19).** Left removed as instructed, but flagged: the document
  says Eriksen `har vurdert å selge cateringvirksomheten`, which reads as ownership and would
  make him a principal under the tightened B19. See "Disagreements" below.
- **R015 `Gårdsdrift`.** Removal is well founded on a second, independent ground: `Gårdsdrift`
  is a generic activity word, not a business name, so it identifies nobody regardless of the
  principal test.
- **B20.** Grepped all 19 documents for `Førerkortnummer`, `Våpenkortnummer`, `Lisensnummer`,
  `D-nummer`, `journalnummer`, `våpennummer`, `pasientjournal`, `lånenummer`, `medlemsnummer`.
  No state-issued identifier is untagged and no private-body identifier is tagged. Zero changes.
  `Referanse:` values (R003 933355, R005 285280, R007 246905, R009 719060, R010 987816,
  R011 453161, R013 725929, R017 567150) correctly stay untagged. `Deres ref`/`Vår ref` values
  are GOV_ID in every dossier document. R016's partially redacted `120376-xxx` is correctly
  GOV_ID under the field-label rule.
- **Religious affiliation** — R001 `åsatru`, R004 `Scientologikirken`, R006 `Wicca`,
  R015 `Den norske kirke`, R016 `katolikk`, R014 `ateist`. All correctly untagged.
- **Hobby association** — R016 `aktiv i en lokal skytterklubb`. Untagged, per the spec's own
  recommendation for a club with no political character.
- **Lawful weapons** — R012 (`hagle, registrert i 2018`), R015 (`registrert rifle (kaliber .308)`),
  R016 (`våpenskap … i samsvar med Sæthers tillatelse`), R018 (`våpentillatelse for en jaktrifle`),
  R019 (`eier en registrert rifle`). No illegality asserted; all correctly untagged.
  R018's `avfyrte et varselskudd mot en påstått ulv` is likewise left untagged — no offence is
  named, unlike R019's `ulovlig jakt på fredet fugl`, which is tagged.
- **Commercial / structural hygiene** — R002, R008, R015, R016, R018, R019 all carry
  `mangelfull hygiene`/`Synlig smuss`/`uhygieniske forhold` findings, and R003/R005/R009/R011/R013
  carry faeces, litter, clutter and ammonia findings. All correctly untagged under B14; R015's
  standalone `mangelfull ventilasjon` bullet is left untagged on the same basis.
- **Witness's own routine behaviour** — R003, R005, R007, R010, R011, R013 (`Jeg går tur …`,
  `har jevnlig observert …`). Excluded per BEHAVIORAL_PATTERN's witness rule.
- **R002 `Han nektet å utdype dette`** — a one-off refusal, not a pattern, and B7 says a refusal
  to disclose discloses nothing. Not tagged.
- **R010 `det konstante bruken av pigghalsbåndet`** — considered as BEHAVIORAL_PATTERN and
  rejected: the grammatical subject is the dog (`den konstant bruker et pigghalsbånd`) and the
  nominalised restatement names no human actor. Its consequences are already HEALTH_INFO
  (`gnage på huden`, `tydelige røde merker der piggene sitter`, `smerte og ubehag`).
- **R011 `manglende filtrering` / the defective filter** — considered under the heat-lamp
  precedent (settled convention 4) and left untagged: unlike the heat-lamp documents, the
  welfare need it serves is already tagged twice here (`grumsete og misfarget`,
  `dårlig vannkvalitet`), so this is the equipment, not the deprivation.
- **R001's `Mattilsynet vurderer det slik:` sentence about the subject's conduct and hygiene** and
  R011 `den åpenbare forsømmligheten` — evaluative risk/neglect conclusions with no stated
  pattern; left untagged, following batch_p's ruling on `Den konstante støyen tyder på …`.
- **R008 `registrert leder`** — kept EMPLOYMENT_INFO rather than promoted to POLITICAL_CASE.
  She leads a named far-right group, but the group's name is not contiguous with the role
  phrase, and POLITICAL_CASE's boundary rule forbids emitting the verb without the org name.
- **R015 `har offentlig uttalt seg kritisk til Mattilsynets arbeid`** — considered as
  POLITICAL_CASE and left untagged: criticism of a regulator is not an affiliation with, or a
  stated position on, a party/movement/policy.
- **Section headings** (`2. Dokumentforfalskning:`, `3. Økonomisk kriminalitet:` in R004,
  `2. Dokumentforfalskning og økonomisk kriminalitet:` in R014) — not tagged as B6
  restatements; they are structural document furniture, not findings.
- **R012 `samlivsbrudd`** — prospective and hypothetical (`vil føre til et samlivsbrudd`), not a
  recorded relationship fact. Untagged.
- **Infidelity spans** — R004 `involvert i en offentlig skandale knyttet til utroskap` /
  `utroskapsskandale` and R006 `utenomekteskapelig affære med en tidligere ansatt` are all
  FAMILY_RELATION. Left as the annotator had them; the batch is internally consistent and the
  spec gives no ruling routing `utroskap` to SEXUAL_ORIENTATION.

## Disagreements with a settled convention

One, recorded rather than acted on: **the R002 B19 removal of `Smaksopplevelser AS`.** The
tightened B19 tags an employer-field company when the document identifies a principal. R002
does not use an owner title, but it records that Eriksen `har vurdert å selge
cateringvirksomheten` — considering selling a business is a statement of ownership, and
`Lars Magnus Eriksens våpentillatelse` covering a weapon found in the company's own vehicle
points the same way. On my reading that clears the principal bar and the company name should
be EMPLOYMENT_INFO. I have left it removed as instructed and left the `Smaksopplevelser AS`
span out of the gold file; if the ruling goes the other way, the fix is a one-line addition.

No disagreement with the other four settled conventions, with B20, or with the (a) removals —
the bare-surname pattern really is unique to this batch and the 12 removals are unambiguous.

## Tool output

```
validate_labels.py data/gold/batch_r_gold.jsonl : records 19, labeled spans 551,
                                                  malformed 0, violations 0, exit 0
19 documents / 551 spans / min 12 spans per document (R017) / 0 empty outputs
check_coverage.py : 2 candidates (the two pre-applied B19 removals; ruled on above)
```
