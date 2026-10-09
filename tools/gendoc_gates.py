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
* G13 -- the document is not a table dump: few table rows, few values in fields,
  no value listed under two labels.
* G14 -- no planned identifier is presented as a different kind of number, no case or
  reference number appears that nothing planned, a professional's licence number is not
  given to the patient, and a device, IP address or username is not presented as the
  issuing organisation's own.
* G14 also owns the role words (docs/ANNOTATION_SPEC.md, EMPLOYMENT: the role word of a specific
  individual is EMPLOYMENT, the name stays PERSON). The output format is one string per type, so a
  planted role word labels every occurrence of its string; `role_word_violations` rejects a
  document where the string occurs anywhere that is not that person's role: embedded in a longer
  word, or beyond four tokens from the person's name. `sweep_unplanned_roles` is the G7 side: a role
  word attached to a person nothing planned a role for.
* G15 -- a planted negative sits alone in its sentence: not beside another negative, not
  coordinated with a seeded clause by "og"/"men"/"samt", not repeated.

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
import collections
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

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


def _outside_literals(text: str, exempt: Sequence[str]) -> List[str]:
    """Return the stretches of text that no exempt literal overlaps.

    Several clauses of one type in one document legitimately share words (`dømt for
    ...`, `siktet for ...`, a stem the bank reuses), and the model restates a planted
    clause as often as it likes. A repetition or near-duplicate measure that counted
    those words would reject a document for carrying the planted facts it was asked to
    carry. So a window that overlaps a planted literal is not counted by G6 or G12; only
    the model's own prose between the literals is measured.

    Args:
        text: The document.
        exempt: Planted literals (seeded clauses).

    Returns:
        The pieces of text between the occurrences of the literals, in order; the whole
        text when `exempt` is empty.
    """
    spans = sorted(iv for iv in _covered_intervals(text, [e for e in exempt if e]))
    if not spans:
        return [text]
    pieces, pos = [], 0
    for start, end in spans:
        if start > pos:
            pieces.append(text[pos:start])
        pos = max(pos, end)
    if pos < len(text):
        pieces.append(text[pos:])
    return pieces


def word_ngrams(text: str, n: int = 5, exempt: Sequence[str] = ()) -> Set[Tuple[str, ...]]:
    """Return the set of lowercase word n-grams in a document.

    Args:
        text: The document.
        n: N-gram width.
        exempt: Planted literals; n-grams that overlap one are left out (see
            `_outside_literals`). Empty counts every word.

    Returns:
        The n-gram set.
    """
    if exempt:
        grams: Set[Tuple[str, ...]] = set()
        for piece in _outside_literals(text, exempt):
            words = re.findall(r"\w+", piece.lower())
            grams.update(tuple(words[i:i + n]) for i in range(len(words) - n + 1))
        return grams
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


# -- G15: where a planted negative sits ---------------------------------------------
#
# A planted negative is a near-miss clause: it must stay verbatim, unlabelled and
# neutral. Pilot v5 showed three ways the model spoils that. It glued two negatives
# into one run-on ("..., og han bur i ei bydel ..., og han tok ikkje stilling til ..."),
# it chained a negative to a seeded clause with "og"/"men" so the two read as one
# claim about the person, and it wrote a negative twice in one sentence. The sentence
# is the unit: one planted negative per sentence, never coordinated with a seeded
# clause, never repeated. Whether a sentence presents a negative as relevant is a
# meaning judgement and belongs to the G11 audit.

_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CONJUNCTION_BEFORE_RE = re.compile(r"(?:^|[\s,;])(?:og|men|samt)\s*$", re.IGNORECASE)
_CONJUNCTION_AFTER_RE = re.compile(r"^\s*[,;]?\s*(?:og|men|samt)\b", re.IGNORECASE)


def _swap_first(text: str) -> str:
    """Return `text` with the case of its first letter flipped; unchanged if it starts with no letter."""
    return text[:1].swapcase() + text[1:] if text[:1].isalpha() else text


def negative_occurrences(text: str, negative: str) -> List[Tuple[int, int]]:
    """Return the spans where a planted negative stands, matching its first letter in either case.

    The model capitalises a negative that opens a sentence ("han ville ikke ..." becomes
    "Han ville ikke ..."). That is the same clause, so the first character is compared
    case-insensitively and the rest exactly.

    Args:
        text: The generated document.
        negative: The planted text, after pronoun filling.

    Returns:
        Non-overlapping `(start, end)` spans in order of position; empty if absent.
    """
    spans: List[Tuple[int, int]] = []
    for form in {negative, _swap_first(negative)}:
        pos = text.find(form)
        while pos >= 0:
            spans.append((pos, pos + len(form)))
            pos = text.find(form, pos + 1)
    return sorted(spans)


