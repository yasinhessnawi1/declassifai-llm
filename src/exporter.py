"""Model export module.

Merges the QLoRA adapter weights back into the base model,
producing a standalone model that can be loaded without PEFT.
"""

import logging
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

from .config_loader import Config, resolve_path

logger = logging.getLogger(__name__)


def export_merged_model(cfg: Config):
    """Merge LoRA adapter into base model and save.

    This produces a full-precision model in models/merged/ that can
    be loaded as a normal Hugging Face model (no PEFT dependency).

    Args:
        cfg: Config object.
    """
    print("\n" + "=" * 60)
    print("  Export: Merge LoRA Adapter into Base Model")
    print("=" * 60)

    adapter_path = resolve_path(cfg, cfg.training.output_dir)
    merged_path = resolve_path(cfg, cfg.export.merged_dir)

    if not adapter_path.exists() or not (adapter_path / "adapter_config.json").exists():
        raise FileNotFoundError(
            f"No adapter found at {adapter_path}\n"
            "Run 'python main.py train' first."
        )

    # Load base model in full precision (no quantization for merging)
    print(f"\n[1/4] Loading base model: {cfg.model.name}")
    print("  (Full precision for clean merge -- needs ~15 GB RAM)")

    base_model = AutoModelForCausalLM.from_pretrained(
        cfg.model.name,
        torch_dtype=torch.float16,
        device_map="cpu",  # Merge on CPU to avoid VRAM limits
        trust_remote_code=cfg.model.trust_remote_code,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model.name,
        trust_remote_code=cfg.model.trust_remote_code,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load adapter
    print(f"[2/4] Loading adapter from {adapter_path}")
    model = PeftModel.from_pretrained(base_model, str(adapter_path))

    # Merge
    print("[3/4] Merging adapter into base model...")
    model = model.merge_and_unload()

    # Save
    print(f"[4/4] Saving merged model to {merged_path}")
    merged_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(merged_path), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_path))

    # Size info
    total_size = sum(f.stat().st_size for f in merged_path.rglob("*") if f.is_file())
    print(f"\n  Merged model saved: {merged_path}")
    print(f"  Total size: {total_size / (1024**3):.1f} GB")

    # Push to hub if configured
    if cfg.export.push_to_hub and cfg.export.hub_model_id:
        print(f"\n  Pushing to HuggingFace Hub: {cfg.export.hub_model_id}")
        model.push_to_hub(cfg.export.hub_model_id)
        tokenizer.push_to_hub(cfg.export.hub_model_id)
        print("  Pushed successfully!")
    elif cfg.export.push_to_hub:
        print("  WARNING: push_to_hub is true but hub_model_id is empty. Skipping.")

    print("\nExport complete!")
    print("  You can now use this model in the detection service:")
    print(f"  ADVANCED_MODEL_MODE=local")
    print(f"  ADVANCED_MODEL_NAME={merged_path}")
