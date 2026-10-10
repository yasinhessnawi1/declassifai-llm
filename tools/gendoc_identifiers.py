"""Identifier generators and validators for Tier A synthetic PII values.

Each generator produces a value that is realistic in format and, by default,
checksum-valid where Norwegian identifiers define a checksum (fødselsnummer,
D-nummer, organisasjonsnummer, bank account number, IBAN, credit card). The
checksum policy is configurable: a small, explicit fraction of identifiers can
be generated with a deliberately broken checksum so a detector trained on this
data does not learn "checksum-valid" as a proxy for "is PII" -- a typo'd real
number is still real PII. Every generator that can be invalid records that fact
in the metadata it returns, so gates and downstream consumers know which policy
applied to which value; nothing is silently wrong.

All randomness goes through a caller-supplied `random.Random`, so a run seeded
with `--seed N` is fully reproducible end to end.

Checksum policy, recorded per identifier because `docs/SYNTHETIC_DATA_SPEC.md`
Section 5 asks for one policy stated rather than a mixture left implicit:

* Real checksum, generated valid and validated in G4: `fødselsnummer` and
  `D-nummer` (two mod-11 digits), `organisasjonsnummer` (mod-11),
  Norwegian bank account number (mod-11), Norwegian IBAN (ISO 7064 mod-97),
  payment card (Luhn), IMEI (Luhn), `MVA`-form TAX_ID (the mod-11
  organisasjonsnummer it is built from).
* No checksum exists in the real identifier, so format realism only and
  nothing for G4 to check: passport number, national ID card number, visa
  sticker number, driver's licence number, HPR number, Forsvaret service
  number, insurance policy number, student number, MAC address, phone and fax
  number, vehicle registration, postal code, case number, IP address, URL,
  username, social-media handle, password, firearms licence number
  (`våpenkortnummer`, `lisensnummer`) and fishing-vessel registration mark
  (fylkesbokstaver + number + kommunebokstaver). The police and the
  Fiskeridirektoratet publish no check digit for either, and the gold
  examples show no single shape, so both are format realism only. G4 still
  checks that a planned value matches one of the generated shapes, so a
  value that was mangled on its way into the record is caught.
* Format only by deliberate choice: bitcoin-style wallet addresses carry a
  base58check or bech32 checksum in reality, but a checksum-valid address is a
  spendable-looking address, and putting one in a published dataset is a
  needless risk. These are generated to the right shape with an invalid
  checksum and G4 does not check them; the field is recorded as
  `checksum_valid=None` rather than claimed valid.

`invalid_rate` in the generator applies only to the first group: a small,
explicit share of those identifiers is emitted with a broken check digit, so a
detector does not learn "checksum-valid" as a proxy for "is PII".
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple


@dataclass
class Identifier:
    """A generated identifier value plus whether it is checksum-valid."""

    value: str
    valid: bool


def _luhn_check_digit(digits: str) -> int:
    """Return the Luhn check digit for a string of digits (excluding it)."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def is_valid_luhn(digits: str) -> bool:
    """Return whether a full digit string (including its check digit) passes Luhn."""
    digits = re.sub(r"[ .\-]", "", digits)
    if not digits.isdigit():
        return False
    return _luhn_check_digit(digits[:-1]) == int(digits[-1])


# -- fødselsnummer / D-nummer -------------------------------------------------

_FNR_W1 = [3, 7, 6, 1, 8, 9, 4, 5, 2]
_FNR_W2 = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def _fnr_checksums(nine_digits: str) -> Optional[Tuple[int, int]]:
    """Compute the two mod-11 check digits for a 9-digit fnr/D-nummer body."""
    d = [int(c) for c in nine_digits]
    k1 = 11 - (sum(w * x for w, x in zip(_FNR_W1, d)) % 11)
    k1 = 0 if k1 == 11 else k1
    if k1 == 10:
        return None
    k2 = 11 - (sum(w * x for w, x in zip(_FNR_W2, d + [k1])) % 11)
    k2 = 0 if k2 == 11 else k2
    if k2 == 10:
        return None
    return k1, k2


