"""Sectioned generation: plan a long document as a few short sections, one model call each.

Pilot v4 asked Qwen3.5-9B for a whole dense or case-file document in one call. The
model is reliable with roughly eight values per call and falls apart at twenty or
more: of 26 dense and case-file documents planned, six were accepted, because a
planned value was missing in 97 attempts (usually one or two of thirty), the
targeted repair worked ten times in fifty-five, 21 attempts ran out of tokens, and
a run took 232 seconds per requested document. The six survivors are not a sample
of the dense documents: they are the easy ones, so the "hard" benchmark was easier
than planned.

The fix is not a better prompt for the whole document, it is a smaller task. This
module plans the split and leaves everything that needs a backend call to
`tools/generate_documents.py`:

* **A section plan per genre.** Three to five neutral, genre-realistic roles in
  order -- for a police report the personalia and introduction, the course of
  events, the background and the assessment; for a NAV decision the background, the
  facts of the case, the assessment and the decision; for a case file the intake,
  the other parties, the findings, the assessment and the decision. Headings come
  from a catalogue, in Bokmål and in Nynorsk, and are checked against the G9
  lexicon (`gendoc_gates._CATEGORY_LABEL_RE`): a heading may never name what the
  paragraph under it discloses, or a detector learns to read the heading instead of
  the clause. A quarter of the documents drop the visible headings and let the
  sections flow as paragraphs, so "a heading precedes the sensitive sentence" does
  not become a pattern either.
* **Assignment of the planned items.** At most `MAX_ITEMS` per section, and each
  section's share roughly even. Identifiers and personalia go early; offences and
  background history to the history or background section; findings and health to
  the findings section; assessments late; the signatory last; a cast member's
  values, and any value that contains another person's name, stay together in the
  section where that person acts. Planted negatives sit among the assessments and
  the facts, where a refusal or a remark belongs.
* **The text a section call sees.** The previous sections, truncated from the
  oldest end but with the first section always kept, so the model neither repeats
  nor contradicts what is already written.

Labels are still located by exact search over the joined text, so the by-construction
guarantee does not change; sectioning only changes how the text came to exist. What
it adds is a place to fail: a missing value is a missing value *in section 3*, and
section 3 alone is repaired or regenerated.
"""

from __future__ import annotations

import collections
import math
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import gendoc_gates as gates

SECTION_PROFILES = {"dense", "case_file"}
SECTION_ITEM_THRESHOLD = 10  # a plan with more planned items than this is sectioned in any profile
TARGET_ITEMS = 5
MAX_ITEMS = 7
MIN_SECTIONS = 3
MAX_SECTIONS = 8
HEADERLESS_SHARE = 0.25
HEADER_CONTEXT_CHARS = 1500
CONTEXT_BUDGET_CHARS = 3200

# -- The catalogue: what a section is for, and what it may be called ---------------

