"""Generate synthetic Norwegian PII documents with labels correct by construction.

The core idea, from `docs/SYNTHETIC_DATA_SPEC.md` Section 6 and
`docs/PROJECT_SPEC_V2.md` Section 3: sample a typed record first (people,
identifiers, clauses), ask a language model to *realise* that record as a
document in a given genre, then locate every planted value in the output by
exact substring search. The label is never guessed -- it is either found
verbatim or the document is discarded. What that guarantees and what it does
not is precise: every emitted span is real and correctly typed, but the model
can still (a) invent PII that was never planted, unlabelled, or (b) always put
PII in the same slot, teaching position instead of language. Both failure
modes get their own gate (G7 and the placement randomisation in the prompt
builder, checked indirectly by G6) rather than being left to hope.

Pipeline per document:

    sample_record -> build_prompt -> backend.generate -> strip_markers
        -> locate spans (labeller) -> gates G2-G4, G6, G7 -> accept or retry

then, over the whole accepted batch: G1 (schema validation via
`tools/validate_labels.py`), G5 (genre/form/length distribution vs the plan)
and G8 (a human-readable sample dump).

Usage:
    python3 tools/generate_documents.py --backend mock --n 50 \\
        --genres gp_referral,police_report,nav_decision,dismissal_letter,udi_decision \\
        --strategy seeded --seed 1 --out data/synthetic/pilot/
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_data as data
import gendoc_gates as gates
import gendoc_genres as genres_mod
import gendoc_identifiers as ident
from gendoc_backends import build_backend
from validate_labels import load_types as validate_labels_load_types  # noqa: E402

MARKER_RE = re.compile(r"⟦([A-Z_]+):\s*(.*?)⟧", re.DOTALL)


# ---------------------------------------------------------------------------
# Record sampling
# ---------------------------------------------------------------------------

@dataclass
class Person:
    """A sampled (never real) Norwegian person."""

    first_name: str
    last_name: str
    gender: str  # "M" or "F"
    birth_date: date

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class PlannedValue:
    """One value or clause the record requires the document to contain."""

    type: str
    tier: str
    value_kind: str  # "value" or "clause"
    value: Optional[str]  # literal text for value_kind=value or strategy=seeded
    strategy: Optional[str]  # None, "seeded" or "marked"
    field_label: str
    checksum_valid: Optional[bool] = None
    difficulty: Optional[str] = None


@dataclass
class Record:
    """A fully sampled, typed record for one document."""

    doc_seed: int
    genre: str
    variant: str
    form: str  # "nb" or "nn"
    length_band: Tuple[int, int]
    person: Person
    other_people: List[Person]
    planned: List[PlannedValue]


def sample_person(rng: random.Random, min_age: int = 18, max_age: int = 85,
                   today: date = date(2026, 9, 26)) -> Person:
    """Sample a person from the embedded name lists, never a real public figure.

    Args:
        rng: Seeded RNG.
        min_age: Minimum age in years as of `today`.
        max_age: Maximum age in years as of `today`.
        today: Reference date for computing the birth date from an age.

    Returns:
        A `Person`. Callers must still run G3 before shipping any document.
    """
    gender = rng.choice(["M", "F"])
    first = rng.choice(data.FIRST_NAMES_MALE if gender == "M" else data.FIRST_NAMES_FEMALE)
    last = rng.choice(data.SURNAMES)
    age = rng.randint(min_age, max_age)
    birth_year = today.year - age
    birth = date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
    return Person(first, last, gender, birth)


def _resample_until_no_collision(rng: random.Random, public_figures: Set[str]) -> Person:
    for _ in range(50):
        person = sample_person(rng)
        if person.full_name not in public_figures:
            return person
    raise RuntimeError("could not sample a non-colliding person after 50 attempts")


def _format_date(rng: random.Random, d: date) -> str:
    styles = [
        lambda d: f"{d.day:02d}.{d.month:02d}.{d.year}",
        lambda d: f"{d.day}. {_MONTHS_NB[d.month - 1]} {d.year}",
    ]
    return rng.choice(styles)(d)


_MONTHS_NB = [
    "januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
    "september", "oktober", "november", "desember",
]

_NATIONALITIES = [
    "norsk", "svensk", "dansk", "somalisk", "syrisk", "polsk", "litauisk",
    "eritreisk", "afghansk", "irakisk", "ukrainsk", "eritreisk", "iransk",
]
_MARITAL = ["gift", "ugift", "skilt", "samboer", "enke", "enkemann"]


def _address(rng: random.Random) -> Tuple[str, str, str]:
    """Return (full_address_with_postal, postal_code, place)."""
    street = rng.choice(data.STREET_NAMES)
    number = rng.randint(1, 180)
    suffix = rng.choice(["", "", "", "A", "B", "C"])
    postal, place = rng.choice(data.POSTAL_PAIRS)
    return f"{street} {number}{suffix}, {postal} {place}", postal, place


def _organization_name(rng: random.Random, person: Person) -> str:
    suffix = rng.choice(["AS", "ASA", "Gruppen AS", "Holding AS", "Entreprenør AS"])
    business = rng.choice(["Transport", "Bygg", "Consulting", "Handel", "Service"])
    return f"{person.last_name} {business} {suffix}"


def _generate_value_kind(
    etype: str, rng: random.Random, person: Person, invalid_rate: float,
) -> Tuple[str, Optional[bool]]:
    """Generate a Tier A / Tier B "value" kind value. Returns (text, checksum_valid)."""
    make_invalid = rng.random() < invalid_rate
    valid = not make_invalid

    if etype == "NATIONAL_ID":
        dnummer = rng.random() < 0.1
        idf = ident.fodselsnummer(rng, person.birth_date, person.gender, valid=valid, dnummer=dnummer)
        return idf.value, idf.valid
    if etype == "DATE_OF_BIRTH":
        return _format_date(rng, person.birth_date), None
    if etype == "ORG_NUMBER":
        idf = ident.org_number(rng, valid=valid)
        return idf.value, idf.valid
    if etype == "BANK_ACCOUNT":
        idf = ident.bank_account(rng, valid=valid)
        return idf.value, idf.valid
    if etype == "IBAN":
        idf = ident.bank_account(rng, valid=valid)
        return ident.iban_no(idf.value), idf.valid
    if etype == "CREDIT_CARD":
        idf = ident.credit_card(rng, valid=valid)
        return idf.value, idf.valid
    if etype == "PHONE":
        return ident.phone_number(rng, mobile=True), None
    if etype == "FAX_NUMBER":
        return ident.phone_number(rng, mobile=False), None
    if etype == "EMAIL":
        return ident.email_address(rng, person.first_name, person.last_name), None
    if etype == "URL":
        return ident.url(rng), None
    if etype == "IP_ADDRESS":
        return ident.ip_address(rng), None
    if etype == "USERNAME":
        return ident.username(rng, person.first_name, person.last_name), None
    if etype == "SOCIAL_MEDIA":
        return ident.social_media_handle(rng, person.first_name, person.last_name), None
    if etype == "CASE_NUMBER":
        return ident.case_number(rng), None
    if etype == "PASSPORT":
        return ident.passport_number(rng), None
    if etype == "DRIVER_LICENSE":
        return ident.driver_license_number(rng), None
    if etype == "IDENTITY_CARD":
        return ident.identity_card_number(rng), None
    if etype == "VISA_NUMBER":
        return ident.visa_number(rng), None
    if etype == "MILITARY_ID":
        return ident.military_id(rng), None
    if etype == "MEDICAL_LICENSE":
        return ident.medical_license_number(rng), None
    if etype == "INSURANCE_NUMBER":
        return ident.insurance_number(rng), None
    if etype == "TAX_ID":
        return ident.tax_id(rng), None
    if etype == "STUDENT_ID":
        return ident.student_id(rng), None
    if etype == "DEVICE_ID":
        return ident.device_id(rng), None
    if etype == "CRYPTO":
        return ident.crypto_address(rng), None
    if etype == "PASSWORD":
        return ident.password_value(rng), None
    if etype == "LICENSE_PLATE":
        return ident.vehicle_reg(rng), None
    if etype == "POSTAL_CODE":
        postal, _place = rng.choice(data.POSTAL_PAIRS)
        return postal, None
    if etype == "ADDRESS":
        full, _postal, _place = _address(rng)
        return full, None
    if etype == "AGE":
        age = date(2026, 9, 26).year - person.birth_date.year
        return str(age), None
    if etype == "GENDER":
        return ("mann" if person.gender == "M" else "kvinne"), None
    if etype == "MARITAL_STATUS":
        return rng.choice(_MARITAL), None
    if etype == "NATIONALITY":
        return rng.choice(_NATIONALITIES), None
    if etype == "LOCATION":
        _postal, place = rng.choice(data.POSTAL_PAIRS)
        return place, None
    if etype == "ORGANIZATION":
        return _organization_name(rng, person), None
    if etype == "DATE_TIME":
        offset = rng.randint(-900, 30)
        return _format_date(rng, date(2026, 9, 26) + timedelta(days=offset)), None
    if etype == "ANIMAL_INFO":
        animal = rng.choice(["hund", "katt", "hest", "sau", "gris", "høne"])
        count = rng.randint(1, 6)
        return f"{count} {animal}(er) holdt på eiendommen", None
    if etype == "IDENTIFIABLE_IMAGE":
        return rng.choice([
            "bilde av vedkommende fra overvåkningskamera",
            "fotografi tatt på stedet som viser vedkommendes ansikt",
        ]), None
    raise KeyError(etype)


_VALUE_KIND_TYPES = {
    "NATIONAL_ID", "DATE_OF_BIRTH", "ORG_NUMBER", "BANK_ACCOUNT", "IBAN",
    "CREDIT_CARD", "PHONE", "FAX_NUMBER", "EMAIL", "URL", "IP_ADDRESS",
    "USERNAME", "SOCIAL_MEDIA", "CASE_NUMBER", "PASSPORT", "DRIVER_LICENSE",
    "IDENTITY_CARD", "VISA_NUMBER", "MILITARY_ID", "MEDICAL_LICENSE",
    "INSURANCE_NUMBER", "TAX_ID", "STUDENT_ID", "DEVICE_ID", "CRYPTO",
    "PASSWORD", "LICENSE_PLATE", "POSTAL_CODE", "ADDRESS", "AGE", "GENDER",
    "MARITAL_STATUS", "NATIONALITY", "LOCATION", "ORGANIZATION", "DATE_TIME",
    "ANIMAL_INFO", "IDENTIFIABLE_IMAGE",
}

# Clause-bank entries occasionally embed a bare personal name (e.g. CRIMINAL's
# "politianmeldelse mot Olsen for trusler ..." or SEXUAL_ORIENTATION's
# "homofilt forhold til Lars Olsen") that is fixed text, unrelated to the
# record's own sampled people. Left as-is, the same name would recur
# identically across every document that draws that clause entry, and the name
# would not be registered as its own PERSON span even though it names someone.
# The clause bank writes embedded names as placeholders rather than literal
# names, so each document gets a fresh, gender-consistent name and the caller
# knows exactly which characters to register as a nested PERSON span.
# `{SURNAME_FAM}` (Familien X) and `{SURNAME_ORG}` (X Sjømat AS) are filled
# with a surname but never tagged PERSON, per the FAMILY_RELATION overlap
# policy in docs/ANNOTATION_SPEC.md.
_CLAUSE_PLACEHOLDER_RE = re.compile(r"\{(PERSON|PERSON_M|PERSON_F|SURNAME_FAM|SURNAME_ORG)\}")


def localize_clause_names(
    rng: random.Random, text: str, public_figures: Set[str],
) -> Tuple[str, List[str]]:
    """Fill the name placeholders of a clause-bank entry with fresh names.

    Args:
        rng: Seeded RNG.
        text: The clause text as drawn from the clause bank.
        public_figures: Embedded public-figure set, to avoid an unlucky collision.

    Returns:
        Tuple of (filled text, list of the full names substituted in, so the
        caller can register them as their own PERSON spans).
    """
    introduced: List[str] = []

    def _fresh_full(kind: str) -> str:
        male = kind == "PERSON_M" or (kind == "PERSON" and rng.random() < 0.5)
        for _ in range(20):
            first = rng.choice(data.FIRST_NAMES_MALE if male else data.FIRST_NAMES_FEMALE)
            full = f"{first} {rng.choice(data.SURNAMES)}"
            if full not in public_figures:
                break
        return full

    def _sub(m: "re.Match") -> str:
        kind = m.group(1)
        if kind.startswith("SURNAME"):
            return rng.choice(data.SURNAMES)
        full = _fresh_full(kind)
        introduced.append(full)
        return full

    return _CLAUSE_PLACEHOLDER_RE.sub(_sub, text), introduced


def sample_record(
    rng: random.Random, doc_seed: int, genre: str, variant: str, form: str,
    length_band: Tuple[int, int], strategy: str, taxonomy_index: Dict[str, dict],
    clause_bank: dict, public_figures: Set[str], forced_types: List[str],
) -> Record:
    """Sample a typed record for one document.

    Args:
        rng: Seeded RNG for this attempt.
        doc_seed: The seed used to build this rng, recorded for reproducibility.
        genre: Genre id from `gendoc_genres.GENRES`.
        variant: Structural variant name.
        form: "nb" or "nn".
        length_band: (min_chars, max_chars) target.
        strategy: "seeded" or "marked", applied to every clause-kind type.
        taxonomy_index: Type name -> taxonomy entry.
        clause_bank: Loaded clause bank dict.
        public_figures: Embedded set of real public figures, to reject collisions.
        forced_types: Extra types to force into this record regardless of genre plan.

    Returns:
        A `Record` with `planned` fully populated.
    """
    genre_spec = genres_mod.GENRES[genre]
    person = _resample_until_no_collision(rng, public_figures)
    other_people = [
        _resample_until_no_collision(rng, public_figures)
        for _ in range(rng.randint(0, 2))
    ]

    chosen_types = list(genre_spec["mandatory"])
    for etype in genre_spec["optional"]:
        if rng.random() < 0.5:
            chosen_types.append(etype)
    rare_pool = [t for t in genre_spec.get("rare", []) if t not in chosen_types]
    if rare_pool:
        chosen_types.extend(rng.sample(rare_pool, k=min(len(rare_pool), rng.randint(1, 2))))
    for etype in forced_types:
        if etype not in chosen_types:
            chosen_types.append(etype)

    planned: List[PlannedValue] = []
    for etype in chosen_types:
        entry = taxonomy_index.get(etype)
        if entry is None:
            continue
        field_label = genres_mod.FIELD_LABELS.get(etype, etype)
        value_kind = entry.get("value_kind", "value")

        if etype == "PERSON":
            target = rng.choice([person] + other_people) if other_people else person
            planned.append(PlannedValue(etype, entry["tier"], "value", target.full_name, None, field_label))
            continue

        if value_kind == "value" or etype in _VALUE_KIND_TYPES:
            try:
                value, checksum_valid = _generate_value_kind(etype, rng, person, invalid_rate=0.0)
            except KeyError:
                # The taxonomy called this type "value" kind but it is not one of
                # the identifier/attribute generators above (e.g. ANIMAL_INFO,
                # IDENTIFIABLE_IMAGE, or a type added to the real taxonomy after
                # this dispatch table was written). Fall back to the clause bank
                # for a short literal phrase rather than silently dropping the
                # type -- coverage over exactness, since it is still a real,
                # locatable string either way.
                bank_candidates = clause_bank.get(etype, [])
                if bank_candidates:
                    value = rng.choice(bank_candidates)["text"]
                else:
                    value = f"forhold knyttet til {etype.replace('_', ' ').lower()}"
                checksum_valid = None
            planned.append(PlannedValue(etype, entry["tier"], "value", value, None, field_label, checksum_valid))
            continue

        candidates = clause_bank.get(etype, [])
        matching = [c for c in candidates if c.get("form") == form] or candidates
        if not matching:
            continue
        else:
            chosen = rng.choice(matching)
            text = chosen["text"]
            difficulty = chosen.get("difficulty")

        chosen_strategy = strategy
        if chosen_strategy == "seeded":
            text, introduced_names = localize_clause_names(rng, text, public_figures)
            for name in introduced_names:
                planned.append(PlannedValue("PERSON", "B", "value", name, None, genres_mod.FIELD_LABELS.get("PERSON", "Navn")))

        planned.append(
            PlannedValue(
                etype, entry["tier"], "clause",
                text if chosen_strategy == "seeded" else None,
                chosen_strategy, field_label, difficulty=difficulty,
            )
        )

    return Record(doc_seed, genre, variant, form, length_band, person, other_people, planned)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_GENRE_INSTRUCTIONS_NB = (
    "Du skriver et offisielt norsk dokument av typen '{title}'. "
    "Bruk formen '{variant}': {variant_desc}. "
    "Skriv utelukkende på {form_name}, med korrekt og naturlig register for en norsk "
    "offentlig etat. Dokumentet skal være mellom {min_len} og {max_len} tegn langt."
)
_GENRE_INSTRUCTIONS_NN = (
    "Du skriv eit offisielt norsk dokument av typen '{title}'. "
    "Bruk forma '{variant}': {variant_desc}. "
    "Skriv utelukkande på {form_name}, med korrekt og naturleg register for eit norsk "
    "offentleg organ. Dokumentet skal vere mellom {min_len} og {max_len} teikn langt."
)

_VARIANT_DESC = {
    "field_header": "et skjema med feltoverskrifter etterfulgt av verdier",
    "prose_letter": "et sammenhengende brev med hilsen og løpende prosa",
    "numbered_findings": "en nummerert liste over funn og vurderinger",
    "table_summary": "en tabellaktig oppsummering med korte rader",
    "minutes": "et møtereferat med punkter",
}


def build_prompt(record: Record) -> str:
    """Build the generation prompt: instructions plus a machine-readable value manifest.

    The manifest (`VALUE|...`, `CLAUSE_SEEDED|...`, `CLAUSE_MARKED|...`, `SEED|...`)
    is both the model's explicit list of required values, restated in prose, and
    the input the mock backend parses to fill its template -- the same contract a
    real model reads as an instruction is what the deterministic test backend
    reads as data, so the two stay honest with each other.

    Args:
        record: The sampled record to realise as a document.

    Returns:
        The full prompt string.
    """
    genre_spec = genres_mod.GENRES[record.genre]
    title = genre_spec["title_nb"] if record.form == "nb" else genre_spec["title_nn"]
    template = _GENRE_INSTRUCTIONS_NB if record.form == "nb" else _GENRE_INSTRUCTIONS_NN
    header = template.format(
        title=title, variant=record.variant, variant_desc=_VARIANT_DESC[record.variant],
        form_name="bokmål" if record.form == "nb" else "nynorsk",
        min_len=record.length_band[0], max_len=record.length_band[1],
    )

    value_lines, manifest_lines = [], [f"SEED|{record.doc_seed}", f"META|form={record.form}"]
    for pv in record.planned:
        if pv.value_kind == "value":
            value_lines.append(f"- {pv.field_label} ({pv.type}): {pv.value}")
            manifest_lines.append(f"VALUE|{pv.type}|{pv.value}")
        elif pv.strategy == "seeded":
            value_lines.append(f"- Klausul som MÅ inngå ordrett ({pv.type}): «{pv.value}»")
            manifest_lines.append(f"CLAUSE_SEEDED|{pv.type}|{pv.value}")
        else:
            value_lines.append(
                f"- Skriv en egen setning om {pv.type} og merk den slik: "
                f"⟦{pv.type}: <din setning>⟧"
            )
            manifest_lines.append(f"CLAUSE_MARKED|{pv.type}")

    rules = (
        "Regler:\n"
        "1. ALLE oppgitte verdier og klausuler skal brukes ORDRETT, uten omskriving.\n"
        "2. Ikke bruk plassholdere som [NAVN] eller [DATO].\n"
        "3. Varier hvor verdiene plasseres -- noen i feltoverskrifter, noen midt i løpende tekst, "
        "og noen verdier kan gjentas naturlig flere steder.\n"
        "4. Ikke skriv noe på engelsk.\n"
        "5. For markerte klausuler: skriv ⟦TYPE: setning⟧ nøyaktig én gang per type, "
        "uten andre ⟦ ⟧ tegn i teksten for øvrig.\n"
    )

    prompt = (
        f"{header}\n\n"
        f"Følgende verdier og opplysninger skal inngå i dokumentet:\n"
        + "\n".join(value_lines) + "\n\n" + rules + "\n"
        + "\n".join(manifest_lines)
    )
    return prompt


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------

def strip_markers(text: str, known_types: Set[str]) -> Tuple[str, Dict[str, List[str]], bool, Optional[str]]:
    """Strip `⟦TYPE: text⟧` markers from generated text and collect their spans.

    Args:
        text: Raw generated text, possibly containing marked clauses.
        known_types: Type names considered valid inside a marker.

    Returns:
        Tuple of (clean text with markers removed, {type: [inner texts]},
        whether marker discipline held, an error message if not).
    """
    if text.count("⟦") != text.count("⟧"):
        return text, {}, False, "unbalanced markers"

    spans: Dict[str, List[str]] = collections.defaultdict(list)
    error = None

    def _replace(m: "re.Match") -> str:
        nonlocal error
        etype, inner = m.group(1), m.group(2).strip()
        if etype not in known_types:
            error = f"unknown marked type: {etype}"
        spans[etype].append(inner)
        return inner

    clean = MARKER_RE.sub(_replace, text)
    if "⟦" in clean or "⟧" in clean:
        return text, {}, False, "leftover marker characters"
    return clean, dict(spans), error is None, error


def build_output(record: Record, clean_text: str, marked_spans: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Locate every planned value and marked span in the text by exact substring search.

    Args:
        record: The record whose planned values must be located.
        clean_text: Generated text after marker stripping.
        marked_spans: Type -> inner texts collected from markers.

    Returns:
        `{TYPE: [unique verbatim spans]}` in the same shape as `data/gold/*_gold.jsonl`.
    """
    output: Dict[str, List[str]] = collections.defaultdict(list)
    for pv in record.planned:
        literal = pv.value if pv.value_kind == "value" or pv.strategy == "seeded" else None
        if literal and literal in clean_text and literal not in output[pv.type]:
            output[pv.type].append(literal)
    for etype, spans in marked_spans.items():
        for span in spans:
            if span in clean_text and span not in output[etype]:
                output[etype].append(span)
    # ANNOTATION_SPEC nesting rule: a postal code written inside an address value
    # is tagged POSTAL_CODE as well as being part of the ADDRESS span.
    for address in output.get("ADDRESS", []):
        for code in re.findall(r"(?<!\d)\d{4}(?!\d)", address):
            if code not in output["POSTAL_CODE"]:
                output["POSTAL_CODE"].append(code)
    return {k: v for k, v in output.items() if v}


