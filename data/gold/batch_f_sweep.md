# Batch F Recall Sweep Log

Starting spans (annotator1): 460
Final spans (gold): 466
Added: 6
Removed: 0

## Additions forced by rule change (1): widened B14 (basic welfare needs)

3 additions. The annotator had already extended B14 on their own initiative to cover
shelter, exercise, social contact and grooming in most places (see e.g. F005, F011, F015,
F017 where "stell", "ly", "mosjon", "sosial kontakt" deprivations were already tagged
HEALTH_INFO before this sweep). The widened rule adds "basic care" (omsorg/pleie) as an
explicit basic need on top of "stell", which the annotator's own extension had not
consistently reached. Two of the three additions below are that specific gap; the third
is a same-fact restatement (B6) that follows once the first is recognized as taggable.

- **F003** HEALTH_INFO `ikke får den omsorgen de trenger`
  (from "...virker det som om hestene ikke får den omsorgen de trenger.") -- "omsorg" (care)
  is explicitly listed among B14's basic needs ("grooming and basic care (stell)"); the
  spec's own HEALTH_INFO include-list already cites `mangle tilstrekkelig bevegelse,
  stimulering og omsorg` as a positive B14 example, so this is squarely inside the rule.
- **F005** HEALTH_INFO `hun ikke får optimal pleie og omsorg`
  (from "Hennes generelle tilstand tyder på at hun ikke får optimal pleie og omsorg.") --
  same basic-care ("stell"/omsorg) deprivation, distinct wording from the two other
  confinement/exercise restatements in the same document that were already tagged.
- **F005** HEALTH_INFO `hun tilbringer det aller meste av sin tid der`
  (from "...men det er tydelig at hun tilbringer det aller meste av sin tid der.") -- this
  is a B6 restatement: the same confinement fact (denial of exercise/social contact) is
  stated a total of three times in this document; the annotator tagged the second and
  third restatements (`svært begrenset tilgang til lek og mosjon`, `tilbringer nesten hele
  dagen, hver dag, alene i buret`) but missed this, the first and mildest-worded, instance.

No spans needed to be REMOVED for the widened B14 rule -- the annotator had not
over-tagged any pure cleanliness/structure findings. Spot-checked every occurrence of
`hygiene`, `renhold`, `omsorg`, `pleie`, `stell`, `ly`, `beskyttelse mot`, `vær og vind`,
`mosjon`, `sosial kontakt`, `isolert` across all 18 documents; all cleanliness/structural
findings (e.g. F001/F004/F006/F014's "Mangelfull hygiene i produksjonslokalene" family,
F002/F010/F018's "renhold"/"skitten" enclosure descriptions) were already correctly left
untagged, matching the task's explicit "still untagged" list.

One borderline case was deliberately NOT added: F011's
`jeg er usikker på om det gir god nok beskyttelse mot vær og vind` -- this is the shelter
need from B14, but the informant explicitly hedges it as uncertain ("jeg er usikker på
om"), unlike the spec's own definitive example (`Burene har ingen beskyttelse mot vær og
vind`). Treated as an unresolved finding, not a stated deprivation, and left untagged
under B15's logic that only an incriminating (asserted) absence is tagged.

## Additions forced by rule change (2): FAMILY_RELATION no longer covers non-kinship ties

**Zero removals required.** Grepped every FAMILY_RELATION span in the batch for
`nabo`/`venn`/`kolleg`: none exist. The annotator never tagged a neighbour/friend/colleague
tie as FAMILY_RELATION in this batch, so this rule change has no effect on batch F's gold
file. (The one case that superficially resembles the pattern, F009's
`utenomekteskelig forhold til en mannlig nabo`, was correctly tagged SEXUAL_ORIENTATION --
not FAMILY_RELATION -- because the male affair-partner's gender combined with the subject's
stated `heterofil` self-identification is itself the disclosed orientation-relevant fact;
the neighbour relationship is incidental, not the basis for the tag.)

## Genuine annotator misses (not rule-change-related)

3 additions.

- **F002** CRIMINAL_RECORD `vanskjøtsel av dyr`
  (from "Tilsynet ble gjennomført etter mistanke om økonomisk kriminalitet, vanskjøtsel av
  dyr, og manipulering av tidligere inspeksjonsresultater.") -- this is the middle item of
  a three-item list under one "mistanke om" scope; the annotator tagged the first item
  (`mistanke om økonomisk kriminalitet`) and the third (`manipulering av tidligere
  inspeksjonsresultater`) as CRIMINAL_RECORD but skipped the middle one, which is
  structurally identical and is itself a suspected animal-welfare-law offense.
- **F009** CRIMINAL_RECORD `betydelige avvik mellom rapporterte fangstmengder og inntekter`
  (from "...avdekket Mattilsynet betydelige avvik mellom rapporterte fangstmengder og
  inntekter i Fiskeriselskapet Havbris AS...") -- a straightforward B6 restatement miss:
  the document restates this same discrepancy later, word-for-word differently, in the
  observation bullet (`Uoverensstemmelser mellom rapporterte fangstmengder og inntekter`),
  and that restatement WAS tagged CRIMINAL_RECORD. The original, earlier statement of the
  same fact was missed.
- **F014** EMPLOYMENT_INFO `tidligere inspektør`
  (from "...innrømmet å ha bestukket en tidligere inspektør, Peder Ås
  (fødselsnummer 12036811223)...") -- a bare occupation/role noun identifying a specific
  named individual's real former job (Mattilsynet inspector), directly analogous to the
  spec's own `Senterets leder, Solveig Berg` pattern where the role word gets its own
  EMPLOYMENT_INFO tag even though it's excluded from the PERSON span. This was the only
  instance of a comma-attached role-appositive preceding a PERSON span that lacked its own
  EMPLOYMENT_INFO tag; checked systematically across all 18 documents' PERSON spans.

## Documents with no changes (12 of 18)

F001, F004, F006, F007, F008, F010, F012, F013, F015, F016, F017, F018 -- reviewed in full
against every category in the sweep checklist (identifiers, dates including B13-nested
years, HEALTH_INFO/B14, employment, family relations, criminal record outcomes/
restatements, B6 restatements, political/orientation/financial facts); no additions or
removals identified. These documents were already thorough, including correct handling of
non-trivial spec points: B4 non-absorbed parentheticals (F013), the domestic-violence
CRIMINAL_RECORD > FAMILY_RELATION precedence with PERSON still nested (F014's `vold mot
sin ekskone, Astrid Nilsen`), the affair+orientation combination exception (F009), and
reassuring/negative findings correctly left untagged (B15, multiple docs).

## Per-type final counts (gold)

PERSON 46, DATE_TIME 34, HEALTH_INFO 114, GOV_ID 52, NO_ADDRESS 21, CRIMINAL_RECORD 57,
POSTAL_CODE 18, NO_PHONE_NUMBER 17, EMAIL_ADDRESS 16, FAMILY_RELATION 22,
EMPLOYMENT_INFO 18, POLITICAL_CASE 11, SEXUAL_ORIENTATION 8, FINANCIAL_INFO 11,
BEHAVIORAL_PATTERN 12, ECONOMIC_STATUS 9. Total: 466.

## Validation

`python3.12 tools/validate_labels.py data/gold/batch_f_gold.jsonl --config configs/config.yaml`
-> `violations: 0`, exit 0, 466 labeled spans, 18 records, 0 malformed lines, 0 conflicting
duplicate docs.
