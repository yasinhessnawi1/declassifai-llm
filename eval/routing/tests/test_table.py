import copy
import json

import pytest

from eval.routing.table import (HERE, build_table, check_table_structure, dumps, engine_sets, load_floors,
                                write_table)
from eval.routing.taxonomy import TaxonomyError, check_pin, load_taxonomy, git_blob_sha1
from eval.routing import build_provisional

TAX = load_taxonomy()
FLOORS = load_floors()
TABLE_PATH = HERE / "routing_table.json"


def committed():
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def test_taxonomy_counts_and_pin():
    assert len(TAX.ids) == 59
    assert [sum(1 for t in TAX.types.values() if t.tier == k) for k in "ABC"] == [30, 13, 16]
    assert check_pin()["blob_sha1"] == git_blob_sha1((HERE / "text_taxonomy.yaml").read_bytes())


def test_pin_refuses_a_changed_taxonomy(tmp_path):
    copy_ = tmp_path / "t.yaml"
    copy_.write_bytes((HERE / "text_taxonomy.yaml").read_bytes() + b"# edit\n")
    with pytest.raises(TaxonomyError):
        check_pin(copy_)


def test_seven_engine_sets():
    assert len(engine_sets()) == 7 and "fast+standard+advanced" in engine_sets()


def test_committed_table_equals_a_rebuild(tmp_path):
    out = tmp_path / "t.json"
    assert build_provisional.main(["x", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == TABLE_PATH.read_text(encoding="utf-8")


def test_table_passes_the_structure_check():
    assert check_table_structure(committed(), TAX, FLOORS) == []


def test_table_shape():
    t = committed()
    assert t["floors"] == {"tagger": None, "gliner": 0.5, "gpt-4o": 0.5} and t["floors_provisional"] == ["gpt-4o"]
    assert len(t["types"]) == 59 and all(v["provisional"] for v in t["types"].values())
    assert set(t["types"]["PERSON"]["routes"]) == set(engine_sets())
    r = t["types"]["PERSON"]["routes"]
    assert r["fast+standard+advanced"] == {"read": ["standard", "fast"], "fallback": ["advanced"], "hint": None}
    assert r["fast"]["hint"] == "weak" and r["advanced"]["hint"] == "no_evidence"
    assert t["types"]["FIREARMS_LICENSE"]["routes"]["standard"] == {"read": [], "fallback": [], "hint": "gap"}


def broken(fn):
    t = copy.deepcopy(committed())
    fn(t)
    return check_table_structure(t, TAX, FLOORS)


@pytest.mark.parametrize("name,fn,needle", [
    ("taxonomy version", lambda t: t.update(taxonomy_version="2.0.0"), "taxonomy_version"),
    ("floors", lambda t: t["floors"].update(gliner=0.6), "floors"),
    ("missing type", lambda t: t["types"].pop("PERSON"), "59"),
    ("missing set", lambda t: t["types"]["PERSON"]["routes"].pop("fast"), "7 engine sets"),
    ("engine not in set", lambda t: t["types"]["PERSON"]["routes"]["fast"]["read"].append("advanced"), "not in the set"),
    ("engine without label",
     lambda t: t["types"]["FIREARMS_LICENSE"]["routes"]["standard"].update(read=["standard"]), "no label"),
    ("both read and fallback", lambda t: t["types"]["PERSON"]["routes"]["fast+standard"].update(fallback=["fast"]), "both"),
    ("nothing reads a labelled type", lambda t: t["types"]["PERSON"]["routes"]["fast"].update(read=[]), "nothing reads"),
    ("bad hint", lambda t: t["types"]["PERSON"]["routes"]["fast"].update(hint="bad"), "hint"),
])
def test_structure_check_refuses(name, fn, needle):
    assert any(needle in p for p in broken(fn)), name


def test_writer_is_deterministic_and_round_trips(tmp_path):
    t = committed()
    write_table(t, tmp_path / "a.json")
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == t
    assert dumps(t) == dumps(copy.deepcopy(t))


def test_below_the_bar_a_route_never_reads_less_on_the_gold_set_than_the_baseline():
    from eval.routing.table import keep_baseline_recall

    unions = {"tagger": {"recall_lenient": 0.6}, "gliner": {"recall_lenient": 0.8}, "gpt-4o": {"recall_lenient": 0.7},
              "tagger+gliner": {"recall_lenient": 0.85}, "tagger+gpt-4o": {"recall_lenient": 0.75},
              "gliner+gpt-4o": {"recall_lenient": 0.9}, "tagger+gliner+gpt-4o": {"recall_lenient": 0.95}}
    read, fallback, added = keep_baseline_recall(["tagger"], ["gliner", "gpt-4o"], ["gliner"], unions)
    assert (read, fallback, added) == (["tagger", "gliner"], ["gpt-4o"], ["gliner"])
    # as good as the baseline already: unchanged
    assert keep_baseline_recall(["gliner"], ["tagger"], ["tagger"], unions) == (["gliner"], ["tagger"], [])
    # no gold number for the type: unchanged
    assert keep_baseline_recall(["tagger"], [], ["gliner"], {}) == (["tagger"], [], [])


def test_the_gate_looks_only_at_the_types_it_is_given():
    from eval.routing.score_gold import gate

    def sc(r):
        return {"per_type": {t: {"recall_lenient": r.get(t, 0.0), "spans": 10 if t in r else 0} for t in TAX.ids}}
    single = {"fast": sc({"PERSON": 0.9, "STUDENT_ID": 0.5}), "standard": sc({"PERSON": 0.9, "STUDENT_ID": 1.0})}
    routed = {"fast+standard": sc({"PERSON": 0.9, "STUDENT_ID": 0.5})}
    assert gate(single, routed, ["PERSON"])["fast+standard"]["pass"]
    assert not gate(single, routed, TAX.ids)["fast+standard"]["pass"]
