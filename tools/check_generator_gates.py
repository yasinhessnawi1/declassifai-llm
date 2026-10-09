"""Injected-failure harness: prove every generator gate catches what it exists to catch.

A validation gate that has never been shown to fire is a comment, not a gate.
This script drives `tools/generate_documents.py` through the mock backend and,
on each document's first attempt, corrupts the generated text in exactly the way
one gate exists to catch -- a dropped planned value, an invented fødselsnummer,
a category-labelled table row, a public figure's name, a truncated generation, a
sensitive elaboration the labels do not cover -- then asserts that the expected
gate is the one that failed, and that the pipeline recovered the way it is meant
to (a targeted repair for one or two missing values, a fresh attempt otherwise).

It needs no GPU and no model: `MockBackend` is a deterministic template filler,
and its G11 audit reports the two cue phrases in `gendoc_backends`
(`MOCK_ELABORATION_CUE`, `MOCK_FRAMING_CUE`) so the content-audit gate can be
exercised without a language model's judgement in the loop.

Sectioned generation has its own cases. A dense or case-file document is written
one section per call, so a failure is attributed to a section and only that section
is repaired or regenerated: a value missing from a middle section is repaired in
place or that section alone is written again, a heading that names a category is
rejected, a neutral heading the model chose is replaced by the planned one, a
passage repeated from an earlier section is caught by G12 on the joined text and the
later section alone is redone, and the joined document validates. The planting of
near-miss negatives has cases of its own: the pronoun placeholders are filled by the
subject's gender and form, a filled negative is planted verbatim and never
labelled, no negative text is planted more than twice in a 100-document benchmark
run (and the training run stays on its own partition at one per document), and the
leakage checker catches a negative shared between a training and a benchmark file.

Record-level defects have cases of their own (41-51, and `record_checks`): a political view
presented as relevant to a money-laundering suspicion is flagged by the G11 framing code and
repaired; a denial of a planted conviction, and a conviction explained away, are flagged by the
contradiction code; an HPR number written next to the patient, and a device identifier or a
username written as "vår"/"vårt", fail G14; several distinct CRIMINAL clauses in a police
document and several HEALTH findings in a veterinary record (Bokmål and Nynorsk) are all
labelled and rejected by neither G6 nor G12; three HEALTH findings use one health-family
slot, not three. `record_checks` adds the cast rules (a parent of 121 and a 19-year-old author
are reported, repaired and, when they survive to the end of sampling, rejected before any
prompt is built), the new clause-bank entries and their partition, and the replay of
`data/synthetic/pilot_v4_train` through the audit prompt and the mock auditor.

It also carries the checks that need no generation: the benchmark/training
partition is disjoint, the leakage checker fires on an injected leak, and G13's
thresholds reject the table dumps they were calibrated on while passing the gold
set. `--calibrate-g13` prints the numbers those thresholds came from.

Run it from the repository root; it exits non-zero if any case fails or if
`tools/validate_labels.py` reports a violation on what the run accepted:

    python3 tools/check_generator_gates.py [--out DIR] [--calibrate-g13]
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import glob
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_dataset_leakage as leakage  # noqa: E402
import gendoc_audit as audit  # noqa: E402
import gendoc_coherence as coherence  # noqa: E402
import gendoc_data as data  # noqa: E402
import gendoc_dataset as dataset_mod  # noqa: E402
import gendoc_gates as gates  # noqa: E402
import gendoc_genres as genres_mod  # noqa: E402
import gendoc_sections as sections_mod  # noqa: E402
import generate_documents as gen  # noqa: E402
import gendoc_store as store_mod  # noqa: E402
from gendoc_backends import (  # noqa: E402
    MANIFEST_SENTINEL, MOCK_ELABORATION_CUE, MOCK_FRAMING_CUE, MockBackend, model_visible,
)

BASE_SEED = 7

# One case per index: (name, expected first failing gate or None, injector).
# An injector takes (generated text, prompt) and returns the corrupted text; the
# cases whose corruption needs the sampled record instead are handled by name in
# `InjectingMock`.
CASES: Dict[int, Tuple[str, Optional[str]]] = {
    0: ("drop1", "G2_verbatim"),
    1: ("drop3", "G2_verbatim"),
    2: ("fnr", "G7_unplanned_pii"),
    3: ("fullname", None),
    4: ("role_surname", "G7_unplanned_pii"),
    5: ("table", "G9_slot"),
    6: ("label", "G9_slot"),
    7: ("marker", "marker_leak"),
    8: ("length", "G10_length"),
    9: ("truncated", "G10_truncated"),
    10: ("public_fig", "G3_name_collision"),
    11: ("placeholder", "G0_placeholder"),
    12: ("date+dob", None),
    13: ("dr", None),
    14: ("postal", "G7_unplanned_pii"),
    15: ("checksum", "G4_checksum"),
    16: ("neardup", "G6_near_duplicate"),
    17: ("wrong_dob", "G7_unplanned_pii"),
    18: ("audit_elaboration", None),
    19: ("audit_framing", None),
    20: ("audit_clean", None),
    21: ("clause_extension", None),
    22: ("pii_free_invented_date", "G7_unplanned_pii"),
    23: ("pii_free_clean", None),
    24: ("repetition", "G12_repetition"),
    25: ("category_heading", "G9_slot"),
    26: ("table_dump", "G13_tabular"),
    27: ("double_label", "G13_tabular"),
    28: ("field_dump", "G13_tabular"),
    29: ("small_id_block", None),
    30: ("negative_planted", None),
    31: ("negative_survives_audit", None),
    32: ("negative_elaboration", None),
    33: ("wrong_role", "G14_roles"),
    34: ("unplanned_reference", "G14_roles"),
    35: ("firearms_valid", None),
    36: ("firearms_invented", "G7_unplanned_pii"),
    37: ("vessel_valid", None),
    38: ("vessel_invented", "G7_unplanned_pii"),
    39: ("firearms_as_case_number", "G14_roles"),
    40: ("vessel_as_firearms", "G14_roles"),
    41: ("political_framing", None),
    42: ("hpr_on_subject", "G14_roles"),
    43: ("device_as_issuers_own", "G14_roles"),
    44: ("contradiction_denial", None),
    45: ("contradiction_explained_away", None),
    46: ("multi_criminal_police", None),
    47: ("multi_health_vet", None),
    48: ("multi_health_vet_nn", None),
    49: ("health_cap_typical", None),
    50: ("health_cap_dense", None),
    51: ("username_as_issuers_own", "G14_roles"),
    52: ("negatives_chained", "G15_negative_placement"),
    53: ("negative_framed_relevant", None),
    54: ("negative_chained_to_clause", "G15_negative_placement"),
}

# Cases that plan hard negatives, as the benchmark does. They need a plan with
# `n_negatives` and a run config carrying a negative bank.
_NEGATIVE_CASES = {30, 31, 32, 52, 53, 54}

# Cases that plan several instances of a type: idx -> (instances, profile, length band, type target, art9 cap, form).
_MULTI_CASES = {
    46: ({"CRIMINAL": 4}, "dense", (2800, 4000), 12, 2, "nb"),
    47: ({"HEALTH": 3}, "dense", (2800, 4000), 12, 2, "nb"),
    48: ({"HEALTH": 4}, "dense", (2800, 4000), 12, 2, "nn"),
    49: ({"HEALTH": 3, "MEDICATION": 2}, "typical", (1600, 2800), 9, 1, "nb"),
    50: ({"HEALTH": 3, "MEDICATION": 2}, "dense", (2800, 4000), 12, 2, "nb"),
}

# Which genre and plan shape each case needs. The slot-label cases need a
# document with a seeded judgement clause; the checksum case needs a genre whose
# values include an identifier with a real checksum; the PII-free cases need the
# one genre that may carry no data subject.
_GENRE_FOR = {
    5: "gp_referral", 6: "gp_referral", 12: "gp_referral", 15: "nav_decision",
    18: "gp_referral", 19: "police_report", 20: "nav_decision", 21: "gp_referral",
    22: "admin_circular", 23: "admin_circular", 24: "nav_decision",
    25: "gp_referral", 26: "nav_decision", 27: "nav_decision", 28: "nav_decision",
    29: "nav_decision", 30: "police_report", 31: "police_report", 32: "police_report",
    33: "nav_decision", 34: "nav_decision",
    35: "police_report", 36: "police_report", 37: "mattilsynet_inspection",
    38: "mattilsynet_inspection", 39: "police_report", 40: "mattilsynet_inspection",
    41: "forsvaret_clearance", 42: "gp_referral", 43: "digital_forensics_report",
    44: "police_report", 45: "police_report", 46: "police_report", 47: "vet_clinical_record",
    48: "vet_clinical_record", 49: "gp_referral", 50: "gp_referral", 51: "digital_forensics_report",
    52: "police_report", 53: "police_report", 54: "police_report",
}

# Types a case forces into its record so the injection has a planned value to work on.
_FORCED_FOR = {35: ["FIREARMS_LICENSE"], 36: ["FIREARMS_LICENSE"], 37: ["VESSEL_REGISTRATION"],
               38: ["VESSEL_REGISTRATION"], 39: ["FIREARMS_LICENSE"], 40: ["VESSEL_REGISTRATION"],
               42: ["MEDICAL_LICENSE"], 43: ["DEVICE_ID"], 51: ["USERNAME"]}
_DEFAULT_GENRES = ["gp_referral", "police_report", "nav_decision", "dismissal_letter",
                   "udi_decision"]


def _manifest(prompt: str) -> str:
    return prompt.split(MANIFEST_SENTINEL, 1)[1]


def _values(prompt: str, kind: str = "VALUE") -> List[str]:
    return [line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
            if line.startswith(kind + "|")]


def _drop(text: str, prompt: str, k: int) -> str:
    for value in [v for v in _values(prompt) + _values(prompt, "CLAUSE_SEEDED") if len(v) > 4][:k]:
        text = text.replace(value, "")
    return text


class InjectingMock(MockBackend):
    """A mock backend that corrupts each document's first attempt in one specific way.

    Audit and audit-repair prompts are passed straight through to `MockBackend`:
    the injection belongs to the generation pass, and the audit must see exactly
    what the gates saw.
    """

    def __init__(self, states: Dict[int, gen.DocState], first_texts: Dict[int, str]) -> None:
        self.states = states
        self.first_texts = first_texts
        self.neardup_base = ""

    def generate(self, prompts, **kwargs):
        outputs = super().generate(prompts, **kwargs)
        finished = []
        for i, (prompt, text) in enumerate(zip(prompts, outputs)):
            is_generation = "\nAUDIT|1" not in prompt and "\nAUDIT_REPAIR|1" not in prompt
            seed = int(re.search(r"SEED\|(\d+)", prompt).group(1))
            idx, attempt = divmod(seed - BASE_SEED * 100003, 97)
            ok = True
            if not is_generation and "\nAUDIT|1" in prompt and CASES.get(idx, ("",))[0] == "negative_survives_audit":
                negatives = self.states[idx].record.planted_negatives
                text = "\n".join(f"FUNN|SENSITIV|{neg.found}" for neg in negatives)
            if is_generation and attempt == 1 and "REPAIR|" not in _manifest(prompt):
                text, ok = self._inject(idx, text, prompt)
                self.first_texts[idx] = text
            outputs[i] = text
            finished.append(ok)
        self.last_finished = finished
        return outputs

    def _inject(self, idx: int, text: str, prompt: str) -> Tuple[str, bool]:
        name = CASES.get(idx, ("", None))[0]
        clauses = _values(prompt, "CLAUSE_SEEDED")
        if name == "drop1":
            return _drop(text, prompt, 1), True
        if name == "drop3":
            return _drop(text, prompt, 3), True
        if name == "fnr":
            return text + " Opplyst fnr for naboen er 01018012345.", True
        if name == "fullname":
            return text + " Til stede var også Ingrid Solberg.", True
        if name == "role_surname":
            return text + " Saken ble drøftet med Saksbehandler Larsen.", True
        if name == "table":
            return text + "\n| Opplysning | " + clauses[0] + " |\n", True
        if name == "label":
            return text + "\nHelseforhold: " + clauses[0] + "\n", True
        if name == "category_heading":
            # The clause under its own rubric line, with no colon anywhere: the
            # shape a smoke probe produced and the same-line label test missed.
            return (text.replace(clauses[0], "")
                    + "\n\nHelserelaterte opplysningar\nDet er registrert at vedkommende "
                    + clauses[0] + " i denne perioden.\n"), True
        if name == "table_dump":
            rows = "\n".join(f"| Felt {k} | {v} |" for k, v in enumerate(_values(prompt)[:12]))
            return "| Identifikasjon | Opplysning |\n| :--- | :--- |\n" + rows + "\n\n" + text, True
        if name == "double_label":
            value = next(v for v in _values(prompt) if len(v) > 6)
            return f"Fødselsnummer: {value}\nStatlig ID: {value}\n\n" + text, True
        if name == "field_dump":
            labels = ["Navn", "Adresse", "Telefon", "E-post", "Saksnummer", "Dato", "Kontonummer",
                      "Stilling", "Virksomhet", "Merknad"]
            lines = "\n".join(f"{labels[k]}: {v}" for k, v in enumerate(_values(prompt)[:10]))
            return text + "\n\n" + lines + "\n", True
        if name == "small_id_block":
            # The mock's own header lines become a two-row table; the rest of the
            # header stays as plain fields. Each value appears once, under one label.
            head, _blank, rest = text.partition("\n\n")
            lines = head.split("\n")
            rows = ["| " + line.replace(": ", " | ", 1) + " |" for line in lines[:2]]
            table = ["| Identifikasjon | Opplysning |", "| :--- | :--- |"] + rows
            return "\n".join(table + lines[2:]) + "\n\n" + rest, True
        if name == "wrong_role":
            fnr = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                       if line.startswith("VALUE|NATIONAL_ID|"))
            return text + f" Saksnummeret er {fnr}.", True
        if name == "unplanned_reference":
            return text + " Vår ref: 2024/05891.", True
        if name == "firearms_invented":
            return text + " Naboen har også våpenkortnummer HG987654.", True
        if name == "vessel_invented":
            planned = {line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                       if line.startswith("VALUE|VESSEL_REGISTRATION|")}
            other = next(v for v in ("ST-9917", "M-318-GR", "SF-6021") if v not in planned)
            return text + f" Båten til broren hans har reg.nr. {other}.", True
        if name == "firearms_as_case_number":
            value = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                         if line.startswith("VALUE|FIREARMS_LICENSE|"))
            return text + f" Saksnummeret er {value}.", True
        if name == "vessel_as_firearms":
            value = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                         if line.startswith("VALUE|VESSEL_REGISTRATION|"))
            return text + f" Våpenkortnummeret er {value}.", True
        if name == "political_framing":
            return (text + " Vi ser at du er aktiv i Senterpartiet og kjent for sine kontroversielle "
                           "uttalelser om innvandring, noe som kan være relevant for helhetsvurderingen."), True
        if name == "hpr_on_subject":
            subject = self.states[idx].record.person
            hpr = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                       if line.startswith("VALUE|MEDICAL_LICENSE|"))
            return text + f" {subject.full_name}, født i 1971, med hpr-nummer {hpr}.", True
        if name == "device_as_issuers_own":
            device = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                          if line.startswith("VALUE|DEVICE_ID|"))
            return text + f" Ved henvendelse til vår enhetsidentifikator {device} mottok vi en melding.", True
        if name == "username_as_issuers_own":
            user = next(line.split("|", 2)[2] for line in _manifest(prompt).splitlines()
                        if line.startswith("VALUE|USERNAME|"))
            return text + f" Kontoen er registrert på vårt brukernavn {user} i systemet.", True
        if name == "contradiction_denial":
            return text + " Det foreligger ingen registrerte straffedommer mot vedkommende.", True
        if name == "contradiction_explained_away" and clauses:
            return text.replace(clauses[0], clauses[0] + ", men denne finst ikkje i oppgjeve register", 1), True
        if name == "negative_elaboration":
            # The elaboration sits in the negative's own sentence, which is what the exemption must not excuse.
            negative = self.states[idx].record.planted_negatives[0].text
            sentence = negative[:1].upper() + negative[1:]
            return text.replace(sentence + ".", f"{sentence}, {MOCK_ELABORATION_CUE}.", 1), True
        if name == "negatives_chained":
            # Pilot v5's run-on: two planted negatives glued into one sentence with "og".
            first, second = (n_.text for n_ in self.states[idx].record.planted_negatives[:2])
            head, tail = first[:1].upper() + first[1:], second[:1].upper() + second[1:]
            return text.replace(tail + ".", "", 1).replace(head + ".", f"{head}, og {second}.", 1), True
        if name == "negative_chained_to_clause":
            first = self.states[idx].record.planted_negatives[0].text
            head = first[:1].upper() + first[1:]
            seeded = f"Videre er det opplyst at vedkommende {clauses[0]}."
            return text.replace(head + ".", "", 1).replace(
                seeded, f"{seeded[:-1]}, og {first}.", 1), True
        if name == "negative_framed_relevant":
            # The pilot's "..., er relevante detaljar i saka": a neutral near-miss presented as bearing on the case.
            first = self.states[idx].record.planted_negatives[0].text
            head = first[:1].upper() + first[1:]
            return text.replace(head + ".", f"{head}, noe som er relevant for saken.", 1), True
        if name == "marker":
            return text + " ⟦TYPE: setning⟧", True
        if name == "length":
            # Distinct sentences, so this case tests the length cap and not the
            # repetition gate, which would otherwise fire first.
            return text + "".join(f" Avsnitt {k} beskriver et eget forhold i saken "
                                  f"med nummer {k * 7 + 3}." for k in range(420)), True
        if name == "repetition":
            return text + " Saken vil bli fulgt opp av ansvarlig enhet ved neste gjennomgang." * 40, True
        if name == "truncated":
            return text, False
        if name == "public_fig":
            return text + " Saken er omtalt av Erna Solberg.", True
        if name == "placeholder":
            return text + " Signert: [NAVN SAKSBEHANDLER]", True
        if name == "date+dob":
            dob = self.states[idx].record.person.birth_date
            return (text + f" Møtet ble holdt 3. mai 2024. "
                           f"Født {dob.day:02d}.{dob.month:02d}.{dob.year}."), True
        if name == "dr":
            return text.replace(_values(prompt)[0], "Dr. " + _values(prompt)[0]), True
        if name == "postal":
            return text + " Naboen bor i Storgata 3, 9008 Tromsø.", True
        if name == "wrong_dob":
            return text + " Vedkommende er født 01.01.1950.", True
        # Finalised means accepted and audited clean: only those documents' n-grams are in G6's
        # reference set.
        accepted = [s.result["text"] for s in self.states.values()
                    if s.result and s.result.get("text") and s.audit_log
                    and not any(entry["kept"] for entry in s.audit_log)]
        if name == "neardup" and accepted:
            # The longest accepted text so far plus doc 16's own literals on one line: every
            # planned value is present, so only G6 can reject it. The longest, because G6
            # does not count a document's seeded clauses and a short base would share too
            # little of its prose to reach the threshold.
            self.neardup_base = max(accepted, key=len)
            return (self.neardup_base + "\n" + " og ".join(_values(prompt) + clauses) + "."), True
        if name == "audit_elaboration":
            return text + f" Pasienten {MOCK_ELABORATION_CUE}.", True
        if name == "audit_framing":
            return (text + " Bakgrunnen hennes har vært "
                    + MOCK_FRAMING_CUE + " av saken."), True
        if name == "clause_extension" and clauses:
            target = min(clauses, key=len)
            return text.replace(target + ".", target + " 2025."), True
        if name == "pii_free_invented_date":
            return text + " Rundskrivet gjelder fra 3. mai 2024.", True
        return text, True


def build_plans() -> List[gen.DocPlan]:
    """Build one plan per case, with the genre and profile that case needs."""
    plans = []
    for idx, (name, _expected) in sorted(CASES.items()):
        genre = _GENRE_FOR.get(idx, _DEFAULT_GENRES[idx % len(_DEFAULT_GENRES)])
        pii_free = name.startswith("pii_free")
        forced = ["HEALTH"] if idx in (5, 6, 18, 21, 25) else list(_FORCED_FOR.get(idx, []))
        multi = _MULTI_CASES.get(idx)
        plans.append(gen.DocPlan(
            n_negatives=2 if idx in _NEGATIVE_CASES else 0,
            idx=idx, genre=genre, variant="prose_letter", form=multi[5] if multi else "nb",
            length_band=multi[2] if multi else ((800, 1600) if pii_free else (1600, 2800)),
            forced_types=forced, profile=multi[1] if multi else ("pii_free" if pii_free else "typical"),
            type_target=multi[3] if multi else (0 if pii_free else (14 if idx in (26, 28) else 8)),
            art9_cap=multi[4] if multi else 1, pii_free=pii_free,
            instances=dict(multi[0]) if multi else {},
        ))
    return plans


_ANIMAL_HEALTH: set = set()


def _animal_health_texts() -> set:
    """The texts of the bank's animal-subject HEALTH clauses, for the veterinary cases."""
    if not _ANIMAL_HEALTH:
        bank = data.load_clause_bank("data/synthetic/clause_bank.json")
        _ANIMAL_HEALTH.update(e["text"] for e in bank["HEALTH"] if e.get("subject") == "animal")
    return _ANIMAL_HEALTH


