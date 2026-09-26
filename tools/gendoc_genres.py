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
a dict keyed by genre id with `core` types every document of the genre carries,
weighted optional `values` and `judgement` types drawn per document in numbers
scaled to its length band, plus a `variants` list -- is designed so the full
Section 4 table can be added later by extending `GENRES` without touching the
generator. The judgement weights are the genre's realistic type profile: the
first pilot drew every optional type with p=0.5 and produced a 1,600-character
NAV decision with 14 types, which no caseworker writes.
"""

from __future__ import annotations

from typing import Dict, List

VARIANTS = ["field_header", "prose_letter", "numbered_findings", "table_summary", "minutes"]

GENRES: Dict[str, dict] = {
    "gp_referral": {
        "title_nb": "Henvisning til spesialisthelsetjenesten",
        "title_nn": "Tilvising til spesialisthelsetenesta",
        "variants": VARIANTS,
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "HEALTH"],
        "values": {"PHONE": 0.4, "AGE": 0.3, "GENDER": 0.2,
                   "MEDICAL_LICENSE": 0.3, "CASE_NUMBER": 0.2, "EMAIL": 0.2},
        "judgement": {"MEDICATION": 3.0, "DISABILITY": 1.5, "FAMILY_RELATION": 1.5,
                      "EMPLOYMENT": 1.5, "BEHAVIORAL_PATTERN": 1.0, "GENETIC_DATA": 0.7,
                      "ECONOMIC_STATUS": 0.7, "ACADEMIC_RECORD": 0.4, "AGE_INFO": 0.3,
                      "SEXUAL_ORIENTATION": 0.4, "ETHNICITY": 0.3},
        "foreign_subject_p": 0.1,
        "signatory_roles": [("fastlege", "fastlege"), ("lege", "lege"), ("allmennlege", "allmennlege")],
    },
    "police_report": {
        "title_nb": "Anmeldelse / politirapport",
        "title_nn": "Melding / politirapport",
        "variants": VARIANTS,
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CRIMINAL"],
        "values": {"CASE_NUMBER": 1.5, "ADDRESS": 1.2, "PHONE": 0.4, "LICENSE_PLATE": 0.3, "LOCATION": 0.3,
                   "AGE": 0.3, "DEVICE_ID": 0.1, "IDENTIFIABLE_IMAGE": 0.15},
        "judgement": {"BEHAVIORAL_PATTERN": 3.0, "FAMILY_RELATION": 1.2, "EMPLOYMENT": 1.0,
                      "HEALTH": 1.0, "BIOMETRIC_DATA": 1.0, "ECONOMIC_STATUS": 0.7,
                      "FINANCIAL": 0.6, "POLITICAL": 0.5, "SEXUAL_ORIENTATION": 0.4,
                      "ETHNICITY": 0.4, "RELIGIOUS_BELIEF": 0.3, "IMMIGRATION_STATUS": 0.8,
                      "AGE_INFO": 0.4, "GENETIC_DATA": 0.3},
        "foreign_subject_p": 0.15,
        "minor_subject_p": 0.08,
        "signatory_roles": [("politibetjent", "politibetjent"), ("etterforsker", "etterforskar"),
                            ("politiførstebetjent", "politiførstebetjent")],
    },
    "nav_decision": {
        "title_nb": "Vedtak om ytelse",
        "title_nn": "Vedtak om yting",
        "variants": VARIANTS,
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "ECONOMIC_STATUS"],
        "values": {"CASE_NUMBER": 0.6, "BANK_ACCOUNT": 0.5, "PHONE": 0.3,
                   "MARITAL_STATUS": 0.3, "EMAIL": 0.2},
        "judgement": {"EMPLOYMENT": 2.0, "HEALTH": 2.0, "FINANCIAL": 1.5, "DISABILITY": 1.5,
                      "FAMILY_RELATION": 1.5, "MEDICATION": 0.7, "BEHAVIORAL_PATTERN": 0.7,
                      "TRADE_UNION": 0.3, "IMMIGRATION_STATUS": 0.8, "GENETIC_DATA": 0.2},
        "foreign_subject_p": 0.15,
        "signatory_roles": [("saksbehandler", "sakshandsamar"), ("rådgiver", "rådgjevar")],
    },
    "dismissal_letter": {
        "title_nb": "Oppsigelse / HR-klage",
        "title_nn": "Oppseiing / HR-klage",
        "variants": VARIANTS,
        "core": ["PERSON", "ORGANIZATION", "EMPLOYMENT", "DATE_TIME"],
        "values": {"ADDRESS": 1.5, "NATIONAL_ID": 0.3, "ORG_NUMBER": 0.4, "CASE_NUMBER": 0.2,
                   "PHONE": 0.3, "EMAIL": 0.3, "AGE": 0.2},
        "judgement": {"BEHAVIORAL_PATTERN": 3.0, "HEALTH": 1.2, "TRADE_UNION": 1.0,
                      "CRIMINAL": 0.6, "DISABILITY": 0.6, "ECONOMIC_STATUS": 0.4,
                      "FAMILY_RELATION": 0.5, "RELIGIOUS_BELIEF": 0.3,
                      "SEXUAL_ORIENTATION": 0.3, "POLITICAL": 0.3, "BIOMETRIC_DATA": 0.2},
        "foreign_subject_p": 0.1,
        "subject_age": (19, 67),
        "signatory_roles": [("daglig leder", "dagleg leiar"), ("HR-leder", "HR-leiar"),
                            ("personalsjef", "personalsjef")],
    },
    "udi_decision": {
        "title_nb": "Vedtak om oppholdstillatelse",
        "title_nn": "Vedtak om opphaldsløyve",
        "variants": VARIANTS,
        "core": ["PERSON", "NATIONAL_ID", "NATIONALITY", "DATE_TIME", "IMMIGRATION_STATUS"],
        "values": {"CASE_NUMBER": 1.5, "ADDRESS": 0.6, "PASSPORT": 0.5, "VISA_NUMBER": 0.2, "PHONE": 0.2},
        "judgement": {"FAMILY_RELATION": 2.0, "EMPLOYMENT": 1.5, "ETHNICITY": 1.2,
                      "RELIGIOUS_BELIEF": 1.0, "POLITICAL": 0.7, "SEXUAL_ORIENTATION": 0.6,
                      "BIOMETRIC_DATA": 0.6, "GENETIC_DATA": 0.5, "HEALTH": 0.7,
                      "CRIMINAL": 0.5, "FINANCIAL": 0.5, "ACADEMIC_RECORD": 0.5},
        "foreign_subject_p": 1.0,
        "signatory_roles": [("saksbehandler", "sakshandsamar"), ("seniorrådgiver", "seniorrådgjevar")],
    },
}

# GDPR Art. 9 categories. The pilot's dismissal letter carrying union
# membership, religion and sexual orientation at once read as a checklist,
# not a letter: a real document discloses one such fact when the case turns on
# it. At most `SPECIAL_CATEGORY_CAP` of these per document, beyond whatever the
# genre's core already requires (a UDI decision's IMMIGRATION_STATUS is not
# in this set).
SPECIAL_CATEGORIES = {
    "RELIGIOUS_BELIEF", "SEXUAL_ORIENTATION", "TRADE_UNION", "POLITICAL",
    "ETHNICITY", "GENETIC_DATA", "BIOMETRIC_DATA",
}
SPECIAL_CATEGORY_CAP = 1

# Types that `docs/SYNTHETIC_DATA_SPEC.md` Section 5 says must be forced in
# because the existing corpus is sparse in them, plus the special categories
# the clause bank covers thinly. Forcing is scheduled across the batch (one
# forced type in some documents, chosen where it is plausible for the genre),
# never by stuffing every document.
RARE_TYPES = [
    "SEXUAL_ORIENTATION", "POLITICAL", "ECONOMIC_STATUS", "BEHAVIORAL_PATTERN",
    "GENETIC_DATA", "BIOMETRIC_DATA", "TRADE_UNION", "RELIGIOUS_BELIEF", "ETHNICITY",
]

# Per length band: (planned distinct types, not counting an address's nested
# POSTAL_CODE; optional judgement types). A
# 500-character letter cannot carry what a 4,000-character decision can. The
# judgement count is drawn first; optional values fill whatever the total
# leaves after the core, so a genre with a heavy core gets fewer extras
# rather than more types.
BAND_BUDGET = {
    (400, 800): ((5, 6), (1, 2)),
    (800, 1600): ((6, 7), (2, 3)),
    (1600, 2800): ((7, 8), (2, 3)),
    (2800, 4000): ((8, 9), (3, 4)),
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
