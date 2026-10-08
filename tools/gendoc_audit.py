"""G11, the content-audit gate: find sensitive statements nothing labels.

The verbatim-location guarantee makes every emitted span correct, but it says
nothing about completeness, and a measurement on `data/synthetic/pilot_v2`
showed exactly where that bites. The old detector in `models/merged` was run
over the 46 accepted pilot documents and its unmatched spans read as 62
genuinely sensitive statements the generator had written and not labelled --
the model elaborates around a seeded clause:

    seeded:    "brukar antidepressiva"
    generated: "brukar antidepressiva for å motverke depresjonssymptom knytt til smerten"

    seeded:    (a CRIMINAL clause about a driving offence)
    generated: "kjørte bil etter å ha konsumert alkohol", "reaksjonstiden var markert
                forsinket", "kontakter med personer som er kjent for å drive med
                illegale aktiviteter"

G7 cannot see any of this: it sweeps identifiers, names, dates and ages, and
these are clauses. Training on them teaches a detector to stay silent about
health and crime, which is the single most damaging thing this dataset could do.

So the same loaded model gets a second, deterministic pass over its own output:
the document, the spans already labelled, and an instruction to quote verbatim
every *other* statement disclosing a person's health, criminal matter, behaviour,
finances, belief, origin, sexuality, immigration status or family relation. A
second reason code covers the other pilot failure -- one police report framed an
ethnicity clause as investigative material ("hun har romani bakgrunn ifølge egne
opplysninger, hvilket har vært relevant for etterforskningen av hennes sosiale
nettverk") -- which is content that should never be generated at all, whatever
its labels say.

Two rules make this safe to act on:

* **Audit findings never become labels.** They are model-guessed spans, and
  adding them would replace the by-construction guarantee with exactly the
  guess-the-span pipeline this project is recovering from. A finding triggers a
  repair or a regeneration and is recorded in the metadata; it is never written
  to `output`.
* **Only exact substrings survive, and only the part no label already covers.**
  The model paraphrases when asked to quote; a paraphrase cannot be located, so
  it is dropped rather than trusted. A quote that merely restates an already
  labelled clause is not a finding either, so the labelled intervals are
  subtracted before the residue is measured.

A benchmark plants hard negatives -- "nektet å oppgi om han er fagorganisert" --
that read like a disclosure and are deliberately unlabelled. The auditor would
flag every one of them, and the repair would delete the very sentence the
benchmark exists to test, so planted negatives are *exempt*: they are subtracted
like labelled spans and a quote that lies wholly inside one is dropped. Anything
the model adds around a negative is still a finding.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence, Tuple

from gendoc_backends import MANIFEST_SENTINEL

AUDIT_OPEN = "<<<DOKUMENT>>>"
AUDIT_CLOSE = "<<<SLUTT PÅ DOKUMENT>>>"

REASON_CODES = {"SENSITIV": "unlabelled_sensitive", "RAMME": "sensitive_framing"}

_FINDING_RE = re.compile(r"^\s*(?:[-*\d.)\s]*)FUNN\s*\|\s*(SENSITIV|RAMME)\s*\|\s*(.+?)\s*$")

# Below this many characters of residue -- the part of the quote no label
# already covers -- a finding is not worth a repair pass: it is the model
# re-quoting a labelled clause with a word of context on either side.
MIN_RESIDUE_CHARS = 15

_AUDIT_TASK_NB = """Du er kontrollør i et datasett-prosjekt. Nedenfor står et dokument, og etter det en \
liste over de opplysningene i dokumentet som ALLEREDE er registrert.

Oppgave A: Finn hver setning eller setningsdel som sier noe KONKRET om en bestemt persons \
helse, funksjonsnedsettelse, medisinbruk, straffbare forhold eller mistanke om slike, \
atferdsmønster, økonomi eller gjeld, religion eller livssyn, politiske oppfatning, \
fagforeningsmedlemskap, etnisitet eller opprinnelse, seksualitet, innvandringsstatus eller \
familieforhold – og som IKKE står i listen over registrerte opplysninger.

