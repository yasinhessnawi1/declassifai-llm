"""Two datasets that never mix: the held-out benchmark and the training set.

`docs/PROJECT_SPEC_V2.md` Section 4 asks for a benchmark that is held out,
published and hard, and a training set that is large and allowed to be easier.
Those are only two different things if no string a model is scored on was ever
generated into its training data. A shared clause text is the obvious leak: the
benchmark's "lider av type 2 diabetes" would be a sentence the detector has
memorised. A shared full name or street is the quiet one: a detector that learned
"Kari Halvorsen" as a PERSON scores well on a benchmark containing her, and the
number says nothing about names it has not seen.

So the partition is fixed in a file, `data/synthetic/benchmark_partition.json`,
and every run reads it. The file lists the *benchmark* share of each clause-bank
type, of the negatives, and of every name, street and employer-prefix pool;
everything not listed belongs to training, which means an entry added to the bank
later can only ever land in training and cannot leak into a benchmark that was
already published. The partition is by text, not by (type, form) entry, because
the bank repeats a Nynorsk clause that is character-identical to its Bokmål one,
and a string is either in one set or the other. Names are partitioned in one
namespace for the same reason: "Hussein" is a surname in one nationality's pool
and a given name in another's.

`DatasetMode` carries the other differences. A benchmark weights clause sampling
toward `difficulty: hard`, draws more dense and case-file documents, and plants
one to three hard negatives per document: near-miss sentences from the bank's
`negatives` that read like a sensitive disclosure and are not one ("nektet å
oppgi om han er fagorganisert"), recorded in the metadata so a detector that
flags one can be scored as a false positive. A training set keeps the
distribution the generator had before datasets existed, plus zero or one planted
negative per document from its own partition of the negatives, so the training
set also teaches "do not label this" without the benchmark's texts ever appearing
in it.

The negatives were first partitioned together with the clauses (`build`). A later
batch of near-misses (`origin: nearmiss_v5`) is partitioned by `extend-negatives`,
which leaves every earlier assignment untouched: it adds the batch's benchmark
share to `negatives`, lists its training share in `negatives_train` so the split is
explicit and checkable, and records the batch in `negative_batches`. Running it
twice for one batch is refused.

Usage:
    python3 tools/gendoc_dataset.py build                         # write the partition file once
    python3 tools/gendoc_dataset.py extend-negatives nearmiss_v5  # partition a later batch of negatives
    python3 tools/gendoc_dataset.py summary                       # print its sizes
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gendoc_data as data

PARTITION_PATH = "data/synthetic/benchmark_partition.json"
PARTITION_VERSION = 2
HOLDOUT_RATIO = 0.25
SALT = "gendoc-benchmark-partition-v1"

# Share of a later negatives batch that goes to the benchmark; the rest is the
# training set's own partition. The benchmark plants one to three negatives per
# document and the training set at most one, so it needs the larger pool.
NEGATIVE_BATCH_BENCHMARK_RATIO = 0.70
NEGATIVE_BATCH_SALT = "gendoc-negatives-batch-v1"

# The two near-misses `PROJECT_SPEC_V2.md` found in the gold set (every apparent
# trade-union hit was a case number containing "LO") and `ANNOTATION_SPEC.md` B7
# (a refusal to disclose). They are the benchmark's canonical hard negatives, so
# they are pinned to it rather than left to the hash.
PINNED_BENCHMARK_NEGATIVES = (
    "nektet å oppgi om han er fagorganisert",
    "saksnummer 2019/LO-4521",
)


# A negative's text may carry `{PRON}`, `{POSS}` and `{OBJ}` so it can hold its own
# subject ("og {PRON} svarte at ..."): a bare predicate spliced into a sentence the
# model had already given a different shape produced "Under ei samtale med
# saksbehandlarane ville ikkje oppgi inntekta si". The sampler fills them from the
# document subject's gender and the document's form, and the filled string is what
# is planted and what G2 searches for. Bokmål `ham` is Nynorsk `han`.
PRONOUN_FORMS: Dict[Tuple[str, str], Dict[str, str]] = {
    ("nb", "M"): {"PRON": "han", "POSS": "hans", "OBJ": "ham"},
    ("nb", "F"): {"PRON": "hun", "POSS": "hennes", "OBJ": "henne"},
    ("nn", "M"): {"PRON": "han", "POSS": "hans", "OBJ": "han"},
    ("nn", "F"): {"PRON": "ho", "POSS": "hennar", "OBJ": "henne"},
}

# No negative text may be planted more than this many times in one run: a model
# trained on a sentence it sees every tenth document learns the sentence, and the
# trap becomes a pattern. Pilot v4 planted one text seven times.
NEGATIVE_CAP_PER_RUN = 2


def fill_pronouns(text: str, gender: str, form: str) -> str:
    """Fill a negative's pronoun placeholders for one subject.

    Args:
        text: Negative text, possibly holding `{PRON}`, `{POSS}` or `{OBJ}`.
        gender: "M" or "F".
        form: "nb" or "nn".

    Returns:
        The text with every placeholder replaced; unchanged when it has none.

    Raises:
        KeyError: `gender`/`form` is not a known pair.
    """
    if "{" not in text:
        return text
    for slot, word in PRONOUN_FORMS[(form, gender)].items():
        text = text.replace("{" + slot + "}", word)
    return text


def pronoun_alternatives(slot: str) -> List[str]:
    """Return every surface form of one placeholder across genders and forms."""
    return sorted({forms[slot] for forms in PRONOUN_FORMS.values()})


@dataclass(frozen=True)
class DatasetMode:
    """What differs between generating the benchmark and generating training data.

    Attributes:
        name: "train" or "benchmark".
        id_prefix: Document id prefix, so the two sets cannot be confused in a
            merged listing.
        file_stem: Output file stem (`synthetic_batch.jsonl` vs
            `benchmark_batch.jsonl`).
        difficulty_weights: Relative weight of a clause-bank entry by its
            `difficulty`; None means a uniform draw, the behaviour before
            datasets existed.
        profile_shares: Density-profile shares overriding
            `gendoc_genres.PROFILES`; None keeps the profile defaults.
        negatives_by_profile: (min, max) hard negatives planted per document of
            each profile, drawn from this dataset's own partition of the
            negatives; empty means none are planted.
        seed_offset: Added to the run seed, so the same `--seed` for both sets
            does not hand them the same plans and the same PII-free documents.
    """

    name: str
    id_prefix: str
    file_stem: str
    difficulty_weights: Optional[Dict[str, float]] = None
    profile_shares: Optional[Dict[str, float]] = None
    negatives_by_profile: Dict[str, Tuple[int, int]] = dataclasses.field(default_factory=dict)
    seed_offset: int = 0


MODES: Dict[str, DatasetMode] = {
    # The training set plants at most one near-miss per document, from its own
    # share of the negatives (never a benchmark text), so it also teaches "do not
    # label this". Profiles with room for a planted sentence draw 0-1; a
    # PII-free document draws none.
    "train": DatasetMode(
        "train", "SYN", "synthetic",
        negatives_by_profile={"minimal": (0, 1), "light": (0, 1), "typical": (0, 1),
                              "dense": (0, 1), "case_file": (0, 1)}),
    "benchmark": DatasetMode(
        "benchmark", "SYB", "benchmark",
        difficulty_weights={"easy": 1.0, "medium": 2.0, "hard": 5.0},
        # Dense and case-file documents carry the most spans, the most parties
        # and the most room for a judgement clause to hide in running prose, so
        # the benchmark leans on them; PII-free documents stay at five percent
        # because a benchmark that never shows a clean document cannot measure
        # false positives either.
        profile_shares={"pii_free": 0.05, "minimal": 0.04, "light": 0.14,
                        "typical": 0.24, "dense": 0.27, "case_file": 0.26},
        negatives_by_profile={"minimal": (1, 1), "light": (1, 1), "typical": (1, 2),
                              "dense": (2, 3), "case_file": (2, 3)},
        seed_offset=7_000_001,
    ),
}


def _rank(*parts: str, salt: str = SALT) -> str:
    return hashlib.sha256("|".join((salt,) + parts).encode("utf-8")).hexdigest()


def _assign(strata: Dict[str, List[str]], assigned: Dict[str, bool], ratio: float,
            singleton_to_benchmark: bool, salt: str = SALT) -> None:
    """Assign every string of every stratum to the benchmark or training, in place.

    Each stratum holds out about `ratio` of its strings, ranked by hash so the
    choice is deterministic and unrelated to the order of the file. At least one
    string is held out of any stratum of two or more, and at least one stays in
    training. Strings already assigned by an earlier stratum keep their side and
    count toward the target, which is how one text shared by two strata stays on
    one side.

    Args:
        strata: Stratum name -> its strings.
        assigned: String -> True for benchmark; extended in place.
        ratio: Share to hold out.
        singleton_to_benchmark: Where a stratum of one string goes. Training
            clauses need their only entry; the negatives were first planted in the
            benchmark alone, so there a lone entry is better used there.
        salt: Hash salt, so a later batch is ranked independently of the first.
    """
    for key in sorted(strata):
        strings = sorted(set(strata[key]), key=lambda s: _rank(key, s, salt=salt))
        n = len(strings)
        if n == 1:
            assigned.setdefault(strings[0], singleton_to_benchmark)
            continue
        target = min(n - 1, max(1, round(ratio * n)))
        held = sum(1 for s in strings if assigned.get(s))
        for s in strings:
            if s in assigned:
                continue
            if held < target:
                assigned[s] = True
                held += 1
            else:
                assigned[s] = False


def _pool_strata(pools: data.NamePools) -> Dict[str, List[str]]:
    strata = {
        "first_male": list(pools.first_male), "first_female": list(pools.first_female),
        "surnames": list(pools.surnames), "street_names": list(pools.street_names),
        "org_prefixes": list(pools.org_prefixes),
    }
    for nat, (males, females, surnames) in pools.foreign_names.items():
        strata[f"foreign:{nat}:first_male"] = list(males)
        strata[f"foreign:{nat}:first_female"] = list(females)
        strata[f"foreign:{nat}:surnames"] = list(surnames)
    return strata


def build_partition(clause_bank: dict, ratio: float = HOLDOUT_RATIO) -> dict:
    """Compute the benchmark share of the clause bank, the negatives and the name pools.

    Args:
        clause_bank: The flat bank from `gendoc_data.load_clause_bank`
            (`{TYPE: [entries], "negatives": {TYPE: [entries]}}`).
        ratio: Share held out for the benchmark.

    Returns:
        The partition dict written to `PARTITION_PATH`: explicit benchmark lists
        per clause type, per negative type and per name pool, plus a `counts`
        summary.
    """
    negatives = clause_bank.get("negatives", {})
    clause_types = sorted(t for t in clause_bank if t != "negatives")

    # One namespace for clauses and negatives: the bank repeats a text across the
    # two (`medlem av Den Evangelisk Lutherske Frikirke` is a RELIGIOUS_BELIEF
    # clause and a POLITICAL negative), and a text is on one side only. Clauses
    # are assigned first, so a negative that is also a training clause is not
    # available to the benchmark. Entries with no `genres` are never sampled and
    # are left out of the clause strata.
    assigned: Dict[str, bool] = {}
    strata = {f"{t}:{form}": [e["text"] for e in clause_bank[t] if e["form"] == form and e.get("genres")]
              for t in clause_types for form in ("nb", "nn", "en")}
    _assign({k: v for k, v in strata.items() if v}, assigned, ratio, False)
    for pinned in PINNED_BENCHMARK_NEGATIVES:
        assert assigned.get(pinned) is not True, pinned
        assigned[pinned] = True
    neg_strata = {f"{t}:{form}": [e["text"] for e in negatives[t] if e["form"] == form]
                  for t in sorted(negatives) for form in ("nb", "nn", "en")}
    _assign({k: v for k, v in neg_strata.items() if v}, assigned, ratio, True)

    name_assigned: Dict[str, bool] = {}
    pool_strata = _pool_strata(data.full_pools())
    _assign(pool_strata, name_assigned, ratio, False)

    benchmark_clauses = {
        t: sorted({e["text"] for e in clause_bank[t] if e.get("genres") and assigned.get(e["text"])})
        for t in clause_types}
    benchmark_negatives = {
        t: sorted({e["text"] for e in negatives[t] if assigned.get(e["text"])})
        for t in sorted(negatives)}
    benchmark_names = {key: sorted(s for s in set(strings) if name_assigned.get(s))
                       for key, strings in pool_strata.items()}
    return {
        "version": PARTITION_VERSION, "salt": SALT, "holdout_ratio": ratio,
        "note": "Benchmark share only. Anything not listed here is training, so an entry "
                "added to the bank later can never appear in a benchmark already published.",
        "clauses": {t: v for t, v in benchmark_clauses.items() if v},
        "negatives": {t: v for t, v in benchmark_negatives.items() if v},
        "names": benchmark_names,
        "counts": _counts(clause_bank, benchmark_clauses, benchmark_negatives, pool_strata,
                          benchmark_names),
    }


def _counts(bank: dict, bench_clauses: dict, bench_negatives: dict, pool_strata: dict,
            bench_names: dict) -> dict:
    negatives = bank.get("negatives", {})
    types = sorted(t for t in bank if t != "negatives")
    n_clauses = sum(len({e["text"] for e in bank[t]}) for t in types)
    n_bench_clauses = sum(len(v) for v in bench_clauses.values())
    n_neg = sum(len({e["text"] for e in negatives[t]}) for t in negatives)
    n_plantable = sum(len({e["text"] for e in negatives[t] if e.get("plantable")}) for t in negatives)
    plantable_bench = sum(
        len({e["text"] for e in negatives[t] if e.get("plantable") and e["text"] in set(bench_negatives.get(t, []))})
        for t in negatives)
    plantable_train = n_plantable - plantable_bench
    pools = {}
    for key, strings in pool_strata.items():
        pools[key] = {"total": len(set(strings)), "benchmark": len(bench_names[key])}
    return {
        "clause_texts": {"total": n_clauses, "benchmark": n_bench_clauses,
                         "share": round(n_bench_clauses / n_clauses, 3) if n_clauses else 0.0},
        "negative_texts": {"total": n_neg, "benchmark": sum(len(v) for v in bench_negatives.values())},
        "plantable_negative_texts": {"total": n_plantable, "benchmark": plantable_bench,
                                     "train": plantable_train},
        "name_pools": pools,
    }


def extend_negatives(partition: dict, clause_bank: dict, batch: str,
                     ratio: float = NEGATIVE_BATCH_BENCHMARK_RATIO) -> dict:
    """Partition a later batch of negatives without touching any earlier assignment.

    The partition lists only the benchmark share, and everything unlisted is
    training, so adding a batch to the bank would silently put all of it in
    training. This assigns the batch deterministically instead, per (type, form)
    stratum and ranked by hash exactly as `build_partition` does, adds its
    benchmark share to `negatives`, and lists its training share in
    `negatives_train` so the split can be read and checked rather than inferred.

    Args:
        partition: The loaded partition.
        clause_bank: The flat bank from `gendoc_data.load_clause_bank`; the batch
            is every negative whose `origin` equals `batch`.
        batch: Batch name, e.g. "nearmiss_v5".
        ratio: Benchmark share of the batch.

    Returns:
        A new partition dict; the argument is not modified.

    Raises:
        ValueError: The batch is already recorded, is empty, or shares a text
            with a clause or an earlier negative (a text is on one side only).
    """
    if batch in partition.get("negative_batches", {}):
        raise ValueError(f"negatives batch {batch!r} is already in the partition")
    negatives = clause_bank.get("negatives", {})
    fresh = {t: [e for e in entries if e.get("origin") == batch] for t, entries in negatives.items()}
    fresh = {t: v for t, v in fresh.items() if v}
    if not fresh:
        raise ValueError(f"no negatives with origin {batch!r} in the bank")
    batch_texts = {e["text"] for v in fresh.values() for e in v}
    earlier = ({e["text"] for t, v in negatives.items() for e in v if e.get("origin") != batch}
               | {e["text"] for t, v in clause_bank.items() if t != "negatives" for e in v})
    if batch_texts & earlier:
        raise ValueError(f"batch shares texts with the bank: {sorted(batch_texts & earlier)[:3]}")

    strata = {f"{t}:{form}": [e["text"] for e in entries if e["form"] == form]
              for t, entries in sorted(fresh.items()) for form in ("nb", "nn", "en")}
    assigned: Dict[str, bool] = {}
    _assign({k: v for k, v in strata.items() if v}, assigned, ratio, True, salt=NEGATIVE_BATCH_SALT)

    out = json.loads(json.dumps(partition))
    bench = {t: set(v) for t, v in out["negatives"].items()}
    train: Dict[str, Set[str]] = {t: set(v) for t, v in out.get("negatives_train", {}).items()}
    for t, entries in fresh.items():
        for e in entries:
            (bench if assigned[e["text"]] else train).setdefault(t, set()).add(e["text"])
    out["negatives"] = {t: sorted(v) for t, v in sorted(bench.items()) if v}
    out["negatives_train"] = {t: sorted(v) for t, v in sorted(train.items()) if v}
    out.setdefault("negative_batches", {})[batch] = {
        "salt": NEGATIVE_BATCH_SALT, "ratio": ratio, "texts": len(batch_texts),
        "benchmark": sum(1 for v in assigned.values() if v),
        "train": sum(1 for v in assigned.values() if not v),
    }
    out["version"] = PARTITION_VERSION
    bench_clauses = {t: set(v) for t, v in out["clauses"].items()}
    pool_strata = _pool_strata(data.full_pools())
    out["counts"] = _counts(clause_bank, bench_clauses, bench, pool_strata, out["names"])
    return out


def load_partition(path: str = PARTITION_PATH) -> dict:
    """Load the partition file, failing loudly if it is missing.

    A missing partition must not fall back to "everything is training": a
    benchmark run would then silently share its clauses with the training set.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found; run `python3 tools/gendoc_dataset.py build` once and commit it")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def select_clause_bank(clause_bank: dict, partition: dict, dataset: str) -> dict:
    """Return the clause bank restricted to one dataset's share.

    Args:
        clause_bank: The flat bank from `gendoc_data.load_clause_bank`.
        partition: The loaded partition.
        dataset: "train" or "benchmark".

    Returns:
        A bank of the same shape holding only the entries (and negatives) that
        belong to `dataset`.
    """
    want_bench = dataset == "benchmark"
    held = {t: set(v) for t, v in partition["clauses"].items()}
    held_neg = {t: set(v) for t, v in partition["negatives"].items()}
    out: dict = {}
    for etype, entries in clause_bank.items():
        if etype == "negatives":
            continue
        out[etype] = [e for e in entries if (e["text"] in held.get(etype, ())) == want_bench]
    out["negatives"] = {
        etype: [e for e in entries if (e["text"] in held_neg.get(etype, ())) == want_bench]
        for etype, entries in clause_bank.get("negatives", {}).items()}
    return out


