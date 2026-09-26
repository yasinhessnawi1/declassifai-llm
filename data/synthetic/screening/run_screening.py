"""Run the model-selection screening prompts against one candidate model.

Loads a single HF model in fp16 with attn_implementation="sdpa" (V100/sm70: no
flash-attn, no usable bf16 tensor cores per docs/SYNTHETIC_DATA_SPEC.md SS2), runs
every prompt in prompts.py through the model's own chat template, and writes raw
text + timing/VRAM metrics to data/synthetic/screening/raw/<slug>/ and
data/synthetic/screening/logs/<slug>.json.

Usage:
    myenv/bin/python run_screening.py <model_id> [--slug SLUG] [--4bit] [--max-new-tokens N]

Run once per candidate (separate process per model keeps VRAM clean between
candidates; this machine has exactly one V100 and no other GPU user right now).
"""
import argparse
import gc
import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
from prompts import PROMPTS

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
LOG_DIR = HERE / "logs"


def slugify(model_id: str) -> str:
    return model_id.replace("/", "__")


def _patch_remote_tied_keys(model_id: str) -> None:
    """Adapt custom-code models written for transformers 4.x to 5.x.

    transformers 5 expects `_tied_weights_keys` to be a {target: source} dict;
    older remote code (e.g. XHToken/Spark-X2.5-4B) still declares a list, which
    crashes in post_init before any weights load.
    """
    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained(model_id, trust_remote_code=True)
    ref = (getattr(cfg, "auto_map", None) or {}).get("AutoModelForCausalLM")
    if not ref:
        return
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    cls = get_class_from_dynamic_module(ref, model_id)
    if isinstance(getattr(cls, "_tied_weights_keys", None), list):
        tied = getattr(cfg, "tie_word_embeddings", False)
        source = "model.embedding.weight" if "self.embedding = nn.Embedding" in open(
            __import__("inspect").getsourcefile(cls)).read() else "model.embed_tokens.weight"
        cls._tied_weights_keys = {"lm_head.weight": source} if tied else {}


def load_model(model_id: str, use_4bit: bool, attn: str = "sdpa"):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    kwargs = dict(torch_dtype=torch.float16, attn_implementation=attn, trust_remote_code=True)
    if use_4bit:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
        )
        kwargs["device_map"] = "auto"
    _patch_remote_tied_keys(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    head = model.get_output_embeddings()
    if head is not None and head.weight.is_meta:
        # Tied checkpoint with no lm_head tensor, which transformers 5 declined
        # to tie for this remote-code class; tie it by hand.
        head.weight = model.get_input_embeddings().weight
    gen = model.generation_config
    if gen.top_k is not None and gen.top_k <= 0:
        # vLLM/SGLang use top_k=-1 for "disabled"; transformers wants None.
        gen.top_k = None
    if hasattr(model.config, "get_rope_theta"):
        print(f"rope_theta per layer type: "
              f"{ {lt: model.config.get_rope_theta(lt) for lt in set(model.config.layer_types)} }")
    if not use_4bit:
        model = model.to("cuda")
    model.eval()
    return tok, model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_id")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--4bit", dest="use_4bit", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=650)
    ap.add_argument("--disable-thinking", action="store_true", help="pass enable_thinking=False to chat template (Qwen3/3.5)")
    ap.add_argument("--attn", default="sdpa", help="attention backend; custom-code models without SDPA support need eager")
    ap.add_argument("--only", default=None, help="comma-separated prompt ids to run (debug)")
    args = ap.parse_args()

    slug = args.slug or slugify(args.model_id)
    out_dir = RAW_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{slug}] loading tokenizer+model ...", flush=True)
    t_load0 = time.time()
    tok, model = load_model(args.model_id, args.use_4bit, args.attn)
    t_load1 = time.time()
    print(f"[{slug}] loaded in {t_load1 - t_load0:.1f}s", flush=True)

    prompts = PROMPTS
    if args.only:
        want = set(args.only.split(","))
        prompts = [p for p in prompts if p["id"] in want]

    results = []
    for p in prompts:
        messages = [{"role": "user", "content": p["instruction"]}]
        template_kwargs = dict(add_generation_prompt=True, return_tensors="pt", return_dict=False)
        if args.disable_thinking:
            template_kwargs["enable_thinking"] = False
        try:
            templated = tok.apply_chat_template(messages, **template_kwargs)
            if hasattr(templated, "shape"):
                input_ids = templated.to("cuda")
            else:
                input_ids = templated["input_ids"].to("cuda")
        except Exception as e:
            print(f"[{slug}] {p['id']}: chat template failed ({e}), falling back to raw prompt", flush=True)
            input_ids = tok(p["instruction"], return_tensors="pt").input_ids.to("cuda")

        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(
                input_ids,
                max_new_tokens=args.max_new_tokens,
                do_sample=True,
                temperature=0.75,
                top_p=0.9,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
        torch.cuda.synchronize()
        t1 = time.time()
        gen_tokens = out.shape[1] - input_ids.shape[1]
        text = tok.decode(out[0, input_ids.shape[1]:], skip_special_tokens=True)
        peak_vram_gb = torch.cuda.max_memory_allocated() / 1e9
        elapsed = t1 - t0
        tok_per_sec = gen_tokens / elapsed if elapsed > 0 else 0.0

        (out_dir / f"{p['id']}.txt").write_text(text, encoding="utf-8")
        results.append({
            "id": p["id"], "genre": p["genre"], "lang": p["lang"], "marked": p["marked"],
            "gen_tokens": gen_tokens, "elapsed_s": elapsed, "tok_per_sec": tok_per_sec,
            "peak_vram_gb": peak_vram_gb, "chars": len(text),
        })
        print(f"[{slug}] {p['id']}: {gen_tokens} tok in {elapsed:.1f}s ({tok_per_sec:.1f} tok/s), "
              f"peak {peak_vram_gb:.1f} GB", flush=True)

    log = {
        "model_id": args.model_id, "slug": slug, "use_4bit": args.use_4bit,
        "load_time_s": t_load1 - t_load0, "max_new_tokens": args.max_new_tokens,
        "results": results,
    }
    (LOG_DIR / f"{slug}.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"[{slug}] wrote log to {LOG_DIR / (slug + '.json')}", flush=True)

    del model
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