def resolve_surfaces(negatives: Sequence[str], text: str) -> List[str]:
    """Return the form of each planted negative that the document actually contains.

    Args:
        negatives: The planted texts.
        text: The generated document.

    Returns:
        One string per negative: the text itself when it stands exactly, the
        first-letter-flipped form when only that does, else the text unchanged
        (so a missing negative stays missing for G2).
    """
    out = []
    for negative in negatives:
        if negative in text:
            out.append(negative)
        elif _swap_first(negative) in text:
            out.append(_swap_first(negative))
        else:
            out.append(negative)
    return out


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    """Split a document into `(start, end)` sentence spans at full stops, question marks and line breaks."""
    spans, start = [], 0
    for match in _SENTENCE_BREAK_RE.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def gate_negative_placement(text: str, negatives: Sequence[str], clauses: Sequence[str] = ()) -> Tuple[bool, List[dict]]:
    """Reject a document that chains, glues or repeats its planted negatives.

    Args:
        text: The document (or section) text.
        negatives: The planted negatives as they stand in the text (`resolve_surfaces`).
        clauses: The seeded judgement clauses of the same text.

    Returns:
        `(passed, hits)`. A hit is `{"kind", "negatives", "sentence"}` with kind
        `chained_negatives` (two negatives in one sentence), `chained_to_clause`
        (a negative coordinated with a seeded clause by "og", "men" or "samt" in one
        sentence) or `repeated_negative` (one negative standing more than once).
    """
    hits: List[dict] = []
    spans = sentence_spans(text)
    by_sentence: Dict[int, List[Tuple[str, int, int]]] = collections.defaultdict(list)
    for negative in negatives:
        found = negative_occurrences(text, negative)
        if len(found) > 1:
            hits.append({"kind": "repeated_negative", "negatives": [negative],
                         "sentence": text[found[0][0]:found[0][1]][:160]})
        if found:
            start, end = found[0]
            k = next(i for i, (a, b) in enumerate(spans) if a <= start < b or i == len(spans) - 1)
            by_sentence[k].append((negative, start, end))
    for k, items in sorted(by_sentence.items()):
        a, b = spans[k]
        sentence = text[a:b]
        if len(items) > 1:
            hits.append({"kind": "chained_negatives", "negatives": [i[0] for i in items],
                         "sentence": sentence[:240]})
        for negative, start, end in items:
            coordinated = (_CONJUNCTION_BEFORE_RE.search(text[a:start]) or _CONJUNCTION_AFTER_RE.match(text[end:b]))
            if not coordinated:
                continue
            for clause in clauses:
                pos = sentence.find(clause) if clause else -1
                if pos >= 0 and not (a + pos < end and start < a + pos + len(clause)):
                    hits.append({"kind": "chained_to_clause", "negatives": [negative], "clause": clause,
                                 "sentence": sentence[:240]})
                    break
    return not hits, hits


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
# that an empty slot is normal. `NN` and `N.N.` are matched case-sensitively, and
# `NN` not when digits follow: a lowercase "nn" is the language code of a Nynorsk
# document, and "NN 23517" is a vehicle registration the generator itself
# produces; under IGNORECASE the first discarded two pilot v3 documents.
_PLACEHOLDER_RE = re.compile(
    r"\[[^\[\]\n]{2,60}\]"
    r"|<[^<>\n]{2,40}>"
    r"|\b(?:X{3,}|x{3,})\b|\d{4,}[Xx]{3,}|(?-i:\bN\.N\.|\bNN\b(?![ \t]?\d))"
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
    # A URL at the end of a sentence is followed by the sentence's full stop, and
    # `\S+` swallowed it: the match then ran one character past the planned URL,
    # `_is_covered` rejected it, and a correctly realised URL was discarded as
    # unplanned. Pilot v3 lost three documents that way.
    "url_like": re.compile(r"https?://\S*[^\s.,;:!?)\]»\"']|\bwww\.\S*[^\s.,;:!?)\]»\"']"),
    "ip_like": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # The Tier A set grew from 7 types to 28, and an identifier shape the sweep
    # does not know is an unplanned identifier it cannot reject. These cover the
    # shapes the new generators produce: IPv6, a MAC address, a card or IMEI or
    # policy number as a long solid digit run, a passport/ID-card number, and a
    # wallet address in either the bech32 or the legacy base58 form.
    # MAC before IPv6: a MAC address matches the IPv6 pattern too, and the
    # dedup keeps whichever pattern is tried first at the same offset, so the
    # reported pattern name should be the specific one.
    "mac_like": re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"),
    "ipv6_like": re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}(?::|[0-9a-fA-F]{1,4})\b"),
    "long_digit_run": re.compile(r"(?<![\d.,/\-])\d{10,19}(?![\d])"),
    "document_number_like": re.compile(r"\b[A-Z]{1,2}\d{7,8}\b"),
    "wallet_like": re.compile(r"\b(?:bc1[023456789acdefghjklmnpqrstuvwxyz]{20,}"
                              r"|[13][1-9A-HJ-NP-Za-km-z]{25,34})\b"),
}

# A firearms number or a vessel mark has no shape of its own that the sweep can trust:
# `HG12345` is plate-shaped, `123456` is any number, and the registered object decides
# the type (docs/ANNOTATION_SPEC.md B20). So these two are recognised by the label
# words the document prints in front of the value, the same cue the annotators use,
# and the finding is the value alone. An invented one is rejected like any
# unplanned identifier; a planned one is covered by its own span. The vessel shapes
# always carry a hyphen or a single letter, so a road plate (`DK 45778`) never matches.
_FIREARMS_LABEL = (
    r"(?i:våpenkort(?:nummer(?:et)?|[ \t]+nr\.?)?|lisens(?:nummer(?:et)?|[ \t]?nr\.?)"
    r"|våpenlisens(?:nummer(?:et)?)?|registreringsnummer(?:et)?[ \t]+i[ \t]+våpenregisteret"
    r"|permit[ \t]+ID|(?:licen[sc]e|permit)[ \t]+number)"
)
_VESSEL_LABEL = (
    r"(?i:reg(?:istrerings)?\.?[ \t]?nr\.?|registreringsnummer(?:et)?|registreringsmerke(?:t)?"
    r"|registrert(?:[ \t]+som)?|kjennemerke(?:t)?|fiskerimerke(?:t)?)"
)
_LABEL_TO_VALUE = r"(?:[ \t]*[:=][ \t]*|[ \t]+(?:er|var|på)[ \t]+|[ \t]+)"

