"""The genre catalogue, the density profiles, and which types each genre may host.

`docs/SYNTHETIC_DATA_SPEC.md` Section 4 asks for genre diversity, not just
lexical diversity -- the existing 32k-document corpus fails because it is
really two templates with varied wording. This module encodes, per genre, which
types are plausible so the record sampler can pick a realistic mix (a dismissal
letter should not carry a vehicle registration; a police report should), plus
structural variants so the same genre does not always render the same way.

Two design decisions are worth stating because both were wrong earlier.

**Coverage is a property of the batch, not of a document.** Pilot v1 drew every
optional type with p=0.5 and produced a 1,600-character NAV decision carrying
14 types; the model had nowhere to put them and fell back on a table whose row
labels named the category. The fix is not a fixed type band -- that is itself a
pattern a detector learns -- but a *distribution* of densities (`PROFILES`)
with length sampled jointly, and a plausibility ceiling that scales with length
and genre (`type_ceiling`). A 6,000-character police case file with 24 types is
realistic; a 1,600-character one with 14 is not.

**Some documents contain no personal data at all.** A detector that only ever
sees documents full of PII learns that everything contains PII. The `pii_free`
profile draws a genre from `PII_FREE_GENRES` (circulars, procedural notices,
statute extracts) and plans nothing, so its label set is empty and the
unplanned-PII sweep becomes the whole gate.

Genres are grouped by the domains of the Section 4 table. Clause-bank entries
carry the five original genre ids in their `genres` list, so each genre here
declares `clause_genres`: the clause-bank genre ids whose clauses are plausible
in it. That lets 30-odd genres share one hand-written clause bank without
re-annotating every entry.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

VARIANTS = ["field_header", "prose_letter", "numbered_findings", "table_summary", "minutes"]

# Density profiles. Each draws its own length band: `docs/SYNTHETIC_DATA_SPEC.md`
# Section 4 asks for ~400 to ~4,000 characters and the case-file profile extends
# that to 7,000, which is where a real multi-party case file sits. `types` is the planned distinct-type target, `bands` the
# length bands the profile draws from, `cast` the number of people beyond the
# data subject and the document's author, and `art9` the Article 9 cap policy
# (see `art9_cap`). Shares sum to 1.0.
PROFILES: Dict[str, dict] = {
    "pii_free": {"share": 0.05, "types": (0, 0), "bands": [(400, 800), (800, 1600)],
                 "cast": (0, 0), "art9": 0, "dates": (0, 0)},
    "minimal": {"share": 0.06, "types": (1, 2), "bands": [(400, 800), (800, 1600)],
                "cast": (0, 0), "art9": 1, "dates": (0, 1)},
    "light": {"share": 0.24, "types": (3, 5), "bands": [(400, 800), (800, 1600)],
              "cast": (0, 1), "art9": 1, "dates": (1, 1)},
    "typical": {"share": 0.30, "types": (6, 9), "bands": [(800, 1600), (1600, 2800)],
                "cast": (0, 2), "art9": 1, "dates": (1, 2)},
    "dense": {"share": 0.20, "types": (10, 18), "bands": [(2400, 3400), (2800, 4000)],
              "cast": (1, 3), "art9": 2, "dates": (2, 4)},
    # The case-file band asks for less than the profile's name suggests on
    # purpose. Measured on Qwen3.5-9B: a 4,000-5,500 band produced an accepted
    # 7,587-character document, and a 5,000-6,500 band produced output that
    # either passed 9,000 characters or ran out of token budget. The model has
    # an effective long-form ceiling around 8,000-9,500 characters and stops
    # obeying a character target above roughly 4,000, so the band is set where
    # the usual 40-70% overshoot lands inside the hard cap.
    "case_file": {"share": 0.15, "types": (18, 28), "bands": [(3600, 4600), (4200, 5200)],
                  "cast": (3, 6), "art9": 3, "dates": (3, 7)},
}

PROFILE_ORDER = ["pii_free", "minimal", "light", "typical", "dense", "case_file"]


def type_ceiling(length_max: int, density_factor: float) -> int:
    """Return the most planned types a document of this length may plausibly carry.

    Pilot v1's unusable document was 14 types in 1,600 characters. The ceiling
    is deliberately generous at the long end -- a case file really does carry
    dozens -- and tight at the short end, where there is no room.

    Args:
        length_max: The upper bound of the document's length band, in characters.
        density_factor: The genre's own tolerance; a police case file or a
            barnevern report carries more parties per page than a GP referral.

    Returns:
        Maximum number of planned distinct types.
    """
    return max(1, int(4 + density_factor * length_max / 320))


def art9_cap(rng: random.Random, profile: str) -> int:
    """Return how many GDPR Art. 9 categories this document may carry.

    A short document discloses at most one such fact, which is what a real
    caseworker writes. A long case file may legitimately touch two or three --
    a psychiatric history and a union dispute in the same dismissal file -- but
    only sometimes: routine co-occurrence would teach the detector that Art. 9
    categories travel in packs.

    Args:
        rng: Seeded RNG.
        profile: Density profile name.

    Returns:
        Maximum Art. 9 categories for the document.
    """
    ceiling = PROFILES[profile]["art9"]
    if ceiling <= 1:
        return ceiling
    if ceiling == 2:
        return 2 if rng.random() < 0.5 else 1
    roll = rng.random()
    return 3 if roll < 0.35 else (2 if roll < 0.75 else 1)


# Weighted age bands per profile name. `docs/PROJECT_SPEC_V2.md` asks for
# measurements rather than impressions; pilot v2's accepted subjects clustered
# at 70-85 because ages were drawn uniformly from (18, 85), which is not what
# any of these document types sees. Working age dominates everywhere except the
# health genres; a dismissal letter cannot name anyone past the retirement age.
AGE_PROFILES: Dict[str, List[Tuple[int, int, float]]] = {
    "working": [(18, 29, 0.22), (30, 44, 0.34), (45, 59, 0.30), (60, 67, 0.14)],
    "adult": [(18, 29, 0.20), (30, 44, 0.30), (45, 59, 0.24), (60, 74, 0.18), (75, 92, 0.08)],
    "health": [(18, 29, 0.12), (30, 44, 0.20), (45, 59, 0.22), (60, 74, 0.28), (75, 92, 0.18)],
    "youth": [(6, 12, 0.34), (13, 15, 0.36), (16, 18, 0.30)],
    "young_adult": [(18, 24, 0.55), (25, 34, 0.31), (35, 49, 0.14)],
    "family": [(24, 34, 0.32), (35, 44, 0.34), (45, 54, 0.24), (55, 64, 0.10)],
}


def sample_age(rng: random.Random, profile: str) -> int:
    """Draw an age from a named weighted band distribution."""
    bands = AGE_PROFILES[profile]
    roll = rng.random() * sum(b[2] for b in bands)
    for lo, hi, weight in bands:
        roll -= weight
        if roll <= 0:
            return rng.randint(lo, hi)
    return rng.randint(bands[-1][0], bands[-1][1])


# Roles a document other than the data subject's own may be about, and the
# person-bound value types each role plausibly brings with it. A case file's
# many distinct values come from here: five people each with their own
# fødselsnummer is five NATIONAL_ID spans under one type.
CAST_ROLES: Dict[str, dict] = {
    "spouse": {"nb": "ektefelle", "nn": "ektefelle",
               "values": ["NATIONAL_ID", "PHONE", "DATE_OF_BIRTH", "ADDRESS", "EMAIL"]},
    "child": {"nb": "barn", "nn": "barn",
              "values": ["NATIONAL_ID", "AGE", "DATE_OF_BIRTH"]},
    "parent": {"nb": "forelder", "nn": "forelder",
               "values": ["NATIONAL_ID", "PHONE", "ADDRESS", "EMAIL"]},
    "guardian": {"nb": "verge", "nn": "verje",
                 "values": ["NATIONAL_ID", "PHONE", "ADDRESS"]},
    "counterparty": {"nb": "motpart", "nn": "motpart",
                     "values": ["NATIONAL_ID", "ADDRESS", "PHONE", "DATE_OF_BIRTH"]},
    "witness": {"nb": "vitne", "nn": "vitne",
                "values": ["PHONE", "ADDRESS", "AGE"]},
    "co_suspect": {"nb": "medmistenkt", "nn": "medmistenkt",
                   "values": ["NATIONAL_ID", "ADDRESS", "LICENSE_PLATE", "PHONE"]},
    "physician": {"nb": "behandlende lege", "nn": "behandlande lege",
                  "values": ["MEDICAL_LICENSE", "PHONE", "EMAIL", "FAX_NUMBER"]},
    "psychologist": {"nb": "psykolog", "nn": "psykolog",
                     "values": ["MEDICAL_LICENSE", "PHONE", "EMAIL"]},
    "veterinarian": {"nb": "veterinær", "nn": "veterinær",
                     "values": ["MEDICAL_LICENSE", "PHONE", "EMAIL"]},
    "caseworker": {"nb": "saksbehandler", "nn": "sakshandsamar",
                   "values": ["PHONE", "EMAIL", "FAX_NUMBER"]},
    "lawyer": {"nb": "advokat", "nn": "advokat",
               "values": ["PHONE", "EMAIL", "ORGANIZATION", "ORG_NUMBER"]},
    "employer_contact": {"nb": "kontaktperson hos arbeidsgiver", "nn": "kontaktperson hos arbeidsgjevar",
                         "values": ["PHONE", "EMAIL", "ORGANIZATION", "ORG_NUMBER"]},
    "landlord": {"nb": "utleier", "nn": "utleigar",
                 "values": ["ADDRESS", "PHONE", "BANK_ACCOUNT", "ORG_NUMBER"]},
    "teacher": {"nb": "kontaktlærer", "nn": "kontaktlærar",
                "values": ["PHONE", "EMAIL"]},
    "officer": {"nb": "tjenestemann", "nn": "tenestemann",
                "values": ["PHONE", "EMAIL"]},
    "creditor_contact": {"nb": "kontaktperson hos kreditor", "nn": "kontaktperson hos kreditor",
                         "values": ["PHONE", "EMAIL", "ORGANIZATION", "ORG_NUMBER", "BANK_ACCOUNT"]},
}

_HEALTH_SIGN = [("fastlege", "fastlege"), ("lege", "lege"), ("overlege", "overlege"),
                ("spesialist", "spesialist")]
_CASEWORKER_SIGN = [("saksbehandler", "sakshandsamar"), ("rådgiver", "rådgjevar"),
                    ("seniorrådgiver", "seniorrådgjevar")]
_POLICE_SIGN = [("politibetjent", "politibetjent"), ("etterforsker", "etterforskar"),
                ("politiførstebetjent", "politiførstebetjent")]

GENRES: Dict[str, dict] = {
    # -- Health ---------------------------------------------------------------
    "gp_referral": {
        "domain": "health",
        "title_nb": "Henvisning til spesialisthelsetjenesten",
        "title_nn": "Tilvising til spesialisthelsetenesta",
        "variants": VARIANTS,
        "clause_genres": ["gp_referral"],
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "HEALTH"],
        "values": {"PHONE": 1.2, "AGE": 0.6, "GENDER": 0.7, "MEDICAL_LICENSE": 1.0,
                   "CASE_NUMBER": 0.4, "EMAIL": 0.7, "MARITAL_STATUS": 0.3,
                   "DATE_OF_BIRTH": 0.4, "ORGANIZATION": 0.4, "INSURANCE_NUMBER": 0.2,
                   "LOCATION": 0.3, "FAX_NUMBER": 0.3},
        "judgement": {"MEDICATION": 3.0, "DISABILITY": 1.5, "FAMILY_RELATION": 1.5,
                      "EMPLOYMENT": 1.5, "BEHAVIORAL_PATTERN": 1.0, "GENETIC_DATA": 0.7,
                      "ECONOMIC_STATUS": 0.7, "ACADEMIC_RECORD": 0.4, "AGE_INFO": 0.3,
                      "SEXUAL_ORIENTATION": 0.4, "ETHNICITY": 0.3},
        "cast_roles": ["physician", "spouse", "child", "caseworker"],
        "age_profile": "health", "density_factor": 0.85,
        "foreign_subject_p": 0.1,
        "signatory_roles": _HEALTH_SIGN,
    },
    "hospital_discharge": {
        "domain": "health",
        "title_nb": "Epikrise / utskrivningsrapport",
        "title_nn": "Epikrise / utskrivingsrapport",
        "variants": VARIANTS,
        "clause_genres": ["gp_referral"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "HEALTH"],
        "values": {"ADDRESS": 1.2, "PHONE": 1.0, "MEDICAL_LICENSE": 1.4, "AGE": 0.6,
                   "GENDER": 0.7, "ORGANIZATION": 0.8, "CASE_NUMBER": 0.5,
                   "DATE_OF_BIRTH": 0.5, "EMAIL": 0.5, "FAX_NUMBER": 0.4,
                   "INSURANCE_NUMBER": 0.3, "LOCATION": 0.3, "MARITAL_STATUS": 0.3},
        "judgement": {"MEDICATION": 3.0, "DISABILITY": 1.6, "FAMILY_RELATION": 1.2,
                      "BEHAVIORAL_PATTERN": 0.9, "GENETIC_DATA": 0.8, "EMPLOYMENT": 0.8,
                      "AGE_INFO": 0.4, "BIOMETRIC_DATA": 0.4, "ECONOMIC_STATUS": 0.4,
                      "RELIGIOUS_BELIEF": 0.3},
        "cast_roles": ["physician", "spouse", "child", "psychologist"],
        "age_profile": "health", "density_factor": 0.95,
        "foreign_subject_p": 0.1,
        "signatory_roles": _HEALTH_SIGN,
    },
    "occupational_health": {
        "domain": "health",
        "title_nb": "Arbeidsmedisinsk vurdering fra bedriftshelsetjenesten",
        "title_nn": "Arbeidsmedisinsk vurdering frå bedriftshelsetenesta",
        "variants": VARIANTS,
        "clause_genres": ["gp_referral", "dismissal_letter"],
        "core": ["PERSON", "DATE_TIME", "EMPLOYMENT", "HEALTH"],
        "values": {"NATIONAL_ID": 1.2, "ORGANIZATION": 1.4, "ADDRESS": 0.8, "PHONE": 1.0,
                   "MEDICAL_LICENSE": 1.2, "ORG_NUMBER": 0.8, "INSURANCE_NUMBER": 1.0,
                   "EMAIL": 0.7, "AGE": 0.5, "GENDER": 0.5, "CASE_NUMBER": 0.5,
                   "DRIVER_LICENSE": 0.5, "FAX_NUMBER": 0.3, "LOCATION": 0.3},
        "judgement": {"DISABILITY": 2.0, "MEDICATION": 1.4, "BEHAVIORAL_PATTERN": 1.0,
                      "ECONOMIC_STATUS": 0.6, "TRADE_UNION": 0.8, "FAMILY_RELATION": 0.6,
                      "AGE_INFO": 0.4, "GENETIC_DATA": 0.4},
        "cast_roles": ["physician", "employer_contact", "caseworker"],
        "age_profile": "working", "density_factor": 0.95,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.12,
        "signatory_roles": [("bedriftslege", "bedriftslege"), ("arbeidsmedisiner", "arbeidsmedisinar")],
    },
    "psychologist_note": {
        "domain": "health",
        "title_nb": "Psykologfaglig journalnotat",
        "title_nn": "Psykologfagleg journalnotat",
        "variants": VARIANTS,
        "clause_genres": ["gp_referral"],
        "core": ["PERSON", "DATE_TIME", "HEALTH"],
        "values": {"NATIONAL_ID": 1.0, "AGE": 0.7, "GENDER": 0.6, "MEDICAL_LICENSE": 1.0,
                   "PHONE": 0.6, "ADDRESS": 0.5, "CASE_NUMBER": 0.4, "MARITAL_STATUS": 0.4,
                   "ORGANIZATION": 0.4, "EMAIL": 0.3, "DATE_OF_BIRTH": 0.3},
        "judgement": {"MEDICATION": 2.0, "BEHAVIORAL_PATTERN": 2.0, "FAMILY_RELATION": 1.6,
                      "DISABILITY": 1.2, "SEXUAL_ORIENTATION": 0.8, "EMPLOYMENT": 0.8,
                      "ECONOMIC_STATUS": 0.6, "RELIGIOUS_BELIEF": 0.5, "AGE_INFO": 0.4,
                      "ACADEMIC_RECORD": 0.4},
        "cast_roles": ["psychologist", "spouse", "parent", "physician"],
        "age_profile": "adult", "density_factor": 0.8,
        "foreign_subject_p": 0.1,
        "signatory_roles": [("psykolog", "psykolog"), ("psykologspesialist", "psykologspesialist")],
    },
    # -- Justice --------------------------------------------------------------
    "police_report": {
        "domain": "justice",
        "title_nb": "Anmeldelse / politirapport",
        "title_nn": "Melding / politirapport",
        "variants": VARIANTS,
        "clause_genres": ["police_report"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CRIMINAL"],
        "values": {"CASE_NUMBER": 1.8, "ADDRESS": 1.4, "PHONE": 1.0, "LICENSE_PLATE": 1.0,
                   "LOCATION": 0.8, "AGE": 0.6, "DEVICE_ID": 0.5, "GENDER": 0.6,
                   "DRIVER_LICENSE": 0.7, "PASSPORT": 0.4, "SOCIAL_MEDIA": 0.6,
                   "IP_ADDRESS": 0.4, "EMAIL": 0.5, "CREDIT_CARD": 0.3, "CRYPTO": 0.2,
                   "DATE_OF_BIRTH": 0.4, "ORGANIZATION": 0.4, "USERNAME": 0.3},
        "judgement": {"BEHAVIORAL_PATTERN": 3.0, "FAMILY_RELATION": 1.2, "EMPLOYMENT": 1.0,
                      "HEALTH": 1.0, "BIOMETRIC_DATA": 1.0, "ECONOMIC_STATUS": 0.7,
                      "FINANCIAL": 0.6, "POLITICAL": 0.4, "IMMIGRATION_STATUS": 0.8,
                      "AGE_INFO": 0.4, "GENETIC_DATA": 0.3, "MEDICATION": 0.5},
        "cast_roles": ["witness", "co_suspect", "counterparty", "officer", "lawyer"],
        "age_profile": "working", "density_factor": 1.35,
        "foreign_subject_p": 0.15,
        "minor_subject_p": 0.08,
        "signatory_roles": _POLICE_SIGN,
    },
    "prosecution_decision": {
        "domain": "justice",
        "title_nb": "Påtaleavgjørelse",
        "title_nn": "Påtaleavgjerd",
        "variants": VARIANTS,
        "clause_genres": ["police_report"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CASE_NUMBER", "CRIMINAL"],
        "values": {"ADDRESS": 1.4, "AGE": 0.6, "GENDER": 0.5, "LICENSE_PLATE": 0.7,
                   "PHONE": 0.6, "DRIVER_LICENSE": 0.6, "LOCATION": 0.6,
                   "DATE_OF_BIRTH": 0.5, "ORGANIZATION": 0.4, "FAX_NUMBER": 0.4,
                   "PASSPORT": 0.3, "ORG_NUMBER": 0.3},
        "judgement": {"BEHAVIORAL_PATTERN": 2.0, "ECONOMIC_STATUS": 1.0, "HEALTH": 0.9,
                      "FAMILY_RELATION": 0.9, "EMPLOYMENT": 0.9, "FINANCIAL": 0.8,
                      "IMMIGRATION_STATUS": 0.6, "MEDICATION": 0.5, "AGE_INFO": 0.4,
                      "DISABILITY": 0.4},
        "cast_roles": ["counterparty", "lawyer", "witness", "officer"],
        "age_profile": "working", "density_factor": 1.15,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("politiadvokat", "politiadvokat"), ("statsadvokat", "statsadvokat")],
    },
    "court_judgment": {
        "domain": "justice",
        "title_nb": "Sammendrag av dom",
        "title_nn": "Samandrag av dom",
        "variants": VARIANTS,
        "clause_genres": ["police_report", "dismissal_letter"],
        "core": ["PERSON", "DATE_TIME", "CASE_NUMBER"],
        "values": {"NATIONAL_ID": 1.2, "ADDRESS": 1.0, "AGE": 0.7, "GENDER": 0.5,
                   "ORGANIZATION": 0.8, "LOCATION": 0.7, "ORG_NUMBER": 0.5,
                   "LICENSE_PLATE": 0.5, "DRIVER_LICENSE": 0.4, "FAX_NUMBER": 0.4,
                   "DATE_OF_BIRTH": 0.4, "BANK_ACCOUNT": 0.3, "PHONE": 0.3},
        "judgement": {"CRIMINAL": 2.4, "BEHAVIORAL_PATTERN": 1.6, "FINANCIAL": 1.2,
                      "ECONOMIC_STATUS": 1.0, "FAMILY_RELATION": 1.0, "EMPLOYMENT": 1.0,
                      "HEALTH": 0.8, "TRADE_UNION": 0.4, "AGE_INFO": 0.4,
                      "IMMIGRATION_STATUS": 0.4, "DISABILITY": 0.4},
        "cast_roles": ["counterparty", "lawyer", "witness"],
        "age_profile": "adult", "density_factor": 1.25,
        "foreign_subject_p": 0.12,
        "signatory_roles": [("tingrettsdommer", "tingrettsdommar"), ("dommerfullmektig", "dommarfullmektig")],
    },
    "restraining_order": {
        "domain": "justice",
        "title_nb": "Vedtak om besøksforbud",
        "title_nn": "Vedtak om besøksforbod",
        "variants": VARIANTS,
        "clause_genres": ["police_report"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CASE_NUMBER", "BEHAVIORAL_PATTERN"],
        "values": {"ADDRESS": 1.6, "PHONE": 0.8, "AGE": 0.5, "GENDER": 0.5,
                   "LOCATION": 0.8, "DATE_OF_BIRTH": 0.4, "SOCIAL_MEDIA": 0.5,
                   "LICENSE_PLATE": 0.4, "EMAIL": 0.3, "USERNAME": 0.3},
        "judgement": {"FAMILY_RELATION": 2.0, "CRIMINAL": 1.8, "HEALTH": 0.8,
                      "EMPLOYMENT": 0.6, "ECONOMIC_STATUS": 0.5, "MEDICATION": 0.5,
                      "IMMIGRATION_STATUS": 0.4, "AGE_INFO": 0.3},
        "cast_roles": ["counterparty", "child", "witness", "lawyer"],
        "age_profile": "working", "density_factor": 1.2,
        "foreign_subject_p": 0.12,
        "signatory_roles": [("politiadvokat", "politiadvokat")] + _POLICE_SIGN,
    },
    "digital_forensics_report": {
        "domain": "justice",
        "title_nb": "Rapport om undersøkelse av elektroniske spor",
        "title_nn": "Rapport om undersøking av elektroniske spor",
        "variants": VARIANTS,
        "clause_genres": ["police_report"],
        "core": ["PERSON", "DATE_TIME", "CASE_NUMBER", "DEVICE_ID"],
        "values": {"NATIONAL_ID": 1.0, "IP_ADDRESS": 1.8, "USERNAME": 1.6,
                   "SOCIAL_MEDIA": 1.4, "EMAIL": 1.2, "URL": 1.4, "PASSWORD": 1.0,
                   "PHONE": 1.0, "ADDRESS": 0.7, "CRYPTO": 0.7, "CREDIT_CARD": 0.5,
                   "AGE": 0.4, "GENDER": 0.4, "LOCATION": 0.4, "ORGANIZATION": 0.4},
        "judgement": {"CRIMINAL": 2.2, "BEHAVIORAL_PATTERN": 1.6, "FINANCIAL": 0.8,
                      "SEXUAL_ORIENTATION": 0.4, "POLITICAL": 0.5, "ECONOMIC_STATUS": 0.5,
                      "HEALTH": 0.4, "FAMILY_RELATION": 0.5},
        "cast_roles": ["co_suspect", "officer", "witness"],
        "age_profile": "working", "density_factor": 1.4,
        "foreign_subject_p": 0.1,
        "signatory_roles": [("dataetterforsker", "dataetterforskar")] + _POLICE_SIGN,
    },
    # -- Welfare --------------------------------------------------------------
    "nav_decision": {
        "domain": "welfare",
        "title_nb": "Vedtak om ytelse",
        "title_nn": "Vedtak om yting",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "ECONOMIC_STATUS"],
        "values": {"CASE_NUMBER": 1.2, "BANK_ACCOUNT": 1.4, "PHONE": 0.9,
                   "MARITAL_STATUS": 0.8, "EMAIL": 0.6, "AGE": 0.5, "GENDER": 0.6,
                   "INSURANCE_NUMBER": 0.6, "ORGANIZATION": 0.5, "ORG_NUMBER": 0.3,
                   "DATE_OF_BIRTH": 0.4, "LOCATION": 0.3, "FAX_NUMBER": 0.3,
                   "IBAN": 0.2, "TAX_ID": 0.2},
        "judgement": {"EMPLOYMENT": 2.0, "HEALTH": 2.0, "FINANCIAL": 1.5, "DISABILITY": 1.5,
                      "FAMILY_RELATION": 1.5, "MEDICATION": 0.7, "BEHAVIORAL_PATTERN": 0.7,
                      "TRADE_UNION": 0.3, "IMMIGRATION_STATUS": 0.8, "GENETIC_DATA": 0.2,
                      "AGE_INFO": 0.4, "ACADEMIC_RECORD": 0.3},
        "cast_roles": ["caseworker", "spouse", "child", "physician", "employer_contact"],
        "age_profile": "adult", "density_factor": 1.0,
        "foreign_subject_p": 0.15,
        "signatory_roles": _CASEWORKER_SIGN,
    },
    "sickness_followup": {
        "domain": "welfare",
        "title_nb": "Oppfølgingsplan for sykmeldt arbeidstaker",
        "title_nn": "Oppfølgingsplan for sjukmeld arbeidstakar",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "gp_referral", "dismissal_letter"],
        "core": ["PERSON", "DATE_TIME", "HEALTH", "EMPLOYMENT"],
        "values": {"NATIONAL_ID": 1.2, "ORGANIZATION": 1.4, "PHONE": 1.0, "EMAIL": 0.8,
                   "MEDICAL_LICENSE": 0.9, "CASE_NUMBER": 0.7, "ADDRESS": 0.7,
                   "ORG_NUMBER": 0.6, "INSURANCE_NUMBER": 0.7, "AGE": 0.4,
                   "GENDER": 0.4, "BANK_ACCOUNT": 0.3, "LOCATION": 0.3},
        "judgement": {"DISABILITY": 1.8, "MEDICATION": 1.4, "ECONOMIC_STATUS": 1.0,
                      "FAMILY_RELATION": 0.9, "BEHAVIORAL_PATTERN": 0.8, "TRADE_UNION": 0.7,
                      "FINANCIAL": 0.6, "AGE_INFO": 0.3, "ACADEMIC_RECORD": 0.3},
        "cast_roles": ["caseworker", "physician", "employer_contact", "spouse"],
        "age_profile": "working", "density_factor": 1.0,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.12,
        "signatory_roles": _CASEWORKER_SIGN + [("veileder", "rettleiar")],
    },
    "debt_counselling": {
        "domain": "welfare",
        "title_nb": "Journalnotat fra økonomisk rådgivning",
        "title_nn": "Journalnotat frå økonomisk rådgjeving",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "ECONOMIC_STATUS"],
        "values": {"BANK_ACCOUNT": 1.8, "ADDRESS": 1.2, "PHONE": 1.0, "CASE_NUMBER": 0.8,
                   "IBAN": 0.8, "CREDIT_CARD": 0.7, "TAX_ID": 0.6, "EMAIL": 0.6,
                   "MARITAL_STATUS": 0.6, "ORGANIZATION": 0.8, "ORG_NUMBER": 0.5,
                   "AGE": 0.4, "GENDER": 0.4, "CRYPTO": 0.3, "LOCATION": 0.3,
                   "INSURANCE_NUMBER": 0.3},
        "judgement": {"FINANCIAL": 2.6, "EMPLOYMENT": 1.4, "FAMILY_RELATION": 1.2,
                      "HEALTH": 1.0, "BEHAVIORAL_PATTERN": 0.9, "DISABILITY": 0.7,
                      "MEDICATION": 0.4, "AGE_INFO": 0.3, "TRADE_UNION": 0.3},
        "cast_roles": ["caseworker", "spouse", "creditor_contact", "child"],
        "age_profile": "working", "density_factor": 1.15,
        "foreign_subject_p": 0.12,
        "signatory_roles": [("økonomisk rådgiver", "økonomisk rådgjevar")] + _CASEWORKER_SIGN,
    },
    # -- Tax and finance ------------------------------------------------------
    "tax_assessment": {
        "domain": "tax",
        "title_nb": "Vedtak om endring av skattefastsetting",
        "title_nn": "Vedtak om endring av skattefastsetjing",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "FINANCIAL"],
        "values": {"CASE_NUMBER": 1.2, "BANK_ACCOUNT": 1.4, "TAX_ID": 1.6,
                   "ORG_NUMBER": 1.0, "ORGANIZATION": 0.9, "IBAN": 0.8, "PHONE": 0.6,
                   "EMAIL": 0.5, "FAX_NUMBER": 0.6, "MARITAL_STATUS": 0.4,
                   "AGE": 0.3, "GENDER": 0.3, "DATE_OF_BIRTH": 0.3, "LOCATION": 0.3,
                   "CREDIT_CARD": 0.2, "CRYPTO": 0.3},
        "judgement": {"ECONOMIC_STATUS": 2.0, "EMPLOYMENT": 1.6, "FAMILY_RELATION": 0.9,
                      "BEHAVIORAL_PATTERN": 0.6, "CRIMINAL": 0.5, "HEALTH": 0.4,
                      "IMMIGRATION_STATUS": 0.4, "AGE_INFO": 0.3},
        "cast_roles": ["caseworker", "spouse", "lawyer", "employer_contact"],
        "age_profile": "working", "density_factor": 1.1,
        "foreign_subject_p": 0.12,
        "signatory_roles": [("skattejurist", "skattejurist"), ("seksjonsleder", "seksjonsleiar")]
                           + _CASEWORKER_SIGN,
    },
    "inkasso_notice": {
        "domain": "tax",
        "title_nb": "Inkassovarsel",
        "title_nn": "Inkassovarsel",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "ADDRESS", "DATE_TIME", "CASE_NUMBER", "FINANCIAL"],
        "values": {"NATIONAL_ID": 1.0, "BANK_ACCOUNT": 1.8, "ORGANIZATION": 1.4,
                   "ORG_NUMBER": 1.0, "IBAN": 0.9, "PHONE": 0.8, "EMAIL": 0.7,
                   "TAX_ID": 0.5, "CREDIT_CARD": 0.5, "FAX_NUMBER": 0.5,
                   "AGE": 0.2, "DATE_OF_BIRTH": 0.4, "LOCATION": 0.3, "URL": 0.4},
        "judgement": {"ECONOMIC_STATUS": 2.0, "EMPLOYMENT": 0.9, "HEALTH": 0.5,
                      "FAMILY_RELATION": 0.6, "BEHAVIORAL_PATTERN": 0.4, "DISABILITY": 0.4,
                      "AGE_INFO": 0.3},
        "cast_roles": ["creditor_contact", "lawyer", "spouse"],
        "age_profile": "working", "density_factor": 1.05,
        "foreign_subject_p": 0.12,
        "signatory_roles": [("inkassomedarbeider", "inkassomedarbeidar"),
                            ("autorisert inkassobevillingshaver", "autorisert inkassoløyvehavar")],
    },
    "bank_aml": {
        "domain": "tax",
        "title_nb": "Forespørsel om kundeopplysninger etter hvitvaskingsloven",
        "title_nn": "Førespurnad om kundeopplysningar etter kvitvaskingslova",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "police_report"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "BANK_ACCOUNT"],
        "values": {"CASE_NUMBER": 1.2, "IBAN": 1.6, "ADDRESS": 1.2, "CREDIT_CARD": 1.2,
                   "CRYPTO": 1.2, "TAX_ID": 1.0, "ORG_NUMBER": 0.9, "ORGANIZATION": 0.9,
                   "IDENTITY_CARD": 1.0, "PASSPORT": 0.7, "PHONE": 0.7, "EMAIL": 0.6,
                   "IP_ADDRESS": 0.8, "DEVICE_ID": 0.5, "FAX_NUMBER": 0.4,
                   "LOCATION": 0.3, "NATIONALITY": 0.6, "GENDER": 0.3},
        "judgement": {"FINANCIAL": 2.4, "ECONOMIC_STATUS": 1.4, "EMPLOYMENT": 1.2,
                      "CRIMINAL": 1.0, "IMMIGRATION_STATUS": 0.7, "BEHAVIORAL_PATTERN": 0.7,
                      "FAMILY_RELATION": 0.7, "POLITICAL": 0.4},
        "cast_roles": ["counterparty", "lawyer", "creditor_contact", "officer"],
        "age_profile": "working", "density_factor": 1.3,
        "foreign_subject_p": 0.2,
        "signatory_roles": [("compliance-ansvarlig", "compliance-ansvarleg"),
                            ("hvitvaskingsansvarlig", "kvitvaskingsansvarleg")],
    },
    # -- Education ------------------------------------------------------------
    "ppt_assessment": {
        "domain": "education",
        "title_nb": "Sakkyndig vurdering fra PP-tjenesten",
        "title_nn": "Sakkunnig vurdering frå PP-tenesta",
        "variants": VARIANTS,
        "clause_genres": ["gp_referral"],
        "core": ["PERSON", "DATE_TIME", "ACADEMIC_RECORD", "DISABILITY"],
        "values": {"NATIONAL_ID": 1.2, "AGE": 1.0, "GENDER": 0.7, "ADDRESS": 0.8,
                   "ORGANIZATION": 1.0, "STUDENT_ID": 1.2, "PHONE": 0.7, "EMAIL": 0.6,
                   "CASE_NUMBER": 0.7, "DATE_OF_BIRTH": 0.6, "LOCATION": 0.3,
                   "MEDICAL_LICENSE": 0.4},
        "judgement": {"HEALTH": 1.8, "FAMILY_RELATION": 1.6, "BEHAVIORAL_PATTERN": 1.4,
                      "MEDICATION": 0.8, "ECONOMIC_STATUS": 0.5, "AGE_INFO": 0.6,
                      "GENETIC_DATA": 0.4, "ETHNICITY": 0.3, "IMMIGRATION_STATUS": 0.3},
        "cast_roles": ["parent", "guardian", "teacher", "psychologist"],
        "age_profile": "youth", "density_factor": 0.95,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("PP-rådgiver", "PP-rådgjevar"), ("pedagogisk-psykologisk rådgiver",
                                                              "pedagogisk-psykologisk rådgjevar")],
    },
    "school_incident": {
        "domain": "education",
        "title_nb": "Avviksmelding om hendelse i skoletiden",
        "title_nn": "Avviksmelding om hending i skuletida",
        "variants": VARIANTS,
        "clause_genres": ["police_report", "gp_referral"],
        "core": ["PERSON", "DATE_TIME", "ORGANIZATION", "BEHAVIORAL_PATTERN"],
        "values": {"AGE": 1.2, "STUDENT_ID": 1.4, "NATIONAL_ID": 0.8, "GENDER": 0.7,
                   "PHONE": 0.9, "EMAIL": 0.8, "ADDRESS": 0.6, "SOCIAL_MEDIA": 1.2,
                   "USERNAME": 1.0, "DEVICE_ID": 0.8, "URL": 0.8, "IP_ADDRESS": 0.6,
                   "PASSWORD": 0.5, "CASE_NUMBER": 0.6, "LOCATION": 0.3},
        "judgement": {"HEALTH": 1.2, "FAMILY_RELATION": 1.4, "CRIMINAL": 0.8,
                      "DISABILITY": 0.8, "ACADEMIC_RECORD": 1.2, "AGE_INFO": 0.6,
                      "MEDICATION": 0.5, "ECONOMIC_STATUS": 0.4, "RELIGIOUS_BELIEF": 0.4},
        "cast_roles": ["parent", "teacher", "guardian", "witness"],
        "age_profile": "youth", "density_factor": 1.2,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("rektor", "rektor"), ("avdelingsleder", "avdelingsleiar"),
                            ("kontaktlærer", "kontaktlærar")],
    },
    "admission_decision": {
        "domain": "education",
        "title_nb": "Vedtak om opptak til studieprogram",
        "title_nn": "Vedtak om opptak til studieprogram",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "gp_referral"],
        "core": ["PERSON", "DATE_TIME", "ACADEMIC_RECORD"],
        "values": {"NATIONAL_ID": 1.2, "STUDENT_ID": 1.8, "ADDRESS": 1.2, "EMAIL": 1.2,
                   "PHONE": 0.9, "CASE_NUMBER": 0.8, "ORGANIZATION": 1.0, "AGE": 0.5,
                   "GENDER": 0.4, "URL": 0.7, "USERNAME": 0.6, "DATE_OF_BIRTH": 0.5,
                   "NATIONALITY": 0.6, "LOCATION": 0.3, "BANK_ACCOUNT": 0.3},
        "judgement": {"DISABILITY": 1.2, "HEALTH": 0.8, "EMPLOYMENT": 0.8,
                      "ECONOMIC_STATUS": 0.6, "IMMIGRATION_STATUS": 0.8,
                      "FAMILY_RELATION": 0.6, "AGE_INFO": 0.3, "ETHNICITY": 0.2},
        "cast_roles": ["caseworker", "parent"],
        "age_profile": "young_adult", "density_factor": 1.0,
        "foreign_subject_p": 0.2,
        "signatory_roles": [("opptaksleder", "opptaksleiar"), ("studiekonsulent", "studiekonsulent")],
    },
    # -- Child welfare --------------------------------------------------------
    "barnevern_concern": {
        "domain": "child_welfare",
        "title_nb": "Bekymringsmelding til barneverntjenesten",
        "title_nn": "Uromelding til barnevernstenesta",
        "variants": VARIANTS,
        "clause_genres": ["police_report", "nav_decision", "gp_referral"],
        "core": ["PERSON", "DATE_TIME", "FAMILY_RELATION", "BEHAVIORAL_PATTERN"],
        "values": {"NATIONAL_ID": 1.4, "AGE": 1.2, "ADDRESS": 1.2, "GENDER": 0.7,
                   "PHONE": 1.0, "CASE_NUMBER": 1.0, "ORGANIZATION": 0.7,
                   "EMAIL": 0.6, "DATE_OF_BIRTH": 0.6, "STUDENT_ID": 0.5,
                   "SOCIAL_MEDIA": 0.4, "LOCATION": 0.4, "MARITAL_STATUS": 0.5},
        "judgement": {"HEALTH": 1.6, "ECONOMIC_STATUS": 1.4, "MEDICATION": 0.9,
                      "CRIMINAL": 1.0, "DISABILITY": 0.8, "ACADEMIC_RECORD": 0.8,
                      "AGE_INFO": 0.6, "IMMIGRATION_STATUS": 0.6, "RELIGIOUS_BELIEF": 0.4,
                      "EMPLOYMENT": 0.8},
        "cast_roles": ["child", "parent", "guardian", "teacher", "caseworker", "physician"],
        "age_profile": "family", "density_factor": 1.3,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("barnevernkonsulent", "barnevernkonsulent")] + _CASEWORKER_SIGN,
    },
    "barnevern_care_plan": {
        "domain": "child_welfare",
        "title_nb": "Gjennomgang av tiltaksplan",
        "title_nn": "Gjennomgang av tiltaksplan",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "gp_referral", "police_report"],
        "core": ["PERSON", "DATE_TIME", "CASE_NUMBER", "FAMILY_RELATION"],
        "values": {"NATIONAL_ID": 1.2, "AGE": 1.0, "ADDRESS": 1.0, "PHONE": 0.9,
                   "GENDER": 0.6, "ORGANIZATION": 0.8, "EMAIL": 0.6, "STUDENT_ID": 0.5,
                   "DATE_OF_BIRTH": 0.5, "MARITAL_STATUS": 0.5, "BANK_ACCOUNT": 0.3,
                   "LOCATION": 0.3},
        "judgement": {"BEHAVIORAL_PATTERN": 1.6, "HEALTH": 1.4, "ECONOMIC_STATUS": 1.2,
                      "ACADEMIC_RECORD": 1.0, "DISABILITY": 0.8, "MEDICATION": 0.7,
                      "EMPLOYMENT": 0.8, "AGE_INFO": 0.5, "IMMIGRATION_STATUS": 0.4,
                      "RELIGIOUS_BELIEF": 0.3},
        "cast_roles": ["child", "parent", "guardian", "caseworker", "teacher", "psychologist"],
        "age_profile": "family", "density_factor": 1.25,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("barnevernkonsulent", "barnevernkonsulent")] + _CASEWORKER_SIGN,
    },
    # -- Employment -----------------------------------------------------------
    "employment_contract": {
        "domain": "employment",
        "title_nb": "Arbeidsavtale",
        "title_nn": "Arbeidsavtale",
        "variants": VARIANTS,
        "clause_genres": ["dismissal_letter"],
        "core": ["PERSON", "ORGANIZATION", "DATE_TIME", "EMPLOYMENT"],
        "values": {"NATIONAL_ID": 1.4, "ADDRESS": 1.6, "ORG_NUMBER": 1.4,
                   "BANK_ACCOUNT": 1.4, "PHONE": 1.0, "EMAIL": 1.0, "TAX_ID": 0.7,
                   "AGE": 0.3, "GENDER": 0.3, "DATE_OF_BIRTH": 0.5, "LOCATION": 0.4,
                   "INSURANCE_NUMBER": 0.6, "CASE_NUMBER": 0.3, "IBAN": 0.4,
                   "URL": 0.4, "USERNAME": 0.3},
        "judgement": {"TRADE_UNION": 1.2, "FAMILY_RELATION": 0.5, "ACADEMIC_RECORD": 0.8,
                      "ECONOMIC_STATUS": 0.6, "HEALTH": 0.4, "DISABILITY": 0.4,
                      "IMMIGRATION_STATUS": 0.6},
        "cast_roles": ["employer_contact", "lawyer"],
        "age_profile": "working", "density_factor": 1.1,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.15,
        "signatory_roles": [("daglig leder", "dagleg leiar"), ("HR-leder", "HR-leiar"),
                            ("personalsjef", "personalsjef")],
    },
    "dismissal_letter": {
        "domain": "employment",
        "title_nb": "Oppsigelse / HR-klage",
        "title_nn": "Oppseiing / HR-klage",
        "variants": VARIANTS,
        "clause_genres": ["dismissal_letter"],
        "core": ["PERSON", "ORGANIZATION", "EMPLOYMENT", "DATE_TIME"],
        "values": {"ADDRESS": 1.5, "NATIONAL_ID": 0.7, "ORG_NUMBER": 0.8, "CASE_NUMBER": 0.5,
                   "PHONE": 0.8, "EMAIL": 0.8, "AGE": 0.4, "GENDER": 0.4,
                   "BANK_ACCOUNT": 0.4, "DATE_OF_BIRTH": 0.3, "LOCATION": 0.3,
                   "MARITAL_STATUS": 0.2, "INSURANCE_NUMBER": 0.3},
        "judgement": {"BEHAVIORAL_PATTERN": 3.0, "HEALTH": 1.2, "TRADE_UNION": 1.0,
                      "CRIMINAL": 0.6, "DISABILITY": 0.6, "ECONOMIC_STATUS": 0.4,
                      "FAMILY_RELATION": 0.5, "RELIGIOUS_BELIEF": 0.3,
                      "SEXUAL_ORIENTATION": 0.3, "POLITICAL": 0.3, "BIOMETRIC_DATA": 0.2},
        "cast_roles": ["employer_contact", "lawyer", "witness"],
        "age_profile": "working", "density_factor": 1.0,
        "subject_age": (19, 66),
        "foreign_subject_p": 0.1,
        "signatory_roles": [("daglig leder", "dagleg leiar"), ("HR-leder", "HR-leiar"),
                            ("personalsjef", "personalsjef")],
    },
    "whistleblowing_report": {
        "domain": "employment",
        "title_nb": "Varsel om kritikkverdige forhold",
        "title_nn": "Varsel om kritikkverdige forhold",
        "variants": VARIANTS,
        "clause_genres": ["dismissal_letter", "police_report"],
        "core": ["PERSON", "ORGANIZATION", "DATE_TIME", "BEHAVIORAL_PATTERN"],
        "values": {"CASE_NUMBER": 1.2, "EMAIL": 1.4, "PHONE": 1.0, "URL": 1.2,
                   "IP_ADDRESS": 1.0, "USERNAME": 1.0, "DEVICE_ID": 0.8,
                   "PASSWORD": 0.7, "SOCIAL_MEDIA": 0.8, "ORG_NUMBER": 0.8,
                   "NATIONAL_ID": 0.6, "ADDRESS": 0.7, "BANK_ACCOUNT": 0.6,
                   "AGE": 0.2, "GENDER": 0.3, "LOCATION": 0.3, "IBAN": 0.3},
        "judgement": {"EMPLOYMENT": 1.8, "CRIMINAL": 1.4, "FINANCIAL": 1.2,
                      "TRADE_UNION": 0.8, "ECONOMIC_STATUS": 0.7, "HEALTH": 0.6,
                      "POLITICAL": 0.5, "FAMILY_RELATION": 0.5},
        "cast_roles": ["employer_contact", "witness", "counterparty", "lawyer"],
        "age_profile": "working", "density_factor": 1.25,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.1,
        "signatory_roles": [("varslingsombud", "varslingsombod"), ("HR-leder", "HR-leiar"),
                            ("internrevisor", "internrevisor")],
    },
    "hr_grievance": {
        "domain": "employment",
        "title_nb": "Referat fra personalsak",
        "title_nn": "Referat frå personalsak",
        "variants": VARIANTS,
        "clause_genres": ["dismissal_letter"],
        "core": ["PERSON", "ORGANIZATION", "DATE_TIME", "EMPLOYMENT"],
        "values": {"CASE_NUMBER": 1.0, "PHONE": 0.8, "EMAIL": 0.9, "ADDRESS": 0.7,
                   "ORG_NUMBER": 0.6, "NATIONAL_ID": 0.5, "AGE": 0.3, "GENDER": 0.4,
                   "DATE_OF_BIRTH": 0.2, "LOCATION": 0.3, "INSURANCE_NUMBER": 0.2},
        "judgement": {"BEHAVIORAL_PATTERN": 2.4, "TRADE_UNION": 1.4, "HEALTH": 1.2,
                      "DISABILITY": 0.8, "FAMILY_RELATION": 0.6, "ECONOMIC_STATUS": 0.5,
                      "RELIGIOUS_BELIEF": 0.4, "SEXUAL_ORIENTATION": 0.4, "POLITICAL": 0.4,
                      "MEDICATION": 0.4, "CRIMINAL": 0.4},
        "cast_roles": ["employer_contact", "witness", "counterparty"],
        "age_profile": "working", "density_factor": 1.1,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.12,
        "signatory_roles": [("HR-rådgiver", "HR-rådgjevar"), ("personalsjef", "personalsjef"),
                            ("tillitsvalgt", "tillitsvald")],
    },
    # -- Housing --------------------------------------------------------------
    "housing_application": {
        "domain": "housing",
        "title_nb": "Vedtak om kommunal bolig",
        "title_nn": "Vedtak om kommunal bustad",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "NATIONAL_ID", "ADDRESS", "DATE_TIME", "ECONOMIC_STATUS"],
        "values": {"CASE_NUMBER": 1.2, "PHONE": 1.0, "MARITAL_STATUS": 0.8,
                   "BANK_ACCOUNT": 0.8, "EMAIL": 0.7, "AGE": 0.5, "GENDER": 0.5,
                   "ORGANIZATION": 0.5, "LOCATION": 0.5, "DATE_OF_BIRTH": 0.4,
                   "POSTAL_CODE": 0.3, "FAX_NUMBER": 0.3},
        "judgement": {"FAMILY_RELATION": 1.8, "HEALTH": 1.4, "EMPLOYMENT": 1.2,
                      "DISABILITY": 1.2, "FINANCIAL": 1.0, "IMMIGRATION_STATUS": 0.8,
                      "BEHAVIORAL_PATTERN": 0.6, "AGE_INFO": 0.5, "MEDICATION": 0.4},
        "cast_roles": ["caseworker", "spouse", "child", "landlord"],
        "age_profile": "adult", "density_factor": 1.05,
        "foreign_subject_p": 0.2,
        "signatory_roles": _CASEWORKER_SIGN + [("boligkonsulent", "bustadkonsulent")],
    },
    "tenancy_dispute": {
        "domain": "housing",
        "title_nb": "Klage i husleiesak",
        "title_nn": "Klage i husleigesak",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "dismissal_letter"],
        "core": ["PERSON", "ADDRESS", "DATE_TIME", "CASE_NUMBER"],
        "values": {"NATIONAL_ID": 0.8, "PHONE": 1.0, "EMAIL": 0.9, "BANK_ACCOUNT": 1.2,
                   "ORGANIZATION": 1.0, "ORG_NUMBER": 0.8, "LOCATION": 0.5,
                   "AGE": 0.3, "GENDER": 0.3, "MARITAL_STATUS": 0.3, "IBAN": 0.3,
                   "FAX_NUMBER": 0.3, "LICENSE_PLATE": 0.2, "URL": 0.3},
        "judgement": {"FINANCIAL": 1.8, "ECONOMIC_STATUS": 1.4, "BEHAVIORAL_PATTERN": 1.2,
                      "FAMILY_RELATION": 0.8, "HEALTH": 0.6, "EMPLOYMENT": 0.7,
                      "DISABILITY": 0.5, "IMMIGRATION_STATUS": 0.4, "AGE_INFO": 0.3},
        "cast_roles": ["landlord", "counterparty", "witness", "lawyer"],
        "age_profile": "adult", "density_factor": 1.1,
        "foreign_subject_p": 0.15,
        "signatory_roles": [("saksbehandler i Husleietvistutvalget",
                             "sakshandsamar i Husleigetvistutvalet")] + _CASEWORKER_SIGN,
    },
    # -- Immigration ----------------------------------------------------------
    "udi_decision": {
        "domain": "immigration",
        "title_nb": "Vedtak om oppholdstillatelse",
        "title_nn": "Vedtak om opphaldsløyve",
        "variants": VARIANTS,
        "clause_genres": ["udi_decision"],
        "core": ["PERSON", "NATIONAL_ID", "NATIONALITY", "DATE_TIME", "IMMIGRATION_STATUS"],
        "values": {"CASE_NUMBER": 1.8, "ADDRESS": 1.2, "PASSPORT": 1.4, "VISA_NUMBER": 1.0,
                   "PHONE": 0.7, "IDENTITY_CARD": 0.9, "EMAIL": 0.6, "AGE": 0.5,
                   "GENDER": 0.6, "MARITAL_STATUS": 0.7, "DATE_OF_BIRTH": 0.7,
                   "FAX_NUMBER": 0.5, "LOCATION": 0.4, "ORGANIZATION": 0.4,
                   "BANK_ACCOUNT": 0.3, "URL": 0.3},
        "judgement": {"FAMILY_RELATION": 2.0, "EMPLOYMENT": 1.5, "ETHNICITY": 1.0,
                      "RELIGIOUS_BELIEF": 1.0, "POLITICAL": 0.7, "SEXUAL_ORIENTATION": 0.6,
                      "BIOMETRIC_DATA": 0.6, "GENETIC_DATA": 0.5, "HEALTH": 0.7,
                      "CRIMINAL": 0.5, "FINANCIAL": 0.5, "ACADEMIC_RECORD": 0.5},
        "cast_roles": ["spouse", "child", "lawyer", "caseworker"],
        "age_profile": "working", "density_factor": 1.15,
        "foreign_subject_p": 1.0,
        "signatory_roles": _CASEWORKER_SIGN,
    },
    "udi_correspondence": {
        "domain": "immigration",
        "title_nb": "Anmodning om tilleggsopplysninger i utlendingssak",
        "title_nn": "Oppmoding om tilleggsopplysningar i utlendingssak",
        "variants": VARIANTS,
        "clause_genres": ["udi_decision"],
        "core": ["PERSON", "NATIONALITY", "DATE_TIME", "CASE_NUMBER"],
        "values": {"NATIONAL_ID": 1.0, "PASSPORT": 1.4, "VISA_NUMBER": 1.2,
                   "IDENTITY_CARD": 1.2, "ADDRESS": 1.2, "FAX_NUMBER": 1.0,
                   "PHONE": 0.8, "EMAIL": 0.8, "URL": 0.7, "DATE_OF_BIRTH": 0.8,
                   "MARITAL_STATUS": 0.5, "GENDER": 0.5, "AGE": 0.4, "LOCATION": 0.4,
                   "BANK_ACCOUNT": 0.3, "ORGANIZATION": 0.4},
        "judgement": {"IMMIGRATION_STATUS": 2.2, "FAMILY_RELATION": 1.6, "EMPLOYMENT": 1.0,
                      "ECONOMIC_STATUS": 0.8, "ACADEMIC_RECORD": 0.6, "HEALTH": 0.5,
                      "ETHNICITY": 0.6, "RELIGIOUS_BELIEF": 0.5, "BIOMETRIC_DATA": 0.5,
                      "FINANCIAL": 0.5},
        "cast_roles": ["spouse", "child", "lawyer", "caseworker"],
        "age_profile": "working", "density_factor": 1.15,
        "foreign_subject_p": 1.0,
        "signatory_roles": _CASEWORKER_SIGN,
    },
    # -- Veterinary -----------------------------------------------------------
    "vet_clinical_record": {
        "domain": "veterinary",
        "title_nb": "Klinisk journal fra veterinær",
        "title_nn": "Klinisk journal frå veterinær",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision"],
        "core": ["PERSON", "DATE_TIME", "ANIMAL_INFO"],
        "values": {"ADDRESS": 1.4, "PHONE": 1.4, "EMAIL": 0.9, "MEDICAL_LICENSE": 1.2,
                   "NATIONAL_ID": 0.6, "INSURANCE_NUMBER": 1.2, "ORGANIZATION": 0.8,
                   "CASE_NUMBER": 0.7, "BANK_ACCOUNT": 0.6, "LOCATION": 0.4,
                   "ORG_NUMBER": 0.4, "AGE": 0.2, "GENDER": 0.2, "LICENSE_PLATE": 0.2},
        "judgement": {"ECONOMIC_STATUS": 0.5, "EMPLOYMENT": 0.6, "FAMILY_RELATION": 0.6,
                      "BEHAVIORAL_PATTERN": 0.4, "AGE_INFO": 0.3},
        "cast_roles": ["veterinarian", "spouse"],
        "age_profile": "adult", "density_factor": 1.0,
        "foreign_subject_p": 0.08,
        "signatory_roles": [("veterinær", "veterinær"), ("dyrlege", "dyrlege")],
    },
    "mattilsynet_inspection": {
        "domain": "veterinary",
        "title_nb": "Vedtak om pålegg etter tilsyn med dyrehold",
        "title_nn": "Vedtak om pålegg etter tilsyn med dyrehald",
        "variants": VARIANTS,
        "clause_genres": ["nav_decision", "police_report"],
        "core": ["PERSON", "ADDRESS", "DATE_TIME", "CASE_NUMBER", "ANIMAL_INFO"],
        "values": {"ORG_NUMBER": 1.2, "NATIONAL_ID": 0.8, "PHONE": 1.0, "EMAIL": 0.8,
                   "ORGANIZATION": 0.9, "LICENSE_PLATE": 0.8, "FAX_NUMBER": 0.6,
                   "URL": 0.7, "LOCATION": 0.6, "MEDICAL_LICENSE": 0.6,
                   "INSURANCE_NUMBER": 0.4, "AGE": 0.2, "GENDER": 0.2,
                   "BANK_ACCOUNT": 0.3},
        "judgement": {"EMPLOYMENT": 1.0, "ECONOMIC_STATUS": 1.0, "CRIMINAL": 1.0,
                      "HEALTH": 0.8, "BEHAVIORAL_PATTERN": 0.8, "FAMILY_RELATION": 0.6,
                      "DISABILITY": 0.4, "AGE_INFO": 0.3, "FINANCIAL": 0.6},
        "cast_roles": ["veterinarian", "witness", "officer", "spouse"],
        "age_profile": "adult", "density_factor": 1.15,
        "foreign_subject_p": 0.08,
        "signatory_roles": [("seniorinspektør", "seniorinspektør"), ("inspektør", "inspektør")],
    },
    # -- Defence --------------------------------------------------------------
    "forsvaret_clearance": {
        "domain": "defence",
        "title_nb": "Vurdering av sikkerhetsklarering",
        "title_nn": "Vurdering av sikkerheitsklarering",
        "variants": VARIANTS,
        "clause_genres": ["police_report", "nav_decision", "dismissal_letter"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "MILITARY_ID"],
        "values": {"CASE_NUMBER": 1.4, "ADDRESS": 1.2, "NATIONALITY": 1.0,
                   "PASSPORT": 0.8, "PHONE": 0.8, "EMAIL": 0.7, "IDENTITY_CARD": 0.6,
                   "ORGANIZATION": 0.7, "DATE_OF_BIRTH": 0.6, "MARITAL_STATUS": 0.6,
                   "AGE": 0.4, "GENDER": 0.4, "BANK_ACCOUNT": 0.5, "FAX_NUMBER": 0.5,
                   "LOCATION": 0.4, "DRIVER_LICENSE": 0.4},
        "judgement": {"ECONOMIC_STATUS": 1.6, "CRIMINAL": 1.4, "FAMILY_RELATION": 1.2,
                      "EMPLOYMENT": 1.2, "FINANCIAL": 1.0, "HEALTH": 0.8,
                      "BEHAVIORAL_PATTERN": 0.8, "MEDICATION": 0.5, "TRADE_UNION": 0.4,
                      "ACADEMIC_RECORD": 0.6, "IMMIGRATION_STATUS": 0.5},
        "cast_roles": ["spouse", "parent", "officer", "employer_contact"],
        "age_profile": "working", "density_factor": 1.2,
        "subject_age": (18, 67),
        "foreign_subject_p": 0.06,
        "signatory_roles": [("sikkerhetsleder", "sikkerheitsleiar"),
                            ("klareringssaksbehandler", "klareringssakshandsamar")],
    },
    # -- Administrative, and the home of the PII-free documents ---------------
    "admin_circular": {
        "domain": "administration",
        "title_nb": "Rundskriv / informasjonsskriv",
        "title_nn": "Rundskriv / informasjonsskriv",
        "variants": ["prose_letter", "numbered_findings", "minutes", "field_header"],
        "clause_genres": ["nav_decision"],
        "core": [],
        "values": {"ORGANIZATION": 1.0, "URL": 1.2, "PHONE": 0.8, "EMAIL": 0.9,
                   "FAX_NUMBER": 0.7, "PERSON": 0.8, "DATE_TIME": 1.0,
                   "CASE_NUMBER": 0.6, "ORG_NUMBER": 0.5, "LOCATION": 0.4,
                   "POSTAL_CODE": 0.3, "ADDRESS": 0.3},
        "judgement": {},
        "cast_roles": ["caseworker"],
        "age_profile": "working", "density_factor": 0.7,
        "foreign_subject_p": 0.0,
        "pii_free_ok": True,
        "signatory_roles": [("avdelingsdirektør", "avdelingsdirektør"), ("seksjonsleder", "seksjonsleiar")],
    },
}

# Genres a document with no data subject at all can plausibly be: a circular, a
# procedural notice, an extract from a statute or a guidance note. Everything
# else names somebody by construction.
PII_FREE_GENRES = [g for g, spec in GENRES.items() if spec.get("pii_free_ok")]

# GDPR Art. 9 categories. Pilot v1's dismissal letter carried union membership,
# religion and sexual orientation at once and read as a checklist: a real
# document discloses one such fact when the case turns on it. `art9_cap`
# decides how many a given document may carry.
SPECIAL_CATEGORIES = {
    "RELIGIOUS_BELIEF", "SEXUAL_ORIENTATION", "TRADE_UNION", "POLITICAL",
    "ETHNICITY", "GENETIC_DATA", "BIOMETRIC_DATA",
}

# The health side of Article 9, capped separately. `SPECIAL_CATEGORIES` leaves
# HEALTH, DISABILITY and MEDICATION out because almost every genre here is
# about somebody's health and a cap of one would empty the health genres. They
# still cannot all stack: a smoke probe produced a debt-counselling note
# disclosing daily epilepsy medication, a wheelchair after a spinal injury and
# a worsening anxiety disorder in three consecutive sentences, which is three
# unrelated conditions in a document about money.
HEALTH_FAMILY = {"HEALTH", "DISABILITY", "MEDICATION", "GENETIC_DATA", "BIOMETRIC_DATA"}


def health_family_cap(profile: str) -> int:
    """Return how many health-family types one document of this profile may carry."""
    return 3 if profile == "case_file" else (2 if profile == "dense" else 1)

# ETHNICITY is the one Art. 9 category the pilot got actively wrong: a police
# report framed a Romani background as "relevant for the investigation of her
# social network and access to weapons caches". Ethnic origin is a personalia
# fact, never an investigative lead, so the type is restricted to the genres
# where a neutral background statement is what a real document contains, and
# kept out of every criminal-suspicion genre.
ETHNICITY_ALLOWED_GENRES = {
    "udi_decision", "udi_correspondence", "ppt_assessment", "admission_decision",
    "gp_referral", "psychologist_note", "hospital_discharge",
}

# Types `docs/SYNTHETIC_DATA_SPEC.md` Section 5 says must be forced in because
# the existing corpus is sparse in them, plus the special categories the clause
# bank covers thinly.
RARE_TYPES = [
    "SEXUAL_ORIENTATION", "POLITICAL", "ECONOMIC_STATUS", "BEHAVIORAL_PATTERN",
    "GENETIC_DATA", "BIOMETRIC_DATA", "TRADE_UNION", "RELIGIOUS_BELIEF", "ETHNICITY",
]

# Types deliberately left uncovered. `docs/ANNOTATION_SPEC.md` cut both with
# documented reasoning and `docs/PROJECT_SPEC_V2.md` reinstates them without
# defining either; inventing a definition here would put guessed semantics into
# a dataset whose whole claim is that its labels are correct by construction.
# The run report lists them so the owner decides, not this generator.
UNCOVERED_TYPES = ["CONTEXT_SENSITIVE", "IDENTIFIABLE_IMAGE"]

FIELD_LABELS: Dict[str, str] = {
    "PERSON": "Navn", "NATIONAL_ID": "Fødselsnummer", "ADDRESS": "Adresse",
    "POSTAL_CODE": "Postnummer", "PHONE": "Telefon", "FAX_NUMBER": "Faks",
    "EMAIL": "E-post", "ORG_NUMBER": "Org.nr.", "CASE_NUMBER": "Saksnummer",
    "DATE_TIME": "Dato", "ORGANIZATION": "Virksomhet", "AGE": "Alder",
    "GENDER": "Kjønn", "NATIONALITY": "Statsborgerskap", "MARITAL_STATUS": "Sivilstand",
    "LICENSE_PLATE": "Kjøretøy, reg.nr.", "BANK_ACCOUNT": "Kontonummer",
    "IBAN": "IBAN", "PASSPORT": "Passnummer", "VISA_NUMBER": "Visumnummer",
    "DRIVER_LICENSE": "Førerkortnummer", "IDENTITY_CARD": "ID-kortnummer",
    "MEDICAL_LICENSE": "HPR-nummer", "MILITARY_ID": "Tjenestenummer",
    "INSURANCE_NUMBER": "Forsikringsnummer", "TAX_ID": "Organisasjonsnummer for mva",
    "STUDENT_ID": "Studentnummer", "URL": "Nettside", "USERNAME": "Brukernavn",
    "SOCIAL_MEDIA": "Konto i sosiale medier", "IP_ADDRESS": "IP-adresse",
    "DEVICE_ID": "Enhetsidentifikator", "CREDIT_CARD": "Kortnummer",
    "CRYPTO": "Kryptolommebok", "PASSWORD": "Passord", "DATE_OF_BIRTH": "Fødselsdato",
    "ANIMAL_INFO": "Dyrehold", "LOCATION": "Sted",
}

# Nynorsk spellings that differ. The label is a prompt hint, not a value that
# must appear verbatim, but a bokmål field name in a nynorsk document is the
# kind of detail that makes generated Norwegian read as generated.
FIELD_LABELS_NN: Dict[str, str] = {
    "PERSON": "Namn", "ORGANIZATION": "Verksemd", "LICENSE_PLATE": "Køyretøy, reg.nr.",
    "DRIVER_LICENSE": "Førarkortnummer", "USERNAME": "Brukarnamn",
    "NATIONALITY": "Statsborgarskap", "URL": "Nettstad", "MILITARY_ID": "Tenestenummer",
    "ANIMAL_INFO": "Dyrehald", "LOCATION": "Stad", "DEVICE_ID": "Eininga sin identifikator",
}


def field_label(etype: str, form: str) -> str:
    """Return the Norwegian field label for a type in the document's written form."""
    if form == "nn" and etype in FIELD_LABELS_NN:
        return FIELD_LABELS_NN[etype]
    return FIELD_LABELS.get(etype, etype)


