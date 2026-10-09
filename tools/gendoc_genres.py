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

**A judgement type may be planned more than once in a document.** Pilot v4's 39 accepted
documents carried every clause-level type exactly once, 100% of the time, while the gold
set's inspection template averages 5.3 CRIMINAL spans and its concern-report template
8.1 HEALTH spans per document: a detector trained on one-of-each learns to find one and
stop. `MULTI_PROPENSITY` says, per genre, which types a real document of that kind
repeats (offences in a police report, findings in a clinical or veterinary record, debts
in a debt-counselling note, observations in a child-welfare or school document),
`draw_instance_counts` draws how many from a profile-dependent distribution that keeps
most documents at one, and `item_budget` bounds the total so the extra instances still fit
the section planner's seven-items-per-section limit.

**Some documents contain only near-misses.** A detector also has to learn that a sentence
which reads like a disclosure ("nektet å oppgi sin religiøse tilhørighet") is not one, and
the only documents that teach it with nothing else to lean on are those with no personal
data at all and a few planted near-misses. The `near_miss_only` profile draws one of
`NEAR_MISS_GENRES` (anonymised summaries, guidance and statistics notes, and the circular),
plans no value, and has `generate_documents` plant two to four near-miss negatives whose
text holds no name, identifier, date or number (`gendoc_dataset.unnamed_safe`).

**A cast member's role word is EMPLOYMENT.** The annotation owner's ruling is that a role
word attached to, or clearly referring to, a specific individual is EMPLOYMENT, and that
the name stays PERSON. `CAST_ROLE_WORDS` gives, per professional role, the concrete words
a document of that kind uses; the sampler plants one for each such person, the prompt asks
for it directly beside the name, and the generic use of the same string is what G14 rejects.