# ---------------------------------------------------------------------------
# Gate orchestration per document
# ---------------------------------------------------------------------------

_TIER_A_VALIDATORS = {
    "NATIONAL_ID": ident.is_valid_fodselsnummer,
    "ORG_NUMBER": ident.is_valid_org_number,
    "BANK_ACCOUNT": ident.is_valid_bank_account,
    "IBAN": ident.is_valid_iban_no,
    "CREDIT_CARD": ident.is_valid_luhn,
}


def build_tier_a_findings(record: Record) -> List[dict]:
    """Build G4 findings: declared vs. actual checksum validity for Tier A values."""
    findings = []
    for pv in record.planned:
        if pv.tier != "A" or pv.checksum_valid is None:
            continue
        validator = _TIER_A_VALIDATORS.get(pv.type)
        if validator is None:
            continue
        findings.append({
            "type": pv.type, "value": pv.value,
            "declared_valid": pv.checksum_valid, "actual_valid": validator(pv.value),
        })
    return findings


@dataclass
class GenerationConfig:
    """Run-wide configuration threaded through document generation."""

    strategy: str
    invalid_checksum_rate: float
    retries: int
    near_dup_threshold: float
    g7_policy: str  # "reject" or "report"
    max_new_tokens: int = 900


def generate_one_document(
    idx: int, genre: str, variant: str, form: str, length_band: Tuple[int, int],
    base_seed: int, taxonomy_index: Dict[str, dict], clause_bank: dict,
    public_figures: Set[str], place_names: Set[str], agency_names: Set[str],
    backend, config: GenerationConfig, accepted_ngrams: List[Set[Tuple[str, ...]]],
    forced_types: List[str],
) -> dict:
    """Sample, generate, label and gate one document, retrying on hard-gate failure.

    Returns:
        Dict with `accepted` (bool), and on success `record`, `text`, `output`,
        plus `gate_log`: the per-attempt reasons for retry/discard and the final
        gate results.
    """
    gate_log = []
    for attempt in range(1, config.retries + 1):
        doc_seed = base_seed * 100003 + idx * 97 + attempt
        rng = random.Random(doc_seed)

        record = sample_record(
            rng, doc_seed, genre, variant, form, length_band, config.strategy,
            taxonomy_index, clause_bank, public_figures, forced_types,
        )
        for pv in record.planned:
            if pv.tier == "A" and pv.checksum_valid is not None:
                if rng.random() < config.invalid_checksum_rate:
                    _, valid = _generate_value_kind(pv.type, rng, record.person, invalid_rate=1.0)
                    if valid is not None:
                        pv.checksum_valid = valid
                        pv.value, _ = _generate_value_kind(pv.type, random.Random(doc_seed + 1), record.person, invalid_rate=1.0)

        prompt = build_prompt(record)
        raw_text = backend.generate([prompt], max_new_tokens=config.max_new_tokens)[0]

        known_types = set(taxonomy_index)
        clean_text, marked_spans, marker_ok, marker_err = strip_markers(raw_text, known_types)
        if not marker_ok:
            gate_log.append({"attempt": attempt, "stage": "marker", "ok": False, "detail": marker_err})
            continue

        output = build_output(record, clean_text, marked_spans)

        literal_values = [
            pv.value for pv in record.planned
            if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")
        ]
        g2_ok, g2_missing = gates.gate_verbatim(literal_values, clean_text)
        missing_marks = [pv.type for pv in record.planned if pv.strategy == "marked" and pv.type not in marked_spans]
        if not g2_ok or missing_marks:
            gate_log.append({
                "attempt": attempt, "stage": "G2_verbatim", "ok": False,
                "detail": {"missing_values": g2_missing, "missing_marked_types": missing_marks},
            })
            continue

        names_to_check = [record.person.full_name] + [p.full_name for p in record.other_people]
        g3_ok, g3_hits = gates.gate_name_collision(names_to_check, clean_text, public_figures, place_names, agency_names)
        if not g3_ok:
            gate_log.append({"attempt": attempt, "stage": "G3_name_collision", "ok": False, "detail": g3_hits})
            continue

        tier_a_findings = build_tier_a_findings(record)
        g4_ok, g4_bad = gates.gate_identifier_checksums(tier_a_findings)
        if not g4_ok:
            gate_log.append({"attempt": attempt, "stage": "G4_checksum", "ok": False, "detail": g4_bad})
            continue

        ngrams = gates.word_ngrams(clean_text)
        g6_ok, g6_sim = gates.gate_near_duplicate(clean_text, ngrams, accepted_ngrams, config.near_dup_threshold)
        if not g6_ok:
            gate_log.append({"attempt": attempt, "stage": "G6_near_duplicate", "ok": False, "detail": g6_sim})
            continue

        covered = [v for vals in output.values() for v in vals]
        g7_ok, g7_findings = gates.gate_unplanned_pii(clean_text, covered, place_names, agency_names)
        if not g7_ok and config.g7_policy == "reject":
            gate_log.append({"attempt": attempt, "stage": "G7_unplanned_pii", "ok": False, "detail": g7_findings})
            continue

        gate_log.append({
            "attempt": attempt, "stage": "accepted", "ok": True,
            "g7_findings": g7_findings, "g7_policy": config.g7_policy,
        })
        return {
            "accepted": True, "record": record, "text": clean_text, "output": output,
            "gate_log": gate_log, "ngrams": ngrams, "tier_a_findings": tier_a_findings,
        }

    return {"accepted": False, "gate_log": gate_log}


