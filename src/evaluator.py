"""Evaluation module.

Runs the fine-tuned model on test data and computes per-entity-type
precision, recall, and F1 scores.
"""

import json
import logging
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

from .config_loader import Config, resolve_path
from .prompt_builder import build_inference_messages

logger = logging.getLogger(__name__)


def load_model_for_eval(cfg: Config):
    """Load the fine-tuned model (base + adapter) for evaluation.

    Tries adapter path first. If merged model exists, uses that instead.

    Args:
        cfg: Config object.

    Returns:
        Tuple of (model, tokenizer).
    """
    merged_path = resolve_path(cfg, cfg.export.merged_dir)
    adapter_path = resolve_path(cfg, cfg.training.output_dir)

    compute_dtype = getattr(torch, cfg.model.bnb_4bit_compute_dtype, torch.bfloat16)

    bnb_config = None
    if cfg.model.load_in_4bit and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type=cfg.model.bnb_4bit_quant_type,
            bnb_4bit_use_double_quant=cfg.model.bnb_4bit_use_double_quant,
        )

    # Prefer merged model if it exists
    if merged_path.exists() and (merged_path / "config.json").exists():
        print(f"  Loading merged model from {merged_path}")
        tokenizer = AutoTokenizer.from_pretrained(
            str(merged_path), trust_remote_code=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            str(merged_path),
            quantization_config=bnb_config,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
            torch_dtype=compute_dtype,
        )
    elif adapter_path.exists() and (adapter_path / "adapter_config.json").exists():
        print(f"  Loading base model + adapter from {adapter_path}")
        tokenizer = AutoTokenizer.from_pretrained(
            cfg.model.name, trust_remote_code=True
        )
        base_model = AutoModelForCausalLM.from_pretrained(
            cfg.model.name,
            quantization_config=bnb_config,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
            torch_dtype=compute_dtype,
        )
        model = PeftModel.from_pretrained(base_model, str(adapter_path))
    else:
        raise FileNotFoundError(
            "No trained model found. Run 'python main.py train' first.\n"
            f"  Checked: {adapter_path}\n"
            f"  Checked: {merged_path}"
        )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model.eval()
    return model, tokenizer


def generate_prediction(
    model,
    tokenizer,
    text: str,
    cfg: Config,
    max_new_tokens: int = 1024,
    types=None,
) -> Dict[str, List[str]]:
    """Run inference on a single text and parse the JSON output.

    Args:
        model: Fine-tuned model.
        tokenizer: Tokenizer.
        text: Norwegian input text.
        cfg: Config with prompt templates.
        max_new_tokens: Max tokens to generate.

    Returns:
        Dict mapping entity types to lists of extracted strings.
    """
    messages = build_inference_messages(text, cfg, types)

    # Training targets were rendered by the chat template as an empty think block
    # followed by the JSON. Qwen3-style templates open a think block at generation
    # time unless thinking is disabled, which left the model free to "think" until
    # max_new_tokens. Render the prompt the way training saw it.
    try:
        formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)

    inputs = tokenizer(formatted, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            eos_token_id=_stop_ids(tokenizer),
        )

    new_tokens = output_ids[0][input_len:]
    raw_output = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    return _parse_output(raw_output, cfg, types)


def _stop_ids(tokenizer) -> List[int]:
    """End-of-turn ids to stop on: the chat end marker as well as the tokenizer EOS."""
    ids = {tokenizer.eos_token_id}
    for tok in ("<|im_end|>", "<|endoftext|>"):
        tid = tokenizer.convert_tokens_to_ids(tok)
        if isinstance(tid, int) and tid >= 0 and tid != tokenizer.unk_token_id:
            ids.add(tid)
    return sorted(i for i in ids if i is not None)


