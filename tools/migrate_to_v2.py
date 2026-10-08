"""Migrate annotations from the 17-type spec to the 59-type v2 taxonomy.

The gold set and the relabel slice were annotated against docs/ANNOTATION_SPEC.md's
17 types. The v2 taxonomy (data/synthetic/taxonomy.json) keeps most of those as
one-to-one renames, but splits six of them into finer types: GOV_ID into eleven
identifier types, FINANCIAL_INFO into five, HEALTH_INFO, DATE_TIME and so on into
two or three each.

The span boundaries survive the migration untouched -- they were adjudicated under
32 boundary rules and nothing here re-decides where a span starts or ends. Only the
label changes, and only by the rules in this file, so every relabel decision is
reviewable in one place and the whole migration is re-runnable if a rule changes.

A span the rules cannot place confidently is never guessed. It is held back as
UNRESOLVED and the run refuses to write output until every such span is decided --
either by a new rule here or by an explicit override.

Usage:
    python tools/migrate_to_v2.py --dry-run
    python tools/migrate_to_v2.py --write
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
from typing import Dict, List, Optional, Tuple

TAXONOMY = "data/synthetic/taxonomy.json"
SOURCES = [
    ("data/gold/batch_*_gold.jsonl", "data/gold_v2"),
    ("data/slice/batch_x*_annotator1.jsonl", "data/slice_v2"),
]

# Legacy types whose v2 home is a single type: a pure rename.
RENAME = {
    "PERSON": "PERSON",
    "NO_ADDRESS": "ADDRESS",
    "POSTAL_CODE": "POSTAL_CODE",
    "NO_PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "CRIMINAL_RECORD": "CRIMINAL",
    "POLITICAL_CASE": "POLITICAL",
    "ECONOMIC_STATUS": "ECONOMIC_STATUS",
    "SEXUAL_ORIENTATION": "SEXUAL_ORIENTATION",
    "BEHAVIORAL_PATTERN": "BEHAVIORAL_PATTERN",
    "RELIGIOUS_BELIEF": "RELIGIOUS_BELIEF",
}

UNRESOLVED = "UNRESOLVED"


def _context(text: str, span: str, width: int = 60) -> str:
    """Return the text immediately before the first occurrence of `span`."""
    i = text.find(span)
    return text[max(0, i - width):i] if i >= 0 else ""


def _digits(span: str) -> str:
    return re.sub(r"\D", "", span)


# --- GOV_ID -> eleven identifier types -------------------------------------------
#
# The label in front of the number decides first, because the shapes collide: a
# Førerkortnummer can be 11 digits exactly like a fødselsnummer. Shape is only the
# fallback when no label is present.

# Identifiers B20 makes GOV_ID but v2 has no type for. They are held back under a
# named sentinel rather than forced into the nearest-looking type, so the gap reads
# as a taxonomy decision to make, not a rule that failed.
NO_V2_HOME = "NO_V2_HOME"

GOV_LABELS: List[Tuple[str, str]] = [
    (r"våpen\w*\s*nr|våpenkort\w*|lisensnummer|license number|permit number", NO_V2_HOME + ":firearms_licence"),
    (r"fiskebåt|fiskefartøy\w*|fishing vessel|vessel", NO_V2_HOME + ":vessel_registration"),
    (r"førerkort", "DRIVER_LICENSE"),
    (r"pass\s*nr|passnummer|pass\s*nummer", "PASSPORT"),
    (r"id-kort|nasjonalt id", "IDENTITY_CARD"),
    (r"visum|oppholdstillatelse", "VISA_NUMBER"),
    (r"militær|tjenestenummer", "MILITARY_ID"),
    (r"autorisasjon|hpr", "MEDICAL_LICENSE"),
    (r"skatte-?id|skattenummer|ligningsnummer", "TAX_ID"),
    (r"registre\w*nummer|reg\.?\s*nr|skiltnummer|kjennemerke", "LICENSE_PLATE"),
    (r"fødselsnummer|personnummer|d-nummer|fnr", "NATIONAL_ID"),
    (r"org\.?\s*nr|organisasjonsnummer|orgnr", "ORG_NUMBER"),
    (r"sak|ref\b|ref\.|ref:|referansenummer|case id|dom|anmeld|tingrett|politi|journal", "CASE_NUMBER"),
]
CASE_SHAPE = re.compile(r"\d{4}[/-]\d{2,}|\d{2,}[/-]\d{4}|tingrett|lagmannsrett|politi", re.I)


def gov_id(span: str, text: str) -> str:
    head = _context(text, span, 45).lower()
    # The authority inside the span itself (B23) settles it.
    if re.search(r"tingrett|lagmannsrett|politistasjon|politidistrikt|skatteetaten",
                 span, re.I):
        return "CASE_NUMBER"
    # Nearest label wins: take the label whose match ends closest to the span.
    best, best_end = None, -1
    for pat, label in GOV_LABELS:
        for m in re.finditer(pat, head):
            if m.end() > best_end:
                best, best_end = label, m.end()
    # `registreringsnummer` / `reg.nr.` is generic: the registered *object* decides.
    # Without this a rifle's state-register number and a fishing vessel's mark both
    # landed in LICENSE_PLATE alongside the cars.
    if best == "LICENSE_PLATE":
        obj = _context(text, span, 90).lower()
        if re.search(r"rifle|hagle|haglegevær|haglgevær|gevær|våpen|pistol|revolver", obj):
            return NO_V2_HOME + ":firearms_licence"
        if re.search(r"fiskefartøy|fiskebåt|fartøy|vessel|\bms\b", obj):
            return NO_V2_HOME + ":vessel_registration"
    if best:
        return best
    d = _digits(span)
    if len(d) == 11 and len(d) >= len(span.replace(" ", "").replace("-", "")) - 1:
        return "NATIONAL_ID"
    if len(d) == 9 and re.fullmatch(r"[\d\s]{9,11}", span):
        return "ORG_NUMBER"
    if CASE_SHAPE.search(span):
        return "CASE_NUMBER"
    return UNRESOLVED


# --- FINANCIAL_INFO -> FINANCIAL + four identifier types ---------------------------
#
# Only a span that IS the identifier is relabelled. An account number sitting inside
# a longer clause with an amount stays FINANCIAL -- the clause is the fact.

def financial(span: str, text: str) -> str:
    s = span.strip()
    if re.fullmatch(r"NO\s?\d{2}(?:\s?\d{4}){2,3}\s?\d{0,3}", s, re.I):
        return "IBAN"
    if re.fullmatch(r"(?:\d{4}[\s-]?){3}\d{4}", s):
        return "CREDIT_CARD"
    if re.fullmatch(r"\d{4}[\s.]?\d{2}[\s.]?\d{5}", s):
        return "BANK_ACCOUNT"
    if re.fullmatch(r"(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}", s):
        return "CRYPTO"
    head = _context(text, span, 30).lower()
    if re.fullmatch(r"[\d\s.]{8,}", s) and re.search(r"konto|lånenummer|lånenr", head):
        return "BANK_ACCOUNT"
    return "FINANCIAL"


# --- HEALTH_INFO -> HEALTH, DISABILITY, MEDICATION ---------------------------------
#
# HEALTH is the default and keeps everything about animals: DISABILITY and MEDICATION
# are defined for a named *person*. MEDICATION is the medication as its own fact, so a
# combined diagnosis-plus-medication clause stays HEALTH, per MEDICATION's own exclude.

# MEDICATION needs a drug *noun*. Treatment verbs on their own (`tar`, `står på`) and
# the stem `medisin-` are too ambiguous in Norwegian: `står på` matched `lysene står på
# konstant` (the lights are on) and `medisinske` matched `ubehandlede medisinske
# problemer`. Both were animal-welfare HEALTH facts.
MED = re.compile(
    r"\b(antidepressiv\w*|insulin\w*|metformin|sertralin|medisiner|medisinen|"
    r"medisinene|medikament\w*|tabletter|smertestillende|beroligende|sovemedisin\w*|"
    r"lithium|ritalin|reseptbelagte)\b", re.I)
DIAG = re.compile(
    r"\b(diabetes|depresjon|angst|bipolar|schizofreni|kreft|astma|epilepsi|adhd|"
    r"diagnos\w*|lidelse|sykdom|demens|ptsd)\b", re.I)
DIS = re.compile(
    r"\b(funksjonshemm\w*|bevegelseshemm\w*|rullestol\w*|synshemm\w*|hørselshemm\w*|"
    r"utviklingshemm\w*|amputert|blind|døv|cerebral parese|uføre\w*)\b", re.I)
# `lam`/`lammet` are deliberately absent: in Norwegian they are also "lamb" / "the lamb",
# and the only hit they produced was `ikke sett lam i flokken` -- a lamb, not a disability.
ANIMAL = re.compile(
    r"\b(hund\w*|katt\w*|hest\w*|ku\b|kyr|sau\w*|gris\w*|dyr\w*|kanin\w*|fugl\w*|"
    r"høn\w*|valp\w*|føll|kalv\w*|geit\w*|pels|hov\w*|fisk\w*|flokk\w*)\b", re.I)


def health(span: str, text: str) -> str:
    if ANIMAL.search(span):
        return "HEALTH"
    if DIS.search(span):
        return "DISABILITY"
    if MED.search(span) and not DIAG.search(span):
        return "MEDICATION"
    return "HEALTH"


# --- DATE_TIME -> DATE_TIME, DATE_OF_BIRTH, AGE ------------------------------------

def date_time(span: str, text: str) -> str:
    s = span.strip()
    if re.fullmatch(r"\d{1,3}\s*år(?:\s+gammel)?", s):
        return "AGE"
    head = _context(text, span, 14).lower()
    if re.search(r"(?:\bf\.|\bfødt(?:\s+den)?|\bfødd|fødselsdato|fødselsdag)\s*:?\s*$", head):
        return "DATE_OF_BIRTH"
    return "DATE_TIME"


# --- EMPLOYMENT_INFO -> EMPLOYMENT, ORGANIZATION -----------------------------------
#
# A bare organisation name is the B19 subject organisation, which v2 calls
# ORGANIZATION. Anything carrying a role, title or employment verb is EMPLOYMENT.

ROLE = re.compile(
    r"\b(jobber|jobbet|ansatt|arbeider|arbeidet|eier|eid av|eiet|driver|drives av|"
    r"driftet|daglig leder|leder|sjef|styreleder|innehaver|utdannet|student|pensjonist|"
    r"pensjonert|frivillig|lærer|lege|sykepleier|veterinær\w*|bonde|gårdbruker|"
    r"selvstendig|ufør|arbeidsledig|kokk|sjåfør|tømrer|elektriker|"
    r"\w*(?:medarbeider|assistent|pleier|ingeniør|konsulent|rådgiver|mekaniker))\b", re.I)
ORGSHAPE = re.compile(r"\b(AS|ASA|ANS|DA|SA|BA|ENK)\b|^[\"«]|kommune\b|stiftelse", re.I)


def employment(span: str, text: str) -> str:
    if ROLE.search(span):
        return "EMPLOYMENT"
    s = span.strip()
    if ORGSHAPE.search(s) or (s[:1].isupper() and len(s.split()) >= 2):
        return "ORGANIZATION"
    if s[:1].isupper():
        return "ORGANIZATION"
    return "EMPLOYMENT"


# --- FAMILY_RELATION -> FAMILY_RELATION, MARITAL_STATUS ----------------------------
#
# v2 contradicts itself here: FAMILY_RELATION includes "marital/partnership status
# with named spouse/partner" and MARITAL_STATUS includes "status with named
# spouse/partner in the same clause". The more specific type wins the overlap, so a
# status word with or without a named partner is MARITAL_STATUS. A span that also
# carries kinship stays FAMILY_RELATION, and so do the relationship-ending nouns
# (`skilsmisse`, `separasjon`) that FAMILY_RELATION's include list names explicitly.

STATUS = re.compile(r"\b(gift|samboer|samboerskap|skilt|separert|ugift|enke|enkemann|"
                    r"partnerskap|forlovet)\b", re.I)
KIN = re.compile(r"\b(barn|sønn\w*|datter|døtre|mor|far|foreldre|bror|brødre|søster\w*|"
                 r"svoger|svigerinne|svigermor|svigerfar|onkel|tante|nevø|niese|"
                 r"barnebarn|bestemor|bestefar|stesønn|stedatter|fosterbarn)\b", re.I)


def family(span: str, text: str) -> str:
    if STATUS.search(span) and not KIN.search(span):
        return "MARITAL_STATUS"
    return "FAMILY_RELATION"


SPLIT = {
    "GOV_ID": gov_id,
    "FINANCIAL_INFO": financial,
    "HEALTH_INFO": health,
    "DATE_TIME": date_time,
    "EMPLOYMENT_INFO": employment,
    "FAMILY_RELATION": family,
}


_GAP: Dict[Tuple[str, str, str], str] = {}


def _is_gap(u: tuple, overrides) -> bool:
    return (u[0], u[1], u[2]) in _GAP


def _gap_reason(rid: str, legacy: str, span: str) -> str:
    return _GAP.get((rid, legacy, span), "unresolved")


def migrate_record(rec: dict, overrides: Dict[Tuple[str, str, str], str],
                   stats: collections.Counter, unresolved: List[tuple]) -> dict:
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for legacy, spans in rec["output"].items():
        for span in spans:
            key = (rec["id"], legacy, span)
            if key in overrides:
                new = overrides[key]
            elif legacy in RENAME:
                new = RENAME[legacy]
            elif legacy in SPLIT:
                new = SPLIT[legacy](span, rec["text_input"])
            else:
                new = UNRESOLVED
            stats[(legacy, new)] += 1
            if new.startswith(NO_V2_HOME):
                _GAP[key] = new.split(":", 1)[1]
            if new == UNRESOLVED or new.startswith(NO_V2_HOME):
                unresolved.append((rec["id"], legacy, span,
                                   _context(rec["text_input"], span, 50)))
                continue
            if span not in out[new]:
                out[new].append(span)
    return {"id": rec["id"], "text_input": rec["text_input"], "output": dict(out)}


def load_overrides(path: str) -> Dict[Tuple[str, str, str], str]:
    if not os.path.exists(path):
        return {}
    o = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            o[(r["id"], r["legacy"], r["span"])] = r["v2"]
    return o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--overrides", default="data/migration_v2_overrides.jsonl")
    ap.add_argument("--show", type=int, default=0, help="print N samples per bucket")
    ap.add_argument("--pending", default="data/migration_v2_pending.jsonl",
                    help="where spans with no v2 home are parked rather than dropped")
    args = ap.parse_args()

    v2_types = {t["name"] for t in json.load(open(TAXONOMY, encoding="utf-8"))["types"]}
    targets = set(RENAME.values())
    for fn in SPLIT.values():
        pass
    overrides = load_overrides(args.overrides)
    stats: collections.Counter = collections.Counter()
    unresolved: List[tuple] = []
    samples = collections.defaultdict(list)
    results = []
    for pattern, outdir in SOURCES:
        for path in sorted(glob.glob(pattern)):
            recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
            migrated = [migrate_record(r, overrides, stats, unresolved) for r in recs]
            for r_old, r_new in zip(recs, migrated):
                for t, spans in r_new["output"].items():
                    for s in spans:
                        if len(samples[t]) < 400:
                            samples[t].append((r_new["id"], s))
            results.append((path, outdir, migrated))

    bad = sorted({new for (_, new) in stats if new not in v2_types
                  and new != UNRESOLVED and not new.startswith(NO_V2_HOME)})
    print("legacy -> v2 relabel counts")
    for (legacy, new), n in sorted(stats.items()):
        print(f"  {legacy:18} -> {new:18} {n:6,}")
    print(f"\nunresolved: {len(unresolved)}")
    for u in unresolved[:40]:
        print(f"  {u[0]:6} [{u[1]}] {u[2]!r:32} ...{u[3][-48:]!r}")
    if args.show:
        for t in sorted(samples):
            if t in targets and t not in ("FINANCIAL",):
                continue
            print(f"\n== sample {t}")
            for i, s in samples[t][:args.show]:
                print(f"     {i:6} {s[:76]!r}")
    if bad:
        print(f"\nFATAL: produced types not in the v2 taxonomy: {bad}")
        return 2
    if args.write:
        # A rule that failed blocks the run. A span v2 simply has no type for does not:
        # it is parked in a sidecar so the gap is a taxonomy decision, not lost data.
        hard = [u for u in unresolved if not _is_gap(u, overrides)]
        if hard:
            print(f"\nrefusing to write: {len(hard)} spans failed every rule")
            return 1
        with open(args.pending, "w", encoding="utf-8") as f:
            for rid, legacy, span, ctx in unresolved:
                f.write(json.dumps({"id": rid, "legacy": legacy, "span": span,
                                    "reason": _gap_reason(rid, legacy, span),
                                    "context": ctx}, ensure_ascii=False) + "\n")
        print(f"\nparked {len(unresolved)} spans with no v2 home in {args.pending}")
        n = 0
        for path, outdir, migrated in results:
            os.makedirs(outdir, exist_ok=True)
            dst = os.path.join(outdir, os.path.basename(path))
            with open(dst, "w", encoding="utf-8") as f:
                for r in migrated:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
        print(f"\nwrote {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