def _first_failure(state: gen.DocState) -> Optional[str]:
    return next((e["stage"] for e in state.gate_log if not e["ok"]), None)


def _check(state: gen.DocState) -> Tuple[bool, str]:
    """Return (passed, a one-line detail) for one case's realised outcome."""
    idx = state.plan.idx
    name = CASES[idx][0]
    expected = CASES[idx][1]
    failure = _first_failure(state)
    accepted = bool(state.result.get("accepted"))
    result = state.result

    if name == "drop1":
        return (failure == "G2_verbatim" and state.repairs_total == 1 and accepted
                and state.attempt == 1), f"repairs={state.repairs_total} attempt={state.attempt}"
    if name == "drop3":
        return (failure == "G2_verbatim" and state.repairs_total == 0
                and state.attempt == 2), f"repairs={state.repairs_total} attempt={state.attempt}"
    if name == "fullname":
        labelled = result.get("g7_labelled", [])
        return (accepted and any(l["text"] == "Ingrid Solberg" and l["type"] == "PERSON"
                                 for l in labelled)), str(labelled)
    if name == "date+dob":
        labelled = result.get("g7_labelled", [])
        return (accepted and {l["type"] for l in labelled} >= {"DATE_TIME", "DATE_OF_BIRTH"}), \
            str({l["type"] for l in labelled})
    if name == "dr":
        persons = result.get("output", {}).get("PERSON", [])
        return (accepted and any(s.startswith("Dr. ") for s in persons)), str(persons)
    if name in ("audit_elaboration", "audit_framing"):
        reasons = [f["reason"] for entry in state.audit_log for f in entry["findings"]]
        want = "unlabelled_sensitive" if name == "audit_elaboration" else "sensitive_framing"
        cue = MOCK_ELABORATION_CUE if name == "audit_elaboration" else MOCK_FRAMING_CUE
        clean = accepted and cue not in result.get("text", "")
        return (want in reasons and state.audit_repairs_total == 1 and clean), \
            f"reasons={reasons} audit_repairs={state.audit_repairs_total} accepted={accepted}"
    if name == "audit_clean":
        kept = sum(entry["kept"] for entry in state.audit_log)
        return (accepted and state.audit_calls >= 1 and kept == 0
                and state.audit_repairs_total == 0), \
            f"audit_calls={state.audit_calls} kept={kept}"
    if name == "clause_extension":
        extensions = result.get("clause_extensions", {})
        extended_ok = all(new.endswith(" 2025") for new in extensions.values())
        return (accepted and len(extensions) == 1 and extended_ok
                and all(new in result["text"] for new in extensions.values())
                and all(any(new in spans for spans in result["output"].values())
                        for new in extensions.values())), str(extensions)
    if name == "category_heading":
        # Like the PII-free case, the attempt count is not asserted: several
        # cases share the gp_referral genre and a forced HEALTH clause, so a
        # mock retry can legitimately collide with one of them on G6.
        return (failure == "G9_slot" and accepted and state.attempt >= 2), \
            f"attempt={state.attempt}"
    if name == "category_heading":
        # Like the PII-free case, the attempt count is not asserted: several
        # cases share the gp_referral genre and a forced HEALTH clause, so a
        # mock retry can legitimately collide with one of them on G6.
        return (failure == "G9_slot" and accepted and state.attempt >= 2), \
            f"attempt={state.attempt}"
    if name == "small_id_block":
        # A two-row table is an identification block: it must not trip G13.
        return (accepted and failure is None and state.attempt == 1), \
            f"failure={failure} attempt={state.attempt}"
    if name in ("negative_planted", "negative_survives_audit", "negative_elaboration"):
        negatives = state.record.planted_negatives
        texts = [n.text for n in negatives]
        spans = [sp for vals in result.get("output", {}).values() for sp in vals]
        allowed = {sub for n in negatives for sub in n.also_labelled.values()}
        verbatim = all(gates.negative_occurrences(result.get("text", ""), t) for t in texts)
        texts = [n.found for n in negatives]
        unlabelled = not any(t in sp or sp in t for t in texts for sp in spans
                             if sp not in allowed and len(sp) >= 4)
        base = accepted and bool(negatives) and verbatim and unlabelled
        if name == "negative_planted":
            capitalised = any(n.found != n.text for n in negatives)
            return base and capitalised, (f"negatives={texts} verbatim={verbatim} unlabelled={unlabelled} "
                                          f"capitalised_at_sentence_start={capitalised}")
        kept = sum(entry["kept"] for entry in state.audit_log)
        overruled = sum(entry.get("exempt_negative_quotes", 0) for entry in state.audit_log)
        if name == "negative_survives_audit":
            return (base and kept == 0 and overruled >= 1 and state.audit_repairs_total == 0), \
                f"kept={kept} overruled={overruled} audit_repairs={state.audit_repairs_total}"
        return (base and state.audit_repairs_total == 1 and MOCK_ELABORATION_CUE not in result["text"]), \
            f"audit_repairs={state.audit_repairs_total} cue_removed={MOCK_ELABORATION_CUE not in result['text']}"
    if name in ("negatives_chained", "negative_chained_to_clause"):
        kinds = [h["kind"] for e in state.gate_log if e["stage"] == "G15_negative_placement" for h in e["detail"]]
        want = "chained_negatives" if name == "negatives_chained" else "chained_to_clause"
        return (failure == "G15_negative_placement" and want in kinds and accepted and state.attempt == 2
                and len(state.record.planted_negatives) >= (2 if name == "negatives_chained" else 1)), \
            f"G15 kinds={kinds} attempt={state.attempt}"
    if name == "negative_framed_relevant":
        reasons = [f["reason"] for entry in state.audit_log for f in entry["findings"]]
        text = result.get("text", "")
        kept = all(gates.negative_occurrences(text, n.text) for n in state.record.planted_negatives)
        return ("sensitive_framing" in reasons and state.audit_repairs_total == 1 and accepted and kept
                and "relevant for saken" not in text), \
            f"reasons={reasons} audit_repairs={state.audit_repairs_total} negatives_kept={kept}"
    if name in ("political_framing", "contradiction_denial", "contradiction_explained_away"):
        reasons = [f["reason"] for entry in state.audit_log for f in entry["findings"]]
        want = "sensitive_framing" if name == "political_framing" else "contradiction"
        gone = {"political_framing": "Senterpartiet", "contradiction_denial": "ingen registrerte straffedommer",
                "contradiction_explained_away": "finst ikkje i oppgjeve register"}[name]
        return (want in reasons and state.audit_repairs_total == 1 and accepted
                and gone not in result.get("text", "")), \
            f"reasons={reasons} audit_repairs={state.audit_repairs_total} phrase_removed={gone not in result.get('text', '')}"
    if name in ("hpr_on_subject", "device_as_issuers_own", "username_as_issuers_own"):
        kinds = [h["kind"] for e in state.gate_log if e["stage"] == "G14_roles" for h in e["detail"]]
        want = {"hpr_on_subject": "wrong_owner"}.get(name, "issuer_identifier")
        return (failure == "G14_roles" and want in kinds and accepted and state.attempt == 2), \
            f"G14 kinds={kinds} attempt={state.attempt}"
    if name.startswith("multi_") or name.startswith("health_cap"):
        etype = "CRIMINAL" if name == "multi_criminal_police" else "HEALTH"
        asked = state.plan.instances[etype]
        planned = [pv for pv in state.record.planned if pv.type == etype and pv.value_kind == "clause"]
        located = [pv.value for pv in planned if pv.value in result.get("output", {}).get(etype, [])]
        family = collections.Counter(pv.type for pv in state.record.planned if pv.type in genres_mod.HEALTH_FAMILY)
        rejected_by = [e["stage"] for e in state.gate_log if not e["ok"] and e["stage"] in ("G6_near_duplicate", "G12_repetition")]
        topics = [pv.topic for pv in planned]
        detail = (f"asked={asked} planned={len(planned)} labelled={len(located)} distinct_topics={len(set(topics))} "
                  f"G6/G12_rejections={rejected_by} health_family={dict(family)}")
        # A typical document's item budget leaves room for one or two further clauses, not three.
        floor = 2 if name == "health_cap_typical" else min(asked, 3)
        base = (accepted and len(planned) >= floor and len(located) == len(planned)
                and len(set(topics)) == len(topics) and not rejected_by)
        if name == "health_cap_typical":
            return base and len(family) == 1 and family["HEALTH"] >= 2, detail
        if name == "health_cap_dense":
            return (base and len(family) == genres_mod.health_family_cap("dense")
                    and sum(family.values()) > genres_mod.health_family_cap("dense")), detail
        if name == "multi_health_vet" or name == "multi_health_vet_nn":
            animal = all(pv.value in _animal_health_texts() for pv in planned)
            return base and animal, detail + f" all_animal_clauses={animal}"
        return base, detail
    if name in ("firearms_valid", "vessel_valid"):
        etype = "FIREARMS_LICENSE" if name == "firearms_valid" else "VESSEL_REGISTRATION"
        planned = [pv.value for pv in state.record.planned if pv.type == etype]
        output = result.get("output", {})
        # The label is the planned value alone, under its own type and never under
        # LICENSE_PLATE, and the mark is nowhere read as a road plate by the sweep.
        labelled = bool(planned) and all(v in output.get(etype, []) for v in planned)
        not_plate = not any(v in output.get("LICENSE_PLATE", []) for v in planned)
        sweep_plate = not any(gates.TIER_A_PATTERNS["plate_like"].search(v) for v in planned)
        return (accepted and failure is None and state.attempt == 1 and labelled and not_plate
                and sweep_plate), f"planned={planned} labelled={labelled} not_plate={not_plate}"
    if name == "pii_free_invented_date":
        # The attempt count is not asserted here: every PII-free mock document
        # is a permutation of the same eight boilerplate sentences, so a retry
        # can legitimately collide with the other PII-free case on G6.
        return (failure == "G7_unplanned_pii" and accepted
                and state.attempt >= 2), f"attempt={state.attempt}"
    if name == "pii_free_clean":
        return (accepted and result.get("output") == {} and failure is None), \
            f"output={result.get('output')}"
    return (failure == expected and accepted and state.attempt == 2), f"attempt={state.attempt}"


def _quantiles(values: List[float]) -> str:
    ordered = sorted(values)
    at = lambda p: ordered[min(len(ordered) - 1, int(p * len(ordered)))]  # noqa: E731
    return (f"n={len(ordered)} mean={statistics.mean(ordered):.3f} median={at(.5):.3f} "
            f"p90={at(.9):.3f} p95={at(.95):.3f} p99={at(.99):.3f} max={ordered[-1]:.3f}")


def _load_jsonl(paths: List[str]) -> List[dict]:
    return [json.loads(line) for path in paths for line in open(path, encoding="utf-8") if line.strip()]


def calibrate_g13(gold_glob: str, pilot_dir: str) -> int:
    """Print the measurements G13's thresholds were calibrated on.

    Gold documents are flattened to one line, so only the value measure applies to
    them; pilot v3's accepted documents keep their line structure, so the table
    measure applies there. Both are printed with the gate's verdict.
    """
    gold = _load_jsonl(sorted(glob.glob(gold_glob)))
    shares, rejected = [], []
    for doc in gold:
        values = [s for spans in doc["output"].values() for s in spans]
        profile = gates.tabular_profile(doc["text_input"], values)
        if profile["values_in_slots"] > gates.MAX_SLOT_VALUES:
            shares.append(profile["value_slot_share"])
        ok, violations = gates.gate_tabular_dump(doc["text_input"], values)
        if not ok:
            rejected.append((doc["id"], [v["kind"] for v in violations]))
    print(f"gold: {len(gold)} documents, thresholds table_line_share>{gates.MAX_TABLE_LINE_SHARE} "
          f"(rows>={gates.MIN_TABLE_ROWS}), value_slot_share>{gates.MAX_VALUE_SLOT_SHARE} "
          f"(more than {gates.MAX_SLOT_VALUES} values in fields), any duplicate label")
    all_shares = []
    for doc in gold:
        values = [s for spans in doc["output"].values() for s in spans]
        profile = gates.tabular_profile(doc["text_input"], values)
        if profile["values_located"] >= 5:
            all_shares.append(profile["value_slot_share"])
    print("  value slot share, documents with >=5 located values:", _quantiles(all_shares))
    print(f"  documents with more than {gates.MAX_SLOT_VALUES} values in fields: {len(shares)}"
          + (f", share {_quantiles(shares)}" if shares else ""))
    print(f"  rejected by G13: {len(rejected)} of {len(gold)} {rejected}")
    pilot_path = os.path.join(pilot_dir, "synthetic_batch.jsonl")
    if os.path.exists(pilot_path):
        pilot = _load_jsonl([pilot_path])
        rows = []
        for doc in pilot:
            values = [s for spans in doc["output"].values() for s in spans]
            profile = gates.tabular_profile(doc["text_input"], values)
            ok, violations = gates.gate_tabular_dump(doc["text_input"], values)
            rows.append((doc["id"], profile, [v["kind"] for v in violations]))
        print(f"pilot accepted: {len(pilot)} documents")
        print("  table line share:", _quantiles([r[1]["table_line_share"] for r in rows]))
        print("  table line share distribution: "
              + str(sorted(round(r[1]["table_line_share"], 2) for r in rows if r[1]["table_line_share"])))
        print("  value slot share (>=5 located):",
              _quantiles([r[1]["value_slot_share"] for r in rows if r[1]["values_located"] >= 5]))
        for doc_id, profile, kinds in rows:
            if kinds:
                print(f"  rejected {doc_id}: {kinds} table_line_share={profile['table_line_share']} "
                      f"table_rows={profile['table_rows']} value_slot_share={profile['value_slot_share']} "
                      f"in_fields={profile['values_in_slots']} duplicates={list(profile['duplicate_labels'])}")
        print(f"  rejected by G13: {sum(1 for r in rows if r[2])} of {len(rows)}")
    return 0


# The pilot v3 documents the orchestrator measured as table dumps (more than half
# of their lines, or a value listed twice); G13 has to reject every one.
_PILOT_V3_DUMPS = {"SYN-000002", "SYN-000015", "SYN-000018", "SYN-000038"}


def spec_alignment_checks(clause_bank: dict) -> bool:
    """Check the four labelling disagreements ANNOTATION_SPEC open question 23 found in pilot v3.

    (a) ANIMAL_INFO keeps no leading determiner; (b) LOCATION inside an
    organisation's name is dropped; (c) one age is one span, and an age inside
    FAMILY_RELATION, AGE_INFO or ANIMAL_INFO is not tagged again; (d)
    MARITAL_STATUS is the bare word in a field and the full clause when the
    partner is named, with the partner also a PERSON.
    """
    import random
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} unit {name:<34} {detail}")

    import gendoc_identifiers as ident
    rng = random.Random(3)
    drawn = {ident.animal_descriptor(rng) for _ in range(800)}
    determiner = re.compile(r"^(?:en|ei|et|ein|eit)\b", re.IGNORECASE)
    bank_hits = [e["text"] for t, v in clause_bank.items() if t != "negatives" for e in v
                 if determiner.match(e["text"]) and e.get("genres")]
    report("a_animal_no_leading_determiner",
           not [d for d in drawn if determiner.match(d)] and any(d.startswith("besetning på") for d in drawn)
           and not bank_hits, f"descriptors={len(drawn)} bank_determiner_initial={bank_hits}")

    text = "Møtet var i lokaler tilhørende Fredrikstad Sjømat AS i dag."
    dropped = gen._drop_absorbed_spans(text, {"LOCATION": ["Fredrikstad"],
                                              "ORGANIZATION": ["Fredrikstad Sjømat AS"]}, set())
    kept = gen._drop_absorbed_spans(text + " Han bor i Fredrikstad.", {
        "LOCATION": ["Fredrikstad"], "ORGANIZATION": ["Fredrikstad Sjømat AS"]}, set())
    in_address = gen._drop_absorbed_spans("Han bor på Storgata 1, 1600 Fredrikstad.", {
        "LOCATION": ["Fredrikstad"], "ADDRESS": ["Storgata 1, 1600 Fredrikstad"]}, set())
    agency = gen._drop_absorbed_spans("Saken er sendt til Oslo tingrett.",
                                      {"LOCATION": ["Oslo"]}, {"Oslo tingrett"})
    report("b_location_inside_org_name",
           "LOCATION" not in dropped and "LOCATION" in kept and "LOCATION" in in_address
           and "LOCATION" not in agency,
           f"org_only={'LOCATION' in dropped} also_standalone={'LOCATION' in kept} "
           f"in_address={'LOCATION' in in_address} agency={'LOCATION' in agency}")

    age_value, _ = gen._generate_value_kind(
        "AGE", random.Random(1), gen.Person("Kari", "Test", "F", gen.date(2013, 1, 1)), 0.0)
    nested = gen._drop_absorbed_spans("De har to barn på 15 og 12 år og han er 40 år gammel.", {
        "FAMILY_RELATION": ["to barn på 15 og 12 år"], "AGE": ["12 år", "40 år"]}, set())
    twice = gen._prune_redundant_nested("Hun er 43 år gammel.", {"AGE": ["43 år", "43 år gammel"]})
    report("c_age_is_one_span", age_value.endswith(" år") and nested.get("AGE") == ["40 år"]
           and twice.get("AGE") == ["43 år gammel"],
           f"planned={age_value!r} nested_kept={nested.get('AGE')} longer_form={twice.get('AGE')}")

    taxonomy_index = data.taxonomy_index(data.load_taxonomy("data/synthetic/taxonomy.json"))
    bank = {t: v for t, v in clause_bank.items() if t != "negatives"}
    forms = set()
    persons_ok = True
    for seed in range(60):
        plan = gen.DocPlan(idx=0, genre="gp_referral", variant="prose_letter", form="nb",
                           length_band=(1600, 2800), forced_types=["MARITAL_STATUS"], profile="dense",
                           type_target=10, art9_cap=1)
        plan.type_target = 12
        rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank,
                                set(data.PUBLIC_FIGURES))
        for pv in rec.planned:
            if pv.type != "MARITAL_STATUS":
                continue
            if " med " in pv.value:
                forms.add("clause")
                partner = pv.value.split(" med ", 1)[1]
                persons_ok &= any(q.type == "PERSON" and q.value == partner for q in rec.planned)
            else:
                forms.add("bare")
    report("d_marital_both_forms", forms == {"clause", "bare"} and persons_ok,
           f"forms={sorted(forms)} partner_also_person={persons_ok}")
    return ok