# kind -> Bokmål headings, Nynorsk headings, then what the section covers (Bokmål,
# Nynorsk). The first heading is the default; the others are used when a document
# holds the same kind twice, and a random one is drawn per document so one heading
# does not become a pattern. Not one of them names a category of information.
KINDS: Dict[str, dict] = {
    "intro": {
        "nb": ["Innledning", "Personalia", "Opplysninger om saken"],
        "nn": ["Innleiing", "Personalia", "Opplysningar om saka"],
        "desc_nb": "innledningen: hvem saken gjelder, med identifiserende opplysninger, og hva dokumentet handler om",
        "desc_nn": "innleiinga: kven saka gjeld, med identifiserande opplysningar, og kva dokumentet handlar om"},
    "background": {
        "nb": ["Bakgrunn", "Bakgrunn for saken", "Videre bakgrunn"],
        "nn": ["Bakgrunn", "Bakgrunn for saka", "Vidare bakgrunn"],
        "desc_nb": "bakgrunnen for saken, i løpende prosa",
        "desc_nn": "bakgrunnen for saka, i løpande prosa"},
    "facts": {
        "nb": ["Saksforhold", "Nærmere om saken", "Videre opplysninger"],
        "nn": ["Saksforhold", "Nærare om saka", "Vidare opplysningar"],
        "desc_nb": "saksforholdet: de konkrete opplysningene saken bygger på",
        "desc_nn": "saksforholdet: dei konkrete opplysningane saka byggjer på"},
    "events": {
        "nb": ["Hendelsesforløp", "Hendelsen", "Det som skjedde videre"],
        "nn": ["Hendingsforløp", "Hendinga", "Det som skjedde vidare"],
        "desc_nb": "forløpet: hva som har skjedd, i den rekkefølgen det skjedde",
        "desc_nn": "forløpet: kva som har skjedd, i den rekkjefølgja det skjedde"},
    "history": {
        "nb": ["Bakgrunnsopplysninger", "Tidligere kontakt", "Tidligere opplysninger"],
        "nn": ["Bakgrunnsopplysningar", "Tidlegare kontakt", "Tidlegare opplysningar"],
        "desc_nb": "opplysninger og tidligere kontakt som har betydning for saken",
        "desc_nn": "opplysningar og tidlegare kontakt som har betydning for saka"},
    "observations": {
        "nb": ["Funn", "Undersøkelser", "Videre funn"],
        "nn": ["Funn", "Undersøkingar", "Vidare funn"],
        "desc_nb": "funn og undersøkelser slik de er gjort",
        "desc_nn": "funn og undersøkingar slik dei er gjorde"},
    "parties": {
        "nb": ["Involverte", "Andre i saken", "Kontaktpersoner"],
        "nn": ["Involverte", "Andre i saka", "Kontaktpersonar"],
        "desc_nb": "de andre som er involvert i saken og hvilken rolle de har",
        "desc_nn": "dei andre som er involverte i saka og kva rolle dei har"},
    "assessment": {
        "nb": ["Vurdering", "Samlet vurdering", "Saksbehandlerens vurdering"],
        "nn": ["Vurdering", "Samla vurdering", "Sakshandsamaren si vurdering"],
        "desc_nb": "vurderingen: en saklig vurdering på grunnlag av det som står i tidligere deler",
        "desc_nn": "vurderinga: ei saklig vurdering på grunnlag av det som står i tidlegare delar"},
    "decision": {
        "nb": ["Vedtak", "Konklusjon", "Avgjørelse"],
        "nn": ["Vedtak", "Konklusjon", "Avgjerd"],
        "desc_nb": "vedtaket eller konklusjonen, med begrunnelse og klageadgang der sjangeren krever det",
        "desc_nn": "vedtaket eller konklusjonen, med grunngjeving og klagerett der sjangeren krev det"},
    "follow_up": {
        "nb": ["Videre oppfølging", "Oppfølging", "Veien videre"],
        "nn": ["Vidare oppfølging", "Oppfølging", "Vegen vidare"],
        "desc_nb": "videre oppfølging: hva som skjer videre og hvem som har ansvaret",
        "desc_nn": "vidare oppfølging: kva som skjer vidare og kven som har ansvaret"},
    "contact": {
        "nb": ["Kontakt", "Kontaktopplysninger", "Avslutning"],
        "nn": ["Kontakt", "Kontaktopplysningar", "Avslutning"],
        "desc_nb": "avslutningen: hvem som har skrevet dokumentet, og hvordan man tar kontakt",
        "desc_nn": "avslutninga: kven som har skrive dokumentet, og korleis ein tek kontakt"},
}

# Section sequences by document family. The first element of each sequence is the
# section that holds the personalia, whatever its heading is.
FAMILIES: Dict[str, List[str]] = {
    "police": ["intro", "events", "history", "assessment"],
    "nav": ["background", "facts", "assessment", "decision"],
    "case_file": ["intro", "parties", "observations", "assessment", "decision"],
    "clinical": ["intro", "background", "observations", "assessment", "follow_up"],
    "letter": ["intro", "background", "facts", "assessment", "decision"],
    "incident": ["intro", "events", "background", "assessment", "follow_up"],
    "inspection": ["intro", "observations", "assessment", "decision"],
    "debt": ["intro", "background", "facts", "assessment", "follow_up"],
    "forensics": ["intro", "observations", "events", "assessment"],
    "request": ["intro", "background", "facts", "follow_up"],
}