def fodselsnummer(
    rng: random.Random, birth: date, gender: str, valid: bool = True,
    dnummer: bool = False,
) -> Identifier:
    """Generate an 11-digit fødselsnummer (or D-nummer) for a birth date and gender.

    Args:
        rng: Seeded RNG.
        birth: The person's date of birth; the number's first six digits encode it.
        gender: "M" or "F" -- the individual number's last digit's parity encodes it.
        valid: If True, search for an individual number giving valid mod-11 checks.
            If False, return a number with a deliberately broken final check digit.
        dnummer: If True, offset the day field by 40, as D-numre do.

    Returns:
        Identifier with the 11-digit string and whether it is checksum-valid.
    """
    day = birth.day + 40 if dnummer else birth.day
    ddmmyy = f"{day:02d}{birth.month:02d}{birth.year % 100:02d}"
    century_range = range(0, 500) if birth.year < 2000 else range(500, 1000)
    for _ in range(200):
        individ = rng.choice(list(century_range))
        parity_ok = (individ % 2 == 0) == (gender.upper() == "F")
        if not parity_ok:
            continue
        body = f"{ddmmyy}{individ:03d}"
        checks = _fnr_checksums(body)
        if checks:
            k1, k2 = checks
            if not valid:
                k2 = (k2 + 1) % 10
            return Identifier(f"{body}{k1}{k2}", valid)
    # Extremely unlikely fallback: no individ number in range gave a clean check.
    body = f"{ddmmyy}000"
    return Identifier(f"{body}00", False)


def is_valid_fodselsnummer(value: str) -> bool:
    """Return whether an 11-digit string is a checksum-valid fnr or D-nummer."""
    if not re.fullmatch(r"\d{11}", value):
        return False
    checks = _fnr_checksums(value[:9])
    return checks is not None and checks == (int(value[9]), int(value[10]))


# -- organisasjonsnummer -------------------------------------------------------

_ORG_W = [3, 2, 7, 6, 5, 4, 3, 2]


def org_number(rng: random.Random, valid: bool = True) -> Identifier:
    """Generate a 9-digit Norwegian organisasjonsnummer with a mod-11 check digit."""
    for _ in range(200):
        first_eight = str(rng.choice([8, 9])) + "".join(
            str(rng.randint(0, 9)) for _ in range(7)
        )
        remainder = sum(w * int(d) for w, d in zip(_ORG_W, first_eight)) % 11
        if remainder == 0:
            check = 0
        else:
            check = 11 - remainder
            if check == 10:
                continue
        if not valid:
            check = (check + 1) % 10
        return Identifier(f"{first_eight}{check}", valid)
    return Identifier(first_eight + "0", False)


def is_valid_org_number(value: str) -> bool:
    """Return whether a 9-digit string is a checksum-valid organisasjonsnummer."""
    if not re.fullmatch(r"\d{9}", value):
        return False
    remainder = sum(w * int(d) for w, d in zip(_ORG_W, value[:8])) % 11
    expected = 0 if remainder == 0 else 11 - remainder
    return expected != 10 and expected == int(value[8])


# -- bank account / IBAN -------------------------------------------------------

_KONTO_W = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def bank_account(rng: random.Random, valid: bool = True) -> Identifier:
    """Generate an 11-digit Norwegian bank account number with a mod-11 check digit."""
    for _ in range(200):
        first_ten = "".join(str(rng.randint(0, 9)) for _ in range(10))
        remainder = sum(w * int(d) for w, d in zip(_KONTO_W, first_ten)) % 11
        if remainder == 0:
            check = 0
        else:
            check = 11 - remainder
            if check == 10:
                continue
        if not valid:
            check = (check + 1) % 10
        return Identifier(f"{first_ten}{check}", valid)
    return Identifier(first_ten + "0", False)


def is_valid_bank_account(value: str) -> bool:
    """Return whether an account number is checksum-valid, however it is punctuated.

    Norwegian documents print the number both solid and grouped
    (`1234.56.78903`), and G4 has to validate what the document actually says,
    so the separators are stripped before the mod-11 check rather than the
    grouped form being reported as a broken checksum.
    """
    digits = re.sub(r"[ .\-]", "", value)
    if not re.fullmatch(r"\d{11}", digits):
        return False
    value = digits
    remainder = sum(w * int(d) for w, d in zip(_KONTO_W, value[:10])) % 11
    expected = 0 if remainder == 0 else 11 - remainder
    return expected != 10 and expected == int(value[10])


def _iban_check_digits(country: str, bban: str) -> str:
    """Compute the two IBAN check digits per ISO 7064 mod-97."""
    rearranged = bban + country + "00"
    numeric = "".join(
        str(int(ch, 36)) if ch.isalpha() else ch for ch in rearranged
    )
    remainder = int(numeric) % 97
    check = 98 - remainder
    return f"{check:02d}"