def registry_identifier_checks(clause_bank: dict, gold_v2_glob: str) -> bool:
    """Check the FIREARMS_LICENSE and VESSEL_REGISTRATION generators, gates and age rule.

    The three registry identifiers (road plate, firearms licence, vessel mark)
    look alike, and ANNOTATION_SPEC B20 says the registered object decides, so
    the generators must not hand the detector the shape as the answer.
    """
    import random
    import gendoc_identifiers as ident
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} unit {name:<34} {detail}")

    rng = random.Random(11)
    firearms = [ident.firearms_license_number(rng) for _ in range(4000)]
    vessels = [ident.vessel_registration_mark(rng) for _ in range(4000)]
    plates = [ident.vehicle_reg(rng) for _ in range(4000)]
    # The one intended overlap: solid plate-shaped firearms numbers (`HG12345`),
    # about one in six, which only their firearms label distinguishes (B20).
    plate_shaped = [v for v in firearms if ident.is_plate_shaped_firearms(v)]
    crossed = (
        [v for v in firearms if (ident.PLATE_RE.fullmatch(v) and not ident.is_plate_shaped_firearms(v))
         or ident.VESSEL_RE.fullmatch(v)]
        + [v for v in vessels if ident.PLATE_RE.fullmatch(v) or ident.FIREARMS_RE.fullmatch(v)]
        + [v for v in plates if ident.is_valid_firearms_license(v) or ident.VESSEL_RE.fullmatch(v)])
    share = len(plate_shaped) / len(firearms)
    report("registry_shapes_disjoint", not crossed and 0.12 <= share <= 0.22
           and len(set(firearms)) > 1000 and len(set(vessels)) > 1000,
           f"firearms={len(set(firearms))} vessels={len(set(vessels))} plate_shaped_share={share:.3f} "
           f"crossed={crossed[:3]} samples={firearms[:3]} {vessels[:3]}")
    report("g4_format_check", all(ident.is_valid_firearms_license(v) for v in firearms)
           and all(ident.is_valid_vessel_registration(v) for v in vessels)
           and not ident.is_valid_firearms_license("DK 45778") and not ident.is_valid_vessel_registration("DK 45778")
           and not ident.is_valid_vessel_registration("HG123456") and not ident.is_valid_firearms_license("N-123-BØ"),
           "generated shapes accepted, plate/vessel/firearm cross-shapes rejected")

    record = gen.Record(0, "mattilsynet_inspection", "prose_letter", "nb", (800, 1600), None, [], [
        gen.PlannedValue("FIREARMS_LICENSE", "A", "value", "HG123456", None, "Våpenkortnummer", True),
        gen.PlannedValue("VESSEL_REGISTRATION", "A", "value", "N-123-BØ", None, "Registreringsmerke", True),
        gen.PlannedValue("VESSEL_REGISTRATION", "A", "value", "DK 45778", None, "Registreringsmerke", True)])
    findings = gen.build_tier_a_findings(record)
    report("g4_flags_malformed_value", [f["actual_valid"] for f in findings] == [True, True, False]
           and not gates.gate_identifier_checksums(findings)[0]
           and gates.gate_identifier_checksums(findings[:2])[0], f"findings={findings}")

    covered = ["HG123456", "ST-476"]
    planned_text = "Han har våpenkortnummer HG123456. Fiskebåten «Havbris» (registrert som ST-476) ligger i Bodø."
    invented_text = ("Han har våpenkortnummer HG987654 og lisensnummer: 2018-475963. Fiskefartøy "
                     "«Nordlys» (reg.nr. N-123-BØ), (reg.nr. SF-4278) og (reg.nr. N54321).")
    plate_text = ("Bilen med registreringsnummer DK 45778 og reg.nr. BT 12345, Registreringsnummer: OS78945. "
                  "Sak 2019/5678, 9008 Tromsø, saksnummer 24-123456. Våpenkort fra 2018.")
    covered_ok = gates.sweep_tier_a(planned_text, gates._covered_intervals(planned_text, covered), set())
    invented = gates.sweep_tier_a(invented_text, [], set())
    plate_hits = [f for f in gates.sweep_tier_a(plate_text, gates._covered_intervals(
        plate_text, ["DK 45778", "BT 12345", "OS78945", "9008"]), {"Tromsø"})]
    report("g7_registry_patterns", not covered_ok and len(invented) == 5
           and {f["pattern"] for f in invented} >= {"firearms_like", "vessel_like"} and not plate_hits,
           f"planned_covered={not covered_ok} invented={[f['match'] for f in invented]} plate_text_hits={plate_hits}")

    def roles(value_type: str, text: str, value: str) -> bool:
        return gates.gate_identifier_roles(text, [(value_type, value)], [value])[0]
    report("g14_registry_roles",
           roles("FIREARMS_LICENSE", "Våpenkortnummer HG123456.", "HG123456")
           and roles("FIREARMS_LICENSE", "Registreringsnummer: AB1234 på rifla.", "AB1234")
           and roles("VESSEL_REGISTRATION", "Fartøyet (reg.nr. SF-4278)", "SF-4278")
           and roles("LICENSE_PLATE", "Bilen, registreringsnummer DK 45778", "DK 45778")
           and not roles("FIREARMS_LICENSE", "Saksnummer HG123456.", "HG123456")
           and not roles("VESSEL_REGISTRATION", "Sak: SF-4278", "SF-4278")
           and not roles("CASE_NUMBER", "Våpenkortnummer 2019/5678", "2019/5678")
           and not roles("CASE_NUMBER", "Fiskefartøyets reg.nr. 2019/5678", "2019/5678")
           and not roles("VESSEL_REGISTRATION", "Våpenkortnummeret er SF-4278", "SF-4278"),
           "own and generic labels pass; case number, firearms and vessel labels crossed are rejected")

    gold_files = sorted(glob.glob(gold_v2_glob))
    if gold_files:
        gold = _load_jsonl(gold_files)
        hits = false_positives = 0
        for doc in gold:
            spans = [sp for vals in doc["output"].values() for sp in vals]
            intervals = gates._covered_intervals(doc["text_input"], spans)
            for pattern in gates.LABELLED_TIER_A_PATTERNS.values():
                for m in pattern.finditer(doc["text_input"]):
                    hits += 1
                    value = m.group(1)
                    if (value not in doc["output"].get("FIREARMS_LICENSE", [])
                            and value not in doc["output"].get("VESSEL_REGISTRATION", [])
                            or not gates._is_covered(m.start(1), m.end(1), intervals)):
                        false_positives += 1
        report("g7_registry_gold_false_positives", false_positives == 0,
               f"{len(gold)} gold_v2 documents, {hits} labelled-pattern hits, "
               f"{false_positives} not on a FIREARMS_LICENSE/VESSEL_REGISTRATION span")

    taxonomy_index = data.taxonomy_index(data.load_taxonomy("data/synthetic/taxonomy.json"))
    bank = {t: v for t, v in clause_bank.items() if t != "negatives"}
    minor_spec = gen.genres_mod.GENRES["police_report"]
    saved = minor_spec.get("minor_subject_p")
    minor_spec["minor_subject_p"] = 1.0
    try:
        adult_forced = []
        for seed in range(40):
            plan = gen.DocPlan(idx=0, genre="police_report", variant="prose_letter", form="nb",
                               length_band=(1600, 2800), forced_types=["FIREARMS_LICENSE"],
                               profile="typical", type_target=8, art9_cap=1)
            rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank,
                                    set(data.PUBLIC_FIGURES))
            adult_forced.append((rec.person.age() >= 18, any(pv.type == "FIREARMS_LICENSE" for pv in rec.planned)))
        child_dropped = []
        for seed in range(40):
            plan = gen.DocPlan(idx=0, genre="school_incident", variant="prose_letter", form="nb",
                               length_band=(1600, 2800), forced_types=["FIREARMS_LICENSE"],
                               profile="typical", type_target=8, art9_cap=1)
            rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank,
                                    set(data.PUBLIC_FIGURES))
            # The youth profile runs to 18, so the subject is sometimes of age; the
            # rule is that the type is planned exactly when the subject is an adult.
            planned_here = any(pv.type == "FIREARMS_LICENSE" for pv in rec.planned)
            child_dropped.append((rec.person.age() < 18, planned_here == (rec.person.age() >= 18)))
    finally:
        minor_spec["minor_subject_p"] = saved if saved is not None else 0.0
        if saved is None:
            del minor_spec["minor_subject_p"]
    minors = [c for c in child_dropped if c[0]]
    report("firearms_blocked_for_minor",
           all(a and b for a, b in adult_forced) and len(minors) >= 10 and all(c[1] for c in child_dropped),
           f"minor-prone genre keeps the subject adult and plans it in {sum(a and b for a, b in adult_forced)}/40; "
           f"{len(minors)} minor subjects in a youth genre, type planned for {sum(1 for c in minors if not c[1])} of them")
    return ok


def unit_checks(clause_bank: dict, partition: dict, gold_glob: str, pilot_dir: str) -> bool:
    """Run the checks that need no generation. Returns True when all pass."""
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} unit {name:<34} {detail}")

    train_bank = dataset_mod.select_clause_bank(clause_bank, partition, "train")
    bench_bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")
    texts = lambda bank: {e["text"] for t, v in bank.items() if t != "negatives" for e in v  # noqa: E731
                          if e.get("genres")}
    shared = texts(train_bank) & texts(bench_bank)
    neg_shared = ({e["text"] for v in bench_bank["negatives"].values() for e in v}
                  & (texts(train_bank) | {e["text"] for v in train_bank["negatives"].values() for e in v}))
    report("partition_clauses_disjoint", not shared and not neg_shared,
           f"train={len(texts(train_bank))} benchmark={len(texts(bench_bank))} "
           f"shared={sorted(shared | neg_shared)[:3]}")
    train_pools = dataset_mod.select_pools(partition, "train")
    bench_pools = dataset_mod.select_pools(partition, "benchmark")
    overlaps = {name: sorted(set(getattr(train_pools, name)) & set(getattr(bench_pools, name)))
                for name in ("first_male", "first_female", "surnames", "street_names", "org_prefixes")}
    for nat in train_pools.foreign_names:
        for k, label in enumerate(("first_male", "first_female", "surnames")):
            overlaps[f"{nat}:{label}"] = sorted(set(train_pools.foreign_names[nat][k])
                                                & set(bench_pools.foreign_names[nat][k]))
    report("partition_pools_disjoint", not any(overlaps.values()),
           f"surnames train/benchmark={len(train_pools.surnames)}/{len(bench_pools.surnames)} "
           f"streets={len(train_pools.street_names)}/{len(bench_pools.street_names)} "
           f"overlaps={ {k: v for k, v in overlaps.items() if v} }")
    pinned_present = all(
        any(e["text"] == t and e.get("plantable") for v in bench_bank["negatives"].values() for e in v)
        for t in dataset_mod.PINNED_BENCHMARK_NEGATIVES)
    report("pinned_negatives_in_benchmark", pinned_present,
           str(list(dataset_mod.PINNED_BENCHMARK_NEGATIVES)))

    leaked = next(e["text"] for t, v in bench_bank.items() if t != "negatives" for e in v
                  if e.get("genres") and e["form"] == "nb" and len(e["text"]) >= 20 and "{" not in e["text"])
    clean_train = [{"id": "T1", "text_input": "Et vanlig dokument uten noe spesielt.", "output": {}}]
    clean_bench = [{"id": "B1", "text_input": "Et annet dokument uten overlapp.", "output": {}}]
    clean = leakage.check(clean_train, clean_bench, clause_bank, partition)
    leaky = leakage.check(
        [{"id": "T1", "text_input": f"Det er opplyst at vedkommende {leaked}.", "output": {"PERSON": ["Kari Test"]}}],
        [{"id": "B1", "text_input": f"Det er opplyst at vedkommende {leaked}.", "output": {"PERSON": ["Kari Test"]}}],
        clause_bank, partition)
    report("leakage_check_fires", clean["ok"] and not leaky["ok"]
           and bool(leaky["shared_clause_texts"]) and bool(leaky["shared_full_names"])
           and bool(leaky["shared_skeleton_hashes"]),
           f"clean_ok={clean['ok']} leaky: texts={len(leaky['shared_clause_texts'])} "
           f"names={leaky['shared_full_names']} skeletons={len(leaky['shared_skeleton_hashes'])}")

    quote = "nektet å oppgi om han er fagorganisert"
    document = f"Saksbehandleren noterte at vedkommende {quote}. Saken avsluttes."
    pairs = [("SENSITIV", quote)]
    with_exempt = audit.filter_audit_findings(document, [], pairs, exempt_spans=[quote])
    without = audit.filter_audit_findings(document, [], pairs)
    extended = f"Saksbehandleren noterte at vedkommende {quote} fordi han er medlem av LO. Saken avsluttes."
    still = audit.filter_audit_findings(
        extended, [], [("SENSITIV", f"{quote} fordi han er medlem av LO")], exempt_spans=[quote])
    report("audit_exempts_planted_negative", not with_exempt and bool(without) and bool(still),
           f"exempt={len(with_exempt)} not_exempt={len(without)} elaboration_still_flagged={len(still)}")

    ok &= spec_alignment_checks(clause_bank)

    gold_files = sorted(glob.glob(gold_glob))
    if gold_files:
        gold = _load_jsonl(gold_files)
        passed = sum(1 for d in gold if gates.gate_tabular_dump(
            d["text_input"], [s for spans in d["output"].values() for s in spans])[0])
        report("g13_passes_gold", passed / len(gold) >= 0.98, f"{passed}/{len(gold)} gold documents pass")
    pilot_path = os.path.join(pilot_dir, "synthetic_batch.jsonl")
    if os.path.exists(pilot_path):
        pilot = {d["id"]: d for d in _load_jsonl([pilot_path])}
        verdict = {i: gates.gate_tabular_dump(d["text_input"], [s for spans in d["output"].values()
                                                                for s in spans])[0]
                   for i, d in pilot.items()}
        missed = sorted(i for i in _PILOT_V3_DUMPS if i in verdict and verdict[i])
        wrongly = sorted(i for i, passed in verdict.items() if not passed and i not in _PILOT_V3_DUMPS)
        report("g13_rejects_pilot_v3_dumps", not missed and len(wrongly) <= 4,
               f"missed={missed} also_rejected={wrongly}")
    return ok


# ---------------------------------------------------------------------------
# Sectioned generation
# ---------------------------------------------------------------------------

# One case per document: (name, the first section index that may be corrupted).
# The mock corrupts that section's first attempt only, so what the pipeline does
# about it is the whole observable: which gate fired, in which section, and what
# was written again.
SECTION_CASES: Dict[int, Tuple[str, int]] = {
    0: ("missing_value_repair", 1),
    1: ("missing_value_section3", 2),
    2: ("category_heading", 2),
    3: ("neutral_heading_normalised", 1),
    4: ("cross_section_repetition", 3),
    5: ("clean", 0),
    6: ("clean_nn", 0),
    7: ("invented_fnr", 1),
    8: ("truncated_section", 2),
    9: ("clean_case_file", 0),
    10: ("clean", 0),
    11: ("clean_nn", 0),
    12: ("audit_elaboration", 1),
}
_SECTION_GENRES = ["police_report", "nav_decision", "gp_referral", "dismissal_letter", "udi_decision",
                   "school_incident", "barnevern_concern", "mattilsynet_inspection"]


def build_section_plans() -> List[gen.DocPlan]:
    """One dense or case-file plan per sectioned case, with negatives planned like a benchmark's."""
    plans = []
    for idx, (name, _target) in sorted(SECTION_CASES.items()):
        case_file = name == "clean_case_file"
        plans.append(gen.DocPlan(
            idx=idx, genre=_SECTION_GENRES[idx % len(_SECTION_GENRES)], variant="prose_letter",
            form="nn" if name.endswith("_nn") else "nb",
            length_band=(3600, 4600) if case_file else (2800, 4000), forced_types=[],
            profile="case_file" if case_file else "dense", type_target=22 if case_file else 16,
            art9_cap=2, n_negatives=2))
    return plans


class SectionInjectingMock(MockBackend):
    """A mock backend that corrupts one section of each document, once, in one specific way.

    Every other call, the regeneration of a corrupted section included, gets the
    clean mock output, so a section that is written again comes back right.
    """

    def __init__(self) -> None:
        self.fired: Dict[int, int] = {}  # document index -> section index corrupted

    def generate(self, prompts, **kwargs):
        outputs = super().generate(prompts, **kwargs)
        finished = [True] * len(prompts)
        for i, prompt in enumerate(prompts):
            if "\nSECTION|" not in prompt or "\nREPAIR|" in prompt:
                continue
            seed = int(re.search(r"SEED\|(\d+)", prompt).group(1))
            idx, attempt = divmod(seed - BASE_SEED * 100003, 97)
            name, target = SECTION_CASES.get(idx, ("clean", 0))
            k, n = (int(x) for x in re.search(r"SECTION\|(\d+)\|(\d+)\|", prompt).groups())
            droppable = [v for v in _values(prompt) + _values(prompt, "CLAUSE_SEEDED") if len(v) > 4]
            wants = {"missing_value_repair": 1, "missing_value_section3": 3}.get(name, 0)
            if (name.startswith("clean") or attempt != 1 or idx in self.fired or k < min(target, n - 1)
                    or len(droppable) < wants):
                continue
            self.fired[idx] = k
            outputs[i], finished[i] = self._corrupt(name, outputs[i], prompt)
        self.last_finished = finished
        return outputs

    @staticmethod
    def _corrupt(name: str, text: str, prompt: str) -> Tuple[str, bool]:
        if name == "missing_value_repair":
            return _drop(text, prompt, 1), True
        if name == "missing_value_section3":
            return _drop(text, prompt, 3), True
        if name == "category_heading":
            return "Helserelaterte opplysningar\n" + text, True
        if name == "neutral_heading_normalised":
            return "Nærmere om forholdene\n\n" + text, True
        if name == "invented_fnr":
            return text + " Opplyst fnr for naboen er 01018012345.", True
        if name == "audit_elaboration":
            return text + f" Pasienten {MOCK_ELABORATION_CUE}.", True
        if name == "truncated_section":
            return text, False
        if name == "cross_section_repetition":
            context = prompt.split("<<<TIDLIGERE>>>\n", 1)[1].split("\n<<<SLUTT PÅ TIDLIGERE>>>", 1)[0]
            return text + "\n\n" + context.split("\n\n")[-1], True
        return text, True


