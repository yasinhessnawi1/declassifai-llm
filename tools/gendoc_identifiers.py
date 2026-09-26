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
    """Return whether an 11-digit string is a checksum-valid Norwegian account number."""
    if not re.fullmatch(r"\d{11}", value):
        return False
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
    """Return whether a Norwegian IBAN's mod-97 checksum is valid."""
    compact = value.replace(" ", "")
    if not re.fullmatch(r"NO\d{13}", compact):
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


# -- misc Tier A -------------------------------------------------------------------

def email_address(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible email address from a person's name."""
    domain = rng.choice(["gmail.com", "hotmail.com", "outlook.com", "online.no", "nav.no"])
    local_style = rng.choice(["dot", "initial", "nodot"])
    f, l = first.lower().replace(" ", ""), last.lower().replace(" ", "")
    for src, dst in (("æ", "ae"), ("ø", "o"), ("å", "a")):
        f, l = f.replace(src, dst), l.replace(src, dst)
    local = {"dot": f"{f}.{l}", "initial": f"{f[0]}.{l}", "nodot": f"{f}{l}"}[local_style]
    if rng.random() < 0.3:
        local += str(rng.randint(1, 99))
    return f"{local}@{domain}"


def url(rng: random.Random) -> str:
    """Generate a plausible URL on a Norwegian-flavoured domain."""
    domain = rng.choice(["nav.no", "politiet.no", "helsenorge.no", "example.no", "udi.no"])
    path = "/".join(rng.choice(["sak", "vedtak", "dokument", "skjema", "profil"]) for _ in range(rng.randint(1, 2)))
    return f"https://www.{domain}/{path}/{rng.randint(1000, 9999)}"


def ip_address(rng: random.Random) -> str:
    """Generate an IPv4 address."""
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def username(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible username from a person's name."""
    f, l = first.lower(), last.lower()
    style = rng.choice([f"{f}{l}", f"{f}.{l}{rng.randint(1,99)}", f"{f[0]}{l}{rng.randint(1,999)}"])
    return style


def social_media_handle(rng: random.Random, first: str, last: str) -> str:
    """Derive a plausible social-media handle."""
    return "@" + username(rng, first, last)


def case_number(rng: random.Random, year_hint: Optional[int] = None) -> str:
    """Generate a case/reference number, e.g. `2024/12873`."""
    year = year_hint or rng.randint(2018, 2026)
    return f"{year}/{rng.randint(1000, 99999)}"


def passport_number(rng: random.Random) -> str:
    """Generate a Norwegian-format passport number: two letters + 7 digits."""
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXYZ") for _ in range(2))
    return f"{letters}{rng.randint(1000000, 9999999)}"


def driver_license_number(rng: random.Random) -> str:
    """Generate an 11-digit driver's licence number (no defined checksum)."""
    return "".join(str(rng.randint(0, 9)) for _ in range(11))


def identity_card_number(rng: random.Random) -> str:
    """Generate a national ID card document number: two letters + 7 digits."""
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXYZ") for _ in range(2))
    return f"{letters}{rng.randint(1000000, 9999999)}"


def visa_number(rng: random.Random) -> str:
    """Generate a visa sticker number: letter + 8 digits."""
    return f"{rng.choice('ABCDEFGH')}{rng.randint(10000000, 99999999)}"


def military_id(rng: random.Random) -> str:
    """Generate a military ID number."""
    return f"FP-{rng.randint(100000, 999999)}"


def medical_license_number(rng: random.Random) -> str:
    """Generate an HPR (helsepersonellregister) number: 9 digits."""
    return "".join(str(rng.randint(0, 9)) for _ in range(9))


def insurance_number(rng: random.Random) -> str:
    """Generate an insurance policy number."""
    return f"FORS-{rng.randint(100000, 999999)}"


def tax_id(rng: random.Random) -> str:
    """Generate a tax reference number (9 digits, business-side skatte-id)."""
    return "".join(str(rng.randint(0, 9)) for _ in range(9))


def student_id(rng: random.Random) -> str:
    """Generate a student ID number."""
    return str(rng.randint(1000000, 9999999))


def device_id(rng: random.Random) -> str:
    """Generate a UUID4-style device identifier."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def crypto_address(rng: random.Random) -> str:
    """Generate a bitcoin-like address (format only, no real base58 checksum)."""
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    body = "".join(rng.choice(alphabet) for _ in range(33))
    return f"1{body}"


def password_value(rng: random.Random) -> str:
    """Generate a plausible-looking password string."""
    words = ["Fjell", "Blomst", "Sommer", "Vinter", "Stjerne", "Tiger", "Kaffe"]
    return f"{rng.choice(words)}{rng.randint(10,99)}!"
