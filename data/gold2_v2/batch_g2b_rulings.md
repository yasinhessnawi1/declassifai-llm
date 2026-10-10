# gold2 batch g2b — adjudication rulings

Two blind Sonnet annotators per document; a third Sonnet agent ruled each dispute against docs/ANNOTATION_SPEC.md (B1-B36).

## chunk 01

G2B001 | HEALTH | drop (B-only "behandles av Dr. Anne Hansen ved Bergen Medisinske Senter": names no condition, only a treating doctor; HEALTH must not swallow the name) | HEALTH overlap policy; B1
G2B002 | CRIMINAL | B "alle anklager om økonomisk kriminalitet" (quantifier kept) | B2
G2B002 | CRIMINAL | A (one process frame covers both offences) | CRIMINAL Positive example 4
G2B002 | CRIMINAL | B "politianmeldt" (subject and linking verb cut) | B1, B34
G2B002 | HEALTH | B (parenthetical itemises the same fact; A's "feil ernæring" dropped) | B4, B11
G2B002 | HEALTH | B (A's "mangel på veterinærkontroll" dropped) | B4, B11
G2B002 | HEALTH | B | B4, B11, B14
G2B002 | RELIGIOUS_BELIEF | A "katolsk tro" ("være av" is the linking frame) | B1, RELIGIOUS_BELIEF
G2B003 | ANIMAL_INFO | keep "flere geiter" (adds a count) | ANIMAL_INFO Exclude/Include
G2B003 | CASE_NUMBER | B "2010/12345" (authority precedes the number) | B23
G2B003 | HEALTH | A (name stays PERSON, role word EMPLOYMENT) | HEALTH overlap policy, B12
G2B004 | SEXUAL_ORIENTATION | A "hans seksuelle orientering" (possessive kept, scandal frame cut) | B10, SEXUAL_ORIENTATION noun-phrase disclosures
G2B005 | CRIMINAL | A (bare "forfalsket" states nothing without its subject; contiguous span) | B17
G2B005 | CRIMINAL | A (same) | B17
G2B006 | CRIMINAL | B (ends at the serial-number parenthetical; location tail is not in the boundary rule) | B33, CRIMINAL boundary rule
G2B006 | RELIGIOUS_BELIEF | A "kristen tro" | B1
G2B007 | ANIMAL_INFO | keep "blandingsrase" | ANIMAL_INFO breed
G2B007 | ECONOMIC_STATUS | keep "bor tilsynelatende i bilen sin" (consistent with agreed "muligens hjemløs"; subject "Personen" cut) | ECONOMIC_STATUS, B1, B25
G2B009 | FAMILY_RELATION | A "sønn, Elias Olsen" (birth-year parenthetical split under B4; "en" cut) | B2, B4, FAMILY_RELATION boundary
G2B009 | FAMILY_RELATION | drop "sin mor" (the mother of the subject's son, not a stated relation of the data subject) | FAMILY_RELATION definition
G2B010 | CRIMINAL | A "Loggbøker og rapporter om Salmonella-utbrudd var manipulerte" | B17
G2B010 | CRIMINAL | B (police report frames the regulatory breach criminally; one frame, one span) | B34, CRIMINAL Positive example 4
G2B010 | HEALTH | drop "Salmonella-utbrudd" (regulatory/reporting text, no outbreak at the farm stated) | B6
G2B002 | ORGANIZATION | third: "\"Hjertets Hjem\"" (agreed span corrected to include quotes) | B35
G2B006 | ORGANIZATION | third: "\"Lars' Kaker & Catering\"" (agreed span corrected to include quotes) | B35
G2B008 | ORGANIZATION | third: "\"Smaken av Norge\"" (agreed span corrected to include quotes) | B35

## chunk 02

G2B011 | CRIMINAL | keep "Haglgevær i transportkjøretøy" | B6 (case-specific finding restated in observation list under the Ulovlig våpenbesittelse heading)
G2B013 | CRIMINAL | A: "dømt for bedrageri" | "One clause, one fact" (og-conjoined offences split; "dømt for" stays with the first)
G2B013 | CRIMINAL | A: "trusler" (separate span) | One clause, one fact; B3/B11
G2B013 | ORGANIZATION | REMOVED bare `Himmelriket's Kjøkken` at first mention; third: "\"Himmelriket's Kjøkken,\"" (bare form kept for the later unquoted mention) | B35 (quotes inside ORGANIZATION), B5 (punctuation printed inside the closing quote)
G2B014 | FINANCIAL | B: "unnlatt å rapportere inntekt på over 750 000 NOK" and "Manglende rapportering av inntekt på over 750 000 NOK" | FINANCIAL boundary (qualifying phrase stays attached), B36 (verb that is itself the fact stays), B6 (restatement)
G2B015 | ADDRESS | A: "Havnegata 23B" | ADDRESS boundary (trailing city only inside an Adresse field value; prose city is LOCATION)
G2B015 | FINANCIAL | B: "unnlatt å rapportere minst 250 000 NOK i inntekt" | same as G2B014
G2B015 | MARITAL_STATUS | drop A-only "Samboer, Rune Hansen" | B31 (same-sex partner; doc also states Seksuell legning: Homofil) -> SEXUAL_ORIENTATION
G2B015 | PERSON | drop B-only "Lars Kristian Olsens" | B21 (genitive -s not part of name; full name already tagged)
G2B015 | SEXUAL_ORIENTATION | keep B-only "Samboer, Rune Hansen" | B31, precedence SEXUAL_ORIENTATION > MARITAL_STATUS
G2B016 | CRIMINAL | B: "forfalskede regnskapsdokumenter og skattemeldinger" | B36/B17 (presentation verb dropped, forged documents are the fact)
G2B016 | EMPLOYMENT | keep A-only "Fisker" | B12 role word of named professional (Fisker Lars Magnus Johansen); nested inside ORGANIZATION
G2B016 | LOCATION | keep B-only "Bodø" | LOCATION (place named in prose; "kemneren i Bodø" is not a proper authority name)
G2B016 | BEHAVIORAL_PATTERN | REMOVED agreed "spilleavhengighet"; HEALTH "spilleavhengighet" ADDED | B22 (dependency noun is always HEALTH)
G2B017 | CRIMINAL | third: "Falske fakturaer" (A) + separate keep "manipulerte regnskapstall" | One clause, one fact (two unshared modifiers); B6 restatement of the manipulation in the prose
G2B018 | CRIMINAL | B: "forfalskede regnskaper og skatteopplysninger" | B36/B17 (delivery verb and recipient dropped)
G2B018 | EMPLOYMENT | keep A-only "Fisker" | B12
G2B019 | CRIMINAL | B: "manipulerte regnskap og fangstrapporter" | B36/B17
G2B019 | FAMILY_RELATION | keep A-only "hans tidligere kone" | B10 (possessive kept), B6 (restatement is its own span)
G2B019 | CRIMINAL | keep B-only "Manipulering av regnskap og fangstrapporter" | B6 (heading of finding; document frames it as økonomisk kriminalitet/straffeforfølgelse)
G2B019 | CRIMINAL | keep B-only "Underrapportering av fangstvolum og inntekt" | B28 / B6 (concealment framed as crime; matches agreed G2B020 span)
G2B019 | CRIMINAL | keep B-only "underrapportering av fangstvolum og inntekt" | B28 / B6
G2B019 | ECONOMIC_STATUS | keep B-only "Manglende økonomisk stabilitet" | ECONOMIC_STATUS (evaluative, no figure); B6
G2B020 | EMPLOYMENT | keep A-only "Fisker" | B12
G2B012 | ORGANIZATION | REMOVED bare `Olsen's Catering` at first mention; third: "\"Olsen's Catering\"" (bare form kept for the later unquoted mention) | B35 (quotes inside ORGANIZATION)

## chunk 03

G2B021 | EMPLOYMENT "eid og drevet av Lars Kristian Olsen" | keep | EMPLOYMENT def (business ownership/operation), B35 owner-role; spec silent on "eid og drevet av"
G2B022 | CRIMINAL "tidligere domfellelse" vs "Bergs tidligere domfellelse" | B | B10 (genitive modifying head noun is kept)
G2B023 | CRIMINAL "Ulovlige fiskemetoder" vs "...dokumentert i båtens logg" | A | B36/B1 (evidence frame is not the fact); B34 (text itself calls it illegal)
G2B023 | CRIMINAL "etterforskning av ulovlige fiskemetoder" | keep | CRIMINAL Include (investigative suspicion of a named offence), B34
G2B023 | CRIMINAL "flere ulovlige fiskemetoder" vs "...dokumentert i båtens logg" | A | B2 (quantifier kept), B36 (evidence frame cut)
G2B023 | CRIMINAL "skatteunndragelse" | keep | Precedence chain (bare offence noun sufficient)
G2B023 | CRIMINAL "systematisk manipulering ..." vs "... over en periode på minst tre år" | B | CRIMINAL Boundary rule (trailing time qualifier kept)
G2B023 | HEALTH "diabetes type 2" vs "registrert med diabetes type 2" | B | B1 (participle carrying the fact kept, cf. `registrert som`, B11 `registrert med`)
G2B023 | SEXUAL_ORIENTATION "forhold med en mann" vs "i et forhold med en mann" | B | B31 (male subject, male partner); SEXUAL_ORIENTATION resolved conflicts (`i et forhold med Karianne Nilsen`)
G2B023 | FAMILY_RELATION "sin mor, Anne Lise Hansen" | keep | FAMILY_RELATION def (kinship noun + name), B10
G2B024 | CRIMINAL "tegn på manipulasjon" | keep | B36 (cut `viser`), B28 (manipulation of accounts = deliberate; consistent with agreed G2B023 manipulering)
G2B024 | CRIMINAL "tidligere kriminelle historie, inkludert ..." vs "Mr. Olsens tidligere kriminelle historie, inkludert ..." | B | B10 (genitive kept), B33 (parenthetical absorbed)
G2B024 | CRIMINAL "underrapportert inntekter" vs "underrapportert inntekter og unndratt skatt" | A | B11 / one clause one fact (two distinct offences split)
G2B024 | CRIMINAL "unndratt skatt" vs "underrapportert inntekter og unndratt skatt" | A | B11 / one clause one fact
G2B024 | CRIMINAL "hans tidligere kriminelle historie" | keep | B6 (restatement is its own span), B10
G2B025 | CRIMINAL "tegn på manipulasjon" | keep | B36, B28 (same as G2B024)
G2B025 | EMPLOYMENT "Fisker" | keep | B12 role word of named professional (Fisker Leif Magnus Olsen)
G2B026 | CRIMINAL "manipulerte regnskapsføringen" | keep | B28, B2 (determiner `den` dropped)
G2B026 | CRIMINAL "manipulerte tall" | keep | B28, B36 (`indikerer` cut)
G2B027 | EMPLOYMENT "Fisker" | keep | B12 role word of named professional
G2B028 | FAMILY_RELATION "deres to barn" vs "deres to barn, Magnus (010203-45678) og Ingrid (030405-78901)" | A | B4 (fødselsnummer parenthetical never absorbed), B10 (`deres` kept)
G2B028 | HEALTH "Manglende berikelse for bjørn" | keep | B14 (enrichment is a named need), B6 (restatement)
G2B029 | MARITAL_STATUS "gift med Astrid Åsberg (f. Knudsen)" vs "gift med Astrid Åsberg" | B | B4 (maiden name is a separate datum, not a qualifier); spec silent on name parentheticals
G2B029 | ORGANIZATION "Smakfullt" (agreed) | REMOVED / third: "\"Smakfullt\"" | B35 as corrected (quotes printed around an organisation name stay inside the span)

## chunk 04

G2B031 | CASE_NUMBER | B ("2018/12345") | B23 forward-only: authority precedes number, tag bare number
G2B031 | CRIMINAL (indikasjoner på manipulerte helsedata) | drop | B34 no criminal framing; "manipulerte helsedata" is a discrepancy, not an offence
G2B031 | CRIMINAL (mistanke om økonomisk kriminalitet, dyremishandling og manipulasjon...) | B (three spans: "mistanke om økonomisk kriminalitet", "dyremishandling", "manipulasjon av helseinspeksjonsresultater"; plus heading restatement "økonomisk kriminalitet") | B11 one clause one fact; B6 restatement
G2B031 | LOCATION (Byrkjelo Legesenter) | keep | LOCATION: public institution as venue where diagnosis was made (consistent with agreed hospital spans)
G2B031 | CRIMINAL (Manipulering av helseinspeksjonsresultater) | keep | B6 restatement of the suspected offence in the findings heading
G2B031 | CRIMINAL (gitt uriktige opplysninger ... ligningsnummer 9876543210) | drop | B28 uriktige opplysninger = discrepancy, not asserted evasion
G2B031 | CRIMINAL (skjøt en rev på naboens eiendom) | drop | B34 no criminal framing in the text
G2B031 | HEALTH (Halthet hos kyr) | keep | B6/B14 animal condition restated in finding heading
G2B031 | HEALTH (Mistanke om Bovine Tuberkulose) | keep | HEALTH (d) hedge, animal disease
G2B032 | HEALTH | A ("for lite og mangler tilstrekkelig berikelse") | B14 dimension plus named unmet need (berikelse); B1 drop subject+er
G2B032 | POLITICAL | A (with "sin") | B10 possessive modifying the tagged noun is kept
G2B032 | RELIGIOUS_BELIEF | A ("medlem av den esoteriske gruppen "Lysets Sirkel"") | RELIGIOUS_BELIEF membership clause; B4 label "hans religiøse overbevisning" adds no fact
G2B033 | ANIMAL_INFO (kyllinger) | drop | ANIMAL_INFO exclusive with HEALTH on same characters; noun sits inside the chosen HEALTH span
G2B033 | CASE_NUMBER | A ("X123456 hos namsfogden") | B23 connector (hos) makes the authority part of the span
G2B033 | HEALTH (Syke og skadde ...) | B (bullet: "Syke og skadde kyllinger uten tilgang til veterinærbehandling") | B14 deprivation of vet care attached to the same animals; one fact
G2B033 | HEALTH (salmonellautbrudd) | keep | HEALTH named livestock disease
G2B033 | HEALTH (syke og skadde ...) | B (prose: "syke og skadde kyllinger uten tilgang til nødvendig veterinærbehandling") | B14, B1 (drop "Det er observert")
G2B033 | HEALTH (uten tilgang til nødvendig veterinærbehandling) | B (same long prose span) | as above
G2B033 | HEALTH (uten tilgang til veterinærbehandling) | B (bullet long span) | as above
G2B033 | CRIMINAL (Falsifisering av dokumentasjon) | keep | B34 text itself calls it falsification/forged; B6 restatement
G2B034 | CRIMINAL | B ("under etterforskning for ... (sak nr. 2023/12345, Bergen Politidistrikt)") | B33 parenthetical absorbed; "under" replaces the participle (cf. B1 keeps fact-carrying verb)
G2B034 | CRIMINAL | B (split: "pågående etterforskning for seksuell trakassering" + "økonomisk kriminalitet") | B11 two distinct offences
G2B034 | ECONOMIC_STATUS (Eierens økonomiske situasjon og personlige forhold er uforenlig ...) | drop | B27 needs a stated condition; no hardship disclosed, and span mixes in personal circumstances
G2B035 | CASE_NUMBER | B ("05-12345") | B23 forward-only
G2B035 | CRIMINAL | B ("tidligere dømt for tyveri i 2005 (sak nr. Oslo Tingrett 05-12345)") | Full-clause rule 2 keeps leading modifier; B33
G2B035 | CRIMINAL | A ("forfalskning av veterinærattester") | CRIMINAL boundary rule: offence + object; purpose clause not part of it
G2B036 | CRIMINAL | B ("beslaglagt flere våpen fra Olsens bopel") | CRIMINAL resolved conflicts: separate event reference "etter en hendelse i 2020" not absorbed
G2B036 | POLITICAL (bar en t-skjorte med gruppens logo) | drop | POLITICAL needs stated affiliation/opinion; a worn logo is conduct, not a statement
G2B036 | ANIMAL_INFO (storfe) | drop | ANIMAL_INFO excludes animals as commodity (slaughter context)
G2B037 | CRIMINAL | A ("misbruk av kommunemidler (saksnummer 2020/5678, Nordland politidistrikt)") | B33; B1/B36 framing "skandale i 2020 knyttet til" cut, year stays DATE_TIME
G2B037 | LOCATION (Leknes Legesenter) | keep | as G2B031
G2B037 | BEHAVIORAL_PATTERN (Forholdet har vært preget av flere krangler) | keep | B18 keeps actor-establishing subject; recurring conduct of the named couple
G2B037 | BEHAVIORAL_PATTERN (over flere tilsynsbesøk ikke fremlagt ...) | keep | BEHAVIORAL_PATTERN include: non-cooperation with authorities as a pattern
G2B038 | CASE_NUMBER | B ("2020-1234") | B23 forward-only
G2B038 | POLITICAL | A (with "sin") | B10
G2B038 | HEALTH (Manglende stell og underernæring) | keep | B14 stell / B6 restatement in heading; single span per B14 example "Utilstrekkelig fôring, vanning, og stell"
G2B039 | CASE_NUMBER | B ("2018-12345") | B23 forward-only
G2B032 | ORGANIZATION | ADDED `"Bergen Villmarkspark"` (agreed unquoted form kept for the unquoted occurrence) | B35 as corrected: printed quotes stay inside ORGANIZATION

## chunk 05

G2B041 | CRIMINAL | A | B1 keep-list (`erkjente` carries the fact); "under intervjuet" forced by contiguity
G2B041 | CRIMINAL | B | B36/B33 convention: evidence noun kept like `tegn på`; resolved conflict forfalskning av veterinærattester
G2B041 | CRIMINAL | keep | manipulering of certificate dates sits in the forgery-evidence list; fraud-framed (Precedence chain, B6)
G2B041 | HEALTH | A | B1 starts at the fact, `transport av dyr med` is activity; B4 alt-name parenthetical absorbed
G2B042 | CRIMINAL | keep | weapons ban is a legal sanction of the conviction, like `besøksforbud` (CRIMINAL)
G2B043 | CRIMINAL | drop | B34: report about suspected neglect, not framed criminally
G2B043 | CRIMINAL | keep | B34 names `politianmeldt` explicitly
G2B043 | EMPLOYMENT | B | B12/B35: role stays, owner's name stays PERSON, so `eiet og drevet`
G2B043 | HEALTH | B | B11 one clause one fact: generic `Alvorlig forsømmelse` head not a named need; `tegn på underernæring` already agreed; B4 alt names absorbed
G2B043 | ANIMAL_INFO | drop | "annen hest": plain re-mention, adds nothing beyond `Flere hester` + name (ANIMAL_INFO Exclude)
G2B043 | ANIMAL_INFO | drop | "hest": same
G2B044 | CRIMINAL | B | same as G2B041 (evidence noun kept; B11 `inkludert` itemisation absorbed)
G2B045 | ANIMAL_INFO | B | B11/B4: parenthetical breakdown itemises the count, one span (Golden Retriever alone dropped)
G2B045 | ANIMAL_INFO | B | as above (Jack Russell Terrier alone dropped)
G2B045 | ANIMAL_INFO | B | as above (`fire hunder` alone dropped)
G2B045 | ANIMAL_INFO | B | as above (`to Siberian Huskies` alone dropped)
G2B045 | BEHAVIORAL_PATTERN | drop | definition: no recurrence/pattern marker, an observed attitude not conduct
G2B045 | BEHAVIORAL_PATTERN | drop | same
G2B045 | HEALTH | B | B11 two conditions joined by og: `Alvorlig underernæring` + `dehydrering hos alle fire hunder`
G2B045 | HEALTH | B | B11: `Manglende pels` + `sår` + `skader på flere av hundene` (+ bare `skader` of next sentence)
G2B045 | HEALTH | A | agreed convention keeps shared "manglende tilgang til X og Y" whole; B14 shelter/environment
G2B045 | HEALTH | B | B11: `synlige tegn til manglende pels` + `skader` split
G2B045 | MARITAL_STATUS | A | Full clause: leading adverb `for tiden` stays; B1 drops `er`
G2B045 | SEXUAL_ORIENTATION | A | B1 keep-list `registrert som` states the record itself (not an attribution verb)
G2B046 | CRIMINAL | keep | B34 `meldt til politiet` is a police report (B3 outcome as own span)
G2B046 | CRIMINAL | third: "registrert med to dommer; en for bedrageri" | B1 `registrert` carries fact (cf. agreed `registrert dom`); B33 (2018) split to DATE_TIME
G2B046 | CRIMINAL | third: "en for ulovlig besittelse av våpen" | B11 second fact after `og`; numeral `en` kept (B2)
G2B047 | HEALTH | A | B1 `registrert med` kept like `registrert som`
G2B048 | CRIMINAL | A | B1 keep-list (`innrømmet`)
G2B049 | CRIMINAL | B | B11 `inkludert` itemisation under the offence; `sin kriminelle fortid` left to the BEHAVIORAL span, avoids same-character overlap
G2B049 | BEHAVIORAL_PATTERN | keep | B18 subject kept, non-disclosure as repeated conduct; B6 restatement
G2B049 | BEHAVIORAL_PATTERN | keep | `gjentatte ganger` repetition marker, human subject (B18)
G2B050 | CRIMINAL | A | precedent `involvert i en offentlig skandale...` (B24 example); B2 only strips a leading determiner; B33 sak parenthetical
G2B050 | CRIMINAL | keep | concealment/forgery elaboration (B28, B6)
G2B050 | CRIMINAL | B | B1 start at predicate; leading `systematisk` before auxiliary `har` cannot stay contiguous
G2B050 | HEALTH | A | B1 `registrert med` kept like `registrert som`
G2B043 | ORGANIZATION | REMOVED `Lykkelig Hest`, third: `"Lykkelig Hest,"` and `"Lykkelig Hest"` | B35 quotes inside the span (agreed span lacked quotes)
G2B044 | ORGANIZATION | REMOVED `Olsen's Osteglede`, third: `"Olsen's Osteglede,"` and `"Olsen's Osteglede"` | B35
G2B046 | ORGANIZATION | REMOVED-in-part: quoted occurrence now `"Kristian's Kaker"`; unquoted occurrences keep `Kristian's Kaker` | B35
G2B047 | ORGANIZATION | REMOVED-in-part: quoted occurrence now `"Astrid's Kjøkken,"`; unquoted keep `Astrid's Kjøkken` | B35
G2B050 | ORGANIZATION | REMOVED-in-part: quoted occurrence now `"Olsen's Økologiske Melk"`; unquoted keep `Olsen's Økologiske Melk` | B35

## chunk 06

G2B051 | ANIMAL_INFO | "Storfe" | keep | ANIMAL_INFO include: species noun names the animals the document is about
G2B051 | BEHAVIORAL_PATTERN | "har et anstrengt forhold til Lars Henrik..." vs "anstrengt forhold..." | B: "anstrengt forhold til Lars Henrik, preget av krangling og til tider fysisk vold" | B1 drop linking "har"; B2 drop "et"
G2B051 | BEHAVIORAL_PATTERN | "høylytte krangler" | drop | BEHAVIORAL_PATTERN def/B18: span names no actor (neighbours report unattributed quarrels)
G2B051 | BEHAVIORAL_PATTERN | "mistenkelig aktivitet nattestid" | drop | BEHAVIORAL_PATTERN def/B18: no identified actor, no conduct specified
G2B051 | BEHAVIORAL_PATTERN | "svært uforberedt og motvillig til å samarbeide" vs "motvillig til å samarbeide" | A: "svært uforberedt og motvillig til å samarbeide" | BEHAVIORAL_PATTERN boundary: include the coordinated adjective; B1 drop "virket"
G2B051 | BEHAVIORAL_PATTERN | "vist grov uaktsomhet i sitt ansvar for dyrenes velferd" | keep, extent third: "Lars Henrik Søderlund har vist grov uaktsomhet i sitt ansvar for dyrenes velferd" | B18 BEHAVIORAL_PATTERN keeps its subject (named actor + verb carry the actor); neglect by a named person is BEHAVIORAL_PATTERN (Removed types)
G2B051 | CASE_NUMBER | "2018/5678" vs "2018/5678, samme tingrett" | B | B23: comma counts as connector; authority goes with the number
G2B051 | CRIMINAL | "familiens kriminelle historikk" vs "kriminelle historikk" | A | B10 keep genitive modifying the tagged head noun
G2B051 | CRIMINAL | "grov utnyttelse" | keep | CRIMINAL include: aggravated exploitation of a named worker stated as a specific incident
G2B051 | CRIMINAL | "truet med hjemsendelse ved klager" | keep | CRIMINAL include: threats against a named victim stated as a specific incident; B1 drop "ble"
G2B051 | ECONOMIC_STATUS | "Hans personlige og økonomiske problemer" vs without "Hans" | A | B10 keep possessive modifying the head noun
G2B051 | FAMILY_RELATION | "broren" | keep | FAMILY_RELATION include kinship noun; B6 restatement is its own span
G2B051 | HEALTH | "Alvorlige tilfeller av munn- og klovsyke hos flere kyr" vs without host | A | HEALTH (c) full noun phrase with trailing qualifier; matches agreed practice (G2B054/055 spans keep "hos ...")
G2B051 | HEALTH | "sliter også med diabetes type 2" vs "diabetes type 2" | A | HEALTH (a)/overlap policy: "sliter med" carries the affliction like "lider av" (kept, cf. agreed "slet med alvorlig depresjon")
G2B051 | HEALTH | "umiddelbar fare for ytterligere forverring av dyrenes helsetilstand" | keep | HEALTH include: states ongoing deterioration of animals' condition; B6 agency finding; B17 subject-is-the-fact
G2B052 | CRIMINAL | "Økonomisk uredelighet (gjeld over 650 000 NOK, forfalskede skattemeldinger)" vs split | A | B33: CRIMINAL absorbs elaborating parenthetical (amount, offence detail)
G2B052 | HEALTH | "Johne's sykdom hos flere kyr" | keep | HEALTH (c) trailing qualifier, same extent as ruled for G2B051; B6 restatement in observation bullet
G2B053 | CRIMINAL | "forfalsket deler av ..." vs "innrømmet å ha forfalsket deler av ..." | B | B1 keep "innrømmet" (verb carrying the fact)
G2B053 | FAMILY_RELATION | "deres to barn" vs "samværskonflikt om deres to barn" | B | Global rule 2 full clause; relation clause includes its custody predicate (cf. B32 "deler omsorgen for deres to barn"); B10 possessive kept
G2B053 | POLITICAL | "medlem av "Norges Frie Fiskere" (politisk parti med ...)" vs without parenthetical | A | POLITICAL boundary: ideological descriptor belongs to the span; B4 parenthetical only qualifies the same fact (no separate datum)
G2B055 | CRIMINAL | "Manipulering av dokumentasjon" | keep | B6 restatement of agreed manipulation finding; B17 subject-is-the-fact (drop "er uakseptabelt...")
G2B055 | HEALTH | "Mistanke om bovin tuberkulose hos en ku" vs without host | A | HEALTH (d) hedge included; HEALTH (c) trailing qualifier, consistent with agreed "Alvorlig halthet hos minst 5 av 12 undersøkte kyr"
G2B055 | HEALTH | "mistanke om bovin tuberkulose hos en voksen ku" vs without host | A | same as above
G2B056 | ADDRESS | "Storgata 34B, Oslo" vs "Storgata 34B" | A | ADDRESS longer-form preference; matches agreed "Fjellveien 12B, Bergen" (G2B058/059)
G2B056 | CRIMINAL | "historie med vold i nære relasjoner" vs "vold i nære relasjoner" | A | CRIMINAL boundary: pull in the noun establishing it as a past record (cf. "dom for vold i nære relasjoner"); B2 drops only "en"; CRIMINAL > FAMILY_RELATION
G2B056 | CRIMINAL | "kriminelle fortiden" | keep | B6 restatement of agreed "kriminell fortid"; B2 drops "den"
G2B056 | FAMILY_RELATION | "deres barn" vs B's "pågående rettslig prosess med ekskona om omsorg for deres barn" | B | Global rule 2 full clause; custody-process predicate belongs to the relation clause (as G2B053/058/059); subsumes bare "deres barn"
G2B056 | FAMILY_RELATION | "ekskona" vs B's same long span | B (long span; bare "ekskona" not separately needed, agreed "ekskona, Annelise Hansen" stands) | same as above
G2B056 | RELIGIOUS_BELIEF | "ingen formell religiøs tilknytning" | drop | B15: absence of formal affiliation discloses no belief (not ateist/agnostiker)
G2B057 | CRIMINAL | "forfalsket skattemeldinger for 2022 og 2023" vs "innrømmet å ha forfalsket ..." | B | B1 keep "innrømmet"
G2B057 | FAMILY_RELATION | "hans to barn" vs "hans to barn, Elias" | B | FAMILY_RELATION boundary: run through the first named individual; stop before fnr parenthetical (B4)
G2B057 | FAMILY_RELATION | "partner, Annelise Johansen" vs "hans partner, Annelise Johansen" | B | B10 keep possessive
G2B058 | FAMILY_RELATION | "deres to barn" vs "delt omsorg for deres to barn" | B | same as G2B053 (relation clause includes custody predicate; B1 drops "har")
G2B059 | CRIMINAL | "Multiple instances of falsified export certificates for dogs, including ..." vs "falsified export certificates for dogs" | A | B11 "including" itemisation absorbed; B2 quantifier kept
G2B059 | CRIMINAL | "The falsification of certificates" vs "falsification of certificates" | B | B2 drop leading determiner (English "The"); B17
G2B059 | CRIMINAL | "undeclared income, fabricated invoices, and manipulated expense reports totaling approximately 150,000 NOK over the past fiscal year" vs three spans | B (three spans) | B11 / one clause, one fact: three distinct offences; relative time "over the past fiscal year" is not a dated qualifier
G2B059 | FAMILY_RELATION | "their two children" vs "shares custody of their two children" | B | same as G2B053; custody verb is the fact (B36 last sentence)
G2B059 | FINANCIAL | "approximately 150,000 NOK" | drop | Precedence CRIMINAL > FINANCIAL: amount lies inside the offence-naming clause, nothing else on those characters
G2B059 | POLITICAL | "known member of the Fremskrittspartiet" vs "member of the Fremskrittspartiet" | B | "known" is a reporting/attribution modifier, cut like other reporting frames; B2 drop "a"
G2B059 | SEXUAL_ORIENTATION | "bisexuality" vs "her bisexuality" | B | B10 keep possessive (cf. "hans homofile legning")
G2B059 | LOCATION | "Bergen Medisinske Senter" | keep | LOCATION include: institution named as the place of care (cf. agreed "Haukeland Sykehus")
G2B060 | CRIMINAL | "dømt for bedrageri i 2015 (...)" vs "tidligere dømt for bedrageri i 2015 (...)" | B | Global rule 2 keep leading adverb (cf. agreed "tidligere domfellelser"); B1 drops "er"; B33 parenthetical absorbed
G2B060 | CRIMINAL | "manipulert regnskapet for å unngå konkurs" vs "innrømmet å ha manipulert ..." | B | B1 keep "innrømmet"
G2B060 | EMPLOYMENT | "hans tidligere forretningspartner" vs "..., Astrid Olsen" | A | EMPLOYMENT excludes personal names (PERSON); forretningspartner is EMPLOYMENT; B10 possessive kept
G2B060 | CRIMINAL | "forsøk på å skjule transaksjoner knyttet til et selskap registrert på Kypros" | keep | B28 asserted intent to conceal (offshore transactions) under stated suspicion of misligheter
G2B060 | CRIMINAL | "forsøk på å skjule virksomhetens reelle økonomiske situasjon" | keep | B28 asserted intent to conceal; B6 restatement of agreed forged-accounts clause
G2B060 | CRIMINAL | "mistanke om misligheter" | keep | CRIMINAL include: investigator-stated suspicion + offence noun (mislighet)
G2B060 | CRIMINAL | "skjulte transaksjoner" | keep | B6 restatement of the concealment finding (observation bullet)
G2B052 | ORGANIZATION | agreed "Olsen's Økologiske Melkegård" | REMOVED -> third: "«Olsen's Økologiske Melkegård»" | B35: quotation marks printed around an organisation name stay inside the span (only occurrence is in guillemets)
G2B052 | FINANCIAL | agreed "gjeld over 650 000 NOK" (only inside the CRIMINAL parenthetical) | REMOVED | Precedence CRIMINAL > FINANCIAL: nothing else on the characters of an offence clause; B33 nests only identifiers
G2B055 | ORGANIZATION | "«Øvrevoll Gård»" (quoted occurrence) | ADDED | B35 quotes inside ORGANIZATION; B19 subject organisation (bare form stays for unquoted occurrences)
G2B056 | ORGANIZATION | agreed "Kristian's Kaker" (both occurrences are quoted) | REMOVED -> third: '"Kristian\'s Kaker,"' and '"Kristian\'s Kaker"' | B35 + B5: quotes stay inside ORGANIZATION; punctuation printed inside the closing quote is kept
G2B057 | ORGANIZATION | "Olsen's Økologiske Melkeprodukter," (quoted occurrence) | ADDED (bare form kept for unquoted occurrences) | B35 + B5

## chunk 07

G2B061 | CRIMINAL | A | B3/Definition: offence phrase only; the "for å unngå kostnader" purpose clause is motive, not the offence
G2B061 | FAMILY_RELATION | B | Full-clause rule (Global 2): custody conflict over the children is the family fact; B10 keeps "deres"
G2B062 | CRIMINAL | B | B34 (text calls them forfalsket) + B36 (a main verb that is itself the fact stays: "presenterte" = use of forged certificates)
G2B063 | CRIMINAL | keep | B34 (act the text itself calls illegal); B10 keeps possessive "hans"
G2B065 | ANIMAL_INFO | keep | ANIMAL_INFO Include (what the document is about: poultry operation); B4 alternative-name parenthetical absorbed
G2B065 | CRIMINAL | keep | B34 "forfalsket" + B6 (restatement in the evaluation line is its own span)
G2B065 | RELIGIOUS_BELIEF | B | Place phrase "i hans bolig" is not part of the belief fact (Boundary: stop at place phrase)
G2B066 | HEALTH | drop | "Mangelfull hygiene og stell" heading fuses premises hygiene (untagged by both annotators everywhere) with care; no non-contiguous split available (one clause, one fact)
G2B066 | HEALTH | keep | HEALTH animal Include + B6 restatement ("Manglende veterinærbehandling" heading, as agreed "Manglende stell av dyr" in G2B067)
G2B067 | CRIMINAL | A | B1: drop aux "vært"/adverb that cannot be kept contiguously; start at "anmeldt for"
G2B067 | CRIMINAL | keep | Definition: referral to Økokrim for investigation is criminally framed (police-report analogue), subject "Saken" dropped per B1
G2B067 | CRIMINAL | REMOVED (agreed) "uregistrert rifle i Olsens bolig" | B34: unregistered weapon is CRIMINAL only when stated illegal/criminally framed; here only "funnet under inspeksjonen"
G2B068 | ORGANIZATION | keep | Boundary rule/B35: generic noun directly attached + quotes stay in the name (`Restaurant "Sjøstjerna"`)
G2B068 | ORGANIZATION | drop | lowercase running-text "restaurant" is a generic noun, not the name; covered by ADDED `"Sjøstjerna"`
G2B068 | ORGANIZATION | REMOVED (agreed) "Sjøstjerna" | B35 (corrected): quotation marks printed round an organisation name stay inside the span
G2B068 | ORGANIZATION | ADDED `"Sjøstjerna"` | B35: quoted name inside span (covers "restaurant "Sjøstjerna"" and "Videre drift av "Sjøstjerna"")
G2B069 | FAMILY_RELATION | B | Full-clause rule (Global 2), consistent with G2B061; "their two children" alone is the bare keyword
G2B070 | CRIMINAL | A | B1: "har tidligere blitt dømt" cannot be kept contiguously without aux "blitt"; start at "dømt for"; B33 parenthetical kept
G2B070 | FINANCIAL | drop | Precedence CRIMINAL > FINANCIAL: the amount sits inside the offence clause (B33), not a separate sentence

## chunk 08

G2B073 | CRIMINAL | keep (A-only) | CRIMINAL def; B33 (case-ref parenthetical absorbed); B34 (police case, framed criminal)
G2B073 | CRIMINAL | keep (B-only) | B34 (text calls it ulovlig); B6 (restatement is own span)
G2B073 | SEXUAL_ORIENTATION | drop | no orientation disclosed; B24/precedence CRIMINAL > SEXUAL_ORIENTATION
G2B074 | RELIGIOUS_BELIEF | B | B10 (possessive modifying head noun kept)
G2B075 | CRIMINAL | A | B17 (subject is the fact; bare "falsified" states nothing), B34 (forfalsket = criminal framing)
G2B075 | ECONOMIC_STATUS | drop | precedence FINANCIAL > ECONOMIC_STATUS; covered by the FINANCIAL span
G2B075 | FINANCIAL | B | B27/B10 (keep possessive noun phrase), B33 (elaborating parenthetical absorbed)
G2B075 | HEALTH | keep ("suffers from type 2 diabetes") | HEALTH (b)/(a), B1; split from medication
G2B075 | HEALTH | drop ("treated by Dr. Ingrid Olsen at Bergen Medical Center") | HEALTH def: no condition stated, provider only; B4; B12 (treatment by a professional not tagged)
G2B075 | MEDICATION | keep | MEDICATION def: drug noun "medication", split from diagnosis per HEALTH (b)
G2B075 | SEXUAL_ORIENTATION | B | B31 (same-sex partner), Global rule 2 (leading adverb kept)
G2B075 | HEALTH | drop ("type 2 diabetes managed with medication") | HEALTH (b): diagnosis and medication are split
G2B076 | BEHAVIORAL_PATTERN | A | Global rule 2 (trailing qualifier part of same fact); B9 example "spesielt på morgenen"
G2B076 | HEALTH | A | Global rule 2; consistent with agreed "tegn på vanskjøtsel av flere dyr"
G2B076 | POLITICAL | B | B10 (possessive kept), B5 (quote closed)
G2B076 | RELIGIOUS_BELIEF | B | B10
G2B077 | BEHAVIORAL_PATTERN | A | B18 (keeps actor), B10
G2B077 | FINANCIAL | B | Global rule 2 (leading modifier kept), B33
G2B077 | HEALTH | drop ("diagnosed by Dr. Anne Lise Hansen at Haukeland University Hospital") | HEALTH def: provider/source of the diagnosis, not a condition; B4; diagnosis already tagged
G2B077 | HEALTH | drop ("treated by psychiatrist Dr. Johan Karlsen") | same; psychiatrist already EMPLOYMENT (B12)
G2B077 | MARITAL_STATUS | A | Global rule 2 (leading adverb kept)
G2B078 | MEDICATION | A | MEDICATION boundary / HEALTH Resolved conflicts (longer form with treatment verb)
G2B079 | CRIMINAL | A | B17 (subject carries the fact), B34 (forfalsket)
G2B080 | MEDICATION | A | MEDICATION boundary / HEALTH Resolved conflicts (longer form)
G2B073 | ORGANIZATION | REMOVED agreed Smaksopplevelser -> third: ""Smaksopplevelser"" | B35 (quotes stay inside ORGANIZATION)
G2B075 | ORGANIZATION | REMOVED agreed Blomstrende Bergen -> third: "'Blomstrende Bergen'" | B35 (quotes stay inside ORGANIZATION)
G2B079 | ORGANIZATION | REMOVED agreed Skjønnhet & Velvære -> third: ""Skjønnhet & Velvære"" | B35 (quotes stay inside ORGANIZATION)

## chunk 09

G2B081 | BEHAVIORAL_PATTERN | keep (Eriksens tilbakeholdelse...) | BP deceptive/evasive conduct, B18 actor kept, B6 restatement
G2B081 | BEHAVIORAL_PATTERN | keep (Lars Magnus Eriksen aktivt har tilbakeholdt...) | BP deceptive conduct, B18
G2B081 | CRIMINAL | A | B28/B1: attempt + forgery is one fact; cf. agreed "forsøk på å forfalske"
G2B081 | CRIMINAL | drop (hans kriminelle fortid) | CRIMINAL needs a named offence; vague mention (offences specified elsewhere in doc)
G2B081 | CRIMINAL | drop (sin kriminelle fortid) | same
G2B082 | CRIMINAL | A | Global rule 2 full clause (leading adverbial kept), B1 drops "har"
G2B082 | HEALTH | keep (dyrenes sykdomstilstand) | HEALTH animal condition, B6 restatement in observation list
G2B082 | HEALTH | keep (syke dyr) | HEALTH animal condition, B6
G2B082 | ORGANIZATION | A | ORGANIZATION boundary / B35: quotes inside, generic noun "Dyrebutikken" dropped
G2B083 | CRIMINAL | A | Global rule 2 (leading adverbial kept)
G2B083 | CRIMINAL | A | B2 example keeps "tidligere"; B33 parenthetical absorbed
G2B083 | FAMILY_RELATION | A | Full clause, gold practice for scandal clauses (B24 analogue); type itself spec-silent
G2B083 | FINANCIAL | drop (over 200,000 NOK) | Precedence CRIMINAL > FINANCIAL: amount sits inside agreed offence clause
G2B083 | ORGANIZATION | A | ORGANIZATION boundary / B35 quotes inside
G2B084 | BEHAVIORAL_PATTERN | keep (Eierens manglende åpenhet...) | BP evasiveness with authorities, B18 actor kept
G2B084 | BEHAVIORAL_PATTERN | keep (gjentatte ganger unnlatt å opplyse...) | BP evasiveness, repetition marker
G2B084 | MEDICATION | A (insulin) | MEDICATION boundary: drug name, stop before purpose; consistent with agreed bare "antidepressiva"
G2B084 | CRIMINAL | drop (sin kriminelle fortid) | vague, no offence named
G2B085 | BEHAVIORAL_PATTERN | keep | BP non-cooperation with inspectors (positive example shape)
G2B085 | HEALTH | keep (påvirker hennes konsentrasjon og hukommelse) | HEALTH symptom; "hevder" frame cut (reporting frame)
G2B085 | HEALTH | A | B10 possessive kept ("sin"); agreed "sin diagnose med..." same
G2B086 | FINANCIAL | drop (150.000 NOK) | Precedence: amount inside agreed CRIMINAL clause
G2B086 | HEALTH | A | B14 veterinary care unmet + B17 keep subject-fact, drop evaluative "er et alvorlig brudd"
G2B087 | BEHAVIORAL_PATTERN | keep (Askeladds unnlatelse...) | BP evasiveness, B18
G2B087 | BEHAVIORAL_PATTERN | keep (Eier av "Søtt & Salt" har unnlatt...) | BP evasiveness, B18
G2B087 | BEHAVIORAL_PATTERN | keep (gitt uriktige opplysninger om sin fortid) | BP deceptive conduct
G2B087 | CRIMINAL | A | hedge "tegn på" is part of clause (HEALTH (d), B36 example keeps "tegn på")
G2B087 | FAMILY_RELATION | keep (affære med en tidligere ansatt) | partner gender unknown so B31 not triggered; intimate relationship; rumour still tagged (reporting-frame rule)
G2B087 | FINANCIAL | A | FINANCIAL boundary: leading qualifier "dokumentert" kept
G2B087 | HEALTH | A | diagnostic verb "påvist" kept (diagnostic frame inside clause)
G2B087 | MEDICATION | A (insulin) | MEDICATION boundary
G2B087 | CRIMINAL | drop (sin kriminelle fortid) | vague, no offence named
G2B087 | ORGANIZATION | drop (Bakeri "Søtt & Salt") | ORGANIZATION boundary: generic noun dropped; quoted name already agreed
G2B088 | CRIMINAL | drop (gjentatte bøter for brudd på hygieneforskrifter) | B34 regulatory breach not framed criminally
G2B088 | FAMILY_RELATION | A | FAMILY_RELATION: children + partner one relation clause (example 4); B32 children enumeration stays one span; B4 stops before "(f. 1980)"
G2B088 | ORGANIZATION | drop (Cateringvirksomhet "Midgardsmat") | ORGANIZATION boundary: generic noun dropped; quoted name already agreed
G2B089 | CRIMINAL | A | hedge "tegn på" kept, as 087
G2B089 | EMPLOYMENT | keep (Fisker) | B12 role word of named professional
G2B089 | FAMILY_RELATION | third: "to barn, Emma (10) og Tobias (14), med sin ekskone, Inger Lise Olsen" | as 088 (one clause) but stop before "(f. Berg)" like PERSON/B4
G2B089 | CRIMINAL | drop (tidligere kriminelle historie) | vague, no offence named
G2B090 | ANIMAL_INFO | A | ANIMAL_INFO boundary: quantifier kept, B11 inkludert itemisation absorbed, B2 drops "et"
G2B090 | HEALTH | keep (mangler tydelige spor av veterinærkontroll) | B14 veterinary care unmet; main verb is the fact

## chunk 10

G2B091 | HEALTH | B: "Deres magre utseende" | B10 (possessive modifying tagged head kept)
G2B091 | HEALTH | A: "svært hardt filtret, med store floker i pelsen" | one clause/one fact; med-phrase elaborates same condition (B11/B33 spirit)
G2B091 | HEALTH | keep "alvorlige filtringen i pelsen" | B17 subject is the fact, B2 drops "Den"; B6 restatement
G2B091 | HEALTH | drop "svært smertefullt for kattene" | hedged ("kan være"), evaluative commentary, B17
G2B092 | BEHAVIORAL_PATTERN | B: "eieren rope til og sparke etter hunden en gang" | B18 (actor named; outer reporting wrapper "Observerte" dropped)
G2B092 | HEALTH | A: "noen sår på snuten" | B3/B9 comma-introduced speculation on cause ("muligens etter slagsmål") is not part of the fact
G2B092 | ANIMAL_INFO | keep "hannhund" | ANIMAL_INFO descriptors (sex/species); reporting frame "tror det er en" cut, B2
G2B092 | HEALTH | keep "redd og usikker" | HEALTH animal fear/apathy; B6 restatement; B1 drops "Den virker"
G2B093 | HEALTH | third: "beveger seg lite" + "generelt utilpasse" (= B) | One clause, one fact; B1 drops "virker"
G2B094 | CRIMINAL | B: "erkjente å ha endret datoer ... veterinærundersøkelser" | B1 (erkjente carries the fact, kept)
G2B094 | HEALTH | B: "smittsom sykdom (blåtunge)" | HEALTH is the condition, not the animal; B4 parenthetical alt name absorbed
G2B094 | FAMILY_RELATION | keep "sin kone" | FAMILY_RELATION spouse noun w/o status word; B10 keeps possessive
G2B096 | CRIMINAL | B: "forfalsket dokumentasjon av dyrehelse" | B34 (mangelfull is administrative, not criminal); offence is forfalsket
G2B096 | CRIMINAL | B: "innrømmet også å ha forfalsket skatteopplysninger for de siste tre årene" | B1 (innrømmet kept)
G2B096 | HEALTH | A: "tegn på Johnes sykdom" | One clause, one fact; B36 drops "viste"
G2B096 | HEALTH | A: "mastitt" | One clause, one fact (two conjoined diseases split)
G2B096 | SEXUAL_ORIENTATION | keep "hennes nåværende samboer, Kristin Hansen" | B31 (female subject, female partner); precedence over MARITAL_STATUS; B10
G2B096 | MARITAL_STATUS | drop "hennes nåværende samboer, Kristin Hansen" | B31 / SEXUAL_ORIENTATION > MARITAL_STATUS
G2B098 | FAMILY_RELATION | B: "currently in a relationship with Ingrid Jensen" | Global rule 2 (leading adverb kept), B1 drops only "is"; opposite-sex so not B31
G2B099 | BEHAVIORAL_PATTERN | A: "utagerende og usammenhengende under inspeksjonen" | BEHAVIORAL_PATTERN boundary rule (situational qualifier included); B1 drops "fremstår"
G2B099 | CRIMINAL | B: "innrømmet også å ha forfalsket skatteopplysninger (saksnummer ...) for å ..." | B1 (innrømmet kept), B33 (case-number parenthetical absorbed)
G2B099 | HEALTH | keep "unødvendig lidelse for dyret" | asserted animal suffering from missing vet care (B14); B6 restatement
G2B100 | CRIMINAL | B: "innrømmet under inspeksjonen å ha forfalsket dokumentene for å unngå konkurs" | B1 (innrømmet kept)
G2B100 | CRIMINAL | A: "økonomisk kriminalitet" | B36 spirit: hedge/evidential frame "kan knyttes til" cut

## chunk 11

G2B101 | HEALTH "salmonellautbruddet" | keep | B6 restatement own span; named animal disease (HEALTH Include)
G2B102 | CRIMINAL boundary | third: "ulovlig oppbevaring av en rifle (registrert våpennummer: 1234567)" | B33 parenthetical stays; CRIMINAL boundary lists only time qualifier, so "i bakrommet" cut
G2B102 | POLITICAL "aktivt distribuerer dette materialet" | drop | POLITICAL overlap: action on belief is BEHAVIORAL_PATTERN
G2B102 | BEHAVIORAL_PATTERN "hun aktivt distribuerer dette materialet" | keep | B18 actor kept; POLITICAL overlap (conduct clause)
G2B102 | LOCATION "Norge" | keep | LOCATION Include: place named in prose
G2B103 | BEHAVIORAL_PATTERN boundary | A | Boundary rule: include target/context qualifier
G2B103 | POLITICAL boundary | A | POLITICAL Boundary: party + "aktiv i lokalpolitikken" kept as one span
G2B104 | CRIMINAL boundary | B | B13/B1: event noun phrase with year; DATE_TIME 2018 nests
G2B104 | HEALTH "avmagring" | A | B4 + B33 (only CRIMINAL/FINANCIAL absorb); one clause, one fact
G2B104 | HEALTH "diaré" | A | same
G2B104 | HEALTH "forhøyet celletall i melk" | A | same
G2B104 | HEALTH "hovne juver" | A | same
G2B104 | HEALTH "mistanke om paratuberkulose" | A | same (hedge kept, HEALTH (d))
G2B104 | HEALTH "står under behandling for kronisk depresjon" | B | B1 drops linking verb; HEALTH (a) keep treatment frame
G2B104 | HEALTH "symptomer på mastitt" | A | B4 + B33 as above
G2B105 | ANIMAL_INFO | B | ANIMAL_INFO boundary: species + attached breed appositive; B4 qualifier
G2B105 | CRIMINAL "Mistanken om skattesvik" | B (whole) | CRIMINAL positive ex. 4: shared process noun, coordinated offences one span
G2B105 | CRIMINAL "forfalskning av helseattester for salg av valper" | B (whole) | same
G2B105 | FAMILY_RELATION | A | B11: comma relative clause is a separate fact
G2B105 | CRIMINAL "uregistrert rifle i boligen" | drop | B34: text never frames it as illegal/criminal
G2B107 | CRIMINAL "Import og bruk av forbudte stoffer ... (hydrokinon, kvikksølvforbindelser)" | drop | B34: prohibited-substance finding is regulatory
G2B107 | CRIMINAL "importerer og bruker stoffer som er forbudt ..." | drop | B34
G2B107 | CRIMINAL "uregistrert pistol i en ulåst skuff på kontoret" | keep | B34: text itself states "Ulovlig besittelse av våpen"
G2B108 | HEALTH "tegn på blåtunge" | A | Global rule 2/B1; explanatory appositive not part of the fact
G2B108 | HEALTH "utbrudd av blåtunge" | B | HEALTH (c): trailing location qualifier; LOCATION nests
G2B109 | CRIMINAL boundary | A | Global rule 2 (leading "tidligere" modifier); B33 parenthetical
G2B109 | CRIMINAL "import av uregistrerte plantearter" | keep | B6 restatement own span; offence called ulovlig elsewhere (B34)
G2B110 | CRIMINAL boundary | A | Global rule 2 ("tidligere"); B33 parenthetical

## chunk 12

G2B111 | ANIMAL_INFO "reptiler" | drop | Animal_info Exclude: plain re-mention adds no count/name (count is in agreed "flere reptiler")
G2B111 | CRIMINAL "Ulovlig import av dyr" | keep | Definition (act text calls illegal), B34, B6 restatement
G2B111 | HEALTH | A | B14 + B14 examples (structure + named unmet need kept together); also ADDED same span for the "Vi har observert" restatement (B6)
G2B111 | CRIMINAL "Import av reptiler og fugler uten ... helsesertifikater" | keep | B6 restatement, B11 (inkludert absorbed), B34 (text calls it ulovlig import)
G2B111 | CRIMINAL "importert flere reptiler ... CITES-tillatelser" | keep | B6 restatement, B34 (text calls it ulovlig import)
G2B112 | POLITICAL | A | POLITICAL boundary (verb+name; trailing appositive is a separate descriptor/fact, B3/B9)
G2B114 | CRIMINAL "Dokumentforfalskning" | keep | CRIMINAL bare offense noun sufficient; B6 restatement
G2B114 | CRIMINAL "Bruk av DDT på potetavlingen" | keep | B34 (text calls it "ulovlig bruk", "forbudt", "ulovlige handlinger"), B6
G2B114 | CRIMINAL "Manipulerte og ufullstendige dokumenter knyttet til sprøytemiddelbruk" | keep | B34 (text itself heads it Dokumentforfalskning), B6
G2B114 | CRIMINAL "bruk av DDT på potetavlingen" | keep | B34, B6 (summary-prose restatement, distinct string)
G2B114 | CRIMINAL "mistenkelig manipulert" | drop | B28 (irregularity not asserted intent); vacuous without subject (B17)
G2B115 | FAMILY_RELATION | B | B2 (drop leading "en"); tag kept as intimate-partner fact (borderline, see open questions)
G2B115 | ORGANIZATION | A | ORGANIZATION boundary (drop leading generic noun "Cateringfirma"), B35 (quotes stay inside)
G2B115 | POLITICAL | A | POLITICAL boundary (verb+name; trailing appositive separate)
G2B116 | CRIMINAL "forfalskning av helsedokumenter og journaler" | A | B11/B3 (purpose clause "for å skjule disse forholdene" adds no offence fact)
G2B116 | CRIMINAL "manipulert for å skjule økonomiske tap" | third: "regnskapet for Bergen Dyrepark AS er manipulert for å skjule økonomiske tap" | B17 (subject is the manipulated object), B16/B28; hedged "muligens ..." cut by B3/B9
G2B116 | HEALTH "tegn på stress" | A | B11 one clause one fact (split), B36
G2B116 | HEALTH "underernæring" | A | B11 one clause one fact (split)
G2B116 | POLITICAL "registrert medlem av Norges Frie Jegere" | drop | POLITICAL definition/Exclude (no stated political or ideological character; secular club untagged)
G2B117 | FINANCIAL "over 500.000 NOK i gjeld" | drop | B33 + precedence CRIMINAL > FINANCIAL (inside the CRIMINAL parenthetical; only identifiers nest)
G2B118 | BEHAVIORAL_PATTERN "domestic disputes related to his financial mismanagement" | keep | BEHAVIORAL_PATTERN Include/B18 (actor in span "his"), reporting verb "reported" cut
G2B118 | FAMILY_RELATION | B | B10 (keep possessive "His")
G2B118 | POLITICAL | B | B10 (keep possessive "His")
G2B119 | ORGANIZATION "Bjørn Olsens kjøttforretning" | drop | ORGANIZATION boundary (name as printed; this is a descriptive phrase, the name is "Slaktar Bjørn Olsen"); see open questions
G2B120 | POLITICAL | A | POLITICAL boundary (verb+name; B5 keeps punctuation inside closing quote; trailing appositive separate)

## chunk 13

G2B121 | AGE_INFO | B: "eldre dame, virker å ha vanskeligheter med å ta vare på seg selv" | AGE_INFO def (age + vulnerability as one clause, cf. "i 80-årene og klarer ikke lenger…"); B17
G2B121 | AGE_INFO | B (A's separate "vanskeligheter…" span dropped, absorbed in merged clause) | AGE_INFO def; B17
G2B121 | ECONOMIC_STATUS | A: "økonomiske problemer" | B1 (hedge/linking "kan ha" dropped)
G2B122 | HEALTH | keep | B14 (abandoned, no care; cf. "alene i lange perioder")
G2B123 | BEHAVIORAL_PATTERN | keep | B18 (owner conduct, subject kept like "Eier observert …"); marginal, no repetition marker
G2B124 | HEALTH | B: "ikke sett den løpe eller leke, bare ligge eller stå apatisk" | full clause (rule 2), B15; animal apathy is HEALTH
G2B125 | HEALTH | B: 'rykket hardt i lenken sin når den ikke "oppfører seg"' | B1 (bli = linking verb dropped), B5 (quote closed)
G2B125 | HEALTH | A: "ingen tilgang til skygge eller vann" | B14, B3/B12 (comma-introduced exception is a separate clause)
G2B125 | HEALTH | A: "klamrer seg til eieren" | B11 (bare "og" joins separate facts)
G2B125 | HEALTH | A: "stivt blikk" | B11, B1 (drops "har")
G2B126 | HEALTH | A: "litt stresset" | B3/B9 (comma cause-clause is separate; not the fact itself)
G2B127 | HEALTH | A: "apatiske" | B11, B1 example (`tynne`, `rufsete og matt`, `apatiske`)
G2B127 | HEALTH | A: "ikke ut som de får nok mat og vann" | B1 (discontinuous `ser … ut` hedge dropped), B15 (negation kept), B14
G2B127 | HEALTH | A: "sitter bare stille i et hjørne" | B11 (separate fact), Exclude note: animal stereotypy/apathy is HEALTH
G2B129 | BEHAVIORAL_PATTERN | drop | Definition/Exclusion scope: animal is grammatical subject ("Dyrene blir etterlatt")
G2B129 | BEHAVIORAL_PATTERN | drop | Exclusion: witness's own observation, no pattern of the data subject's conduct
G2B129 | HEALTH | keep: "etterlatt i bilen i timevis i både sterk sol og kulde" | B14 (exposure/shelter from weather), B1 (drops "Dyrene blir")
G2B129 | HEALTH | keep | B14, B6 (restatement is its own span)
G2B130 | HEALTH | A: "noen var tomme" | B14 (empty food/water bowls = unmet need), B11 (splits off untagged "skitne"), B17 analogue

## chunk 14

G2B131 | BEHAVIORAL_PATTERN | A | B18 (named actor: drop outer reporting wrapper "ved flere anledninger sett")
G2B131 | BEHAVIORAL_PATTERN | A | B18 (actor "eieren" inside span; "Har observert" lead-in not needed)
G2B131 | BEHAVIORAL_PATTERN | A | B18 (pronoun/noun referent, not a clean name: witnessing verb kept, cf. "hørt eieren rope")
G2B131 | HEALTH | B | B1 (body-part subject and linking verb dropped; "synlige"); B17 tension noted
G2B132 | HEALTH | A | B1 (aux "kunne" dropped), B15 (incriminating absence, negation kept)
G2B132 | ADDRESS | drop | ADDRESS Include (postal+city only inside Adresse field; in-sentence street+number "Fjellveien 22" already agreed)
G2B133 | HEALTH | A | B1 example "står tett sammen og skjelver, spesielt på morgenen" (coordinated verbs + qualifier = one span)
G2B133 | HEALTH | keep | B14 (exposure/lack of weather protection, shelter need)
G2B134 | BEHAVIORAL_PATTERN | drop | B18 (no actor in clause); fact typed HEALTH instead
G2B134 | HEALTH | third: "flere tilfeller av manglende tilsyn de siste ukene" | B14 (basic care/tilsyn), B2 (quantifier kept)
G2B134 | HEALTH | keep | B14 (basic care unmet)
G2B134 | HEALTH | ADDED | B17/B6: "Manglende tilsyn" (subject is the fact; restatement)
G2B135 | HEALTH | A | B1 (aux "har"/aspectual "begynt å" dropped; start at fact)
G2B135 | HEALTH | drop | not a condition or unmet need (eating garden waste is a hazard observation)
G2B136 | HEALTH | B | B1 (as G2B131)
G2B137 | ANIMAL_INFO | B | B2 (quantifier "noen" kept)
G2B137 | BEHAVIORAL_PATTERN | A | B18 (generic actor "eieren": witnessing verb kept, cf. "Har sett eieren bli sint")
G2B137 | HEALTH | A | B1/B2 + one clause one fact: "apatiske fiskene"
G2B137 | HEALTH | drop | B14 (water quality / overbefolkning = structure, density alone)
G2B137 | HEALTH | B | B2 (quantifier "noen" kept)
G2B137 | HEALTH | A | one clause one fact: "døde fiskene" separate span
G2B138 | HEALTH | B | B36 (evidential "tyder på" dropped) + one clause one fact: split into two spans
G2B139 | HEALTH | keep | B6 (restatement is its own span)
G2B139 | HEALTH | B | full clause: leading adverb "generelt" kept
G2B139 | HEALTH | keep | B17 (subject "Problemet med klovene" is the fact; B-extent kept whole)
G2B140 | HEALTH | A | B36 keeps "tegn på" (only evidential verbs are cut)
G2B140 | HEALTH | keep | HEALTH hedged condition (exhaustion/overwork), B1 drops "blir"

## chunk 15

G2B141 | FAMILY_RELATION | drop ("barna i huset") | FAMILY_RELATION def: no stated kinship to the data subject; unnamed children, already inside agreed BEHAVIORAL span
G2B142 | FAMILY_RELATION | A (A="barn" | B="barn som går på Steinerskolen i Bergen") | FAMILY_RELATION Boundary: school attendance is a separate fact; B1/B11 one clause one fact
G2B142 | HEALTH | A (A="apatiske" | B="apatiske og sitter mest stille i et hjørne av buret") | B11 + B1 three-span example: 'og' joins distinct facts, split
G2B142 | HEALTH | A (A="sitter mest stille i et hjørne av buret" | B="apatiske og sitter me) | B11 split distinct facts
G2B142 | HEALTH | A (A="tegn på stress" | B="apatiske og viser tegn på stress") | B11 split; B1 evidential/linking verb 'viser' dropped (B36)
G2B143 | HEALTH | A (A="tegn til stress" | B="urolige og viser tegn til stress") | B11 split; B36 drops 'viser'
G2B143 | HEALTH | A (A="urolige" | B="urolige og viser tegn til stress") | B11 split distinct facts
G2B144 | HEALTH | A (A="i dårlig forfatning" | B="pelsen deres er i dårlig forfatning") | B1 drop subject 'pelsen deres er' (consistent with agreed 'matt og flokete')
G2B144 | HEALTH | keep ("ikke sett dem leke eller vise normal katteatferd") | B15 incriminating absence (lack of normal behaviour is the symptom); HEALTH Include animal apathy
G2B145 | HEALTH | A (A="matt" | B="matt og ser ustelt ut") | B11 split distinct facts
G2B145 | HEALTH | B (A="ser ikke ut til å bli luftet regelmessig" | B="ikke ut til å bli lu) | B1 drops linking/hedge 'ser'; complement kept
G2B145 | HEALTH | A (A="ustelt" | B="matt og ser ustelt ut") | B11 split; B1 'ser … ut' complement only
G2B145 | HEALTH | keep ("forsømmelse") | B6 restatement of neglect, B36 drops 'tyder på'; parallels agreed 'omsorgssvikt'/'mangelfull omsorg'
G2B146 | ADDRESS | B (A="Gammel Gruvevei 12, Forlatt gruveområde" | B="Gammel Gruvevei 12") | ADDRESS Boundary: street+number (+postcode/city or floor/apartment); 'Forlatt gruveområde' is a descriptor
G2B146 | HEALTH | drop ("lider") | Full clause rule (rule 2) / HEALTH needs a condition; bare 'lider' names none
G2B146 | CRIMINAL | keep ("Mulig organisert virksomhet") | B25 specific address present; consistent with agreed 'Mulig kriminell aktivitet' / 'mistenker organisert virksomhet'
G2B147 | ANIMAL_INFO | B (A="ukjent antall fisk i forskjellige akvarier" | B="ukjent antall fisk) | ANIMAL_INFO Boundary: stop at place phrase
G2B147 | HEALTH | A (A="bleke i fargen" | B="finneslør og virket bleke i fargen") | B11 split; B1 drops 'virket'
G2B147 | HEALTH | B (A="døde fisker på bunnen" | B="flere døde fisker på bunnen") | B2 keeps quantifier 'flere'
G2B147 | HEALTH | A (A="finneslør" | B="finneslør og virket bleke i fargen") | B11 split distinct facts
G2B147 | HEALTH | drop ("lider") | Full clause rule (rule 2) / HEALTH needs a condition; bare 'lider' names none
G2B147 | HEALTH | A (A="oppblåst fjærdrakt" | B="oppblåst fjærdrakt og virket slapp") | B11 split; B1 drops 'virket'
G2B147 | HEALTH | A (A="oppblåste" | B="skitne fjær rundt kloakken og virket oppblåste") | B11 split; B1 drops 'virket'
G2B147 | HEALTH | A (A="skitne fjær rundt kloakken" | B="skitne fjær rundt kloakken og virk) | B11 split distinct facts
G2B147 | HEALTH | A (A="slapp" | B="oppblåst fjærdrakt og virket slapp") | B11 split; B1 drops 'virket'
G2B149 | ANIMAL_INFO | A (A="blandingsrase" | B="blandingsrase av noe slag") | ANIMAL_INFO Exclude: uncertainty commentary ('av noe slag')
G2B149 | BEHAVIORAL_PATTERN | A (A="har sett han sparke etter hunden når han trodde ingen så ham" | B=") | B18 keep witnessing lead-in when actor is only a pronoun (named-subject drop applies to cleanly named actors)
G2B149 | HEALTH | A (A="ofte tom for både vann og mat" | B="Hundeskålen er ofte tom for båd) | B1 drop subject 'Hundeskålen er'
G2B149 | HEALTH | B (A="ser ikke ut til å tilby ly for vær og vind" | B="ikke ut til å tilb) | B1 drops linking/hedge 'ser'; complement kept
G2B149 | BEHAVIORAL_PATTERN | drop ("han ble aggressiv og avvisende") | BEHAVIORAL_PATTERN def: single reaction, not recurring/characteristic
G2B149 | HEALTH | keep ("forsømmelse") | B6 restatement of neglect, B36 drops 'tyder på'; parallels agreed 'omsorgssvikt'/'mangelfull omsorg'
G2B149 | HEALTH | keep ("skrike fra bakgården ved flere anledninger") | HEALTH animal distress/pain behaviour, repeated
G2B149 | HEALTH | keep ("sårene dens ser ikke ut som vanlige skader") | HEALTH animal wounds; B17 subject is the fact

## chunk 16

G2B151 | HEALTH | A "pelsløss" | B1 (ser…ut complement only)
G2B152 | HEALTH | B | B1/B15 (negation wraps subject, keep intact; B14 water/shelter deprivation)
G2B152 | HEALTH | B (two spans: "flere mindre sår og rifter, spesielt rundt snuten og potene", "tynn") | B11 one clause one fact
G2B153 | HEALTH | A "for lite mat" | B11 split; B14 food
G2B153 | HEALTH | B (two spans "kjedelig pels", "magre") | B11 (B1 example "mager og har…" in tension)
G2B153 | HEALTH | A "mistanke om manglende stell" | B11, hedge kept (Reporting frames)
G2B154 | HEALTH | drop | B14 (rest not a listed welfare need)
G2B155 | ANIMAL_INFO | keep | ANIMAL_INFO Include (species noun)
G2B155 | HEALTH | A "lider på grunn av overbefolkning" | B14 (resulting state); "renhold" untagged
G2B155 | HEALTH | A "mangel på stimulering" | B14 (enrichment is a named need)
G2B155 | HEALTH | third: "foregår slåssing" | B1 (drop expletive "det"); animal behaviour is HEALTH
G2B157 | HEALTH | drop | B14 (tilsyn not a listed need)
G2B157 | HEALTH | A | Boundary (c); hedge "muligens på grunn av" is commentary
G2B157 | HEALTH | B "tydelig problemer med å regulere temperaturen" | HEALTH boundary (c) intensifiers kept
G2B157 | HEALTH | keep | HEALTH Include (animal heat-stress behaviour)
G2B157 | HEALTH | A "tykk ull" | B11 trailing clause is commentary
G2B157 | LOCATION | keep "Bergen sentrum" | LOCATION Include (place in prose)
G2B159 | ANIMAL_INFO | keep | ANIMAL_INFO Include (species noun)
G2B159 | HEALTH | A "lider på grunn av manglende stell" | B11 split; B14 stell; hygiene/plass untagged
G2B159 | HEALTH | A "utilstrekkelig mat og vann" | B11, B14
G2B160 | HEALTH | A "Mangel på rent vann, mat" | B14 ("rengjøring" is cleanliness, untagged)
G2B160 | HEALTH | B "sykdom og stress, som matt pels, sår og apati" | B1 drop subject "Tegnene på"; B11 itemisation absorbed
G2B160 | HEALTH | keep | B14 (clean water need)