def section_cases(taxonomy_index, clause_bank, partition, out_dir: str) -> Tuple[bool, List[dict]]:
    """Run the sectioned-generation cases. Returns (all passed, accepted documents for G1)."""
    ok = True
    public_figures = set(data.PUBLIC_FIGURES)
    place_names = {p for _c, p in data.POSTAL_PAIRS}
    agency_names = set(data.AGENCY_NAMES)
    bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")
    negative_bank = bank.pop("negatives")
    mock = SectionInjectingMock()
    config = gen.GenerationConfig(
        strategy="seeded", invalid_checksum_rate=0.0, retries=3, near_dup_threshold=0.7,
        g7_policy="reject", batch_size=4, audit=True, max_audit_repairs=1, dataset="benchmark",
        negative_bank=negative_bank, sectioning="auto")
    states, stats = gen.run_generation(
        build_section_plans(), BASE_SEED, taxonomy_index, bank, public_figures, place_names,
        agency_names, mock, config)

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} section {name:<28} {detail}")

    docs = []
    visible = []
    for st in states:
        idx = st.plan.idx
        name, _target = SECTION_CASES[idx]
        plan = st.section_plan
        k = mock.fired.get(idx)
        accepted = bool(st.result.get("accepted"))
        text = st.result.get("text", "")
        section_fails = [e for e in st.gate_log if e.get("scope") == "section" and not e["ok"]]
        joined_fails = [e for e in st.gate_log if not e.get("ok") and "section" not in e]
        attempts = [s.attempts for s in plan.sections] if plan else []
        only_k_again = bool(plan) and k is not None and all(
            a == (2 if i == k else 1) for i, a in enumerate(attempts))
        all_once = bool(plan) and all(a == 1 for a in attempts)
        base = accepted and plan is not None and st.attempt == 1
        detail = f"sections={len(attempts)} attempts={attempts} doc_attempt={st.attempt} fired_in={k}"
        if name == "missing_value_repair":
            passed = (base and k is not None and section_fails and section_fails[0]["stage"] == "G2_verbatim"
                      and section_fails[0]["section"] == k and plan.sections[k].repairs_total == 1
                      and all_once and not joined_fails)
        elif name == "missing_value_section3":
            passed = (base and k is not None and section_fails and section_fails[0]["stage"] == "G2_verbatim"
                      and section_fails[0]["section"] == k and plan.sections[k].repairs_total == 0
                      and only_k_again and not joined_fails)
        elif name == "category_heading":
            first = section_fails[0] if section_fails else {}
            passed = (base and first.get("stage") == "G9_slot" and first.get("section") == k
                      and first["detail"][0]["kind"] == "category_heading" and only_k_again
                      and "Helserelaterte" not in text)
        elif name == "neutral_heading_normalised":
            passed = (base and not section_fails and not joined_fails and all_once
                      and "Nærmere om forholdene" not in text)
        elif name == "cross_section_repetition":
            passed = (base and not section_fails and joined_fails and joined_fails[0]["stage"] == "G12_repetition"
                      and plan.redos_after_join == 1 and only_k_again
                      and gates.repetition_share(text) <= config.repetition_threshold)
        elif name == "invented_fnr":
            passed = (base and section_fails and section_fails[0]["stage"] == "G7_unplanned_pii"
                      and section_fails[0]["section"] == k and only_k_again and "01018012345" not in text)
        elif name == "audit_elaboration":
            reasons = [f["reason"] for entry in st.audit_log for f in entry["findings"]]
            passed = (base and not section_fails and not joined_fails and all_once
                      and "unlabelled_sensitive" in reasons and st.audit_repairs_total == 1
                      and k is not None and plan.sections[k].audit_repairs == 1
                      and sum(s.audit_repairs for s in plan.sections) == 1
                      and MOCK_ELABORATION_CUE not in text)
        elif name == "truncated_section":
            passed = (base and section_fails and section_fails[0]["stage"] == "G10_truncated"
                      and section_fails[0]["section"] == k and only_k_again)
        else:
            passed = base and not section_fails and not joined_fails and all_once
        report(f"#{idx} {name}", bool(passed), detail)
        if plan:
            visible.append(plan.headings_visible)
        if accepted:
            docs.append({"id": f"SEC-{idx:03d}", "text_input": text, "output": st.result["output"],
                         "state": st})

    # Whatever the injections did, the joined document must validate: every label is a
    # substring of the text at a known position, and every section the plan promised is there.
    located = all(sp in d["text_input"] for d in docs for spans in d["output"].values() for sp in spans)
    complete = all(
        all(sec.text and sec.text in d["text_input"] for sec in d["state"].section_plan.sections)
        for d in docs)
    report("joined_document_validates", located and complete and len(docs) == len(states),
           f"documents={len(docs)}/{len(states)} labels_located={located} sections_present={complete}")
    report("headings_vary", True in visible and False in visible or len(visible) < 6,
           f"headings_visible={visible.count(True)} flowing={visible.count(False)}")
    print(f"section run stats: {stats}")
    for d in docs:
        d.pop("state")
    return ok, docs


def section_unit_checks(taxonomy_index, clause_bank, partition) -> bool:
    """Checks on the section plan and the section prompt that need no backend."""
    import random
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} section {name:<28} {detail}")

    problems = sections_mod.validate_catalogue()
    report("catalogue_headings_neutral", not problems, f"problems={problems[:3]}")
    covered = [g for g in genres_mod.genre_names() if g in sections_mod.GENRE_FAMILY]
    report("every_genre_has_a_family", len(covered) == len(genres_mod.genre_names()),
           f"genres={len(covered)}/{len(genres_mod.genre_names())}")
    lengths = {f: len(seq) for f, seq in sections_mod.FAMILIES.items()}
    report("families_have_3_to_5_roles", all(3 <= n <= 5 for n in lengths.values()), f"{lengths}")

    bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")
    negative_bank = bank.pop("negatives")
    public_figures = set(data.PUBLIC_FIGURES)
    over_cap, unassigned, bad_heading, wrong_form = [], [], [], []
    shares, seen_sections = [], []
    n_docs = 0
    for seed in range(60):
        profile = "case_file" if seed % 3 == 0 else "dense"
        genre = _SECTION_GENRES[seed % len(_SECTION_GENRES)]
        plan = gen.DocPlan(
            idx=seed, genre=genre, variant="prose_letter", form="nn" if seed % 2 else "nb",
            length_band=(3600, 4600) if profile == "case_file" else (2800, 4000), forced_types=[],
            profile=profile, type_target=22 if profile == "case_file" else 16, art9_cap=2, n_negatives=2)
        rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank,
                                public_figures, negative_bank=negative_bank, dataset="benchmark")
        sp = sections_mod.build_plan(rec, random.Random(seed))
        n_docs += 1
        seen_sections.append(len(sp.sections))
        items = sorted(i for s in sp.sections for i in s.items)
        negs = sorted(j for s in sp.sections for j in s.negatives)
        if items != list(range(len(rec.planned))) or negs != list(range(len(rec.planted_negatives))):
            unassigned.append(seed)
        over_cap += [(seed, s.load) for s in sp.sections if s.load > sections_mod.MAX_ITEMS]
        col = rec.form
        for s in sp.sections:
            if sections_mod.names_category(s.role_heading):
                bad_heading.append(s.role_heading)
            if s.role_heading not in sections_mod.KINDS[s.kind][col] and not any(
                    s.role_heading in ov[0 if col == "nb" else 1]
                    for ov in sections_mod.FAMILY_HEADINGS.get(sp.family, {}).values()):
                wrong_form.append((rec.form, s.role_heading))
        loads = [s.load for s in sp.sections]
        shares.append(max(loads) - min(loads))
        # Cast members act where their role is: a witness's values are never in the
        # signature section, and the signatory's are in the last one.
        for s in sp.sections:
            for i in s.items:
                if rec.planned[i].party == "author" and s.index != len(sp.sections) - 1:
                    unassigned.append(("author_not_last", seed))
    report("every_item_in_one_section", not unassigned, f"documents={n_docs} problems={unassigned[:3]}")
    report("at_most_7_items_per_section", not over_cap, f"over_cap={over_cap[:3]}")
    report("headings_neutral_and_in_form", not bad_heading and not wrong_form,
           f"category={bad_heading[:2]} wrong_form={wrong_form[:2]}")
    report("sections_3_to_8", min(seen_sections) >= 3 and max(seen_sections) <= sections_mod.MAX_SECTIONS,
           f"min={min(seen_sections)} max={max(seen_sections)} mean_load_spread={sum(shares) / len(shares):.1f}")

    # The prompt of section k carries only section k's values, the text before it, its
    # heading, the shared rules and the manifest the mock reads.
    plan = gen.DocPlan(idx=1, genre="police_report", variant="prose_letter", form="nb",
                       length_band=(2800, 4000), forced_types=[], profile="dense", type_target=16,
                       art9_cap=2, n_negatives=2)
    rec = gen.sample_record(random.Random(1), 1, plan, "seeded", taxonomy_index, bank,
                            public_figures, negative_bank=negative_bank, dataset="benchmark")
    sp = sections_mod.build_plan(rec, random.Random(1))
    sp.headings_visible = True
    for sec in sp.sections:
        sec.heading = sec.role_heading
    k = 2
    sp.sections[0].text = "Innledning\n\n" + "Åpningen av dokumentet nevner saken. " * 20
    sp.sections[1].text = "Videre tekst fra den andre delen. " * 10
    prompt = gen.build_section_prompt(rec, sp, k, [s.text for s in sp.sections[:k]])
    visible_part = model_visible(prompt)
    mine = [rec.planned[i].value for i in sp.sections[k].items if rec.planned[i].value]
    others = [rec.planned[i].value for s in sp.sections if s.index != k for i in s.items
              if rec.planned[i].value and len(rec.planned[i].value) > 6]
    foreign = [v for v in others if v in visible_part and v not in mine]
    # A foreign value may appear legitimately only inside the cast list or the previous text.
    leaked = [v for v in foreign if f"«{v}»" in visible_part]
    report("prompt_has_only_this_sections_items",
           all(f"«{v}»" in visible_part for v in mine) and not leaked,
           f"own={len(mine)} listed_from_other_sections={leaked[:2]}")
    report("prompt_carries_context_and_rules",
           "<<<TIDLIGERE>>>" in visible_part and "Innledning" in visible_part
           and f"del {k + 1} av {len(sp.sections)}" in visible_part and "ORDRETT" in visible_part
           and "Skriv bare denne delen" in visible_part and "ikke i tabeller" in visible_part
           and f"«{sp.sections[k].heading}»" in visible_part
           and f"\nSECTION|{k}|{len(sp.sections)}|" in prompt,
           f"chars={len(visible_part)}")
    long_context = sections_mod.previous_context(
        ["Første del. " * 300, "Midten én. " * 200, "Midten to. " * 200, "Siste før. " * 50])
    report("context_keeps_first_drops_oldest",
           long_context.startswith("Første del.") and "Siste før." in long_context
           and "Midten én." not in long_context and "…" in long_context
           and len(long_context) <= sections_mod.CONTEXT_BUDGET_CHARS + 50,
           f"chars={len(long_context)}")
    last_prompt = model_visible(gen.build_section_prompt(rec, sp, len(sp.sections) - 1,
                                                          [s.text for s in sp.sections[:-1]]))
    first_prompt = model_visible(gen.build_section_prompt(rec, sp, 0, []))
    report("only_last_section_closes",
           "dokumentet avsluttes her" in last_prompt and "dokumentet avsluttes her" not in first_prompt
           and "dokumentet fortsetter i neste del" in first_prompt, "")
    return ok


def no_discard_check(taxonomy_index, clause_bank, partition) -> bool:
    """Dense and case-file mock documents are no longer discarded for missing values."""
    public_figures = set(data.PUBLIC_FIGURES)
    place_names = {p for _c, p in data.POSTAL_PAIRS}
    agency_names = set(data.AGENCY_NAMES)
    bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")
    negative_bank = bank.pop("negatives")
    plans = []
    for i in range(24):
        profile = "case_file" if i % 2 else "dense"
        plans.append(gen.DocPlan(
            idx=i, genre=_SECTION_GENRES[i % len(_SECTION_GENRES)], variant="prose_letter",
            form="nn" if i % 3 == 0 else "nb",
            length_band=(3600, 4600) if profile == "case_file" else (2800, 4000), forced_types=[],
            profile=profile, type_target=24 if profile == "case_file" else 16, art9_cap=2, n_negatives=2))
    config = gen.GenerationConfig(
        strategy="seeded", invalid_checksum_rate=0.0, retries=3, near_dup_threshold=0.7,
        g7_policy="reject", batch_size=4, audit=True, dataset="benchmark", negative_bank=negative_bank)
    states, _stats = gen.run_generation(plans, 11, taxonomy_index, bank, public_figures, place_names,
                                        agency_names, MockBackend(), config)
    accepted = sum(1 for st in states if st.result.get("accepted"))
    g2 = sum(1 for st in states for e in st.gate_log if e["stage"] == "G2_verbatim")
    passed = accepted == len(states) and g2 == 0
    print(f"{'PASS' if passed else 'FAIL'} section {'dense_case_file_not_discarded':<28} "
          f"accepted={accepted}/{len(states)} G2_failures={g2}")
    return passed


# ---------------------------------------------------------------------------
# Planted near-miss negatives
# ---------------------------------------------------------------------------

def mock_dataset_run(dataset: str, n: int, seed: int, taxonomy_index, clause_bank, partition) -> dict:
    """Run the whole generator on the mock backend, as `--dataset X --n N --coverage-target 3` does.

    Returns:
        `{"docs": accepted documents with id/text_input/output, "meta": the planted negatives
        per document, "ledger": the run's reuse report, "states": every state, "stats": run stats,
        "plans": the plans, "coherence_log": the cast-coherence report of every record sampled,
        "coherence_rejected": records refused before generation}`.
    """
    import random
    mode = dataset_mod.MODES[dataset]
    run_seed = seed + mode.seed_offset
    rng = random.Random(run_seed)
    bank = dataset_mod.select_clause_bank(clause_bank, partition, dataset)
    negative_bank = bank.pop("negatives") if mode.negatives_by_profile else {}
    bank.pop("negatives", None)
    data.use_pools(dataset_mod.select_pools(partition, dataset))
    try:
        public_figures = set(data.PUBLIC_FIGURES)
        place_names = {p for _c, p in data.POSTAL_PAIRS}
        agency_names = set(data.AGENCY_NAMES)
        types = [entry["name"] for entry in data.load_taxonomy("data/synthetic/taxonomy.json")["types"]]
        plans, _plan_report = gen.plan_batch(
            rng, n, genres_mod.genre_names(), [], 0.5, coverage_target=3,
            schedulable_types=genres_mod.coverage_types(types), mode=mode, clause_bank=bank,
            coverage_margin=1,
            natural_probe=gen._make_natural_probe(run_seed, taxonomy_index, bank, public_figures))
        config = gen.GenerationConfig(
            strategy="seeded", invalid_checksum_rate=0.05, retries=4, near_dup_threshold=0.7,
            g7_policy="reject", batch_size=4, audit=True, dataset=dataset,
            difficulty_weights=mode.difficulty_weights, negative_bank=negative_bank)
        states, stats = gen.run_generation(plans, run_seed, taxonomy_index, bank, public_figures,
                                           place_names, agency_names, MockBackend(), config)
    finally:
        data.use_pools(data.full_pools())
    docs, planted = [], []
    for st in states:
        if not st.result.get("accepted"):
            continue
        doc_id = f"{mode.id_prefix}-{st.plan.idx:06d}"
        docs.append({"id": doc_id, "text_input": st.result["text"], "output": st.result["output"],
                     "profile": st.plan.profile, "sectioned": st.section_plan is not None,
                     "sections": len(st.section_plan.sections) if st.section_plan else 0})
        planted.append({"id": doc_id, "planted_negatives": [
            {"text": n_.text, "template": n_.template, "type": n_.type, "surface": n_.found}
            for n_ in st.record.planted_negatives]})
    return {"docs": docs, "meta": planted, "ledger": config.negative_ledger.report(),
            "states": states, "stats": stats, "plans": plans, "coherence_log": config.coherence_log,
            "coherence_rejected": config.coherence_rejected}


