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

Pipeline per document:

    plan_batch -> sample_record -> build_prompt -> backend.generate (batched)
        -> marker check, truncation, G0 placeholders, length
        -> G2 verbatim (1-2 missing values: targeted repair of the draft)
        -> G9 slot labels, G3 names, G4 checksums, G6 near-duplicate,
           seeded-clause boundary extension, G7 (unplanned names and dates
           labelled, other unplanned PII rejected)
        -> G11 content audit (a second, temperature-0 pass of the same model:
           any unlabelled sensitive statement or any sentence framing origin,
           belief or sexuality as relevant to suspicion triggers one targeted
           repair, then a regeneration)
        -> accept, or retry with a new record

then, over the whole accepted batch: G1 (schema validation via
`tools/validate_labels.py`), G5 (genre/form/length/type distribution vs the
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
its profile can absorb. `CONTEXT_SENSITIVE` and `IDENTIFIABLE_IMAGE` are
deliberately left uncovered and reported as such; see
`gendoc_genres.UNCOVERED_TYPES`.

Usage:
    python3 tools/generate_documents.py --backend hf --model Qwen/Qwen3.5-9B \\
        --n 50 --strategy seeded --seed 1 --batch-size 4 --coverage-target 3 \\
        --out data/synthetic/pilot_v3/
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_audit as audit
import gendoc_data as data
import gendoc_gates as gates
import gendoc_genres as genres_mod
import gendoc_identifiers as ident
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


@dataclass
class Record:
    """A fully sampled, typed record for one document.

    `person` is the single data subject the document is about and is None only
    for a PII-free plan. `parties` is everyone the document names, the subject
    included: a case file's spouse, children, caseworker and doctor each carry
    their own coherent identifiers, which is where a dense document's many
    distinct spans come from.
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
            from that nationality's pool in `gendoc_data.FOREIGN_NAMES`.
        gender: Force "M" or "F"; None picks at random.
        age: Force an exact age, bypassing the profile.
        age_clamp: (min, max) the drawn age is clamped into, for a genre that
            cannot name anyone outside it.

    Returns:
        A `Person`. Callers must still run G3 before shipping any document.
    """
    gender = gender or rng.choice(["M", "F"])
    if nationality in data.FOREIGN_NAMES:
        males, females, surnames = data.FOREIGN_NAMES[nationality]
        first = rng.choice(males if gender == "M" else females)
        last = rng.choice(surnames)
    else:
        first = rng.choice(data.FIRST_NAMES_MALE if gender == "M" else data.FIRST_NAMES_FEMALE)
        last = rng.choice(data.SURNAMES)
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
    street = rng.choice(data.STREET_NAMES)
    number = rng.randint(1, 180)
    suffix = rng.choice(["", "", "", "A", "B", "C"])
    postal, place = rng.choice(data.POSTAL_PAIRS)
    return f"{street} {number}{suffix}, {postal} {place}", postal, place


def _ascii(name: str) -> str:
    """Fold a name to ASCII for email/username local parts (`Wiśniewski` -> `wisniewski`)."""
    folded = unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in folded if not unicodedata.combining(c))


