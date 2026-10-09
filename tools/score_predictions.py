"""Score any model's predictions against the v2 gold set, model-agnostically.

Every candidate -- a fine-tuned LLM, an encoder tagger, GLiNER -- writes one JSONL line
per document, `{"id": ..., "output": {TYPE: [span strings]}}`, and this scores it the same
way, so models of different families are compared on identical terms.

Two matches, per type:

* **exact**   -- the predicted string equals a gold string.
* **lenient** -- case-insensitive containment either way (the src/evaluator.py rule).

Each gold string and each predicted string is matched at most once. Scores are reported
per type, per taxonomy tier (A mechanical / B contextual / C judgement), and overall
(micro-averaged). Types with no gold support are listed separately, because gold cannot
measure them.

Usage:
    python tools/score_predictions.py preds.jsonl
    python tools/score_predictions.py preds.jsonl --gold 'data/gold_v2/*.jsonl' --json out.json
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
from typing import Dict, List, Tuple

from v2_schema import TAXONOMY_PATH


def load(patterns: List[str]) -> Dict[str, dict]:
    out = {}
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    out[r["id"]] = r
    return out


def _match(gold: List[str], pred: List[str], lenient: bool) -> int:
    used, hits = set(), 0
    for g in gold:
        gl = g.lower().strip()
        for j, p in enumerate(pred):
            if j in used:
                continue
            ok = (g == p) if not lenient else (gl in p.lower().strip() or p.lower().strip() in gl)
            if ok:
                used.add(j); hits += 1
                break
    return hits


def prf(tp: int, n_pred: int, n_gold: int) -> Tuple[float, float, float]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score(gold: Dict[str, dict], preds: Dict[str, dict]) -> dict:
    tiers = {t["name"]: t["tier"] for t in json.load(open(TAXONOMY_PATH, encoding="utf-8"))["types"]}
    c = collections.defaultdict(lambda: collections.Counter())
    missing = [i for i in gold if i not in preds]
    for doc_id, g in gold.items():
        pout = (preds.get(doc_id) or {}).get("output") or {}
        for t in set(g["output"]) | set(pout):
            gs, ps = list(dict.fromkeys(g["output"].get(t, []))), list(dict.fromkeys(pout.get(t, [])))
            c[t]["gold"] += len(gs); c[t]["pred"] += len(ps)
            c[t]["exact"] += len(set(gs) & set(ps))
            c[t]["lenient"] += _match(gs, ps, True)
    res = {"per_type": {}, "per_tier": {}, "missing_docs": len(missing)}
    agg = collections.defaultdict(collections.Counter)
    for t, k in c.items():
        tier = tiers.get(t, "?")
        res["per_type"][t] = {
            "tier": tier, "support": k["gold"], "predicted": k["pred"],
            "exact": prf(k["exact"], k["pred"], k["gold"]),
            "lenient": prf(k["lenient"], k["pred"], k["gold"]),
        }
        for key in ("gold", "pred", "exact", "lenient"):
            agg[tier][key] += k[key]; agg["ALL"][key] += k[key]
    for tier, k in agg.items():
        res["per_tier"][tier] = {"support": k["gold"],
                                 "exact": prf(k["exact"], k["pred"], k["gold"]),
                                 "lenient": prf(k["lenient"], k["pred"], k["gold"])}
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("predictions")
    ap.add_argument("--gold", nargs="*", default=["data/gold_v2/*.jsonl"])
    ap.add_argument("--json", help="write the full result here")
    args = ap.parse_args()
    gold, preds = load(args.gold), load([args.predictions])
    res = score(gold, preds)
    print(f"{'type':22} tier support   exact P/R/F1          lenient P/R/F1")
    for t, m in sorted(res["per_type"].items(), key=lambda kv: (kv[1]["tier"], -kv[1]["support"])):
        if not m["support"]:
            continue
        e, l = m["exact"], m["lenient"]
        print(f"{t:22} {m['tier']:4} {m['support']:7}   {e[0]:.3f} {e[1]:.3f} {e[2]:.3f}   {l[0]:.3f} {l[1]:.3f} {l[2]:.3f}")
    fp_only = sorted(t for t, m in res["per_type"].items() if not m["support"] and m["predicted"])
    if fp_only:
        print(f"\npredicted but absent from gold (unmeasurable here): {', '.join(fp_only)}")
    print()
    for tier in ("A", "B", "C", "ALL"):
        if tier in res["per_tier"]:
            m = res["per_tier"][tier]
            print(f"{'tier ' + tier:22}      {m['support']:7}   exact F1 {m['exact'][2]:.3f}   lenient F1 {m['lenient'][2]:.3f}")
    if res["missing_docs"]:
        print(f"\nWARNING: {res['missing_docs']} gold documents have no prediction (scored as empty)")
    if args.json:
        json.dump(res, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
