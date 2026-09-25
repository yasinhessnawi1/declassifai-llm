"""Flag mechanically-detectable values that a document contains but no span covers.

The recall sweeps are good at judgement calls and measurably worse at the boring
categories. Across the first eleven batches the residual misses clustered in
values a regex can find exactly: an employer name in a "Navn på ... virksomhet:"
field, the company in an "Org.nr.: NNN (Company AS)" parenthetical, a
"Fødselsnummer:" value at the end of a document, a phone number, an email.

This is deliberately a *reporting* tool, not a repair tool. Whether a detected
value should be tagged still needs the spec -- B12 tags a company name only when
it identifies where the person works or owns a business, so an incidental
mention of a bank is a legitimate non-match. It prints candidates for a human or
an agent to rule on, and never edits a label file.

Usage:
    python tools/check_coverage.py data/gold/batch_a_gold.jsonl
    python tools/check_coverage.py data/gold/*_gold.jsonl --quiet
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from typing import Dict, Iterator, List, Tuple

# Each probe yields the exact substrings it believes must appear in some span.
# Patterns capture the value alone, never a leading preposition, because the
# span must be verbatim and a captured "Under inspeksjonen av X AS" is noise.
PROBES: Dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w{2,}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+47\s?)?(?:\d{2}\s?){3}\d{2}(?!\d)"),
    "id_number": re.compile(r"(?<!\d)\d{9}(?!\d)|(?<!\d)\d{11}(?!\d)"),
    "employer_field": re.compile(
        r"Navn på dyreeier eller virksomhet:\s*\"?([^\"\n,]{3,40}?)\"?\s*(?:Adresse|\(|$)"
    ),
    "orgnr_company": re.compile(r"Org\.?nr\.?:?[^()\n]{0,30}\(([^)\n]{3,40})\)"),
}

# Placeholder values that occupy a name field without naming anything. These are
# not employers and must never be flagged as missing coverage.
PLACEHOLDERS = {
    "privatperson", "ukjent", "unknown", "not applicable", "n/a", "none",
    "none provided", "gårdsbruk", "ingen", "blank", "-",
}


# A probe hit is excused when any span already covers it, or when the document
# simply has no such value -- both are normal.
def _hits(text: str, pattern: re.Pattern) -> Iterator[str]:
    for match in pattern.finditer(text):
        value = (match.group(1) if match.groups() else match.group(0)).strip()
        if len(value) >= 3 and value.strip().lower() not in PLACEHOLDERS:
            yield value


def scan(path: str) -> Tuple[List[tuple], collections.Counter]:
    """Find probe values in each document that no span covers.

    Args:
        path: JSONL label file with text_input and output per record.

    Returns:
        Tuple of (list of (doc id, probe name, value), counter by probe).
    """
    findings: List[tuple] = []
    counts: collections.Counter = collections.Counter()

    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        text = record.get("text_input", "")
        spans = [s for v in record.get("output", {}).values() for s in v]
        blob = " || ".join(spans)

        for name, pattern in PROBES.items():
            for value in set(_hits(text, pattern)):
                # Covered if any span contains it, or it contains a tagged span
                # (a longer "eier av X AS" span legitimately covers "X AS").
                if value in blob:
                    continue
                if any(s and (s in value or value in s) for s in spans):
                    continue
                findings.append((record.get("id", "?"), name, value))
                counts[name] += 1
    return findings, counts


def main() -> int:
    """CLI entry point.

    Returns:
        1 if any candidate was flagged, else 0, so this can gate a pipeline.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--quiet", action="store_true",
                        help="totals only, omit per-value detail")
    args = parser.parse_args()

    grand: collections.Counter = collections.Counter()
    for path in args.paths:
        findings, counts = scan(path)
        grand.update(counts)
        label = path.rsplit("/", 1)[-1]
        if not findings:
            print(f"{label:34} clean")
            continue
        print(f"{label:34} {len(findings)} candidate(s)")
        if not args.quiet:
            for doc, name, value in findings:
                print(f"    [{doc} {name}] {value!r}")

    if grand:
        print(f"\ntotal candidates: {sum(grand.values())}  {dict(grand)}")
        print("Candidates are values present in the text that no span covers.")
        print("Rule on each against the spec -- an incidental mention may be a")
        print("legitimate non-match. This tool never edits a label file.")
    return 1 if grand else 0


if __name__ == "__main__":
    raise SystemExit(main())