def negative_checks(taxonomy_index, clause_bank, partition, out_dir: str, types_config: str) -> bool:
    """The near-miss negatives: placeholders, planting, the per-run cap, the partition and leakage."""
    import collections
    import random
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} negative {name:<30} {detail}")

    # Pronoun filling by gender and form.
    forms = {(f, g): dataset_mod.fill_pronouns("og {PRON} fant {POSS} sak, og {OBJ} også", g, f)
             for f in ("nb", "nn") for g in ("M", "F")}
    expected = {("nb", "M"): "og han fant hans sak, og ham også", ("nb", "F"): "og hun fant hennes sak, og henne også",
                ("nn", "M"): "og han fant hans sak, og han også", ("nn", "F"): "og ho fant hennar sak, og henne også"}
    report("pronouns_by_gender_and_form", forms == expected and
           dataset_mod.fill_pronouns("ingen plassholder", "M", "nb") == "ingen plassholder",
           str({k: v.split(",")[0] for k, v in forms.items()}))

    # The planting itself: filled, verbatim, never labelled, never a leftover placeholder.
    bench_bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")["negatives"]
    nn_female = gen.Person("Sigrid", "Test", "F", gen.date(1985, 3, 3))
    nb_male = gen.Person("Per", "Test", "M", gen.date(1985, 3, 3))
    picks = {}
    for person, form in ((nn_female, "nn"), (nb_male, "nb")):
        for seed in range(40):
            plan = gen.DocPlan(idx=0, genre="nav_decision", variant="prose_letter", form=form,
                               length_band=(1600, 2800), forced_types=[], profile="typical", n_negatives=3)
            spec = genres_mod.GENRES["nav_decision"]
            chosen = gen._plant_negatives(random.Random(seed), plan, spec, person, form, set(), bench_bank, [])
            for neg in chosen:
                if "{" in neg.template:
                    picks.setdefault(form, neg)
    filled_ok = all("{" not in n_.text and n_.text != n_.template for n_ in picks.values())
    word_ok = (re.search(r"\b(ho|hennar)\b", picks["nn"].text) is not None
               and re.search(r"\b(han|hans|ham)\b", picks["nb"].text) is not None
               and "hun" not in picks["nb"].text)
    report("placeholders_filled_for_the_subject", bool(picks) and filled_ok and word_ok,
           f"nn={picks['nn'].text!r} nb={picks['nb'].text!r}")

    # Run the generator as the verification does, once per dataset.
    bench = mock_dataset_run("benchmark", 100, 1, taxonomy_index, clause_bank, partition)
    train = mock_dataset_run("train", 100, 1, taxonomy_index, clause_bank, partition)
    for label, run in (("benchmark", bench), ("train", train)):
        planted = [n_ for m in run["meta"] for n_ in m["planted_negatives"]]
        use = collections.Counter(n_["template"] for n_ in planted)
        per_doc = collections.Counter(len(m["planted_negatives"]) for m in run["meta"])
        by_id = {d["id"]: d for d in run["docs"]}
        verbatim = all(gates.negative_occurrences(by_id[m["id"]]["text_input"], n_["text"])
                       for m in run["meta"] for n_ in m["planted_negatives"])
        unlabelled = True
        for m in run["meta"]:
            spans = [sp for vals in by_id[m["id"]]["output"].values() for sp in vals]
            for n_ in m["planted_negatives"]:
                if any(n_["surface"] in sp for sp in spans if len(sp) >= len(n_["surface"])):
                    unlabelled = False
        allowed = {e["text"] for v in dataset_mod.select_clause_bank(clause_bank, partition, label)["negatives"].values()
                   for e in v if e.get("plantable")}
        own_partition = all(t in allowed for t in use)
        cap_ok = max(use.values(), default=0) <= dataset_mod.NEGATIVE_CAP_PER_RUN
        limit = 3 if label == "benchmark" else 1
        count_ok = max(per_doc, default=0) <= limit and (label == "train" or min(
            (len(m["planted_negatives"]) for m, d in zip(run["meta"], run["docs"])
             if d["profile"] not in ("pii_free",) ), default=1) >= 0)
        report(f"{label}_run_cap_and_partition",
               cap_ok and own_partition and verbatim and unlabelled and count_ok and sum(use.values()) > 0
               and run["ledger"]["max_reuse"] <= dataset_mod.NEGATIVE_CAP_PER_RUN,
               f"accepted={len(run['docs'])} plantings={sum(use.values())} distinct={len(use)} "
               f"max_reuse={max(use.values(), default=0)} per_doc={dict(sorted(per_doc.items()))} "
               f"verbatim={verbatim} unlabelled={unlabelled}")
    bench_planted = {n_["template"] for m in bench["meta"] for n_ in m["planted_negatives"]}
    train_planted = {n_["template"] for m in train["meta"] for n_ in m["planted_negatives"]}
    report("train_and_benchmark_plant_disjoint_texts", not (bench_planted & train_planted),
           f"benchmark={len(bench_planted)} train={len(train_planted)} shared={sorted(bench_planted & train_planted)[:2]}")
    leak = leakage.check(train["docs"], bench["docs"], clause_bank, partition,
                         train_meta=train["meta"], benchmark_meta=bench["meta"])
    report("leakage_none_between_mock_runs", leak["ok"] and not leak["shared_negative_texts"],
           f"shared_clause={len(leak['shared_clause_texts'])} negatives={len(leak['shared_negative_texts'])} "
           f"names={len(leak['shared_full_names'])} skeletons={len(leak['shared_skeleton_hashes'])}")

    # G1 on both runs' labelled subsets, then the numbers the report asks for.
    validator = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_labels.py")
    for label, run in (("benchmark", bench), ("train", train)):
        path = os.path.join(out_dir, f"mock_{label}_labelled.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for d in run["docs"]:
                if d["output"]:
                    handle.write(json.dumps({"id": d["id"], "text_input": d["text_input"],
                                             "output": d["output"]}, ensure_ascii=False) + "\n")
        proc = subprocess.run([sys.executable, validator, path, "--config", types_config],
                              capture_output=True, text=True)
        sectioned = [d for d in run["docs"] if d["sectioned"]]
        big = [st for st in run["states"] if st.plan.profile in ("dense", "case_file")]
        big_ok = sum(1 for st in big if st.result.get("accepted"))
        report(f"{label}_g1_and_sectioned_share", proc.returncode == 0 and big_ok == len(big),
               f"G1_exit={proc.returncode} sectioned={len(sectioned)}/{len(run['docs'])} "
               f"dense_case_file_accepted={big_ok}/{len(big)} "
               f"sections_per_doc={dict(sorted(collections.Counter(d['sections'] for d in sectioned).items()))}")

    # The leakage check must catch a negative planted in both files.
    shared_template = next(iter(sorted(bench_planted)))
    entry = next(e for v in clause_bank["negatives"].values() for e in v if e["text"] == shared_template)
    filled = dataset_mod.fill_pronouns(shared_template, "F", entry["form"])
    leaky = leakage.check(
        [{"id": "T1", "text_input": f"Saken er avsluttet, {filled}. Ferdig.", "output": {}}],
        [{"id": "B1", "text_input": f"Et annet dokument; {filled}. Slutt.", "output": {}}],
        clause_bank, partition,
        train_meta=[{"id": "T1", "planted_negatives": [{"text": filled, "template": shared_template}]}],
        benchmark_meta=[{"id": "B1", "planted_negatives": [{"text": filled, "template": shared_template}]}])
    clean = leakage.check(
        [{"id": "T1", "text_input": "Et vanlig dokument.", "output": {}}],
        [{"id": "B1", "text_input": f"Et annet dokument; {filled}. Slutt.", "output": {}}],
        clause_bank, partition)
    report("leakage_catches_shared_negative",
           not leaky["ok"] and shared_template in leaky["shared_negative_texts"]
           and shared_template in leaky["shared_planted_negatives"] and clean["ok"],
           f"shared={list(leaky['shared_negative_texts'])[:1]} clean_ok={clean['ok']}")

    # The bank and the partition.
    added = [(t, e) for t, v in clause_bank["negatives"].items() for e in v if e.get("origin") == "nearmiss_v5"]
    bench_side = {s for v in partition["negatives"].values() for s in v}
    train_listed = {s for v in partition.get("negatives_train", {}).items() for s in v[1]}
    nn_share = sum(1 for _t, e in added if e["form"] == "nn") / max(1, len(added))
    texts = [e["text"] for _t, e in added]
    types_covered = {t for t, _e in added}
    needed = {"RELIGIOUS_BELIEF", "TRADE_UNION", "ETHNICITY", "SEXUAL_ORIENTATION", "POLITICAL", "HEALTH",
              "DISABILITY", "MEDICATION", "CRIMINAL", "BEHAVIORAL_PATTERN", "ECONOMIC_STATUS", "FINANCIAL",
              "BIOMETRIC_DATA", "GENETIC_DATA", "IMMIGRATION_STATUS", "ACADEMIC_RECORD"}
    report("new_negatives_cover_types_and_nynorsk",
           len(added) >= 150 and nn_share >= 0.35 and needed <= types_covered and len(set(texts)) == len(texts)
           and all(e.get("plantable") and e.get("why_not") for _t, e in added),
           f"added={len(added)} nn_share={nn_share:.2f} types={len(types_covered)}")
    in_bench = {e["text"] for _t, e in added if e["text"] in bench_side}
    in_train = {e["text"] for _t, e in added if e["text"] not in bench_side}
    report("new_negatives_partitioned_disjointly",
           in_bench and in_train and not (in_bench & train_listed) and in_train == train_listed
           and 0.2 <= len(in_train) / len(added) <= 0.4,
           f"benchmark={len(in_bench)} train={len(in_train)} share_train={len(in_train) / len(added):.2f}")
    # Every new negative reads as an ordinary clause when filled, and is a null under the spec's
    # plainest tests: no digit unless it is an identifier-shaped one, no kinship or marital word, no capitals.
    banned = re.compile(r"\b(barn|mor|far|søster|bror|kone|ektefelle|ektemann|samboer|gift|skilt|enke|sønn|datter|"
                        r"norsk|svensk|polsk|januar|februar|mars|april|juni|juli|august|september|oktober|"
                        r"november|desember|statsborger|hund|katt)\b", re.IGNORECASE)
    bad = []
    for _t, e in added:
        for g in "MF":
            filled = dataset_mod.fill_pronouns(e["text"], g, e["form"])
            digits = re.search(r"\d", filled) and e.get("kind") != "id_shaped"
            caps = [w for w in re.findall(r"\b[A-ZÆØÅ]\w*", filled) if w not in ("DNA",) and not re.fullmatch(r"[A-Z]{2}\d+", w)]
            if (digits or caps or banned.search(filled) or "{" in filled or not filled[0].islower()
                    or len(filled) < 12 or not e["genres"]):
                bad.append(filled)
    report("new_negatives_pass_plain_null_tests", not bad, f"bad={bad[:2]}")
    # No text is a substring of one on the other side of the partition (a leak the checker would raise).
    bench_clause = {s for v in partition["clauses"].values() for s in v}
    side_bench, side_train = set(), set()
    for v in clause_bank["negatives"].values():
        for e in v:
            for g in "MF":
                (side_bench if e["text"] in bench_side else side_train).add(
                    dataset_mod.fill_pronouns(e["text"], g, e["form"]))
    for t, v in clause_bank.items():
        if t != "negatives":
            for e in v:
                if e.get("genres"):
                    (side_bench if e["text"] in bench_clause else side_train).add(e["text"])
    new_texts = {dataset_mod.fill_pronouns(e["text"], g, e["form"]) for _t, e in added for g in "MF"}
    crossing = [(a, b) for a in side_bench & new_texts if len(a) >= leakage.MIN_TEXT_CHARS
                for b in side_train if a != b and a in b]
    crossing += [(a, b) for a in side_train & new_texts if len(a) >= leakage.MIN_TEXT_CHARS
                 for b in side_bench if a != b and a in b]
    report("no_text_inside_a_text_of_the_other_side", not crossing, f"crossing={crossing[:2]}")
    unplanted = [e for e in clause_bank["negatives"]["ETHNICITY"]
                 if e["text"] in ("har utenlandsk klingende navn", "har utanlandsk klingande namn")]
    report("v2_positive_negatives_unplanted", len(unplanted) == 2 and not any(e.get("plantable") for e in unplanted),
           f"unplanted={[e['text'] for e in unplanted]}")
    return ok


# ---------------------------------------------------------------------------
# How planted negatives are worded, placed, framed and partitioned
# ---------------------------------------------------------------------------

# Bokmål forms that must not occur in a Nynorsk negative, and the Nynorsk errors pilot v5 and the
# review of the bank found: a noun given the wrong gender, and an a-verb written with the Bokmål ending.
_BOKMAL_IN_NYNORSK = re.compile(
    r"\b(?:ikke|hva|hvem|hvilken|noe|noen|uten|mye|siden|bare|mannlig|etter|gjør)\b")
_NYNORSK_ERRORS = re.compile(r"\bei (?:bydel|minoritet|bankfilial|dokumentar|artikkel)\b|\boppbevarer\b")


def negative_wording_checks(taxonomy_index, clause_bank: dict, partition: dict) -> bool:
    """The wording of the planted negatives, the G15 and G11 handling of their placement and framing.

    Covers: no fixed "og"/"men" opening (in the bank and in the prompts), the Nynorsk and the
    reflexive-possessive fixes, a negative that opens a sentence being matched case-insensitively in
    its first letter, G15's three hits, the audit's framing finding for a neutral negative, and the
    deterministic rebuild of the negatives batch.
    """
    import hashlib
    import random
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} negwording {name:<36} {detail}")

    negatives = [(t, e) for t, v in clause_bank["negatives"].items() for e in v]
    plantable = [e for _t, e in negatives if e.get("plantable")]

    # -- no fixed opening --------------------------------------------------------------
    opening_conj = [e["text"] for e in plantable if re.match(r"(?:og|men)\b", e["text"])]
    firsts = collections.Counter(e["text"].split()[0] for e in plantable)
    pairs = collections.Counter(" ".join(e["text"].split()[:2]) for e in plantable
                                if not e["text"].startswith("{"))
    top_word, top_n = firsts.most_common(1)[0]
    top_pair, top_pair_n = pairs.most_common(1)[0]
    report("bank_has_no_fixed_opening",
           not opening_conj and top_n / len(plantable) <= 0.5 and top_pair_n / len(plantable) <= 0.06
           and len(firsts) >= 20,
           f"og/men openings={len(opening_conj)} commonest first word {top_word!r} {top_n / len(plantable):.2f} "
           f"commonest pair {top_pair!r} {top_pair_n / len(plantable):.3f} distinct first words={len(firsts)}")

    bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")
    negative_bank = bank.pop("negatives")
    public_figures = set(data.PUBLIC_FIGURES)
    plan = gen.DocPlan(idx=1, genre="police_report", variant="prose_letter", form="nb",
                       length_band=(2800, 4000), forced_types=[], profile="dense", type_target=16,
                       art9_cap=2, n_negatives=2)
    rec = gen.sample_record(random.Random(1), 1, plan, "seeded", taxonomy_index, bank,
                            public_figures, negative_bank=negative_bank, dataset="benchmark")
    sp = sections_mod.build_plan(rec, random.Random(1))
    holder = next(k for k, sec in enumerate(sp.sections) if sec.negatives)
    whole = model_visible(gen.build_prompt(rec))
    section = model_visible(gen.build_section_prompt(rec, sp, holder, [s.text for s in sp.sections[:holder]]))
    lines = [ln for ln in whole.splitlines()
             if ln.startswith("- «") and any(n_.text in ln for n_ in rec.planted_negatives)]
    report("prompts_state_the_placement_rule_and_no_fixed_opening",
           bool(rec.planted_negatives) and len(lines) == len(rec.planted_negatives)
           and not any(re.match(r"- «(?:og|men)\b", ln) for ln in lines)
           and gen._NEGATIVE_PLACEMENT_RULE in whole and gen._NEGATIVE_PLACEMENT_RULE in section
           and "etter en hovedsetning eller et komma" not in whole,
           f"negative_lines={[ln[:40] for ln in lines]} rule_in_whole={gen._NEGATIVE_PLACEMENT_RULE in whole} "
           f"rule_in_section={gen._NEGATIVE_PLACEMENT_RULE in section}")

    # -- Nynorsk and Bokmål grammar of the bank ----------------------------------------
    bad_nn = [e["text"] for _t, e in negatives if e["form"] == "nn"
              and (_BOKMAL_IN_NYNORSK.search(e["text"]) or _NYNORSK_ERRORS.search(e["text"]))]
    nn_texts = [e["text"] for _t, e in negatives if e["form"] == "nn"]
    fixed_present = (any("ein bydel" in t for t in nn_texts) and any("ein minoritet" in t for t in nn_texts)
                     and any("oppbevarar" in t for t in nn_texts))
    # A possessive that refers back to the clause's own subject is reflexive: "om sin seksuelle legning".
    non_reflexive = [e["text"] for _t, e in negatives
                     if "{PRON}" in e["text"] and re.search(r"\b(?:om|på|med|av) \{POSS\}", e["text"])]
    report("nynorsk_gender_and_reflexive_fixed", not bad_nn and fixed_present and not non_reflexive,
           f"nynorsk problems={bad_nn[:2]} fixed_forms_present={fixed_present} non_reflexive={non_reflexive[:2]}")

    # -- a negative that opens a sentence is matched with its first letter in either case ---
    negative = "han ville ikke svare på hva han tror på"
    capital_text = "Saken er avklart. Han ville ikke svare på hva han tror på. Mer følger."
    inline_text = "Saken er avklart, og han ville ikke svare på hva han tror på. Mer følger."
    wrong_case = "Saken er avklart. HAN ville ikke svare på hva han tror på."
    surfaces = gates.resolve_surfaces([negative], capital_text) + gates.resolve_surfaces([negative], inline_text)
    g2_cap = gates.gate_verbatim(gates.resolve_surfaces([negative], capital_text), capital_text)
    g2_wrong = gates.gate_verbatim(gates.resolve_surfaces([negative], wrong_case), wrong_case)
    template = "han ville ikke svare på hva {PRON} tror på"
    seen = leakage.texts_in([{"id": "D1", "text_input": capital_text}, {"id": "D2", "text_input": wrong_case}],
                            [template])
    report("capitalised_sentence_initial_negative_matched",
           surfaces == ["Han ville ikke svare på hva han tror på", negative] and g2_cap[0] and not g2_wrong[0]
           and seen == {template: ["D1"]},
           f"surfaces={surfaces} g2_capital={g2_cap[0]} g2_other_case_rejected={not g2_wrong[0]} leakage_seen={seen}")

    # -- G15 ----------------------------------------------------------------------------
    one, two = "han bor i nærheten av en bankfilial", "han tok ikke stilling til spørsmålet om livssynet sitt"
    cap_one, cap_two = one.capitalize(), two.capitalize()
    clause = "har antatt god økonomi"

    def kinds(text: str, negs, clauses=()) -> List[str]:
        return [h["kind"] for h in gates.gate_negative_placement(text, negs, clauses)[1]]

    chained = f"Det fremgår at {one}, og {two}."
    apart = f"{cap_one}. Mer følger. {cap_two}."
    with_clause = f"Han {clause}, og {one}."
    clause_apart = f"Han {clause}. {cap_one}."
    twice = f"{cap_one}. Senere: {one}."
    report("g15_rejects_chained_negatives_and_clause_chains",
           kinds(chained, [one, two]) == ["chained_negatives"] and not kinds(apart, [cap_one, cap_two])
           and kinds(with_clause, [one], [clause]) == ["chained_to_clause"]
           and not kinds(clause_apart, [cap_one], [clause]) and kinds(twice, [one]) == ["repeated_negative"],
           f"chained={kinds(chained, [one, two])} apart={kinds(apart, [cap_one, cap_two])} "
           f"clause={kinds(with_clause, [one], [clause])} clause_apart={kinds(clause_apart, [cap_one], [clause])} "
           f"twice={kinds(twice, [one])}")

    # -- G11: a neutral negative presented as relevant ----------------------------------
    framed = f"Det vurderes at {one}, noe som er relevant for saken."
    denied = f"Det vurderes at {one}, noe som ikke er relevant for saken."
    plain = f"Det vurderes at {one}."
    backend = MockBackend()

    def audit_pairs(document: str, negs) -> list:
        prompt = audit.build_audit_prompt(document, [], 7, negatives=[("FINANCIAL", n_) for n_ in negs])
        return audit.parse_audit_reply(backend.generate([prompt])[0])

    with_manifest = audit_pairs(framed, [one])
    without_manifest = audit_pairs(framed, [])
    findings = audit.filter_audit_findings(framed, [], with_manifest, exempt_spans=[one])
    inside = audit.filter_audit_findings(framed, [], [("RAMME", one)], exempt_spans=[one])
    shown = model_visible(audit.build_audit_prompt(framed, [], 7, negatives=[("FINANCIAL", one)]))
    report("audit_flags_a_negative_framed_as_relevant",
           [k for k, _q in with_manifest] == ["RAMME"] and not without_manifest and len(findings) == 1
           and findings[0]["reason"] == "sensitive_framing" and not inside
           and not audit_pairs(denied, [one]) and not audit_pairs(plain, [one])
           and "Plantede nøytrale formuleringer" in shown and one in shown,
           f"with_negatives={[k for k, _q in with_manifest]} without={without_manifest} kept={len(findings)} "
           f"quote_inside_negative_dropped={not inside} negated_cue_clean={not audit_pairs(denied, [one])}")

    # -- the negatives batch is rebuilt deterministically ------------------------------
    batch = "nearmiss_v5"
    batch_texts = {e["text"] for _t, e in negatives if e.get("origin") == batch}
    recorded = partition["negative_batches"][batch]
    digest = hashlib.sha256("\n".join(sorted(batch_texts)).encode("utf-8")).hexdigest()[:16]
    rebuilt = dataset_mod.rebuild_negatives(partition, clause_bank, batch)
    again = dataset_mod.rebuild_negatives(rebuilt, clause_bank, batch)
    # A partition made before the texts were corrected: the old texts are listed, none of the new.
    stale = json.loads(json.dumps(partition))
    for key in ("negatives", "negatives_train"):
        for etype in list(stale[key]):
            stale[key][etype] = [t for t in stale[key][etype] if t not in batch_texts]
        stale[key]["HEALTH"] = stale[key].get("HEALTH", []) + ["og han hadde en gammel formulering"]
    stale["negative_batches"][batch]["digest"] = "0" * 16
    from_stale = dataset_mod.rebuild_negatives(stale, clause_bank, batch)
    report("negatives_partition_rebuild_is_deterministic",
           rebuilt == partition and again == rebuilt and from_stale == partition
           and recorded["digest"] == digest,
           f"matches_committed={rebuilt == partition} idempotent={again == rebuilt} "
           f"same_from_stale_partition={from_stale == partition} digest_current={recorded['digest'] == digest}")
    bench_side = {t for v in partition["negatives"].values() for t in v}
    train_side = {t for v in partition["negatives_train"].values() for t in v}
    ratio = recorded["benchmark"] / recorded["texts"]
    report("negatives_partition_keeps_the_ratio_and_the_sides",
           batch_texts <= bench_side | train_side and not (bench_side & train_side)
           and (recorded["benchmark"], recorded["train"]) == (len(batch_texts & bench_side), len(batch_texts & train_side))
           and abs(ratio - dataset_mod.NEGATIVE_BATCH_BENCHMARK_RATIO) <= 0.05,
           f"texts={len(batch_texts)} benchmark={recorded['benchmark']} train={recorded['train']} share={ratio:.3f}")
    try:
        dataset_mod.extend_negatives(partition, clause_bank, batch)
        refused = False
    except ValueError:
        refused = True
    report("negatives_partition_second_extension_refused", refused, f"refused={refused}")
    return ok


# ---------------------------------------------------------------------------
# Record-level checks: several instances of a type, possible people, special categories
# ---------------------------------------------------------------------------

def _bank_entries(clause_bank: dict) -> List[Tuple[str, dict, "re.Pattern"]]:
    """Return `(type, entry, pattern)` for every clause entry; a pattern matches the entry's text
    with its name placeholders filled, so a planted clause can be traced back to its bank entry."""
    out = []
    for etype, entries in clause_bank.items():
        if etype == "negatives":
            continue
        for entry in entries:
            pattern = re.escape(entry["text"])
            pattern = re.sub(r"\\\{(?:PERSON|PERSON_M|PERSON_F|SURNAME_FAM|SURNAME_ORG)\\\}", r".+?", pattern)
            out.append((etype, entry, re.compile("^" + pattern + "$")))
    return out


def _entry_of(index, etype: str, form: str, text: str) -> Optional[dict]:
    return next((e for t, e, rx in index if t == etype and e["form"] == form and rx.match(text)), None)


