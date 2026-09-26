# Batch T recall sweep log

Second-pass review of `batch_t_annotator1.jsonl` (529 spans, 19 docs) against
`docs/ANNOTATION_SPEC.md` (B1–B20) and the 287-document committed gold set (batches a–p).
Output: `batch_t_gold.jsonl` (532 spans, 19 docs, min 10 spans/doc, no empty outputs).

21 removals, 24 additions. Net +3.

## The batch-specific question: is CRIMINAL_RECORD over-split?

**Verdict: no — the rate is driven by the documents, with one real over-tagging cluster
and one mistyping cluster, both of which I corrected.**

Checked all 88 CRIMINAL_RECORD spans document by document. 14 of the 19 documents are
`Inspeksjonsrapport med skriftlig veiledning` dossiers, the template that states the same
offence in prose, again in a `Vi har observert:` bullet, again as a numbered section
heading, and again in the `Mattilsynet vurderer det slik:` paragraph. **B6 mandates tagging
each restatement**, and committed gold does exactly that (K015, K016, M009, M010, F008,
D001, C014, B019, P003, P015 all tag the `Mattilsynet vurderer det slik:` forgery sentence
as its own span). T's high per-doc count is that template, not shredding: where an offence
list was split (T004 `forfalsket fakturaer` / `unndratt skatt` / `tatt opp ulovlige lån…`;
T014 `fyllekjøring i 2019` / `besittelse av ulovlige våpen i 2015`; T017 `bedrageri (2015)`
/ `vold (2018)`), each piece still names a distinct offence, exactly as B11 and the spec's
own `trusler mot en nabo` + `våpenbeslag hos Hansen i 2018` resolved conflict require.

The two genuine defects were **presence and type**, not splitting:

### Over-tagging: a whistleblower's guess about a missing permit is not a criminal record (T009, −3)
T009 is a near-clone of the committed **A009** (same fictional business, same street, same
tip template). A009's gold tags **zero** CRIMINAL_RECORD across three equivalent statements
of "they don't seem to be registered / to have the permits". Removed all three T009
CRIMINAL_RECORD spans: a neighbour's speculation is neither an investigator-stated
suspicion nor a named offence.

### Mistyping: non-disclosure of one's own background is BEHAVIORAL_PATTERN (T006, −3 CR / +3 BP)
Committed gold is unanimous: K014, N004, O016, G002, L002, L011, H004 all tag
"har gjentatte ganger unnlatt å opplyse om sin kriminelle fortid" and its restatements as
BEHAVIORAL_PATTERN. T006 had all three occurrences as CRIMINAL_RECORD, and the first also
swallowed the offence list into the same span. Split per B11 and retyped:
BEHAVIORAL_PATTERN `har gjentatte ganger unnlatt å opplyse om sin kriminelle fortid`,
`Eier har unnlatt å opplyse om relevant informasjon om sin bakgrunn, inkludert kriminell
historie og helsetilstand` (subject kept per B18, exactly as N004), `Eriksen's unnlatelse
av å opplyse om sin kriminelle fortid og helsetilstand` (genitive kept, as K014/G002); plus
CRIMINAL_RECORD for the offence list alone.

CRIMINAL_RECORD lands at 84 (4.42/doc). Still above the 3.09 mean, and I am satisfied that
the residue is the restatement-heavy template rather than a labeling defect.