LABELLED_TIER_A_PATTERNS: Dict[str, re.Pattern] = {
    "firearms_like": re.compile(
        _FIREARMS_LABEL + _LABEL_TO_VALUE + r"((?:[A-Z]{1,2}-)?[A-Z]{0,2}\d[\d\-]{2,}\d)(?![\w\-])"),
    "vessel_like": re.compile(
        _VESSEL_LABEL + _LABEL_TO_VALUE
        + r"([A-ZÆØÅ]{1,2}-\d{1,4}(?:-[A-ZÆØÅ]{1,2})?|[A-Z]\d{5})(?![\w\-])"),
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
    # Before the shape patterns: where both describe the same characters the
    # dedup below keeps the first, and the labelled name says more.
    for name, pattern in LABELLED_TIER_A_PATTERNS.items():
        for m in pattern.finditer(text):
            value = m.group(1)
            if _is_covered(m.start(1), m.end(1), covered) or _YEAR_RE.fullmatch(value):
                continue
            findings.append({"pattern": name, "match": value, "start": m.start(1),
                             "end": m.end(1), "action": "reject"})
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
    # Several patterns describe the same shapes at different widths -- an
    # 11-digit fødselsnummer is also a long digit run -- so a hit fully inside
    # another hit is the same finding counted twice, and reporting it twice
    # makes a single invented identifier look like two.
    findings.sort(key=lambda f: (f["start"], -(f["end"] - f["start"])))
    deduped: List[dict] = []
    for finding in findings:
        if any(kept["start"] <= finding["start"] and finding["end"] <= kept["end"]
               for kept in deduped):
            continue
        deduped.append(finding)
    return deduped


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


def _preceding_heading(text: str, line_start: int) -> Optional[str]:
    """Return the nearest heading-like line above `line_start`, or None.

    A heading is a short line with no sentence-ending punctuation -- what a
    model writes when it groups the judgement clauses under a rubric. A smoke
    probe produced a nynorsk debt-counselling note whose medication, disability
    and behaviour clauses all sat under `Helserelaterte opplysningar og
    risikovurdering`, which teaches the detector to read the rubric rather than
    the clause. The label-on-the-same-line test could not see it, because the
    heading is its own line.
    """
    above = text[:line_start].rstrip("\n").split("\n")
    for raw in reversed(above[-3:]):
        candidate = raw.strip().strip("*_#>-•· ")
        if not candidate:
            continue
        if len(candidate) > 70 or candidate[-1] in ".!?;":
            return None
        return candidate
    return None


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
            if kind is None:
                heading = _preceding_heading(text, line_start)
                if heading and _CATEGORY_LABEL_RE.search(heading):
                    kind = "category_heading"
            if kind:
                violations.append({"clause": clause, "kind": kind, "line": line.strip()[:160]})
                break
            pos = text.find(clause, pos + 1)
    return not violations, violations


# -- G13: tabular dumps ------------------------------------------------------------
#
# G9 deliberately lets Tier A values sit in labelled fields, because a real form
# has `Fødselsnummer: ...` on it. What it cannot see is a document that is mostly
# fields: pilot v3's accepted `forsvaret_clearance` opened with 33 table rows
# listing every planned value, then repeated each in prose, and listed one
# fødselsnummer twice, as "Fødselsnummer" and as "Statlig ID". No Norwegian
# clearance opens with that, and a detector trained on it learns that PII lives
# in a header table. The gate measures three things, each with a threshold
# calibrated on the 400 adjudicated gold documents and on pilot v3's accepted
# set (see `check_generator_gates.py` and the thresholds' comments below).

_FIELD_LINE_RE = re.compile(r"^\s*(?:[-*•]\s*)?\**([A-ZÆØÅ][^\n:|]{0,40}?)\**\s*:\s*\**\s*\S")
_LABEL_BEFORE_RE = re.compile(
    r"(?:^|[\s|*])([A-ZÆØÅ][\wæøåÆØÅ.\-]*(?: (?:[a-zæøå][\wæøåÆØÅ.\-]*|[A-ZÆØÅ]{2,})){0,3})\**\s*:\s*\**$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|\-]+\|?\s*$")
# What may follow a value that fills its field: the end of the line, a table
# separator, a parenthetical gloss, or the next field's label. Prose that merely
# begins after a section label ("Oppsummering: Kari Hansen har ...") is not a field.
_FIELD_END_RE = re.compile(
    r"[ \t]*(?:[,;.]?[ \t]*(?:\n|$)|\||\(|[A-ZÆØÅ][\wæøåÆØÅ.\-]*(?: (?:[a-zæøå][\wæøåÆØÅ.\-]*|[A-ZÆØÅ]{2,})){0,3}[ \t]*:)")
FIELD_VALUE_MAX_CHARS = 70
# A name is legitimately both the addressee and the subject of a letter
# ("Til: Kari Hansen" above "Navn: Kari Hansen"), so these labels never count as
# a second label for the same value.
_ADDRESSING_LABELS = {"til", "fra", "kopi", "mottaker", "avsender", "vedrørende", "gjelder", "att"}

# Calibration, measured by `python3 tools/check_generator_gates.py --calibrate-g13`:
#   gold (400 documents, flattened to one line, so only the value measure
#   applies): the share of a document's distinct labelled values that sit in a
#   field has median 0.26, p90 0.38, p95 0.43, p99 0.67, max 0.75; real forms
#   do put most of a short document's values in fields, which is why the share
#   only counts once a document has more than MAX_SLOT_VALUES of them -- an
#   identification block of five or six fields is what the prompt asks for.
#   pilot v3 accepted (43 documents): the pipe-table line share is exactly 0 for
#   30 documents and 0.55-0.90 for the 7 with a table, so nothing sits between 0
#   and 0.55 and any threshold in that gap separates them. A table of fewer than
#   MIN_TABLE_ROWS rows (header included) is an identification block however
#   short the document makes its line share look.
MAX_TABLE_LINE_SHARE = 0.40
MIN_TABLE_ROWS = 5
MAX_VALUE_SLOT_SHARE = 0.50
MAX_SLOT_VALUES = 6


def is_table_line(line: str) -> bool:
    """Whether a line is a Markdown-style table row or separator."""
    stripped = line.strip()
    return stripped.startswith("|") or stripped.count("|") >= 2


def is_field_line(line: str) -> bool:
    """Whether a line is a short `Label: value` field, as opposed to prose with a colon."""
    match = _FIELD_LINE_RE.match(line)
    return bool(match) and len(line.split(":", 1)[1].strip()) <= FIELD_VALUE_MAX_CHARS


def _normalise_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip(" *_:\t")).lower()


