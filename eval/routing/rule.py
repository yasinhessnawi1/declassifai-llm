"""The router rule. It lives here and nowhere else: the service only reads the table it writes.

Per type and set of enabled engines (models: tagger, gliner, gpt-4o; cheapest first):
  1. floors: a number counts only when measured at its engine's floor;
  2. candidates: enabled engines with a label of their own (a shared label counts only when
     no other enabled engine has a label);
  3. evidence ladder: gold set at the bar, then a real set with >= 50 spans, then the
     synthetic set with >= 30 spans, else the type goes to its default;
  4. primary: highest lenient F1; engines within 0.03 tie and the cheapest wins;
  5. second engine (recall first): a) primary lenient recall < 0.90 and another is higher;
     b) runner-up within 0.03 lenient and 0.15 exact F1, primary not >= 0.95 on F1 and recall;
     c) below the gold rung, a real set and the synthetic set pick different engines (at the gold
        rung the gold set settles the type and the synthetic set plays no part);
     d) the union of the top two engines (where the deciding set scored unions): its lenient recall
        beats the best single engine by more than 0.005 and its lenient F1 falls at most 0.11 under
        the primary's (a missed value costs more than an extra box);
  6. default: the tagger if on, else the cheapest enabled engine with a label; a watch-list
     type (primary lenient recall < 0.5 on the evidence there is) also reads the next engine;
  7. fallback: the other enabled candidates by lenient F1, cost order where there is no number;
  8. hint: gap, no_evidence, weak or null, read off the set that decides with all engines on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .taxonomy import ENGINES, Taxonomy

RULE_NAME = "routing rule v1"
TIE = 0.03
EXACT_NEAR = 0.15
RECALL_BAR = 0.90
TOP = 0.95
WATCH_BELOW = 0.5
GOLD_MIN_SPANS, GOLD_MIN_DOCS = 30, 15
REAL_MIN_SPANS = 50
BENCH_MIN_SPANS = 30
SPAN_BAR = 30  # the spans part of the bar that clears "provisional"
UNION_RECALL_GAIN = 0.005  # 5d: the union's lenient recall must beat the best single engine by more than this
UNION_F1_DROP = 0.11  # 5d: and its lenient F1 may fall at most this far under the primary's


@dataclass
class Decision:
    candidates: list
    primary: str | None = None
    second: str | None = None
    second_reason: str | None = None
    watch: bool = False
    watch_extra: str | None = None
    rung: str = "default"  # gold | real | bench | default
    deciding_set: str | None = None
    evidence_set: str | None = None  # deciding set, else the set with most spans (for hints)
    fallback: list = field(default_factory=list)
    hint: str | None = None

    @property
    def read(self) -> list:
        out = [e for e in (self.primary, self.second, self.watch_extra) if e]
        return list(dict.fromkeys(out))


def candidates(tax: Taxonomy, type_id: str, enabled: list) -> list:
    own = [e for e in ENGINES if e in enabled and tax.has_own_label(type_id, e)]
    if own:
        return own
    return [e for e in ENGINES if e in enabled and tax.has_shared_label(type_id, e)]


def _usable(cells: dict, floors: dict, cands: list) -> dict:
    """Cells of the candidates that were measured at their floor."""
    return {e: c for e, c in cells.items() if e in cands and c.get("floor") == floors.get(e)}


def _spans(usable: dict) -> int:
    return max((c["spans"] for c in usable.values()), default=0)


def _docs(usable: dict):
    docs = [c.get("docs") for c in usable.values()]
    return None if not docs or any(d is None for d in docs) else max(docs)


def pick(usable: dict) -> tuple:
    """(primary, ranking). Ranking is by lenient F1, ties within TIE go to the cheapest."""
    if not usable:
        return None, []
    best = max(c["f1_lenient"] for c in usable.values())
    tied = [e for e in ENGINES if e in usable and best - usable[e]["f1_lenient"] <= TIE + 1e-9]
    primary = tied[0]
    rest = sorted((e for e in usable if e != primary), key=lambda e: (-usable[e]["f1_lenient"], ENGINES.index(e)))
    return primary, [primary] + rest


def _second(primary: str, usable: dict, ranking: list, other_pick: str | None) -> tuple:
    p = usable[primary]
    others = [e for e in ranking if e != primary]
    # a) recall first
    rec = p.get("recall_lenient")
    if rec is not None and rec < RECALL_BAR:
        better = [e for e in others if (usable[e].get("recall_lenient") or -1) > rec]
        if better:
            best = max(better, key=lambda e: (usable[e]["recall_lenient"], -ENGINES.index(e)))
            return best, "recall"
    # b) close runner-up
    if others:
        r = others[0]
        close = (p["f1_lenient"] - usable[r]["f1_lenient"] <= TIE + 1e-9
                 and p["f1_exact"] - usable[r]["f1_exact"] <= EXACT_NEAR + 1e-9)
        top = p["f1_lenient"] >= TOP - 1e-9 and rec is not None and rec >= TOP - 1e-9
        if close and not top:
            return r, "runner_up"
    # c) real and synthetic disagree
    if other_pick and other_pick != primary:
        return other_pick, "sets_disagree"
    return None, None


def union_key(models) -> str:
    """The key of an engine combination's union cell: its models in cost order, joined by '+'."""
    return "+".join(e for e in ENGINES if e in set(models))


