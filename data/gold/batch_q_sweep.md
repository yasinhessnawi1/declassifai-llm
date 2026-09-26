# Batch Q recall sweep log

Reviewer pass over `batch_q_annotator1.jsonl` (540 spans, 19 docs). Output:
`batch_q_gold.jsonl` (548 spans: +11, -3).

The batch note flagged that the annotator was interrupted and re-ran, so the first
check was completeness rather than judgement. All 19 documents received a genuine
full pass: no record has an empty output, every `Adresse:`/`Poststed:`/`Telefon:`/
`E-post:`/`Org.nr.:`/`Fødselsnummer:` field value in the batch is covered, and a scan
for date-shaped strings found **zero** uncovered DATE_TIME candidates in any document.
`check_coverage.py` reported the annotator file clean before any edit.

Span density was measured per document against the 287-document committed gold set,
split by template (interview-style mean 9.48 spans/1k chars, dossier-style 10.89).
Eighteen documents sit between 0.89x and 1.42x of their template's mean. The single
outlier is **Q018 at 0.69x**, which was re-read line by line; it yielded one genuine
miss (below) and is otherwise explained by a long passage of generic reptile-biology
explanation that gold consistently leaves untagged.

A second, mechanical recall probe was run: every span string that occurs in >=3
committed-gold documents and is tagged in >=75% of them was searched for in Batch Q.
It returned **no** uncovered hits. The annotator's recall on recurring vocabulary is
solid; the residual misses below are all one-off constructions.

## Genuine recall misses

### B10 / FAMILY_RELATION+PERSON nesting — an ex-spouse clause missed entirely (Q004)
- `Hennes eksmann, Bjørn Hansen` — ADD FAMILY_RELATION. `Bjørn Hansen` was already
  tagged PERSON and his fødselsnummer, address, phone and email were all tagged, but
  the kinship clause itself carried no tag. Precedent is unanimous: of 15
  `eksmann`/`ekskone`/`tidligere ektefelle` constructions in committed gold, 13 are
  FAMILY_RELATION (`Hans ekskone, Astrid Jacobsen`, `hennes eksmann, Lars Olsen`,
  `sin ekskone, Astrid Olsen`) and the other 2 are subsumed by a CRIMINAL_RECORD
  clause, which is not the case here. Possessive kept per B10.

### B6 — observation-bullet restatement missed (Q004)
- `Import og planting av settepoteter uten nødvendig tillatelse og karantene` — ADD
  CRIMINAL_RECORD. The `Vi har observert:` bullet restates two clauses the annotator
  correctly tagged in prose. Gold tags this restatement in 6 of 10 comparable
  `Vi har observert: Import ...` bullets (`Import og omsetning av planter uten
  nødvendig importkontroll og karantene`, `Import av orkideer fra Thailand uten
  nødvendig importtillatelse ...`); the untagged four are symptom lists, not
  offence restatements. Subject kept per B17, trailing stop trimmed per B9.

### B6 — suspicion restated in the `Inspeksjonen omfattet:` scope line (Q008, Q011)
- Q008 `mistanke om økonomisk kriminalitet` — ADD CRIMINAL_RECORD.
- Q011 `mistanke om økonomisk mislighold` — ADD CRIMINAL_RECORD.
  Both documents tag the suspicion where it recurs later but not where the scope line
  states it first. Committed gold tags the scope-line instance in 6 of 10 cases, and
  the exact string `mistanke om økonomisk kriminalitet` is tagged there 3 times with
  no counter-example. Q006 in *this batch* already tags both occurrences of
  `mistanke om økonomisk mislighold`, so this is also an internal-consistency fix.

### ECONOMIC_STATUS — evaluative half of a mixed clause dropped (Q005)
- `sliter økonomisk` — ADD ECONOMIC_STATUS. The annotator tagged only the quantified
  half (`gjeld på over 700.000 NOK, hovedsakelig ...`) as FINANCIAL_INFO. `sliter
  økonomisk` occurs 12 times in committed gold and is tagged ECONOMIC_STATUS **12/12**,
  including one case (`betydelig gjeld (over 700 000 NOK) og sliter økonomisk`) where
  it sits alongside a FINANCIAL_INFO amount exactly as here. The amount is not inside
  the added span, so the ECONOMIC_STATUS exclusion for quantified spans does not bite.