# ---------------------------------------------------------------------------
# Batch-level gates (G1, G5, G8) and CLI
# ---------------------------------------------------------------------------

def run_g1_validate_labels(batch_path: str, types_config_path: str) -> Tuple[bool, str]:
    """Run `tools/validate_labels.py --config` on the output batch and capture the result."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_labels.py")
    proc = subprocess.run(
        [sys.executable, script, batch_path, "--config", types_config_path],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def gate_g5_distribution(accepted_meta: List[dict], requested_genres: List[str]) -> dict:
    """Compare realised genre/form/length distribution against the plan."""
    genre_counts = collections.Counter(m["genre"] for m in accepted_meta)
    form_counts = collections.Counter(m["form"] for m in accepted_meta)
    lengths = [m["length"] for m in accepted_meta]
    return {
        "genre_counts": dict(genre_counts),
        "requested_genres": requested_genres,
        "missing_genres": [g for g in requested_genres if genre_counts.get(g, 0) == 0],
        "form_counts": dict(form_counts),
        "nn_share": form_counts.get("nn", 0) / len(accepted_meta) if accepted_meta else 0.0,
        "length_min": min(lengths) if lengths else None,
        "length_max": max(lengths) if lengths else None,
        "length_mean": sum(lengths) / len(lengths) if lengths else None,
    }


def gate_g6_aggregate(texts: List[str]) -> dict:
    """Aggregate diversity report: distinct skeleton-hash ratio."""
    hashes = [gates.skeleton_hash(t) for t in texts]
    return {
        "documents": len(texts),
        "distinct_skeletons": len(set(hashes)),
        "distinct_ratio": len(set(hashes)) / len(texts) if texts else 0.0,
    }


def write_sample_dump(path: str, records: List[dict], n: int, rng: random.Random) -> None:
    """Write a human-readable Markdown sample of N random accepted documents."""
    sample = rng.sample(records, k=min(n, len(records)))
    lines = ["# Synthetic document sample dump\n"]
    for r in sample:
        rec = r["record"]
        lines.append(f"## {r['id']} -- {rec.genre} / {rec.variant} / {rec.form}\n")
        lines.append("**Text:**\n")
        lines.append("```\n" + r["text"] + "\n```\n")
        lines.append("**Labels:**\n")
        for etype, spans in r["output"].items():
            lines.append(f"- `{etype}`: {spans}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def measure_g7_false_positive_rate(paths: List[str], place_names: Set[str], agency_names: Set[str], max_docs: int = 8) -> dict:
    """Run the G7 sweep read-only over a few gold documents to estimate its false-positive rate.

    Since gold documents have no "planned span manifest" the way synthetic ones
    do, every already-labeled gold span is treated as covered and only spans
    the sweep finds beyond that are counted; a manual sample is returned for
    inspection rather than an automatic verdict, per the project's own rule
    that a regex count is not evidence about spans without reading the matches.
    """
    results = []
    for path in paths[:max_docs]:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                text = rec.get("text_input", "")
                covered = [s for v in rec.get("output", {}).values() for s in v]
                ok, findings = gates.gate_unplanned_pii(text, covered, place_names, agency_names)
                results.append({"id": rec.get("id"), "clean": ok, "findings": findings})
                break  # one document per file is enough for a spot measurement
    total_findings = sum(len(r["findings"]) for r in results)
    return {"docs_checked": len(results), "total_findings": total_findings, "detail": results}


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=["mock", "hf"], default="mock")
    parser.add_argument("--model", help="HF repo id, required for --backend hf")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--genres", default=",".join(genres_mod.genre_names()))
    parser.add_argument("--strategy", choices=["seeded", "marked"], default="seeded")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", required=True)
    parser.add_argument("--taxonomy", default="data/synthetic/taxonomy.json")
    parser.add_argument("--types-config", default="data/synthetic/types_config.yaml")
    parser.add_argument("--clause-bank", default="data/synthetic/clause_bank.json")
    parser.add_argument("--invalid-checksum-rate", type=float, default=0.05)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--near-dup-threshold", type=float, default=0.7)
    parser.add_argument("--g7-policy", choices=["reject", "report"], default="reject")
    parser.add_argument("--sample-dump-n", type=int, default=10)
    parser.add_argument("--force-types", default="", help="comma-separated types to force into every record")
    parser.add_argument("--gold-sample-glob", nargs="*", default=[],
                         help="gold files to spot-measure the G7 false-positive rate on (read-only)")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)

    taxonomy = data.load_taxonomy(args.taxonomy if os.path.exists(args.taxonomy) else None)
    taxonomy_index = data.taxonomy_index(taxonomy)
    clause_bank = data.load_clause_bank(args.clause_bank if os.path.exists(args.clause_bank) else None)
    used_fallback_taxonomy = not os.path.exists(args.taxonomy)
    used_fallback_clause_bank = not os.path.exists(args.clause_bank)

    types_config_path = args.types_config
    if not os.path.exists(types_config_path):
        types_config_path = os.path.join(args.out, "types_config.generated.yaml")
        data.write_types_config_yaml(taxonomy, types_config_path)

    public_figures = set(data.PUBLIC_FIGURES)
    place_names = {p for _c, p in data.POSTAL_PAIRS}
    agency_names = set(data.AGENCY_NAMES)

    backend = build_backend(args.backend, args.model)
    genre_list = [g.strip() for g in args.genres.split(",") if g.strip()]
    forced_types = [t.strip() for t in args.force_types.split(",") if t.strip()]

    config = GenerationConfig(
        strategy=args.strategy, invalid_checksum_rate=args.invalid_checksum_rate,
        retries=args.retries, near_dup_threshold=args.near_dup_threshold,
        g7_policy=args.g7_policy,
    )

    length_bands = [(400, 800), (800, 1600), (1600, 2800), (2800, 4000)]
    accepted, discarded = [], 0
    accepted_ngrams: List[Set[Tuple[str, ...]]] = []

    for i in range(args.n):
        genre = genre_list[i % len(genre_list)]
        variant = rng.choice(genres_mod.GENRES[genre]["variants"])
        form = "nn" if rng.random() < 0.35 else "nb"
        length_band = rng.choice(length_bands)

        result = generate_one_document(
            i, genre, variant, form, length_band, args.seed, taxonomy_index,
            clause_bank, public_figures, place_names, agency_names, backend,
            config, accepted_ngrams, forced_types,
        )
        if not result["accepted"]:
            discarded += 1
            continue

        doc_id = f"SYN-{i:06d}"
        accepted_ngrams.append(result["ngrams"])
        accepted.append({
            "id": doc_id, "record": result["record"], "text": result["text"],
            "output": result["output"], "gate_log": result["gate_log"],
            "tier_a_findings": result["tier_a_findings"],
        })

    batch_path = os.path.join(args.out, "synthetic_batch.jsonl")
    meta_path = os.path.join(args.out, "synthetic_batch_meta.jsonl")
    with open(batch_path, "w", encoding="utf-8") as batch_f, open(meta_path, "w", encoding="utf-8") as meta_f:
        for r in accepted:
            batch_f.write(json.dumps({"id": r["id"], "text_input": r["text"], "output": r["output"]}, ensure_ascii=False) + "\n")
            rec = r["record"]
            meta_f.write(json.dumps({
                "id": r["id"], "genre": rec.genre, "variant": rec.variant, "form": rec.form,
                "strategy": config.strategy, "seed": rec.doc_seed, "length": len(r["text"]),
                "num_attempts": r["gate_log"][-1]["attempt"], "gate_log": r["gate_log"],
                "tier_a_findings": r["tier_a_findings"],
            }, ensure_ascii=False) + "\n")

    g1_ok, g1_output = run_g1_validate_labels(batch_path, types_config_path)

    accepted_meta_for_g5 = [
        {"genre": r["record"].genre, "form": r["record"].form, "length": len(r["text"])}
        for r in accepted
    ]
    g5_report = gate_g5_distribution(accepted_meta_for_g5, genre_list)
    g6_report = gate_g6_aggregate([r["text"] for r in accepted])

    dump_path = os.path.join(args.out, "sample_dump.md")
    if accepted:
        write_sample_dump(dump_path, accepted, args.sample_dump_n, rng)

    g7_fp_report = measure_g7_false_positive_rate(args.gold_sample_glob, place_names, agency_names) if args.gold_sample_glob else None
    g7_mock_findings = sum(
        len(entry.get("g7_findings", [])) for r in accepted for entry in r["gate_log"] if entry.get("stage") == "accepted"
    )

    report = {
        "requested": args.n, "accepted": len(accepted), "discarded": discarded,
        "backend": args.backend, "strategy": args.strategy,
        "used_fallback_taxonomy": used_fallback_taxonomy,
        "used_fallback_clause_bank": used_fallback_clause_bank,
        "types_config_used": types_config_path,
        "G1_validate_labels": {"passed": g1_ok, "output": g1_output},
        "G5_distribution": g5_report,
        "G6_diversity": g6_report,
        "G7_unplanned_pii_on_accepted": {"policy": args.g7_policy, "residual_findings": g7_mock_findings},
        "G7_false_positive_measurement_on_gold": g7_fp_report,
    }
    report_path = os.path.join(args.out, "gate_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=lambda o: str(o))

    print(json.dumps({k: v for k, v in report.items() if k not in ("G1_validate_labels",)}, ensure_ascii=False, indent=2, default=str))
    print("\nG1 validate_labels.py output:\n" + g1_output)
    print(f"\nWrote {len(accepted)}/{args.n} accepted documents to {batch_path}")
    print(f"Gate report: {report_path}")
    return 0 if g1_ok else 1


if __name__ == "__main__":
    sys.exit(main())
