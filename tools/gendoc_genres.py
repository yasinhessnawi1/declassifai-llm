"""The genre catalogue: the five pilot document genres and their structural variants.

`docs/SYNTHETIC_DATA_SPEC.md` Section 4 asks for genre diversity, not just
lexical diversity -- the existing 32k-document corpus fails because it is really
two templates with varied wording. This module encodes, per genre, which types
are plausible so the record sampler can pick a realistic mix (a dismissal letter
should not usually carry a vehicle registration; a police report should), plus
a handful of structural variants (field-header form, prose letter, numbered
findings, table-ish summary, minutes) so the same genre does not always render
the same way.

Only the five pilot genres from `docs/SYNTHETIC_DATA_SPEC.md` Section 4 are
implemented (GP referral, police report, NAV benefit decision, dismissal
letter/HR grievance, UDI residence-permit decision); the structure here --
a dict keyed by genre id with `mandatory`, `optional` and `rare` type lists plus
a `variants` list -- is designed so the full Section 4 table can be added later
by extending `GENRES` without touching the generator.
"""

from __future__ import annotations

from typing import Dict, List

VARIANTS = ["field_header", "prose_letter", "numbered_findings", "table_summary", "minutes"]

GENRES: Dict[str, dict] = {
    "gp_referral": {
        "title_nb": "Henvisning til spesialisthelsetjenesten",
        "title_nn": "Tilvising til spesialisthelsetenesta",
        "variants": VARIANTS,
        "mandatory": ["PERSON", "NATIONAL_ID", "ADDRESS", "POSTAL_CODE", "DATE_TIME", "HEALTH"],
        "optional": [
            "PHONE", "EMAIL", "ORGANIZATION", "EMPLOYMENT", "MEDICATION",
            "DISABILITY", "FAMILY_RELATION", "AGE", "GENDER", "CASE_NUMBER",
            "MEDICAL_LICENSE", "GENETIC_DATA", "ACADEMIC_RECORD",
        ],
        "rare": ["GENETIC_DATA", "BIOMETRIC_DATA", "ETHNICITY", "DISABILITY"],
    },
    "police_report": {
        "title_nb": "Anmeldelse / politirapport",
        "title_nn": "Melding / politirapport",
        "variants": VARIANTS,
        "mandatory": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "CASE_NUMBER", "CRIMINAL"],
        "optional": [
            "PHONE", "LICENSE_PLATE", "ORGANIZATION", "EMPLOYMENT", "GENDER",
            "AGE", "FAMILY_RELATION", "ETHNICITY", "BEHAVIORAL_PATTERN",
            "IDENTIFIABLE_IMAGE", "DEVICE_ID",
        ],
        "rare": ["SEXUAL_ORIENTATION", "ETHNICITY", "POLITICAL", "TRADE_UNION"],
    },
    "nav_decision": {
        "title_nb": "Vedtak om ytelse",
        "title_nn": "Vedtak om yting",
        "variants": VARIANTS,
        "mandatory": ["PERSON", "NATIONAL_ID", "ADDRESS", "POSTAL_CODE", "DATE_TIME", "ECONOMIC_STATUS"],
        "optional": [
            "BANK_ACCOUNT", "EMPLOYMENT", "FINANCIAL", "DISABILITY", "HEALTH",
            "FAMILY_RELATION", "CASE_NUMBER", "PHONE", "EMAIL", "MARITAL_STATUS",
            "IMMIGRATION_STATUS",
        ],
        "rare": ["DISABILITY", "IMMIGRATION_STATUS", "TRADE_UNION", "ETHNICITY"],
    },
    "dismissal_letter": {
        "title_nb": "Oppsigelse / HR-klage",
        "title_nn": "Oppseiing / HR-klage",
        "variants": VARIANTS,
        "mandatory": ["PERSON", "ORGANIZATION", "EMPLOYMENT", "DATE_TIME", "ADDRESS"],
        "optional": [
            "NATIONAL_ID", "CASE_NUMBER", "BEHAVIORAL_PATTERN", "ECONOMIC_STATUS",
            "FAMILY_RELATION", "PHONE", "EMAIL", "AGE", "TRADE_UNION",
            "ORG_NUMBER",
        ],
        "rare": ["TRADE_UNION", "DISABILITY", "SEXUAL_ORIENTATION", "RELIGIOUS_BELIEF"],
    },
    "udi_decision": {
        "title_nb": "Vedtak om oppholdstillatelse",
        "title_nn": "Vedtak om opphaldsløyve",
        "variants": VARIANTS,
        "mandatory": ["PERSON", "NATIONAL_ID", "NATIONALITY", "DATE_TIME", "IMMIGRATION_STATUS", "CASE_NUMBER"],
        "optional": [
            "ADDRESS", "POSTAL_CODE", "FAMILY_RELATION", "PASSPORT",
            "VISA_NUMBER", "EMPLOYMENT", "ETHNICITY", "RELIGIOUS_BELIEF",
        ],
        "rare": ["ETHNICITY", "RELIGIOUS_BELIEF", "POLITICAL", "TRADE_UNION"],
    },
}

FIELD_LABELS: Dict[str, str] = {
    "PERSON": "Navn", "NATIONAL_ID": "Fødselsnummer", "ADDRESS": "Adresse",
    "POSTAL_CODE": "Postnummer", "PHONE": "Telefon", "FAX_NUMBER": "Faks",
    "EMAIL": "E-post", "ORG_NUMBER": "Org.nr.", "CASE_NUMBER": "Saksnummer",
    "DATE_TIME": "Dato", "ORGANIZATION": "Virksomhet", "AGE": "Alder",
    "GENDER": "Kjønn", "NATIONALITY": "Statsborgerskap", "MARITAL_STATUS": "Sivilstand",
    "LICENSE_PLATE": "Kjøretøy, reg.nr.", "BANK_ACCOUNT": "Kontonummer",
    "IBAN": "IBAN", "PASSPORT": "Passnummer", "VISA_NUMBER": "Visumnummer",
    "DRIVER_LICENSE": "Førerkortnummer", "IDENTITY_CARD": "ID-kortnummer",
    "MEDICAL_LICENSE": "HPR-nummer", "MILITARY_ID": "Militær ID",
    "INSURANCE_NUMBER": "Forsikringsnummer", "TAX_ID": "Skatte-ID",
    "STUDENT_ID": "Studentnummer", "URL": "Nettside", "USERNAME": "Brukernavn",
    "SOCIAL_MEDIA": "Sosiale medier", "IP_ADDRESS": "IP-adresse",
    "DEVICE_ID": "Enhets-ID", "CREDIT_CARD": "Kortnummer", "CRYPTO": "Kryptolommebok",
    "PASSWORD": "Passord", "DATE_OF_BIRTH": "Fødselsdato",
}


def genre_names() -> List[str]:
    """Return the list of implemented genre ids."""
    return list(GENRES.keys())