def _employer(rng: random.Random, place: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Sample an employer name and the (nb, nn) roles that fit its sector.

    The pilot named every organisation after the subject's own surname, which
    turned a dismissal letter into a family-business dispute. Employers here
    are named after a place (often the subject's own town) or a neutral
    prefix, and the sector drives which roles EMPLOYMENT can take.
    """
    sector_words, roles = rng.choice(data.ROLE_SECTORS)
    prefix = place if rng.random() < 0.4 else rng.choice(data.ORG_NAME_PREFIXES)
    suffix = rng.choice(["AS", "AS", "AS", "ASA", "Gruppen AS"])
    return f"{prefix} {rng.choice(sector_words)} {suffix}", roles


# Types that are generated as a literal value rather than drawn from the clause
# bank. `IDENTIFIABLE_IMAGE` and `CONTEXT_SENSITIVE` are deliberately absent:
# see `gendoc_genres.UNCOVERED_TYPES`.
_VALUE_KIND_TYPES = {
    "NATIONAL_ID", "DATE_OF_BIRTH", "ORG_NUMBER", "BANK_ACCOUNT", "IBAN",
    "CREDIT_CARD", "PHONE", "FAX_NUMBER", "EMAIL", "URL", "IP_ADDRESS",
    "USERNAME", "SOCIAL_MEDIA", "CASE_NUMBER", "PASSPORT", "DRIVER_LICENSE",
    "IDENTITY_CARD", "VISA_NUMBER", "MILITARY_ID", "MEDICAL_LICENSE",
    "INSURANCE_NUMBER", "TAX_ID", "STUDENT_ID", "DEVICE_ID", "CRYPTO",
    "PASSWORD", "LICENSE_PLATE", "POSTAL_CODE", "ADDRESS", "AGE", "GENDER",
    "MARITAL_STATUS", "NATIONALITY", "LOCATION", "ORGANIZATION", "DATE_TIME",
    "ANIMAL_INFO",
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
    if etype == "POSTAL_CODE":
        postal, _place = rng.choice(data.POSTAL_PAIRS)
        return postal, None
    if etype == "ADDRESS":
        full, _postal, _place = _address(rng)
        return full, None
    if etype == "AGE":
        return str(person.age()), None
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

    @property
    def foreign(self) -> bool:
        return self.person.nationality != "norsk"


_YEAR_IN_TEXT_RE = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")


def _clause_fits(entry: dict, subject: _Subject) -> bool:
    """Whether a clause-bank entry is coherent with the record's subject.

    The clause bank annotates each entry with the five original pilot genre
    ids; a genre declares in `gendoc_genres.GENRES[...]["clause_genres"]` which
    of those its own clauses may come from, so 30-odd genres share one bank.

    Args:
        entry: A clause-bank entry (see `schema_note` in clause_bank.json).
        subject: The subject state so far.

    Returns:
        True if the entry's genre, form, gender, age, origin, status and partner
        constraints all hold, and any year it mentions falls after the
        subject's 15th birthday.
    """
    if not subject.clause_genres.intersection(entry.get("genres", [])):
        return False
    if entry.get("form") != subject.form:
        return False
    if entry.get("subject", "person") != "person":
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
    elif role in {"parent", "guardian"}:
        age = subject_age + rng.randint(22, 42)
        gender = None
    elif role in {"physician", "psychologist", "veterinarian", "lawyer", "caseworker",
                  "officer", "teacher", "employer_contact", "creditor_contact"}:
        age = genres_mod.sample_age(rng, "working")
        gender = None
    else:
        age = genres_mod.sample_age(rng, age_profile)
        gender = None
    return _resample_until_no_collision(
        rng, public_figures, nationality=nationality, gender=gender, age=age,
    )


_STAFF_ROLES = {"physician", "psychologist", "veterinarian", "caseworker", "lawyer",
                "officer", "teacher", "employer_contact", "creditor_contact"}


def sample_record(
    rng: random.Random, doc_seed: int, plan: "DocPlan", strategy: str,
    taxonomy_index: Dict[str, dict], clause_bank: dict, public_figures: Set[str],
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

    Returns:
        A `Record` with `planned` fully populated (empty for a PII-free plan).
    """
    genre, form, length_band = plan.genre, plan.form, plan.length_band
    spec = genres_mod.GENRES[genre]
    label = lambda t: genres_mod.field_label(t, form)  # noqa: E731

    if plan.pii_free:
        return Record(doc_seed, genre, plan.variant, form, length_band, None, [], [],
                      profile=plan.profile, pii_free=True)

    foreign = rng.random() < spec.get("foreign_subject_p", 0.0)
    minor = rng.random() < spec.get("minor_subject_p", 0.0)
    nationality = rng.choice(data.FOREIGN_NATIONALITIES) if foreign else "norsk"
    age_profile = spec.get("age_profile", "adult")
    person = _resample_until_no_collision(
        rng, public_figures, nationality=nationality, age_profile=age_profile,
        age=rng.randint(13, 17) if minor else None,
        age_clamp=spec.get("subject_age"),
    )
    status = None
    if genre in _EMPLOYED_SUBJECT_GENRES:
        status = "employed"
    elif person.age() > 67:
        status = "retired"
    subject = _Subject(person, genre, form, set(spec["clause_genres"]), status=status)
    street_address, postal, place = _address(rng)

    signatory = None
    signatory_role = None
    if rng.random() < 0.75:
        signatory = _resample_until_no_collision(rng, public_figures, age_profile="working")
        signatory_role = rng.choice(spec["signatory_roles"])[0 if form == "nb" else 1]

    ceiling = genres_mod.type_ceiling(length_band[1], spec.get("density_factor", 1.0))
    target = max(1, min(plan.type_target, ceiling))

    def _clause_types_ok(etype: str) -> bool:
        if taxonomy_index.get(etype, {}).get("value_kind") != "clause":
            return etype in taxonomy_index and etype in _VALUE_KIND_TYPES
        if etype == "ETHNICITY" and genre not in genres_mod.ETHNICITY_ALLOWED_GENRES:
            return False
        if etype == "EMPLOYMENT" and minor:
            return False
        if etype == "EMPLOYMENT":
            return True
        if etype == "IMMIGRATION_STATUS" and not subject.foreign:
            return False
        return any(_clause_fits(e, subject) for e in clause_bank.get(etype, []))

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
    is_clause = lambda t: taxonomy_index.get(t, {}).get("value_kind") == "clause"  # noqa: E731
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

    pair_employer = genre in _EMPLOYED_SUBJECT_GENRES or rng.random() < 0.4
    extra_org = int("EMPLOYMENT" in judgement and pair_employer and "ORGANIZATION" not in core)
    room = target - len(core) - len(judgement) - len(forced_values) - extra_org
    value_weights = {t: w for t, w in spec["values"].items()
                     if t not in core and t not in judgement and t not in forced_values}
    values = forced_values + _weighted_pick(rng, value_weights, max(0, room),
                                            lambda t: t in _VALUE_KIND_TYPES or t == "PERSON")

    chosen = core + [t for t in values if t not in core] + judgement
    order = {t: i for i, t in enumerate(_SAMPLING_ORDER)}
    clause_types = sorted(
        [t for t in chosen if taxonomy_index.get(t, {}).get("value_kind") == "clause"],
        key=lambda t: order.get(t, len(order)),
    )

    planned: List[PlannedValue] = []
    tier = lambda t: taxonomy_index[t]["tier"]  # noqa: E731

    employer: Optional[str] = None
    employer_roles: List[Tuple[str, str]] = []
    if "ORGANIZATION" in chosen or ("EMPLOYMENT" in chosen and pair_employer
                                    and subject.status != "retired"):
        employer, employer_roles = _employer(rng, place)
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
        candidates = [e for e in clause_bank.get(etype, []) if _clause_fits(e, subject)]
        if not candidates:
            continue
        entry = rng.choice(candidates)
        subject.status = subject.status or entry.get("status")
        subject.marital = subject.marital or entry.get("marital")
        if etype == "SEXUAL_ORIENTATION":
            subject.no_partner = True
        clause_texts[etype] = entry

    parties: List[Party] = [Party(person, None, "hovedpersonen", is_subject=True)]
    if signatory:
        parties.append(Party(signatory, "author", signatory_role or "saksbehandler", staff=True))

    profile_cast = genres_mod.PROFILES[plan.profile]["cast"]
    n_cast = min(rng.randint(*profile_cast), len(spec.get("cast_roles", [])) + 2)
    cast_pool = list(spec.get("cast_roles", []))
    rng.shuffle(cast_pool)
    for role in cast_pool[:n_cast]:
        role_spec = genres_mod.CAST_ROLES[role]
        member = _cast_person(rng, role, person, public_figures, age_profile)
        parties.append(Party(member, role, role_spec[form], staff=role in _STAFF_ROLES))

    date_lo, date_hi = genres_mod.PROFILES[plan.profile]["dates"]

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
                                            None, label(etype), hint=hint))
            continue
        if etype == "ADDRESS":
            planned.append(PlannedValue(etype, tier(etype), "value", street_address, None, label(etype),
                                        hint="hovedpersonens bostedsadresse"))
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
                employer, employer_roles = _employer(rng, place)
            planned.append(PlannedValue(etype, tier(etype), "value", employer, None, label(etype),
                                        hint="hovedpersonens arbeidsgiver"))
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
            planned.append(PlannedValue(
                etype, tier(etype), "clause", text if strategy == "seeded" else None,
                strategy, label(etype), difficulty=chosen_entry.get("difficulty"),
            ))
            continue
        if entry.get("value_kind") == "clause":
            continue  # no coherent clause for this subject; drop rather than contradict
        try:
            value, checksum_valid = _generate_value_kind(etype, rng, person, invalid_rate=0.0)
        except KeyError:
            continue
        hint = None
        if etype == "MEDICAL_LICENSE" and signatory:
            hint = f"HPR-nummeret til {signatory.full_name}"
        elif etype == "ORG_NUMBER" and employer:
            hint = f"organisasjonsnummeret til {employer}"
        planned.append(PlannedValue(etype, tier(etype), "value", value, None, label(etype),
                                    checksum_valid, hint=hint))

    if "MARITAL_STATUS" in chosen:
        marital = subject.marital
        if not marital:
            options = ["ugift", "gift", "skilt", "samboer"]
            if person.age() >= 55:
                options.append("enke" if person.gender == "F" else "enkemann")
            marital = rng.choice(options if person.age() >= 20 else ["ugift"])
        planned.append(PlannedValue("MARITAL_STATUS", tier("MARITAL_STATUS"), "value", marital, None,
                                    label("MARITAL_STATUS"), hint="hovedpersonens sivilstand"))

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
            if etype not in planned_types and len(planned_types) >= ceiling:
                continue
            if etype == "ORGANIZATION":
                value, checksum_valid = _employer(rng, place)[0], None
            else:
                try:
                    value, checksum_valid = _generate_value_kind(
                        etype, rng, party.person, invalid_rate=0.0, staff=party.staff)
                except KeyError:
                    continue
            planned_types.add(etype)
            planned.append(PlannedValue(
                etype, tier(etype), "value", value, None, genres_mod.field_label(etype, form),
                checksum_valid, hint=f"tilhører {party.label} {party.person.full_name}"))

    return Record(doc_seed, genre, plan.variant, form, length_band, person, parties, planned,
                  signatory_role=signatory_role, employer=employer, profile=plan.profile)


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
    "field_header": "et skjema med feltoverskrifter for personalia og saksopplysninger, "
                    "etterfulgt av en fritekstdel i hele setninger",
    "prose_letter": "et sammenhengende brev med hilsen og løpende prosa",
    "numbered_findings": "nummererte avsnitt med funn og vurderinger, hvert avsnitt i hele setninger",
    "table_summary": "en kort tabell med bare identifikasjonsopplysninger (navn, nummer, datoer), "
                     "etterfulgt av en vurdering i løpende tekst",
    "minutes": "et møtereferat der hvert punkt er skrevet som hele setninger",
}

