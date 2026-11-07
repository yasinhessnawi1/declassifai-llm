"""Builds the provisional routing table from the recorded numbers (no model run).

Usage: python -m eval.routing.build_provisional [out_path]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .table import HERE, build_table, check_table_structure, load_floors, write_table
from .taxonomy import check_pin, load_taxonomy

VERSION = "2026-11-07.3"
BUILT = "2026-11-07"
NOTE = ("Provisional: built from numbers already measured (engine research note sections 4.2 and 4.3), "
        "no new run. Every type is provisional. The taxonomy is the one merged in the detection service, see taxonomy_pin.json.")


def main(argv: list) -> int:
    out = Path(argv[1]) if len(argv) > 1 else HERE / "routing_table.json"
    check_pin()
    tax = load_taxonomy()
    evidence = json.loads((HERE / "data" / "engine_evidence.json").read_text(encoding="utf-8"))
    floors = load_floors()
    table = build_table(tax, evidence, floors, version=VERSION, built=BUILT, note=NOTE)
    problems = check_table_structure(table, tax, floors)
    if problems:
        print("\n".join(problems))
        return 1
    write_table(table, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
