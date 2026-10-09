"""Multi-label span tagger for the 59-type v2 schema on top of any HF encoder.

Why this shape:
* Spans nest across types (a LOCATION inside an ADDRESS, a CASE_NUMBER inside a CRIMINAL
  clause), so one BIO sequence cannot hold them. Each type gets its own O/B/I head on the
  shared encoder: logits [tokens, types, 3].
* Corpus examples are annotated for only 8 types. Their loss is masked to those types, so
  an un-annotated type is never taught as absent (the same rule as the LLM prompt scope).
* Labels are distinct span strings, not offsets. Every occurrence of a labelled string in
  the document is marked; predictions are turned back into distinct strings, which is
  what tools/score_predictions.py compares.
* Documents run to ~1,500 tokens; they are cut into overlapping windows and the window
  predictions are merged at the character level.

Usage (GPU for training, CPU for inference timing):
    python experiments/tagger/tagger.py train --model ltg/norbert3-small --out models/tagger_norbert3_small
    python experiments/tagger/tagger.py predict --ckpt models/tagger_norbert3_small --device cpu \
        --out evaluation/tagger_norbert3_small/predictions.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from typing import Dict, List, Tuple

import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from v2_schema import v2_types  # noqa: E402

TYPES = v2_types()
T2I = {t: i for i, t in enumerate(TYPES)}
O, B, I = 0, 1, 2


# --------------------------------------------------------------------------- data

def load_jsonl(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def char_tags(text: str, output: Dict[str, List[str]]) -> List[List[Tuple[int, int]]]:
    """Per type, the character spans of every occurrence of every labelled string."""
    spans: List[List[Tuple[int, int]]] = [[] for _ in TYPES]
    for t, strings in output.items():
        if t not in T2I:
            continue
        for s in strings:
            if not s:
                continue
            for m in re.finditer(re.escape(s), text):
                spans[T2I[t]].append((m.start(), m.end()))
    return spans


def windows(tok, text: str, max_len: int, stride: int):
    """Tokenise once and cut into overlapping windows of at most max_len tokens."""
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    body = max_len - 2
    starts = list(range(0, max(1, len(ids) - stride), body - stride)) or [0]
    out = []
    for s in starts:
        e = min(len(ids), s + body)
        out.append((s, e, ids[s:e], offs[s:e]))
        if e == len(ids):
            break
    return out


def encode_example(tok, rec: dict, max_len: int, stride: int):
    text = rec["text_input"]
    scope = rec.get("types") or TYPES
    mask = torch.zeros(len(TYPES), dtype=torch.bool)
    for t in scope:
        if t in T2I:
            mask[T2I[t]] = True
    spans = char_tags(text, rec.get("output") or {})
    items = []
    for _, _, ids, offs in windows(tok, text, max_len, stride):
        labels = torch.zeros(len(ids), len(TYPES), dtype=torch.long)
        for ti, sp in enumerate(spans):
            for (a, b) in sp:
                toks = [k for k, (x, y) in enumerate(offs) if x < y and x < b and y > a]
                if not toks:
                    continue
                labels[toks[0], ti] = B
                for k in toks[1:]:
                    if labels[k, ti] == O:
                        labels[k, ti] = I
        input_ids = [tok.cls_token_id] + ids + [tok.sep_token_id]
        lab = torch.cat([torch.full((1, len(TYPES)), -100), labels, torch.full((1, len(TYPES)), -100)])
        lab[:, ~mask] = -100  # un-annotated types contribute no loss
        items.append((torch.tensor(input_ids), lab))
    return items


def collate(batch, pad_id):
    n = max(len(x) for x, _ in batch)
    ids = torch.full((len(batch), n), pad_id)
    att = torch.zeros((len(batch), n), dtype=torch.long)
    lab = torch.full((len(batch), n, len(TYPES)), -100)
    for i, (x, y) in enumerate(batch):
        ids[i, :len(x)] = x; att[i, :len(x)] = 1; lab[i, :len(x)] = y
    return ids, att, lab


# --------------------------------------------------------------------------- model

def local_base(name: str) -> str:
    """Return a local copy of `name` with safetensors weights.

    Several Norwegian encoders (NorBERT3, mmBERT) ship only pytorch_model.bin, and this
    transformers refuses torch.load on torch < 2.6. Convert once into models/hf_local/.
    """
    if os.path.isdir(name):
        return name
    from huggingface_hub import snapshot_download
    dst = os.path.join(ROOT, "models", "hf_local", name.replace("/", "__"))
    if os.path.exists(os.path.join(dst, "model.safetensors")):
        return dst
    src = snapshot_download(name)
    os.makedirs(dst, exist_ok=True)
    import shutil
    for f in os.listdir(src):
        if not f.endswith(".bin"):
            shutil.copy(os.path.join(src, f), os.path.join(dst, f))
    bin_path = os.path.join(src, "pytorch_model.bin")
    if os.path.exists(bin_path) and not os.path.exists(os.path.join(src, "model.safetensors")):
        from safetensors.torch import save_file
        sd = torch.load(bin_path, map_location="cpu", weights_only=True)
        save_file({k: v.clone().contiguous() for k, v in sd.items()}, os.path.join(dst, "model.safetensors"))
    return dst


class Tagger(nn.Module):
    def __init__(self, name: str):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(local_base(name), trust_remote_code=True)
        h = self.encoder.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.head = nn.Linear(h, len(TYPES) * 3)

    def forward(self, ids, att):
        hs = self.encoder(input_ids=ids, attention_mask=att).last_hidden_state
        return self.head(self.drop(hs)).view(ids.size(0), ids.size(1), len(TYPES), 3)


# --------------------------------------------------------------------------- decode

def decode(text: str, offs, logits: torch.Tensor, acc: Dict[int, List[Tuple[int, int]]]):
    """Turn one window's O/B/I predictions into character spans per type."""
    pred = logits.argmax(-1)  # [tokens, types]
    for ti in range(pred.size(1)):
        col = pred[:, ti].tolist()
        k = 0
        while k < len(col):
            if col[k] == B or (col[k] == I and (k == 0 or col[k - 1] == O)):
                s = k
                k += 1
                while k < len(col) and col[k] == I:
                    k += 1
                a, b = offs[s][0], offs[k - 1][1]
                if b > a:
                    acc.setdefault(ti, []).append((a, b))
            else:
                k += 1