### PERSON — honorific+surname form untagged (Q007)
- `Frk. Berglund` — ADD PERSON. The spec's PERSON Include list names `Fru Berglund`
  and `Mr. Halvorsen` explicitly, and committed gold tags honorific+surname in 29 of
  30 occurrences (`Fru Berg`, `Fru Hansen`, `Mr. Askeland`, `Herr`-forms). This is not
  a bare sub-token under the settled convention: the honorific is part of the
  referring expression. Q008 in this same batch already tags `Herr Olsen`, so the
  annotator was inconsistent rather than applying a rule.

### HEALTH_INFO — animal disease named inside a criminal clause (Q012)
- `salmonellautbrudd i besetningen i juli 2023` — ADD HEALTH_INFO. Only the
  falsification clause around it was tagged. Committed gold tags the directly
  comparable `Salmonellautbrudd i 2023 og 2024` HEALTH_INFO while separately tagging
  `Manipulerte rapporter om salmonellautbrudd` CRIMINAL_RECORD. `juli 2023` was
  already DATE_TIME (B13 nesting preserved).

### B14 / B17 — missing UV light for reptiles (Q018)
- `Mangel på UV-lys` — ADD HEALTH_INFO. This is the settled heat/UV-lamp rule, and
  gold tags all 6 occurrences of the pattern. The nearest precedent is structurally
  identical: `Mangelen på varmelamper` is tagged, with its trailing
  "er spesielt bekymringsfullt, da reptiler er avhengige av ..." dropped as commentary
  per B17 — exactly the shape of this sentence. The document's other lamp finding
  (`har aldri sett varmelamper på, selv om det er midt på vinteren`) was already tagged.

## Precision / boundary repairs

- **Q005** HEALTH_INFO `kronisk depresjon hos Dr. Per Hansen ved Bergen Medisinske
  Senter` -> `kronisk depresjon hos Dr. Per Hansen`. The span ran through a PERSON
  span and on into an institution name. Gold's one directly comparable case tags
  `er under behandling hos Dr. Per Hansen` and stops before `ved Lørenskog Legesenter`;
  institution names are excluded by NO_ADDRESS's own rule and own no HEALTH_INFO
  characters. Provider kept, institution trimmed.
- **Q008** FAMILY_RELATION `to barn med` -> `to barn`. The original ended on a dangling
  preposition. B2 keeps the quantifier; nothing else in the clause belongs.
- **Q010** FAMILY_RELATION `rykter om utroskap med flere kvinnelige medlemmer av
  menigheten` -> `utroskap med flere kvinnelige medlemmer av menigheten`. `rykter om`
  is a reporting/sourcing frame and the Global rules cut it (the spec's own worked
  example turns "rykter om hans homofile legning" into `hans homofile legning`). Gold
  agrees on this exact vocabulary: `rykter om utroskap sirkulerer i lokalmiljøet` is
  tagged `utroskap`, and `rykter om en affære med en lokal politiker` is tagged
  `affære med en lokal politiker`. (Note the contrast with `anklager om` /
  `beskyldninger om`, which gold *keeps* — see below.)

## Reviewed and deliberately left alone

Each of these looked like a defect and was checked against committed gold before being
left as the annotator had it.

- **Q003 `Eieren,`** (the `Eieren, <Name> (Fødselsnummer: ...)` dossier opener) — not
  added as EMPLOYMENT_INFO. Gold leaves this untagged in 8 of 9 occurrences of that
  exact construction; the single tagged instance is the outlier.
