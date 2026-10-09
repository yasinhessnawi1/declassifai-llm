"""Sanity-check teacher pseudo-labels against the human-annotated slice.

There is no gold for the corpus documents, so the check is distributional: for each type,
spans per document in the teacher labels vs. slice_v2 documents of the same length range
(the relabeller runs shortest-first, so an unmatched comparison would mix templates).
A type whose rate differs by more than ~40% is flagged for manual review.

Usage:
    python tools/qa_teacher_labels.py data/corpus_v2_teacher/labels.jsonl [more.jsonl ...]
"""
import collections
import glob
import json
import statistics
import sys


def rates(records):
    spans, docs = collections.Counter(), collections.Counter()
    for r in records:
        for k, v in r["output"].items():
            if v:
                spans[k] += len(set(v))
                docs[k] += 1
    n = max(1, len(records))
    return {k: (spans[k] / n, docs[k] / n) for k in spans}


def main():
    teacher = [json.loads(l) for p in sys.argv[1:] for l in open(p, encoding="utf-8") if l.strip()]
    slice_ = [json.loads(l) for p in glob.glob("data/slice_v2/*.jsonl") for l in open(p, encoding="utf-8")]
    lengths = [len(r["text_input"]) for r in teacher]
    lo, hi = min(lengths), max(lengths)
    matched = [r for r in slice_ if lo <= len(r["text_input"]) <= hi]
    print(f"teacher {len(teacher)} docs, {lo}-{hi} chars (median {statistics.median(lengths):.0f}); "
          f"length-matched slice {len(matched)}/{len(slice_)}")
    rt, rs = rates(teacher), rates(matched)
    print(f"{'type':24}{'slice sp/doc':>13}{'teacher':>9}{'ratio':>7}")
    for k in sorted(set(rt) | set(rs), key=lambda k: -(rs.get(k, (0, 0))[0] + rt.get(k, (0, 0))[0])):
        s, t = rs.get(k, (0, 0))[0], rt.get(k, (0, 0))[0]
        ratio = t / s if s else float("inf")
        flag = "  <<" if max(s, t) > 0.05 and not 0.6 <= ratio <= 1.6 else ""
        print(f"{k:24}{s:13.3f}{t:9.3f}{ratio:7.2f}{flag}")


if __name__ == "__main__":
    main()