def iban_no(bban_11_digits: str) -> str:
    """Build a Norwegian IBAN from an 11-digit account number (valid or not).

    Args:
        bban_11_digits: The account number to embed as the BBAN.

    Returns:
        A 15-character IBAN string, `NO` + 2 check digits + the BBAN.
    """
    check = _iban_check_digits("NO", bban_11_digits)
    return f"NO{check}{bban_11_digits}"


def is_valid_iban_no(value: str) -> bool:
    """Return whether a Norwegian IBAN is valid: its mod-97 checksum and the embedded account's mod-11.

    Both are part of what makes a Norwegian IBAN valid. Checking only mod-97 made
    an IBAN built on a deliberately invalid account number "valid" (its check
    digits are computed over whatever account it wraps), so G4 saw a declared-
    invalid IBAN that tested valid and discarded the document.
    """
    compact = value.replace(" ", "")
    if not re.fullmatch(r"NO\d{13}", compact) or not is_valid_bank_account(compact[4:]):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        str(int(ch, 36)) if ch.isalpha() else ch for ch in rearranged
    )
    return int(numeric) % 97 == 1


# -- credit card ----------------------------------------------------------------

def credit_card(rng: random.Random, valid: bool = True) -> Identifier:
    """Generate a 16-digit card number (Visa-like prefix) with a Luhn check digit."""
    body = "4" + "".join(str(rng.randint(0, 9)) for _ in range(14))
    check = _luhn_check_digit(body)
    if not valid:
        check = (check + 1) % 10
    return Identifier(f"{body}{check}", valid)


# -- phone / fax ------------------------------------------------------------------

_MOBILE_PREFIXES = ["4", "9"]
_LANDLINE_PREFIXES = ["2", "3", "5", "6", "7"]


def phone_number(rng: random.Random, with_country_code: Optional[bool] = None,
                  mobile: bool = True) -> str:
    """Generate an 8-digit Norwegian phone number with varied spacing/prefix style.

    Args:
        rng: Seeded RNG.
        with_country_code: Force +47 on/off; None picks randomly.
        mobile: Use a mobile prefix (4/9) rather than a landline prefix.

    Returns:
        A phone number string, e.g. "+47 912 34 567" or "23456789".
    """
    prefixes = _MOBILE_PREFIXES if mobile else _LANDLINE_PREFIXES
    digits = rng.choice(prefixes) + "".join(str(rng.randint(0, 9)) for _ in range(7))
    use_cc = rng.random() < 0.4 if with_country_code is None else with_country_code
    style = rng.choice(["none", "pairs", "3-2-3", "4-4"])
    if style == "none":
        formatted = digits
    elif style == "pairs":
        formatted = " ".join(digits[i:i + 2] for i in range(0, 8, 2))
    elif style == "3-2-3":
        formatted = f"{digits[:3]} {digits[3:5]} {digits[5:]}"
    else:
        formatted = f"{digits[:4]} {digits[4:]}"
    return f"+47 {formatted}" if use_cc else formatted


# -- vehicle registration ---------------------------------------------------------

_PLATE_LETTERS = [c for c in "ABCDEFGHJKLMNPRSTUVXYZ"]  # I, O, Q avoided


def vehicle_reg(rng: random.Random) -> str:
    """Generate a Norwegian vehicle registration plate, e.g. `DK 45778`."""
    letters = rng.choice(_PLATE_LETTERS) + rng.choice(_PLATE_LETTERS)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(5))
    return f"{letters} {digits}"


PLATE_RE = re.compile(r"\b[A-Z]{2}\s?\d{5}\b")


# -- firearms licence and fishing-vessel registration -------------------------------
#
# Three registers issue look-alike marks and `docs/ANNOTATION_SPEC.md` B20 says the
# registered object decides the type, not the shape. The generators therefore keep
# the three shape families apart so that a detector trained on the output cannot
# learn the shape as the answer: a road plate is always two letters, a space and
# five digits; a vessel mark always has a hyphen or is one letter plus five digits.
# One firearms shape deliberately overlaps the plate: two letters and five digits
# written solid (`HG12345`, the spec's own example and the form gold and the slice
# use under `våpenkortnummer`/`lisensnummer`). ANNOTATION_SPEC B20 says the label,
# not the shape, decides the type, and a detector only learns that from data where
# the same shape appears under both labels. So about one firearms number in six
# takes this shape, always under an explicit firearms label, and the sampler often
# plants a road plate in the same document so the contrast is local.

