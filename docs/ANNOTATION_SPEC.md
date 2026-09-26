# Annotation Specification

This is the single authoritative annotation specification for the PII/sensitive-information labeling schema used on `combined_data.jsonl` (32,439 documents). It supersedes the four cluster-level drafts written in parallel (identifier types, economic/work types, personal-sensitive types, conduct/belief types) and incorporates the project owner's final decisions on every point where those drafts disagreed or where a draft's own supporting numbers were wrong. Where a rule below differs from what an earlier draft argued, that difference is a deliberate, final decision — it is not open for re-litigation during re-labeling.

All counts in this document were computed directly against `/home/coder/llm_finetune/data/combined_data.jsonl` and the evidence files under `scratchpad/evidence/`, except where a figure has been corrected below against the owner's own verification pass.

---

## Global rules

These four rules govern every type in the taxonomy and are not repeated inside each type's section unless a type needs to narrow or clarify one of them.

1. **Verbatim.** Every labeled span must be an exact, case-sensitive substring of `text_input`. Never translate, normalize, expand abbreviations, fix typos/casing, or synthesize punctuation the source doesn't contain. This is machine-enforced by `tools/validate_labels.py`. If a source string contains a typo (e.g. `ektektefelle`, a duplicated-syllable typo for `ektefelle`), tag the literal string as it appears — do not "fix" it. English-language source documents keep English-language spans; do not translate a span into Norwegian or vice versa just because most of the corpus is Norwegian.
2. **Full clause.** Tag the complete meaningful phrase — leading modifiers/adverbs, the head, and trailing qualifiers/appositives that are part of the same fact — never the bare minimal keyword. Example: `dømt for bedrageri i 2010`, not `bedrageri`. The single documented exception is POSTAL_CODE, whose own definition caps it at exactly 4 digits (see its section).
3. **Nesting is allowed and expected.** The same characters may legitimately carry two types at once, one nested inside the other. This is not a labeling defect to resolve by picking one type — both tags are correct simultaneously. Verified precedent: 94.0% (1,855 of 1,974, colloquially "~95%") of FAMILY_RELATION spans that contain a full proper name already have that name separately tagged PERSON. See "Cross-type precedence and overlap" for the full list of nesting pairs.
4. **Extraction, not summarization.** Copy the source's own wording, including specific nouns, vehicle/location/institution detail, and exact casing. Do not compress a specific description into a generic paraphrase. Real violation found and corrected in this corpus: a label read `'Hunden blir ofte etterlatt alene i bilen'` where the source actually read *"Hunden blir ofte etterlatt alene i en sølvgrå Volvo stasjonsvogn, registreringsnummer BC 12345."* The correct span is `'Hunden blir ofte etterlatt alene i en sølvgrå Volvo stasjonsvogn'` (stopping before the registration number, which is a separate identifier out of scope for that span).

### Additional mechanical rules

These are lower-level mechanics that recur across many types; they are stated once here instead of being repeated in every type section.

- **Field-label authority.** Most source documents are structured as `Label: value` (`Telefon:`, `Fødselsnummer:`, `Poststed:`, `Org.nr.:`, `Mottatt:`, `E-post:`). When a value's type is ambiguous from shape alone (a bare digit string, a redaction placeholder, a 4-digit number that could be a year or a postal code), **the immediately preceding field label is authoritative** and overrides shape-based guessing. This single rule resolves the large majority of the presence and type-migration conflicts documented in the type sections below (e.g. an 11-digit string under "Telefon:" is NO_PHONE_NUMBER even though it is shaped like a fødselsnummer; the identical shape under "Fødselsnummer:" is GOV_ID).
- **Redaction placeholders.** `[REDACTED]` / `[redacted]` are tagged with whatever type the adjacent field label indicates (GOV_ID after "Fødselsnummer:"/"Org.nr.:"/"saksnummer:", NO_PHONE_NUMBER after "Telefon:"/"Tlf:", EMAIL_ADDRESS after "E-post:"). Never leave a redaction placeholder untagged when it follows a recognized label, and never tag it with more than one type.
- **Reporting frames vs. diagnostic/evidentiary frames.** Verbs of attribution or self-report ("identifiserer seg som", "hevder", "erklærte seg som", "ifølge naboen", "rykter om", "mistenker at" when it is merely introducing who is speculating) sit **outside** the tagged clause and are cut. Verbs of diagnosis, treatment, conviction, or accusation ("diagnostisert med", "lider av", "behandles med", "mistanke om" the medical/legal hedge itself, "dømt for", "anmeldt for") sit **inside** the tagged clause — they are part of the fact being recorded, not commentary about it. A third-party allegation or rumour about a special-category fact (e.g. sexual orientation) is still tagged: the sensitivity attaches to the fact being processed/written down, not to whether it is proven true.
- **One clause, one fact.** If a sentence conjoins two distinct facts with "og"/"and" ("diagnostisert med diabetes type 2 og kronisk depresjon"; two separately named children), give each fact its own span rather than merging them because a conjunction sits between them.

### Clause boundary determination

These rules are normative for every narrative type (CRIMINAL_RECORD, POLITICAL_CASE,
FAMILY_RELATION, BEHAVIORAL_PATTERN, HEALTH_INFO, ECONOMIC_STATUS, FINANCIAL_INFO,
EMPLOYMENT_INFO, SEXUAL_ORIENTATION). They were added after a two-annotator trial on 22
documents scored strict F1 0.818 / relaxed 0.923, with 67% of all boundary disputes
traced to a single unanswered question: where does a clause start?

**B1 — Start at the predicate.** The span always begins at the fact itself. Drop the
grammatical subject and any linking verb, with no exceptions.

- Drop the subject **whatever it refers to** — a person (`Berg`, `Lothbroksson`, `han`),
  an animal (`Hunden`, `Hestene`, `Den`), a body part (`Øynene`, `Pelsen`) or an object.
  There is no person-only carve-out: one rule, applied everywhere.
- Drop a leading linking or auxiliary verb: `er`, `var`, `har`, `hadde`, `blir`, `ble`,
  and the hedges `virker`, `virket`, `fremstår`, together with the discontinuous
  `ser … ut` / `så … ut til å`. These only connect a subject to its predicate.
- **Keep** a leading verb or participle that carries the fact: `dømt for`, `anmeldt for`,
  `mistenkt for`, `siktet for`, `diagnostisert med`, `behandles med`, `lider av`,
  `medlem av`, `registrert som`, `innrømmet`, `erkjente`.
- `medlem av Fremskrittspartiet`, never `er medlem av Fremskrittspartiet`.
- `to barn`, never `Paret har to barn`.
- `litt sunkne`, never `Øynene virker litt sunkne`.
- `mager og har en matt fjærdrakt`, never `Den virker mager og har en matt fjærdrakt`.
- For a discontinuous `ser … ut`, tag only the predicate complement:
  `Hestene ser tynne ut` → `tynne`.
- Combined with "one clause, one fact", a multi-clause condition sentence yields one span
  per clause. `Hestene ser tynne ut, pelsen deres er rufsete og matt, og de virker
  apatiske.` → three HEALTH_INFO spans: `tynne`, `rufsete og matt`, `apatiske`.

**B2 — Drop a leading determiner.** Strip a leading `en` / `et` / `den` / `det` / `de`.
Numerals and quantifiers are part of the fact and are kept (`to barn`, `flere hester`).
- `tidligere dom for bedrageri i 2018`, never `en tidligere dom for bedrageri i 2018`.

**B3 — A case outcome is its own span.** An outcome clause separated by a comma or
conjunction is tagged separately, under the same type, rather than absorbed.
- `anmeldt for dyremishandling i 2018` **+** `sak henlagt grunnet bevisets stilling`
  = two CRIMINAL_RECORD spans, not one.

**B4 — Parentheticals.** Absorb a parenthetical when it only *qualifies the fact the span
already states* — an age, or a quantity/amount. Do **not** absorb a parenthetical that
introduces a separate identifiable datum: a date, a fødselsnummer, or any other
identifier. There the span stops before the `(` and the identifier is tagged on its own.

- `to barn, Sondre (15) og Maren (12)` — absorbed (ages qualify the children).
- `betydelig gjeld (over 500.000 NOK)` — absorbed (the amount quantifies the debt); this
  is FINANCIAL_INFO, and the longer form is mandated by FINANCIAL_INFO's own section.
- `paratuberkulose (Johne's sykdom)` — absorbed (an alternative name for the same disease).
- `gift med Bjørn Harald Olsen (f. 12.05.1972, fødselsnummer 12057212345)` — **not**
  absorbed: FAMILY_RELATION `gift med Bjørn Harald Olsen`, DATE_TIME `12.05.1972`,
  GOV_ID `12057212345`.

**B5 — Never end a span mid-token or mid-parenthetical.** A span that opens a bracket or
quote must close it, or stop before it entirely.

**B6 — Agency findings are taggable; boilerplate is not.** Case-specific factual findings
in an inspection or observation list (`Vi har observert:`) are tagged under whichever type
they state, exactly as they would be in running prose. Generic legal-citation or
requirement text is never tagged: `Kravene som gjelder:`,
`Regelverket som veiledningen bygger på:`, `Mattilsynet vurderer det slik:`.
  A restatement is its own span. Documents routinely state the same offence or
  condition twice — once in prose and again, in different words, in an observation
  bullet or an evaluation paragraph. Both are tagged. They are distinct strings of
  text, not a duplicate, and skipping the second as redundant was the single largest
  genuine recall gap measured in a single-pass batch (13 spans in 21 documents).

**B7 — A stated refusal to disclose is not a disclosure.** No fact is revealed, so nothing
is tagged: `nektet å oppgi sin seksuelle orientering`,
`nektet å oppgi informasjon om sin økonomiske situasjon`.

**B8 — A redaction placeholder standing in for a name is tagged PERSON**, consistent with
the placeholder rule for GOV_ID, phone and email fields: `[Name Redacted]` following
`Kontaktperson hos Mattilsynet:` is PERSON.

**B9 — Never include terminal punctuation.** A span stops at the last word of the fact.
Trim a trailing full stop, comma, semicolon or colon. Internal punctuation inside the
clause is kept.
- `spesielt på morgenen`, never `spesielt på morgenen.`
- `Sauene står tett sammen og skjelver, spesielt på morgenen.` → `står tett sammen og
  skjelver, spesielt på morgenen` (internal comma kept, final stop trimmed, subject
  dropped per B1).

**B10 — Keep a possessive that modifies the tagged noun.** B1 drops a clause *subject*;
it does not drop a possessive pronoun or genitive that modifies the head noun of the span
itself. Keep it — it ties the fact to the data subject and there is no shorter alternative.
- `hans samboer, Astrid Olsen`, not `samboer, Astrid Olsen`.
- `hennes ektemann, Lars Erik Bergquist`; `deres felles barn`.
- This keeps a possessive the source already has; it never adds one. Where the source
  uses a definite form instead, tag it as it stands: `ektefellen Astrid Knudsen`,
  `ektemannen Per Hansen`.

**B11 — Itemisation is absorbed; a second distinct fact is split.** A trailing
`inkludert …` / `herunder …` phrase itemises the fact already stated and stays in the span.
A clause joined by a bare `og` / `men` that states a genuinely separate fact gets its own
span.
- One span: `utestående gjeld på over 700 000 NOK, inkludert ubetalt skatt på 150 000 NOK`.
- Two spans: `utestående gjeld på over 700 000 NOK` **+** `registrert med
  betalingsanmerkninger`.
- Two spans: `diabetes type 2` **+** `kronisk depresjon`.

**B12 — EMPLOYMENT_INFO: role and employer.** A bare role word and a bare company name are
each tagged on their own. Merge them into one span only when directly attached with no
clause break; split them when they state distinct facts.
- One span: `ansatt Bergen Slakt AS`.
- Two spans: `utdannet veterinærassistent` **+** `jobber for tiden i en dyrebutikk`
  (joined by `men`, two distinct facts).

**B13 — A date inside a narrative clause is also tagged DATE_TIME.** When a clause tagged
as CRIMINAL_RECORD, HEALTH_INFO or any other narrative type contains a calendar date or a
bare year as its own token, that date is additionally tagged DATE_TIME on the same
characters. This mirrors the existing GOV_ID-nests-inside-CRIMINAL_RECORD rule and keeps
dates retrievable as entities in their own right.
- `dømt for bedrageri i 2018` → CRIMINAL_RECORD `dømt for bedrageri i 2018`
  **+** DATE_TIME `2018` (nested).
- `diagnostisert med diabetes type 2 i mars 2021` → HEALTH_INFO for the clause
  **+** DATE_TIME `mars 2021`.
- This also recovers a date that B1 would otherwise discard. In
  `I 2018 var Sæther involvert i en hendelse…`, B1 drops `I 2018 var Sæther` from the
  CRIMINAL_RECORD span because the span must stay contiguous; B13 tags `2018` as
  DATE_TIME so the year is not lost.
- **Not** when the digits are structurally part of an identifier rather than a date in
  their own right: `2018` inside the case number `2018/45678`, or the date-shaped prefix
  of a fødselsnummer, stays GOV_ID only and is never additionally DATE_TIME.

**B14 — Deprivation is health; structure is not.** In an inspection-findings bullet
(`Vi har observert:`) or in running prose, a finding that the animal is denied a **basic
welfare need** is HEALTH_INFO: it states a fact about the animal's condition, not about
the premises. A finding about the **structure, cleanliness or layout** of the premises is
not tagged by any type.

The basic welfare needs are: **food, water, veterinary care, shelter or protection from
weather, grooming and basic care (`stell`), exercise, and social contact with its own
species.** Deprivation of any of these is HEALTH_INFO even when the sentence is phrased
as a property of the enclosure — `Burene har ingen beskyttelse mot vær og vind` deprives
the animal of shelter and is tagged, while `Burene er skitne` describes cleanliness and
is not. The test is whether a need of the animal is going unmet, not whether the
grammatical subject is the animal or the enclosure.
- HEALTH_INFO: `Utilstrekkelig fôring, vanning, og stell`, `Utilstrekkelig fôr og vann`,
  `mangle tilgang til vann`, `fortsatt ikke hadde tilgang til mat eller vann`,
  `ikke får den nødvendige veterinærbehandlingen`, `Ubehandlet skade på hund`.
- Also HEALTH_INFO: `ingen beskyttelse mot vær og vind`, `ikke noe tydelig ly`,
  `lite skygge`, `mangle tilstrekkelig bevegelse, stimulering og omsorg`,
  `isolert fra andre dyr av samme art`.
- Untagged: `Manglende renhold i dyrenes oppholdsområde`, `Dårlig hygiene i fjøset`,
  `Innhegningene er små og virker skitne`, `Manglende isolering av syke dyr`.
- The rule is domain-neutral in the same way B6 is: it turns on whether the finding
  describes a living subject's deprivation, not on whether the premises house animals or
  serve food. A commercial hygiene finding (`Muggsopp på flere bakevarer`,
  `Manglende hygiene i produksjonslokalene`) is structural and stays untagged.

**B15 — An incriminating absence is tagged; a reassuring one is not.** A negated finding
that *is itself* the documented problem is tagged under the type it evidences. A negative
finding that records the absence of a problem is not tagged.
- Tagged: `fortsatt ikke hadde tilgang til mat eller vann`,
  `ikke får den nødvendige veterinærbehandlingen` (HEALTH_INFO).
- Untagged: `ingen synlige skader`, `Jeg så ingen lam` — nothing sensitive is disclosed.
- Where a negation wraps the subject and B1 cannot be applied without inverting the
  meaning (`uten at Olsen hadde kontaktet veterinær`), keep the span intact including the
  subject. Never emit a span whose meaning is the opposite of the source.

**B16 — An organisation's conduct is the named principal's conduct.** When a document
attributes an offence, neglect or other taggable conduct to a company, farm, congregation
or other organisation, and the document names a human principal for it — owner, sole
proprietor, daglig leder, leader — the clause IS tagged under whichever type applies. In a
one-principal organisation the conduct is in practice personal data about that person, and
these documents exist to record what the named party did.
- `Astrid Bjørgen Sjømat AS har systematisk feilmerket eksportprodukter` → CRIMINAL_RECORD,
  where the document names Astrid Bjørgen as the owner.
- `Gårdens regnskap viser tegn på skatteunndragelse` → CRIMINAL_RECORD, where the farm's
  owner is named.
- This rule licenses **tagging**; it does not change the boundary. B1 still applies, so the
  organisation name is dropped as the grammatical subject and the span begins at the
  predicate. The organisation's name may separately be EMPLOYMENT_INFO under B12.
- Where the document names **several** humans and none is identifiable as the responsible
  principal, leave it untagged: the referent is genuinely ambiguous and a guess would
  attribute an offence to the wrong person.

**B17 — When the subject *is* the fact, keep it.** B1 drops a subject that is a redundant
*referent* — `Hestene`, `Øynene`, `Den` — because what it names is recorded elsewhere. It
does **not** apply when the grammatical subject is a nominalised action or a
fact-bearing noun phrase that carries the disclosure itself. Dropping that would leave a
span with no content, or leave only vacuous evaluative filler.
- `Oppbevaring av uregistrert våpen er ulovlig` → CRIMINAL_RECORD
  `Oppbevaring av uregistrert våpen`, never the bare adjective `ulovlig`.
- `Forfalskede veterinærattester ble funnet i hans besittelse` → CRIMINAL_RECORD
  `Forfalskede veterinærattester`, since `Forfalskede` is the offence.
- `Mangel på mosjon er også en bekymring` → HEALTH_INFO `Mangel på mosjon`; the tail
  `er også en bekymring` is the commentary, not the fact.
- The test: after applying B1, would the span still state the disclosed fact on its own?
  If not, the subject was the fact — keep it and drop the evaluative predicate instead.

**B18 — BEHAVIORAL_PATTERN keeps its subject.** This type is the one documented exception
to B1. Its definition requires the clause to show **who** performs the pattern, so the
span starts at the earliest word that establishes the actor, and the witnessing lead-in is
kept when it is the only thing that does so.
- `Har sett eieren bli sint på hunden ved flere anledninger` — kept whole.
- `har flere ganger hørt eieren rope og skrike til hundene` — kept whole.
- Where a cleanly named subject and verb already carry the actor, drop the outer reporting
  wrapper as usual: `jeg har sett Frank Olsen oppføre seg uberegnelig` →
  `Frank Olsen oppføre seg uberegnelig`.
- No other type takes this exception.

