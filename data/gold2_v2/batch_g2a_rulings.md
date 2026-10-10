# gold2 batch g2a — adjudication rulings

Two blind Sonnet annotators per document; a third Sonnet agent ruled each dispute against docs/ANNOTATION_SPEC.md (incl. B33-B35). Inter-annotator agreement before adjudication: strict F1 0.948, relaxed 0.983.

## chunk 1

G2A001 | BEHAVIORAL_PATTERN | B ("høylytte krangler"; police callouts are a consequence, a separate fact) | B11 one clause one fact; BEHAVIORAL_PATTERN Definition
G2A002 | HEALTH | A | HEALTH Boundary (c): trailing qualifier kept; agreed precedent "Halthet hos kyr"
G2A002 | HEALTH | A | B10: possessive modifying the head noun is kept
G2A003 | CRIMINAL | A (year-only parenthetical split out; DATE_TIME 2021, 2022 already present) | B33 / B4 date-only parenthetical; B35 year list
G2A004 | CRIMINAL | B (three spans) | B3 outcome/process clauses are own spans; B1 drops "er"; B11
G2A004 | CRIMINAL | keep ("kriminell historie som involverer dyremishandling") | B6 restatement is its own span; B2 drops "en"
G2A004 | FAMILY_RELATION | B ("bror"; the sentence is CRIMINAL "soner dom for narkotikaforbrytelser") | Precedence CRIMINAL > FAMILY_RELATION, no shared characters; B2
G2A004 | FAMILY_RELATION | B ("mor"; residence is a separate fact, LOCATION) | B11 one clause one fact; FAMILY_RELATION Boundary rule
G2A005 | CRIMINAL | B (long span incl. elaborating parenthetical) | B33
G2A005 | CRIMINAL | B (same long span) | B33
G2A005 | CRIMINAL | A (legal-process verb stays inside) | CRIMINAL Definition: politianmeldelse/process verb inside span; B1 drops "Vi vil videre"
G2A005 | CRIMINAL | A ("voldsepisoder"; the date-only parenthetical "(fra 2021)" splits the ban from its cause) | B33 date-only parenthetical split under B4; B11
G2A005 | CRIMINAL | A ("våpenbesittelsesforbud"; legal sanction like besøksforbud) | B33 / B4; CRIMINAL legal-sanction vocabulary
G2A005 | FAMILY_RELATION | B ("mor"; residence/contact are separate facts) | B11; FAMILY_RELATION Boundary rule
G2A005 | POLITICAL | A (trailing "hos ansatt" ties the belief to the data subject) | Global rule 2 trailing qualifier; B27 spirit
G2A005 | USERNAME | drop (already SOCIAL_MEDIA: Facebook profile handle; one type per string) | Identifier types: @handle/profile on a platform = SOCIAL_MEDIA
G2A005 | ANIMAL_INFO | drop ("hund" is the victim animal of a conviction, not what the document is about) | ANIMAL_INFO Definition; Exclude plain mentions
G2A006 | CRIMINAL | B (both spans: "ulovlige importen", "ulovlige importen og omsetningen av kosmetikk med forbudte stoffer") | B2 drops leading determiner; B17 keeps the fact-bearing subject
G2A006 | CRIMINAL | B ("ulovlige importen") | B2
G2A006 | CRIMINAL | keep ("utsatt for utpressing fra en tidligere forretningspartner") | CRIMINAL: bare offence noun suffices, accused identified (Lars Holm); B1 drops "ble" (see open question: victim-side)
G2A006 | EMPLOYMENT | keep ("tidligere forretningspartner") | Precedence: EMPLOYMENT > FAMILY_RELATION for forretningspartner; B12 named person
G2A008 | CASE_NUMBER | A ("2018/12345") | B23 extends forward only; a preceding authority is not pulled in
G2A008 | DATE_TIME | drop ("2018") | B13: digits structurally part of a case number are not DATE_TIME
G2A010 | CRIMINAL | B ("ulovlige driften av fôringsanlegget") | B2 / B17
G2A010 | CRIMINAL | B ("tidligere voldsepisode i 2021 (sak nr. 2021-9876-5432)") | B2 drops "en", keeps "tidligere"; B33 case-number parenthetical absorbed
G2A010 | ECONOMIC_STATUS | A | Global rule 2 trailing qualifier names whose hardship; B27 spirit
G2A002 | CRIMINAL | REMOVED "uregistrert rifle i våpenskapet" | B34: unregistered weapon is CRIMINAL only when stated illegal/reported; neither here
G2A005 | CRIMINAL | REMOVED "Mulig brudd på våpenloven" | B34: "brudd på …" administrative, not framed criminally
G2A008 | ORGANIZATION | REMOVED "Restaurant \"Smak av Norge\""; third: "Smak av Norge" | B35: quotation marks stay outside ORGANIZATION
G2A009 | CRIMINAL | REMOVED short span; third: "anklager om seksuell trakassering av to tidligere ansatte (Maria Olsen, fødselsnummer: 01027043210, og Lars Jensen, fødselsnummer: 15047254321)" | B33: directly attached elaborating parenthetical stays inside CRIMINAL; PERSON and NATIONAL_ID nest