# Headings a family overrides, because they are what that kind of document calls
# the section: a police report opens with "Personalia", a NAV decision does not
# have an "Innledning".
FAMILY_HEADINGS: Dict[str, Dict[str, Tuple[List[str], List[str]]]] = {
    "police": {"intro": (["Personalia", "Innledning"], ["Personalia", "Innleiing"]),
               "events": (["Hendelsesforløp", "Hendelsen"], ["Hendingsforløp", "Hendinga"]),
               "history": (["Bakgrunnsopplysninger", "Tidligere kontakt"], ["Bakgrunnsopplysningar", "Tidlegare kontakt"])},
    "nav": {"background": (["Bakgrunn", "Bakgrunn for saken"], ["Bakgrunn", "Bakgrunn for saka"]),
            "facts": (["Saksforhold"], ["Saksforhold"]),
            "decision": (["Vedtak"], ["Vedtak"])},
    "case_file": {"intro": (["Mottak av saken", "Innledning"], ["Mottak av saka", "Innleiing"]),
                  "observations": (["Funn"], ["Funn"]),
                  "decision": (["Konklusjon", "Vedtak"], ["Konklusjon", "Vedtak"])},
}

GENRE_FAMILY: Dict[str, str] = {
    "police_report": "police", "prosecution_decision": "police", "restraining_order": "police",
    "court_judgment": "police", "digital_forensics_report": "forensics",
    "nav_decision": "nav", "housing_application": "nav", "tax_assessment": "nav",
    "udi_decision": "nav", "admission_decision": "nav", "sickness_followup": "clinical",
    "gp_referral": "clinical", "hospital_discharge": "clinical", "psychologist_note": "clinical",
    "occupational_health": "clinical", "ppt_assessment": "clinical", "vet_clinical_record": "clinical",
    "barnevern_concern": "case_file", "barnevern_care_plan": "case_file",
    "forsvaret_clearance": "case_file", "whistleblowing_report": "case_file",
    "dismissal_letter": "letter", "hr_grievance": "letter", "employment_contract": "letter",
    "tenancy_dispute": "letter", "school_incident": "incident",
    "mattilsynet_inspection": "inspection", "debt_counselling": "debt", "inkasso_notice": "debt",
    "bank_aml": "debt", "udi_correspondence": "request", "admin_circular": "request",
    "anonymised_case_summary": "request", "guidance_note": "request", "statistics_note": "request",
}
DEFAULT_FAMILY = "letter"