**B19 — The organisation in an employer field is EMPLOYMENT_INFO.** The value of a
`Navn på dyreeier eller virksomhet:` field, and the organisation named in an
`Org.nr.: NNNNNNNNN (Name)` parenthetical, is the entity under inspection and is tagged
EMPLOYMENT_INFO **when the organisation is a subject of the document** — the entity being
inspected or reported on, or the workplace of a named person who is themselves a subject.
The test is the organisation's role in the document, not whether a human owner happens to
be named. A company that appears only incidentally — the reporter's own employer, a
neighbour's workplace — is not tagged, because it is not what the document is about.
Measured across the gold set, organisations in a subject slot are tagged 37 times and left
untagged 3. An earlier revision of this rule required a named **principal** (owner,
innehaver, daglig leder); that was inferred from too small a sample and contradicted by
`batch_h` H011 and `batch_l` L006, which tag `Slakteri AS` on the strength of the
`Org.nr.` parenthetical alone with only an `ansatt` named. The principal is sufficient, not
necessary. This holds regardless of what the
organisation does: a congregation is treated exactly like a farm or a company, because the
field means *employer*, not *belief*.
- `Org.nr.: 987654321 (Stavanger Menighetssenter)` → EMPLOYMENT_INFO
  `Stavanger Menighetssenter`.
- Religious **affiliation** remains untagged, as before: `medlem av Jehovas Vitner`,
  `tilhører Den norske kirke`. The distinction is between an organisation someone runs and
  a belief someone holds.
- **Not** when the company appears only as a financial counterparty rather than an
  employer — a bank the subject owes money to (`Kreditbanken AS` as the creditor) is
  excluded by FINANCIAL_INFO's own section and is not EMPLOYMENT_INFO.
- **Not** a placeholder occupying the field without naming anything: `Privatperson`,
  `Ukjent`, `Not applicable`, `N/A`.

