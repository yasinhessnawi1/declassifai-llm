"""The v2 type inventory and the legacy-to-v2 conversion, shared by the data tools.

`data/synthetic/taxonomy.json` (57 types) is the inventory; `docs/ANNOTATION_SPEC.md`
is the rulebook. The annotated sets already live in v2 (`data/gold_v2/`,
`data/slice_v2/`, written by `tools/migrate_to_v2.py`). The raw Gemini corpus does
not: it is still keyed by the 17-type names, so anything that reads it converts
through `legacy_to_v2`, which applies the same renames and splits as the migration.
"""

from __future__ import annotations

import collections
import json
import os
from typing import Dict, List, Set, Tuple

import migrate_to_v2 as _mig

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAXONOMY_PATH = os.path.join(_ROOT, _mig.TAXONOMY)

# The 17 legacy names a corpus span must carry to be converted at all. Anything
# else (`CONTEXT_SENSITIVE`, `IDENTIFIABLE_IMAGE`, stray `AGE`/`ANIMAL_INFO` keys the
# labeller invented) is out of schema and dropped by the caller.
LEGACY_TYPES: Set[str] = set(_mig.RENAME) | set(_mig.SPLIT)

# The v2 types the corpus can be trusted for. These are the v2 images of the seven
# legacy types that score >=0.91 relaxed F1 against the gold set (docs/DATA_QUALITY.md).
# DATE_TIME splits into DATE_TIME and DATE_OF_BIRTH; both inherit its reliability.
# AGE is left out: the corpus almost never tagged a bare age, so an absent AGE span
# in a corpus document means "not annotated", not "no age".
CORPUS_TRUSTED: Set[str] = {
    "EMAIL", "PHONE", "PERSON", "POSTAL_CODE", "DATE_TIME", "DATE_OF_BIRTH",
    "SEXUAL_ORIENTATION", "ADDRESS",
}


# Every v2 type a legacy corpus label can turn into, minus AGE and RELIGIOUS_BELIEF.
# The corpus almost never tagged a bare age, and Gemini's schema had no religion type
# at all (0 spans), so a corpus document is not annotated for either even though the
# legacy schema can produce them.
CORPUS_ANNOTATED = {
    "PERSON", "ADDRESS", "POSTAL_CODE", "PHONE", "EMAIL", "CRIMINAL", "POLITICAL",
    "ECONOMIC_STATUS", "SEXUAL_ORIENTATION", "BEHAVIORAL_PATTERN",
    "NATIONAL_ID", "ORG_NUMBER", "CASE_NUMBER", "DRIVER_LICENSE", "PASSPORT",
    "IDENTITY_CARD", "VISA_NUMBER", "MILITARY_ID", "MEDICAL_LICENSE", "TAX_ID",
    "LICENSE_PLATE", "FIREARMS_LICENSE", "VESSEL_REGISTRATION", "FINANCIAL", "IBAN", "CREDIT_CARD", "BANK_ACCOUNT", "CRYPTO",
    "HEALTH", "DISABILITY", "MEDICATION", "DATE_TIME", "DATE_OF_BIRTH", "EMPLOYMENT",
    "ORGANIZATION", "FAMILY_RELATION", "MARITAL_STATUS",
}


def v2_types(path: str = TAXONOMY_PATH) -> List[str]:
    """Return the v2 type names in taxonomy order."""
    with open(path, encoding="utf-8") as fh:
        return [t["name"] for t in json.load(fh)["types"]]


def legacy_to_v2(output: Dict[str, List[str]], text: str,
                 stats: collections.Counter | None = None) -> Dict[str, List[str]]:
    """Convert one record's 17-type output to v2 names, splitting where v2 does.

    Spans the migration cannot place (`UNRESOLVED`) or that v2 has no type for
    (firearms and vessel registrations) are dropped and counted.

    Args:
        output: `{legacy type: [spans]}`; keys outside LEGACY_TYPES are ignored.
        text: The document, which the split rules read for context.
        stats: Optional counter for dropped spans.

    Returns:
        `{v2 type: [distinct spans]}`.
    """
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for legacy, spans in output.items():
        if legacy not in LEGACY_TYPES:
            continue
        for span in spans:
            if legacy in _mig.RENAME:
                new = _mig.RENAME[legacy]
            else:
                new = _mig.SPLIT[legacy](span, text)
            if new == _mig.UNRESOLVED or new.startswith(_mig.NO_V2_HOME):
                if stats is not None:
                    stats[f"spans_dropped_{'no_v2_home' if new != _mig.UNRESOLVED else 'unresolved'}"] += 1
                continue
            if span not in out[new]:
                out[new].append(span)
    return dict(out)