def _parse_output(raw: str, cfg: Config, types=None) -> Dict[str, List[str]]:
    """Parse model output JSON into entity dict.

    Args:
        raw: Raw model output string.
        cfg: Config for entity type keys.

    Returns:
        Dict mapping entity types to extracted string lists.
    """
    import re
    # Drop any think block, then take the outermost JSON object.
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).replace("</think>", "").strip()
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first >= 0 and last > first:
        cleaned = cleaned[first:last + 1]
    if cleaned.startswith("```"):
        import re
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    scope = list(types) if types else list(cfg.entity_types)
    result = {etype: [] for etype in scope}

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            for etype in scope:
                val = parsed.get(etype, [])
                if isinstance(val, list):
                    result[etype] = [str(v) for v in val]
                elif isinstance(val, str) and val:
                    result[etype] = [val]
    except json.JSONDecodeError:
        logger.warning("Failed to parse model output as JSON")
        logger.debug("Raw output: %s", raw[:500])

    return result


def compute_metrics(
    predicted: Dict[str, List[str]],
    expected: Dict[str, List[str]],
) -> Dict[str, Dict[str, float]]:
    """Compute per-entity-type precision, recall, F1.

    Uses fuzzy matching: a prediction matches an expected entity if one
    is a case-insensitive substring of the other.

    Args:
        predicted: Model output entity dict.
        expected: Ground truth entity dict.

    Returns:
        Dict mapping entity type to {precision, recall, f1, tp, fp, fn}.
    """
    metrics = {}

    all_types = set(list(predicted.keys()) + list(expected.keys()))

    for etype in sorted(all_types):
        pred_list = predicted.get(etype, [])
        exp_list = expected.get(etype, [])

        # Match predictions to expected (fuzzy substring match)
        matched_pred = set()
        matched_exp = set()

        for i, exp in enumerate(exp_list):
            for j, pred in enumerate(pred_list):
                if j in matched_pred:
                    continue
                if _fuzzy_match(exp, pred):
                    matched_pred.add(j)
                    matched_exp.add(i)
                    break

        tp = len(matched_exp)
        fp = len(pred_list) - tp
        fn = len(exp_list) - tp
        strict_tp = len(set(exp_list) & set(pred_list))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[etype] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "strict_tp": strict_tp,
            "n_pred": len(pred_list),
            "n_exp": len(exp_list),
        }

    return metrics


def _fuzzy_match(a: str, b: str) -> bool:
    """Check if two strings match (case-insensitive substring)."""
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    return a_lower in b_lower or b_lower in a_lower


