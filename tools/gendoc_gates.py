"""Validation gates for the synthetic document generator (G2-G7 of the spec).

`docs/PROJECT_SPEC_V2.md` Section 3 and `docs/SYNTHETIC_DATA_SPEC.md` Section 7
both insist the "labels correct by construction" guarantee is not enough on its
own: it guarantees every emitted span is real, not that the set of spans is
complete, diverse or safe. These gates check the things construction does not
guarantee automatically:

* G2 -- every value the record planned actually landed in the text verbatim.
* G3 -- no generated or model-invented name collides with a real public figure.
* G4 -- every Tier A span still has the right format/checksum after generation.
* G6 -- the corpus is not secretly one template (skeleton hashing + near-dup).
* G7 -- the model did not invent PII that was never planned and never labeled.

G1 (schema validation via `tools/validate_labels.py`), G5 (distribution vs
plan) and G8 (sample dump) are orchestrated directly in
`tools/generate_documents.py` since they operate over the whole batch rather
than one document; they are documented here for completeness of the gate list.

`docs/SYNTHETIC_DATA_SPEC.md` Section 7.6 says diversity should be checked by
"skeleton-hashing the output the way tools/sample_gold.py does -- digits to #,
capitalised tokens to N". `tools/sample_gold.py` does not actually do this: it
hashes the raw document text with plain md5, with no normalisation. That
normalising skeleton hash is implemented fresh here to match what the spec
describes; see the final report for this discrepancy.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Sequence, Set, Tuple

_DIGIT_RE = re.compile(r"\d")
_CAP_WORD_RE = re.compile(r"\b[A-ZÆØÅ][a-zæøå]+\b")


def skeleton(text: str) -> str:
    """Normalise a document to its structural skeleton: digits to '#', caps to 'N'."""
    collapsed = _DIGIT_RE.sub("#", text)
    collapsed = _CAP_WORD_RE.sub("N", collapsed)
    return re.sub(r"\s+", " ", collapsed).strip()


def skeleton_hash(text: str) -> str:
    """Return the md5 digest of a document's skeleton, for diversity checks."""
    return hashlib.md5(skeleton(text).encode("utf-8")).hexdigest()


