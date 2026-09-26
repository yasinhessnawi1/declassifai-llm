# Batch S recall sweep log

Reviewer pass over `batch_s_annotator1.jsonl` (534 spans, 19 docs), full B1–B20 sweep.
Output: `batch_s_gold.jsonl` (544 spans; +15 additions, −5 removals/boundary repairs).

## Template mix first — the distributional flags are almost entirely composition

S was flagged for the largest deviation in the cycle, led by HEALTH_INFO 3.05/doc vs. the
287-doc gold mean of 5.26. Establishing the template split first dissolves most of it.

S is **17 dossiers (`Inspeksjonsrapport med skriftlig veiledning`) and 2 interviews**
(S016, S017) — 89% dossier against 59% in the committed gold set. The two templates have
very different profiles:

| | gold dossier (n=168) | gold interview (n=119) |
|---|---|---|
| HEALTH_INFO / doc | 3.29 | 8.05 |
| spans / doc | 31.13 | 18.20 |

Conditioned on template, S's dossiers land on the gold dossier mean across *every* type:

| Type | gold dossier | S dossier |
|---|---|---|
| HEALTH_INFO | 3.29 | 3.06 |
| GOV_ID | 4.98 | 5.00 |
| FAMILY_RELATION | 1.99 | 2.06 |
| POLITICAL_CASE | 1.18 | 1.24 |
| CRIMINAL_RECORD | 5.17 | 4.29 |
| ECONOMIC_STATUS | 0.30 | 0.12 |

So GOV_ID "high", FAMILY_RELATION "high" and POLITICAL_CASE "high" are not findings: they
are what a dossier-heavy batch looks like. The batch-level HEALTH_INFO gap is the same
artefact. A further, template-independent factor: S's dossiers are mostly **food-safety /
cosmetics / plant-health** inspections of businesses, where the only health content is the
owner's own human diagnoses. Only 4 of the 17 dossiers (S005, S007, S015, S019) contain
live animals at all.

Two genuine residues survived the conditioning, and both were swept:

1. **The two interview documents are thin** — 11.5 spans/doc vs. the gold interview mean
   of 18.2, and 3.0 HEALTH_INFO/doc vs. 8.05. S016 was under-tagged (B14). S017 is not:
   see "Reviewed, no change".
2. **ECONOMIC_STATUS 0.12 vs. 0.30** in the dossiers was a real recall gap — three
   `<Name>s økonomiske situasjon …` clauses, the type's single most template-bound form.

## Genuine recall misses

### B14 — welfare-need deprivation, missed wholesale in one dossier (S007)
S007 is an animal-welfare dossier (sheep) whose entire animal block was left untagged; the
only HEALTH_INFO tagged was the owner's and his son's human diagnoses.
- `underernærte` — ADD HEALTH_INFO. Subject + copula dropped per B1. 69 precedents in
  committed gold, 10 of them the identical bare string.
- `manglet tilgang på rent vann` — ADD HEALTH_INFO. B14 water. Precedents:
  `mangelfull tilgang på rent vann`, `manglende tilgang på rent vann og fôr hos flere dyr`.
- `hadde ikke tilgang på tilstrekkelig rent vann` — ADD HEALTH_INFO. The observation-bullet
  restatement of the same two facts (B6); kept whole including `hadde ikke` per B15, on the
  spec's own `fortsatt ikke hadde tilgang til mat eller vann` model.
- Left untagged in the same block: `levde i uhygieniske forhold`, `Fjøset var i svært
  dårlig forfatning`, `Fjøset var skittent` — structure/cleanliness, B14's explicit
  exclusion side.

### B14 — overcrowding and an animal-condition restatement (S016, interview)
- `for mange katter i en liten leilighet` — ADD HEALTH_INFO. Overcrowding/cramped space is
  HEALTH_INFO under the settled convention (`trangt`, `like trange, med minimal plass til
  bevegelse`, `Det var lite plass til bevegelse for dyrene`). B1 drops `det er`.
- `kattenes tilsynelatende dårlige tilstand` — ADD HEALTH_INFO. The evaluation-paragraph
  restatement (B6) of the animals' condition. Genitive-animal + condition-noun is a settled
  gold form: `hundenes magre tilstand`, `dyrenes generelt dårlige kroppstilstand`,
  `kaninenes tynne og apatiske tilstand`, `dyrenes dårlige helsetilstand`.

### ECONOMIC_STATUS — the `<Name>s økonomiske situasjon` form (S006, S008, S014)
The evaluative-financial clause was missed in two documents and mis-bounded in a third.
- S006 `Hauglands økonomiske situasjon er anstrengt` — ADD. Exact gold precedent:
  `hans økonomiske situasjon er svært anstrengt` (×2), `Hennes økonomiske situasjon er
  presset`. The possessive is kept per B10 and the subject per B17 (dropping it leaves the
  vacuous `anstrengt`).
- S008 `Bjørklunds økonomiske situasjon` — ADD. Precedent `Edvardsens økonomiske
  situasjon`. Stops before the `(` per B4: the parenthetical introduces a separate
  quantified datum (already FINANCIAL_INFO) and a separate GOV_ID.