def _table_label(lines: List[str], row: int, position: int, line: str) -> Optional[str]:
    """Return the label of the table cell containing `position` in `line`."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    lead = 1 if line.lstrip().startswith("|") else 0
    index = max(0, min(len(cells) - 1, line[:position].count("|") - lead))
    if len(cells) == 2:
        return _normalise_label(cells[0]) if index == 1 else None
    top = row
    while top > 0 and is_table_line(lines[top - 1]):
        top -= 1
    header = [c.strip() for c in lines[top].strip().strip("|").split("|")]
    return _normalise_label(header[index]) if index < len(header) and top != row else None


def value_slots(text: str, values: Iterable[str]) -> Dict[str, List[Optional[str]]]:
    """Locate each value's occurrences and the field label it sits under, if any.

    An occurrence is a *slot* when it is in a table row, or directly follows a
    `Label:` and fills the field (the line, or the text up to the next label,
    ends with it). Occurrences nested inside a longer planned value
    (the postal code inside an address) are not reported separately.

    Args:
        text: The document.
        values: Planned value strings; those under 3 characters are ignored.

    Returns:
        `{value: [label or None per occurrence]}`, only for values that occur.
        A label of "" marks a slot whose label could not be read (a table cell
        with no header).
    """
    distinct = sorted({v for v in values if v and len(v) >= 3}, key=len, reverse=True)
    lines = text.split("\n")
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    taken: List[Tuple[int, int]] = []
    found: Dict[str, List[Optional[str]]] = {}
    for value in distinct:
        pattern = re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)")
        for match in pattern.finditer(text):
            lo, hi = match.span()
            if any(a <= lo and hi <= b for a, b in taken):
                continue
            taken.append((lo, hi))
            row = max(0, min(len(lines) - 1, text.count("\n", 0, lo)))
            line, line_start = lines[row], starts[row]
            if is_table_line(line):
                label: Optional[str] = _table_label(lines, row, lo - line_start, line) or ""
            else:
                before = _LABEL_BEFORE_RE.search(text[max(line_start, lo - 45):lo])
                fills_field = before and _FIELD_END_RE.match(text, hi)
                label = _normalise_label(before.group(1)) if fills_field else None
            found.setdefault(value, []).append(label)
    return found


def tabular_profile(text: str, values: Iterable[str]) -> dict:
    """Measure how much of a document is table or field lines and where its values sit.

    Args:
        text: The document.
        values: Planned value strings.

    Returns:
        `table_line_share` and `field_line_share` (of non-empty lines),
        `table_rows` (non-separator table lines), `values_located`,
        `values_in_slots` (distinct values with at least one slot occurrence),
        `value_slot_share`, and `duplicate_labels`: values that sit under two or
        more different field labels.
    """
    lines = [l for l in text.split("\n") if l.strip()]
    table = [l for l in lines if is_table_line(l)]
    fields = [l for l in lines if not is_table_line(l) and is_field_line(l)]
    found = value_slots(text, values)
    in_slots = [v for v, labels in found.items() if any(l is not None for l in labels)]
    duplicates = {}
    for value, labels in found.items():
        distinct = {l for l in labels if l and l not in _ADDRESSING_LABELS}
        if len(distinct) >= 2:
            duplicates[value] = sorted(distinct)
    return {
        "lines": len(lines),
        "table_line_share": round(len(table) / len(lines), 3) if lines else 0.0,
        "field_line_share": round(len(fields) / len(lines), 3) if lines else 0.0,
        "table_rows": sum(1 for l in table if not _TABLE_SEPARATOR_RE.match(l)),
        "values_located": len(found),
        "values_in_slots": len(in_slots),
        "value_slot_share": round(len(in_slots) / len(found), 3) if found else 0.0,
        "duplicate_labels": duplicates,
    }


def gate_tabular_dump(
    text: str, values: Iterable[str], max_table_line_share: float = MAX_TABLE_LINE_SHARE,
    min_table_rows: int = MIN_TABLE_ROWS, max_value_slot_share: float = MAX_VALUE_SLOT_SHARE,
    max_slot_values: int = MAX_SLOT_VALUES,
) -> Tuple[bool, List[dict]]:
    """Reject a document that is mostly a table, lists its values as fields, or lists one twice.

    Args:
        text: The generated document.
        values: The planned value and clause strings.
        max_table_line_share: Maximum share of non-empty lines that are table rows.
        min_table_rows: Tables with fewer rows (header included) are an
            identification block, never a dump, whatever their share of a very
            short document.
        max_value_slot_share: Maximum share of the located values that sit in a
            table row or fill a `Label:` field.
        max_slot_values: A document may keep this many values in fields before
            the share applies; it is the size of an identification block.

    Returns:
        Tuple of (passed, violations as `{"kind", ...}` dicts).
    """
    profile = tabular_profile(text, list(values))
    violations = []
    if profile["table_line_share"] > max_table_line_share and profile["table_rows"] >= min_table_rows:
        violations.append({"kind": "table_lines", "table_line_share": profile["table_line_share"],
                           "table_rows": profile["table_rows"]})
    if profile["values_in_slots"] > max_slot_values and profile["value_slot_share"] > max_value_slot_share:
        violations.append({"kind": "value_slots", "value_slot_share": profile["value_slot_share"],
                           "values_in_slots": profile["values_in_slots"],
                           "values_located": profile["values_located"]})
    if profile["duplicate_labels"]:
        violations.append({"kind": "duplicate_label", "values": profile["duplicate_labels"]})
    return not violations, violations


# -- G14: identifier roles ----------------------------------------------------------
#
# Asking for a small identification block and no longer printing a `Label:` in
# front of every value in the prompt had a cost the first benchmark smoke run
# showed: a service number printed as "Sak 24723932", a 15-digit device id as
# "Sak: 999583174166724", "saksnummeret er 71056542" for a tjenestenummer, and a
# case number ("Sak 2026-0451") that nothing planned. The span is still correct
# by construction -- the value is there and typed -- but the sentence around it
# tells the detector it is something else, which is the label-versus-context
# mismatch a benchmark must not contain. G14 reads the words just before each
# planned identifier and rejects one that names a different kind of number.

_ROLE_WORDS: Dict[str, "re.Pattern"] = {
    "CASE_NUMBER": re.compile(r"\b(?:saksnummer(?:et)?|saksnr\.?|sak(?:s)?[ \t]?nr\.?|sak)\b[ \t]*[:.]?", re.IGNORECASE),
    "NATIONAL_ID": re.compile(r"\b(?:fødselsnummer(?:et)?|fødselsnr\.?|personnummer(?:et)?|fnr\.?|d-nummer(?:et)?)\b", re.IGNORECASE),
    "MILITARY_ID": re.compile(r"\b(?:tjenestenummer(?:et)?|tenestenummer(?:et)?|tjenestenr\.?)\b", re.IGNORECASE),
    "ORG_NUMBER": re.compile(r"\b(?:org\.?[ \t]?nr\.?|organisasjonsnummer(?:et)?)\b", re.IGNORECASE),
    "BANK_ACCOUNT": re.compile(r"\b(?:kontonummer(?:et)?|kontonr\.?)\b", re.IGNORECASE),
    "PASSPORT": re.compile(r"\b(?:passnummer(?:et)?|pass[ \t]med[ \t]nummer(?:et)?)\b", re.IGNORECASE),
    "IDENTITY_CARD": re.compile(r"\b(?:id-?kort(?:nummer(?:et)?)?)\b", re.IGNORECASE),
    "DRIVER_LICENSE": re.compile(r"\b(?:førerkort(?:nummer(?:et)?)?|førarkort(?:nummer(?:et)?)?)\b", re.IGNORECASE),
    "STUDENT_ID": re.compile(r"\b(?:studentnummer(?:et)?|studentnr\.?)\b", re.IGNORECASE),
    "PHONE": re.compile(r"\b(?:telefon(?:nummer(?:et)?)?|tlf\.?|mobil(?:nummer(?:et)?)?)\b", re.IGNORECASE),
    "DEVICE_ID": re.compile(r"\b(?:enhets-?id(?:entifikator)?|einings-?id(?:entifikator)?|imei)\b", re.IGNORECASE),
    "FIREARMS_LICENSE": re.compile(
        r"\b(?:våpenkort(?:nummer(?:et)?|[ \t]+nr\.?)?|lisens(?:nummer(?:et)?|[ \t]?nr\.?)|våpenlisens(?:nummer(?:et)?)?)",
        re.IGNORECASE),
    # `registreringsnummer` and `reg.nr.` name a car's plate, a rifle's register entry
    # and a vessel's mark alike (B20: the registered object decides), so this one
    # is only a wrong role for a type that is none of the three.
    "REGISTRATION": re.compile(
        r"\b(?:reg(?:istrerings)?\.?[ \t]?nr\.?|registreringsnummer(?:et)?|registreringsmerke(?:t)?|kjennemerke(?:t)?)",
        re.IGNORECASE),
}
_REGISTRY_TYPES = {"LICENSE_PLATE", "FIREARMS_LICENSE", "VESSEL_REGISTRATION"}
# Types that have no role word of their own but are still checked against every
# other type's words: a firearms number or a vessel mark is a registry number
# and must not sit under a case number's, a phone number's or an ID's label.
_FULLY_ROLE_CHECKED = {"FIREARMS_LICENSE", "VESSEL_REGISTRATION"}
_ROLE_REACH_CHARS = 14

# Whose number it is. The span is correct by construction either way, but pilot v4 wrote
# "Håkon Selvik, født 17. mars 1933, med hpr-nummer 4665353" for a patient (an HPR number
# is a clinician's) and "vår enhetsidentifikator 999038879317022" for a device the bank's
# letter was asking about (a device, an IP address and a username are the customer's, never
# the issuing organisation's own). The sentence tells the detector the wrong thing about
# who the value identifies.
_CLINICIAN_TITLES_RE = re.compile(
    r"\b(?:lege|legen|fastlege\w*|overlege\w*|bedriftslege\w*|spesialist\w*|psykolog\w*|"
    r"veterinær\w*|dyrlege\w*|arbeidsmedisin\w*|sykepleier\w*|behandlende)\b",
    re.IGNORECASE)
_SUBJECT_GENERIC_RE = re.compile(r"\b(?:pasienten|vedkommende|hovedpersonen|klienten|søkeren)\b", re.IGNORECASE)
_OWNER_WINDOW_CHARS = 90
_CLINICIAN_WINDOW_CHARS = 150
_ISSUER_OWNED_TYPES = {"DEVICE_ID", "IP_ADDRESS", "USERNAME"}
# "vår enhetsidentifikator 99..." and "vårt brukernavn x" present the value as the sender's own; a
# sentence that merely has the sender as its subject ("våre systemer logget IP-adressen ...") or
# says the customer is registered with the sender does not, so the possessive must be within two
# words of the value.
_ISSUER_OWN_RE = re.compile(
    r"\b(?:vår|vårt|våre)\b(?:[ \t]+[\w\-]+){0,2}[ \t:]*$"
    r"|\b(?:referanse(?:nummer(?:et)?)?|ref\.?(?:nr\.?)?)\W{0,3}$",
    re.IGNORECASE)


def _ref_in_window(text: str, window_start: int, end: int, refs: Sequence[str]) -> bool:
    """Whether any reference string occurs, as a whole word, in text[window_start:end]."""
    window = text[window_start:end]
    for ref in refs:
        if ref and re.search(r"(?<!\w)" + re.escape(ref) + r"(?!\w)", window, re.IGNORECASE if ref.islower() else 0):
            return True
    return False


# `Sak 2026-0451`, `Saksnummer 24723932`, `Vår ref: MT-2023-4789-BA`: a label that
# introduces a reference number, and the number. The number has to look like one
# (a digit, and either a separator or five characters) so "sak 3 av 7" is left alone.
# A bare `Referanse: 187406` is not here: the gold set leaves that kind of agency
# routing metadata untagged, while
# it labels a case number and a `Vår ref`, so only the latter are unplanned PII.
_REFERENCE_RE = re.compile(
    r"\b(?:saksnummer(?:et)?|saksnr\.?|sak(?:s)?[ \t]?nr\.?|sak|vår[ \t]ref(?:eranse)?\.?|"
    r"deres[ \t]ref(?:eranse)?\.?)\b[ \t]*[:.]?[ \t]*"
    r"(\d[\w/\-.]*\w)", re.IGNORECASE)


def _reference_like(token: str) -> bool:
    return bool(re.search(r"\d", token)) and (len(token) >= 5 or re.search(r"[/\-]", token) is not None)


def gate_identifier_roles(
    text: str, typed_values: Iterable[Tuple[str, str]], covered_spans: Iterable[str],
    owners: Optional[dict] = None, role_words: Optional[Sequence[dict]] = None, earlier: str = "",
) -> Tuple[bool, List[dict]]:
    """Reject an identifier presented as a different kind of number, or as someone else's.

    Five things are caught: an identifier whose preceding words name another kind of
    number; a reference number nothing planned; a clinician's HPR number written next to the
    subject instead of next to a clinician; a device identifier, IP address or username
    presented as the issuing organisation's own ("vår enhetsidentifikator ...", "referanse
    ..."); and a planted role word used somewhere that is not that person's role
    (`role_word_violations`).

    Args:
        text: The generated document.
        typed_values: `(type, value)` for each planned value.
        covered_spans: Every planned or labelled span, so a reference number that
            sits inside one (the case number in a seeded CRIMINAL clause) is not
            reported as unplanned.
        owners: Whose value is whose, for the two ownership checks: `subject_refs`
            (the subject's name parts and pronouns) and `clinician_refs` (the names of the
            document's clinicians). None skips the HPR check; the issuer check needs no
            context and always runs.
        role_words: The planted role words as `{"word", "name", "definite"}` dicts; None checks none.
        earlier: The text of the sections before this one, for the role words' references back to a name.

    Returns:
        Tuple of (passed, violations as `{"kind", ...}`): `wrong_role` when the
        words just before a planned identifier name another type, `unplanned_reference`
        for a "Sak <number>" nothing planned, `wrong_owner` for an HPR number placed with
        the subject, `issuer_identifier` for a customer's device, IP address or username
        written as the organisation's own and `generic_role_word` for a planted role word
        used away from its person.
    """
    violations = []
    owners = owners or {}
    for etype, value in typed_values:
        if not value:
            continue
        if etype == "MEDICAL_LICENSE" and owners.get("subject_refs"):
            for match in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                near_subject = _ref_in_window(
                    text, max(line_start, match.start() - _OWNER_WINDOW_CHARS), match.start(),
                    owners["subject_refs"])
                far = max(line_start, match.start() - _CLINICIAN_WINDOW_CHARS)
                near_clinician = (_ref_in_window(text, far, match.start(), owners.get("clinician_refs", []))
                                  or bool(_CLINICIAN_TITLES_RE.search(text[far:match.start()])))
                if near_subject and not near_clinician:
                    violations.append({"kind": "wrong_owner", "type": etype, "value": value,
                                       "context": text[max(line_start, match.start() - 70):match.end()].strip()})
                    break
        if etype in _ISSUER_OWNED_TYPES:
            for match in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                window = text[max(line_start, match.start() - 60):match.start()]
                if _ISSUER_OWN_RE.search(window):
                    violations.append({"kind": "issuer_identifier", "type": etype, "value": value,
                                       "context": text[max(line_start, match.start() - 60):match.end()].strip()})
                    break
        for match in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            window = text[max(line_start, match.start() - 48):match.start()]
            nearest = None
            for other, pattern in _ROLE_WORDS.items():
                if other == "REGISTRATION" and etype not in _REGISTRY_TYPES | {"CASE_NUMBER"}:
                    continue
                for hit in pattern.finditer(window):
                    if len(window) - hit.end() <= _ROLE_REACH_CHARS and (nearest is None or hit.end() > nearest[0]):
                        nearest = (hit.end(), other)
            # Types with no role word of their own (an e-mail address, a date) are
            # only checked against the two labels they were seen under in smoke
            # runs, "Saksnummer: kari@x.no"; their own words are too varied to police.
            if (etype not in _ROLE_WORDS and etype not in _FULLY_ROLE_CHECKED
                    and (not nearest or nearest[1] not in ("CASE_NUMBER", "NATIONAL_ID")
                         or etype in ("DATE_TIME", "AGE", "GENDER", "PERSON"))):
                continue
            if nearest and nearest[1] == "REGISTRATION" and etype in _REGISTRY_TYPES:
                continue
            if nearest and nearest[1] != etype:
                violations.append({"kind": "wrong_role", "type": etype, "value": value,
                                   "presented_as": nearest[1], "context": window.strip()[-60:]})
                break
    covered = _covered_intervals(text, covered_spans)
    for match in _REFERENCE_RE.finditer(text):
        token = match.group(1)
        if _reference_like(token) and not _overlaps(match.start(1), match.end(1), covered):
            violations.append({"kind": "unplanned_reference", "value": token,
                               "context": text[max(0, match.start() - 10):match.end()].strip()})
    if role_words:
        violations += role_word_violations(text, role_words, earlier)
    return not violations, violations


# -- Role words: the EMPLOYMENT of a specific individual ------------------------------
#
# The annotation owner ruled that a role word attached to, or clearly referring to, a specific
# individual is EMPLOYMENT (`Veterinæren` in "Veterinæren Ola Nilsen", `legen` in "legen Oda
# Rørvik"), that the name stays PERSON, and that a generic or institutional use ("ble tatt med
# til veterinær", "bør kontakte lege", "Mattilsynets inspektører") or a hypothetical ("en
# veterinær kan ...") is not EMPLOYMENT. The label format cannot say which occurrence of a string
# is which: `{"EMPLOYMENT": ["lege"]}` labels every `lege` in the document, `lege` inside
# `legemiddel` included. So the generator may only plant a role word, or label one it did not
# plant, when every occurrence of the string is a role word of a person.

ROLE_ADJACENT_TOKENS = 4
# What may follow a planted role word and still be that word: nothing, or the genitive -s. An
# inflected form ("psykologspesialisten") is another string; the label would cover part of a word.
_ROLE_TAILS = {"", "s"}
# What may follow a lexicon word in the sweep for unplanned role words: the definite article
# ("legen", "legens"), which is then part of the labelled string.
_LEXICON_TAILS = {"": "", "s": "", "n": "n", "en": "en", "ns": "n", "ens": "en"}
_SENTENCE_BREAK_CHARS = ".!?;\n"
_LETTERS = "A-Za-zÆØÅæøåÉéÈèÓóÖöÄäÜüß"


def role_variants(word: str) -> List[str]:
    """Return the forms a role word can take in running text: as planted, and with a capital first letter.

    A model capitalises a word that opens a sentence ("Psykologspesialist Lars Ottesen
    undersøkte ..."), and both forms are labels of the same planted word.
    """
    variants = [word]
    if word[:1].islower():
        variants.append(word[:1].upper() + word[1:])
    return variants


def _role_occurrences(text: str, word: str) -> List[dict]:
    """Every occurrence of a role word's string, with what makes it a whole word or part of one.

    The label is a substring match, so an occurrence inside a longer word counts: `lege` inside
    `legemiddel` or `overlege` is an occurrence of the planted string like any other.
    """
    found = []
    for variant in role_variants(word):
        for m in re.finditer(re.escape(variant), text):
            tail = re.match(r"[" + _LETTERS + r"]*", text[m.end():]).group(0)
            found.append({"start": m.start(), "end": m.end(), "variant": variant, "tail": tail,
                          "embedded_before": bool(m.start() and text[m.start() - 1].isalpha())})
    return sorted(found, key=lambda o: o["start"])


def role_present(word: str, text: str) -> bool:
    """Whether the role word occurs in `text` as a whole word, in either capitalisation.

    "Whole" means no letter before it and nothing but a genitive -s after it, so a draft that wrote
    `psykologspesialisten` for the planted `psykologspesialist` counts as missing the word (and is
    repaired) rather than as having it.
    """
    return any(not o["embedded_before"] and o["tail"] in _ROLE_TAILS for o in _role_occurrences(text, word))


def _name_refs(name: str) -> List[str]:
    """The ways a person is referred to by name: the full string, the first name and the surname."""
    parts = [p for p in name.split() if not p.endswith(".")]
    return [name] + [p for p in (parts[0], parts[-1]) if len(p) >= 3 and p != name] if parts else [name]


def _mention_spans(text: str, refs: Sequence[str]) -> List[Tuple[int, int]]:
    spans = []
    for ref in refs:
        for m in re.finditer(r"(?<![" + _LETTERS + r"])" + re.escape(ref) + r"(?![" + _LETTERS + r"])", text):
            spans.append((m.start(), m.end()))
    return spans


def _adjacent(text: str, start: int, end: int, mentions: Sequence[Tuple[int, int]]) -> bool:
    """Whether a name mention lies within `ROLE_ADJACENT_TOKENS` words of [start, end), in one sentence."""
    for ms, me in mentions:
        if ms >= end:
            between = text[end:ms]
        elif me <= start:
            between = text[me:start]
        else:
            continue
        if (not any(c in between for c in _SENTENCE_BREAK_CHARS)
                and len(re.findall(r"\w+", between)) <= ROLE_ADJACENT_TOKENS):
            return True
    return False


def role_word_violations(text: str, roles: Sequence[dict], earlier: str = "") -> List[dict]:
    """Return every occurrence of a planted role word that is not that person's role.

    An occurrence is the person's role only when it stands directly beside their name (within
    `ROLE_ADJACENT_TOKENS` words, in one sentence, before or after it). ANNOTATION_SPEC B12
    (commit e81b639) tags a professional title only when it is attached to a named person:
    gold leaves an unnamed reference untagged ("Veterinæren mente…", "inspektørene"), even when
    the person was named earlier, so the planted string anywhere else would be over-labelled.
    The generic use ("ta kontakt med lege") and any occurrence inside a longer word or in an
    inflected form are violations for the same reason.

    Args:
        text: The document, or a section of it.
        roles: One dict per planted role word: `word`, `name` (the person's full name) and
            `definite` (whether the planted form is the definite one).
        earlier: The text of the sections before this one, in which a name may already have been given.

    Returns:
        Violations as `{"kind": "generic_role_word", "reason", "value", "name", "start", "context"}`;
        `reason` is `embedded_in_word` or `not_beside_the_name`.
    """
    violations = []
    for role in roles:
        word, name = role["word"], role["name"]
        refs = _name_refs(name)
        mentions = _mention_spans(text, refs)
        named_before = bool(_mention_spans(earlier, refs)) if earlier else False
        for occ in _role_occurrences(text, word):
            reason = None
            if occ["embedded_before"] or occ["tail"] not in _ROLE_TAILS:
                reason = "embedded_in_word"
            elif not _adjacent(text, occ["start"], occ["end"], mentions):
                reason = "not_beside_the_name"
            if reason:
                violations.append({
                    "kind": "generic_role_word", "reason": reason, "value": word, "name": name,
                    "start": occ["start"],
                    "context": text[max(0, occ["start"] - 40):occ["end"] + len(occ["tail"]) + 40].strip()})
    return violations


def sweep_unplanned_roles(
    text: str, person_names: Sequence[str], lexicon: Sequence[str], planned_words: Sequence[str],
    employment_spans: Sequence[str] = (),
) -> List[dict]:
    """Find role words attached to a person that has no planned role, and decide each string.

    The G7 sweep labels a full name the model wrote on its own as PERSON; the same person's role
    word is then an incompleteness of the same kind, and under the ruling it is EMPLOYMENT. The
    labelled string is the role word with its definite article if it has one (`legen`, not `lege`).
    A string is labelled when it can be labelled correctly and the document is rejected when it
    cannot:

    * **label** (`action: "label"`, `label_type: "EMPLOYMENT"`): every occurrence of the string
      in the document stands beside a labelled person's name, so the one-string-per-type output
      labels nothing wrongly;
    * **reject**: some other occurrence of the string is generic, inside a longer word
      (`lege` in `legemiddel`) or a different inflection of it. The string cannot be labelled
      without over-labelling, and leaving it unlabelled is the incompleteness being avoided,
      so the document is regenerated.

    Args:
        text: The document.
        person_names: Every labelled PERSON string (planned and G7-labelled).
        lexicon: The professional role words recognised (`gendoc_genres.professional_lexicon`).
        planned_words: Role words already planned for a person; they are the role gate's business.
        employment_spans: EMPLOYMENT strings already labelled (the subject's `ansatt som sykepleier`):
            an occurrence inside one is already an EMPLOYMENT label and is neither counted nor
            reconsidered.

    Returns:
        Findings in the shape of `gate_unplanned_pii`'s: `pattern`, `match`, `start`, `end`,
        `action` and, for a label, `label_type`.
    """
    mentions = _mention_spans(text, sorted({r for name in person_names for r in _name_refs(name)}))
    if not mentions:
        return []
    labelled = _covered_intervals(text, employment_spans)
    planned = set(planned_words)
    candidates: Dict[str, List[dict]] = collections.defaultdict(list)
    for word in lexicon:
        if word in planned:
            continue
        for occ in _role_occurrences(text, word):
            if (occ["embedded_before"] or occ["tail"] not in _LEXICON_TAILS
                    or _is_covered(occ["start"], occ["end"], labelled)):
                continue
            unit_end = occ["end"] + len(_LEXICON_TAILS[occ["tail"]])
            beside = _adjacent(text, occ["start"], unit_end, mentions)
            # Only a title beside a name is EMPLOYMENT (B12, e81b639); a later unnamed reference
            # to the same professional is untagged in gold, so it counts as a stray use.
            candidates[text[occ["start"]:unit_end]].append(
                {"start": occ["start"], "end": unit_end, "beside": beside, "attached": beside})
    findings: List[dict] = []
    for unit, occs in sorted(candidates.items()):
        # A longer lexicon word that holds this one (`overlege` holds `lege`) is a different word,
        # not an occurrence of this one; it is not in `occs` because `embedded_before` excluded it
        # for the shorter word, and the substring search below finds it.
        attached_starts = {o["start"] for o in occs if o["attached"]}
        stray = [m.start() for m in re.finditer(re.escape(unit), text)
                 if m.start() not in attached_starts and not _is_covered(m.start(), m.end(), labelled)]
        beside = [o for o in occs if o["beside"]]
        if not beside:
            continue
        clean = not stray
        findings.append({
            "pattern": "person_role_word" if clean else "role_word_also_used_generically",
            "match": unit, "start": beside[0]["start"], "end": beside[0]["end"],
            "action": "label" if clean else "reject",
            **({"label_type": "EMPLOYMENT"} if clean else {})})
    return findings


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

# -- Seeded-clause boundary: a clause the model completed with a date --------------
#
# `docs/ANNOTATION_SPEC.md` requires the full clause, and the model routinely
# finishes a seeded one: the record seeded `har hatt vedvarande ryggsmerter sidan
# hausten` and the document reads `... sidan hausten 2025`, so the located label
# stops one word short of the clause the spec asks for. Extending the span is
# only safe for a closed set of completions whose own boundary is unambiguous --
# a bare year, `i YYYY`, or a full date, with nothing but a single space between
# them and the clause. Anything else (another noun phrase, a comma, a
# subordinate clause) is left alone: guessing a clause boundary is the failure
# mode this whole pipeline exists to avoid.

_CLAUSE_COMPLETION_RE = re.compile(
    r"^ (?:i )?(?:"
    r"(?:19|20)\d{2}"
    r"|[0-3]?\d\.[01]?\d\.(?:19|20)\d{2}"
    r"|[0-3]?\d\.[ \t]?(?:januar|februar|mars|april|mai|juni|juli|august|september|"
    r"oktober|november|desember)(?:[ \t]+(?:19|20)\d{2})?"
    # A year at the end of a sentence is followed by a full stop, which is fine;
    # `2025.03.12`, `2025/2026` and `2025-2026` are not completions at all, so
    # only a separator followed by a digit blocks the match.
    r")(?![\w])(?![./\-]\d)"
)


def extend_seeded_clause_spans(text: str, clauses: Sequence[str]) -> Tuple[Dict[str, str], int]:
    """Extend a seeded clause label over a date that immediately completes it.

    A clause is extended only when *every* occurrence of it in the text is
    followed by such a completion, so the document never carries both the short
    and the long form of the same clause (which `validate_labels.py` reports as
    a redundant nested span).

    Args:
        text: The document text.
        clauses: The seeded clause strings located in the text.

    Returns:
        Tuple of (mapping from original clause to extended clause, number of
        clauses extended).
    """
    mapping: Dict[str, str] = {}
    for clause in clauses:
        if not clause or _YEAR_RE.search(clause[-5:]):
            continue
        spots = _covered_intervals(text, [clause])
        if not spots:
            continue
        completions = set()
        for _start, end in spots:
            match = _CLAUSE_COMPLETION_RE.match(text[end:end + 40])
            if not match:
                completions = set()
                break
            completions.add(match.group(0))
        if len(completions) == 1:
            mapping[clause] = clause + completions.pop()
    return mapping, len(mapping)


# -- G12: intra-document degeneration ----------------------------------------------

# How many occurrences of one planted literal G12 exempts: the planting and one natural
# restatement. A model that loops a clause forty times is still degenerate.
EXEMPT_OCCURRENCES = 2


def repetition_share(text: str, n: int = 8, exempt: Sequence[str] = ()) -> float:
    """Return the share of word n-grams in the text that are exact repeats.

    Args:
        text: The generated document text.
        n: N-gram width; 8 words is long enough that ordinary Norwegian
            administrative boilerplate does not trip it.
        exempt: Planted literals. A window that overlaps one is never counted as a repeat
            (it stays in the denominator, so the threshold keeps the calibration it was
            measured with), so a document that plans four offences opening `dømt for ...`
            or `siktet for ...`, or restates one, is not read as looping. Only the first
            `EXEMPT_OCCURRENCES` occurrences of each literal are exempt.

    Returns:
        Duplicated n-grams as a share of all n-grams, 0.0 for a short text.
    """
    tokens = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]
    if len(tokens) < n * 2:
        return 0.0
    covered = []
    for literal in {e for e in exempt if e}:
        covered += _covered_intervals(text, [literal])[:EXEMPT_OCCURRENCES]
    covered.sort()
    grams: collections.Counter = collections.Counter()
    total = 0
    for i in range(len(tokens) - n + 1):
        total += 1
        if covered:
            lo, hi = tokens[i][0], tokens[i + n - 1][1]
            if any(a < hi and lo < b for a, b in covered):
                continue
        grams[tuple(tok[2] for tok in tokens[i:i + n])] += 1
    duplicated = sum(count - 1 for count in grams.values() if count > 1)
    return duplicated / max(1, total)


def gate_internal_repetition(text: str, threshold: float,
                             exempt: Sequence[str] = ()) -> Tuple[bool, float]:
    """Reject a document that has started repeating itself.

    Raising the length cap so long documents are not discarded for overshooting
    their band lets in the other long-generation failure: the model stops
    writing and starts looping. A smoke-run whistleblowing letter repeated
    "Vi gitt deg fire dagar til å svare, og vi vil deretter vurdere neste steg i
    saka" verbatim and closed with a dump of every planted value in a field
    list, and no gate saw it. Measured on 40 `data/gold/` documents the 8-gram
    repeat share has median 0.000, 90th percentile 0.015 and maximum 0.035, so
    a threshold of 0.06 leaves real Norwegian administrative prose alone.

    Args:
        text: The generated document text.
        threshold: Maximum allowed duplicated-8-gram share.
        exempt: Planted literals whose windows are never counted as repeats (see
            `repetition_share`).

    Returns:
        Tuple of (passed, the measured share).
    """
    share = repetition_share(text, exempt=exempt)
    return share <= threshold, round(share, 4)