**B20 — GOV_ID is decided by the issuer, not by the label.** Tag an identifier when a
**public authority** issued it, whatever the field is called. Leave it untagged when a
private body issued it, however official the label looks. This replaces reliance on the
surface-form list above, which cannot anticipate every label the corpus uses — 1,171
documents (3.6%) carry an identifier label that list does not name.
- GOV_ID: `Førerkortnummer` (driver's licence), `Våpenkortnummer` (firearms card),
  `Lisensnummer` (a state licence), alongside the enumerated fødselsnummer, D-nummer,
  org.nr and case/reference numbers.
- Not tagged: `journalnummer` and `pasientjournal` (a hospital's internal record),
  `lånenummer` (a bank's), `medlemsnummer` (a private association's), `våpennummer`
  (a manufacturer's serial on the weapon itself, as distinct from the state-issued card).
- The test is who issued the number, not whether it identifies a person. A hospital record
  number does identify someone, but it is not a government identifier and no other type
  covers it, so it is left untagged — as with religious affiliation.
- `Referanse:` remains untagged regardless: it is the agency's own intake routing, not an
  identifier of a person.

**B21 — Honorific + surname is PERSON; the genitive `-s` is not part of the name.**
`Fru Olsen`, `Herr Hansen`, `Mr. Olsen`, `Dr. Eriksen` are all PERSON, whether or not the
same person's full name is tagged elsewhere in the document — the surface form differs, so
this is not the bare sub-token case that B10 excludes. Measured before this rule was
written, gold tagged the form 65 times and missed it 16, with `Herr` carrying 10 of the 16;
those 16 have been normalised. A genitive occurrence is tagged in its bare form only
(`Fru Hansens personlige omstendigheter` → `Fru Hansen`), matching PERSON's general
treatment of possessives, which is unanimous at 31-0 across the gold set.


**B22 — Intoxication is typed by what the document asserts.** A named clinical condition
(`alkoholmisbruk`, `rusproblem`, `alkoholpåvirket tilstand`) is HEALTH_INFO; an offence
(`fyllekjøring`, `promillekjøring`) is CRIMINAL_RECORD; recurring conduct with no clinical
term and no offence (`beruset ved flere anledninger`) is BEHAVIORAL_PATTERN. Gold splits
18 / 17 / 4 across those three readings, and the split follows this test rather than any
single keyword. HEALTH_INFO's own positive example `alkoholpåvirket tilstand` and the
HEALTH_INFO x BEHAVIORAL_PATTERN exclusivity note previously disagreed about this.

**B23 — A case number takes its authority with it, preposition or not.** `2018-12345 Oslo
Tingrett`, `2019/12345 ved Bergen Politistasjon`, `18/00345 ved Ålesund Tingrett` and
`12-2017/0035, Nordland Tingrett` are all one GOV_ID span. The rule's examples were all
juxtaposed, which two annotators read as limiting it to that shape and so emitted the bare
number wherever `ved`, `hos` or `i` intervened. Gold includes the authority in 46 spans and
uses the bare number in 0, so the connecting word makes no difference: extend the span to
the end of the authority name.

---

## Taxonomy

| Type | One-line definition |
|---|---|
| PERSON | The full referring expression (given name(s) + surname, plus any directly-adjacent honorific) for one identifiable human being. |
| DATE_TIME | Any explicit calendar date and/or clock time as printed, standalone or attached to an event/record. |
| HEALTH_INFO | A clause stating or strongly implying a medical condition, diagnosis, disability, medication, or treatment — of a human **or**, in this corpus's animal-welfare threat model, of an animal whose condition evidences owner negligence. |
| GOV_ID | Any government-issued or government-assigned identifier: fødselsnummer, D-nummer, organisasjonsnummer, generic ID-numbers, and police/court/case reference numbers. |
| NO_ADDRESS | The Norwegian street-address portion of a location (street + house number, with optional suffix/qualifier), from an Adresse field or an in-sentence self-report. |
| CRIMINAL_RECORD | A clause naming a conviction, sentence, charge, formal accusation, police report, or investigator-stated suspicion of a specific criminal offense against an identified person. |
| POSTAL_CODE | The bare 4-digit Norwegian postal code, exactly as printed, never including the place name. |
| NO_PHONE_NUMBER | A Norwegian telephone number as it appears under a Telefon/Tlf/Telefonnummer label. |
| EMAIL_ADDRESS | A complete `local-part@domain` email address as printed after an E-post label. |
| FAMILY_RELATION | A clause naming a family, kinship, or intimate-partnership relationship between the data subject and another individual. |
| FINANCIAL_INFO | A concrete, verifiable financial fact: a specific amount, account/loan/case number, named creditor or bank, or a specific named debt instrument. |
| EMPLOYMENT_INFO | A named person's occupation, job title, professional role, employer/workplace, or business ownership position. |
| POLITICAL_CASE | A clause stating that an identified person holds, has stated, or is affiliated with a political party, movement, or opinion. |
| BEHAVIORAL_PATTERN | A clause describing a recurring or characteristic pattern of conduct performed by an identified natural person (never an animal's own conduct). |
| ECONOMIC_STATUS | A subjective, evaluative characterization of a person's or organization's overall financial condition, with no attached number, account, or named instrument. |
| SEXUAL_ORIENTATION | A clause stating, disclosing, or credibly alleging a named individual's sexual orientation, gender identity, or GDPR-Art.-9 "sex life" fact. |

### Removed types

Two types that existed in earlier drafts of this schema are cut entirely. Neither appears in the 16-type taxonomy above, and neither should be re-labeled going forward.

**CONTEXT_SENSITIVE — cut (23,621 spans dropped).** This type had no positive membership test and behaved empirically as a dumping ground rather than a class: 3,345 presence conflicts (the highest of any type measured — worse than CRIMINAL_RECORD's 2,015 and POLITICAL_CASE's 859 combined) and 338 type migrations spread across 11 different destination types. A keyword-bucket audit of its spans (buckets are non-exclusive, so they do not sum to 100%) shows no single category anywhere close to a majority: animal/disease content 10.6%, weapon mentions 9.9%, financial-crime words 7.6%, criminal-suspicion language 5.7%, bare organisation/business names 3.9%, political/organisation-affiliation words 1.5%, pure administrative form fields 0.4%. No category exceeds roughly 11% of the type's own content, confirming it is a dumping ground rather than a coherent class. It was also never wired into the training config (`entity_types`), so relabeling it would have produced zero training signal even before this cut. Its content is redistributed as follows, with each destination rule fully specified in that type's own section:

| Former CONTEXT_SENSITIVE content | New home |
|---|---|
| Suspicion-of-crime phrasing (`mistenker rusmisbruk`, `muligens ulovlig spillvirksomhet`, weapon possession, financial-fraud phrasing) | CRIMINAL_RECORD |
| Political/organisation affiliation with a stated membership verb | POLITICAL_CASE |
| A person's own conduct/pattern (aggression, drinking, neglect performed by a named person) | BEHAVIORAL_PATTERN |
| Animal disease, animal physical condition, animal-only behaviour, and administrative metadata (Fylke/Kommune/Referanse/Poststed values, bare organisation names) | **not tagged at all** — this is a distinct pool of spans from HEALTH_INFO's own animal-condition content (see HEALTH_INFO below); it is dropped, not migrated |
| A genuine "other sensitive fact" with no home in the remaining 16 types | **drop, do not tag** — a spec that cannot state a positive rule for a residual case must not force an annotation |

**IDENTIFIABLE_IMAGE — cut (15,016 spans).** An earlier draft recommended cutting this type but justified it with an incorrect statistic, claiming 98.6–99.9% of spans matched a fixed animal-attachment template with a small (~9-span, 0.06%) genuine minority of person-depicting images worth preserving elsewhere. That specific claim does not hold up: the verified match rate against the animal-attachment template is only 55.2%, not 98.6–99.9%. The type is still cut, but for the correct reason, verified directly against the corpus: **these spans are overwhelmingly generic attachment references that identify nobody**, not narrowly a single template. The most common spans are `bilder av dyrene` (560×), `bilder og video av dyrene` (462×), `bilder` (395×), `bilder av hunden` (366×), `video tatt fra offentlig vei` (198×), and `video` (110×) — none of these disclose an identifiable person's likeness. A separate, targeted check specifically for person-referencing spans (candidates like a described photo of a named individual, or a social-media profile pointer) found **zero genuine hits** in the corpus. There is accordingly no minority worth preserving under any type, and nothing to fold into another type — the entire population is dropped.

---

## Cross-type precedence and overlap

### Precedence chains (same characters, choose one type when clauses compete for it)

- **Financial-crime cluster: CRIMINAL_RECORD > FINANCIAL_INFO > ECONOMIC_STATUS.** Whenever a clause's head word/phrase names a criminal offense (`skatteunndragelse`, `forfalskning av skatte*`, `svindel`, `bedrageri`, `unndragelse`, `hvitvasking`, `underslag`), tag the whole clause CRIMINAL_RECORD and nothing else on those characters. A bare offense noun is sufficient on its own — **no accompanying accusation/conviction verb is required.** A quantified amount standing separately in the same sentence, outside the offense-naming clause, still gets its own independent FINANCIAL_INFO span (e.g. "dømt for skatteunndragelse. Gjelden hans er 550 000 NOK" → `skatteunndragelse` = CRIMINAL_RECORD, `550 000 NOK` = FINANCIAL_INFO, two spans). Below CRIMINAL_RECORD, FINANCIAL_INFO wins over ECONOMIC_STATUS whenever a number, named creditor, or named instrument is present; ECONOMIC_STATUS is reserved for pure evaluative judgement with none of those. See the CRIMINAL_RECORD, FINANCIAL_INFO, and ECONOMIC_STATUS sections for the full evidence and boundary rules.
- **GOV_ID vs. FINANCIAL_INFO for a bare number:** FINANCIAL_INFO wins when the number is explicitly a monetary amount; GOV_ID wins when the number is explicitly a fødselsnummer/case/account-style reference with no currency unit attached.
- **PERSON > EMPLOYMENT_INFO** for the name portion of any "Dr. `<Name>`" construction — EMPLOYMENT_INFO only ever owns the title/role words, never the name.
- **POLITICAL_CASE > EMPLOYMENT_INFO** for candidacy/elected-office spans (`kandidat til kommunestyret`).
- **EMPLOYMENT_INFO > FAMILY_RELATION** specifically for `forretningspartner` (business partner) — always employment, never kinship.
- **CRIMINAL_RECORD > FAMILY_RELATION** for domestic-violence/legal-sanction vocabulary (`vold i nære relasjoner`, `besøksforbud`) even inside a sentence that also describes a family relationship.
- **CRIMINAL_RECORD > SEXUAL_ORIENTATION** for `seksuell trakassering` and similar criminal-behaviour terms.
- **SEXUAL_ORIENTATION > FAMILY_RELATION** when a clause contains both a relationship noun and an orientation adjective in one phrase (`lesbisk forhold`, `homofilt forhold til Lars Olsen`) — tag the entire clause SEXUAL_ORIENTATION only.
- **Field-label wins over digit-shape** throughout the identifier types (see Additional mechanical rules above) — this is how GOV_ID, NO_PHONE_NUMBER, FINANCIAL_INFO (Kontonummer), POSTAL_CODE, and DATE_TIME are told apart when a bare digit string could shape-match more than one of them.

### Nesting (same characters legitimately carry two types)

- **PERSON nests inside FAMILY_RELATION.** When a FAMILY_RELATION clause names a person in full (given name + surname), that name is separately tagged PERSON on the same characters (94.0% of the corpus's own FAMILY_RELATION+name spans already do this). Exception: a bare surname attached to "Familien" (`Familien Eriksen`) is not additionally tagged PERSON, because it names a household, not one identified individual.
- **POSTAL_CODE nests inside NO_ADDRESS — but only field-conditionally.** When the 4-digit postal code is physically written inside an "Adresse:" field's own value (`Fjellveien 12, 8300 Svolvær`), the whole clause is NO_ADDRESS and the 4 digits are additionally, separately tagged POSTAL_CODE. This nesting does **not** happen on a standalone "Poststed: NNNN By" field — there, only the 4 digits are tagged (POSTAL_CODE), and the city name is tagged by neither type. See the NO_ADDRESS and POSTAL_CODE sections for the full field-conditioned rule.
- **GOV_ID nests inside CRIMINAL_RECORD — not adjacent.** When a case/docket number is directly attached to a criminal-record clause, the CRIMINAL_RECORD span runs through the number rather than stopping before it, and the number is additionally, separately tagged GOV_ID on the same characters. Example: for "dømt for bedrageri i sak 12345/2018", CRIMINAL_RECORD = `dømt for bedrageri i sak 12345/2018` (the whole clause) and GOV_ID = `12345/2018` (nested). This is a deliberate double-tag, confirmed as final by the project owner, overriding an earlier draft's "stop before the number" adjacency rule. GOV_ID still owns the number's *own* type identity when no criminal-record clause surrounds it at all: `12345/2018` on its own, with no accusation/conviction language nearby, is GOV_ID 117 times vs. CRIMINAL_RECORD 2 times in the corpus. See CRIMINAL_RECORD §Overlap policy and Precedence for the worked example.
- **GOV_ID also nests inside FINANCIAL_INFO** full-clause spans on the same basis (e.g. a case/reference number inside a debt-description clause) — this resolves 32 CRIMINAL_RECORD and 31 FINANCIAL_INFO historical "type migrations" that were really annotators picking only one of two valid simultaneous tags.
- **PERSON nests inside SEXUAL_ORIENTATION** clauses that name a partner (`homofilt forhold til Lars Olsen`, `i et forhold med Karianne Nilsen`) — the name is separately PERSON while the whole clause stays SEXUAL_ORIENTATION.

### Mutually exclusive (same characters carry exactly one type, never two)

- HEALTH_INFO and BEHAVIORAL_PATTERN — pick HEALTH_INFO only when a named clinical/diagnostic term is present; otherwise BEHAVIORAL_PATTERN.
- HEALTH_INFO and FAMILY_RELATION — a plain kinship noun (`barn`) is never a health fact.
- FAMILY_RELATION and SEXUAL_ORIENTATION — see precedence above (SEXUAL_ORIENTATION wins when both are present in one clause).
- FAMILY_RELATION and CRIMINAL_RECORD — see precedence above.
- SEXUAL_ORIENTATION and CRIMINAL_RECORD — see precedence above.
- NO_ADDRESS and POSTAL_CODE on a standalone "Poststed:" field — see nesting rule above; this is the one case where the two behave as mutually exclusive rather than nested.
- DATE_TIME and GOV_ID — a run of digits is either a date or an ID reference, never both.
- DATE_TIME and POSTAL_CODE — a 4-digit run is either a postal code or a year, disambiguated by field label/sentence context.
- GOV_ID and NO_PHONE_NUMBER — disambiguated purely by field label, never by digit count.
- GOV_ID and FINANCIAL_INFO for a bare account-shaped number — disambiguated by field label ("Kontonummer:" → FINANCIAL_INFO; "Org.nr.:" → GOV_ID) even when the digit shapes are identical.

---

## Type specifications

### PERSON

#### Definition
The complete referring expression for one identifiable, named human being — given name(s) plus surname, together with any honorific title that is directly and adjacently prefixed to the name with no intervening punctuation. Excludes animals, deities/mythological names used as pet names, organizations, and role/job descriptions.

#### Include
- Full name: first + last (`Marius Skatteboe`, `Per Arne Olsen`)
- Full name with middle name(s) (`Hans Petter Halvorsen`, `Liv Kristin Haugen`)
- Honorific/title directly prefixed, no comma (`Dr. Hans Petter Hansen`, `Dr. Per Hansen`, `Fru Berglund`, `Mr. Halvorsen`, `Mr. Bergquist`)
- Single given name when the surrounding context unambiguously identifies a human (a named "varsler" (reporter), "eier" (owner), sender/recipient of correspondence) — e.g. a first-name-only signer of a tip
- Initial + surname (`R. Lothbrok`) when used as a human signature/reference

#### Exclude
- Bare surname used as a family label, not naming an individual (owned by FAMILY_RELATION) — e.g. `Familien Eriksen`
- Animal/pet names, even proper nouns that look like personal names (`Rex`, `Balder`, `Odin`, `Thor`, `Luna`, `Snøball`, `Pus`, `Frøya`, `Birk`) — the entity referred to is not human
- Role/appositive phrases separated from the name by a comma (`Senterets leder,` in "Senterets leder, Solveig Berg") — descriptive metadata, not part of the referring expression; only `Solveig Berg` is PERSON
- Deity/mythological single names used as commentary rather than as a name for a person or pet in context (rare, judged case by case)

#### Boundary rule
Full clause = **title (if directly adjacent, no comma) + full given name(s) + surname**, nothing more, nothing less.
- `Dr. Hans Petter Hansen` (title glued to name) — mandate the **longer** form whenever a title is directly adjacent.
- `Dr. Per Olsen`, `Mr. Halvorsen`, `Fru Berglund` — same rule.
- Stop before any comma, parenthesis, or role description: in `...Eieren, Astrid Solveig Hansen (Fødselsnummer:...` the PERSON span is `Astrid Solveig Hansen` only.
- Stop before job-title appositives: in `Senterets leder, Solveig Berg (fødselsnummer: 120378-12345)` the PERSON span is `Solveig Berg` only.
- Do not extend across "og" (and) to swallow a second person's given name into the first person's span: `Silje Lie` and `Erik Lie` are two separate PERSON spans in `...Silje Lie (fødselsnummer 15048823456, fiktivt) og Erik Lie (fødselsnummer 20109134567, fiktivt)`.

#### Overlap policy
- May co-occur (adjacent, non-overlapping) with GOV_ID, NO_PHONE_NUMBER, EMAIL_ADDRESS, DATE_TIME, NO_ADDRESS in the same record.
- Does not overlap FAMILY_RELATION spans on the exact same span boundaries, but a name inside a FAMILY_RELATION clause is separately, nested-tagged PERSON — see Cross-type precedence and overlap.

#### Positive examples
1. `Marius Skatteboe` — named recipient of a mottatt-melding ("Bekymringsmelding mottatt av Marius Skatteboe").
2. `Per Arne Olsen` — value of "Navn på dyreeier eller virksomhet:" field, a named animal owner.
3. `Liv Kristin Haugen` — value of "Navn på varsler:" (reporter's name) field.
4. `Hans Petter Halvorsen` — three-part full name, animal-owner field.
5. `Dr. Per Hansen` — title-glued form; majority corpus tagging (16 PERSON vs 1 EMPLOYMENT_INFO) supports including the title.

#### Negative examples
1. `Rex` — from `...men schæferen tror jeg heter ">>>Rex<<<"...` — a dog's name; not PERSON even though the old labels tagged it as one.
2. `Balder` — ambiguous corpus token (25 PERSON, 3 former-CONTEXT_SENSITIVE); tag PERSON only when the surrounding sentence identifies a human referent, not when used as a pet's name.
3. `Familien Eriksen` — a family collective reference, not one named individual; FAMILY_RELATION, not PERSON.
4. `Senterets leder,` (in "Senterets leder, Solveig Berg") — a role/title appositive; excluded, though `Solveig Berg` itself is included.

#### Resolved conflicts
- Boundary conflicts (`Hans Petter Hansen` vs. `Dr. Hans Petter Hansen`, and 15 similar rows): mandate the **longer form including the adjacent honorific** in every case (Dr., Mr., Fru).
- Presence conflicts (`Astrid Eide`, `Harald Bjørklund`, `Lars Olsen`, etc. missed in one copy): always tag per the field-label rule.
- Presence conflicts where animal names appeared in the list (`Elvira`, `Bjørn`, `Balder`, `Frida`, `Zar`, `Zarina`, `Luna`, `Thor`, `Baron`, `Missy`): resolved as **exclude** in both copies — these are pet names.
- Type migration (`Leif Arnesen` PERSON vs. FAMILY_RELATION 1×, `Bjørn Olsen` PERSON 761 vs. FAMILY_RELATION 2×, etc.): PERSON wins whenever the span is a specific named individual; a relational phrase containing that name is additionally, separately FAMILY_RELATION (nested, not exclusive).

---

### DATE_TIME

#### Definition
Any explicit calendar date and/or clock time as printed in the source text — a document timestamp ("Mottatt: 24.10.2023 16:35"), an incident/event date, or a date embedded in prose ("22. september 2023"). The config's literal definition text ("dates tied to identifiable persons") does not match actual annotation practice — the overwhelming majority of DATE_TIME spans are standalone administrative/event timestamps with no grammatical tie to a specific person. This spec follows the data: standalone dates/times are DATE_TIME whether or not a person is named nearby (the config's definition text should be updated to match — see Open questions).

#### Include
- Full timestamp: `24.10.2023 16:35`, `27.10.2023 19:45`
- Date only, dotted: `22.10.2023`
- Date only, prose form with month name and year: `15. oktober 2023`, `22. september 2023`
- ISO date: `2023-11-02` (when standalone, not part of a case-number suffix)
- Compact multi-date prose expressions sharing one month/year, tagged as a single span: `15. og 22. september 2023`

#### Exclude
- A bare year or ISO-date-shaped string that is structurally the prefix of a GOV_ID case number or fødselsnummer (`2018` inside `2018/45678`; `121270` inside `12127012345`) — tag the whole thing GOV_ID only.
- Vague/relative time expressions with no anchored calendar value: `nylig` ("recently"), `det siste året`, `flere anledninger` — not verifiable dates.
- Durations that are not calendar points: `14 dager` — a duration/quantity, not a date/time point.
- Deictic qualifiers trailing an actual date: in `17. mai` vs. `17. mai i år`, exclude the trailing `i år` — commentary, not a calendar-verifiable component.

#### Boundary rule
Full clause = the complete explicit date/time expression: day + month (name or number) + year (if printed) + clock time (if printed) — but stop before deictic/relative qualifiers and before any non-date reference-number suffix.
- `15. oktober` vs. `15. oktober 2023` → mandate the **longer** form; always include the year when adjacent and part of the same expression.
- `18. oktober` vs. `18. oktober 2023` → **longer** form, same reasoning.
- `17. mai` vs. `17. mai i år` → mandate the **shorter** form `17. mai`; exclude the trailing deictic `i år`.
- `22. september 2023` vs. `15. og 22. september 2023` → mandate the **longer**, compound form as a single span when two day-numbers share one trailing month/year.
- `2023` vs. `oktober 2023` → mandate the **longer** form when a month name is adjacent to the year.
- `2024.10.2024` vs. `2024-03-15-AB` (date vs. date+case-suffix): tag only the bare date as DATE_TIME and the full suffixed string as GOV_ID instead — do not tag both.
- `Mottatt: 24.10.2024 15:32 Type:` — always include the time whenever it is printed immediately after the date with no intervening field label; `24.10.2024 15:32` is one DATE_TIME span, not two.

#### Overlap policy
- Mutually exclusive with GOV_ID on the same characters — a run of digits is either a date or an ID, never both.
- Mutually exclusive with POSTAL_CODE on 4-digit strings — disambiguate by field label/sentence context ("Poststed:" → POSTAL_CODE; prose/timestamp context → DATE_TIME).
- May co-occur (adjacent, non-overlapping) with PERSON, NO_ADDRESS, GOV_ID in the same record.

#### Positive examples
1. `24.10.2023 14:35` — "Mottatt:" field, full timestamp.
2. `22.10.2023` — in-prose incident date ("Jeg besøkte MiniZoo Eventyr med familien min 22.10.2023").
3. `15. januar 2024, 14:37` — "Mottatt:" field with comma-separated time.
4. `27.10.2023 15:32` — "Mottatt:" field.
5. `22. september 2023` — prose date embedded in a sentence.

#### Negative examples
1. `2018` as the prefix of `2018/45678` — excluded; the whole `2018/45678` is GOV_ID instead.
2. `121270` as the prefix of `12127012345` — excluded; the whole 11-digit string is GOV_ID instead.
3. `14 dager` — excluded; a duration, not a date/time point.
4. `17. mai i år` — only `17. mai` is included; `i år` is excluded.

#### Resolved conflicts
- Boundary (88 rows): resolved per the Boundary rule — longer form wins when a year/month is genuinely part of the date; shorter form wins when the "extra" material is a deictic qualifier or an ID suffix.
- Presence (730 rows, e.g. `2023-11-08`, `2023-10-26`, `2018`, `2010`, `14 dager`): genuine standalone dates are always tagged; `14 dager` is excluded (duration) in every copy.
- Type migration (152 rows, 144 to GOV_ID): date-shaped ID prefixes and full fødselsnummer strings are GOV_ID only, never additionally DATE_TIME.

---

### HEALTH_INFO

Current spans: 52,778. Boundary conflicts: 58. Presence conflicts: 682. Type migrations: 10.

#### Definition
HEALTH_INFO tags a clause that states or strongly implies a medical condition, diagnosis, disability, medication, or treatment. It covers named diseases/disorders, diagnosis codes, prescribed or used medications, disabilities, and clearly medical symptoms — of a **human** individual, and, in this corpus's animal-welfare threat model, of an **animal** whose documented physical condition or symptoms serve as evidence of the owner's negligence (see Verdict below for the reasoning and the reversal this represents from an earlier draft of this spec).

#### Include
- Named diagnoses and disorders of a human: `diabetes type 2`, `kronisk depresjon`, `ADHD`, `bipolar lidelse`, `tuberkulose` (when the patient is human).
- Diagnosis codes: `F32.9`.
- Medications tied to a person: `Metformin`, `Sertralin`, `antidepressiva`, `insulin`.
- Substance use/dependency framed as a health condition: `rusmisbruk`, `alkoholproblem`, `cannabis` (when used clinically/medically, e.g. "medisinsk cannabis").
- Human hospitalization/incapacity facts: `innlagt på Bærum sykehus`, `hentet i ambulanse`.
- Explicit human mental-health language: `ustabil mental helse`, `tegn på depresjon`.
- **Animal physical/behavioural/medical condition** — pelage, weight, gait, wounds, parasites, appetite, discharge, lameness, apathy, and named livestock/veterinary disease: `skorper rundt øynene`, `halter litt`, `sikler kraftig`, `synlige sår`, `betente sår`, `matt og flokete`, `unormal gange`, `åpenbart en hudsykdom`, `bovine tuberkulose`, `paratuberkulose`, `paratuberkulose (Johne's sykdom)`, `blåtunge`, `rabies` (in an animal), `Canine distemper`, `Equine influenza`, `Parvovirus`, `mistanke om rabies` / `mistenkt tuberkulose` (in an animal).

*Note on scope: this animal-condition Include bullet is HEALTH_INFO's own pre-existing span population (documented in animal-welfare interview-template documents) — it is not a migration target for the former CONTEXT_SENSITIVE type's separate animal-disease bucket, which is dropped entirely rather than redirected here (see Removed types above).*

#### Exclude
- Generic behavioural descriptions of a **human** with no medical content (`aggressiv atferd`, `stereotyp atferd`) — BEHAVIORAL_PATTERN, not HEALTH_INFO, unless a clinical diagnosis word is present. This does **not** extend to an animal: BEHAVIORAL_PATTERN excludes animal subjects outright, so routing animal stereotypy there would drop it from the schema entirely. An animal's stereotypy, pacing or apathy is HEALTH_INFO — a welfare condition, tagged in 37 gold documents and 0 as BEHAVIORAL_PATTERN.
- Financial/behavioural euphemisms that aren't a diagnosis: `spilleavhengighet` (gambling) is BEHAVIORAL_PATTERN, not HEALTH_INFO, unless the text names a clinical diagnosis (`diagnostisert spillavhengighet` would qualify).

#### Boundary rule (per subcategory)
**(a) Diagnoses/conditions:** span = `[diagnostic or affliction verb phrase] + [condition name]`, stopping at the first conjunction/comma that introduces a second distinct fact.
- `diagnostisert med diabetes type 2` (include the verb — part of the medical fact, not commentary).
- `diagnosekode F32.9` (include the field label — directly and structurally attached to the code).
- `behandling for kronisk depresjon` (include the treatment-frame).
- Two conditions conjoined ("diagnostisert med diabetes type 2 og kronisk depresjon") → split into **two spans**: `diagnostisert med diabetes type 2` and `kronisk depresjon`.

**(b) Medications:** span = `[usage/treatment verb] + [medication name]`, stopped before any trailing purpose clause naming a *different* fact.
- `bruker antidepressiva`, `behandles med antidepressiva`, `tar Metformin daglig`.
- `Metformin for diabetes type 2` is **not** one span — split into `Metformin` (or `tar Metformin`) and `diabetes type 2`, each independently.

**(c) Symptoms/disabilities:** span = full descriptive noun phrase including leading intensifying adjectives and trailing location/body-part qualifiers, for humans and animals alike.
- `synlig sår på venstre hånd` (not `sår på venstre hånd`).
- `minor injury to his left hand` (English-language doc keeps English span).

**(d) Suspected/hedged conditions:** medical hedge words are part of the clause.
- `mistanke om rabies`, `mistenkt tuberkulose` — include the hedge; applies equally whether the patient is human or animal.

#### Overlap policy
- May co-occur (different, nested characters) with PERSON when a name appears adjacent to the diagnosis (`Fjeldstad sliter med diabetes type 2` → `Fjeldstad` tagged PERSON separately, `sliter med diabetes type 2` tagged HEALTH_INFO — do not extend HEALTH_INFO leftward to swallow the name).
- Never overlaps FAMILY_RELATION on the same characters (`barn`: 992 FAMILY_RELATION / 1 HEALTH_INFO → mandate FAMILY_RELATION; a plain kinship noun is never itself a health fact).
- Mutually exclusive with BEHAVIORAL_PATTERN on identical spans — pick HEALTH_INFO only if a named clinical/diagnostic term is present, otherwise BEHAVIORAL_PATTERN (`aggressiv atferd`, `klør seg mye` without a named skin condition → BEHAVIORAL_PATTERN).
- Since the former CONTEXT_SENSITIVE type is cut, conditions/diseases go to HEALTH_INFO exclusively regardless of whether the subject is human or animal — this resolves the `Giardia`, `rabies`, `rusproblem`, `alkoholproblem`, `halthet` migrations (see Resolved conflicts).
- Never shares characters with ECONOMIC_STATUS/FINANCIAL_INFO even when a sentence links them ("Jens sliter med både økonomi og helse" → split: `sliter med ... økonomi` = ECONOMIC_STATUS, `helse` alone is too vague to tag unless a named condition follows).

#### Positive examples
1. `diabetes type 2` in "...Fjeldstad sliter med diabetes type 2, noe som..." — named clinical diagnosis of a human.
2. `alvorlig depresjon` in "...har hatt perioder med alvorlig depresjon, bekreftet av journalnotater fra Sørum Legekontor..." — clinical, corroborated.
3. `Metformin` in "...Sørli, som er diagnostisert med diabetes type 2 og tar Metformin daglig..." — named medication tied to a person.
4. `mentale helse` in "...Naboer har uttrykt bekymring for hennes mentale helse..." — human mental-health concern.
5. `alkoholpåvirket tilstand` in "...Jeg har observert Lars Olsen i alkoholpåvirket tilstand ved flere anledninger..." — human intoxication state, named individual.
6. `skorper rundt øynene` in "...En av dem så ut til å ha noe skorper rundt øynene..." (subject is a cat) — animal symptom, tagged per the reversed animal-health verdict.
7. `åpenbart en hudsykdom` (source: "Hunden har åpenbart en hudsykdom") — explicitly an animal; the condition is tagged HEALTH_INFO, with the subject and auxiliary dropped per B1.
8. `tuberkulose` in a livestock-inspection sentence about cattle ("bovine tuberkulose ble bekreftet ved funn av mistenkelige lesjoner hos tre dyr") — animal disease, tagged.

#### Negative examples
1. `spilleavhengighet` — gambling addiction is BEHAVIORAL_PATTERN, not HEALTH_INFO, unless a clinical diagnosis frame is present.
2. `aggressiv atferd` / `stereotyp atferd` alone, with no diagnostic word, **describing a human** — BEHAVIORAL_PATTERN, not HEALTH_INFO. The same words describing an animal are HEALTH_INFO (see the Exclude note above); BEHAVIORAL_PATTERN cannot take an animal subject.

#### Resolved conflicts
- `sår på venstre hånd` vs. `synlig sår på venstre hånd` → **longer form**.
- `F32.9` vs. `diagnosekode F32.9` → **longer form**.
- `kronisk depresjon` vs. `behandling for kronisk depresjon` → **longer form**.
- `diabetes type 2` vs. `diagnostisert med diabetes type 2` → **longer form**.
- `diabetes type 2` vs. `diagnostisert med diabetes type 2 og kronisk depresjon` → **split** into `diagnostisert med diabetes type 2` and `kronisk depresjon`.
- `antidepressiva` vs. `bruk av antidepressiva` / `bruker antidepressiva` / `behandles med antidepressiva` → **longer form** in each case.
- `rabies` vs. `mistanke om rabies` → **mandate the longer form in all cases, regardless of whether the patient is human or animal** (this reverses an earlier draft's species-conditioned split).
- `paratuberkulose` vs. `paratuberkulose (Johne's sykdom)` → **mandate the longer form**; this is a cattle disease, and animal disease names are included under HEALTH_INFO (no longer excluded).
- `Type 2 diabetes` vs. `diagnosed with Type 2 diabetes and chronic depression` (English) → **split**, same as the Norwegian case.
- `cannabis` vs. `brukt cannabis` → **longer form** (`brukt cannabis`), unless the mention is purely about a criminal offence with no health framing, in which case it is CRIMINAL_RECORD, not HEALTH_INFO.
- `diabetiker type 2` vs. `diabetiker type 2-diagnose` → **longer form**.
- `Giardia`, `rabies`, `rusproblem`, `alkoholproblem`, `halthet` (previously migrating to the now-cut CONTEXT_SENSITIVE type) → **mandate HEALTH_INFO in all cases, regardless of whether the subject is human or animal** — CONTEXT_SENSITIVE, the alternative destination, no longer exists, and the animal-health exclusion that would otherwise have excluded `rabies`/`halthet` on an animal has been reversed (see Verdict).
- `barn`: {HEALTH_INFO: 1, FAMILY_RELATION: 992} → **mandate FAMILY_RELATION**; the single HEALTH_INFO tag is a labeling error.

#### Verdict: animal health/condition stays in HEALTH_INFO

**Animal health/condition content is tagged HEALTH_INFO and is not excluded.** An earlier draft of this spec argued for excluding it on the grounds that GDPR Art. 4(1) restricts "personal data" to natural persons, and estimated that doing so would drop roughly 15,769 of the type's 52,778 spans. The project owner has reversed that recommendation: in these Mattilsynet animal-welfare reports, the documented condition of an animal is direct evidence of the owner's negligence, and this product's threat model treats it as sensitive information in its own right, independent of the strict "natural person" reading of Art. 4(1). HEALTH_INFO therefore keeps all 52,778 spans, with no species-based carve-out at annotation time.

For reference, the document-template split that motivated the earlier (now-reversed) recommendation still describes where these spans live: of the 52,778 HEALTH_INFO spans, 15,769 (29.9%) occur in the 16,537 documents written as an animal-welfare interview transcript (marked by "-- Hvordan ..." / "Hvilket dyr er du bekymret for?"), and 37,009 (70.1%) occur in the 15,902 "dossier" documents (structured personal-data reports about a named owner). Both populations are retained.

Action for re-labeling: tag animal condition/symptom content as HEALTH_INFO on the same basis as human diagnoses. Do not gate inclusion on checking whether the grammatical subject is human or animal — that check is no longer part of this type's rule.

---

### GOV_ID

#### Definition
Any government-issued or government-assigned identifier for a person, entity, or case: fødselsnummer, D-nummer, organisasjonsnummer, generic "ID-nummer" values, and police/court/case reference numbers ("saksnummer", "sak nr.", "Vår ref", "Deres ref" when populated). Excludes plain calendar dates and durations that merely resemble part of an ID.

#### Include — surface-form enumeration (not closed; see B20)
The forms below are the ones observed in this corpus. They are **not** a closed list:
where a label is not listed, apply B20's issuer test rather than defaulting to untagged.
- `Førerkortnummer:` — a driver's licence number is government-issued; tag the value as GOV_ID. (Distinct from `Referanse:`, which is excluded below.)

1. **Fødselsnummer/personnummer** — 11 digits, `DDMMYY` + 5-digit personal number, written with no separator (`12127012345`), a single dash after digit 6 (`120378-12345`), or a single space after digit 6 (`150701 44556`). Trigger labels: "Fødselsnummer:", "fødselsnummer", "personnummer:", "personnummer".
2. **D-nummer** — same 11-digit shape as fødselsnummer (day-of-birth digit conventionally offset by +4, e.g. `05123456789`); trigger label: "D-nummer". Do not attempt to verify the +4 offset arithmetically — trust the field label.
3. **Organisasjonsnummer (org.nr)** — 9 digits, solid (`987654321`, `912345678`) or grouped in 3s with spaces (`987 654 321`, `912 345 678`). Trigger labels: "Org.nr.:", "org.nr", "organisasjonsnummer".
4. **Generic "ID-nummer" / "Nasjonal ID-nummer"** — whatever digit or alphanumeric string directly follows this literal label, regardless of length or whether it matches a real ID format — tag it anyway because the document itself presents it as an identity number.
5. **Case/reference numbers** — the value of "saksnummer", "sak nr.", "Vår ref"/"Vår ref.", "Deres ref"/"Deres ref." (only when populated with an actual value, not `-` or blank), in any of these observed formats:
   - `YYYY/NNNNN` or `YYYY-NNNNN` (`2018/45678`, `2015-00472`)
   - `YYYYMMDD-NNNN` or `YYYY-MM-DD-NNNN` (`20230512-0047`, `2023-11-02-BH-027`)
   - `NN-NNNNN/YYYY` (`08-12345/2018`, `15-54321/2019`)
   - Court/police-authority-suffixed (`2018-12345 Oslo Tingrett`, `2019/423 Lofoten Tingrett`, `Nordland politidistrikt 2022/11458`)
   - Court-prefixed compact form `TOSLO-YYYY-NNNNN` (`TOSLO-2008-12345`, `TOSLO-2018-12345`) — 268 documents in the corpus contain a TOSLO-prefixed case number (verified count).
   - Letter-coded prefixes (`BH-2023-10-27`, `I-2023-005432`, `I-2023-007890`, `L-456789`)
6. **Redaction placeholders** `[REDACTED]`/`[redacted]` — only when immediately preceded by one of the labels in items 1–5 above.

#### Exclude
- A bare 4-digit year or a full calendar date (`2018`, `2023-10-26`) used **on its own**, with no attached ID suffix — DATE_TIME, not GOV_ID.
- The date-shaped **prefix** of a case number when it is structurally part of that number (see Boundary rule) — not additionally tagged as a standalone date.
- Account/loan numbers under a "Kontonummer"/"kontonr" label — FINANCIAL_INFO, even if the digit string is shape-identical to an org number.
- **`Referanse: NNNNNN`** — the agency's own complaint-intake reference, present in
  51% of the corpus (16,537 documents). It is administrative routing metadata, not an
  identifier of a person, and the corpus leaves it untagged in 16,309 of 16,537 cases
  (98.6%). Never tagged, by any type. This is a deliberate omission from the trigger-label
  enumeration above, not an oversight: `Vår ref:` and `Deres ref:` *are* in that list and
  *are* GOV_ID.
- `Fylke:`, `Kommune:`, `Poststed:` as bare administrative form fields carry no GOV_ID.

#### Boundary rule
- **Fødselsnummer/D-nummer/org.nr/ID-nummer**: tag the number exactly as written — full 11 digits (with its single dash or space if present) or full 9 digits (with its spaces if present). Never split off the leading 6 digits. Examples: `120378-12345`, `987654321`, `987 654 321`, `15048823456`.
- **Case/reference numbers with a court/authority name**: the full clause **includes** the authority name when adjacent. `2018-12345` vs. `2018-12345 Oslo Tingrett` → **longer** form; `2010/12345` vs. `Oslo tingrett 2010/12345` → **longer** form (authority name included wherever it touches the number, before or after); `2019/423` vs. `Lofoten Tingrett 2019/423` → **longer** form.
- **Case/reference numbers with a date-shaped prefix followed by a suffix**: tag the **entire** compound string as one GOV_ID span; do not also tag the date-shaped prefix as DATE_TIME. `2018/45678` is GOV_ID in full; `2024-03-15-BH-042` is GOV_ID in full.

#### Overlap policy
- **GOV_ID nests inside CRIMINAL_RECORD and FINANCIAL_INFO full-clause spans.** Example: the full CRIMINAL_RECORD clause "dømt for bedrageri (sak nr. TOSLO-2018-12345)" is tagged CRIMINAL_RECORD end-to-end, and `TOSLO-2018-12345` is **additionally** tagged GOV_ID as a nested span. This is a deliberate double-tag, not a conflict — it resolves the 32 CRIMINAL_RECORD and 31 FINANCIAL_INFO "type migrations": those were annotators picking only one of two valid simultaneous tags instead of applying both. See Cross-type precedence and overlap and CRIMINAL_RECORD §Overlap policy for the full worked example and the (final) reasoning for nesting over adjacency.
- **GOV_ID does NOT nest with DATE_TIME** on the same characters. A given substring is either a date or an ID reference number, never both.
- May co-occur (non-overlapping) with PERSON in the same "(Fødselsnummer: ...)" parenthetical.

#### Positive examples
1. `987654321` — value of "Org.nr.:" field, animal-welfare inspection report.
2. `120378-12345` — value of "(fødselsnummer: ...)" parenthetical attached to a named person.
3. `20231027-0045` — value of "Vår ref:" field, a case reference number.
4. `2023-08-9876 Oslo politidistrikt` — full clause with authority name per boundary rule.
5. `05123456789` — labeled explicitly "(D-nummer)" in `078956370 (Fødselsnummer), 05123456789 (D-nummer)`.
6. `TOSLO-2018-12345` — court-prefixed case number, "sak nr. TOSLO-2018-12345" clause.

#### Negative examples
1. `2018` alone (from `2018/45678`) — not tagged separately; it is structurally part of the case number.
2. `9876543210` under a "Kontonummer:" label — excluded from GOV_ID (belongs to FINANCIAL_INFO); the identical digit shape under "Org.nr.:" would be GOV_ID.
3. `98765432` (8 digits) under a "Telefon:" label — excluded from GOV_ID; 8-digit numbers under a phone label are NO_PHONE_NUMBER.
4. `121270` (bare 6 digits, date-shaped) — excluded as GOV_ID unless contiguously followed by 5 more digits forming the full 11-digit ID.

#### Resolved conflicts
- DATE_TIME × GOV_ID migration (202 total): a full 11-digit fødselsnummer/D-nummer string, or a date-shaped case-number prefix glued to a reference suffix, is tagged **GOV_ID in its entirety**; the leading 6 digits or leading date are never separately tagged DATE_TIME. `010175-54321` → GOV_ID only; `2018/45678` → GOV_ID only, not also DATE_TIME.
- Presence conflicts (1,485+/1,787 evidenced): resolved by the mechanical enumeration above plus field-label authority — every value following a trigger label in items 1–5 must be tagged, with no exceptions for unusual length or format.
- CRIMINAL_RECORD/FINANCIAL_INFO type migrations (32 + 31): resolved as intentional nesting, not exclusive alternation.
- NO_PHONE_NUMBER migration (6): resolved by field-label authority — a number under "Telefon:"/"Tlf:" is NO_PHONE_NUMBER even if its digit count matches a fødselsnummer/org.nr shape.

---

### NO_ADDRESS

#### Definition
The Norwegian street-address portion of a location: street name plus house number (with optional letter suffix and apartment/floor qualifier), taken from an "Adresse:" field or an equivalent in-sentence self-report ("Jeg bor på Granveien 14"). Does not include a bare city/place name or a bare postal code on their own.

#### Include
- Street + number: `Fjellveien 12`, `Fjellveien 22`, `Storgata 45`
- Street + number + letter suffix: `Fjellveien 12B`, `Storgata 22B`, `Granveien 12B`
- Street + number + apartment/floor qualifier: `Fjellstien 12B, Leilighet 3`, `Strandveien 12B, 3. etasje`
- Street + number + trailing postal code and city, when all of it appears together inside the Adresse field's own value: `Fjellveien 12, 8300 Svolvær`, `Fjellveien 12, Lødingen, 8410`
- In-sentence self-reported address ("Jeg bor på Granveien 14", "Jeg er naboen ... og bor på Granveien 14")

#### Exclude
- Bare city/place name alone with no street: `Oslo`, `Bergen`, `Trondheim`, `Drammen`, `Bærum`, `Majorstuen`, `Lierstranda`.
- Institution or business names, even if location-like: `Bærum sykehus`, `Rema 1000`.
- The value of a **"Poststed:" field taken alone** (e.g. "Poststed: 5055 Bergen") — never tag this whole field value as NO_ADDRESS.

#### Boundary rule
Full clause = street name + house number + any letter suffix + any apartment/floor qualifier, and — **only when they occur inside the same Adresse field value** — a trailing postal code + city.
- `Fjellveien 12, Lødingen` vs. `Fjellveien 12, Lødingen, 8410` → **longer** form.
- `Fjellstien 12B, Leilighet 3` vs. `Fjellstien 12B, Leilighet 3, 7012 Trondheim` → **longer** form.
- `Fjellveien 12, Leirvik i Sogn` vs. `Fjellveien 12, Leirvik i Sogn, 6870` → **longer** form.
- Do NOT extend a NO_ADDRESS span to swallow a separately-occurring "Poststed: 5055 Bergen" elsewhere in the record.

#### Overlap policy
- **NO_ADDRESS and POSTAL_CODE nest** when the postal code is physically written inside the Adresse field's own value (`8300` inside `Fjellveien 12, 8300 Svolvær` is tagged both NO_ADDRESS as part of the whole clause and, separately, POSTAL_CODE for just the 4 digits).
- **NO_ADDRESS and POSTAL_CODE are mutually exclusive on a "Poststed:" field.** There, only the 4 digits are POSTAL_CODE; the city/place word is tagged by neither type. This is field-conditioned nesting, not blanket nesting and not blanket exclusivity. Justification: NO_ADDRESS's own definition ("street addresses with house numbers") structurally excludes a bare "postal code + city" pair with no house number; POSTAL_CODE's own definition ("4 digits") is matched exactly by confining it to the digits.
- This deliberately **reverses the numeric majority in the old labels** for extremely common spans — e.g. `5000 Bergen` was tagged NO_ADDRESS 622 times vs. POSTAL_CODE 21 times in the old data. That majority is overridden going forward because it contradicts both types' own definitions, not because the count was wrong.

#### Positive examples
1. `Fjellveien 22` — "Adresse:" field, animal-owner record.
2. `Storgata 45` — "Adresse:" field, business owner record.
3. `Fjellveien 12, 8300 Svolvær` — Adresse field with embedded postal code and city; full clause per boundary rule (nested POSTAL_CODE `8300` also applies).
4. `Granveien 14` — self-reported neighbor address, "Jeg er naboen til Per Arne Halvorsen og bor på Granveien 14."
5. `Fjellstien 12B, Leilighet 3, 7012 Trondheim` — resolved boundary conflict, longer form mandated.

#### Negative examples
1. `Oslo` — a bare city name; excluded, no street present.
2. `5055 Bergen` (from a "Poststed:" field) — excluded from NO_ADDRESS entirely under the field-conditioned rule; only `5055` is POSTAL_CODE.
3. `Bærum sykehus` — an institution name, not a street address.
4. `Rema 1000` — a business name.

#### Resolved conflicts
- Boundary (5 rows, street+locality vs. street+locality+postal-code): resolved uniformly — mandate the longer form whenever the postal code is part of the same Adresse-field value.
- Presence (110 rows, e.g. `Fjellveien 12B, Bergen`, `Kirkeveien 22, 8000 Bodø`): always tag the Adresse field's full value.
- NO_ADDRESS×POSTAL_CODE overlap (28,195 occurrences; e.g. `5072 Bergen`: {NO_ADDRESS:228, POSTAL_CODE:33}, `5000 Bergen`: {NO_ADDRESS:622, POSTAL_CODE:21}, `0170 Oslo`: {NO_ADDRESS:6, POSTAL_CODE:113}): resolved by the field-conditioned rule above — none of these bare "NNNN Cityname" spans from a Poststed field should be tagged NO_ADDRESS going forward; tag only the 4-digit POSTAL_CODE.

---

### CRIMINAL_RECORD

#### Definition
CRIMINAL_RECORD is a verbatim clause naming a **conviction, sentence, criminal charge, formal accusation, police report, or investigator-stated suspicion of a specific criminal offense**, attributed to an identified or identifiable natural person, including the legal-process verb or noun that establishes it as a criminal matter (dømt for / domfellelse for / sonet dom for / anmeldt for / siktet for / mistanke om / politianmeldelse for), when one is present, plus any offense-defining noun phrase and a trailing time qualifier when present.

**A bare offense noun is sufficient on its own — no accompanying accusation/conviction verb is required.** This resolves a disagreement between two earlier drafts of this spec, one of which required a legal-process verb alongside the offense word; the project owner has resolved it in favor of the no-verb-required reading, matching the corpus's own plurality: `skatteunndragelse` appears 1,418 times, split CRIMINAL_RECORD 680 / FINANCIAL_INFO 456 / (formerly) CONTEXT_SENSITIVE 144 / ECONOMIC_STATUS 131 / POLITICAL_CASE 7 — CRIMINAL_RECORD is already the plurality even counting the many bare-noun instances with no accusation verb attached.

When a case/docket number is directly attached to the clause, it stays **inside** the CRIMINAL_RECORD span (the span is not cut short before it) and is additionally, separately tagged GOV_ID as a nested span — see Boundary rule and Cross-type precedence and overlap.

#### Include
- Convictions/sentences: `Dømt for vold i 2010`, `domfellelse for bedrageri i 2018`, `sonet en dom for vold mot offentlig tjenestemann`.
- Charges, reports, accusations under an active or past legal process: `anmeldt for trusler med kniv`, `politianmeldelse mot Olsen for trusler og ulovlig besittelse av et våpen`.
- Explicit investigative suspicion of a criminal act: `mistanke om skatteunndragelse`, `mistenker at hundene brukes i ulovlige kampaktiviteter`.
- Illegal possession/acts stated as such: `ulovlig våpenbesittelse`, `ulovlig besittelse av våpen`.
- Financial offenses framed with an offense noun, with or without an accusation verb: `skattesvindel`, `forfalskning av skattedokumenter`, `hvitvasking av penger` (see Precedence — this beats FINANCIAL_INFO/ECONOMIC_STATUS whenever crime-framing is present, verb or no verb).
- Threats/violence against a named victim stated as a specific incident, even without explicit legal-process wording, because these are themselves offenses under Norwegian law: `truet Jensen med en kjøkkenkniv`.
- Bare single-word offense nouns with no fuller clause available in the source: `fyllekjøring` (driving under influence) — must still be tagged even as one word, because Norwegian criminal vocabulary sometimes gives the annotator nothing more to extend the clause with.
- A criminal-record clause's own attached case/docket reference, e.g. `12345/2018` inside `dømt for bedrageri i sak 12345/2018` — kept inside the span (see Definition and Boundary rule).

#### Exclude
- Bare case/docket numbers and court names standing entirely alone, with **no** accusation/conviction/suspicion clause anywhere in the same sentence: `sak nr. 2018/45678, Oslo Tingrett`, `politisak nr. 2023/98765`, `Bergen Tingrett` used alone — GOV_ID only.
- Lawful, registered possession with no illegality asserted: `registrert jaktvåpen (rifle, registrert 2015)`, `eier en registrert rifle` — a registered, lawful weapon is not a criminal fact.
- Bare financial amounts/state with no accusation or offense word: `gjeld på over 500 000 NOK` → ECONOMIC_STATUS, not CRIMINAL_RECORD.
- Generic behavioural description with no legal-process language and no named per-se offense: `aggressiv atferd overfor dyr og kolleger` → BEHAVIORAL_PATTERN.
- Vague, non-specific mentions with no offense named: `kriminelle miljøer` used as a bare descriptor is weaker evidence than a named offense; defaults to CRIMINAL_RECORD only when it is the only reference to a documented association (corpus split 7 CRIMINAL_RECORD / 1 formerly-CONTEXT_SENSITIVE — with that type cut, this defaults to CRIMINAL_RECORD).

#### Boundary rule
Span = [optional leading conviction/accusation/suspicion verb or noun — optional because a bare offense noun already qualifies, see Definition] + [offense noun phrase, including its direct object/victim if stated] + [optional trailing time qualifier "i YYYY"/"fra YYYY"] + [any case/docket reference or court name+number directly attached to the same clause, kept **inside** the span rather than cut off before it].

- `trusler` → correct: `trusler mot en journalist` (include the victim/target).
- `domfellelse for bedrageri` → correct: `domfellelse for bedrageri i 2018` (include the trailing year).
- `dom for bedrageri` → correct: `dom for bedrageri i 2010`.
- `vold i nære relasjoner` → correct: `dom for vold i nære relasjoner` (pull in the leading noun that establishes it as adjudicated, not merely alleged).
- **Nesting example** (final; supersedes an earlier "stop before the number" draft rule): for "dømt for bedrageri i sak 12345/2018" — CRIMINAL_RECORD = `dømt for bedrageri i sak 12345/2018` (the whole clause including the case number), and GOV_ID is additionally, separately tagged on the nested substring `12345/2018`.
- Worked example from context *"Dømt for vold i 2010 (saksnr. 2010-12-3456), betinget dom."*: CRIMINAL_RECORD span = `Dømt for vold i 2010 (saksnr. 2010-12-3456)` — the clause now runs through the parenthetical case reference rather than stopping before it — and GOV_ID is additionally, separately tagged on the nested substring `2010-12-3456`. `betinget dom` is a second, adjacent CRIMINAL_RECORD span for a distinct fact after the comma (evidence: `betinget dom` appears 222 times as its own CRIMINAL_RECORD span) rather than being merged across the comma into the first span.

#### Overlap policy and Precedence
1. **Case/docket numbers inside a CRIMINAL_RECORD clause: GOV_ID nests, it does not sit adjacent.** When a case/docket number (`politisak nr. 2023/98765`, `sak nr. 2018/45678 Oslo Tingrett`, `2015-07-8765`) appears inside a criminal-record clause, the full CRIMINAL_RECORD clause is tagged end-to-end including the number, and the number is additionally, separately tagged GOV_ID on the same characters. This is a deliberate double-tag, decided by the project owner, overriding an earlier draft's adjacency rule. GOV_ID still owns the number's *own* type identity whenever no criminal-record clause surrounds it at all: `12345/2018` standing completely on its own, with no accusation/conviction language anywhere nearby, is GOV_ID 117 times vs. CRIMINAL_RECORD 2 times in the corpus — that statistic describes the standalone case, not the nested case.
2. **Financial crime: CRIMINAL_RECORD wins whenever crime-framing language is present, and an offense noun alone is enough.** If the phrase includes an offense noun (svindel, unndragelse, forfalskning, underslag, hvitvasking) — whether or not it is also introduced by an accusation/suspicion/conviction verb (mistanke om, dømt for, anmeldt for) — tag CRIMINAL_RECORD, not FINANCIAL_INFO or ECONOMIC_STATUS. Evidence: `skattesvindel` is CRIMINAL_RECORD 729 times vs. FINANCIAL_INFO 99 + ECONOMIC_STATUS 19 (118); `forfalsket skatteopplysninger` is CRIMINAL_RECORD 51 vs. FINANCIAL_INFO 7 + ECONOMIC_STATUS 8 (15). A phrase stating only an amount or a financial condition with no offense/accusation word (`gjeld på over 500 000 NOK`) is not CRIMINAL_RECORD at all.
3. **vs. BEHAVIORAL_PATTERN**: legal-process language or a named per-se offense (weapon + named victim) tips to CRIMINAL_RECORD; a bare description of conduct with no such language stays BEHAVIORAL_PATTERN.
4. **vs. the former CONTEXT_SENSITIVE type**: N/A — cut. Its "mistenker/mistanke om/ulovlig" suspicion spans move here; this is already the descriptive majority (`ulovlig våpenbesittelse`: CRIMINAL_RECORD 2,589 vs. former-CONTEXT_SENSITIVE 29).

#### Extraction-not-summarisation rule
Copy exact case and exact wording — do not normalize capitalization to look like a "clean" tag. Real violation found in data: label `'mistenker organisert kamphundaktivitet'` (lowercase "m") was applied where the source reads *"Andre opplysninger: Mistenker organisert kamphundaktivitet."* — the sentence-initial capital "M" was silently lowercased. Correct span: `Mistenker organisert kamphundaktivitet` (capital M, matching source exactly).

#### Positive examples
1. `Dømt for vold i 2010` — conviction verb + offense + year, correctly excludes an unattached trailing case reference elsewhere in the sentence (or includes it if directly attached — see Boundary rule nesting example).
2. `domfellelse for bedrageri i 2018` — same pattern, different offense.
3. `mistanke om skatteunndragelse` — suspicion language is the qualifying marker; no conviction needed.
4. `politianmeldelse mot Olsen for trusler og ulovlig besittelse av et våpen` — names the accused, the process, and two offenses in one coordinated clause; kept as one span.
5. `ulovlig våpenbesittelse` — self-contained illegality assertion, no legal-process verb needed.
6. `dømt for bedrageri i sak 12345/2018` — nesting worked example (see Boundary rule); GOV_ID `12345/2018` nests inside it.

#### Negative examples
1. `eier en registrert rifle` — lawful, registered possession; excluded.
2. `gjeld på over 500 000 NOK` — financial state, no offense/accusation word; ECONOMIC_STATUS.
3. `aggressiv atferd overfor dyr og kolleger` — conduct with no legal-process language; BEHAVIORAL_PATTERN.
4. `sak nr. 2018/45678, Oslo Tingrett` — a case reference with no surrounding criminal-record clause; GOV_ID only, not CRIMINAL_RECORD.

#### Resolved conflicts
- `trusler` vs. `trusler mot en journalist` → **longer form**.
- `domfellelse for bedrageri` vs. `domfellelse for bedrageri i 2018` → **longer form**.
- `2018/12345` vs. `case number 2018/12345` → **neither is CRIMINAL_RECORD**; both are GOV_ID.
- `trusler mot en nabo` vs. `våpenbeslag hos Hansen i 2018 etter en episode med trusler mot en nabo` → **split** into two spans: `trusler mot en nabo` and `våpenbeslag hos Hansen i 2018` — do not merge two distinct criminal facts into one span just because they are causally linked.
- Presence conflict `forfalskning av veterinærattester` (missed in one copy) → **must be tagged** (offense noun "forfalskning" is a per-se qualifier).
- Presence conflict `fyllekjøring` → **must be tagged**, a named offense even as a single word.

---

### POSTAL_CODE

#### Definition
The 4-digit Norwegian postal code number by itself, exactly as it appears in a "Poststed:" field or embedded inside a NO_ADDRESS clause. Never includes the accompanying place name. This is the **one documented exception to the Full clause global rule** — the type's own definition caps the span at the number itself.

#### Include
- The 4 digits alone, including forms with a leading zero: `5055`, `7048`, `1358`, `0182`, `0170`.
- The 4 digits when embedded inside a NO_ADDRESS clause (nested tagging): `8300` inside `Fjellveien 12, 8300 Svolvær`.

#### Exclude
- The trailing place/city name (`Bergen`, `Trondheim`, `Oslo`, `Svolvær`, `Stord`) — not part of the 4-digit code; belongs to neither type in this cluster.
- Any 4-digit number functioning as a **year** (`2018`, `2020`, `2007`) — DATE_TIME, even though shape-identical (`2018`: {DATE_TIME: 6,713, POSTAL_CODE: 1} — the single POSTAL_CODE tagging is the error).
- Any 4-digit fragment of a GOV_ID case number (`2345` inside a longer case-number token) (`2345`: {POSTAL_CODE: 59, GOV_ID: 1} — the GOV_ID tagging is the error; check field context).

#### Boundary rule
Exactly 4 digits, no more, no less — never the place name.
- `...Kommune: Bergen Poststed: >>>5055<<< Bergen...` → span is `5055` only.
- `...Poststed: >>>1358<<< Jar...` → span is `1358` only.
- `...Fylke: Vestland Kommune: Voss Poststed: >>>5700<<< Voss...` → span is `5700` only.
- `1234` vs. `1234 Bygda` → mandate the **shorter** form, `1234` — this is the one type where full-clause does *not* mean "longer."

#### Overlap policy
- May be nested inside a NO_ADDRESS span when the 4 digits occur inside the Adresse field's own text.
- Mutually exclusive with NO_ADDRESS when the 4 digits occur inside a standalone "Poststed:" field (no house number present).
- Mutually exclusive with DATE_TIME and GOV_ID — a given 4-digit run is postal code, year, or case-number fragment, never two of these at once; disambiguate by field label/surrounding sentence.

#### Positive examples
1. `5055` — "Poststed: 5055 Bergen" field.
2. `7048` — "Poststed: 7048 Trondheim" field.
3. `1358` — "Poststed: 1358 Jar" field.
4. `0182` — "Poststed: 0182 Oslo" field, leading-zero form.
5. `8300` — nested inside NO_ADDRESS clause "Fjellveien 12, 8300 Svolvær".

#### Negative examples
1. `1234 Bygda` — excluded in favor of `1234` alone.
2. `2018` used as a year ("Org.nr.: ... Dato: 27. oktober 2018") — excluded; DATE_TIME.
3. `2345` as a fragment of a longer GOV_ID case number — excluded.
4. `5409 Stord` — excluded in favor of `5409` alone.

#### Resolved conflicts
- `1234` vs. `1234 Bygda` → mandate the shorter, digits-only form.
- Presence (333 rows, e.g. `5072`, `8410`, `0182`) → always tag the 4 digits of a Poststed field.
- NO_ADDRESS overlap (28,195 occurrences) → resolved jointly with NO_ADDRESS — field-conditioned nesting, deliberately reversing the old majority tagging (see NO_ADDRESS §Overlap policy).

---

### NO_PHONE_NUMBER

#### Definition
A Norwegian telephone number as it appears under a "Telefon:"/"Tlf:"/"Telefonnummer:" label: 8 digits, optionally grouped with spaces, optionally prefixed with a country code.

#### Include
- 8 digits, solid: `97512483`, `95784213`.
- 8 digits, grouped (`XXX XX XXX`): `975 12 889`, `924 87 513`.
- With `+47` prefix: `+47 952 83741`.
- With bare `47` prefix, no `+`: `47 987 65 432`.
- Any digit string under a "Telefon:"/"Tlf:" label, **regardless of its digit count**, including ones that happen to be 11 digits and shape-match a fødselsnummer (`12087567890`, `01017598765`) — field label wins over shape.
- Redaction placeholders `[REDACTED]`/`[redacted]` when they follow a "Telefon:"/"Tlf:" label.

#### Exclude
- 9-digit numbers under an "Org.nr.:" label — GOV_ID, even if superficially phone-number-like.
- 11-digit numbers under a "Fødselsnummer:"/"personnummer:" label — GOV_ID, not phone; the distinguishing factor is the field label, not the digit count.

#### Boundary rule
The digits (and any interior spaces/plus-sign that are part of the written number) only — stop at the following punctuation or field label.
- `Telefon: >>>97512483<<< E-post:` → span is `97512483`.
- `Telefon: >>>+47 952 83741<<< E-post:` → span is `+47 952 83741` (include the `+47` prefix).
- `Telefon: >>>47 987 65 432<<< E-post:` → span is `47 987 65 432` (include the bare prefix likewise).

#### Overlap policy
- Mutually exclusive with GOV_ID and DATE_TIME on the same characters — disambiguate purely by field label, never by digit-count heuristics.
- Never overlaps EMAIL_ADDRESS (adjacent field, not the same span).

#### Positive examples
1. `97512483` — "Telefon:" field, 8-digit solid form.
2. `975 12 889` — "Telefon:" field, grouped form.
3. `+47 952 83741` — "Telefon:" field with country code.
4. `47 987 65 432` — "Telefon:" field, bare country-code prefix.
5. `924 87 513` — "Telefon:" field, most common grouped pattern in the corpus.

#### Negative examples
1. `987654321` under an "Org.nr.:" label — 9-digit org number, not a phone number.
2. `9876543210` under an "ID-nummer" or "Org.nr." label — GOV_ID, not NO_PHONE_NUMBER, even though 10 mislabels exist in the corpus.
3. `01017598765` under a "Fødselsnummer:" label — GOV_ID, not phone.
4. `98765432` under a "Telefon:" label — still NO_PHONE_NUMBER; do not second-guess a plausible 8-digit number under the correct label.

#### Resolved conflicts
- Presence (10 rows, e.g. `12087567890`, `18067567890`, `01017598765`, `01016543210`, `01027043210`): 11-digit, fødselsnummer-shaped strings under a "Telefon:" label — tag as NO_PHONE_NUMBER because the field label says "Telefon:"; do not additionally tag GOV_ID.
- Type migration (6 rows, e.g. `4758 12 34567` → GOV_ID, `9876543210` → GOV_ID): when the label is "Org.nr."/"Fødselsnummer"/"ID-nummer", tag GOV_ID only, never NO_PHONE_NUMBER.
- Redaction placeholders (`[REDACTED]`, `[redacted]`): tag NO_PHONE_NUMBER only when immediately following a "Telefon:"/"Tlf:" label; the same placeholder following "Fødselsnummer:" or "E-post:" is a different type.

---

### EMAIL_ADDRESS

#### Definition
A complete email address in `local-part@domain` form, exactly as printed after an "E-post:" label.

#### Include
- Standard address: `anette.strand@email.com`, `line.olsen@email.com`.
- Norwegian-letter local parts, printed verbatim: `hildegunn.sæbo@email.com`.
- Numbered/disambiguated local parts: `astrid.nilsen.1978@email.com`.
- Redaction placeholders `[REDACTED]`/`[redacted]` when they follow an "E-post:" label.

#### Exclude
- Any string without an `@` sign.
- A redaction placeholder following a non-email label (`Telefon:`, `Fødselsnummer:`) — that placeholder is a different type.

#### Boundary rule
The full `local-part@domain` string only, stopping at the first following whitespace or field label; never include leading "E-post:" or trailing punctuation.
- `E-post: >>>anette.strand@email.com<<< Anonym varsler:` → span is `anette.strand@email.com` exactly.
- `E-post: >>>hanne.kristin.haugen@email.no<<< Anonym varsler:` → span is the full address including the multi-dot local part.
- `E-post: >>>tobias.skogly@email.no<<< Anonym varsler:` → span stops at `.no`.

#### Overlap policy
- Never overlaps any other type in this cluster — always its own separate field's value, adjacent to but not overlapping a NO_PHONE_NUMBER or PERSON span in the same record.

#### Positive examples
1. `anette.strand@email.com` — "E-post:" field.
2. `hanne.kristin.haugen@email.no` — "E-post:" field, `.no` TLD.
3. `elise.kverneland@email.com` — "E-post:" field.
4. `hildegunn.sæbo@email.com` — Norwegian-letter local part, printed verbatim.
5. `tobias.skogly@email.no` — "E-post:" field, unaffected by a nearby `+47`-prefixed phone number.

#### Negative examples
1. `[REDACTED]` following a "Fødselsnummer:" label — belongs to GOV_ID here.
2. `[redacted]` following a "Telefon:" label — belongs to NO_PHONE_NUMBER here.
3. Bare domain fragments without a local part — not present in evidence, would not qualify regardless.
4. A local part alone without `@domain` — incomplete, excluded per definition.

#### Resolved conflicts
- Presence (2 rows, both `[REDACTED]`/`[redacted]`): tag EMAIL_ADDRESS only when the placeholder follows an "E-post:" label; do not blanket-tag every redaction placeholder as every type.

---

### FAMILY_RELATION

Current spans: 30,154. Boundary conflicts: 1,032 (2nd-worst in the corpus). Presence conflicts: 532. Type migrations: 31.

#### Definition
FAMILY_RELATION tags a clause naming a family, kinship, or intimate-partnership relationship between the data subject and another (usually named) individual: spouse/partner, child, parent, sibling, or equivalent (adoptive, step-, in-law). It includes both the relationship word and, when a name is given in the same clause, the full clause through that name.

#### Include
- Kinship nouns with their full descriptive clause: `to barn (10 og 14 år)`, `sønn fra et tidligere forhold`, `mor til to barn (8 og 12 år gamle) fra et tidligere forhold med Lars Ove Hansen`.
- Marital/partnership status with named spouse/partner: `gift med Astrid Olsen Åsberg`, `samboerforhold med Per Arne Olsen`, `Samboer med Lars Olsen`.
- Relationship-ending facts: `skilsmisse`, `separasjon`, `skilt fra sin tidligere ektefelle`.
- Household/family collectives naming a family unit tied to a surname: `Familien Eriksen` (see Overlap policy for why the surname itself is not additionally tagged PERSON).
- Third-party relational identifiers a witness/reporter uses to explain how they know the
  subject, **only when they express kinship or intimate partnership**: `svigerinne til
  Hans Petter Wiik`, `eksmannen til Raymond`.
- Not tagged: a non-kinship social tie, however specific — `nabo til Hans Petter Wiik`,
  `venn av Raymond`, `kollega av`, plain `naboen`. A neighbour or friend is neither
  family nor an intimate partner, so it falls outside this type's definition, and no
  other type covers it. Leave it untagged, as with religious affiliation and hobby-club
  membership. (Earlier drafts listed `venn av Raymond` and `nabo til Hans Petter Wiik`
  as positive examples, contradicting both the definition above and the bullet's own
  kinship condition; that was an error.)

#### Exclude
- `eieren` (the owner) — a property/animal-ownership role, never FAMILY_RELATION, despite 4 stray tags vs. 23 correct EMPLOYMENT_INFO/other tags.
- `nestlederen` (deputy leader) — an organizational role; EMPLOYMENT_INFO.
- `vold i nære relasjoner` (domestic violence) — CRIMINAL_RECORD (665 of the corpus's own tags agree), not FAMILY_RELATION (only 19 stray tags), even though the phrase contains "relasjoner."
- `besøksforbud` (restraining order) — a legal/criminal sanction; CRIMINAL_RECORD, even when it arises from a family dispute.
- Bare age numerals detached from a kinship noun: `10 år` on its own is DATE_TIME; only tag the age when it sits inside the family-member clause itself (`to barn, Elias (10) og Sofia (7)` — the ages are part of the FAMILY_RELATION clause here because they are the parenthetical of "barn").

#### Boundary rule
Span = the relationship noun/phrase **plus** any named individual and descriptive qualifier in the same clause. When the clause names a person, the FAMILY_RELATION span runs through the full name's characters; those same characters are **also** tagged PERSON (deliberate nesting, not a conflict).
- `gift` vs. `gift med Astrid Olsen Åsberg` → **longer form**; `Astrid Olsen Åsberg` additionally tagged PERSON.
- `partner` vs. `partner: Kjell Ivar Hansen` → **longer form** (including the label-colon, directly attached); `Kjell Ivar Hansen` additionally PERSON.
- `barn` vs. `to barn, Sondre (15) og Maren (12)` → **longer form**; if the two children are each independently named, prefer **splitting into two FAMILY_RELATION spans** (`Sondre (15)` and `Maren (12)`) rather than one merged span. `Sondre` and `Maren` additionally tagged PERSON.
- `ektefellen` vs. `ektefellen Astrid Knudsen` → **longer form**; `Astrid Knudsen` additionally PERSON.
- `Familien Eriksen` (surname-only collective) → tag the full `Familien Eriksen` as FAMILY_RELATION; do **not** additionally tag `Eriksen` as PERSON — a bare surname attached to "Familien" names a household, not an identified individual.

#### Overlap policy
- **FAMILY_RELATION + PERSON nesting is the default, not the exception.** Of 1,974 FAMILY_RELATION spans in the corpus containing an embedded proper name, 1,855 (94.0%, colloquially "~95%") already have that name separately tagged PERSON; only 119 (6.0%) do not, and nearly all of those are the `Familien X` surname-collective pattern. Whenever a FAMILY_RELATION clause contains a full given-name-plus-surname, nest-tag that name PERSON on the same characters.
- Never shares characters with SEXUAL_ORIENTATION — when an orientation adjective is present in the relationship clause, the whole clause goes to SEXUAL_ORIENTATION instead.
- Never shares characters with CRIMINAL_RECORD — violence/legal-sanction vocabulary (`vold i nære relasjoner`, `besøksforbud`) is CRIMINAL_RECORD only, even inside a sentence that also describes a family relationship.
- Never shares characters with HEALTH_INFO (`barn` is never HEALTH_INFO).
- An age in years is DATE_TIME on its own, but when it is the parenthetical of a named/counted family member it is absorbed into the FAMILY_RELATION span and not separately tagged DATE_TIME.

#### Positive examples
1. `to barn (10 og 14 år)` in "* Familie: Gift med Anne Lise Olsen, to barn (10 og 14 år)." — full clause with count and ages.
2. `Gift med Per Anders Hansen, ingen barn` — full field-value clause; note "gift with X" and "no children" are two distinct facts, so this spec recommends splitting into `Gift med Per Anders Hansen` + `ingen barn` per the one-clause-one-fact principle.
3. `sønn fra et tidligere forhold` in "...Olsen har en sønn fra et tidligere forhold, Jonas Olsen (Fødselsnummer: 05119923456)." — `Jonas Olsen` additionally PERSON.
4. `mor til to barn (8 og 12 år gamle) fra et tidligere forhold med Lars Ove Hansen` — one genuine clause describing one relationship structure; `Lars Ove Hansen` additionally PERSON.
5. `samboerforhold med Lars Erik Olsen` in "...Holsts personlige forhold viste at hun er i et samboerforhold med Lars Erik Olsen, og at de har en felles sønn, Elias Olsen..." — two family facts in one sentence: tag `samboerforhold med Lars Erik Olsen` and, separately, `felles sønn, Elias Olsen` as two spans.

#### Negative examples
1. `eieren` in an animal-welfare inspection — never FAMILY_RELATION.
2. `nestlederen` (deputy leader) — EMPLOYMENT_INFO, not kinship.
3. `vold i nære relasjoner` — CRIMINAL_RECORD (665:19:45:5 vote strongly favors CRIMINAL_RECORD).
4. `10 år` standing alone — DATE_TIME.

#### Resolved conflicts
- `barn` vs. `to barn` → **longer form** whenever a quantifier is present.
- `partner` vs. `partner: Kjell Ivar Hansen`; `ekskone` vs. `ekskone, Kari Olsen`; `kona` vs. `separert fra kona`; `gift` vs. `gift med [Name]`; `ektefellen` vs. `ektefellen Astrid Knudsen`; `samboerskap` vs. `samboerskap med Marit Olsen`; `ektemannen` vs. `ektemannen Per Hansen`; `eks-partner` vs. `eks-partner Per Hansen`; `Samboer` vs. `Samboer med Lars Olsen` → **longer form** in every pair; named individual additionally tagged PERSON.
- `gift` vs. `gift med Astrid` (bare first name, no surname) → **longer form** for FAMILY_RELATION regardless; tag `Astrid` PERSON only if the corpus's PERSON policy tags bare first names elsewhere in the same document.
- `ektefelle` vs. `ektektefelle` → the second is a typo (duplicated syllable) in the source; tag the literal string as it appears — do not "fix" it (Global rule 1).
- `svoger` vs. `tidligere svoger` → **longer form**.
- `felles barn` vs. `to felles barn` → **longer form**.
- `skilsmisse` vs. `skilsmisse fra sin tidligere partner` → **longer form**.
- `forhold til en ansatt` vs. `personlige forhold til en ansatt` → **longer form**, but route to SEXUAL_ORIENTATION instead if the same clause discloses orientation.
- `barn`: {HEALTH_INFO: 1, FAMILY_RELATION: 992} → **mandate FAMILY_RELATION**.
- `Lars Jensen`, `Ida`, `Markus`, `Bjørn Olsen`, etc. migrating to PERSON → **not an error, intended nested overlap**; both tags are correct simultaneously.
- `husband` → also SEXUAL_ORIENTATION → **mandate FAMILY_RELATION only**.
- `besøksforbud` {CRIMINAL_RECORD: 121, former-CONTEXT_SENSITIVE: 91, FAMILY_RELATION: 8, BEHAVIORAL_PATTERN: 2} → **mandate CRIMINAL_RECORD**.

---

### FINANCIAL_INFO and ECONOMIC_STATUS: why they remain two separate types

**Recommendation: keep FINANCIAL_INFO and ECONOMIC_STATUS separate**, governed by one hard mechanical rule: presence of a concrete quantified/nameable financial fact (FINANCIAL_INFO) vs. a purely evaluative characterization of a person's overall financial condition (ECONOMIC_STATUS).

Corpus-wide validation of this rule:

| Metric | Count | % |
|---|---|---|
| FINANCIAL_INFO spans total | 24,036 | — |
| FINANCIAL_INFO spans containing a digit | 18,402 | 76.6% |
| ECONOMIC_STATUS spans total | 15,221 | — |
| ECONOMIC_STATUS spans containing a digit | 3,938 | 25.9% |
| ECONOMIC_STATUS spans containing an explicit NOK/kr amount | 3,915 | 25.7% |
| ECONOMIC_STATUS spans containing a financial-crime word (skatteunndragelse/forfalsk*/svindel/bedrageri/unndragelse) | 866 | 5.7% |

Reading of these numbers: the two types are already mostly separable by this rule in the raw data — three-quarters of everything currently called FINANCIAL_INFO is a hard number; three-quarters of everything currently called ECONOMIC_STATUS is *not* a number, it's a judgement phrase ("sliter økonomisk", "dårlig økonomi", "økonomisk press", "bekymret for eierens økonomiske situasjon"). The remaining 25.7% — ECONOMIC_STATUS spans that are actually NOK amounts (e.g. `gjeld på over 500 000 NOK` tagged ECONOMIC_STATUS 106 times vs. FINANCIAL_INFO 65 times for the identical string) — is the migration bug this precedence rule fixes going forward, not a reason to merge the types.

FINANCIAL_INFO spans are short, factual, high-sensitivity PII (median length 11 chars — account numbers, exact NOK figures, bank names) suitable for strict redaction; ECONOMIC_STATUS spans are long, narrative, low-precision inferences (**median length 25 chars**, up to 170) suitable for a "sensitive inference" handling path. Collapsing them would force one redaction policy onto two different risk profiles. EMPLOYMENT_INFO is kept as its own type with no merge question attached to it.

---

### FINANCIAL_INFO

#### Definition
FINANCIAL_INFO is any concrete, verifiable financial fact about a named person or organization: a specific monetary amount, an account/loan/case number, a named creditor or bank, a specific income figure, or a specific named debt/financial instrument — regardless of whether it is framed positively or negatively. If the span can be read out as a fact for a spreadsheet cell ("amount: X", "creditor: Y"), it is FINANCIAL_INFO.

#### Include
- Any NOK/currency amount, however formatted (`500 000 NOK`, `500.000 NOK`, `1,5 millioner NOK`, `120,000 NOK`).
- Named financial institutions/creditors attached to a debt or account (`DNB`, `Santander`, `Sparebanken Vest`, `Fjordbanken`, `Lindorff`) when identifying who money is owed to/held with.
- Specific debt/credit instruments even without a number, when the instrument itself is the fact: `misligholdte lån`, `ubetalte fakturaer`, `kredittkortgjeld`, `pant i eiendom`, `inkassosaker`.
- Government IDs/account numbers appearing in a financial context, unless a more specific type (GOV_ID) applies (see Cross-type precedence and overlap).
- Bare generic financial nouns (`gjeld`, `debts`, `utestående lån`) when no evaluative wrapper is present — default winner per the tie-break rule below.

#### Exclude
- Pure evaluative wrappers with no attached number/named instrument (`sliter økonomisk`, `dårlig økonomi`, `økonomisk press`) — ECONOMIC_STATUS.
- Spans whose primary content is a criminal-law characterization (`skatteunndragelse`, `forfalskning av skattemeldinger`, `svindel`) — CRIMINAL_RECORD by precedence, even though financially themed.
- Employment/company identity alone with no financial content (`Sørensen Fisk AS` as an employer name) — EMPLOYMENT_INFO, unless the company appears specifically as a financial counterparty (e.g. "lån til Sørensen Fisk AS").

#### Boundary rule
Tag the complete quantified financial clause: the amount together with its qualifier ("over", "estimert til", "på anslagsvis"), its direct preposition phrase naming the debt type or creditor, and any appositive supplying a second quantified fact joined by "inkludert"/comma. Do not truncate to the bare number if a qualifier or creditor directly attaches; do not truncate to the bare noun ("gjeld") if a number directly attaches.
- `over 500 000 NOK` — not `500 000 NOK`. The leading "over" is a qualifier and must stay.
- `gjeld på over 700.000 NOK, inkludert misligholdte lån og ubetalte skatter` — not `gjeld` and not the bare amount; the debt figure plus its itemized appositive is one span.
- `forfalskning av skattedokumenter fra 2021 og 2022` — per Precedence this whole clause is CRIMINAL_RECORD, not FINANCIAL_INFO, but it illustrates the same full-clause mechanic (trailing date qualifier stays attached).
- `unexplained cash deposits totaling 120,000 NOK` — the qualifying participle phrase stays attached; do not shrink to `120,000 NOK` alone.

#### Overlap policy and Precedence
- **CRIMINAL_RECORD > FINANCIAL_INFO > ECONOMIC_STATUS** whenever the span's head word/phrase names a criminal offense (see Cross-type precedence and overlap for the full chain, including the "no accusation verb required" rule). A separate, textually distinct NOK amount elsewhere in the same sentence that is not part of the offense-naming clause is still tagged FINANCIAL_INFO independently (e.g. "dømt for skatteunndragelse. Gjelden hans er 550 000 NOK" → `skatteunndragelse` = CRIMINAL_RECORD, `550 000 NOK` = FINANCIAL_INFO, two spans).
- **Tie-break default:** a bare financial noun with no number and no evaluative wrapper (`gjeld`, `debts`, `utestående lån`, `gjeldsforpliktelser`) defaults to **FINANCIAL_INFO** rather than ECONOMIC_STATUS — it still names a financial instrument/fact, however unquantified.
- FINANCIAL_INFO wins over GOV_ID when the number is explicitly a monetary amount; GOV_ID wins when the number is explicitly a fødselsnummer/case/reference number with no currency unit (`9876543210`, `2023-54321`, `Lån-4567890123` are GOV_ID-shaped identifiers, not amounts).
- GOV_ID nests inside a FINANCIAL_INFO full-clause span on the same basis as it nests inside CRIMINAL_RECORD (see Cross-type precedence and overlap).

#### Positive examples
- `over 500 000 NOK` (context: "...har en betydelig gjeld (over 500.000 NOK)...") — quantified debt amount.
- `gjeld på over 700 000 NOK, inkludert misligholdte lån til DNB og gjeld til private kreditorer` — full clause: amount + itemized creditor list.
- `over 1,5 millioner NOK` (context: "en aksjekonto med over 1,5 millioner NOK") — named account + amount.
- `DNB` (context: "lån nr. 1234567890... inkludert DNB") — named creditor institution.
- `ubetalte skatter` (context: "...ubetalte skatter på 520 000 NOK...") when it stands with its amount as one clause — specific tax-debt fact, not an offense name.
- `3,5 millioner NOK` (context: "Dette representerer skatteunndragelse på anslagsvis 3,5 millioner NOK") — the amount portion is FINANCIAL_INFO even though `skatteunndragelse` in the same sentence is CRIMINAL_RECORD; two spans.

#### Negative examples
- `skatteunndragelse` — NOT FINANCIAL_INFO; names a criminal offense, CRIMINAL_RECORD wins. Historically split 680 CRIMINAL_RECORD / 456 FINANCIAL_INFO / 131 ECONOMIC_STATUS — the spec now forces one answer.
- `sliter økonomisk` — NOT FINANCIAL_INFO; no number, no named instrument → ECONOMIC_STATUS.
- `Sørensen Fisk AS` (as employer identity, no debt/loan context) — NOT FINANCIAL_INFO; EMPLOYMENT_INFO.
- `forsøk på skattesvindel` — NOT FINANCIAL_INFO; "svindel" is an offense noun → CRIMINAL_RECORD, historically already the majority (9/12 instances).

#### Resolved conflicts
- `500 000 NOK` vs. `over 500 000 NOK` → **longer form**.
- `gjeldspost` vs. `gjeldspost på over 500.000 NOK tilknyttet DNB` → **longer form**.
- `700,000 NOK` (FINANCIAL_INFO:1021 vs. ECONOMIC_STATUS:4) → **FINANCIAL_INFO** confirmed as the already-overwhelming majority.
- `debts exceeding 550,000 NOK` (ECONOMIC_STATUS:10 vs. FINANCIAL_INFO:6, wrong majority) → **FINANCIAL_INFO** mandated (contains an amount, overriding the historical majority).
- `forfalskning av skattedokumenter` vs. `forfalskning av skattedokumenter fra 2021 og 2022` → **longer form** AND reassign both to **CRIMINAL_RECORD**, not FINANCIAL_INFO.

---

### ECONOMIC_STATUS

#### Definition
ECONOMIC_STATUS is a subjective, evaluative characterization of a person's or organization's overall financial condition — typically hedged, third-party, rumor-based observation language from an informant/tipster — that does **not** itself state a specific number, account, creditor, or named debt instrument. If the span answers "how well off are they, in someone's opinion?" rather than "what specific financial fact is documented?", it is ECONOMIC_STATUS.

#### Include
- Hedged hardship judgements: `sliter økonomisk`, `har økonomiske problemer`, `dårlig økonomi`, `begrenset økonomi`, `økonomisk ustabil situasjon`.
- Wealth judgements (the definition covers wealth as well as hardship, even though none appeared in the smaller evidence sample — a hypothetical `åpenbart velstående` would qualify equally; the absence of positive-wealth examples reflects a corpus skew toward hardship tips, not a scope restriction).
- Narrative descriptions of financial *behavior/situation* used as circumstantial evidence, without a figure: `begrensede økonomiske midler`, `vansker med å få endene til å møtes`, `bekymret for eierens økonomiske situasjon`.
- `mistet jobben` / `pensjonert og har begrenset inntekt` when used to characterize reduced financial capacity (income-status judgement), not merely to state an occupation (contrast with EMPLOYMENT_INFO's `pensjonist` used to answer an occupation question).

#### Exclude
- Any span containing a NOK/kr amount → FINANCIAL_INFO (this is the fix for the 25.7% contamination measured above).
- Any span whose head word names a criminal offense (`skatteunndragelse`, `forfalskning`, `svindel`) → CRIMINAL_RECORD.
- Bare financial nouns with no evaluative language (`gjeld`, `debts`) → FINANCIAL_INFO by the tie-break default.
- Pure occupational statements with no hardship/wealth framing (`er pensjonist` answering "hvilket yrke har du") → EMPLOYMENT_INFO.

#### Boundary rule
Tag the complete evaluative clause, including the hedging frame the informant uses ("har hørt rykter om at", "mistenker at", "virker som") only up to the point the object of concern begins; the object clause itself is the span. Include trailing cause/effect qualifiers that are part of the same judgement.
- `sliter økonomisk og ikke har råd til for til sauene` — the hardship judgement plus its stated consequence is one full clause, not truncated to `sliter økonomisk`.
- `bekymret for eierens økonomiske situasjon` — the concern-frame plus its object is the span; do not shrink to `økonomiske situasjon` alone.
- `har vanskeligheter med å få endene til å møtes` — idiomatic full clause; do not truncate to `vanskeligheter`.
- `økonomisk søksmål` vs. `pågående økonomisk søksmål` → **longer form**; "pågående" (ongoing) is load-bearing.

#### Overlap policy and Precedence
- **CRIMINAL_RECORD > FINANCIAL_INFO > ECONOMIC_STATUS.** ECONOMIC_STATUS is the lowest-precedence type in this chain: any number, named creditor, named instrument, or offense word anywhere in the candidate span promotes it to FINANCIAL_INFO or CRIMINAL_RECORD instead.
- Where BEHAVIORAL_PATTERN could also apply (`spillegjeld`, `mislykket investeringsprosjekt i kryptovaluta`, `gambling losses`), ECONOMIC_STATUS wins when the span characterizes the *financial outcome/condition* ("has gambling debt"); BEHAVIORAL_PATTERN wins when the span characterizes the *conduct/habit* itself ("gambles compulsively"). Default to ECONOMIC_STATUS for outcome-framed spans within this type's own boundary. A clinical frame (`diagnostisert spillavhengighet`) is HEALTH_INFO. Confirmed by the project owner; see Open question 7.

#### Positive examples
- `sliter økonomisk og ikke har råd til for til sauene` — hardship judgement with stated consequence, no number.
- `dårlig økonomi` (context: "Mistanker om dårlig økonomi hos restauranten") — pure qualitative judgement about a business.
- `bekymring for økonomisk bærekraft hos senteret` — evaluative concern about sustainability, no figure.
- `begrensede økonomiske midler` (context: inferred from "kjøre en gammel, slitt varebil") — circumstantial wealth inference, no number.
- `økonomisk ustabil situasjon mistenkes` — hedged, evaluative, no figure.

#### Negative examples
- `gjeld på over 700 000 NOK` — NOT ECONOMIC_STATUS despite appearing inside an "økonomiske problemer" narrative; a quantified figure → FINANCIAL_INFO. (Historically mislabeled ECONOMIC_STATUS 106 times for the closely related `gjeld på over 500 000 NOK` string — that majority was wrong under this rule.)
- `skattesvik` — NOT ECONOMIC_STATUS; names an offense → CRIMINAL_RECORD.
- `mistet jobben` alone, answering an occupation question — NOT ECONOMIC_STATUS; EMPLOYMENT_INFO, unless paired with an explicit hardship-consequence clause ("mistet jobben og sliter nå økonomisk"), in which case the hardship clause is ECONOMIC_STATUS and the job-loss clause is EMPLOYMENT_INFO as two spans.
- `utestående gjeld på 789 000 NOK` — NOT ECONOMIC_STATUS; quantified → FINANCIAL_INFO. The short form `utestående gjeld` (no figure) in the same document also resolves to FINANCIAL_INFO, by the tie-break default — both forms land on FINANCIAL_INFO, eliminating what looked like a conflict.

#### Resolved conflicts
- `gjeld` vs. `gjeld til DNB` → both resolve to **FINANCIAL_INFO** (bare noun defaults FINANCIAL_INFO; named creditor is FINANCIAL_INFO).
- `betydelig gjeld` vs. `betydelig gjeld (over 500.000 NOK)` → **longer form**, and it is **FINANCIAL_INFO** (quantified), not ECONOMIC_STATUS.
- `høy inntekt` vs. `tilsynelatende høy inntekt` → **longer form**, `tilsynelatende høy inntekt`, and it stays **ECONOMIC_STATUS** (no number).
- `forfalskning av skattemeldinger` (FINANCIAL_INFO:129 / ECONOMIC_STATUS:84 / CRIMINAL_RECORD:241 / former-CONTEXT_SENSITIVE:77) → **CRIMINAL_RECORD** only.
- `gjeld på over 700 000 NOK til flere kreditorer` (ECONOMIC_STATUS:29 vs. FINANCIAL_INFO:4, wrong majority) → **FINANCIAL_INFO**.

---

### EMPLOYMENT_INFO

#### Definition
EMPLOYMENT_INFO is any span identifying a named person's occupation, job title, professional role, employer/workplace, or business ownership position — including a bare occupation noun with no employer named, and including a bare employer/company name with no title attached, as long as it identifies that person's real, specific work situation (not a hypothetical or a third party's unrelated employer).

#### Include
- Bare occupation/role nouns referring to a real, specific person's actual job: `veterinærassistent`, `lærer`, `barista`, `servitør`, `butikkmedarbeider`, `pensjonist`/`pensjonert lærer` (when answering an occupation question). These are the majority of real spans in the corpus — excluding them would silently drop most of the type's true positives.
- Coordinated ownership/management titles as one full clause: `eier og daglig leder`, `daglig leder og eier`, `styreleder og daglig leder`.
- A bare company/employer name (`Sørensen Fisk AS`) when it identifies where the person works/owns a business and no role word is attached in the same clause.
- Workplace-condition statements about the subject's own business: `Flere ansatte har sluttet den siste tiden` (staff turnover at the subject's workplace).
- `forretningspartner` (business partner) — always EMPLOYMENT_INFO, never FAMILY_RELATION; a generic `partner` with no "forretnings-" prefix is out of scope for this cluster.
- Farm/business operator role nouns: `gårdbruker` (farmer).

#### Exclude
- Full personal names, even with a professional honorific (`Dr. Astrid Sæther`, `Dr. Per Hansen`) — the name itself is PERSON; only the title/role text is EMPLOYMENT_INFO. If "Dr." appears with an attached role clause ("Dr. Astrid Sæther, veterinær ved..."), tag only `veterinær ved...` as EMPLOYMENT_INFO.
- Hobby/association memberships that are not occupational: `medlem av det lokale hagelaget` — a garden club is not a job.
- Political candidacy: `kandidat til kommunestyret` — POLITICAL_CASE's domain.
- Court/institution names appearing incidentally (`Bergen Tingrett`, `Vest politidistrikt`) — not the subject's employer.
- Generic/hypothetical role nouns not tied to a specific named person's real job ("en ansatt kan...") — excluded.

#### Boundary rule
Tag the full coordinated title, including conjunctions ("eier og", "styreleder og") joining multiple roles held by the same person, and including a directly-attached "av/i/ved `<company>`" phrase with no intervening clause break (a comma introducing new information, "som har", etc. breaks the clause).
- `eier og daglig leder` — not `daglig leder` alone (already the dominant historical label, 2,186 vs. 1).
- `daglig leder og eier av Larsen Sjømat AS` — not `eier av Larsen Sjømat AS` alone.
- `owner of Sørensen Fisk AS` — English equivalent construction, same rule. When the company name alone appears elsewhere with no role word attached, it is still tagged on its own — two legitimately different spans in two different sentences, not a boundary conflict.
- `utdannet veterinærassistent` — the qualifier "utdannet" stays attached.

#### Overlap policy and Precedence
- EMPLOYMENT_INFO > FAMILY_RELATION for `forretningspartner` specifically.
- PERSON > EMPLOYMENT_INFO for the name portion of any "Dr. `<Name>`" construction.
- POLITICAL_CASE > EMPLOYMENT_INFO for candidacy/elected-office spans.
- Where a span is both an occupation and a hardship signal (`mistet jobben sin nylig`), EMPLOYMENT_INFO wins for the bare fact of job loss; ECONOMIC_STATUS only applies to an attached hardship-consequence clause, tagged separately.

#### Positive examples
- `veterinærassistent` (context: "Jeg er utdannet veterinærassistent, men jobber for tiden i barnehage") — bare occupation noun, real trained role.
- `eier og daglig leder` — coordinated ownership+management title, dominant historical convention (2,186 instances).
- `pensjonert lærer` — retired-occupation answer to an explicit "yrke" question.
- `sykepleier på Haukeland Universitetssjukehus` — role + attached workplace, one full clause.
- `ansvarlig for deler av prosessen før dyrene går til bedøvelse` — a specific described work responsibility at a named employer (Nortura SA).

#### Negative examples
- `medlem av det lokale hagelaget` — NOT EMPLOYMENT_INFO; a hobby club.
- `Dr. Astrid Sæther` — NOT EMPLOYMENT_INFO as a whole string; the name is PERSON.
- `kandidat til kommunestyret` — NOT EMPLOYMENT_INFO; POLITICAL_CASE.
- `Bergen Tingrett` — NOT EMPLOYMENT_INFO; a court name is not the subject's employer.

#### Resolved conflicts
- `daglig leder` vs. `eier og daglig leder` → **long coordinated form** wherever "eier og" appears in source.
- `Sørensen Fisk AS` vs. `owner of Sørensen Fisk AS` → tag **whichever form the specific sentence uses**; not a real conflict, just two different sentences.
- `ansatt` vs. `ansatt Bergen Slakt AS` → **long form** when the employer directly follows with no punctuation break; bare `ansatt` is retained as valid only when no employer is named in that clause.
- `arbeidsledig` vs. `registrert arbeidsledig` → **long form**, both remain EMPLOYMENT_INFO (employment status), not ECONOMIC_STATUS, since it answers the occupation/status question directly.

---

### POLITICAL_CASE

#### Definition
POLITICAL_CASE is a verbatim clause stating that an identified or identifiable natural person **holds, has stated, or is affiliated with (as a member, donor, or active participant) a specific political party, movement, or organisation with a stated ideological/political character**, including the affiliation verb (medlem av / aktiv i / tilhenger av / tilknytning til) and the full quoted or proper name of the organisation. A bare organisation name with no affiliation verb attached to a person is not, by itself, evidence of that person's political opinion and is not tagged.

#### Include
- Membership clauses with the full verb + org name: `medlem av Fremskrittspartiet`, `aktivt medlem av det høyreekstreme politiske partiet "Norges Renhet"`.
- Quoted movement/party names embedded in a membership or activity clause: `medlem av den høyreekstreme organisasjonen "Norges Frie Folkeparti"`, `aktiv i det høyreekstreme politiske partiet "Nasjonal Front"`.
- Stated political opinions/positions attributed to the person, not just party membership: `anti-immigrant holdninger`, `sterke anti-EU holdninger`, `motstand mot regjeringens innvandringspolitikk`.
- Donations/financial support tied to a political cause when stated as the person's action, when attached to a named political recipient.

#### Exclude
- **A bare organisation/party name with no attached affiliation verb**: `Norges Renhet` alone, `Frihetspartiet` alone, `Jehovas Vitner` alone — not tagged. The corpus already prefers the long form for genuine hits (`medlem av den høyreekstreme organisasjonen "Norges Frie Folkeparti"`: POLITICAL_CASE 21 vs. 1 former-CONTEXT_SENSITIVE); several bare-name instances (`Norges Frie Planteimportører`, `Norges Frie Dyreimportører`) are plainly fictional trade names invented for the animal-welfare/food-safety scenario with no political content at all.
- Religious affiliation with no stated political character: `medlem av Den Evangelisk Lutherske Frikirke`, `medlem av Human-Etisk Forbund`, `tilhenger av Jehovas Vitner` — route to a religion/belief type if the schema has one; with the former CONTEXT_SENSITIVE type cut, the correct outcome for these is "neither," not "default to POLITICAL_CASE" (see Open questions).
- Local/professional roles with no ideological content: `lokal politiker` alone — EMPLOYMENT_INFO, unless a specific party/opinion is also named in the same clause.
- Generic activity with no political framing: `aktiv i lokalpolitikken` alone — too vague; only tag when a party name is present in the full clause (`medlem av Senterpartiet og aktiv i lokalpolitikken`).

#### Boundary rule
Span = [affiliation/opinion verb or noun] + [full name of the party/movement, including any quotation marks genuinely present in the source] + [ideological descriptor if present, e.g. "høyreekstreme"]. Always pull the verb in; never emit the bare proper noun alone.
- `Norges Renhet` → correct: `medlem av den høyreekstreme organisasjonen "Norges Renhet"`.
- `Frihetspartiet` → correct: `medlem av partiet "Frihetspartiet"`.
- `Fremskrittspartiet` → correct: `Medlem av Fremskrittspartiet` (capital "M" preserved exactly as it appears in that source sentence — do not normalize casing across instances).
- `demonstrasjoner mot innvandring` → correct: `deltatt i demonstrasjoner mot innvandring`.
- `aktiv i lokalpolitikken` → correct (when a party is present): `medlem av Senterpartiet og aktiv i lokalpolitikken` — kept as one span.

#### Overlap policy and Precedence
- **vs. CRIMINAL_RECORD**: if the same clause also states a criminal consequence (e.g. a party-financing offense), split into two spans — the affiliation (POLITICAL_CASE) and the offense (CRIMINAL_RECORD).
- **vs. BEHAVIORAL_PATTERN**: a stated opinion/belief (`antisemittiske synspunkter`, `anti-immigrant holdninger`) is POLITICAL_CASE; an *action* taken because of the belief is BEHAVIORAL_PATTERN or CRIMINAL_RECORD depending on severity — tag both as adjacent spans when both are present, never one span spanning both.
- **vs. religion/belief types outside this cluster**: religious organisation membership with no stated political content is never POLITICAL_CASE.
- **vs. the former CONTEXT_SENSITIVE type**: N/A — cut. Former migrations for genuine political content (`Norges Frie Folkeparti`, `rasistiske og homofobe synspunkter`) now resolve unambiguously to POLITICAL_CASE.

#### Extraction-not-summarisation rule
Never fabricate or move punctuation, especially around quoted organisation names. Real violation found in data: label `'tilknytning til den høyreekstreme gruppen "Nordisk Samhold"'` was applied where the source actually reads *"...bekreftet sin tilknytning til den høyreekstreme gruppen "Nordisk Samhold," noe som..."* — the source's quotation mark never actually closes there; the labeler invented a closing quote. Correct span: `tilknytning til den høyreekstreme gruppen "Nordisk Samhold` (stop at the comma; do not synthesize a closing quote the source does not contain).

#### Positive examples
1. `medlem av den høyreekstreme organisasjonen "Norges Frie Folkeparti"` — full affiliation verb + ideological descriptor + quoted name.
2. `aktivt medlem av det høyreekstreme politiske partiet "Norges Renhet"` — same pattern with intensifier "aktivt".
3. `sterke anti-EU holdninger` — a stated opinion; no party name needed.
4. `kontroversielle uttalelser om innvandring` (context: "Mr. Olsen er aktiv i Fremskrittspartiet og er kjent for sine kontroversielle uttalelser om innvandring") — two adjacent POLITICAL_CASE facts (membership + stated views), kept as two spans.
5. `Member of the politically controversial group "Norges Fremtid"` — English-language full form, same rule.

#### Negative examples
1. `Norges Renhet` (bare) — excluded; must use the long form.
2. `medlem av Den Evangelisk Lutherske Frikirke` — religious, not political; excluded.
3. `lokal politiker` (bare) — a job title; EMPLOYMENT_INFO unless a party/opinion is named alongside it.
4. `aktiv i lokalpolitikken` (bare, no party named) — excluded until a specific party/movement is present.

#### Resolved conflicts
- `Norges Renhet` vs. `medlem av den høyreekstreme organisasjonen "Norges Renhet"` → **long form**.
- `Fremskrittspartiet` vs. `Medlem av Fremskrittspartiet` vs. `medlem av Fremskrittspartiet` → **long form**, case preserved exactly as it appears in that instance.
- `Jehovas Vitner` vs. `tilhenger av Jehovas Vitner` and `aktive medlemmer av Jehovas Vitner` → both **excluded from POLITICAL_CASE entirely** (religious, not political) regardless of boundary form.
- `aktiv i lokalpolitikken` vs. `medlem av Senterpartiet og aktiv i lokalpolitikken` → **long form** required.
- Presence conflict `medlem av "Høyre"` (missed in one copy) → **must be tagged**.
- Ambiguous span `skandale`/`offentlig skandale` alone → **excluded from POLITICAL_CASE**; only tag if the clause names the political actor/party involved.

---

### BEHAVIORAL_PATTERN

Current spans: 16,431. Boundary conflicts: 10. Presence conflicts: 301. Verbatim-miss (paraphrase) rate: 2.98% (490/16,431 spans not found verbatim in source text) — the highest of the four conduct/belief types measured (former-CONTEXT_SENSITIVE 2.70%, POLITICAL_CASE 3.68%, CRIMINAL_RECORD 0.56%).

#### Definition
BEHAVIORAL_PATTERN is a verbatim clause describing a **recurring or characteristic pattern of conduct performed by an identified or identifiable natural person** (never an animal's own conduct), reported as observed fact — e.g. aggression, neglect, intoxication, non-cooperation with inspectors, deceptive conduct — where the clause names or clearly implies the human subject and the action they repeatedly perform. A single isolated adjective with no subject and no repetition marker is not enough; the full clause must show *who* and *what pattern*.

#### Exclusion scope — narrower than an earlier draft, exclude only when the animal is the grammatical subject

An earlier draft of this spec used a rough keyword heuristic (checking for an animal noun in the first 40 characters of a span) and concluded that 19.4% of spans (3,189) should be excluded as animal-subject. That heuristic conflated three different things. A verified, grammatical-subject-level breakdown gives a materially different, and narrower, picture:

- **12,172 spans (76.4%) mention no animal at all** — keep.
- **1,538 spans (9.6%) describe a human acting on an animal** (`sparke og slå hundene`, `Har sett eieren bli sint på hunden`, `slå hunden ved flere anledninger`) — **keep**; this is owner conduct, exactly the PII this type exists to capture.
- **666 spans (4.2%) have the animal as the grammatical subject of the span** (`Hunden bjeffer ofte`, `Hunden virker anspent og redd`) — **exclude**; not personal data.
- **1,565 spans (9.8%) are ambiguous** (`kaste gjenstander etter hundene`, `sløve og apatiske`, `går tur med hunden min forbi eiendommen hver dag`) — **flag for review, do not auto-drop.**

**The rule is: exclude a span from BEHAVIORAL_PATTERN only where the animal is the grammatical subject of the span itself** — not wherever an animal is merely mentioned, referenced, or acted upon. This is narrower than "any animal mention excludes," and it is what makes 9.6% of the corpus's owner-conduct-toward-an-animal spans (the type's actual core use case) stay in scope. Separately, and on a different basis, the reporting witness's own routine behaviour is excluded even though its grammatical subject is human — see Exclude below; the ambiguous example `går tur med hunden min forbi eiendommen hver dag` belongs to that witness-exclusion rule specifically, not to the general "flag for review" bucket, because it is about the witness, not the data subject.

For any of the 1,565 ambiguous spans not otherwise resolved by the witness-exclusion rule, do not mechanically include or exclude at re-labeling time; route them to manual review.

#### Include
- Owner/subject conduct with an explicit human subject: `Eier observert kranglende med naboer angående hunden`, `Har sett eieren bli sint på hunden ved flere anledninger`, `Frank Olsen oppføre seg uberegnelig` (context: "jeg har sett Frank Olsen oppføre seg uberegnelig noen ganger").
- Recurring conduct toward people or animals stated as an action of the person: `rope på hunden aggressivt flere ganger`, `kaste tomflasker og stein etter hundene`, `nektet å samarbeide med inspektørene og fremviste aggressiv atferd`.
- Verbal threats/outbursts attributed to a named or identifiable person and not already a chargeable criminal act under CRIMINAL_RECORD's precedence rule: `Dere skal få svi, begge to!` (quoted outburst attributed to "han", in a context of "høylytte krangler").
- Non-cooperation/evasiveness with authorities, stated as a pattern: `resistant to previous guidance and exhibits a pattern of non-compliance` (its short-form `pattern of non-compliance` is the wrong boundary — see Boundary rule).

#### Exclude
- Any span whose full subject, once pulled in by the boundary rule, is an animal and not the person: `Schæferen virker undervektig og har matt pels.`, `Apene virker stressede, beveger seg raskt og urolig rundt i buret, og plukker mye i pelsen sin.`, `bjeffer utrøstelig i timevis hver dag` — these describe the animal's condition or behaviour, not the owner's conduct. **Not BEHAVIORAL_PATTERN.** They are not therefore untagged: an animal's distress is a welfare condition and belongs to HEALTH_INFO, which is where the gold set puts all three of these examples. The earlier wording, "Not tagged at all", was written from this type's point of view and wrongly read as a global exclusion.
- The line for an animal vocalising is what the document uses it to show. Barking offered as a sign of the animal's state — alongside `stresset`, `rastløs`, `alene i lange perioder`, `klynke` — is HEALTH_INFO (13 gold spans). Barking offered only as a nuisance to neighbours (`bjeffingen forstyrrer naboene`), as aggression towards people (`bjeffer og knurrer aggressivt mot forbipasserende`), or as circumstantial evidence of an activity, is untagged (20 gold mentions). Where the tagged fact is the owner striking the animal and the barking is only the trigger clause (`sparke og slå hundene når de bjeffer`), the span is BEHAVIORAL_PATTERN about the owner.
- The **reporter's/witness's own** routine behaviour, even though grammatically human-subject: `Jeg går tur forbi eiendommen regelmessig`, `Jeg går ofte tur i nabolaget`, `går tur med hunden min forbi eiendommen hver dag` — personal data about a third party (the whistleblower), not a conduct pattern of the data subject under investigation.
- Financial/political/criminal acts that already have a positive home and a stronger, more specific type available: `skattesvindel`, `utroskap` alone with no conduct-pattern verb, `antisemittiske synspunkter` (→ POLITICAL_CASE).
- Bare adjectives with no subject and no repetition/pattern marker: `aggressiv` alone (contrast with the correct boundary `aggressiv og kontrollerende`).

#### Boundary rule
A BEHAVIORAL_PATTERN span starts at the earliest word that establishes **who** (the human subject, or a preceding possessive/verb clearly attaching the pattern to them, e.g. "Eier observert...", "Har sett eieren...") and ends at the end of the described action/pattern, including any manner/frequency/target qualifier, but stopping before a new independent clause (usually a period, "og" starting a new sentence, or "--" in the interview-style documents).
- `lite samarbeidsvillig` → correct: `aggressiv og lite samarbeidsvillig` (include the coordinated adjective).
- `pattern of non-compliance` → correct: `resistant to previous guidance and exhibits a pattern of non-compliance` (include the lead-in that establishes it as a *pattern*, not a one-off).
- `aggressiv adferd` → correct: `aggressiv adferd mot en kollega etter en uenighet om politikk` (include target + trigger context).
- `utagerende oppførsel` → correct: `utagerende oppførsel, spesielt etter inntak av alkohol` (include the qualifying condition).
- `radikalisert` → correct: `stadig mer radikalisert` (include the intensifier marking it as a trend/pattern).

#### Overlap policy and Precedence
- **vs. CRIMINAL_RECORD**: once a described act is framed with legal-process language (dømt, siktet, anmeldt, mistanke om, politianmeldelse) or is itself a per-se chargeable act naming a weapon/victim (`truet Jensen med en kjøkkenkniv`), CRIMINAL_RECORD wins. Plain conduct with no legal framing (`aggressiv atferd` on its own) stays BEHAVIORAL_PATTERN. Evidence: `voldelig atferd` skews CRIMINAL_RECORD (121); `aggressiv atferd` splits 64 BEHAVIORAL_PATTERN vs. 1 CRIMINAL_RECORD when no legal process is named.
- **vs. POLITICAL_CASE**: if the conduct describes a belief/affiliation rather than an action (`antisemittiske synspunkter`, `anti-immigrant holdninger`), POLITICAL_CASE wins. If it's an action taken because of a political motive but the action itself is the point, BEHAVIORAL_PATTERN wins for the conduct clause and POLITICAL_CASE (if present) is a separate adjacent span for the belief/affiliation.
- **vs. HEALTH_INFO**: `virket apatisk`/`sitter apatisk` describing an animal is excluded per this spec's animal-subject rule; the same phrase describing a person's own demeanor is HEALTH_INFO if it reads as a medical/psychological state.
- **vs. the former CONTEXT_SENSITIVE type**: N/A — cut; its "owner conduct" bucket redistributes here (see Removed types).

#### Extraction-not-summarisation rule
Copy the exact substring of the source, including exact wording, vehicle/location detail, and case. Real violation found in data: label `'Hunden blir ofte etterlatt alene i bilen'` was applied to a document whose actual text reads *"Hunden blir ofte etterlatt alene i en sølvgrå Volvo stasjonsvogn, registreringsnummer BC 12345."* Correct span: `Hunden blir ofte etterlatt alene i en sølvgrå Volvo stasjonsvogn` (stop before the registration number).

#### Positive examples
1. `Eier observert kranglende med naboer angående hunden` — names the subject, the pattern, and the trigger; fully self-contained.
2. `Har sett eieren bli sint på hunden ved flere anledninger` — explicit repetition marker plus named subject and action.
3. `rope på hunden aggressivt flere ganger` — action + manner + frequency.
4. `nektet å samarbeide med inspektørene og fremviste aggressiv atferd` — conduct toward an authority, clean human-subject pattern.
5. `kaste tomflasker og stein etter hundene` — concrete, repeated, verbatim, unambiguously human-subject action.

#### Negative examples
1. `Schæferen virker undervektig og har matt pels.` — subject is the dog; excluded.
2. `Jeg går tur forbi eiendommen regelmessig` — human subject, but it's the reporting witness, not the data subject; excluded.
3. `aggressiv` (bare) — no subject, no pattern marker.
4. `sår på hodet` — a physical injury description; in the observed context it is the animal's, correctly routed to HEALTH_INFO / excluded here, not BEHAVIORAL_PATTERN.

#### Resolved conflicts
- `lite samarbeidsvillig` vs. `aggressiv og lite samarbeidsvillig` → **long form**.
- `aggressiv` vs. `aggressiv og kontrollerende` → **long form**.
- `concerning behavior` vs. `broader pattern of concerning behavior` → **long form** (the word "pattern" is required by the definition itself).
- `unnvikende` vs. `stresset og unnvikende` → **long form**.
- `utagerende oppførsel` vs. `utagerende oppførsel, spesielt etter inntak av alkohol` → **long form**.
- Presence conflict `aktiv i den lokale skytterklubben` / `medlem av den lokale pinsemenigheten` → affiliation, not conduct; for a hobby club/church with no political or extremist character, this is arguably not sensitive under any of the 16 types — recommend leaving untagged rather than forcing it into BEHAVIORAL_PATTERN (see Open questions).
- Presence conflict `spillegjeld` / `spilleavhengighet` → routed by framing, per the
  project owner's ruling: a stated financial outcome (`spillegjeld`, `gambling losses`,
  an amount lost) is ECONOMIC_STATUS; the habit or conduct itself
  (`spilleavhengighet`, `spiller bort pengene sine ukentlig`) is BEHAVIORAL_PATTERN;
  and a clinical frame (`diagnostisert spillavhengighet`) is HEALTH_INFO.

---

### SEXUAL_ORIENTATION

Current spans: 11,817. Boundary conflicts: 219. Presence conflicts: 191. Type migrations: 13.

#### Definition
SEXUAL_ORIENTATION tags a clause that states, discloses, or credibly alleges a named individual's sexual orientation, gender identity, or a fact squarely about their "sex life" in the GDPR Art. 9 sense (e.g., non-monogamous/polyamorous relationship structure). This is a GDPR special-category type: it is tagged whether the disclosure is self-reported, officially recorded, or merely alleged/rumoured by a third party, because the special-category sensitivity attaches to the *processing of the claim about the person*, not to whether the claim is proven true.

#### Include
- Orientation self-identifiers, with their immediate modifiers: `homofil`, `lesbisk`, `biseksuell`, `heterofil`, `bifil`, `heteroseksuell`, and English equivalents (`homosexual`, `bisexual`, `heterosexual`, `lesbian`).
- The adverbial-modified form when present in source: `åpent homofil`, `åpen lesbisk`, `Openly lesbian`.
- Noun-phrase disclosures: `seksuell legning`, `seksuelle legning`, `homofile legning`, `homofili`, `biseksualitet`.
- Same-sex or orientation-revealing relationship descriptions when the orientation word is present in the same clause: `homofilt forhold`, `lesbisk forhold`, `homofile forhold til en lokal politiker`.
- Consensual-non-monogamy relationship structure, which GDPR's "sex life" limb covers: `polyamorøst forhold`, `polyamorøst forhold med to partnere`, `lever i et åpent forhold`.
- Third-party allegation/rumour about orientation — tag the substantive clause, drop the reporting frame: from "rykter om hans homofile legning", tag `hans homofile legning`.

#### Exclude
- Plain relationship-status nouns with no orientation word: `samboer`, `partner`, `ektefelle`, `gift`, `skilt`, `registrert partnerskap`, `ektemann`, `husband` — FAMILY_RELATION, even though 1,168/1,421/276/40 of them carry a single stray SEXUAL_ORIENTATION mislabel in the corpus. A civil partnership or cohabitation is available to opposite-sex and same-sex couples alike and reveals nothing about orientation by itself.
- Extramarital-affair language with no orientation content: `affære`, `utroskap`, `utenomekteskapelig forhold`, `kortvarig affære` — FAMILY_RELATION, not orientation, unless the affair partner's gender combined with the subject's stated orientation is the disclosed fact.
- Generic workplace/social descriptors caught by keyword collision: `mannlig kollega` alone.
- Religious/political self-identifiers that are lexically adjacent in these dossiers but categorically unrelated: `ateist` — POLITICAL_CASE territory (or untagged), never SEXUAL_ORIENTATION, despite 14 stray co-occurrences.

#### Boundary rule
Include leading intensifying adverbs and trailing descriptive/appositive nouns that are part of the same noun phrase as the orientation word. Exclude self-report or third-party reporting verbs outside that noun phrase.
- `homofil` vs. `åpent homofil` → the adverb "åpent" is part of the clause; mandate the longer form whenever "åpent"/"åpen"/"Åpent"/"Åpen" immediately precedes the orientation word (935 of 11,817 spans already carry this adverb).
- `lesbiske` vs. `lesbiske forhold` → **longer form**.
- `homofil` vs. `homofile legning` → **longer form**.
- `forhold til en kvinne` vs. `har hatt et tidligere forhold til en kvinne` → **longer form**.
- Reporting verbs are cut: from "Olsen identifiserer seg som homofil", the tagged span is `homofil` only.

#### Overlap policy
- Never shares characters with FAMILY_RELATION. When one clause contains both a relationship noun and an orientation adjective (`lesbisk forhold`, `homofilt forhold til Lars Olsen`), the **entire clause is SEXUAL_ORIENTATION** (resolves `lesbisk forhold` {SEXUAL_ORIENTATION: 11, FAMILY_RELATION: 2} → mandate SEXUAL_ORIENTATION only).
- If a person's proper name is embedded inside the clause (`homofilt forhold til Lars Olsen`, `i et forhold med Karianne Nilsen`), the name is **also** separately tagged PERSON on its own characters (nested), while the SEXUAL_ORIENTATION span still runs through the full clause including the name's characters.
- Can legitimately co-occur with CRIMINAL_RECORD on different characters in the same sentence, but never on identical characters; `seksuell trakassering` is CRIMINAL_RECORD, never SEXUAL_ORIENTATION, despite one stray co-tag.
- Extramarital-affair vocabulary (`utroskap`, `utroskapsaffære`, `utenomekteskapelig forhold`) defaults to FAMILY_RELATION, not SEXUAL_ORIENTATION, unless the orientation itself (not just infidelity) is the disclosed fact.

#### Positive examples
1. `homofil` in "...Olsen identifiserer seg som homofil. Vår rett til å føre tilsyn..." — direct self-identification, reporting verb correctly excluded.
2. `åpent homofil` in "...er en aktiv medlem i Senterpartiet og åpent homofil, har innrømmet..." — adverb included per boundary rule.
3. `registrert partnerskap` — **not** SEXUAL_ORIENTATION; included here only to contrast with item 4.
4. `homofilt forhold` in "...Berg har et homofilt forhold til Lars Olsen (født 05.02.1985...)" — `Lars Olsen` inside it is separately tagged PERSON.
5. `hans homofile legning` from "...Olsen hevder at rykter om hans homofile legning er falske..." — allegation still tagged; reporting frame excluded.
6. `biseksuell` in "Hun er for tiden separert fra sin ektefelle, Bjørn Olsen... identifiserer seg som biseksuell." — self-identification.

#### Negative examples
1. `samboer` in "...og har en samboer, Bjørn Hansen..." — FAMILY_RELATION, even though one corpus instance was mislabeled SEXUAL_ORIENTATION.
2. `ektemann` — same reasoning; FAMILY_RELATION, despite 13 stray co-tags.
3. `mannlig kollega` alone — does not by itself disclose orientation.
4. `ateist` — religious/philosophical self-identifier; 14 mislabels must be corrected to POLITICAL_CASE or left untagged.
5. `skilt` (divorced) — FAMILY_RELATION, despite one stray co-tag.

#### Resolved conflicts
- `homofil` vs. `åpent homofil` → **longer form** whenever the adverb is present.
- `lesbiske` vs. `lesbiske forhold`; `lesbisk` vs. `lesbisk forhold`; `homofile` vs. `homofile legning`; `homofilt` vs. `homofilt forhold` → **longer form** in every case.
- `LGBT+` vs. `aktiv i den lokale LGBT+ bevegelsen` → **longer form**.
- `Karianne Nilsen` vs. `i et forhold med Karianne Nilsen` → **longer form** for SEXUAL_ORIENTATION; additionally tag `Karianne Nilsen` PERSON.
- `extramarital affair` vs. `concealed extramarital affair` → if orientation is not otherwise disclosed, **exclude both** (route to FAMILY_RELATION); if the corpus intends this as an orientation disclosure, mandate the longer form and tag SEXUAL_ORIENTATION.
- `polyamorøst forhold` vs. `polyamorøst forhold med to partnere` → **longer form**, tag SEXUAL_ORIENTATION, not FAMILY_RELATION.
- `seksuell trakassering` vs. `etterforskning for seksuell trakassering` → **exclude from SEXUAL_ORIENTATION entirely**; mandate CRIMINAL_RECORD for both forms.
- `registrert partner` {FAMILY_RELATION: 102, SEXUAL_ORIENTATION: 1} → **mandate FAMILY_RELATION**.
- `samboer`, `ektemann`, `husband`, `skilt` stray SEXUAL_ORIENTATION co-tags → **mandate FAMILY_RELATION exclusively**.
- `ateist` {former-CONTEXT_SENSITIVE: 158, SEXUAL_ORIENTATION: 14, POLITICAL_CASE: 15, BEHAVIORAL_PATTERN: 5} → **mandate POLITICAL_CASE** when explicit political-atheism-movement framing is present, otherwise leave untagged now that CONTEXT_SENSITIVE is cut; **never SEXUAL_ORIENTATION.**

**Does third-party speculation/allegation count?** **Yes — tag it.** GDPR Art. 9 attaches to the *processing of data concerning* sexual orientation; a recorded allegation, rumour, or denied claim about someone's orientation is still special-category data about that person once it is written into the document, regardless of truth value. Tag the substantive orientation clause and cut only the outer reporting/sourcing verb, per the general reporting-frame rule in Global rules.

---

## Open questions

Each item below is marked **OPEN** (no override addresses it — needs a project-owner decision before re-labeling) or **RESOLVED** (an override above already settles it, with a pointer to which one).

1. **DATE_TIME's config definition text is stale.** OPEN. The current config text ("Dates and times tied to identifiable persons") does not match actual practice — the vast majority of labeled spans are standalone administrative timestamps. This spec adopts the data-driven interpretation (include standalone dates), but the config's definition text should be formally updated to avoid future re-drift.
2. **D-nummer digit-offset verification.** OPEN. Real Norwegian D-numre increment the birth-day digit by 4 (day 41–71 instead of 01–31). The evidence sample is too small (one example, `05123456789`) to confirm the synthetic corpus follows this convention. This spec relies on the literal field label rather than verifying the digit pattern.
3. **"Vår ref"/"Deres ref" with a value of `-` or blank.** OPEN. Confirmed exclude (no value to tag), but the evidence does not show how often a real reference number is hidden behind a dash placeholder vs. genuinely absent — worth a targeted grep before full re-labeling.
4. **POSTAL_CODE as a separate type vs. folding into NO_ADDRESS.** RESOLVED by Override 6 — the project owner has adopted the field-conditioned nesting/exclusivity rule as written, keeping POSTAL_CODE as its own type with the documented "4 digits only" exception to the full-clause rule.
5. **NO_ADDRESS field-conditioned nesting reverses the old labels' numeric majority.** RESOLVED by Override 6 — explicitly confirmed acceptable; e.g. `5000 Bergen` was NO_ADDRESS 622× vs. POSTAL_CODE 21× in the old data, and the new rule deliberately reverses that majority because it contradicts both types' own definitions.
6. **Single first-name PERSON vs. animal-name disambiguation** (`Balder`, `Odin`, `Pus`, `Snøball`, etc.). OPEN. No purely mechanical rule reliably separates "a human named Odin" from "a dog named Odin" beyond checking whether the field is "Navn på varsler/dyreeier" (human) vs. free-text animal description ("hunden heter..."). A short explicit gazetteer of common Norse/mythological pet-names in this corpus may be worth building if perfect inter-annotator agreement is required.
7. **ECONOMIC_STATUS vs. BEHAVIORAL_PATTERN for gambling/investment-loss spans** (`spillegjeld`, `gambling losses`, `mislykket investeringsprosjekt i kryptovaluta`). **RESOLVED** by the project owner: split by framing — outcome is ECONOMIC_STATUS, habit is BEHAVIORAL_PATTERN, clinical diagnosis is HEALTH_INFO. Previously OPEN.
8. **`pensjonist` as EMPLOYMENT_INFO vs. ECONOMIC_STATUS vs. neither.** OPEN. This spec keeps it as EMPLOYMENT_INFO when it answers an occupation question in the source template, on the grounds that excluding it would blow a large hole in presence recall for a frequent, template-driven span.
9. **FINANCIAL_INFO's tie-break default** (bare `gjeld`/`debts` → FINANCIAL_INFO) **vs. not tagging at all.** OPEN. This spec keeps tagging for recall consistency, but it's a policy call, not a fact derivable from the data.
10. **English-language spans** (`falsified tax documents`, `undeclared income`, `tax evasion`). PARTIALLY RESOLVED. Global Rule 1 already settles the general case: a genuinely English-language source document keeps its English span verbatim, untranslated. What remains open is a verification task, not a rule question: confirming which apparent English spans are genuine source text vs. translation artifacts from the corpus's generation pipeline (in which case the actual Norwegian source text at that position should be located and tagged instead).
11. **Animal-welfare severity signal as a separate non-PII field.** RESOLVED by Override 3 — moot. An earlier draft proposed a new `ANIMAL_CONDITION` label to preserve animal-welfare severity data outside of HEALTH_INFO if HEALTH_INFO excluded it. Since Override 3 keeps animal condition inside HEALTH_INFO itself, no separate label is needed.
12. **Splitting conjoined facts into multiple spans.** OPEN. This spec mandates splitting compound diagnosis clauses and multi-child FAMILY_RELATION lists into per-fact spans. Whether the downstream consumer (model / detection service) requires non-overlapping, contiguous spans, or can handle multiple short spans from one sentence, needs confirmation — if contiguous single-span output is a hard requirement, this splitting rule needs to be revisited project-wide.
13. **Nested-tag support in the data/training pipeline.** OPEN. The FAMILY_RELATION↔PERSON, SEXUAL_ORIENTATION↔PERSON, and GOV_ID↔CRIMINAL_RECORD/FINANCIAL_INFO nesting rules in this spec assume the annotation/training format supports overlapping spans of different types on the same characters. Confirm the JSONL schema and the fine-tuning pipeline (`src/data_processor.py`, `src/prompt_builder.py`) actually preserve overlaps rather than silently deduplicating or picking one type per character span — if the pipeline is span-exclusive, the nesting policy in this document cannot be implemented as written and needs a fallback (e.g., "on overlap, keep the outer/longer span's type only").
14. **`polyamorøst`/`åpent forhold` classification** (SEXUAL_ORIENTATION vs. FAMILY_RELATION). OPEN. This spec places consensual non-monogamy under SEXUAL_ORIENTATION on a GDPR "sex life" theory. If the project's legal/product interpretation is narrower (orientation = hetero/homo/bi/asexual identity only), these should move to FAMILY_RELATION instead — the corpus itself is split roughly evenly (12 FAMILY_RELATION vs. 10 SEXUAL_ORIENTATION for `åpent forhold`) with no clearly dominant existing practice.
15. **IDENTIFIABLE_IMAGE disposition.** RESOLVED by Override 2 — the type is cut entirely, and there is no fold-in destination, since the former CONTEXT_SENSITIVE type (the only candidate destination an earlier draft proposed) is also cut. Nothing from this type's span population should be retagged into any of the 16 remaining types.
16. **Typo verbatim policy** (`ektektefelle`). RESOLVED by Global Rule 1 — tag the typo exactly as it literally appears in the source; it already satisfies "verbatim substring of the source," so there is no conflict with the verbatim rule, and no correction should be made to it.
17. **Religious organisations with no home in the 16-type taxonomy** (Jehovas Vitner, Den Evangelisk Lutherske Frikirke, Human-Etisk Forbund, Scientologikirken). OPEN. These appear constantly in the corpus and were previously absorbed into POLITICAL_CASE or the now-cut CONTEXT_SENSITIVE type. This spec routes them to neither (POLITICAL_CASE is defined as party/political-opinion). Since the fixed 16-type taxonomy has no religion/belief type, roughly 300+ spans will go untagged unless the project owner decides religion should get its own type or be folded into a broadened POLITICAL_CASE definition.
18. **Hobby/social club affiliations with no political or extremist character** (`aktiv i den lokale skytterklubben`, `medlem av den lokale pinsemenigheten`). OPEN. Previously tagged BEHAVIORAL_PATTERN or the now-cut CONTEXT_SENSITIVE type; this spec recommends leaving them untagged as not sensitive personal data under any of the 16 types' GDPR Art. 9-style logic, which is a measurable drop in total labeled spans versus the old (over-)labeled corpus and needs sign-off.
19. **Fictional/synthetic party and organisation names** (`Norges Renhet`, `Norges Fremtid`, `Nordens Lys`, etc.). OPEN. These are consistently-reused, obviously LLM-generated placeholders for real-world extremist groups. Confirm whether annotators should keep tagging these as this spec assumes (they function exactly like real party names within the synthetic corpus), or whether their fictional/repeated nature should down-weight or exclude the political-affiliation scenario type as low-value synthetic filler — this affects a meaningful fraction of POLITICAL_CASE's spans.
20. **Cross-document identity / deduplication before re-labeling.** OPEN. 2,548 documents appear more than once in the corpus with contradictory labels. This spec fixes the annotation *rules*, but the re-labeling pass should deduplicate documents before annotation (label each unique document once) rather than re-annotating every duplicate independently, or the same near-100% contradiction problem will regenerate under the new rules by chance variation between annotators/sessions.
