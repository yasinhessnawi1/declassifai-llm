"""Generate synthetic Norwegian PII documents with labels correct by construction.

The core idea, from `docs/SYNTHETIC_DATA_SPEC.md` Section 6 and
`docs/PROJECT_SPEC_V2.md` Section 3: sample a typed record first (people,
identifiers, clauses), ask a language model to *realise* that record as a
document in a given genre, then locate every planted value in the output by
exact substring search. The label is never guessed -- it is either found
verbatim or the document is discarded. What that guarantees and what it does
not is precise: every emitted span is real and correctly typed, but the model
can still (a) invent PII that was never planted, unlabelled, (b) write a
sensitive statement of its own that no planned value covers, or (c) always put
PII in the same slot, teaching position instead of language. Each failure mode
gets its own gate (G7, G11, and the placement randomisation checked indirectly
by G6 and G9) rather than being left to hope.

Pipeline per document (a whole-document call; dense and case-file documents, and
any plan of more than about ten items, are written in sections instead, see below):

    plan_batch -> sample_record -> build_prompt -> backend.generate (batched)
        -> marker check, truncation, G0 placeholders, length
        -> G2 verbatim (1-2 missing values: targeted repair of the draft)
        -> G15 negative placement (one planted negative per sentence, none chained to a
           seeded clause with "og"/"men", none repeated), G9 slot labels, G13 tabular
           dumps, G3 names, G4 checksums, G6
           near-duplicate, seeded-clause boundary extension, G7 (unplanned names
           and dates labelled, other unplanned PII rejected)
        -> G11 content audit (a second, temperature-0 pass of the same model:
           any unlabelled sensitive statement or any sentence framing origin,
           belief or sexuality as relevant to suspicion triggers one targeted
           repair, then a regeneration)
        -> accept, or retry with a new record

**A judgement type may appear more than once.** Pilot v4's 39 accepted documents carried
every clause-level type exactly once, so a detector trained on them learns "find one and
stop", while a gold inspection report averages 5.3 CRIMINAL and a concern report 8.1 HEALTH
spans. `gendoc_genres.draw_instance_counts` plans, per document, 1 to 4 instances of the
types a genre repeats (several offences in a police report, several findings in a vet
record, several debts in a debt-counselling note); most documents stay at one. The extra
instances are chosen after the rest of the record is fixed, from clauses whose `topic`
differs, that do not share a run of six words with each other, and that agree with what the
record already says (status, marital status, means, one psychiatric condition at a
time, headline debt against its components), and they are counted against the document's
item budget. The Art. 9 and health-family caps count categories, never instances.

**Long documents are written in sections.** Pilot v4 asked Qwen3.5-9B for a whole
dense or case-file document in one call, and the model is reliable with about eight
values per call and falls apart at twenty. 6 of 26 such documents were accepted, so
the "hard" benchmark was easier than planned. `tools/gendoc_sections.py` plans three
to eight sections per document (neutral, genre-realistic roles and headings, never
one that names a category, or no visible headings at all), assigns at most seven
planned items to each, and `run_generation` writes one section per call, batched
across documents, each from the text of the sections before it. G0, G2, G7, G9, G13
and G14 run on the section, and a failure repairs or regenerates that section alone;
G1, G3, G4, G6, G12 across sections, G11 and the total length run on the joined text,
and a failure there that can be traced to one section regenerates that section.
Labels are still found by exact search over the joined text.

then, over the accepted documents on disk: G1 (schema validation via
`tools/validate_labels.py`, per shard as it closes and over all shards), G5 (genre/form/length/type distribution vs the
plan), the coverage and density reports, and G8 (a human-readable sample dump).

Three things the pilots changed, each because a measurement said so:

**Records are sampled for coherence.** Pilot v1 drew every optional type
independently and produced incoherent subjects. Now each party is internally
consistent (one gender, one age that agrees with their own fødselsnummer, their
own address), the employer and role belong together, immigration facts only
attach to a foreign subject, and judgement clauses are checked against the
subject's state before they are accepted.

**Density is a distribution, not a band.** Pilot v1 put 14 types in a
1,600-character NAV decision and the text was unusable; a fixed 5-9 band would
have been a pattern of its own. `gendoc_genres.PROFILES` draws a profile per
document -- from PII-free through minimal, light, typical and dense to a
multi-party case file -- with length sampled jointly and a plausibility ceiling
that scales with length and genre. About one document in twenty contains no
personal data at all, because a detector that never sees a clean document
learns that everything contains PII.

**Coverage is a property of the batch.** `--coverage-target K` schedules every
schedulable type into at least K documents, always in a genre where a real
Norwegian document would carry it, and never more of them into one document than
its profile can absorb. The target is all 57 taxonomy types.

**Two datasets, never mixed.** `--dataset train` is the large, easier set;
`--dataset benchmark` is the held-out one (`docs/PROJECT_SPEC_V2.md` Section 4).
Each draws only from its own share of the clause bank and of the name, street and
employer pools, fixed in `data/synthetic/benchmark_partition.json`
(`tools/gendoc_dataset.py`), so no string a benchmark scores on was generated into
training data; `tools/check_dataset_leakage.py` verifies that on finished files.
The benchmark also leans on `difficulty: hard` clauses and on dense and case-file
documents, and plants one to three hard negatives per document -- near-miss clauses
such as "under samtalen ville han ikke si om han er fagorganisert" -- that must stay verbatim
and unlabelled, recorded in the metadata as `planted_negatives`. The training set
plants zero or one, from its own share of the negatives. A negative's pronoun
placeholders are filled from the subject, and no negative text is planted more than
twice in a run (`NegativeLedger`): pilot v4 planted 37 negatives from 13 distinct
texts, and a model memorises a sentence it sees every tenth document.

**A negative is a clause with its own subject, not a fragment that opens with "og" or "men".**
Pilot v5 planted 62 negatives and kept all 62 verbatim, but every new bank text began with
"og " or "men ", so the model chained them into run-ons ("..., og han bur i ei bydel ..., og
han tok ikkje stilling til ...") and a fixed opening was itself a surface mark of a trap. The
bank texts now start at the subject (`{PRON}`) or at a lead word that varies ("under samtalen
ville han ...", "i helgen leste han ..."), and the prompt lets the model write one as a
sentence of its own or build it into a longer one. When it opens a sentence the model
capitalises it, so the first letter is matched in either case and the rest exactly
(`PlantedNegative.surface`, `gendoc_gates.resolve_surfaces`); the labels and every later gate
use that surface. G15 rejects a document or section where two negatives share a sentence,
where a negative is coordinated with a seeded clause by "og", "men" or "samt", or where one
negative stands twice; G11 asks the auditor whether a sentence presents a negative as
relevant or suspicious, and a finding is repaired like any other framing finding.

Benchmark ids are `SYB-`, training ids `SYN-`.

**A run survives being stopped.** The GPU is shared and a full run is days of it, so the run
yields to other jobs and picks up later (`tools/gendoc_store.py`). Every finished document,
accepted or discarded, is appended to disk and fsynced the moment it finishes, into shards of
`--shard-size` accepted documents (`synthetic_batch_00000.jsonl` with its `_labelled` and `_meta`
files); the meta line is written last and commits the document. `run_manifest.json` records the
arguments, the git commit and the hashes of the generator source and data files. `--resume`
re-derives the identical plan from the seed, skips every index already on disk, and rebuilds the
cross-document state from the files: the G6 5-gram list in write order and the negative-reuse
ledger. It refuses when the code or data hashes changed, unless `--resume-force`, which records
the override in the manifest. Documents are generated in windows of `--window` plans (default
`--batch-size`); cross-document state is exact at window boundaries, so a killed window is
generated again from its start and the run's files are byte-identical to an uninterrupted run's
(under the mock backend; see the harness). A stop (SIGTERM, SIGINT, the stop file, or
`--yield-when-gpu-busy`) finishes the window in flight, writes it, records progress and exits 0.
`--status` reports progress and `--report-only` rebuilds the gate report from the shards.

Usage:
    python3 tools/generate_documents.py --backend hf --model Qwen/Qwen3.5-9B \\
        --n 50 --strategy seeded --seed 1 --batch-size 4 --coverage-target 3 \\
        --dataset train --out data/synthetic/full_train/
    python3 tools/generate_documents.py --resume --out data/synthetic/full_train/
    touch data/synthetic/full_train/STOP        # graceful stop
    python3 tools/generate_documents.py --status --out data/synthetic/full_train/
    python3 tools/generate_documents.py --report-only --out data/synthetic/full_train/
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_audit as audit
import gendoc_coherence as coherence
import gendoc_data as data
import gendoc_dataset as dataset_mod
import gendoc_gates as gates
import gendoc_genres as genres_mod
import gendoc_identifiers as ident
import gendoc_sections as sections_mod
import gendoc_store as store_mod
from gendoc_backends import DRAFT_CLOSE, DRAFT_OPEN, MANIFEST_SENTINEL, build_backend
from validate_labels import load_types as validate_labels_load_types  # noqa: E402

MARKER_RE = re.compile(r"⟦([A-Z_]+):\s*(.*?)⟧", re.DOTALL)


# ---------------------------------------------------------------------------
# Record sampling
# ---------------------------------------------------------------------------

REFERENCE_DATE = date(2026, 9, 26)


@dataclass
class Person:
    """A sampled (never real) person."""

    first_name: str
    last_name: str
    gender: str  # "M" or "F"
    birth_date: date
    nationality: str = "norsk"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def age(self, today: date = REFERENCE_DATE) -> int:
        """Exact age in whole years, so AGE never contradicts the fødselsnummer."""
        before_birthday = (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        return today.year - self.birth_date.year - int(before_birthday)


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
    hint: Optional[str] = None  # whose value this is / where it belongs, for the prompt
    party: Optional[str] = None  # "author" or a cast role for a person other than the subject; None = subject
    topic: Optional[str] = None  # clause bank `topic` of a clause, for the compatibility and instance reports


@dataclass
class PlantedNegative:
    """A near-miss sentence planted verbatim and deliberately left unlabelled.

    Attributes:
        type: The type it is a near-miss for (the bank's `negatives` key).
        text: The sentence after pronoun filling, exactly as the document must
            contain it.
        why_not: The annotation-spec reason it is not a disclosure.
        also_labelled: `{TYPE: substring}` for a real value of another type inside
            the text (a case number that happens to contain "LO"); that substring
            is labelled as its own type, the near-miss reading is the one left alone.
        template: The bank text before `{PRON}`/`{POSS}`/`{OBJ}` were filled; the
            per-run reuse cap counts templates, so "han" and "hun" fills of one
            sentence are one sentence.
        surface: The form the document actually contains, set by the gates once the
            text is written. It differs from `text` only in the case of the first
            letter: a negative that opens a sentence is capitalised by the model.
            Empty until a document has been checked.
    """

    type: str
    text: str
    why_not: str
    also_labelled: Dict[str, str] = field(default_factory=dict)
    template: str = ""
    surface: str = ""

    def __post_init__(self) -> None:
        self.template = self.template or self.text

    @property
    def found(self) -> str:
        """The string to search for in the document: its realised surface, else the planted text."""
        return self.surface or self.text


@dataclass
class Record:
    """A fully sampled, typed record for one document.

    `person` is the single data subject the document is about and is None only
    for a PII-free plan. `parties` is everyone the document names, the subject
    included: a case file's spouse, children, caseworker and doctor each carry
    their own coherent identifiers, which is where a dense document's many
    distinct spans come from.

    Attributes beyond the sampled content: `instances_planned` is what the plan asked for
    (`{type: 2..4}`), `instances_realised` what the record could supply (types with two or more
    planned values), and `coherence` the report of the cast-coherence pass.
    """

    doc_seed: int
    genre: str
    variant: str
    form: str  # "nb" or "nn"
    length_band: Tuple[int, int]
    person: Optional[Person]
    parties: List["Party"]
    planned: List[PlannedValue]
    signatory_role: Optional[str] = None
    employer: Optional[str] = None
    profile: str = "typical"
    pii_free: bool = False
    dataset: str = "train"
    planted_negatives: List[PlantedNegative] = field(default_factory=list)
    dropped_forced: List[str] = field(default_factory=list)
    instances_planned: Dict[str, int] = field(default_factory=dict)  # plan: type -> instances asked for
    instances_realised: Dict[str, int] = field(default_factory=dict)  # type -> planned values of it (>= 2 only)
    coherence: Optional[dict] = None  # `gendoc_coherence.CoherenceReport.as_dict()` of the cast


def sample_person(rng: random.Random, age_profile: str = "adult", today: date = REFERENCE_DATE,
                   nationality: str = "norsk", gender: Optional[str] = None,
                   age: Optional[int] = None, age_clamp: Optional[Tuple[int, int]] = None) -> Person:
    """Sample a person from the embedded name lists, never a real public figure.

    Ages come from a weighted per-genre band distribution rather than a uniform
    draw: pilot v2 drew uniformly from (18, 85) and its accepted subjects
    clustered at 70-85, which is not the population any of these document types
    describes.

    Args:
        rng: Seeded RNG.
        age_profile: Name of a distribution in `gendoc_genres.AGE_PROFILES`.
        today: Reference date for computing the birth date from an age.
        nationality: Nationality adjective; a non-Norwegian one draws the name
            from that nationality's pool in `gendoc_data.active_pools()`.
        gender: Force "M" or "F"; None picks at random.
        age: Force an exact age, bypassing the profile.
        age_clamp: (min, max) the drawn age is clamped into, for a genre that
            cannot name anyone outside it.

    Returns:
        A `Person`. Callers must still run G3 before shipping any document.
    """
    gender = gender or rng.choice(["M", "F"])
    pools = data.active_pools()
    if nationality in pools.foreign_names:
        males, females, surnames = pools.foreign_names[nationality]
        first = rng.choice(males if gender == "M" else females)
        last = rng.choice(surnames)
    else:
        first = rng.choice(pools.first_male if gender == "M" else pools.first_female)
        last = rng.choice(pools.surnames)
    if age is None:
        age = genres_mod.sample_age(rng, age_profile)
    if age_clamp:
        age = max(age_clamp[0], min(age_clamp[1], age))
    birth = date(today.year - age, rng.randint(1, 12), rng.randint(1, 28))
    if (birth.month, birth.day) > (today.month, today.day):
        birth = date(birth.year - 1, birth.month, birth.day)
    return Person(first, last, gender, birth, nationality)


def _resample_until_no_collision(rng: random.Random, public_figures: Set[str], **kwargs) -> Person:
    for _ in range(50):
        person = sample_person(rng, **kwargs)
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
    "eritreisk", "afghansk", "irakisk", "ukrainsk", "iransk",
]
_MARITAL = ["gift", "ugift", "skilt", "samboer", "enke", "enkemann"]


def _address(rng: random.Random) -> Tuple[str, str, str]:
    """Return (full_address_with_postal, postal_code, place)."""
    street = rng.choice(data.active_pools().street_names)
    number = rng.randint(1, 180)
    suffix = rng.choice(["", "", "", "A", "B", "C"])
    postal, place = rng.choice(data.POSTAL_PAIRS)
    return f"{street} {number}{suffix}, {postal} {place}", postal, place


def _ascii(name: str) -> str:
    """Fold a name to ASCII for email/username local parts (`Wiśniewski` -> `wisniewski`)."""
    folded = unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in folded if not unicodedata.combining(c))


def _employer(rng: random.Random, place: Optional[str]) -> Tuple[str, List[Tuple[str, str]]]:
    """Sample an employer name and the (nb, nn) roles that fit its sector.

    The pilot named every organisation after the subject's own surname, which
    turned a dismissal letter into a family-business dispute. Employers here
    are named after a place (often the subject's own town) or a neutral
    prefix, and the sector drives which roles EMPLOYMENT can take.
    """
    sector_words, roles = rng.choice(data.ROLE_SECTORS)
    use_place = rng.random() < 0.4 and place is not None
    prefix = place if use_place else rng.choice(data.active_pools().org_prefixes)
    suffix = rng.choice(["AS", "AS", "AS", "ASA", "Gruppen AS"])
    return f"{prefix} {rng.choice(sector_words)} {suffix}", roles


# Types that are generated as a literal value rather than drawn from the clause
# bank.
_VALUE_KIND_TYPES = {
    "NATIONAL_ID", "DATE_OF_BIRTH", "ORG_NUMBER", "BANK_ACCOUNT", "IBAN",
    "CREDIT_CARD", "PHONE", "FAX_NUMBER", "EMAIL", "URL", "IP_ADDRESS",
    "USERNAME", "SOCIAL_MEDIA", "CASE_NUMBER", "PASSPORT", "DRIVER_LICENSE",
    "IDENTITY_CARD", "VISA_NUMBER", "MILITARY_ID", "MEDICAL_LICENSE",
    "INSURANCE_NUMBER", "TAX_ID", "STUDENT_ID", "DEVICE_ID", "CRYPTO",
    "PASSWORD", "LICENSE_PLATE", "POSTAL_CODE", "ADDRESS", "AGE", "GENDER",
    "MARITAL_STATUS", "NATIONALITY", "LOCATION", "ORGANIZATION", "DATE_TIME",
    "ANIMAL_INFO", "FIREARMS_LICENSE", "VESSEL_REGISTRATION",
}

def _generate_value_kind(
    etype: str, rng: random.Random, person: Person, invalid_rate: float,
    staff: bool = False,
) -> Tuple[str, Optional[bool]]:
    """Generate a Tier A / Tier B "value" kind value.

    Args:
        etype: Entity type name.
        rng: Seeded RNG.
        person: The person the value belongs to, for the values derived from a
            name or a birth date.
        invalid_rate: Probability of deliberately breaking a real checksum.
        staff: Whether the person is a professional acting in the document (a
            doctor, a caseworker), whose email sits on an institutional domain
            rather than a consumer one.

    Returns:
        Tuple of (value text, whether its checksum is valid, or None when the
        identifier has no checksum to be right or wrong about).
    """
    make_invalid = rng.random() < invalid_rate
    valid = not make_invalid
    first, last = _ascii(person.first_name), _ascii(person.last_name)

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
        return ident.format_bank_account(rng, idf.value), idf.valid
    if etype == "IBAN":
        idf = ident.bank_account(rng, valid=valid)
        return ident.format_iban(rng, ident.iban_no(idf.value)), idf.valid
    if etype == "CREDIT_CARD":
        idf = ident.credit_card(rng, valid=valid)
        return idf.value, idf.valid
    if etype == "TAX_ID":
        idf = ident.tax_id(rng, valid=valid)
        return idf.value, idf.valid
    if etype == "DEVICE_ID":
        if rng.random() < 0.4:
            idf = ident.imei(rng, valid=valid)
            return idf.value, idf.valid
        return ident.device_id(rng), None
    if etype == "PHONE":
        return ident.phone_number(rng, mobile=True), None
    if etype == "FAX_NUMBER":
        return ident.phone_number(rng, mobile=False), None
    if etype == "EMAIL":
        if staff:
            return ident.work_email_address(rng, first, last), None
        return ident.email_address(rng, first, last), None
    if etype == "URL":
        return ident.url(rng), None
    if etype == "IP_ADDRESS":
        return ident.ip_address(rng), None
    if etype == "USERNAME":
        return ident.username(rng, first, last), None
    if etype == "SOCIAL_MEDIA":
        return ident.social_media_handle(rng, first, last), None
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
    if etype == "STUDENT_ID":
        return ident.student_id(rng), None
    if etype == "CRYPTO":
        return ident.crypto_address(rng), None
    if etype == "PASSWORD":
        return ident.password_value(rng), None
    if etype == "LICENSE_PLATE":
        return ident.vehicle_reg(rng), None
    if etype == "FIREARMS_LICENSE":
        return ident.firearms_license_number(rng), None
    if etype == "VESSEL_REGISTRATION":
        return ident.vessel_registration_mark(rng), None
    if etype == "POSTAL_CODE":
        postal, _place = rng.choice(data.POSTAL_PAIRS)
        return postal, None
    if etype == "ADDRESS":
        full, _postal, _place = _address(rng)
        return full, None
    if etype == "AGE":
        # AGE is one span including its unit ("13 år", ANNOTATION_SPEC); a bare
        # "13" planned here and "13 år" found by the sweep were labelled twice.
        return f"{person.age()} år", None
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
        return _employer(rng, "Oslo")[0], None
    if etype == "DATE_TIME":
        offset = rng.randint(-700, 0)
        return _format_date(rng, REFERENCE_DATE + timedelta(days=offset)), None
    if etype == "ANIMAL_INFO":
        return ident.animal_descriptor(rng), None
    raise KeyError(etype)


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


# Identifier literals fixed inside a clause-bank text. `dømt for bedrageri i sak
# 12345/2018` is ANNOTATION_SPEC's own worked example; printed as written it puts the
# same case number into every document that draws it, a string a detector can
# memorise, and it would sit unlabelled although the spec nests CASE_NUMBER inside a
# CRIMINAL clause. The bank text stays unchanged (it keys the benchmark partition);
# the number is swapped at sampling time and planted as its own CASE_NUMBER value.
_CLAUSE_ID_LITERALS = {"12345/2018": "CASE_NUMBER"}


def localize_clause_ids(rng: random.Random, text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Replace fixed identifier literals in a clause with fresh values.

    Args:
        rng: Seeded RNG.
        text: The clause text after name localisation.

    Returns:
        Tuple of (text, list of (type, value) to plant as nested labels).
    """
    planted: List[Tuple[str, str]] = []
    for literal, etype in _CLAUSE_ID_LITERALS.items():
        if literal in text:
            value = ident.case_number(rng)
            text = text.replace(literal, value)
            planted.append((etype, value))
    return text, planted


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

    pools = data.active_pools()

    def _fresh_full(kind: str) -> str:
        male = kind == "PERSON_M" or (kind == "PERSON" and rng.random() < 0.5)
        for _ in range(20):
            first = rng.choice(pools.first_male if male else pools.first_female)
            full = f"{first} {rng.choice(pools.surnames)}"
            if full not in public_figures:
                break
        return full

    def _sub(m: "re.Match") -> str:
        kind = m.group(1)
        if kind.startswith("SURNAME"):
            return rng.choice(pools.surnames)
        full = _fresh_full(kind)
        introduced.append(full)
        return full

    return _CLAUSE_PLACEHOLDER_RE.sub(_sub, text), introduced


@dataclass
class Party:
    """One person the document is about or names, with their role in it.

    The earlier design allowed exactly one data subject, which made a case file
    impossible: a barnevern review names a child, two parents, a caseworker and
    a teacher, and each of them has their own fødselsnummer, address and phone.
    `is_subject` marks the single person the document is *about*; everyone else
    is a named participant whose own values are generated from their own
    `Person`, so gender, age and fødselsnummer stay consistent per person.
    """

    person: Person
    role: Optional[str]
    label: str
    is_subject: bool = False
    staff: bool = False


@dataclass
class _Subject:
    """What is already fixed about the record's subject while types are drawn.

    Every clause drawn from the bank is checked against this before it is
    accepted, and some clauses update it (an EMPLOYMENT clause fixes the
    employment status, a FAMILY_RELATION clause the marital status). This is
    what stops a NAV claimant from also "søker om asyl", a dismissed employee
    from also being "daglig leder og eier" of another firm, and a woman from
    being described with "hans homofile legning".
    """

    person: Person
    genre: str
    form: str
    clause_genres: Set[str] = dataclasses.field(default_factory=set)
    status: Optional[str] = None  # employed / unemployed / retired / uforetrygd
    marital: Optional[str] = None
    no_partner: bool = False  # set once a SEXUAL_ORIENTATION clause is chosen
    animal_types: Set[str] = dataclasses.field(default_factory=set)  # types drawn from the animal's clauses
    polarity: Optional[str] = None  # "poor" / "rich", the means the first financial clause implies
    groups: Dict[str, str] = dataclasses.field(default_factory=dict)  # clause `group` -> the one topic in use

    @property
    def foreign(self) -> bool:
        return self.person.nationality != "norsk"


_YEAR_IN_TEXT_RE = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")


def _clause_fits(entry: dict, subject: _Subject, etype: Optional[str] = None) -> bool:
    """Whether a clause-bank entry is coherent with the record's subject.

    The clause bank annotates each entry with the original pilot genre ids and the ids
    added since for particular kinds of document (`crime`, `debt`, `barnevern`, `school`,
    `vet_clinical` ...); a genre declares in `gendoc_genres.GENRES[...]["clause_genres"]`
    which of those its own clauses may come from, so 30-odd genres share one bank.

    Args:
        entry: A clause-bank entry (see `schema_note` in clause_bank.json).
        subject: The subject state so far.
        etype: The clause type being drawn. Needed for the types a veterinary genre
            takes from the *animal's* clauses (`subject.animal_types`); those entries are
            then the only ones that fit, and every other type takes a person's clause.

    Returns:
        True if the entry's genre, form, subject kind, gender, age, origin, status, partner,
        means (`polarity`) and `group` constraints all hold, and any year it mentions falls
        after the subject's 15th birthday.
    """
    if not subject.clause_genres.intersection(entry.get("genres", [])):
        return False
    if entry.get("form") != subject.form:
        return False
    wanted_kind = "animal" if etype in subject.animal_types else "person"
    if entry.get("subject", "person") != wanted_kind:
        return False
    if entry.get("polarity") and subject.polarity and entry["polarity"] != subject.polarity:
        return False
    group = entry.get("group")
    if group and subject.groups.get(group, entry.get("topic")) != entry.get("topic"):
        return False
    person = subject.person
    if entry.get("gender") and entry["gender"] != person.gender:
        return False
    lo, hi = entry.get("age_range", [18, 120])
    if not lo <= person.age() <= hi:
        return False
    if entry.get("nationalities") and person.nationality not in entry["nationalities"]:
        return False
    origin = entry.get("origin")
    if origin == "foreign" and not subject.foreign:
        return False
    if origin == "native" and subject.foreign:
        return False
    status = entry.get("status")
    if status and subject.status and status != subject.status:
        return False
    if entry.get("partner") and subject.no_partner:
        return False
    marital = entry.get("marital")
    if marital and subject.marital and marital != subject.marital:
        return False
    for year in _YEAR_IN_TEXT_RE.findall(entry["text"]):
        if int(year) < person.birth_date.year + 15 or int(year) > REFERENCE_DATE.year:
            return False
    return True


def _commit_entry(subject: _Subject, etype: str, entry: dict) -> None:
    """Record what a chosen clause settles about the subject, so later clauses agree with it.

    An EMPLOYMENT clause fixes the employment status, a family clause the marital status,
    an orientation clause rules out a partner of the other sex, the first clause that
    implies means (`polarity`) fixes whether the subject is in difficulty or comfortable,
    and a clause with a `group` fixes which one topic of that group the document is about
    (one psychiatric condition, one general financial condition).
    """
    subject.status = subject.status or entry.get("status")
    subject.marital = subject.marital or entry.get("marital")
    subject.polarity = subject.polarity or entry.get("polarity")
    if etype == "SEXUAL_ORIENTATION":
        subject.no_partner = True
    if entry.get("group"):
        subject.groups.setdefault(entry["group"], entry.get("topic"))


def _entry_topics(entry: dict) -> Set[str]:
    """Return the topics an entry occupies: its own and any it also covers (`also`)."""
    return {entry["topic"], *entry.get("also", ())} if entry.get("topic") else {entry["text"]}


def clauses_compatible(chosen: Sequence[dict], cand: dict) -> bool:
    """Whether a candidate clause may join clauses of the same type already chosen.

    Several clauses of one type in one document must be several different facts that can all
    be true of one person. Four tests, none of which needs the model:

    * **Different topic.** Two convictions for violence, two depressions and two statements
      of the general financial condition are one fact said twice. A topic is the bank's
      `topic` (and its `also` list), so an entry that mentions a threat and a weapon occupies
      both topics.
    * **Different words.** No text contains another, and no two share a run of six words
      (`_SHARED_RUN_WORDS`): "dømt for bedrageri i 2018" and "dømt for bedrageri i sak
      12345/2018" are one clause. Shorter shared stems ("har ved flere anledninger ...",
      "dømt for ...") are ordinary and are allowed; G6 and G12 do not count them.
    * **Debts add up.** A headline debt ("gjeld på over 700 000 NOK") is a floor on the sum
      of the debts listed beside it, so the components may not exceed it.
    * **Different cases.** Entries marked `as_type` (a civil-status clause filed under
      MARITAL_STATUS) are never a further instance of the type they were drawn for.

    Args:
        chosen: Entries already chosen for this type in this document.
        cand: The candidate entry.

    Returns:
        True when the candidate may be added.
    """
    if cand.get("as_type"):
        return False
    used: Set[str] = set()
    for entry in chosen:
        used |= _entry_topics(entry)
    if _entry_topics(cand) & used:
        return False
    for entry in chosen:
        a, b = entry["text"].lower(), cand["text"].lower()
        if a in b or b in a or _shares_word_run(a, b):
            return False
    both = list(chosen) + [cand]
    headlines = [e["amount"] for e in both if e.get("kind") == "headline" and e.get("amount")]
    if headlines:
        components = sum(e.get("amount", 0) for e in both if e.get("kind") == "debt")
        if components > min(headlines):
            return False
    return True


def _weighted_pick(rng: random.Random, weights: Dict[str, float], k: int,
                   allowed=lambda t: True) -> List[str]:
    """Draw up to k distinct keys with probability proportional to weight."""
    pool = {t: w for t, w in weights.items() if w > 0}
    chosen: List[str] = []
    while pool and len(chosen) < k:
        total = sum(pool.values())
        r = rng.random() * total
        for t, w in pool.items():
            r -= w
            if r <= 0:
                break
        del pool[t]
        if allowed(t):
            chosen.append(t)
    return chosen


# Types whose clause choice constrains later ones go first: orientation rules
# out an opposite-sex partner, employment fixes the status economic/disability
# clauses must agree with, and family relations fix the marital status.
_SAMPLING_ORDER = [
    "SEXUAL_ORIENTATION", "EMPLOYMENT", "ECONOMIC_STATUS", "DISABILITY",
    "FAMILY_RELATION",
]

# Genres whose data subject is in work by construction, so an unemployment or
# retirement clause would contradict the document itself.
_EMPLOYED_SUBJECT_GENRES = {
    "dismissal_letter", "employment_contract", "hr_grievance", "whistleblowing_report",
    "occupational_health", "sickness_followup", "forsvaret_clearance",
}


def _cast_person(rng: random.Random, role: str, subject: Person, public_figures: Set[str],
                  age_profile: str) -> Person:
    """Sample a cast member coherent with the role they play and with the subject.

    A spouse is of a similar age and shares the household; a child is a minor
    younger than the subject; a parent is a generation older. Professionals get
    a working-age draw. Nationality is inherited only for family members, so a
    foreign subject's caseworker is not also foreign by construction.

    Args:
        rng: Seeded RNG.
        role: Cast role id from `gendoc_genres.CAST_ROLES`.
        subject: The data subject, whose age and nationality family roles follow.
        public_figures: Embedded public-figure set (G3).
        age_profile: The genre's own age distribution, for the neutral roles.

    Returns:
        A `Person`.
    """
    subject_age = subject.age()
    family = role in {"spouse", "child", "parent", "guardian"}
    nationality = subject.nationality if family and rng.random() < 0.7 else (
        "norsk" if rng.random() < 0.85 else rng.choice(data.FOREIGN_NATIONALITIES))
    if role == "spouse":
        age = max(18, subject_age + rng.randint(-8, 8))
        gender = "M" if subject.gender == "F" else "F"
    elif role == "child":
        age = max(0, min(subject_age - 18, rng.randint(1, 17)))
        age = age if age >= 1 else 1
        gender = None
    elif role == "parent" or (role == "guardian" and subject_age < 18):
        age = subject_age + rng.randint(22, 42)
        gender = None
    elif role in coherence.PROFESSIONAL_ROLES or role == "guardian":
        # A verge for an adult is a professional; every professional is 25-67 (see
        # `gendoc_coherence`), which the old "working" band (18-29 for a fifth of draws) broke.
        age = genres_mod.sample_age(rng, "professional")
        gender = None
    else:
        age = genres_mod.sample_age(rng, age_profile)
        gender = None
    return _resample_until_no_collision(
        rng, public_figures, nationality=nationality, gender=gender, age=age,
    )


def _with_age(person: Person, age: int, rng: random.Random, today: date = REFERENCE_DATE) -> Person:
    """Return the same person (name, sex, nationality) at a different age.

    Used by the coherence repair: a physician drawn at 23 keeps their name and becomes 41.
    """
    birth = date(today.year - age, rng.randint(1, 12), rng.randint(1, 28))
    if (birth.month, birth.day) > (today.month, today.day):
        birth = date(birth.year - 1, birth.month, birth.day)
    return Person(person.first_name, person.last_name, person.gender, birth, person.nationality)


# A child under fifteen has no phone, mailbox or bank account of their own to
# give a caseworker; the smoke run's eleven-year-old witness supplied a phone
# number that the document then printed as the school's contact line.
_NOT_FOR_YOUNG_CHILDREN = {"PHONE", "EMAIL", "FAX_NUMBER", "BANK_ACCOUNT", "ORG_NUMBER"}

_STAFF_ROLES = {"physician", "psychologist", "veterinarian", "caseworker", "lawyer",
                "officer", "teacher", "employer_contact", "creditor_contact"}

# Whose a professional licence number can be: a clinician's. The subject of a record is a
# patient, a claimant or a suspect, and an HPR number printed next to them (pilot v4's
# "Håkon Selvik ... med hpr-nummer 4665353") is the sampler's mistake before it is the
# model's, so the planned value is always given to a clinician.
_CLINICIAN_ROLES = ("physician", "psychologist", "veterinarian")
_CLINICAL_TITLES = {"fastlege", "lege", "overlege", "spesialist", "bedriftslege", "arbeidsmedisiner",
                    "arbeidsmedisinar", "psykolog", "psykologspesialist", "veterinær", "dyrlege"}


def _animal_conflict(a: str, b: str) -> bool:
    """Whether two animal descriptors could be the same animal or the same herd.

    `hunden Rex` and `Rex, labrador` name one dog, and `120 sauer` beside `besetning på 40
    sauer` is one flock counted twice; `hunden Rex` beside `katten Mia` is two animals.
    """
    names = lambda s: set(re.findall(r"[A-ZÆØÅ][\wæøå]+", s))  # noqa: E731
    kind = lambda s: re.sub(r"\d+|besetning på", "", s).strip()  # noqa: E731
    return bool(names(a) & names(b)) or kind(a) == kind(b)


def _add_instances(
    rng: random.Random, plan: "DocPlan", planned: List[PlannedValue], clause_texts: Dict[str, dict],
    subject: _Subject, clause_bank: dict, public_figures: Set[str],
    difficulty_weights: Optional[Dict[str, float]], form: str, tier, label,
) -> None:
    """Append the further instances `plan.instances` asks for, as far as the record allows.

    Runs after every first instance, cast value and identifier is fixed, so each extra is
    chosen against the finished record: it must fit the subject (`_clause_fits`, which carries
    status, marital status, means and the one-topic-per-group rule) and the clauses already
    chosen for its type (`clauses_compatible`), and its cost -- the clause and any person it
    names -- must fit what is left of `genres_mod.item_budget`. A type the document did not
    draw, an EMPLOYMENT role, and a type with no compatible clause left are skipped, so the
    realised count can be lower than the planned one; the shortfall is in the metadata.

    Args:
        rng: The instance RNG stream.
        plan: The document plan; `plan.instances` is `{type: total instances wanted}`.
        planned: The record's planned values, extended in place.
        clause_texts: `{type: the first clause entry chosen}`.
        subject: The subject state after the first instances.
        clause_bank: The dataset's clause bank.
        public_figures: Public-figure set, for names in clauses.
        difficulty_weights: Dataset weights by clause difficulty.
        form: "nb" or "nn".
        tier: Type -> tier lookup.
        label: Type -> field label lookup.
    """
    room = (genres_mod.item_budget(plan.profile, plan.length_band[1]) - len(planned) - plan.n_negatives)
    order = {t: i for i, t in enumerate(_SAMPLING_ORDER)}
    for etype in sorted(plan.instances, key=lambda t: (order.get(t, len(order)), t)):
        extra = plan.instances[etype] - 1
        if etype == "ANIMAL_INFO":
            existing = [pv.value for pv in planned if pv.type == "ANIMAL_INFO"]
            if not existing:
                continue
            for _ in range(extra):
                if room < 1:
                    break
                for _try in range(12):
                    value = ident.animal_descriptor(rng)
                    if not any(_animal_conflict(value, other) for other in existing):
                        planned.append(PlannedValue(etype, tier(etype), "value", value, None, label(etype),
                                                    hint="et annet dyr eller en annen flokk i saken"))
                        existing.append(value)
                        room -= 1
                        break
            continue
        first = clause_texts.get(etype)
        if first is None or first.get("role_value"):
            continue
        chosen = [first]
        for _ in range(extra):
            candidates = [
                e for e in clause_bank.get(etype, [])
                if _clause_fits(e, subject, etype) and clauses_compatible(chosen, e)
                and 1 + len(re.findall(r"\{PERSON(?:_[MF])?\}", e["text"])) <= room]
            if not candidates:
                break
            entry = _weighted_entry(rng, candidates, difficulty_weights)
            text, introduced = localize_clause_names(rng, entry["text"], public_figures)
            for name in introduced:
                planned.append(PlannedValue("PERSON", "B", "value", name, None, label("PERSON"),
                                            hint="person nevnt i en av opplysningene"))
            text, nested_ids = localize_clause_ids(rng, text)
            for id_type, id_value in nested_ids:
                planned.append(PlannedValue(id_type, tier(id_type), "value", id_value, None, label(id_type),
                                            hint="saksnummeret i opplysningen over; skrives bare der"))
            planned.append(PlannedValue(
                etype, tier(etype), "clause", text, "seeded", label(etype),
                difficulty=entry.get("difficulty"), topic=entry.get("topic")))
            _commit_entry(subject, etype, entry)
            chosen.append(entry)
            room -= 1 + len(introduced)


def _licence_holder(parties: Sequence["Party"], signatory_role: Optional[str]) -> Optional["Party"]:
    """Return the party whose HPR number a planned MEDICAL_LICENSE is: a clinician, never the subject.

    The author when the signature is clinical (a GP, a psychologist, a vet), otherwise the
    first clinician in the cast.
    """
    author = next((p for p in parties if p.role == "author"), None)
    if author is not None and (signatory_role or "") in _CLINICAL_TITLES:
        return author
    return next((p for p in parties if p.role in _CLINICIAN_ROLES), None)


def _weighted_entry(rng: random.Random, candidates: List[dict],
                    difficulty_weights: Optional[Dict[str, float]]) -> dict:
    """Draw a clause-bank entry, uniformly or weighted by its `difficulty`.

    With no weights this is exactly `rng.choice`, so a training run draws the same
    clauses it did before datasets existed.
    """
    if not difficulty_weights:
        return rng.choice(candidates)
    weights = [difficulty_weights.get(e.get("difficulty"), 1.0) for e in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def _nationalities_hosting(forced_clauses: Sequence[str], spec: dict, form: str,
                           clause_bank: dict) -> List[str]:
    """Return the foreign nationalities for which every forced clause type has a clause.

    A clause entry may be restricted to a nationality (`identifiziserer seg som
    etnisk somalisk`) or to a native/foreign subject, so a forced ETHNICITY clause
    in a Nynorsk UDI decision found a fitting entry for four of the nine
    nationalities and was dropped for the other five. Drawing the nationality
    from the compatible ones is what makes a forced type land.

    Args:
        forced_clauses: Forced types that are clause types.
        spec: The genre spec, for its `clause_genres`.
        form: "nb" or "nn".
        clause_bank: Loaded clause bank (or one dataset's share of it).

    Returns:
        Compatible nationalities; every foreign nationality when none constrains
        the draw, and also when the constraints cannot be met together.
    """
    everyone = list(data.active_pools().foreign_names)
    genres = set(spec["clause_genres"])
    allowed = set(everyone)
    for etype in forced_clauses:
        fits = set()
        for entry in clause_bank.get(etype, []):
            if entry.get("form") != form or not genres & set(entry.get("genres", [])):
                continue
            if entry.get("origin") == "native" or entry.get("subject", "person") != "person":
                continue
            fits |= set(entry.get("nationalities") or everyone)
        if fits:
            allowed &= fits
    return [n for n in everyone if n in allowed] or everyone


def _age_for_forced_clauses(rng: random.Random, forced_clauses: Sequence[str], spec: dict, form: str,
                            clause_bank: dict) -> Tuple[Optional[int], Optional[str]]:
    """Pick a subject age (and gender) that a forced age-restricted clause can use.

    AGE_INFO clauses are written for a minor or for someone over 75; an age drawn
    from the genre's working-age profile fits none of them, and the sampler
    dropped every forced AGE_INFO (24 of 24 in a measured run). The age comes from
    a fitting entry's own `age_range` instead. A minor is only chosen in a genre
    whose subject is a child: making an adult genre's subject six years old to
    place one clause would drop every other adult clause scheduled with it.

    Args:
        rng: Seeded RNG; consumed only when a forced clause is age-restricted.
        forced_clauses: Forced types that are clause types.
        spec: The genre spec.
        form: "nb" or "nn".
        clause_bank: Loaded clause bank.

    Returns:
        (age, gender) inside the genre's own subject range; gender is the one the
        chosen entry requires, if any. (None, None) when no forced clause
        restricts age.
    """
    genres = set(spec["clause_genres"])
    youth = spec.get("age_profile") == "youth"
    lo_clamp, hi_clamp = (6, 17) if youth else spec.get("subject_age", (18, 120))
    for etype in forced_clauses:
        ranged = [e for e in clause_bank.get(etype, [])
                  if e.get("age_range") and e.get("form") == form
                  and genres & set(e.get("genres", []))
                  and e["age_range"][0] <= hi_clamp and e["age_range"][1] >= lo_clamp
                  and (youth or e["age_range"][0] >= 18)]
        if ranged:
            entry = rng.choice(ranged)
            lo, hi = entry["age_range"]
            return rng.randint(max(lo, lo_clamp), min(hi, hi_clamp)), entry.get("gender")
    return None, None


_SHARED_RUN_WORDS = 6


def _shares_word_run(a: str, b: str, n: int = _SHARED_RUN_WORDS) -> bool:
    """Whether two texts have a run of `n` consecutive words in common."""
    def runs(text: str) -> Set[Tuple[str, ...]]:
        words = text.lower().split()
        return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}
    return bool(runs(a) & runs(b))


class NegativeLedger:
    """Counts how often each negative template is planted in one run.

    Pilot v4 planted 37 negatives in accepted documents and used 13 distinct
    texts; one was planted seven times. A model that sees the same sentence in
    every tenth document memorises it, and the near-miss stops being a trap and
    becomes a pattern. The ledger is the run-wide state `_plant_negatives` needs
    to keep any one text at or under `cap`: it is consulted when a record is
    sampled, and a retry hands back the previous attempt's claims first so a
    document that is regenerated does not use up its texts twice.

    Attributes:
        cap: Maximum plantings of one template in the run.
        used: Template -> plantings currently claimed.
    """

    def __init__(self, cap: int = dataset_mod.NEGATIVE_CAP_PER_RUN) -> None:
        self.cap = cap
        self.used: collections.Counter = collections.Counter()

    def available(self, template: str) -> bool:
        """Whether `template` may be planted once more."""
        return self.used[template] < self.cap

    def claim(self, template: str) -> None:
        """Record one planting of `template`."""
        self.used[template] += 1

    def release(self, negatives: Sequence["PlantedNegative"]) -> None:
        """Give back the claims of a record that is being replaced or discarded."""
        for neg in negatives:
            if self.used[neg.template] > 0:
                self.used[neg.template] -= 1
            if not self.used[neg.template]:
                del self.used[neg.template]

    def report(self) -> dict:
        """Return the distinct templates in use, the maximum reuse and the reuse histogram."""
        counts = [c for c in self.used.values() if c > 0]
        return {
            "cap": self.cap, "distinct_templates": len(counts), "plantings": sum(counts),
            "max_reuse": max(counts, default=0),
            "reuse_histogram": dict(sorted(collections.Counter(counts).items())),
        }


def _plant_negatives(rng: random.Random, plan: "DocPlan", spec: dict, person: Person, form: str,
                     clause_types: Set[str], negative_bank: dict,
                     literals: Sequence[str] = (),
                     ledger: Optional[NegativeLedger] = None) -> List[PlantedNegative]:
    """Choose the hard negatives to plant in one document.

    A negative is only planted where it reads as an ordinary sentence of the
    genre (its `genres` meet the genre's clause genres, its form, the
    subject's gender and age match) and never next to a real disclosure of the type it
    imitates: "nektet å oppgi om han er fagorganisert" in a document that also
    says he is a union member is a contradiction, not a near-miss. At most one
    negative per type, so a document does not read as a list of refusals.

    The text is filled from the subject (`{PRON}`, `{POSS}`, `{OBJ}`) before it
    is compared with the planned values or planted, so what the document must
    contain, what G2 searches for and what the metadata records are one string.
    Among the eligible texts the least-used ones come first, which spreads the
    plantings over the whole pool instead of letting chance repeat a text; a text
    already at the ledger's cap is not eligible, so the document falls back to a
    different text or plants fewer.

    Args:
        rng: Seeded RNG.
        plan: The document plan; `n_negatives` is how many to plant.
        spec: Genre spec.
        person: The data subject.
        form: "nb" or "nn".
        clause_types: Clause types this document already discloses.
        negative_bank: `{TYPE: [negative entries]}` for the active dataset.
        literals: The document's planned value strings. A negative that contains
            one is skipped: the value would be located inside the near-miss, and
            the near-miss would stop being unlabelled.
        ledger: The run's reuse ledger; None applies no cap. Chosen texts are
            claimed on it.

    Returns:
        The planted negatives, possibly fewer than requested.
    """
    genres = set(spec["clause_genres"])
    options: List[Tuple[str, dict, str]] = []
    for etype, entries in negative_bank.items():
        if etype in clause_types:
            continue
        # The same restriction as the ETHNICITY clause itself: a near-miss about a
        # name that "sounds foreign" in a clearance or a police report is the
        # origin-as-suspicion framing that restriction exists to prevent.
        if etype == "ETHNICITY" and plan.genre not in genres_mod.ETHNICITY_ALLOWED_GENRES:
            continue
        for entry in entries:
            if not entry.get("plantable") or entry.get("form") != form:
                continue
            if not genres & set(entry.get("genres", [])):
                continue
            if entry.get("gender") and entry["gender"] != person.gender:
                continue
            lo, hi = entry.get("age_range", [18, 120])
            if not lo <= person.age() <= hi:
                continue
            if ledger is not None and not ledger.available(entry["text"]):
                continue
            filled = dataset_mod.fill_pronouns(entry["text"], person.gender, form)
            if any(re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", filled)
                   for v in literals if len(v) >= 3):
                continue
            options.append((etype, entry, filled))
    chosen: List[PlantedNegative] = []
    used_types: Set[str] = set()
    rng.shuffle(options)
    if ledger is not None:
        options.sort(key=lambda option: ledger.used[option[1]["text"]])
    for etype, entry, filled in options:
        if len(chosen) >= plan.n_negatives:
            break
        if etype in used_types:
            continue
        # Two refusals that open alike ("men han ønsket ikke å svare på spørsmål om
        # ...") repeat a long word run inside one document, which G12 reads as the
        # model looping; the second is skipped for a different one.
        if any(_shares_word_run(filled, other.text) for other in chosen):
            continue
        used_types.add(etype)
        chosen.append(PlantedNegative(etype, filled, entry.get("why_not", ""),
                                      dict(entry.get("also_labelled") or {}), template=entry["text"]))
        if ledger is not None:
            ledger.claim(entry["text"])
    return chosen


def sample_record(
    rng: random.Random, doc_seed: int, plan: "DocPlan", strategy: str,
    taxonomy_index: Dict[str, dict], clause_bank: dict, public_figures: Set[str],
    negative_bank: Optional[dict] = None, difficulty_weights: Optional[Dict[str, float]] = None,
    dataset: str = "train", negative_ledger: Optional[NegativeLedger] = None,
) -> Record:
    """Sample a coherent, genre-realistic typed record for one document.

    Density is drawn from the plan's profile rather than fixed: a
    500-character note carries one or two types, a 6,000-character case file
    carries twenty-odd across several named parties, and about one document in
    twenty carries none at all. The planned type count is capped by
    `gendoc_genres.type_ceiling`, which scales with length and with the genre's
    own tolerance -- pilot v1's unusable document was 14 types in 1,600
    characters, which no ceiling would have allowed.

    Within a document, each party is internally coherent (one gender, one age
    that agrees with their own fødselsnummer, their own address), there is
    exactly one data subject, the address's postal code is the POSTAL_CODE, and
    an employer and role belong together. At most `plan.art9_cap` GDPR Art. 9
    categories appear.

    Args:
        rng: Seeded RNG for this attempt.
        doc_seed: The seed used to build this rng, recorded for reproducibility.
        plan: The document's batch plan: genre, variant, form, length band,
            density profile, type target, cast target, Art. 9 cap and any
            types coverage scheduling forced into it.
        strategy: "seeded" or "marked", applied to every clause-kind type.
        taxonomy_index: Type name -> taxonomy entry.
        clause_bank: Loaded clause bank dict.
        public_figures: Embedded set of real public figures, to reject collisions.
        negative_bank: `{TYPE: [negative entries]}` to plant `plan.n_negatives`
            hard negatives from; None plants none.
        difficulty_weights: Relative weight of a clause entry by `difficulty`;
            None draws uniformly.
        dataset: "train" or "benchmark", recorded on the record.
        negative_ledger: The run's reuse ledger for planted negatives; None
            applies no cap.

    Returns:
        A `Record` with `planned` fully populated (empty for a PII-free plan).
        `dropped_forced` lists scheduled types the sampler could not place.
    """
    genre, form, length_band = plan.genre, plan.form, plan.length_band
    spec = genres_mod.GENRES[genre]
    label = lambda t: genres_mod.field_label(t, form)  # noqa: E731

    if plan.pii_free:
        return Record(doc_seed, genre, plan.variant, form, length_band, None, [], [],
                      profile=plan.profile, pii_free=True, dataset=dataset)

    is_clause_type = lambda t: taxonomy_index.get(t, {}).get("value_kind") == "clause"  # noqa: E731
    foreign = rng.random() < spec.get("foreign_subject_p", 0.0)
    foreign = foreign or bool(set(plan.forced_types) & genres_mod.FOREIGN_SUBJECT_TYPES)
    minor = rng.random() < spec.get("minor_subject_p", 0.0)
    # A scheduled firearms licence outranks the genre's chance of a child subject:
    # dropping the forced type would only cost the batch its coverage of it.
    minor = minor and not set(plan.forced_types) & genres_mod.ADULT_ONLY_TYPES
    nationality = "norsk"
    if foreign:
        compatible = _nationalities_hosting(
            [t for t in plan.forced_types if is_clause_type(t)], spec, form, clause_bank)
        compatible = [n for n in compatible if n != "svensk"] or compatible
        nationality = rng.choice(compatible)
    age_profile = spec.get("age_profile", "adult")
    forced_age, forced_gender = _age_for_forced_clauses(
        rng, [t for t in plan.forced_types if is_clause_type(t)], spec, form, clause_bank)
    person = _resample_until_no_collision(
        rng, public_figures, nationality=nationality, age_profile=age_profile,
        age=rng.randint(13, 17) if minor else forced_age, gender=forced_gender,
        age_clamp=spec.get("subject_age"),
    )
    status = None
    if genre in _EMPLOYED_SUBJECT_GENRES:
        status = "employed"
    elif person.age() > 67:
        status = "retired"
    subject = _Subject(person, genre, form, set(spec["clause_genres"]), status=status,
                       animal_types=set(spec.get("animal_types", ())))
    street_address, postal, place = _address(rng)

    signatory = None
    signatory_role = None
    if rng.random() < 0.75:
        signatory = _resample_until_no_collision(rng, public_figures, age_profile="professional")
        signatory_role = rng.choice(spec["signatory_roles"])[0 if form == "nb" else 1]

    ceiling = genres_mod.type_ceiling(length_band[1], spec.get("density_factor", 1.0))
    target = max(1, min(plan.type_target, ceiling))

    def _clause_types_ok(etype: str) -> bool:
        if taxonomy_index.get(etype, {}).get("value_kind") != "clause":
            return etype in taxonomy_index and etype in _VALUE_KIND_TYPES and _value_fits(etype)
        if etype == "ETHNICITY" and genre not in genres_mod.ETHNICITY_ALLOWED_GENRES:
            return False
        if etype == "EMPLOYMENT" and minor:
            return False
        if etype == "EMPLOYMENT":
            return True
        if etype == "IMMIGRATION_STATUS" and not subject.foreign:
            return False
        return any(_clause_fits(e, subject, etype) for e in clause_bank.get(etype, []))

    def _value_fits(etype: str) -> bool:
        if etype in genres_mod.ADULT_ONLY_TYPES and person.age() < 18:
            return False
        return not (etype == "VISA_NUMBER" and not subject.foreign)

    # Both lists hold *types*, appended once per type however many instances `_add_instances`
    # adds afterwards, so the Art. 9 cap and the health-family cap count categories: three HEALTH
    # findings use one health-family slot, and a typical document (cap 1) cannot also carry a
    # MEDICATION clause.
    special_used = [t for t in spec["core"] if t in genres_mod.SPECIAL_CATEGORIES]
    health_used = [t for t in spec["core"] if t in genres_mod.HEALTH_FAMILY]
    health_cap = genres_mod.health_family_cap(plan.profile)

    def _allowed(etype: str) -> bool:
        if etype in genres_mod.SPECIAL_CATEGORIES and len(special_used) >= plan.art9_cap:
            return False
        if etype in genres_mod.HEALTH_FAMILY and len(health_used) >= health_cap:
            return False
        ok = _clause_types_ok(etype)
        if ok and etype in genres_mod.SPECIAL_CATEGORIES:
            special_used.append(etype)
        if ok and etype in genres_mod.HEALTH_FAMILY:
            health_used.append(etype)
        return ok

    # A short document keeps the part of the core that makes it the genre it is:
    # PERSON, then whatever judgement type the genre is about, then the
    # identifying fields. Truncating the core in list order would leave a GP
    # referral that mentions no health fact at all.
    core_all = list(spec["core"])
    core_ranked = (
        [t for t in core_all if t == "PERSON"]
        + [t for t in core_all if t != "PERSON"
           and taxonomy_index.get(t, {}).get("value_kind") == "clause"]
        + [t for t in core_all if t != "PERSON"
           and taxonomy_index.get(t, {}).get("value_kind") != "clause"]
    )
    core = [t for t in core_ranked[:target] if _clause_types_ok(t) or t in {"PERSON"}]
    for t in core:
        if t in genres_mod.SPECIAL_CATEGORIES and t not in special_used:
            special_used.append(t)

    # A forced identifier and a forced judgement clause compete for different
    # room: coverage scheduling puts up to eight Tier A types into a case file,
    # and counting them against the judgement budget left such a document with
    # one clause-level type, which is the opposite of what the judgement types
    # need. They are budgeted separately.
    is_clause = is_clause_type
    judgement: List[str] = []
    forced_values: List[str] = []
    for etype in plan.forced_types:
        if etype in core or etype in judgement or etype in forced_values:
            continue
        if not _allowed(etype):
            continue
        (judgement if is_clause(etype) else forced_values).append(etype)
    n_judgement = max(0, min(int(round(target * 0.35)) + rng.randint(-1, 1), 9))
    remaining = {t: w for t, w in spec["judgement"].items() if t not in judgement and t not in core}
    judgement += _weighted_pick(rng, remaining, max(0, n_judgement - len(judgement)), _allowed)
    # A type the plan asks for several instances of is part of this document, not left to the
    # weighted draw; it still has to pass the Art. 9 and health-family budgets (which count
    # the category once however many instances follow) and the subject's coherence.
    for etype in sorted(plan.instances):
        if (is_clause(etype) and etype not in core and etype not in judgement
                and etype not in forced_values and len(core) + len(judgement) < ceiling and _allowed(etype)):
            judgement.append(etype)

    pair_employer = genre in _EMPLOYED_SUBJECT_GENRES or rng.random() < 0.4
    extra_org = int("EMPLOYMENT" in judgement and pair_employer and "ORGANIZATION" not in core)
    room = target - len(core) - len(judgement) - len(forced_values) - extra_org
    value_weights = {t: w for t, w in spec["values"].items()
                     if t not in core and t not in judgement and t not in forced_values}
    values = forced_values + _weighted_pick(rng, value_weights, max(0, room),
                                            lambda t: t in _VALUE_KIND_TYPES or t == "PERSON")

    chosen = core + [t for t in values if t not in core] + judgement
    # The plan's identification block (address and postal code) is part of how a letter or
    # decision about a named person opens, so it is added to the chosen types rather than
    # competing with them for the type target.
    chosen += [t for t in plan.id_block if t not in chosen and t in _VALUE_KIND_TYPES and _value_fits(t)]
    order = {t: i for i, t in enumerate(_SAMPLING_ORDER)}
    clause_types = sorted(
        [t for t in chosen if taxonomy_index.get(t, {}).get("value_kind") == "clause"],
        key=lambda t: order.get(t, len(order)),
    )

    planned: List[PlannedValue] = []
    tier = lambda t: taxonomy_index[t]["tier"]  # noqa: E731

    # A place name inside an organisation's own name is not a LOCATION
    # (ANNOTATION_SPEC), and the labeller marks every occurrence of a planned place
    # string, so an employer named after the subject's town is not generated when
    # the town is itself a planned LOCATION.
    employer_place = None if "LOCATION" in chosen else place
    employer: Optional[str] = None
    employer_roles: List[Tuple[str, str]] = []
    if "ORGANIZATION" in chosen or ("EMPLOYMENT" in chosen and pair_employer
                                    and subject.status != "retired"):
        employer, employer_roles = _employer(rng, employer_place)
        if "EMPLOYMENT" in chosen and "ORGANIZATION" not in chosen:
            chosen.append("ORGANIZATION")

    clause_texts: Dict[str, dict] = {}
    for etype in clause_types:
        if etype == "EMPLOYMENT" and employer:
            role = rng.choice(employer_roles)[0 if form == "nb" else 1]
            employed_word = "ansatt" if form == "nb" else "tilsett"
            text = rng.choice([role, f"{employed_word} som {role}", f"fast {employed_word} som {role}"])
            subject.status = "employed"
            clause_texts[etype] = {"text": text, "difficulty": "easy", "role_value": True}
            continue
        candidates = [e for e in clause_bank.get(etype, []) if _clause_fits(e, subject, etype)]
        if not candidates:
            continue
        entry = _weighted_entry(rng, candidates, difficulty_weights)
        _commit_entry(subject, etype, entry)
        clause_texts[etype] = entry

    profile_cast = genres_mod.PROFILES[plan.profile]["cast"]
    n_cast = min(rng.randint(*profile_cast), len(spec.get("cast_roles", [])) + 2)
    cast_pool = list(spec.get("cast_roles", []))
    rng.shuffle(cast_pool)
    cast: List[Tuple[str, Person]] = []
    for role in cast_pool[:n_cast]:
        cast.append((role, _cast_person(rng, role, person, public_figures, age_profile)))
    # A planned HPR number belongs to a clinician. When the document has neither a clinical
    # signatory nor a clinician in its cast, one is added rather than giving the number to
    # the patient.
    author_is_clinician = bool(signatory) and (signatory_role or "") in _CLINICAL_TITLES
    if ("MEDICAL_LICENSE" in chosen and not author_is_clinician
            and not any(role in _CLINICIAN_ROLES for role, _p in cast)):
        clinician_role = "veterinarian" if spec.get("domain") == "veterinary" else "physician"
        cast.append((clinician_role, _cast_person(rng, clinician_role, person, public_figures, age_profile)))

    # The cast is drawn from each role's natural distribution and then held to the rules of
    # `gendoc_coherence` (professionals 25-67, no living parent past 100, a child at least 16
    # years younger, a spouse of a possible age) before any value is generated for them, so
    # a violating plan is repaired here and costs no model call.
    roster = ([coherence.Member("author", signatory.age())] if signatory else []) \
        + [coherence.Member(role, member.age()) for role, member in cast]
    repaired, coherence_report = coherence.enforce_cast(person.age(), roster, rng)
    if signatory:
        author_fixed, repaired = repaired[0], repaired[1:]
        if author_fixed is not None and author_fixed.age != signatory.age():
            signatory = _with_age(signatory, author_fixed.age, rng)
    parties: List[Party] = [Party(person, None, "hovedpersonen", is_subject=True)]
    if signatory:
        parties.append(Party(signatory, "author", signatory_role or "saksbehandler", staff=True))
    for (role, member), fixed in zip(cast, repaired):
        if fixed is None:
            continue
        if fixed.age != member.age():
            member = _with_age(member, fixed.age, rng)
        parties.append(Party(member, fixed.role, genres_mod.CAST_ROLES[fixed.role][form],
                             staff=fixed.role in _STAFF_ROLES))

    date_lo, date_hi = genres_mod.PROFILES[plan.profile]["dates"]

    plate_contrast_wanted = False
    for etype in chosen:
        entry = taxonomy_index.get(etype)
        if entry is None:
            continue
        if etype == "PERSON":
            for party in parties:
                hint = ("hovedpersonen" if party.is_subject
                        else (f"{party.label}, som skriver dokumentet" if party.role == "author"
                              else f"{party.label} i saken"))
                planned.append(PlannedValue("PERSON", tier(etype), "value", party.person.full_name,
                                            None, label(etype), hint=hint,
                                            party=None if party.is_subject else party.role))
            continue
        if etype == "ADDRESS":
            in_block = "ADDRESS" in plan.id_block
            planned.append(PlannedValue(
                etype, tier(etype), "value", street_address, None, label(etype),
                hint=("hovedpersonens bostedsadresse, som hører hjemme i identifikasjonsblokken i begynnelsen "
                      "av dokumentet" if in_block else "hovedpersonens bostedsadresse")))
            continue
        if etype == "POSTAL_CODE":
            planned.append(PlannedValue(etype, tier(etype), "value", postal, None, label(etype),
                                        hint=f"postnummeret i hovedpersonens adresse ({place})"))
            continue
        if etype == "LOCATION":
            planned.append(PlannedValue(etype, tier(etype), "value", place, None, label(etype),
                                        hint="stedet der hovedpersonen bor"))
            continue
        if etype == "ORGANIZATION":
            if employer is None:
                employer, employer_roles = _employer(rng, employer_place)
            planned.append(PlannedValue(
                etype, tier(etype), "value", employer, None, label(etype),
                hint=("en virksomhet nevnt i saken, ikke hovedpersonens arbeidsgiver"
                      if person.age() < 18 else "hovedpersonens arbeidsgiver")))
            continue
        if etype == "NATIONALITY":
            planned.append(PlannedValue(etype, tier(etype), "value", person.nationality, None,
                                        label(etype), hint="hovedpersonens statsborgerskap"))
            continue
        if etype == "MARITAL_STATUS":
            continue  # filled in after the clauses, from whatever they imply
        if etype == "NATIONAL_ID":
            idf = ident.fodselsnummer(rng, person.birth_date, person.gender, valid=True,
                                      dnummer=subject.foreign and rng.random() < 0.6)
            planned.append(PlannedValue(etype, tier(etype), "value", idf.value, None, label(etype),
                                        idf.valid, hint="hovedpersonens"))
            continue
        if etype == "CASE_NUMBER":
            for k in range(1 if plan.profile != "case_file" else rng.randint(1, 2)):
                hint = "saksnummeret" if k == 0 else "et henvist saksnummer i en tilknyttet sak"
                planned.append(PlannedValue(etype, tier(etype), "value", ident.case_number(rng),
                                            None, label(etype), hint=hint))
            continue
        if etype == "DATE_TIME":
            n_dates = max(1, rng.randint(date_lo, date_hi) if date_hi else 1)
            offsets = sorted(rng.sample(range(1, 900), min(n_dates, 8)))
            hints = ["dokumentets dato", "dato for hendelsen eller vedtaket saken gjelder",
                     "dato for et tidligere møte eller brev i saken",
                     "dato for en tidligere kontakt i saken", "dato for en frist i saken",
                     "dato for en undersøkelse i saken", "dato for et tidligere vedtak",
                     "dato for en samtale i saken"]
            for k, off in enumerate(offsets):
                planned.append(PlannedValue(etype, tier(etype), "value",
                                            _format_date(rng, REFERENCE_DATE - timedelta(days=off)),
                                            None, label(etype), hint=hints[k % len(hints)]))
            continue
        if etype in clause_texts:
            chosen_entry = clause_texts[etype]
            text = chosen_entry["text"]
            if chosen_entry.get("role_value"):
                planned.append(PlannedValue(etype, tier(etype), "value", text, None, "Stilling",
                                            hint=f"hovedpersonens stilling hos {employer}"))
                continue
            if strategy == "seeded":
                text, introduced_names = localize_clause_names(rng, text, public_figures)
                for name in introduced_names:
                    planned.append(PlannedValue("PERSON", "B", "value", name, None, label("PERSON"),
                                                hint="person nevnt i en av opplysningene"))
                text, nested_ids = localize_clause_ids(rng, text)
                for id_type, id_value in nested_ids:
                    planned.append(PlannedValue(id_type, tier(id_type), "value", id_value, None,
                                                label(id_type),
                                                hint="saksnummeret i opplysningen over; skrives bare der"))
            # A civil-status clause with no kinship noun ("gift med Kari Hansen") is
            # MARITAL_STATUS, not FAMILY_RELATION; the bank marks such entries.
            as_type = chosen_entry.get("as_type", etype)
            planned.append(PlannedValue(
                as_type, tier(as_type), "clause", text if strategy == "seeded" else None,
                strategy, label(as_type), difficulty=chosen_entry.get("difficulty"),
                topic=chosen_entry.get("topic"),
            ))
            continue
        if entry.get("value_kind") == "clause":
            continue  # no coherent clause for this subject; drop rather than contradict
        try:
            value, checksum_valid = _generate_value_kind(etype, rng, person, invalid_rate=0.0)
        except KeyError:
            continue
        hint = None
        field = label(etype)
        holder_role = None
        if etype == "MEDICAL_LICENSE":
            holder = _licence_holder(parties, signatory_role)
            if holder is None:
                continue
            hint = f"HPR-nummeret til {holder.person.full_name} ({holder.label}), ikke hovedpersonens"
            holder_role = holder.role
        elif etype == "DEVICE_ID":
            hint = ("enhetsidentifikatoren til en enhet som tilhører hovedpersonen – aldri avsenderens egen; "
                    "skriv aldri «vår» eller «vårt» foran den")
        elif etype == "IP_ADDRESS":
            hint = "IP-adressen hovedpersonens tilkobling kom fra – aldri avsenderens egen"
        elif etype == "USERNAME":
            hint = "hovedpersonens brukernavn – aldri avsenderens eget"
        elif etype == "ORG_NUMBER" and employer:
            hint = f"organisasjonsnummeret til {employer}"
        elif etype == "FIREARMS_LICENSE":
            field = genres_mod.field_label_variant(rng, etype, form)
            if ident.is_plate_shaped_firearms(value):
                # A plate-shaped number is only a firearms number by its label (B20).
                field = rng.choice(["Våpenkortnummer", "Lisensnummer"])
                plate_contrast_wanted = True
            hint = (f"hovedpersonens våpenkort- eller lisensnummer for {ident.firearm_description(rng, form)}; "
                    "våpenet kan beskrives i teksten, men beskrivelsen er ikke en del av nummeret")
        elif etype == "VESSEL_REGISTRATION":
            field = genres_mod.field_label_variant(rng, etype, form)
            hint = (f"registreringsmerket til {ident.vessel_description(rng, form)}, som hovedpersonen eier; "
                    "fartøyets navn kan nevnes i teksten, men er ikke en del av merket")
        planned.append(PlannedValue(etype, tier(etype), "value", value, None, field,
                                    checksum_valid, hint=hint, party=holder_role))

    # A plate-shaped firearms number teaches "label decides" best with a real road
    # plate in the same document to contrast it with.
    if (plate_contrast_wanted and rng.random() < 0.5
            and not any(pv.type == "LICENSE_PLATE" for pv in planned)):
        planned.append(PlannedValue("LICENSE_PLATE", tier("LICENSE_PLATE"), "value",
                                    ident.vehicle_reg(rng), None, label("LICENSE_PLATE"),
                                    None, hint="registreringsnummeret til hovedpersonens bil"))

    if "MARITAL_STATUS" in chosen and not any(pv.type == "MARITAL_STATUS" for pv in planned):
        marital = subject.marital
        if not marital:
            options = ["ugift", "gift", "skilt", "samboer"]
            if person.age() >= 55:
                options.append("enke" if person.gender == "F" else "enkemann")
            marital = rng.choice(options if person.age() >= 20 else ["ugift"])
        hint = "hovedpersonens sivilstand"
        spouse = next((p for p in parties if p.role == "spouse"), None)
        # ANNOTATION_SPEC: the bare word is right for a `Sivilstand:` field, but
        # when the text names the partner the span is "gift med Kari Hansen" with
        # the name also a PERSON. Both forms are generated.
        if spouse and marital in ("gift", "samboer") and rng.random() < 0.5:
            marital = f"{marital} med {spouse.person.full_name}"
            hint = "hovedpersonens sivilstand, skrevet som en frase med navnet på partneren"
        planned.append(PlannedValue("MARITAL_STATUS", tier("MARITAL_STATUS"), "value", marital, None,
                                    label("MARITAL_STATUS"), hint=hint))

    # Cast members bring their own values. This is where a case file's many
    # distinct spans come from: the output format is {TYPE: [unique spans]}, so
    # five people each with a fødselsnummer is one type and five spans. A
    # member's value type is added even when the type is new, but only while
    # the document stays under its length-and-genre ceiling.
    planned_types = {pv.type for pv in planned}
    for party in parties:
        if party.is_subject or party.role in (None, "author"):
            continue
        role_values = list(genres_mod.CAST_ROLES[party.role]["values"])
        rng.shuffle(role_values)
        n_values = rng.randint(1, 3) if plan.profile in ("dense", "case_file") else rng.randint(0, 2)
        for etype in role_values[:n_values]:
            if etype not in taxonomy_index or etype not in _VALUE_KIND_TYPES:
                continue
            if party.person.age() < 15 and etype in _NOT_FOR_YOUNG_CHILDREN:
                continue
            if etype not in planned_types and len(planned_types) >= ceiling:
                continue
            if etype == "MEDICAL_LICENSE" and any(
                    pv.type == "MEDICAL_LICENSE" and pv.party == party.role for pv in planned):
                continue  # one clinician, one HPR number
            if etype == "ORGANIZATION":
                value, checksum_valid = _employer(rng, employer_place)[0], None
            else:
                try:
                    value, checksum_valid = _generate_value_kind(
                        etype, rng, party.person, invalid_rate=0.0, staff=party.staff)
                except KeyError:
                    continue
            planned_types.add(etype)
            planned.append(PlannedValue(
                etype, tier(etype), "value", value, None, genres_mod.field_label(etype, form),
                checksum_valid, hint=f"tilhører {party.label} {party.person.full_name}",
                party=party.role))

    # Further instances of the repeatable types, from their own RNG stream so that a document
    # planned at one of everything is sampled exactly as it was before instances existed.
    if strategy == "seeded" and plan.instances:
        _add_instances(random.Random(doc_seed ^ 0x1257), plan, planned, clause_texts, subject, clause_bank,
                       public_figures, difficulty_weights, form, tier, label)

    negatives: List[PlantedNegative] = []
    if plan.n_negatives and negative_bank:
        literals = [pv.value for pv in planned if pv.value]
        negatives = _plant_negatives(rng, plan, spec, person, form, set(clause_texts), negative_bank,
                                     literals, negative_ledger)
    realised = {pv.type for pv in planned}
    dropped = [t for t in plan.forced_types if t not in realised]
    per_type = collections.Counter(pv.type for pv in planned if pv.type in genres_mod.MULTI_INSTANCE_TYPES)
    return Record(doc_seed, genre, plan.variant, form, length_band, person, parties, planned,
                  signatory_role=signatory_role, employer=employer, profile=plan.profile,
                  dataset=dataset, planted_negatives=negatives, dropped_forced=dropped,
                  instances_planned=dict(plan.instances),
                  instances_realised={t: n for t, n in per_type.items() if n >= 2},
                  coherence=coherence_report.as_dict())


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_GENRE_INSTRUCTIONS_NB = (
    "Du skriver et offisielt norsk dokument av typen '{title}'. "
    "Form: {variant_desc}. "
    "Skriv utelukkende på {form_name}, med korrekt og naturlig register for en norsk "
    "offentlig etat eller virksomhet. Dokumentet skal være mellom {min_len} og {max_len} tegn "
    "langt, og aldri lengre enn {max_len} tegn."
)
_GENRE_INSTRUCTIONS_NN = (
    "Du skriv eit offisielt norsk dokument av typen '{title}'. "
    "Form: {variant_desc}. "
    "Skriv utelukkande på {form_name}, med korrekt og naturleg register for eit norsk "
    "offentleg organ eller ei verksemd. Dokumentet skal vere mellom {min_len} og {max_len} teikn "
    "langt, og aldri lengre enn {max_len} teikn."
)

_VARIANT_DESC = {
    "field_header": "et brev eller skjema som åpner med en kort identifikasjonsblokk på høyst fem "
                    "linjer med feltoverskrifter (hovedpersonens navn, nummer, adresse, saksnummer, "
                    "dato), etterfulgt av en fritekstdel i hele setninger",
    "prose_letter": "et sammenhengende brev med hilsen og løpende prosa",
    "numbered_findings": "nummererte avsnitt med funn og vurderinger, hvert avsnitt i hele setninger",
    "table_summary": "en tabell på høyst tre rader med hovedpersonens navn, nummer og dato, "
                     "etterfulgt av en vurdering i løpende tekst",
    "minutes": "et møtereferat der hvert punkt er skrevet som hele setninger",
}

_PRONOUNS = {
    ("F", "nb"): "hun / henne / hennes", ("M", "nb"): "han / ham / hans",
    ("F", "nn"): "ho / henne / hennar", ("M", "nn"): "han / han / hans",
}

# A negative written in the first person ("min seksuelle legning er privat") reads
# as a mistake inside third-person prose; the prompt asks for it as a quotation.
_FIRST_PERSON_RE = re.compile(r"(?:jeg|eg|min|mi|mitt|meg)\b", re.IGNORECASE)

_POSITION_HINTS = [
    "tidlig i dokumentet", "i begrunnelsen eller vurderingen", "mot slutten",
    "midt i en lengre setning", "som del av bakgrunnen for saken",
]


def build_prompt(record: Record, rng: Optional[random.Random] = None) -> str:
    """Build the generation prompt, plus a manifest for the mock backend after a sentinel.

    Judgement clauses are listed without their type name and with a request
    to weave them into running prose: the pilot's prompt listed each clause
    as `(HEALTH): ...` and the model responded with tables whose row labels
    named the category, which teaches position and label instead of language.
    The machine-readable manifest (`VALUE|...`, `CLAUSE_SEEDED|...`) sits after
    `MANIFEST_SENTINEL`; the HF backend cuts it off before the model sees it,
    and the mock backend reads only it.

    Args:
        record: The sampled record to realise as a document.
        rng: RNG for clause order and position hints; defaults to one seeded
            from the record's seed so prompts are reproducible.

    Returns:
        The full prompt string.
    """
    rng = rng or random.Random(record.doc_seed ^ 0x5EED)
    genre_spec = genres_mod.GENRES[record.genre]
    nb = record.form == "nb"
    title = genre_spec["title_nb"] if nb else genre_spec["title_nn"]
    template = _GENRE_INSTRUCTIONS_NB if nb else _GENRE_INSTRUCTIONS_NN
    header = template.format(
        title=title, variant_desc=_VARIANT_DESC[record.variant],
        form_name="bokmål" if nb else "nynorsk",
        min_len=record.length_band[0], max_len=record.length_band[1],
    )
    # Models count words far better than characters: the pilot and the first
    # smoke run overshot character targets by 20-40%. Generated Norwegian
    # averages ~6.5 characters per word; the word ceiling is set a little
    # under the band so the usual overshoot still lands inside it.
    lo_words = max(40, round(record.length_band[0] / 6.5 / 10) * 10)
    hi_words = max(lo_words + 20, round(record.length_band[1] * 0.85 / 6.5 / 10) * 10)
    header += (f" Det betyr omtrent {lo_words}–{hi_words} ord; skriv aldri mer enn {hi_words} ord."
               if nb else f" Det tyder om lag {lo_words}–{hi_words} ord; skriv aldri meir enn {hi_words} ord.")
    if record.pii_free:
        return _build_pii_free_prompt(record, header)

    subject_line = _subject_line(record)
    manifest = [f"SEED|{record.doc_seed}", f"META|form={record.form}"]
    value_lines, clause_lines, negative_lines, item_manifest, marked = _item_blocks(
        record, record.planned, record.planted_negatives, rng)
    manifest += item_manifest
    planned_types = {pv.type for pv in record.planned}
    rules = _prompt_rules(record, planned_types, marked, negatives=bool(record.planted_negatives))

    prompt = f"{header}\n\n{subject_line}\n\nVerdier som skal stå ordrett:\n" + "\n".join(value_lines)
    if clause_lines:
        prompt += ("\n\nOpplysninger som skal stå ordrett inne i løpende setninger:\n"
                   + "\n".join(clause_lines))
    if negative_lines:
        prompt += _NEGATIVE_INTRO + "\n".join(negative_lines)
    prompt += "\n\nRegler:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    return prompt + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


# The pilot-v5 wording said every negative "begynner med liten forbokstav og skal stå midt i
# en setning, etter en hovedsetning eller et komma", and every bank text opened with "og" or
# "men", so the model glued negatives into run-ons and the fixed opening was a surface mark of
# a trap. A negative is now a clause with its own subject: the model writes it as a sentence
# of its own (capitalising the first letter) or builds it into a longer one.
_NEGATIVE_INTRO = (
    "\n\nNøytrale formuleringer som også skal stå ordrett. "
    "De sier ikke noe om personens helse, tro, tilhørighet, opprinnelse, seksualitet "
    "eller straffbare forhold. Utdyp dem ikke, forklar dem ikke og knytt dem ikke til "
    "noen diagnose, medlemskap eller lovbrudd. Har en formulering eget subjekt («han», «hun», «ho», "
    "«naboen»), kan den stå som en egen setning (da skriver du første bokstav med stor bokstav, resten "
    "ordrett) eller bygges inn i en lengre setning. «han», «hun» og «ho» i formuleringene er hovedpersonen. "
    "Begynner en formulering med et verb, er hovedpersonen subjektet: sett «han», «hun» eller «ho» rett "
    "foran. Hver formulering skal stå i sin egen setning:\n")

_NEGATIVE_PLACEMENT_RULE = (
    "Hver nøytral formulering står i en setning for seg. Bind aldri to nøytrale formuleringer, eller en "
    "nøytral formulering og en opplysning fra listen, sammen i én setning med «og», «men» eller «samt», og "
    "gjenta ingen formulering. Skriv aldri at en nøytral formulering er relevant, viktig, påfallende, "
    "mistenkelig eller av betydning for saken, vurderingen eller personens troverdighet: den står som en "
    "vanlig, uviktig opplysning.")


def _subject_line(record: Record) -> str:
    """Describe the data subject, the signatory, the employer and the cast for a prompt.

    Shared by the whole-document prompt and every section prompt: a section is
    written without seeing the other sections' lists, so it needs the same facts
    about who the document is about (name, gender and pronouns, age, role) to stay
    coherent with them.
    """
    person = record.person
    gender_word = ("kvinne" if person.gender == "F" else "mann")
    subject_line = (
        f"Hovedpersonen er {person.full_name}, {gender_word}, {person.age()} år. "
        f"Omtal hovedpersonen med pronomenene {_PRONOUNS[(person.gender, record.form)]}"
        + (" – aldri «han»." if person.gender == "F" else " – aldri «hun»/«ho».")
    )
    author = next((p for p in record.parties if p.role == "author"), None)
    if record.signatory_role and author:
        subject_line += (f" Dokumentet er skrevet og signert av {author.person.full_name} "
                         f"({record.signatory_role}).")
    if record.employer:
        subject_line += f" Hovedpersonens arbeidsgiver er {record.employer}; ingen annen virksomhet er involvert."
    cast = [p for p in record.parties if not p.is_subject and p.role != "author"]
    if cast:
        listed = "; ".join(
            f"{p.person.full_name} ({p.label}, {'kvinne' if p.person.gender == 'F' else 'mann'}, "
            f"{p.person.age()} år)" for p in cast
        )
        subject_line += (f" Andre personer som er nevnt i saken: {listed}. "
                         "Bruk bare disse navnene, og bare om disse personene.")
    return subject_line


def _item_blocks(record: Record, planned: Sequence[PlannedValue],
                 negatives: Sequence[PlantedNegative], rng: random.Random):
    """Format planned items and planted negatives as prompt lines plus mock-manifest lines.

    Args:
        record: The record (only its strategy-independent facts are used).
        planned: The planned values and clauses to list, in order.
        negatives: The planted negatives to list.
        rng: RNG for clause order and position hints.

    Returns:
        `(value_lines, clause_lines, negative_lines, manifest_lines, marked)`
        where `marked` says whether any clause uses the marked strategy.
    """
    value_lines, clause_lines, negative_lines, manifest = [], [], [], []
    marked = False
    for pv in planned:
        if pv.value_kind == "value":
            # The value leads and its kind trails, so the list does not read as a
            # `Label: value` table the model would copy: pilot v3 mirrored the
            # old `- Fødselsnummer: ...` lines into a 33-row table.
            hint = f" ({pv.hint})" if pv.hint else ""
            value_lines.append(f"- «{pv.value}» – {pv.field_label.lower()}{hint}")
            manifest.append(f"VALUE|{pv.type}|{pv.value}")
        elif pv.strategy == "seeded":
            clause_lines.append(f"- «{pv.value}» – {rng.choice(_POSITION_HINTS)}")
            manifest.append(f"CLAUSE_SEEDED|{pv.type}|{pv.value}")
        else:
            marked = True
            clause_lines.append(
                f"- Skriv en egen setning om {pv.type} og merk den slik: ⟦{pv.type}: <din setning>⟧"
            )
            manifest.append(f"CLAUSE_MARKED|{pv.type}")
    rng.shuffle(clause_lines)
    for neg in negatives:
        hint = ("som et direkte sitat fra personen selv, i anførselstegn"
                if _FIRST_PERSON_RE.match(neg.text) else rng.choice(_POSITION_HINTS))
        negative_lines.append(f"- «{neg.text}» – {hint}")
        manifest.append(f"NEGATIVE|{neg.type}|{neg.text}")
    return value_lines, clause_lines, negative_lines, manifest, marked


def _prompt_rules(record: Record, planned_types: Set[str], marked: bool, *,
                  first_part: bool = True, section: bool = False,
                  items: Optional[Sequence[PlannedValue]] = None, negatives: bool = False) -> List[str]:
    """Return the numbered rules of a generation prompt.

    Every rule a whole-document prompt carries is carried by a section prompt too:
    no added personal facts, no tables, no category labels, clauses never extended.
    What changes with a section is scope -- the identification block belongs to the
    first section alone, the "no case number" rules follow the section's own types,
    and the model is told to write only this part.

    Args:
        record: The record.
        planned_types: Types of the items this prompt asks for.
        marked: Whether any clause is a marked one.
        first_part: False for a section after the first, which opens no
            identification block.
        section: True for a section prompt.
        items: The planned items this prompt lists; the rule about several clauses of one
            kind is given only when this prompt lists two of them. None means the whole record.
        negatives: Whether this prompt lists planted negatives, which adds the placement rule.

    Returns:
        The rules in order, without numbering.
    """
    named = ", ".join(p.person.full_name for p in record.parties) or "ingen"
    # The labels the identification block names, in the document's own form: a Nynorsk
    # document that is told «Navn:» writes «Navn:» (pilot v4's Nynorsk headers did).
    labels = ", ".join(f"«{genres_mod.field_label(t, record.form)}:»"
                       for t in ("PERSON", "NATIONAL_ID", "ADDRESS", "CASE_NUMBER", "DATE_TIME"))
    rules = [
        "ALLE oppgitte verdier og opplysninger skal brukes ORDRETT, tegn for tegn, uten omskriving "
        "eller endret bøyning.",
        "Opplysningene om personene skal flettes inn i vanlige, hele setninger i brødteksten – "
        "ikke i tabeller, ikke som punkter i en liste og ikke rett etter en feltetikett eller overskrift"
        + (" (unntaket er den lille identifikasjonsblokken beskrevet nedenfor). " if first_part else ". ")
        + "Ingen overskrift eller etikett i dokumentet får nevne hva slags opplysning det er "
        "(for eksempel helse, atferd, religion, fagforening, seksuell legning, økonomi, familie, etnisitet).",
        f"Navngi ingen andre enn disse: {named}. Skriv ikke om denne regelen i dokumentet. "
        "Ikke finn på andre personnavn, "
        "fødselsnumre, telefonnumre, e-postadresser, adresser, postnumre, kontonumre eller "
        "virksomheter enn de som er oppgitt. Andre personer omtales bare med rolle "
        "(«saksbehandleren», «naboen», «legen») og uten navn.",
        "Ikke bruk andre datoer enn de oppgitte. Trenger du å vise til tid uten at en dato er "
        "oppgitt, skriv «samme dag» eller «tre uker senere» inne i en setning – aldri som verdien "
        "i et datofelt og aldri etter en overskrift som «Dato».",
        "Ikke bruk plassholdere som [NAVN] eller [DATO], og ikke skriv noe på engelsk.",
    ]
    if first_part:
        rules.append(
            "Dokumentet kan åpne med én liten identifikasjonsblokk på høyst fem linjer. Hver linje har en "
            f"etikett som sier hva verdien er ({labels}), og blokken har bare hovedpersonens egne "
            "verdier fra listen ovenfor. Står hovedpersonens adresse i listen, hører den hjemme i blokken. Finn ikke på "
            "et saksnummer eller en referanse som ikke står i listen, og sett aldri et nummer under "
            "etiketten for en annen slags nummer (et tjenestenummer eller en enhetsidentifikator er "
            "aldri et saksnummer). Alt annet – andre personers navn og nummer, telefon, e-post, "
            "kontonumre, datoer, virksomheter – står i løpende setninger, i signaturen eller i en "
            "kontaktlinje på slutten av brevet. Aldri en tabell eller liste med flere enn fem rader, og "
            "ingen tabell for noe annet enn identifikasjon.")
    else:
        rules.append(
            "Denne delen har ingen identifikasjonsblokk, ingen tabell og ingen liste med feltetiketter. "
            "Alt står i løpende setninger. Finn ikke på et saksnummer eller en referanse som ikke står i "
            "listen, og sett aldri et nummer under etiketten for en annen slags nummer.")
    rules += [
        "Hver verdi står under én etikett, og bare én gang som felt. Gjenta aldri det samme nummeret "
        "under to etiketter (for eksempel både «Fødselsnummer» og «Statlig ID»); i teksten kan en "
        "verdi gjentas naturlig.",
        # The pilot's most serious defect: the model added diagnoses, offences,
        # suspicions and financial troubles of its own around the seeded
        # clauses, and nothing labelled them. See tools/gendoc_audit.py.
        "Dokumentet skal ikke inneholde NOEN personopplysning om noen person utover de verdiene og "
        "opplysningene som er listet opp ovenfor. Ikke legg til diagnoser, symptomer, medisiner, "
        "straffbare forhold, mistanker, atferdsmønstre, økonomiske forhold, tro, tilhørighet, "
        "opprinnelse eller seksualitet som ikke står i listen. Saksbehandlingstekst, "
        "lovhenvisninger, frister, klageadgang og nøytral administrativ tekst er derimot fritt.",
        "Opplysningene i listen skal gjengis ordrett og IKKE utvides: ikke føy til et årstall, en "
        "dato, en årsak, en følge eller en presisering på slutten av en oppgitt opplysning.",
        # Pilot v4 wrote "Vi ser at du er aktiv i Senterpartiet ..., noe som kan være relevant for
        # helhetsvurderingen" in a money-laundering letter. The rule covers every special category.
        "En opplysning om etnisitet, religion, nasjonalitet, seksualitet, oppholdsstatus, politisk "
        "ståsted, helse, funksjonsnedsettelse, medisinbruk eller fagforeningsmedlemskap skal stå som et "
        "nøytralt faktum. Den skal ALDRI presenteres som en grunn til, eller et bevis i, en vurdering: "
        "ikke knytt den til mistanke, risiko, kriminalitet, farlighet, troverdighet eller en økonomisk "
        "vurdering eller sikkerhetsvurdering, og ikke skriv at den er «relevant» for noe.",
        # Pilot v4 wrote "Det foreligger ingen registrerte straffedomar" and then the seeded
        # conviction, "men denne finst ikkje i oppgjeve register".
        "Benekt, begrens, betvil eller forklar aldri bort en opplysning i listen. Skriv ikke at den "
        "ikke finnes i et register, at den er uklar eller ubekreftet, eller at ingen slike forhold "
        "foreligger. Hver opplysning er sann og står som et nøytralt faktum.",
    ]
    if negatives:
        rules.append(_NEGATIVE_PLACEMENT_RULE)
    listed = record.planned if items is None else items
    if any(count >= 2 for count in collections.Counter(
            pv.type for pv in listed if pv.value_kind == "clause").values()):
        rules.append(
            "Flere av opplysningene i listen gjelder samme slags forhold, men de er ulike forhold. Skriv "
            "hver av dem ordrett i sin egen setning eller sitt eget setningsledd, slå dem ikke sammen til "
            "én, og gjenta ingen av dem.")
    where = "denne delen" if section else "dette dokumentet"
    if "CASE_NUMBER" not in planned_types:
        rules.append(f"{where.capitalize()} har ikke noe saksnummer og ingen referanse. Skriv ingen linje "
                     "eller setning med «Saksnummer», «Sak nr.», «Sak» foran et nummer, «Vår ref.» "
                     "eller «Deres ref.».")
    for etype, word in (("MILITARY_ID", "tjenestenummer"), ("IDENTITY_CARD", "ID-kortnummer"),
                        ("DEVICE_ID", "enhetsidentifikator")):
        if etype in planned_types:
            rules.append(f"Verdien oppgitt som {word} skal alltid omtales som {word} og aldri som "
                         "saksnummer, referanse eller noe annet nummer.")
    if planned_types & {"DEVICE_ID", "IP_ADDRESS", "USERNAME"}:
        rules.append("Enhetsidentifikatoren, IP-adressen og brukernavnet i listen tilhører hovedpersonen (eller "
                     "en annen person som er nevnt), ikke den som skriver dokumentet. Skriv aldri «vår» eller «vårt» "
                     "foran dem, og omtal dem aldri som avsenderens egen referanse eller eget system.")
    if "MEDICAL_LICENSE" in planned_types:
        rules.append("HPR-nummeret i listen tilhører legen, psykologen eller veterinæren det står oppgitt for, "
                     "og skal stå sammen med den personens navn eller tittel – aldri ved hovedpersonen eller en pasient.")
    if "FIREARMS_LICENSE" in planned_types:
        rules.append("Nummeret oppgitt for våpenet (våpenkortnummer, lisensnummer eller registreringsnummer "
                     "i våpenregisteret) skal stå alene som nummer, med våpenet beskrevet utenfor nummeret, "
                     "og omtales aldri som saksnummer, referanse eller bilens registreringsnummer.")
    if "VESSEL_REGISTRATION" in planned_types:
        rules.append("Registreringsmerket oppgitt for fiskefartøyet skal stå alene, med fartøyets navn "
                     "utenfor merket, og omtales aldri som saksnummer, referanse eller bilens "
                     "registreringsnummer.")
    if marked:
        rules.append("For markerte setninger: skriv ⟦TYPE: setning⟧ nøyaktig én gang per type, "
                     "uten andre ⟦ ⟧ tegn i teksten for øvrig.")
    if not section:
        rules.append("Skriv dokumentet slik en saksbehandler ville skrevet det. Kommenter aldri "
                     "instruksjonene, og skriv ikke setninger som «ingen ytterligere "
                     "personopplysninger foreligger» eller «X er den eneste personen som nevnes».")
        rules.append("Ikke gjenta verdiene i en liste eller et felt til slutt i dokumentet.")
        rules.append("Svar bare med selve dokumentet, uten kommentarer før eller etter.")
    else:
        rules.append("Skriv delen slik en saksbehandler ville skrevet den. Kommenter aldri "
                     "instruksjonene, og skriv ikke setninger som «ingen ytterligere "
                     "personopplysninger foreligger» eller «X er den eneste personen som nevnes».")
        rules.append("Ikke gjenta verdiene i en liste eller et felt til slutt i delen.")
        rules.append("Svar bare med selve delen, uten kommentarer før eller etter.")
    return rules


def _build_pii_free_prompt(record: Record, header: str) -> str:
    """Build the prompt for a document that must contain no personal data at all.

    A detector that has only ever seen documents full of PII learns that
    everything contains PII, so roughly one document in twenty is a circular, a
    procedural notice or a statute extract with no data subject. Its label set
    is empty, which means the unplanned-PII sweep is the entire gate: any name,
    identifier, postal code or date the model invents rejects the document,
    because nothing was planned for it to be covered by. The prompt therefore
    forbids each of those explicitly rather than trusting the model to notice
    that nobody was mentioned.

    Args:
        record: The PII-free record (no person, no planned values).
        header: The genre/length header already built by `build_prompt`.

    Returns:
        The full prompt, with a mock manifest after `MANIFEST_SENTINEL`.
    """
    rules = [
        "Dokumentet skal IKKE handle om noen bestemt person og skal ikke inneholde noen "
        "personopplysning i det hele tatt.",
        "Ikke skriv personnavn, initialer, fødselsnumre, telefonnumre, e-postadresser, "
        "nettadresser, adresser, postnumre, saksnumre, organisasjonsnumre, kontonumre eller "
        "aldersangivelser.",
        "Ikke skriv noen dato og ingen datolignende tallrekke – verken «12.03.2025», "
        "«3. mars 2025» eller «2025-03-12». Skriv i stedet «innen fristen», «ved neste "
        "rapportering», «fra og med kommende termin» og liknende.",
        "Ikke navngi noen kommune, by eller stedsnavn. Omtal mottakerne generelt "
        "(«virksomhetene», «tjenestestedene», «søkerne»).",
        "Henvisninger til lov og forskrift skal stå som paragraf og kapittel uten dato, "
        "for eksempel «forvaltningsloven § 17» eller «kapittel VI».",
        "Skriv generell, upersonlig saksbehandlingstekst: formål, virkeområde, rutine, ansvar, "
        "frister uttrykt uten dato, og hva mottakeren skal gjøre.",
        "Ikke bruk plassholdere som [NAVN] eller [DATO], og ikke skriv noe på engelsk.",
        "Svar bare med selve dokumentet, uten kommentarer før eller etter.",
    ]
    prompt = (header + "\n\nDette er et generelt skriv uten noen sak og uten noen part.\n\nRegler:\n"
              + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)))
    manifest = [f"SEED|{record.doc_seed}", f"META|form={record.form}", "PII_FREE|1"]
    return prompt + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


