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

import gendoc_data as data

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

# `[ \t]` rather than `\s` throughout this module: a name never spans a line
# break, and the first pilot's G7 hits were dominated by matches that did
# (`2024\nMottaker` read as a postal code and place).
_CAP_RUN_RE = re.compile(r"\b[A-ZÆØÅ][a-zæøå'\-]+(?:[ \t]+[A-ZÆØÅ][a-zæøå'\-]+)+\b")

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


# Template residue an instruct model leaves when it has no value to hand:
# `[Navn saksbehandler]`, `<dato>`, `XXX`, `NN`, `(sett inn ...)`. Real PII
# would sit where these are, so a document carrying one teaches the detector
# that an empty slot is normal.
_PLACEHOLDER_RE = re.compile(
    r"\[[^\[\]\n]{2,60}\]"
    r"|<[^<>\n]{2,40}>"
    r"|\b(?:X{3,}|x{3,}|N\.N\.|NN)\b"
    r"|\((?:sett inn|fyll inn|set inn)[^)]*\)"
    r"|\{[A-Z_]{3,}\}",
    re.IGNORECASE,
)


def gate_placeholders(text: str) -> Tuple[bool, List[str]]:
    """Reject documents containing unfilled template placeholders.

    Markdown links and footnote-style references such as `[1]` are not
    placeholders and are ignored.

    Args:
        text: Generated document after marker stripping.

    Returns:
        Tuple of (passed, list of placeholder strings found).
    """
    hits = []
    for m in _PLACEHOLDER_RE.finditer(text):
        token = m.group(0)
        if re.fullmatch(r"\[\d{1,2}\]", token):
            continue
        if token.startswith("[") and text[m.end():m.end() + 1] == "(":
            continue
        hits.append(token)
    return not hits, hits


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
#
# The first real pilot (data/synthetic/pilot_v1) failed 23 of 39 retries on G7,
# and reading the hits showed most were not PII: regexes that ran across a line
# break (`2024\nMottaker` as a postal code), union and bank names read as a
# first name plus a surname (`Norsk Sykepleierforbund`, `Bank Norwegian`), and
# a role title next to an ordinary noun (`Forvaltningsansvarlig Offentlig`).
# The genuine catches were invented people and invented dates. So the sweep now
# (a) never crosses a newline, (b) treats organisations as organisations, (c)
# only calls something a name when it has name evidence -- a known given name,
# an honorific, or a role title in front of a surname -- and (d) says what to do
# with each hit. `docs/PROJECT_SPEC_V2.md` Section 3.1 allows an unplanned
# value to be labelled instead of regenerated; that is safe exactly when the
# span boundary is unambiguous, which holds for a full name, an honorific plus
# surname (B21 in docs/ANNOTATION_SPEC.md) and a date, and does not hold for a
# role title plus bare surname or for an unplanned identifier, whose owner and
# type the sweep cannot know.

_MONTHS = "januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember"
_MONTH_ABBR = "jan|feb|mar|apr|jun|jul|aug|sep|sept|okt|nov|des"

