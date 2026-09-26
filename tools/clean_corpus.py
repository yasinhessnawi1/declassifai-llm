"""Apply the deterministic repairs the raw corpus needs before anything trains on it.

`data/combined_data.jsonl` is 32,439 Gemini-labeled documents with four mechanical
defects, all fixable without judgement:

1. **Out-of-schema types.** 21 distinct keys appear where the spec defines 16.
   `CONTEXT_SENSITIVE` and `IDENTIFIABLE_IMAGE` were cut from the taxonomy -- neither
   identifies a natural person under GDPR Art. 4(1) -- and `ANIMAL_INFO`, `AGE` and
   `AGE_INFO` are stray keys the labeler invented, 11 spans between them.
2. **Non-verbatim spans.** 0.57% of spans are not substrings of their document. An
   extractive model cannot learn a target it cannot point at.
3. **Contradictory duplicates.** 2,548 texts appear more than once and 2,531 of those
   carry different labels on each copy. Training on all copies shows the model the same
   input with conflicting targets.
4. **Empty records**, which teach the model that "no entities" is a valid answer for a
   document full of them.

Deduplication takes the **union** of every copy's spans, then collapses any span wholly
contained in a longer span of the same type. Measured on the 400-document gold set, that
beats keeping the first copy on both metrics (relaxed F1 0.9663 vs 0.9652, recall 0.9829
vs 0.9791) because 65% of duplicate disagreements are one copy simply missing spans the
other found.

What this script does **not** do is fix the labels. Against the gold set the corpus scores
0.966 relaxed F1 on seven types and 0.26-0.55 on five others, and no deterministic pass
can close that gap -- see `docs/DATA_QUALITY.md`. `--reliable-only` emits just the seven
types worth keeping, for a training set whose remaining types come from re-annotation.

Usage:
    python tools/clean_corpus.py data/combined_data.jsonl -o data/processed/corpus_clean.jsonl
    python tools/clean_corpus.py data/combined_data.jsonl -o out.jsonl --reliable-only
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from typing import Dict, List, Optional, Set

# The taxonomy in docs/ANNOTATION_SPEC.md.
SCHEMA_TYPES = {
    "PERSON", "NO_ADDRESS", "POSTAL_CODE", "NO_PHONE_NUMBER", "EMAIL_ADDRESS",
    "DATE_TIME", "HEALTH_INFO", "EMPLOYMENT_INFO", "CRIMINAL_RECORD",
    "FINANCIAL_INFO", "ECONOMIC_STATUS", "GOV_ID", "FAMILY_RELATION",
    "POLITICAL_CASE", "SEXUAL_ORIENTATION", "BEHAVIORAL_PATTERN",
}

# Types where the corpus scores >=0.91 relaxed F1 against the gold set. The other
# nine are kept by default but should be treated as suspect; the five below 0.60
# (BEHAVIORAL_PATTERN, ECONOMIC_STATUS, HEALTH_INFO, CRIMINAL_RECORD,
# EMPLOYMENT_INFO) are not usable as training targets.
RELIABLE_TYPES = {
    "EMAIL_ADDRESS", "NO_PHONE_NUMBER", "PERSON", "POSTAL_CODE",
    "DATE_TIME", "SEXUAL_ORIENTATION", "NO_ADDRESS",
}


def repair(span: str, text: str) -> Optional[str]:
    """Return the document's own wording for a span that differs only cosmetically.

    Roughly 800 corpus spans fail the verbatim test for reasons that carry no
    meaning -- the labeler lowercased a sentence-initial word, or collapsed a
    double space. Dropping them loses real annotations, so recover the document's
    actual substring instead. Anything that still does not match, such as a
    paraphrase or a typo (`tynnee` for `tynne`), is a genuine defect and is left
    for the caller to drop.

    Args:
        span: The labeled span, possibly mis-cased or mis-spaced.
        text: The document it should have come from.

    Returns:
        The matching substring of `text`, or None if there is no cosmetic match.
    """
    if span in text:
        return span
    pattern = r"\s+".join(re.escape(part) for part in span.split())
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None


def collapse(spans: Set[str]) -> List[str]:
    """Drop spans wholly contained in a longer span of the same type.

    Unioning duplicate copies can produce both `26. oktober 2023` and `oktober 2023`
    for one date. Keeping both would train the model to emit overlapping answers.

    Args:
        spans: Span strings for a single entity type.

    Returns:
        The surviving spans, longest first.
    """
    kept: List[str] = []
    for span in sorted(spans, key=len, reverse=True):
        if not any(span in other and span != other for other in kept):
            kept.append(span)
    return kept


def clean(path: str, types: Set[str]) -> tuple:
    """Merge duplicate copies of each document and drop unusable spans.

    Args:
        path: Path to the raw JSONL corpus.
        types: Entity types to keep; everything else is dropped.

    Returns:
        Tuple of (cleaned records, statistics counter).
    """
    texts: Dict[str, str] = {}
    merged: Dict[str, Dict[str, Set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    order: List[str] = []
    stats: collections.Counter = collections.Counter()

    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        text = record.get("text_input", "")
        digest = hashlib.md5(text.encode()).hexdigest()
        if digest not in texts:
            texts[digest] = text
            order.append(digest)
        else:
            stats["duplicate_copies_merged"] += 1

        for etype, spans in (record.get("output") or {}).items():
            if not isinstance(spans, list):
                continue
            if etype not in SCHEMA_TYPES:
                stats["spans_dropped_out_of_schema"] += len(spans)
                continue
            if etype not in types:
                stats["spans_dropped_unreliable_type"] += len(spans)
                continue
            for span in spans:
                if not isinstance(span, str) or not span.strip():
                    stats["spans_dropped_empty"] += 1
                    continue
                fixed = repair(span, text)
                if fixed is None:
                    stats["spans_dropped_non_verbatim"] += 1
                else:
                    if fixed != span:
                        stats["spans_repaired_case_or_space"] += 1
                    merged[digest][etype].add(fixed)

    records = []
    for digest in order:
        output = {t: collapse(s) for t, s in merged[digest].items() if s}
        before = sum(len(s) for s in merged[digest].values())
        stats["spans_dropped_nested_duplicate"] += before - sum(
            len(v) for v in output.values()
        )
        if not output:
            stats["records_dropped_empty"] += 1
            continue
        records.append({"text_input": texts[digest], "output": output})
        stats["spans_kept"] += sum(len(v) for v in output.values())

    stats["records_in"] = stats["duplicate_copies_merged"] + len(order)
    stats["records_out"] = len(records)
    return records, stats


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="raw JSONL corpus")
    parser.add_argument("-o", "--out", required=True, help="output JSONL")
    parser.add_argument(
        "--reliable-only", action="store_true",
        help="keep only the 7 types scoring >=0.91 against the gold set",
    )
    args = parser.parse_args()

    types = RELIABLE_TYPES if args.reliable_only else SCHEMA_TYPES
    records, stats = clean(args.path, types)

    with open(args.out, "w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"types kept              : {len(types)}")
    print(f"records in              : {stats['records_in']:,}")
    print(f"  duplicate copies merged : {stats['duplicate_copies_merged']:,}")
    print(f"  dropped, no spans left  : {stats['records_dropped_empty']:,}")
    print(f"records out             : {stats['records_out']:,} -> {args.out}")
    print(f"spans kept              : {stats['spans_kept']:,}")
    for reason in (
        "spans_dropped_out_of_schema", "spans_dropped_unreliable_type",
        "spans_dropped_non_verbatim", "spans_dropped_empty",
        "spans_dropped_nested_duplicate", "spans_repaired_case_or_space",
    ):
        if stats[reason]:
            print(f"  {reason[14:]:24}: {stats[reason]:,}")


if __name__ == "__main__":
    main()