# Where an item of a type prefers to go, best first. "intro" means the first
# section whatever it is called; "__last__" the last. Judgement types are placed
# where a real document would put them -- history and findings before the
# assessment, never in a section whose job is to decide -- and none of this is
# visible in the text, because the headings are neutral.
TYPE_PREFS: Dict[str, List[str]] = {
    "PERSON": ["intro"], "NATIONAL_ID": ["intro"], "DATE_OF_BIRTH": ["intro"], "ADDRESS": ["intro"],
    "POSTAL_CODE": ["intro"], "LOCATION": ["intro", "background"], "PHONE": ["intro", "contact"],
    "EMAIL": ["intro", "contact"], "CASE_NUMBER": ["intro", "facts"], "NATIONALITY": ["intro", "background"],
    "GENDER": ["intro"], "AGE": ["intro", "background"], "MARITAL_STATUS": ["intro", "background"],
    "DRIVER_LICENSE": ["intro", "facts"], "PASSPORT": ["intro", "facts"], "IDENTITY_CARD": ["intro", "facts"],
    "VISA_NUMBER": ["intro", "facts"], "MILITARY_ID": ["intro", "background"], "STUDENT_ID": ["intro", "background"],
    "TAX_ID": ["intro", "facts"], "INSURANCE_NUMBER": ["facts", "background"],
    "EMPLOYMENT": ["background", "history", "facts"], "ORGANIZATION": ["background", "facts"],
    "ORG_NUMBER": ["background", "facts"], "ACADEMIC_RECORD": ["background", "history"],
    "FAMILY_RELATION": ["background", "history"], "ANIMAL_INFO": ["facts", "background"],
    "CRIMINAL": ["history", "events", "background", "facts"],
    "BEHAVIORAL_PATTERN": ["history", "events", "assessment"],
    "HEALTH": ["observations", "background", "assessment"], "MEDICATION": ["observations", "assessment"],
    "DISABILITY": ["observations", "assessment", "background"], "GENETIC_DATA": ["observations", "background"],
    "BIOMETRIC_DATA": ["observations", "facts"],
    "ECONOMIC_STATUS": ["assessment", "facts", "background"], "FINANCIAL": ["facts", "background", "history"],
    "BANK_ACCOUNT": ["facts", "contact"], "IBAN": ["facts", "contact"], "CREDIT_CARD": ["facts"],
    "CRYPTO": ["facts"], "AGE_INFO": ["assessment", "background"],
    "RELIGIOUS_BELIEF": ["background", "history"], "POLITICAL": ["background", "history"],
    "TRADE_UNION": ["background", "history"], "ETHNICITY": ["background", "history"],
    "SEXUAL_ORIENTATION": ["background", "history"], "IMMIGRATION_STATUS": ["background", "facts"],
    "LICENSE_PLATE": ["events", "facts"], "FIREARMS_LICENSE": ["facts", "history"],
    "VESSEL_REGISTRATION": ["facts", "observations"], "MEDICAL_LICENSE": ["observations", "assessment", "contact"],
    "IP_ADDRESS": ["observations", "facts"], "DEVICE_ID": ["observations", "facts"],
    "USERNAME": ["observations", "facts"], "PASSWORD": ["observations"], "SOCIAL_MEDIA": ["observations", "facts"],
    "URL": ["observations", "facts"], "FAX_NUMBER": ["contact", "intro"],
}
DATE_PREFS_BY_HINT = [
    ("dokumentets dato", ["intro"]), ("frist", ["follow_up", "decision", "facts"]),
    ("tidligere", ["history", "background", "events"]), ("undersøkelse", ["observations", "events"]),
]
DEFAULT_DATE_PREFS = ["events", "facts", "background", "observations"]
CAST_PREFS: Dict[str, List[str]] = {
    "author": ["__last__"], "witness": ["events", "facts", "parties"], "co_suspect": ["events", "history", "parties"],
    "counterparty": ["events", "facts", "parties"], "spouse": ["parties", "background"],
    "child": ["parties", "background"], "parent": ["parties", "background"], "guardian": ["parties", "background"],
    "physician": ["observations", "assessment", "parties"], "psychologist": ["observations", "assessment", "parties"],
    "veterinarian": ["observations", "assessment", "parties"], "caseworker": ["follow_up", "assessment", "parties", "decision"],
    "officer": ["events", "follow_up", "parties"], "teacher": ["background", "parties", "follow_up"],
    "lawyer": ["facts", "decision", "parties"], "employer_contact": ["facts", "background", "parties"],
    "landlord": ["facts", "background", "parties"], "creditor_contact": ["facts", "history", "parties"],
}
NEGATIVE_PREFS = ["assessment", "facts", "follow_up", "events", "background"]
_BIG = 50


# -- The plan ------------------------------------------------------------------------

@dataclass
class Section:
    """One section of a sectioned document: its role, its items and its progress.

    Attributes:
        index: Position, from 0.
        kind: Key into `KINDS`.
        heading: The visible heading, or None when the document's sections flow
            as paragraphs.
        role_heading: The heading the section would carry; used in the prompt as
            its role even when no heading is printed.
        desc: What the section covers, in the document's language.
        items: Indices into `Record.planned` realised in this section.
        negatives: Indices into `Record.planted_negatives` planted in this section.
        chars: (min, max) characters the section is asked to be.
        draft: The latest generated text for the section, normalised, accepted or not;
            a targeted repair starts from it.
        raw: The accepted section text with any markers still in it.
        text: The accepted section text, markers stripped.
        attempts: Generation attempts used (the first plus regenerations).
        repairs: Targeted repairs used in the current attempt.
        repairs_total: Targeted repairs used in all attempts.
        audit_repairs: G11 repairs of this section.
        done: Whether `text` is accepted.
        log: Gate outcomes for this section.
    """

    index: int
    kind: str
    heading: Optional[str]
    role_heading: str
    desc: str
    items: List[int] = field(default_factory=list)
    negatives: List[int] = field(default_factory=list)
    chars: Tuple[int, int] = (200, 600)
    draft: str = ""
    raw: str = ""
    text: str = ""
    attempts: int = 0
    repairs: int = 0
    repairs_total: int = 0
    audit_repairs: int = 0
    done: bool = False
    log: List[dict] = field(default_factory=list)

    @property
    def load(self) -> int:
        return len(self.items) + len(self.negatives)


