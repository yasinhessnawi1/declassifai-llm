"""String-level scoring of the real route's answers against a string-level gold set (A12's definition).

Per document and type, the distinct gold strings are matched with the distinct predicted strings:
  - exact: the predicted string equals a gold string;
  - lenient: case-insensitive containment either way (tools/score_predictions.py), each string matched once.
Precision and F1 count the predicted strings of the type; recall the gold strings. Overall numbers are
micro-averaged over the 59 types.

A predicted string is the document's own text under a box of the route's answer (run_route.py): the route
answers one box per finding (the merge has already joined overlapping findings of a category). Boxes of a type
that overlap, which only the offline floors can produce, are joined. A box with no taxonomy category is not a
prediction of any type.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from .taxonomy import DEFAULT_ENGINE_MODELS

RULES = "rules"


def match_lenient(gold: list, pred: list) -> int:
    used, hits = set(), 0
    for g in gold:
        gl = g.lower().strip()
        for j, p in enumerate(pred):
            if j in used:
                continue
            pl = p.lower().strip()
            if gl in pl or pl in gl:
                used.add(j)
                hits += 1
                break
    return hits


def prf(tp: int, n_pred: int, n_gold: int) -> tuple:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def _kept(item: dict, floors: dict, models: dict) -> bool:
    """Whether a box stands at these floors: a rule box always; an engine box when one engine's score clears
    that engine's floor (None: no floor)."""
    engines = item.get("engines") or []
    if not engines or RULES in engines:
        return True
    scores = item.get("engine_scores") or {}
    for e in engines:
        floor = floors.get(models.get(e, e))
        score = scores.get(e, item.get("score"))
        if floor is None or score is None or score >= floor:
            return True
    return False


def boxes_at(doc: dict, floors: dict | None = None, models: dict = DEFAULT_ENGINE_MODELS) -> list:
    """The route's boxes, or the boxes it would give at other floors: boxes under a raised floor are removed and
    findings recorded under the route's floor that clear a lowered one are added. Offline, so a finding added
    back does not go through the rules' merge again (an approximation, stated where it is used)."""
    items = list(doc.get("items") or [])
    if floors is None:
        return items
    out = [i for i in items if _kept(i, floors, models)]
    for u in doc.get("under_floor") or []:
        floor = floors.get(u.get("model"))
        if floor is None or (u.get("score") is not None and u["score"] >= floor):
            out.append({"category": u.get("category"), "start": u["start"], "end": u["end"],
                        "score": u.get("score"), "engines": u.get("engines") or []})
    return out


def strings_of(boxes: list, text: str) -> dict:
    """{type: [distinct strings]} from boxes over the document's own text."""
    by_type = collections.defaultdict(list)
    for b in boxes:
        if b.get("category") and b["end"] > b["start"]:
            by_type[b["category"]].append((b["start"], b["end"]))
    out = {}
    for t, spans in by_type.items():
        spans.sort()
        joined = []
        for s, e in spans:
            if joined and s < joined[-1][1]:
                joined[-1][1] = max(joined[-1][1], e)
            else:
                joined.append([s, e])
        out[t] = list(dict.fromkeys(text[s:e] for s, e in joined))
    return out


def score(gold_docs: dict, preds: dict, type_ids: list, tiers: dict) -> dict:
    """gold_docs: id -> {"text", "output"}; preds: id -> {type: [strings]}. Documents missing from preds count
    as answered with nothing."""
    c = {t: collections.Counter() for t in type_ids}
    for doc, g in gold_docs.items():
        p = preds.get(doc) or {}
        for t in type_ids:
            gs, ps = g["output"].get(t, []), p.get(t, [])
            if gs:
                c[t]["docs"] += 1
            c[t]["gold"] += len(gs)
            c[t]["pred"] += len(ps)
            c[t]["exact"] += len(set(gs) & set(ps))
            c[t]["lenient"] += match_lenient(gs, ps)
    per_type = {t: metrics(k) for t, k in c.items()}
    agg = collections.defaultdict(collections.Counter)
    for t, k in c.items():
        for key in ("gold", "pred", "exact", "lenient"):
            agg["ALL"][key] += k[key]
            agg[tiers[t]][key] += k[key]
    for doc, g in gold_docs.items():  # documents with a gold string, overall and per tier
        held = {tiers[t] for t, v in g["output"].items() if v and t in tiers}
        for name in held | ({"ALL"} if held else set()):
            agg[name]["docs"] += 1
    return {"per_type": per_type, "overall": {name: metrics(k) for name, k in sorted(agg.items())},
            "docs": len(gold_docs), "missing": sorted(set(gold_docs) - set(preds))}


def metrics(k) -> dict:
    pe, re_, fe = prf(k["exact"], k["pred"], k["gold"])
    pl, rl, fl = prf(k["lenient"], k["pred"], k["gold"])
    return {"f1_exact": round(fe, 3), "f1_lenient": round(fl, 3), "recall_exact": round(re_, 3),
            "recall_lenient": round(rl, 3), "precision_exact": round(pe, 3), "precision_lenient": round(pl, 3),
            "spans": k["gold"], "predicted": k["pred"], "docs": k.get("docs", 0)}


def read_run(path: Path) -> tuple:
    """(docs by id, summary) of a run_route.py output file."""
    docs, summary, start = {}, None, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("{"):
            continue
        d = json.loads(line)
        if d.get("type") == "doc":
            docs[d["id"]] = d
        elif d.get("type") == "summary":
            summary = d
        elif d.get("type") == "start":
            start = d
    if summary is not None:
        summary = {**summary, "table": start.get("table")}
    return docs, summary


def score_run(gold_docs: dict, run_docs: dict, type_ids: list, tiers: dict, floors: dict | None = None) -> dict:
    preds = {i: strings_of(boxes_at(d, floors), gold_docs[i]["text"]) for i, d in run_docs.items() if i in gold_docs}
    return score(gold_docs, preds, type_ids, tiers)
