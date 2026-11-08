"""Aggregates-only report of a gold-set scoring run, and the comparison of two routing tables.

    python -m eval.routing.report OUT_DIR OLD_TABLE.json > routing_report.md

Reads OUT_DIR/scores.json, floors.json, gate.json and routing_table.json (score_gold.py). Prints numbers, type
names and engine names only, never document text.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .taxonomy import load_taxonomy

NAMES = {"rules": "Rules alone", "fast": "Fast (tagger)", "standard": "Standard (GLiNER 0.5)",
         "advanced": "Advanced (gpt-4o 0.5)"}
ORDER = ["rules", "fast", "standard", "advanced"]


def label(run: str) -> str:
    if run in NAMES:
        return NAMES[run]
    if run.startswith("routed_"):
        return run[len("routed_"):] + ", routed (new table)"
    return run + ", routed (provisional table)"


def runs_in_order(runs: dict) -> list:
    rest = sorted(r for r in runs if r not in ORDER)
    return [r for r in ORDER if r in runs] + [r for r in rest if not r.startswith("routed_")] + \
        [r for r in rest if r.startswith("routed_")]


def f(x) -> str:
    return "–" if x is None else f"{x:.3f}"


def overall_table(scores: dict) -> list:
    out = ["| Engine | Exact F1 | Lenient F1 | Exact recall | Lenient recall | Exact P | Lenient P | Gold strings | Predicted | Documents |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs_in_order(scores):
        m = scores[r]["overall"]["ALL"]
        out.append(f"| {label(r)} | {f(m['f1_exact'])} | {f(m['f1_lenient'])} | {f(m['recall_exact'])} | "
                   f"{f(m['recall_lenient'])} | {f(m['precision_exact'])} | {f(m['precision_lenient'])} | "
                   f"{m['spans']} | {m['predicted']} | {m['docs']} |")
    return out


def tier_table(scores: dict) -> list:
    out = ["| Engine | Tier A lenient F1 / R | Tier B lenient F1 / R | Tier C lenient F1 / R |", "|---|---|---|---|"]
    for r in runs_in_order(scores):
        o = scores[r]["overall"]
        cells = [f"{f(o[t]['f1_lenient'])} / {f(o[t]['recall_lenient'])}" if t in o else "–" for t in "ABC"]
        out.append(f"| {label(r)} | " + " | ".join(cells) + " |")
    return out


def per_type_table(scores: dict, tax, table: dict, runs: list) -> list:
    head = "| Type | Tier | Strings | Docs | " + " | ".join(label(r) for r in runs) + " | Provisional |"
    out = [head, "|" + "---|" * (5 + len(runs))]
    for t in tax.ids:
        any_run = scores[runs[0]]["per_type"][t]
        cells = []
        for r in runs:
            m = scores[r]["per_type"][t]
            cells.append(f"{f(m['f1_exact'])}/{f(m['f1_lenient'])} · {f(m['recall_exact'])}/{f(m['recall_lenient'])}")
        prov = "yes" if table["types"][t]["provisional"] else "no"
        out.append(f"| {t} | {tax.types[t].tier} | {any_run['spans']} | {any_run['docs']} | " + " | ".join(cells) + f" | {prov} |")
    return out


def route_of(table: dict, t: str, key: str) -> str:
    r = table["types"][t]["routes"][key]
    return "+".join(r["read"]) or "–"


def comparison(old: dict, new: dict, tax) -> tuple:
    rows, primary_changed, second_changed = [], [], []
    for t in tax.ids:
        o, n = old["types"][t], new["types"][t]
        p_change = o["primary"] != n["primary"]
        s_change = o.get("second") != n.get("second")
        reads = {k: (route_of(old, t, k), route_of(new, t, k)) for k in ("fast+standard", "fast+standard+advanced")}
        r_change = any(a != b for a, b in reads.values())
        if p_change:
            primary_changed.append(t)
        if s_change:
            second_changed.append(t)
        if p_change or s_change or r_change or o["provisional"] != n["provisional"]:
            rows.append(f"| {t} | {o['primary']} → {n['primary']} | {o.get('second') or '–'} → {n.get('second') or '–'} | "
                        f"{reads['fast+standard'][0]} → {reads['fast+standard'][1]} | "
                        f"{reads['fast+standard+advanced'][0]} → {reads['fast+standard+advanced'][1]} | "
                        f"{n['rung']} | {'yes' if o['provisional'] else 'no'} → {'yes' if n['provisional'] else 'no'} |")
    head = ["| Type | Primary (old → new) | Second (old → new) | Reads, Fast+Standard | Reads, all three | Deciding rung | Provisional |",
            "|---|---|---|---|---|---|---|"]
    return head + rows, primary_changed, second_changed


def main(argv: list) -> int:
    out, old_path = Path(argv[1]), Path(argv[2])
    tax = load_taxonomy()
    scores = json.loads((out / "scores.json").read_text())["runs"]
    new = json.loads((out / "routing_table.json").read_text())
    old = json.loads(old_path.read_text())
    gate = json.loads((out / "gate.json").read_text())
    floors = json.loads((out / "floors.json").read_text())
    lines = ["## Overall (all 59 types, micro-averaged)", ""] + overall_table(scores) + ["", "## Per tier", ""] + tier_table(scores)
    runs = [r for r in runs_in_order(scores)]
    lines += ["", "## Per type", "", "Each cell: exact F1 / lenient F1 · exact recall / lenient recall. Strings and documents are the gold "
              "set's (distinct strings per document).", ""] + per_type_table(scores, tax, new, runs)
    lines += ["", "## Floors (offline, from the single-engine runs)", "",
              "| Model | Floor | Lenient F1 | Lenient recall | Exact F1 |", "|---|---|---|---|---|"]
    for model, by in floors.items():
        for fl, v in by.items():
            o = v["overall"]
            lines.append(f"| {model} | {fl} | {f(o['f1_lenient'])} | {f(o['recall_lenient'])} | {f(o['f1_exact'])} |")
    lines += ["", "## Table gate", ""]
    for key, v in gate["sets"].items():
        fails = ", ".join(f"{x['type']} ({f(x['routed'])} vs {f(x['best_single'])}, {x['spans']} strings)" for x in v["fails"])
        lines.append(f"- {key}: {'passes' if v['pass'] else 'fails: ' + fails}")
    if gate.get("not_run"):
        lines.append(f"- not run: {', '.join(gate['not_run'])}")
    rows, pc, sc = comparison(old, new, tax)
    prov = [t for t in tax.ids if new["types"][t]["provisional"]]
    lines += ["", f"## Old table {old['version']} against new {new['version']}", "",
              f"Primary changes: {len(pc)} ({', '.join(pc) or 'none'}).", "",
              f"Second-engine changes: {len(sc)} ({', '.join(sc) or 'none'}).", "", *rows, "",
              f"Still provisional: {len(prov)} of 59: {', '.join(prov)}."]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