def word_ngrams(text: str, n: int = 5) -> Set[Tuple[str, ...]]:
    """Return the set of lowercase word n-grams in a document."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: Set, b: Set) -> float:
    """Return the Jaccard similarity of two sets, 1.0 if both are empty."""
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


# -- G2: verbatim presence -----------------------------------------------------

def gate_verbatim(planned: Sequence[str], text: str) -> Tuple[bool, List[str]]:
    """Check that every planned value string is a verbatim substring of the text.

    Args:
        planned: The literal value/clause strings the record required.
        text: The generated document, after marker stripping.

    Returns:
        Tuple of (all present, list of the ones that are missing).
    """
    missing = [value for value in planned if value not in text]
    return not missing, missing


# -- G3: real-person name collision ---------------------------------------------

_STOPWORD_FIRST = {
    "Han", "Hun", "Det", "Vi", "Jeg", "De", "Denne", "Dette", "Disse", "Under",
    "Etter", "Før", "Ved", "Som", "Der", "Da", "Når", "Hvis", "Mens", "For",
    "Med", "Om", "Til", "Fra", "På", "Og", "Men", "Så", "Vår", "Deres",
    "Herved", "Vedrørende", "Gjelder", "Se", "Jf", "Ref", "Punkt", "Vedlegg",
    "Januar", "Februar", "Mars", "April", "Mai", "Juni", "Juli", "August",
    "September", "Oktober", "November", "Desember", "Mandag", "Tirsdag",
    "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag", "Kapittel", "Del",
}

_NAME_BIGRAM_RE = re.compile(r"\b([A-ZÆØÅ][a-zæøå'\-]+)\s+([A-ZÆØÅ][a-zæøå'\-]+)\b")
_CAP_RUN_RE = re.compile(r"\b[A-ZÆØÅ][a-zæøå'\-]+(?:\s+[A-ZÆØÅ][a-zæøå'\-]+)+\b")

# Field-header vocabulary that regularly sits adjacent to a real labeled span
# (e.g. "... Hansen Adresse: ..." or "Postnummer: 5020 Deres ref: ...") and
# would otherwise register as a false-positive name or postal-code hit purely
# because a bigram or digit-run regex spills one word past the labeled span's
# boundary. Measured on gold documents during development: these words
# accounted for roughly half of all G7 findings on real Norwegian text.
_FIELD_LABEL_WORDS = {
    "Deres", "Vår", "Org", "Ref", "Referanse", "Adresse", "Address",
    "Personalia", "Postnummer", "Poststed", "Fylke", "Kommune", "Telefon",
    "Dato", "Saksnummer", "Sendt", "Nei", "Ja", "Kl", "Sak", "Vedlegg",
    "Att", "Gjelder", "Navn", "Fødselsnummer", "Kontonummer",
}

# Institution-name suffixes: "X Sykehus", "X Kommune" etc. are organisations
# or places, not person names, even though both words are capitalised.
_INSTITUTION_SUFFIXES = {
    "Sykehus", "Kommune", "Fylke", "Fylkeskommune", "Politidistrikt",
    "Tingrett", "Skole", "Skule", "Barnehage", "Legekontor", "Legevakt",
    "Universitet", "Høgskole", "Høgskule", "Sykehjem", "Fengsel", "Rådhus",
}


def gate_name_collision(
    person_full_names: Iterable[str], text: str, public_figures: Set[str],
    place_names: Set[str], agency_names: Set[str],
) -> Tuple[bool, List[str]]:
    """Check for a real public figure's name among the generated or invented names.

    Two checks: the sampled person's own full name against the public-figure
    list (should never trigger by construction, checked anyway as a backstop),
    and every capitalised bigram the model wrote, in case it invented a name
    that happens to collide.

    Args:
        person_full_names: Full names sampled for this document's people.
        text: The generated document text.
        public_figures: Embedded set of real public figures' full names.
        place_names: Known place names (postal pairs), excluded from the sweep.
        agency_names: Known agency/organisation names, excluded from the sweep.

    Returns:
        Tuple of (no collision found, list of colliding names).
    """
    hits = [name for name in person_full_names if name in public_figures]
    # Many public figures have three-word names (`Jonas Gahr Støre`, `Kjell
    # Ingolf Ropstad`), so a plain bigram scan misses roughly a third of the
    # embedded list -- it only ever sees the first two words of a longer run.
    # Scan maximal runs of consecutive capitalised words instead, and check
    # every contiguous sub-sequence of length >= 2 against the public-figure
    # set, so a two- or three-word collision is caught regardless of where in
    # the run it falls.
    for run_match in _CAP_RUN_RE.finditer(text):
        words = run_match.group(0).split()
        for i in range(len(words)):
            for j in range(i + 2, len(words) + 1):
                candidate = " ".join(words[i:j])
                if candidate in public_figures:
                    hits.append(candidate)
    return not hits, sorted(set(hits))


# -- G4: identifier format/checksum ---------------------------------------------

def gate_identifier_checksums(
    tier_a_findings: List[dict],
) -> Tuple[bool, List[dict]]:
    """Check that every Tier A finding's declared validity matches its actual checksum.

    Args:
        tier_a_findings: List of `{"type", "value", "declared_valid", "actual_valid"}`.

    Returns:
        Tuple of (all consistent, the findings whose declared/actual disagree).
    """
    bad = [f for f in tier_a_findings if f["declared_valid"] != f["actual_valid"]]
    return not bad, bad


# -- G6: diversity ----------------------------------------------------------------

def gate_near_duplicate(
    text: str, ngrams: Set[Tuple[str, ...]], recent_ngrams: List[Set[Tuple[str, ...]]],
    threshold: float = 0.7,
) -> Tuple[bool, float]:
    """Check a document's 5-gram Jaccard similarity against previously accepted ones.

    Args:
        text: The candidate document (unused directly, kept for signature clarity).
        ngrams: This document's word 5-gram set.
        recent_ngrams: 5-gram sets of already-accepted documents.
        threshold: Similarity above which the document counts as a near-duplicate.

    Returns:
        Tuple of (is acceptable i.e. not a near-duplicate, worst similarity found).
    """
    worst = 0.0
    for other in recent_ngrams:
        score = jaccard(ngrams, other)
        worst = max(worst, score)
        if worst >= threshold:
            break
    return worst < threshold, worst


# -- G7: unplanned PII sweep -----------------------------------------------------

TIER_A_PATTERNS: Dict[str, re.Pattern] = {
    "fnr_like": re.compile(r"(?<!\d)\d{11}(?!\d)"),
    "org_like": re.compile(r"(?<!\d)\d{9}(?!\d)"),
    "phone_like": re.compile(
        r"(?<!\d)(?:\+47[\s-]?)?(?:\d{2}[\s-]?){3}\d{2}(?!\d)"
    ),
    "email_like": re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w{2,}\b"),
    "date_like": re.compile(
        r"\b\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}\b"
        r"|\b\d{1,2}\.\s?[a-zA-ZæøåÆØÅ]+\s?\d{4}\b"
    ),
    "postal_like": re.compile(r"\b(\d{4})\s+([A-ZÆØÅ][a-zæøå]+)\b"),
    "plate_like": re.compile(r"\b[A-Z]{2}\s?\d{5}\b"),
    "iban_like": re.compile(r"\bNO\d{2}\s?(?:\d{4}\s?){2}\d{3}\b"),
    "url_like": re.compile(r"https?://\S+|\bwww\.\S+"),
    "ip_like": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def _covered_intervals(text: str, spans: Iterable[str]) -> List[Tuple[int, int]]:
    """Return every (start, end) interval covered by a known labeled span."""
    intervals = []
    for span in spans:
        if not span:
            continue
        start = text.find(span)
        while start >= 0:
            intervals.append((start, start + len(span)))
            start = text.find(span, start + 1)
    return intervals


def _is_covered(start: int, end: int, intervals: List[Tuple[int, int]]) -> bool:
    return any(lo <= start and end <= hi for lo, hi in intervals)


def _is_sentence_initial(text: str, pos: int) -> bool:
    """Return whether position `pos` starts a sentence (or the document).

    Any word is capitalised at a sentence's start, so a bigram whose first
    word sits there (`"Personen Ola ..."` at the very start of a document, or
    right after a full stop) is capitalisation noise, not a name signal --
    this is one of the two false-positive sources the project's own spec
    calls out by name for the G7 name pass, alongside agency/place names.
    """
    before = text[:pos].rstrip()
    return not before or before[-1] in ".!?\n"


def sweep_tier_a(text: str, covered: List[Tuple[int, int]]) -> List[dict]:
    """Find Tier A-shaped substrings not covered by any known labeled span."""
    findings = []
    for name, pattern in TIER_A_PATTERNS.items():
        for m in pattern.finditer(text):
            if name == "postal_like" and m.group(2) in _FIELD_LABEL_WORDS:
                continue
            if not _is_covered(m.start(), m.end(), covered):
                findings.append({"pattern": name, "match": m.group(0), "start": m.start(), "end": m.end()})
    return findings


def sweep_names(
    text: str, covered: List[Tuple[int, int]], place_names: Set[str],
    agency_names: Set[str],
) -> List[dict]:
    """Find capitalised-bigram name-like strings not covered by a known span.

    Excludes agency names, known place names, and bigrams starting with a
    stopword (pronouns, prepositions, month/weekday names) as a proxy for
    sentence-initial or non-name capitalisation.

    Args:
        text: The generated document text.
        covered: Intervals already covered by a known labeled span.
        place_names: Known place names to exclude (addresses, postal pairs).
        agency_names: Known agency/organisation names to exclude.

    Returns:
        List of finding dicts for bigrams that look like an unplanned name.
    """
    findings = []
    for m in _NAME_BIGRAM_RE.finditer(text):
        first, second = m.group(1), m.group(2)
        candidate = f"{first} {second}"
        if _is_sentence_initial(text, m.start()):
            continue
        if first in _STOPWORD_FIRST:
            continue
        if first in _FIELD_LABEL_WORDS or second in _FIELD_LABEL_WORDS:
            continue
        if second in _INSTITUTION_SUFFIXES:
            continue
        if candidate in agency_names or first in agency_names or second in agency_names:
            continue
        if candidate in place_names or first in place_names or second in place_names:
            continue
        if _is_covered(m.start(), m.end(), covered):
            continue
        findings.append({"pattern": "name_bigram", "match": candidate, "start": m.start(), "end": m.end()})
    return findings


def gate_unplanned_pii(
    text: str, covered_spans: Iterable[str], place_names: Set[str],
    agency_names: Set[str],
) -> Tuple[bool, List[dict]]:
    """Run the full G7 sweep and report anything not covered by a planned span.

    Args:
        text: The generated document text (after marker stripping).
        covered_spans: All planned/labeled span strings for this document.
        place_names: Known place names to exclude from the name pass.
        agency_names: Known agency names to exclude from the name pass.

    Returns:
        Tuple of (clean i.e. no findings, list of findings).
    """
    intervals = _covered_intervals(text, covered_spans)
    findings = sweep_tier_a(text, intervals)
    findings += sweep_names(text, intervals, place_names, agency_names)
    return not findings, findings
