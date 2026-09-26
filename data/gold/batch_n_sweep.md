# Batch N recall sweep log

Starting spans (annotator1): 468. Final (gold): 469. Added: 4. Removed: 2.

## 1. B20 (new rule — issuer, not label) — 1 forced change

- **N010** — REMOVE GOV_ID `9876543210`.
  Source: `...inkassokrav fra Lindorff (sak nr. 9876543210)`. Lindorff is a private
  debt-collection (inkasso) company, not a public authority. B20: "GOV_ID is
  decided by the issuer, not the label" — a `sak nr.` looks official but here
  the issuer is a private creditor, directly analogous to B20's own
  `lånenummer` (bank) exclusion. The number stays inside the existing
  FINANCIAL_INFO clause; it is simply not additionally GOV_ID.
  Checked for the same pattern elsewhere: `lån nr. 1234567890` (Nordea Bank,
  N010) was already correctly excluded by the annotator; `journalnummer
  2018/12345` (Haukeland Universitetssjukehus, N016) was already correctly
  excluded. No other B20 violations found — every other `sak nr.`/`saksnr.`/
  `Vår ref`/`Deres ref`/`ID-nummer`/fødselsnummer/org.nr in the batch is
  issued by a court, police district (politisak), or Mattilsynet itself.

## 2. EMPLOYMENT_INFO over-tagging check — 0 corrections

Direction was to check whether an incidental third party (doctor, inspector)
had their occupation tagged. Actual count: **29** EMPLOYMENT_INFO spans (not
41 as stated in the task framing — recounted directly from the file twice).
Grepped the batch for veterinær/lege/inspektør/dyrlege/saksbehandler: the only
hits are `utdannet veterinærassistent` (N002) and `utdannet veterinærsykepleier`
(N003), both the **reporter's own** past training, volunteered in answer to
the template's own "Har du et yrke...?" question — this is the exact
construction the spec's own EMPLOYMENT_INFO positive example is drawn from
("Jeg er utdannet veterinærassistent, men jobber for tiden i barnehage"), so
it is required, not over-tagged. Every other EMPLOYMENT_INFO span is either
the data subject's own business/role (B12) or the organisation in a "Navn på
... virksomhet:" / "Org.nr.: NNN (Name)" field where the document names a
human principal (B19/B16: N001, N004-N006, N008, N010-N012, N014-N018). No
third-party professional's occupation was found tagged anywhere in the batch.
Conclusion: the elevated span count is legitimate B12/B19 volume (several
docs carry a coordinated title + separate bare company-name span, e.g. N014,
N017), not a defect.

## 3. Other genuine misses/violations — 3 changes

- **N007** — REMOVE CRIMINAL_RECORD
  `Mistenker at det kan være økonomiske motiver bak den antatte ulovlige aktiviteten`.
  Global mechanical rule ("Reporting frames vs. diagnostic/evidentiary
  frames"): "mistenker at ... when it is merely introducing who is
  speculating" sits outside the tagged clause and is cut — this is the
  rule's own named example, verbatim. This is the reporter's personal hedge
  in the "Andre opplysninger" field, not an official "mistenkt for
  [offense]"/"mistanke om [offense]" accusation. After trimming the
  reporting-frame verb, the remainder ("det kan være økonomiske motiver bak
  den antatte ulovlige aktiviteten") names no specific offense and is
  redundant with the document's actual specific offenses (`hundeslagsmål`,
  `brukt i kamper`), which remain tagged. Confirmed the annotator applies the
  cut correctly elsewhere (N008 "erklærte seg som", N012 "hun hevder ble
  brukt til...", N015/N017 "hevder"/"oppga å være") — this one instance was
  the inconsistency.

- **N012** — ADD CRIMINAL_RECORD `graverende brudd på hygieneforskriftene`.
  Sibling-document consistency: N010 (`alvorlige brudd på dyrevelferdsloven og
  forskrift om import av dyr`) and N011 (`alvorlige brudd på regelverket
  knyttet til...`) and N017 (`Alvorlige brudd på Mattilsynets regelverk
  vedrørende karanteneforskrifter...`) all tag the "Inspeksjonen avdekket
  [severity] brudd på [named regulation]" opening finding as CRIMINAL_RECORD
  (dropping the "Inspeksjonen avdekket" subject+verb per B1); only a fully
  generic "avdekket ... brudd på regelverket" with no named regulation (N006)
  is left untagged. N012's sentence names a specific regulation
  (hygieneforskriftene) and was missed.

- **N012** — ADD CRIMINAL_RECORD `Ulovlig politisk aktivitet i tilknytning til virksomheten`.
  B6 restatement: the fact ("illegal political activity" at the venue) is
  introduced in the intro line and then restated verbatim, capitalized, as
  its own bulleted finding under `Vi har observert:` — the exact pattern B6
  flags as the most persistent miss. `Ulovlig` + noun phrase is a
  self-contained illegality assertion (same shape as the spec's own
  `ulovlig våpenbesittelse` positive example), so CRIMINAL_RECORD, not
  POLITICAL_CASE (no party/movement is named in this clause).

- **N015** — ADD BEHAVIORAL_PATTERN `Mangler oppdatert helseattest for produksjonsansvarlig`.
  B6 restatement of the already-tagged prose fact `har ikke fremlagt
  oppdatert helseattest til tross for gjentatte pålegg`, restated in the
  `Vi har observert:` bullet in different words. Tagged under the same type
  as the prose version per B6 ("tagged under whichever type they state,
  exactly as they would be in running prose").

## Confirmed NOT changed (checked and left alone)

- Short bare-predicate HEALTH_INFO spans (`halter`, `lider`, `tynne`, `redd`,
  etc.) — left untouched per instruction; boundary convention confirmed
  consistent with B1's own worked examples across all 18 docs.
- Structural/premises findings (dirty enclosures, small cages/yards, barn
  hygiene, store hygiene, expired food) — consistently left untagged per B14's
  own negative examples (`Innhegningene er små og virker skitne`); verified
  the same convention holds in N002, N003, N007, N010, N012, N013, N014,
  N018.
- Reassuring negatives (`Det ble ikke funnet våpen`, `ingen registrerte
  våpenhendelser`, `Jeg har ikke sett den leke...`) — left untagged per B15.
- Registered/lawful weapons (`registrert jaktrifle`, `eier en registrert
  rifle`) — left untagged per CRIMINAL_RECORD's own exclude list.
- Religious affiliation and atheism (`medlem av Den norske kirke`, `erklærte
  seg som ateist`, `åsatru`) — left untagged; no type covers belief.
- `hemmelig affære` (N005) kept as FAMILY_RELATION as tagged — defensible
  boundary call (intimate-relationship fact, similar to `skilsmisse` which is
  tagged without a named partner), not a clear violation.
- Single non-recurring hygiene lapses by the data subject (N012 "håndterte
  mat uten tilstrekkelig hygiene", N014 "ikke benyttet hansker eller
  hårnett") — left untagged both places for consistency; neither is clearly
  BEHAVIORAL_PATTERN (no repetition marker) nor any other type.
