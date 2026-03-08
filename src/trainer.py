"""QLoRA training module.

Handles model loading with 4-bit quantization, LoRA adapter setup,
and training via Hugging Face SFTTrainer.
"""

import json
import logging
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig as PeftLoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

from .config_loader import Config, resolve_path

logger = logging.getLogger(__name__)


def _check_gpu():
    """Check GPU availability and print info."""
    if not torch.cuda.is_available():
        logger.warning("No CUDA GPU detected. Training will be very slow on CPU.")
        return False

    gpu_name = torch.cuda.get_device_name(0)
    gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    logger.info("GPU: %s (%.1f GB VRAM)", gpu_name, gpu_mem)
    return True


def load_tokenizer(cfg: Config):
    """Load and configure the tokenizer.

    Args:
        cfg: Config with model settings.

    Returns:
        Configured tokenizer.
    """
    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model.name,
        trust_remote_code=cfg.model.trust_remote_code,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    return tokenizer


def load_model(cfg: Config):
    """Load base model with 4-bit quantization.

    Args:
        cfg: Config with model and quantization settings.

    Returns:
        Quantized model ready for LoRA.
    """
    compute_dtype = getattr(torch, cfg.model.bnb_4bit_compute_dtype, torch.bfloat16)

    bnb_config = None
    if cfg.model.load_in_4bit and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type=cfg.model.bnb_4bit_quant_type,
            bnb_4bit_use_double_quant=cfg.model.bnb_4bit_use_double_quant,
            llm_int8_enable_fp32_cpu_offload=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        cfg.model.name,
        quantization_config=bnb_config,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=cfg.model.trust_remote_code,
        dtype=compute_dtype,
    )

    if cfg.model.load_in_4bit and torch.cuda.is_available():
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=cfg.training.gradient_checkpointing,
        )

    return model


def setup_lora(model, cfg: Config):
    """Apply LoRA adapter to the model.

    Args:
        model: Base model (quantized).
        cfg: Config with LoRA settings.

    Returns:
        Model with LoRA adapter applied.
    """
    peft_config = PeftLoraConfig(
        r=cfg.lora.r,
        lora_alpha=cfg.lora.lora_alpha,
        lora_dropout=cfg.lora.lora_dropout,
        target_modules=cfg.lora.target_modules,
        task_type=cfg.lora.task_type,
        bias=cfg.lora.bias,
    )

    model = get_peft_model(model, peft_config)
    trainable, total = model.get_nb_trainable_parameters()
    logger.info(
        "LoRA: %d trainable / %d total params (%.2f%%)",
        trainable, total, 100 * trainable / total,
    )
    return model, peft_config


def _formatting_func(example, tokenizer):
    """Format a single example into a tokenized chat string.

    Applied by SFTTrainer to each dataset row during training.
    """
    messages = example["messages"]
    # Apply the model's chat template (e.g., ChatML for Qwen)
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    return text


def train(cfg: Config):
    """Run the full QLoRA training pipeline.

    Args:
        cfg: Config object with all settings.
    """
    print("\n" + "=" * 60)
    print("  QLoRA Fine-Tuning for Norwegian NER")
    print("=" * 60)

    # Check GPU
    has_gpu = torch.cuda.is_available()
    if has_gpu:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"  GPU: {gpu_name} ({gpu_mem:.1f} GB)")
    else:
        print("  GPU: None (CPU mode)")

    # Load tokenizer
    print(f"\n[1/5] Loading tokenizer: {cfg.model.name}")
    tokenizer = load_tokenizer(cfg)

    # Load model
    print(f"[2/5] Loading model with {'4-bit' if cfg.model.load_in_4bit else 'full'} precision...")
    model = load_model(cfg)

    if has_gpu:
        vram = torch.cuda.memory_allocated(0) / (1024**3)
        print(f"  VRAM after model load: {vram:.2f} GB")

    # Build LoRA config (SFTTrainer will apply it)
    print("[3/5] Configuring LoRA adapter...")
    peft_config = PeftLoraConfig(
        r=cfg.lora.r,
        lora_alpha=cfg.lora.lora_alpha,
        lora_dropout=cfg.lora.lora_dropout,
        target_modules=cfg.lora.target_modules,
        task_type=cfg.lora.task_type,
        bias=cfg.lora.bias,
    )

    # Load dataset
    print("[4/5] Loading training data...")
    train_path = resolve_path(cfg, cfg.dataset.train_file)
    val_path = resolve_path(cfg, cfg.dataset.val_file)

    if not train_path.exists():
        raise FileNotFoundError(
            f"Training data not found: {train_path}\n"
            "Run 'python main.py prepare' first to process the dataset."
        )

    train_dataset = load_dataset("json", data_files=str(train_path), split="train")
    val_dataset = load_dataset("json", data_files=str(val_path), split="train") if val_path.exists() else None

    print(f"  Train samples: {len(train_dataset)}")
    if val_dataset:
        print(f"  Val samples:   {len(val_dataset)}")

    # Training arguments
    output_dir = resolve_path(cfg, cfg.training.output_dir)

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=cfg.training.num_train_epochs,
        per_device_train_batch_size=cfg.training.per_device_train_batch_size,
        per_device_eval_batch_size=cfg.training.per_device_eval_batch_size,
        gradient_accumulation_steps=cfg.training.gradient_accumulation_steps,
        learning_rate=cfg.training.learning_rate,
        weight_decay=cfg.training.weight_decay,
        warmup_steps=cfg.training.warmup_ratio * len(train_dataset) / cfg.training.per_device_train_batch_size,
        lr_scheduler_type=cfg.training.lr_scheduler_type,
        logging_steps=cfg.training.logging_steps,
        save_steps=cfg.training.save_steps,
        eval_steps=cfg.training.eval_steps if val_dataset else None,
        eval_strategy="steps" if val_dataset else "no",
        save_total_limit=cfg.training.save_total_limit,
        fp16=cfg.training.fp16,
        bf16=cfg.training.bf16,
        gradient_checkpointing=cfg.training.gradient_checkpointing,
        optim=cfg.training.optim,
        max_grad_norm=cfg.training.max_grad_norm,
        report_to=cfg.training.report_to,
        dataloader_num_workers=cfg.training.dataloader_num_workers,
        max_length=cfg.model.max_seq_length,
        packing=False,
    )

    # Create formatting function with tokenizer bound
    def format_fn(example):
        return _formatting_func(example, tokenizer)

    # SFTTrainer
    print("[5/5] Starting training...")
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        formatting_func=format_fn,
        peft_config=peft_config,
    )

    # Train
    trainer.train()

    # Save adapter
    print(f"\nSaving adapter to {output_dir}")
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    print("\nTraining complete!")
    print(f"  Adapter saved: {output_dir}")
    print(f"  Run 'python main.py export' to merge adapter into base model.")