Oppgave B: Finn hver setning som nevner etnisitet, religion, nasjonalitet, seksualitet \
eller innvandringsstatus OG samtidig knytter dette til mistanke, risiko, kriminalitet, \
farlighet eller troverdighet. Begge delene må være til stede i samme setning.

Dette skal IKKE regnes med, og er den vanligste feilen:
- navn, alder, kjønn, adresse, postnummer, telefonnummer, e-post, saksnummer, datoer, \
  stillingstittel, signatur og hilsen
- ren saksbehandlingstekst: lovhenvisninger, frister, klageadgang, utbetalingsvilkår, \
  tilbud om flere opplysninger, hvem som har behandlet saken
- dokumentets eget vedtak eller konklusjon, for eksempel at en søknad innvilges eller \
  avslås, eller at en ytelse tilkjennes
- generelle betraktninger, prinsipper og formaninger som ikke sier noe om denne personen
- ønsker om hva som bør vurderes eller vektlegges videre, uten at en ny opplysning oppgis

Det vanligste funnet er en UTVIDELSE av en opplysning som allerede er registrert: \
dokumentet legger til en årsak, en følge, en vurdering eller en konsekvens rundt den. \
Tillegget er et funn selv om kjernen står i listen. Sitér da bare tillegget. Eksempel:
- registrert: «vert utgreidd for mogleg hjartesvikt»
- i dokumentet: «... vert utgreidd for mogleg hjartesvikt, noko som er ein kritisk \
helsemessig faktor som må vurderast i samanheng med evna til å utføre ansvarlege oppgåver»
- funn: FUNN|SENSITIV|noko som er ein kritisk helsemessig faktor som må vurderast i \
samanheng med evna til å utføre ansvarlege oppgåver

Det er også et funn når dokumentet sier at en person er en fare for andre, at andre er \
utrygge på grunn av personen, eller at et forhold hos personen har påvirket arbeidet, \
helsen eller omgivelsene negativt – med mindre den formuleringen står i listen.

Eksempler på funn som SKAL med:
FUNN|SENSITIV|brukar antidepressiva for å motverke depresjonssymptom knytt til smerten
FUNN|SENSITIV|kjørte bil etter å ha konsumert alkohol
FUNN|SENSITIV|har hatt kontakter med personer som er kjent for å drive med illegale aktiviteter
FUNN|RAMME|hun har romani bakgrunn, hvilket har vært relevant for etterforskningen

Eksempler på setninger som IKKE skal med:
- «Hun bor per dags dato på adressen Myrveien 102A, 3040 Drammen.»
- «Vi står til disposisjon for ytterligere opplysninger.»
- «Det innvilges oppholdstillatelse for søkeren.»
- «Slik misbruk av tillit er alvorlig i et demokrati.»
- «Vennlig hilsen, allmennlege.»

Svar bare med linjer på dette formatet, én linje per funn:
FUNN|SENSITIV|<ordrett sitat fra dokumentet>
FUNN|RAMME|<ordrett sitat fra dokumentet>