- S014 `presset` → `Menighetens økonomiske situasjon er presset` — boundary repair. The
  bare adjective was the annotator's span; gold's own form for this clause keeps the
  fact-bearing subject.

### B18 — pattern of non-compliance with the authority (S006, S011)
- S006 `Torbjørn Haugland, eier av den økologiske geitegården, har gjentatte ganger unnlatt
  å levere nødvendig helsedokumentasjon for seg selv og ansatte` — ADD BEHAVIORAL_PATTERN.
  Near-verbatim gold precedent, including the name+role lead-in:
  `Lars Magnus Olsen, eier av L.M. Olsen Økologisk Gårdsdrift, har gjentatte ganger unnlatt
  å levere nødvendig helsedokumentasjon til Mattilsynet`. Span stops before
  `, som påkrevd av regelverket` (B6 requirement text). PERSON and EMPLOYMENT_INFO nest.
- S011 `gjentatte ganger blitt informert om manglende overholdelse av
  matsikkerhetsforskrifter` — ADD BEHAVIORAL_PATTERN. Precedent
  `gjentatte ganger blitt informert om regelverket, men har unnlatt å følge dette`.

### B6 — offence clause missed entirely (S002)
- `mistanke om forfalskning av skattedokumenter` — ADD CRIMINAL_RECORD. The document's
  `økonomiske uregelmessigheter, inkludert gjeld … og mistanke om forfalskning av
  skattedokumenter` had the debt tagged FINANCIAL_INFO but the offence clause untagged.
  Its three sibling dossiers (S004, S006, S008) all tag the same clause.

### B12/B19 — business name with a named principal (S003)
- `Astrid's Beauty Boutique` — ADD EMPLOYMENT_INFO. S003 had **zero** EMPLOYMENT_INFO
  despite being a business inspection whose principal is named (`Eieren, Astrid Kjersti
  Berg`). Bare business names are routinely tagged in gold (`Dyretransport AS`,
  `Plantehagen AS`, `Slakteri AS`, `Smakfullt AS`).

## Precision / boundary repairs

### B9 — terminal punctuation inside a POLITICAL_CASE span (S002, S004)
Both spans ran through the source's sentence punctuation while leaving the party name's
opening quote unclosed — the worst of both rules.
- S002 `medlem av det høyreekstreme partiet "Norges Fremtid.` →
  `medlem av det høyreekstreme partiet "Norges Fremtid`
- S004 `det høyreekstreme partiet "Norges Fremtid,` →
  `det høyreekstreme partiet "Norges Fremtid`

Governed by POLITICAL_CASE's own extraction rule, whose worked example is this exact
shape: source `"Nordisk Samhold," noe som` → span `tilknytning til den høyreekstreme
gruppen "Nordisk Samhold`. Stop before the punctuation; never synthesize the closing quote.
B5's "close the quote or stop before it" yields to that specific, documented precedent.

### B1 — leading linking verb (S010)
- `er under behandling for dette` → `under behandling for dette`. `under behandling for
  dette` is the verbatim gold form; 13 `under behandling …` spans in gold, none carrying a
  leading `er` except where it is not clause-initial.

### B19 (tightened) — no principal named (S009) — **applied, but see the dissent below**
- `Slakteri AS` — REMOVED EMPLOYMENT_INFO. The document's subject is explicitly `ansatt`
  Lars Magnus Olsen; no owner, innehaver or daglig leder of Slakteri AS appears anywhere.
  `ansatt` is retained. This is the only document in S where the tightened B19 forces a
  change; S013's `Sæther Catering AS` was kept because the business is attributed to the
  named subject (`kontoret til Magnus Sæther`), which satisfies "other person the business
  is attributed to".

## Reviewed, no change

- **S017 (7 spans) is genuinely thin, not under-annotated.** It is a plant-health report
  against a company (`Blomsteroasen AS`) with **no principal named anywhere** — the only
  named humans are the case handler, the reporter, and an unnamed `tidligere ansatt`.
  Consequently: the employer field is untagged (tightened B19, and `check_coverage.py`'s
  one flagged candidate); the suspicion clause `mistenker at Blomsteroasen AS importerer
  planter uten å følge nødvendige karantenebestemmelser` is untagged because CRIMINAL_RECORD
  requires an identifiable natural person and B16's final bullet forbids guessing a
  principal; `medlem av Norsk Hagebrukslag` is untagged as a hobby club, matching the spec's
  own `medlem av det lokale hagelaget` exclusion; and `hobbygartner` is a hobby, not an
  occupation.
- **Plant disease is not HEALTH_INFO.** S008 (`Rosa rosettvirus`, `spredning av
  plantesykdommer`) and S017 (`planter med misfarging og uvanlige flekker på bladene`) were
  left untagged. HEALTH_INFO's taxonomy line and its Verdict section extend the type to
  humans and **animals** only; a plant has no owner-negligence threat model attached and no
  other type covers it. This is a visible chunk of untagged disease vocabulary in two
  documents and is a deliberate call, not an oversight.
