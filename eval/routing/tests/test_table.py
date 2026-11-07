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