_FIREARM_LETTERS = "HWVRJBKLMNPSTU"

FIREARMS_RE = re.compile(
    r"[A-Z]\d{6,7}|[A-Z]{2}\d{5,6}|[A-Z]{2}\d{4}|\d{6,7}"
    r"|(?:19|20)\d{2}-\d{6}|[A-Z]{2}-(?:19|20)\d{2}-\d{4}"
)

_COUNTY_MARKS = ["F", "T", "N", "NT", "ST", "M", "SF", "H", "R", "VA", "AA", "TE"]
_MUNICIPALITY_LETTERS = "ABDEFGHKLMNOPRSTVYØÅ"

VESSEL_RE = re.compile(
    r"[A-ZÆØÅ]{1,2}-\d{1,3}-[A-ZÆØÅ]{1,2}|[A-ZÆØÅ]{1,2}-\d{1,4}|[A-Z]\d{5}"
)

_WEAPONS = [
    ("en jaktrifle", "ein jaktrifle"), ("et haglegevær", "eit haglegevær"),
    ("en rifle", "ein rifle"), ("en hagle", "ei hagle"),
    ("et elggevær", "eit elggevær"), ("en pistol til sportsskyting", "ein pistol til sportsskyting"),
    ("en kombinasjonsrifle", "ein kombinasjonsrifle"), ("en rifle i kaliber .308", "ein rifle i kaliber .308"),
]
_VESSEL_NAMES = [
    "Havbris", "Havets Dronning", "Nordlys", "Sjøstjerna", "Ragnhild", "Svanen",
    "Kystbris", "Havørn", "Fiskaren", "Polarfangst", "Nordkapp", "Liv",
    "Havets Drøm", "Ålesundsbuen", "Sjøfuglen", "Vikingen",
]
_VESSEL_TYPES = [("fiskefartøyet", "fiskefartøyet"), ("fiskebåten", "fiskebåten"),
                 ("kystfiskefartøyet", "kystfiskefartøyet")]


def firearms_license_number(rng: random.Random, max_year: int = 2026) -> str:
    """Generate a firearms card (`våpenkort`) or weapon licence number.

    The gold set prints these as a letter and six or seven digits (`W0987654`,
    `H123456`), two letters and six digits (`WA123456`), a bare six or seven
    digit number (`123456`), a year and six digits (`2018-475963`), a permit ID
    (`HR-2024-4321`), two letters with four digits for a register entry
    (`AB1234`), and, in about one case in six, the plate-shaped `HG12345`, which
    the caller must print under an explicit firearms label (see the block comment
    above and `is_plate_shaped_firearms`).

    Args:
        rng: Seeded RNG.
        max_year: Latest year an issue-year form may carry, so a number is never issued
            after the document that mentions it.
    """
    letter = lambda: rng.choice(_FIREARM_LETTERS)  # noqa: E731
    digits = lambda n: "".join(str(rng.randint(0, 9)) for _ in range(n))  # noqa: E731
    if rng.random() < 0.17:
        return letter() + letter() + str(rng.randint(1, 9)) + digits(4)
    roll = rng.random()
    if roll < 0.22:
        return letter() + str(rng.randint(1, 9)) + digits(5)
    if roll < 0.36:
        return letter() + digits(7)
    if roll < 0.50:
        return letter() + letter() + str(rng.randint(1, 9)) + digits(5)
    if roll < 0.58:
        return letter() + letter() + str(rng.randint(1, 9)) + digits(3)
    if roll < 0.78:
        return str(rng.randint(1, 9)) + digits(5)
    if roll < 0.88:
        return str(rng.randint(1, 9)) + digits(6)
    if roll < 0.96:
        return f"{rng.randint(2005, min(2025, max_year))}-{rng.randint(1, 9)}{digits(5)}"
    return f"{letter()}{rng.choice('RSTK')}-{rng.randint(2015, min(2025, max_year))}-{rng.randint(1000, 9999)}"


def is_plate_shaped_firearms(value: str) -> bool:
    """Return whether a firearms number has the solid two-letters-five-digits shape.

    Such a value reads as a road plate on shape alone, so it must be printed
    under an explicit firearms label (`Våpenkortnummer`, `Lisensnummer`).
    """
    return re.fullmatch(r"[A-Z]{2}\d{5}", value) is not None


