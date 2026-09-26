# Batch L Recall Sweep Log

Starting spans: 400. Added: 24. Removed: 0. Final: 424.

## Group 1 — B20 (GOV_ID issuer test, new rule)
- L002: add GOV_ID `HG12345` — `våpenkortnummer: HG12345` (firearms card, state-issued).
- L007: add GOV_ID `W0987654` — `våpenkortnummer W0987654` (firearms card, state-issued).
- Confirmed correctly left untagged under B20 (no change): L007 `journalnummer H1234567` (hospital), L016 `lånenummer: 1234567890` (bank) and `våpennummer: ABC1234` (manufacturer's serial).

## Group 2 — GOV_ID nesting gap (case/docket numbers inside a CRIMINAL_RECORD clause not separately tagged)
- L002: add GOV_ID `2019/456-ST` — nested inside `dømt for ordensforstyrrelse i forbindelse med en politisk demonstrasjon (sak nr. 2019/456-ST)`.
- L006: add GOV_ID `2021-12345, Bergen tingrett` and `2023-54321, Skatteetaten` — nested inside two CRIMINAL_RECORD clauses that were tagged whole but never got the nested GOV_ID (other docs, e.g. L004/L007/L008/L011/L016, did this nesting correctly, confirming it was an oversight here, not a stylistic choice).
- L015: add DATE_TIME `2018` — B13 nested date inside `dømt for skattesvindel (2018)`, missed even though the analogous `2018` in `dømt for fyllekjøring i 2018` (L003) etc. was caught elsewhere.

## Group 3 — BEHAVIORAL_PATTERN under-tagging (batch direction 1)
This batch had 1 span pre-sweep; sibling batches had 8–12. Swept every document for owner-conduct (aggression, neglect, intoxication, non-cooperation, deceptive conduct, ignored warnings), keeping the subject per B18.
- L002: add 2 spans — `Lars Magnus Olsen ... har gjentatte ganger unnlatt å levere nødvendig helsedokumentasjon til Mattilsynet` (non-cooperation) and its B6 restatement `Manglende helsedokumentasjon for Lars Magnus Olsen (...) for tredje gang på under ett år`.
- L003: add 1 span — `Torbjørn Askeladd, innrømmet å ha unnlatt nødvendige tiltak for å begrense spredningen av sykdommen, til tross for å være kjent med risikoen` (neglect, admitted).
- L008: add 1 span — `Astrid Berg, innehaver og daglig leder, innrømmet å ha omgått karantenereglene for å spare tid og penger` (deceptive/non-compliant conduct).
- L011: add 2 spans — the ongoing non-compliant import practice, and `Halvorsen har gjentatte ganger blitt varslet om regelverket, både skriftlig og muntlig, men har unnlatt å rette seg etter dette` (repeated ignored warnings — matches the direction's example category verbatim).
- L015: add 2 spans — `Bjørklund har innrømmet å bevisst ha omgått karantenereglene` and its B6 restatement `Bjørklund har unnlatt å rapportere mistanke om smitte, til tross for synlige tegn på sykdommen`.
- Considered and rejected: anonymous/impersonal "Vi har observert" bullet items with no named actor in-clause (L003, L008) — BEHAVIORAL_PATTERN's own definition (and B18) requires the clause to show who; left these to manual review rather than force a tag, consistent with the spec's own "ambiguous — flag, don't auto-tag" guidance.

## Group 4 — HEALTH_INFO (B14 welfare-deprivation sweep, animal behavioural condition)
- L012: add `sky og aggressive` (foxes) — animal behavioural condition; the same document already tags `sløve` (lethargic) as HEALTH_INFO for raccoons, confirming behavioural descriptors are in scope here.
- L012: add `uten tilgang til frisk mat og vann` (birds) — direct B14 food+water deprivation, phrased as an enclosure property, missed while sibling sentences in the same document were caught.
- L013: add `aldri sett den leke eller vise noen form for glede` — stimulation/enrichment deprivation; boundary (drop `Jeg har`, keep `aldri sett...`) matches the established pattern used elsewhere in the same document and in L009.
- L017: add `admitted to occasionally experiencing hypoglycemic episodes while preparing food, a potential health risk` — a distinct medical fact joined by "and" to an already-tagged diagnosis (B11 split), missed entirely.

## Group 5 — Other genuine misses (CRIMINAL_RECORD / FAMILY_RELATION / FINANCIAL_INFO)
- L004: add `involvert i en våpenhendelse i 2005` (CRIMINAL_RECORD) — the only reference to this incident; defaults to CRIMINAL_RECORD per the spec's own "kriminelle miljøer" precedent for a sole, non-specific criminal reference. Flagged as a closer judgment call than the others.
- L004: add `kan være del av en større økonomisk svindel` (CRIMINAL_RECORD) — B6 restatement of the fraud suspicion in the "Mattilsynet vurderer det slik" block, worded differently from the earlier instance.
- L016: add `sin eks-partner, Astrid Olsen` (FAMILY_RELATION) — `eks-partner` is an explicit named-relation term in the spec's own resolved-conflicts list; PERSON was already tagged but the relation type itself was missing entirely.
- L016: add `forsøkt å skjule inntekter fra salg av kjøtt direkte til forbrukere, noe som kan ha skattemessige konsekvenser` (CRIMINAL_RECORD) — the original statement of the tax-evasion suspicion; only its later restatement (`mistanken om skatteunndragelse`) had been tagged.
- L017: add `Ms. Sørensen's son, Bjørn Sørensen` (FAMILY_RELATION) — kinship relation to a named, separately-PERSON-tagged individual, entirely missed.
- L018: add `Systematisk manipulering av økonomiske data, inkludert forfalskning av skattemeldinger` and `Manglende samsvar mellom oppgitte inntekter og faktiske inntekter` (CRIMINAL_RECORD), and `Betydelig gjeld på over 550 000 NOK som ikke er deklaret i offisielle regnskap` (FINANCIAL_INFO) — B6 restatements in the "Vi har observert" bullet list, worded distinctly from the earlier narrative-paragraph versions, in a single-subject document.

## Documents swept with no changes
L001, L005, L009, L010, L013 (aside from the one HEALTH_INFO add), L014 — reviewed in full against every checklist item (address/postal/phone/email, GOV_ID fields, dates incl. nested, B14 welfare needs, B3/B6 criminal restatements, BEHAVIORAL_PATTERN, family/political/sexual-orientation/financial facts) with no defensible misses found.

## Removed
None. No clear spec violations were found warranting removal.