_PRONOUNS = {
    ("F", "nb"): "hun / henne / hennes", ("M", "nb"): "han / ham / hans",
    ("F", "nn"): "ho / henne / hennar", ("M", "nn"): "han / han / hans",
}

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

    value_lines, clause_lines = [], []
    manifest = [f"SEED|{record.doc_seed}", f"META|form={record.form}"]
    marked = False
    for pv in record.planned:
        if pv.value_kind == "value":
            hint = f" ({pv.hint})" if pv.hint else ""
            value_lines.append(f"- {pv.field_label}{hint}: {pv.value}")
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

    named = ", ".join(p.person.full_name for p in record.parties) or "ingen"
    rules = [
        "ALLE oppgitte verdier og opplysninger skal brukes ORDRETT, tegn for tegn, uten omskriving "
        "eller endret bøyning.",
        "Opplysningene om personene skal flettes inn i vanlige, hele setninger i brødteksten – "
        "ikke i tabeller, ikke som punkter i en liste og ikke rett etter en feltetikett eller overskrift. "
        "Ingen overskrift eller etikett i dokumentet får nevne hva slags opplysning det er "
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
        "Varier hvor verdiene står – noen i felt, noen midt i løpende tekst, og noen kan gjentas naturlig.",
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
        "Etnisitet, religion, nasjonalitet, seksualitet og oppholdsstatus skal, hvis de er oppgitt, "
        "stå som nøytrale personopplysninger. De skal ALDRI knyttes til mistanke, risiko, "
        "kriminalitet, farlighet eller troverdighet.",
    ]
    if marked:
        rules.append("For markerte setninger: skriv ⟦TYPE: setning⟧ nøyaktig én gang per type, "
                     "uten andre ⟦ ⟧ tegn i teksten for øvrig.")
    rules.append("Skriv dokumentet slik en saksbehandler ville skrevet det. Kommenter aldri "
                 "instruksjonene, og skriv ikke setninger som «ingen ytterligere "
                 "personopplysninger foreligger» eller «X er den eneste personen som nevnes».")
    rules.append("Ikke gjenta verdiene i en liste eller et felt til slutt i dokumentet.")
    rules.append("Svar bare med selve dokumentet, uten kommentarer før eller etter.")

    prompt = f"{header}\n\n{subject_line}\n\nVerdier som skal stå ordrett:\n" + "\n".join(value_lines)
    if clause_lines:
        prompt += ("\n\nOpplysninger som skal stå ordrett inne i løpende setninger:\n"
                   + "\n".join(clause_lines))
    prompt += "\n\nRegler:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    return prompt + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


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
    lines = []
    for m in missing:
        pv = by_value.get(m)
        if pv is not None and pv.value_kind == "value":
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
    "TAX_ID": ident.is_valid_tax_id,
    # Only the IMEI branch of DEVICE_ID declares a checksum at all; a UUID or a
    # MAC address is recorded with checksum_valid=None and never reaches here.
    "DEVICE_ID": ident.is_valid_luhn,
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