def evaluate(cfg: Config):
    """Run full evaluation on the test set.

    Args:
        cfg: Config object.
    """
    print("\n" + "=" * 60)
    print("  Evaluation: Fine-Tuned NER Model")
    print("=" * 60)

    # Load model
    print("\n[1/3] Loading model...")
    model, tokenizer = load_model_for_eval(cfg)

    if torch.cuda.is_available():
        vram = torch.cuda.memory_allocated(0) / (1024**3)
        print(f"  VRAM used: {vram:.2f} GB")

    # Load test data
    print("[2/3] Loading test data...")
    test_path = resolve_path(cfg, cfg.dataset.test_file)
    if not test_path.exists():
        raise FileNotFoundError(
            f"Test data not found: {test_path}\n"
            "Run 'python main.py prepare' first."
        )

    test_data = []
    with open(test_path, "r", encoding="utf-8") as f:
        for line in f:
            test_data.append(json.loads(line))

    num_samples = min(cfg.evaluation.num_samples, len(test_data))
    test_data = test_data[:num_samples]
    print(f"  Evaluating on {num_samples} samples")

    # Run evaluation
    print("[3/3] Running inference...")
    all_metrics = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "strict_tp": 0,
                                       "n_pred": 0, "n_exp": 0})
    total_time = 0
    valid_json_count = 0
    predictions = []  # saved for tools/score_predictions.py

    for i, entry in enumerate(test_data):
        types = entry.get("types")
        if "text_input" in entry:
            # Prebuilt splits carry the raw text, expected spans and scope.
            actual_text = entry["text_input"]
            scope = types or list(cfg.entity_types)
            expected = {t: entry["output"].get(t, []) for t in scope}
        else:
            messages = entry["messages"]
            text = messages[1]["content"]  # user message contains the text
            try:
                expected = json.loads(messages[2]["content"])
            except json.JSONDecodeError:
                continue
            text_marker = "Text:\n"
            text_idx = text.rfind(text_marker)
            actual_text = text[text_idx + len(text_marker):] if text_idx >= 0 else text

        start = time.time()
        predicted = generate_prediction(model, tokenizer, actual_text, cfg, types=types)
        elapsed = time.time() - start
        total_time += elapsed
        predictions.append({"id": entry.get("source", i), "output": {k: v for k, v in predicted.items() if v},
                            "seconds": round(elapsed, 2)})

        # Check if output was valid JSON
        if any(predicted[k] for k in predicted):
            valid_json_count += 1

        # Aggregate metrics per entity type
        sample_metrics = compute_metrics(predicted, expected)
        for etype, m in sample_metrics.items():
            for k in ("tp", "fp", "fn", "strict_tp", "n_pred", "n_exp"):
                all_metrics[etype][k] += m[k]

        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1}/{num_samples}] {elapsed:.1f}s/sample")

    # Compute final metrics
    print(f"\n{'=' * 60}")
    print(f"  Results ({num_samples} samples, {total_time:.0f}s total)")
    print(f"  Valid JSON: {valid_json_count}/{num_samples} ({100*valid_json_count/num_samples:.0f}%)")
    print(f"  Avg time: {total_time/num_samples:.1f}s/sample")
    print(f"{'=' * 60}")

    total_tp = total_fp = total_fn = 0
    total_strict = total_pred = total_exp = 0
    results = {}

    if cfg.evaluation.per_type_metrics:
        print(f"\n  {'Entity Type':<25} {'Prec':>6} {'Rec':>6} {'F1':>6} {'TP':>5} {'FP':>5} {'FN':>5}")
        print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*5} {'-'*5}")

    for etype in sorted(all_metrics.keys()):
        m = all_metrics[etype]
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        sp = m["strict_tp"] / m["n_pred"] if m["n_pred"] else 0.0
        sr = m["strict_tp"] / m["n_exp"] if m["n_exp"] else 0.0
        sf1 = 2 * sp * sr / (sp + sr) if (sp + sr) else 0.0
        total_strict += m["strict_tp"]; total_pred += m["n_pred"]; total_exp += m["n_exp"]
        results[etype] = {"precision": prec, "recall": rec, "f1": f1, "strict_f1": sf1,
                          "support": m["n_exp"]}

        if cfg.evaluation.per_type_metrics:
            print(f"  {etype:<25} {prec:>5.1%} {rec:>5.1%} {f1:>5.1%} {tp:>5} {fp:>5} {fn:>5}  strict F1 {sf1:>5.1%}")

    # Overall
    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0

    print(f"\n  {'OVERALL':<25} {overall_prec:>5.1%} {overall_rec:>5.1%} {overall_f1:>5.1%} {total_tp:>5} {total_fp:>5} {total_fn:>5}")
    sp = total_strict / total_pred if total_pred else 0.0
    sr = total_strict / total_exp if total_exp else 0.0
    strict_f1 = 2 * sp * sr / (sp + sr) if (sp + sr) else 0.0
    print(f"  {'OVERALL strict (exact span)':<25} P {sp:.1%}  R {sr:.1%}  F1 {strict_f1:.1%}")
    results["OVERALL"] = {"precision": overall_prec, "recall": overall_rec, "f1": overall_f1,
                          "strict_precision": sp, "strict_recall": sr, "strict_f1": strict_f1}

    # Save results
    output_dir = resolve_path(cfg, cfg.evaluation.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "eval_results.json"
    with open(output_dir / "predictions.jsonl", "w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n  Results saved to {results_path}")
