# LLM Fine-Tuning for Norwegian NER

Fine-tune a small LLM (Qwen2.5-3B) with QLoRA to extract named entities and PII
from Norwegian government documents. The resulting model accepts prompts (like Gemini)
but runs 100% locally for GDPR compliance.

## Architecture

```
Qwen2.5-3B-Instruct (base, frozen, 4-bit quantized = ~2.5 GB VRAM)
    + QLoRA adapter (64-rank, ~228 MB)
    = Norwegian NER specialist that outputs structured JSON
```

**Training data:** 32,439 raw Norwegian documents labeled by Gemini. The Gemini labels
are being replaced -- see `docs/DATA_QUALITY.md` for the audit and
`docs/ANNOTATION_SPEC.md` for the 16-type schema that supersedes them.

**Hardware:** RTX 2060 (6GB VRAM) with 4-bit quantization + gradient checkpointing.
Peak VRAM during training: ~5.6 GB.

## Project Structure

```
llm_finetune/
  configs/
    config.yaml          # Central configuration (edit this)
  data/
    combined_data.jsonl   # Raw 32K dataset (Gemini-labeled)
    processed/            # Auto-generated train/val/test splits
  src/
    config_loader.py      # Loads config.yaml into typed dataclasses
    prompt_builder.py     # Builds chat messages (system/user/assistant)
    data_processor.py     # Converts JSONL -> chat format, splits data
    trainer.py            # QLoRA training with SFTTrainer
    evaluator.py          # Per-entity-type precision/recall/F1
    exporter.py           # Merges adapter into standalone model
  models/
    qlora_adapter/        # Trained adapter weights (~100MB)
    merged/               # Full merged model (~14GB)
  evaluation/
    eval_results.json     # Evaluation metrics
  main.py                 # CLI entry point
  requirements.txt
```

## Quick Start

### 1. Install dependencies

```bash
cd llm_finetune
pip install -r requirements.txt
```

### 2. Prepare the dataset

Converts the raw JSONL into chat-format train/val/test splits:

```bash
python main.py prepare
```

This creates:
- `data/processed/train.jsonl` (~30K samples)
- `data/processed/val.jsonl` (~1.6K samples)
- `data/processed/test.jsonl` (~650 samples)

### 3. Train the model

QLoRA fine-tuning (3 epochs, ~2-4 hours on RTX 2060):

```bash
python main.py train
```

Saves adapter to `models/qlora_adapter/`.

### 4. Evaluate

Run inference on the test set and compute per-entity F1:

```bash
python main.py eval
```

### 5. Export for deployment

Merge adapter into base model (runs on CPU, needs ~15GB RAM):

```bash
python main.py export
```

### 6. Use in detection service

Point the detection service to the merged model:

```env
ADVANCED_MODEL_MODE=local
ADVANCED_MODEL_NAME=path/to/llm_finetune/models/merged
```

## Configuration

All settings are in `configs/config.yaml`. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `model.name` | `Qwen/Qwen2.5-7B-Instruct` | Base model from HuggingFace |
| `model.max_seq_length` | 2048 | Max tokens per training sample |
| `lora.r` | 64 | LoRA rank (higher = more capacity) |
| `training.num_train_epochs` | 3 | Training epochs |
| `training.gradient_accumulation_steps` | 16 | Effective batch size |
| `training.learning_rate` | 2e-4 | Learning rate |
| `dataset.max_samples` | null | Limit dataset size for testing |

### Quick test run

To test the pipeline on a small subset:

```yaml
# In config.yaml:
dataset:
  max_samples: 100  # Use only 100 samples
training:
  num_train_epochs: 1
  save_steps: 50
  eval_steps: 50
```

## Entity Types (16)

Defined in `docs/ANNOTATION_SPEC.md`, which is the authority: each type has a
boundary definition and the shared rules B1-B20 govern span edges, overlap and
precedence. `CONTEXT_SENSITIVE` and `IDENTIFIABLE_IMAGE` were cut from the original
18 -- neither identifies a natural person under GDPR Art. 4(1).

Counts below are raw Gemini spans in `data/combined_data.jsonl`, before cleanup.
They are a measure of the input, not of the schema.

| Type | Description | Dataset Count |
|------|-------------|---------------|
| PERSON | Full names | 82,884 |
| DATE_TIME | Dates/times tied to persons | 81,612 |
| HEALTH_INFO | Medical conditions, diseases | 52,778 |
| GOV_ID | National IDs, org numbers | 51,237 |
| NO_ADDRESS | Street addresses | 45,637 |
| CRIMINAL_RECORD | Criminal history | 37,511 |
| POSTAL_CODE | Norwegian postal codes | 35,531 |
| NO_PHONE_NUMBER | Phone numbers | 32,217 |
| EMAIL_ADDRESS | Email addresses | 30,937 |
| FAMILY_RELATION | Family relationships | 30,154 |
| FINANCIAL_INFO | Financial data | 24,036 |
| EMPLOYMENT_INFO | Job titles, workplaces | 22,651 |
| POLITICAL_CASE | Political opinions | 19,137 |
| BEHAVIORAL_PATTERN | Behavioral patterns | 16,431 |
| ECONOMIC_STATUS | Economic references | 15,221 |
| SEXUAL_ORIENTATION | Sexual orientation | 11,817 |

## How It Works

1. **Data Processing**: Each raw document is converted to a chat sequence:
   - **System**: "You are a precise NER system for Norwegian texts..."
   - **User**: "Extract entities from this text: {entity_types}\n\nText: {document}"
   - **Assistant**: `{"PERSON":["Ola Nordmann"],"EMAIL_ADDRESS":["ola@test.no"],...}`

2. **QLoRA Training**: Only ~2% of model parameters are trained (LoRA adapters on
   attention + MLP layers). 4-bit quantization keeps VRAM under 6GB.

3. **Inference**: Same prompt format as training. Model outputs JSON with entity
   types as keys and arrays of extracted strings as values.
