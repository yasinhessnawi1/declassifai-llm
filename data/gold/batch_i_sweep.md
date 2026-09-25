# Batch I Recall Sweep Log

Reviewer pass over `batch_i_annotator1.jsonl` (16 docs, 396 spans) against
`docs/ANNOTATION_SPEC.md` plus the three post-annotation rule changes (B17 completeness,
B18 confirmation, gambling routing). Final output: `batch_i_gold.jsonl`, 410 spans,
validator: `violations: 0`.

Net change: **+14 spans** (14 additions, 2 boundary fixes [net 0 count change], 2 type
retypes [net 0 count change, cross-type shift]).

---

## 1. Gambling routing retypes (forced by rule change (3))

Two spans mixed a quantified NOK amount with a gambling-loss frame. General precedence
(any NOK amount -> FINANCIAL_INFO) would keep these as FINANCIAL_INFO, but the project
owner's gambling ruling explicitly carves out "an amount lost" to gambling as
ECONOMIC_STATUS (the financial-outcome/habit framing test), overriding the general
numeric rule for this one scenario.

- **I004** RETYPE FINANCIAL_INFO -> ECONOMIC_STATUS:
  `gjeldsproblemer på over 700 000 NOK, primært relatert til spillegjeld`
- **I011** RETYPE FINANCIAL_INFO -> ECONOMIC_STATUS:
  `currently struggling with debt exceeding 550,000 NOK due to gambling debts and failed investments`

No BEHAVIORAL_PATTERN-framed gambling spans (e.g. `spiller bort pengene sine ukentlig`)
or clinical-diagnosis gambling spans were found anywhere in batch I, so no other gambling
retypes were needed.

## 2. B17 / B18 audit (no forced changes)

The annotator had already anticipated B17 and applied it correctly and consistently:
`Mangel på mosjon` (I005), `Mangelen på tilstrekkelig beite, ly og vann` (I006),
`Mangelen på tilsynelatende rent drikkevann og fôr` (I016), `Funn av uregistrerte
skytevåpen i Olsens private bolig i 2019` (I001) all correctly keep the nominalised-fact
subject and drop only the evaluative tail. No B17 fixes were required anywhere in the
batch.

