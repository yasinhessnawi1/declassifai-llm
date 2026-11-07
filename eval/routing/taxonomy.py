"""Loads the vendored text taxonomy and checks it against its pin."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).parent
TAXONOMY_PATH = HERE / "text_taxonomy.yaml"
PIN_PATH = HERE / "taxonomy_pin.json"

# Models (the columns of the routing table), cheapest first.
ENGINES = ("tagger", "gliner", "gpt-4o")
# Product engines, in the order route keys list them, and the model behind each by default.
PRODUCT_ENGINES = ("fast", "standard", "advanced")
DEFAULT_ENGINE_MODELS = {"fast": "tagger", "standard": "gliner", "advanced": "gpt-4o"}
_LABEL_KEY = {"tagger": "tagger", "gliner": "gliner", "gpt-4o": "advanced"}
TIER_COUNTS = {"A": 30, "B": 13, "C": 16}


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class TypeInfo:
    id: str
    tier: str
    rules: bool
    labels: dict  # model -> list of labels of its own (empty list = gap)
    shared: dict  # model -> list of type ids whose labels also serve those types


@dataclass(frozen=True)
class Taxonomy:
    version: str
    types: dict  # id -> TypeInfo, in file order

    @property
    def ids(self) -> list:
        return list(self.types)

    def has_own_label(self, type_id: str, engine: str) -> bool:
        return bool(self.types[type_id].labels[engine])

    def has_shared_label(self, type_id: str, engine: str) -> bool:
        """True when another type's labels also serve this type for the engine."""
        return any(type_id in t.shared.get(engine, []) and t.labels[engine] for t in self.types.values())


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    types = {}
    for t in raw["types"]:
        if t["id"] in types:
            raise TaxonomyError(f"duplicate type id {t['id']}")
        labels = {m: list(t["engine_labels"].get(_LABEL_KEY[m], [])) for m in ENGINES}
        shared = {m: list(v) for m, v in (t.get("shared_labels") or {}).items()}
        types[t["id"]] = TypeInfo(t["id"], t["tier"], bool(t["rules"]), labels, shared)
    tax = Taxonomy(str(raw["version"]), types)
    check_taxonomy(tax)
    return tax


def check_taxonomy(tax: Taxonomy) -> None:
    if len(tax.types) != 59:
        raise TaxonomyError(f"expected 59 types, found {len(tax.types)}")
    counts = {k: sum(1 for t in tax.types.values() if t.tier == k) for k in TIER_COUNTS}
    if counts != TIER_COUNTS:
        raise TaxonomyError(f"tier counts {counts}, expected {TIER_COUNTS}")
    if sum(1 for t in tax.types.values() if t.rules) != 12:
        raise TaxonomyError("expected 12 rule types")
    for t in tax.types.values():
        if not t.labels["tagger"]:
            raise TaxonomyError(f"{t.id}: the tagger has a label for every type")


def check_pin(path: Path = TAXONOMY_PATH, pin_path: Path = PIN_PATH) -> dict:
    """The vendored file must hash to the pin. Returns the pin."""
    pin = json.loads(Path(pin_path).read_text(encoding="utf-8"))
    actual = git_blob_sha1(Path(path).read_bytes())
    if actual != pin["blob_sha1"]:
        raise TaxonomyError(f"taxonomy blob {actual} does not match pin {pin['blob_sha1']}")
    return pin
