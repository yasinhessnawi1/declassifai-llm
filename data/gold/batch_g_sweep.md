# Batch G — Recall Sweep Log

Reviewer: recall-review pass over `batch_g_annotator1.jsonl` (16 docs, 380 spans) against
`docs/ANNOTATION_SPEC.md`, applying three post-dated rule changes (B17, B18, gambling
routing) plus a targeted company-name fix and a general recall sweep per Step 3 of the
task brief. Output: `batch_g_gold.jsonl` (395 spans). Validator: `tools/validate_labels.py`
reports `violations: 0`.

Starting spans: 380. Added: 15. Fixed (boundary retype, same net count): 2. Removed: 0.
Final total: 395.

---

## 1. B18 — BEHAVIORAL_PATTERN keeps its subject (2 fixes, 1 add)

**G002** — Two spans were built by applying B1's subject-drop to a BEHAVIORAL_PATTERN
clause, which is the one type B18 exempts from B1. Both sentences state the pattern as a
plain declarative ("Eriksen har... / Eriksen har unnlatt...") with no witness-reporting
wrapper to peel off, so the named subject is the earliest word establishing WHO and must
stay in the span (PERSON `Lars Magnus Eriksen` nests inside it, same as the FAMILY_RELATION
precedent).

- FIX: `har gjentatte ganger tilbakeholdt informasjon om sin kriminelle fortid, inkludert
  økonomisk kriminalitet og voldsepisoder` → `Lars Magnus Eriksen har gjentatte ganger
  tilbakeholdt informasjon om sin kriminelle fortid, inkludert økonomisk kriminalitet og
  voldsepisoder`
- FIX: `har unnlatt å oppgi sin kriminelle fortid` → `Lars Magnus Eriksen har unnlatt å
  oppgi sin kriminelle fortid`

**G003** — a general-recall BEHAVIORAL_PATTERN miss that happens to be a clean B18 case:
`Har sett bonden kjøre forbi med høy flere ganger` (witness lead-in + subject + recurring
action, stopped before the hedge clause "men usikker på..."). Structurally identical to
the spec's own worked example `Har sett eieren bli sint på hunden ved flere anledninger`.
- ADD: `Har sett bonden kjøre forbi med høy flere ganger`

## 2. B17 — when the subject is the fact, keep it (1 add)

**G002**, `Mattilsynet vurderer det slik:` paragraph: "Eriksens tilbakeholdelse av
informasjon er et alvorlig brudd på tilliten." Applying plain B1 would drop the subject
and leave only `et alvorlig brudd på tilliten` — vacuous filler that names no fact. The
subject `tilbakeholdelse av informasjon` (withholding of information) is itself a
nominalised action carrying the disclosure, so B17 keeps it (with the B10 possessive
"Eriksens"). This is also a B6 restatement of the withholding pattern already established
earlier in the document.
- ADD: `Eriksens tilbakeholdelse av informasjon` (BEHAVIORAL_PATTERN)

No other B17 candidates were found: all other bare-adjective HEALTH_INFO/ECONOMIC_STATUS
spans in the batch (`anstrengt`, `tynn`, `undervektig`, `sliter økonomisk`-type phrases,
etc.) already state their fact fully once the subject is dropped, matching the spec's own
positive-form examples — B17 does not apply to them and they were left untouched.

## 3. Gambling routing (1 add)

**G012**: "Han hevdet at hans økonomiske problemer stammer fra spilleavhengighet og et
mislykket investeringsprosjekt i kryptovaluta" was tagged as one ECONOMIC_STATUS span.
Per the ruling, the habit itself (`spilleavhengighet`) is BEHAVIORAL_PATTERN while the
outcome-framed narrative (`hans økonomiske problemer... mislykket investeringsprosjekt i
kryptovaluta`) is correctly ECONOMIC_STATUS. Added the missing BEHAVIORAL_PATTERN tag as
a nested span rather than fragmenting the existing ECONOMIC_STATUS clause (both facts are
genuinely disclosed on overlapping characters, consistent with the spec's general nesting
philosophy for the financial-crime cluster).
- ADD: `spilleavhengighet` (BEHAVIORAL_PATTERN, nested inside the existing ECONOMIC_STATUS
  span)

