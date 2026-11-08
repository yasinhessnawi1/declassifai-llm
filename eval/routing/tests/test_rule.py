import copy
import json
from collections import Counter

import pytest

from eval.routing.rule import decide, provisional_reasons
from eval.routing.table import HERE, load_floors
from eval.routing.taxonomy import ENGINES, load_taxonomy

TAX = load_taxonomy()
EV = json.loads((HERE / "data" / "engine_evidence.json").read_text(encoding="utf-8"))
FLOORS = load_floors()["floors"]
ALL = list(ENGINES)


def full(tid, evidence=None, sets=None, enabled=ALL):
    ev = EV["cells"].get(tid, {}) if evidence is None else evidence
    return decide(TAX, tid, ev, sets or EV["sets"], FLOORS, enabled)


def cell(f1l, f1e=None, rl=None, spans=100, docs=20, floor=None, re_=None):
    return {"f1_lenient": f1l, "f1_exact": f1l if f1e is None else f1e, "recall_lenient": rl,
            "recall_exact": re_, "spans": spans, "docs": docs, "floor": floor}


def test_reproduces_the_recorded_picks():
    decs = {t: full(t) for t in TAX.ids}
    assert Counter(d.primary for d in decs.values()) == {"tagger": 53, "gliner": 6}
    assert sorted(t for t, d in decs.items() if d.second) == ["DATE_TIME", "EMPLOYMENT", "ORGANIZATION", "PERSON"]
    assert {t for t, d in decs.items() if d.primary == "gliner"} == {
        "SOCIAL_MEDIA", "URL", "DATE_TIME", "EMPLOYMENT", "ORGANIZATION", "PERSON"}
    assert Counter(d.rung for d in decs.values()) == {"default": 39, "bench": 13, "real": 7}
    assert all(d.second == "tagger" and d.second_reason == "sets_disagree" for d in decs.values() if d.second)


def test_every_type_is_provisional_without_a_gold_set():
    for t in TAX.ids:
        assert provisional_reasons(full(t), EV["cells"].get(t, {}))[0] == "not_gold"


def test_watch_list_holds_the_recorded_eleven():
    watch = {t for t in TAX.ids if full(t).watch}
    recorded = set(
        "FAX_NUMBER MILITARY_ID TAX_ID VISA_NUMBER MARITAL_STATUS BIOMETRIC_DATA DISABILITY "
        "IMMIGRATION_STATUS RELIGIOUS_BELIEF".split()
    ) | {"PASS" + "WORD", "USER" + "NAME"}
    assert recorded <= watch
    assert watch - recorded == {"ORGANIZATION"}  # GLiNER's NorNE lenient recall 0.32; already reads two engines


def test_a_number_at_another_floor_is_not_evidence():
    ev = copy.deepcopy(EV["cells"]["PERSON"])
    ev["norne_test"]["gliner"]["floor"] = 0.8
    d = full("PERSON", ev)
    assert d.primary == "tagger" and d.rung == "real"  # only the tagger has a usable real number


def test_ties_go_to_the_cheapest_engine():
    ev = {"s": {"tagger": cell(0.80), "gliner": cell(0.83, floor=0.5), "gpt-4o": cell(0.90, floor=0.5)}}
    sets = [{"id": "s", "kind": "real"}]
    assert full("PERSON", ev, sets).primary == "gpt-4o"  # 0.10 ahead is not a tie
    ev["s"]["gpt-4o"] = cell(0.82, floor=0.5)
    assert full("PERSON", ev, sets).primary == "tagger"  # all within 0.03 of the best


def test_second_engine_rules_a_and_b():
    sets = [{"id": "s", "kind": "real"}]
    a = {"s": {"tagger": cell(0.90, rl=0.70), "gliner": cell(0.80, rl=0.85, floor=0.5)}}
    d = full("PERSON", a, sets)
    assert (d.primary, d.second, d.second_reason) == ("tagger", "gliner", "recall")
    b = {"s": {"tagger": cell(0.90, f1e=0.80, rl=0.92), "gliner": cell(0.88, f1e=0.70, rl=0.91, floor=0.5)}}
    d = full("PERSON", b, sets)
    assert (d.second, d.second_reason) == ("gliner", "runner_up")
    b["s"]["tagger"] = cell(0.97, f1e=0.97, rl=0.97)  # at 0.95 on F1 and recall: no second
    b["s"]["gliner"] = cell(0.96, f1e=0.96, rl=0.97, floor=0.5)
    assert full("PERSON", b, sets).second is None


def test_bench_never_decides_against_a_real_set():
    sets = [{"id": "r", "kind": "real"}, {"id": "b", "kind": "synthetic_weak"}]
    ev = {"r": {"tagger": cell(0.4, spans=60), "gliner": cell(0.8, spans=60, floor=0.5)},
          "b": {"tagger": cell(0.99, spans=60), "gliner": cell(0.5, spans=60, floor=0.5)}}
    d = full("PERSON", ev, sets)
    assert (d.rung, d.primary, d.second) == ("real", "gliner", "tagger")


def test_evidence_ladder_thresholds():
    sets = [{"id": "r", "kind": "real"}, {"id": "b", "kind": "synthetic_weak"}]
    # 49 real spans do not decide; 30 bench spans do
    ev = {"r": {"tagger": cell(0.1, spans=49), "gliner": cell(0.9, spans=49, floor=0.5)},
          "b": {"tagger": cell(0.9, spans=30), "gliner": cell(0.1, spans=30, floor=0.5)}}
    assert (full("PERSON", ev, sets).rung, full("PERSON", ev, sets).primary) == ("bench", "tagger")
    ev["b"] = {"tagger": cell(0.9, spans=29), "gliner": cell(0.1, spans=29, floor=0.5)}
    d = full("PERSON", ev, sets)
    assert (d.rung, d.primary, d.deciding_set) == ("default", "tagger", None)