def select_pools(partition: dict, dataset: str) -> data.NamePools:
    """Return the name, street and employer-prefix pools for one dataset."""
    want_bench = dataset == "benchmark"
    held = {key: set(v) for key, v in partition["names"].items()}

    def pick(key: str, strings) -> Tuple[str, ...]:
        return tuple(s for s in strings if (s in held.get(key, ())) == want_bench)

    full = data.full_pools()
    foreign = {nat: (pick(f"foreign:{nat}:first_male", m), pick(f"foreign:{nat}:first_female", f),
                     pick(f"foreign:{nat}:surnames", s))
               for nat, (m, f, s) in full.foreign_names.items()}
    return data.NamePools(
        pick("first_male", full.first_male), pick("first_female", full.first_female),
        pick("surnames", full.surnames), foreign, pick("street_names", full.street_names),
        pick("org_prefixes", full.org_prefixes))


def partition_text_sets(partition: dict) -> Dict[str, Set[str]]:
    """Return the benchmark clause texts, negative texts and names as flat sets, for the leakage check."""
    return {
        "clauses": {s for v in partition["clauses"].values() for s in v},
        "negatives": {s for v in partition["negatives"].values() for s in v},
        "names": {s for v in partition["names"].values() for s in v},
    }


def main() -> int:
    """CLI: build or summarise the partition file."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "extend-negatives", "summary"])
    parser.add_argument("batch", nargs="?", help="negatives batch name for extend-negatives")
    parser.add_argument("--clause-bank", default="data/synthetic/clause_bank.json")
    parser.add_argument("--partition", default=PARTITION_PATH)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing partition; this re-assigns entries and "
                             "invalidates every benchmark generated against the old one")
    args = parser.parse_args()
    if args.command == "build":
        if os.path.exists(args.partition) and not args.force:
            print(f"{args.partition} exists; refusing to overwrite without --force", file=sys.stderr)
            return 2
        partition = build_partition(data.load_clause_bank(args.clause_bank))
        with open(args.partition, "w", encoding="utf-8") as handle:
            json.dump(partition, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
    elif args.command == "extend-negatives":
        if not args.batch:
            print("extend-negatives needs a batch name", file=sys.stderr)
            return 2
        partition = extend_negatives(load_partition(args.partition),
                                     data.load_clause_bank(args.clause_bank), args.batch)
        with open(args.partition, "w", encoding="utf-8") as handle:
            json.dump(partition, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
    else:
        partition = load_partition(args.partition)
    print(json.dumps(partition["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