def spans_to_strings(text: str, acc: Dict[int, List[Tuple[int, int]]]) -> Dict[str, List[str]]:
    out = {}
    for ti, sp in acc.items():
        merged = []
        for a, b in sorted(sp):
            if merged and a < merged[-1][1]:  # overlapping windows: keep the union
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        strings = list(dict.fromkeys(text[a:b].strip() for a, b in merged if text[a:b].strip()))
        if strings:
            out[TYPES[ti]] = strings
    return out


@torch.no_grad()
def predict_doc(model, tok, text, max_len, stride, device):
    acc: Dict[int, List[Tuple[int, int]]] = {}
    for _, _, ids, offs in windows(tok, text, max_len, stride):
        x = torch.tensor([[tok.cls_token_id] + ids + [tok.sep_token_id]], device=device)
        logits = model(x, torch.ones_like(x))[0, 1:-1].float().cpu()
        decode(text, offs, logits, acc)
    return spans_to_strings(text, acc)


# --------------------------------------------------------------------------- main

def train(args):
    random.seed(args.seed); torch.manual_seed(args.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda" and args.gpu_fraction:
        # The GPU is shared with the generator session; stay within an agreed cap.
        torch.cuda.set_per_process_memory_fraction(args.gpu_fraction)
    tok = AutoTokenizer.from_pretrained(local_base(args.model), trust_remote_code=True)
    train_recs = load_jsonl(args.train)
    annotated = [r for r in train_recs if r.get("source") != "corpus"]
    train_recs = train_recs + annotated * (args.upsample - 1)
    items = [w for r in train_recs for w in encode_example(tok, r, args.max_len, args.stride)]
    print(f"{len(train_recs)} train docs -> {len(items)} windows", flush=True)
    model = Tagger(args.model).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = math.ceil(len(items) / args.batch) * args.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, s / max(1, int(0.06 * steps))) * max(0.0, (steps - s) / steps))
    scaler = torch.cuda.amp.GradScaler(enabled=dev == "cuda")
    lossf = nn.CrossEntropyLoss(ignore_index=-100)
    step = 0
    for ep in range(args.epochs):
        random.shuffle(items)
        model.train()
        for i in range(0, len(items), args.batch):
            ids, att, lab = collate(items[i:i + args.batch], tok.pad_token_id)
            ids, att, lab = ids.to(dev), att.to(dev), lab.to(dev)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev == "cuda"):
                logits = model(ids, att)
            loss = lossf(logits.float().reshape(-1, 3), lab.reshape(-1))
            opt.zero_grad(); scaler.scale(loss).backward()
            scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step(); step += 1
            if step % 100 == 0:
                print(f"epoch {ep} step {step}/{steps} loss {loss.item():.4f}", flush=True)
    os.makedirs(args.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(args.out, "tagger.pt"))
    tok.save_pretrained(args.out)
    json.dump({"base": args.model, "types": TYPES, "max_len": args.max_len, "stride": args.stride},
              open(os.path.join(args.out, "tagger.json"), "w"))
    print("saved", args.out)