@dataclass
class SectionPlan:
    """The ordered sections of one document and whether their headings print.

    Attributes:
        sections: In document order.
        headings_visible: False when the sections flow as paragraphs.
        family: The family whose sequence was used.
        redos_after_join: Sections regenerated because the joined document failed.
    """

    sections: List[Section]
    headings_visible: bool
    family: str
    redos_after_join: int = 0


def needs_sections(profile: str, n_items: int, pii_free: bool, mode: str = "auto") -> bool:
    """Whether a document is generated in sections.

    Args:
        profile: Density profile of the plan.
        n_items: Planned values and clauses plus planted negatives.
        pii_free: A PII-free document has nothing to split.
        mode: "auto" sections dense and case-file plans and any plan above
            `SECTION_ITEM_THRESHOLD` items; "off" never does; "always" sections
            every document that plans something.

    Returns:
        True when the document should be generated section by section.
    """
    if pii_free or mode == "off" or n_items == 0:
        return False
    if mode == "always":
        return True
    return profile in SECTION_PROFILES or n_items > SECTION_ITEM_THRESHOLD


def family_for(genre: str) -> str:
    """Return the section family a genre uses."""
    return GENRE_FAMILY.get(genre, DEFAULT_FAMILY)


def _fit_sequence(sequence: List[str], n: int) -> List[str]:
    """Stretch or shrink a family's kind sequence to `n` sections, keeping its order.

    Shrinking drops the optional middle kinds first (the personalia, the
    assessment and the closing section are what make the document the genre it is);
    stretching repeats the middle kinds that carry the case itself.
    """
    seq = list(sequence)
    essential = {seq[0], "assessment", "decision", "follow_up", "contact"}
    while len(seq) > n:
        drop = next((i for i in range(len(seq) - 1, 0, -1) if seq[i] not in essential), None)
        if drop is None:
            break
        seq.pop(drop)
    stretch = [k for k in ("facts", "observations", "events", "background", "history") if k in seq]
    stretch = stretch or [k for k in seq if k not in (seq[0], seq[-1])] or [seq[0]]
    i = 0
    while len(seq) < n:
        kind = stretch[i % len(stretch)]
        seq.insert(max(j for j, k in enumerate(seq) if k == kind) + 1, kind)
        i += 1
    return seq


def _pick_headings(rng: random.Random, family: str, kinds: List[str], form: str,
                   avoid: Sequence[str] = ()) -> List[str]:
    """Choose a heading per section, never the same heading twice in one document.

    Args:
        rng: Plan RNG.
        family: Section family.
        kinds: The section kinds, in order.
        form: "nb" or "nn".
        avoid: Planted role words. A heading that holds one ("Saksbehandlerens vurdering" with a
            planted `saksbehandler`) would be an occurrence of the string away from the person's
            name, which G14 rejects; another heading of the kind is used instead.
    """
    used: Set[str] = set()
    chosen = []
    col = 0 if form == "nb" else 1
    for kind in kinds:
        override = FAMILY_HEADINGS.get(family, {}).get(kind)
        options = list(override[col]) if override else []
        options += [h for h in KINDS[kind][form] if h not in options]
        fresh = [h for h in options if h not in used] or options
        fresh = [h for h in fresh if not any(w in h.lower() for w in avoid)] or fresh
        # The first option is the one a real document of the genre uses; later ones
        # are for repeats and for variety, drawn with a bias toward the first.
        heading = fresh[0] if rng.random() < 0.6 else rng.choice(fresh)
        used.add(heading)
        chosen.append(heading)
    return chosen


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _prefs_for(pv) -> List[str]:
    party = getattr(pv, "party", None)
    if party and party != "subject":
        return CAST_PREFS.get(party, ["facts", "background", "parties"])
    if pv.type == "DATE_TIME":
        hint = pv.hint or ""
        for needle, prefs in DATE_PREFS_BY_HINT:
            if needle in hint:
                return prefs
        return DEFAULT_DATE_PREFS
    return TYPE_PREFS.get(pv.type, ["facts", "background"])


