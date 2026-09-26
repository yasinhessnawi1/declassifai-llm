"""Automated crude scoring of screening outputs (docs/MODEL_SELECTION.md measurements).

For every raw/<slug>/<prompt_id>.txt this computes, per docs/SYNTHETIC_DATA_SPEC.md SS3
and the task's screening protocol:
  (a) verbatim-inclusion rate of planned values/clauses (exact substring check)
  (b) marker-discipline rate for the marked-generation prompts
  (c) crude English-leakage / placeholder / instruction-echo flags

This is a screen, not a verdict: read the flagged files before concluding anything
(SYNTHETIC_DATA_SPEC.md SS8's "a keyword count is not evidence" rule applies here too).

Usage:
    myenv/bin/python score_outputs.py [--slug SLUG ...]   # default: all slugs under raw/
Writes data/synthetic/screening/logs/<slug>_score.json and prints a summary table.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prompts import PROMPTS

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
LOG_DIR = HERE / "logs"

PROMPTS_BY_ID = {p["id"]: p for p in PROMPTS}

MARKER_RE = re.compile(r"⟦\s*([A-Z_]+)\s*:\s*(.*?)⟦", re.DOTALL)

ENGLISH_TELLS = [
    r"\bthe\b", r"\bwith\b", r"\band\b", r"\bplease\b", r"\bnote\b", r"\bhere is\b",
    r"\bI cannot\b", r"\bI can'?t\b", r"\bAs an AI\b", r"\bsure[,!]\b", r"\bcertainly\b",
    r"\bbelow is\b", r"\bhope this helps\b",
]
PLACEHOLDER_TELLS = [
    r"\[[A-Za-zæøåÆØÅ_ ]{2,30}\]", r"\bXXX+\b", r"\{[a-zA-Z_]+\}", r"<[a-zA-Z_ ]+>",
    r"\bLOREM\b", r"\bTODO\b", r"\bINSERT\b", r"\bPLACEHOLDER\b",
]
ECHO_TELLS = [
    "Bruk NØYAKTIG", "skal du SELV formulere", "skal du SJØLV formulere",
    "Her er en henvisning", "Her er ", "Basert på de gitt", "som du ba om",
    "based on the", "Instruction:", "System:",
]


def score_file(prompt, text):
    out = {"id": prompt["id"], "chars": len(text)}

    values = prompt.get("values", {})
    hits = {k: (v in text) for k, v in values.items()}
    out["values_total"] = len(values)
    out["values_hit"] = sum(hits.values())
    out["values_missing"] = [k for k, ok in hits.items() if not ok]
    out["value_rate"] = out["values_hit"] / out["values_total"] if values else None

    if prompt["marked"]:
        marker_types = prompt.get("marker_types", [])
        found = MARKER_RE.findall(text)
        out["markers_expected"] = len(marker_types)
        out["markers_found"] = len(found)
        type_ok = 0
        for i, mt in enumerate(marker_types):
            if i < len(found) and found[i][0].strip() == mt:
                type_ok += 1
        out["marker_type_match"] = type_ok
        out["marker_discipline_rate"] = (
            len(found) / len(marker_types) if marker_types else None
        )
        out["stray_marker_char"] = text.count("⟦") - 2 * len(found) != 0
        out["clauses_total"] = None
        out["clauses_hit"] = None
    else:
        clauses = prompt.get("clauses", [])
        chits = [c in text for c in clauses]
        out["clauses_total"] = len(clauses)
        out["clauses_hit"] = sum(chits)
        out["clauses_missing"] = [c for c, ok in zip(clauses, chits) if not ok]
        out["clause_rate"] = out["clauses_hit"] / out["clauses_total"] if clauses else None
        out["markers_expected"] = 0
        out["markers_found"] = text.count("⟦") // 2
        out["marker_discipline_rate"] = None

    out["english_hits"] = [p for p in ENGLISH_TELLS if re.search(p, text, re.IGNORECASE)]
    out["placeholder_hits"] = [p for p in PLACEHOLDER_TELLS if re.search(p, text)]
    out["echo_hits"] = [t for t in ECHO_TELLS if t.lower() in text.lower()]
    return out


def score_slug(slug):
    d = RAW_DIR / slug
    per_prompt = []
    for f in sorted(d.glob("*.txt")):
        pid = f.stem
        prompt = PROMPTS_BY_ID.get(pid)
        if prompt is None:
            continue
        text = f.read_text(encoding="utf-8")
        per_prompt.append(score_file(prompt, text))

    seeded = [r for r in per_prompt if r["clauses_total"] is not None]
    marked = [r for r in per_prompt if r["markers_expected"]]

    value_rates = [r["value_rate"] for r in per_prompt if r["value_rate"] is not None]
    clause_rates = [r["clause_rate"] for r in seeded if r["clause_rate"] is not None]
    marker_rates = [r["marker_discipline_rate"] for r in marked if r["marker_discipline_rate"] is not None]

    summary = {
        "slug": slug,
        "n_prompts": len(per_prompt),
        "mean_value_rate": sum(value_rates) / len(value_rates) if value_rates else None,
        "mean_clause_rate_seeded": sum(clause_rates) / len(clause_rates) if clause_rates else None,
        "mean_marker_discipline_rate": sum(marker_rates) / len(marker_rates) if marker_rates else None,
        "n_with_english_tell": sum(1 for r in per_prompt if r["english_hits"]),
        "n_with_placeholder": sum(1 for r in per_prompt if r["placeholder_hits"]),
        "n_with_echo": sum(1 for r in per_prompt if r["echo_hits"]),
        "per_prompt": per_prompt,
    }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", action="append", default=None)
    args = ap.parse_args()

    slugs = args.slug or sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir())
    print(f"{'slug':35s} {'value%':>8s} {'clause%':>8s} {'marker%':>8s} {'eng':>4s} {'plh':>4s} {'echo':>4s}")
    for slug in slugs:
        s = score_slug(slug)
        (LOG_DIR / f"{slug}_score.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        vr = f"{s['mean_value_rate']*100:.0f}" if s["mean_value_rate"] is not None else "-"
        cr = f"{s['mean_clause_rate_seeded']*100:.0f}" if s["mean_clause_rate_seeded"] is not None else "-"
        mr = f"{s['mean_marker_discipline_rate']*100:.0f}" if s["mean_marker_discipline_rate"] is not None else "-"
        print(f"{slug:35s} {vr:>8s} {cr:>8s} {mr:>8s} {s['n_with_english_tell']:>4d} "
              f"{s['n_with_placeholder']:>4d} {s['n_with_echo']:>4d}")


if __name__ == "__main__":
    main()