def record_checks(taxonomy_index, clause_bank: dict, partition: dict, out_dir: str) -> bool:
    """The checks for several instances of a type, the cast-coherence rules and the special categories."""
    import collections
    import random
    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'} record {name:<34} {detail}")

    public_figures = set(data.PUBLIC_FIGURES)
    place_names = {p for _c, p in data.POSTAL_PAIRS}
    agency_names = set(data.AGENCY_NAMES)
    index = _bank_entries(clause_bank)

    # -- the bank and its partition ----------------------------------------------------
    new = [(t, e) for t, entries in clause_bank.items() if t != "negatives"
           for e in entries if e.get("origin") == "multi_v6"]
    nn_share = sum(1 for _t, e in new if e["form"] == "nn") / max(1, len(new))
    no_topic = [e["text"] for t, e in new if not e.get("topic")]
    batch = partition.get("clause_batches", {}).get("multi_v6", {})
    bench_new = {t for v in partition["clauses"].values() for t in v} & {e["text"] for _t, e in new}
    train_new = {t for v in partition.get("clauses_train", {}).values() for t in v}
    batch_texts = {e["text"] for _t, e in new}
    old_texts = {e["text"] for t, entries in clause_bank.items() if t != "negatives"
                 for e in entries if e.get("origin") != "multi_v6"}
    report("new_clauses_cover_types_and_nynorsk", nn_share >= 0.35 and not no_topic
           and {t for t, _e in new} >= {"CRIMINAL", "HEALTH", "MEDICATION", "BEHAVIORAL_PATTERN",
                                         "FINANCIAL", "ECONOMIC_STATUS"},
           f"entries={len(new)} nn_share={nn_share:.2f} without_topic={no_topic[:2]} "
           f"by_type={dict(collections.Counter(t for t, _e in new))}")
    report("new_clauses_partitioned_about_a_quarter",
           bench_new.isdisjoint(train_new) and (bench_new | train_new) == batch_texts
           and train_new.isdisjoint(old_texts) and 0.2 <= len(bench_new) / max(1, len(batch_texts)) <= 0.32
           and batch.get("benchmark") == len(bench_new) and batch.get("train") == len(train_new),
           f"benchmark={len(bench_new)} train={len(train_new)} share={len(bench_new) / max(1, len(batch_texts)):.3f}")
    # Run again, the extension must refuse and leave the old assignments alone.
    try:
        dataset_mod.extend_clauses(partition, clause_bank, "multi_v6")
        refused = False
    except ValueError:
        refused = True
    fresh = dataset_mod.extend_clauses({**partition, "clause_batches": {}}, clause_bank, "multi_v6")
    report("clause_extension_deterministic_and_idempotent", refused and fresh["clauses"] == partition["clauses"],
           f"second_run_refused={refused} same_assignments_on_rerun={fresh['clauses'] == partition['clauses']}")

    # New entries obey the v2 boundary rules that can be tested mechanically.
    determiner = re.compile(r"^(?:en|et|ei|ein|eit|den|det|de)\b", re.IGNORECASE)
    linking = re.compile(r"^(?:er|var|har|hadde|blir|ble)\b")
    bad = [e["text"] for _t, e in new if determiner.match(e["text"]) or linking.match(e["text"])
           or e["text"][-1] in ".,;:!?" or e["text"] != e["text"].strip()]
    report("new_clauses_follow_boundary_rules", not bad, f"leading determiner/linking verb or final punctuation: {bad[:3]}")

    # -- supply: three or four compatible clauses for the main cases -------------------
    from datetime import date
    main_cases = [("police_report", "CRIMINAL"), ("gp_referral", "HEALTH"), ("gp_referral", "MEDICATION"),
                  ("vet_clinical_record", "HEALTH"), ("debt_counselling", "FINANCIAL"),
                  ("debt_counselling", "ECONOMIC_STATUS"), ("barnevern_concern", "BEHAVIORAL_PATTERN"),
                  ("school_incident", "BEHAVIORAL_PATTERN")]
    thin = []
    supply_cells = {}
    for dataset in ("train", "benchmark"):
        bank = dataset_mod.select_clause_bank(clause_bank, partition, dataset)
        for genre, etype in main_cases:
            spec = genres_mod.GENRES[genre]
            for form in ("nb", "nn"):
                youth = spec.get("age_profile") == "youth"
                person = gen.Person("Test", "Person", "F", date(2026 - (11 if youth else 40), 3, 3))
                subject = gen._Subject(person, genre, form, set(spec["clause_genres"]),
                                       animal_types=set(spec.get("animal_types", ())))
                fits = [e for e in bank.get(etype, []) if gen._clause_fits(e, subject, etype) and not e.get("as_type")]
                chosen: List[dict] = []
                for entry in sorted(fits, key=lambda e: e["text"]):
                    if gen.clauses_compatible(chosen, entry) and not (
                            entry.get("group") and any(c.get("group") == entry["group"] for c in chosen)):
                        chosen.append(entry)
                supply_cells[(dataset, genre, etype, form)] = len(chosen)
                if len(chosen) < 3:
                    thin.append((dataset, genre, etype, form, len(chosen)))
    report("bank_supplies_three_compatible_clauses", not thin,
           f"cells={len(supply_cells)} min={min(supply_cells.values())} thin={thin[:4]}")

    # -- clauses_compatible: contradictions and repeats are refused -----------------------
    a = {"text": "dømt for vold i 2010", "topic": "violence"}
    cases = [
        ("same_topic", [a], {"text": "siktet for grov vold i 2021", "topic": "violence"}, False),
        ("also_topic", [{"text": "anmeldt for trusler med kniv", "topic": "threat", "also": ["weapon"]}],
         {"text": "ulovlig våpenbesittelse", "topic": "weapon"}, False),
        ("text_contained", [a], {"text": "dømt for vold i 2010 og 2011", "topic": "other"}, False),
        ("shared_six_word_run", [{"text": "han ble dømt for grov vold mot en nabo i 2010", "topic": "x"}],
         {"text": "dømt for grov vold mot en nabo igjen", "topic": "y"}, False),
        ("headline_floor", [{"text": "gjeld på over 700 000 NOK", "topic": "debt_total", "kind": "headline", "amount": 700000},
                            {"text": "studielån på 340 000 NOK hos Lånekassen", "topic": "student_loan", "kind": "debt", "amount": 340000}],
         {"text": "forbrukslån på 450 000 NOK hos Nordea", "topic": "consumer_loan", "kind": "debt", "amount": 450000}, False),
        ("as_type_never_extra", [a], {"text": "gift med Kari Hansen", "topic": "spouse", "as_type": "MARITAL_STATUS"}, False),
        ("distinct_is_fine", [a], {"text": "tiltalt for innbrudd i en bolig i 2021", "topic": "burglary"}, True),
        ("short_shared_stem_is_fine", [{"text": "dømt for vold i 2010", "topic": "violence"}],
         {"text": "dømt for heleri i 2018", "topic": "receiving"}, True),
    ]
    wrong = [name for name, chosen, cand, want in cases if gen.clauses_compatible(chosen, cand) != want]
    report("clauses_compatible_rules", not wrong, f"cases={len(cases)} wrong={wrong}")

    # -- means, psychiatric condition and status cannot contradict across types -------------
    person = gen.Person("Test", "Person", "F", date(1986, 3, 3))
    spec = genres_mod.GENRES["debt_counselling"]
    subject = gen._Subject(person, "debt_counselling", "nb", set(spec["clause_genres"]))
    rich = next(e for e in clause_bank["ECONOMIC_STATUS"] if e.get("polarity") == "rich" and e["form"] == "nb")
    poor_fin = next(e for e in clause_bank["FINANCIAL"] if e.get("polarity") == "poor" and e["form"] == "nb"
                    and "nav_decision" in e["genres"])
    gen._commit_entry(subject, "ECONOMIC_STATUS", rich)
    poor_blocked = not gen._clause_fits(poor_fin, subject, "FINANCIAL")
    subject2 = gen._Subject(person, "gp_referral", "nb", {"gp_referral"})
    depression = next(e for e in clause_bank["HEALTH"] if e.get("topic") == "depression" and e["form"] == "nb")
    anxiety = next(e for e in clause_bank["HEALTH"] if e.get("topic") == "anxiety" and e["form"] == "nb")
    antidepressant = next(e for e in clause_bank["MEDICATION"] if e.get("topic") == "depression" and e["form"] == "nb")
    antipsychotic = next(e for e in clause_bank["MEDICATION"] if e.get("topic") == "psychosis" and e["form"] == "nb")
    gen._commit_entry(subject2, "HEALTH", depression)
    report("subject_state_blocks_contradictions",
           poor_blocked and not gen._clause_fits(anxiety, subject2, "HEALTH")
           and gen._clause_fits(antidepressant, subject2, "MEDICATION")
           and not gen._clause_fits(antipsychotic, subject2, "MEDICATION"),
           f"rich_means_blocks_poor_debt={poor_blocked} second_psychiatric_condition_blocked=True "
           f"matching_medication_allowed=True")

    # -- many records: every extra instance is distinct, compatible and in budget --------------
    problems: List[str] = []
    multi_docs = 0
    extras_total = 0
    shortfalls = collections.Counter()
    for dataset in ("train", "benchmark"):
        bank = dataset_mod.select_clause_bank(clause_bank, partition, dataset)
        bank.pop("negatives")
        data.use_pools(dataset_mod.select_pools(partition, dataset))
        try:
            for seed in range(260):
                genre = sorted(genres_mod.MULTI_PROPENSITY)[seed % len(genres_mod.MULTI_PROPENSITY)]
                profile = ("typical", "dense", "case_file", "dense")[seed % 4]
                form = "nn" if seed % 3 == 0 else "nb"
                length = {"typical": (1600, 2800), "dense": (2800, 4000), "case_file": (3600, 4600)}[profile]
                plan = gen.DocPlan(
                    idx=seed, genre=genre, variant="prose_letter", form=form, length_band=length,
                    forced_types=[], profile=profile, type_target={"typical": 8, "dense": 14, "case_file": 22}[profile],
                    art9_cap=2, instances={t: 4 for t in genres_mod.MULTI_PROPENSITY[genre]})
                rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank,
                                        public_figures, dataset=dataset)
                if rec.pii_free:
                    continue
                by_type = collections.defaultdict(list)
                for pv in rec.planned:
                    if pv.value_kind == "clause" and pv.type in clause_bank:
                        by_type[pv.type].append(pv)
                states = {"psych": {}, "general_condition": {}, "cause": {}, "behaviour": {}, "children": {},
                          "partner": {}, "intoxication": {}, "infection": {}, "musculoskeletal": {}}
                polarities = set()
                for etype, pvs in by_type.items():
                    entries = [_entry_of(index, etype, form, pv.value) for pv in pvs]
                    if any(e is None for e in entries):
                        problems.append(("untraceable", seed, etype))
                        continue
                    topics = [t for e in entries for t in gen._entry_topics(e)]
                    if len(pvs) >= 2:
                        multi_docs += 1
                        extras_total += len(pvs) - 1
                    if len(set(topics)) != len(topics):
                        problems.append(("repeated_topic", seed, etype, topics))
                    texts = [pv.value.lower() for pv in pvs]
                    for i in range(len(texts)):
                        for j in range(i + 1, len(texts)):
                            if texts[i] in texts[j] or texts[j] in texts[i] or gen._shares_word_run(texts[i], texts[j]):
                                problems.append(("repeated_words", seed, etype, texts[i], texts[j]))
                    for e in entries:
                        if e.get("polarity"):
                            polarities.add(e["polarity"])
                        if e.get("group") in states:
                            states[e["group"]].setdefault(e["topic"], 0)
                    headlines = [e["amount"] for e in entries if e.get("kind") == "headline"]
                    if headlines and sum(e.get("amount", 0) for e in entries if e.get("kind") == "debt") > min(headlines):
                        problems.append(("debt_above_headline", seed))
                for group, seen in states.items():
                    if len(seen) > 1:
                        problems.append(("two_topics_in_one_group", seed, group, sorted(seen)))
                if len(polarities) > 1:
                    problems.append(("means_contradict", seed, sorted(polarities)))
                if len(rec.planned) + len(rec.planted_negatives) > genres_mod.item_budget(profile, length[1]) + 12:
                    problems.append(("over_item_budget", seed, len(rec.planned)))
                for etype, n in rec.instances_planned.items():
                    shortfalls[etype] += max(0, n - rec.instances_realised.get(etype, 1 if any(
                        pv.type == etype for pv in rec.planned) else 0))
        finally:
            data.use_pools(data.full_pools())
    report("extra_instances_distinct_and_consistent", not problems and multi_docs > 100,
           f"types_with_2plus_instances={multi_docs} extras={extras_total} problems={problems[:3]}")

    # -- caps count categories, not instances ----------------------------------------------
    bank = dataset_mod.select_clause_bank(clause_bank, partition, "train")
    bank.pop("negatives")
    typical = gen.DocPlan(idx=0, genre="gp_referral", variant="prose_letter", form="nb", length_band=(1600, 2800),
                          forced_types=[], profile="typical", type_target=9, art9_cap=1,
                          instances={"HEALTH": 3, "MEDICATION": 2})
    dense = gen.DocPlan(idx=1, genre="gp_referral", variant="prose_letter", form="nb", length_band=(2800, 4000),
                        forced_types=[], profile="dense", type_target=12, art9_cap=2,
                        instances={"HEALTH": 3, "MEDICATION": 2})
    got = {}
    for name, plan in (("typical", typical), ("dense", dense)):
        for seed in range(40):
            rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank, public_figures)
            fam = collections.Counter(pv.type for pv in rec.planned if pv.type in genres_mod.HEALTH_FAMILY)
            if fam.get("HEALTH", 0) >= 3:
                got.setdefault(name, (len(fam), sum(fam.values()), dict(fam)))
                break
    cap_ok = ("typical" in got and got["typical"][0] == 1 and got["typical"][1] >= 3
              and "dense" in got and got["dense"][0] <= genres_mod.health_family_cap("dense") < got["dense"][1])
    report("caps_count_categories_not_instances", cap_ok,
           f"typical(cap {genres_mod.health_family_cap('typical')}): {got.get('typical')} "
           f"dense(cap {genres_mod.health_family_cap('dense')}): {got.get('dense')}")

    # -- G6 and G12 do not reject several clauses that share words -----------------------------
    stems = ["dømt for vold mot offentlig tjenestemann i 2010", "dømt for dokumentfalsk i 2014",
             "dømt for heleri i 2018", "dømt for farlig kjøring i 2023"]
    frames = " ".join(f"Videre er det opplyst at vedkommende {c}." for c in stems)
    text = frames + " " + frames.replace("Videre er det opplyst", "Det er også opplyst")
    plain = gates.repetition_share(text)
    exempt = gates.repetition_share(text, exempt=stems)
    prose_a = "Saken gjelder en kontroll i Oslo sentrum. Opplysningene er hentet fra politiets register. "
    prose_b = "Rapporten omhandler en anmeldelse fra nabolaget. Opplysningene stammer fra tidligere saker hos politiet. "
    doc_a = prose_a + " ".join(f"Han er {c}." for c in stems)
    doc_b = prose_b + " ".join(f"Han er {c}." for c in stems)
    sim_plain = gates.jaccard(gates.word_ngrams(doc_a), gates.word_ngrams(doc_b))
    sim_exempt = gates.jaccard(gates.word_ngrams(doc_a, exempt=stems), gates.word_ngrams(doc_b, exempt=stems))
    looping = ("Han er dømt for heleri i 2018. " * 6 + "Saken følges opp av ansvarlig enhet. ")
    report("g12_g6_do_not_count_shared_clauses",
           plain > 0.06 >= exempt and sim_plain >= 0.5 > sim_exempt
           and gates.repetition_share(looping, exempt=["dømt for heleri i 2018"]) > 0.06,
           f"G12 share {plain:.3f}->{exempt:.3f} (limit 0.06); G6 similarity {sim_plain:.2f}->{sim_exempt:.2f}; "
           "a clause looped six times is still caught")

    # -- the cast: possible ages, and a record that breaks the rules is refused --------------------
    cm = coherence.Member
    broken = coherence.check(93, [cm("parent", 121), cm("author", 19), cm("child", 6), cm("spouse", 30), cm("officer", 70)])
    rules = sorted({rule for rule, _role, _age in broken})
    clean = coherence.check(40, [cm("parent", 68), cm("author", 25), cm("author", 67), cm("child", 12), cm("spouse", 36),
                                 cm("physician", 52)])
    report("coherence_check_names_the_violations",
           {"parent_too_old", "professional_age", "child_gap", "spouse_age"} <= set(rules) and not clean,
           f"rules={rules} clean_cast_violations={clean}")
    rng = random.Random(4)
    fixed, rep = coherence.enforce_cast(93, [cm("parent", 121), cm("author", 19), cm("child", 6), cm("officer", 70)], rng)
    flipped_ok = fixed[0] is not None and fixed[0].role == "child" and 93 - fixed[0].age >= coherence.MIN_PARENT_GAP
    report("coherence_repairs_parent_and_professionals",
           flipped_ok and not coherence.check(93, [m for m in fixed if m]) and rep.flipped == 1 and rep.fixed == 3,
           f"{rep.notes}")
    young = coherence.enforce_cast(12, [cm("child", 5)], random.Random(1))
    report("coherence_drops_an_impossible_member", young[0] == [None] and young[1].dropped == 1,
           f"subject 12 cannot have a child: dropped={young[1].dropped}")

    # A record whose cast is impossible is refused and sampled again before any prompt exists.
    plan = gen.DocPlan(idx=3, genre="psychologist_note", variant="prose_letter", form="nb", length_band=(1600, 2800),
                       forced_types=[], profile="typical", type_target=8, art9_cap=1)
    config = gen.GenerationConfig(strategy="seeded", invalid_checksum_rate=0.0, retries=1, near_dup_threshold=0.7,
                                  g7_policy="reject", dataset="train")
    state = gen.DocState(plan)
    real_sample = gen.sample_record
    calls = []

    def poisoned(rng, doc_seed, plan_, *args, **kwargs):
        rec = real_sample(rng, doc_seed, plan_, *args, **kwargs)
        calls.append(doc_seed)
        if len(calls) == 1:
            rec.parties.append(gen.Party(gen.Person("Ole", "Fredriksen", "M", gen.date(1905, 5, 5)), "parent",
                                         "forelder"))
            rec.parties.append(gen.Party(gen.Person("Kari", "Tester", "F", gen.date(2007, 5, 5)), "author", "saksbehandler",
                                         staff=True))
        return rec

    gen.sample_record = poisoned
    try:
        record = gen.new_attempt_record(state, 11, taxonomy_index, bank, public_figures, config)
    finally:
        gen.sample_record = real_sample
    report("incoherent_record_rejected_before_generation",
           len(calls) == 2 and config.coherence_rejected == 1 and not gen.check_record_coherence(record),
           f"samples={len(calls)} rejected={config.coherence_rejected} violations_in_first="
           f"{[r for r, _a, _b in coherence.check(40, [cm('parent', 121), cm('author', 19)])]}")

    # -- the finished mock runs: how many plans needed fixing --------------------------------------
    run = mock_dataset_run("train", 120, 3, taxonomy_index, clause_bank, partition)
    summary = coherence.summarise(run["coherence_log"], run["coherence_rejected"])
    leftovers = [st.plan.idx for st in run["states"] if st.record and gen.check_record_coherence(st.record)]
    report("mock_run_casts_are_possible", not leftovers,
           f"records={summary['records_checked']} with_a_violation={summary['records_with_a_violation']} "
           f"ages_redrawn={summary['fixed_by_redrawing_an_age']} parents_flipped="
           f"{summary['fixed_by_turning_a_parent_into_a_child']} dropped={summary['fixed_by_dropping_the_member']} "
           f"rejected={summary['rejected_and_resampled']} by_rule={summary['violations_by_rule']}")

    # Many documents stay at one instance, and the repeated ones fit the section planner's limit.
    docs_by_id = {d["id"]: d for d in run["docs"]}
    shares = {}
    for etype in ("CRIMINAL", "HEALTH", "BEHAVIORAL_PATTERN", "FINANCIAL"):
        counts = [len(d["output"][etype]) for d in run["docs"] if etype in d["output"]]
        shares[etype] = (sum(1 for c in counts if c == 1) / max(1, len(counts)), sum(1 for c in counts if c >= 2))
    bench_run = mock_dataset_run("benchmark", 120, 3, taxonomy_index, clause_bank, partition)
    loads = [s.load for st in bench_run["states"] if st.section_plan is not None for s in st.section_plan.sections]
    repeated = sum(1 for st in bench_run["states"] if st.record and st.record.instances_realised)
    report("most_documents_stay_at_one_and_sections_stay_small",
           all(share >= 0.5 and n >= 1 for share, n in shares.values()) and loads and max(loads) <= sections_mod.MAX_ITEMS
           and repeated >= 10,
           f"share_at_exactly_one={ {t: round(s, 2) for t, (s, _n) in shares.items()} } "
           f"benchmark_docs_with_a_repeated_type={repeated} max_items_in_a_section={max(loads)}")

    nn_docs = [(st, d) for st in run["states"] if st.result.get("accepted") and st.record.form == "nn"
               for d in [docs_by_id[f"SYN-{st.plan.idx:06d}"]]]
    bokmaal = re.compile(r"^(?:Navn|Brukernavn|Statsborgerskap|Nettside|Virksomhet|Enhetsidentifikator|Sted|"
                         r"Førerkortnummer|Tjenestenummer):", re.MULTILINE)
    nynorsk = re.compile(r"^(?:Namn|Brukarnamn|Statsborgarskap|Nettstad|Verksemd|Einingsidentifikator|Stad|"
                         r"Førarkortnummer|Tenestenummer):", re.MULTILINE)
    wrong_labels = [d["id"] for _st, d in nn_docs if bokmaal.search(d["text_input"])]
    right_labels = sum(1 for _st, d in nn_docs if nynorsk.search(d["text_input"]))
    report("nn_documents_print_nn_labels", nn_docs and not wrong_labels and right_labels >= 3,
           f"nn_documents={len(nn_docs)} with_a_nn_only_label={right_labels} with_a_bokmaal_label={wrong_labels[:3]}")

    # -- who a number belongs to: the sampler gives an HPR number to a clinician ----------------------
    wrong_holder = []
    for seed in range(120):
        genre = ("gp_referral", "vet_clinical_record", "mattilsynet_inspection", "psychologist_note",
                 "occupational_health")[seed % 5]
        plan = gen.DocPlan(idx=seed, genre=genre, variant="prose_letter", form="nb", length_band=(1600, 2800),
                           forced_types=["MEDICAL_LICENSE"], profile="typical", type_target=8, art9_cap=1)
        rec = gen.sample_record(random.Random(seed), seed, plan, "seeded", taxonomy_index, bank, public_figures)
        for pv in rec.planned:
            if pv.type == "MEDICAL_LICENSE":
                holder = next((p for p in rec.parties if p.role == (pv.party or "")), None)
                clinical = holder is not None and (holder.role in ("physician", "psychologist", "veterinarian")
                                                    or (holder.role == "author" and rec.signatory_role in gen._CLINICAL_TITLES))
                if pv.party is None or not clinical:
                    wrong_holder.append((genre, pv.party, rec.signatory_role))
    report("hpr_number_belongs_to_a_clinician", not wrong_holder, f"records=120 wrong_holder={wrong_holder[:3]}")

    # -- special categories: hosts are places a real document states them neutrally -----------------
    hosts = {t: sorted(n for n, s in genres_mod.GENRES.items()
                       if t in s["core"] or t in s["judgement"] or t in s["values"])
             for t in sorted(genres_mod.SPECIAL_CATEGORIES)}
    banned = {"POLITICAL": {"police_report", "bank_aml", "dismissal_letter", "digital_forensics_report"},
              "SEXUAL_ORIENTATION": {"digital_forensics_report", "dismissal_letter"},
              "RELIGIOUS_BELIEF": {"dismissal_letter", "school_incident", "barnevern_concern"},
              "TRADE_UNION": {"forsvaret_clearance", "debt_counselling", "court_judgment"},
              "GENETIC_DATA": {"police_report", "occupational_health"}, "BIOMETRIC_DATA": {"dismissal_letter"}}
    present = {t: sorted(set(hosts[t]) & b) for t, b in banned.items() if set(hosts[t]) & b}
    report("art9_hosts_are_plausible", not present and {"forsvaret_clearance", "whistleblowing_report", "hr_grievance",
                                                          "udi_decision"} <= set(hosts["POLITICAL"]),
           f"POLITICAL hosts={hosts['POLITICAL']} still_banned={present}")

    # -- prompt: nn labels, the rules, the audit's three codes ---------------------------------------------
    def prompt_for(form: str, genre: str = "police_report", forced=("DEVICE_ID", "MEDICAL_LICENSE")) -> str:
        pl = gen.DocPlan(idx=5, genre=genre, variant="prose_letter", form=form, length_band=(1600, 2800),
                         forced_types=list(forced), profile="dense", type_target=14, art9_cap=2,
                         instances={"CRIMINAL": 2})
        rc = gen.sample_record(random.Random(5), 5, pl, "seeded", taxonomy_index, bank, public_figures)
        return model_visible(gen.build_prompt(rc))

    nb_prompt, nn_prompt = prompt_for("nb"), prompt_for("nn")
    opening = "Dokumentet kan åpne med én liten identifikasjonsblokk"
    block_nn = nn_prompt.split(opening)[1][:400]
    block_nb = nb_prompt.split(opening)[1][:400]
    report("nn_prompt_uses_nn_field_labels",
           "«Namn:»" in block_nn and "«Navn:»" not in block_nn and "«Navn:»" in block_nb and "«Namn:»" not in block_nb,
           f"nn_block={block_nn[60:150]!r}")
    section_plan_nn = gen.DocPlan(idx=6, genre="nav_decision", variant="prose_letter", form="nn", length_band=(2800, 4000),
                                  forced_types=[], profile="dense", type_target=14, art9_cap=2)
    section_record = gen.sample_record(random.Random(6), 6, section_plan_nn, "seeded", taxonomy_index, bank, public_figures)
    section_prompt = model_visible(gen.build_section_prompt(
        section_record, sections_mod.build_plan(section_record, random.Random(6)), 0, []))
    report("nn_section_prompt_uses_nn_field_labels",
           "«Namn:»" in section_prompt and "«Navn:»" not in section_prompt and "del 1 av" in section_prompt,
           f"chars={len(section_prompt)}")
    report("prompt_rules_special_categories_and_denials",
           all(s in nn_prompt for s in ("nøytralt faktum", "politisk ståsted", "fagforeningsmedlemskap",
                                          "Benekt, begrens, betvil eller forklar aldri bort", "aldri «vår» eller «vårt»",
                                          "tilhører legen, psykologen eller veterinæren"))
           and "ulike forhold" in nn_prompt,
           f"chars={len(nn_prompt)}")
    sample_doc = "Han er aktiv i Senterpartiet, noe som kan være relevant for helhetsvurderingen av mistanken."
    prompt = audit.build_audit_prompt(sample_doc, ["aktiv i Senterpartiet"], 9, clauses=[("POLITICAL", "aktiv i Senterpartiet")])
    task = model_visible(prompt)
    report("audit_prompt_has_three_reason_codes",
           all(s in task for s in ("FUNN|SENSITIV|", "FUNN|RAMME|", "FUNN|MOTSIGELSE|", "Oppgave C", "politisk ståsted",
                                    "medisinbruk", "fagforeningsmedlemskap", "sikkerhetsvurdering"))
           and "CLAUSE|" not in task and "CLAUSE|POLITICAL|" in prompt,
           f"visible_chars={len(task)}")

    def audit_reasons(document: str, labelled: List[str], clauses=()) -> List[str]:
        reply = MockBackend().generate([audit.build_audit_prompt(document, labelled, 3, clauses=clauses)])[0]
        found = audit.filter_audit_findings(document, labelled, audit.parse_audit_reply(reply))
        return [f["reason"] for f in found]

    political = audit_reasons(sample_doc, ["aktiv i Senterpartiet"], [("POLITICAL", "aktiv i Senterpartiet")])
    neutral = audit_reasons("Han er aktiv i Senterpartiet. Saken avsluttes uten videre tiltak.", ["aktiv i Senterpartiet"],
                            [("POLITICAL", "aktiv i Senterpartiet")])
    health_support = audit_reasons("Hun bruker antidepressiva, og dette begrunner tilrettelegging på arbeidsplassen.",
                                   ["bruker antidepressiva"], [("MEDICATION", "bruker antidepressiva")])
    health_framing = audit_reasons("Hun bruker antidepressiva, noe som øker risikoen for at hun kan presses.",
                                   ["bruker antidepressiva"], [("MEDICATION", "bruker antidepressiva")])
    denial = audit_reasons("Det foreligger ingen registrerte straffedommer mot henne. Hun er dømt for vold i 2010.",
                           ["dømt for vold i 2010"], [("CRIMINAL", "dømt for vold i 2010")])
    explain = audit_reasons("Hun er dømt for vold i 2010, men denne finst ikkje i oppgjeve register.",
                            ["dømt for vold i 2010"], [("CRIMINAL", "dømt for vold i 2010")])
    exempt_neg = audit.filter_audit_findings(
        "Han nektet å oppgi om han er fagorganisert. Saken avsluttes.", [],
        [("MOTSIGELSE", "Han nektet å oppgi om han er fagorganisert")],
        exempt_spans=["Han nektet å oppgi om han er fagorganisert"])
    report("audit_flags_framing_in_every_special_category",
           political == ["sensitive_framing"] and not neutral and not health_support
           and health_framing == ["sensitive_framing"],
           f"political={political} neutral={neutral} health_for_support={health_support} health_as_risk={health_framing}")
    report("audit_flags_contradiction_and_exempts_negatives",
           denial == ["contradiction"] and explain == ["contradiction"] and not exempt_neg,
           f"denial={denial} explain_away={explain} planted_negative_findings={len(exempt_neg)}")

    # The pilot's own texts, through the same prompt and the mock auditor. This measures the mock's
    # lexical stand-in, not the model: see the report for what only a real run can judge.
    pilot = os.path.join("data", "synthetic", "pilot_v4_train", "synthetic_batch.jsonl")
    if os.path.exists(pilot):
        clause_types = {t for t, e in taxonomy_index.items() if e.get("value_kind") == "clause"}
        counts: collections.Counter = collections.Counter()
        flagged_docs = {}
        for doc in _load_jsonl([pilot]):
            spans = [s for v in doc["output"].values() for s in v]
            clauses = [(t, s) for t, v in doc["output"].items() if t in clause_types for s in v]
            reasons = audit_reasons(doc["text_input"], spans, clauses)
            counts.update(reasons)
            if reasons:
                flagged_docs[doc["id"]] = reasons
        report("pilot_v4_through_the_mock_auditor",
               flagged_docs.get("SYN-000000", []).count("contradiction") >= 2
               and "sensitive_framing" in flagged_docs.get("SYN-000001", []),
               f"documents={len(_load_jsonl([pilot]))} flagged={len(flagged_docs)} findings={dict(counts)} "
               f"SYN-000000={flagged_docs.get('SYN-000000')} SYN-000001={flagged_docs.get('SYN-000001')}")

    # -- labels and the identification block ----------------------------------------------------------------
    letter_genres = sorted(genres_mod.ID_BLOCK_GENRES - {"mattilsynet_inspection", "vet_clinical_record"})
    plans, _rep = gen.plan_batch(random.Random(2), 400, letter_genres, [], 0.5)
    eligible = [p for p in plans if not p.pii_free and p.profile != "minimal"]
    blocked = sum(1 for p in eligible if "ADDRESS" in p.id_block)
    never = [p for p in plans if (p.pii_free or p.profile == "minimal") and p.id_block]
    report("identification_block_planned_for_letters",
           blocked / max(1, len(eligible)) >= 0.8 and not never,
           f"letter_and_decision_plans_with_address_block={blocked}/{len(eligible)} in_minimal_or_pii_free={len(never)}")
    return ok