def _rank(prefs: Sequence[str], section: Section, n: int) -> int:
    best = _BIG
    for i, pref in enumerate(prefs):
        if pref == "__last__":
            hit = section.index == n - 1
        elif pref == "intro":
            hit = section.index == 0 or section.kind == "intro"
        else:
            hit = section.kind == pref
        if hit:
            best = min(best, i)
    return best if best < _BIG else len(prefs) + 3


def _bundles(record) -> List[dict]:
    """Group the record's planned items that must be realised in the same section.

    Two items are joined when one's literal text contains a person's name that is
    another item's PERSON value ("gift med Kari Hansen" with Kari Hansen herself, or
    a clause that carries a name the sampler introduced), and a cast member's values
    are joined with the member's name. Anything else is its own bundle.
    """
    planned = record.planned
    uf = _UnionFind(len(planned))
    person_at = {pv.value: i for i, pv in enumerate(planned) if pv.type == "PERSON" and pv.value}
    for i, pv in enumerate(planned):
        if not pv.value or pv.type == "PERSON":
            continue
        for name, j in person_at.items():
            if name in pv.value:
                uf.union(i, j)
    by_party: Dict[str, int] = {}
    for i, pv in enumerate(planned):
        party = getattr(pv, "party", None)
        if party and party != "subject":
            if party in by_party:
                uf.union(i, by_party[party])
            else:
                by_party[party] = i
    groups: Dict[int, List[int]] = collections.defaultdict(list)
    for i in range(len(planned)):
        groups[uf.find(i)].append(i)
    out = []
    for members in groups.values():
        lead = next((planned[i] for i in members if getattr(planned[i], "party", None) not in (None, "subject")),
                    None)
        lead = lead or next((planned[i] for i in members if planned[i].type != "PERSON"), planned[members[0]])
        out.append({"members": sorted(members), "prefs": _prefs_for(lead), "negative": False})
    for j in range(len(record.planted_negatives)):
        out.append({"members": [j], "prefs": NEGATIVE_PREFS, "negative": True})
    return out


def build_plan(record, rng: random.Random) -> SectionPlan:
    """Plan the sections of one record and assign every planned item to one.

    Args:
        record: A `generate_documents.Record` (read, not imported): `genre`,
            `form`, `length_band`, `planned` (each with `type`, `hint`, `value`,
            `party`) and `planted_negatives`.
        rng: RNG seeded from the record, so the plan is reproducible.

    Returns:
        The `SectionPlan`: between `MIN_SECTIONS` and `MAX_SECTIONS` sections, each
        holding at most `MAX_ITEMS` items where the items allow it.
    """
    n_items = len(record.planned) + len(record.planted_negatives)
    family = family_for(record.genre)
    n = max(MIN_SECTIONS, math.ceil(n_items / TARGET_ITEMS), math.ceil(n_items / MAX_ITEMS))
    n = min(n, MAX_SECTIONS)
    kinds = _fit_sequence(FAMILIES[family], n)
    n = len(kinds)
    headings = _pick_headings(rng, family, kinds, record.form,
                              [pv.value.lower() for pv in record.planned if getattr(pv, "anchor", None)])
    visible = rng.random() >= HEADERLESS_SHARE
    desc_key = "desc_nb" if record.form == "nb" else "desc_nn"
    sections = [Section(i, kind, headings[i] if visible else None, headings[i], KINDS[kind][desc_key])
                for i, kind in enumerate(kinds)]

    cap = MAX_ITEMS
    bundles = sorted(_bundles(record), key=lambda b: (-len(b["members"]), min(b["members"]), b["negative"]))
    for bundle in bundles:
        size = len(bundle["members"])

        def score(section: Section) -> float:
            over = max(0, section.load + size - cap)
            return _rank(bundle["prefs"], section, n) * 1.5 + over * 10 + (section.load + size) * 0.6

        target = min(sections, key=lambda s: (score(s), s.index))
        (target.negatives if bundle["negative"] else target.items).extend(bundle["members"])
        bundle["section"] = target.index

    # An empty section would be asked to write a page of nothing in particular; move
    # the smallest movable bundle from the heaviest section into it.
    for empty in [s for s in sections if s.load == 0]:
        donor = max(sections, key=lambda s: s.load)
        if donor.load < 4:
            break
        movable = [b for b in bundles if b["section"] == donor.index and b["prefs"] != ["__last__"]]
        if not movable:
            continue
        move = min(movable, key=lambda b: (len(b["members"]), b["members"][0]))
        src, dst = (donor.negatives, empty.negatives) if move["negative"] else (donor.items, empty.items)
        for m in move["members"]:
            src.remove(m)
            dst.append(m)
        move["section"] = empty.index

    for s in sections:
        s.items.sort()
        s.negatives.sort()
    lo, hi = record.length_band
    weights = [1.0 + s.load for s in sections]
    total = sum(weights)
    for s, w in zip(sections, weights):
        s.chars = (max(150, int(lo * w / total)), max(320, int(hi * w / total)))
    return SectionPlan(sections, visible, family)