### EMPLOYMENT_INFO: 37 → 36 (1.89/doc)
One real over-tag: T004 `Haukeland Universitetssjukehus`, which is the *diagnosing doctor's*
institution inside a parenthetical, not the data subject's employer. Gold tags a hospital
EMPLOYMENT_INFO only when it is the subject's own workplace (P006 `jobber for tiden i
administrasjonen på Haukeland sykehus`) and otherwise leaves it inside the HEALTH_INFO
clause (J009, O005, P011, V003-style). The spec's own exclusion of incidental institution
names applies. T009 `"Smakfullt AS"` was re-cut to `Smakfullt AS` to match A009. Everything
else checked out: every company tagged has a named principal (B19 tightened), and the two
placeholder employer fields (T007 `Not applicable - Private individual`, T016's
`Fjordland Delikatesser AS` with no owner named, only an ex-employee reporter) were
correctly left untagged by the annotator.

## Other changes, by rule

### B1 — start at the predicate (3)
- T002 `har gjentatte ganger importert eksotiske dyr…` → dropped `har ` (N010's identical
  clause does). T019's parallel span was already correct — the annotator was inconsistent.
- T013 `Hansen ble anmeldt for ulovlig besittelse av en hagle` → `anmeldt for …`.
- T019 `har to barn med` → `to barn` (leading auxiliary + dangling trailing preposition).

### B10 — keep the possessive that modifies the tagged noun (1)
- T013 `tidligere partner, Anette Berg` → `sin tidligere partner, Anette Berg`.

### B13 — bare year nested inside a narrative clause (1)
- T015 `2017` ADD DATE_TIME (inside `registrert Sørensen for mindre tyveri i 2017`).

### FAMILY_RELATION ↔ PERSON nesting (1)
- T005 `Astrid Hansen` ADD PERSON (inside `gift med Astrid Hansen (f. Olsen)`).

### B14 + settled point 2 — cramped/overcrowded space is HEALTH_INFO (3)
Precedents D017 `overfylt`, R005 `overfylte`, H005 `for lite og mangler naturlig vegetasjon`,
K013 `trangt`/`trange buret`, J011 `små og trange, med minimal plass til bevegelse`.
- T007 `holdt i et lite, skittent bur` ADD.
- T008 `liten, overfylt hønsegård` ADD (the only welfare finding in that paragraph the
  annotator skipped; the surrounding cleanliness findings correctly stay untagged).
- T012 `lille plassen` ADD — the annotator tagged `Mangelen på mosjon` from
  "Mangelen på mosjon og den lille plassen…" but dropped the second conjunct (B11).

### B14 + C010 — denial of veterinary care is HEALTH_INFO, not BEHAVIORAL_PATTERN (1)
- T002 `Eriksens unnlatelse av å gi dyrene nødvendig helsehjelp` retyped to HEALTH_INFO,
  structurally identical to C010's `Olsens unnlatelse av å kontakte veterinær`.

### B6 — generic requirement text is never tagged (1)
- T005 `Forfalskning av slike dokumenter` REMOVED. It sits inside `Kravene som gjelder:`
  and is anaphoric ("such documents"). I swept all 44 `Kravene som gjelder:` blocks in
  committed gold: not one has the requirement sentence itself tagged (P003's
  "Det er straffbart å forfalske dokumenter." in that block is untagged). The same
  document's `Mattilsynet vurderer det slik:` and `Vi har observert:` forgery spans stay.

### SEXUAL_ORIENTATION boundary and precedence (6)
- Reporting verbs cut, per the spec's `identifiserer seg som homofil` → `homofil` rule:
  T015 `bekreftet sin lesbiske legning` → `sin lesbiske legning`;
  T019 `bekreftet sin seksuelle orientering som lesbisk` → `sin seksuelle orientering som lesbisk`.
- Same-sex relationship clauses retyped FAMILY_RELATION → SEXUAL_ORIENTATION, per committed
  J004 `tidligere forhold til en mann` and F009 `utenomekteskelig forhold til en mannlig
  nabo`, and the spec's own `i et forhold med Karianne Nilsen` resolved conflict:
  T004 `i et forhold med Kjell Pedersen` (male subject with an ex-wife; male partner),
  T018 `for tiden i et forhold med en kvinne` (female subject). `Kjell Pedersen` stays
  nested PERSON.
- T006 `affære med sin bakeriassistent, Inger Lise Hansen` retyped SEXUAL_ORIENTATION →
  FAMILY_RELATION. Committed gold is 7/7 for `affære` = FAMILY_RELATION (A006, C006, F002,
  F008, L018, N005, R006), and the spec's default is FAMILY_RELATION unless orientation
  itself is the disclosed fact. Flagged below as the one call I am least sure of.

### BEHAVIORAL_PATTERN presence (2)
- T002 `ved en anledning vært involvert i en offentlig krangel…` REMOVED. The type requires
  a recurring or characteristic pattern; the source explicitly marks this as one occasion,
  no offence is named, and no orientation value is disclosed (so nothing for
  SEXUAL_ORIENTATION either — matching H004/N008/I014/O009, where a bare mention of
  "seksuelle orientering" with no stated value is untagged).
- T015 `har gjentatte ganger blitt varslet om alvorlige hygiene- og helsemessige mangler ved
  restauranten` ADD, per L011 and H004 (both tag `har gjentatte ganger blitt varslet/informert
  om regelverket`) and P009.

### Recall: an enforcement sanction (1)
- T015 `tidligere ilagt tvangsmulkt for lignende forhold` ADD CRIMINAL_RECORD.
  H007 `tidligere blitt ilagt bot…`, I007 `ilagt bøter for lignende overtredelser i 2021`,
  J016, G013 and G014 all tag an imposed fine/fee as CRIMINAL_RECORD.

### Splitting two distinct criminal facts (1)
- T019 `ulovlig besittelse av et haglegevær uten tillatelse, knyttet til en tidligere dom for
  trusler i 2018` → two spans. This is the spec's own resolved conflict verbatim
  ("do not merge two distinct criminal facts into one span just because they are causally
  linked"). Both halves independently name an offence, so it is not shredding.

## Reviewed, deliberately left alone

- **T001 `Forfalskning av dokumenter`** in the `Mattilsynet vurderer det slik:` paragraph
  looks like generic legal text, but ten committed documents tag exactly this sentence.
  Kept. This is the counterpart to the T005 removal above: the distinction gold actually
  draws is `Kravene som gjelder:` (untagged) vs. `Mattilsynet vurderer det slik:` (tagged).
- **Numbered section headings** (`1. Ulovlig import av dyr:` in T002, `2. Manglende kontroll
  med dyrevelferd:` in T014). Committed gold is split — K008/I013/F002/D018 tag them, N010
  does not. Given the over-tagging brief for this batch I left them untagged, as the
  annotator had.
- **`utilstrekkelig/mangelfull ventilasjon`** (T013, T017, T018). M012 tags
  `mangelfull ventilasjon` HEALTH_INFO, but ventilation is not on B14's list of basic
  welfare needs and B14 puts premises condition out of scope. Followed B14 and the
  annotator's own consistent treatment; flagging the M012 conflict rather than silently
  following it.
- **T015 `Inspektør`** (EMPLOYMENT_INFO for the signing Mattilsynet inspector). No clean
  precedent either way — F014 tags `tidligere inspektør` but that inspector is a data
  subject; O009's signature block is a placeholder. Left as tagged, since `Bjørn Olsen` is
  itself a tagged PERSON and the type's definition covers any named person's job title.
- **T005 `syke dyr`** nested inside CRIMINAL_RECORD `sende syke dyr til slakt…`. HEALTH_INFO
  × CRIMINAL_RECORD is not on the licensed nesting list, but it is not on the
  mutually-exclusive list either, and it is a genuine animal-health fact. Kept.
- **T002/T013 spans beginning with a dangling `med`** (`med symptomer på sykdom, inkludert
  diaré`, `med symptomer på Johnes sykdom (diaré, avmagring) og mastitt (…)`). B17 would
  argue for pulling in the subject noun `Dyr`/`Flere kyr`; the annotator was at least
  internally consistent and the fact is intact either way. Not churned.
- **T011 `Eier kjører en gammel, rusten bil og virker generelt ustelt`** — not tagged
  ECONOMIC_STATUS. P006's precedent span is `kjøre en gammel, slitt traktor, muligens
  indikerer økonomiske problemer`; the economic inference is what carries the tag and T011
  has no such clause.
- **T004 `Per` / `Marte`** single-token PERSON spans — confirmed standalone given names,
  per the batch note.
- **Religious affiliation** (T001, T004, T005, T006, T013, T014, T017, T018, T019),
  **hobby-club membership** (T004 `aktiv i den lokale skytterklubben`), **lawful registered
  weapons** (T004, T005, T010, T017, T018), **`Referanse:` values** (T003, T008, T009, T011,
  T012, T016), and **commercial hygiene findings** (T001, T006, T010, T013, T015, T016,
  T017, T018) — all correctly untagged; verified in every document.

## Where I think a settled convention is questionable

The `affære` retype (T006) is the one place I followed precedent against my own reading.
The source is "Han har også oppgitt å være homofil, **men** rykter … antyder en affære med
sin bakeriassistent, Inger Lise Hansen" — the `men` makes the partner's gender load-bearing
against his stated orientation, which is precisely the spec's stated exception ("unless the
affair partner's gender combined with the subject's stated orientation is the disclosed
fact"). 7/7 committed precedents nonetheless put `affære` in FAMILY_RELATION, and none of
those 7 has a contrasting orientation statement, so the exception has never actually been
exercised. I applied FAMILY_RELATION and am flagging it rather than deviating.

Secondarily: M012's `mangelfull ventilasjon` as HEALTH_INFO contradicts B14's closed list
of basic welfare needs. One of the two should be corrected project-wide.

## Tool output

```
validate_labels.py: records 19, labeled spans 532, violations: 0, exit 0
check_coverage.py: 1 candidate -- T004 [id_number] '123456789'
    Reviewed: this is `journalnummer 123456789`, a hospital's internal record number.
    B20 excludes it explicitly (issuer test: private body). Correctly untagged;
    not added.
docs 19 / total spans 532 / min spans per doc 10 (T016) / empty outputs 0
```