def build_repair_prompt(record: Record, draft: str, missing: List[str]) -> str:
    """Ask the model to revise its own draft minimally so the missing values appear verbatim.

    Regenerating a whole document because one value was inflected
    (`Fjellveien 12 B` for `Fjellveien 12B`) throws away everything else that
    was right; a minimal-edit pass fixes the common case at a fraction of the
    cost. The repaired text goes through every gate again. Each missing string
    is given with what it is and whose it is -- in the first smoke run a bare
    `«14098526197»` was pasted under the signature, where it read as the
    caseworker's number -- and the task is restated after the draft, since a
    long draft otherwise pushes the instruction out of the model's attention.

    Args:
        record: The record the draft realises.
        draft: The draft text that failed G2.
        missing: The planned strings not found verbatim.

    Returns:
        The repair prompt, with a mock manifest after `MANIFEST_SENTINEL`.
    """
    form_name = "bokmål" if record.form == "nb" else "nynorsk"
    by_value = {pv.value: pv for pv in record.planned if pv.value}
    negative_texts = {neg.text for neg in record.planted_negatives}
    lines = []
    for m in missing:
        pv = by_value.get(m)
        if m in negative_texts:
            lines.append(f"- en nøytral formulering som skal stå ordrett i en setning i brødteksten: «{m}»")
        elif pv is not None and pv.value_kind == "value":
            what = pv.field_label + (f" ({pv.hint})" if pv.hint else "")
            lines.append(f"- {what}: «{m}»")
        else:
            lines.append(f"- opplysning om hovedpersonen, i en hel setning i brødteksten: «{m}»")
    missing_block = "\n".join(lines)
    prompt = (
        f"Nedenfor er et utkast til et dokument på {form_name}. Det mangler noe som må stå ORDRETT, "
        f"tegn for tegn:\n{missing_block}\n\n{DRAFT_OPEN}\n{draft}\n{DRAFT_CLOSE}\n\n"
        f"Oppgave: Skriv utkastet ut på nytt, likt ord for ord, men sett inn det som mangler:\n{missing_block}\n"
        "Sett hver verdi inn der den naturlig hører hjemme, sammen med det den er (for eksempel "
        "«fødselsnummer 12345678901» ved hovedpersonens navn), ikke i signaturen eller til slutt. "
        "Ikke endre noe annet – ikke navn, datoer, tall eller formuleringer. Svar bare med hele dokumentet."
    )
    manifest = [f"SEED|{record.doc_seed}", "REPAIR|1"] + [f"MISSING|{m}" for m in missing]
    return prompt + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


