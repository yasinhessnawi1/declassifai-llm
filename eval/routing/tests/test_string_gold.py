from eval.routing.score_gold import gate
from eval.routing.string_gold import check_rows
from eval.routing.string_score import boxes_at, match_lenient, score, strings_of
from eval.routing.taxonomy import load_taxonomy

TAX = load_taxonomy()
IDS = set(TAX.ids)
TIERS = {t: i.tier for t, i in TAX.types.items()}
TEXT = "Brev til Kari Nordmann om saken.\nKari ringte 12.03.2025."


def row(output, text=TEXT, status="reviewed", doc="D-1"):
    return {"id": doc, "text_input": text, "output": output, "review": {"status": status}}


def test_a_clean_row_passes_and_field_label_is_dropped():
    g = check_rows([row({"PERSON": ["Kari Nordmann", "Kari"], "FIELD_LABEL": ["Brev"]})], IDS)
    assert g.ok and g.dropped == {"FIELD_LABEL": 1}
    assert g.docs["D-1"]["output"] == {"PERSON": ["Kari Nordmann", "Kari"]}


def test_each_check_fails_on_its_own():
    assert not check_rows([row({"NOT_A_TYPE": ["Kari"]})], IDS).ok
    assert not check_rows([row({"PERSON": ["Ola"]})], IDS).ok  # not in the text
    assert not check_rows([row({"PERSON": [""]})], IDS).ok
    assert not check_rows([row({"PERSON": ["Kari"]}, text="Kari\r\n")], IDS).ok
    assert not check_rows([row({"PERSON": ["Kari"]}, text="Kári")], IDS).ok  # not NFC
    assert not check_rows([row({}), row({})], IDS).ok  # duplicate id


def test_only_reviewed_documents_are_scored():
    g = check_rows([row({"PERSON": ["Kari"]}, status="prelabelled")], IDS)
    assert g.ok and g.docs == {} and g.not_reviewed == 1


def test_lenient_is_containment_either_way_and_each_string_counts_once():
    assert match_lenient(["Kari Nordmann"], ["kari nordmann"]) == 1
    assert match_lenient(["Kari Nordmann"], ["Kari"]) == 1
    assert match_lenient(["Kari"], ["Brev til Kari Nordmann"]) == 1
    assert match_lenient(["Kari", "Kari Nordmann"], ["Kari Nordmann"]) == 1  # one prediction, matched once


def test_strings_come_from_the_documents_own_text_and_join_only_overlaps():
    s = TEXT.index("Kari Nordmann")
    boxes = [{"category": "PERSON", "start": s, "end": s + 4}, {"category": "PERSON", "start": s + 5, "end": s + 13},
             {"category": "PERSON", "start": s + 2, "end": s + 7}, {"category": None, "start": 0, "end": 4}]
    assert strings_of(boxes, TEXT) == {"PERSON": ["Kari Nordmann"]}
    apart = [{"category": "PERSON", "start": s, "end": s + 4}, {"category": "PERSON", "start": s + 5, "end": s + 13}]
    assert strings_of(apart, TEXT) == {"PERSON": ["Kari", "Nordmann"]}  # touching boxes stay two findings


def test_score_counts_per_type_and_overall():
    gold = {"D-1": {"text": TEXT, "output": {"PERSON": ["Kari Nordmann", "Kari"], "DATE_TIME": ["12.03.2025"]}}}
    preds = {"D-1": {"PERSON": ["Kari Nordmann"], "EMAIL": ["x"]}}
    sc = score(gold, preds, TAX.ids, TIERS)
    p = sc["per_type"]["PERSON"]
    assert (p["spans"], p["docs"], p["predicted"]) == (2, 1, 1)
    assert p["recall_exact"] == 0.5 and p["recall_lenient"] == 0.5 and p["precision_exact"] == 1.0
    assert sc["per_type"]["DATE_TIME"]["recall_lenient"] == 0.0
    assert sc["per_type"]["EMAIL"]["precision_lenient"] == 0.0 and sc["per_type"]["EMAIL"]["spans"] == 0
    assert sc["overall"]["ALL"]["spans"] == 3 and sc["overall"]["ALL"]["predicted"] == 2


def test_offline_floors_remove_and_add_back():
    doc = {"items": [{"category": "PERSON", "start": 0, "end": 4, "engines": ["standard"], "engine_scores": {"standard": 0.55}},
                     {"category": "PHONE", "start": 5, "end": 9, "engines": ["standard", "rules"], "engine_scores": {"standard": 0.51}},
                     {"category": "EMAIL", "start": 10, "end": 12, "engines": ["fast"], "engine_scores": {"fast": 1.0}}],
           "under_floor": [{"category": "PERSON", "start": 20, "end": 24, "score": 0.35, "model": "gliner", "engines": ["standard"]}]}
    floors = {"tagger": None, "gliner": 0.5, "gpt-4o": 0.5}
    assert len(boxes_at(doc)) == 3 and len(boxes_at(doc, floors)) == 3
    raised = boxes_at(doc, {**floors, "gliner": 0.6})
    assert [b["category"] for b in raised] == ["PHONE", "EMAIL"]  # a rule box stands at any floor
    lowered = boxes_at(doc, {**floors, "gliner": 0.3})
    assert len(lowered) == 4 and lowered[-1]["start"] == 20


def _sc(recalls):
    return {"per_type": {t: {"recall_lenient": recalls.get(t, 0.0), "spans": 10 if t in recalls else 0} for t in TAX.ids}}


def test_gate_fails_a_type_that_loses_more_than_three_points_against_the_best_single_engine():
    single = {"fast": _sc({"PERSON": 0.80, "EMAIL": 1.0}), "standard": _sc({"PERSON": 0.90, "EMAIL": 0.5}),
              "advanced": _sc({"PERSON": 0.95})}
    g = gate(single, {"fast+standard": _sc({"PERSON": 0.87, "EMAIL": 1.0})}, TAX.ids)
    assert g["fast+standard"]["pass"]  # 0.03 under GLiNER's 0.90 is inside the margin
    g = gate(single, {"fast+standard": _sc({"PERSON": 0.86, "EMAIL": 1.0})}, TAX.ids)
    assert [f["type"] for f in g["fast+standard"]["fails"]] == ["PERSON"]