def cpu_budget():
    """Return the CPUs this process may actually use.

    os.cpu_count() reports the host (96 here), but the container's cgroup quota
    allows far fewer; running 96 threads against a 6-CPU quota throttles every
    matmul and made CPU inference ~100x slower than it should be.
    """
    n = len(os.sched_getaffinity(0))
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max":
            n = min(n, int(quota) // int(period))
    except (OSError, ValueError):
        pass
    return max(1, n)


def predict(args):
    meta = json.load(open(os.path.join(args.ckpt, "tagger.json")))
    assert meta["types"] == TYPES, "type list changed since training"
    torch.set_num_threads(cpu_budget())
    tok = AutoTokenizer.from_pretrained(args.ckpt, trust_remote_code=True)
    model = Tagger(meta["base"])
    model.load_state_dict(torch.load(os.path.join(args.ckpt, "tagger.pt"), map_location="cpu"))
    model.to(args.device).eval()
    recs = load_jsonl(args.test)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    t0 = time.time()
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            s = time.time()
            out = predict_doc(model, tok, r["text_input"], meta["max_len"], meta["stride"], args.device)
            f.write(json.dumps({"id": r.get("source", r.get("id")), "output": out,
                                "seconds": round(time.time() - s, 3)}, ensure_ascii=False) + "\n")
    n = sum(p.numel() for p in model.parameters())
    print(f"{len(recs)} docs in {time.time() - t0:.1f}s on {args.device} "
          f"({(time.time() - t0) / len(recs):.2f}s/doc), {n / 1e6:.1f}M params -> {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--model", required=True)
    t.add_argument("--train", default=os.path.join(ROOT, "data/processed_v2/raw/train.jsonl"))
    t.add_argument("--out", required=True)
    t.add_argument("--epochs", type=int, default=4)
    t.add_argument("--batch", type=int, default=16)
    t.add_argument("--lr", type=float, default=5e-5)
    t.add_argument("--max-len", type=int, default=512)
    t.add_argument("--stride", type=int, default=128)
    t.add_argument("--upsample", type=int, default=3)
    t.add_argument("--seed", type=int, default=42)
    t.add_argument("--gpu-fraction", type=float, default=0.2,
                   help="cap on this process's share of GPU memory (shared GPU)")
    p = sub.add_parser("predict")
    p.add_argument("--ckpt", required=True)
    p.add_argument("--test", default=os.path.join(ROOT, "data/processed_v2/raw/test.jsonl"))
    p.add_argument("--device", default="cpu")
    p.add_argument("--out", required=True)
    args = ap.parse_args()
    train(args) if args.cmd == "train" else predict(args)


if __name__ == "__main__":
    main()