def _union(primary: str, usable: dict, ranking: list, unions: dict) -> str | None:
    """5d: the runner-up, when the union of the top two engines finds clearly more at a small cost in F1."""
    if len(ranking) < 2 or not unions:
        return None
    u = unions.get(union_key(ranking[:2]))
    if not u or u.get("recall_lenient") is None:
        return None
    best_single = max((c.get("recall_lenient") or 0) for c in usable.values())
    if (u["recall_lenient"] - best_single > UNION_RECALL_GAIN + 1e-9
            and usable[primary]["f1_lenient"] - u["f1_lenient"] <= UNION_F1_DROP + 1e-9):
        return ranking[1]
    return None


def decide(tax: Taxonomy, type_id: str, evidence: dict, sets: list, floors: dict, enabled: list,
           hint_set: str | None = None, unions: dict | None = None) -> Decision:
    """unions: set id -> union key -> cell, the unions of engine combinations scored on that set."""
    cands = candidates(tax, type_id, enabled)
    dec = Decision(candidates=cands)
    if not cands:
        return dec
    kinds = {s["id"]: s["kind"] for s in sets}
    per_set = {sid: _usable(c, floors, cands) for sid, c in evidence.items() if sid in kinds}
    per_set = {sid: u for sid, u in per_set.items() if u}

    def best_of(kind_ok, min_spans, need_docs=False):
        found = [(sid, u) for sid, u in per_set.items()
                 if kind_ok(kinds[sid]) and _spans(u) >= min_spans
                 and (not need_docs or (_docs(u) or 0) >= GOLD_MIN_DOCS)]
        return max(found, key=lambda x: _spans(x[1]), default=(None, None))

    sid, usable = best_of(lambda k: k == "gold", GOLD_MIN_SPANS, need_docs=True)
    rung = "gold"
    if sid is None:
        sid, usable = best_of(lambda k: k in ("real", "gold"), REAL_MIN_SPANS)
        rung = "real"
    if sid is None:
        sid, usable = best_of(lambda k: k == "synthetic_weak", BENCH_MIN_SPANS)
        rung = "bench"

    if sid is not None:
        dec.rung, dec.deciding_set = rung, sid
        dec.primary, ranking = pick(usable)
        other_pick = None
        # 5c: below the gold rung a real set and the synthetic set that disagree both read the type. Once the
        # gold set is at the bar it settles the type: the synthetic set neither picks nor adds an engine.
        if rung == "real":
            b_sid, b_u = best_of(lambda k: k == "synthetic_weak", BENCH_MIN_SPANS)
            other_pick = pick(b_u)[0] if b_sid else None
        dec.second, dec.second_reason = _second(dec.primary, usable, ranking, other_pick)
        if dec.second is None:
            dec.second = _union(dec.primary, usable, ranking, (unions or {}).get(sid, {}))
            dec.second_reason = "union" if dec.second else None
        dec.evidence_set = sid
    else:
        dec.primary = "tagger" if "tagger" in cands else cands[0]
        # the set with most spans, for watch list and hints
        if per_set:
            dec.evidence_set = max(per_set, key=lambda s: _spans(per_set[s]))

    ev = per_set.get(dec.evidence_set, {})
    rec = ev.get(dec.primary, {}).get("recall_lenient")
    dec.watch = rec is not None and rec < WATCH_BELOW

    # fallback: the other candidates, those with a number first
    in_read = {dec.primary, dec.second}
    rest = [e for e in cands if e not in in_read]
    rest.sort(key=lambda e: (e not in ev, -(ev[e]["f1_lenient"] if e in ev else 0), ENGINES.index(e)))
    if dec.watch and rest:
        dec.watch_extra = rest.pop(0)
    dec.fallback = rest

    # hint: read off the set that decides for the type with every engine on (hint_set), so an
    # engine with no number there is "no_evidence" rather than judged on another set
    hev = _usable(evidence.get(hint_set, {}), floors, cands) if hint_set else ev
    read_cells = [hev[e] for e in dec.read if e in hev]
    recalls = [c["recall_lenient"] for c in read_cells if c.get("recall_lenient") is not None]
    if not read_cells:
        dec.hint = "no_evidence"
    elif recalls and max(recalls) < WATCH_BELOW:
        dec.hint = "weak"
    return dec


def provisional_reasons(dec: Decision, evidence: dict, sets: list | None = None) -> list:
    """The parts of the evidence bar that fail. Empty only for a gold set at the bar. Where a gold set has a
    number for the type, spans and documents are counted on it (the bar is the gold set's), else on the set
    the type's evidence comes from."""
    if dec.rung == "gold":
        return []
    reasons = ["not_gold"]
    gold_ids = [s["id"] for s in (sets or []) if s.get("kind") == "gold" and evidence.get(s["id"])]
    where = gold_ids[0] if gold_ids else dec.evidence_set
    cells = evidence.get(where, {}).values()
    spans = max((c["spans"] for c in cells), default=0)
    if spans < SPAN_BAR:
        reasons.append("spans")
    docs = [c.get("docs") for c in cells]
    if not docs or any(d is None for d in docs) or max(docs) < GOLD_MIN_DOCS:
        reasons.append("docs")
    reasons.append("genres")
    return reasons
