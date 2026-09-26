"""Assemble train/val/test from three sources that must not be mixed carelessly.

The training data now comes from three places of very different quality:

* **The gold set** (400 documents) -- annotated to spec and adjudicated. This is the
  measuring stick. It goes to **test** and nowhere else.
* **The relabel slice** (1,000 documents) -- annotated to the same spec in a single
  pass. Full 16-type supervision, and the only usable source for the five types the
  corpus gets wrong.
* **The cleaned corpus** (~29,000 documents) -- Gemini's labels. Scored against the
  gold set it reaches 0.966 relaxed F1 on seven types and 0.26-0.55 on five others,
  so by default only the seven reliable types are taken from it.

Two failure modes this script exists to prevent:

1. **Leaking the gold set into training.** `src/data_processor.py` splits by random
   shuffle. Pointed at a merged file it would put most of the gold documents in
   train, and the resulting test score would measure memorisation. Splits here are
   assigned by source and then asserted disjoint by text digest, because the corpus
   physically contains the gold and slice documents.

2. **Teaching absence that was never annotated.** A corpus example carries no
   HEALTH_INFO spans -- not because the document has none, but because Gemini missed
   two thirds of them. Emitting it with `"HEALTH_INFO": []` trains the model to stay
   silent. Instead each example declares the type list it was annotated against, and
   the prompt names only those types. The model learns to extract what it was asked
   for, which is also what it must do at inference.

Usage:
    python tools/build_training_set.py --out-dir data/processed
    python tools/build_training_set.py --out-dir data/processed --corpus-types none
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import random
from typing import Dict, List, Set

from clean_corpus import RELIABLE_TYPES, SCHEMA_TYPES, clean


def digest(text: str) -> str:
    """Return the md5 digest of a document's text."""
    return hashlib.md5(text.encode()).hexdigest()


def load_annotated(patterns: List[str]) -> List[dict]:
    """Read annotation files produced by the gold or slice pipeline.

    Args:
        patterns: Glob patterns for JSONL files of `{id, text_input, output}`.

    Returns:
        Records carrying the full 16-type scope.
    """
    records = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                output = {
                    k: v for k, v in (record.get("output") or {}).items()
                    if k in SCHEMA_TYPES and v
                }
                records.append({
                    "text_input": record["text_input"],
                    "output": output,
                    "types": sorted(SCHEMA_TYPES),
                    "source": record.get("id", "?"),
                })
    return records


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", nargs="*", default=["data/gold/batch_*_gold.jsonl"])
    parser.add_argument("--slice", nargs="*", default=["data/slice/batch_*_annotator1.jsonl"])
    parser.add_argument("--corpus", default="data/combined_data.jsonl")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument(
        "--corpus-types", choices=["reliable", "all", "none"], default="reliable",
        help="which of the corpus's types to trust (default: the 7 scoring >=0.91)",
    )
    parser.add_argument("--val-share", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    gold = load_annotated(args.gold)
    sliced = load_annotated(args.slice)
    gold_digests = {digest(r["text_input"]) for r in gold}
    slice_digests = {digest(r["text_input"]) for r in sliced}

    print(f"gold  (-> test)         : {len(gold):,} documents")
    print(f"slice (-> train)        : {len(sliced):,} documents")
    if gold_digests & slice_digests:
        raise SystemExit(
            f"FATAL: {len(gold_digests & slice_digests)} documents appear in both the "
            "gold set and the slice. The slice must be drawn with --exclude."
        )

    corpus: List[dict] = []
    if args.corpus_types != "none":
        types = RELIABLE_TYPES if args.corpus_types == "reliable" else SCHEMA_TYPES
        cleaned, stats = clean(args.corpus, types)
        held = gold_digests | slice_digests
        dropped = 0
        for record in cleaned:
            if digest(record["text_input"]) in held:
                dropped += 1
                continue
            corpus.append({
                "text_input": record["text_input"],
                "output": record["output"],
                "types": sorted(types),
                "source": "corpus",
            })
        print(f"corpus (-> train)       : {len(corpus):,} documents "
              f"({len(types)} types, {dropped:,} held out as gold/slice)")

    rng = random.Random(args.seed)
    trainable = sliced + corpus
    rng.shuffle(trainable)
    n_val = int(len(trainable) * args.val_share)
    val, train = trainable[:n_val], trainable[n_val:]
    test = gold

    # The corpus physically contains the gold and slice documents, so overlap here
    # is a live risk rather than a theoretical one. Fail loudly instead of quietly
    # producing a test score that measures memorisation.
    test_digests = {digest(r["text_input"]) for r in test}
    for name, split in (("train", train), ("val", val)):
        overlap = test_digests & {digest(r["text_input"]) for r in split}
        if overlap:
            raise SystemExit(f"FATAL: {len(overlap)} test documents leaked into {name}")

    for name, split in (("train", train), ("val", val), ("test", test)):
        path = f"{args.out_dir}/{name}.jsonl"
        with open(path, "w", encoding="utf-8") as out:
            for record in split:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        spans = sum(len(v) for r in split for v in r["output"].values())
        mix = collections.Counter(
            "corpus" if r["source"] == "corpus" else "annotated" for r in split
        )
        print(f"{name:6} : {len(split):>7,} documents  {spans:>9,} spans  {dict(mix)} -> {path}")

    print("\nno test document appears in train or val (checked by text digest)")


if __name__ == "__main__":
    main()
