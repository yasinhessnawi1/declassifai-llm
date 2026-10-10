"""G16 and G17: two prose defects the content gates cannot see.

Both were found by reading the accepted documents of a 20-document benchmark check on
Qwen3.5-9B, not by any earlier gate:

* **G16, a statement about the document instead of content.** The prompt has long told the model
  not to write "ingen ytterligere personopplysninger foreligger" or "X er den eneste personen som
  nevnes", and it still wrote "Det er ikkje opplyst om andre personar enn dei nemnde i denne
  saksbehandlingsrekka", "Ingen andre personer enn de nevnte er inkludert i denne meldingen",
  "Ingen ytterligere personopplysninger ble ført inn i rapporten" and "Alle nevnte personer er
  knyttet til saken uten at ytterligere opplysninger foreligger". A prompt rule was the only
  defence. Such a sentence is not a label problem; it is a sentence no real case file contains, and
  a detector that sees it learns that a document announces what PII it holds. `meta_statements`
  finds them, `strip_meta_statements` deletes them when no planted string is in them.
* **G17, Bokmål in a Nynorsk document.** A generator cannot repair Nynorsk in general, but a short
  list of forms that exist in Bokmål and nowhere in Nynorsk ("avholdt", "bodd", "foreligger",
  "ikke", "hennes", "uten", "ble", ...) is unmistakable, and a count of them says whether a
  document is Nynorsk or Bokmål with a Nynorsk veneer. `bokmal_forms` counts them and
  `bokmal_sentences` names the sentences, for a targeted rewrite by the G11 repair pass.

Neither module-level list was written from general knowledge alone. G16 was tuned until it fired on
none of the 400 documents of `data/gold_v2` and on the five phrasings above; G17's list was built
from words that Nynorsk's own orthography does not allow, then thinned of every word that real
Nynorsk text also uses ("tatt", "blitt", "kun", "mer", "dem", "selv" were left out), and the
threshold was set from the measured distribution on the Nynorsk documents of the check run and of
`data/synthetic/pilot_v5_bench` (see `NYNORSK_MIN_FORMS`).
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

import gendoc_gates as gates

# -- G16 -----------------------------------------------------------------------------------

_PERSON_NOUNS = (r"(?:personer|personene|personar|personane|parter|partene|partar|partane|"
                 r"personopplysning\w*|personlige\s+opplysning\w*|personlege\s+opplysning\w*|opplysning\w*)")
_MORE = r"(?:andre|anna|ytterligere|ytterlegare|flere|fleire|øvrige|ekstra|nokre\s+andre|noen\s+andre)"
_NEG = r"(?:ingen|inga|ikke|ikkje)"
# The verbs and adjectives a sentence about the record uses of itself. "Ingen andre personer var til
# stede" is a fact about an event and has none of them.
_RECORD_WORDS = (r"(?:nevnt|nemnt|nemnd|nevnes|nemnast|nemnes|omtalt|omtala|omtales|omtalast|oppgitt|"
                 r"oppgjeve|opplyst|inkludert|inkluderte|inkluderast|registrert|registrerte|ført\s+inn|"
                 r"førd\s+inn|foreligger|føreligg|foreliggande|foreliggende|ligg\s+føre|ligger\s+føre|finnes|"
                 r"finst|inneholder|inneheld|dokumentert|tilgjengelig|tilgjengeleg|medtatt|teke\s+med|tatt\s+med)")

_META_PATTERNS: Dict[str, "re.Pattern"] = {
    # "ingen andre personer enn de nevnte er inkludert", "ingen ytterligere personopplysninger ble ført inn"
    "no_more_persons": re.compile(
        rf"\b{_NEG}\s+{_MORE}\s+{_PERSON_NOUNS}\b", re.IGNORECASE),
    # "ikke opplyst om andre personer", "ikkje oppgjeve fleire"
    # (the thing not stated about must be persons or data, or "enn de nevnte": "ikke opplyst om andre
    # mistenkte enn de to som er pågrepet" is a fact about a case)
    "not_stated_about_others": re.compile(
        rf"\b(?:{_NEG})\s+(?:er\s+)?(?:opplyst|oppgitt|oppgjeve|nevnt|nemnt|nemnd|omtalt|omtala)\s+"
        rf"(?:om\s+)?{_MORE}\s+(?:{_PERSON_NOUNS}|enn\b)", re.IGNORECASE),
    # "er den eneste personen som nevnes", "var einaste personen som er nemnd"
    "only_person_mentioned": re.compile(
        r"\b(?:eneste|einaste)\s+person(?:en)?\b[^.!?\n]{0,50}\b(?:nevn\w*|nemn\w*|omtal\w*|oppgi\w*|opplys\w*)",
        re.IGNORECASE),
    # "de nevnte personene" together with a restriction: "bare", "kun", "utover", "enn", "ingen"
    "the_named_persons": re.compile(
        r"\b(?:de|dei|disse|desse)\s+(?:nevnte|nemnde|omtalte|omtala|oppgitte|oppgjevne|ovennevnte|"
        r"ovanfornemnde)\s+(?:personene|personane|personer|personar|partene|partane)\b", re.IGNORECASE),
    # "uten at ytterligere opplysninger foreligger"
    "without_more_information": re.compile(
        rf"\b(?:uten|utan)\s+at\s+{_MORE}\s+{_PERSON_NOUNS}\b", re.IGNORECASE),
    # "Dokumentet inneholder ingen personopplysninger"
    "document_holds_no_data": re.compile(
        r"\b(?:inneholder|inneheld|omfatter|omfattar|har)\s+(?:ingen|inga)\s+(?:andre\s+|anna\s+|"
        r"ytterligere\s+|ytterlegare\s+)?(?:personopplysning\w*|personlige\s+opplysning\w*|personlege\s+opplysning\w*)",
        re.IGNORECASE),
    # "Opplysningene er registrerte fakta som inngår i den administrative prosessen"
    "registered_facts_filler": re.compile(
        r"\bregistrerte?\s+fakta\s+som\s+(?:inngår|inngår|ligg|ligger)\b", re.IGNORECASE),
}
_RESTRICTION = re.compile(r"\b(?:bare|berre|kun|utover|utanom|enn|ingen|inga|ikke|ikkje|andre|eneste|einaste)\b",
                          re.IGNORECASE)
_RECORD_RE = re.compile(rf"\b{_RECORD_WORDS}\b", re.IGNORECASE)
_NEEDS_RECORD_WORD = {"no_more_persons"}
_NEEDS_RESTRICTION = {"the_named_persons"}


def meta_statements(text: str) -> List[dict]:
    """Find the sentences that comment on which persons or data the document contains.

    Args:
        text: A generated document or section.

    Returns:
        One dict per sentence that matches, `{"pattern", "sentence", "start", "end"}`, in text order.
        `no_more_persons` ("ingen andre personer ...") needs a word about the record in the same
        sentence ("nevnt", "foreligger", "ført inn", ...): "Ingen andre personer var til stede" is a
        fact about an event and passes.
    """
    hits: List[dict] = []
    for start, end in gates.sentence_spans(text):
        sentence = text[start:end]
        if not sentence.strip():
            continue
        for name, pattern in _META_PATTERNS.items():
            if not pattern.search(sentence):
                continue
            if name in _NEEDS_RECORD_WORD and not _RECORD_RE.search(sentence):
                continue
            if name in _NEEDS_RESTRICTION and not _RESTRICTION.search(sentence.replace("de nevnte", "")):
                continue
            hits.append({"pattern": name, "sentence": sentence.strip(), "start": start, "end": end})
            break
    return hits


def strip_meta_statements(text: str, protected: Sequence[str]) -> Tuple[str, List[dict], List[dict]]:
    """Delete the meta-statement sentences that carry no planted string.

    A sentence that also holds a planted value, clause or negative cannot be deleted without losing
    a label, so it is returned as unremovable and the caller rejects the text instead.

    Args:
        text: A generated document or section.
        protected: Every string the text must keep verbatim (values, seeded clauses, negatives).

    Returns:
        `(text, removed, unremovable)`: the text without the removable sentences, with the blank
        space they leave tidied, and the hit dicts of each kind.
    """
    removed: List[dict] = []
    unremovable: List[dict] = []
    for hit in meta_statements(text):
        sentence = hit["sentence"]
        if any(p and (p in sentence or p[:1].swapcase() + p[1:] in sentence) for p in protected):
            unremovable.append(hit)
        else:
            removed.append(hit)
    for hit in sorted(removed, key=lambda h: h["start"], reverse=True):
        text = text[:hit["start"]] + text[hit["end"]:]
    if removed:
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, removed, unremovable


# -- G17 -----------------------------------------------------------------------------------

# Words that exist in Bokmål and not in Nynorsk, in either of Nynorsk's two written norms. Words
# that Nynorsk also accepts are deliberately absent: "tatt", "blitt", "kun", "mer", "dem", "selv",
# "bare", "mens", "meg", "etter". "ikke" and "hun" are here because a Nynorsk text has "ikkje" and
# "ho"; "ble" because it has "vart" or "blei".
_BOKMAL_WORDS = (
    "ikke hennes hvordan hvis mye noen noe uten fra sammen disse vært gjøre gjør ble skrev avholdt avholde "
    "bodd bodde innen siden hva hvem hvor hvorfor hvilken hvilke hvert hun jeg foreligger foreliggende "
    "fremgår fremgikk fremkom fremlagt oppholdt tillatelse tillatelsen uke uker ukene "
    "arbeidsgiver arbeidsgivere arbeidsgiveren arbeidsgivers").split()
_BOKMAL_WORD_RE = re.compile(r"\b(?:" + "|".join(_BOKMAL_WORDS) + r"|opphold\w*)\b", re.IGNORECASE)
# Bokmål endings: -lig adjectives (Nynorsk -leg), -het nouns (-heit) and the definite singular of
# an -ing noun (Nynorsk -inga: "saksbehandlingen", "meldingen"). "ingen" is the pronoun, "veldig" and
# "frivillig" are accepted in both, and a masculine -ing noun ("utlending") really does take -en in
# Nynorsk.
_BOKMAL_ENDINGS_RE = re.compile(
    r"\b(?!(?:ingen|veldig|frivillig)\b)(?!(?:utlending|arving|slektning|sørlending|nordlending|innlending)en\b)"
    r"(?:\w{3,}(?:lig|ligere|lige|ligst|ligste|ingen)|\w{2,}het(?:en|ene|er)?)\b", re.IGNORECASE)
# A neuter noun after "denne" ("Denne referatet" for "Dette referatet") is wrong in both norms; it
# is counted here because it is the commonest agreement slip of a model that writes Nynorsk.
_AGREEMENT_RE = re.compile(r"\bdenne\s+(?!(?:gangen|veka|helga|uka)\b)\w{3,}et\b", re.IGNORECASE)

# Threshold, from the 33 Nynorsk documents of the check run (fp16 and nf4) and `pilot_v5_bench`: 17
# had no Bokmål-only form, 3 had one, 7 had two and 6 had three; none had more. Three forms in one
# document is the point where it reads as Bokmål with some Nynorsk words; a short document, which
# cannot reach three, is also over the line with two forms at a rate of one per 100 words.
NYNORSK_MIN_FORMS = 3
NYNORSK_SHORT_MIN_FORMS = 2
NYNORSK_SHORT_RATE = 1.0


def bokmal_forms(text: str, exempt: Sequence[str] = ()) -> List[dict]:
    """Find the Bokmål-only forms in a Nynorsk text.

    Args:
        text: A generated Nynorsk document or section.
        exempt: Planted strings (names, organisations, clauses, negatives) whose characters are
            not the model's own Nynorsk and are not counted.

    Returns:
        One dict per form, `{"form", "start", "end", "kind"}` with kind `word`, `ending` or
        `agreement`, in text order.
    """
    shadow = list(text)
    for literal in exempt:
        pos = text.find(literal) if literal else -1
        while pos >= 0:
            shadow[pos:pos + len(literal)] = " " * len(literal)
            pos = text.find(literal, pos + len(literal))
    masked = "".join(shadow)
    hits: List[dict] = []
    for kind, pattern in (("word", _BOKMAL_WORD_RE), ("ending", _BOKMAL_ENDINGS_RE),
                          ("agreement", _AGREEMENT_RE)):
        for match in pattern.finditer(masked):
            hits.append({"form": match.group(0).lower(), "start": match.start(), "end": match.end(),
                         "kind": kind})
    hits.sort(key=lambda h: h["start"])
    deduped: List[dict] = []
    for hit in hits:
        if deduped and hit["start"] < deduped[-1]["end"]:
            continue
        deduped.append(hit)
    return deduped


def bokmal_sentences(text: str, forms: Sequence[dict]) -> List[dict]:
    """Group Bokmål forms by the sentence they stand in.

    Args:
        text: The text the forms were found in.
        forms: The result of `bokmal_forms` on the same text.

    Returns:
        `{"quote", "start", "end", "forms"}` for each sentence holding at least one form, quote
        being the sentence exactly as written.
    """
    out: List[dict] = []
    for start, end in gates.sentence_spans(text):
        inside = [f["form"] for f in forms if start <= f["start"] < end]
        if inside and text[start:end].strip():
            lead = len(text[start:end]) - len(text[start:end].lstrip())
            trail = len(text[start:end]) - len(text[start:end].rstrip())
            out.append({"quote": text[start + lead:end - trail], "start": start + lead,
                        "end": end - trail, "forms": inside})
    return out


def nynorsk_check(text: str, exempt: Sequence[str] = ()) -> dict:
    """Count the Bokmål-only forms of a Nynorsk text and say whether it is over the threshold.

    Args:
        text: A generated Nynorsk document.
        exempt: Planted strings that are not the model's own wording (see `bokmal_forms`).

    Returns:
        `{"count", "per_100_words", "forms", "over_threshold", "sentences"}`; `forms` is the list of
        form strings in text order and `sentences` the `bokmal_sentences` groups.
    """
    forms = bokmal_forms(text, exempt)
    words = max(1, len(text.split()))
    rate = round(100.0 * len(forms) / words, 2)
    over = len(forms) >= NYNORSK_MIN_FORMS or (len(forms) >= NYNORSK_SHORT_MIN_FORMS and rate >= NYNORSK_SHORT_RATE)
    return {"count": len(forms), "per_100_words": rate, "forms": [f["form"] for f in forms],
            "over_threshold": over, "sentences": bokmal_sentences(text, forms)}
