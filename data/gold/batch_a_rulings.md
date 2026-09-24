# Batch A Adjudication Rulings

99 disputes across 22 documents (A001–A022). Rulings below are grouped by
recurring pattern first (these account for the bulk of the 99), followed by
per-document tables for the disputes that needed individual judgment.

Legend: **B** = boundary dispute (choice of extent), **P** = presence dispute
(only one annotator produced the span).

---

## 1. Recurring patterns (apply identically everywhere they occur)

### 1.1 `Referanse: NNNNNN` → **DROP** (not GOV_ID) — systematic collision (a)

GOV_ID's "Include — exhaustive surface-form enumeration" lists specific
case/reference trigger labels (`saksnummer`, `sak nr.`, `Vår ref`, `Deres
ref`) and does **not** include `Referanse`. Separately, the Removed-types
table for former CONTEXT_SENSITIVE explicitly names `Referanse` as
"administrative metadata... not tagged at all". Both point the same way, so
every `Referanse: NNNNNN` value is dropped, consistently.

| Doc | Span | Ruling | Rule |
|---|---|---|---|
| A002 | `187406` (P, found by A) | DROP | GOV_ID enumeration + Removed-types table |
| A004 | `193877` (P, found by A) | DROP | same |
| A005 | `338074` (P, found by A) | DROP | same |
| A008 | `216447` (P, found by A) | DROP | same |
| A009 | `497398` (P, found by A) | DROP | same |
| A014 | `607342` (P, found by A) | DROP | same |
| A016 | `177621` (P, found by A) | DROP | same |
| A018 | `411042` (P, found by A) | DROP | same |
| A022 | `830372` (P, found by A) | DROP | same |

`Førerkortnummer:` raises the identical question, but the one instance in
this batch (A001, `12345678901`) is in the **agreed** set (both annotators
tagged it GOV_ID) and therefore untouched per instructions — it was not one
of the 99 disputes. Flagging for consistency: under the same reasoning it
would be dropped too, since `Førerkortnummer` is likewise absent from GOV_ID's
exhaustive enumeration. This should be corrected when the spec is revised for
the next 378 documents.

By contrast, `Vår ref` **is** in the enumeration and was upheld: A011-P6
`2024-475-8923` (found by B, "Vår ref: 2024-475-8923") → **INCLUDE** as
GOV_ID. This contrast (Vår ref included, Referanse dropped) is the clearest
textual evidence that the omission of `Referanse` is deliberate, not a gap.

### 1.2 `to barn` vs `de/Paret har to barn` → shorter form **wins**

