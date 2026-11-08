"""Scores the real route's runs on a string-level gold set and rebuilds the routing table from them.

    python -m eval.routing.score_gold GOLD.jsonl RUNS_DIR OUT_DIR --set-id ID --date YYYY-MM-DD \\
        --version V --built YYYY-MM-DD [--scorer-commit SHA]

RUNS_DIR holds run_route.py outputs named after the engine set: rules.jsonl, fast.jsonl, standard.jsonl,
advanced.jsonl, and the routed combinations (fast+standard.jsonl, ...). A file named routed_<set>.jsonl is a
combination run with the new table; the table gate reads those.

OUT_DIR gets (aggregates only, never document text):
  scores.json            per run: per type and overall, exact and lenient F1, recall, precision, spans, documents
  floors.json            GLiNER and gpt-4o at other floors, from the single-engine runs (offline)
  engine_evidence.json   the recorded evidence plus this gold set's cells (single engines at their floors)
  routing_table.json     the rule applied to that evidence
  gate.json              the table gate, when routed runs with this table exist
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .string_gold import load_string_gold
from .string_score import read_run, score_run
from .table import HERE, build_table, check_table_structure, engine_sets, load_floors, write_table
from .taxonomy import DEFAULT_ENGINE_MODELS, check_pin, load_taxonomy

FLOOR_STEPS = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7)
GATE_DROP = 0.03
SOURCE = ("held-out gold set: {docs} documents written through an Opus pipeline from labels planned in advance, "
          "reviewed by Sonnet and Opus, then proofread and accepted by the owner (frozen {date}); held out of every "
          "training build. It comes from a different pipeline than bench_v3_s100, but it is synthetic: these are not "
          "real customer documents. Each engine alone through the service's text route (categories ALL, one page per "
          "document, the rules on) at its floor; detection_service {commit}. String-level scoring (A12: distinct "
          "strings per document, exact and lenient). The set has no offsets, so there is no span-level score; genre is "
          "not recorded.")


def gate(single: dict, routed: dict, type_ids: list) -> dict:
    """Per routed engine set: types whose lenient recall falls more than GATE_DROP under the best single engine of
    the set. single: product engine -> scores; routed: set key -> scores."""
    out = {}
    for key, sc in routed.items():
        engines = key.split("+")
        fails = []
        for t in type_ids:
            if not sc["per_type"][t]["spans"]:
                continue
            best = max(single[e]["per_type"][t]["recall_lenient"] for e in engines if e in single)
            got = sc["per_type"][t]["recall_lenient"]
            if best - got > GATE_DROP + 1e-9:
                fails.append({"type": t, "routed": got, "best_single": best, "spans": sc["per_type"][t]["spans"]})
        out[key] = {"fails": fails, "pass": not fails}
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("runs")
    ap.add_argument("out")
    ap.add_argument("--set-id", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--built", required=True)
    ap.add_argument("--scorer-commit")
    ap.add_argument("--service-commit", required=True)
    a = ap.parse_args(argv[1:])

    check_pin()
    tax = load_taxonomy()
    gold = load_string_gold(Path(a.gold))
    if not gold.ok:
        print("\n".join(gold.errors[:20]))
        print(f"gold set fails its checks ({len(gold.errors)} errors); nothing scored")
        return 1
    tiers = {t: info.tier for t, info in tax.types.items()}
    runs, summaries = {}, {}
    for p in sorted(Path(a.runs).glob("*.jsonl")):
        docs, summary = read_run(p)
        missing = set(gold.docs) - set(docs)
        if missing:
            print(f"{p.name}: {len(missing)} documents not answered; refused")
            return 1
        runs[p.stem] = docs
        summaries[p.stem] = summary
    scores = {name: score_run(gold.docs, docs, tax.ids, tiers) for name, docs in runs.items()}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.json").write_text(json.dumps({"set": a.set_id, "runs": scores, "summaries": summaries}, indent=1) + "\n")

    floors_doc = load_floors()
    floors = floors_doc["floors"]
    sweep = {}
    for product in ("standard", "advanced"):
        if product not in runs:
            continue
        model = DEFAULT_ENGINE_MODELS[product]
        sweep[model] = {}
        for f in FLOOR_STEPS:
            sc = score_run(gold.docs, runs[product], tax.ids, tiers, floors={**floors, model: f})
            sweep[model][str(f)] = {"overall": sc["overall"]["ALL"],
                                    "per_type": {t: {k: v[k] for k in ("recall_lenient", "f1_lenient", "spans")}
                                                 for t, v in sc["per_type"].items()}}
    (out / "floors.json").write_text(json.dumps(sweep, indent=1) + "\n")

    evidence = json.loads((HERE / "data" / "engine_evidence.json").read_text(encoding="utf-8"))
    evidence["sets"] = [s for s in evidence["sets"] if s["id"] != a.set_id] + [
        {"id": a.set_id, "kind": "gold", "docs": len(gold.docs), "date": a.date,
         "note": "held out; Opus-written from planned labels and accepted by the owner; synthetic, not customer documents"}]
    evidence["sources"][a.set_id] = SOURCE.format(docs=len(gold.docs), date=a.date, commit=a.service_commit)
    for product, model in DEFAULT_ENGINE_MODELS.items():
        if product not in scores:
            print(f"no run for {product}; the table needs all three engines")
            return 1
        for t in tax.ids:
            m = scores[product]["per_type"][t]
            if not m["spans"]:
                continue
            cell = {k: m[k] for k in ("f1_exact", "f1_lenient", "recall_exact", "recall_lenient", "spans", "docs")}
            cell["floor"] = floors.get(model)
            evidence["cells"].setdefault(t, {}).setdefault(a.set_id, {})[model] = cell
    (out / "engine_evidence.json").write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n")

    note = (f"Built from the gold set {a.set_id} ({a.date}) where a type meets the bar (at least 30 gold strings in "
            "at least 15 documents); other types keep the earlier evidence and stay provisional. The gold set is "
            "held out and comes from a different pipeline than bench_v3_s100, but it is synthetic (Opus-written), "
            "not real customer documents. See sources.")
    table = build_table(tax, evidence, floors_doc, version=a.version, built=a.built, scorer_commit=a.scorer_commit,
                        note=note)
    table["sources"] = evidence["sources"]
    problems = check_table_structure(table, tax, floors_doc)
    if problems:
        print("\n".join(problems))
        return 1
    routed = {name[len("routed_"):]: sc for name, sc in scores.items() if name.startswith("routed_")
              and (summaries.get(name) or {}).get("table", table["version"]) == table["version"]}
    single = {p: scores[p] for p in DEFAULT_ENGINE_MODELS}
    g = gate(single, routed, tax.ids)
    missing_sets = [k for k in engine_sets() if "+" in k and k not in routed]
    (out / "gate.json").write_text(json.dumps({"table": a.version, "sets": g, "not_run": missing_sets}, indent=1) + "\n")
    if any(not v["pass"] for v in g.values()):
        print("table gate fails; the table is not written:", {k: [f["type"] for f in v["fails"]] for k, v in g.items()})
        return 2
    write_table(table, out / "routing_table.json")
    print(f"scored {len(runs)} runs on {len(gold.docs)} documents; table {a.version}; gate "
          f"{'not run for ' + ', '.join(missing_sets) if missing_sets else 'passes'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