## chunk 2

G2A011 | LOCATION | keep | LOCATION: hospital named as place of the diagnosis (public institution used as a place)
G2A012 | CRIMINAL | B | CRIMINAL boundary: trailing time qualifier and destination stay in the offence clause; date also DATE_TIME (B13)
G2A012 | FINANCIAL | A | B33: elaborating case-number parenthetical stays inside; CASE_NUMBER nested
G2A012 | HEALTH | keep | B14/HEALTH: animals unfit for transport is an animal condition; B11 separate fact from parasittinfeksjoner
G2A013 | CRIMINAL | keep | B34: storage the text itself calls ulovlig (illegal), named owner
G2A016 | CRIMINAL | third: "erkjent å ha forfalsket skattedokumenter (ligningsnummer: 98765432100)" (agreed span REMOVED) | B33 parenthetical identifier absorbed; B1 keeps erkjent
G2A017 | DATE_TIME | A (2021) | B35 year list = one span per year
G2A017 | DATE_TIME | A (2022) | B35 year list = one span per year
G2A017 | DATE_TIME | A (2023) | B35 year list = one span per year
G2A017 | HEALTH | A | HEALTH overlap policy: treating professional's name is PERSON (and role EMPLOYMENT, B12), not part of the treatment fact
G2A017 | CRIMINAL | keep | Offence noun (manipulering/forfalskning of documents) suffices; same heading pattern agreed in G2A019
G2A018 | CRIMINAL | A | B1: innrømmet carries the fact and is kept
G2A018 | FINANCIAL | A | B33: parenthetical identifier elaborates the debt; TAX_ID nested
G2A019 | CRIMINAL | B | Evidentiary frame (Bevis for) sits inside the clause, cf. agreed tegn på; B11 split from the other offences
G2A019 | CRIMINAL | A | Global rule 2: leading adverbial kept; B1 drops only subject and aux
G2A019 | POLITICAL | A | POLITICAL boundary: the opinion is the fact; channel (på sosiale medier) is circumstantial
G2A020 | ANIMAL_INFO | keep | ANIMAL_INFO: count + species adds identifying detail
G2A020 | CRIMINAL | A | B1: innrømmet kept
G2A020 | CRIMINAL | drop | CRIMINAL definition: police callout with no charge or report is not a criminal fact (text says ingen anmeldelse)

## chunk 3

