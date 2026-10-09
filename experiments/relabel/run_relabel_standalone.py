"""Standalone teacher relabelling worker (no repo needed).

Inputs in the working dir: meta.json (model name, system prompt, user prefix, type list,
quantisation), docs.jsonl ({digest, text_input}), adapter/ (PEFT adapter).
Output: labels.jsonl, resumable by digest; `touch STOP` exits after the current batch.
Behaviour mirrors experiments/relabel/teacher_label.py: shortest-first, greedy, stop on
<|im_end|>/<|endoftext|>, outer-JSON parse, non-verbatim spans dropped, OOM -> split batch.
"""
import argparse, json, os, re, sys, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--max-new-tokens", type=int, default=1024)
ap.add_argument("--gpu-fraction", type=float, default=None)
args = ap.parse_args()
D = args.dir
meta = json.load(open(os.path.join(D, "meta.json")))
TYPES = meta["types"]

def parse(raw):
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).replace("</think>", "").strip()
    a, b = cleaned.find("{"), cleaned.rfind("}")
    if a >= 0 and b > a:
        cleaned = cleaned[a:b + 1]
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    out = {t: [] for t in TYPES}
    try:
        p = json.loads(cleaned)
        if isinstance(p, dict):
            for t in TYPES:
                v = p.get(t, [])
                if isinstance(v, list):
                    out[t] = [str(x) for x in v]
                elif isinstance(v, str) and v:
                    out[t] = [v]
    except json.JSONDecodeError:
        pass
    return out

out_path = os.path.join(D, "labels.jsonl")
done = set()
if os.path.exists(out_path):
    for l in open(out_path, encoding="utf-8"):
        if l.strip():
            done.add(json.loads(l)["digest"])
todo = [r for r in (json.loads(l) for l in open(os.path.join(D, "docs.jsonl"), encoding="utf-8"))
        if r["digest"] not in done]
todo.sort(key=lambda r: len(r["text_input"]))
print(f"{len(done)} already labelled, {len(todo)} to go", flush=True)

if args.gpu_fraction:
    torch.cuda.set_per_process_memory_fraction(args.gpu_fraction)
q = meta["quant"]
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                         bnb_4bit_quant_type=q["quant_type"], bnb_4bit_use_double_quant=q["double_quant"])
tok = AutoTokenizer.from_pretrained(meta["model"], trust_remote_code=True)
base = AutoModelForCausalLM.from_pretrained(meta["model"], quantization_config=bnb, device_map="auto",
                                            trust_remote_code=True, torch_dtype=torch.float16)
model = PeftModel.from_pretrained(base, os.path.join(D, "adapter")).eval()
tok.padding_side = "left"
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
stops = {tok.eos_token_id}
for s in ("<|im_end|>", "<|endoftext|>"):
    tid = tok.convert_tokens_to_ids(s)
    if isinstance(tid, int) and tid >= 0 and tid != tok.unk_token_id:
        stops.add(tid)
stops = sorted(i for i in stops if i is not None)

def generate(chunk):
    prompts = [tok.apply_chat_template(
        [{"role": "system", "content": meta["system"]},
         {"role": "user", "content": meta["user_prefix"] + r["text_input"]}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in chunk]
    enc = None
    try:
        enc = tok(prompts, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, do_sample=False, max_new_tokens=args.max_new_tokens,
                                 pad_token_id=tok.pad_token_id, eos_token_id=stops)
        return [tok.decode(s, skip_special_tokens=True) for s in gen[:, enc.input_ids.shape[1]:]]
    except torch.cuda.OutOfMemoryError:
        if len(chunk) == 1:
            raise
        enc = None
        torch.cuda.empty_cache()
        h = len(chunk) // 2
        print(f"OOM at batch {len(chunk)}; retrying as {h}+{len(chunk) - h}", flush=True)
        return generate(chunk[:h]) + generate(chunk[h:])

kept = dropped = 0
t0 = time.time()
with open(out_path, "a", encoding="utf-8") as out:
    for i in range(0, len(todo), args.batch):
        if os.path.exists(os.path.join(D, "STOP")):
            print("STOP file found; exiting cleanly", flush=True)
            break
        chunk = todo[i:i + args.batch]
        for r, raw in zip(chunk, generate(chunk)):
            text = r["text_input"]; output = {}
            for t, spans in parse(raw).items():
                ok = [s for s in dict.fromkeys(spans) if s and s in text]
                dropped += len(set(spans)) - len(ok); kept += len(ok)
                if ok:
                    output[t] = ok
            out.write(json.dumps({"digest": r["digest"], "text_input": text, "output": output},
                                 ensure_ascii=False) + "\n")
        out.flush()
        n = i + len(chunk); rate = (time.time() - t0) / n
        print(f"{n}/{len(todo)}  {rate:.1f}s/doc  eta {rate * (len(todo) - n) / 3600:.1f}h  "
              f"kept {kept} dropped-non-verbatim {dropped}", flush=True)
