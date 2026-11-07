"""One case per validator rule. All documents here are synthetic."""
import copy
import hashlib
import json

import pytest

from eval.routing.gold import validate_gold
from eval.routing.taxonomy import load_taxonomy

TEXT = "Kari Hansen bor i Oslo.\nHansen ringer 12345678.\n"


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def label(text=TEXT, **over):
    base = {
        "doc_id": "g0001", "text_sha256": sha(text), "genre": "case_file", "language": "nb",
        "source": "handwritten", "hard_negative": False,
        "pages": [{"page": 1, "start": 0, "end": len(text)}],
        "spans": [
            {"start": 0, "end": 11, "type": "PERSON", "planted": False},
            {"start": 24, "end": 30, "type": "PERSON", "planted": False, "note": "lone surname"},
            {"start": 38, "end": 46, "type": "PHONE", "planted": False},
        ],
        "review": {"prelabel_model": "m", "reviewed_by": "x", "reviewed_at": "2026-11-20", "status": "reviewed"},
    }
    base.update(over)
    return base


def write(root, lab=None, text=TEXT, manifest=None, documents=1):
    lab = lab or label(text)
    (root / "documents").mkdir(exist_ok=True)
    (root / "documents" / f"{lab['doc_id']}.txt").write_bytes(text.encode("utf-8"))
    m = {"set_id": "gold_real", "version": "1", "taxonomy_version": load_taxonomy().version,
         "labelling_rules": "rules", "created": "2026-11-20", "documents": documents}
    m.update(manifest or {})
    (root / "manifest.json").write_text(json.dumps(m))
    (root / "labels.jsonl").write_text(json.dumps(lab) + "\n")
    return root


def errors(root):
    return validate_gold(root).errors


def test_valid_set_passes(tmp_path):
    rep = validate_gold(write(tmp_path))
    assert rep.ok, rep.errors
    assert (rep.documents, rep.reviewed) == (1, 1)


def test_text_slice_matches_offsets():
    assert TEXT[24:30] == "Hansen" and TEXT[38:46] == "12345678" and TEXT[0:11] == "Kari Hansen"


def mutate_spans(fn):
    lab = label()
    fn(lab["spans"])
    return lab


@pytest.mark.parametrize("name,lab,needle", [
    ("unknown type", mutate_spans(lambda s: s[0].update(type="PERSON_S")), "not one of the 59"),
    ("hash", label(text_sha256="0" * 64), "hash"),
    ("start negative", mutate_spans(lambda s: s[0].update(start=-1)), "start < end"),
    ("start == end", mutate_spans(lambda s: s[0].update(start=5, end=5)), "start < end"),
    ("end past text", mutate_spans(lambda s: s[0].update(end=len(TEXT) + 1)), "start < end"),
    ("starts on whitespace", mutate_spans(lambda s: s[0].update(start=4, end=11)), "whitespace"),
    ("ends on whitespace", mutate_spans(lambda s: s[0].update(end=5)), "whitespace"),
    ("same type overlap", mutate_spans(lambda s: s[1].update(start=5, end=11)), "overlap"),
    ("gap in pages", label(pages=[{"page": 1, "start": 0, "end": 10}, {"page": 2, "start": 12, "end": len(TEXT)}]), "gap"),
    ("pages stop early", label(pages=[{"page": 1, "start": 0, "end": 10}]), "text length"),
    ("pages start late", label(pages=[{"page": 1, "start": 3, "end": len(TEXT)}]), "gap"),
    ("hard negative with spans", label(hard_negative=True), "hard negative"),
    ("bad genre", label(genre="novel"), "genre"),
    ("bad source", label(source="scraped"), "source"),
    ("bad status", label(review={"status": "done"}), "review.status"),
    ("planted missing", mutate_spans(lambda s: s[0].pop("planted")), "planted"),
])
def test_rule_is_refused(tmp_path, name, lab, needle):
    errs = errors(write(tmp_path, lab))
    assert any(needle in e for e in errs), (name, errs)


def test_nested_spans_of_different_types_are_allowed(tmp_path):
    text = "Storgata 5, 0182 Oslo\n"
    lab = label(text, spans=[
        {"start": 0, "end": 21, "type": "ADDRESS", "planted": False},
        {"start": 12, "end": 16, "type": "POSTAL_CODE", "planted": False}])
    assert errors(write(tmp_path, lab, text=text)) == []


def test_hard_negative_without_spans_passes(tmp_path):
    assert errors(write(tmp_path, label(hard_negative=True, spans=[]))) == []


def test_offsets_are_code_points_not_utf16(tmp_path):
    text = "\U0001F600 Kari Hansen\n"  # one code point, two UTF-16 units
    lab = label(text, spans=[{"start": 2, "end": 13, "type": "PERSON", "planted": False}])
    assert errors(write(tmp_path, lab, text=text)) == []
    lab["spans"][0].update(start=3, end=14)  # what a UTF-16 tool would write
    assert errors(write(tmp_path, lab, text=text))


def test_text_must_be_nfc_with_lf(tmp_path):
    text = "Kari\r\nHansen\n"
    assert any("NFC" in e for e in errors(write(tmp_path, label(text, spans=[]), text=text)))
    text = "Ola\u030a\n"  # decomposed a + ring
    assert any("NFC" in e for e in errors(write(tmp_path, label(text, spans=[]), text=text)))


def test_manifest_checks(tmp_path):
    assert any("documents is 5" in e for e in errors(write(tmp_path, documents=5)))
    assert any("taxonomy_version" in e for e in errors(write(tmp_path, manifest={"taxonomy_version": "9.9.9"})))


def test_duplicate_and_missing_document(tmp_path):
    root = write(tmp_path)
    line = (root / "labels.jsonl").read_text()
    (root / "labels.jsonl").write_text(line + line)
    assert any("duplicate" in e for e in errors(root))
    (root / "documents" / "g0001.txt").unlink()
    (root / "labels.jsonl").write_text(line)
    assert any("cannot read document" in e for e in errors(root))


def test_prelabelled_is_counted_but_not_reviewed(tmp_path):
    lab = label()
    lab["review"]["status"] = "prelabelled"
    rep = validate_gold(write(tmp_path, lab))
    assert rep.ok and (rep.documents, rep.reviewed) == (1, 0)


def test_example_in_the_format_doc_validates(tmp_path):
    import re
    from pathlib import Path
    doc = (Path(__file__).parents[3] / "GOLD_SET_FORMAT.md").read_text(encoding="utf-8")

    def block(name):
        return re.search(rf"```{name}\n(.*?)\n```", doc, re.S).group(1)

    text = block("example-document") + "\n"
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "g0001.txt").write_text(text, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(block("example-manifest"))
    (tmp_path / "labels.jsonl").write_text(json.dumps(json.loads(block("example-label"))) + "\n")
    assert validate_gold(tmp_path).errors == []
    assert len(text) == 86