_CONTINUATION_DESC = ("løpende tekst i hele setninger, som fortsettelsen av et dokument der de "
                      "tidligere delene allerede er skrevet")


def build_section_prompt(record: Record, plan: "sections_mod.SectionPlan", k: int,
                         previous: Sequence[str], rng: Optional[random.Random] = None) -> str:
    """Build the prompt for section `k` of a sectioned document.

    The call carries the genre, form and register; the facts about the subject
    and the cast that every section needs to stay coherent; what is already
    written (truncated from the oldest end, the first section always kept); the
    section's role and heading; and only this section's values, clauses and
    negatives, verbatim. Every rule of the whole-document prompt applies. The model
    is told to write this section only, to repeat or summarise nothing, and to
    close the document only if this is the last section.

    Args:
        record: The record being realised.
        plan: The document's section plan.
        k: Which section to write.
        previous: Accepted texts of sections 0..k-1.
        rng: RNG for clause order and position hints; defaults to one seeded
            from the record and the section.

    Returns:
        The prompt, with a machine-readable manifest after `MANIFEST_SENTINEL`
        (`SECTION|k|n|kind`, `HEADING|...`, then this section's items) that
        `MockBackend` reads to fill exactly one section.
    """
    section = plan.sections[k]
    n = len(plan.sections)
    rng = rng or random.Random(record.doc_seed ^ 0x5EC7 ^ (k * 7919) ^ (section.attempts * 104729))
    nb = record.form == "nb"
    genre_spec = genres_mod.GENRES[record.genre]
    title = genre_spec["title_nb"] if nb else genre_spec["title_nn"]
    lo_words = max(25, round(section.chars[0] / 6.5 / 5) * 5)
    hi_words = max(lo_words + 15, round(section.chars[1] * 0.85 / 6.5 / 5) * 5)
    variant = _VARIANT_DESC[record.variant] if k == 0 else _CONTINUATION_DESC
    if nb:
        header = (f"Du skriver del {k + 1} av {n} av et offisielt norsk dokument av typen '{title}'. "
                  f"Form: {variant}. Skriv utelukkende på bokmål, med korrekt og naturlig register for en "
                  "norsk offentlig etat eller virksomhet. Hele dokumentet blir omtrent "
                  f"{record.length_band[0]}–{record.length_band[1]} tegn; denne delen skal være omtrent "
                  f"{lo_words}–{hi_words} ord, aldri mer enn {hi_words} ord.")
    else:
        header = (f"Du skriv del {k + 1} av {n} av eit offisielt norsk dokument av typen '{title}'. "
                  f"Form: {variant}. Skriv utelukkande på nynorsk, med korrekt og naturleg register for eit "
                  "norsk offentleg organ eller ei verksemd. Heile dokumentet blir om lag "
                  f"{record.length_band[0]}–{record.length_band[1]} teikn; denne delen skal vere om lag "
                  f"{lo_words}–{hi_words} ord, aldri meir enn {hi_words} ord.")

    items = [record.planned[i] for i in section.items]
    negatives = [record.planted_negatives[i] for i in section.negatives]
    value_lines, clause_lines, negative_lines, item_manifest, marked = _item_blocks(
        record, items, negatives, rng)
    last = k == n - 1
    role = [f"Denne delen er {section.desc}."]
    if section.heading is not None:
        role.append(f"Første linje i svaret er overskriften «{section.heading}», skrevet nøyaktig slik og alene "
                    "på linjen, uten nummer og uten kolon. Bruk ingen andre overskrifter i delen.")
    else:
        role.append("Delen har ingen overskrift: skriv den som løpende avsnitt, uten overskrifter og uten "
                    "nummerering.")
    role.append("Skriv bare denne delen. Ikke gjenta, omskriv eller oppsummer det som står i tidligere deler, "
                "og ikke skriv noen hilsen, signatur, avslutning eller oppsummering"
                + (" – bortsett fra at dette er siste del, så dokumentet avsluttes her på den måten sjangeren krever."
                   if last else " – dokumentet fortsetter i neste del."))
    if not items and not negatives:
        role.append("Denne delen har ingen oppgitte verdier: skriv nøytral saksbehandlingstekst som passer til "
                    "rollen, uten nye personopplysninger.")

    context = sections_mod.previous_context(previous)
    parts = [header, _subject_line(record), " ".join(role)]
    if context:
        parts.append("Det som allerede er skrevet i tidligere deler (skal ikke gjentas; fortsett der teksten "
                     f"slutter):\n<<<TIDLIGERE>>>\n{context}\n<<<SLUTT PÅ TIDLIGERE>>>")
    if value_lines:
        parts.append("Verdier som skal stå ordrett i denne delen:\n" + "\n".join(value_lines))
    if clause_lines:
        parts.append("Opplysninger som skal stå ordrett inne i løpende setninger i denne delen:\n"
                     + "\n".join(clause_lines))
    if negative_lines:
        parts.append(_NEGATIVE_INTRO.strip("\n") + "\n" + "\n".join(negative_lines))
    rules = _prompt_rules(record, {pv.type for pv in items}, marked, first_part=k == 0, section=True,
                          items=items, negatives=bool(negatives))
    rules.append("Bruk bare personer, verdier og opplysninger som står i listen for denne delen eller i tidligere "
                 "deler; ikke legg til noe nytt om noen.")
    parts.append("Regler:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)))
    manifest = [f"SEED|{record.doc_seed}", f"META|form={record.form}",
                f"SECTION|{k}|{n}|{section.kind}"]
    if section.heading is not None:
        manifest.append(f"HEADING|{section.heading}")
    if last:
        manifest.append("LAST|1")
    manifest += item_manifest
    return "\n\n".join(parts) + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


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
        # v2 LOCATION rule: the place name after the postal code inside an address
        # value is LOCATION too, nested in the ADDRESS span.
        place = re.search(r"(?<!\d)\d{4}\s+([A-ZÆØÅ][\wæøåÆØÅ.\- ]*?)\s*$", address)
        if place and place.group(1) not in output["LOCATION"]:
            output["LOCATION"].append(place.group(1))
    # B13: a date or bare year inside a narrative clause is also DATE_TIME.
    clause_types = {pv.type for pv in record.planned if pv.value_kind == "clause"}
    for etype in clause_types:
        for span in output.get(etype, []):
            for date in clause_dates(span):
                if date not in output["DATE_TIME"] and date not in output.get("DATE_OF_BIRTH", []):
                    output["DATE_TIME"].append(date)
    return {k: v for k, v in output.items() if v}


_CLAUSE_DATE_RE = re.compile(
    rf"(?<![\w./-])\d{{1,2}}\.\s?(?:{gates._MONTHS})\s\d{{4}}(?![\w/-])"
    rf"|(?<![\w./-])\d{{1,2}}\.\d{{1,2}}\.\d{{4}}(?![\w/-])"
    rf"|(?<![\w./-])(?:{gates._MONTHS})\s(?:19|20)\d{{2}}(?![\w/-])"
    r"|(?<![\w./-])(?:19|20)\d{2}(?![\w/-]|\.\d)",
    re.IGNORECASE,
)


_YEAR_CUES = {
    "i", "fra", "frå", "siden", "sidan", "før", "etter", "innen", "til", "og", "mellom",
    "høsten", "hausten", "våren", "sommeren", "sommaren", "vinteren", "året", "år", "uke",
    "veke", "januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
    "september", "oktober", "november", "desember", "dømt", "domfelt", "anmeldt",
    "siktet", "sikta", "tiltalt", "diagnostisert", "innlagt", "utskrevet", "utskriven",
}


def clause_dates(span: str) -> List[str]:
    """Return the dates and bare years ANNOTATION_SPEC B13 nests inside a clause.

    Longest form first (`3. mars 2021`, `12.05.2019`, `mars 2021`, then a bare
    year as its own token), so a year that belongs to a fuller date is not
    emitted twice. Digits glued to `/`, `-` or another digit are part of an
    identifier (`2018/45678`, `2018-475963`) and are left alone, per B13.

    Args:
        span: A labelled clause.

    Returns:
        The date substrings, in order of appearance, without duplicates.
    """
    found: List[str] = []
    taken: List[Tuple[int, int]] = []
    for m in _CLAUSE_DATE_RE.finditer(span):
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", m.group(0)):
            # A bare four-digit number is a year only with a temporal cue before it;
            # `betalte 2000 kroner` and `2000 høner` are amounts.
            prev = re.findall(r"[\wæøåÆØÅ]+", span[:m.start()])
            if not prev or prev[-1].lower() not in _YEAR_CUES:
                continue
        taken.append((m.start(), m.end()))
        if m.group(0) not in found:
            found.append(m.group(0))
    return found


# ---------------------------------------------------------------------------
# Gate orchestration per document
# ---------------------------------------------------------------------------

_TIER_A_VALIDATORS = {
    "NATIONAL_ID": ident.is_valid_fodselsnummer,
    "ORG_NUMBER": ident.is_valid_org_number,
    "BANK_ACCOUNT": ident.is_valid_bank_account,
    "IBAN": ident.is_valid_iban_no,
    "CREDIT_CARD": ident.is_valid_luhn,
    "TAX_ID": ident.is_valid_tax_id,
    # Only the IMEI branch of DEVICE_ID declares a checksum at all; a UUID or a
    # MAC address is recorded with checksum_valid=None and never reaches here.
    "DEVICE_ID": ident.is_valid_luhn,
}

# Identifiers with no checksum but a closed set of generated shapes. The record
# declares them valid, so G4 fails a value that no longer matches any shape
# (a mangled planned string) the way it fails a broken check digit.
_TIER_A_FORMAT_VALIDATORS = {
    "FIREARMS_LICENSE": ident.is_valid_firearms_license,
    "VESSEL_REGISTRATION": ident.is_valid_vessel_registration,
}


def build_tier_a_findings(record: Record) -> List[dict]:
    """Build G4 findings: declared vs. actual checksum validity for Tier A values."""
    findings = []
    for pv in record.planned:
        if pv.tier == "A" and pv.type in _TIER_A_FORMAT_VALIDATORS:
            findings.append({
                "type": pv.type, "value": pv.value, "declared_valid": True,
                "actual_valid": _TIER_A_FORMAT_VALIDATORS[pv.type](pv.value),
            })
            continue
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
    max_new_tokens: int = 700
    temperature: float = 0.75
    batch_size: int = 4
    repair_temperature: float = 0.3
    max_repairs: int = 2
    repair_max_missing: int = 2
    repair_missing_per_values: int = 8
    length_factor: float = 1.9
    repetition_threshold: float = 0.06
    hard_max_chars: int = 10000
    audit: bool = True
    max_audit_repairs: int = 1
    audit_max_new_tokens: int = 512
    dataset: str = "train"
    difficulty_weights: Optional[Dict[str, float]] = None
    negative_bank: Dict[str, List[dict]] = field(default_factory=dict)
    negative_cap: int = dataset_mod.NEGATIVE_CAP_PER_RUN
    negative_ledger: Optional[NegativeLedger] = None
    sectioning: str = "auto"  # "auto", "off" or "always"; see gendoc_sections.needs_sections
    section_retries: int = 3  # generations per section: the first and two regenerations
    section_join_redos: int = 2  # sections regenerated because the joined document failed
    known_clause_texts: List[str] = field(default_factory=list)  # every literal clause text of the dataset's bank (G6)
    coherence_log: List[dict] = field(default_factory=list)  # one CoherenceReport.as_dict() per record that went on
    coherence_rejected: int = 0  # records `check_record_coherence` refused before any model call
    max_coherence_redraws: int = 5  # fresh samples tried for one attempt before giving up


@dataclass
class DocPlan:
    """What the batch plan fixes for one document before any attempt is made.

    The plan owns density, not the sampler: genre, length band, profile, type
    target, Art. 9 cap and any coverage-scheduled types are all decided for the
    whole batch up front, so density and coverage are batch properties and every
    retry of a document keeps the same shape.
    """

    idx: int
    genre: str
    variant: str
    form: str
    length_band: Tuple[int, int]
    forced_types: List[str]
    profile: str = "typical"
    type_target: int = 7
    art9_cap: int = 1
    pii_free: bool = False
    n_negatives: int = 0
    instances: Dict[str, int] = field(default_factory=dict)  # repeatable type -> instances planned (2..4)
    id_block: List[str] = field(default_factory=list)  # types the document's identification block must carry


@dataclass
class DocState:
    """Per-document progress across attempts, repairs and batches."""

    plan: DocPlan
    attempt: int = 0
    repairs: int = 0  # repair passes used in the current attempt
    repairs_total: int = 0
    gate_log: List[dict] = field(default_factory=list)
    record: Optional[Record] = None
    last_text: Optional[str] = None
    gen_seconds: float = 0.0
    generate_calls: int = 0
    audit_repairs: int = 0  # audit repair passes used in the current attempt
    audit_repairs_total: int = 0
    audit_calls: int = 0
    audit_seconds: float = 0.0
    audit_log: List[dict] = field(default_factory=list)
    result: Optional[dict] = None
    section_plan: Optional["sections_mod.SectionPlan"] = None
    queued: Set[int] = field(default_factory=set)  # sections with a job queued or in flight
    section_calls: int = 0
    coherence_log: List[dict] = field(default_factory=list)  # this document's share of `config.coherence_log`
    coherence_rejected: int = 0  # this document's share of `config.coherence_rejected`


def _doc_seed(base_seed: int, idx: int, attempt: int) -> int:
    return base_seed * 100003 + idx * 97 + attempt


def check_record_coherence(record: Record) -> List[Tuple[str, str, int]]:
    """Test a sampled record's cast against the rules of `gendoc_coherence`.

    Returns:
        `(rule, role, age)` for each violation; empty when the cast is possible or the record
        has no subject.
    """
    if record.person is None:
        return []
    members = [coherence.Member(p.role or "subject", p.person.age())
               for p in record.parties if not p.is_subject]
    return coherence.check(record.person.age(), members)


def new_attempt_record(state: DocState, base_seed: int, taxonomy_index: Dict[str, dict],
                       clause_bank: dict, public_figures: Set[str], config: GenerationConfig) -> Record:
    """Sample the record for the state's next attempt, deterministically from its doc seed.

    The sampler repairs an impossible cast (`gendoc_coherence.enforce_cast`); this is the
    independent test of the result. A record that still fails it is released and sampled
    again from a derived seed -- before any prompt is built, so no model call is spent on it
    -- and counted in `config.coherence_rejected`.
    """
    state.attempt += 1
    state.repairs = 0
    state.audit_repairs = 0
    state.section_plan = None
    state.queued = set()
    plan = state.plan
    if config.negative_ledger is None:
        config.negative_ledger = NegativeLedger(config.negative_cap)
    if state.record is not None:
        config.negative_ledger.release(state.record.planted_negatives)
    for redraw in range(config.max_coherence_redraws + 1):
        doc_seed = _doc_seed(base_seed, plan.idx, state.attempt) + redraw * 7_919_000
        rng = random.Random(doc_seed)
        record = sample_record(
            rng, doc_seed, plan, config.strategy, taxonomy_index, clause_bank, public_figures,
            negative_bank=config.negative_bank, difficulty_weights=config.difficulty_weights,
            dataset=config.dataset, negative_ledger=config.negative_ledger,
        )
        if not check_record_coherence(record):
            break
        config.coherence_rejected += 1
        state.coherence_rejected += 1
        config.negative_ledger.release(record.planted_negatives)
    else:
        raise RuntimeError(f"no coherent record for plan {plan.idx} after {config.max_coherence_redraws} redraws")
    if record.coherence is not None:
        config.coherence_log.append(record.coherence)
        state.coherence_log.append(record.coherence)
    for pv in record.planned:
        if pv.tier == "A" and pv.checksum_valid is not None and rng.random() < config.invalid_checksum_rate:
            value, valid = _generate_value_kind(pv.type, random.Random(doc_seed + 1), record.person,
                                                invalid_rate=1.0)
            if valid is not None:
                pv.value, pv.checksum_valid = value, valid
    state.record = record
    return record


_BIRTH_CUE_RE = re.compile(r"(?:født|fødd|fødselsdato|fødselsdag|f\.)\s*(?:den\s*|:\s*)?$", re.IGNORECASE)


def _date_of_birth_forms(person: Person) -> Set[str]:
    d = person.birth_date
    return {
        f"{d.day:02d}.{d.month:02d}.{d.year}", f"{d.day}.{d.month}.{d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}", f"{d.day}. {_MONTHS_NB[d.month - 1]} {d.year}",
    }


def _prune_redundant_nested(text: str, output: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Drop a span every occurrence of which sits inside a longer span of the same type.

    Labelling `Dr. Kari Hansen` from the sweep when `Kari Hansen` was planned
    would otherwise tag one mention twice, which `validate_labels.py` rejects
    as REDUNDANT_NESTED.
    """
    def occ(span: str) -> List[Tuple[int, int]]:
        return gates._covered_intervals(text, [span])

    pruned: Dict[str, List[str]] = {}
    for etype, spans in output.items():
        keep = []
        for short in spans:
            longer = [s for s in spans if s != short and short in s]
            wide = [iv for s in longer for iv in occ(s)]
            if wide and all(any(lo <= a and b <= hi for lo, hi in wide) for a, b in occ(short)):
                continue
            keep.append(short)
        pruned[etype] = keep
    return {k: v for k, v in pruned.items() if v}


_AGE_ABSORBERS = ("FAMILY_RELATION", "AGE_INFO", "ANIMAL_INFO")


def _drop_absorbed_spans(text: str, output: Dict[str, List[str]],
                         agency_names: Set[str]) -> Dict[str, List[str]]:
    """Drop labels that ANNOTATION_SPEC says a larger span absorbs.

    The labeller marks every occurrence of a planned string, so a string whose
    every occurrence lies inside a span of another type is a label the spec does
    not allow:

    * an AGE inside a FAMILY_RELATION, AGE_INFO or ANIMAL_INFO span ("12 år" in
      "to barn på 15 og 12 år") is not tagged again;
    * a LOCATION inside an organisation's or authority's own name ("Fredrikstad"
      in "Fredrikstad Sjømat AS") is not a LOCATION. A city inside an ADDRESS is,
      and is left alone.

    Args:
        text: The document.
        output: `{TYPE: [spans]}`.
        agency_names: Known authority and institution names.

    Returns:
        The output without the absorbed spans; types left empty are removed.
    """
    def intervals(spans: Sequence[str]) -> List[Tuple[int, int]]:
        return gates._covered_intervals(text, spans)

    def absorbed(span: str, wide: List[Tuple[int, int]]) -> bool:
        spots = intervals([span])
        return bool(spots) and all(any(lo <= a and b <= hi for lo, hi in wide) for a, b in spots)

    out = {k: list(v) for k, v in output.items()}
    wide_age = [iv for t in _AGE_ABSORBERS for iv in intervals(out.get(t, []))]
    out["AGE"] = [s for s in out.get("AGE", []) if not absorbed(s, wide_age)]
    names = list(out.get("ORGANIZATION", [])) + [a for a in agency_names if a in text]
    wide_org = intervals(names)
    out["LOCATION"] = [s for s in out.get("LOCATION", []) if not absorbed(s, wide_org)]
    return {k: v for k, v in out.items() if v}


def _seeded_clause_literals(record: Record) -> List[str]:
    """The seeded clause texts of a record: the words G6 and G12 must not count as the model's prose."""
    return [pv.value for pv in record.planned if pv.value_kind == "clause" and pv.value]


def _ownership_context(record: Record) -> Optional[dict]:
    """Whose-value context for G14: the subject's names and pronouns, and the clinicians' names.

    A planned HPR number is a clinician's; the gate rejects it when the text writes it next to
    the subject (or the subject's pronoun) and not next to a clinician's name or title.
    """
    if record.person is None:
        return None
    person = record.person
    pronouns = {("M", "nb"): ["han", "ham", "hans"], ("F", "nb"): ["hun", "henne", "hennes"],
                ("M", "nn"): ["han", "hans"], ("F", "nn"): ["ho", "henne", "hennar"]}[(person.gender, record.form)]
    clinicians = []
    for party in record.parties:
        if party.role in _CLINICIAN_ROLES or (party.role == "author" and (record.signatory_role or "") in _CLINICAL_TITLES):
            clinicians += [party.person.full_name, party.person.last_name]
    return {"subject_refs": [person.full_name, person.first_name, person.last_name, *pronouns],
            "clinician_refs": clinicians}


def evaluate_candidate(
    state: DocState, raw_text: str, finished: bool, *, taxonomy_index: Dict[str, dict],
    public_figures: Set[str], place_names: Set[str], agency_names: Set[str],
    config: GenerationConfig, accepted_ngrams: List[Set[Tuple[str, ...]]],
) -> Tuple[str, Optional[List[str]]]:
    """Run every per-document gate on one generated (or repaired) text.

    Args:
        state: The document's state; its `record` is the record being realised.
        raw_text: Backend output.
        finished: Whether the backend stopped on end-of-sequence rather than
            on the token budget.
        taxonomy_index: Type name -> taxonomy entry.
        public_figures: Embedded public-figure set (G3).
        place_names: Known place names (G7).
        agency_names: Known agency names (G7).
        config: Run configuration.
        accepted_ngrams: 5-gram sets of already-accepted documents (G6).

    Returns:
        ("accepted", None) with `state.result` filled in; ("repair", missing
        values) when G2 found only a few missing values and a repair pass is
        still allowed; or ("retry", None) for any other failure. Every outcome
        is appended to `state.gate_log`.
    """
    record = state.record
    attempt = state.attempt
    stage_tag = {"attempt": attempt, "repair": state.repairs}
    clause_literals = _seeded_clause_literals(record)

    def fail(stage: str, detail) -> Tuple[str, None]:
        state.gate_log.append({**stage_tag, "stage": stage, "ok": False, "detail": detail})
        return "retry", None

    raw_text = raw_text.strip()
    state.last_text = raw_text
    if config.strategy == "seeded":
        # The seeded prompt never asks for markers, so any ⟦ ⟧ is the model
        # copying syntax it was not given (pilot_v1 accepted a HEALTH span
        # "setning" this way); it is never parsed as a label.
        if "⟦" in raw_text or "⟧" in raw_text:
            return fail("marker_leak", "marker characters in a seeded-strategy document")
        clean_text, marked_spans = raw_text, {}
    else:
        clean_text, marked_spans, marker_ok, marker_err = strip_markers(raw_text, set(taxonomy_index))
        if not marker_ok:
            return fail("marker", marker_err)
    state.last_text = clean_text

    if not finished:
        return fail("G10_truncated", "generation hit the token budget before end of sequence")
    placeholders_ok, placeholder_hits = gates.gate_placeholders(clean_text)
    if not placeholders_ok:
        return fail("G0_placeholder", placeholder_hits)
    length_ok, length = gates.gate_length(clean_text, config.hard_max_chars)
    if not length_ok:
        return fail("G10_length", {"length": length, "band_max": record.length_band[1],
                                   "hard_max": config.hard_max_chars})
    repetition_ok, repetition = gates.gate_internal_repetition(
        clean_text, config.repetition_threshold, exempt=clause_literals)
    if not repetition_ok:
        return fail("G12_repetition", {"repeat_8gram_share": repetition,
                                       "threshold": config.repetition_threshold})

    literal_values = [
        pv.value for pv in record.planned
        if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")
    ]
    if record.pii_free and literal_values:
        return fail("plan_inconsistent", "a PII-free record must plan no values")
    negative_texts = _realise_negatives(record.planted_negatives, clean_text)
    g2_ok, g2_missing = gates.gate_verbatim(literal_values + negative_texts, clean_text)
    missing_marks = [pv.type for pv in record.planned if pv.strategy == "marked" and pv.type not in marked_spans]
    if not g2_ok or missing_marks:
        state.gate_log.append({**stage_tag, "stage": "G2_verbatim", "ok": False,
                               "detail": {"missing_values": g2_missing, "missing_marked_types": missing_marks}})
        # A 600-character note plants five values and a case file plants
        # twenty-five; allowing the same two missing values in both meant every
        # case file was discarded for one inflected string out of twenty-five,
        # which threw away a document whose other twenty-four labels were
        # correct. The repair allowance scales with how much was planted.
        n_planted = max(1, len(literal_values) + len(negative_texts))
        allowance = max(config.repair_max_missing, n_planted // config.repair_missing_per_values)
        if (not missing_marks and len(g2_missing) <= allowance
                and state.repairs < config.max_repairs):
            return "repair", g2_missing
        return "retry", None

    clauses = [pv.value for pv in record.planned if pv.value_kind == "clause" and pv.value]
    clauses += [span for spans in marked_spans.values() for span in spans]
    placement_ok, placement_hits = gates.gate_negative_placement(clean_text, negative_texts, clauses)
    if not placement_ok:
        return fail("G15_negative_placement", placement_hits)
    slot_ok, slot_hits = gates.gate_slot_labels(clean_text, clauses + negative_texts)
    if not slot_ok:
        return fail("G9_slot", slot_hits)
    tabular_ok, tabular_hits = gates.gate_tabular_dump(clean_text, literal_values + negative_texts)
    if not tabular_ok:
        return fail("G13_tabular", tabular_hits)
    roles_ok, role_hits = gates.gate_identifier_roles(
        clean_text, [(pv.type, pv.value) for pv in record.planned if pv.value_kind == "value"],
        literal_values + negative_texts, owners=_ownership_context(record))
    if not roles_ok:
        return fail("G14_roles", role_hits)

    names_to_check = [p.person.full_name for p in record.parties]
    g3_ok, g3_hits = gates.gate_name_collision(names_to_check, clean_text, public_figures, place_names, agency_names)
    if not g3_ok:
        return fail("G3_name_collision", g3_hits)

    tier_a_findings = build_tier_a_findings(record)
    g4_ok, g4_bad = gates.gate_identifier_checksums(tier_a_findings)
    if not g4_ok:
        return fail("G4_checksum", g4_bad)

    # G6 compares prose with prose. Two documents that draw the same bank clause (or the same
    # pair of clauses of one type) look more alike by that clause alone, so the windows that
    # overlap any clause text of the dataset's bank, and this document's own literals, are not
    # part of the fingerprint.
    ngrams = gates.word_ngrams(clean_text, exempt=clause_literals + config.known_clause_texts)
    g6_ok, g6_sim = gates.gate_near_duplicate(clean_text, ngrams, accepted_ngrams, config.near_dup_threshold)
    if not g6_ok:
        return fail("G6_near_duplicate", g6_sim)

    output = build_output(record, clean_text, marked_spans)

    # docs/ANNOTATION_SPEC.md wants the full clause, and the model finishes a
    # seeded one often enough to matter: "sidan hausten" came back as "sidan
    # hausten 2025". Extending is only safe for the closed set of completions
    # `extend_seeded_clause_spans` allows.
    seeded_clauses = [pv.value for pv in record.planned
                      if pv.value_kind == "clause" and pv.value and pv.type in output]
    extensions, n_extended = gates.extend_seeded_clause_spans(clean_text, seeded_clauses)
    if extensions:
        for pv in record.planned:
            if pv.value in extensions and pv.type in output:
                spans = output[pv.type]
                output[pv.type] = [extensions.get(sp, sp) if sp == pv.value else sp for sp in spans]

    for neg in record.planted_negatives:
        for etype, sub in neg.also_labelled.items():
            if sub in clean_text and sub not in output.get(etype, []):
                output.setdefault(etype, []).append(sub)
    covered = [v for vals in output.values() for v in vals] + negative_texts
    g7_ok, g7_findings = gates.gate_unplanned_pii(clean_text, covered, place_names, agency_names)
    # A PII-free document planned nothing, so nothing is covered and there is no
    # owner the sweep could attribute a hit to. Every finding rejects, including
    # the ones a normal document would be allowed to label.
    if record.pii_free:
        if g7_findings:
            return fail("G7_unplanned_pii", g7_findings)
    else:
        rejecting = [f for f in g7_findings if f["action"] == "reject"]
        if rejecting and config.g7_policy == "reject":
            return fail("G7_unplanned_pii", rejecting)

    # Unplanned full names, honorific+surname forms and dates are labelled
    # rather than regenerated (PROJECT_SPEC_V2.md Section 3.1). A name the
    # model invented still has to clear the public-figure check.
    dob_forms = _date_of_birth_forms(record.person) if record.person else set()
    labelled = []
    for f in g7_findings:
        if f["action"] != "label":
            continue
        etype = f["label_type"]
        if etype == "DATE_TIME" and f["match"] in dob_forms:
            etype = "DATE_OF_BIRTH"
        elif etype == "DATE_TIME" and _BIRTH_CUE_RE.search(clean_text[max(0, f["start"] - 30):f["start"]]):
            # An invented birth date that disagrees with the fødselsnummer is
            # an incoherent record, and labelling it DATE_TIME would be wrong too.
            return fail("G7_unplanned_pii", [{**f, "action": "reject", "pattern": "contradictory_birth_date"}])
        if etype == "PERSON":
            bare = re.sub(r"^(?:Fru|Herr|Frk\.|Frøken|Dr\.|Mr\.|Mrs\.|Ms\.)\s+", "", f["match"])
            if bare in public_figures or f["match"] in public_figures:
                return fail("G3_name_collision", [f["match"]])
        if f["match"] not in output.get(etype, []):
            output.setdefault(etype, []).append(f["match"])
            labelled.append({"type": etype, "text": f["match"], "pattern": f["pattern"]})
    output = _drop_absorbed_spans(clean_text, output, agency_names)
    output = _prune_redundant_nested(clean_text, output)

    state.gate_log.append({**stage_tag, "stage": "accepted", "ok": True,
                           "g7_findings": g7_findings, "g7_policy": config.g7_policy})
    tabular = gates.tabular_profile(clean_text, literal_values + negative_texts)
    state.result = {
        "accepted": True, "record": record, "text": clean_text, "output": output,
        "ngrams": ngrams, "tier_a_findings": tier_a_findings, "g7_labelled": labelled,
        "clause_extensions": extensions, "clause_extensions_count": n_extended,
        "tabular": tabular,
    }
    return "accepted", None


def _realise_negatives(negatives: Sequence[PlantedNegative], text: str) -> List[str]:
    """Record on each planted negative the form it takes in `text`, and return those forms.

    Args:
        negatives: The negatives planted in the text's document.
        text: The generated document or section.

    Returns:
        One string per negative, in order: the planted text, or the same text with its
        first letter in the other case when that is what the model wrote.
    """
    surfaces = gates.resolve_surfaces([neg.text for neg in negatives], text)
    for neg, surface in zip(negatives, surfaces):
        neg.surface = surface
    return surfaces


def _document_literals(record: Record) -> List[str]:
    """Every literal string the record plants anywhere: values, seeded clauses, negatives."""
    literals = [pv.value for pv in record.planned
                if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")]
    return literals + [neg.found for neg in record.planted_negatives]


def evaluate_section(
    state: DocState, k: int, raw_text: str, finished: bool, *, taxonomy_index: Dict[str, dict],
    place_names: Set[str], agency_names: Set[str], config: GenerationConfig,
) -> Tuple[str, Optional[List[str]]]:
    """Run the per-section gates on one generated (or repaired) section.

    The gates that look at one passage run here, so a failure is attributed to its
    section and only that section is repaired or regenerated: the model's output
    is complete, G0 placeholders, G2 that this section's own values and negatives
    are present, G9 that no heading or label names a category, G13 and G14 on the
    section's fields and identifiers, G7 that nothing unplanned appeared. The gates
    that need the whole document (G1, G3, G4, G6, G12 across sections, G11, the
    total length) run on the joined text in `evaluate_candidate`.

    Args:
        state: The document's state; `state.section_plan` is the plan.
        k: Index of the section.
        raw_text: Backend output for the section.
        finished: Whether the backend stopped on end-of-sequence.
        taxonomy_index: Type name -> taxonomy entry.
        place_names: Known place names (G7).
        agency_names: Known agency names (G7).
        config: Run configuration.

    Returns:
        ("ok", None) with the section's `raw` and `text` set; ("repair", missing
        values) when a repair of this section is allowed; ("retry", None) when the
        section must be regenerated. Every failure is appended to `state.gate_log`
        with the section's index.
    """
    record, plan = state.record, state.section_plan
    section = plan.sections[k]
    tag = {"attempt": state.attempt, "section": k, "section_attempt": section.attempts,
           "repair": section.repairs, "scope": "section"}

    def fail(stage: str, detail) -> Tuple[str, None]:
        entry = {**tag, "stage": stage, "ok": False, "detail": detail}
        state.gate_log.append(entry)
        section.log.append(entry)
        return "retry", None

    text, heading_problems = sections_mod.normalise_section(raw_text, section.heading)
    section.draft = text
    if not finished:
        return fail("G10_truncated", "generation hit the token budget before end of sequence")
    if config.strategy == "seeded":
        if "⟦" in text or "⟧" in text:
            return fail("marker_leak", "marker characters in a seeded-strategy section")
        clean, marked_spans = text, {}
    else:
        clean, marked_spans, marker_ok, marker_err = strip_markers(text, set(taxonomy_index))
        if not marker_ok:
            return fail("marker", marker_err)
    if heading_problems:
        return fail("G9_slot", [{"kind": "category_heading", "clause": None, "line": p["heading"]}
                                for p in heading_problems])
    placeholders_ok, placeholder_hits = gates.gate_placeholders(clean)
    if not placeholders_ok:
        return fail("G0_placeholder", placeholder_hits)
    section_max = min(config.hard_max_chars, 2 * section.chars[1] + 800)
    length_ok, length = gates.gate_length(clean, section_max)
    if not length_ok:
        return fail("G10_length", {"length": length, "section_max": section_max})
    repetition_ok, repetition = gates.gate_internal_repetition(
        clean, config.repetition_threshold, exempt=_seeded_clause_literals(record))
    if not repetition_ok:
        return fail("G12_repetition", {"repeat_8gram_share": repetition,
                                       "threshold": config.repetition_threshold})

    planned = [record.planned[i] for i in section.items]
    negatives = [record.planted_negatives[i] for i in section.negatives]
    literals = [pv.value for pv in planned
                if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")]
    negative_texts = _realise_negatives(negatives, clean)
    g2_ok, g2_missing = gates.gate_verbatim(literals + negative_texts, clean)
    missing_marks = [pv.type for pv in planned if pv.strategy == "marked" and pv.type not in marked_spans]
    if not g2_ok or missing_marks:
        entry = {**tag, "stage": "G2_verbatim", "ok": False,
                 "detail": {"missing_values": g2_missing, "missing_marked_types": missing_marks}}
        state.gate_log.append(entry)
        section.log.append(entry)
        if (not missing_marks and len(g2_missing) <= config.repair_max_missing
                and section.repairs < config.max_repairs):
            return "repair", g2_missing
        return "retry", None

    clauses = [pv.value for pv in planned if pv.value_kind == "clause" and pv.value]
    clauses += [span for spans in marked_spans.values() for span in spans]
    placement_ok, placement_hits = gates.gate_negative_placement(clean, negative_texts, clauses)
    if not placement_ok:
        return fail("G15_negative_placement", placement_hits)
    slot_ok, slot_hits = gates.gate_slot_labels(clean, clauses + negative_texts)
    if not slot_ok:
        return fail("G9_slot", slot_hits)
    tabular_ok, tabular_hits = gates.gate_tabular_dump(clean, literals + negative_texts)
    if not tabular_ok:
        return fail("G13_tabular", tabular_hits)
    everything = _document_literals(record)
    roles_ok, role_hits = gates.gate_identifier_roles(
        clean, [(pv.type, pv.value) for pv in planned if pv.value_kind == "value"], everything,
        owners=_ownership_context(record))
    if not roles_ok:
        return fail("G14_roles", role_hits)
    covered = everything + [sub for neg in record.planted_negatives for sub in neg.also_labelled.values()]
    _g7_ok, g7_findings = gates.gate_unplanned_pii(clean, covered, place_names, agency_names)
    rejecting = [f for f in g7_findings if f["action"] == "reject"]
    if rejecting and config.g7_policy == "reject":
        return fail("G7_unplanned_pii", rejecting)

    entry = {**tag, "stage": "section_accepted", "ok": True}
    state.gate_log.append(entry)
    section.log.append(entry)
    section.raw, section.text = text, clean
    return "ok", None


def _token_budget(config: GenerationConfig, max_chars: int) -> int:
    # Norwegian runs ~2.6 characters per token under the Qwen tokenizer. The
    # model overshoots its band by 20-40%, and overshoot is accepted, so the
    # budget leaves 60% headroom for it to finish; only output that still hits
    # the budget is truncated and rejected.
    return min(max(config.max_new_tokens, int(max_chars * config.length_factor / 2.6) + 120),
               int(config.hard_max_chars / 2.6) + 120)


def known_clause_texts_of(clause_bank: dict) -> List[str]:
    """Every literal clause text of a bank: the wording G6 must not count as the model's prose."""
    return sorted({
        e["text"] for etype, entries in clause_bank.items() if etype != "negatives"
        for e in entries if "{" not in e["text"] and len(e["text"].split()) >= 3})


def run_generation(
    plans: List[DocPlan], base_seed: int, taxonomy_index: Dict[str, dict], clause_bank: dict,
    public_figures: Set[str], place_names: Set[str], agency_names: Set[str], backend,
    config: GenerationConfig, progress=None,
    accepted_ngrams: Optional[List[Set[Tuple[str, ...]]]] = None,
    before_generate: Optional[Callable[[str, int], None]] = None,
) -> Tuple[List[DocState], dict]:
    """Generate every planned document, `config.batch_size` prompts per backend call.

    A job is one of several kinds, and jobs of different kinds never share a
    backend call because they need different sampling: a fresh attempt (a new
    record from the attempt's doc seed, at the run temperature), a G2 repair of
    the current draft (lower temperature, so the repair stays close to the
    draft), a G11 content audit of an otherwise-accepted document (temperature
    0, because the same document must audit the same way every time), and a G11
    repair that deletes or neutralises what the audit found.

    A document with more than about ten planned items, and every dense or
    case-file document, is generated in sections instead (`gendoc_sections`):
    `section` jobs write one section each, in order, from the sections before it;
    `section_repair` repairs one section's missing values; `section_audit_repair`
    repairs one section's G11 findings. A section that fails its own gates is
    repaired or regenerated alone, up to `config.section_retries` times, and only
    then does the document get a new record. When all sections are in, the joined
    text goes through `evaluate_candidate` (G1-bound checks, G3, G4, G6, G12 across
    sections, the total length) and, if it fails in a way that can be traced to one
    section, that section alone is regenerated.

    Jobs from different documents share a call. Each document's record, prompt
    and gate outcome depend only on its own seed and outputs, so batching
    changes throughput, not which records are sampled.

    A document is only finalised once it has passed every per-document gate and
    audited clean, which is also when its 5-grams join the near-duplicate
    reference set: a document accepted by the gates and then rejected by the
    audit must not make its own regeneration look like a duplicate of itself.

    Args:
        plans: One `DocPlan` per document, in output order.
        base_seed: Run seed.
        taxonomy_index: Type name -> taxonomy entry.
        clause_bank: Loaded clause bank.
        public_figures: Public-figure set (G3).
        place_names: Known place names (G7).
        agency_names: Known agency names (G7).
        backend: Generation backend.
        config: Run configuration.
        progress: Optional callable(state) invoked when a document finishes.
        accepted_ngrams: The near-duplicate reference list (G6). Documents accepted here are appended
            to it, so a caller that runs the plans in several calls, or resumes a run, passes the
            list it rebuilt from the documents already written. None starts empty.
        before_generate: Optional callable(kind, n_jobs) invoked before every backend call, for
            stop-file and GPU-contention checks. It cannot cancel the call; a stop is honoured by
            the caller once the documents in flight are finished.

    Returns:
        Tuple of (final states in plan order, run statistics).
    """
    states = [DocState(plan) for plan in plans]
    queue: collections.deque = collections.deque()
    if not config.known_clause_texts:
        config.known_clause_texts = known_clause_texts_of(clause_bank)
    if config.negative_ledger is None:
        config.negative_ledger = NegativeLedger(config.negative_cap)
    if accepted_ngrams is None:
        accepted_ngrams = []
    stats: collections.Counter = collections.Counter()

    def _purge(st: DocState) -> None:
        """Drop the document's queued jobs: they belong to a record that is being replaced."""
        for job in [j for j in queue if j[0] is st]:
            queue.remove(job)

    def _begin(st: DocState) -> None:
        """Sample the next record and queue its first job: the whole text or section 0."""
        _purge(st)
        new_attempt_record(st, base_seed, taxonomy_index, clause_bank, public_figures, config)
        rec = st.record
        n_items = len(rec.planned) + len(rec.planted_negatives)
        if sections_mod.needs_sections(st.plan.profile, n_items, rec.pii_free, config.sectioning):
            st.section_plan = sections_mod.build_plan(rec, random.Random(rec.doc_seed ^ 0x5EC7))
            stats["sectioned_attempts"] += 1
            _advance(st)
        else:
            queue.append((st, "fresh", None))

    def _advance(st: DocState) -> None:
        """Queue the next section that still needs writing, or join and gate the document."""
        plan = st.section_plan
        for sec in plan.sections:
            if not sec.done and sec.index not in st.queued:
                st.queued.add(sec.index)
                sec.repairs = 0
                queue.append((st, "section", sec.index))
                return
        if not st.queued:
            _join_and_gate(st)

    def _finalize(st: DocState) -> None:
        accepted_ngrams.append(st.result["ngrams"])
        if progress:
            progress(st)

    def _retry_or_give_up(st: DocState, reason: str) -> None:
        if st.attempt < config.retries:
            _begin(st)
        else:
            _purge(st)
            st.result = {"accepted": False, "reason": reason}
            if st.record is not None:
                config.negative_ledger.release(st.record.planted_negatives)
            if progress:
                progress(st)

    def _redo_section(st: DocState, k: int, reason: str) -> bool:
        """Regenerate section k alone; False when its attempts or the join redos are used up."""
        plan = st.section_plan
        sec = plan.sections[k]
        if sec.attempts >= config.section_retries:
            return False
        sec.done = False
        st.queued.add(k)
        queue.append((st, "section", k))
        stats["section_regenerations"] += 1
        stats[f"section_regenerations_{reason}"] += 1
        return True

    def _section_failed(st: DocState, k: int) -> None:
        st.queued.discard(k)
        if not _redo_section(st, k, "gate"):
            stats["section_gave_up"] += 1
            _retry_or_give_up(st, "section_failure")

    def _join_and_gate(st: DocState) -> None:
        """All sections are in: run the document-level gates on the joined text."""
        plan = st.section_plan
        joined = sections_mod.join_sections([s.raw for s in plan.sections])
        outcome, _ = evaluate_candidate(
            st, joined, True, taxonomy_index=taxonomy_index, public_figures=public_figures,
            place_names=place_names, agency_names=agency_names, config=config,
            accepted_ngrams=accepted_ngrams)
        if outcome == "accepted":
            if config.audit:
                queue.appendleft((st, "audit", None))
            else:
                _finalize(st)
            return
        k = _attribute_failure(st)
        if (k is not None and plan.redos_after_join < config.section_join_redos
                and plan.sections[k].attempts < config.section_retries):
            plan.redos_after_join += 1
            stats["join_redos"] += 1
            _redo_section(st, k, "joined")
        else:
            _retry_or_give_up(st, "gate_failure")

    def _attribute_failure(st: DocState) -> Optional[int]:
        """Trace the joined document's last gate failure to the one section that caused it."""
        plan = st.section_plan
        failures = [e for e in st.gate_log if not e.get("ok") and "section" not in e]
        if not failures:
            return None
        stage, detail = failures[-1]["stage"], failures[-1]["detail"]
        texts = [s.text for s in plan.sections]
        spans = sections_mod.section_spans(texts)

        def containing(needle: str) -> Optional[int]:
            return next((i for i, t in enumerate(texts) if needle and needle in t), None)

        if stage == "G12_repetition":
            return sections_mod.repeated_section(texts)
        if stage == "G10_length":
            return max(range(len(texts)), key=lambda i: len(texts[i]))
        if stage == "G7_unplanned_pii" and isinstance(detail, list) and detail:
            return sections_mod.section_at(spans, detail[0].get("start", -1))
        if stage == "G9_slot" and isinstance(detail, list) and detail:
            return containing(detail[0].get("line", "")[:60])
        if stage == "G15_negative_placement" and isinstance(detail, list) and detail:
            return containing(detail[0]["negatives"][0])
        if stage == "G14_roles" and isinstance(detail, list) and detail:
            return containing(str(detail[0].get("value", "")))
        if stage == "G3_name_collision" and isinstance(detail, list) and detail:
            return containing(str(detail[0]))
        if stage == "G13_tabular":
            return max(range(len(texts)), key=lambda i: sum(
                1 for line in texts[i].split("\n")
                if gates.is_table_line(line) or gates.is_field_line(line)))
        return None

    def _covered_spans(st: DocState) -> List[str]:
        return [v for vals in st.result["output"].values() for v in vals]

    def _exempt_spans(st: DocState) -> List[str]:
        return [neg.found for neg in st.record.planted_negatives]

    def _section_keep(st: DocState, k: int) -> List[str]:
        sec = st.section_plan.sections[k]
        return ([st.record.planned[i].value for i in sec.items if st.record.planned[i].value]
                + [st.record.planted_negatives[j].found for j in sec.negatives])

    for st in states:
        _begin(st)

    while queue:
        kind = queue[0][1]
        jobs = [j for j in queue if j[1] == kind][:config.batch_size]
        for j in jobs:
            queue.remove(j)
        prompts, budgets = [], []
        for st, _kind, payload in jobs:
            if kind == "fresh":
                prompts.append(build_prompt(st.record))
                budgets.append(_token_budget(config, st.record.length_band[1]))
            elif kind == "repair":
                prompts.append(build_repair_prompt(st.record, st.last_text, payload))
                budgets.append(_token_budget(config, max(st.record.length_band[1], len(st.last_text))))
            elif kind == "section":
                sec = st.section_plan.sections[payload]
                sec.attempts += 1
                previous = [s.text for s in st.section_plan.sections[:payload]]
                prompts.append(build_section_prompt(st.record, st.section_plan, payload, previous))
                budgets.append(_token_budget(config, sec.chars[1]))
            elif kind == "section_repair":
                k, missing = payload
                sec = st.section_plan.sections[k]
                prompts.append(build_repair_prompt(st.record, sec.draft, missing))
                budgets.append(_token_budget(config, max(sec.chars[1], len(sec.draft))))
            elif kind == "section_audit_repair":
                k, findings, _attempt = payload
                sec = st.section_plan.sections[k]
                prompts.append(audit.build_audit_repair_prompt(
                    sec.text, findings, _section_keep(st, k), st.record.form, st.record.doc_seed))
                budgets.append(_token_budget(config, max(sec.chars[1], len(sec.text))))
            elif kind == "audit":
                prompts.append(audit.build_audit_prompt(
                    st.result["text"], _covered_spans(st), st.record.doc_seed,
                    clauses=[(pv.type, pv.value) for pv in st.record.planned
                             if pv.value_kind == "clause" and pv.value],
                    negatives=[(neg.type, neg.found) for neg in st.record.planted_negatives]))
                budgets.append(config.audit_max_new_tokens)
            else:
                keep = [pv.value for pv in st.record.planned if pv.value] + _exempt_spans(st)
                prompts.append(audit.build_audit_repair_prompt(
                    st.result["text"], payload, keep, st.record.form, st.record.doc_seed))
                budgets.append(_token_budget(config, max(st.record.length_band[1],
                                                         len(st.result["text"]))))

        def _salt(st: DocState, payload) -> int:
            k = payload if isinstance(payload, int) else (payload[0] if isinstance(payload, tuple) else 0)
            sec = st.section_plan.sections[k] if st.section_plan is not None and kind.startswith("section") else None
            return (st.record.doc_seed * 10 + st.repairs + 3 * st.audit_repairs
                    + (k * 17 + sec.attempts * 31 + sec.repairs * 7 if sec else 0))

        call_seed = hash(tuple(_salt(st, payload) for st, _k, payload in jobs)) & 0x7FFFFFFF
        temperature = {
            "fresh": config.temperature, "repair": config.repair_temperature,
            "section": config.temperature, "section_repair": config.repair_temperature,
            "section_audit_repair": config.repair_temperature,
            "audit": 0.0, "audit_repair": config.repair_temperature,
        }[kind]
        if before_generate is not None:
            before_generate(kind, len(jobs))
        started = time.time()
        texts = backend.generate(prompts, max_new_tokens=max(budgets), temperature=temperature,
                                 seed=call_seed)
        elapsed = time.time() - started
        finished_flags = getattr(backend, "last_finished", None) or [True] * len(texts)
        stats["generate_calls"] += 1
        stats[f"{kind}_jobs"] += len(jobs)
        if kind == "audit":
            stats["audit_seconds"] += elapsed

        for (st, _k, payload), text, finished in zip(jobs, texts, finished_flags):
            share = elapsed / len(jobs)
            if kind == "section_audit_repair" and (
                    payload[2] != st.attempt or (st.result is not None and not st.result.get("accepted"))):
                continue  # the document was given a new record, or given up, since this job was queued
            if kind == "audit":
                st.audit_seconds += share
                st.audit_calls += 1
                document = st.result["text"]
                pairs = audit.parse_audit_reply(text)
                findings = audit.filter_audit_findings(
                    document, _covered_spans(st), pairs, exempt_spans=_exempt_spans(st))
                st.audit_log.append({
                    "attempt": st.attempt, "audit_repairs": st.audit_repairs,
                    **audit.audit_stats(pairs, findings),
                    "exempt_negative_quotes": audit.exempt_quote_count(
                        document, pairs, _exempt_spans(st)),
                    "findings": [{k: v for k, v in f.items() if k != "residue"} for f in findings],
                })
                stats["audit_raw_quotes"] += len(pairs)
                stats["audit_kept_findings"] += len(findings)
                if not findings:
                    _finalize(st)
                    continue
                stats["audit_docs_with_findings"] += 1
                if st.audit_repairs < config.max_audit_repairs:
                    st.audit_repairs += 1
                    st.audit_repairs_total += 1
                    if st.section_plan is None:
                        queue.appendleft((st, "audit_repair", findings))
                        continue
                    texts_now = [s.text for s in st.section_plan.sections]
                    spans = sections_mod.section_spans(texts_now)
                    by_section: Dict[int, List[dict]] = collections.defaultdict(list)
                    for f in findings:
                        idx = sections_mod.section_at(spans, f["start"])
                        by_section[idx if idx is not None else len(spans) - 1].append(f)
                    for idx, fs in sorted(by_section.items()):
                        st.queued.add(idx)
                        st.section_plan.sections[idx].audit_repairs += 1
                        queue.appendleft((st, "section_audit_repair", (idx, fs, st.attempt)))
                else:
                    stats["audit_regenerations"] += 1
                    _retry_or_give_up(st, "audit_findings_remain")
                continue

            st.gen_seconds += share
            st.generate_calls += 1

            if kind in ("section", "section_repair", "section_audit_repair"):
                k = payload if kind == "section" else payload[0]
                sec = st.section_plan.sections[k]
                st.section_calls += 1
                outcome, missing = evaluate_section(
                    st, k, text, finished, taxonomy_index=taxonomy_index, place_names=place_names,
                    agency_names=agency_names, config=config)
                if kind == "section_repair":
                    stats["section_repairs_succeeded" if outcome == "ok" else "section_repairs_failed"] += 1
                if kind == "section_audit_repair":
                    stats["section_audit_repairs_gated_ok" if outcome == "ok"
                          else "section_audit_repairs_gated_fail"] += 1
                if outcome == "ok":
                    sec.done = True
                    st.queued.discard(k)
                    _advance(st)
                elif outcome == "repair":
                    sec.repairs += 1
                    sec.repairs_total += 1
                    queue.appendleft((st, "section_repair", (k, missing)))
                else:
                    sec.done = False
                    _section_failed(st, k)
                continue

            outcome, missing = evaluate_candidate(
                st, text, finished, taxonomy_index=taxonomy_index, public_figures=public_figures,
                place_names=place_names, agency_names=agency_names, config=config,
                accepted_ngrams=accepted_ngrams,
            )
            if kind == "repair":
                stats["repairs_succeeded" if outcome == "accepted" else "repairs_failed"] += 1
            if kind == "audit_repair":
                stats["audit_repairs_gated_ok" if outcome == "accepted"
                      else "audit_repairs_gated_fail"] += 1
            if outcome == "accepted":
                if config.audit:
                    queue.appendleft((st, "audit", None))
                else:
                    _finalize(st)
            elif outcome == "repair":
                st.repairs += 1
                st.repairs_total += 1
                queue.appendleft((st, "repair", missing))
            else:
                _retry_or_give_up(st, "gate_failure")
    stats["audit_seconds"] = round(stats["audit_seconds"], 1)
    return states, dict(stats)


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
    """Compare realised genre/form/length/type distribution against the plan."""
    genre_counts = collections.Counter(m["genre"] for m in accepted_meta)
    type_counts = collections.Counter(t for m in accepted_meta for t in m.get("types", []))
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
        "over_band_max": sum(1 for m in accepted_meta if m.get("band") and m["length"] > m["band"][1]),
        "type_counts": dict(type_counts.most_common()),
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
        lines.append(f"## {r['id']} -- {rec.genre} / {rec.variant} / {rec.form} / "
                     f"{rec.profile}{' / PII-free' if rec.pii_free else ''} / "
                     f"{len(r['text'])} tegn\n")
        lines.append("**Text:**\n")
        lines.append("```\n" + r["text"] + "\n```\n")
        lines.append("**Labels:**\n")
        for etype, spans in sorted(r["output"].items()):
            lines.append(f"- `{etype}`: {spans}")
        if not r["output"]:
            lines.append("- (none: PII-free document)")
        if r.get("clause_extensions"):
            lines.append(f"\n**Clause labels extended over a completing date:** "
                         f"{r['clause_extensions']}")
        state = r["state"]
        if state.section_plan is not None:
            lines.append("\n**Sections:** " + "; ".join(
                f"{s.index + 1}. {s.role_heading if s.heading else '(flowing)'} "
                f"[{s.kind}, {s.load} items, {s.attempts} call(s), {s.repairs_total} repair(s)]"
                for s in state.section_plan.sections))
        if rec.planted_negatives:
            lines.append("\n**Planted hard negatives (verbatim in the text, unlabelled by design):**")
            for neg in rec.planted_negatives:
                lines.append(f"- `{neg.type}`: {neg.text!r}"
                             + (f" (labelled as its own type: {neg.also_labelled})" if neg.also_labelled else ""))
        audit_findings = [f for entry in r["state"].audit_log for f in entry["findings"]]
        if audit_findings:
            lines.append("\n**G11 audit findings (never labels; repaired or regenerated):**")
            for finding in audit_findings:
                lines.append(f"- `{finding['reason']}`: {finding['quote']!r}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def measure_g7_false_positive_rate(paths: List[str], place_names: Set[str], agency_names: Set[str], max_docs: int = 20) -> dict:
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
    return {
        "docs_checked": len(results), "total_findings": total_findings,
        "docs_rejected": sum(1 for r in results if not r["clean"]),
        "reject_findings": sum(1 for r in results for f in r["findings"] if f["action"] == "reject"),
        "label_findings": sum(1 for r in results for f in r["findings"] if f["action"] == "label"),
        "detail": results,
    }


# Share of documents planned in Nynorsk. `docs/SYNTHETIC_DATA_SPEC.md` Section 4
# asks for a deliberate mix and the project's target is 35% accepted. Pilot v2
# planned 35% and accepted 26%, because a Nynorsk document fails the verbatim
# gate more often -- the model drifts into Bokmål inflections around a seeded
# Bokmål-free clause. A document's form is fixed by the plan and every retry
# keeps it, so the fix is to plan a higher share rather than to let a failed
# Nynorsk document come back as Bokmål.
NN_PLAN_SHARE = 0.45

# Genres in which a real document would carry a phone number or an email
# address. Pilot v2 accepted 1 PHONE and 2 EMAIL spans in 46 documents, which
# is not what Norwegian correspondence looks like; these genres get a floor.
CONTACT_FLOOR_SHARE = 0.38

# Share of letter and decision documents (`gendoc_genres.ID_BLOCK_GENRES`, never minimal or
# PII-free ones) whose identification block carries the subject's address. The gold set has
# an address block in nearly every official document about a named person; pilot v4's
# generated ones had it in a quarter. The postal code needs no separate item: it is the four
# digits inside the address span and `build_output` labels it POSTAL_CODE by the nesting rule.
ID_BLOCK_P = 0.85

# How many coverage-scheduled types one document may be asked to host, by
# density profile. A 600-character note cannot absorb a forced type without
# becoming the checklist pilot v1 produced; a case file absorbs several.
MAX_FORCED_BY_PROFILE = {
    "pii_free": 0, "minimal": 0, "light": 1, "typical": 2, "dense": 5, "case_file": 8,
}


def _draw_profiles(rng: random.Random, n: int, shares: Optional[Dict[str, float]] = None) -> List[str]:
    """Allocate density profiles across a batch by their target shares.

    Quotas are allocated by largest remainder rather than by an independent draw
    per document, so a 16-document smoke run still contains a case file and a
    PII-free document instead of depending on luck.

    Args:
        rng: Run-level RNG, used only to shuffle the allocation.
        n: Number of documents.
        shares: Profile shares overriding `gendoc_genres.PROFILES`, which is how
            a benchmark leans toward dense and case-file documents.

    Returns:
        One profile name per document, in shuffled order.
    """
    quotas = {name: (shares or {}).get(name, genres_mod.PROFILES[name]["share"]) * n
              for name in genres_mod.PROFILE_ORDER}
    counts = {name: int(q) for name, q in quotas.items()}
    remainder = n - sum(counts.values())
    for name, _frac in sorted(quotas.items(), key=lambda kv: -(kv[1] - int(kv[1])))[:remainder]:
        counts[name] += 1
    profiles = [name for name, count in counts.items() for _ in range(count)]
    rng.shuffle(profiles)
    return profiles


def _contact_types_for(genre: str) -> List[str]:
    """Return the contact types a genre should be nudged to carry, if it hosts them."""
    spec = genres_mod.GENRES[genre]
    return [t for t in ("PHONE", "EMAIL") if t in spec["values"] or t in spec["core"]]


def plan_batch(
    rng: random.Random, n: int, genre_list: List[str], forced_types: List[str],
    rare_force_share: float, coverage_target: int = 0,
    schedulable_types: Optional[List[str]] = None,
    mode: Optional[dataset_mod.DatasetMode] = None, clause_bank: Optional[dict] = None,
    coverage_margin: int = 0,
    natural_probe: Optional[Callable[[DocPlan, int], Set[str]]] = None,
) -> Tuple[List[DocPlan], dict]:
    """Fix genre, variant, form, density profile, length, type target and forced types.

    Density is a batch property. `_draw_profiles` allocates the profile mix,
    each profile draws its own length band, and the type target is the profile's
    range clamped by `gendoc_genres.type_ceiling` for the chosen genre and
    length -- so a dense document is long *and* type-rich and a short one stays
    writable.

    Coverage is a batch property too. With `coverage_target = K`, every
    schedulable type is scheduled into at least K documents, always in a genre
    `gendoc_genres.genres_hosting` says the type is plausible in, and never more
    than `MAX_FORCED_BY_PROFILE` of them into one document. Genres are chosen
    greedily to maximise the number of still-deficient types a document can
    host, which is what lets a 50-document run reach most of a 59-type taxonomy
    without any document turning into a checklist. Without `coverage_target`,
    genres cycle and only `gendoc_genres.RARE_TYPES` are scheduled, as before.

    Args:
        rng: Run-level RNG.
        n: Number of documents.
        genre_list: Genres the run may use.
        forced_types: Types the user forces into every record (`--force-types`).
        rare_force_share: Share of documents that get one scheduled rare type
            when coverage scheduling is off.
        coverage_target: K -- minimum documents per schedulable type, or 0 to
            disable coverage scheduling.
        schedulable_types: Types coverage scheduling should cover; defaults to
            every type any requested genre hosts.
        mode: Dataset mode; sets the profile shares and how many hard negatives
            each document plans. None is the training distribution.
        clause_bank: The clause bank the run samples from. Coverage scheduling
            only places a clause type in a genre the bank can actually fill.
        coverage_margin: Extra documents a type is aimed at on top of
            `coverage_target`, to absorb discards and sampler drops.
        natural_probe: `(plan, k) -> types the sampler draws for that plan with
            nothing forced`. When given, a type that the plans already carry often
            enough on their own is scheduled fewer times, which is what leaves room
            for the scarce ones.

    Returns:
        Tuple of (one `DocPlan` per document, a scheduling report with the
        planned per-type document counts, the shortfalls and the types no
        requested genre can host).
    """
    profiles = _draw_profiles(rng, n, mode.profile_shares if mode else None)
    pii_free_genres = [g for g in genre_list if g in genres_mod.PII_FREE_GENRES]
    plans: List[DocPlan] = []
    for i, profile in enumerate(profiles):
        pii_free = profile == "pii_free" and bool(pii_free_genres)
        if profile == "pii_free" and not pii_free_genres:
            profile = "minimal"
        if pii_free:
            genre = rng.choice(pii_free_genres)
        else:
            # A circular has no data subject by definition, so it is only ever
            # drawn for a PII-free plan: the smoke run produced a "Rundskriv"
            # addressed to one named person whose whole content was her postal
            # code, which is not a document anybody writes.
            ordinary = [g for g in genre_list if g not in genres_mod.PII_FREE_GENRES] or genre_list
            genre = ordinary[i % len(ordinary)]
        band = rng.choice(genres_mod.PROFILES[profile]["bands"])
        plans.append(DocPlan(
            idx=i, genre=genre, variant=rng.choice(genres_mod.GENRES[genre]["variants"]),
            form="nn" if rng.random() < NN_PLAN_SHARE else "nb",
            length_band=band, forced_types=list(forced_types), profile=profile,
            type_target=rng.randint(*genres_mod.PROFILES[profile]["types"]),
            art9_cap=genres_mod.art9_cap(rng, profile), pii_free=pii_free,
        ))

    if coverage_target > 0:
        natural = (_natural_expectation(plans, natural_probe) if natural_probe else None)
        report = _schedule_coverage(rng, plans, genre_list, coverage_target, schedulable_types or [],
                                    clause_bank=clause_bank, margin=coverage_margin, natural=natural)
    else:
        report = _schedule_rare_types(rng, plans, rare_force_share)

    # Instances and the identification block are drawn from their own stream, after the
    # coverage scheduling has settled each plan's genre.
    irng = random.Random(rng.getrandbits(32))
    for plan in plans:
        if plan.pii_free:
            continue
        spec = genres_mod.GENRES[plan.genre]
        ceiling = genres_mod.type_ceiling(plan.length_band[1], spec.get("density_factor", 1.0))
        plan.type_target = max(1, min(plan.type_target, ceiling))
        plan.instances = genres_mod.draw_instance_counts(irng, plan.genre, plan.profile)
        if (plan.genre in genres_mod.ID_BLOCK_GENRES and plan.profile != "minimal"
                and irng.random() < ID_BLOCK_P):
            plan.id_block = ["ADDRESS"]
        # A contact floor, applied where the genre hosts one: pilot v2's
        # accepted batch carried one phone number in 46 documents.
        contact = _contact_types_for(plan.genre)
        if (contact and plan.profile not in ("pii_free", "minimal")
                and not any(t in plan.forced_types for t in contact)
                and rng.random() < CONTACT_FLOOR_SHARE):
            plan.forced_types.append(rng.choice(contact))
    if mode and mode.negatives_by_profile:
        for plan in plans:
            lo, hi = mode.negatives_by_profile.get(plan.profile, (0, 0))
            plan.n_negatives = 0 if plan.pii_free else rng.randint(lo, hi)
    report["dataset"] = mode.name if mode else "train"
    report["planned_negatives"] = sum(p.n_negatives for p in plans)
    report["planned_profiles"] = dict(collections.Counter(p.profile for p in plans))
    report["planned_pii_free"] = sum(1 for p in plans if p.pii_free)
    report["planned_instances"] = {
        "documents_with_a_repeated_type": sum(1 for p in plans if p.instances),
        "by_type": dict(collections.Counter(t for p in plans for t in p.instances)),
        "by_count": dict(sorted(collections.Counter(n for p in plans for n in p.instances.values()).items())),
    }
    report["planned_id_block_address"] = sum(1 for p in plans if p.id_block)
    report["planned_nn_share"] = round(sum(1 for p in plans if p.form == "nn") / max(1, len(plans)), 3)
    report["planned_type_target"] = {
        "min": min((p.type_target for p in plans), default=None),
        "max": max((p.type_target for p in plans), default=None),
        "mean": round(sum(p.type_target for p in plans) / max(1, len(plans)), 2),
    }
    return plans, report


def _schedule_rare_types(rng: random.Random, plans: List[DocPlan], rare_force_share: float) -> dict:
    """Schedule `gendoc_genres.RARE_TYPES` across the batch, one per chosen document."""
    scheduled: collections.Counter = collections.Counter()
    for plan in plans:
        if plan.pii_free or MAX_FORCED_BY_PROFILE[plan.profile] == 0:
            continue
        spec = genres_mod.GENRES[plan.genre]
        plausible = [t for t in genres_mod.RARE_TYPES
                     if t in spec["judgement"] and t not in plan.forced_types
                     and (t != "ETHNICITY" or plan.genre in genres_mod.ETHNICITY_ALLOWED_GENRES)]
        if plausible and rng.random() < rare_force_share:
            low = min(scheduled[t] for t in plausible)
            pick = rng.choice([t for t in plausible if scheduled[t] == low])
            scheduled[pick] += 1
            plan.forced_types.append(pick)
    return {"mode": "rare_types", "scheduled": dict(scheduled.most_common()),
            "coverage_target": 0, "shortfall": [], "unreachable": []}


# How often a document of each profile survives every gate, lowest risk first.
# Pilot v3 discarded 7 of 50 documents and every one of them was dense or a case
# file (7 of 17); none of the 33 lighter ones. A type scheduled only into dense
# and case-file documents therefore reached its target only when none of them
# was lost, which is why CREDIT_CARD and CRYPTO, scheduled three times each into
# the same three large documents, were absent from the output.
_PROFILE_RISK = {"pii_free": 0, "minimal": 0, "light": 0, "typical": 0, "dense": 1, "case_file": 2}

# Share of documents of each profile that survive every gate: pilot v3 lost 4 of
# its 10 dense documents and 3 of its 7 case files, and none of the other 33.
_PROFILE_SURVIVAL = {"dense": 0.6, "case_file": 0.57}
_DEFAULT_SURVIVAL = 0.97
_FORCED_SLOT_SURVIVAL = 0.85
NATURAL_PROBES = 3


def _natural_expectation(plans: List[DocPlan], probe: Callable[[DocPlan, int], Set[str]]) -> Dict[str, float]:
    """Estimate how many surviving documents carry each type with nothing forced.

    Coverage scheduling used to treat every type as absent until forced, so it
    spent a case file's eight slots on PERSON-adjacent types that appear in half
    the batch anyway and starved the scarce ones. The sampler is cheap, so the
    estimate is the sampler itself: each non-PII-free plan is drawn
    `NATURAL_PROBES` times with no forced types and the type's share of those
    draws is weighted by the profile's survival rate.

    Args:
        plans: The plans, with their genres as drawn before scheduling.
        probe: `(plan, k) -> set of types the k-th draw carries`.

    Returns:
        `{type: expected surviving documents}`.
    """
    expected: collections.Counter = collections.Counter()
    for plan in plans:
        if plan.pii_free:
            continue
        survival = _PROFILE_SURVIVAL.get(plan.profile, _DEFAULT_SURVIVAL)
        for k in range(NATURAL_PROBES):
            for etype in probe(plan, k):
                expected[etype] += survival / NATURAL_PROBES
    return dict(expected)


def _schedule_coverage(
    rng: random.Random, plans: List[DocPlan], genre_list: List[str], target: int,
    schedulable: List[str], clause_bank: Optional[dict] = None, margin: int = 0,
    natural: Optional[Dict[str, float]] = None,
) -> dict:
    """Assign genres and forced types so every schedulable type reaches K documents.

    The pass is greedy and deliberately simple: each document is given the genre
    that covers the largest remaining deficit, and the deficit types that genre
    hosts are attached to it up to its profile's limit. A type whose host genres
    are all outside `genre_list`, or that the clause bank cannot fill in any of
    them, is reported as unreachable rather than forced somewhere implausible.

    Three things were added after pilot v3 realised 54 of 57 types:

    * **Reliable documents first.** Plans are visited light and typical before
      dense before case file, and the scarcest types pick first, so the types
      that are hardest to land are scheduled into the documents least likely to
      be discarded.
    * **A margin.** Each type is scheduled `target + margin` times, because a
      forced slot is lost to a discard or a sampler drop about a third of the
      time and exactly K slots meant exactly K chances.
    * **Budgets the sampler enforces.** A type is only scheduled into a document
      whose Art. 9 and health-family budgets still have room, so the sampler does
      not silently drop it (GENETIC_DATA in a typical-profile health genre, whose
      core HEALTH had already used the one health-family slot).

    Args:
        rng: Run-level RNG, for tie-breaking.
        plans: The plans to mutate in place.
        genre_list: Genres the run may use.
        target: Documents each type should reach.
        schedulable: Types to cover.
        clause_bank: Clause bank to check clause types against; None skips it.
        margin: Documents each type is aimed at beyond `target`.
        natural: Expected surviving documents per type that the plans carry with
            nothing forced (`_natural_expectation`). A type's slots are then only
            the shortfall, divided by the survival rate a forced slot has; None
            schedules the full `target + margin` for every type.

    Returns:
        A scheduling report.
    """
    hosts = {t: [g for g in genres_hosting_cached(t, clause_bank) if g in genre_list] for t in schedulable}
    unreachable = sorted(t for t, gs in hosts.items() if not gs)
    want = target + margin
    if natural is None:
        deficit = {t: want for t in schedulable if hosts[t]}
    else:
        deficit = {t: math.ceil(max(0.0, want - natural.get(t, 0.0)) / _FORCED_SLOT_SURVIVAL)
                   for t in schedulable if hosts[t]}
    assignable = [p for p in plans if not p.pii_free and MAX_FORCED_BY_PROFILE[p.profile] > 0]
    order = sorted(assignable, key=lambda p: (_PROFILE_RISK[p.profile], -MAX_FORCED_BY_PROFILE[p.profile], p.idx))
    scheduled: collections.Counter = collections.Counter()

    used_genres: collections.Counter = collections.Counter(p.genre for p in plans)
    for plan in order:
        room = MAX_FORCED_BY_PROFILE[plan.profile] - len(plan.forced_types)
        if room <= 0:
            continue
        wanted = [t for t, d in deficit.items() if d > 0 and t not in plan.forced_types]
        if not wanted:
            break
        # Score a genre by how much *scarce* deficit it can absorb, not by how
        # many types it hosts: MILITARY_ID has one possible genre and PHONE has
        # twenty, so a plain count would spend every forced slot on the types
        # that were going to appear anyway. The novelty divisor keeps the
        # scheduler from collapsing the batch onto the three or four broadest
        # genres, which would trade the Section 4 genre spread for coverage.
        best_genre, best_types, best_score = None, [], 0.0
        for genre in genre_list:
            if genre in genres_mod.PII_FREE_GENRES and not plan.pii_free:
                continue
            hostable = _hostable_for(genre, wanted, hosts, plan.art9_cap,
                                     genres_mod.health_family_cap(plan.profile))[:room]
            if not hostable:
                continue
            score = (sum(1.0 / len(hosts[t]) for t in hostable)
                     / (1.0 + 0.60 * used_genres[genre]))
            if score > best_score:
                best_genre, best_types, best_score = genre, hostable, score
        if best_genre is None:
            continue
        if best_genre != plan.genre:
            used_genres[plan.genre] -= 1
            used_genres[best_genre] += 1
            plan.genre = best_genre
            plan.variant = rng.choice(genres_mod.GENRES[best_genre]["variants"])
            if plan.profile == "pii_free":
                plan.pii_free = best_genre in genres_mod.PII_FREE_GENRES
        for etype in best_types:
            plan.forced_types.append(etype)
            deficit[etype] -= 1
            scheduled[etype] += 1

    shortfall = [{"type": t, "scheduled": scheduled[t], "target": want}
                 for t in sorted(deficit) if deficit[t] > 0]
    return {"mode": "coverage_target", "coverage_target": target, "coverage_margin": margin,
            "scheduled": dict(scheduled.most_common()), "shortfall": shortfall,
            "unreachable": unreachable}


def _hostable_for(
    genre: str, wanted: Sequence[str], hosts: Dict[str, List[str]], art9_cap: int,
    health_cap: int = 99,
) -> List[str]:
    """Return the deficient types a genre can host, scarcest first, within the sampler's budgets.

    A document's Art. 9 and health-family budgets are decided by its profile, so
    the scheduler must respect them: scheduling three special categories into a
    short document only to have the sampler drop two of them wastes the forced
    slots and is why RELIGIOUS_BELIEF and GENETIC_DATA reached no document in an
    earlier run. The health-family cap is the same trap: a typical-profile
    `hospital_discharge` already carries HEALTH in its core, which uses its one
    health-family slot, so a scheduled GENETIC_DATA was refused there.

    Args:
        genre: Candidate genre id.
        wanted: Types still short of their target.
        hosts: Type -> the requested genres that host it.
        art9_cap: How many Art. 9 categories this document may carry.
        health_cap: How many health-family types this document may carry.

    Returns:
        Hostable type names, scarcest host set first.
    """
    core = genres_mod.GENRES[genre]["core"]
    budget = max(0, art9_cap - sum(1 for t in core if t in genres_mod.SPECIAL_CATEGORIES))
    health_budget = max(0, health_cap - sum(1 for t in core if t in genres_mod.HEALTH_FAMILY))
    hostable = sorted((t for t in wanted if genre in hosts[t]),
                      key=lambda t: (len(hosts[t]), t))
    picked, art9_used, health_used = [], 0, 0
    for etype in hostable:
        if etype in genres_mod.SPECIAL_CATEGORIES and art9_used >= budget:
            continue
        if etype in genres_mod.HEALTH_FAMILY and health_used >= health_budget:
            continue
        art9_used += etype in genres_mod.SPECIAL_CATEGORIES
        health_used += etype in genres_mod.HEALTH_FAMILY
        picked.append(etype)
    return picked


_HOSTS_CACHE: Dict[Tuple[str, int], List[str]] = {}


def genres_hosting_cached(etype: str, clause_bank: Optional[dict] = None) -> List[str]:
    """Memoised `gendoc_genres.genres_hosting`; the scheduler calls it O(n*genres) times."""
    key = (etype, id(clause_bank))
    if key not in _HOSTS_CACHE:
        _HOSTS_CACHE[key] = genres_mod.genres_hosting(etype, clause_bank)
    return _HOSTS_CACHE[key]


def _bucket(value: int, edges: Sequence[int]) -> str:
    """Return the label of the histogram bucket a value falls in."""
    for lo, hi in zip(edges, list(edges[1:]) + [None]):
        if hi is None or value < hi:
            return f"{lo}-{hi - 1}" if hi else f"{lo}+"
    return str(value)


def coverage_report(
    accepted_meta: List[dict], schedulable: List[str], target: int, plan_report: dict,
) -> dict:
    """Report how many accepted documents each type reached, and what fell short.

    The 57-type taxonomy is to become project-wide, so a type that the synthetic
    data never exercises is a gap that has to be found now rather than after the
    gold set is relabelled.

    Args:
        accepted_meta: One dict per accepted document with its realised `types`.
        schedulable: Types coverage scheduling aimed to cover.
        target: Documents per type the run aimed for.
        plan_report: The scheduling report from `plan_batch`.

    Returns:
        The coverage section of the gate report.
    """
    counts: collections.Counter = collections.Counter()
    for meta in accepted_meta:
        counts.update(sorted(set(meta["types"])))
    below = [{"type": t, "documents": counts.get(t, 0), "target": target}
             for t in schedulable if counts.get(t, 0) < target]
    return {
        "target_documents_per_type": target,
        "types_seen": len(counts),
        "per_type_documents": dict(counts.most_common()),
        "types_absent": sorted(t for t in schedulable if not counts.get(t)),
        "types_below_target": sorted(below, key=lambda r: (r["documents"], r["type"])),
        "unreachable_in_requested_genres": plan_report.get("unreachable", []),
        "planned_schedule": plan_report,
    }


def sectioning_report(accepted: List[dict], states: List[DocState], plans: List[DocPlan]) -> dict:
    """Report how much of the batch was generated in sections and how the sections fared.

    The number that matters is the acceptance rate of the dense and case-file
    profiles: pilot v4 accepted 6 of 26 of them, and a benchmark whose large
    documents are lost is easier than planned. Section-level failures are counted
    apart from document-level ones so a run shows where the retries went.

    Args:
        accepted: Accepted document dicts.
        states: Every document state.
        plans: Every plan.

    Returns:
        The sectioning section of the gate report.
    """
    sectioned = [r for r in accepted if r["state"].section_plan is not None]
    per_profile = {}
    for profile in sorted({p.profile for p in plans}):
        wanted = [st for st in states if st.plan.profile == profile]
        got = [st for st in wanted if st.result and st.result.get("accepted")]
        per_profile[profile] = {
            "planned": len(wanted), "accepted": len(got),
            "sectioned_accepted": sum(1 for st in got if st.section_plan is not None)}
    section_events = [e for st in states for e in st.gate_log if e.get("scope") == "section"]
    doc_events = [e for st in states for e in st.gate_log if not e.get("ok") and "section" not in e]
    loads = [s.load for r in sectioned for s in r["state"].section_plan.sections]
    return {
        "accepted_sectioned": len(sectioned),
        "accepted_total": len(accepted),
        "sectioned_share_of_accepted": round(len(sectioned) / len(accepted), 3) if accepted else 0.0,
        "sections_per_doc": dict(sorted(collections.Counter(
            len(r["state"].section_plan.sections) for r in sectioned).items())),
        "items_per_section": {"max": max(loads, default=0), "mean": round(sum(loads) / len(loads), 2)
                              if loads else None,
                              "over_cap": sum(1 for n in loads if n > sections_mod.MAX_ITEMS)},
        "headings_visible_share": round(sum(1 for r in sectioned
                                            if r["state"].section_plan.headings_visible) / len(sectioned), 3)
        if sectioned else None,
        "per_profile": per_profile,
        "section_failure_stages": dict(collections.Counter(
            e["stage"] for e in section_events if not e.get("ok"))),
        "joined_failure_stages": dict(collections.Counter(e["stage"] for e in doc_events)),
        "section_calls": sum(st.section_calls for st in states),
        "section_attempts": sum(s.attempts for st in states if st.section_plan for s in st.section_plan.sections),
        "section_repairs": sum(s.repairs_total for st in states if st.section_plan
                               for s in st.section_plan.sections),
        "redos_after_join": sum(st.section_plan.redos_after_join for st in states if st.section_plan),
        "headline_headings": dict(collections.Counter(
            s.role_heading for r in sectioned for s in r["state"].section_plan.sections).most_common(20)),
    }


def density_report(accepted: List[dict], plans: List[DocPlan]) -> dict:
    """Report the realised density distribution: types, distinct spans and length.

    A fixed type band is itself a pattern a detector learns, so the run aims at
    a distribution and has to be able to show the one it hit.

    Args:
        accepted: Accepted document dicts.
        plans: Every plan, so planned and realised profiles can be compared.

    Returns:
        The density section of the gate report.
    """
    types_per_doc = [len(r["output"]) for r in accepted]
    spans_per_doc = [sum(len(v) for v in r["output"].values()) for r in accepted]
    lengths = [len(r["text"]) for r in accepted]
    ages = [r["record"].person.age() for r in accepted if r["record"].person]
    contact = sum(1 for r in accepted if r["output"].get("PHONE") or r["output"].get("EMAIL"))
    parties = [len(r["record"].parties) for r in accepted]
    # The type ceiling is computed from the planned length band, but the model
    # decides the realised length, and a model that undershoots a 6,000-character
    # case file by half reproduces pilot v1's failure -- too many types in too
    # little text -- without any gate firing. This counts it rather than
    # rejecting on it: rejecting would discard documents whose labels are
    # perfectly correct, and the number is what says whether the length prompt
    # or the profile's band needs changing.
    over_dense = [
        {"id": r["id"], "types": len(r["output"]), "length": len(r["text"]),
         "ceiling_at_realised_length": genres_mod.type_ceiling(
             len(r["text"]), genres_mod.GENRES[r["record"].genre].get("density_factor", 1.0))}
        for r in accepted
        if len(r["output"]) > genres_mod.type_ceiling(
            len(r["text"]), genres_mod.GENRES[r["record"].genre].get("density_factor", 1.0))
    ]
    return {
        "profiles_planned": dict(collections.Counter(p.profile for p in plans)),
        "profiles_accepted": dict(collections.Counter(r["record"].profile for r in accepted)),
        "pii_free_planned": sum(1 for p in plans if p.pii_free),
        "pii_free_accepted": sum(1 for r in accepted if r["record"].pii_free),
        "types_per_doc_hist": dict(sorted(collections.Counter(
            _bucket(t, [0, 1, 3, 6, 10, 15, 20, 26]) for t in types_per_doc).items())),
        "distinct_spans_per_doc_hist": dict(sorted(collections.Counter(
            _bucket(t, [0, 1, 5, 10, 20, 35, 55, 80]) for t in spans_per_doc).items())),
        "length_hist": dict(sorted(collections.Counter(
            _bucket(t, [0, 400, 800, 1600, 2800, 4000, 5500, 7000]) for t in lengths).items())),
        "distinct_spans": {"min": min(spans_per_doc, default=None), "max": max(spans_per_doc, default=None),
                           "mean": round(sum(spans_per_doc) / len(spans_per_doc), 2) if spans_per_doc else None},
        "parties_per_doc": {"min": min(parties, default=None), "max": max(parties, default=None),
                            "mean": round(sum(parties) / len(parties), 2) if parties else None},
        "subject_age_hist": dict(sorted(collections.Counter(
            _bucket(a, [0, 18, 30, 45, 60, 68, 76]) for a in ages).items())),
        "subject_age_mean": round(sum(ages) / len(ages), 1) if ages else None,
        "phone_or_email_share": round(contact / len(accepted), 3) if accepted else 0.0,
        "over_dense_for_realised_length": over_dense,
    }


def multi_instance_report(accepted: List[dict], plans: List[DocPlan], clause_types: Sequence[str]) -> dict:
    """Report how many spans of each clause type the accepted documents carry, and where.

    Pilot v4 had exactly one span per clause type per document in all 39 documents, so the
    number to show is the histogram itself: for each clause type, how many documents carry
    1, 2, 3 or 4 spans of it. The per-family table is the comparison with the gold set
    (inspection reports average 5.3 CRIMINAL spans, concern reports 8.1 HEALTH spans), and
    the planned-versus-realised table says how much of what was planned the record could
    supply.

    Args:
        accepted: Accepted document dicts.
        plans: Every plan.
        clause_types: Taxonomy types of kind `clause`.

    Returns:
        The multi-instance section of the gate report.
    """
    import gendoc_sections as sec
    hist: Dict[str, Dict[int, int]] = {}
    for etype in clause_types:
        counts = collections.Counter(len(r["output"][etype]) for r in accepted if etype in r["output"])
        if counts:
            hist[etype] = dict(sorted(counts.items()))
    families: Dict[str, List[dict]] = collections.defaultdict(list)
    for r in accepted:
        families[sec.family_for(r["record"].genre)].append(r)
    by_family = {}
    for fam, docs in sorted(families.items()):
        n = len(docs)
        by_family[fam] = {
            "documents": n,
            "CRIMINAL_spans_per_doc": round(sum(len(d["output"].get("CRIMINAL", [])) for d in docs) / n, 2),
            "HEALTH_spans_per_doc": round(sum(len(d["output"].get("HEALTH", [])) for d in docs) / n, 2),
            "docs_with_2plus_CRIMINAL": sum(1 for d in docs if len(d["output"].get("CRIMINAL", [])) >= 2),
            "docs_with_2plus_HEALTH": sum(1 for d in docs if len(d["output"].get("HEALTH", [])) >= 2),
        }
    n_all = max(1, len(accepted))
    planned_vs_realised = {}
    for etype in genres_mod.MULTI_INSTANCE_TYPES:
        asked = [r for r in accepted if etype in r["record"].instances_planned]
        planned_vs_realised[etype] = {
            "documents_planned_repeated": len(asked),
            "realised_repeated": sum(1 for r in asked if r["record"].instances_realised.get(etype, 0) >= 2),
            "instances_asked": sum(r["record"].instances_planned[etype] for r in asked),
            "instances_realised": sum(r["record"].instances_realised.get(etype, 1) if etype in
                                      r["record"].instances_planned and etype in r["output"] else 0
                                      for r in asked),
        }
    items_by_profile: Dict[str, List[int]] = collections.defaultdict(list)
    for r in accepted:
        items_by_profile[r["record"].profile].append(len(r["record"].planned) + len(r["record"].planted_negatives))
    return {
        "spans_per_document_histogram": hist,
        "criminal_and_health_by_genre_family": by_family,
        "all_documents": {
            "CRIMINAL_spans_per_doc": round(sum(len(r["output"].get("CRIMINAL", [])) for r in accepted) / n_all, 2),
            "HEALTH_spans_per_doc": round(sum(len(r["output"].get("HEALTH", [])) for r in accepted) / n_all, 2),
        },
        "planned_vs_realised": planned_vs_realised,
        "planned_items_per_document": {p: {"mean": round(sum(v) / len(v), 1), "max": max(v)}
                                       for p, v in sorted(items_by_profile.items())},
        "political_hosts": dict(collections.Counter(
            r["record"].genre for r in accepted if "POLITICAL" in r["output"])),
    }


def coherence_report(config: GenerationConfig) -> dict:
    """Report what the cast-coherence check found, repaired and rejected in the run."""
    return coherence.summarise(config.coherence_log, config.coherence_rejected)


def identification_report(accepted: List[dict]) -> dict:
    """Report how often the documents carry an address block, a postal code, an e-mail and a case number.

    The gold set carries these in nearly every official document about a named person; pilot v4's
    generated ones in a quarter. The second rate leaves out PII-free and minimal documents and
    the genres that are not letters or decisions about a named person, which is the population the
    identification-block change is aimed at.

    Args:
        accepted: Accepted document dicts.

    Returns:
        Rates of ADDRESS, POSTAL_CODE, EMAIL and CASE_NUMBER overall and in letter and decision genres.
    """
    def rates(docs: List[dict]) -> dict:
        n = max(1, len(docs))
        return {"documents": len(docs),
                **{t: round(sum(1 for d in docs if t in d["output"]) / n, 3)
                   for t in ("ADDRESS", "POSTAL_CODE", "EMAIL", "CASE_NUMBER")}}

    letters = [r for r in accepted if r["record"].genre in genres_mod.ID_BLOCK_GENRES
               and not r["record"].pii_free and r["record"].profile != "minimal"]
    return {"all_documents": rates(accepted), "letter_and_decision_documents": rates(letters)}


def negatives_report(accepted: List[dict], states: List[DocState], plans: List[DocPlan]) -> dict:
    """Report what happened to the planted hard negatives.

    A negative that is in an accepted document is, by G2, verbatim in its text;
    what the run still has to show is that none was *labelled* (apart from the
    declared `also_labelled` value of another type) and how often the auditor
    wanted to flag one and was overruled by the exemption.

    Args:
        accepted: Accepted document dicts.
        states: Every document state.
        plans: Every plan.

    Returns:
        The hard-negative section of the gate report.
    """
    planted = [(r["id"], neg) for r in accepted for neg in r["record"].planted_negatives]
    labelled_by_mistake = []
    for doc_id, neg in planted:
        record = next(r for r in accepted if r["id"] == doc_id)
        for etype, spans in record["output"].items():
            allowed = neg.also_labelled.get(etype)
            for span in spans:
                if span == allowed or len(span) < 4:
                    continue
                if re.search(r"(?<!\w)" + re.escape(span) + r"(?!\w)", neg.found) or neg.found in span:
                    labelled_by_mistake.append({"id": doc_id, "type": etype, "span": span,
                                                "negative": neg.text})
    template_use = collections.Counter(neg.template for _doc, neg in planted)
    return {
        "planned": sum(p.n_negatives for p in plans),
        "planted_in_accepted_documents": len(planted),
        "distinct_templates": len(template_use),
        "max_reuse_of_one_text": max(template_use.values(), default=0),
        "reuse_histogram": dict(sorted(collections.Counter(template_use.values()).items())),
        "per_document": dict(sorted(collections.Counter(
            len(r["record"].planted_negatives) for r in accepted).items())),
        "by_form": dict(collections.Counter(r["record"].form for r in accepted
                                            for _neg in r["record"].planted_negatives)),
        "kept_verbatim": sum(1 for doc_id, neg in planted
                             if gates.negative_occurrences(
                                 next(r for r in accepted if r["id"] == doc_id)["text"], neg.text)),
        "capitalised_at_sentence_start": sum(1 for _doc, neg in planted if neg.found != neg.text),
        "labelled_by_mistake": labelled_by_mistake,
        "audit_quotes_overruled_by_exemption": sum(
            e.get("exempt_negative_quotes", 0) for st in states for e in st.audit_log),
        "by_type": dict(collections.Counter(neg.type for _doc, neg in planted)),
        "distinct_texts": len({neg.text for _doc, neg in planted}),
    }


def tabular_report(accepted: List[dict]) -> dict:
    """Report the table and field share of the accepted documents (G13's measurements).

    Args:
        accepted: Accepted document dicts, each with the `tabular` profile
            `evaluate_candidate` measured.

    Returns:
        Per-document shares, their summary, and how many documents carry a table.
    """
    profiles = {r["id"]: r.get("tabular", {}) for r in accepted}
    table = [p.get("table_line_share", 0.0) for p in profiles.values()]
    field = [p.get("field_line_share", 0.0) for p in profiles.values()]
    slots = [p.get("value_slot_share", 0.0) for p in profiles.values()]
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {
        "per_document": {i: {k: p.get(k) for k in ("table_line_share", "field_line_share", "table_rows",
                                                   "value_slot_share", "values_in_slots")}
                         for i, p in profiles.items()},
        "table_line_share": {"mean": mean(table), "max": max(table, default=None)},
        "field_line_share": {"mean": mean(field), "max": max(field, default=None)},
        "value_slot_share": {"mean": mean(slots), "max": max(slots, default=None)},
        "documents_with_a_table": sum(1 for p in profiles.values() if p.get("table_rows")),
    }


def audit_report(states: List[DocState], accepted: List[dict], wall_seconds: float) -> dict:
    """Report what G11 found, what it repaired and what it cost.

    Args:
        states: Every document state, accepted or not.
        accepted: Accepted document dicts.
        wall_seconds: Total run wall time, for the per-document audit cost share.

    Returns:
        The G11 section of the gate report.
    """
    audit_seconds = sum(st.audit_seconds for st in states)
    reasons: collections.Counter = collections.Counter()
    kept = raw = 0
    for st in states:
        for entry in st.audit_log:
            raw += entry["raw_quotes"]
            kept += entry["kept"]
            for finding in entry["findings"]:
                reasons[finding["reason"]] += 1
    audited = sum(1 for st in states if st.audit_calls)
    return {
        "documents_audited": audited,
        "audit_passes": sum(st.audit_calls for st in states),
        "raw_quotes": raw,
        "findings_kept_after_substring_and_label_filter": kept,
        "findings_by_reason": dict(reasons),
        "documents_with_findings": sum(1 for st in states if any(e["kept"] for e in st.audit_log)),
        "audit_repairs": sum(st.audit_repairs_total for st in states),
        "audit_seconds_total": round(audit_seconds, 1),
        "audit_seconds_per_audited_doc": round(audit_seconds / audited, 1) if audited else None,
        "audit_share_of_wall_time": round(audit_seconds / wall_seconds, 3) if wall_seconds else None,
        "findings_are_never_labels": True,
    }


def _make_natural_probe(run_seed: int, taxonomy_index: Dict[str, dict], clause_bank: dict,
                        public_figures: Set[str]) -> Callable[[DocPlan, int], Set[str]]:
    """Build the sampler-backed probe `plan_batch` uses to estimate natural coverage."""
    def probe(plan: DocPlan, k: int) -> Set[str]:
        bare = dataclasses.replace(plan, forced_types=[], n_negatives=0)
        seed = run_seed * 31 + plan.idx * 7 + k + 1_000_003
        record = sample_record(random.Random(seed), seed, bare, "seeded", taxonomy_index,
                               clause_bank, public_figures)
        return {pv.type for pv in record.planned}
    return probe


def state_stats(st: DocState) -> dict:
    """Everything the gate report needs from a document's state, as plain JSON.

    Written into every accepted document's metadata and every discard record, so the report can
    be rebuilt from the files alone, mid-run or after.
    """
    plan = st.section_plan
    return {
        "attempts": st.attempt, "repairs": st.repairs_total, "audit_repairs": st.audit_repairs_total,
        "audit_calls": st.audit_calls, "audit_seconds": round(st.audit_seconds, 1),
        "generate_calls": st.generate_calls, "gen_seconds": round(st.gen_seconds, 1),
        "section_calls": st.section_calls,
        "section_attempts": sum(s.attempts for s in plan.sections) if plan else 0,
        "section_repairs": sum(s.repairs_total for s in plan.sections) if plan else 0,
        "redos_after_join": plan.redos_after_join if plan else 0,
        "headings_visible": plan.headings_visible if plan else None,
        "coherence_log": st.coherence_log, "coherence_rejected": st.coherence_rejected,
    }


def discard_record(st: DocState, dataset: str) -> dict:
    """The line `discarded.jsonl` gets for a document that was given up on."""
    return {
        "index": st.plan.idx, "genre": st.plan.genre, "variant": st.plan.variant,
        "form": st.plan.form, "profile": st.plan.profile, "pii_free": st.plan.pii_free,
        "dataset": dataset, "reason": st.result.get("reason"), "gate_log": st.gate_log,
        "sectioned": st.section_plan is not None,
        "section_plan": (sections_mod.summary(st.section_plan, st.record)
                         if st.section_plan is not None and st.record else None),
        "audit_log": st.audit_log, "last_text": st.last_text,
        "planned": [dataclasses.asdict(pv) for pv in st.record.planned] if st.record else None,
        "state_stats": state_stats(st),
    }


def accepted_lines(st: DocState, mode: dataset_mod.DatasetMode, strategy: str) -> Tuple[dict, dict]:
    """Return `(batch line, meta line)` for an accepted document."""
    rec, result = st.record, st.result
    doc_id = f"{mode.id_prefix}-{st.plan.idx:06d}"
    text, output = result["text"], result["output"]
    batch_line = {"id": doc_id, "text_input": text, "output": output}
    meta = {
        "id": doc_id, "dataset": rec.dataset, "genre": rec.genre, "variant": rec.variant,
        "form": rec.form,
        "profile": rec.profile, "pii_free": rec.pii_free,
        "strategy": strategy, "seed": rec.doc_seed, "length": len(text),
        "length_band": list(rec.length_band),
        "planned_types": sorted({pv.type for pv in rec.planned}),
        "planned_items": len(rec.planned) + len(rec.planted_negatives),
        "instances_planned": rec.instances_planned, "instances_realised": rec.instances_realised,
        "id_block": st.plan.id_block, "cast_coherence": rec.coherence,
        "forced_types": st.plan.forced_types, "dropped_forced": rec.dropped_forced,
        "planted_negatives": [
            {"type": neg.type, "text": neg.text, "template": neg.template,
             "why_not": neg.why_not, "also_labelled": neg.also_labelled,
             "surface": neg.found, "in_text": bool(gates.negative_occurrences(text, neg.text))}
            for neg in rec.planted_negatives],
        "tabular": result["tabular"],
        "type_target": st.plan.type_target, "art9_cap": st.plan.art9_cap,
        "realised_types": sorted(output),
        "distinct_spans": sum(len(v) for v in output.values()),
        "parties": [{"role": p.role or ("subject" if p.is_subject else None),
                     "gender": p.person.gender, "age": p.person.age(),
                     "nationality": p.person.nationality} for p in rec.parties],
        "subject": ({"gender": rec.person.gender, "age": rec.person.age(),
                     "nationality": rec.person.nationality} if rec.person else None),
        "sectioned": st.section_plan is not None,
        "section_plan": (sections_mod.summary(st.section_plan, rec)
                         if st.section_plan is not None else None),
        "section_calls": st.section_calls,
        "section_attempts": ([s.attempts for s in st.section_plan.sections]
                             if st.section_plan is not None else None),
        "section_repairs": ([s.repairs_total for s in st.section_plan.sections]
                            if st.section_plan is not None else None),
        "section_redos_after_join": (st.section_plan.redos_after_join
                                     if st.section_plan is not None else None),
        "num_attempts": st.attempt, "num_repairs": st.repairs_total,
        "num_audit_repairs": st.audit_repairs_total,
        "generate_calls": st.generate_calls, "gen_seconds": round(st.gen_seconds, 1),
        "audit_calls": st.audit_calls, "audit_seconds": round(st.audit_seconds, 1),
        "audit_log": st.audit_log,
        "clause_extensions": result.get("clause_extensions", {}),
        "g7_labelled": result["g7_labelled"],
        "gate_log": st.gate_log, "tier_a_findings": result["tier_a_findings"],
        "seeded_clause_literals": _seeded_clause_literals(rec),
        "state_stats": state_stats(st),
    }
    return batch_line, meta


# ---------------------------------------------------------------------------
# Rebuilding a run from its files
# ---------------------------------------------------------------------------

@dataclass
class StoredState:
    """A finished document's state as far as the gate report reads it, rebuilt from its record."""

    plan: DocPlan
    attempt: int
    result: dict
    gate_log: List[dict]
    audit_log: List[dict]
    audit_calls: int
    audit_seconds: float
    audit_repairs_total: int
    section_calls: int
    section_plan: Optional[SimpleNamespace]


def doc_index(doc_id: str) -> int:
    """Return the plan index encoded in a document id such as `SYN-000042`."""
    return int(doc_id.rsplit("-", 1)[1])


def _stored_section_plan(summary: Optional[List[dict]], stats: dict) -> Optional[SimpleNamespace]:
    if summary is None:
        return None
    return SimpleNamespace(
        sections=[SimpleNamespace(
            index=s["index"], kind=s["kind"], heading=s["heading"], role_heading=s["role_heading"],
            load=s["items"] + s["negatives"], attempts=s["attempts"], repairs_total=s["repairs"])
            for s in summary],
        headings_visible=stats.get("headings_visible"), redos_after_join=stats["redos_after_join"])


def _stored_state(plan: DocPlan, record: dict, accepted: bool, reason: Optional[str]) -> StoredState:
    stats = record["state_stats"]
    result = {"accepted": True} if accepted else {"accepted": False, "reason": reason}
    return StoredState(
        plan=plan, attempt=stats["attempts"], result=result, gate_log=record["gate_log"],
        audit_log=record["audit_log"], audit_calls=stats["audit_calls"],
        audit_seconds=stats["audit_seconds"], audit_repairs_total=stats["audit_repairs"],
        section_calls=stats["section_calls"],
        section_plan=_stored_section_plan(record.get("section_plan"), stats))


def stored_accepted(batch_line: dict, meta: dict, plan: DocPlan) -> dict:
    """Rebuild the accepted-document dict the report functions take, from its two lines."""
    subject = meta["subject"]
    record = SimpleNamespace(
        genre=meta["genre"], variant=meta["variant"], form=meta["form"], profile=meta["profile"],
        pii_free=meta["pii_free"], dataset=meta["dataset"], length_band=tuple(meta["length_band"]),
        person=SimpleNamespace(age=lambda age=subject["age"]: age) if subject else None,
        parties=[None] * len(meta["parties"]),
        planned=[None] * (meta["planned_items"] - len(meta["planted_negatives"])),
        planted_negatives=[PlantedNegative(n["type"], n["text"], n["why_not"], n["also_labelled"],
                                           template=n["template"], surface=n.get("surface", ""))
                           for n in meta["planted_negatives"]],
        instances_planned=meta["instances_planned"], instances_realised=meta["instances_realised"],
        dropped_forced=meta["dropped_forced"])
    return {
        "id": batch_line["id"], "record": record, "text": batch_line["text_input"],
        "output": batch_line["output"], "gate_log": meta["gate_log"],
        "tier_a_findings": meta["tier_a_findings"], "g7_labelled": meta["g7_labelled"],
        "clause_extensions": meta["clause_extensions"], "tabular": meta["tabular"],
        "clause_literals": meta["seeded_clause_literals"],
        "state": _stored_state(plan, meta, True, None),
    }


def rebuild_cross_doc_state(
    store: store_mod.ShardStore, below_idx: int, known_clause_texts: List[str], cap: int,
) -> Tuple[List[Set[Tuple[str, ...]]], NegativeLedger]:
    """Rebuild what documents share, from the accepted documents with a plan index below `below_idx`.

    The near-duplicate reference list is each accepted document's 5-grams, in write order -- the
    order a live run appends them, which matters because G6 stops at the first match over the
    threshold and logs that similarity. The reuse ledger is the planted-negative templates of the
    accepted documents; a discarded document gave its claims back when it was given up.

    Args:
        store: A loaded store.
        below_idx: Only documents with a smaller plan index count.
        known_clause_texts: The bank's literal clause texts (G6 exempts them).
        cap: Most plantings of one negative text in the run.

    Returns:
        Tuple of (5-gram sets, ledger).
    """
    ngrams: List[Set[Tuple[str, ...]]] = []
    ledger = NegativeLedger(cap)
    for batch_line, meta in store.accepted:
        if doc_index(meta["id"]) >= below_idx:
            continue
        ngrams.append(gates.word_ngrams(
            batch_line["text_input"], exempt=meta["seeded_clause_literals"] + known_clause_texts))
        for neg in meta["planted_negatives"]:
            ledger.used[neg["template"]] += 1
    return ngrams, ledger


# ---------------------------------------------------------------------------
# Context, plan and manifest
# ---------------------------------------------------------------------------

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

# Arguments that change where or how a run is operated but not which documents it produces.
OPERATIONAL_ARGS = {"out", "resume", "resume_force", "report_only", "status", "stop_file",
                    "yield_when_gpu_busy", "sample_dump_n", "gold_sample_glob", "types_config"}
EPHEMERAL_ARGS = {"resume", "resume_force", "report_only", "status"}


@dataclass
class RunContext:
    """Everything loaded from the arguments and the data files, shared by run, resume and report."""

    mode: dataset_mod.DatasetMode
    run_seed: int
    taxonomy: dict
    taxonomy_index: Dict[str, dict]
    clause_bank: dict
    negative_bank: dict
    partition: dict
    public_figures: Set[str]
    place_names: Set[str]
    agency_names: Set[str]
    genre_list: List[str]
    forced_types: List[str]
    schedulable: List[str]
    types_config_path: str
    used_fallback_taxonomy: bool
    used_fallback_clause_bank: bool


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
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
    parser.add_argument("--batch-size", type=int, default=4, help="prompts per backend generate() call")
    parser.add_argument("--max-repairs", type=int, default=1,
                        help="targeted repair passes per attempt when G2 finds 1-2 missing values")
    parser.add_argument("--rare-force-share", type=float, default=0.5,
                        help="share of documents that get one scheduled rare type (Section 5), "
                             "used only when --coverage-target is 0")
    parser.add_argument("--coverage-target", type=int, default=3, metavar="K",
                        help="schedule every schedulable type into at least K documents; 0 disables "
                             "coverage scheduling and falls back to rare-type forcing")
    parser.add_argument("--coverage-margin", type=int, default=1, metavar="M",
                        help="aim each type at K+M documents, because a forced slot is lost to a "
                             "discard or a sampler drop about a fifth of the time; forced capacity "
                             "is finite, and in a 50-document batch M=2 already leaves 15 types short")
    parser.add_argument("--dataset", choices=sorted(dataset_mod.MODES), default="train",
                        help="train: the large, easier set. benchmark: held out, hard, with hard "
                             "negatives planted; draws only from the benchmark share of the clause "
                             "bank and name pools (see tools/gendoc_dataset.py)")
    parser.add_argument("--partition", default=dataset_mod.PARTITION_PATH,
                        help="benchmark/training partition file")
    parser.add_argument("--sectioning", choices=["auto", "off", "always"], default="auto",
                        help="auto: generate dense and case-file documents, and any plan with more than "
                             f"{sections_mod.SECTION_ITEM_THRESHOLD} planned items, in sections of at most "
                             f"{sections_mod.MAX_ITEMS} items, one model call each; off: whole documents "
                             "only; always: section every document that plans something")
    parser.add_argument("--section-retries", type=int, default=3,
                        help="generations of one section (the first and its regenerations) before the "
                             "document is given a new record")
    parser.add_argument("--negative-cap", type=int, default=dataset_mod.NEGATIVE_CAP_PER_RUN,
                        help="most times one negative text may be planted in the run")
    parser.add_argument("--no-audit", dest="audit", action="store_false",
                        help="skip the G11 content audit (a second model pass per document)")
    parser.add_argument("--max-audit-repairs", type=int, default=1,
                        help="targeted repair passes per attempt when G11 finds unlabelled "
                             "sensitive content")
    parser.add_argument("--gold-sample-glob", nargs="*", default=[],
                         help="gold files to spot-measure the G7 false-positive rate on (read-only)")
    parser.add_argument("--shard-size", type=int, default=250,
                        help="accepted documents per output shard (synthetic_batch_00000.jsonl, ...); "
                             "fixed for the life of a run")
    parser.add_argument("--window", type=int, default=None,
                        help="documents generated together before the next ones start; defaults to "
                             "--batch-size. Cross-document state (G6, the negative ledger) is exact at "
                             "window boundaries, which is what makes a resume reproduce an "
                             "uninterrupted run; a stop finishes the current window, so a smaller "
                             "window yields the GPU sooner and a larger one batches better")
    parser.add_argument("--resume", action="store_true",
                        help="continue the run in --out from its run_manifest.json; refuses when the "
                             "generator source or the data files changed since it started")
    parser.add_argument("--resume-force", action="store_true",
                        help="with --resume, continue although the code or data hashes differ; the "
                             "override is recorded in the manifest history")
    parser.add_argument("--stop-file", default=None,
                        help="a graceful stop is requested when this file exists (default OUT/STOP)")
    parser.add_argument("--yield-when-gpu-busy", type=int, default=None, metavar="MB",
                        help="before each generate() call, stop gracefully if other processes use more "
                             "than MB of GPU memory according to nvidia-smi")
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild gate_report.json and sample_dump.md from the shards in --out "
                             "and exit; safe while a run is writing")
    parser.add_argument("--status", action="store_true",
                        help="print progress, ETA, accepted/discarded by profile and coverage for --out")
    return parser


def merge_with_manifest(parser: argparse.ArgumentParser, cli: argparse.Namespace,
                        manifest: dict) -> Tuple[Optional[argparse.Namespace], List[str]]:
    """Take the run-defining arguments from the manifest, the operational ones from the command line.

    A run-defining flag given on the command line with a value that is neither its default nor the
    manifest's is a conflict: it would describe a different run.

    Returns:
        Tuple of (merged namespace, conflict descriptions); the namespace is None on conflict.
    """
    stored = manifest["args"]
    defaults = vars(parser.parse_args(["--out", cli.out]))
    merged = dict(vars(cli))
    conflicts = []
    for key, value in stored.items():
        if key in OPERATIONAL_ARGS or key not in merged:
            continue
        given = merged[key]
        if given != defaults.get(key) and given != value:
            conflicts.append(f"--{key.replace('_', '-')}: manifest has {value!r}, command line has {given!r}")
        merged[key] = value
    return (None, conflicts) if conflicts else (argparse.Namespace(**merged), [])


def load_context(args: argparse.Namespace) -> Optional[RunContext]:
    """Load the taxonomy, banks and pools a run draws from; None if the genre list is invalid."""
    mode = dataset_mod.MODES[args.dataset]
    taxonomy = data.load_taxonomy(args.taxonomy if os.path.exists(args.taxonomy) else None)
    full_bank = data.load_clause_bank(args.clause_bank if os.path.exists(args.clause_bank) else None)
    partition = dataset_mod.load_partition(args.partition)
    clause_bank = dataset_mod.select_clause_bank(full_bank, partition, args.dataset)
    negative_bank = clause_bank.pop("negatives") if mode.negatives_by_profile else {}
    clause_bank.pop("negatives", None)
    data.use_pools(dataset_mod.select_pools(partition, args.dataset))
    genre_list = [g.strip() for g in args.genres.split(",") if g.strip()]
    unknown = [g for g in genre_list if g not in genres_mod.GENRES]
    if unknown:
        print(f"unknown genres: {unknown}", file=sys.stderr)
        return None
    types_config_path = args.types_config
    if not os.path.exists(types_config_path):
        types_config_path = os.path.join(args.out, "types_config.generated.yaml")
        data.write_types_config_yaml(taxonomy, types_config_path)
    return RunContext(
        mode=mode, run_seed=args.seed + mode.seed_offset, taxonomy=taxonomy,
        taxonomy_index=data.taxonomy_index(taxonomy), clause_bank=clause_bank,
        negative_bank=negative_bank, partition=partition, public_figures=set(data.PUBLIC_FIGURES),
        place_names={p for _c, p in data.POSTAL_PAIRS}, agency_names=set(data.AGENCY_NAMES),
        genre_list=genre_list, forced_types=[t.strip() for t in args.force_types.split(",") if t.strip()],
        schedulable=genres_mod.coverage_types([entry["name"] for entry in taxonomy["types"]]),
        types_config_path=types_config_path,
        used_fallback_taxonomy=not os.path.exists(args.taxonomy),
        used_fallback_clause_bank=not os.path.exists(args.clause_bank))


def make_config(args: argparse.Namespace, ctx: RunContext) -> GenerationConfig:
    """Build the generation configuration a run uses."""
    return GenerationConfig(
        strategy=args.strategy, invalid_checksum_rate=args.invalid_checksum_rate,
        retries=args.retries, near_dup_threshold=args.near_dup_threshold,
        g7_policy=args.g7_policy, batch_size=args.batch_size, max_repairs=args.max_repairs,
        audit=args.audit, max_audit_repairs=args.max_audit_repairs,
        dataset=args.dataset, difficulty_weights=ctx.mode.difficulty_weights,
        negative_bank=ctx.negative_bank, negative_cap=args.negative_cap, sectioning=args.sectioning,
        section_retries=args.section_retries,
        known_clause_texts=known_clause_texts_of(ctx.clause_bank))


def derive_plans(args: argparse.Namespace, ctx: RunContext) -> Tuple[List[DocPlan], dict]:
    """Derive the whole run's plan from the seed. Pure: the same arguments give the same plan."""
    return plan_batch(
        random.Random(ctx.run_seed), args.n, ctx.genre_list, ctx.forced_types, args.rare_force_share,
        coverage_target=args.coverage_target, schedulable_types=ctx.schedulable,
        mode=ctx.mode, clause_bank=ctx.clause_bank, coverage_margin=args.coverage_margin,
        natural_probe=_make_natural_probe(ctx.run_seed, ctx.taxonomy_index, ctx.clause_bank,
                                          ctx.public_figures))


def plans_as_json(plans: List[DocPlan]) -> List[dict]:
    """Return the plans as JSON-normalised dicts, the form they are stored and compared in."""
    return json.loads(json.dumps([dataclasses.asdict(p) for p in plans]))


def plans_from_json(rows: List[dict]) -> List[DocPlan]:
    return [DocPlan(**{**row, "length_band": tuple(row["length_band"])}) for row in rows]


def plan_digest(plan_rows: List[dict]) -> str:
    return hashlib.sha256(json.dumps(plan_rows, sort_keys=True).encode()).hexdigest()


def data_file_hashes(args: argparse.Namespace) -> Dict[str, Optional[str]]:
    """Hash the data files whose contents decide what is generated."""
    return {"taxonomy": store_mod.sha256_file(args.taxonomy),
            "clause_bank": store_mod.sha256_file(args.clause_bank),
            "benchmark_partition": store_mod.sha256_file(args.partition)}


def plan_summary(plan_rows: List[dict], plan_report: dict, window: int) -> dict:
    """The planned schedule in brief, for the manifest; the full plan is in `plan.json`."""
    keys = ("planned_profiles", "planned_pii_free", "planned_negatives", "planned_nn_share",
            "planned_type_target", "planned_id_block_address", "dataset")
    return {"documents": len(plan_rows), "window": window,
            "windows": -(-len(plan_rows) // window), "plan_sha256": plan_digest(plan_rows),
            "genres": dict(collections.Counter(p["genre"] for p in plan_rows)),
            **{k: plan_report.get(k) for k in keys}}


def fresh_progress(n: int) -> dict:
    return {"status": "not started", "done": 0, "accepted": 0, "discarded": 0, "remaining": n,
            "last_update": store_mod.now_iso(), "wall_seconds_total": 0.0, "run_stats": {},
            "run_stats_through_idx": 0, "stop_reason": None, "pid": None}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def shard_g1(store: store_mod.ShardStore, shard: int, types_config_path: str) -> dict:
    """Validate one closed shard (its labelled file and its whole batch) and cache the verdict."""
    cache_path = os.path.join(store.out_dir, store_mod.G1_NAME)
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    digest = store_mod.sha256_file(store.path(shard))
    entry = cache.get(str(shard))
    if entry and entry.get("sha256") == digest:
        return entry
    ok, output = run_g1_validate_labels(store.path(shard, "labelled"), types_config_path)
    full_ok, full_output = run_g1_validate_labels(store.path(shard), types_config_path)
    entry = {"sha256": digest, "checked": store_mod.now_iso(), "passed": ok, "output": output,
             "full_batch_passed": full_ok, "full_batch_output": full_output}
    cache[str(shard)] = entry
    store_mod.atomic_write_json(cache_path, cache)
    return entry


def g1_over_all_shards(store: store_mod.ShardStore, types_config_path: str) -> dict:
    """Run G1 over every committed document of every shard, and per closed shard."""
    tag = os.getpid()
    batch_path = os.path.join(store.out_dir, f".g1_all_batch.{tag}.jsonl")
    labelled_path = os.path.join(store.out_dir, f".g1_all_labelled.{tag}.jsonl")
    try:
        with open(batch_path, "w", encoding="utf-8") as batch_f, \
                open(labelled_path, "w", encoding="utf-8") as lab_f:
            for line, _meta in store.accepted:
                text = json.dumps(line, ensure_ascii=False) + "\n"
                batch_f.write(text)
                if line["output"]:
                    lab_f.write(text)
        ok, output = run_g1_validate_labels(labelled_path, types_config_path)
        full_ok, full_output = run_g1_validate_labels(batch_path, types_config_path)
    finally:
        for path in (batch_path, labelled_path):
            if os.path.exists(path):
                os.remove(path)
    per_shard = {str(s): shard_g1(store, s, types_config_path) for s in store.closed_shards()}
    pattern = os.path.join(store.out_dir, f"{store.stem}_batch_*_labelled.jsonl")
    return {
        "G1_validate_labels": {
            "passed": ok and all(e["passed"] for e in per_shard.values()), "path": pattern,
            "output": output, "per_shard": {s: e["passed"] for s, e in per_shard.items()}},
        "G1_validate_labels_full_batch": {
            "passed": full_ok, "path": pattern.replace("_labelled", ""),
            "note": "exits 1 when the batch contains PII-free documents; validate_labels.py "
                    "treats any empty output as an unfinished annotation. Semantics unchanged.",
            "output": full_output},
    }


def build_report(args: argparse.Namespace, ctx: RunContext, plans: List[DocPlan], plan_report: dict,
                 store: store_mod.ShardStore, manifest: dict) -> Tuple[dict, List[dict]]:
    """Build the gate report from what is on disk.

    The same function produces the report at the end of a run, when a run stops, and for
    `--report-only`, and it reads nothing but the shards, `plan.json` and the manifest's progress,
    so the three cannot differ.

    Returns:
        Tuple of (the report, the accepted-document dicts in plan order).
    """
    by_idx = {p.idx: p for p in plans}
    accepted = sorted((stored_accepted(line, meta, by_idx[doc_index(meta["id"])])
                       for line, meta in store.accepted), key=lambda r: doc_index(r["id"]))
    discarded_records = sorted(store.discarded, key=lambda d: d["index"])
    states = sorted(
        [r["state"] for r in accepted]
        + [_stored_state(by_idx[d["index"]], d, False, d.get("reason")) for d in discarded_records],
        key=lambda st: st.plan.idx)
    progress = manifest["progress"]
    wall_seconds = progress["wall_seconds_total"]
    n_done = len(accepted) + len(discarded_records)
    stats_all = [m["state_stats"] for _l, m in store.accepted] + [d["state_stats"] for d in discarded_records]
    coherence_log = [entry for s in stats_all for entry in s["coherence_log"]]
    coherence_rejected = sum(s["coherence_rejected"] for s in stats_all)

    g1 = g1_over_all_shards(store, ctx.types_config_path)
    accepted_meta_for_g5 = [
        {"genre": r["record"].genre, "form": r["record"].form, "length": len(r["text"]),
         "band": r["record"].length_band, "types": list(r["output"])}
        for r in accepted]
    g5_report = gate_g5_distribution(accepted_meta_for_g5, ctx.genre_list)
    g6_report = gate_g6_aggregate([r["text"] for r in accepted])
    g7_fp_report = (measure_g7_false_positive_rate(args.gold_sample_glob, ctx.place_names, ctx.agency_names)
                    if args.gold_sample_glob else None)
    g7_mock_findings = sum(
        1 for r in accepted for entry in r["gate_log"] if entry.get("stage") == "accepted"
        for f in entry.get("g7_findings", []) if f.get("action") == "reject")
    total_spans = sum(len(v) for r in accepted for v in r["output"].values())
    labelled_spans = sum(len(r["g7_labelled"]) for r in accepted)
    types_per_doc = [len(r["output"]) for r in accepted]
    ledger = NegativeLedger(args.negative_cap)
    for r in accepted:
        for neg in r["record"].planted_negatives:
            ledger.used[neg.template] += 1
    window = args.window or args.batch_size
    report = {
        "requested": args.n, "done": n_done, "remaining": args.n - n_done,
        "complete": n_done == args.n, "accepted": len(accepted), "discarded": len(discarded_records),
        "backend": args.backend, "model": args.model, "strategy": args.strategy,
        "batch_size": args.batch_size, "window": window, "shard_size": args.shard_size,
        "shards": len(store.shard_numbers()), "audit_enabled": args.audit,
        "wall_seconds": round(wall_seconds, 1),
        "wall_seconds_per_requested_doc": round(wall_seconds / max(1, args.n), 1),
        "wall_seconds_per_accepted_doc": round(wall_seconds / len(accepted), 1) if accepted else None,
        "attempts_total": sum(st.attempt for st in states),
        "run_stats": progress["run_stats"], "run_stats_through_idx": progress["run_stats_through_idx"],
        "types_per_accepted_doc": {"min": min(types_per_doc, default=None),
                                   "max": max(types_per_doc, default=None),
                                   "mean": round(sum(types_per_doc) / len(types_per_doc), 2)
                                   if types_per_doc else None},
        "g7_labelled_spans": {"count": labelled_spans, "total_spans": total_spans,
                              "share": round(labelled_spans / total_spans, 4) if total_spans else 0.0},
        "repetition_share": {
            "max": max((gates.repetition_share(r["text"], exempt=r["clause_literals"])
                        for r in accepted), default=None),
            "threshold": GenerationConfig.repetition_threshold,
        },
        "clause_extension_fired": sum(len(r["clause_extensions"]) for r in accepted),
        "clause_extension_docs": sum(1 for r in accepted if r["clause_extensions"]),
        "failure_stages": dict(collections.Counter(
            e["stage"] for st in states for e in st.gate_log if not e.get("ok"))),
        "discard_reasons": dict(collections.Counter(
            d.get("reason") or "unknown" for d in discarded_records)),
        "used_fallback_taxonomy": ctx.used_fallback_taxonomy,
        "used_fallback_clause_bank": ctx.used_fallback_clause_bank,
        "types_config_used": ctx.types_config_path,
        **g1,
        "G5_distribution": g5_report,
        "G6_diversity": g6_report,
        "G7_unplanned_pii_on_accepted": {"policy": args.g7_policy, "residual_findings": g7_mock_findings},
        "G7_false_positive_measurement_on_gold": g7_fp_report,
        "G11_content_audit": audit_report(states, accepted, wall_seconds),
        "coverage": coverage_report(accepted_meta_for_g5, ctx.schedulable, args.coverage_target, plan_report),
        "density": density_report(accepted, plans),
        "sectioning": sectioning_report(accepted, states, plans),
        "dataset": args.dataset,
        "partition": {"path": args.partition, "counts": ctx.partition.get("counts")},
        "hard_negatives": {**negatives_report(accepted, states, plans), "run_ledger": ledger.report()},
        "tabular": tabular_report(accepted),
        "multi_instance": multi_instance_report(accepted, plans, sorted(
            t for t, entry in ctx.taxonomy_index.items() if entry.get("value_kind") == "clause")),
        "cast_coherence": coherence.summarise(coherence_log, coherence_rejected),
        "identification_block": identification_report(accepted),
        "forced_types_dropped_by_sampler": dict(collections.Counter(
            t for r in accepted for t in r["record"].dropped_forced)),
    }
    return report, accepted


def write_report(args: argparse.Namespace, ctx: RunContext, plans: List[DocPlan], plan_report: dict,
                 store: store_mod.ShardStore, manifest: dict) -> Tuple[dict, str]:
    """Build the report and write `gate_report.json` and `sample_dump.md`; return the report and its path."""
    report, accepted = build_report(args, ctx, plans, plan_report, store, manifest)
    report_path = os.path.join(args.out, "gate_report.json")
    store_mod.atomic_write_json(report_path, report)
    if accepted:
        write_sample_dump(os.path.join(args.out, "sample_dump.md"), accepted, args.sample_dump_n,
                          random.Random(ctx.run_seed ^ 0xD0C5))
    return report, report_path


def print_report(report: dict, report_path: str, store: store_mod.ShardStore) -> None:
    printable = {k: v for k, v in report.items()
                 if k not in ("G1_validate_labels", "G1_validate_labels_full_batch")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    print("\nG1 validate_labels.py output (labelled subset, all shards):\n"
          + report["G1_validate_labels"]["output"])
    print(f"\n{report['accepted']}/{report['requested']} accepted, {report['discarded']} discarded, "
          f"in {report['shards']} shard(s) under {store.out_dir}")
    print(f"Gate report: {report_path}")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    return (f"{days}d " if days else "") + f"{hours}h {rest // 60:02d}m"


def print_status(out_dir: str) -> int:
    """Print where a run in `out_dir` stands, from its files, without modifying anything."""
    manifest_path = os.path.join(out_dir, store_mod.MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        print(f"no {store_mod.MANIFEST_NAME} in {out_dir}: nothing has been started here", file=sys.stderr)
        return 2
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    args = manifest["args"]
    mode = dataset_mod.MODES[args["dataset"]]
    store = store_mod.ShardStore(out_dir, mode.file_stem, args["shard_size"]).load(repair=False)
    n = args["n"]
    progress = manifest["progress"]
    accepted, discarded = store.n_accepted, len(store.discarded)
    done = accepted + discarded
    stats = [m["state_stats"] for _l, m in store.accepted] + [d["state_stats"] for d in store.discarded]
    seconds = sum(s["gen_seconds"] + s["audit_seconds"] for s in stats)
    per_doc = seconds / done if done else None
    state = progress["status"]
    pid = progress.get("pid")
    if state == "running" and pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            state = "interrupted (the process is gone without a clean stop; resume is safe)"
        except PermissionError:
            pass
    print(f"run        {out_dir}  dataset={args['dataset']} backend={args['backend']} model={args['model']}"
          f" seed={args['seed']}")
    print(f"state      {state}" + (f"  (stopped: {progress['stop_reason']})" if progress.get("stop_reason") else ""))
    print(f"progress   {done}/{n} done ({accepted} accepted, {discarded} discarded), {n - done} remaining;"
          f" {len(store.shard_numbers())} shard(s) of {args['shard_size']}")
    print(f"last update {progress['last_update']}   wall time generating {_duration(progress['wall_seconds_total'])}")
    if per_doc and seconds >= 1:
        print(f"speed      {per_doc:.1f} s per finished document (model time, gaps excluded);"
              f" ETA {_duration((n - done) * per_doc)} of GPU time for the remaining {n - done}")
    else:
        print("speed      nothing measurable yet, no ETA")
    profiles = collections.defaultdict(lambda: [0, 0])
    for _l, m in store.accepted:
        profiles[m["profile"]][0] += 1
    for d in store.discarded:
        profiles[d["profile"]][1] += 1
    print("by profile (accepted / discarded):")
    for name in genres_mod.PROFILE_ORDER:
        if name in profiles:
            print(f"  {name:<12} {profiles[name][0]:>5} / {profiles[name][1]}")
    reasons = collections.Counter(d.get("reason") or "unknown" for d in store.discarded)
    if reasons:
        print("discard reasons: " + ", ".join(f"{k}={v}" for k, v in reasons.most_common()))
    taxonomy = data.load_taxonomy(args["taxonomy"] if os.path.exists(args["taxonomy"]) else None)
    schedulable = genres_mod.coverage_types([e["name"] for e in taxonomy["types"]])
    counts: collections.Counter = collections.Counter()
    for _l, m in store.accepted:
        counts.update(set(m["realised_types"]))
    target = args["coverage_target"]
    absent = sorted(t for t in schedulable if not counts.get(t))
    below = sorted(t for t in schedulable if 0 < counts.get(t, 0) < target)
    print(f"coverage   {len(schedulable) - len(absent)}/{len(schedulable)} schedulable types seen;"
          f" target {target} documents per type: {len(schedulable) - len(absent) - len(below)} reached,"
          f" {len(below)} below, {len(absent)} absent")
    if absent:
        print("  absent: " + ", ".join(absent))
    if below:
        print("  below target: " + ", ".join(f"{t}({counts[t]})" for t in below))
    for note in store.repairs:
        print(f"note       a writer is mid-append or a kill left: {note} (ignored; a resume repairs it)")
    return 0


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def new_manifest(args: argparse.Namespace, ctx: RunContext, plan_rows: List[dict], plan_report: dict,
                 window: int) -> dict:
    code = store_mod.code_hashes(TOOLS_DIR)
    return {
        "format": store_mod.MANIFEST_FORMAT, "created": store_mod.now_iso(),
        "args": {k: v for k, v in vars(args).items() if k not in EPHEMERAL_ARGS}, "model": args.model, "dataset": args.dataset, "seed": args.seed,
        "run_seed": ctx.run_seed, "n": args.n,
        "git_commit": store_mod.git_commit(TOOLS_DIR),
        "source_hashes": code, "source_sha256": store_mod.combined_hash(code),
        "data_hashes": data_file_hashes(args),
        "plan_summary": plan_summary(plan_rows, plan_report, window),
        "history": [{"event": "start", "time": store_mod.now_iso(), "argv": sys.argv,
                     "git_commit": store_mod.git_commit(TOOLS_DIR)}],
        "progress": fresh_progress(args.n),
    }


def check_resumable(manifest: dict, args: argparse.Namespace, force: bool) -> Tuple[bool, dict, str]:
    """Compare the manifest's code and data hashes with the files now on disk.

    Returns:
        Tuple of (may continue, changed files as `{name: {was, now}}`, a refusal message).
    """
    changed = {
        **{f"source:{k}": v for k, v in store_mod.changed_hashes(
            manifest["source_hashes"], store_mod.code_hashes(TOOLS_DIR)).items()},
        **{f"data:{k}": v for k, v in store_mod.changed_hashes(
            manifest["data_hashes"], data_file_hashes(args)).items()}}
    if not changed:
        return True, {}, ""
    listing = "\n".join(f"  {name}: {(v['was'] or 'missing')[:12]} -> {(v['now'] or 'missing')[:12]}"
                        for name, v in changed.items())
    if force:
        return True, changed, ""
    return False, changed, (
        "refusing to resume: the generator or its data changed since this run started:\n" + listing +
        "\nA changed generator mid-run mixes two data distributions in one dataset. If that is what "
        "you want, repeat the command with --resume-force; the override is recorded in the "
        f"history of {store_mod.MANIFEST_NAME}.")


def save_progress(manifest: dict, manifest_path: str, store: store_mod.ShardStore, n: int,
                  status: str, reason: Optional[str] = None) -> None:
    done = store.n_accepted + len(store.discarded)
    manifest["progress"].update({
        "status": status, "done": done, "accepted": store.n_accepted, "discarded": len(store.discarded),
        "remaining": n - done, "last_update": store_mod.now_iso(), "stop_reason": reason,
        "pid": os.getpid() if status == "running" else None})
    store_mod.atomic_write_json(manifest_path, manifest)


def run_windows(args: argparse.Namespace, ctx: RunContext, plans: List[DocPlan],
                store: store_mod.ShardStore, manifest: dict, manifest_path: str,
                controller: store_mod.StopController) -> Tuple[bool, Optional[object]]:
    """Generate the plans window by window, writing each document as it finishes.

    A window is `--window` consecutive plan indices generated together. Cross-document state is
    exact at window boundaries, so a window interrupted by a kill is generated again from its
    start with the state of the windows before it; documents of it already on disk are not
    written twice, and the ones still missing come out as an uninterrupted run would have
    produced them.

    Returns:
        Tuple of (whether every document is done, the backend if one was loaded).
    """
    n = args.n
    window = args.window or args.batch_size
    config = make_config(args, ctx)
    done = {doc_index(m["id"]) for _l, m in store.accepted} | {d["index"] for d in store.discarded}
    spans = [(s, min(s + window, n)) for s in range(0, n, window)]
    first = next((i for i, (a, b) in enumerate(spans) if any(k not in done for k in range(a, b))), len(spans))
    if first < len(spans) and any(k >= spans[first][1] for k in done):
        raise store_mod.StoreError("documents exist beyond the first incomplete window; the files do "
                                   "not belong to this plan")
    below = spans[first][0] if first < len(spans) else n
    ngrams, config.negative_ledger = rebuild_cross_doc_state(
        store, below, config.known_clause_texts, args.negative_cap)
    stats = collections.Counter(manifest["progress"]["run_stats"])
    backend = None
    session_started = time.time()
    wall_base = manifest["progress"]["wall_seconds_total"]

    def on_finished(st: DocState) -> None:
        idx = st.plan.idx
        if idx in done:
            return
        if st.result.get("accepted"):
            batch_line, meta = accepted_lines(st, ctx.mode, args.strategy)
            closed = store.append_accepted(batch_line, meta)
            outcome = "accepted"
        else:
            store.append_discarded(discard_record(st, args.dataset))
            closed, outcome = None, "DISCARDED"
        done.add(idx)
        _log(f"[{len(done)}/{n}] {ctx.mode.id_prefix}#{idx} {st.plan.genre}/{st.plan.form}/"
             f"{st.plan.profile} {outcome} after {st.attempt} attempt(s), {st.repairs_total} repair(s), "
             f"{st.audit_repairs_total} audit repair(s), {wall_base + time.time() - session_started:.0f}s")
        if closed is not None:
            verdict = shard_g1(store, closed, ctx.types_config_path)
            _log(f"shard {closed:05d} closed ({args.shard_size} documents): G1 validate_labels "
                 f"{'passed' if verdict['passed'] else 'FAILED, see ' + store_mod.G1_NAME}")

    for position in range(first, len(spans)):
        if controller.poll():
            break
        start, end = spans[position]
        if backend is None:
            loading = time.time()
            backend = build_backend(args.backend, args.model)
            controller.own_gpu_mb = backend.gpu_memory_mb
            manifest["progress"]["model_load_seconds"] = round(time.time() - loading, 1)
        replay = any(k in done for k in range(start, end))
        _, window_stats = run_generation(
            plans[start:end], ctx.run_seed, ctx.taxonomy_index, ctx.clause_bank, ctx.public_figures,
            ctx.place_names, ctx.agency_names, backend, config, progress=on_finished,
            accepted_ngrams=ngrams, before_generate=lambda _kind, _jobs: controller.poll())
        if replay:
            ngrams, config.negative_ledger = rebuild_cross_doc_state(
                store, end, config.known_clause_texts, args.negative_cap)
        stats.update(window_stats)
        manifest["progress"]["run_stats"] = dict(stats)
        manifest["progress"]["run_stats_through_idx"] = end
        manifest["progress"]["wall_seconds_total"] = round(
            wall_base + time.time() - session_started, 1)
        save_progress(manifest, manifest_path, store, n, "running")
    return len(done) == n, backend


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    cli = parser.parse_args()
    if cli.status:
        return print_status(cli.out)
    out = cli.out
    manifest_path = os.path.join(out, store_mod.MANIFEST_NAME)
    plan_path = os.path.join(out, store_mod.PLAN_NAME)
    resuming = cli.resume or cli.report_only
    if resuming:
        if not os.path.exists(manifest_path):
            return _refuse(f"nothing to {'resume' if cli.resume else 'report on'}: no "
                           f"{store_mod.MANIFEST_NAME} in {out}")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        args, conflicts = merge_with_manifest(parser, cli, manifest)
        if args is None:
            return _refuse("these flags describe a different run than the one in " + out + ":\n  "
                           + "\n  ".join(conflicts))
    else:
        args = cli
        stem = dataset_mod.MODES[args.dataset].file_stem
        if os.path.exists(manifest_path) or store_mod.ShardStore(out, stem, args.shard_size).has_output():
            return _refuse(f"{out} already holds a run; continue it with --resume or choose a new --out "
                           f"(an existing run is never overwritten)")
    os.makedirs(out, exist_ok=True)
    args.stop_file = args.stop_file or os.path.join(out, "STOP")
    if args.window is not None and args.window < 1 or args.shard_size < 1:
        return _refuse("--window and --shard-size must be at least 1")
    window = args.window = args.window or args.batch_size
    ctx = load_context(args)
    if ctx is None:
        return 2
    store = store_mod.ShardStore(out, ctx.mode.file_stem, args.shard_size)

    if cli.report_only:
        store.load(repair=False)
        stored = json.load(open(plan_path, encoding="utf-8"))
        report, report_path = write_report(args, ctx, plans_from_json(stored["plans"]),
                                           stored["plan_report"], store, manifest)
        print_report(report, report_path, store)
        return 0 if report["G1_validate_labels"]["passed"] else 1

    if cli.resume:
        try:
            store.load(repair=True)
        except store_mod.StoreError as err:
            return _refuse(f"cannot resume: {err}")
        for note in store.repairs:
            _log(f"repaired on load: {note}")
        ok, changed, message = check_resumable(manifest, args, cli.resume_force)
        if not ok:
            return _refuse(message)
        stored = json.load(open(plan_path, encoding="utf-8"))
        plans, plan_report = derive_plans(args, ctx)
        rows = plans_as_json(plans)
        plan_differs = rows != stored["plans"]
        if plan_differs and not changed:
            return _refuse("refusing to resume: the plan derived from the seed differs from plan.json "
                           "although no source or data file changed; the generator is not deterministic here")
        plan_rows, plan_report = (stored["plans"], stored["plan_report"]) if plan_differs else (rows, plan_report)
        history = {"event": "resume-force" if changed else "resume", "time": store_mod.now_iso(),
                   "argv": sys.argv, "git_commit": store_mod.git_commit(TOOLS_DIR),
                   "documents_done": store.n_accepted + len(store.discarded)}
        if changed:
            history.update({"overridden": changed, "plan_rederived_differs": plan_differs,
                            "plan_used": "stored plan.json" if plan_differs else "re-derived (identical)"})
            code = store_mod.code_hashes(TOOLS_DIR)
            manifest.update({"source_hashes": code, "source_sha256": store_mod.combined_hash(code),
                             "data_hashes": data_file_hashes(args), "git_commit": history["git_commit"]})
            _log("--resume-force: continuing with changed code or data; recorded in " + store_mod.MANIFEST_NAME)
        manifest["history"].append(history)
        plans = plans_from_json(plan_rows)
    else:
        plans, plan_report = derive_plans(args, ctx)
        plan_rows = plans_as_json(plans)
        store_mod.atomic_write_json(plan_path, {"plan_report": plan_report, "plans": plan_rows})
        manifest = new_manifest(args, ctx, plan_rows, plan_report, window)
        store_mod.atomic_write_json(manifest_path, manifest)
        store_mod.touch(store.discarded_path)
    stored = json.load(open(plan_path, encoding="utf-8"))
    plan_report = stored["plan_report"]

    controller = store_mod.StopController(args.stop_file, args.yield_when_gpu_busy, _log)
    controller.install_signal_handlers()
    save_progress(manifest, manifest_path, store, args.n, "running")
    backend = None
    try:
        complete, backend = run_windows(args, ctx, plans, store, manifest, manifest_path, controller)
    except BaseException as err:
        save_progress(manifest, manifest_path, store, args.n, "crashed", f"{type(err).__name__}: {err}")
        raise
    if backend is not None:
        backend.close()
    done = store.n_accepted + len(store.discarded)
    if complete:
        save_progress(manifest, manifest_path, store, args.n, "finished")
    else:
        save_progress(manifest, manifest_path, store, args.n, "stopped", controller.reason)
    report, report_path = write_report(args, ctx, plans, plan_report, store, manifest)
    print_report(report, report_path, store)
    if complete:
        return 0 if report["G1_validate_labels"]["passed"] else 1
    print(f"\nStopped cleanly ({controller.reason}): {done}/{args.n} documents are on disk "
          f"({store.n_accepted} accepted, {len(store.discarded)} discarded), {args.n - done} remaining.\n"
          f"Continue with: python3 tools/generate_documents.py --resume --out {out}"
          + (f"   (remove {args.stop_file} first)" if os.path.exists(args.stop_file) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
