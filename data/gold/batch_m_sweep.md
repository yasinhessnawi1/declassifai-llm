# Batch M recall sweep — annotator1 -> gold

18 docs, 473 spans -> 486 spans. 13 added, 0 removed. Full B20 audit performed; no removals were required (annotator1 had already applied the issuer test correctly for `journalnummer`, `medlemsnummer`, `lånenummer`).

## Group 1 — Contested/alleged claims withheld by annotator1 (B15-misapplication fix; GDPR Art. 9 processing-of-claim principle from SEXUAL_ORIENTATION section, extended to CRIMINAL_RECORD)

- **M017** `CRIMINAL_RECORD: "uregistrert rifle"` — from "...som angivelig involverte en uregistrert rifle. Bergquist hevder at riflen tilhører Hansen." The allegation (unregistered rifle tied to a conflict) is tagged; the hedge "angivelig" and Bergquist's denial sentence are correctly left untagged (denial is not a separate fact).
- **M001** `CRIMINAL_RECORD: "mishandles når ingen ser det"` — from "Jeg er redd for at hundene mishandles når ingen ser det..." Parallels the spec's own worked example ("mistenker at hundene brukes i ulovlige kampaktiviteter") — suspicion of animal mistreatment, reporting frame cut, referent subject dropped.
- **M013** `CRIMINAL_RECORD: "tyder på mishandling"` — from "Jeg har også hørt rop og lyder som tyder på mishandling." Same hedge-stays-inside logic as `mistanke om`.
- **M003, M004, M010, M011** — checked for the same pattern; in each, the underlying allegation (seksuell trakassering, skatteunndragelse, forfalskning) was **already** tagged by annotator1, and the subsequent denial/minimization sentence (`hevder ... fabrikert`, `hevder ... engangshendelse`, `Han har benektet alle anklagene`) was correctly left untagged. No change needed — annotator1 got these right.

## Group 2 — B20 GOV_ID re-routing

No reassignments were needed. All private-issuer identifiers in the batch (`journalnummer 1234567890` hospital record in M010, `medlemsnummer 9876`/`medlemsnummer` shooting-club refs in M010, `lånenummer 9988776655` bank loan ref in M010) were already left out of GOV_ID by annotator1. `lånenummer 9988776655` was checked against the "untag entirely?" question raised for this batch: FINANCIAL_INFO's own definition explicitly enumerates "an account/loan/case number" as a concrete financial fact (spreadsheet-cell test: "loan_number: X"), so FINANCIAL_INFO is the correct home, not untagged — no change made. All `Vår ref:`/`Deres ref:`/case-number GOV_ID tags (government-issued case/reference numbers) were already correct.

## Group 3 — ECONOMIC_STATUS restatement misses (B6: distinct wording = distinct span)

A recurring pattern: a bare, unquantified hardship/irregularity phrase ("økonomiske problemer", "økonomiske vanskeligheter") stated once, immediately before an itemized list of concrete facts (FINANCIAL_INFO amounts, CRIMINAL_RECORD offenses) that absorbed the annotator's attention. Since ECONOMIC_STATUS is the lowest-precedence type and the concrete items already have their own tags, the generic lead-in was left completely untagged in 7 documents:
- M003: `"bekymringsverdige opplysninger om eierens økonomiske situasjon"`
- M008: `"økonomiske problemer"`
- M009: `"økonomiske problemer"`
- M010: `"økonomiske vanskeligheter"`
- M011: `"betydelige økonomiske uregelmessigheter"`
- M016: `"Hans personlige økonomiske problemer"`
- M017: `"økonomiske problemer"`

## Group 4 — Other genuine misses

- **M002** `HEALTH_INFO: "har et elektrisk halsbånd på seg hele tiden, selv innendørs"` — a permanently-worn shock collar restated as a distinct welfare fact, directly parallel to the already-tagged muzzle-worn-constantly pattern in M007 (`alltid har en snutekurv på seg...`).
- **M008** `FAMILY_RELATION: "utenomekteskapelig forhold"` — "Det har versert rykter om et utenomekteskapelig forhold, men dette ble ikke bekreftet under inspeksjonen." Per spec, extramarital-affair language defaults to FAMILY_RELATION; the rumour is tagged, the "ikke bekreftet" non-confirmation is not (same allegation-stays-denial-doesn't principle as Group 1).

## Checked, no change (boundary calls left alone per instructions)

M004, M005, M006, M007, M009 (weapon/case-number nesting), M012, M014, M015, M018 were read in full against B1–B20; existing spans (including several already-correct restatements, B3 outcome splits, B16 organisational-principal tags, and B19 employer-field tags) were left untouched. `Referanse:` fields remained untagged throughout, matching B20.
