# Batch V recall sweep log

Reviewer pass over `batch_v_annotator1.jsonl` (518 spans, 18 docs), targeted at
BEHAVIORAL_PATTERN (flagged at 0.22 spans/doc vs. a 0.59 gold mean) plus a full
B1–B20 sweep. Output: `batch_v_gold.jsonl` (529 spans).

## Template mix — V is dossier-heavy, and that explains the three "high" types

14 of 18 documents are `Inspeksjonsrapport med skriftlig veiledning` dossiers;
only 4 (V002, V007, V012, V016) are interview transcripts carrying the
`-- Hvilket dyr er du bekymret for` / `-- Hvordan ser dyrene ut` markers. That is
78% dossier against a corpus split of roughly 51/49 (16,537 interview vs. 15,902
dossier per the spec's own HEALTH_INFO note).

This single fact accounts for all three elevated rates at once, and none of them
is an over-tagging defect:

- **GOV_ID 4.00 vs. 2.91** — every dossier carries `Vår ref` + `Deres ref` +
  `Org.nr` + a fødselsnummer, and most add one or two court case numbers. All 72
  were re-checked against B20; see below. No additions, no removals.
- **SEXUAL_ORIENTATION 0.72 vs. 0.45** — the dossier template has a fixed
  orientation-disclosure slot (`åpent homofil`, `lesbisk forhold med …`,
  `identifiserer seg som heterofil`). 13 spans in 14 dossiers is one per document,
  not inflation.
- **POLITICAL_CASE 1.00 vs. 0.69** — same template slot (party membership, often
  plus a stated opinion span, which B12/POLITICAL_CASE's own worked example says
  is a second adjacent span).

Per the batch direction, this makes the low BEHAVIORAL_PATTERN rate *more*
suspicious, since conduct sits in dossiers. It was therefore worked directly.

## Verdict on BEHAVIORAL_PATTERN — mostly a real property of this draw, two genuine defects

Every document was read for conduct clauses, and a keyword sweep was run over the
batch for the type's whole vocabulary (aggresjon, rope/skrike, trusler, nekte/
samarbeide, beruselse, støy, gjentatte/stadig/ofte/jevnlig, unnlate, tilbakeholde,
fortie, manipulere, motstand). The sweep returned 18 contexts; 16 of them were
already tagged correctly under another type (CRIMINAL_RECORD for the offence
clauses, HEALTH_INFO for `rusmisbruk`) or are witness-own-behaviour, which the
type's Exclude list removes (`Jeg går tur i området jevnlig` in V012 and V016).

The conduct simply is not there at normal density: V's dossiers are
financial-crime and identity dossiers (forfalskning, bedrageri, skatteunndragelse,
våpen), not aggression/neglect dossiers. Twelve of the eighteen documents contain
no human-conduct clause at all.

Two real defects were found, and both are exactly the B18 failure mode the
direction predicted — an annotator applying B1 mechanically to this type:

- **V007, boundary (B18).** `hissig temperament` → `Leif Gustavsen er kjent for å
  ha et hissig temperament`. B1 was applied and the subject dropped, leaving a
  bare characteristic noun phrase with no actor — which the type's own Exclude
  bullet rejects (`aggressiv` alone) and B18 explicitly exempts from B1. The
  actor is named in the clause, so the span starts there.
- **V011, type migration.** `gjentatte ganger unnlatt å implementere nødvendige
  tiltak for å sikre tilfredsstillende hygienestandard` moved
  CRIMINAL_RECORD → BEHAVIORAL_PATTERN. There is no legal-process verb and no
  offence noun anywhere in the clause; it is a named principal's repeated
  non-compliance with an explicit frequency marker, which is the type's core
  case and CRIMINAL_RECORD §Overlap 3's stated tie-break ("a bare description of
  conduct with no such language stays BEHAVIORAL_PATTERN"). Boundary left as the
  annotator drew it: the named subject is separated from the predicate by a
  fødselsnummer parenthetical and a conviction clause, so B18's "earliest word
  that establishes the actor" cannot be reached contiguously.

Net effect: 4 → 5 spans, 0.28/doc. Still about half the gold mean, and on the
evidence that is the draw, not the annotator.

## Additions, grouped by rule

