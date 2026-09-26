# Batch O recall sweep

Reviewer pass over `batch_o_annotator1.jsonl` (429 spans, 18 docs) against
`docs/ANNOTATION_SPEC.md` (B1-B20). Output: `batch_o_gold.jsonl` (430 spans).
Full read of all 18 source documents against the existing annotations,
line-by-line, plus targeted greps for every B20 field-label family, every
`Vi har observert:` / `Mattilsynet vurderer det slik:` block, every kinship
noun, and every `økonom*` occurrence (for the ECONOMIC_STATUS check).

## B20 (new rule) — REMOVE: private-issuer IDs wrongly tagged GOV_ID (3 spans)

- **O010** `GOV_ID` remove `Lån-4738291` — a DNB loan reference
  ("misligholdte lån til DNB (referansenummer Lån-4738291)"). DNB is a
  private bank; B20 explicitly excludes `lånenummer`. Was nested inside a
  correctly-tagged FINANCIAL_INFO span but should not have carried a
  separate GOV_ID tag.
- **O010** `GOV_ID` remove `123456-7890` — a Lindorff debt-collection case
  ID ("inkassosaker hos Lindorff (sak ID 123456-7890)"). Lindorff is a
  private collections agency, not a public authority; same B20 issuer test
  as `lånenummer`/`medlemsnummer`.
- **O016** `GOV_ID` remove `HN1234567` — "pasientjournal Helse Nord ID:
  HN1234567", a hospital record number. Task-specified forced removal:
  hospital-issued, same footing as O005's untagged `pasientjournal
  referanse HUH-2021-12345` and O010's untagged `journalnummer 2017/1234`,
  which the annotator (correctly, per B20) left untagged. O016 was the one
  inconsistent case, tagged only because it followed a literal `ID:` label.

## B20 (new rule) — ADD: state-issued IDs left untagged

None found. Checked every document for `Førerkortnummer`, `Våpenkortnummer`,
`Lisensnummer`, and generic `ID-nummer`/`Nasjonal ID` labels; none of those
field names occur anywhere in batch O. All `Fødselsnummer:`, `Org.nr.:`,
`Vår ref:`, `Deres ref:`, and attached court/police case numbers were
already tagged GOV_ID by the annotator, including the two Skatteetaten/
police-district case IDs in O016 (correctly GOV_ID — those issuers are
public authorities, unlike Lindorff/DNB above).

## ECONOMIC_STATUS verification

Checked the annotator's claim that every hardship mention in this batch
carries a NOK figure or offence word (hence zero ECONOMIC_STATUS spans).
Grepped every `sliter økonomisk`, `anstrengt økonomi`, `økonomiske
problemer` and every `økonom*` occurrence across all 18 docs (21 hits).
Every instance is one of: (a) a quantified debt/figure → FINANCIAL_INFO,
(b) a crime-framed phrase (`økonomisk kriminalitet`, `mistanke om
forfalskning`) → CRIMINAL_RECORD, (c) audit-process boilerplate
("gjennomgang av økonomisk dokumentasjon"), or (d) a denial ("Olsen
benektet kjennskap til Viks økonomiske situasjon" — B7, not a disclosure).
The one arguable case, O006's "noe han oppgir har påvirket hans
økonomiske vurderingsevne" (effect on financial *judgment*, not a
condition judgement), does not fit ECONOMIC_STATUS's "how well off are
they" test and was left alone. Claim holds — no ECONOMIC_STATUS spans
added.

## Other genuine misses — ADD (4 spans)

- **O004** `HEALTH_INFO` add `underernærte og hadde ikke tilgang til rent
  vann` — restatement (B6) of the malnutrition/water-deprivation facts
  already tagged in the main narrative (`underernærte, med synlige
  ribbein og matt pels`; `utilstrekkelig tilgang til rent vann`), appearing
  a second time, in different wording, in the `Vi har observert:` bullet.
  Tagged as one combined span per the spec's own precedent for combined
  deprivation clauses (`Utilstrekkelig fôr og vann`).
- **O005** `FAMILY_RELATION` add `sin bestefar` — "en uregistrert hagle...
  som Eriksen hevdet å ha arvet fra sin bestefar." A kinship relation
  (grandfather) between the data subject and another individual; possessive
  kept per B10.
- **O008** `CRIMINAL_RECORD` add `manglende kontroll med dyrenes
  helsetilstand` — restatement (B6), in the `Vi har observert:` bullet, of
  the falsified-documentation-about-animal-health-status fact already
  tagged in the main narrative CRIMINAL_RECORD span (which explicitly
  covers "manglende eller feilaktig informasjon om dyrenes helsetilstand
  og vaksinasjonsstatus"). It sits in the same bulleted violation list as
  two already-tagged neighbours (`Forfalskning av veterinærdokumentasjon`,
  `brudd på dyrehelseforskriften...`).
- **O009** `CRIMINAL_RECORD` add `Diskrepans mellom rapporterte fangster og
  omsetningstall` — restatement (B6) of the underreporting/fraud suspicion
  already stated in the main narrative, in the `Vi har observert:` bullet.
  Directly parallel to O006's `Uoverensstemmelser mellom deklarert fangst
  og faktisk levert kvantum, samt manipulerte regnskapsbilag`, which the
  annotator did tag in the identical document template. The list's third
  item in the same bullet, `manglende dokumentasjon for utgifter`, was
  left untagged — consistent with O010's parallel, also-untagged
  `Mangelfull dokumentasjon av produktenes innhold og opprinnelse`
  (administrative/procedural, not itself an offence-bearing finding).

## Confirmed correct (no action) — spot checks worth recording

- O005 `pasientjournal referanse HUH-2021-12345` and O010 `journalnummer
  2017/1234` — already correctly left untagged under B20.
- O017 `medlem av "Norges Frie Planteimportører"` — correctly untagged;
  this is the spec's own named example of a fictional trade name with no
  political content.
- All `Referanse:` fields (O001, O003, O007, O011-O014) — correctly
  untagged per B20's explicit carve-out.
- Every `Mattilsynet vurderer det slik:` block across all 18 docs is
  generic evaluative boilerplate with no new fact; none needed tagging.
- `tools/check_coverage.py` flagged one candidate, `Private individual`
  (O005's `Org.nr.: N/A (Private individual)`). Ruled not a defect: B19
  explicitly excludes placeholder values (`Privatperson`, `N/A`, etc.)
  from EMPLOYMENT_INFO.