Genres are grouped by the domains of the Section 4 table. Clause-bank entries
carry the five original genre ids in their `genres` list, so each genre here
declares `clause_genres`: the clause-bank genre ids whose clauses are plausible
in it. That lets 30-odd genres share one hand-written clause bank without
re-annotating every entry.
"""

from __future__ import annotations

import functools
import random
from typing import Dict, List, Optional, Sequence, Tuple

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
    # No personal data and 2-4 planted near-misses, so the label set is `{}` and the only
    # thing in the text that looks like a disclosure is a sentence that is not one. Its 5%
    # is taken proportionally from the five profiles below (their former shares times 0.90 / 0.95).
    "near_miss_only": {"share": 0.05, "types": (0, 0), "bands": [(400, 800), (800, 1600)],
                       "cast": (0, 0), "art9": 0, "dates": (0, 0)},
    "minimal": {"share": 0.057, "types": (1, 2), "bands": [(400, 800), (800, 1600)],
                "cast": (0, 0), "art9": 1, "dates": (0, 1)},
    "light": {"share": 0.227, "types": (3, 5), "bands": [(400, 800), (800, 1600)],
              "cast": (0, 1), "art9": 1, "dates": (1, 1)},
    "typical": {"share": 0.284, "types": (6, 9), "bands": [(800, 1600), (1600, 2800)],
                "cast": (0, 2), "art9": 1, "dates": (1, 2)},
    "dense": {"share": 0.190, "types": (10, 18), "bands": [(2400, 3400), (2800, 4000)],
              "cast": (1, 3), "art9": 2, "dates": (2, 4)},
    # The case-file band asks for less than the profile's name suggests on
    # purpose. Measured on Qwen3.5-9B: a 4,000-5,500 band produced an accepted
    # 7,587-character document, and a 5,000-6,500 band produced output that
    # either passed 9,000 characters or ran out of token budget. The model has
    # an effective long-form ceiling around 8,000-9,500 characters and stops
    # obeying a character target above roughly 4,000, so the band is set where
    # the usual 40-70% overshoot lands inside the hard cap.
    "case_file": {"share": 0.142, "types": (18, 28), "bands": [(3600, 4600), (4200, 5200)],
                  "cast": (3, 6), "art9": 3, "dates": (3, 7)},
}

PROFILE_ORDER = ["pii_free", "near_miss_only", "minimal", "light", "typical", "dense", "case_file"]


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
    # Anyone acting in a professional capacity -- author, caseworker, physician,
    # psychologist, vet, lawyer, officer, teacher, employer contact. Pilot v4 drew
    # them from "working" (18-29 for 22% of them) and printed a 19-year-old
    # security-clearance author and a 23-year-old police officer.
    "professional": [(25, 34, 0.28), (35, 49, 0.40), (50, 67, 0.32)],
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

# Concrete role words for the professionals in a cast, as (Bokmål, Nynorsk, weight). The annotation
# owner's ruling makes the role word of a specific individual EMPLOYMENT, and the output format is
# one string per type, so a planted word labels every occurrence of its string. The words are
# therefore chosen to be distinctive (`psykologspesialist`, `tilsynsveterinær`, `kontaktlærer`
# rather than `lærer`), and the sampler refuses a word that is a substring of another planted
# string or contains one. The weights come from pilot v5's texts: a bare `lege` or `saksbehandler`
# was also used generically (or inside `overlege`, `saksbehandleren`) in all 10 and all 8 of the
# documents that held it, so both are drawn rarely; the definite `saksbehandleren` was in 8 and
# generic in none, so the definite forms are drawn more. A word in `DEFINITE_ROLE_WORDS` may stand
# later in the document as a reference to the person once the name has been given; an indefinite
# one is only ever valid directly beside the name.
CAST_ROLE_WORDS: Dict[str, List[Tuple[str, str, float]]] = {
    "physician": [("fastlege", "fastlege", 3.0), ("overlege", "overlege", 2.0), ("lege", "lege", 0.6),
                  ("legen", "legen", 1.2)],
    "psychologist": [("psykologspesialist", "psykologspesialist", 3.0), ("psykolog", "psykolog", 1.5),
                     ("psykologen", "psykologen", 1.0)],
    "veterinarian": [("tilsynsveterinær", "tilsynsveterinær", 2.5), ("veterinær", "veterinær", 2.5),
                     ("veterinæren", "veterinæren", 1.2)],
    "caseworker": [("saksbehandler", "sakshandsamar", 1.0), ("rådgiver", "rådgjevar", 3.0),
                   ("seniorrådgiver", "seniorrådgjevar", 2.5), ("saksbehandleren", "sakshandsamaren", 1.5)],
    "lawyer": [("advokat", "advokat", 2.5), ("advokaten", "advokaten", 1.2)],
    "officer": [("politibetjent", "politibetjent", 3.0), ("etterforsker", "etterforskar", 2.0),
                ("politioverbetjent", "politioverbetjent", 1.5)],
    "teacher": [("kontaktlærer", "kontaktlærar", 3.0), ("lærer", "lærar", 1.5), ("læreren", "læraren", 1.0)],
    "employer_contact": [("daglig leder", "dagleg leiar", 2.0), ("personalsjef", "personalsjef", 2.0),
                         ("HR-rådgiver", "HR-rådgjevar", 2.0), ("avdelingsleder", "avdelingsleiar", 2.0)],
    "creditor_contact": [("inkassomedarbeider", "inkassomedarbeidar", 3.0),
                         ("kredittansvarlig", "kredittansvarleg", 1.5), ("kundebehandler", "kundebehandlar", 1.0)],
}

DEFINITE_ROLE_WORDS = frozenset({
    "legen", "psykologen", "veterinæren", "saksbehandleren", "sakshandsamaren", "advokaten",
    "læreren", "læraren"})

# Signatory roles that are not a role word: planted as nothing, since a bare "spesialist" is
# an adjective of a title and not the title.
SIGNATORY_NOT_A_ROLE_WORD = frozenset({"spesialist"})


def signatory_role_word(signatory_role: Optional[str]) -> Optional[str]:
    """Return the role word to plant for a document's signatory, or None.

    The signatory's role is the one the prompt already names beside the author
    ("signert av Kari Hansen (rådgiver)"). A role that names a unit ("saksbehandler i
    Husleietvistutvalget") is cut before the unit, so the planted string holds no
    organisation name.

    Args:
        signatory_role: The role string drawn from the genre's `signatory_roles`.

    Returns:
        The role word, or None when the signatory has no role or only a bare adjective of one.
    """
    if not signatory_role:
        return None
    word = signatory_role.split(" i ")[0].strip()
    return None if not word or word in SIGNATORY_NOT_A_ROLE_WORD else word


@functools.lru_cache(maxsize=None)
def professional_lexicon() -> Tuple[str, ...]:
    """Return every professional role word the sweep for unplanned role words recognises."""
    words = {nb for forms in CAST_ROLE_WORDS.values() for nb, _nn, _w in forms}
    words |= {nn for forms in CAST_ROLE_WORDS.values() for _nb, nn, _w in forms}
    for spec in GENRES.values():
        for nb, nn in spec.get("signatory_roles", []):
            words |= {signatory_role_word(nb), signatory_role_word(nn)} - {None}
    words |= {
        "sykepleier", "sjukepleiar", "helsesøster", "jordmor", "tannlege", "fysioterapeut", "sosionom",
        "barnevernspedagog", "barnevernkonsulent", "rektor", "dommer", "dommar", "politiadvokat",
        "statsadvokat", "politimester", "lensmann", "forsvarer", "forsvarar", "aktor", "bedriftslege",
        "kommuneoverlege", "arbeidsmedisiner", "arbeidsmedisinar", "seniorinspektør", "inspektør",
        "fagleder", "fagleiar", "konsulent", "politiførstebetjent", "psykiater", "dyrlege"}
    return tuple(sorted(w for w in words if w))


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
                      "RELIGIOUS_BELIEF": 0.3, "ETHNICITY": 0.3},
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
                      "AGE_INFO": 0.4},
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
                      "ACADEMIC_RECORD": 0.4, "ETHNICITY": 0.3},
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
        "clause_genres": ["police_report", "crime"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CRIMINAL"],
        "values": {"CASE_NUMBER": 1.8, "ADDRESS": 1.4, "PHONE": 1.0, "LICENSE_PLATE": 1.0,
                   "LOCATION": 0.8, "AGE": 0.6, "DEVICE_ID": 0.5, "GENDER": 0.6,
                   "DRIVER_LICENSE": 0.7, "PASSPORT": 0.4, "SOCIAL_MEDIA": 0.6,
                   "IP_ADDRESS": 0.4, "EMAIL": 0.5, "CREDIT_CARD": 0.3, "CRYPTO": 0.2,
                   "DATE_OF_BIRTH": 0.4, "ORGANIZATION": 0.4, "USERNAME": 0.3,
                   "FIREARMS_LICENSE": 0.5},
        "judgement": {"BEHAVIORAL_PATTERN": 3.0, "FAMILY_RELATION": 1.2, "EMPLOYMENT": 1.0,
                      "HEALTH": 1.0, "BIOMETRIC_DATA": 1.0, "ECONOMIC_STATUS": 0.7,
                      "FINANCIAL": 0.6, "IMMIGRATION_STATUS": 0.8,
                      "AGE_INFO": 0.4, "MEDICATION": 0.5},
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
        "clause_genres": ["police_report", "crime"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CASE_NUMBER", "CRIMINAL"],
        "values": {"ADDRESS": 1.4, "AGE": 0.6, "GENDER": 0.5, "LICENSE_PLATE": 0.7,
                   "PHONE": 0.6, "DRIVER_LICENSE": 0.6, "LOCATION": 0.6,
                   "DATE_OF_BIRTH": 0.5, "ORGANIZATION": 0.4, "FAX_NUMBER": 0.4,
                   "PASSPORT": 0.3, "ORG_NUMBER": 0.3, "CREDIT_CARD": 0.3, "CRYPTO": 0.25,
                   "FIREARMS_LICENSE": 0.4},
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
        "clause_genres": ["police_report", "dismissal_letter", "crime"],
        "core": ["PERSON", "DATE_TIME", "CASE_NUMBER"],
        "values": {"NATIONAL_ID": 1.2, "ADDRESS": 1.0, "AGE": 0.7, "GENDER": 0.5,
                   "ORGANIZATION": 0.8, "LOCATION": 0.7, "ORG_NUMBER": 0.5,
                   "LICENSE_PLATE": 0.5, "DRIVER_LICENSE": 0.4, "FAX_NUMBER": 0.4,
                   "DATE_OF_BIRTH": 0.4, "BANK_ACCOUNT": 0.3, "PHONE": 0.3, "CREDIT_CARD": 0.25,
                   "CRYPTO": 0.2,
                   "FIREARMS_LICENSE": 0.3,
                   "VESSEL_REGISTRATION": 0.3},
        "judgement": {"CRIMINAL": 2.4, "BEHAVIORAL_PATTERN": 1.6, "FINANCIAL": 1.2,
                      "ECONOMIC_STATUS": 1.0, "FAMILY_RELATION": 1.0, "EMPLOYMENT": 1.0,
                      "HEALTH": 0.8, "AGE_INFO": 0.4,
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
        "clause_genres": ["police_report", "crime"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "CASE_NUMBER", "BEHAVIORAL_PATTERN"],
        "values": {"ADDRESS": 1.6, "PHONE": 0.8, "AGE": 0.5, "GENDER": 0.5,
                   "LOCATION": 0.8, "DATE_OF_BIRTH": 0.4, "SOCIAL_MEDIA": 0.5,
                   "LICENSE_PLATE": 0.4, "EMAIL": 0.3, "USERNAME": 0.3,
                   "FIREARMS_LICENSE": 0.5},
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
        "clause_genres": ["police_report", "crime", "forensics"],
        "core": ["PERSON", "DATE_TIME", "CASE_NUMBER", "DEVICE_ID"],
        "values": {"NATIONAL_ID": 1.0, "IP_ADDRESS": 1.8, "USERNAME": 1.6,
                   "SOCIAL_MEDIA": 1.4, "EMAIL": 1.2, "URL": 1.4, "PASSWORD": 1.0,
                   "PHONE": 1.0, "ADDRESS": 0.7, "CRYPTO": 0.7, "CREDIT_CARD": 0.5,
                   "AGE": 0.4, "GENDER": 0.4, "LOCATION": 0.4, "ORGANIZATION": 0.4},
        "judgement": {"CRIMINAL": 2.2, "BEHAVIORAL_PATTERN": 1.6, "FINANCIAL": 0.8,
                      "ECONOMIC_STATUS": 0.5, "HEALTH": 0.4, "FAMILY_RELATION": 0.5},
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
        "clause_genres": ["nav_decision", "debt"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "ECONOMIC_STATUS"],
        "values": {"BANK_ACCOUNT": 1.8, "ADDRESS": 1.2, "PHONE": 1.0, "CASE_NUMBER": 0.8,
                   "IBAN": 0.8, "CREDIT_CARD": 0.7, "TAX_ID": 0.6, "EMAIL": 0.6,
                   "MARITAL_STATUS": 0.6, "ORGANIZATION": 0.8, "ORG_NUMBER": 0.5,
                   "AGE": 0.4, "GENDER": 0.4, "CRYPTO": 0.3, "LOCATION": 0.3,
                   "INSURANCE_NUMBER": 0.3,
                   "VESSEL_REGISTRATION": 0.3},
        "judgement": {"FINANCIAL": 2.6, "EMPLOYMENT": 1.4, "FAMILY_RELATION": 1.2,
                      "HEALTH": 1.0, "BEHAVIORAL_PATTERN": 0.9, "DISABILITY": 0.7,
                      "MEDICATION": 0.4, "AGE_INFO": 0.3},
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
                   "CREDIT_CARD": 0.2, "CRYPTO": 0.3,
                   "VESSEL_REGISTRATION": 0.4},
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
        "clause_genres": ["nav_decision", "debt"],
        "core": ["PERSON", "ADDRESS", "DATE_TIME", "CASE_NUMBER", "FINANCIAL"],
        "values": {"NATIONAL_ID": 1.0, "BANK_ACCOUNT": 1.8, "ORGANIZATION": 1.4,
                   "ORG_NUMBER": 1.0, "IBAN": 0.9, "PHONE": 0.8, "EMAIL": 0.7,
                   "TAX_ID": 0.5, "CREDIT_CARD": 0.5, "FAX_NUMBER": 0.5,
                   "AGE": 0.2, "DATE_OF_BIRTH": 0.4, "LOCATION": 0.3, "URL": 0.4,
                   "VESSEL_REGISTRATION": 0.3},
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
        "clause_genres": ["nav_decision", "police_report", "bank", "debt"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "BANK_ACCOUNT"],
        "values": {"CASE_NUMBER": 1.2, "IBAN": 1.6, "ADDRESS": 1.2, "CREDIT_CARD": 1.2,
                   "CRYPTO": 1.2, "TAX_ID": 1.0, "ORG_NUMBER": 0.9, "ORGANIZATION": 0.9,
                   "IDENTITY_CARD": 1.0, "PASSPORT": 0.7, "PHONE": 0.7, "EMAIL": 0.6,
                   "IP_ADDRESS": 0.8, "DEVICE_ID": 0.5, "FAX_NUMBER": 0.4,
                   "LOCATION": 0.3, "NATIONALITY": 0.6, "GENDER": 0.3,
                   "VESSEL_REGISTRATION": 0.3},
        "judgement": {"FINANCIAL": 2.4, "ECONOMIC_STATUS": 1.4, "EMPLOYMENT": 1.2,
                      "CRIMINAL": 1.0, "IMMIGRATION_STATUS": 0.7, "BEHAVIORAL_PATTERN": 0.7,
                      "FAMILY_RELATION": 0.7},
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
        "clause_genres": ["police_report", "gp_referral", "school"],
        "core": ["PERSON", "DATE_TIME", "ORGANIZATION", "BEHAVIORAL_PATTERN"],
        "values": {"AGE": 1.2, "STUDENT_ID": 1.4, "NATIONAL_ID": 0.8, "GENDER": 0.7,
                   "PHONE": 0.9, "EMAIL": 0.8, "ADDRESS": 0.6, "SOCIAL_MEDIA": 1.2,
                   "USERNAME": 1.0, "DEVICE_ID": 0.8, "URL": 0.8, "IP_ADDRESS": 0.6,
                   "PASSWORD": 0.5, "CASE_NUMBER": 0.6, "LOCATION": 0.3},
        "judgement": {"HEALTH": 1.2, "FAMILY_RELATION": 1.4, "CRIMINAL": 0.8,
                      "DISABILITY": 0.8, "ACADEMIC_RECORD": 1.2, "AGE_INFO": 0.6,
                      "MEDICATION": 0.5, "ECONOMIC_STATUS": 0.4},
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
                   "NATIONALITY": 0.6, "LOCATION": 0.3, "BANK_ACCOUNT": 0.3, "VISA_NUMBER": 0.4},
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
        "clause_genres": ["police_report", "nav_decision", "gp_referral", "barnevern"],
        "core": ["PERSON", "DATE_TIME", "FAMILY_RELATION", "BEHAVIORAL_PATTERN"],
        "values": {"NATIONAL_ID": 1.4, "AGE": 1.2, "ADDRESS": 1.2, "GENDER": 0.7,
                   "PHONE": 1.0, "CASE_NUMBER": 1.0, "ORGANIZATION": 0.7,
                   "EMAIL": 0.6, "DATE_OF_BIRTH": 0.6, "STUDENT_ID": 0.5,
                   "SOCIAL_MEDIA": 0.4, "LOCATION": 0.4, "MARITAL_STATUS": 0.5},
        "judgement": {"HEALTH": 1.6, "ECONOMIC_STATUS": 1.4, "MEDICATION": 0.9,
                      "CRIMINAL": 1.0, "DISABILITY": 0.8, "ACADEMIC_RECORD": 0.8,
                      "AGE_INFO": 0.6, "IMMIGRATION_STATUS": 0.6, "EMPLOYMENT": 0.8},
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
        "clause_genres": ["nav_decision", "gp_referral", "police_report", "barnevern"],
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
                   "URL": 0.4, "USERNAME": 0.3, "VISA_NUMBER": 0.3},
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
                      "FAMILY_RELATION": 0.5},
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
                      "POLITICAL": 0.4, "FINANCIAL": 0.5},
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
        "clause_genres": ["nav_decision", "vet_clinical"],
        "animal_types": ["HEALTH"],
        "core": ["PERSON", "DATE_TIME", "ANIMAL_INFO"],
        "values": {"ADDRESS": 1.4, "PHONE": 1.4, "EMAIL": 0.9, "MEDICAL_LICENSE": 1.2,
                   "NATIONAL_ID": 0.6, "INSURANCE_NUMBER": 1.2, "ORGANIZATION": 0.8,
                   "CASE_NUMBER": 0.7, "BANK_ACCOUNT": 0.6, "LOCATION": 0.4,
                   "ORG_NUMBER": 0.4, "AGE": 0.2, "GENDER": 0.2, "LICENSE_PLATE": 0.2,
                   "FIREARMS_LICENSE": 0.2},
        "judgement": {"HEALTH": 2.6, "ECONOMIC_STATUS": 0.5, "EMPLOYMENT": 0.6,
                      "FAMILY_RELATION": 0.6, "BEHAVIORAL_PATTERN": 0.4, "AGE_INFO": 0.3},
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
        "clause_genres": ["nav_decision", "police_report", "vet_inspection"],
        "animal_types": ["HEALTH"],
        "core": ["PERSON", "ADDRESS", "DATE_TIME", "CASE_NUMBER", "ANIMAL_INFO"],
        "values": {"ORG_NUMBER": 1.2, "NATIONAL_ID": 0.8, "PHONE": 1.0, "EMAIL": 0.8,
                   "ORGANIZATION": 0.9, "LICENSE_PLATE": 0.8, "FAX_NUMBER": 0.6,
                   "URL": 0.7, "LOCATION": 0.6, "MEDICAL_LICENSE": 0.6,
                   "INSURANCE_NUMBER": 0.4, "AGE": 0.2, "GENDER": 0.2,
                   "BANK_ACCOUNT": 0.3,
                   "FIREARMS_LICENSE": 0.3,
                   "VESSEL_REGISTRATION": 0.6},
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
        "clause_genres": ["police_report", "nav_decision", "dismissal_letter", "crime"],
        "core": ["PERSON", "NATIONAL_ID", "DATE_TIME", "MILITARY_ID"],
        "values": {"CASE_NUMBER": 1.4, "ADDRESS": 1.2, "NATIONALITY": 1.0,
                   "PASSPORT": 0.8, "PHONE": 0.8, "EMAIL": 0.7, "IDENTITY_CARD": 0.6,
                   "ORGANIZATION": 0.7, "DATE_OF_BIRTH": 0.6, "MARITAL_STATUS": 0.6,
                   "AGE": 0.4, "GENDER": 0.4, "BANK_ACCOUNT": 0.5, "FAX_NUMBER": 0.5,
                   "LOCATION": 0.4, "DRIVER_LICENSE": 0.4,
                   "FIREARMS_LICENSE": 0.3},
        "judgement": {"ECONOMIC_STATUS": 1.6, "CRIMINAL": 1.4, "FAMILY_RELATION": 1.2,
                      "EMPLOYMENT": 1.2, "FINANCIAL": 1.0, "HEALTH": 0.8,
                      "BEHAVIORAL_PATTERN": 0.8, "MEDICATION": 0.5, "POLITICAL": 0.5,
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
        "pii_free_ok": True, "near_miss_ok": True,
        "signatory_roles": [("avdelingsdirektør", "avdelingsdirektør"), ("seksjonsleder", "seksjonsleiar")],
    },
    "anonymised_case_summary": {
        "domain": "administration",
        "title_nb": "Anonymisert saksoppsummering til opplæring",
        "title_nn": "Anonymisert saksoppsummering til opplæring",
        "variants": ["prose_letter", "numbered_findings", "minutes"],
        "clause_genres": ["nav_decision", "dismissal_letter", "gp_referral"],
        "core": [], "values": {}, "judgement": {}, "cast_roles": [],
        "age_profile": "working", "density_factor": 0.7,
        "foreign_subject_p": 0.0, "near_miss_ok": True,
        "signatory_roles": [("seksjonsleder", "seksjonsleiar"), ("avdelingsdirektør", "avdelingsdirektør")],
    },
    "guidance_note": {
        "domain": "administration",
        "title_nb": "Veiledningsnotat om saksbehandling",
        "title_nn": "Rettleiingsnotat om sakshandsaming",
        "variants": ["prose_letter", "numbered_findings"],
        "clause_genres": ["nav_decision", "dismissal_letter"],
        "core": [], "values": {}, "judgement": {}, "cast_roles": [],
        "age_profile": "working", "density_factor": 0.7,
        "foreign_subject_p": 0.0, "near_miss_ok": True,
        "signatory_roles": [("seksjonsleder", "seksjonsleiar"), ("avdelingsdirektør", "avdelingsdirektør")],
    },
    "statistics_note": {
        "domain": "administration",
        "title_nb": "Notat om statistikk og praksis i behandlede saker",
        "title_nn": "Notat om statistikk og praksis i handsama saker",
        "variants": ["prose_letter", "numbered_findings", "minutes"],
        "clause_genres": ["nav_decision", "gp_referral"],
        "core": [], "values": {}, "judgement": {}, "cast_roles": [],
        "age_profile": "working", "density_factor": 0.7,
        "foreign_subject_p": 0.0, "near_miss_ok": True,
        "signatory_roles": [("seksjonsleder", "seksjonsleiar"), ("avdelingsdirektør", "avdelingsdirektør")],
    },
}

# Genres a document with no data subject at all can plausibly be: a circular, a
# procedural notice, an extract from a statute or a guidance note. Everything
# else names somebody by construction.
PII_FREE_GENRES = [g for g, spec in GENRES.items() if spec.get("pii_free_ok")]

# Genres in which an unnamed person is natural: an anonymised summary of a case used for
# training, a guidance note whose examples speak of "søkeren", a statistics note, the circular.
# A near-miss-only document is drawn from these and from no other genre, and an ordinary
# document is never drawn from them.
NEAR_MISS_GENRES = [g for g, spec in GENRES.items() if spec.get("near_miss_ok")]
NO_SUBJECT_GENRES = sorted(set(PII_FREE_GENRES) | set(NEAR_MISS_GENRES))

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


# Types a document may plan more than once. Every one is a clause type whose real
# documents list several distinct instances (an offence, a finding, a debt, an
# observation, a relative) or, for ANIMAL_INFO, a value type for which a herd or a pair of
# pets is several descriptors. None is an Art. 9 special category: those stay at one, and
# the Art. 9 and health-family caps count categories (`SPECIAL_CATEGORIES`,
# `HEALTH_FAMILY` membership of the types drawn), never instances, so three HEALTH
# findings use one health-family slot.
MULTI_INSTANCE_TYPES = (
    "CRIMINAL", "HEALTH", "MEDICATION", "BEHAVIORAL_PATTERN", "FINANCIAL", "ECONOMIC_STATUS",
    "FAMILY_RELATION", "ANIMAL_INFO",
)

# How readily a genre repeats a type, 0..1. Anything not listed is planned once.
MULTI_PROPENSITY: Dict[str, Dict[str, float]] = {
    "police_report": {"CRIMINAL": 1.0, "BEHAVIORAL_PATTERN": 0.5, "HEALTH": 0.2},
    "prosecution_decision": {"CRIMINAL": 1.0},
    "court_judgment": {"CRIMINAL": 1.0, "FINANCIAL": 0.3, "BEHAVIORAL_PATTERN": 0.4},
    "restraining_order": {"CRIMINAL": 0.8, "BEHAVIORAL_PATTERN": 1.0},
    "digital_forensics_report": {"CRIMINAL": 0.8, "BEHAVIORAL_PATTERN": 0.4},
    "gp_referral": {"HEALTH": 1.0, "MEDICATION": 0.8},
    "hospital_discharge": {"HEALTH": 1.0, "MEDICATION": 0.8},
    "psychologist_note": {"HEALTH": 0.8, "MEDICATION": 0.5, "FAMILY_RELATION": 0.3},
    "occupational_health": {"HEALTH": 0.8, "MEDICATION": 0.5},
    "sickness_followup": {"HEALTH": 0.8, "MEDICATION": 0.5},
    "nav_decision": {"FINANCIAL": 0.7, "HEALTH": 0.6, "ECONOMIC_STATUS": 0.3, "FAMILY_RELATION": 0.3},
    "debt_counselling": {"FINANCIAL": 1.0, "ECONOMIC_STATUS": 0.6},
    "inkasso_notice": {"FINANCIAL": 1.0, "ECONOMIC_STATUS": 0.3},
    "tax_assessment": {"FINANCIAL": 0.8},
    "bank_aml": {"FINANCIAL": 0.8, "CRIMINAL": 0.7, "ECONOMIC_STATUS": 0.3},
    "housing_application": {"ECONOMIC_STATUS": 0.4, "FINANCIAL": 0.5, "FAMILY_RELATION": 0.3},
    "barnevern_concern": {"BEHAVIORAL_PATTERN": 1.0, "FAMILY_RELATION": 0.8, "HEALTH": 0.3},
    "barnevern_care_plan": {"BEHAVIORAL_PATTERN": 1.0, "FAMILY_RELATION": 0.8, "HEALTH": 0.3},
    "school_incident": {"BEHAVIORAL_PATTERN": 1.0},
    "udi_decision": {"FAMILY_RELATION": 0.4},
    "udi_correspondence": {"FAMILY_RELATION": 0.4},
    "dismissal_letter": {"BEHAVIORAL_PATTERN": 0.8},
    "whistleblowing_report": {"BEHAVIORAL_PATTERN": 0.8, "FINANCIAL": 0.4},
    "hr_grievance": {"BEHAVIORAL_PATTERN": 0.8},
    "forsvaret_clearance": {"CRIMINAL": 0.5, "FINANCIAL": 0.5, "ECONOMIC_STATUS": 0.3},
    "vet_clinical_record": {"HEALTH": 1.0, "ANIMAL_INFO": 0.6},
    "mattilsynet_inspection": {"HEALTH": 1.0, "ANIMAL_INFO": 0.7, "BEHAVIORAL_PATTERN": 0.6,
                               "CRIMINAL": 0.4},
}

# Chance that a type with propensity 1.0 is planned more than once, by density profile.
# Most documents stay at one so that "always several" is not learned either; a short
# document has no room for a list, a case file does.
MULTI_BASE_P: Dict[str, float] = {
    "pii_free": 0.0, "near_miss_only": 0.0, "minimal": 0.0, "light": 0.20, "typical": 0.45, "dense": 0.65, "case_file": 0.75,
}
# Given that a type is repeated: the weight of 2, 3 and 4 instances, and the most a profile takes.
MULTI_COUNT_WEIGHTS: Dict[int, float] = {2: 0.55, 3: 0.30, 4: 0.15}
MULTI_MAX_BY_PROFILE: Dict[str, int] = {"light": 2, "typical": 3, "dense": 4, "case_file": 4}

# Planned items (values, clauses, names, dates, planted negatives) a document of each
# profile may hold, extra clause instances included. Measured before instances existed, a
# document's items had median 8 (light), 13-14 (typical), 23-25 (dense) and 36-37 (case
# file), so each ceiling leaves room for about three to a dozen further clauses; a case file
# stays under the section planner's eight sections of seven (`gendoc_sections.MAX_SECTIONS
# * MAX_ITEMS` = 56) with room for a repair. Each budget was then raised by the role words a
# profile's cast brings (one for the signatory and one per professional in the cast: 1, 2, 3, 4
# and 4 for minimal to case file), so the room for further clause instances is what it was.
PROFILE_ITEM_BUDGET: Dict[str, int] = {
    "pii_free": 0, "near_miss_only": 0, "minimal": 7, "light": 14, "typical": 20, "dense": 38, "case_file": 54,
}


def item_budget(profile: str, length_max: int) -> int:
    """Return how many planned items one document may hold, extra clause instances included.

    Args:
        profile: Density profile name.
        length_max: Upper bound of the document's length band, in characters.

    Returns:
        The smaller of the profile's budget and what the length can carry at about
        eighty characters an item.
    """
    return min(PROFILE_ITEM_BUDGET[profile], max(6, length_max // 80))


def draw_instance_counts(rng: random.Random, genre: str, profile: str) -> Dict[str, int]:
    """Draw how many instances of each repeatable type a document plans.

    The draw happens at plan time, so it is a batch property like density: every retry
    of a document keeps the counts it was planned with, and a run can report the
    histogram it aimed for. Only counts above one are returned.

    Args:
        rng: Run-level RNG.
        genre: Genre id.
        profile: Density profile name.

    Returns:
        `{type: count}` with count in 2..4, empty for most documents.
    """
    base = MULTI_BASE_P.get(profile, 0.0)
    cap = MULTI_MAX_BY_PROFILE.get(profile, 1)
    counts: Dict[str, int] = {}
    for etype in sorted(MULTI_PROPENSITY.get(genre, {})):
        # The roll is always taken, so adding a genre or a type to the table does not
        # shift the draws of the types after it.
        roll_repeat, roll_count = rng.random(), rng.random()
        if cap < 2 or roll_repeat >= base * MULTI_PROPENSITY[genre][etype]:
            continue
        options = [(n, w) for n, w in MULTI_COUNT_WEIGHTS.items() if n <= cap]
        roll_count *= sum(w for _n, w in options)
        for n, w in options:
            roll_count -= w
            if roll_count <= 0:
                break
        counts[etype] = n
    return counts


# Genres that are letters, decisions or reports about a named person, and so open with an
# identification block that carries the person's address. The gold set has an address
# block in nearly every such document; pilot v4's generated ones had it in a quarter. A
# circular, a contract text with no data subject and a PII-free or minimal document are
# not in the set or are excluded by profile in `generate_documents.plan_batch`.
ID_BLOCK_GENRES = {
    "gp_referral", "hospital_discharge", "occupational_health", "psychologist_note",
    "police_report", "prosecution_decision", "court_judgment", "restraining_order",
    "nav_decision", "sickness_followup", "debt_counselling", "tax_assessment", "inkasso_notice",
    "bank_aml", "ppt_assessment", "school_incident", "admission_decision", "barnevern_concern",
    "barnevern_care_plan", "employment_contract", "dismissal_letter", "hr_grievance",
    "housing_application", "tenancy_dispute", "udi_decision", "udi_correspondence",
    "forsvaret_clearance", "mattilsynet_inspection", "vet_clinical_record",
}

# Types that only a non-Norwegian subject can coherently carry. Coverage
# scheduling forces them, so the sampler makes the subject foreign rather than
# dropping the type when the genre's `foreign_subject_p` comes up short.
FOREIGN_SUBJECT_TYPES = {"IMMIGRATION_STATUS", "VISA_NUMBER"}

# Types a minor cannot coherently carry: a firearms licence is issued from age 18
# (a hunter's course at 16 gives no licence of its own). The sampler keeps the
# subject an adult when one is scheduled, and refuses the type for a minor
# otherwise; no youth-profile genre hosts it.
ADULT_ONLY_TYPES = {"FIREARMS_LICENSE"}


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
    "FIREARMS_LICENSE": "Våpenkortnummer", "VESSEL_REGISTRATION": "Registreringsmerke",
}

# Nynorsk spellings that differ. The label is a prompt hint, not a value that
# must appear verbatim, but a bokmål field name in a nynorsk document is the
# kind of detail that makes generated Norwegian read as generated.
FIELD_LABELS_NN: Dict[str, str] = {
    "PERSON": "Namn", "ORGANIZATION": "Verksemd", "LICENSE_PLATE": "Køyretøy, reg.nr.",
    "DRIVER_LICENSE": "Førarkortnummer", "USERNAME": "Brukarnamn",
    "NATIONALITY": "Statsborgarskap", "URL": "Nettstad", "MILITARY_ID": "Tenestenummer",
    "ANIMAL_INFO": "Dyrehald", "LOCATION": "Stad", "DEVICE_ID": "Einingsidentifikator",
    "SOCIAL_MEDIA": "Konto i sosiale medium",
}


# Several names exist for the same number in real documents, and the prompt's label
# word steers which one the model writes. Both forms spell these alike
# (`våpenkortnummer`, `lisensnummer`, `reg.nr.`, `registreringsmerke` are the same
# word in nynorsk); the table is per form anyway so a spelling that diverges has a
# place to go. `registreringsnummer` is generic, so its entry carries the register
# in the label itself.
FIELD_LABEL_VARIANTS: Dict[str, Dict[str, List[str]]] = {
    "FIREARMS_LICENSE": {
        "nb": ["Våpenkortnummer", "Våpenkortnummer", "Lisensnummer",
               "Registreringsnummer i våpenregisteret"],
        "nn": ["Våpenkortnummer", "Våpenkortnummer", "Lisensnummer",
               "Registreringsnummer i våpenregisteret"],
    },
    "VESSEL_REGISTRATION": {
        "nb": ["Reg.nr. (fiskefartøy)", "Registreringsmerke", "Registreringsmerke (fiskefartøy)"],
        "nn": ["Reg.nr. (fiskefartøy)", "Registreringsmerke", "Registreringsmerke (fiskefartøy)"],
    },
}


def field_label_variant(rng: random.Random, etype: str, form: str) -> str:
    """Return a field label for a type, drawn from its variants when it has any."""
    variants = FIELD_LABEL_VARIANTS.get(etype)
    if variants:
        return rng.choice(variants[form])
    return field_label(etype, form)


def field_label(etype: str, form: str) -> str:
    """Return the Norwegian field label for a type in the document's written form."""
    if form == "nn" and etype in FIELD_LABELS_NN:
        return FIELD_LABELS_NN[etype]
    return FIELD_LABELS.get(etype, etype)


def genre_names() -> List[str]:
    """Return the list of implemented genre ids."""
    return list(GENRES.keys())


def genres_hosting(etype: str, clause_bank: Optional[dict] = None) -> List[str]:
    """Return every genre whose core, optional values or judgement mix may carry a type.

    This is what batch-level coverage scheduling schedules against: a type is
    only ever forced into a document whose genre a real Norwegian equivalent
    would plausibly carry it in.

    A genre that lists a clause type is not enough on its own. Pilot v3 listed
    BIOMETRIC_DATA under `hospital_discharge`, whose clause genre is
    `gp_referral`, and the bank held no BIOMETRIC_DATA clause for `gp_referral`
    at all: the scheduler forced the type into that genre and the sampler dropped
    it silently. With a `clause_bank`, a clause type is hosted only where the bank
    holds at least one entry in each written form, of the subject the genre draws:
    a person's clause, or for the types a genre lists in `animal_types` (the findings
    of a veterinary record) an animal's.

    Args:
        etype: Entity type name.
        clause_bank: The flat clause bank (or one dataset's share of it) to check
            clause types against; None skips the check.

    Returns:
        Genre ids, in catalogue order.
    """
    hosts = []
    for name, spec in GENRES.items():
        if etype in spec["core"] or etype in spec["values"] or etype in spec["judgement"]:
            if etype == "ETHNICITY" and name not in ETHNICITY_ALLOWED_GENRES:
                continue
            if clause_bank is not None and etype in clause_bank and etype != "negatives":
                genres = set(spec["clause_genres"])
                # A clause defaults to adult subjects (`age_range` [18, 120]), so a
                # genre whose subject is a child hosts only clauses that name a
                # younger range, and a genre that clamps its subject to working
                # age hosts none that need 75+. Without this the scheduler forced
                # ETHNICITY, GENETIC_DATA and ACADEMIC_RECORD into school
                # assessments and the sampler found nothing that fitted a
                # twelve-year-old.
                band_lo, band_hi = (0, 17) if spec.get("age_profile") == "youth" else spec.get(
                    "subject_age", (18, 120))
                want_subject = "animal" if etype in spec.get("animal_types", ()) else "person"
                forms = {e["form"] for e in clause_bank[etype]
                         if genres & set(e.get("genres", []))
                         and e.get("subject", "person") == want_subject
                         and e.get("age_range", [18, 120])[0] <= band_hi
                         and e.get("age_range", [18, 120])[1] >= band_lo}
                if not {"nb", "nn"} <= forms:
                    continue
            hosts.append(name)
    return hosts


def coverage_types(taxonomy_types: Sequence[str]) -> List[str]:
    """Return the types coverage scheduling should aim to cover, in scheduling order.

    Excludes anything no genre hosts, and puts the
    hardest-to-place types first so they get the documents they need before the
    easy ones use the budget up.

    Args:
        taxonomy_types: Every type name in the taxonomy.

    Returns:
        Schedulable type names, rarest host set first.
    """
    schedulable = [t for t in taxonomy_types
                   if genres_hosting(t)]
    return sorted(schedulable, key=lambda t: (len(genres_hosting(t)), t))