def is_valid_firearms_license(value: str) -> bool:
    """Return whether a value is one of the shapes `firearms_license_number` generates.

    The spaced plate form (`DK 45778`) is never a firearms number; the solid
    form (`HG12345`) is, see `is_plate_shaped_firearms`.
    """
    if " " in value:
        return False
    return FIREARMS_RE.fullmatch(value) is not None


def vessel_registration_mark(rng: random.Random) -> str:
    """Generate a Norwegian fishing-vessel registration mark.

    The official form is the county letters, the vessel's number in the county
    and the municipality letters, hyphen-separated (`N-123-BØ`, `M-45-A`). The
    gold documents also carry the shorter county-and-number form (`SF-4278`,
    `ST-476`) and a single letter with five digits (`N54321`), so all three are
    generated, the official one most often.
    """
    roll = rng.random()
    county = rng.choice(_COUNTY_MARKS)
    if roll < 0.45:
        width = 1 if rng.random() < 0.35 else 2
        town = "".join(rng.choice(_MUNICIPALITY_LETTERS) for _ in range(width))
        return f"{county}-{rng.randint(1, 999)}-{town}"
    if roll < 0.90:
        return f"{county}-{rng.randint(1, 9999)}"
    return f"{rng.choice('FTNMHRS')}{rng.randint(10000, 99999)}"


def is_valid_vessel_registration(value: str) -> bool:
    """Return whether a value is one of the shapes `vessel_registration_mark` generates."""
    return VESSEL_RE.fullmatch(value) is not None


def firearm_description(rng: random.Random, form: str) -> str:
    """Return a weapon description for the prompt to print around the number, never part of the span."""
    nb, nn = rng.choice(_WEAPONS)
    return nb if form == "nb" else nn


def vessel_description(rng: random.Random, form: str) -> str:
    """Return the vessel-type word and quoted name the prompt prints around the mark."""
    nb, nn = rng.choice(_VESSEL_TYPES)
    return f"{nb if form == 'nb' else nn} «{rng.choice(_VESSEL_NAMES)}»"


# -- misc Tier A -------------------------------------------------------------------

