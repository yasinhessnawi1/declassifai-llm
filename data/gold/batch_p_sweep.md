# Batch P recall sweep log

Reviewer pass over `batch_p_annotator1.jsonl` (449 spans, 17 docs) applying B20 (new)
and a full B1–B19 recall sweep. Output: `batch_p_gold.jsonl` (458 spans).

## B20 (GOV_ID issuer test) — 0 changes forced

Checked every document for `Førerkortnummer`, `Våpenkortnummer`, `Lisensnummer`, `D-nummer`,
and any other issuer-based identifier label not already covered. None found anywhere in
the batch (grep across all 17 docs for those label stems returned zero hits beyond the
already-known cases). The three flagged private-body identifiers were re-verified against
B20 and confirmed to correctly stay **untagged**:

- P009 `våpennummer: ABC12345` — manufacturer's serial, not the state-issued card. Untagged.
- P011 `våpennummer: RIF-987654` — same reasoning. Untagged.
- P011 `pasientjournalnummer: HKL-123456789` — hospital's internal record. Untagged.
  (Flagged again by `check_coverage.py` as an `id_number` candidate; confirmed not a
  defect — B20 explicitly excludes hospital journal numbers.)

`check_coverage.py`'s second candidate, P014 `Ikke kjent` (the `Navn på dyreeier eller
virksomhet:` field value), was also reviewed: it is a placeholder ("not known"), matching
B19's exclusion list (`Privatperson`, `Ukjent`, `N/A`). Confirmed correctly untagged.

No document in this batch contains an actual state-issued card/licence number that was
missing a GOV_ID tag, so B20 required zero additions to this batch's data — every private
vs. public distinction the annotator made (or left ambiguous) already lands correctly
under B20.

## Genuine recall misses (not B20-related)

### B14 — welfare-need deprivation, restated in a different clause (P001)
- `Vannflaskene var tomme eller nesten tomme i flere av burene` — ADD HEALTH_INFO.
  Water-bottle emptiness is a direct statement of water deprivation (a basic welfare
  need); kept the noun-subject `Vannflaskene` per B17 since dropping it would erase the
  "water" component of the disclosed fact.
- `Det ser ikke ut som de får nødvendig stimuli eller plass for å utføre naturlig adferd`
  — ADD HEALTH_INFO. States deprivation of exercise/stimulation, directly matching B14's
  own example (`mangle tilstrekkelig bevegelse, stimulering og omsorg`). Kept the full
  negated clause including `Det` per B15 (negation wraps the fact; dropping the hedge
  would invert the meaning) — modeled directly on this same document's own sibling
  pattern found correctly handled in P006 (`Det ser ikke ut til å være noen form for ly
  eller skjul for dyrene`, kept whole) and P004 (`ikke eieren er i stand til å gi dem den
  omsorgen de trenger`, kept whole).

### B14 — same pattern, second document (P012)
- `lider av mangel på renslighet og trivsel` — ADD HEALTH_INFO. Second clause of "de ikke
  får tilstrekkelig tilsyn og veterinærbehandling, og at de lider av mangel på renslighet
  og trivsel" was split off per B11 (one clause, one fact) but only the first half had
  been tagged. `renslighet` (basic grooming/care) is an explicit B14 welfare need; kept
  the verb `lider av` per B1's keep-list.

### B6 — restatement missed entirely (P003)
- `voldsanmeldelsen` — ADD CRIMINAL_RECORD. "Han oppga ingen personlige skandaler utover
  voldsanmeldelsen" restates the earlier-tagged assault report as a bare compound noun;
  matches the bare-offense-noun rule (`fyllekjøring` precedent) and B6's restatement
  principle.

### B3/B11 — an entire sentence with two convictions and an amount, missed (P007)
- `tidligere blitt dømt for skattesvindel` — ADD CRIMINAL_RECORD (kept `blitt` for
  verbatim contiguity; verb chain carries the fact).
- `besittelse av ulovlige våpen` — ADD CRIMINAL_RECORD, second conviction split off per
  B11 (`... og besittelse av ulovlige våpen (2018)`), same pattern as the spec's own
  `diagnostisert med diabetes type 2 og kronisk depresjon` split example.
- `2015`, `2018` — ADD DATE_TIME each, nested per B13; both years sat in parentheses
  directly after each offense, per B4 not absorbed into the CRIMINAL_RECORD span.
- `gjeld på over 700 000 NOK, primært kredittkortgjeld og ubetalte skatter` — ADD
  FINANCIAL_INFO. Entire sentence ("Hun oppga å ha gjeld...") had no FINANCIAL_INFO tag
  in the whole document; itemised debt clause kept as one span per B11.

## Reviewed, no change (selected high-risk checks that came back clean)

- All NO_ADDRESS/POSTAL_CODE field-conditioned nesting pairs (Adresse vs. standalone
  Poststed/Postnummer fields) — correct in every document.
- All hedged/suspected criminal allegations (`mistanke om`, `mistenker`) — already tagged.
- All CRIMINAL_RECORD × FAMILY_RELATION precedence cases (`vold i nære relasjoner`,
  `vold mot sin kone/ekskone`) — correctly CRIMINAL_RECORD-only, no stray FAMILY_RELATION.
- All lawful/registered-weapon mentions with no illegality asserted — correctly untagged.
- P001's `Dyrebutikken Zoogle` (EMPLOYMENT_INFO, B19) and P014's `Ikke kjent (Gateartist)`
  — confirmed correct per the batch note, left as-is.
- P012's `Den konstante støyen tyder på frustrasjon og kjedsomhet` — considered and
  **not** added: an inferential/evaluative conclusion about the animals' emotional state
  (behavioural, not medical), distinguishable from P016's `tyder på ... store smerter`
  (pain, unambiguously medical) which the annotator correctly did tag.

## Tool output

```
validate_labels.py: violations: 0, exit 0
check_coverage.py: 2 candidates (both reviewed above, both correctly left untagged)
```