- **Q003 `pågående konflikt med naboen angående en eiendomsgrense`** — not added as
  BEHAVIORAL_PATTERN, despite resembling the spec's `Eier observert kranglende med
  naboer angående hunden` example. The near-verbatim gold twin (`nevnte en pågående
  konflikt med naboer knyttet til støyklager`) and a second (`involvert i en offentlig
  konflikt med naboer angående gjerdehold`) are both untagged.
- **Q001 `beskyldninger om utroskap`** — frame kept. Unlike `rykter om`, gold keeps
  accusation frames: `involvert i en offentlig skilsmisse med anklager om utroskap`,
  `anklager om økonomisk utroskap`.
- **Q007 and Q012 BEHAVIORAL_PATTERN spans running through a `(f. ..., fødselsnummer
  ...)` parenthetical** — left whole. B4 argues for stopping before the bracket and B18
  argues for starting at the actor; gold resolves the conflict in favour of contiguity
  (`Manglende helsedokumentasjon for Lars Magnus Olsen (f. 1962, ID-nummer: ...,
  telefon: ..., email: ...) for tredje gang på under ett år` is a committed
  BEHAVIORAL_PATTERN span).
- **Q014 `registreringsnummer BT 12345`** — untagged. Both vehicle registrations in
  committed gold are untagged, and the spec's own extraction example treats the
  registration number as out of scope.
- **Q011 `ST-476`** (fishing-vessel registration) — left as GOV_ID. State-issued under
  B20's issuer test; no counter-precedent found.
- **Q017 `Overbefolkning`, `det store antallet fisk`, `den dårlige vannkvaliteten`** in
  the reporter's closing "Hvorfor mener du ..." summary — not added, even though
  overcrowding and dirty water are both settled HEALTH_INFO triggers. Gold tags
  `overbefolkning` in inspection reports and observation bullets but leaves the
  interview-template *reason-summary* restatement untagged in 3 of 3 comparable cases
  (`Det store antallet katter i en liten leilighet ...`, `lider på grunn av
  overbefolkning, manglende hygiene ...`, `på grunn av overbefolkning, mangel på
  rengjøring ...`). `vannkvalitet` is untagged in its single gold occurrence.
- **Q018 `Erik Bakke virker isolert og har sjelden besøk`** — untagged. A gold document
  contains a near-identical sentence in the same `Andre opplysninger:` slot and leaves
  it untagged; 4 of 5 `virker isolert` occurrences in gold are untagged.
- **Q019 `Saken er meldt til politiet`**, **Q009 `De observerte forfalskningene ...`**,
  **Q015 `manglende opplæring av ansatte`** — all untagged. Gold leaves every
  comparable instance untagged (7/7 for referral-to-police boilerplate, 10/10 for
  `Mattilsynet vurderer det slik: De observerte ...` evaluation openers, 1/1 for staff
  training).
- **Q015 `(sak henlagt pga. manglende bevis)`** absorbed into its CRIMINAL_RECORD
  clause rather than split per B3 — gold does it both ways depending on whether the
  outcome sits in a parenthetical (absorbed, 2 cases) or after a comma (split, 4
  cases); the annotator matched the parenthetical pattern.
- **Q004 `Høydahls økonomiske situasjon, preget av ...`** — the FINANCIAL_INFO span was
  not extended leftward. Gold leaves the bare `X's økonomiske situasjon` prefix
  untagged in 6 cases where only an amount follows, and tags ECONOMIC_STATUS only when
  an evaluative predicate is present (`er svært anstrengt`, `bekymrer meg`). "preget
  av" is not evaluative.
- **Q004 `mistenkes å være bærer av ringrot`** — untagged. HEALTH_INFO covers humans
  and animals; a plant pathogen is neither.
- All religious affiliations (`Jehovas vitner`, `Den norske kirke`,
  `Pinsemenigheten "Levende Lys"`, Wicca symbols, `katolikk`), `ateist` with no
  political framing, all commercial/structural hygiene findings, all lawful registered
  weapons, all `Referanse:` values, all placeholder field values (`Ukjent`,
  `(None provided)`, `(blank)`, `Deres ref.: -`) — reviewed, correctly untagged.

## Disagreements with the settled conventions

None. Every settled point was applied as written; the two places where I initially
expected to deviate (the B6 restatement rule in interview-template reason-summaries,
and B19's treatment of a bare `Eieren`) turned out to be settled the other way by the
committed gold set, and I followed gold rather than my first reading.

One observation worth recording, not a disagreement: within this batch, Q010 and Q012
fold an evaluative phrase and a NOK amount into a single FINANCIAL_INFO span
(`økonomiske situasjon er kritisk, med gjeld over 500 000 NOK`), whereas committed gold
elsewhere splits that into ECONOMIC_STATUS + FINANCIAL_INFO. Both readings are
defensible under the precedence chain (the merged span contains an amount, so
FINANCIAL_INFO is the correct single type), so I did not churn them, but a future
adjudication pass may want to standardise it.

## Tool output

```
validate_labels.py data/gold/batch_q_gold.jsonl : violations 0, exit 0
records 19 | labeled spans 548 | distinct documents 19 | empty records 0
min spans/doc 16 (Q014), max 50 (Q019)
check_coverage.py data/gold/batch_q_gold.jsonl  : clean (0 candidates)
```