### Settled convention 2 — overcrowding / cramped space is HEALTH_INFO (B14, exercise)
- V003 `overbefolkning i flere av bur og rom` — the annotator tagged the two
  sibling findings in the same sentence (`utilstrekkelig fôr`, and separately the
  hygiene finding correctly left untagged) but dropped the overcrowding one.
- V005 `holdes i et for lite anlegg` — kept `holdes`, which is not on B1's
  drop-list and carries the fact. The coordinated `manglende berikelse` was
  already tagged.
- V010 `utilstrekkelig plass` — sits between `mangelfulle sanitærforhold`
  (structural, correctly untagged) and `manglende tilgang til artstilpasset fôr
  og miljøberikelse` (tagged); only the middle item was missed.

### B6 — restatement in the `Vi har observert:` list, missed
- V005 `mangler tilstrekkelig berikelse` — HEALTH_INFO. The prose form
  (`manglende berikelse`) was tagged; the bullet restatement is a different
  string and is its own span.
- V009 `Import og salg av kosmetikkprodukter som inneholder hydrokinon og
  kvikksølv` — CRIMINAL_RECORD. The lowercase prose form was tagged; the
  capital-I bullet restatement was not. V001 and V008, which use the same
  template sentence, both have the pair tagged — V009 is the odd one out.
- V015 `Manipulerte regnskapstall og uriktig rapportering av inntekter` —
  CRIMINAL_RECORD, the bullet restatement of the tagged
  `systematisk forfalskning av regnskap …`.
- V015 `Høy gjeld og misligholdte lån` — FINANCIAL_INFO. `misligholdte lån` is a
  named debt instrument on FINANCIAL_INFO's own Include list, so this stays
  FINANCIAL_INFO rather than ECONOMIC_STATUS even with no figure attached.
- V017 `Mangelfull karantenehåndtering av importerte planter` — CRIMINAL_RECORD,
  the bullet restatement of the tagged `Klare brudd på karantenebestemmelser`.
  The bullet's other two items were already tagged; only the first was dropped.
  `spredning av *Phytophthora ramorum*` in the same bullet is plant-disease
  content with no home in the 16 types and stays untagged.

### Other single misses
- V015 `Olsens økonomiske situasjon gir grunn til bekymring` — ECONOMIC_STATUS.
  The document had zero ECONOMIC_STATUS spans; this is a pure evaluative
  judgement with no figure in it, matching the type's own positive example
  `bekymret for eierens økonomiske situasjon`. B17 keeps the subject, since the
  fact-bearing noun phrase *is* the subject here.
- V016 `gradvis forverret seg` — HEALTH_INFO. An animal-condition statement
  (deterioration over weeks) in an otherwise well-covered document; B1 drops
  `Tilstanden deres har`.
- V017 `sønn: Magnus Hansen` — FAMILY_RELATION. Only the downstream
  `sin sønns fremtid` was tagged; the kinship statement itself
  (`sønn: Magnus Hansen, f. 19.02.2008`) had no FAMILY_RELATION span, though
  `Magnus Hansen` was already PERSON and `19.02.2008` already DATE_TIME.
  Boundary follows FAMILY_RELATION's `partner: Kjell Ivar Hansen` precedent
  (label-colon included, stop before the B4 date parenthetical).

## Removals
- V007 BEHAVIORAL_PATTERN `hissig temperament` (replaced, see above).
- V011 CRIMINAL_RECORD `gjentatte ganger unnlatt …` (migrated, see above).

No span was removed for being wrong-in-substance; both removals are halves of a
replacement.

## Settled conventions, verified across the batch

1. **Single-token PERSON.** The four flagged spans (V006 `Magnus`, V006 `Mia`,
   V015 `Ida`, V015 `Markus`) are standalone given names of children who never
   appear with a surname in their document. Left. No further single-token PERSON
   spans were added, and no bare surname (`Krogstad`, `Berglund`, `Olsen`,
   `Halvorsen`) was tagged anywhere.
2. **Overcrowding / cramped space is HEALTH_INFO.** Three misses found and added;
   see the Additions section above.
3. **Dirty / unavailable water.** V003 `utilstrekkelig tilgang til rent vann`,
   V012 `ikke sett noen mat- eller vannskåler`, V016 `ingen synlig vannkilde` —
   all already tagged HEALTH_INFO. Nothing to add.
