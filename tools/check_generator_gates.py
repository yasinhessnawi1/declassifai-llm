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
import glob
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
import gendoc_data as data  # noqa: E402
import gendoc_dataset as dataset_mod  # noqa: E402
import gendoc_gates as gates  # noqa: E402
import generate_documents as gen  # noqa: E402
from gendoc_backends import (  # noqa: E402
    MANIFEST_SENTINEL, MOCK_ELABORATION_CUE, MOCK_FRAMING_CUE, MockBackend,
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
}

# Cases that plan hard negatives, as the benchmark does. They need a plan with
# `n_negatives` and a run config carrying a negative bank.
_NEGATIVE_CASES = {30, 31, 32}

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
}

# Types a case forces into its record so the injection has a planned value to work on.
_FORCED_FOR = {35: ["FIREARMS_LICENSE"], 36: ["FIREARMS_LICENSE"], 37: ["VESSEL_REGISTRATION"],
               38: ["VESSEL_REGISTRATION"], 39: ["FIREARMS_LICENSE"], 40: ["VESSEL_REGISTRATION"]}
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
                text = "\n".join(f"FUNN|SENSITIV|{neg.text}" for neg in negatives)
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
        if name == "negative_elaboration":
            negative = self.states[idx].record.planted_negatives[0].text
            return text + f" Det ble notert at vedkommende {negative} {MOCK_ELABORATION_CUE}.", True
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
        if name == "neardup" and self.states[0].result and self.states[0].result.get("text"):
            # Doc 0's accepted text plus doc 16's own literals on one line: every
            # planned value is present, so only G6 can reject it.
            return (self.states[0].result["text"] + "\n"
                    + " og ".join(_values(prompt) + clauses) + "."), True
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
        plans.append(gen.DocPlan(
            n_negatives=2 if idx in _NEGATIVE_CASES else 0,
            idx=idx, genre=genre, variant="prose_letter", form="nb",
            length_band=(800, 1600) if pii_free else (1600, 2800),
            forced_types=forced, profile="pii_free" if pii_free else "typical",
            type_target=0 if pii_free else (14 if idx in (26, 28) else 8), art9_cap=1,
            pii_free=pii_free,
        ))
    return plans


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
        verbatim = all(t in result.get("text", "") for t in texts)
        unlabelled = not any(t in sp or sp in t for t in texts for sp in spans
                             if sp not in allowed and len(sp) >= 4)
        base = accepted and bool(negatives) and verbatim and unlabelled
        if name == "negative_planted":
            return base, f"negatives={texts} verbatim={verbatim} unlabelled={unlabelled}"
        kept = sum(entry["kept"] for entry in state.audit_log)
        overruled = sum(entry.get("exempt_negative_quotes", 0) for entry in state.audit_log)
        if name == "negative_survives_audit":
            return (base and kept == 0 and overruled >= 1 and state.audit_repairs_total == 0), \
                f"kept={kept} overruled={overruled} audit_repairs={state.audit_repairs_total}"
        return (base and state.audit_repairs_total == 1 and MOCK_ELABORATION_CUE not in result["text"]), \
            f"audit_repairs={state.audit_repairs_total} cue_removed={MOCK_ELABORATION_CUE not in result['text']}"
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
    try:
        config = gen.GenerationConfig(
            strategy="seeded", invalid_checksum_rate=0.0, retries=3,
            near_dup_threshold=0.5, g7_policy="reject", batch_size=4,
            audit=True, max_audit_repairs=1, dataset="benchmark", negative_bank=negative_bank,
        )
        states, stats = gen.run_generation(
            build_plans(), BASE_SEED, taxonomy_index, clause_bank, public_figures,
            place_names, agency_names, InjectingMock(states_by_idx, first_texts), config,
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

    similarity = gates.jaccard(
        gates.word_ngrams(states[0].result.get("text", "")),
        gates.word_ngrams(first_texts.get(16, "")),
    )
    print(f"G6 5-gram similarity, doc 16 first attempt vs. doc 0: {similarity:.3f}")

    out_dir = args.out or tempfile.mkdtemp(prefix="gendoc_gate_check_")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "accepted.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        for state in states:
            if state.result.get("accepted") and state.result.get("output"):
                handle.write(json.dumps({
                    "id": f"CHK-{state.plan.idx:03d}", "text_input": state.result["text"],
                    "output": state.result["output"],
                }, ensure_ascii=False) + "\n")
    validator = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_labels.py")
    proc = subprocess.run([sys.executable, validator, path, "--config", args.types_config],
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
