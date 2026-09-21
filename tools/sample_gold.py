"""Select a stratified gold-set sample for manual adjudication.

The gold set is the measuring stick for every later claim about label quality:
without it there is no way to show that re-annotation improved anything, and
"100% correct" is unverifiable.

Sampling has to satisfy three competing goals:

1. Every entity type must appear often enough to estimate its F1, including the
   rare ones -- a uniform random sample under-represents SEXUAL_ORIENTATION and
   over-represents PERSON.
2. Both document templates must be present. The corpus is ~half animal-welfare
   interview reports and ~half dossiers about a named human, and they have very
   different entity profiles.
3. Some genuinely hard cases must be included, otherwise the gold set measures
   only the easy majority. Documents whose duplicate copies were labeled
   inconsistently are known-hard by construction.

Usage:
    python tools/sample_gold.py data/combined_data.jsonl -n 400 -o data/gold_candidates.jsonl
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
from typing import Dict, List, Tuple

# The 16 types that survive the taxonomy decisions in docs/DATA_QUALITY.md.
GOLD_TYPES = [
    "PERSON", "DATE_TIME", "HEALTH_INFO", "GOV_ID", "NO_ADDRESS",
    "CRIMINAL_RECORD", "POSTAL_CODE", "NO_PHONE_NUMBER", "EMAIL_ADDRESS",
    "FAMILY_RELATION", "FINANCIAL_INFO", "EMPLOYMENT_INFO", "POLITICAL_CASE",
    "BEHAVIORAL_PATTERN", "ECONOMIC_STATUS", "SEXUAL_ORIENTATION",
]

INTERVIEW = re.compile(r"Hvilket dyr er du bekymret for|-- Hvordan ser dyrene ut")


def load(path: str) -> Tuple[List[dict], Dict[str, bool]]:
    """Read the corpus, keeping one copy of each distinct document.

    Args:
        path: Path to the JSONL corpus.

    Returns:
        Tuple of (deduplicated records, map of text digest -> had conflicting
        duplicate labels).
    """
    seen: Dict[str, dict] = {}
    variants: Dict[str, set] = collections.defaultdict(set)

    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        text = record.get("text_input", "")
        output = record.get("output") or {}
        digest = hashlib.md5(text.encode()).hexdigest()

        variants[digest].add(
            json.dumps(
                {k: sorted(set(v)) for k, v in output.items() if v},
                sort_keys=True, ensure_ascii=False,
            )
        )
        seen.setdefault(digest, record)

    conflicted = {d: len(v) > 1 for d, v in variants.items()}
    return list(seen.values()), conflicted


def _digest(record: dict) -> str:
    """Return the md5 digest of a record's document text."""
    return hashlib.md5(record.get("text_input", "").encode()).hexdigest()


def select(
    records: List[dict],
    conflicted: Dict[str, bool],
    size: int,
    min_per_type: int,
    conflict_share: float,
    seed: int,
) -> List[dict]:
    """Pick a stratified sample covering every type and both templates.

    Args:
        records: Deduplicated corpus records.
        conflicted: Map of text digest -> had contradictory duplicate labels.
        size: Total documents to select.
        min_per_type: Minimum documents containing each entity type.
        conflict_share: Fraction of the sample drawn from known-hard documents.
        seed: RNG seed, so the gold set is reproducible.

    Returns:
        Selected records, each annotated with a _gold metadata block.
    """
    rng = random.Random(seed)
    pool = list(records)
    rng.shuffle(pool)

    chosen: Dict[str, dict] = {}
    per_type: collections.Counter = collections.Counter()

    def take(record: dict, reason: str) -> None:
        key = _digest(record)
        if key in chosen:
            return
        record = dict(record)
        record["_gold"] = {
            "reason": reason,
            "template": "interview" if INTERVIEW.search(record["text_input"]) else "dossier",
            "hard": bool(conflicted.get(key)),
        }
        chosen[key] = record
        for etype, spans in (record.get("output") or {}).items():
            if spans and etype in GOLD_TYPES:
                per_type[etype] += 1

    # Pass 1: guarantee coverage of the rare types first, since common types
    # will be picked up incidentally by everything that follows.
    for etype in sorted(GOLD_TYPES, key=lambda t: sum(
        1 for r in pool if (r.get("output") or {}).get(t)
    )):
        for record in pool:
            if per_type[etype] >= min_per_type or len(chosen) >= size:
                break
            if (record.get("output") or {}).get(etype):
                take(record, f"coverage:{etype}")

    # Pass 2: known-hard documents -- those whose duplicates disagreed.
    hard_target = int(size * conflict_share)
    hard = [r for r in pool if conflicted.get(_digest(r))]
    for record in hard:
        if sum(1 for r in chosen.values() if r["_gold"]["hard"]) >= hard_target:
            break
        if len(chosen) >= size:
            break
        take(record, "hard:conflicting_duplicate")

    # Pass 3: fill the rest at random, balancing the two templates.
    by_template = {"interview": [], "dossier": []}
    for record in pool:
        bucket = "interview" if INTERVIEW.search(record["text_input"]) else "dossier"
        by_template[bucket].append(record)

    while len(chosen) < size:
        progressed = False
        for bucket in ("interview", "dossier"):
            if len(chosen) >= size:
                break
            while by_template[bucket]:
                record = by_template[bucket].pop()
                if _digest(record) not in chosen:
                    take(record, f"random:{bucket}")
                    progressed = True
                    break
        if not progressed:
            break

    return list(chosen.values())


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="JSONL corpus to sample from")
    parser.add_argument("-o", "--out", required=True, help="output JSONL")
    parser.add_argument("-n", "--size", type=int, default=400)
    parser.add_argument("--min-per-type", type=int, default=30)
    parser.add_argument("--conflict-share", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    records, conflicted = load(args.path)
    print(f"distinct documents      : {len(records):,}")
    print(f"with conflicting dupes  : {sum(conflicted.values()):,}")

    sample = select(
        records, conflicted, args.size,
        args.min_per_type, args.conflict_share, args.seed,
    )

    with open(args.out, "w", encoding="utf-8") as out:
        for record in sample:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    templates = collections.Counter(r["_gold"]["template"] for r in sample)
    reasons = collections.Counter(r["_gold"]["reason"].split(":")[0] for r in sample)
    coverage: collections.Counter = collections.Counter()
    for record in sample:
        for etype, spans in (record.get("output") or {}).items():
            if spans and etype in GOLD_TYPES:
                coverage[etype] += 1

    print(f"\nselected                : {len(sample):,} documents -> {args.out}")
    print(f"  hard (conflicting)    : {sum(1 for r in sample if r['_gold']['hard']):,}")
    print(f"  by template           : {dict(templates)}")
    print(f"  by selection reason   : {dict(reasons)}")
    print("\ntype coverage (documents containing the type):")
    missing = []
    for etype in GOLD_TYPES:
        count = coverage[etype]
        flag = "" if count >= args.min_per_type else "  << UNDER TARGET"
        if count < args.min_per_type:
            missing.append(etype)
        print(f"  {etype:22} {count:>5}{flag}")
    if missing:
        print(f"\nunder target: {', '.join(missing)} -- raise -n or lower --min-per-type")


if __name__ == "__main__":
    main()
