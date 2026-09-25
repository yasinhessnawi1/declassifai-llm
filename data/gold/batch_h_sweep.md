# Batch H recall sweep log

Reviewer pass over `batch_h_annotator1.jsonl` (16 documents, 434 spans) against
`docs/ANNOTATION_SPEC.md`, applying the three post-annotation rule changes (B17,
B18, gambling routing) and sweeping for missed spans per the categories in the task
brief. Starting count 434, final count 444 (net +10).

## 1. Rule-forced fixes (B17 / B18 / gambling)

### B17 — subject-is-the-fact over-trims (2 found, both fixed)

- **H005** — HEALTH_INFO. Source: "Ulvene er undervektige og viser tegn på
  underernæring. **Fôrmengden er utilstrekkelig.**" Annotator tagged the bare
  predicate `utilstrekkelig` (dropping the subject "Fôrmengden" by analogy to B1).
  Under B17 this is over-trimmed: `utilstrekkelig` alone doesn't say what is
  insufficient (parallel to `ulovlig`/`en bekymring` in the spec's own worked
  examples — the predicate carries no fact on its own). Unlike the canonical B17
  examples (`Mangel på mosjon`, `Oppbevaring av uregistrert våpen`), the subject
  "Fôrmengden" is not itself a nominalised-negative noun phrase, so dropping the
  verb too (as in the `Mangel på mosjon` fix) would leave an equally empty
  "Fôrmengden" alone. Kept the whole minimal clause instead.
  - REMOVE: `utilstrekkelig`
  - ADD: `Fôrmengden er utilstrekkelig`

- **H010** — ECONOMIC_STATUS. This is the exact case flagged in the task brief's
  NOTE: "Edvardsens økonomiske situasjon **synes** uoversiktlig, med gjeld på over
  700 000 NOK..." Annotator dropped `synes` as a hedge (by analogy to `virker`) and
  tagged only `uoversiktlig`. Per B17 the fact-bearing subject is "Edvardsens
  økonomiske situasjon" (the predicate alone doesn't name the domain — "unclear"
  could describe anything). Fixed per the NOTE's explicit instruction.
  - REMOVE: `uoversiktlig`
  - ADD: `Edvardsens økonomiske situasjon`

No other bare post-hedge adjectives (`ulovlig`, `en bekymring`, and all `virker`/
`synes`/`fremstår` occurrences) were found needing this fix — checked every
occurrence of `synes`, `fremstår`, `virker`, `utilstrekkelig` across all 16 docs;
every other instance already retains enough of the noun phrase to state the fact on
its own (e.g. `Fôrmengden`'s siblings like "Reinsdyrenes beiteområde er for lite og
mangler naturlig vegetasjon" → `for lite og mangler naturlig vegetasjon` passes the
B17 test because the predicate itself names the deprivation).

### B18 — BEHAVIORAL_PATTERN keeps its subject

Checked every BEHAVIORAL_PATTERN span with a witnessing lead-in ("Har sett...",
"har ... hørt..."). All were already compliant — the annotator already kept the
witnessing clause whole in every case (e.g. H014: `har over flere uker sett Arvid
Bakken slå og sparke hundene, spesielt schæferhunden`; `har også hørt ham rope og
skjelle på dyrene på en aggressiv måte` — both kept intact, matching the spec's own
worked examples almost verbatim). **No B18 fixes were needed in this batch.**

### Gambling routing

Searched all 16 documents for gambling vocabulary (`spill`, `gambl`, etc.) — **no
gambling content exists in batch H.** No retyping was needed or possible.

## 2. Genuine annotator misses (recall gaps)

### Pattern: bare employer/company name not tagged (B12) — 5 instances

