"""Label the remaining corpus documents with the v2 teacher (Qwen3.5-9B QLoRA).

On the 400 gold documents the teacher scores 0.814 exact / 0.907 lenient F1, against
0.521 / 0.705 for the corpus's own Gemini labels, and it beats them type by type even on
the types the corpus was trusted for (SEXUAL_ORIENTATION 0.857 vs 0.538 exact, ADDRESS
0.972 vs 0.903). So the enhanced corpus takes the teacher's labels for all 59 types.

Batched greedy generation with left padding; prompts rendered exactly as in training
(no think block); generation stops on <|im_end|>. Documents run shortest first so each
batch pads little, and a batch that runs out of GPU memory is split in half and retried
(plain Qwen3.5-9B peaks at ~29.5 GB on a 7k-token prompt). Any predicted string that is not a
verbatim substring of the document is dropped and counted. Resumable: documents already
in the output file are skipped, so the job can be stopped and restarted (the GPU is shared).

Usage:
    python experiments/relabel/teacher_label.py --out data/corpus_v2_teacher/labels.jsonl
    touch data/corpus_v2_teacher/STOP    # stop gracefully after the current batch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from src.config_loader import load_config  # noqa: E402
from src.evaluator import load_model_for_eval, _parse_output, _stop_ids  # noqa: E402
from src.prompt_builder import build_inference_messages  # noqa: E402


def corpus_docs(path_clean: str, held: set):
    import hashlib
    for line in open(path_clean, encoding="utf-8"):
        r = json.loads(line)
        d = hashlib.md5(r["text_input"].encode()).hexdigest()
        if d not in held:
            yield d, r["text_input"]


def generate(model, tok, cfg, chunk, stops, args):
    """Decode one batch; on CUDA OOM split it in half and retry each half."""
    prompts = [tok.apply_chat_template(build_inference_messages(t, cfg), tokenize=False,
                                       add_generation_prompt=True, enable_thinking=False)
               for _, t in chunk]
    enc = None
    try:
        enc = tok(prompts, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, do_sample=False, max_new_tokens=args.max_new_tokens,
                                 pad_token_id=tok.pad_token_id, eos_token_id=stops)
        return [tok.decode(seq, skip_special_tokens=True) for seq in gen[:, enc.input_ids.shape[1]:]]
    except torch.cuda.OutOfMemoryError:
        if len(chunk) == 1:
            raise
        enc = None
        torch.cuda.empty_cache()
        half = len(chunk) // 2
        print(f"OOM at batch {len(chunk)}; retrying as {half}+{len(chunk) - half}", flush=True)
        return (generate(model, tok, cfg, chunk[:half], stops, args)
                + generate(model, tok, cfg, chunk[half:], stops, args))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(ROOT, "configs/config_v2.yaml"))
    ap.add_argument("--clean", default=os.path.join(ROOT, "data/processed_v2/corpus_clean_v2.jsonl"),
                    help="output of tools/clean_corpus.py (one record per distinct text)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--gpu-fraction", type=float, default=None,
                    help="cap this process's share of GPU memory so a shared GPU keeps headroom "
                         "for other jobs; an over-cap batch is split like any other OOM")
    args = ap.parse_args()

    import glob, hashlib
    held = set()
    for pat in ("data/gold_v2/*.jsonl", "data/slice_v2/*.jsonl"):
        for p in glob.glob(os.path.join(ROOT, pat)):
            for l in open(p, encoding="utf-8"):
                held.add(hashlib.md5(json.loads(l)["text_input"].encode()).hexdigest())

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    done = set()
    if os.path.exists(args.out):
        for l in open(args.out, encoding="utf-8"):
            if l.strip():
                done.add(json.loads(l)["digest"])
    todo = [(d, t) for d, t in corpus_docs(args.clean, held) if d not in done]
    if args.limit:
        todo = todo[: args.limit]
    todo.sort(key=lambda x: len(x[1]))
    print(f"{len(done)} already labelled, {len(todo)} to go", flush=True)

    if args.gpu_fraction and torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(args.gpu_fraction)
    cfg = load_config(args.config)
    model, tok = load_model_for_eval(cfg)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    stops = _stop_ids(tok)
    stop_file = os.path.join(os.path.dirname(args.out), "STOP")
    dropped = kept = 0
    t0 = time.time()
    with open(args.out, "a", encoding="utf-8") as out:
        for i in range(0, len(todo), args.batch):
            if os.path.exists(stop_file):
                print("STOP file found; exiting cleanly", flush=True)
                break
            chunk = todo[i:i + args.batch]
            for (digest, text), raw in zip(chunk, generate(model, tok, cfg, chunk, stops, args)):
                parsed = _parse_output(raw, cfg)
                output = {}
                for t, spans in parsed.items():
                    ok = [s for s in dict.fromkeys(spans) if s and s in text]
                    dropped += len(set(spans)) - len(ok); kept += len(ok)
                    if ok:
                        output[t] = ok
                out.write(json.dumps({"digest": digest, "text_input": text, "output": output},
                                     ensure_ascii=False) + "\n")
            out.flush()
            n = i + len(chunk)
            rate = (time.time() - t0) / n
            # shortest documents run first, so this ETA is optimistic early on
            print(f"{n}/{len(todo)}  {rate:.1f}s/doc  eta {rate * (len(todo) - n) / 3600:.1f}h  "
                  f"kept {kept} dropped-non-verbatim {dropped}", flush=True)


if __name__ == "__main__":
    main()