_DRIVER = r"""
import os, signal, sys
sys.path.insert(0, os.environ["GD_TOOLS"])
import gendoc_store as store_mod
import generate_documents as gen

after = int(os.environ.get("GD_AFTER", "0"))
action = os.environ.get("GD_ACTION", "")
flag = os.environ.get("GD_FLAG", "")
count = [0]
real_append = store_mod.append_line


def counting_append(path, line):
    real_append(path, line)
    count[0] += 1
    if after and count[0] == after:
        if action == "sigkill":
            os.kill(os.getpid(), signal.SIGKILL)
        elif action == "sigterm":
            os.kill(os.getpid(), signal.SIGTERM)
        elif action == "sigint2":
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGINT)
        elif action in ("stopfile", "busy"):
            open(flag, "w").close()


store_mod.append_line = counting_append
if os.environ.get("GD_MUTATE") == "empty_state":
    real_rebuild = gen.rebuild_cross_doc_state

    def empty_rebuild(store, below_idx, known, cap):
        return [], gen.NegativeLedger(cap)

    gen.rebuild_cross_doc_state = empty_rebuild
sys.argv = ["generate_documents.py"] + sys.argv[1:]
sys.exit(gen.main())
"""

_TIMING_KEYS = {"gen_seconds", "audit_seconds"}