# -- Text handling ------------------------------------------------------------------

_BULLET_PREFIX = re.compile(r"^[\s#>*_\-•·]*(?:\d+[.)]\s*)?")
_FENCE = re.compile(r"^```[\w-]*\s*\n|\n```\s*$")


def heading_candidate(line: str) -> Optional[str]:
    """Return the heading a line reads as, or None when it is a sentence, field or row.

    A heading is a short capitalised line with no sentence-ending punctuation and no
    value after a colon: what a model prints when it groups paragraphs. A line like
    `Navn: Kari Hansen` is a field, not a heading, and a table row is neither.
    """
    stripped = _BULLET_PREFIX.sub("", line).strip().strip("*_# ").rstrip(":").strip()
    if not stripped or len(stripped) > 70 or "|" in line:
        return None
    if stripped[-1] in ".!?;,":
        return None
    if ":" in stripped or not stripped[0].isupper() or len(stripped.split()) > 7:
        return None
    return stripped


def names_category(heading: str) -> bool:
    """Whether a heading names a category of information, by the G9 lexicon."""
    return bool(gates._CATEGORY_LABEL_RE.search(heading))


def body_headings(text: str) -> List[str]:
    """Return the heading-like lines of a text: short lines set apart above and followed by text."""
    lines = text.split("\n")
    found = []
    for i, line in enumerate(lines):
        candidate = heading_candidate(line)
        if candidate is None or i + 1 >= len(lines):
            continue
        if (i == 0 or not lines[i - 1].strip()) and lines[i + 1].strip():
            found.append(candidate)
    return found


def normalise_section(raw: str, heading: Optional[str]) -> Tuple[str, List[dict]]:
    """Make a section's first line what the plan says it is, and report category headings.

    The model is asked to print the planned heading as the first line, or no heading
    at all. Whatever heading-like first line it printed is dropped and the planned
    heading is put in its place (a heading carries no label, so replacing it cannot
    change which values are present); a flowing section gets no heading. A heading
    that names a category is not silently rewritten: it is reported, so the section
    is regenerated and the model is not taught that such a heading is tolerated.

    Args:
        raw: The model's output for one section.
        heading: The planned visible heading, or None for a flowing section.

    Returns:
        (the section text, problems as `{"kind": "category_heading", "heading"}`).
    """
    text = _FENCE.sub("", raw.strip()).strip()
    lines = text.split("\n")
    problems: List[dict] = []
    first = heading_candidate(lines[0]) if len(lines) > 1 else None
    if first is not None:
        if names_category(first):
            problems.append({"kind": "category_heading", "heading": first})
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    body = "\n".join(lines).strip()
    for extra in body_headings(body):
        if names_category(extra):
            problems.append({"kind": "category_heading", "heading": extra})
    if heading:
        body = f"{heading}\n\n{body}"
    return body, problems


def join_sections(texts: Sequence[str]) -> str:
    """Join section texts into the document, one blank line between sections."""
    return "\n\n".join(t.strip() for t in texts if t.strip())