G011's two `spillegjeld` occurrences were already correctly split by the annotator
(quantified → FINANCIAL_INFO `Gjeldsbelastning over 500 000 NOK, inkludert spillegjeld`;
unquantified growth description → ECONOMIC_STATUS `økende spillegjeld`) — no change
needed there. No other gambling-vocabulary spans exist in the batch.

## 4. Known company-name error (B12 vs. B16 conflation) — 3 adds, 1 declined

Bare business/company names in "Navn på dyreeier eller virksomhet:" fields where **no
human owner is named anywhere in the document** were skipped, apparently because B16's
"needs a named principal" condition (which only licenses tagging *conduct*) was
mistakenly applied to B12 (which tags a bare company name regardless of any owner).

- ADD `Fjordland AS` (G007) — flagged in the task brief; no owner named in the document.
- ADD `Blomsterhagen AS` (G010) — flagged in the task brief; no owner named.
- ADD `Dyrebutikken "Kosekassen"` (G004) — **found during the sweep, not in the flagged
  list**: same pattern (pet shop under investigation, "Eieren" referenced but never
  named).
- `Olsen's Melk AS` (G011) — flagged in the task brief as missing, but verified **already
  present** in `batch_g_annotator1.jsonl` (both the quoted form `"Olsen's Melk AS,"` and
  the bare form `Olsen's Melk AS` are in the existing EMPLOYMENT_INFO list). No change
  made; noted as a discrepancy between the brief and the source file.
- `Kreditbanken AS` (G012) — flagged in the task brief, but **declined**. In this
  document `Kreditbanken AS` appears exactly once, exclusively as the creditor to whom
  Iversen's debt is owed ("Gjelden overstiger 500 000 NOK, primært tilhørende Kreditbanken
  AS..."), never as anyone's employer. FINANCIAL_INFO's own Exclude list states a company
  name is EMPLOYMENT_INFO "unless the company appears specifically as a financial
  counterparty" — which is exactly this case. The batch's own G008 treats an identical
  `Kreditbanken` creditor mention the same way (financial counterparty only, no
  EMPLOYMENT_INFO tag), so tagging G012's occurrence as EMPLOYMENT_INFO would both
  contradict the spec and be inconsistent with the rest of this batch. Left untagged as
  EMPLOYMENT_INFO (it remains correctly captured inside the existing FINANCIAL_INFO span).

Other "Org.nr.: NNNNNN (Company AS/Name)" and business-name occurrences in the batch
(Eriksen's Bakeri AS, Catering Virksomheten AS, Halvorsen Fiskeforedling AS, Meieri
Iversen, Høydahl Plantesenter AS) were already correctly tagged — all of those documents
name a human owner and already carry an EMPLOYMENT_INFO span. `Catering "Smakfullt"`
(G006) has a bare mention in addition to the already-tagged `innehaver av "Smakfullt,"`
combined span; not added, since G006 does name an owner (Olsen) and already has a valid
EMPLOYMENT_INFO tag for that business — adding a second bare-form tag for the same
company would be re-litigating a presence choice outside the specifically identified
missing-owner error pattern, not fixing it.

## 5. General recall sweep (Step 3) — 8 adds

**GOV_ID — "Deres ref:" / "Vår ref:" populated values never tagged (4 adds):**
- G008: `2024-475-8963` ("Vår ref:" — populated, was entirely missed)
- G009: `PGH/2024-03-15` ("Deres ref:" — populated, only "Vår ref:" was tagged)
- G012: `MI/2023-10-27` ("Deres ref:" — populated, only "Vår ref:" was tagged)
- G013: `AH/20231026` ("Deres ref:" — populated, only "Vår ref:" was tagged)