B1 gives this exact pair as its own worked example ("`to barn`, never `Paret
har to barn`"): drop the subject + auxiliary `har`, keep the quantifier.

| Doc | Dispute | Ruling |
|---|---|---|
| A003-B0 | `Paret har to barn` vs `to barn` | `to barn` |
| A007-B2 | `de har to barn` vs `to barn` | `to barn` |
| A017-B2 | `de har to barn` vs `to barn` | `to barn` |
| A019-B1 | `de har to barn` vs `to barn` | `to barn` |
| A021-B2 | `de har to barn` vs `to barn` | `to barn` |

### 1.3 `tidligere dømt/anmeldt for X` → **keep** `tidligere`

B2 explicitly keeps a leading temporal qualifier while dropping only the
determiner (`tidligere dom for bedrageri i 2018`, never `en tidligere dom...`).
`tidligere` is not a linking/auxiliary verb, so it stays; where `tidligere` is
directly glued to an auxiliary (`blitt`, `dømt`) that auxiliary comes along
for the ride since the string is contiguous.

| Doc | Dispute | Ruling |
|---|---|---|
| A006-B0 | `dømt for skattesvindel (...)` vs `tidligere dømt for skattesvindel (...)` | longer (`tidligere dømt...`) |
| A007-B0 | `dømt for bedrageri i 2010 (...)` vs `tidligere dømt for bedrageri i 2010 (...)` | longer |
| A020-B0 | `anmeldt for skatteunndragelse (...)` vs `tidligere blitt anmeldt for skatteunndragelse (...)` | longer (`tidligere blitt anmeldt...`) |
| A021-B0 | `dømt for fyllekjøring i 2018 (...)` vs `tidligere dømt for fyllekjøring i 2018 (...)` | longer |

### 1.4 `innrømmet` → **keep** (B1's own explicit keep-list)

B1 lists `innrømmet`/`erkjente` alongside `dømt for`/`diagnostisert med` as
fact-carrying verbs that must stay in the span.

| Doc | Dispute | Ruling |
|---|---|---|
| A011-B2 | `innrømmet også å ha økonomiske problemer med gjeld...` vs `økonomiske problemer med gjeld...` | longer (keep `innrømmet også å ha`) |
| A015-B1 | `forfalskning av skattemeldinger for 2021 og 2022` vs `innrømmet forfalskning av skattemeldinger for 2021 og 2022` | longer (keep `innrømmet`) |

Contrast: A007-B3 `oppgitt gjeld på over 700.000 NOK...` vs `gjeld på over
700.000 NOK...` → **shorter form**, dropping `oppgitt`. `Oppgitt` ("as
declared/self-reported") is a self-report attribution word, not a
fact-establishing verb like `innrømmet`/`diagnostisert med` — it patterns
with the Additional-mechanical-rules "reporting frames sit outside the
clause" principle, not with B1's keep-list.

### 1.5 `tegn på` / `symptomer på` X (hedged animal-disease finding) → **keep**

HEALTH_INFO's own Include list keeps hedge words for suspected animal disease
verbatim (`mistanke om rabies`, `mistenkt tuberkulose`); `tegn på`/`symptomer
på` are the same kind of evidentiary hedge in an inspection-finding register,
not a droppable reporting frame, so they stay in the span.

| Doc | Dispute | Ruling |
|---|---|---|
| A012-B1 | `alvorlig underernæring` vs `tegn på alvorlig underernæring` | longer (`tegn på...`) |
| A020-B2 | `munn- og klovsyke` vs `tegn på munn- og klovsyke` | longer |
| A017-B4 | `mastitt` vs `tegn på kronisk sykdom, inkludert paratuberkulose (Johne's sykdom) og mastitt` | longer (merged — see §2.3) |

### 1.6 Bare company/employer name → **include** as EMPLOYMENT_INFO — systematic collision (c), part 1

EMPLOYMENT_INFO's Include list explicitly covers "a bare company/employer
name... when it identifies where the person works/owns a business and no
role word is attached in the same clause." Every inspection report in this
batch names the business in an `Org.nr.: NNN (Company AS)` parenthetical or
in `hos/av Company AS`, tied to a named owner elsewhere in the document. All
such presence disputes are included.

| Doc | Span | Ruling |
|---|---|---|
| A001-P3 | `Åsland Transport AS` | INCLUDE |
| A006-P5 | `Glamour & Glød AS` | INCLUDE |
| A007-P4 | `Olsen Fisk AS` | INCLUDE |
| A010-P6 | `Olsen Transport AS` | INCLUDE |
| A011-P3 | `Dyrebutikken "Eksotiske Venner"` | INCLUDE |

### 1.7 Bare occupation / role words and role↔company splitting — systematic collision (c), part 2

EMPLOYMENT_INFO's Include list explicitly keeps bare occupation nouns/verb
phrases ("majority of real spans in the corpus"), and its own resolved
conflict (`ansatt` vs. `ansatt Bergen Slakt AS`) shows role+employer merge
into one span **only when directly attached with no clause break**; when two
distinct employment facts are conjoined by "men"/"og" as separate clauses,
the global "one clause, one fact" rule splits them into two spans instead.

| Doc | Dispute | Ruling |
|---|---|---|
| A008-P3 | `jobber som lærer` (found by B) | INCLUDE (bare occupation, answers "yrke" question) |
| A013-P2 | `hovedansvarlig for matlagingen den siste tiden` (found by A) | INCLUDE (specific described work responsibility) |
| A013-P3 | `leder av menigheten` (found by A) | INCLUDE (leadership/management title of an organisation, same family as `styreleder`/`daglig leder`) |
| A022-B2 | `jobber for tiden i en dyrebutikk` vs `utdannet veterinærassistent, men jobber for tiden i en dyrebutikk` | SPLIT: short form (`jobber for tiden...`) for the boundary dispute |
| A022-P4 | `utdannet veterinærassistent` (found by A) | INCLUDE as its own separate span (paired with the split above — "trained as X, but currently works as Y" are two distinct facts joined by "men") |

### 1.8 B3 "case outcome is its own span" generalised beyond CRIMINAL_RECORD

B1–B9 are explicitly stated to be "normative for every narrative type
(CRIMINAL_RECORD, POLITICAL_CASE, FAMILY_RELATION, BEHAVIORAL_PATTERN,
HEALTH_INFO, ECONOMIC_STATUS, FINANCIAL_INFO, EMPLOYMENT_INFO,
SEXUAL_ORIENTATION)". B3's principle — an outcome/consequence clause
separated by a comma or conjunction is its own span, not absorbed — was
therefore applied wherever a sentence conjoined a primary fact with a
distinct causal outcome, including outside CRIMINAL_RECORD. This is also the
general "one clause, one fact" rule at work: **collision (b)** falls out of
this same principle for FINANCIAL_INFO.

| Doc | Sentence | Split into |
|---|---|---|
| A015 (B0 + P3) | `...var involvert i en skandale i 2022 knyttet til misbruk av offentlige midler, noe som resulterte i en betinget dom.` | CRIMINAL_RECORD: `involvert i en skandale i 2022 knyttet til misbruk av offentlige midler` **+** `betinget dom` (matches the spec's own `betinget dom` worked example exactly) |
| A017 (B0 + P5) | `Sæther ble i 2010 dømt for fyllekjøring, noe som resulterte i inndragning av førerkort i seks måneder.` | CRIMINAL_RECORD: `i 2010 dømt for fyllekjøring` **+** `inndragning av førerkort i seks måneder` |
| A006 (B2 + P6) | `Myhre innrømmet også en affære med en tidligere ansatt, noe som har ført til en pågående skilsmissesak.` | FAMILY_RELATION: `innrømmet også en affære med en tidligere ansatt` **+** `pågående skilsmissesak` |
| A001 (B0 + P4) | `Han har også utestående gjeld på over 700 000 NOK, inkludert ubetalt skatt på 150 000 NOK, og er registrert med betalingsanmerkninger.` | FINANCIAL_INFO: `utestående gjeld på over 700 000 NOK, inkludert ubetalt skatt på 150 000 NOK` **+** `registrert med betalingsanmerkninger` — **collision (b) worked example** |

### 1.9 Reporting/evidentiary frames cut (`mistenker at`, `tyder på at`, `funnet/ble funnet`, `dokumenter som viser`, `viste seg å være`)

The Additional-mechanical-rules "reporting frames sit outside the clause"
principle (explicit example: `mistenker at` when merely introducing who is
speculating) was extended consistently to its close paraphrases — discovery
verbs (`(ble) funnet`, `avdekket`) and evidentiary hedges (`tyder på at`,
`viste seg å være`, `dokumenter som viser`) that introduce a fact rather than
stating it directly.

| Doc | Dispute | Ruling |
|---|---|---|
| A010-B0 | `funnet bevis for systematisk forfalskning...` vs `bevis for systematisk forfalskning...` | shorter (drop `funnet`) |
| A006-B1 | `forfalsket` vs `viste seg å være forfalsket` | shorter (drop `viste seg å være`, hedge like `fremstår`) |
| A019-B0 | `forsøk på å skjule inntekter for skattemyndighetene` vs `dokumenter som viser forsøk på å skjule inntekter for skattemyndighetene` | shorter (drop `dokumenter som viser`) |
| A022-B0 | `der hundekampene foregår` vs `mistenker at det er der hundekampene foregår` | shorter — this is the spec's own `mistenker at` example almost verbatim |
| A022-B1 + P3 | `hundekamper` vs `tyder på at de brukes til ulovlige aktiviteter, sannsynligvis hundekamper`; separately `ulovlige aktiviteter, sannsynligvis hundekamper` (P, found by A) | unify on `ulovlige aktiviteter, sannsynligvis hundekamper` (drop the `Støyen fra låven tyder på at de brukes til` evidentiary frame; keep the substantive suspected-offense clause) |

### 1.10 Discontinuous `ser/virker ... ut` → drop the trailing/framing particle

B1's discontinuous-predicate rule (`Hestene ser tynne ut` → `tynne`) plus the
hedge-verb drop list (`virker`) were applied to two boundary disputes.

| Doc | Dispute | Ruling |
|---|---|---|
| A008-B0 | `sløve og apatiske ut` vs `sløve og apatiske` | drop trailing `ut` |
| A018-B0 | `små og svake` vs `også små og svake` | drop leading discourse adverb `også` (not part of the fact, a connective to the previous sentence) |

### 1.11 `saken ble henlagt` → drop subject + passive auxiliary

Direct B1 application (drop subject `saken` + auxiliary `ble`).

| Doc | Dispute | Ruling |
|---|---|---|
| A007-B1 | `saken ble henlagt` vs `henlagt` | `henlagt` |
| A017-B1 | `saken ble henlagt grunnet manglende bevis` vs `henlagt grunnet manglende bevis` | `henlagt grunnet manglende bevis` |

### 1.12 Leading possessive before a kinship noun (`hans`/`hennes`/`deres`/`X's`) → **keep**

Not explicitly covered by B1 (which drops *the grammatical subject of a
clause*, not a possessive determiner inside a noun phrase) or B2 (whose
drop-list is the closed set `en/et/den/det/de`, which does not include
possessive pronouns). Because the possessive is what ties the relation to the
data subject — arguably part of "the fact" itself under Global Rule 2 — and
because B2's enumerated drop-list is explicit and short, the longer form was
adopted consistently. This reading is also the one that agrees with the
batch's own only-one-annotator spans (A020-P4/P5 already include the
possessive with no competing shorter alternative offered).

| Doc | Dispute | Ruling |
|---|---|---|
| A011-B0 | `felles barn` vs `deres felles barn` | `deres felles barn` |
| A011-B1 | `samboer, Astrid Olsen` vs `hans samboer, Astrid Olsen` | `hans samboer, Astrid Olsen` |
| A012-B0 | `bror, Hans Olsen` vs `Lars Kristian Olsen's bror, Hans Olsen` | `Lars Kristian Olsen's bror, Hans Olsen` |
| A013-B0 | `ektemann, Lars Erik Bergquist` vs `hennes ektemann, Lars Erik Bergquist` | `hennes ektemann, Lars Erik Bergquist` |
| A020-P4 | `Hans bror, Trygve Olsen` (found by B) | INCLUDE |
| A020-P5 | `Magnus Olsens samboer, Ane Hansen` (found by B) | INCLUDE |

**This is flagged as a genuine spec gap** — see final report.

---

## 2. Individual / harder judgment calls

### 2.1 Financial-crime findings with an explicit offense noun (`forfalskning`, `skatteunndragelse`) — CRIMINAL_RECORD precedence, offense-noun-sufficient rule

| Doc | Span | Ruling | Rule |
|---|---|---|---|
| A001-P1 | `Forfalskede veterinærattester ble funnet for flere transporter av storfe` | INCLUDE | offense noun `forfalskede` present; matches spec's own `forfalskning av veterinærattester` resolved-conflict example |
| A001-P2 | `Forfalskede veterinærattester for flere dyretransporter` | INCLUDE | same, `Vi har observert:` bullet — B6 taggable |
| A003-P3 | `mistanke om skatteunndragelse knyttet til inntekter fra nettbasert salg av kosmetikk` (found by B) | INCLUDE | `mistanke om` + offense noun, positive example pattern exactly |
| A010-P1 | `Betydelige økonomiske uregelmessigheter i selskapets regnskap, inkludert skatteunndragelse og manglende rapportering av inntekter` | INCLUDE | offense noun present, B6 bullet finding |
| A010-P2 | `Systematisk forfalskning av veterinærsertifikater` | INCLUDE | same |
| A010-P4 | `potensielle brudd knyttet til forfalskning av veterinærdokumentasjon` | INCLUDE | offense noun present even hedged as "potensielle" |
| A017-P9 | `mistanke om skatteunndragelse basert på uoverensstemmelser i inntektsopplysninger` (found by B) | INCLUDE | textbook `mistanke om` + offense noun |

### 2.2 Findings with **no** offense noun — excluded from CRIMINAL_RECORD

Bare documentation-mismatch or compliance-deficiency findings, with no
accusation/conviction verb and no per-se offense noun, do not meet
CRIMINAL_RECORD's definition ("a specific criminal offense... attributed to
an identified natural person"). Consistent with A003's own agreed data, which
already excludes the parallel "importerer og selger kosmetikk... forbudt i
Norge" fact pattern from CRIMINAL_RECORD.

| Doc | Span | Ruling | Rule |
|---|---|---|---|
| A010-P3 | `Uriktig informasjon om dyrenes helsestatus i transportdokumentene` | EXCLUDE | no offense noun, a documentation-accuracy finding |
| A010-P5 | `uriktig informasjon om dyrenes helsestatus` | EXCLUDE | same fact, shorter mention |
| A017-P6 | `samsvarer ikke med den observerte dyrehelsen` | EXCLUDE | records-mismatch finding, no offense noun in this specific sentence |
| A006-P4 | `importerer og selger kosmetikk som inneholder hydrokinon og kvikksølv, stoffer som er forbudt i kosmetikk i Norge` | EXCLUDE | same fact pattern as A003's un-tagged cosmetics clause (both annotators of A003 already agree to exclude it) |

### 2.3 Two diseases conjoined — split vs. merge depends on "inkludert" itemization vs. two fully-detailed diagnoses

HEALTH_INFO's own rule splits two conjoined *named diagnoses* into separate
spans (`diagnostisert med diabetes type 2 og kronisk depresjon` → two spans),
but FINANCIAL_INFO's own boundary rule absorbs an "inkludert"-introduced
itemised list into one span. A017 contains both patterns in the same
document, applied differently based on which structure is present:

- **A017-B4**: `Flere kyr viste tegn på kronisk sykdom, inkludert
  paratuberkulose (Johne's sykdom) og mastitt.` — one general fact ("signs of
  chronic disease") with two itemised examples introduced by `inkludert` →
  kept **merged** as one span (chose the long option). A017-P8
  (`paratuberkulose (Johne's sykdom)` alone) is therefore **not** added
  separately — it is already subsumed by the merged span.
- **A017-B3**: `Flere kyr viser symptomer på Johne's sykdom (diaré,
  avmagring) og mastitt (hovne, varme jur).` — two fully, independently
  detailed diagnoses (each with its own symptom parenthetical) directly
  conjoined by `og`, with no itemisation frame → **split** into two spans:
  `symptomer på Johne's sykdom (diaré, avmagring)` (third span, chosen over
  both offered options) and `mastitt (hovne, varme jur)` (A017-P7, INCLUDE).

### 2.4 Victim-of-crime framing — not CRIMINAL_RECORD

| Doc | Span | Ruling | Rule |
|---|---|---|---|
| A011-P5 | `utsatt for utpressing på grunn av sin seksuelle legning` (found by B) | EXCLUDE | CRIMINAL_RECORD's definition requires the offense be "attributed to an identified natural person" (i.e. the data subject as accused/perpetrator). Here the data subject is the **victim** of an unnamed party's extortion; no identified perpetrator is named. Paired SEXUAL_ORIENTATION span `sin seksuelle legning` (A011-P4) is still included. |

### 2.5 Political-affiliation reputation framing — cut like a reporting frame

| Doc | Dispute | Ruling | Rule |
|---|---|---|---|
| A015-B2 | `kjent for sin politiske aktivisme i "Norgespartiet"` vs `politiske aktivisme i "Norgespartiet"` | shorter (`politiske aktivisme i "Norgespartiet"`) | `kjent for` ("known for") is third-party reputation framing, not an official/evidentiary record of affiliation. Distinguished from `kjent for politiet for voldsepisoder` elsewhere in the batch (agreed, untouched) where "known **to the police**" implies an actual institutional record, not mere public reputation. `politiske aktivisme i` already supplies POLITICAL_CASE's required affiliation noun, so nothing is lost. |
| A006-B3 | `innrømmet under inspeksjonen å være aktivt medlem og økonomisk bidragsyter til partiet` vs the same text **plus** the preceding sentence's `det høyreekstreme partiet "Norges Fremtid" i lokalet.` prefix (crossing a full stop) | shorter, single-sentence form | Spans should not cross a sentence-ending full stop to pick up an antecedent proper name; `partiet` refers back to "Norges Fremtid" anaphorically and the affiliation verb + noun (`innrømmet ... medlem og ... bidragsyter til partiet`) already satisfies the boundary rule on its own. |

### 2.6 `Mattilsynet vurderer det slik:` section — mechanical exclusion honored even for a case-specific-looking sentence

| Doc | Span | Ruling | Rule |
|---|---|---|---|
| A020-P3 | `manglende vilje til å forbedre dyreholdet` (from "Magnus Olsens manglende vilje til å forbedre dyreholdet er bekymringsfull.") | EXCLUDE | B6 names `Mattilsynet vurderer det slik:`, without qualification, as one of the labels whose content is "never tagged" (contrasted explicitly with `Vi har observert:`, which is taggable). Applied mechanically for consistency even though this particular sentence names the individual and describes a non-cooperation pattern that would otherwise read as BEHAVIORAL_PATTERN Include material. |

### 2.7 Miscellaneous single-instance rulings

| Doc | Dispute | Ruling | Rule |
|---|---|---|---|
| A001-B0 / P4 | (see §1.8) | split | FINANCIAL_INFO / collision (b) |
| A002-B0 | `flere bare flekker på brystet og vingene` vs `plukker fjærene sine konstant, og har flere bare flekker på brystet og vingene` | longer (merged) | Same-kind coordinate symptom description under one subject, matching the kept-merged precedent `mager og har en matt fjærdrakt`, not the split precedent (which applies to distinct named diagnoses or clauses with a newly reintroduced subject) |
| A002-P2 | `plukker fjærene sine konstant` | EXCLUDE (not separate) | subsumed by the merged span chosen in A002-B0 |
| A003-B1 | `det høyreekstreme politiske partiet...` vs `propaganda-materiell for det høyreekstreme politiske partiet...` | longer | `propaganda-materiell for` is itself the affiliation-evidencing fact (possessing party propaganda), required by POLITICAL_CASE's "never emit the bare proper noun alone" |
| A003-P2 | `Fru Berg` | INCLUDE | matches PERSON's own `Fru Berglund`-style honorific+surname positive example exactly |
| A005-P1 | `piper mye` (found by A) | INCLUDE (judgment call) | animal vocalization as a welfare/behavioural indicator; HEALTH_INFO's animal-condition Include list is broad (parallels `sikler kraftig`) |
| A005-P2 | `tegn på sykdom eller underernæring` (found by B) | INCLUDE | direct animal-health finding |
| A008-P2 | `apatiske tilstand` | INCLUDE | "apathy" explicitly listed in HEALTH_INFO's animal-condition Include |
| A009 | (only dispute is Referanse) | — | see §1.1 |
| A010-P7 | `gebyr på 500.000 NOK` | INCLUDE | concrete monetary amount, FINANCIAL_INFO Include |
| A010-P8/P9/P10 | vaccination/disease-outbreak findings | INCLUDE | named livestock disease (`blåtunge`) / vaccination status, B6 taggable findings |
| A012-P2 | `systematisk forsømt dyrehold` | INCLUDE | drop hedge `tyder på`, core BEHAVIORAL_PATTERN owner-conduct fact |
| A012-P3 | `alvorlige psykiske lidelser` (found by B) | INCLUDE | concrete family health fact |
| A013-P1 | `håndterte matvarer uten å vaske hendene etter å ha tatt i penger` | INCLUDE | B6 case-specific inspection finding, hygiene-violation conduct |
| A013-P4 | `03.07.1978` (found by B) | INCLUDE | standalone dotted birthdate under "f.", distinct field from the adjacent fødselsnummer |
| A014-P1 | `overoppheting, kløe, og sannsynligvis også til infeksjoner` (found by B) | INCLUDE | animal-condition consequence description |
| A018-P2 | `altfor små til å være separert fra moren` (found by B) | INCLUDE | drop hedge `virket`; welfare/developmental fact already matches the given span |
| A019-B2 | `registrert med diagnose for type 2 diabetes` vs `diagnose for type 2 diabetes` | longer | `registrert med diagnose for` treated as equivalent fact-establishing verb phrase to the explicitly-kept `diagnostisert med` |
| A019-B3 | `Politisk tilknytning til partiet "Kristent Samlingsparti" er registrert` vs same without `er registrert` | shorter | here the fact itself is expressed as the sentence's grammatical subject; trailing `er registrert` is the droppable copula/auxiliary, not additional content |
| A021-B1 | `økonomiske situasjon er svært presset` vs `svært presset` | shorter | direct B1 subject+linking-verb+predicate-adjective pattern (`Øynene virker litt sunkne` → `litt sunkne`) |
| A020-B1 | `økonomiske problemer` vs `sosial utfrysing og økonomiske problemer` | shorter | `sosial utfrysing` is a different fact with no type in the 16-type taxonomy; only the ECONOMIC_STATUS-typed half of the conjunction belongs in this span |

---

## 3. Systematic collisions — summary of the three rulings

**(a) `Referanse: NNNNNN` / `Førerkortnummer:`** → **not tagged** (dropped
from GOV_ID). See §1.1.

**(b) FINANCIAL_INFO vs. ECONOMIC_STATUS around amount parentheticals** → no
document in this batch actually pit the two types against each other on
identical characters, but the underlying B4/one-clause-one-fact question
recurred within FINANCIAL_INFO itself (A001, §1.8): a quantified amount and
its itemised ("inkludert") appositive stay merged in one span; a
non-quantified, distinct follow-on fact ("og er registrert med
betalingsanmerkninger") joined by a bare conjunction gets its own separate
span rather than being folded in. Applied consistently, the general rule is:
absorb only what B4/FINANCIAL_INFO's own section calls for (amount +
qualifier + itemised appositive); split off anything joined by "og" that
states a genuinely distinct fact.

**(c) EMPLOYMENT_INFO scope** → bare role words (`jobber som lærer`,
`utdannet veterinærassistent`, `hovedansvarlig for...`, `leder av
menigheten`) and bare company names (`Åsland Transport AS`, etc.) are both
tagged on their own; role and company merge into one span only when directly
grammatically attached with no clause break, and split into two spans when
they express two distinct facts (e.g. "trained as X, but currently works as
Y"). See §1.6–1.7.