def section_spans(texts: Sequence[str]) -> List[Tuple[int, int]]:
    """Return each section's (start, end) offsets in `join_sections(texts)`."""
    spans, pos = [], 0
    for t in texts:
        t = t.strip()
        if not t:
            spans.append((pos, pos))
            continue
        spans.append((pos, pos + len(t)))
        pos += len(t) + 2
    return spans


def section_at(spans: Sequence[Tuple[int, int]], offset: int) -> Optional[int]:
    """Return the index of the section containing `offset` in the joined text."""
    for i, (start, end) in enumerate(spans):
        if start <= offset < end:
            return i
    return len(spans) - 1 if spans and offset == spans[-1][1] else None


def previous_context(texts: Sequence[str], header_chars: int = HEADER_CONTEXT_CHARS,
                     budget: int = CONTEXT_BUDGET_CHARS) -> str:
    """Build the "what is already written" block for a section call.

    The first section is always kept (it carries the names, the genre's opening and
    the register), cut at a sentence end if it is longer than `header_chars`. The
    rest is added newest first until `budget` characters are used, so the oldest
    middle sections are the ones dropped; a line holding only an ellipsis marks the
    cut.

    Args:
        texts: Accepted texts of the sections before this one, in order.
        header_chars: Cap on the first section.
        budget: Cap on the whole block.

    Returns:
        The block, empty when there is nothing before.
    """
    texts = [t.strip() for t in texts if t and t.strip()]
    if not texts:
        return ""
    head = texts[0]
    if len(head) > header_chars:
        cut = head.rfind(". ", 0, header_chars)
        head = head[:cut + 1] if cut > header_chars // 2 else head[:header_chars]
    rest = texts[1:]
    kept: List[str] = []
    used = len(head)
    for t in reversed(rest):
        if used + len(t) + 2 > budget:
            break
        kept.append(t)
        used += len(t) + 2
    kept.reverse()
    parts = [head]
    if len(kept) < len(rest):
        parts.append("…")
    parts.extend(kept)
    return "\n\n".join(parts)


def repeated_section(texts: Sequence[str], n: int = 8) -> Optional[int]:
    """Return the later section that repeats earlier text most, or None.

    G12 measures repetition over the joined document; this finds which section to
    regenerate. A word n-gram counted as repeated if it occurred in an earlier
    section (or earlier in the same one); the section with the most is the one that
    repeated, since the first occurrence is where the text belongs.
    """
    seen: Set[Tuple[str, ...]] = set()
    counts = []
    for t in texts:
        words = re.findall(r"\S+", t)
        grams = [tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))]
        counts.append(sum(1 for g in grams if g in seen))
        seen.update(grams)
    if not counts or max(counts) == 0:
        return None
    return counts.index(max(counts))


def summary(plan: SectionPlan, record) -> List[dict]:
    """Describe a section plan for the metadata: roles, headings, loads, progress."""
    out = []
    for s in plan.sections:
        out.append({
            "index": s.index, "kind": s.kind, "heading": s.heading,
            "role_heading": s.role_heading, "heading_visible": s.heading is not None,
            "types": sorted({record.planned[i].type for i in s.items}),
            "items": len(s.items), "negatives": len(s.negatives),
            "band_chars": list(s.chars), "chars": len(s.text),
            "attempts": s.attempts, "repairs": s.repairs_total, "audit_repairs": s.audit_repairs,
        })
    return out


def validate_catalogue() -> List[str]:
    """Return every catalogue heading that names a category, and every unknown kind in use.

    The catalogue is the only source of headings, so checking it once is checking all
    of them. A problem here means a heading would teach a detector to read the heading.
    """
    problems = []
    for kind, entry in KINDS.items():
        for form in ("nb", "nn"):
            for heading in entry[form]:
                if names_category(heading):
                    problems.append(f"{kind}/{form}: {heading!r} names a category")
    for family, overrides in FAMILY_HEADINGS.items():
        for kind, (nb, nn) in overrides.items():
            for heading in nb + nn:
                if names_category(heading):
                    problems.append(f"{family}/{kind}: {heading!r} names a category")
    for family, sequence in FAMILIES.items():
        problems += [f"{family}: unknown kind {k!r}" for k in sequence if k not in KINDS]
    problems += [f"{genre}: unknown family {family!r}" for genre, family in GENRE_FAMILY.items()
                 if family not in FAMILIES]
    return problems
