#!/usr/bin/env python3
"""LLM Fine-Tuning CLI for Norwegian NER.

Usage:
    python main.py prepare               # Process dataset into chat format
    python main.py train                  # Run QLoRA fine-tuning
    python main.py eval                   # Evaluate on test set
    python main.py export                 # Merge adapter into base model
    python main.py all                    # Run full pipeline

Options:
    --config PATH                         # Custom config file path
"""

import sys
import argparse
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="LLM Fine-Tuning for Norwegian NER",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  prepare   Convert raw JSONL dataset to chat fine-tuning format
  train     Run QLoRA fine-tuning on processed dataset
  eval      Evaluate fine-tuned model on test set
  export    Merge LoRA adapter into base model for deployment
  all       Run the full pipeline (prepare -> train -> eval)
        """,
    )

    parser.add_argument(
        "command",
        choices=["prepare", "train", "eval", "export", "all"],
        help="Command to run",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML (default: configs/config.yaml)",
    )

    args = parser.parse_args()

    # Load config
    from src.config_loader import load_config

    cfg = load_config(args.config)

    # Dispatch
    if args.command == "prepare":
        from src.data_processor import process_dataset
        process_dataset(cfg)

    elif args.command == "train":
        from src.trainer import train
        train(cfg)

    elif args.command == "eval":
        from src.evaluator import evaluate
        evaluate(cfg)

    elif args.command == "export":
        from src.exporter import export_merged_model
        export_merged_model(cfg)

    elif args.command == "all":
        from src.data_processor import process_dataset
        from src.trainer import train
        from src.evaluator import evaluate

        print("\n=== STEP 1/3: Preparing Dataset ===")
        process_dataset(cfg)

        print("\n=== STEP 2/3: Training ===")
        train(cfg)

        print("\n=== STEP 3/3: Evaluating ===")
        evaluate(cfg)

        print("\n=== Pipeline Complete ===")
        print("Run 'python main.py export' to merge adapter for deployment.")


if __name__ == "__main__":
    main()
