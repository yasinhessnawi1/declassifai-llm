"""Builds, writes and structure-checks routing_table.json."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import yaml

from .rule import RULE_NAME, WATCH_BELOW, candidates, decide, provisional_reasons, union_key
from .taxonomy import DEFAULT_ENGINE_MODELS, ENGINES, PRODUCT_ENGINES, Taxonomy

HERE = Path(__file__).parent
SCHEMA = 1


def engine_sets() -> list:
    """The 7 non-empty sets of product engines, as route keys."""
    out = []
    for r in range(1, 4):
        for combo in itertools.combinations(PRODUCT_ENGINES, r):
            out.append("+".join(combo))
    return sorted(out, key=lambda k: (k.count("+"), k))


def load_floors(path: Path = HERE / "floors.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _gold_recall(unions: dict, models) -> float | None:
    """Lenient recall on the gold set of reading these models together (a single engine or a union)."""
    cell = unions.get(union_key(models)) if models else None
    return None if cell is None else cell.get("recall_lenient")


def keep_baseline_recall(read: list, fallback: list, baseline_read: list, unions: dict) -> tuple:
    """Below the gold bar a new route never reads less on the gold set than the baseline table's route: while it
    would, the baseline engine that helps most is added to the reads (and leaves the fallback)."""
    read, fallback = list(read), list(fallback)
    added = []
    while True:
        now, before = _gold_recall(unions, read), _gold_recall(unions, baseline_read)
        if now is None or before is None or now >= before - 1e-9:
            return read, fallback, added
        options = [m for m in baseline_read if m not in read]
        if not options:
            return read, fallback, added
        best = max(options, key=lambda m: (_gold_recall(unions, read + [m]) or 0, -ENGINES.index(m)))
        read.append(best)
        added.append(best)
        if best in fallback:
            fallback.remove(best)


def build_table(tax: Taxonomy, evidence_doc: dict, floors_doc: dict, *, version: str, built: str,
                scorer_commit=None, note=None, engine_models: dict = DEFAULT_ENGINE_MODELS,
                baseline: dict | None = None) -> dict:
    """evidence_doc may carry `unions` (type -> gold set id -> union key -> cell). With a baseline table, a type
    below the gold bar keeps at least the baseline route's lenient recall on the gold set (see keep_baseline_recall)."""
    floors = floors_doc["floors"]
    sets = evidence_doc["sets"]
    to_product = {m: p for p, m in engine_models.items()}
    gold_ids = [s["id"] for s in sets if s.get("kind") == "gold"]
    types = {}
    for tid in tax.ids:
        ev = evidence_doc["cells"].get(tid, {})
        unions = (evidence_doc.get("unions") or {}).get(tid, {})
        full = decide(tax, tid, ev, sets, floors, list(engine_models.values()), unions=unions)
        routes = {}
        kept_by_baseline = {}
        for key in engine_sets():
            enabled = [engine_models[p] for p in key.split("+")]
            d = decide(tax, tid, ev, sets, floors, enabled, hint_set=full.evidence_set, unions=unions)
            read, fallback, hint = list(d.read), list(d.fallback), d.hint
            gold_unions = unions.get(gold_ids[0], {}) if gold_ids else {}
            if baseline is not None and full.rung != "gold" and gold_unions:
                old = baseline["types"][tid]["routes"][key]["read"]
                read, fallback, added = keep_baseline_recall(
                    read, fallback, [engine_models[p] for p in old], gold_unions)
                if added:
                    kept_by_baseline[key] = [to_product[m] for m in added]
                    if hint == "weak" and any((_gold_recall(gold_unions, [m]) or 0) >= WATCH_BELOW for m in read):
                        hint = None
            routes[key] = {
                "read": [to_product[m] for m in read],
                "fallback": [to_product[m] for m in fallback],
                "hint": "gap" if not d.candidates else hint,
            }
        reasons = provisional_reasons(full, ev, sets)
        types[tid] = {
            "evidence": ev,
            "deciding_set": full.deciding_set,
            "rung": full.rung,
            "provisional": bool(reasons),
            "provisional_reasons": reasons,
            "watch": full.watch,
            "primary": full.primary,
            "second": full.second,
            "routes": routes,
        }
        if kept_by_baseline:
            types[tid]["kept_from_baseline"] = kept_by_baseline
    table = {
        "schema": SCHEMA,
        "version": version,
        "taxonomy_version": tax.version,
        "built": built,
        "scorer": {"repo": "llm_finetune", "commit": scorer_commit, "rule": RULE_NAME},
        "engine_models": dict(engine_models),
        "floors": dict(floors),
        "floors_provisional": list(floors_doc.get("provisional", [])),
        "sets": sets,
        "types": types,
    }
    if note:
        table["note"] = note
    return table


def dumps(table: dict) -> str:
    return json.dumps(table, indent=1, ensure_ascii=False) + "\n"


def write_table(table: dict, path: Path) -> None:
    Path(path).write_text(dumps(table), encoding="utf-8")


def check_table_structure(table: dict, tax: Taxonomy, floors_doc: dict | None = None) -> list:
    """The checks the service makes at start. Returns problems; empty means it passes."""
    floors_doc = floors_doc or load_floors()
    problems = []
    if table.get("schema") != SCHEMA:
        problems.append(f"schema is {table.get('schema')!r}")
    if table.get("taxonomy_version") != tax.version:
        problems.append(f"taxonomy_version {table.get('taxonomy_version')!r}, loaded {tax.version!r}")
    if table.get("floors") != floors_doc["floors"]:
        problems.append("floors differ from the engines' config")
    models = table.get("engine_models") or {}
    if set(models) != set(PRODUCT_ENGINES):
        problems.append("engine_models must name fast, standard and advanced")
        return problems
    types = table.get("types", {})
    if list(sorted(types)) != sorted(tax.ids):
        problems.append("types are not the taxonomy's 59 ids")
    expected_sets = set(engine_sets())
    for tid, t in types.items():
        if tid not in tax.types:
            continue
        routes = t.get("routes", {})
        if set(routes) != expected_sets:
            problems.append(f"{tid}: routes are not the 7 engine sets")
            continue
        for key, r in routes.items():
            enabled = key.split("+")
            labelled = {p for p in enabled if models[p] in candidates(tax, tid, [models[q] for q in enabled])}
            for field in ("read", "fallback"):
                for p in r.get(field, []):
                    if p not in enabled:
                        problems.append(f"{tid} {key}: {field} names {p}, which is not in the set")
                    elif p not in labelled:
                        problems.append(f"{tid} {key}: {field} names {p}, which has no label for the type")
            if set(r.get("read", [])) & set(r.get("fallback", [])):
                problems.append(f"{tid} {key}: an engine is in both read and fallback")
            if not r.get("read") and labelled:
                problems.append(f"{tid} {key}: nothing reads a type that has a label")
            if r.get("hint") not in (None, "gap", "weak", "no_evidence"):
                problems.append(f"{tid} {key}: bad hint {r.get('hint')!r}")
    return problems