def _doc_seed(base_seed: int, idx: int, attempt: int) -> int:
    return base_seed * 100003 + idx * 97 + attempt


def new_attempt_record(state: DocState, base_seed: int, taxonomy_index: Dict[str, dict],
                       clause_bank: dict, public_figures: Set[str], config: GenerationConfig) -> Record:
    """Sample the record for the state's next attempt, deterministically from its doc seed."""
    state.attempt += 1
    state.repairs = 0
    state.audit_repairs = 0
    plan = state.plan
    doc_seed = _doc_seed(base_seed, plan.idx, state.attempt)
    rng = random.Random(doc_seed)
    record = sample_record(
        rng, doc_seed, plan, config.strategy, taxonomy_index, clause_bank, public_figures,
    )
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
    repetition_ok, repetition = gates.gate_internal_repetition(clean_text, config.repetition_threshold)
    if not repetition_ok:
        return fail("G12_repetition", {"repeat_8gram_share": repetition,
                                       "threshold": config.repetition_threshold})

    literal_values = [
        pv.value for pv in record.planned
        if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")
    ]
    if record.pii_free and literal_values:
        return fail("plan_inconsistent", "a PII-free record must plan no values")
    g2_ok, g2_missing = gates.gate_verbatim(literal_values, clean_text)
    missing_marks = [pv.type for pv in record.planned if pv.strategy == "marked" and pv.type not in marked_spans]
    if not g2_ok or missing_marks:
        state.gate_log.append({**stage_tag, "stage": "G2_verbatim", "ok": False,
                               "detail": {"missing_values": g2_missing, "missing_marked_types": missing_marks}})
        # A 600-character note plants five values and a case file plants
        # twenty-five; allowing the same two missing values in both meant every
        # case file was discarded for one inflected string out of twenty-five,
        # which threw away a document whose other twenty-four labels were
        # correct. The repair allowance scales with how much was planted.
        n_planted = max(1, len(literal_values))
        allowance = max(config.repair_max_missing, n_planted // config.repair_missing_per_values)
        if (not missing_marks and len(g2_missing) <= allowance
                and state.repairs < config.max_repairs):
            return "repair", g2_missing
        return "retry", None

    clauses = [pv.value for pv in record.planned if pv.value_kind == "clause" and pv.value]
    clauses += [span for spans in marked_spans.values() for span in spans]
    slot_ok, slot_hits = gates.gate_slot_labels(clean_text, clauses)
    if not slot_ok:
        return fail("G9_slot", slot_hits)

    names_to_check = [p.person.full_name for p in record.parties]
    g3_ok, g3_hits = gates.gate_name_collision(names_to_check, clean_text, public_figures, place_names, agency_names)
    if not g3_ok:
        return fail("G3_name_collision", g3_hits)

    tier_a_findings = build_tier_a_findings(record)
    g4_ok, g4_bad = gates.gate_identifier_checksums(tier_a_findings)
    if not g4_ok:
        return fail("G4_checksum", g4_bad)

    ngrams = gates.word_ngrams(clean_text)
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

    covered = [v for vals in output.values() for v in vals]
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
    output = _prune_redundant_nested(clean_text, output)

    state.gate_log.append({**stage_tag, "stage": "accepted", "ok": True,
                           "g7_findings": g7_findings, "g7_policy": config.g7_policy})
    state.result = {
        "accepted": True, "record": record, "text": clean_text, "output": output,
        "ngrams": ngrams, "tier_a_findings": tier_a_findings, "g7_labelled": labelled,
        "clause_extensions": extensions, "clause_extensions_count": n_extended,
    }
    return "accepted", None


def _token_budget(config: GenerationConfig, max_chars: int) -> int:
    # Norwegian runs ~2.6 characters per token under the Qwen tokenizer. The
    # model overshoots its band by 20-40%, and overshoot is accepted, so the
    # budget leaves 60% headroom for it to finish; only output that still hits
    # the budget is truncated and rejected.
    return min(max(config.max_new_tokens, int(max_chars * config.length_factor / 2.6) + 120),
               int(config.hard_max_chars / 2.6) + 120)


def run_generation(
    plans: List[DocPlan], base_seed: int, taxonomy_index: Dict[str, dict], clause_bank: dict,
    public_figures: Set[str], place_names: Set[str], agency_names: Set[str], backend,
    config: GenerationConfig, progress=None,
) -> Tuple[List[DocState], dict]:
    """Generate every planned document, `config.batch_size` prompts per backend call.

    A job is one of four kinds, and jobs of different kinds never share a
    backend call because they need different sampling: a fresh attempt (a new
    record from the attempt's doc seed, at the run temperature), a G2 repair of
    the current draft (lower temperature, so the repair stays close to the
    draft), a G11 content audit of an otherwise-accepted document (temperature
    0, because the same document must audit the same way every time), and a G11
    repair that deletes or neutralises what the audit found.

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

    Returns:
        Tuple of (final states in plan order, run statistics).
    """
    states = [DocState(plan) for plan in plans]
    queue: collections.deque = collections.deque()
    for st in states:
        new_attempt_record(st, base_seed, taxonomy_index, clause_bank, public_figures, config)
        queue.append((st, "fresh", None))
    accepted_ngrams: List[Set[Tuple[str, ...]]] = []
    stats: collections.Counter = collections.Counter()

    def _finalize(st: DocState) -> None:
        accepted_ngrams.append(st.result["ngrams"])
        if progress:
            progress(st)

    def _retry_or_give_up(st: DocState, reason: str) -> None:
        if st.attempt < config.retries:
            new_attempt_record(st, base_seed, taxonomy_index, clause_bank, public_figures, config)
            queue.append((st, "fresh", None))
        else:
            st.result = {"accepted": False, "reason": reason}
            if progress:
                progress(st)

    def _covered_spans(st: DocState) -> List[str]:
        return [v for vals in st.result["output"].values() for v in vals]

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
            elif kind == "audit":
                prompts.append(audit.build_audit_prompt(
                    st.result["text"], _covered_spans(st), st.record.doc_seed))
                budgets.append(config.audit_max_new_tokens)
            else:
                keep = [pv.value for pv in st.record.planned if pv.value]
                prompts.append(audit.build_audit_repair_prompt(
                    st.result["text"], payload, keep, st.record.form, st.record.doc_seed))
                budgets.append(_token_budget(config, max(st.record.length_band[1],
                                                         len(st.result["text"]))))
        call_seed = hash(tuple(st.record.doc_seed * 10 + st.repairs + 3 * st.audit_repairs
                              for st, _k, _p in jobs)) & 0x7FFFFFFF
        temperature = {
            "fresh": config.temperature, "repair": config.repair_temperature,
            "audit": 0.0, "audit_repair": config.repair_temperature,
        }[kind]
        started = time.time()
        texts = backend.generate(prompts, max_new_tokens=max(budgets), temperature=temperature,
                                 seed=call_seed)
        elapsed = time.time() - started
        finished_flags = getattr(backend, "last_finished", None) or [True] * len(texts)
        stats["generate_calls"] += 1
        stats[f"{kind}_jobs"] += len(jobs)
        if kind == "audit":
            stats["audit_seconds"] += elapsed

        for (st, _k, _payload), text, finished in zip(jobs, texts, finished_flags):
            share = elapsed / len(jobs)
            if kind == "audit":
                st.audit_seconds += share
                st.audit_calls += 1
                document = st.result["text"]
                pairs = audit.parse_audit_reply(text)
                findings = audit.filter_audit_findings(document, _covered_spans(st), pairs)
                st.audit_log.append({
                    "attempt": st.attempt, "audit_repairs": st.audit_repairs,
                    **audit.audit_stats(pairs, findings),
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
                    queue.appendleft((st, "audit_repair", findings))
                else:
                    stats["audit_regenerations"] += 1
                    _retry_or_give_up(st, "audit_findings_remain")
                continue

            st.gen_seconds += share
            st.generate_calls += 1
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

# How many coverage-scheduled types one document may be asked to host, by
# density profile. A 600-character note cannot absorb a forced type without
# becoming the checklist pilot v1 produced; a case file absorbs several.
MAX_FORCED_BY_PROFILE = {
    "pii_free": 0, "minimal": 0, "light": 1, "typical": 2, "dense": 5, "case_file": 8,
}


def _draw_profiles(rng: random.Random, n: int) -> List[str]:
    """Allocate density profiles across a batch by their target shares.

    Quotas are allocated by largest remainder rather than by an independent draw
    per document, so a 16-document smoke run still contains a case file and a
    PII-free document instead of depending on luck.

    Args:
        rng: Run-level RNG, used only to shuffle the allocation.
        n: Number of documents.

    Returns:
        One profile name per document, in shuffled order.
    """
    quotas = {name: genres_mod.PROFILES[name]["share"] * n for name in genres_mod.PROFILE_ORDER}
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

    Returns:
        Tuple of (one `DocPlan` per document, a scheduling report with the
        planned per-type document counts, the shortfalls and the types no
        requested genre can host).
    """
    profiles = _draw_profiles(rng, n)
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
        report = _schedule_coverage(rng, plans, genre_list, coverage_target, schedulable_types or [])
    else:
        report = _schedule_rare_types(rng, plans, rare_force_share)

    for plan in plans:
        if plan.pii_free:
            continue
        spec = genres_mod.GENRES[plan.genre]
        ceiling = genres_mod.type_ceiling(plan.length_band[1], spec.get("density_factor", 1.0))
        plan.type_target = max(1, min(plan.type_target, ceiling))
        # A contact floor, applied where the genre hosts one: pilot v2's
        # accepted batch carried one phone number in 46 documents.
        contact = _contact_types_for(plan.genre)
        if (contact and plan.profile not in ("pii_free", "minimal")
                and not any(t in plan.forced_types for t in contact)
                and rng.random() < CONTACT_FLOOR_SHARE):
            plan.forced_types.append(rng.choice(contact))
    report["planned_profiles"] = dict(collections.Counter(p.profile for p in plans))
    report["planned_pii_free"] = sum(1 for p in plans if p.pii_free)
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


def _schedule_coverage(
    rng: random.Random, plans: List[DocPlan], genre_list: List[str], target: int,
    schedulable: List[str],
) -> dict:
    """Assign genres and forced types so every schedulable type reaches K documents.

    The pass is greedy and deliberately simple: documents that can host the most
    forced types go first, each is given the genre that covers the largest
    remaining deficit, and the deficit types that genre hosts are attached to it
    up to its profile's limit. A type whose host genres are all outside
    `genre_list` is reported as unreachable rather than forced somewhere
    implausible.

    Args:
        rng: Run-level RNG, for tie-breaking.
        plans: The plans to mutate in place.
        genre_list: Genres the run may use.
        target: Documents each type should reach.
        schedulable: Types to cover.

    Returns:
        A scheduling report.
    """
    hosts = {t: [g for g in genres_hosting_cached(t) if g in genre_list] for t in schedulable}
    unreachable = sorted(t for t, gs in hosts.items() if not gs)
    deficit = {t: target for t in schedulable if hosts[t]}
    assignable = [p for p in plans if not p.pii_free and MAX_FORCED_BY_PROFILE[p.profile] > 0]
    order = sorted(assignable, key=lambda p: (-MAX_FORCED_BY_PROFILE[p.profile], p.idx))
    scheduled: collections.Counter = collections.Counter()

    used_genres: collections.Counter = collections.Counter(p.genre for p in plans)
    for plan in order:
        room = MAX_FORCED_BY_PROFILE[plan.profile] - len(plan.forced_types)
        if room <= 0:
            continue
        wanted = [t for t, d in deficit.items() if d > 0]
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
            hostable = _hostable_for(genre, wanted, hosts, plan.art9_cap)[:room]
            if not hostable:
                continue
            score = (sum(1.0 / len(hosts[t]) for t in hostable)
                     / (1.0 + 0.30 * used_genres[genre]))
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

    shortfall = [{"type": t, "scheduled": scheduled[t], "target": target}
                 for t in sorted(deficit) if deficit[t] > 0]
    return {"mode": "coverage_target", "coverage_target": target,
            "scheduled": dict(scheduled.most_common()), "shortfall": shortfall,
            "unreachable": unreachable}


def _hostable_for(
    genre: str, wanted: Sequence[str], hosts: Dict[str, List[str]], art9_cap: int,
) -> List[str]:
    """Return the deficient types a genre can host, scarcest first, Art. 9 capped.

    A document's Art. 9 budget is decided by its profile, so the scheduler must
    respect it: scheduling three special categories into a short document only
    to have the sampler drop two of them wastes the forced slots and is why
    RELIGIOUS_BELIEF and GENETIC_DATA reached no document in an earlier run.

    Args:
        genre: Candidate genre id.
        wanted: Types still short of their target.
        hosts: Type -> the requested genres that host it.
        art9_cap: How many Art. 9 categories this document may carry.

    Returns:
        Hostable type names, scarcest host set first.
    """
    core_art9 = sum(1 for t in genres_mod.GENRES[genre]["core"]
                    if t in genres_mod.SPECIAL_CATEGORIES)
    budget = max(0, art9_cap - core_art9)
    hostable = sorted((t for t in wanted if genre in hosts[t]),
                      key=lambda t: (len(hosts[t]), t))
    picked, art9_used = [], 0
    for etype in hostable:
        if etype in genres_mod.SPECIAL_CATEGORIES:
            if art9_used >= budget:
                continue
            art9_used += 1
        picked.append(etype)
    return picked


_HOSTS_CACHE: Dict[str, List[str]] = {}


def genres_hosting_cached(etype: str) -> List[str]:
    """Memoised `gendoc_genres.genres_hosting`; the scheduler calls it O(n*genres) times."""
    if etype not in _HOSTS_CACHE:
        _HOSTS_CACHE[etype] = genres_mod.genres_hosting(etype)
    return _HOSTS_CACHE[etype]


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

    `docs/PROJECT_SPEC_V2.md` intends the 59-type taxonomy to become
    project-wide, so a type that the synthetic data never exercises is a gap
    that has to be found now rather than after the gold set is relabelled.
    `CONTEXT_SENSITIVE` and `IDENTIFIABLE_IMAGE` are reported separately as
    deliberately uncovered: `docs/ANNOTATION_SPEC.md` cut both with documented
    reasoning and `PROJECT_SPEC_V2.md` reinstates them without a definition, and
    guessing one would put invented semantics into a dataset whose whole claim
    is that its labels are not guessed.

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
        counts.update(set(meta["types"]))
    below = [{"type": t, "documents": counts.get(t, 0), "target": target}
             for t in schedulable if counts.get(t, 0) < target]
    return {
        "target_documents_per_type": target,
        "types_seen": len(counts),
        "per_type_documents": dict(counts.most_common()),
        "types_absent": sorted(t for t in schedulable if not counts.get(t)),
        "types_below_target": sorted(below, key=lambda r: (r["documents"], r["type"])),
        "deliberately_uncovered": {
            "types": genres_mod.UNCOVERED_TYPES,
            "reason": "ANNOTATION_SPEC.md cut both with documented reasoning; "
                      "PROJECT_SPEC_V2.md reinstates them without defining either. "
                      "Nothing is generated for them and no definition is invented here.",
        },
        "unreachable_in_requested_genres": plan_report.get("unreachable", []),
        "planned_schedule": plan_report,
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
    parser.add_argument("--batch-size", type=int, default=4, help="prompts per backend generate() call")
    parser.add_argument("--max-repairs", type=int, default=1,
                        help="targeted repair passes per attempt when G2 finds 1-2 missing values")
    parser.add_argument("--rare-force-share", type=float, default=0.5,
                        help="share of documents that get one scheduled rare type (Section 5), "
                             "used only when --coverage-target is 0")
    parser.add_argument("--coverage-target", type=int, default=3, metavar="K",
                        help="schedule every schedulable type into at least K documents; 0 disables "
                             "coverage scheduling and falls back to rare-type forcing")
    parser.add_argument("--no-audit", dest="audit", action="store_false",
                        help="skip the G11 content audit (a second model pass per document)")
    parser.add_argument("--max-audit-repairs", type=int, default=1,
                        help="targeted repair passes per attempt when G11 finds unlabelled "
                             "sensitive content")
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
    unknown_genres = [g for g in genre_list if g not in genres_mod.GENRES]
    if unknown_genres:
        print(f"unknown genres: {unknown_genres}", file=sys.stderr)
        return 2
    forced_types = [t.strip() for t in args.force_types.split(",") if t.strip()]

    config = GenerationConfig(
        strategy=args.strategy, invalid_checksum_rate=args.invalid_checksum_rate,
        retries=args.retries, near_dup_threshold=args.near_dup_threshold,
        g7_policy=args.g7_policy, batch_size=args.batch_size, max_repairs=args.max_repairs,
        audit=args.audit, max_audit_repairs=args.max_audit_repairs,
    )

    schedulable = genres_mod.coverage_types([entry["name"] for entry in taxonomy["types"]])
    plans, plan_report = plan_batch(
        rng, args.n, genre_list, forced_types, args.rare_force_share,
        coverage_target=args.coverage_target, schedulable_types=schedulable,
    )

    run_started = time.time()
    finished_count = [0]

    def _progress(st: DocState) -> None:
        finished_count[0] += 1
        ok = st.result and st.result.get("accepted")
        print(
            f"[{finished_count[0]}/{args.n}] #{st.plan.idx} {st.plan.genre}/{st.plan.form}/"
            f"{st.plan.profile} {'accepted' if ok else 'DISCARDED'} after {st.attempt} attempt(s), "
            f"{st.repairs_total} repair(s), {st.audit_repairs_total} audit repair(s), "
            f"{time.time() - run_started:.0f}s elapsed",
            file=sys.stderr, flush=True,
        )

    states, run_stats = run_generation(
        plans, args.seed, taxonomy_index, clause_bank, public_figures, place_names,
        agency_names, backend, config, progress=_progress,
    )
    wall_seconds = time.time() - run_started

    accepted, discarded_records = [], []
    for st in states:
        if not st.result.get("accepted"):
            discarded_records.append({
                "index": st.plan.idx, "genre": st.plan.genre, "variant": st.plan.variant,
                "form": st.plan.form, "profile": st.plan.profile, "pii_free": st.plan.pii_free,
                "reason": st.result.get("reason"), "gate_log": st.gate_log,
                "audit_log": st.audit_log, "last_text": st.last_text,
                "planned": [dataclasses.asdict(pv) for pv in st.record.planned] if st.record else None,
            })
            continue
        accepted.append({
            "id": f"SYN-{st.plan.idx:06d}", "record": st.result["record"], "text": st.result["text"],
            "output": st.result["output"], "gate_log": st.gate_log,
            "tier_a_findings": st.result["tier_a_findings"], "g7_labelled": st.result["g7_labelled"],
            "clause_extensions": st.result.get("clause_extensions", {}),
            "state": st,
        })
    discarded = len(discarded_records)

    batch_path = os.path.join(args.out, "synthetic_batch.jsonl")
    labelled_path = os.path.join(args.out, "synthetic_batch_labelled.jsonl")
    meta_path = os.path.join(args.out, "synthetic_batch_meta.jsonl")
    with open(os.path.join(args.out, "discarded.jsonl"), "w", encoding="utf-8") as disc_f:
        for d in discarded_records:
            disc_f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    with open(batch_path, "w", encoding="utf-8") as batch_f, \
            open(labelled_path, "w", encoding="utf-8") as lab_f, \
            open(meta_path, "w", encoding="utf-8") as meta_f:
        for r in accepted:
            line = json.dumps({"id": r["id"], "text_input": r["text"], "output": r["output"]},
                              ensure_ascii=False)
            batch_f.write(line + "\n")
            if r["output"]:
                lab_f.write(line + "\n")
            rec, st = r["record"], r["state"]
            meta_f.write(json.dumps({
                "id": r["id"], "genre": rec.genre, "variant": rec.variant, "form": rec.form,
                "profile": rec.profile, "pii_free": rec.pii_free,
                "strategy": config.strategy, "seed": rec.doc_seed, "length": len(r["text"]),
                "length_band": list(rec.length_band),
                "planned_types": sorted({pv.type for pv in rec.planned}),
                "forced_types": st.plan.forced_types,
                "type_target": st.plan.type_target, "art9_cap": st.plan.art9_cap,
                "realised_types": sorted(r["output"]),
                "distinct_spans": sum(len(v) for v in r["output"].values()),
                "parties": [{"role": p.role or ("subject" if p.is_subject else None),
                             "gender": p.person.gender, "age": p.person.age(),
                             "nationality": p.person.nationality} for p in rec.parties],
                "subject": ({"gender": rec.person.gender, "age": rec.person.age(),
                             "nationality": rec.person.nationality} if rec.person else None),
                "num_attempts": st.attempt, "num_repairs": st.repairs_total,
                "num_audit_repairs": st.audit_repairs_total,
                "generate_calls": st.generate_calls, "gen_seconds": round(st.gen_seconds, 1),
                "audit_calls": st.audit_calls, "audit_seconds": round(st.audit_seconds, 1),
                "audit_log": st.audit_log,
                "clause_extensions": r["clause_extensions"],
                "g7_labelled": r["g7_labelled"],
                "gate_log": r["gate_log"], "tier_a_findings": r["tier_a_findings"],
            }, ensure_ascii=False) + "\n")

    # `validate_labels.py` exits 1 on any record with an empty output, by
    # design: an unfinished annotation run looks exactly like a clean document.
    # PII-free documents are legitimately empty, so G1 runs on the labelled
    # subset for the pass/fail verdict and on the whole batch for the record.
    # The validator's semantics are not changed here; whether it should grow an
    # opt-in flag for deliberately empty records is the owner's call.
    g1_ok, g1_output = run_g1_validate_labels(labelled_path, types_config_path)
    g1_full_ok, g1_full_output = run_g1_validate_labels(batch_path, types_config_path)

    accepted_meta_for_g5 = [
        {"genre": r["record"].genre, "form": r["record"].form, "length": len(r["text"]),
         "band": r["record"].length_band, "types": list(r["output"])}
        for r in accepted
    ]
    g5_report = gate_g5_distribution(accepted_meta_for_g5, genre_list)
    g6_report = gate_g6_aggregate([r["text"] for r in accepted])

    dump_path = os.path.join(args.out, "sample_dump.md")
    if accepted:
        write_sample_dump(dump_path, accepted, args.sample_dump_n, rng)

    g7_fp_report = (measure_g7_false_positive_rate(args.gold_sample_glob, place_names, agency_names)
                    if args.gold_sample_glob else None)
    g7_mock_findings = sum(
        1 for r in accepted for entry in r["gate_log"] if entry.get("stage") == "accepted"
        for f in entry.get("g7_findings", []) if f.get("action") == "reject"
    )

    total_spans = sum(len(v) for r in accepted for v in r["output"].values())
    labelled_spans = sum(len(r["g7_labelled"]) for r in accepted)
    types_per_doc = [len(r["output"]) for r in accepted]
    report = {
        "requested": args.n, "accepted": len(accepted), "discarded": discarded,
        "backend": args.backend, "model": args.model, "strategy": args.strategy,
        "batch_size": args.batch_size, "audit_enabled": config.audit,
        "wall_seconds": round(wall_seconds, 1),
        "wall_seconds_per_requested_doc": round(wall_seconds / max(1, args.n), 1),
        "wall_seconds_per_accepted_doc": round(wall_seconds / len(accepted), 1) if accepted else None,
        "attempts_total": sum(st.attempt for st in states),
        "run_stats": run_stats,
        "types_per_accepted_doc": {"min": min(types_per_doc, default=None),
                                   "max": max(types_per_doc, default=None),
                                   "mean": round(sum(types_per_doc) / len(types_per_doc), 2)
                                   if types_per_doc else None},
        "g7_labelled_spans": {"count": labelled_spans, "total_spans": total_spans,
                              "share": round(labelled_spans / total_spans, 4) if total_spans else 0.0},
        "repetition_share": {
            "max": max((gates.repetition_share(r["text"]) for r in accepted), default=None),
            "threshold": config.repetition_threshold,
        },
        "clause_extension_fired": sum(len(r["clause_extensions"]) for r in accepted),
        "clause_extension_docs": sum(1 for r in accepted if r["clause_extensions"]),
        "failure_stages": dict(collections.Counter(
            e["stage"] for st in states for e in st.gate_log if not e.get("ok"))),
        "discard_reasons": dict(collections.Counter(
            d.get("reason") or "unknown" for d in discarded_records)),
        "used_fallback_taxonomy": used_fallback_taxonomy,
        "used_fallback_clause_bank": used_fallback_clause_bank,
        "types_config_used": types_config_path,
        "G1_validate_labels": {"passed": g1_ok, "path": labelled_path, "output": g1_output},
        "G1_validate_labels_full_batch": {
            "passed": g1_full_ok, "path": batch_path,
            "note": "exits 1 when the batch contains PII-free documents; validate_labels.py "
                    "treats any empty output as an unfinished annotation. Semantics unchanged.",
            "output": g1_full_output,
        },
        "G5_distribution": g5_report,
        "G6_diversity": g6_report,
        "G7_unplanned_pii_on_accepted": {"policy": args.g7_policy, "residual_findings": g7_mock_findings},
        "G7_false_positive_measurement_on_gold": g7_fp_report,
        "G11_content_audit": audit_report(states, accepted, wall_seconds),
        "coverage": coverage_report(accepted_meta_for_g5, schedulable, args.coverage_target, plan_report),
        "density": density_report(accepted, plans),
    }
    report_path = os.path.join(args.out, "gate_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=lambda o: str(o))

    printable = {k: v for k, v in report.items()
                 if k not in ("G1_validate_labels", "G1_validate_labels_full_batch")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    print("\nG1 validate_labels.py output (labelled subset):\n" + g1_output)
    print(f"\nWrote {len(accepted)}/{args.n} accepted documents to {batch_path}")
    print(f"Gate report: {report_path}")
    return 0 if g1_ok else 1


if __name__ == "__main__":
    sys.exit(main())