TIER_A_PATTERNS: Dict[str, re.Pattern] = {
    "fnr_like": re.compile(r"(?<![\d.])\d{6}[ \t]?\d{5}(?!\d)"),
    "org_like": re.compile(r"(?<![\d.])(?:\d{9}|\d{3} \d{3} \d{3})(?!\d)"),
    "account_like": re.compile(r"(?<!\d)\d{4}\.\d{2}\.\d{5}(?!\d)"),
    "phone_like": re.compile(
        r"(?<![\d/.,])(?:\+47[ \t-]?)?"
        r"(?:[2-9]\d{7}|\d{2}(?:[ \t-]\d{2}){3}|\d{3}[ \t]\d{2}[ \t]\d{3}|\d{4}[ \t]\d{4})"
        r"(?![\d/])"
    ),
    "email_like": re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w{2,}\b"),
    "postal_like": re.compile(r"(?<![\d.,/\-])(\d{4})[ \t]+([A-ZÆØÅ][a-zæøå]+)\b"),
    "plate_like": re.compile(r"\b[A-Z]{2}[ \t]?\d{5}\b"),
    "iban_like": re.compile(r"\bNO\d{2}[ \t]?(?:\d{4}[ \t]?){2}\d{3}\b"),
    "url_like": re.compile(r"https?://\S+|\bwww\.\S+"),
    "ip_like": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

DATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?<![\d.])\d{1,2}\.[ \t]?\d{1,2}\.[ \t]?(?:\d{4}|\d{2})(?!\d)(?!\.\d)"),
    re.compile(rf"(?<!\d)\d{{1,2}}\.[ \t]?(?:{_MONTHS}|(?:{_MONTH_ABBR})\.?)[ \t]+\d{{4}}\b", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}-[01]\d-[0-3]\d\b"),
]

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_WORD_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|['’\-])*")
_HONORIFIC_STEMS = {h.rstrip("."): h for h in data.HONORIFICS}
_ROLE_TITLES = set(data.ROLE_TITLES)
_FIRST_NAMES = (
    set(data.FIRST_NAMES_MALE) | set(data.FIRST_NAMES_FEMALE) | set(data.EXTRA_FIRST_NAMES)
    | {n for m, f, _s in data.FOREIGN_NAMES.values() for n in m + f}
)
_SURNAMES = set(data.SURNAMES) | {s for _m, _f, ss in data.FOREIGN_NAMES.values() for s in ss}
_LOWER_ROLE_SURNAME_RE = re.compile(
    r"(?<![\w-])(" + "|".join(sorted((re.escape(r) for r in _ROLE_TITLES), key=len, reverse=True))
    + r")[ \t]+([A-ZÆØÅ][a-zæøå'\-]+)(?:[ \t]+([A-ZÆØÅ][a-zæøå'\-]+))?"
)


def _is_surname_like(token: str) -> bool:
    if token in _SURNAMES:
        return True
    low = token.lower()
    return len(token) >= 4 and token[0].isupper() and low.endswith(data.SURNAME_SUFFIXES)


def _strip_genitive(token: str) -> str:
    """Return a name token without a genitive -s when the bare form is a name."""
    if token.endswith("s") and len(token) > 3:
        bare = token[:-1]
        if bare in _FIRST_NAMES or _is_surname_like(bare):
            return bare
    return token


def _is_org_run(tokens: List[str]) -> bool:
    last = tokens[-1]
    if last in data.ORG_FORM_CODES:
        return True
    return any(t.lower().endswith(data.ORG_SUFFIX_WORDS) or t in _INSTITUTION_SUFFIXES
               for t in tokens[1:] or tokens)


def _masked_intervals(text: str, names: Iterable[str]) -> List[Tuple[int, int]]:
    intervals = []
    for name in names:
        if not name:
            continue
        for m in re.finditer(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text):
            intervals.append((m.start(), m.end()))
    return intervals


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


def _overlaps(start: int, end: int, intervals: List[Tuple[int, int]]) -> bool:
    return any(start < hi and lo < end for lo, hi in intervals)


def _is_sentence_initial(text: str, pos: int) -> bool:
    """Return whether position `pos` starts a sentence, line or list item.

    Any word is capitalised there, so a capitalised first word is not name
    evidence on its own.
    """
    before = text[:pos].rstrip(" \t*#>-•|")
    return not before or before[-1] in ".!?:\n"


def sweep_tier_a(text: str, covered: List[Tuple[int, int]], place_names: Set[str]) -> List[dict]:
    """Find Tier A-shaped substrings not covered by any known labeled span.

    Every hit rejects: an unplanned identifier has no owner the sweep can name,
    so it cannot be labelled safely.
    """
    findings = []
    for name, pattern in TIER_A_PATTERNS.items():
        for m in pattern.finditer(text):
            if _is_covered(m.start(), m.end(), covered):
                continue
            if name == "postal_like":
                code, word = m.group(1), m.group(2)
                # The code is the PII; a labelled POSTAL_CODE covers it even
                # when the place name beside it is not part of any span.
                if _is_covered(m.start(1), m.end(1), covered):
                    continue
                if word in _FIELD_LABEL_WORDS:
                    continue
                if _YEAR_RE.fullmatch(code) and word not in place_names:
                    continue
                if re.search(rf"(?:{_MONTHS})[ \t]*$", text[max(0, m.start() - 12):m.start()], re.IGNORECASE):
                    continue
            if name == "phone_like":
                parts = re.findall(r"\d+", m.group(0).replace("+47", ""))
                if len(parts) == 2 and all(_YEAR_RE.fullmatch(p) for p in parts):
                    continue
            findings.append({"pattern": name, "match": m.group(0), "start": m.start(),
                             "end": m.end(), "action": "reject"})
    return findings


# A stated age ("som er 75 år", "(42 år)", "44 år gammel", "37-årig") is AGE,
# and the model writes one whenever the prompt hints at the subject's age.
# Durations ("gjelde i 3 år", "de siste 2 årene") share the digits-plus-år shape,
# so the pattern requires an age cue on one side.
_AGE_RE = re.compile(
    r"(?:(?<=\ber )|(?<=\bvar )|(?<=\bvert )|(?<=\bblir )|(?<=\bblei )|(?<=\()|(?<=\balder )|(?<=\balderen )|(?<=\balder: )|(?<=\bAlder: ))"
    r"\d{1,3} år(?: gammel| gammal)?(?!\w)"
    r"|\b\d{1,3} år gam(?:mel|mal)\b"
    r"|\b\d{1,3}-åri(?:g|ng)(?:e|en)?\b"
)


def sweep_ages(text: str, covered: List[Tuple[int, int]]) -> List[dict]:
    """Find stated ages not covered by a planned span; these are labelled AGE, not rejected."""
    findings, seen = [], []
    for m in _AGE_RE.finditer(text):
        if _is_covered(m.start(), m.end(), covered) or _overlaps(m.start(), m.end(), seen):
            continue
        seen.append((m.start(), m.end()))
        findings.append({"pattern": "age_like", "match": m.group(0), "start": m.start(),
                         "end": m.end(), "action": "label", "label_type": "AGE"})
    return findings


def sweep_dates(text: str, covered: List[Tuple[int, int]]) -> List[dict]:
    """Find date strings not covered by a planned span; these are labelled, not rejected."""
    findings, seen = [], []
    for pattern in DATE_PATTERNS:
        for m in pattern.finditer(text):
            if _is_covered(m.start(), m.end(), covered) or _overlaps(m.start(), m.end(), seen):
                continue
            seen.append((m.start(), m.end()))
            findings.append({"pattern": "date_like", "match": m.group(0), "start": m.start(),
                             "end": m.end(), "action": "label", "label_type": "DATE_TIME"})
    return findings


def _capitalised_runs(text: str, masked: List[Tuple[int, int]]) -> List[List[Tuple[int, int, str]]]:
    """Group capitalised words separated only by spaces/tabs into runs.

    Honorific abbreviations keep their full stop (`Dr.`); any other full stop,
    comma, line break or masked (organisation, agency, place) word ends a run.
    """
    runs: List[List[Tuple[int, int, str]]] = []
    current: List[Tuple[int, int, str]] = []
    for m in _WORD_RE.finditer(text):
        start, end, tok = m.start(), m.end(), m.group(0)
        if tok in _HONORIFIC_STEMS and text[end:end + 1] == "." and _HONORIFIC_STEMS[tok].endswith("."):
            end, tok = end + 1, tok + "."
        if not tok[0].isupper() or _overlaps(start, end, masked):
            if current:
                runs.append(current)
            current = []
            continue
        if current and not re.fullmatch(r"[ \t]+", text[current[-1][1]:start]):
            runs.append(current)
            current = []
        current.append((start, end, tok))
    if current:
        runs.append(current)
    return runs


def sweep_names(
    text: str, covered: List[Tuple[int, int]], place_names: Set[str],
    agency_names: Set[str],
) -> List[dict]:
    """Find unplanned references to people.

    Returns findings with `action`:
      * "label" / PERSON for a full name (known given name + surname-like
        word) or an honorific + name (`Fru Olsen`, `Dr. Kari Hansen`);
      * "reject" for a role title + bare surname (`Saksbehandler Larsen`) or
        an unknown capitalised word + a known surname, where a person is
        referred to but the span is not one the annotation spec settles.

    A capitalised run ending in a legal-form code or an organisation word
    (`... Holding AS`, `Norsk Sykepleierforbund`, `Oslo tingrett`) is an
    organisation and is skipped whole; known organisations, agencies and place
    names are masked before the runs are built.

    Args:
        text: The generated document text.
        covered: Intervals already covered by a known labeled span.
        place_names: Known place names (masked).
        agency_names: Known agency names (masked, with `KNOWN_ORGANISATIONS`).

    Returns:
        List of finding dicts.
    """
    masked = _masked_intervals(text, list(agency_names) + data.KNOWN_ORGANISATIONS + sorted(place_names))
    findings: List[dict] = []

    def _emit(start: int, end: int, action: str, kind: str) -> None:
        if _is_covered(start, end, covered):
            return
        if any(f["start"] <= start and end <= f["end"] for f in findings):
            return
        finding = {"pattern": kind, "match": text[start:end], "start": start, "end": end, "action": action}
        if action == "label":
            finding["label_type"] = "PERSON"
        findings.append(finding)

    for run in _capitalised_runs(text, masked):
        toks = [t for _s, _e, t in run]
        if len(toks) >= 2 and _is_org_run(toks):
            continue
        i = 0
        if (_is_sentence_initial(text, run[0][0]) and toks[0] not in _FIRST_NAMES
                and toks[0] not in _HONORIFIC_STEMS.values() and toks[0].lower() not in _ROLE_TITLES):
            i = 1
        while i < len(run):
            start, _end, tok = run[i]
            bare = _strip_genitive(tok)
            nxt = [_strip_genitive(t) for _s, _e, t in run[i + 1:i + 4]]

            def _name_extent(first_idx: int, need_given: bool) -> int:
                """Index one past the last name-like token starting at first_idx."""
                j = first_idx
                while j < len(run) and j < first_idx + 4:
                    t = _strip_genitive(run[j][2])
                    if t in _FIRST_NAMES or _is_surname_like(t) or (need_given and j == first_idx and t[0].isupper()):
                        j += 1
                        if run[j - 1][2] != t:  # genitive ends the name
                            break
                    else:
                        break
                return j

            def _span_end(last_idx: int) -> int:
                s, e, t = run[last_idx]
                return s + len(_strip_genitive(t))

            if tok in _HONORIFIC_STEMS.values() or tok in _HONORIFIC_STEMS:
                j = _name_extent(i + 1, need_given=False)
                if j > i + 1:
                    _emit(start, _span_end(j - 1), "label", "person_honorific")
                    i = j
                    continue
            elif tok.lower() in _ROLE_TITLES:
                if nxt and nxt[0] in _FIRST_NAMES and len(nxt) > 1 and _is_surname_like(nxt[1]):
                    j = _name_extent(i + 1, need_given=False)
                    _emit(run[i + 1][0], _span_end(j - 1), "label", "person_full_name")
                    i = j
                    continue
                if nxt and _is_surname_like(nxt[0]):
                    _emit(start, _span_end(i + 1), "reject", "person_role_surname")
                    i += 2
                    continue
            elif bare in _FIRST_NAMES and nxt and (nxt[0] in _FIRST_NAMES or _is_surname_like(nxt[0])):
                j = _name_extent(i, need_given=False)
                if j - i >= 2 and _is_surname_like(_strip_genitive(run[j - 1][2])):
                    _emit(start, _span_end(j - 1), "label", "person_full_name")
                    i = j
                    continue
            elif nxt and nxt[0] in _SURNAMES and bare not in _SURNAMES and len(bare) > 2:
                _emit(start, _span_end(i + 1), "reject", "person_unknown_given")
                i += 2
                continue
            i += 1

    for m in _LOWER_ROLE_SURNAME_RE.finditer(text):
        surname = _strip_genitive(m.group(2))
        if m.group(3) or not _is_surname_like(surname) or surname in _FIRST_NAMES:
            continue
        if _overlaps(m.start(2), m.end(2), masked) or _is_sentence_initial(text, m.start(1)):
            continue
        _emit(m.start(1), m.start(2) + len(surname), "reject", "person_role_surname")
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
        Tuple of (no finding requires rejection, all findings). Findings with
        `action == "label"` carry a `label_type` and are safe to add to the
        document's output instead of regenerating it.
    """
    intervals = _covered_intervals(text, covered_spans)
    findings = sweep_tier_a(text, intervals, place_names)
    date_findings = sweep_dates(text, intervals)
    # A date can look like a phone number to nothing here, but an 8-digit date
    # hit and a Tier A hit on the same characters would double-count; dates win.
    findings = [f for f in findings if not _overlaps(f["start"], f["end"], [(d["start"], d["end"]) for d in date_findings])]
    findings += date_findings
    findings += sweep_ages(text, intervals)
    findings += sweep_names(text, intervals, place_names, agency_names)
    return not any(f["action"] == "reject" for f in findings), findings


# -- Slot learning: category-named labels and table rows ---------------------------
#
# The pilot's model put seeded judgement clauses in a markdown table whose row
# labels named the category (`Adferdsmønster | ...`, `Faglig tilknytning:
# ...`). A detector trained on that learns to read the label, not the clause.
# Tier A values in labelled fields (`Fødselsnummer: ...`) are what real forms
# look like and stay allowed; this gate only looks at judgement clauses.

_CATEGORY_LABEL_RE = re.compile(
    r"adferd|atferd|åtferd|helse|diagnos|sykdom|sjukdom|religi|livssyn|\btro\b|\btru\b|\btros|"
    r"fagforen|fagforein|fagorgan|faglig|fagleg|tilknytning|tilknyting|seksuel|legning|"
    r"orientering|relasjon|familie|økonomi|politisk|etnisk|etnisitet|opprinnelse|opphav|"
    r"straff|krimin|vandel|medisin|medikament|legemiddel|funksjons|innvandring|"
    r"oppholdsstatus|opphaldsstatus|biometri|genetisk|arvelig|arveleg|sensitiv|særlige|"
    r"særlege|personlige forhold|personlege forhold|rusmiddel",
    re.IGNORECASE,
)


def gate_slot_labels(text: str, clauses: Iterable[str]) -> Tuple[bool, List[dict]]:
    """Reject a document whose judgement clauses sit in table rows or category-labelled fields.

    Args:
        text: The generated document text.
        clauses: The judgement clause strings the record seeded.

    Returns:
        Tuple of (passed, violations as `{"clause", "kind", "line"}`).
    """
    violations = []
    for clause in clauses:
        if not clause:
            continue
        pos = text.find(clause)
        while pos >= 0:
            line_start = text.rfind("\n", 0, pos) + 1
            line_end = text.find("\n", pos)
            line = text[line_start:line_end if line_end >= 0 else len(text)]
            prefix = text[line_start:pos]
            kind = None
            if line.lstrip().startswith("|") or line.count("|") >= 2:
                kind = "table_row"
            elif ":" in prefix:
                label = re.sub(r"[*_#>\-•·\d.)\s]+", " ", prefix[:prefix.index(":")]).strip()
                if label and len(label.split()) <= 6 and _CATEGORY_LABEL_RE.search(label):
                    kind = "category_label"
            if kind:
                violations.append({"clause": clause, "kind": kind, "line": line.strip()[:160]})
                break
            pos = text.find(clause, pos + 1)
    return not violations, violations


# -- Length band -------------------------------------------------------------------

def gate_length(text: str, hard_max_chars: int = 7000) -> Tuple[bool, int]:
    """Reject only runaway documents; overshooting the planned band is allowed.

    The band is a diversity target, not a correctness property: a document that
    runs 30% long still carries verbatim, correctly located labels, and
    regenerating it cost the smoke run 9 of 20 failed attempts. Overshoot is
    reported through G5's length distribution instead. The hard cap exists for
    degenerate output (repetition loops) and keeps documents well inside the
    detector's context window.

    Args:
        text: The generated document text.
        hard_max_chars: Absolute ceiling in characters.

    Returns:
        Tuple of (passed, actual length).
    """
    return len(text) <= hard_max_chars, len(text)
