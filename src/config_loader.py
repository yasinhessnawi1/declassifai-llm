"""Central configuration loader.

Loads config.yaml and provides typed access to all settings.
Every module imports config from here -- single source of truth.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Dataclasses for typed config access
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    name: str = "Qwen/Qwen2.5-7B-Instruct"
    max_seq_length: int = 2048
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    trust_remote_code: bool = True


@dataclass
class LoraConfig:
    r: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])
    task_type: str = "CAUSAL_LM"
    bias: str = "none"


@dataclass
class DatasetConfig:
    source: str = "data/combined_data.jsonl"
    processed_dir: str = "data/processed"
    train_file: str = "data/processed/train.jsonl"
    val_file: str = "data/processed/val.jsonl"
    test_file: str = "data/processed/test.jsonl"
    val_split: float = 0.05
    test_split: float = 0.02
    seed: int = 42
    max_samples: Optional[int] = None


@dataclass
class TrainingConfig:
    output_dir: str = "models/qlora_adapter"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 1
    per_device_eval_batch_size: int = 1
    gradient_accumulation_steps: int = 16
    learning_rate: float = 2e-4
    weight_decay: float = 0.01
    warmup_ratio: float = 0.03
    lr_scheduler_type: str = "cosine"
    logging_steps: int = 25
    save_steps: int = 500
    eval_steps: int = 500
    save_total_limit: int = 3
    fp16: bool = False
    bf16: bool = True
    gradient_checkpointing: bool = True
    optim: str = "paged_adamw_8bit"
    max_grad_norm: float = 0.3
    group_by_length: bool = True
    report_to: str = "none"
    dataloader_num_workers: int = 0


@dataclass
class PromptConfig:
    system_instruction: str = ""
    user_template: str = ""
    assistant_prefix: str = ""


@dataclass
class ExportConfig:
    merged_dir: str = "models/merged"
    push_to_hub: bool = False
    hub_model_id: str = ""


@dataclass
class EvaluationConfig:
    output_dir: str = "evaluation"
    num_samples: int = 200
    threshold: float = 0.5
    per_type_metrics: bool = True


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    lora: LoraConfig = field(default_factory=LoraConfig)
    dataset: DatasetConfig = field(default_factory=DatasetConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    entity_types: Dict[str, str] = field(default_factory=dict)
    project_root: Path = field(default_factory=lambda: Path("."))


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _dict_to_dataclass(cls, data: dict):
    """Convert a dict to a dataclass, ignoring unknown keys."""
    if not data:
        return cls()
    valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return cls(**filtered)


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config YAML. If None, uses configs/config.yaml
                     relative to this file's package root.

    Returns:
        Fully populated Config object.
    """
    if config_path is None:
        # Default: llm_finetune/configs/config.yaml
        config_path = Path(__file__).parent.parent / "configs" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    project_root = config_path.parent.parent  # llm_finetune/

    cfg = Config(
        model=_dict_to_dataclass(ModelConfig, raw.get("model", {})),
        lora=_dict_to_dataclass(LoraConfig, raw.get("lora", {})),
        dataset=_dict_to_dataclass(DatasetConfig, raw.get("dataset", {})),
        training=_dict_to_dataclass(TrainingConfig, raw.get("training", {})),
        prompt=_dict_to_dataclass(PromptConfig, raw.get("prompt", {})),
        export=_dict_to_dataclass(ExportConfig, raw.get("export", {})),
        evaluation=_dict_to_dataclass(EvaluationConfig, raw.get("evaluation", {})),
        entity_types=raw.get("entity_types", {}),
        project_root=project_root,
    )

    return cfg


def resolve_path(cfg: Config, relative_path: str) -> Path:
    """Resolve a config-relative path to an absolute path."""
    return cfg.project_root / relative_path
