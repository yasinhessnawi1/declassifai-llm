"""Measure span-level agreement between two or more sets of NER annotations.

This is the instrument that tells us whether the annotation spec actually
works. The original corpus failed on reproducibility -- the same document
labeled twice got different answers 99.7% of the time -- so the test of the
spec is whether two annotators who follow it independently now converge.

Agreement is reported two ways:

* **strict**   -- a (type, span) pair must match exactly on both sides.
* **relaxed**  -- same type, and the spans overlap in the document (one
  contains the other). The gap between strict and relaxed is precisely the
  boundary disagreement, which was 21.2% of conflicts in the original corpus.

With exactly two inputs the score is symmetric, so F1 is a true
inter-annotator agreement figure rather than a precision/recall pair that
depends on which side you call the reference.

Usage:
    python tools/score_agreement.py a.jsonl b.jsonl
    python tools/score_agreement.py a.jsonl b.jsonl --names annotator1 annotator2
    python tools/score_agreement.py a.jsonl ref.jsonl --keys output gemini
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
from typing import Dict, List, Set, Tuple

Span = Tuple[str, str]  # (entity type, span text)

# Types cut from the taxonomy; excluded so a legacy file with 18 types can be
# compared fairly against a spec-conformant file with 16.
DROPPED = {"CONTEXT_SENSITIVE", "IDENTIFIABLE_IMAGE"}


def load(path: str, key: str) -> Dict[str, Set[Span]]:
    """Read an annotation file into {document id: set of (type, span)}.

    Args:
        path: JSONL file with `id` and an annotation dict per line.
        key: Field holding the annotation dict (e.g. "output" or "gemini").

    Returns:
        Mapping of document id to its set of typed spans.
    """
    docs: Dict[str, Set[Span]] = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        annotation = record.get(key) or {}
        docs[record["id"]] = {
            (etype, span)
            for etype, values in annotation.items()
            if etype not in DROPPED and isinstance(values, list)
            for span in values
            if isinstance(span, str)
        }
    return docs


def _relaxed_hits(left: Set[Span], right: Set[Span]) -> int:
    """Count same-type spans that overlap textually but may differ in extent.

    Each span on either side is consumed at most once, so the count is a
    matching rather than a cross product.

    Args:
        left: Typed spans from one annotator.
        right: Typed spans from the other.

    Returns:
        Number of matched pairs, including exact matches.
    """
    matched = len(left & right)
    spare_right = set(right - left)

    for etype, span in sorted(left - right):
        for other in sorted(spare_right):
            if other[0] == etype and (span in other[1] or other[1] in span):
                spare_right.discard(other)
                matched += 1
                break
    return matched


def compare(a: Dict[str, Set[Span]], b: Dict[str, Set[Span]]) -> dict:
    """Score one annotation set against another.

    Args:
        a: First annotator's spans by document id.
        b: Second annotator's spans by document id.

    Returns:
        Dict of totals, per-type counts and example disagreements.
    """
    shared = sorted(set(a) & set(b))
    totals: collections.Counter = collections.Counter()
    per_type: Dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    only_a: List[Tuple[str, Span]] = []
    only_b: List[Tuple[str, Span]] = []
    boundary: List[Tuple[str, str, str, str]] = []

    for doc in shared:
        left, right = a[doc], b[doc]
        totals["a"] += len(left)
        totals["b"] += len(right)
        totals["exact"] += len(left & right)
        totals["relaxed"] += _relaxed_hits(left, right)

        for etype, _ in left:
            per_type[etype]["a"] += 1
        for etype, _ in right:
            per_type[etype]["b"] += 1
        for etype, _ in left & right:
            per_type[etype]["exact"] += 1

        spare_right = set(right - left)
        for etype, span in sorted(left - right):
            partner = next(
                (
                    o for o in sorted(spare_right)
                    if o[0] == etype and (span in o[1] or o[1] in span)
                ),
                None,
            )
            if partner:
                spare_right.discard(partner)
                boundary.append((doc, etype, span, partner[1]))
            else:
                only_a.append((doc, (etype, span)))
        only_b.extend((doc, s) for s in sorted(spare_right))

    return {
        "docs": len(shared),
        "totals": totals,
        "per_type": per_type,
        "only_a": only_a,
        "only_b": only_b,
        "boundary": boundary,
    }


def _f1(hits: int, left: int, right: int) -> float:
    """Return the symmetric F1 for `hits` matches across two span sets."""
    return 2 * hits / (left + right) if left + right else 1.0


def _report(result: dict, name_a: str, name_b: str, examples: int) -> None:
    """Print a full comparison report."""
    totals = result["totals"]
    print(f"\n{'=' * 64}")
    print(f"{name_a}  vs  {name_b}")
    print("=" * 64)
    print(f"documents compared : {result['docs']}")
    print(f"spans: {name_a}={totals['a']:,}  {name_b}={totals['b']:,}")

    strict = _f1(totals["exact"], totals["a"], totals["b"])
    relaxed = _f1(totals["relaxed"], totals["a"], totals["b"])
    print(f"\n  strict  F1 (exact type+span) : {strict:.3f}   ({totals['exact']:,} matched)")
    print(f"  relaxed F1 (type + overlap)  : {relaxed:.3f}   ({totals['relaxed']:,} matched)")
    print(f"  boundary-only disagreements  : {len(result['boundary']):,}")
    print(f"  only in {name_a:<20} : {len(result['only_a']):,}")
    print(f"  only in {name_b:<20} : {len(result['only_b']):,}")

    print("\nper-type strict F1:")
    rows = [
        (etype, counts["a"], counts["b"],
         _f1(counts["exact"], counts["a"], counts["b"]))
        for etype, counts in result["per_type"].items()
    ]
    for etype, ca, cb, score in sorted(rows, key=lambda r: r[3]):
        print(f"  {etype:22} {ca:>5} / {cb:<5}  F1={score:.3f}")

    if result["boundary"]:
        print(f"\nboundary disagreements (first {examples}):")
        for doc, etype, sa, sb in result["boundary"][:examples]:
            print(f"  [{doc} {etype}]")
            print(f"      {sa!r}")
            print(f"   vs {sb!r}")

    for label, key in ((name_a, "only_a"), (name_b, "only_b")):
        if result[key]:
            print(f"\nfound only by {label} (first {examples}):")
            for doc, (etype, span) in result[key][:examples]:
                print(f"  [{doc} {etype}] {span[:70]!r}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="two or more annotation JSONL files")
    parser.add_argument("--names", nargs="+", help="display name per file")
    parser.add_argument("--keys", nargs="+", help="annotation field per file")
    parser.add_argument("--examples", type=int, default=12)
    args = parser.parse_args()

    names = args.names or [f.rsplit("/", 1)[-1] for f in args.files]
    keys = args.keys or ["output"] * len(args.files)
    if len(keys) == 1:
        keys = keys * len(args.files)

    loaded = [load(path, key) for path, key in zip(args.files, keys)]
    for name, docs in zip(names, loaded):
        print(f"{name:24} {len(docs):>4} docs, "
              f"{sum(len(v) for v in docs.values()):>5} spans")

    for i, j in itertools.combinations(range(len(loaded)), 2):
        _report(compare(loaded[i], loaded[j]), names[i], names[j], args.examples)


if __name__ == "__main__":
    main()