4. **Missing heat/UV lamps for reptiles.** No document in V contains a
   varmelampe/terrarium heating finding. V010 holds reptiles but the finding is
   space/feed/enrichment, not heat. Zero changes forced.
5. **B20 — issuer test.** Grepped the batch for every identifier label stem.
   Three private-body identifiers confirmed correctly untagged:
   V003 `journalnr. 1234567890` (hospital record), V005 `serienummer: AB12345`
   and V018 `våpennummer ABC123` (manufacturer's serial on the weapon, as
   distinct from the state-issued card). `Referanse: NNNNNN` untagged in all four
   interviews. `Deres ref` tagged GOV_ID wherever populated
   (`HTB/2024/03`, `BH/2023-10-26`, `AK/2023-10-26`, `PGH-2023-10-26`,
   `BH/2023-09-14`, `BH/2024-03-15`) and untagged wherever the value is a
   placeholder (`(None provided)`, `(blank)`, `(Left blank for recipient to
   fill)`). V015 `SF-4278` under `reg.nr.` is a state fishing-vessel registration
   and stays GOV_ID. No B20 change was required anywhere.
6. **B19 (tightened).** Every EMPLOYMENT_INFO company span in the batch sits in a
   document that names the business's owner/innehaver/daglig leder, so all 9 hold.
   V004's `Org.nr.: 923 567 890 (Fictitious organization number)` parenthetical is
   a placeholder note, not a company, and stays untagged — this is
   `check_coverage.py`'s only candidate and it is correctly left flagged.

## Reviewed, deliberately not changed

