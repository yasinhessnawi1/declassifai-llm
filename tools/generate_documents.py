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

    plan_batch -> sample_record -> build_prompt -> backend.generate (batched)
        -> marker check, truncation, G0 placeholders, length band
        -> G2 verbatim (1-2 missing values: targeted repair of the draft)
        -> slot-label gate, G3, G4, G6, G7 (unplanned names/dates labelled,
           other unplanned PII rejected) -> accept or retry with a new record

then, over the whole accepted batch: G1 (schema validation via
`tools/validate_labels.py`), G5 (genre/form/length/type distribution vs the
plan) and G8 (a human-readable sample dump).

What the first real pilot (data/synthetic/pilot_v1) changed: records are now
sampled for coherence (one subject, consistent gender, age and fødselsnummer,
the address's own postal code, an employer and role that belong together,
immigration facts only for foreign subjects) and for a genre-realistic type
mix, instead of drawing every optional type independently; judgement clauses
are listed without category names and must sit in running prose; and several
documents share one generate() call.

Usage:
    python3 tools/generate_documents.py --backend mock --n 50 \\
        --genres gp_referral,police_report,nav_decision,dismissal_letter,udi_decision \\
        --strategy seeded --seed 1 --batch-size 4 --out data/synthetic/pilot/
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
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    """A fully sampled, typed record for one document."""

    doc_seed: int
    genre: str
    variant: str
    form: str  # "nb" or "nn"
    length_band: Tuple[int, int]
    person: Person
    other_people: List[Person]
    planned: List[PlannedValue]
    signatory_role: Optional[str] = None
    employer: Optional[str] = None