def test_gold_set_at_the_bar_decides_and_clears_provisional():
    sets = [{"id": "g", "kind": "gold"}, {"id": "r", "kind": "real"}]
    ev = {"g": {"tagger": cell(0.9, spans=30, docs=15), "gliner": cell(0.5, spans=30, docs=15, floor=0.5)},
          "r": {"tagger": cell(0.1, spans=900), "gliner": cell(0.9, spans=900, floor=0.5)}}
    d = full("PERSON", ev, sets)
    assert (d.rung, d.primary) == ("gold", "tagger")
    assert provisional_reasons(d, ev) == []
    ev["g"]["tagger"]["docs"] = 14  # under the document bar: only a real set with 50 spans
    ev["g"]["gliner"]["docs"] = 14
    ev["g"]["tagger"]["spans"] = ev["g"]["gliner"]["spans"] = 60
    d = full("PERSON", ev, sets)
    assert d.rung == "real" and provisional_reasons(d, ev)[0] == "not_gold"


def test_default_is_the_tagger_else_the_cheapest_with_a_label():
    assert full("CRYPTO").primary == "tagger"
    assert full("CRYPTO", enabled=["gliner", "gpt-4o"]).primary == "gliner"
    assert full("CRYPTO", enabled=["gpt-4o"]).primary == "gpt-4o"


def test_gaps_and_shared_labels():
    assert full("FIREARMS_LICENSE", enabled=["gliner", "gpt-4o"]).candidates == []
    assert full("VESSEL_REGISTRATION", enabled=["gliner", "gpt-4o"]).candidates == ["gliner"]  # shared plate labels
    assert full("VESSEL_REGISTRATION", enabled=["tagger", "gliner"]).candidates == ["tagger"]  # shared label only as last resort
    assert full("VESSEL_REGISTRATION", enabled=["gpt-4o"]).candidates == []


def test_single_engine_reads_what_it_has_a_label_for():
    d = full("PERSON", enabled=["gpt-4o"])
    assert d.read == ["gpt-4o"] and d.second is None


def test_bench_plays_no_part_at_the_gold_rung():
    sets = [{"id": "g", "kind": "gold"}, {"id": "r", "kind": "real"}, {"id": "b", "kind": "synthetic_weak"}]
    ev = {"g": {"tagger": cell(0.96, rl=0.96, spans=40, docs=20), "gliner": cell(0.5, rl=0.5, spans=40, docs=20, floor=0.5)},
          "b": {"tagger": cell(0.2, spans=60), "gliner": cell(0.9, spans=60, floor=0.5)}}
    d = full("PERSON", ev, sets)
    assert (d.rung, d.primary, d.second, d.second_reason) == ("gold", "tagger", None, None)
    # below the gold rung the same disagreement still adds the second engine
    ev["g"] = {"tagger": cell(0.96, rl=0.96, spans=60, docs=14), "gliner": cell(0.5, rl=0.5, spans=60, docs=14, floor=0.5)}
    d = full("PERSON", ev, sets)
    assert (d.rung, d.primary, d.second, d.second_reason) == ("real", "tagger", "gliner", "sets_disagree")


def test_provisional_reasons_count_on_the_gold_set_where_it_has_a_number():
    sets = [{"id": "g", "kind": "gold"}, {"id": "r", "kind": "real"}]
    ev = {"g": {"tagger": cell(0.9, spans=12, docs=5), "gliner": cell(0.5, spans=12, docs=5, floor=0.5)},
          "r": {"tagger": cell(0.1, spans=900, docs=300), "gliner": cell(0.9, spans=900, docs=300, floor=0.5)}}
    d = full("PERSON", ev, sets)
    assert d.deciding_set == "r"
    assert provisional_reasons(d, ev, sets) == ["not_gold", "spans", "docs", "genres"]
    assert provisional_reasons(d, ev) == ["not_gold", "genres"]  # without the gold set: counted on the deciding set


def test_rule_5d_reads_the_top_two_when_their_union_finds_clearly_more():
    sets = [{"id": "g", "kind": "gold"}]
    ev = {"g": {"tagger": cell(0.70, f1e=0.55, rl=0.69, spans=160, docs=100),
                "gliner": cell(0.54, f1e=0.42, rl=0.53, spans=160, docs=100, floor=0.5)}}
    unions = {"g": {"tagger+gliner": {"f1_lenient": 0.66, "recall_lenient": 0.74}}}
    d = decide(TAX, "EMPLOYMENT", ev, sets, FLOORS, ["tagger", "gliner"], unions=unions)
    assert (d.primary, d.second, d.second_reason) == ("tagger", "gliner", "union")
    unions["g"]["tagger+gliner"] = {"f1_lenient": 0.64, "recall_lenient": 0.74}  # F1 falls 0.06: too much
    assert decide(TAX, "EMPLOYMENT", ev, sets, FLOORS, ["tagger", "gliner"], unions=unions).second is None
    unions["g"]["tagger+gliner"] = {"f1_lenient": 0.69, "recall_lenient": 0.71}  # recall gains only 0.02
    assert decide(TAX, "EMPLOYMENT", ev, sets, FLOORS, ["tagger", "gliner"], unions=unions).second is None
    assert decide(TAX, "EMPLOYMENT", ev, sets, FLOORS, ["tagger", "gliner"]).second is None  # no unions scored