Krav til sitatet: kopier tegn for tegn fra dokumentet, ikke omskriv, ikke forkort med «...», \
og sitér bare den delen som ikke allerede er registrert. Skriv ordet INGEN alene på én \
linje dersom du ikke finner noe. Ikke skriv forklaringer."""


def build_audit_prompt(text: str, labelled_spans: Sequence[str], doc_seed: int) -> str:
    """Build the G11 audit prompt for one generated document.

    Args:
        text: The document as it will be written, after marker stripping.
        labelled_spans: Every span already in the document's `output`.
        doc_seed: The document's seed, echoed into the mock manifest.

    Returns:
        The prompt, with a machine-readable manifest after `MANIFEST_SENTINEL`
        so `MockBackend` can answer it without a model.
    """
    listed = "\n".join(f"- «{s}»" for s in sorted(set(labelled_spans), key=len, reverse=True))
    body = (
        f"{_AUDIT_TASK_NB}\n\n{AUDIT_OPEN}\n{text}\n{AUDIT_CLOSE}\n\n"
        f"Allerede registrerte opplysninger:\n{listed or '- (ingen)'}\n"
    )
    manifest = [f"SEED|{doc_seed}", "AUDIT|1"]
    return body + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)


def parse_audit_reply(reply: str) -> List[Tuple[str, str]]:
    """Parse the model's audit reply into (reason code label, quote) pairs.

    Args:
        reply: Raw model output.

    Returns:
        List of (`SENSITIV`/`RAMME`, quote) pairs in reply order. A reply of
        `INGEN`, an empty reply or unparseable prose yields an empty list.
    """
    pairs: List[Tuple[str, str]] = []
    for line in reply.splitlines():
        match = _FINDING_RE.match(line)
        if not match:
            continue
        kind, quote = match.group(1), match.group(2).strip()
        quote = quote.strip("«»\"'").strip()
        if quote:
            pairs.append((kind, quote))
    return pairs


def _occurrences(text: str, span: str) -> List[Tuple[int, int]]:
    spots, i = [], text.find(span)
    while i >= 0:
        spots.append((i, i + len(span)))
        i = text.find(span, i + 1)
    return spots


def _covered_intervals(text: str, spans: Iterable[str]) -> List[Tuple[int, int]]:
    intervals: List[Tuple[int, int]] = []
    for span in spans:
        if span:
            intervals.extend(_occurrences(text, span))
    return intervals


def _residue(text: str, start: int, end: int, covered: List[Tuple[int, int]]) -> str:
    """Return the characters of text[start:end] that no covered interval overlaps."""
    keep = []
    for pos in range(start, end):
        if not any(lo <= pos < hi for lo, hi in covered):
            keep.append(text[pos])
    return "".join(keep)


def _trim_to_substring(text: str, quote: str) -> str:
    """Return the longest prefix-trimmed form of `quote` that is a substring of `text`.

    Models append or prepend a word when asked to quote. Stripping leading and
    trailing punctuation and a trailing partial word recovers the exact
    substring often enough to be worth doing, and returns "" when it does not.
    """
    candidate = quote.strip().strip(".,;:!?()[]")
    if candidate and candidate in text:
        return candidate
    words = candidate.split()
    for drop_end in range(0, min(4, len(words))):
        for drop_start in range(0, min(3, len(words) - drop_end)):
            trial = " ".join(words[drop_start:len(words) - drop_end]).strip(".,;:!?()[]")
            if len(trial) >= MIN_RESIDUE_CHARS and trial in text:
                return trial
    return ""


def filter_audit_findings(
    text: str, labelled_spans: Sequence[str], pairs: Sequence[Tuple[str, str]],
    exempt_spans: Sequence[str] = (),
) -> List[dict]:
    """Keep only audit findings that are exact substrings and not already labelled.

    Args:
        text: The document text.
        labelled_spans: Every span in the document's `output`.
        pairs: Parsed (kind, quote) pairs from `parse_audit_reply`.
        exempt_spans: Planted hard negatives. Treated like labelled spans for the
            residue test, and a quote lying wholly inside one is dropped for
            either reason code.

    Returns:
        Finding dicts with `reason`, `quote`, `residue`, `start` and `end`.
        A quote the label set already covers entirely, or whose uncovered
        residue is shorter than `MIN_RESIDUE_CHARS`, is dropped; so is a quote
        that is not a substring of the text at all.
    """
    exempt = _covered_intervals(text, exempt_spans)
    covered = _covered_intervals(text, list(labelled_spans) + list(exempt_spans))
    findings: List[dict] = []
    seen: set = set()
    for kind, raw_quote in pairs:
        quote = _trim_to_substring(text, raw_quote)
        if not quote or quote in seen:
            continue
        spots = _occurrences(text, quote)
        if not spots:
            continue
        start, end = spots[0]
        if any(lo <= start and end <= hi for lo, hi in exempt):
            continue
        residue = _residue(text, start, end, covered)
        # A RAMME finding is about how a sentence frames a fact, so the fact
        # itself being labelled does not excuse it; only the substring test and
        # a non-trivial length apply.
        if kind == "SENSITIV" and len(residue.strip()) < MIN_RESIDUE_CHARS:
            continue
        if kind == "RAMME" and len(quote.strip()) < MIN_RESIDUE_CHARS:
            continue
        seen.add(quote)
        findings.append({
            "reason": REASON_CODES[kind], "kind": kind, "quote": quote,
            "residue": residue.strip(), "start": start, "end": end,
            "raw_quote": raw_quote if raw_quote != quote else None,
        })
    return findings


def exempt_quote_count(text: str, pairs: Sequence[Tuple[str, str]], exempt_spans: Sequence[str]) -> int:
    """Count the audit quotes that lie wholly inside a planted negative.

    Reported so a benchmark run can show how often the auditor wanted to flag a
    hard negative and was overruled, which is the evidence that the exemption is
    doing something rather than being unreachable.
    """
    exempt = _covered_intervals(text, exempt_spans)
    count = 0
    for _kind, raw_quote in pairs:
        quote = _trim_to_substring(text, raw_quote)
        spots = _occurrences(text, quote) if quote else []
        if spots and any(lo <= spots[0][0] and spots[0][1] <= hi for lo, hi in exempt):
            count += 1
    return count


def audit_stats(pairs: Sequence[Tuple[str, str]], findings: Sequence[dict]) -> Dict[str, int]:
    """Summarise one audit pass: what the model said and what survived filtering."""
    return {
        "raw_quotes": len(pairs),
        "kept": len(findings),
        "dropped_not_substring_or_covered": len(pairs) - len(findings),
        "unlabelled_sensitive": sum(1 for f in findings if f["reason"] == "unlabelled_sensitive"),
        "sensitive_framing": sum(1 for f in findings if f["reason"] == "sensitive_framing"),
    }


def build_audit_repair_prompt(
    text: str, findings: Sequence[dict], keep_verbatim: Sequence[str], form: str, doc_seed: int,
) -> str:
    """Ask the model to delete or neutralise exactly the audited sentences.

    The repair is deliberately narrow: remove or make administratively neutral
    the quoted material, keep every planned value and clause character for
    character, and add nothing. The result goes back through every gate and
    through the audit again, so a repair that introduces a new problem is
    caught rather than shipped.

    Args:
        text: The document to repair.
        findings: Surviving audit findings.
        keep_verbatim: Planned values and clauses that must survive unchanged.
        form: "nb" or "nn", so the repaired document stays in its own form.
        doc_seed: Seed echoed into the mock manifest.

    Returns:
        The repair prompt, with a manifest after `MANIFEST_SENTINEL`.
    """
    form_name = "bokmål" if form == "nb" else "nynorsk"
    quoted = "\n".join(f"- «{f['quote']}»" for f in findings)
    keep = "\n".join(f"- «{v}»" for v in sorted(set(keep_verbatim), key=len, reverse=True))
    body = (
        f"Nedenfor er et dokument på {form_name}. Følgende formuleringer skal fjernes helt, "
        f"eller erstattes med nøytral saksbehandlingstekst som ikke sier noe om personens "
        f"forhold:\n{quoted}\n\n{AUDIT_OPEN}\n{text}\n{AUDIT_CLOSE}\n\n"
        "Oppgave: Skriv dokumentet ut på nytt, likt ord for ord bortsett fra at de nevnte "
        "formuleringene er fjernet eller gjort nøytrale. Følgende skal fortsatt stå ORDRETT, "
        f"tegn for tegn:\n{keep}\n"
        "Ikke legg til nye opplysninger om noen person, og ikke skriv nye navn, datoer eller "
        "tall. Svar bare med hele dokumentet."
    )
    manifest = ([f"SEED|{doc_seed}", "AUDIT_REPAIR|1"]
                + [f"REMOVE|{f['quote']}" for f in findings]
                + [f"KEEP|{v}" for v in sorted(set(keep_verbatim), key=len, reverse=True)])
    return body + "\n" + MANIFEST_SENTINEL + "\n" + "\n".join(manifest)
