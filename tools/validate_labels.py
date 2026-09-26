"""Validate and repair NER label files for the Norwegian PII dataset.

The dataset is JSONL with one object per line:

    {"text_input": "<document>", "output": {"<TYPE>": ["<span>", ...], ...}}

This module enforces the invariants the annotation spec depends on. The single
most important one is that every labeled span must be an exact, case-sensitive
substring of its source document -- labels are extractions, never paraphrases,
translations or normalisations.

Usage:
    python tools/validate_labels.py data/combined_data.jsonl
    python tools/validate_labels.py data/combined_data.jsonl --fix data/clean.jsonl
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from typing import Dict, List, Optional, Tuple

# The 18 types present in the raw corpus. The training config currently lists
# only 15 of these; see docs/DATA_QUALITY.md for the discrepancy.
ALL_TYPES = [
    "PERSON", "DATE_TIME", "HEALTH_INFO", "GOV_ID", "NO_ADDRESS",
    "CRIMINAL_RECORD", "POSTAL_CODE", "NO_PHONE_NUMBER", "EMAIL_ADDRESS",
    "FAMILY_RELATION", "CONTEXT_SENSITIVE", "FINANCIAL_INFO",
    "EMPLOYMENT_INFO", "POLITICAL_CASE", "BEHAVIORAL_PATTERN",
    "ECONOMIC_STATUS", "IDENTIFIABLE_IMAGE", "SEXUAL_ORIENTATION",
]

# Violation codes, ordered roughly by severity.
NOT_A_SUBSTRING = "not_a_substring"
UNKNOWN_TYPE = "unknown_type"
CASE_MISMATCH = "case_mismatch"
WHITESPACE_MISMATCH = "whitespace_mismatch"
PADDED_SPAN = "padded_span"
DUPLICATE_SPAN = "duplicate_span"
EMPTY_SPAN = "empty_span"
BAD_SHAPE = "bad_shape"

# Violations that _fix_record can repair without human or model judgement.
REPAIRABLE = {CASE_MISMATCH, WHITESPACE_MISMATCH, PADDED_SPAN, DUPLICATE_SPAN}


def load_types(config_path: Optional[str]) -> List[str]:
    """Read the entity type names from a config.yaml without needing PyYAML.

    Args:
        config_path: Path to config.yaml, or None to use ALL_TYPES.

    Returns:
        List of entity type names.
    """
    if not config_path:
        return list(ALL_TYPES)
    types, in_section = [], False
    with open(config_path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("entity_types:"):
                in_section = True
                continue
            if in_section:
                match = re.match(r"^  ([A-Z_]+):", line)
                if match:
                    types.append(match.group(1))
                elif line.strip() and not line.startswith(" "):
                    break
    return types or list(ALL_TYPES)


def _locate(text: str, span: str) -> Tuple[str, Optional[str]]:
    """Classify how a span relates to its document and recover the true text.

    Args:
        text: The source document.
        span: The labeled span as stored in the dataset.

    Returns:
        Tuple of (violation code or "ok", the corrected verbatim span or None).
    """
    if span in text:
        return "ok", span

    stripped = span.strip()
    if stripped and stripped in text:
        return PADDED_SPAN, stripped

    lowered = text.lower()
    index = lowered.find(span.lower())
    if index >= 0:
        return CASE_MISMATCH, text[index:index + len(span)]

    # Collapse runs of whitespace and retry, recovering the original slice by
    # matching token-by-token so the replacement stays verbatim.
    collapsed = " ".join(span.split())
    if collapsed:
        pattern = r"\s+".join(re.escape(part) for part in collapsed.split())
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return WHITESPACE_MISMATCH, match.group(0)

    return NOT_A_SUBSTRING, None


def validate_record(record: dict, types: List[str]) -> List[dict]:
    """Check a single dataset record against the label invariants.

    Args:
        record: Parsed JSON object with text_input and output keys.
        types: Allowed entity type names.

    Returns:
        List of violation dicts, each with code, type, span and optional fix.
    """
    problems: List[dict] = []
    text = record.get("text_input")
    output = record.get("output")

    if not isinstance(text, str) or not isinstance(output, dict):
        return [{"code": BAD_SHAPE, "type": None, "span": None, "fix": None}]

    allowed = set(types)
    for etype, spans in output.items():
        if etype not in allowed:
            problems.append(
                {"code": UNKNOWN_TYPE, "type": etype, "span": None, "fix": None}
            )
            continue
        if not isinstance(spans, list):
            problems.append(
                {"code": BAD_SHAPE, "type": etype, "span": None, "fix": None}
            )
            continue

        seen = set()
        for span in spans:
            if not isinstance(span, str):
                problems.append(
                    {"code": BAD_SHAPE, "type": etype, "span": None, "fix": None}
                )
                continue
            if not span.strip():
                problems.append(
                    {"code": EMPTY_SPAN, "type": etype, "span": span, "fix": None}
                )
                continue
            if span in seen:
                problems.append(
                    {"code": DUPLICATE_SPAN, "type": etype, "span": span, "fix": None}
                )
                continue
            seen.add(span)

            code, fixed = _locate(text, span)
            if code != "ok":
                problems.append(
                    {"code": code, "type": etype, "span": span, "fix": fixed}
                )
    return problems


def fix_record(record: dict, types: List[str]) -> Tuple[dict, collections.Counter]:
    """Apply every mechanical repair to a record.

    Unknown types, empty spans and spans absent from the text are dropped --
    an absent span cannot be repaired without judgement, so it is quarantined
    for model or human review rather than guessed at.

    Args:
        record: Parsed JSON object with text_input and output keys.
        types: Allowed entity type names.

    Returns:
        Tuple of (repaired record, counter of applied actions).
    """
    actions: collections.Counter = collections.Counter()
    text = record.get("text_input", "")
    output = record.get("output") or {}
    allowed = set(types)
    repaired: Dict[str, List[str]] = {}

    for etype, spans in output.items():
        if etype not in allowed:
            actions[f"dropped_{UNKNOWN_TYPE}"] += 1
            continue
        if not isinstance(spans, list):
            actions[f"dropped_{BAD_SHAPE}"] += 1
            continue

        kept: List[str] = []
        seen = set()
        for span in spans:
            if not isinstance(span, str) or not span.strip():
                actions[f"dropped_{EMPTY_SPAN}"] += 1
                continue
            code, fixed = _locate(text, span)
            if code == NOT_A_SUBSTRING:
                actions[f"dropped_{NOT_A_SUBSTRING}"] += 1
                continue
            if code != "ok":
                actions[f"repaired_{code}"] += 1
            if fixed in seen:
                actions[f"dropped_{DUPLICATE_SPAN}"] += 1
                continue
            seen.add(fixed)
            kept.append(fixed)

        if kept:
            repaired[etype] = kept

    return {"text_input": text, "output": repaired}, actions


def scan(path: str, types: List[str]) -> dict:
    """Validate a whole dataset file and summarise what is wrong with it.

    Args:
        path: Path to the JSONL dataset.
        types: Allowed entity type names.

    Returns:
        Dict with counts, per-code and per-type breakdowns, and examples.
    """
    codes: collections.Counter = collections.Counter()
    per_type: collections.Counter = collections.Counter()
    unknown: collections.Counter = collections.Counter()
    examples: Dict[str, List[Tuple[str, str]]] = collections.defaultdict(list)
    variants: Dict[str, set] = collections.defaultdict(set)

    total = spans = malformed = empty = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue

        text = record.get("text_input", "")
        output = record.get("output") or {}
        spans += sum(len(v) for v in output.values() if isinstance(v, list))

        if not any(v for v in output.values() if isinstance(v, list)):
            empty += 1

        digest = hashlib.md5(text.encode()).hexdigest()
        variants[digest].add(
            json.dumps(
                {k: sorted(set(v)) for k, v in output.items() if v},
                sort_keys=True, ensure_ascii=False,
            )
        )

        for problem in validate_record(record, types):
            codes[problem["code"]] += 1
            if problem["type"]:
                per_type[(problem["type"], problem["code"])] += 1
            if problem["code"] == UNKNOWN_TYPE:
                unknown[problem["type"]] += 1
            elif len(examples[problem["code"]]) < 8 and problem["span"]:
                examples[problem["code"]].append(
                    (problem["type"], problem["span"][:70])
                )

    duplicated = sum(1 for v in variants.values() if len(v) > 1)
    return {
        "records": total,
        "malformed": malformed,
        "spans": spans,
        "codes": codes,
        "per_type": per_type,
        "unknown": unknown,
        "examples": examples,
        "distinct_texts": len(variants),
        "texts_with_conflicting_labels": duplicated,
        "empty_records": empty,
    }


def _print_report(report: dict, types: List[str]) -> None:
    """Print a human-readable validation report."""
    print(f"records                  : {report['records']:,}")
    print(f"malformed JSON lines     : {report['malformed']:,}")
    print(f"labeled spans            : {report['spans']:,}")
    print(f"distinct documents       : {report['distinct_texts']:,}")
    print(
        f"docs w/ conflicting dupes: {report['texts_with_conflicting_labels']:,}"
    )
    print(f"allowed entity types     : {len(types)}")
    if report["empty_records"]:
        print(f"\n*** {report['empty_records']} RECORD(S) HAVE NO SPANS AT ALL ***")
        print("    A record with an empty output is legal JSON and produces no")
        print("    violation, so an unfinished annotation run looks identical to a")
        print("    clean one. Confirm these documents genuinely contain nothing")
        print("    taggable before accepting the file.")

    total = sum(report["codes"].values())
    print(f"\nviolations: {total:,}")
    for code, count in report["codes"].most_common():
        share = count / report["spans"] * 100 if report["spans"] else 0
        flag = "repairable" if code in REPAIRABLE else "needs review"
        print(f"  {code:22} {count:>7,}  ({share:5.2f}% of spans)  [{flag}]")
        for etype, span in report["examples"].get(code, [])[:3]:
            print(f"       e.g. [{etype}] {span!r}")

    if report["unknown"]:
        print("\nunknown entity types:")
        for etype, count in report["unknown"].most_common():
            print(f"  {etype:22} {count:>7,}")

    worst = [
        (t, c, n) for (t, c), n in report["per_type"].items()
        if c == NOT_A_SUBSTRING
    ]
    if worst:
        print("\nspans not found in source text, by type:")
        for etype, _, count in sorted(worst, key=lambda r: -r[2]):
            print(f"  {etype:22} {count:>7,}")


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code: 0 if clean, 1 if unrepairable violations remain.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL dataset to validate")
    parser.add_argument("--config", help="config.yaml to read entity_types from")
    parser.add_argument("--fix", metavar="OUT", help="write a repaired copy here")
    parser.add_argument(
        "--all-types", action="store_true",
        help="allow all 18 corpus types rather than the config's list",
    )
    args = parser.parse_args()

    types = ALL_TYPES if args.all_types else load_types(args.config)
    report = scan(args.path, types)
    _print_report(report, types)

    if args.fix:
        actions: collections.Counter = collections.Counter()
        kept = 0
        with open(args.fix, "w", encoding="utf-8") as out:
            for line in open(args.path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                repaired, acted = fix_record(record, types)
                actions.update(acted)
                out.write(json.dumps(repaired, ensure_ascii=False) + "\n")
                kept += 1
        print(f"\nwrote {kept:,} repaired records to {args.fix}")
        for action, count in actions.most_common():
            print(f"  {action:32} {count:>7,}")

    unrepairable = sum(
        count for code, count in report["codes"].items() if code not in REPAIRABLE
    )
    return 1 if unrepairable or report["empty_records"] else 0


if __name__ == "__main__":
    sys.exit(main())