- **V002 / V007 "activity from the property" clauses.** V002's
  `har observert mye urolig aktivitet i leiligheten` and `mye støy og
  uregelmessig aktivitet fra leiligheten`, and V007's `Naboer har tidligere
  klaget på støy og mistenkelig aktivitet på eiendommen`, are the closest
  remaining BEHAVIORAL_PATTERN candidates. All three were left untagged: the
  grammatical subject in each is the witness or the neighbours, no human actor
  appears inside the clause, and B18 requires the span to show *who* performs the
  pattern. These sit squarely in the spec's own 9.8% "ambiguous — route to manual
  review, do not auto-drop or auto-include" bucket, so a sweep should not force
  them either way. Flagging for a human ruling.
- **V005 / V006 `Til tross for gjentatte pålegg om forbedringer, observer(t)e …
  fortsatt alvorlige mangler`.** A near-match for the type's Include example
  `resistant to previous guidance and exhibits a pattern of non-compliance`, but
  the grammatical subject is Mattilsynet and the predicate states deficiencies
  observed, not conduct performed. Left untagged in both, for consistency with
  each other.
- **V008 `hevdet å være uvitende om forbudet, til tross for tidligere advarsler
  fra Mattilsynet`.** Evasiveness with an authority, but the head verb `hevdet`
  is a reporting/self-report verb that Global rule 3 cuts, and what survives the
  cut is a knowledge claim rather than an action. Left.
- **V013 `Eriksens manglende åpenhet om sin kriminelle fortid` and V018
  `bevisst har tilbakeholdt opplysninger om sin kriminelle fortid, inkludert
  økonomisk kriminalitet og voldsepisoder` / `Bjørnar Halvorsens tilbakeholdelse
  av opplysninger og kriminelle fortid`.** All three read naturally as
  BEHAVIORAL_PATTERN ("deceptive conduct" is in the type's definition), and I
  considered migrating them. They were left CRIMINAL_RECORD because each clause
  names offence content (`kriminelle fortid`, `økonomisk kriminalitet`,
  `voldsepisoder`) and CRIMINAL_RECORD §Overlap 3 gives CRIMINAL_RECORD the
  clause whenever a named offence is present. Migrating them would have lifted
  BEHAVIORAL_PATTERN to 0.44/doc, which is precisely why I did not do it on a
  rate argument.
- **V003 `inndratt i 2020 etter en hendelse med trusler mot en nabo (politisak nr.
  2020/10-1212-BV)`.** CRIMINAL_RECORD's Resolved-conflicts list has a very close
  parallel (`våpenbeslag hos Hansen i 2018 etter en episode med trusler mot en
  nabo` → **split** into two spans). Left merged: splitting would also require
  re-deciding the head boundary (B1 drops `Hans våpentillatelse ble`, leaving a
  span that no longer says what was revoked, while B17 argues for keeping it), and
  that is a boundary question a reviewer should not settle unilaterally. Flagging.
- **V005 `stereotyp atferd` / `stereotyp atferd, som pacing og overdreven
  slikking` as HEALTH_INFO.** The spec contradicts itself here (see below). Left
  as HEALTH_INFO.
- **V004 `tegn på parvovirus og kennelhoste`** as one span rather than split per
  B11 — two diseases conjoined by `og`. Left; the reading as a single observation
  is defensible and the split would be cosmetic.
- **V014 / V015 FAMILY_RELATION `to barn med`** (trailing preposition). Left; the
  annotator is internally consistent and B9 governs punctuation, not a dangling
  preposition.
- **`lite vegetasjon` (V012, V016).** Arguably food deprivation under B14, on the
  same footing as the tagged precedent `lite skygge`. Left untagged: in both
  documents the food-deprivation fact is already carried by explicit spans
  (`uten tilgang til ly, mat eller vann`, `ikke sett noen forautomater …`,
  `uten tilstrekkelig for i lengre tid`), and the clause as written describes the
  pasture rather than the animals' access.
- **Commercial hygiene findings** in V004, V006, V008, V011, V013, V014, V018
  (`Mangelfull håndhygiene`, `Spor av skadedyr`, `synlig muggvekst på
  kjøkkenbenken`, `Uhygieniske forhold i lagerlokalene`) — structural, untagged
  per B14's last bullet. Verified all 12 such bullets; annotator was right on all
  of them.
- **Religious affiliation** — 9 instances across the batch (`Den norske kirke` ×3,
  `Human-Etisk Forbund`, `Jesu Kristi Kirke av Siste Dagers Hellige`,
  `Jehovas vitner`, `katolikk` ×2, `pinsemenigheten` ×2, `Wicca-troen`,
  `"Guds Lys"`). All correctly untagged (Open question 17).
- **Lawful weapons** — V005 and V014 `registrert rifle`, untagged. Correct.
- **B7 refusals/denials** — V001 `nektet for å ha vært involvert i noen
  våpenrelaterte hendelser`, V001 `Fru Johansens seksuelle orientering er
  irrelevant for saken`, V008 `benektet å eie eller oppbevare våpen`. All
  correctly untagged; no orientation or weapon fact is disclosed.

## Where I think the spec is wrong

**HEALTH_INFO contradicts itself on animal stereotypy.** HEALTH_INFO's Include
bullet covers "animal physical/**behavioural**/medical condition … apathy", and
the batch's `apatiske` / `virker slappe` spans rely on it. Two bullets later its
Exclude list says `stereotyp atferd` with no diagnostic word is
"BEHAVIORAL_PATTERN, not HEALTH_INFO" — but BEHAVIORAL_PATTERN's own rule
excludes animal-subject conduct outright, so an animal's stereotypy falls through
both types and lands nowhere. That cannot be the intent: pacing and over-grooming
in a too-small enclosure are the canonical welfare-deprivation indicators, and
B14 tags the deprivation that causes them. V005's two `stereotyp atferd` spans
were left as HEALTH_INFO on that reading. The Exclude bullet should be narrowed
to human/owner subjects, where it makes sense, rather than stated flatly.

**B18 is internally inconsistent about the subject.** B18 says the type "keeps its
subject", but three of the type's five positive examples carry no subject at all
(`rope på hunden aggressivt flere ganger`, `kaste tomflasker og stein etter
hundene`, `nektet å samarbeide med inspektørene og fremviste aggressiv atferd`).
The workable reading — and the one applied here — is that the span must show who
performs the pattern *when the source makes that reachable contiguously*, and
must never be reduced to a subject-less bare adjective or characteristic noun.
Worth stating that way explicitly, because the mechanical reading of B18 is what
produces disagreements like V005's two spans (subject dropped) versus V007's
(subject now kept).

## Tool output

```
validate_labels.py: records 18, labeled spans 529, violations: 0, exit 0
docs 18 / total spans 529 / min spans per doc 18 (V007) / no empty output
check_coverage.py: 1 candidate (V004 'Fictitious organization number' —
  a placeholder note in the Org.nr parenthetical, correctly left untagged per B19)
```
