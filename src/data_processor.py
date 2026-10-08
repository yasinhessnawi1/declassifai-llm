"""Dataset processor: converts raw JSONL to chat fine-tuning format.

Two modes:

* **prebuilt** (`dataset.prebuilt_dir` set) -- reads the train/val/test files that
  `tools/build_training_set.py` wrote. The split is already fixed (gold is test and
  only test, enforced there by text digest), and each record carries its annotation
  scope in `types`, which becomes that example's prompt. This is the v2 path.
* **legacy** -- reads `dataset.source` and splits it at random. Kept for old configs;
  it cannot keep a gold set out of training.
"""

import json
import random
import logging
from pathlib import Path
from typing import Optional

from .config_loader import Config, resolve_path
from .prompt_builder import build_chat_messages

logger = logging.getLogger(__name__)


def load_raw_dataset(cfg: Config) -> list:
    """Load raw JSONL dataset.

    Args:
        cfg: Config with dataset.source path.

    Returns:
        List of dicts with 'text_input' and 'output' keys.
    """
    source_path = resolve_path(cfg, cfg.dataset.source)
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset not found: {source_path}")

    data = []
    skipped = 0
    with open(source_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if "text_input" not in entry or "output" not in entry:
                    skipped += 1
                    continue
                data.append(entry)
            except json.JSONDecodeError:
                skipped += 1
                logger.warning("Skipped malformed JSON at line %d", i + 1)

    logger.info("Loaded %d samples (%d skipped)", len(data), skipped)
    return data


def convert_to_chat_format(data: list, cfg: Config) -> list:
    """Convert raw dataset entries to chat message format.

    Args:
        data: List of raw entries with text_input and output.
        cfg: Config with prompt templates and entity types.

    Returns:
        List of dicts, each with a 'messages' key containing the chat sequence.
    """
    converted = []
    for entry in data:
        text = entry["text_input"]
        entities = entry["output"]

        messages = build_chat_messages(text, entities, cfg)
        converted.append({"messages": messages})

    return converted


def split_dataset(data: list, cfg: Config) -> tuple:
    """Split dataset into train/val/test.

    Args:
        data: Full converted dataset.
        cfg: Config with split ratios and seed.

    Returns:
        Tuple of (train, val, test) lists.
    """
    random.seed(cfg.dataset.seed)
    shuffled = data.copy()
    random.shuffle(shuffled)

    if cfg.dataset.max_samples:
        shuffled = shuffled[: cfg.dataset.max_samples]

    n = len(shuffled)
    n_test = max(1, int(n * cfg.dataset.test_split))
    n_val = max(1, int(n * cfg.dataset.val_split))
    n_train = n - n_val - n_test

    train = shuffled[:n_train]
    val = shuffled[n_train : n_train + n_val]
    test = shuffled[n_train + n_val :]

    logger.info("Split: train=%d, val=%d, test=%d", len(train), len(val), len(test))
    return train, val, test


def load_prebuilt_split(path: Path) -> list:
    """Read one split written by tools/build_training_set.py."""
    if not path.exists():
        raise FileNotFoundError(
            f"Prebuilt split not found: {path}\n"
            "Run 'python tools/build_training_set.py --out-dir <dir>' first."
        )
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def to_chat(records: list, cfg: Config) -> list:
    """Convert prebuilt records to chat format, keeping what evaluation needs.

    The raw text, the expected output and the scope ride along with the messages so
    the evaluator never has to recover them by parsing the prompt.
    """
    out = []
    for r in records:
        messages = build_chat_messages(r["text_input"], r["output"], cfg, r.get("types"))
        out.append({"messages": messages, "text_input": r["text_input"],
                    "output": r["output"], "types": r.get("types"),
                    "source": r.get("source")})
    return out


def process_prebuilt(cfg: Config):
    """Prepare chat-format splits from tools/build_training_set.py output."""
    base = resolve_path(cfg, cfg.dataset.prebuilt_dir)
    splits = {name: load_prebuilt_split(base / f"{name}.jsonl") for name in ("train", "val", "test")}

    factor = max(1, cfg.dataset.upsample_annotated)
    train = splits["train"]
    if factor > 1:
        annotated = [r for r in train if r.get("source") != "corpus"]
        train = train + annotated * (factor - 1)
        random.Random(cfg.dataset.seed).shuffle(train)
    if cfg.dataset.max_samples:
        train = train[: cfg.dataset.max_samples]

    chat = {"train": to_chat(train, cfg), "val": to_chat(splits["val"], cfg),
            "test": to_chat(splits["test"], cfg)}
    save_jsonl(chat["train"], resolve_path(cfg, cfg.dataset.train_file))
    save_jsonl(chat["val"], resolve_path(cfg, cfg.dataset.val_file))
    save_jsonl(chat["test"], resolve_path(cfg, cfg.dataset.test_file))

    n_annot = sum(1 for r in train if r.get("source") != "corpus")
    print(f"\nDataset Processing Complete (prebuilt: {cfg.dataset.prebuilt_dir})")
    print(f"  Train: {len(train)} examples ({n_annot} fully annotated, upsampled x{factor})")
    print(f"  Val:   {len(splits['val'])}   Test: {len(splits['test'])} (gold only)")
    print(f"  Entity types configured: {len(cfg.entity_types)}")
    if chat["train"]:
        sample = chat["train"][0]["messages"]
        print(f"\n  Sample user prompt head: {sample[1]['content'][:160]!r}")
        print(f"  Sample target head:      {sample[2]['content'][:160]!r}")


def save_jsonl(data: list, path: Path):
    """Save list of dicts as JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info("Saved %d samples to %s", len(data), path)


def process_dataset(cfg: Config, config_path: Optional[str] = None):
    """Full pipeline: load -> convert -> split -> save.

    Args:
        cfg: Config object.
        config_path: Optional path override (unused, kept for CLI compat).
    """
    if cfg.dataset.prebuilt_dir:
        return process_prebuilt(cfg)
    logger.info("Loading raw dataset from %s", cfg.dataset.source)
    raw_data = load_raw_dataset(cfg)

    logger.info("Converting %d samples to chat format...", len(raw_data))
    chat_data = convert_to_chat_format(raw_data, cfg)

    logger.info("Splitting dataset...")
    train, val, test = split_dataset(chat_data, cfg)

    # Save splits
    save_jsonl(train, resolve_path(cfg, cfg.dataset.train_file))
    save_jsonl(val, resolve_path(cfg, cfg.dataset.val_file))
    save_jsonl(test, resolve_path(cfg, cfg.dataset.test_file))

    # Print summary
    print(f"\nDataset Processing Complete")
    print(f"  Source:    {cfg.dataset.source} ({len(raw_data)} samples)")
    print(f"  Train:     {cfg.dataset.train_file} ({len(train)} samples)")
    print(f"  Val:       {cfg.dataset.val_file} ({len(val)} samples)")
    print(f"  Test:      {cfg.dataset.test_file} ({len(test)} samples)")
    print(f"  Entity types: {len(cfg.entity_types)}")

    # Show a sample
    if train:
        sample = train[0]["messages"]
        print(f"\n  Sample (first training entry):")
        print(f"    System: {sample[0]['content'][:80]}...")
        print(f"    User:   {sample[1]['content'][:80]}...")
        print(f"    Assist: {sample[2]['content'][:80]}...")
