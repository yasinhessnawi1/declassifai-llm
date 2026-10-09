"""Check that a benchmark file and a training file share nothing a model could memorise.

`docs/PROJECT_SPEC_V2.md` Section 4 keeps the benchmark and the training set
apart so that a benchmark score measures generalisation. The generator enforces
that at the source -- `tools/gendoc_dataset.py` partitions the clause bank and
the name pools -- and this script is the independent check on what actually came
out, run over finished files rather than trusted from the sampler:

* **Clause text.** Every clause-bank and negative text that occurs in a document
  is found by search, and a text found in both files is a leak. A benchmark
  document that contains a *training-partition* text, or a training document that
  contains a *benchmark-partition* one, is reported too, since the generator
  should never have produced either.
* **Planted negatives.** Both sets plant near-miss sentences, each from its own
  partition, so a negative found in both is the one leak that teaches a detector
  exactly what the benchmark will ask. A negative's `{PRON}`/`{POSS}`/`{OBJ}` is
  filled per document ("han"/"hun"/"ho"), so it is searched for as a pattern, and with
  its first letter in either case: a negative that opens a sentence is capitalised by
  the model. Only negatives the sampler can plant are searched for.
  They are reported on their own (`shared_negative_texts`) as well as inside the
  clause-text checks, and, when the metadata files are given, the recorded
  `planted_negatives` of the two runs are compared too (`shared_planted_negatives`).
* **Full names.** A PERSON span equal in both files. Name components that cross
  the partition (a benchmark surname in a training document) are counted but are
  not failures: the model sometimes invents a name, and an invented "Hansen" is
  not the sampler leaking.
* **Skeleton hash.** Two documents whose skeletons (digits to `#`, capitalised
  tokens to `N`) are identical, one in each file, are the same template.
* **Streets.** Street names in address spans that belong to the other partition.

Exit status is 0 only when the hard checks (shared clause text, shared full name,
shared skeleton, shared planted negative) and the partition-crossing clause check are
all empty.

Usage:
    python3 tools/check_dataset_leakage.py --train train.jsonl [more.jsonl] \\
        --benchmark bench.jsonl [--train-meta train_meta.jsonl --benchmark-meta bench_meta.jsonl] \\
        [--json report.json]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from typing import Dict, Iterable, List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_data as data
import gendoc_dataset as dataset_mod
import gendoc_gates as gates

# A bare word such as "samboer" or "eieren" is a clause-bank negative but also
# ordinary Norwegian; matching it would report a leak in every document. The same
# holds for a template whose fixed words are that short: `gift med {PERSON_F}` is
# also what the sampler writes for a MARITAL_STATUS value in every document of both
# sets, so it is measured without its placeholders.
MIN_TEXT_CHARS = 12
_ANY_PLACEHOLDER = re.compile(r"\{[A-Z_]+\}")
_PLACEHOLDER = re.compile(r"\\\{(?:PERSON|PERSON_M|PERSON_F|SURNAME_FAM|SURNAME_ORG)\\\}")
_PRONOUN_PLACEHOLDER = re.compile(r"\\\{(PRON|POSS|OBJ)\\\}")
_NAME_TOKEN = r"[A-ZÆØÅ][\wæøå'\-]+(?: [A-ZÆØÅ][\wæøå'\-]+)*"


def load_documents(paths: Iterable[str]) -> List[dict]:
    """Read `{id, text_input, output}` records from one or more JSONL files."""
    docs = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            docs.extend(json.loads(line) for line in handle if line.strip())
    return docs


def _pattern(text: str) -> "re.Pattern":
    """Return the regex for a text with placeholders, its first letter in either case.

    A negative that opens a sentence is capitalised by the model, so "han ville ikke ..." is
    also found as "Han ville ikke ...".
    """
    escaped = _PLACEHOLDER.sub(lambda _m: _NAME_TOKEN, re.escape(text))
    escaped = _PRONOUN_PLACEHOLDER.sub(
        lambda m: "(?i:" + "|".join(dataset_mod.pronoun_alternatives(m.group(1))) + ")", escaped)
    if not escaped.startswith("(?i:") and escaped[:1].isalpha():
        escaped = "(?i:" + escaped[0] + ")" + escaped[1:]
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)")


def texts_in(docs: List[dict], texts: Iterable[str]) -> Dict[str, List[str]]:
    """Return `{text: [ids of the documents containing it]}` for the texts that occur."""
    found: Dict[str, List[str]] = collections.defaultdict(list)
    for text in texts:
        if len(_ANY_PLACEHOLDER.sub("", text).strip()) < MIN_TEXT_CHARS:
            continue
        plain = "{" not in text
        pattern = None if plain else _pattern(text)
        swapped = text[:1].swapcase() + text[1:] if text[:1].isalpha() else text
        for doc in docs:
            haystack = doc["text_input"]
            if (text in haystack or swapped in haystack) if plain else pattern.search(haystack):
                found[text].append(doc["id"])
    return dict(found)


def persons(docs: List[dict]) -> Dict[str, List[str]]:
    """Return `{PERSON span: [document ids]}`."""
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for doc in docs:
        for name in doc.get("output", {}).get("PERSON", []):
            out[name].append(doc["id"])
    return dict(out)


def _planted(meta: Iterable[dict]) -> Dict[str, List[str]]:
    """Return `{planted negative template: [document ids]}` from metadata records."""
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for record in meta:
        for neg in record.get("planted_negatives", []):
            out[neg.get("template") or neg["text"]].append(record["id"])
    return dict(out)


def check(train: List[dict], benchmark: List[dict], clause_bank: dict, partition: dict,
          train_meta: Optional[List[dict]] = None, benchmark_meta: Optional[List[dict]] = None) -> dict:
    """Compare a training and a benchmark document set and report every overlap.

    Args:
        train: Training documents.
        benchmark: Benchmark documents.
        clause_bank: The full flat clause bank.
        partition: The loaded benchmark partition.
        train_meta: The training run's `*_batch_meta.jsonl` records, whose
            `planted_negatives` are compared with the benchmark's; optional.
        benchmark_meta: Likewise for the benchmark run.

    Returns:
        The report dict; `ok` is True only when every hard check is empty.
    """
    bench_clause = {s for v in partition["clauses"].values() for s in v}
    bench_negative = {s for v in partition["negatives"].values() for s in v}
    sampled = {e["text"] for t, v in clause_bank.items() if t != "negatives" for e in v if e.get("genres")}
    # Only a negative the sampler can plant can reach a document. The others (a bare "Kirkeveien 22")
    # sit on a side of the partition by hash, and a document that happens to contain one in either case
    # of its first letter -- "Saksnummer 2019/LO-4521" is the capitalised form of the benchmark's planted
    # "saksnummer 2019/LO-4521" -- is not a leak from a side that never planted it.
    negatives = {e["text"] for v in clause_bank.get("negatives", {}).values() for e in v if e.get("plantable")}
    universe = sampled | negatives
    bench_texts = bench_clause | bench_negative
    train_texts = universe - bench_texts

    in_train = texts_in(train, universe)
    in_bench = texts_in(benchmark, universe)
    # A short text found in both files is often a fragment of two different longer
    # clauses ("over 1,5 millioner NOK"); the longer clause is what would be shared.
    inside_longer = lambda t: any(t in other for other in universe if other != t)  # noqa: E731
    shared_text = sorted(t for t in set(in_train) & set(in_bench) if not inside_longer(t))
    # A short benchmark text is a substring of a longer training clause now and
    # then ("mistet jobben" inside "har mistet jobben i fjor"); finding it in a
    # training document is the longer clause, not the benchmark text leaking.
    contained_in_train = lambda t: any(t in other for other in train_texts if other != t)  # noqa: E731
    contained_in_bench = lambda t: any(t in other for other in bench_texts if other != t)  # noqa: E731
    bench_text_in_train = sorted(t for t in in_train if t in bench_texts and not contained_in_train(t))
    train_text_in_bench = sorted(t for t in in_bench if t in train_texts and not contained_in_bench(t))

    p_train, p_bench = persons(train), persons(benchmark)
    shared_names = sorted(set(p_train) & set(p_bench))
    bench_pool = partition["names"]
    bench_components = {s for key, v in bench_pool.items() if not key.startswith(("street", "org"))
                        for s in v}
    train_components = ({n for n in data.FIRST_NAMES_MALE + data.FIRST_NAMES_FEMALE + data.SURNAMES}
                        | {n for m, f, s in data.FOREIGN_NAMES.values() for n in m + f + s}) - bench_components
    crossing_in_train = sorted({tok for name in p_train for tok in name.split()
                                if tok in bench_components})
    crossing_in_bench = sorted({tok for name in p_bench for tok in name.split()
                                if tok in train_components})

    street_bench = set(bench_pool.get("street_names", []))
    street_train = set(data.STREET_NAMES) - street_bench

    def streets(docs: List[dict], pool: Set[str]) -> List[str]:
        hit = set()
        for doc in docs:
            for address in doc.get("output", {}).get("ADDRESS", []):
                hit |= {s for s in pool if address.startswith(s)}
        return sorted(hit)

    skeletons: Dict[str, List[str]] = collections.defaultdict(list)
    for doc in train:
        skeletons[gates.skeleton_hash(doc["text_input"])].append(doc["id"])
    shared_skeletons = []
    for doc in benchmark:
        digest = gates.skeleton_hash(doc["text_input"])
        if digest in skeletons:
            shared_skeletons.append({"benchmark": doc["id"], "train": skeletons[digest]})

    neg_texts = set(negatives)
    shared_negatives = sorted(t for t in shared_text if t in neg_texts)
    planted_train, planted_bench = _planted(train_meta or []), _planted(benchmark_meta or [])
    shared_planted = sorted(set(planted_train) & set(planted_bench))
    bench_negative_in_train = [t for t in bench_text_in_train if t in neg_texts]
    train_negative_in_bench = [t for t in train_text_in_bench if t in neg_texts]

    ok = not (shared_text or bench_text_in_train or train_text_in_bench or shared_names
              or shared_skeletons or shared_planted)
    return {
        "ok": ok,
        "documents": {"train": len(train), "benchmark": len(benchmark)},
        "shared_negative_texts": {t: {"train": in_train[t], "benchmark": in_bench[t]}
                                  for t in shared_negatives},
        "benchmark_negatives_in_train_documents": bench_negative_in_train,
        "train_negatives_in_benchmark_documents": train_negative_in_bench,
        "shared_planted_negatives": {t: {"train": planted_train[t], "benchmark": planted_bench[t]}
                                     for t in shared_planted},
        "shared_clause_texts": {t: {"train": in_train[t], "benchmark": in_bench[t]} for t in shared_text},
        "benchmark_partition_texts_in_train_documents": bench_text_in_train,
        "train_partition_texts_in_benchmark_documents": train_text_in_bench,
        "shared_full_names": shared_names,
        "shared_skeleton_hashes": shared_skeletons,
        "informational": {
            "benchmark_name_components_in_train_persons": crossing_in_train,
            "train_name_components_in_benchmark_persons": crossing_in_bench,
            "benchmark_streets_in_train_addresses": streets(train, street_bench),
            "train_streets_in_benchmark_addresses": streets(benchmark, street_train),
            "clause_texts_distinct": {"train": len(in_train), "benchmark": len(in_bench)},
            "texts_skipped_as_too_short": sum(1 for t in universe if len(t) < MIN_TEXT_CHARS),
        },
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", nargs="+", required=True, help="training JSONL file(s)")
    parser.add_argument("--benchmark", nargs="+", required=True, help="benchmark JSONL file(s)")
    parser.add_argument("--clause-bank", default="data/synthetic/clause_bank.json")
    parser.add_argument("--partition", default=dataset_mod.PARTITION_PATH)
    parser.add_argument("--train-meta", nargs="*", default=[],
                        help="training *_batch_meta.jsonl file(s), to compare planted negatives")
    parser.add_argument("--benchmark-meta", nargs="*", default=[],
                        help="benchmark *_batch_meta.jsonl file(s), to compare planted negatives")
    parser.add_argument("--json", default=None, help="also write the report here")
    args = parser.parse_args()

    report = check(load_documents(args.train), load_documents(args.benchmark),
                   data.load_clause_bank(args.clause_bank), dataset_mod.load_partition(args.partition),
                   train_meta=load_documents(args.train_meta), benchmark_meta=load_documents(args.benchmark_meta))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    print(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print("LEAKAGE: none" if report["ok"] else "LEAKAGE: FOUND", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