B18 (BEHAVIORAL_PATTERN keeps its subject) was likewise already applied correctly and
matches the spec's own worked examples verbatim in places: `har flere ganger hørt eieren
rope og skrike til hundene...` (I008), `Har observert aggressiv atferd fra eieren
tidligere` (I012), `har ved flere anledninger sett eieren kaste gjenstander...` (I012),
`Hoarding-tendensene til eieren ser ut til å ha eskalert` (I015). No B18 fixes were
required.

## 3. Genuine annotator misses — additions

### Missing phone/email (never tagged in the document at all)
- **I001** ADD NO_PHONE_NUMBER `98765432` — "Telefonnummeret hans er 98765432." never tagged.
- **I001** ADD EMAIL_ADDRESS `lars.m.olsen@email.com` — "e-postadresse lars.m.olsen@email.com" never tagged.

### CRIMINAL_RECORD — bare offense noun / B6 restatement misses
- **I003** ADD `evidence of illegal animal importation` (Oppsummering sentence; bare
  offense noun is sufficient per CRIMINAL_RECORD's own rule, no accusation verb required).
- **I003** ADD `the animals were imported illegally from Brazil, bypassing required
  import permits and quarantine procedures` (B6 restatement in the "Vi har observert"
  bullet — same offense, different wording, distinct string).
- **I009** ADD `Manglende karantene for importerte planter` (B6 restatement bullet).
- **I009** ADD `Forfalsket importdokumentasjon` (B6 restatement bullet).
- **I013** ADD `den ulovlige våpenoppbevaringen` (B6 restatement — third, distinctly
  worded restatement of the same illegal-weapon-storage fact already covered by two
  other spans in the doc).

### HEALTH_INFO — B14 welfare-deprivation misses and B6 restatements
- **I003** ADD `a lack of appropriate care for the animals` (B14 basic-care/`stell`
  deprivation, nominalised-fact clause from the Oppsummering sentence).
- **I003** ADD `insufficient food and water` (B14 food/water deprivation, restated in
  the "Vi har observert" bullet).
- **I016** ADD `nesten ingen tørre områder` (B14 shelter/dry-resting-area deprivation;
  restates the same mud/no-shelter condition tagged later in the doc as "...uten tilgang
  til tørre liggeplasser eller ly").
- **I016** ADD `dekket av tykk, våt gjørme` (same sentence, second clause per
  one-clause-one-fact; B14 shelter deprivation).

### FAMILY_RELATION — utroskap/infidelity misses
- **I010** ADD `hans engasjement i en utroskapsskandale som ble omtalt i lokalavisen
  "Bergens Tidende" i juni 2023` — infidelity defaults to FAMILY_RELATION per spec; never
  tagged, entire fact skipped.
- **I011** ADD `allegations of infidelity` — second fact in a parenthetical whose other
  half ("a restraining order filed by Hansen") was already correctly tagged CRIMINAL_RECORD;
  the infidelity half was dropped.

### POLITICAL_CASE — presence miss
- **I013** ADD `aktiv i det politiske partiet "Frihetspartiet"` — full membership clause
  with quoted party name never tagged; POLITICAL_CASE was entirely absent from this doc's
  output despite the clause being present in the source.

## 4. Genuine annotator misses — boundary fixes (under-trimmed spans)

- **I008** FIX HEALTH_INFO `utilpasse` -> `generelt utilpasse` — B1 keeps a leading
  intensifying adverb on the retained predicate (direct analogy to the spec's own
  `Øynene virker litt sunkne` -> `litt sunkne` worked example); only the linking verb
  "virker" should have been dropped, not the adverb "generelt".
- **I014** FIX HEALTH_INFO `bluetongue` -> `viste tegn på bluetongue` — the hedge "viste
  tegn på" (showed signs of) is part of the clause per the same rule that keeps "mistanke
  om"/"tegn på" hedges, and this exact document already applies it correctly elsewhere
  ("uregelmessigheter... som tyder på skatteunndragelse" keeps "tyder på"); the identical
  construction in I006 ("Sauene viser klare tegn på sykdom" -> "viser klare tegn på
  sykdom") confirms the pattern this span under-trimmed.

## 5. Spans reviewed and left unchanged (flagged, not forced)

A few borderline calls were reviewed and deliberately left as the annotator had them,
since none is a clear spec violation:

- **I007**: `en bot på 250 000 NOK` (a Mattilsynet-imposed fine) — left untagged. It's a
  quantified amount, but it reads as part of the agency's own future decision/vedtak
  paragraph rather than a personal financial fact about the data subject's own economic
  condition. Genuinely ambiguous; spec has no worked example for a regulator-imposed fine.
- **I005 / I012**: several premises-condition clauses (damp/dark/poorly-ventilated
  basement, "generelle forholdene i hagen") were left untagged as structural, since
  darkness/ventilation/general "conditions" are not among B14's seven enumerated basic
  welfare needs (food, water, vet care, shelter/weather, grooming/stell, exercise, social
  contact).
- **I014**: "Transport av sauer med bluetongue." (a further restatement bullet) was not
  given its own separate list entry, since the bare string "bluetongue" is already a
  substring of the corrected HEALTH_INFO span from the same document and the output
  format has no positional tracking — adding a duplicate string would be a no-op.

## Totals

| Metric | Count |
|---|---|
| Starting spans (annotator1) | 396 |
| Added | 14 |
| Fixed (boundary, net 0 count change) | 2 |
| Retyped (gambling routing, net 0 count change) | 2 |
| Removed | 0 |
| Final total | 410 |

**Forced by the three rule changes:** 2 (both gambling retypes — I004, I011). No B17 or
B18 fixes were needed; the annotator had already applied both correctly and consistently
across all 16 documents.

**Genuine annotator misses:** 16 (14 additions + 2 boundary fixes).

Per-type counts (before -> after):

| Type | Before | After |
|---|---|---|
| PERSON | 44 | 44 |
| DATE_TIME | 42 | 42 |
| GOV_ID | 40 | 40 |
| NO_ADDRESS | 21 | 21 |
| POSTAL_CODE | 16 | 16 |
| NO_PHONE_NUMBER | 13 | 14 |
| EMAIL_ADDRESS | 13 | 14 |
| CRIMINAL_RECORD | 44 | 49 |
| FINANCIAL_INFO | 9 | 7 |
| ECONOMIC_STATUS | 8 | 10 |
| HEALTH_INFO | 73 | 77 |
| FAMILY_RELATION | 21 | 23 |
| EMPLOYMENT_INFO | 28 | 28 |
| POLITICAL_CASE | 10 | 11 |
| SEXUAL_ORIENTATION | 6 | 6 |
| BEHAVIORAL_PATTERN | 8 | 8 |
| **Total** | **396** | **410** |

Validator: `records: 16, malformed JSON lines: 0, labeled spans: 410, docs w/ conflicting
dupes: 0, violations: 0` — exit 0.