Five inspection-report ("Inspeksjonsrapport") documents name the inspected
business in a header line (an "Inspeksjonen omfattet: ... ved `<Company>`" scope
line, or a "(`<Company>`)" parenthetical next to Org.nr) that was left untagged,
even though the *same* company name, merged with a role word elsewhere in the same
document (`eier og daglig leder av X` / `innehaver av X`), *was* tagged. Two other
documents in this batch (H010's `Edvardsen Planter`, H012's `Høybakkens Spiseri`)
show the annotator does tag this bare form when a clean ownership appositive
exists elsewhere in the doc, confirming these are misses rather than a deliberate
convention. Per B12 ("A bare role word and a bare company name are each tagged on
their own" / "two legitimately different spans in two different sentences, not a
boundary conflict"), each is added once (spans are de-duplicated per type).

- H004: ADD EMPLOYMENT_INFO `Planteskolen Bergseth AS`
- H005: ADD EMPLOYMENT_INFO `Villmarken Dyrepark`
- H007: ADD EMPLOYMENT_INFO `Plantehagen AS`
- H009: ADD EMPLOYMENT_INFO `Pedersen Bakeri AS`
- H011: ADD EMPLOYMENT_INFO `Slakteri AS`

(Left alone: H013 and H016 both use a different, passive "Senteret/Menighetssenteret,
**drevet av** `<Person>`" construction with no clean eier/leder appositive anywhere
in either document — this construction is never tagged EMPLOYMENT_INFO across
either occurrence, suggesting a consistent, deliberate scope choice rather than a
miss. Flagged as an open question below rather than force-added.)

### Pattern: B6 restatement missed inside an otherwise-tagged list — 3 instances

- **H007** — BEHAVIORAL_PATTERN. The "Vi har observert:" bullet list "Importerte
  planter uten nødvendig sunnhetssertifikat, manglende karantene for importerte
  planter, **spredning av plantesykdommer**." has three comma-separated findings;
  the first two were tagged, the third was not, despite being the exact same kind
  of restatement (B6) as its neighbours.
  - ADD: `spredning av plantesykdommer`

- **H011** — FAMILY_RELATION. "Det er rapportert om en **konfliktfylt skilsmisse**
  med beskyldninger om vold i hjemmet (sak henlagt av politiet)." restates the
  earlier `skilt fra sin kone, Astrid Hansen` divorce fact in a new clause. The
  violence half was correctly tagged CRIMINAL_RECORD by precedence, but the
  divorce-restatement half (`skilsmisse` is explicitly Included under
  FAMILY_RELATION) was left untagged.
  - ADD: `konfliktfylt skilsmisse`

- **H015** — HEALTH_INFO. "Andre opplysninger: Har sett lysene på i akvariene hele
  døgnet i flere uker." is the first statement of the constant-light fact; it is
  restated and explained later ("lysene står på konstant, forstyrrer også fiskens
  naturlige døgnrytme" — already tagged). The earlier, shorter restatement was
  missed.
  - ADD: `lysene på i akvariene hele døgnet i flere uker`

### Pattern: B14 deprivation phrased as enclosure property — 1 instance

- **H001** — HEALTH_INFO. "Burene virker altfor små til at de kan bevege seg
  skikkelig." states an exercise/movement-space deprivation exactly like B14's own
  worked example ("Burene har ingen beskyttelse mot vær og vind" is tagged despite
  the enclosure being the grammatical subject). This was left untagged while the
  parallel structural-cleanliness sentences right after it ("Burene er for små og
  skitne") were correctly left untagged as pure structure — the annotator seems to
  have folded this instance into the same (correct) exclusion as the cleanliness
  ones, missing that this one specifically names an unmet need (movement/exercise).
  - ADD: `altfor små til at de kan bevege seg skikkelig`

### Pattern: field-labeled identifier dropped entirely — 1 instance

- **H010** — GOV_ID. "...vedrørende støy fra Edvardsens eiendom. **Fødselsnummer:
  12036712345.** Vår rett til å føre tilsyn..." — a clearly field-labeled
  fødselsnummer value at the end of the document was not tagged at all (the other
  three GOV_ID values in this document all were). Straightforward miss.
  - ADD: `12036712345`

## 3. Explicitly re-verified and left unchanged (no action taken)

To avoid over-fixing, several categories were checked closely and confirmed
correct as originally annotated:

- Every commercial food-safety **state** finding (mould/expired stock/fridge
  temperature/hand hygiene/documentation gaps) in H009, H011, H012, H013, H016 —
  correctly left untagged per B14's domain-neutral structure/cleanliness carve-out,
  confirmed by the task brief's own NOTE. Not reversed.
- The `synes`/`virker` hedge-drop judgement call, checked against every occurrence
  in the batch — only H010's instance needed the B17 fix; all others already state
  the fact via the retained predicate.
- Gambling vocabulary — none present in this batch.
- B4 parenthetical-date handling (e.g. H013's `tidligere dom for tyveri (2010)` →
  DATE_TIME `2010` tagged separately, CRIMINAL_RECORD span stopping before the
  parenthetical) — consistently correct throughout.
- B13 nested dates inside inverted "I `<year>` var X involvert..." constructions
  (H005, H016) — consistently correct.
- GOV_ID/CRIMINAL_RECORD/FINANCIAL_INFO nesting (case numbers, TOSLO-prefixed
  references) — consistently correct throughout, including the "sak nr." /
  "skattesak nr." prefix-exclusion convention.
- `Referanse: NNNNNN` — never tagged in any of the 16 docs, correct.
- Religious affiliation with no political content (Den norske kirke, Human-Etisk
  Forbund/Human-Etiker, Levende Ord, Den Germanske Hedensk Samfunn) — consistently
  left untagged per Open Question 17.
- Extramarital-affair vocabulary (H016's `utenomekteskapelig forhold`) — correctly
  routed to FAMILY_RELATION, not SEXUAL_ORIENTATION, per spec.
- H008's `nylig mistet jobben` (EMPLOYMENT_INFO) + `sliter økonomisk`
  (ECONOMIC_STATUS) split — matches the spec's own worked example exactly.

## Totals

| | Count |
|---|---|
| Starting spans | 434 |
| Added (genuine misses) | 10 |
| Fixed (B17 over-trims; each = 1 removed + 1 corrected added) | 2 |
| Removed only (clear spec violations, no replacement) | 0 |
| **Final spans** | **444** |

Per-type final counts: PERSON 42, DATE_TIME 44, NO_ADDRESS 20, POSTAL_CODE 16,
NO_PHONE_NUMBER 14, EMAIL_ADDRESS 13, ECONOMIC_STATUS 7, HEALTH_INFO 113,
EMPLOYMENT_INFO 23, GOV_ID 48, BEHAVIORAL_PATTERN 28, FINANCIAL_INFO 9,
CRIMINAL_RECORD 33, POLITICAL_CASE 11, FAMILY_RELATION 16, SEXUAL_ORIENTATION 7.

Validator: `violations: 0`, exit 0.

## Open questions (spec left me guessing)

1. **"Senteret/Menighetssenteret, drevet av `<Person>`" (H013, H016).** No clean
   eier/daglig-leder appositive exists in either document for the person who runs
   the centre — only the passive "drevet av" construction. Left untagged for
   consistency with itself (both instances), but B12/B16 arguably support tagging
   an EMPLOYMENT_INFO fact here too. Needs a project-owner call on whether "drevet
   av X" counts as an occupation appositive.
2. **Fish-tank water/environment quality (H015).** "Vannet er grumsete", algae, and
   "overbefolket i alle tre akvariene" read like B14 welfare-need deprivation (water
   quality, space) for an aquatic species, but also read like enclosure
   structure/cleanliness (the B14 carve-out) since for fish the water *is* the
   enclosure. Left untagged, consistent with the document's own treatment of
   "Akvariene er svært skitne", but this boundary is genuinely ambiguous and not
   resolved by the spec's terrestrial-animal-centric B14 examples.
3. **Single quoted animal-welfare-adjacent complaint tips ("Muligens narkotikarelatert",
   H006).** Tagged CRIMINAL_RECORD per the `kriminelle miljøer`-style default, but
   the spec's own example for that default is a corpus vote (7:1); a single
   unsupported drug-related suspicion phrase in a tip about rabbits is a judgment
   call the spec doesn't fully anticipate. Left as annotated (not flagged as wrong),
   but noting the thinness of the analogy.
