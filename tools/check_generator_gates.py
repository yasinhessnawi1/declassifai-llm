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

Run it from the repository root; it exits non-zero if any case fails or if
`tools/validate_labels.py` reports a violation on what the run accepted:

    python3 tools/check_generator_gates.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_data as data  # noqa: E402
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
}

# Which genre and plan shape each case needs. The slot-label cases need a
# document with a seeded judgement clause; the checksum case needs a genre whose
# values include an identifier with a real checksum; the PII-free cases need the
# one genre that may carry no data subject.
_GENRE_FOR = {
    5: "gp_referral", 6: "gp_referral", 12: "gp_referral", 15: "nav_decision",
    18: "gp_referral", 19: "police_report", 20: "nav_decision", 21: "gp_referral",
    22: "admin_circular", 23: "admin_circular", 24: "nav_decision",
    25: "gp_referral",
}
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
        forced = ["HEALTH"] if idx in (5, 6, 18, 21, 25) else []
        plans.append(gen.DocPlan(
            idx=idx, genre=genre, variant="prose_letter", form="nb",
            length_band=(800, 1600) if pii_free else (1600, 2800),
            forced_types=forced, profile="pii_free" if pii_free else "typical",
            type_target=0 if pii_free else 8, art9_cap=1, pii_free=pii_free,
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
    args = parser.parse_args()

    taxonomy_index = data.taxonomy_index(data.load_taxonomy(args.taxonomy))
    clause_bank = data.load_clause_bank(args.clause_bank)
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
            audit=True, max_audit_repairs=1,
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