- **Religious affiliation** — `medlem av Den norske kirke` (S005, S009, S010, S018),
  `Den Evangelisk Lutherske Frikirke` (S009), `konvertering til Islam i 2020` (S012),
  `medlem av den kristne menigheten "Lysveien"` (S014), `aktivt medlem av en kontroversiell
  religiøs sekt` (S007), `tilhørighet til ny-hedensk tro` (S003), `ateist` (S004, S006,
  S013, S015, S019). All untagged per POLITICAL_CASE's exclusion and Open question 17. The
  `ateist` cases carry no political-atheism framing, so they are untagged rather than
  POLITICAL_CASE. The employer-side counterparts (`Frikirken "Lysets Port"`, `Lysveien
  Menighetssenter`, `Stiftelsen Lysbuen`) stay EMPLOYMENT_INFO per B19, which is the correct
  asymmetry.
- **B20 private-issuer identifiers** — all confirmed untagged: `medlemsnummer 234567`
  (S001), `våpennummer 123456` (S001), `serienummer: ABC1234` (S006),
  `lånenummer: DEF5678` (S006). All state-issued ones are tagged: `sak ID: GHI9012`
  (Skatteetaten, S006), `våpenkortnummer WA123456` (S008) — the batch's one genuine
  Våpenkortnummer, already correct. No `Førerkortnummer`/`Lisensnummer`/`D-nummer` anywhere
  in the batch.
- **`Referanse:`** (S016 `628540`, S017 `364101`) — untagged, per B20's closing bullet.
- **S016 `mye urin og avføring`** — kept. Considered as a B14 cleanliness exclusion, but the
  cats live in the apartment described, which matches gold's `kryper rundt i sin egen
  avføring` rather than `Manglende renhold i dyrenes oppholdsområde`. `Leiligheten ser
  ekstremt rotete ut`, `sterk lukt av ammoniakk` and `vinduene ofte er skitne` stay
  untagged as premises description.
- **S015 `Herr Hansen`** — left untagged. PERSON's Include list covers honorific+surname
  (`Fru Berglund`, `Mr. Halvorsen`), and `Fru Berg`/`Dr. Bjørndal`/`Mr. Askeland` are tagged
  in gold. But the only `Herr <Surname>` precedent in the committed gold is untagged, 7×,
  in exactly this configuration (alongside a tagged full name). Followed the direct
  precedent; flagging it as a real inconsistency in the gold set.
- **S008 `tvangsmulkt på 250 000 NOK`** — left untagged. It sits inside the
  `Mattilsynet vurderer det slik:` block, which B6 names as boilerplate, and it is the
  agency's prospective sanction rather than a documented financial fact about the subject.
  No `tvangsmulkt` precedent exists in gold either way.
- **Four single-token PERSON spans** (S001 `Lars`, S005 `Ingrid`, `Magnus`, S019 `Astrid`)
  — re-verified standalone; left as-is per the settled convention.
- **DATE_TIME recall** — mechanically swept. Every uncovered date-shaped string in the batch
  is a regulation citation (`Forordning (EF) nr. 852/2004`, `FOR-2002-03-08-279`,
  `LOV-2003-06-20-58`), untagged per B6. Durations `14 dager`, `to uker`, `tre årene` also
  correctly untagged.
- **Weapon mentions** — `registrert eier av en hagle` (S001), `registrert våpenlisens`
  (S002), `et registrert haglegevær` (S005), `en registrert rifle` (S008),
  `våpenbesittelseskort … utstedt i 2015` (S009), `et arvevåpen etter bestefaren` (S011)
  all correctly untagged as lawful; the uregistrert/ulovlig cases (S006, S012, S013, S018)
  all correctly CRIMINAL_RECORD.

## Where I think a settled convention is wrong

**The tightened B19 contradicts the gold set it cites.** B19's text claims "All 20 gold
batches follow this reading," but the two nearest precedents to S009 do not. `batch_h_gold`
and `batch_l_gold` each contain a near-identical Slakteri AS document — same
`Org.nr: 987654321 (Slakteri AS)` parenthetical, same `ansatt` subject, and **no principal
named anywhere in either text** — and both tag `Slakteri AS` **and** `ansatt`. I applied the
rule as directed and removed the span from S009, but the result is that three documents of
the same template now disagree. Either B19 needs a carve-out for the Org.nr parenthetical
(where the inspected entity is named by the form itself, not by a human attribution), or
those two committed gold records need the same removal. A broader scan is ambiguous because
principal detection is regex-hard, but the Slakteri AS pair was checked by hand.

## Tool output

```
validate_labels.py data/gold/batch_s_gold.jsonl
  records 19 | labeled spans 544 | violations: 0 | exit 0
  no record with an empty output; min spans/doc = 7 (S017)

check_coverage.py: 2 candidates
  [S009 orgnr_company] 'Slakteri AS'   -- removed above under tightened B19
  [S017 employer_field] 'Blomsteroasen AS' -- no principal named; correctly untagged
  (advisory only; neither added)
```
