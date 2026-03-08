"""Dataset processor: converts raw JSONL to chat fine-tuning format.

Reads the Gemini-labeled combined_data.jsonl and produces train/val/test
splits in chat message format, ready for the Hugging Face Trainer.
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
