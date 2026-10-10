"""Assemble train/val/test from three sources that must not be mixed carelessly.

The training data now comes from three places of very different quality:

* **The gold set** (400 documents) -- annotated to spec and adjudicated. This is the
  measuring stick. It goes to **test** and nowhere else.
* **The relabel slice** (1,000 documents) -- annotated to the same spec in a single
  pass. Full v2 supervision, and the only usable source for the types the corpus gets
  wrong or never had.
* **The cleaned corpus** (~29,800 documents) -- Gemini's labels, converted to v2 names.
  Scored against the gold set it reaches 0.966 relaxed F1 on seven legacy types and
  0.26-0.55 on five others, so by default only the v2 images of the seven reliable types
  are taken from it (`v2_schema.CORPUS_TRUSTED`).
* **Generated documents** (optional, `--synthetic`) -- from the synthetic generator,
  already in v2. Their annotation scope is taken from a record's own `types` field when
  it has one, otherwise all 57 types; confirm with the generator's owner that its labels
  are exhaustive before relying on the default.

All three annotated sources are in v2 type names (57 types, `data/synthetic/taxonomy.json`).

Two failure modes this script exists to prevent:

1. **Leaking the gold set into training.** `src/data_processor.py` splits by random
   shuffle. Pointed at a merged file it would put most of the gold documents in
   train, and the resulting test score would measure memorisation. Splits here are
   assigned by source and then asserted disjoint by text digest, because the corpus
   physically contains the gold and slice documents.

2. **Teaching absence that was never annotated.** A corpus example carries no
   HEALTH spans -- not because the document has none, but because Gemini missed
   two thirds of them -- and no LOCATION or ANIMAL_INFO at all, because the legacy
   schema never asked for them. Emitting it with `"HEALTH": []` trains the model to stay
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

from clean_corpus import RELIABLE_TYPES, clean
from v2_schema import CORPUS_ANNOTATED, v2_types

V2_TYPES = set(v2_types())



def digest(text: str) -> str:
    """Return the md5 digest of a document's text."""
    return hashlib.md5(text.encode()).hexdigest()


def load_annotated(patterns: List[str]) -> List[dict]:
    """Read v2 annotation files (gold, slice or generated).

    A type outside the v2 taxonomy is a hard error: it means a file was written
    against an old schema and would silently teach the wrong label set.

    Args:
        patterns: Glob patterns for JSONL files of `{id, text_input, output[, types]}`.

    Returns:
        Records carrying their annotation scope: the record's own `types` if present,
        else all 57 v2 types.
    """
    records = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                output = {k: v for k, v in (record.get("output") or {}).items() if v}
                unknown = set(output) - V2_TYPES
                if unknown:
                    raise SystemExit(f"FATAL: {path} {record.get('id')}: types not in the v2 "
                                     f"taxonomy: {sorted(unknown)}")
                scope = record.get("types") or sorted(V2_TYPES)
                records.append({
                    "text_input": record["text_input"],
                    "output": output,
                    "types": sorted(scope),
                    "source": record.get("id", "?"),
                })
    return records


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", nargs="*", default=["data/gold_v2/batch_*_gold.jsonl", "data/gold2_v2/batch_*_gold.jsonl"])
    parser.add_argument("--slice", nargs="*", default=["data/slice_v2/batch_*_annotator1.jsonl", "data/slice2_v2/batch_*_annotator1.jsonl"])
    parser.add_argument("--synthetic", nargs="*", default=[],
                        help="generated v2 documents for train (off by default)")
    parser.add_argument("--corpus", default="data/combined_data.jsonl")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument(
        "--corpus-types", choices=["reliable", "all", "none"], default="reliable",
        help="which of the corpus's types to trust (default: the v2 images of the 7 "
             "legacy types scoring >=0.91)",
    )
    parser.add_argument("--corpus-max", type=int, default=None,
                        help="cap the corpus documents taken (random, seeded), e.g. for a "
                             "first run that has to fit in a day of GPU time")
    parser.add_argument("--val-share", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    gold = load_annotated(args.gold)
    sliced = load_annotated(args.slice)
    synthetic = load_annotated(args.synthetic) if args.synthetic else []
    gold_digests = {digest(r["text_input"]) for r in gold}
    slice_digests = {digest(r["text_input"]) for r in sliced}

    print(f"gold  (-> test)         : {len(gold):,} documents")
    print(f"slice (-> train)        : {len(sliced):,} documents")
    if synthetic:
        print(f"synthetic (-> train)    : {len(synthetic):,} documents")
    if gold_digests & slice_digests:
        raise SystemExit(
            f"FATAL: {len(gold_digests & slice_digests)} documents appear in both the "
            "gold set and the slice. The slice must be drawn with --exclude."
        )

    corpus: List[dict] = []
    if args.corpus_types != "none":
        types = RELIABLE_TYPES if args.corpus_types == "reliable" else CORPUS_ANNOTATED
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
        if args.corpus_max is not None and len(corpus) > args.corpus_max:
            random.Random(args.seed).shuffle(corpus)
            corpus = corpus[: args.corpus_max]
        print(f"corpus (-> train)       : {len(corpus):,} documents "
              f"({len(types)} types, {dropped:,} held out as gold/slice)")

    rng = random.Random(args.seed)
    trainable = sliced + synthetic + corpus
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
            "corpus" if r["source"] == "corpus"
            else "synthetic" if str(r["source"]).startswith("SYN-") else "annotated"
            for r in split
        )
        print(f"{name:6} : {len(split):>7,} documents  {spans:>9,} spans  {dict(mix)} -> {path}")

    print("\nno test document appears in train or val (checked by text digest)")


if __name__ == "__main__":
    main()