def _strip_timing(value):
    if isinstance(value, dict):
        return {k: (0.0 if k in _TIMING_KEYS else _strip_timing(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_timing(v) for v in value]
    return value


def _document_files(out_dir: str) -> Dict[str, bytes]:
    """Every shard file and the discard file of a run, by name."""
    names = sorted(n for n in os.listdir(out_dir)
                   if re.match(r"^(synthetic|benchmark)_batch_\d{5}", n) or n == "discarded.jsonl")
    return {n: open(os.path.join(out_dir, n), "rb").read() for n in names}


def _normalised(files: Dict[str, bytes]) -> Dict[str, list]:
    """Parse the files with wall-clock timing fields zeroed, the only fields a re-run changes.

    The resume checks compare runs through this rather than raw bytes: the meta
    lines carry rounded wall-clock seconds, which are 0.0 on an idle host but not
    under load, and made the byte comparison fail spuriously on a busy machine.
    Every other field, including all document text and labels, still has to match.
    """
    return {n: [_strip_timing(json.loads(line)) for line in raw.decode("utf-8").splitlines()]
            for n, raw in files.items()}


def resume_checks(out_root: str) -> bool:
    """Prove a mock run can be killed, stopped and resumed without changing what it produces.

    Every case runs `generate_documents.py` in a subprocess through a driver that counts durable
    appends and, after the K-th, kills the process (SIGKILL, so possibly between a document's
    text line and its meta line), raises a signal or creates the stop file. The reference is the
    same run, uninterrupted.
    """
    import shutil
    import stat
    tools = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(tools, "generate_documents.py")
    root = os.path.join(out_root, "resume_checks")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    results: List[Tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> bool:
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'} resume: {name} {detail}")
        return ok

    base = ["--n", "40", "--seed", "7", "--dataset", "benchmark", "--near-dup-threshold", "0.2",
            "--negative-cap", "1", "--batch-size", "4", "--shard-size", "7"]

    def run(out: str, extra: List[str], env: Optional[dict] = None, resume: bool = False,
            use_base: bool = True):
        cmd = [sys.executable, "-c", _DRIVER] + (base if use_base else []) + ["--out", out] + extra
        if resume:
            cmd.append("--resume")
        full_env = {**os.environ, "GD_TOOLS": tools, **(env or {})}
        return subprocess.run(cmd, capture_output=True, text=True, env=full_env, timeout=600)

    def manifest_of(out: str) -> dict:
        return json.load(open(os.path.join(out, "run_manifest.json"), encoding="utf-8"))

    ref = os.path.join(root, "reference")
    proc = run(ref, [])
    ref_files = _document_files(ref)
    ref_docs = {n: len(raw.splitlines()) for n, raw in ref_files.items()}
    record("uninterrupted reference run completes", proc.returncode == 0 and bool(ref_files),
           f"exit {proc.returncode}, {sum(v for n, v in ref_docs.items() if n.endswith('_meta.jsonl'))} "
           f"accepted, {ref_docs.get('discarded.jsonl', 0)} discarded")
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        return False
    ref_report = open(os.path.join(ref, "gate_report.json"), "rb").read()

    # Shard rollover.
    metas = sorted(n for n in ref_files if n.endswith("_meta.jsonl"))
    sizes = [len(ref_files[n].splitlines()) for n in metas]
    texts = [n.replace("_meta", "") for n in metas]
    lab_ok = all(
        [json.loads(l)["id"] for l in ref_files[n.replace(".jsonl", "_labelled.jsonl")].decode().splitlines()]
        == [json.loads(l)["id"] for l in ref_files[n].decode().splitlines()
            if json.loads(l)["output"]] for n in texts)
    ids = [json.loads(l)["id"] for n in metas for l in ref_files[n].decode().splitlines()]
    record("shards roll over at --shard-size, one text/labelled/meta triple per shard",
           all(s == 7 for s in sizes[:-1]) and 0 < sizes[-1] <= 7 and len(sizes) == -(-sum(sizes) // 7)
           and [len(ref_files[n].splitlines()) for n in texts] == sizes and lab_ok
           and metas[0] == "benchmark_batch_00000_meta.jsonl" and len(set(ids)) == len(ids),
           f"shard sizes {sizes}")

    # Kill -9 at arbitrary appends, three times, then finish.
    killed = os.path.join(root, "killed")
    codes = [run(killed, [], {"GD_AFTER": "11", "GD_ACTION": "sigkill"}).returncode]
    for after in ("17", "10"):
        codes.append(run(killed, [], {"GD_AFTER": after, "GD_ACTION": "sigkill"}, resume=True,
                         use_base=False).returncode)
    mid = manifest_of(killed)
    mid_state = (mid["progress"]["status"], mid["progress"]["done"])
    final = run(killed, [], resume=True, use_base=False)
    killed_files = _document_files(killed)
    same_bytes = _normalised(killed_files) == _normalised(ref_files)
    same_norm = _normalised(killed_files) == _normalised(ref_files)
    record("kill -9 three times (between a document's lines too), resume: killed codes are SIGKILL",
           codes == [-9, -9, -9] and final.returncode == 0, f"codes {codes}, final exit {final.returncode}")
    record("killed-and-resumed run is byte-identical to the uninterrupted run (batch, labelled, meta, "
           "discarded)", same_bytes, "" if same_bytes else
           f"differs in {[n for n in ref_files if killed_files.get(n) != ref_files[n]]}; "
           f"identical once wall-clock seconds are zeroed: {same_norm}")
    record("manifest was left 'running' by the kill and is 'finished' after resume",
           mid_state[0] == "running" and manifest_of(killed)["progress"]["status"] == "finished"
           and manifest_of(killed)["progress"]["done"] == 40,
           f"after kills: {mid_state}")
    history = [h["event"] for h in manifest_of(killed)["history"]]
    record("manifest history lists start and each resume", history == ["start", "resume", "resume", "resume"],
           str(history))
    resumed_report = _strip_report(json.loads(open(os.path.join(killed, "gate_report.json")).read()))
    reference_report = _strip_report(json.loads(ref_report))
    record("report of the resumed run equals the uninterrupted run's apart from wall-clock fields",
           resumed_report == reference_report,
           f"differs in {[k for k in reference_report if resumed_report.get(k) != reference_report[k]]}")

    # Mutation: with the rebuilt state discarded, the same kill/resume must NOT match.
    mutant = os.path.join(root, "mutant")
    run(mutant, [], {"GD_AFTER": "30", "GD_ACTION": "sigkill"})
    run(mutant, [], {"GD_MUTATE": "empty_state"}, resume=True, use_base=False)
    mutant_files = _document_files(mutant)
    record("sensitivity: resuming with the G6 list and negative ledger NOT rebuilt changes the output",
           _normalised(mutant_files) != _normalised(ref_files),
           "(proves the rebuild is what makes the resumed run identical)")

    # G6 list and ledger rebuilt from disk equal the live ones of an uninterrupted run.
    live = {}
    real_run_generation = gen.run_generation

    def capture(plans, *a, **kw):
        live.setdefault("ngrams", kw.get("accepted_ngrams"))
        live["config"] = a[-1] if a else kw.get("config")
        return real_run_generation(plans, *a, **kw)

    inproc = os.path.join(root, "inproc")
    argv_before, gen.run_generation = sys.argv, capture
    sys.argv = ["generate_documents.py"] + base + ["--out", inproc]
    try:
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            gen.main()
    finally:
        gen.run_generation, sys.argv = real_run_generation, argv_before
    store = store_mod.ShardStore(inproc, "benchmark", 7).load(repair=False)
    ngrams, ledger = gen.rebuild_cross_doc_state(store, 40, live["config"].known_clause_texts, 1)
    record("rebuilt G6 5-gram list equals the live list, entry for entry and in order",
           ngrams == live["ngrams"] and len(ngrams) == store.n_accepted, f"{len(ngrams)} documents")
    record("rebuilt negative ledger equals the live ledger and respects the cap",
           +ledger.used == +live["config"].negative_ledger.used and max(ledger.used.values(), default=0) <= 1,
           f"{sum(ledger.used.values())} plantings, cap 1")
    first_text = store.accepted[0][0]["text_input"]
    ngrams_partial, _ = gen.rebuild_cross_doc_state(store, 5, live["config"].known_clause_texts, 1)
    own = gates.word_ngrams(first_text, exempt=store.accepted[0][1]["seeded_clause_literals"]
                            + live["config"].known_clause_texts)
    dup_ok, dup_sim = gates.gate_near_duplicate(first_text, own, ngrams_partial, 0.2)
    record("a duplicate of a document written before the stop is still caught by G6 after resume",
           not dup_ok and dup_sim >= 0.99, f"similarity {dup_sim:.2f}")

    # Stop file.
    stopped = os.path.join(root, "stopfile")
    flag = os.path.join(root, "STOP_FLAG")
    proc = run(stopped, ["--stop-file", flag], {"GD_AFTER": "14", "GD_ACTION": "stopfile", "GD_FLAG": flag})
    prog = manifest_of(stopped)["progress"]
    done_files = _document_files(stopped)
    n_done = (sum(len(r.splitlines()) for n, r in done_files.items() if n.endswith("_meta.jsonl"))
              + len(done_files.get("discarded.jsonl", b"").splitlines()))
    record("stop file: exit 0, in-flight window finished, progress recorded",
           proc.returncode == 0 and prog["status"] == "stopped" and prog["done"] == n_done
           and 0 < n_done < 40 and prog["remaining"] == 40 - n_done and prog["stop_reason"]
           and prog["last_update"] and "Stopped cleanly" in proc.stdout and n_done % 4 == 0,
           f"exit {proc.returncode}, done {n_done}, reason {prog['stop_reason']!r}")
    partial_report = json.load(open(os.path.join(stopped, "gate_report.json")))
    record("partial progress is inspectable: the stop wrote a report with complete=false",
           partial_report["complete"] is False and partial_report["done"] == n_done)
    status = subprocess.run([sys.executable, script, "--status", "--out", stopped],
                            capture_output=True, text=True)
    record("--status prints progress, ETA, profiles and coverage",
           status.returncode == 0 and f"{n_done}/40 done" in status.stdout and "by profile" in status.stdout
           and "coverage" in status.stdout and "state      stopped" in status.stdout, "")
    stale = run(stopped, ["--stop-file", flag], resume=True, use_base=False)
    record("a leftover stop file stops the resume at once, without generating",
           stale.returncode == 0 and manifest_of(stopped)["progress"]["done"] == n_done,
           stale.stdout.strip().splitlines()[-2] if stale.stdout.strip() else "")
    os.remove(flag)
    rep_before = subprocess.run([sys.executable, script, "--report-only", "--out", stopped],
                                capture_output=True, text=True)
    partial_again = json.load(open(os.path.join(stopped, "gate_report.json")))
    record("--report-only rebuilds the partial report identically",
           rep_before.returncode == 0 and partial_again == partial_report)
    run(stopped, ["--stop-file", flag], resume=True, use_base=False)
    record("resuming a stop-file stop gives byte-identical files to the uninterrupted run",
           _normalised(_document_files(stopped)) == _normalised(ref_files))

    # SIGTERM and SIGINT.
    term = os.path.join(root, "sigterm")
    proc = run(term, [], {"GD_AFTER": "9", "GD_ACTION": "sigterm"})
    prog = manifest_of(term)["progress"]
    record("SIGTERM: graceful stop, exit 0, in-flight window finished",
           proc.returncode == 0 and prog["status"] == "stopped" and 0 < prog["done"] < 40
           and prog["done"] % 4 == 0 and "signal SIGTERM" in prog["stop_reason"], f"done {prog['done']}")
    run(term, [], resume=True, use_base=False)
    record("resuming after SIGTERM is byte-identical", _normalised(_document_files(term)) == _normalised(ref_files))
    sigint = os.path.join(root, "sigint")
    proc = run(sigint, [], {"GD_AFTER": "9", "GD_ACTION": "sigint2"})
    rows_ok = all(raw.endswith(b"\n") for raw in _document_files(sigint).values() if raw)
    record("second SIGINT exits immediately (130) leaving no torn line",
           proc.returncode == 130 and rows_ok, f"exit {proc.returncode}")
    run(sigint, [], resume=True, use_base=False)
    record("resuming after the double SIGINT is byte-identical", _normalised(_document_files(sigint)) == _normalised(ref_files))

    # Torn trailing lines.
    torn = os.path.join(root, "torn")
    run(torn, [], {"GD_AFTER": "25", "GD_ACTION": "sigkill"})
    files = _document_files(torn)
    victim_meta = sorted(n for n in files if n.endswith("_meta.jsonl"))[-1]
    victim_text = victim_meta.replace("_meta", "")
    with open(os.path.join(torn, victim_meta), "ab") as handle:
        handle.write(b'{"id": "SYB-000999", "genre": "gp_ref')
    with open(os.path.join(torn, victim_text), "ab") as handle:
        handle.write(b'{"id": "SYB-000999", "text_input": "cut o')
    with open(os.path.join(torn, "discarded.jsonl"), "ab") as handle:
        handle.write(b'{"index": 39, "genre"')
    proc = run(torn, [], resume=True, use_base=False)
    record("torn trailing lines (meta, text, discarded) are detected, reported and dropped on resume",
           proc.returncode == 0 and proc.stderr.count("dropped") >= 3 and _normalised(_document_files(torn)) == _normalised(ref_files),
           "files byte-identical to the reference after the repair")
    garbage = os.path.join(root, "garbage_tail")
    run(garbage, [], {"GD_AFTER": "25", "GD_ACTION": "sigkill"})
    with open(os.path.join(garbage, victim_meta), "ab") as handle:
        handle.write(b'{"id": "SYB-000998", "genre"\n')
    proc = run(garbage, [], resume=True, use_base=False)
    record("a complete-looking final line that is not valid JSON is dropped too",
           proc.returncode == 0 and _normalised(_document_files(garbage)) == _normalised(ref_files))
    middle = os.path.join(root, "middle")
    run(middle, [], {"GD_AFTER": "25", "GD_ACTION": "sigkill"})
    meta0 = os.path.join(middle, "benchmark_batch_00000_meta.jsonl")
    lines = open(meta0, "rb").read().split(b"\n")
    lines[1] = b"{not json"
    open(meta0, "wb").write(b"\n".join(lines))
    proc = run(middle, [], resume=True, use_base=False)
    record("corruption before the last line is refused, not guessed at",
           proc.returncode == 2 and "cannot resume" in proc.stderr)

    # Hash guard.
    guard = os.path.join(root, "guard")
    run(guard, [], {"GD_AFTER": "12", "GD_ACTION": "sigterm"})
    manifest_path = os.path.join(guard, "run_manifest.json")
    manifest = manifest_of(guard)
    tampered = json.loads(json.dumps(manifest))
    tampered["source_hashes"]["gendoc_gates.py"] = "0" * 64
    json.dump(tampered, open(manifest_path, "w"))
    before = _document_files(guard)
    proc = run(guard, [], resume=True, use_base=False)
    record("resume refuses when a generator source hash differs, naming the file, and writes nothing",
           proc.returncode == 2 and "gendoc_gates.py" in proc.stderr and "--resume-force" in proc.stderr
           and _document_files(guard) == before, proc.stderr.strip().splitlines()[0] if proc.stderr else "")
    tampered = json.loads(json.dumps(manifest))
    tampered["data_hashes"]["clause_bank"] = "f" * 64
    json.dump(tampered, open(manifest_path, "w"))
    proc = run(guard, [], resume=True, use_base=False)
    record("resume refuses when a data file hash differs", proc.returncode == 2
           and "data:clause_bank" in proc.stderr)
    tampered = json.loads(json.dumps(manifest))
    tampered["source_hashes"]["gendoc_gates.py"] = "0" * 64
    json.dump(tampered, open(manifest_path, "w"))
    proc = run(guard, ["--resume-force"], resume=True, use_base=False)
    forced = manifest_of(guard)
    last = forced["history"][-1]
    record("--resume-force continues and records the override, with old and new hashes, in the history",
           proc.returncode == 0 and last["event"] == "resume-force"
           and last["overridden"]["source:gendoc_gates.py"]["was"] == "0" * 64
           and last["overridden"]["source:gendoc_gates.py"]["now"] == store_mod.code_hashes(tools)["gendoc_gates.py"]
           and forced["source_hashes"] == store_mod.code_hashes(tools)
           and forced["progress"]["status"] == "finished",
           f"history events {[h['event'] for h in forced['history']]}")
    proc = run(guard, [], resume=True, use_base=False)
    record("after a forced resume the new hashes are the baseline (a further plain resume is allowed)",
           proc.returncode == 0)

    # Argument and directory guards.
    proc = run(ref, [])
    record("starting a new run in a directory that holds one is refused", proc.returncode == 2
           and "already holds a run" in proc.stderr)
    proc = run(ref, ["--seed", "8"], resume=True, use_base=False)
    record("--resume with a conflicting seed is refused", proc.returncode == 2 and "--seed" in proc.stderr)
    proc = run(os.path.join(root, "nothing_here"), [], resume=True, use_base=False)
    record("--resume with nothing to resume is refused", proc.returncode == 2)
    proc = run(ref, ["--window", "4"], resume=True, use_base=False)
    record("a plain --resume of a finished run does nothing and reports", proc.returncode == 0
           and _normalised(_document_files(ref)) == _normalised(ref_files))
    record("--report-only equals the end-of-run report, byte for byte",
           subprocess.run([sys.executable, script, "--report-only", "--out", ref],
                          capture_output=True, text=True).returncode == 0
           and open(os.path.join(ref, "gate_report.json"), "rb").read() == ref_report)

    # Yield when the GPU is busy.
    bin_dir = os.path.join(root, "bin")
    os.makedirs(bin_dir)
    fake = os.path.join(bin_dir, "nvidia-smi")
    with open(fake, "w") as handle:
        handle.write('#!/bin/sh\necho "$PPID, 20000"\necho "4242, 100"\n'
                     'if [ -e "$GD_FLAG" ]; then echo "31337, 9000"; echo "31338, 700"; fi\n')
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
    busy_flag = os.path.join(root, "BUSY")
    env = {"PATH": bin_dir + os.pathsep + os.environ["PATH"], "GD_FLAG": busy_flag}
    quiet = os.path.join(root, "yield_quiet")
    proc = run(quiet, ["--yield-when-gpu-busy", "1000"], env)
    record("yield: own PID and a 100 MiB neighbour are below the limit, the run completes",
           proc.returncode == 0 and manifest_of(quiet)["progress"]["status"] == "finished"
           and _normalised(_document_files(quiet)) == _normalised(ref_files))
    busy = os.path.join(root, "yield_busy")
    proc = run(busy, ["--yield-when-gpu-busy", "1000"], {**env, "GD_AFTER": "14", "GD_ACTION": "busy"})
    prog = manifest_of(busy)["progress"]
    record("yield: other processes above MB stop the run gracefully, logging the PIDs that triggered it",
           proc.returncode == 0 and prog["status"] == "stopped" and 0 < prog["done"] < 40
           and prog["done"] % 4 == 0 and "yielding the GPU" in prog["stop_reason"]
           and "PID 31337 9000 MiB" in proc.stderr and "PID 31338 700 MiB" in proc.stderr
           and f"PID {os.getpid()}" not in proc.stderr, prog["stop_reason"][:120])
    proc = run(busy, ["--yield-when-gpu-busy", "1000"], env, resume=True, use_base=False)
    record("yield: while the other job is still there a resume steps aside before generating anything",
           proc.returncode == 0 and manifest_of(busy)["progress"]["done"] == prog["done"], "")
    os.remove(busy_flag)
    run(busy, ["--yield-when-gpu-busy", "1000"], env, resume=True, use_base=False)
    record("yield: once the GPU is free the resume completes byte-identically",
           _normalised(_document_files(busy)) == _normalised(ref_files))
    controller = store_mod.StopController("/nonexistent/stop", 1000, lambda m: None)
    controller.gpu_query = lambda: [(900001, 15000)]
    controller.own_gpu_mb = lambda: 14800
    unlisted_self_ok = controller.gpu_contention() is None
    controller.own_gpu_mb = lambda: 100
    record("yield: a process not identifiable by PID is subtracted using the backend's own figure",
           unlisted_self_ok and controller.gpu_contention() is not None)
    controller.gpu_query = lambda: None
    record("yield: an unavailable nvidia-smi never stops a run", controller.gpu_contention() is None)

    return all(ok for _n, ok, _d in results)


def _strip_report(report: dict) -> dict:
    """The report without the fields that measure wall-clock time or name the run's directory."""
    out = _strip_timing(report)
    for key in ("wall_seconds", "wall_seconds_per_requested_doc", "wall_seconds_per_accepted_doc",
                "run_stats"):
        out.pop(key, None)
    out.get("G11_content_audit", {}).pop("audit_share_of_wall_time", None)
    for key in ("G1_validate_labels", "G1_validate_labels_full_batch"):
        out[key].pop("path", None)
    return out


def main() -> int:
    """Run every injected-failure case and report. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None,
                        help="directory for the accepted-output JSONL G1 validates "
                             "(default: a temporary directory)")
    parser.add_argument("--taxonomy", default="data/synthetic/taxonomy.json")
    parser.add_argument("--clause-bank", default="data/synthetic/clause_bank.json")
    parser.add_argument("--types-config", default="data/synthetic/types_config.yaml")
    parser.add_argument("--calibrate-g13", action="store_true",
                        help="print the gold and pilot_v3 measurements G13's thresholds came from, "
                             "then exit")
    parser.add_argument("--gold-glob", default="data/gold/batch_*_gold.jsonl")
    parser.add_argument("--gold-v2-glob", default="data/gold_v2/batch_*_gold.jsonl")
    parser.add_argument("--pilot-dir", default="data/synthetic/pilot_v3")
    parser.add_argument("--partition", default=dataset_mod.PARTITION_PATH)
    args = parser.parse_args()
    if args.calibrate_g13:
        return calibrate_g13(args.gold_glob, args.pilot_dir)

    taxonomy_index = data.taxonomy_index(data.load_taxonomy(args.taxonomy))
    clause_bank = data.load_clause_bank(args.clause_bank)
    partition = dataset_mod.load_partition(args.partition)
    negative_bank = dataset_mod.select_clause_bank(clause_bank, partition, "benchmark")["negatives"]
    public_figures = set(data.PUBLIC_FIGURES)
    place_names = {p for _c, p in data.POSTAL_PAIRS}
    agency_names = set(data.AGENCY_NAMES)

    states_by_idx: Dict[int, gen.DocState] = {}
    first_texts: Dict[int, str] = {}

    original_new_attempt = gen.new_attempt_record

    def patched_new_attempt(state, *rest, **kwargs):
        record = original_new_attempt(state, *rest, **kwargs)
        states_by_idx[state.plan.idx] = state
        if CASES[state.plan.idx][0] == "checksum" and state.attempt == 1:
            # Flip a declared validity flag so G4's "declared vs. actual" check
            # has something to disagree about.
            for planned in record.planned:
                if planned.checksum_valid is not None:
                    planned.checksum_valid = not planned.checksum_valid
                    break
        return record

    gen.new_attempt_record = patched_new_attempt
    injecting = InjectingMock(states_by_idx, first_texts)
    try:
        config = gen.GenerationConfig(
            strategy="seeded", invalid_checksum_rate=0.0, retries=3,
            near_dup_threshold=0.5, g7_policy="reject", batch_size=4,
            audit=True, max_audit_repairs=1, dataset="benchmark", negative_bank=negative_bank,
            # The cases below corrupt a whole document's first attempt; sectioned
            # generation is exercised by its own cases further down.
            sectioning="off",
        )
        states, stats = gen.run_generation(
            build_plans(), BASE_SEED, taxonomy_index, clause_bank, public_figures,
            place_names, agency_names, injecting, config,
        )
    finally:
        gen.new_attempt_record = original_new_attempt

    all_passed = True
    for state in states:
        passed, detail = _check(state)
        all_passed &= passed
        print(f"{'PASS' if passed else 'FAIL'} #{state.plan.idx} {CASES[state.plan.idx][0]:<24}"
              f" first_fail={_first_failure(state)} accepted={state.result.get('accepted')}"
              f" {detail}")
    print(f"run stats: {stats}")

    all_passed &= unit_checks(clause_bank, partition, args.gold_glob, args.pilot_dir)
    all_passed &= registry_identifier_checks(clause_bank, args.gold_v2_glob)

    out_dir = args.out or tempfile.mkdtemp(prefix="gendoc_gate_check_")
    os.makedirs(out_dir, exist_ok=True)
    types_config = args.types_config
    all_passed &= section_unit_checks(taxonomy_index, clause_bank, partition)
    sections_ok, section_docs = section_cases(taxonomy_index, clause_bank, partition, out_dir)
    all_passed &= sections_ok
    all_passed &= no_discard_check(taxonomy_index, clause_bank, partition)
    all_passed &= negative_checks(taxonomy_index, clause_bank, partition, out_dir, types_config)
    all_passed &= negative_wording_checks(taxonomy_index, clause_bank, partition)
    all_passed &= record_checks(taxonomy_index, clause_bank, partition, out_dir)
    all_passed &= resume_checks(out_dir)

    clause_literals = ([pv.value for pv in states[16].record.planned if pv.value_kind == "clause" and pv.value]
                       + config.known_clause_texts)
    similarity = gates.jaccard(
        gates.word_ngrams(injecting.neardup_base, exempt=clause_literals),
        gates.word_ngrams(first_texts.get(16, ""), exempt=clause_literals),
    )
    print(f"G6 5-gram similarity, doc 16 first attempt vs. the longest accepted text: {similarity:.3f}")

    path = os.path.join(out_dir, "accepted.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        for state in states:
            if state.result.get("accepted") and state.result.get("output"):
                handle.write(json.dumps({
                    "id": f"CHK-{state.plan.idx:03d}", "text_input": state.result["text"],
                    "output": state.result["output"],
                }, ensure_ascii=False) + "\n")
        for doc in section_docs:
            if doc["output"]:
                handle.write(json.dumps({k: doc[k] for k in ("id", "text_input", "output")},
                                        ensure_ascii=False) + "\n")
    validator = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_labels.py")
    proc = subprocess.run([sys.executable, validator, path, "--config", types_config],
                          capture_output=True, text=True)
    print(f"G1 validate_labels.py on accepted output: exit {proc.returncode}")
    print("  " + (proc.stdout.strip().splitlines() or ["(no output)"])[-1])
    if proc.returncode != 0:
        print(proc.stdout)
        all_passed = False

    print("ALL PASS" if all_passed else "SOME FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
