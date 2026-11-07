"""Gold-set file format and its validator. See GOLD_SET_FORMAT.md at the repo root."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .taxonomy import load_taxonomy

GENRES = {
    "case_file", "letter_public_body", "medical_welfare", "hr_employment", "table", "form",
    "scanned_ocr", "email_thread", "invoice", "cv", "news", "other",
}
SOURCES = {"handwritten", "consent", "public_layout", "generated_planted"}
STATUSES = {"prelabelled", "reviewed"}
_DOC_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class Report:
    errors: list = field(default_factory=list)
    documents: int = 0
    reviewed: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_document(label: dict, text: str, type_ids: set, rep: Report) -> None:
    doc = label.get("doc_id", "?")
    n = len(text)  # code points
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != label.get("text_sha256"):
        rep.err(doc, "text hash does not match")
    if "\r" in text or unicodedata.normalize("NFC", text) != text:
        rep.err(doc, "text must be NFC with \\n line ends")
    for key, allowed in (("genre", GENRES), ("source", SOURCES)):
        if label.get(key) not in allowed:
            rep.err(doc, f"{key} {label.get(key)!r} is not one of {sorted(allowed)}")
    if not isinstance(label.get("language"), str) or not label["language"]:
        rep.err(doc, "language is required")
    if not isinstance(label.get("hard_negative"), bool):
        rep.err(doc, "hard_negative must be true or false")
    review = label.get("review")
    if not isinstance(review, dict) or review.get("status") not in STATUSES:
        rep.err(doc, f"review.status must be one of {sorted(STATUSES)}")

    # pages cover the text without gaps or overlaps
    pages = label.get("pages")
    if not isinstance(pages, list) or not pages:
        rep.err(doc, "pages is required")
    else:
        pos = 0
        for i, p in enumerate(pages):
            s, e = p.get("start"), p.get("end")
            if not (_is_int(s) and _is_int(e)) or s >= e:
                rep.err(doc, f"page {i + 1}: bad start/end")
                break
            if p.get("page") != i + 1:
                rep.err(doc, f"page {i + 1}: page numbers must run 1, 2, 3, ...")
            if s != pos:
                rep.err(doc, f"pages leave a gap or overlap at offset {pos}")
                break
            pos = e
        else:
            if pos != n:
                rep.err(doc, f"pages end at {pos}, text length is {n}")

    spans = label.get("spans")
    if not isinstance(spans, list):
        rep.err(doc, "spans must be a list")
        return
    if label.get("hard_negative") is True and spans:
        rep.err(doc, "a hard negative has no spans")
    by_type: dict = {}
    for i, sp in enumerate(spans):
        where = f"{doc} span {i}"
        s, e, t = sp.get("start"), sp.get("end"), sp.get("type")
        if t not in type_ids:
            rep.err(where, f"type {t!r} is not one of the 59")
        if not isinstance(sp.get("planted"), bool):
            rep.err(where, "planted must be true or false")
        if not (_is_int(s) and _is_int(e)) or not (0 <= s < e <= n):
            rep.err(where, f"need 0 <= start < end <= {n}")
            continue
        if text[s].isspace() or text[e - 1].isspace():
            rep.err(where, "span starts or ends on whitespace")
        by_type.setdefault(t, []).append((s, e, i))
    for t, items in by_type.items():
        items.sort()
        for (s1, e1, i1), (s2, e2, i2) in zip(items, items[1:]):
            if s2 < e1:
                rep.err(doc, f"spans {i1} and {i2} of type {t} overlap")


def validate_gold(root: Path) -> Report:
    """Validates a gold-set directory. Run before every score."""
    root = Path(root)
    rep = Report()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        rep.err("manifest.json", f"cannot read: {ex}")
        return rep
    tax = load_taxonomy()
    if manifest.get("taxonomy_version") != tax.version:
        rep.err("manifest.json", f"taxonomy_version {manifest.get('taxonomy_version')!r}, expected {tax.version!r}")
    for key in ("set_id", "version", "labelling_rules", "created"):
        if not manifest.get(key):
            rep.err("manifest.json", f"{key} is required")
    type_ids = set(tax.ids)
    seen = set()
    try:
        lines = (root / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError as ex:
        rep.err("labels.jsonl", f"cannot read: {ex}")
        return rep
    for ln, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            label = json.loads(line)
        except ValueError:
            rep.err(f"labels.jsonl line {ln}", "not valid JSON")
            continue
        doc = label.get("doc_id")
        if not isinstance(doc, str) or not _DOC_ID.match(doc):
            rep.err(f"labels.jsonl line {ln}", "doc_id missing or has characters outside A-Z a-z 0-9 _ -")
            continue
        if doc in seen:
            rep.err(doc, "duplicate doc_id")
            continue
        seen.add(doc)
        rep.documents += 1
        try:
            raw = (root / "documents" / f"{doc}.txt").read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as ex:
            rep.err(doc, f"cannot read document: {ex}")
            continue
        check_document(label, text, type_ids, rep)
        if (label.get("review") or {}).get("status") == "reviewed":
            rep.reviewed += 1
    if manifest.get("documents") != rep.documents:
        rep.err("manifest.json", f"documents is {manifest.get('documents')}, labels.jsonl has {rep.documents}")
    return rep
