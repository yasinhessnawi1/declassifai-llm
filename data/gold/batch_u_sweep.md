# Batch U recall sweep log

Second pass over `batch_u_annotator1.jsonl` (472 spans, 19 docs). Full B1–B20 sweep with
the batch direction's two targeted questions. Output: `batch_u_gold.jsonl` (484 spans:
+14 additions, −2 removals).

## (a) The one PERSON removal — done, confirmed

- U002 `Jonas` — REMOVE PERSON. Given name of `Jonas Hansen`, which is tagged PERSON in
  the same document. Settled convention 1 (0 of 743 committed PERSON spans are the given
  name or surname of a full name tagged in the same document).
- Confirmed after the removal: U002 PERSON = `Anne Lise Hansen`, `Dr. Astrid Olsen`,
  **`Jonas Hansen`**, `Maria Hansen`, `Per Gunnar Hansen`. `Jonas Hansen` also remains as
  a FAMILY_RELATION span (nested, per the spec's default).
- U017 `Astrid` and `Bjørn` — left as tagged. Neither ever appears with a surname in that
  document (`sin ekskone, Astrid`, `nåværende partner, Bjørn`), so both are standalone
  given names and fall under the 9-span standalone carve-out, not the removal rule.

## (b) Is U under-tagged, or just interview-heavy? — mostly the mix

**Template mix established first.** Interview markers (`Hvilket dyr er du bekymret for`
or `-- Hvordan ser dyrene ut`) split U into **10 interviews / 9 dossiers (52.6%
interviews)**. The 287-document committed gold set is **119 interviews / 168 dossiers
(41.5% interviews)**. U drew ~11 points more interviews than average, and interviews are
the thin template.

Normalising per template against committed gold (spans per doc):

| | gold interview | U interview | gold dossier | U dossier |
|---|---|---|---|---|
| all types | 18.20 | 17.50 | 31.13 | **33.00** |
| EMPLOYMENT_INFO | 1.10 | 0.70 | 1.67 | 1.11 |
| POLITICAL_CASE | 0.00 | 0.00 | 1.18 | 0.89 |
| FINANCIAL_INFO | 0.00 | 0.00 | 1.08 | 0.89 |

U's **dossiers are above the gold dossier mean**, and its interviews are within noise of
the interview mean. The 472-vs-518/549 headline gap is a template-mix artefact, not a
systematic recall failure. The three flagged types are also all dossier-only types
(POLITICAL_CASE and FINANCIAL_INFO literally never occur in an interview in committed
gold), so a batch with one extra interview and one fewer dossier mechanically loses ~1
span of each.

Working the dossiers type by type:

- **EMPLOYMENT_INFO — a real shortfall, 4 spans recovered.** This was the one flagged type
  with genuine misses (see below). After the sweep U's dossier rate is 1.44 and its
  interview rate 0.90, both inside the gold range.
- **POLITICAL_CASE — no genuine miss.** The only candidate was U008's
  `medlem av "Norges Frie Dyreeiere", en organisasjon med kontroversielle synspunkter på
  dyrevelferd`. Left untagged: the spec's POLITICAL_CASE §Exclude names
  `Norges Frie Dyreimportører`/`Norges Frie Planteimportører` as fictional trade names
  with no political content, and gold O017 leaves the exactly parallel
  `medlem av "Norges Frie Planteimportører", en organisasjon kjent for sin motstand mot
  importreguleringer` untagged. Every other dossier's affiliation clause was already
  tagged in its long form.
- **FINANCIAL_INFO — no genuine miss.** The only dossier at 0 is U018, where the amount
  sits *inside* the fraud-confession clause (`…manipulert regnskapene for å skjule gjeld
  på over 700.000 NOK til flere kreditorer…`). Gold E008, L016, N005, N012 and R012 all
  keep that whole "…for å skjule gjeld på over N NOK…" clause as a single CRIMINAL_RECORD
  span with no separate FINANCIAL_INFO, per the CRIMINAL_RECORD > FINANCIAL_INFO
  precedence chain. Correct as it stands.

## Changes, grouped by rule

### B19 / EMPLOYMENT_INFO — employer field and ownership position (4 adds)
- U008 `eid av Anette Bergquist` — ADD. Ownership position of the inspected shop; the
  exact string `eid av Anette Bergquist` is already an EMPLOYMENT_INFO span in committed
  gold. The company name itself (`Dyrebutikken "Eksotiske Venner"`) was already tagged.
- U010 `Dyrebutikken "Kosekassen"` — ADD. Value of `Navn på dyreeier eller virksomhet:`.
  B19 is satisfied: the document identifies a principal (`Eier observert kranglende med
  leverandør om betaling`), an owner, not a reporter or a neighbour. Direct twin in gold
  G004, where `Dyrebutikken "Kosekassen"` is tagged with an equally unnamed `Eieren`;
  A005 (`Dyrebutikken Kos`) and P001 (`Dyrebutikken Zoogle`) are the same pattern.
- U010 `lite ansatte i butikken` — ADD. Workplace-condition statement about the subject's
  own business, matching EMPLOYMENT_INFO's Include bullet (`Flere ansatte har sluttet den
  siste tiden`). Leading auxiliary `har` dropped per B1. **Lowest-confidence addition in
  this batch** — the spec bullet is explicit but I found no instance of that bullet's
  pattern anywhere in the 287 committed documents, so there is no precedent either way.
- U011 `owned by Bjørnar Halvorsen` — ADD. English dossier; `the seafood processing
  facility owned by Bjørnar Halvorsen`. Gold D002 tags the direct English analogue
  (`"Fjordens Delikatesser AS," owned and operated by Bjørn Helge Pedersen`), and Norwegian
  `eid av <Name>` is tagged twice. Only the ownership predicate is taken; the generic
  noun phrase `the seafood processing facility` is not a company name.

### B6 + B14 — welfare-need restatement in an observation bullet (2 adds, U008)
U008's `Vi har observert: Mangelfulle importdokumenter, manglende veterinærkontroll,
utilstrekkelig stell av dyr, brudd på dyrevelferdsloven` had no span at all, although the
same document's prose findings were tagged. Per B6 a restatement is its own span, and two
of the four items are B14 welfare-need deprivations:
- `manglende veterinærkontroll` — ADD HEALTH_INFO (veterinary care). Gold has
  `manglende veterinærbehandling av sykdom og skader`, `manglende veterinæromsorg for syke
  eller skadde dyr`, `Manglende veterinærbehandling av syke og skadde dyr`.
- `utilstrekkelig stell av dyr` — ADD HEALTH_INFO (`stell` is named in B14's own list;
  gold has `manglende stell` 9× and `utilstrekkelig stell`).
- `Mangelfulle importdokumenter` and `brudd på dyrevelferdsloven` deliberately left
  untagged: documentation deficiencies and bare statute-breach statements are not tagged
  anywhere in committed gold (B015, D010, E003, J004 all leave `Gjentatte brudd på
  regelverket` untagged). U013's parallel bullet, which the annotator did tag, follows the
  same split — it excludes `uhygieniske burforhold` and keeps only the welfare items.

### B18 — pattern of non-compliance, prior warnings (2 adds)
- U019 `Hansen har tidligere mottatt advarsler` — ADD BEHAVIORAL_PATTERN. Span stops
  before the `(saksnummer 2023-1234-567)` parenthetical per B4 (a separate identifiable
  datum, already tagged GOV_ID on its own). Gold precedent for the identical lead:
  K003 `Hansen har tidligere mottatt advarsler fra Mattilsynet angående mangelfull hygiene
  og plantesykdommer i 2022 og 2023, men har ikke…` and N017 `tidligere mottatt advarsler
  for lignende forhold`, plus P009. **Split precedent, noted honestly:** gold I009 leaves
  a near-identical sentence (`Olsen har tidligere mottatt advarsler (Vår ref: …) for
  mangelfull hygiene…`) untagged. Majority is 3:1 for tagging.
- U014 `Han har tidligere fått advarsler fra Mattilsynet for dårlig hygiene på gården` —
  ADD BEHAVIORAL_PATTERN. Same rule, subject kept per B18 (`Han` = the named Lars Olsen).

### B3 — a case outcome is its own span (1 split, net +1)
- U015: REMOVE CRIMINAL_RECORD `involvert i en hendelse med ulovlig besittelse av en hagle,
  noe som resulterte i en bot`; ADD CRIMINAL_RECORD `involvert i en hendelse med ulovlig
  besittelse av en hagle` and CRIMINAL_RECORD `resulterte i en bot`. Gold H012 and G012
  both carry `resulterte i en bot` as its own span alongside the offence clause, and this
  annotator already split the same construction in U002 (`Involvert i en hendelse med
  ulovlig besittelse av våpen i 2015` + `henlagt sak`).

### ECONOMIC_STATUS — evaluative clause with no figure (1 add)
- U015 `ikke hadde ressurser til å følge forskriftene` — ADD. A distinct hardship
  judgement from the already-tagged FINANCIAL_INFO `gjeld på over 700 000 NOK`; no number
  in the span itself, so ECONOMIC_STATUS, not FINANCIAL_INFO. Gold has
  `manglende ressurser til å håndtere situasjonen` and `manglende økonomisk evne til å
  opprettholde hygiene- og sikkerhetsstandarder`.

### FAMILY_RELATION — second fact in a conjoined clause (1 add)
- U017 `deres to barn` — ADD. The besøksforbud clause is correctly CRIMINAL_RECORD through
  `sin ekskone, Astrid` (CRIMINAL_RECORD > FAMILY_RELATION for `besøksforbud`), but
  `og deres to barn` is a separate kinship fact on characters no span covered. U006 and
  U018 both tag the sibling form `to barn`.

### PERSON — honorific + surname (2 adds)
- U015 `Fru Hansen`, U019 `Fru Hansen` — ADD. The PERSON §Include bullet lists
  `Fru Berglund` and mandates the title-glued form; committed gold tags `Fru Hansen`
  itself twice, plus 11 other honorific+surname spans, against 4 untagged. This is *not* a
  convention-1 violation: convention 1 covers a **bare** given name or surname, and the
  annotator already applied the same reading in U011 (`Mr. Halvorsen` tagged alongside
  `Bjørnar Halvorsen`). The genitive `Fru Hansens` is not separately tagged (gold V001
  leaves `Fru Johansens` untagged).

## B20 — 0 changes forced

Grepped all 19 documents for `Førerkortnummer`, `Våpenkortnummer`, `Lisensnummer`,
`D-nummer`, `journalnummer`, `pasientjournal`, `medlemsnummer`, `våpennummer`. The only
private-body identifier in the batch is U002's `lånenummer: 1234567890` (DNB's own loan
number): correctly **not** tagged GOV_ID, and it sits inside the FINANCIAL_INFO debt clause
that legitimately runs through it. All state-issued values (fødselsnummer, org.nr,
Vår ref/Deres ref case numbers, court case numbers, the two `[redacted]` fødselsnummer
placeholders in U006) were already GOV_ID. No additions, no removals.

## Reviewed and deliberately left alone

- **U005 `Blomsterglede AS`** (the one `check_coverage.py` candidate). Left untagged. It is
  the `Navn på dyreeier eller virksomhet:` value, but the document names **no principal** —
  only the reporter (Live Kristoffersen) and a neighbour (Anne Lise Fredriksen). This is
  exactly the case tightened B19 excludes, and it is the distinction that separates U005
  from U010: U010 has an `Eier`, U005 has nobody. Coverage stays at 1 candidate by design.
- **Doctors' workplaces** — U002 `Bodø Legesenter`, U011 `Haukeland University Hospital`.
  Left untagged. Committed gold is split roughly 3 tagged (B009 `Jessheim Legesenter`,
  B010 `Bergen Psykiatriske Sykehus`, G008 `Haukeland University Hospital`) against 6
  untagged (B001, J014, M010, M018, N016, L007). Tagging is the minority practice, and
  these are a treating physician's employer rather than the data subject's. Flagging it as
  a real inconsistency in the committed set that deserves a ruling.
- **U002 `Fjordfisk AS`** (already tagged by the annotator) — kept. The `Virksomhet:`
  header field has no precedent anywhere in the 287 committed documents, but the document
  attaches a complete personal dossier for Per Gunnar Hansen (fødselsnummer, health,
  finances, criminal history) to that business, which identifies him as its principal in
  substance. Judgement call, retained rather than reversed.
- **U006 `Lars Magnus Bergers sauehold`, U015 `Astrid Bjørg Hansens planteskole`,
  U014 `Lars Olsens produksjon av poteter og gulrøtter`** — left untagged despite both
  documents having EMPLOYMENT_INFO 0. A possessive generic business noun is consistently
  untagged in gold: B006 `Karlsens dyrehold`, O005 `Eriksens dyrehold`, C010 `Olsens
  dyrehold`, and G014's `Anette Borgersens planteskole` (which appears only inside a
  CRIMINAL_RECORD span, never as EMPLOYMENT_INFO). These two dossiers have no company name
  in the Org.nr field and no role word, so 0 is the right answer for them.
- **U012's merged `Eier observert flere ganger hentende mat fra matsentral, mulig økonomisk
  utfordringer`** (ECONOMIC_STATUS). Considered splitting into BEHAVIORAL_PATTERN +
  ECONOMIC_STATUS to match U010's `Eier observert kranglende med leverandør om betaling`.
  Left merged: gold carries the same behaviour-plus-inference shape as a single
  ECONOMIC_STATUS span (`kjøre en gammel, slitt traktor, muligens indikerer økonomiske
  problemer`; `bekymret for eierens økonomiske situasjon; jeg har sett ham forsøke å selge
  deler av eiendommen flere ganger uten hell`).
- **`klør seg mye` / `de løper konstant rundt og biter på burets gitter` / `bjeffe`**
  (U001, U007, U010, U016). Left untagged. The spec routes `klør seg mye` with no named
  skin condition to BEHAVIORAL_PATTERN, and BEHAVIORAL_PATTERN excludes an animal
  grammatical subject, so no type claims them. The annotator applied this consistently.
- **U010 `burene er overfylte`.** Not added as a separate HEALTH_INFO span. Overcrowding is
  HEALTH_INFO (settled convention 2) and is already carried in this document by
  `holdes i overfylte, skitne bur med lite tilgang til mat og vann` and `altfor små for
  antall dyr som oppholder seg der`; the B1 remainder here would be the bare adjective
  `overfylte`, a substring of a span already present.
- **U002 `Dette er gjentatte brudd på regelverket, til tross for tidligere advarsler`.**
  Left untagged — a bare repeated-breach statement about the business is untagged in gold
  B015, D010, E003, J004, A020 and B018.
- **Commercial/structural hygiene throughout** (U002 fish-waste and temperature logs,
  U006 `dårlig hygiene i fjøset` and `mangelfull ventilasjon`, U011 bloodstains and pests,
  U013 `uhygieniske burforhold`, U017 `Avføring og urin i flere bur`). Correctly untagged
  per B14's structural carve-out. Plant disease (U005, U015, U019) likewise: HEALTH_INFO
  covers humans and animals, not plants.
- **Religious affiliation** (U002 Human-Etisk Forbund, U006/U017 Den norske kirke, U013/U018
  praktiserende katolikk, U019 Jehovas Vitner) and U011's `identifies as atheist` — all
  correctly untagged; open question 17 still has no home type.
- **Lawful weapons** (U006 `gyldig våpenkort`, U017 `et registrert hagle` inside the
  violence clause) and **B7/B15 non-disclosures** (U011 `No information regarding sexual
  orientation was solicited or provided`, U018 `Det ble ikke funnet våpen ombord`) —
  correctly untagged.

## Points where I think the spec or a settled convention is shaky

1. **The doctor's-workplace case has no rule.** EMPLOYMENT_INFO's definition covers "a
   named person's … employer/workplace" with no restriction to the data subject, so
   `Bodø Legesenter` after `Dr. Astrid Olsen` is literally in scope — yet committed gold
   tags it in only a third of its occurrences. Either B19's principal test should be
   extended to say that a treating clinician's institution is out of scope, or the ~6
   untagged instances in the committed set are recall misses. I followed the majority and
   left them untagged, but this needs an owner ruling, not another sweep's judgement.
2. **"X har tidligere mottatt advarsler" is 3:1, not settled.** I tagged it, but gold I009
   does not, and the two readings produce a systematically different BEHAVIORAL_PATTERN
   rate in dossiers. Worth an explicit line in the spec.

## Tool output

```
validate_labels.py data/gold/batch_u_gold.jsonl
  records: 19   malformed JSON lines: 0   labeled spans: 484
  distinct documents: 19   docs w/ conflicting dupes: 0
  violations: 0, exit 0

19 docs / 484 spans / min 8 spans per doc (U005) / max 41 (U002) / 0 empty outputs

check_coverage.py: 1 candidate (U005 'Blomsterglede AS' — reviewed above, correctly
left untagged under B19: no principal named)
```
