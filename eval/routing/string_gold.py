"""The string-level gold format and its checks.

A string-level gold set is one JSON line per document: `{"id", "text_input", "output": {TYPE: [strings]},
"review": {"status": ...}}`, the shape of the synthetic sets and the held-out gold set. It has no offsets: a
string marks every place it occurs, and it is scored at the string level (distinct strings per document and
type, see string_score.py). Span-level scoring needs the offset format of gold.py.

Checks, run before every score:
  - every type is one of the 59; FIELD_LABEL (a training-only label) is dropped and counted;
  - every string occurs in its document's text;
  - the text is NFC with "\\n" line ends;
  - ids are unique, strings are non-empty, and only reviewed documents are scored.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .taxonomy import load_taxonomy

DROPPED_TYPES = {"FIELD_LABEL"}


@dataclass
class StringGold:
    docs: dict = field(default_factory=dict)  # id -> {"text": str, "output": {type: [distinct strings]}}
    errors: list = field(default_factory=list)
    dropped: dict = field(default_factory=dict)  # type -> strings dropped
    not_reviewed: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")


def check_rows(rows: list, type_ids: set) -> StringGold:
    gold = StringGold()
    for n, row in enumerate(rows, 1):
        doc = row.get("id")
        where = f"line {n}" if not isinstance(doc, str) else doc
        if not isinstance(doc, str) or not doc:
            gold.err(where, "id is required")
            continue
        if doc in gold.docs:
            gold.err(where, "duplicate id")
            continue
        text = row.get("text_input")
        if not isinstance(text, str) or not text:
            gold.err(where, "text_input is required")
            continue
        if "\r" in text or unicodedata.normalize("NFC", text) != text:
            gold.err(where, "text must be NFC with \\n line ends")
        if (row.get("review") or {}).get("status") != "reviewed":
            gold.not_reviewed += 1
            continue
        output = row.get("output")
        if not isinstance(output, dict):
            gold.err(where, "output must be an object of type -> strings")
            continue
        kept = {}
        for t, strings in output.items():
            if t in DROPPED_TYPES:
                gold.dropped[t] = gold.dropped.get(t, 0) + len(strings or [])
                continue
            if t not in type_ids:
                gold.err(where, f"type {t!r} is not one of the 59")
                continue
            if not isinstance(strings, list):
                gold.err(where, f"{t}: strings must be a list")
                continue
            for s in strings:
                if not isinstance(s, str) or not s:
                    gold.err(where, f"{t}: empty or non-string value")
                elif s not in text:
                    gold.err(where, f"{t}: a string does not occur in the text")
            kept[t] = list(dict.fromkeys(s for s in strings if isinstance(s, str) and s))
        gold.docs[doc] = {"text": text, "output": kept}
    return gold


def load_string_gold(path: Path) -> StringGold:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return check_rows(rows, set(load_taxonomy().ids))


def main(argv: list) -> int:
    gold = load_string_gold(Path(argv[1]))
    for e in gold.errors:
        print(e)
    spans = sum(len(v) for d in gold.docs.values() for v in d["output"].values())
    print(f"{len(gold.docs)} documents, {spans} strings; dropped {gold.dropped}; not reviewed {gold.not_reviewed}; "
          f"{'OK' if gold.ok else f'{len(gold.errors)} errors'}")
    return 0 if gold.ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