def email_address(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible email address from a person's name."""
    domain = rng.choice([
        "gmail.com", "hotmail.com", "outlook.com", "online.no", "icloud.com",
        "live.no", "vgsnett.no", "getmail.no",
    ])
    local_style = rng.choice(["dot", "initial", "nodot", "underscore"])
    f, l = first.lower().replace(" ", ""), last.lower().replace(" ", "")
    for src_ch, dst_ch in (("æ", "ae"), ("ø", "o"), ("å", "a")):
        f, l = f.replace(src_ch, dst_ch), l.replace(src_ch, dst_ch)
    local = {"dot": f"{f}.{l}", "initial": f"{f[0]}.{l}", "nodot": f"{f}{l}",
             "underscore": f"{f}_{l}"}[local_style]
    if rng.random() < 0.3:
        local += str(rng.randint(1, 99))
    return f"{local}@{domain}"


def work_email_address(rng: random.Random, first: str, last: str, org_hint: str = "") -> str:
    """Derive a work email address on a Norwegian institutional domain.

    A caseworker's or doctor's address does not sit on gmail.com; a detector
    trained only on consumer domains learns the domain rather than the shape.

    Args:
        rng: Seeded RNG.
        first: Given name, already folded to ASCII.
        last: Surname, already folded to ASCII.
        org_hint: Unused placeholder for a future org-derived domain.

    Returns:
        An email address string.
    """
    domain = rng.choice([
        "nav.no", "politiet.no", "udi.no", "skatteetaten.no", "helse-bergen.no",
        "ous-hf.no", "oslo.kommune.no", "bergen.kommune.no", "trondheim.kommune.no",
        "mattilsynet.no", "uio.no", "ntnu.no", "domstol.no", "forsvaret.no",
    ])
    f, l = first.lower(), last.lower()
    for src_ch, dst_ch in (("æ", "ae"), ("ø", "o"), ("å", "a")):
        f, l = f.replace(src_ch, dst_ch), l.replace(src_ch, dst_ch)
    return f"{f}.{l}@{domain}" if rng.random() < 0.7 else f"{f[0]}{l}@{domain}"


_URL_HOSTS = [
    "nav.no", "politiet.no", "helsenorge.no", "udi.no", "skatteetaten.no",
    "mattilsynet.no", "altinn.no", "lovdata.no", "domstol.no", "regjeringen.no",
]
_URL_SEGMENTS = [
    "sak", "vedtak", "dokument", "skjema", "no/person", "rettskilder", "rundskriv",
    "tjenester", "min-side", "veiledning",
]


def url(rng: random.Random) -> str:
    """Generate a plausible URL on a Norwegian-flavoured domain."""
    host = rng.choice(_URL_HOSTS)
    prefix = rng.choice(["https://www.", "https://", "www."])
    depth = rng.randint(1, 3)
    path = "/".join(rng.choice(_URL_SEGMENTS) for _ in range(depth))
    tail = rng.choice(["", f"/{rng.randint(1000, 99999)}", f"?sak={rng.randint(1000, 99999)}",
                       f"/{rng.choice(['nb', 'nn'])}"])
    return f"{prefix}{host}/{path}{tail}"


def ip_address(rng: random.Random) -> str:
    """Generate an IPv4 address, occasionally an IPv6 one.

    Norwegian consumer ISPs hand out both, and a detector that has only seen
    dotted quads misses the hexadecimal form entirely.
    """
    if rng.random() < 0.15:
        groups = [f"{rng.getrandbits(16):04x}" for _ in range(4)]
        return "2001:" + ":".join(groups) + "::" + f"{rng.getrandbits(16):x}"
    first = rng.choice([10, 51, 62, 77, 78, 84, 88, 128, 158, 193, 213])
    return ".".join([str(first)] + [str(rng.randint(0, 255)) for _ in range(3)])


def username(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible username from a person's name."""
    f, l = first.lower(), last.lower()
    for src_ch, dst_ch in (("æ", "ae"), ("ø", "o"), ("å", "a")):
        f, l = f.replace(src_ch, dst_ch), l.replace(src_ch, dst_ch)
    return rng.choice([
        f"{f}{l}", f"{f}.{l}{rng.randint(1, 99)}", f"{f[0]}{l}{rng.randint(1, 999)}",
        f"{f}_{l}{rng.randint(70, 99)}", f"{l}{f[0]}{rng.randint(1, 99)}",
    ])


_SOCIAL_PLATFORMS = ["Snapchat", "Instagram", "TikTok", "Facebook", "X", "Discord"]


def social_media_handle(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible social-media handle.

    Only the handle itself is returned, with or without the leading `@`: the
    platform name belongs in the prose around it, not inside the labelled span,
    since `SOCIAL_MEDIA` is the account identifier and not the sentence about it.
    """
    handle = username(rng, first, last)
    return "@" + handle if rng.random() < 0.7 else handle


def case_number(rng: random.Random, year_hint: Optional[int] = None, max_year: int = 2026) -> str:
    """Generate a case/reference number in one of the real Norwegian shapes.

    Args:
        rng: Seeded RNG.
        year_hint: Force the year of the year-bearing shapes.
        max_year: Latest year a drawn year may be, so a case number is never from a year
            after the document that cites it. Years before 2018 are not drawn; a
            document dated earlier than 2018 would get 2018.
    """
    year = year_hint or rng.randint(2018, max(2018, min(2026, max_year)))
    style = rng.random()
    if style < 0.45:
        return f"{year}/{rng.randint(1000, 99999)}"
    if style < 0.7:
        return f"{rng.randint(10, 99)}-{rng.randint(100000, 999999)}{rng.choice('ABCDEFGHJKLM')}{rng.choice('ABCDEFGHJKLM')}-{''.join(rng.choice('ABCDEFGHJKLMNPRST') for _ in range(4))}"
    if style < 0.85:
        return f"{year}{rng.randint(100000, 999999)}"
    return f"{rng.randint(10, 24)}-{rng.randint(100, 999)}{rng.randint(100, 999)}"


def passport_number(rng: random.Random) -> str:
    """Generate a Norwegian passport number.

    Norwegian passports issued since 2020 carry an eight-digit number; older
    ones and most foreign passports in a UDI file are two letters plus seven
    digits, so both forms are generated.
    """
    if rng.random() < 0.5:
        return str(rng.randint(10000000, 99999999))
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXYZ") for _ in range(2))
    return f"{letters}{rng.randint(1000000, 9999999)}"


def driver_license_number(rng: random.Random) -> str:
    """Generate an 11-digit Norwegian driving-licence number (no defined checksum).

    Norwegian licences print an 11-digit number in field 5 that is not the
    holder's fødselsnummer and carries no published check digit, so this is
    format realism only. The leading digit is kept out of the 0-3 range a
    DDMMYY-shaped number would start with, so the value does not read as a
    fødselsnummer with a broken checksum.
    """
    return str(rng.randint(4, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))


def identity_card_number(rng: random.Random) -> str:
    """Generate a Norwegian national ID card document number: two letters + 7 digits."""
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXYZ") for _ in range(2))
    return f"{letters}{rng.randint(1000000, 9999999)}"


def visa_number(rng: random.Random) -> str:
    """Generate a Schengen visa sticker number: one letter + 8 digits."""
    return f"{rng.choice('ABCDEFGH')}{rng.randint(10000000, 99999999)}"


def military_id(rng: random.Random) -> str:
    """Generate a Forsvaret service number (`tjenestenummer`).

    Forsvaret's service numbers are plain digit strings of seven or eight
    digits, sometimes written with a slash before a two-digit intake year.
    There is no published check digit.
    """
    body = str(rng.randint(1000000, 99999999))
    if rng.random() < 0.25:
        intake = rng.choice(list(range(85, 100)) + list(range(0, 27)))
        return f"{body}/{intake:02d}"
    return body


def medical_license_number(rng: random.Random) -> str:
    """Generate an HPR number from Helsepersonellregisteret.

    HPR numbers are sequential integers, seven digits for most practitioners
    licensed in the last decades and nine for the newest, with no check digit.
    """
    return str(rng.randint(1000000, 9999999)) if rng.random() < 0.7 else str(
        rng.randint(100000000, 999999999))


def insurance_number(rng: random.Random, max_year: int = 2026) -> str:
    """Generate a private insurance policy or claim number.

    Norwegian insurers print no common format; the shapes here are the ones
    that actually appear on `polisenummer` and `skadenummer` lines (a plain
    eight-to-ten-digit run, a year-prefixed claim reference, or a short
    alphabetic prefix plus digits). No check digit.

    Args:
        rng: Seeded RNG.
        max_year: Latest year the year-prefixed form may carry.
    """
    style = rng.random()
    if style < 0.4:
        return str(rng.randint(10000000, 9999999999))
    if style < 0.7:
        return f"{rng.randint(2018, max(2018, min(2026, max_year)))}-{rng.randint(100000, 999999)}"
    return f"{rng.choice(['POL', 'SKA', 'FP', 'AV'])}{rng.randint(1000000, 9999999)}"


def tax_id(rng: random.Random, valid: bool = True) -> Identifier:
    """Generate a Skatteetaten taxpayer reference in `organisasjonsnummer MVA` form.

    Norway issues no separate personal tax number -- the fødselsnummer is the
    taxpayer identifier -- so the only identifier that is a TAX_ID and not a
    NATIONAL_ID is the VAT registration number, which is the mod-11
    organisasjonsnummer followed by `MVA`. That makes it checksum-checkable, so
    it is generated and validated like one.

    Args:
        rng: Seeded RNG.
        valid: Whether the embedded organisasjonsnummer's check digit is correct.

    Returns:
        Identifier whose value is e.g. `912345678 MVA`.
    """
    base = org_number(rng, valid=valid)
    separator = rng.choice([" ", "", " MVA"[:1]])
    return Identifier(f"{base.value}{separator if separator != ' ' else ' '}MVA", base.valid)


def is_valid_tax_id(value: str) -> bool:
    """Return whether a `NNNNNNNNN MVA` TAX_ID's embedded org number checksum is valid."""
    digits = re.sub(r"[^0-9]", "", value)
    return is_valid_org_number(digits)


def student_id(rng: random.Random) -> str:
    """Generate a Norwegian student number (six or seven digits, no check digit)."""
    return str(rng.randint(100000, 9999999))


def imei(rng: random.Random, valid: bool = True) -> Identifier:
    """Generate a 15-digit IMEI with a Luhn check digit.

    Args:
        rng: Seeded RNG.
        valid: Whether the final Luhn digit is correct.

    Returns:
        Identifier with the 15-digit IMEI.
    """
    body = str(rng.choice([35, 86, 99])) + "".join(str(rng.randint(0, 9)) for _ in range(12))
    check = _luhn_check_digit(body)
    if not valid:
        check = (check + 1) % 10
    return Identifier(f"{body}{check}", valid)


def mac_address(rng: random.Random) -> str:
    """Generate a MAC address in colon-separated hexadecimal."""
    return ":".join(f"{rng.getrandbits(8):02X}" for _ in range(6))


def device_id(rng: random.Random) -> str:
    """Generate a device identifier: a UUID, a MAC address or a serial number.

    IMEI is generated separately because it has a checksum worth validating;
    this returns the checksum-free shapes a police or forensics document uses
    for a laptop, router or phone.
    """
    style = rng.random()
    if style < 0.4:
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))
    if style < 0.7:
        return mac_address(rng)
    prefix = rng.choice(["SN", "S/N ", "DL", "C02", "FVF"])
    return prefix + "".join(rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(9))


def crypto_address(rng: random.Random) -> str:
    """Generate a bitcoin-shaped wallet address with a deliberately invalid checksum.

    Both the legacy base58 and the bech32 shape appear. The checksum is not
    made valid on purpose: see the module docstring's policy note.
    """
    if rng.random() < 0.45:
        body = "".join(rng.choice("023456789acdefghjklmnpqrstuvwxyz") for _ in range(38))
        return f"bc1q{body}"
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    body = "".join(rng.choice(alphabet) for _ in range(33))
    return f"{rng.choice('13')}{body}"


_PASSWORD_WORDS = [
    "Fjell", "Blomst", "Sommer", "Vinter", "Stjerne", "Tiger", "Kaffe", "Hytta",
    "Rognen", "Nordlys", "Skogen", "Bryggen", "Havet", "Fossen",
]


def password_value(rng: random.Random) -> str:
    """Generate a plausible-looking password or passphrase string."""
    style = rng.random()
    word = rng.choice(_PASSWORD_WORDS)
    if style < 0.4:
        return f"{word}{rng.randint(10, 99)}!"
    if style < 0.7:
        return f"{word.lower()}{rng.choice('!?#*')}{rng.randint(1000, 9999)}"
    return f"{word}-{rng.choice(_PASSWORD_WORDS).lower()}-{rng.randint(10, 99)}"


_ANIMAL_NAMES = [
    "Balder", "Mons", "Luna", "Rex", "Tussi", "Sokken", "Nala", "Buster",
    "Snurr", "Freia", "Bella", "Findus", "Truls", "Pelle",
]
_DOG_BREEDS = ["schäfer", "border collie", "labrador", "dachs", "golden retriever",
               "norsk elghund", "blandingshund"]
_LIVESTOCK = [("sau", "sauer"), ("storfe", "storfe"), ("gris", "griser"),
              ("høne", "høner"), ("geit", "geiter"), ("hest", "hester")]


def animal_descriptor(rng: random.Random) -> str:
    """Generate a bare identifying descriptor of the animal a document is about.

    Per the taxonomy, ANIMAL_INFO is the identifying descriptor (species, name,
    count), not the animal's condition; the condition belongs to the
    veterinary prose the model writes around it. Norwegian animal-holding
    documents name a pet and count a herd, so both shapes appear.
    """
    style = rng.random()
    if style < 0.35:
        return f"{rng.choice(['hunden', 'katten', 'hesten'])} {rng.choice(_ANIMAL_NAMES)}"
    if style < 0.55:
        return f"{rng.choice(_ANIMAL_NAMES)}, {rng.choice(_DOG_BREEDS)}"
    if style < 0.8:
        singular, plural = rng.choice(_LIVESTOCK)
        return f"{rng.randint(3, 240)} {plural}"
    singular, plural = rng.choice(_LIVESTOCK)
    # No leading "en": ANNOTATION_SPEC B2 drops a leading determiner from a span,
    # and the span is what the generator labels. The prompt may print the article.
    return f"besetning på {rng.randint(8, 180)} {plural}"


def format_bank_account(rng: random.Random, digits: str) -> str:
    """Format an 11-digit account number the way Norwegian documents print it.

    Roughly half of real documents group the number `1234.56.78903` and the
    rest write it solid, so a detector must handle both.
    """
    if len(digits) != 11 or rng.random() < 0.45:
        return digits
    return f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"


def format_iban(rng: random.Random, compact: str) -> str:
    """Format a Norwegian IBAN either compact or in the printed four-character groups."""
    if rng.random() < 0.5:
        return compact
    return " ".join(compact[i:i + 4] for i in range(0, len(compact), 4))