G2A021 | SEXUAL_ORIENTATION | drop ("seksuelle skandaler involverende ansatte": rumour of scandals, no orientation or sex-life fact about the subject; B24 is minors only) | SEXUAL_ORIENTATION Include/Exclude
G2A022 | CRIMINAL | B (admission verb `innrømmet` is a kept fact-carrying verb; contiguous) | B1
G2A022 | CRIMINAL | B (same; concealment purpose clause kept) | B1, B28
G2A022 | HEALTH | A (appositive describing the disease is part of the same fact) | Global rule 2 (full clause)
G2A022 | HEALTH | keep ("dyr med smittsom sykdom": animal condition finding, restatement) | HEALTH animal verdict, B6
G2A022 | CRIMINAL | REMOVED agreed "brudd på dyrevelferdsloven" (administrative breach, not framed criminally) | B34
G2A023 | FINANCIAL | B (drop leading determiner `et`) | B2
G2A025 | CRIMINAL | A (`tidligere` is a leading modifier kept; `er` dropped) | Global rule 2, B1, B2
G2A025 | CRIMINAL | REMOVED both extents of "uregistrert rifle ..." (storage finding; not stated illegal) | B34
G2A025 | FINANCIAL | B (comma-attached account number elaborates the DNB debt; BANK_ACCOUNT nested) | B33, Precedence (identifier nests in FINANCIAL)
G2A025 | CRIMINAL | drop ("uforsvarlige oppbevaringen av våpen": storage-rule breach) | B34
G2A025 | CRIMINAL | REMOVED agreed "uforsvarlig oppbevaring av våpen" | B34
G2A026 | BEHAVIORAL_PATTERN | keep (repeated non-cooperation with authorities by identified owner) | BEHAVIORAL_PATTERN Include, B18
G2A026 | LOCATION | drop ("Svolvær Legesenter" is the named doctor's employer, not a subject) | LOCATION Exclude (employer institution)
G2A026 | PERSON | keep ("fru Berg" honorific + surname) | B21
G2A026 | FINANCIAL | third: "gjeld på over 700 000 NOK til DNB (konto: 1234.56.78910)" (agreed span stopped before the elaborating parenthetical; BANK_ACCOUNT stays nested) | B33
G2A027 | BEHAVIORAL_PATTERN | keep (failure to act despite repeated warnings from authority) | BEHAVIORAL_PATTERN Include
G2A027 | FAMILY_RELATION | third: "omsorgen for deres to barn, Jonas (f. 01010512345) og Maria (f. 01010767890)" (enumerated children stay in one span; 11-digit after f. nested NATIONAL_ID) | B32, B35
G2A027 | FAMILY_RELATION | drop ("omsorgen for deres to barn": subsumed by the span above) | B32
G2A027 | HEALTH | drop ("diagnostisert av Dr. ... ved ... i 2020": provenance of the two agreed diagnoses, no new condition) | HEALTH boundary (a)
G2A027 | POLITICAL | keep ("fokus på politisk aktivisme") | POLITICAL Include (cf. G2A024 agreed)
G2A027 | FINANCIAL | third: "betydelig gjeld på over 500 000 NOK til flere kreditorer, inkludert DNB (lånenummer: 1234567890)" (agreed span stopped before loan-number parenthetical) | B33
G2A028 | ANIMAL_INFO | A for the Inspeksjonen omfattet occurrence ("eksotiske dyr") and B's longer extent kept at the importerer sentence (primært-itemisation is one fact) | ANIMAL_INFO Boundary, B11
G2A028 | ANIMAL_INFO | keep ("flere eksotiske dyr": count + species) | ANIMAL_INFO Include, B6
G2A028 | ANIMAL_INFO | B ("fugler" folded into itemised span) | B11
G2A028 | ANIMAL_INFO | B ("reptiler" folded into itemised span) | B11
G2A028 | CRIMINAL | B (admission verb kept) | B1
G2A028 | CRIMINAL | A (`tidligere` modifier kept) | Global rule 2, B2
G2A028 | CRIMINAL | REMOVED agreed "Mangel på nødvendige importtillatelser og CITES-dokumenter for flere eksotiske dyr" (permit finding; "importerer ... uten tillatelser" and "ulovlige importen" kept since text calls the import illegal) | B34
G2A029 | BEHAVIORAL_PATTERN | A (possessive modifying head noun kept; actor established) | B10, B18
G2A029 | CRIMINAL | drop (quarantine-guideline violation, administrative) | B34
G2A029 | CRIMINAL | drop both extents (firearm storage-rule violation) | B34
G2A029 | ECONOMIC_STATUS | keep ("gambling losses": outcome-framed, separate fact) | ECONOMIC_STATUS overlap / Resolved conflicts (spillegjeld)
G2A029 | FINANCIAL | A (cause clause is its own ECONOMIC_STATUS span, not part of the debt figure) | FINANCIAL Boundary, B11
G2A029 | CRIMINAL | REMOVED agreed "Improper storage of a registered firearm" (lawful registered weapon, storage breach) | B34, CRIMINAL Exclude
G2A030 | CRIMINAL | A (B would overlap the agreed FINANCIAL debt span; offence clause only) | Precedence CRIMINAL > FINANCIAL, B1

## chunk 4

G2A035 | CRIMINAL | A "familiens kriminelle fortid" | B1 (skjult is not a fact-carrying verb)
G2A035 | HEALTH | B "Underernærte" | B1 (subject dropped), consistent with agreed "underernærte"
G2A035 | HEALTH | B (split "synlige sår", "infeksjoner") | "one clause, one fact"; B1 drops "flere med"
G2A035 | EMPLOYMENT | keep "involvert i gårdsdriften" | EMPLOYMENT definition (named person's work situation)
G2A036 | CRIMINAL | A "dømt for bedrageri (sak nr. 12-0455/2018 Oslo Tingrett)" | B1/B33 (aux "blitt" and "tidligere" not part of fact)
G2A036 | CRIMINAL | A | B13 example keeps "involvert i en hendelse…"; B1
G2A036 | BEHAVIORAL_PATTERN | drop "Distribusjon av politisk propaganda…" | B18 (no actor in span); administrative finding, B34; already CRIMINAL "ulovlig politisk aktivitet"
G2A036 | BEHAVIORAL_PATTERN | drop "distribuerte politisk propaganda…" | B18 (actor "organisasjonen" omitted), B34
G2A037 | CRIMINAL | A "dømt for vold mot offentlig tjenestemann i 2018" | B1 (aux "vært" mid-clause), B13
G2A037 | HEALTH | B "Døde og syke dyr" | B17 subject is the fact; place phrase excluded (cf. ANIMAL_INFO owner/place rule)
G2A037 | HEALTH | drop "salmonellautbrudd" | HEALTH Definition (condition of a person/animal); outbreak is premises/documentation topic, covered by agreed CRIMINAL
G2A038 | CRIMINAL | drop "innrømmet importen av disse produktene…" | B34 (regulatory breach, not framed as illegal/criminal)
G2A038 | POLITICAL | keep "propaganda knyttet til det høyreekstreme partiet "Norges Fremtid"" | POLITICAL Include (activity for named party); B17
G2A039 | CRIMINAL | A "involvert i en episode med uforsvarlig våpenbruk i 2019 (politisak nr. 19/87654)" | B33 (police case ref absorbed), B13 example keeps "involvert i"
G2A039 | SEXUAL_ORIENTATION | keep "gift med Bjørg Hansen" | B31 (female subject, female partner)
G2A039 | MARITAL_STATUS | drop "gift med Bjørg Hansen" | B31 / precedence SEXUAL_ORIENTATION > MARITAL_STATUS
G2A040 | FINANCIAL | third: "loss of 200,000 NOK" + "her actual profit exceeded 150,000 NOK" | B11 split two facts; B17/B10 keep fact-bearing subject "her actual profit"
G2A040 | HEALTH | drop "receiving treatment" | HEALTH Include (named condition/treatment); generic, adds no fact beyond tagged conditions
G2A040 | ORGANIZATION | B "Jungeldyr" | B35 quotes outside ORGANIZATION
G2A040 | HEALTH | keep "improper temperature regulation" | B14 (protection from weather/shelter need unmet)
G2A040 | ORGANIZATION | REMOVED agreed 'Dyrebutikken "Jungeldyr"' (replaced by "Jungeldyr") | B35