def genre_names() -> List[str]:
    """Return the list of implemented genre ids."""
    return list(GENRES.keys())


def genres_hosting(etype: str) -> List[str]:
    """Return every genre whose core, optional values or judgement mix may carry a type.

    This is what batch-level coverage scheduling schedules against: a type is
    only ever forced into a document whose genre a real Norwegian equivalent
    would plausibly carry it in.

    Args:
        etype: Entity type name.

    Returns:
        Genre ids, in catalogue order.
    """
    hosts = []
    for name, spec in GENRES.items():
        if etype in spec["core"] or etype in spec["values"] or etype in spec["judgement"]:
            if etype == "ETHNICITY" and name not in ETHNICITY_ALLOWED_GENRES:
                continue
            hosts.append(name)
    return hosts


def coverage_types(taxonomy_types: Sequence[str]) -> List[str]:
    """Return the types coverage scheduling should aim to cover, in scheduling order.

    Excludes `UNCOVERED_TYPES` and anything no genre hosts, and puts the
    hardest-to-place types first so they get the documents they need before the
    easy ones use the budget up.

    Args:
        taxonomy_types: Every type name in the taxonomy.

    Returns:
        Schedulable type names, rarest host set first.
    """
    schedulable = [t for t in taxonomy_types
                   if t not in UNCOVERED_TYPES and genres_hosting(t)]
    return sorted(schedulable, key=lambda t: (len(genres_hosting(t)), t))