def sample_person(rng: random.Random, min_age: int = 18, max_age: int = 85,
                   today: date = REFERENCE_DATE, nationality: str = "norsk",
                   gender: Optional[str] = None) -> Person:
    """Sample a person from the embedded name lists, never a real public figure.

    Args:
        rng: Seeded RNG.
        min_age: Minimum age in years as of `today`.
        max_age: Maximum age in years as of `today`.
        today: Reference date for computing the birth date from an age.
        nationality: Nationality adjective; a non-Norwegian one draws the name
            from that nationality's pool in `gendoc_data.FOREIGN_NAMES`.
        gender: Force "M" or "F"; None picks at random.

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
    age = rng.randint(min_age, max_age)
    birth = date(today.year - age, rng.randint(1, 12), rng.randint(1, 28))
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
        return ident.email_address(rng, _ascii(person.first_name), _ascii(person.last_name)), None
    if etype == "URL":
        return ident.url(rng), None
    if etype == "IP_ADDRESS":
        return ident.ip_address(rng), None
    if etype == "USERNAME":
        return ident.username(rng, _ascii(person.first_name), _ascii(person.last_name)), None
    if etype == "SOCIAL_MEDIA":
        return ident.social_media_handle(rng, _ascii(person.first_name), _ascii(person.last_name)), None
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
    status: Optional[str] = None  # employed / unemployed / retired / uforetrygd
    marital: Optional[str] = None
    no_partner: bool = False  # set once a SEXUAL_ORIENTATION clause is chosen

    @property
    def foreign(self) -> bool:
        return self.person.nationality != "norsk"


_YEAR_IN_TEXT_RE = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")


def _clause_fits(entry: dict, subject: _Subject) -> bool:
    """Whether a clause-bank entry is coherent with the record's subject.

    Args:
        entry: A clause-bank entry (see `schema_note` in clause_bank.json).
        subject: The subject state so far.

    Returns:
        True if the entry's genre, form, gender, age, origin, status and partner
        constraints all hold, and any year it mentions falls after the
        subject's 15th birthday.
    """
    if subject.genre not in entry.get("genres", []) or entry.get("form") != subject.form:
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


def sample_record(
    rng: random.Random, doc_seed: int, genre: str, variant: str, form: str,
    length_band: Tuple[int, int], strategy: str, taxonomy_index: Dict[str, dict],
    clause_bank: dict, public_figures: Set[str], forced_types: List[str],
) -> Record:
    """Sample a coherent, genre-realistic typed record for one document.

    One data subject, with one address whose postal code is the POSTAL_CODE,
    an employer and role that belong together, an age that agrees with the
    fødselsnummer, and a type mix drawn from the genre's profile
    (`gendoc_genres.GENRES`): its core types, plus optional values and 1-4
    judgement types scaled to the length band, with at most
    `SPECIAL_CATEGORY_CAP` GDPR Art. 9 categories.

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
        forced_types: Types to include if they can be made coherent (batch-level
            rare-type scheduling plus any `--force-types`).

    Returns:
        A `Record` with `planned` fully populated.
    """
    spec = genres_mod.GENRES[genre]
    foreign = rng.random() < spec.get("foreign_subject_p", 0.0)
    minor = rng.random() < spec.get("minor_subject_p", 0.0)
    nationality = rng.choice(data.FOREIGN_NATIONALITIES) if foreign else "norsk"
    age_lo, age_hi = spec.get("subject_age", (18, 85))
    person = _resample_until_no_collision(
        rng, public_figures, nationality=nationality,
        min_age=13 if minor else age_lo, max_age=17 if minor else age_hi,
    )
    status = "employed" if genre == "dismissal_letter" else ("retired" if person.age() > 67 else None)
    subject = _Subject(person, genre, form, status=status)
    street_address, postal, place = _address(rng)

    signatory = None
    signatory_role = None
    if rng.random() < 0.75:
        signatory = _resample_until_no_collision(rng, public_figures)
        signatory_role = rng.choice(spec["signatory_roles"])[0 if form == "nb" else 1]

    def _clause_types_ok(etype: str) -> bool:
        if taxonomy_index.get(etype, {}).get("value_kind") != "clause":
            return etype in taxonomy_index
        if etype == "EMPLOYMENT" and (minor or subject.status == "retired"):
            return any(_clause_fits(e, subject) for e in clause_bank.get(etype, [])) and not minor
        if etype == "EMPLOYMENT":
            return True
        if etype == "IMMIGRATION_STATUS" and not subject.foreign:
            return False
        return any(_clause_fits(e, subject) for e in clause_bank.get(etype, []))

    special_used = [t for t in spec["core"] if t in genres_mod.SPECIAL_CATEGORIES]

    def _allowed(etype: str) -> bool:
        if etype in genres_mod.SPECIAL_CATEGORIES:
            if len(special_used) >= genres_mod.SPECIAL_CATEGORY_CAP:
                return False
        ok = _clause_types_ok(etype)
        if ok and etype in genres_mod.SPECIAL_CATEGORIES:
            special_used.append(etype)
        return ok

    (t_lo, t_hi), (j_lo, j_hi) = genres_mod.BAND_BUDGET.get(tuple(length_band), ((6, 7), (2, 3)))
    pair_employer = genre == "dismissal_letter" or rng.random() < 0.4
    judgement: List[str] = []
    for etype in forced_types:
        if etype not in spec["core"] and etype not in judgement and _allowed(etype):
            judgement.append(etype)
    remaining = {t: w for t, w in spec["judgement"].items() if t not in judgement}
    n_judgement = min(rng.randint(j_lo, j_hi), t_hi - len(spec["core"]))
    judgement += _weighted_pick(rng, remaining, max(0, n_judgement - len(judgement)), _allowed)
    # EMPLOYMENT with its employer adds ORGANIZATION too, so it counts double.
    # An ADDRESS's nested POSTAL_CODE is not counted: it is the same fact.
    extra_org = int("EMPLOYMENT" in judgement and pair_employer and "ORGANIZATION" not in spec["core"])
    room = rng.randint(t_lo, t_hi) - len(spec["core"]) - len(judgement) - extra_org
    values = _weighted_pick(rng, spec["values"], max(0, room))

    chosen = list(spec["core"]) + [t for t in values if t not in spec["core"]] + judgement
    if "EMPLOYMENT" in chosen and minor:
        chosen.remove("EMPLOYMENT")
    order = {t: i for i, t in enumerate(_SAMPLING_ORDER)}
    clause_types = sorted(
        [t for t in chosen if taxonomy_index.get(t, {}).get("value_kind") == "clause"],
        key=lambda t: order.get(t, len(order)),
    )

    planned: List[PlannedValue] = []
    tier = lambda t: taxonomy_index[t]["tier"]  # noqa: E731
    label = lambda t: genres_mod.FIELD_LABELS.get(t, t)  # noqa: E731

    employer: Optional[str] = None
    employer_roles: List[Tuple[str, str]] = []
    if "ORGANIZATION" in chosen or ("EMPLOYMENT" in chosen and pair_employer and subject.status != "retired"):
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

    for etype in chosen:
        entry = taxonomy_index.get(etype)
        if entry is None:
            continue
        if etype == "PERSON":
            planned.append(PlannedValue("PERSON", tier(etype), "value", person.full_name, None,
                                        label(etype), hint="hovedpersonen"))
            if signatory:
                planned.append(PlannedValue("PERSON", tier(etype), "value", signatory.full_name, None,
                                            label(etype), hint=f"{signatory_role}, som skriver dokumentet"))
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
            planned.append(PlannedValue(etype, tier(etype), "value", person.nationality, None, label(etype),
                                        hint="hovedpersonens statsborgerskap"))
            continue
        if etype == "MARITAL_STATUS":
            continue  # filled in after the clauses, from whatever they imply
        if etype == "NATIONAL_ID":
            idf = ident.fodselsnummer(rng, person.birth_date, person.gender, valid=True,
                                      dnummer=subject.foreign and rng.random() < 0.6)
            planned.append(PlannedValue(etype, tier(etype), "value", idf.value, None, label(etype),
                                        idf.valid, hint="hovedpersonens"))
            continue
        if etype == "DATE_TIME":
            n_dates = 2 if length_band[1] > 800 and rng.random() < 0.5 else 1
            offsets = sorted(rng.sample(range(1, 700), n_dates))
            hints = ["dokumentets dato", "dato for hendelsen eller vedtaket saken gjelder"]
            for k, off in enumerate(offsets):
                planned.append(PlannedValue(etype, tier(etype), "value",
                                            _format_date(rng, REFERENCE_DATE - timedelta(days=off)),
                                            None, label(etype), hint=hints[k]))
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

    others = [signatory] if signatory else []
    return Record(doc_seed, genre, variant, form, length_band, person, others, planned,
                  signatory_role=signatory_role, employer=employer)


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
    person = record.person
    gender_word = ("kvinne" if person.gender == "F" else "mann")
    subject_line = (
        f"Hovedpersonen er {person.full_name}, {gender_word}, {person.age()} år. "
        f"Omtal hovedpersonen med pronomenene {_PRONOUNS[(person.gender, record.form)]}"
        + (" – aldri «han»." if person.gender == "F" else " – aldri «hun»/«ho».")
    )
    if record.signatory_role and record.other_people:
        subject_line += (f" Dokumentet er skrevet og signert av {record.other_people[0].full_name} "
                         f"({record.signatory_role}).")
    if record.employer:
        subject_line += f" Hovedpersonens arbeidsgiver er {record.employer}; ingen annen virksomhet er involvert."

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

    rules = [
        "ALLE oppgitte verdier og opplysninger skal brukes ORDRETT, tegn for tegn, uten omskriving "
        "eller endret bøyning.",
        "Opplysningene om hovedpersonen skal flettes inn i vanlige, hele setninger i brødteksten – "
        "ikke i tabeller, ikke som punkter i en liste og ikke rett etter en feltetikett eller overskrift. "
        "Ingen overskrift eller etikett i dokumentet får nevne hva slags opplysning det er "
        "(for eksempel helse, atferd, religion, fagforening, seksuell legning, økonomi, familie, etnisitet).",
        "Ikke finn på andre personnavn, fødselsnumre, telefonnumre, e-postadresser, adresser, postnumre, "
        "kontonumre eller virksomheter enn de som er oppgitt. Andre personer omtales bare med rolle "
        "(«saksbehandleren», «naboen», «legen») og uten navn.",
        "Ikke bruk andre datoer enn de oppgitte; skriv heller «samme dag», «tre uker senere» og lignende.",
        "Ikke bruk plassholdere som [NAVN] eller [DATO], og ikke skriv noe på engelsk.",
        "Varier hvor verdiene står – noen i felt, noen midt i løpende tekst, og noen kan gjentas naturlig.",
    ]
    if marked:
        rules.append("For markerte setninger: skriv ⟦TYPE: setning⟧ nøyaktig én gang per type, "
                     "uten andre ⟦ ⟧ tegn i teksten for øvrig.")
    rules.append("Svar bare med selve dokumentet, uten kommentarer før eller etter.")

    prompt = f"{header}\n\n{subject_line}\n\nVerdier som skal stå ordrett:\n" + "\n".join(value_lines)
    if clause_lines:
        prompt += ("\n\nOpplysninger som skal stå ordrett inne i løpende setninger:\n"
                   + "\n".join(clause_lines))
    prompt += "\n\nRegler:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
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
    max_repairs: int = 1
    repair_max_missing: int = 2
    length_factor: float = 1.6
    hard_max_chars: int = 7000


@dataclass
class DocPlan:
    """What the batch plan fixes for one document before any attempt is made."""

    idx: int
    genre: str
    variant: str
    form: str
    length_band: Tuple[int, int]
    forced_types: List[str]


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
    result: Optional[dict] = None


def _doc_seed(base_seed: int, idx: int, attempt: int) -> int:
    return base_seed * 100003 + idx * 97 + attempt


def new_attempt_record(state: DocState, base_seed: int, taxonomy_index: Dict[str, dict],
                       clause_bank: dict, public_figures: Set[str], config: GenerationConfig) -> Record:
    """Sample the record for the state's next attempt, deterministically from its doc seed."""
    state.attempt += 1
    state.repairs = 0
    plan = state.plan
    doc_seed = _doc_seed(base_seed, plan.idx, state.attempt)
    rng = random.Random(doc_seed)
    record = sample_record(
        rng, doc_seed, plan.genre, plan.variant, plan.form, plan.length_band, config.strategy,
        taxonomy_index, clause_bank, public_figures, plan.forced_types,
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

    literal_values = [
        pv.value for pv in record.planned
        if pv.value is not None and (pv.value_kind == "value" or pv.strategy == "seeded")
    ]
    g2_ok, g2_missing = gates.gate_verbatim(literal_values, clean_text)
    missing_marks = [pv.type for pv in record.planned if pv.strategy == "marked" and pv.type not in marked_spans]
    if not g2_ok or missing_marks:
        state.gate_log.append({**stage_tag, "stage": "G2_verbatim", "ok": False,
                               "detail": {"missing_values": g2_missing, "missing_marked_types": missing_marks}})
        if (not missing_marks and len(g2_missing) <= config.repair_max_missing
                and state.repairs < config.max_repairs):
            return "repair", g2_missing
        return "retry", None

    clauses = [pv.value for pv in record.planned if pv.value_kind == "clause" and pv.value]
    clauses += [span for spans in marked_spans.values() for span in spans]
    slot_ok, slot_hits = gates.gate_slot_labels(clean_text, clauses)
    if not slot_ok:
        return fail("G9_slot", slot_hits)

    names_to_check = [record.person.full_name] + [p.full_name for p in record.other_people]
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
    covered = [v for vals in output.values() for v in vals]
    g7_ok, g7_findings = gates.gate_unplanned_pii(clean_text, covered, place_names, agency_names)
    rejecting = [f for f in g7_findings if f["action"] == "reject"]
    if rejecting and config.g7_policy == "reject":
        return fail("G7_unplanned_pii", rejecting)

    # Unplanned full names, honorific+surname forms and dates are labelled
    # rather than regenerated (PROJECT_SPEC_V2.md Section 3.1). A name the
    # model invented still has to clear the public-figure check.
    dob_forms = _date_of_birth_forms(record.person)
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

    A job is either a fresh attempt (new record from the attempt's doc seed)
    or a repair of the current attempt's draft. Jobs from different documents
    share a backend call; each document's record, prompt and gate outcome
    depend only on its own seed and outputs, so batching changes throughput,
    not which records are sampled. Model sampling itself is seeded per call
    from the seeds of the jobs in it.

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
    stats = collections.Counter()

    while queue:
        # Fresh drafts and repairs never share a call: a repair should stay
        # close to its draft, so it samples at a lower temperature.
        kind = queue[0][1]
        jobs = [j for j in queue if j[1] == kind][:config.batch_size]
        for j in jobs:
            queue.remove(j)
        prompts, budgets = [], []
        for st, kind, missing in jobs:
            if kind == "fresh":
                prompts.append(build_prompt(st.record))
                budgets.append(_token_budget(config, st.record.length_band[1]))
            else:
                prompts.append(build_repair_prompt(st.record, st.last_text, missing))
                budgets.append(_token_budget(config, max(st.record.length_band[1], len(st.last_text))))
        call_seed = hash(tuple(st.record.doc_seed * 10 + st.repairs for st, _k, _m in jobs)) & 0x7FFFFFFF
        started = time.time()
        temperature = config.repair_temperature if kind == "repair" else config.temperature
        texts = backend.generate(prompts, max_new_tokens=max(budgets), temperature=temperature,
                                 seed=call_seed)
        elapsed = time.time() - started
        finished_flags = getattr(backend, "last_finished", None) or [True] * len(texts)
        stats["generate_calls"] += 1
        stats["repair_jobs"] += sum(1 for _s, k, _m in jobs if k == "repair")

        for (st, kind, _missing), text, finished in zip(jobs, texts, finished_flags):
            st.gen_seconds += elapsed / len(jobs)
            st.generate_calls += 1
            outcome, missing = evaluate_candidate(
                st, text, finished, taxonomy_index=taxonomy_index, public_figures=public_figures,
                place_names=place_names, agency_names=agency_names, config=config,
                accepted_ngrams=accepted_ngrams,
            )
            if kind == "repair":
                stats["repairs_succeeded" if outcome == "accepted" else "repairs_failed"] += 1
            if outcome == "accepted":
                accepted_ngrams.append(st.result["ngrams"])
                if progress:
                    progress(st)
            elif outcome == "repair":
                st.repairs += 1
                st.repairs_total += 1
                queue.appendleft((st, "repair", missing))
            elif st.attempt < config.retries:
                new_attempt_record(st, base_seed, taxonomy_index, clause_bank, public_figures, config)
                queue.append((st, "fresh", None))
            else:
                st.result = {"accepted": False}
                if progress:
                    progress(st)
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
        lines.append(f"## {r['id']} -- {rec.genre} / {rec.variant} / {rec.form}\n")
        lines.append("**Text:**\n")
        lines.append("```\n" + r["text"] + "\n```\n")
        lines.append("**Labels:**\n")
        for etype, spans in r["output"].items():
            lines.append(f"- `{etype}`: {spans}")
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


def plan_batch(
    rng: random.Random, n: int, genre_list: List[str], length_bands: List[Tuple[int, int]],
    forced_types: List[str], rare_force_share: float,
) -> List[DocPlan]:
    """Fix genre, variant, form, length band and scheduled rare type for every document.

    Rare types (`gendoc_genres.RARE_TYPES`) are forced across the batch rather
    than into every record: a `rare_force_share` of documents each get one,
    chosen among the rare types plausible for that document's genre, always
    the one scheduled least so far, so coverage evens out over the batch
    without any single document turning into a checklist.

    Args:
        rng: Run-level RNG.
        n: Number of documents.
        genre_list: Genres to cycle through.
        length_bands: Candidate (min, max) character bands.
        forced_types: Types the user forces into every record (`--force-types`).
        rare_force_share: Share of documents that get one scheduled rare type.

    Returns:
        One `DocPlan` per document.
    """
    plans, scheduled = [], collections.Counter()
    for i in range(n):
        genre = genre_list[i % len(genre_list)]
        spec = genres_mod.GENRES[genre]
        variant = rng.choice(spec["variants"])
        form = "nn" if rng.random() < 0.35 else "nb"
        band = rng.choice(length_bands)
        forced = list(forced_types)
        plausible = [t for t in genres_mod.RARE_TYPES if t in spec["judgement"] and t not in forced]
        if plausible and rng.random() < rare_force_share:
            low = min(scheduled[t] for t in plausible)
            pick = rng.choice([t for t in plausible if scheduled[t] == low])
            scheduled[pick] += 1
            forced.append(pick)
        plans.append(DocPlan(i, genre, variant, form, band, forced))
    return plans


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
                        help="share of documents that get one scheduled rare type (Section 5)")
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
        g7_policy=args.g7_policy, batch_size=args.batch_size, max_repairs=args.max_repairs,
    )

    length_bands = [(400, 800), (800, 1600), (1600, 2800), (2800, 4000)]
    plans = plan_batch(rng, args.n, genre_list, length_bands, forced_types, args.rare_force_share)

    run_started = time.time()
    finished_count = [0]

    def _progress(st: DocState) -> None:
        finished_count[0] += 1
        ok = st.result and st.result.get("accepted")
        print(
            f"[{finished_count[0]}/{args.n}] #{st.plan.idx} {st.plan.genre}/{st.plan.form} "
            f"{'accepted' if ok else 'DISCARDED'} after {st.attempt} attempt(s), "
            f"{st.repairs_total} repair(s), {time.time() - run_started:.0f}s elapsed",
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
                "form": st.plan.form, "gate_log": st.gate_log, "last_text": st.last_text,
                "planned": [dataclasses.asdict(pv) for pv in st.record.planned] if st.record else None,
            })
            continue
        accepted.append({
            "id": f"SYN-{st.plan.idx:06d}", "record": st.result["record"], "text": st.result["text"],
            "output": st.result["output"], "gate_log": st.gate_log,
            "tier_a_findings": st.result["tier_a_findings"], "g7_labelled": st.result["g7_labelled"],
            "state": st,
        })
    discarded = len(discarded_records)

    batch_path = os.path.join(args.out, "synthetic_batch.jsonl")
    meta_path = os.path.join(args.out, "synthetic_batch_meta.jsonl")
    with open(os.path.join(args.out, "discarded.jsonl"), "w", encoding="utf-8") as disc_f:
        for d in discarded_records:
            disc_f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    with open(batch_path, "w", encoding="utf-8") as batch_f, open(meta_path, "w", encoding="utf-8") as meta_f:
        for r in accepted:
            batch_f.write(json.dumps({"id": r["id"], "text_input": r["text"], "output": r["output"]}, ensure_ascii=False) + "\n")
            rec, st = r["record"], r["state"]
            meta_f.write(json.dumps({
                "id": r["id"], "genre": rec.genre, "variant": rec.variant, "form": rec.form,
                "strategy": config.strategy, "seed": rec.doc_seed, "length": len(r["text"]),
                "length_band": list(rec.length_band),
                "planned_types": sorted({pv.type for pv in rec.planned}),
                "forced_types": st.plan.forced_types,
                "subject": {"gender": rec.person.gender, "age": rec.person.age(),
                            "nationality": rec.person.nationality},
                "num_attempts": st.attempt, "num_repairs": st.repairs_total,
                "generate_calls": st.generate_calls, "gen_seconds": round(st.gen_seconds, 1),
                "g7_labelled": r["g7_labelled"],
                "gate_log": r["gate_log"], "tier_a_findings": r["tier_a_findings"],
            }, ensure_ascii=False) + "\n")

    g1_ok, g1_output = run_g1_validate_labels(batch_path, types_config_path)

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

    g7_fp_report = measure_g7_false_positive_rate(args.gold_sample_glob, place_names, agency_names) if args.gold_sample_glob else None
    g7_mock_findings = sum(
        1 for r in accepted for entry in r["gate_log"] if entry.get("stage") == "accepted"
        for f in entry.get("g7_findings", []) if f.get("action") == "reject"
    )

    total_spans = sum(len(v) for r in accepted for v in r["output"].values())
    labelled_spans = sum(len(r["g7_labelled"]) for r in accepted)
    types_per_doc = [len(r["output"]) for r in accepted]
    report = {
        "requested": args.n, "accepted": len(accepted), "discarded": discarded,
        "backend": args.backend, "strategy": args.strategy, "batch_size": args.batch_size,
        "wall_seconds": round(wall_seconds, 1),
        "wall_seconds_per_requested_doc": round(wall_seconds / max(1, args.n), 1),
        "attempts_total": sum(st.attempt for st in states),
        "run_stats": run_stats,
        "types_per_accepted_doc": {"min": min(types_per_doc, default=None), "max": max(types_per_doc, default=None),
                                   "mean": round(sum(types_per_doc) / len(types_per_doc), 2) if types_per_doc else None},
        "g7_labelled_spans": {"count": labelled_spans, "total_spans": total_spans,
                              "share": round(labelled_spans / total_spans, 4) if total_spans else 0.0},
        "failure_stages": dict(collections.Counter(
            e["stage"] for st in states for e in st.gate_log if not e.get("ok"))),
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