Verified every other "Deres ref:"/"Vår ref:" field in the batch: blank/dash placeholders
(G002, G005, G006, G008's Deres ref, G011, G014) are correctly excluded per spec.

**CRIMINAL_RECORD — B6 restatements in "Vi har observert:" bullets (5 adds):**
- G011: `Systematisk feilrapportering av inntekter og kostnader` — restates "systematisk
  manipulering av inntekter og kostnader" from the Oppsummering paragraph, in different
  words, as its own bullet.
- G011: `Bruk av falske fakturaer for å skjule faktiske kostnader` — restates the
  falsified-invoices fact from the fuller offense clause, in different words.
- G011: `Forsøk på skatteunndragelse` — a standalone bullet sentence restating the offense
  named inside the larger Oppsummering clause; a distinct string per B6.
- G014: `Forfalskning av importdokumentasjon` — restates the forgery confession already
  in the Oppsummering paragraph; the parallel bullet in sibling document G013
  ("Forfalskning av importdokumentasjon") was already correctly tagged there, so this was
  an inconsistency between two structurally identical documents.
- G014: `ilegge Anette Borgersens planteskole en bot på 250 000 NOK` — a B3 case outcome
  (the fine actually imposed); the parallel span in G013 ("ilegge Høydahl Plantesenter AS
  et gebyr på 250 000 NOK") was already tagged CRIMINAL_RECORD there, confirming this is
  a genuine miss rather than a deliberate boundary choice.

`Manglende oppbevaring av nødvendig dokumentasjon` (G011) and `Manglende isolasjon av
importerte planter` (G014) were considered and left untagged: neither names a per-se
criminal offense noun (unlike `Forfalskning`/`Brudd på karantenebestemmelser`), and they
read as administrative/compliance findings rather than a restated offense — flagged below
as a guess call rather than forced either way.

Checked and found already complete, no changes needed: all phone numbers, email
addresses, postal codes, street addresses, dotted/prose dates (including B13 nested
dates inside CRIMINAL_RECORD/HEALTH_INFO clauses), org.nr values, fødselsnummer/D-nummer
values, family-relation clauses (gift med/samboer/partner/skilt/barn — all present,
including the correctly-excluded `nabo`/`adskilt` false leads), and HEALTH_INFO
deprivation coverage (food/water/shelter/grooming/exercise/social-contact) across both
the interview-style and inspection-style document templates. `Referanse: NNNNNN` values
were correctly never tagged in any of the 7 documents that carry one.

---

## Totals

| | Count |
|---|---|
| Starting spans | 380 |
| Added | 15 |
| Fixed (boundary retype) | 2 |
| Removed | 0 |
| **Final total** | **395** |

Per-type (orig → gold, delta):

| Type | Orig | Gold | Δ |
|---|---:|---:|---:|
| BEHAVIORAL_PATTERN | 8 | 11 | +3 |
| CRIMINAL_RECORD | 33 | 38 | +5 |
| DATE_TIME | 39 | 39 | 0 |
| ECONOMIC_STATUS | 5 | 5 | 0 |
| EMAIL_ADDRESS | 15 | 15 | 0 |
| EMPLOYMENT_INFO | 22 | 25 | +3 |
| FAMILY_RELATION | 20 | 20 | 0 |
| FINANCIAL_INFO | 11 | 11 | 0 |
| GOV_ID | 44 | 48 | +4 |
| HEALTH_INFO | 70 | 70 | 0 |
| NO_ADDRESS | 19 | 19 | 0 |
| NO_PHONE_NUMBER | 18 | 18 | 0 |
| PERSON | 42 | 42 | 0 |
| POLITICAL_CASE | 11 | 11 | 0 |
| POSTAL_CODE | 17 | 17 | 0 |
| SEXUAL_ORIENTATION | 6 | 6 | 0 |

Validator: `python3.12 tools/validate_labels.py data/gold/batch_g_gold.jsonl --config
configs/config.yaml` → `violations: 0`, exit 0.
