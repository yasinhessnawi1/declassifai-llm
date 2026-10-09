#!/usr/bin/env bash
# Prepare relabelling shard 1/2 and start it on the second V100 (anward/tm-to-llm).
# Workloads only: sends the standalone worker, the prompt metadata, the adapter weights and the
# shard-1 corpus documents. No repository code or docs leave this box.
# Run from llm_finetune/:   bash experiments/relabel/send_shard_to_remote.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
CODER=/tmp/coder.cWJGKt/coder
HOST=anward/tm-to-llm.main
B=$(mktemp -d)
trap 'rm -rf "$B"' EXIT

myenv/bin/python - "$B" <<'EOF'
import sys, json, glob, hashlib, os
sys.path.insert(0, "."); sys.path.insert(0, "experiments/relabel")
from src.config_loader import load_config
from src.prompt_builder import build_inference_messages
from teacher_label import corpus_docs
B = sys.argv[1]
cfg = load_config("configs/config_v2.yaml")
a = build_inference_messages("Hei A", cfg)
system, prefix = a[0]["content"], a[1]["content"][:-len("Hei A")]
json.dump({"model": cfg.model.name, "system": system, "user_prefix": prefix,
           "types": list(cfg.entity_types),
           "quant": {"quant_type": cfg.model.bnb_4bit_quant_type,
                     "double_quant": cfg.model.bnb_4bit_use_double_quant}, "shard": "1/2"},
          open(os.path.join(B, "meta.json"), "w"), ensure_ascii=False, indent=1)
held = set()
for pat in ("data/gold_v2/*.jsonl", "data/slice_v2/*.jsonl"):
    for p in glob.glob(pat):
        for l in open(p, encoding="utf-8"):
            held.add(hashlib.md5(json.loads(l)["text_input"].encode()).hexdigest())
done = {json.loads(l)["digest"] for l in open("data/corpus_v2_teacher/labels.jsonl") if l.strip()}
n = 0
with open(os.path.join(B, "docs.jsonl"), "w", encoding="utf-8") as f:
    for d, t in corpus_docs("data/processed_v2/corpus_clean_v2.jsonl", held):
        if int(d, 16) % 2 == 1 and d not in done:
            assert build_inference_messages(t, cfg)[1]["content"] == prefix + t
            f.write(json.dumps({"digest": d, "text_input": t}, ensure_ascii=False) + "\n"); n += 1
print(f"shard 1/2: {n} documents")
EOF

R='~/declassifai/relabel'
$CODER ssh $HOST "mkdir -p $R/adapter"
$CODER ssh $HOST "cat > $R/meta.json" < "$B/meta.json"
$CODER ssh $HOST "cat > $R/docs.jsonl" < "$B/docs.jsonl"
$CODER ssh $HOST "cat > $R/adapter/adapter_config.json" < models/qlora_adapter_v2/adapter_config.json
$CODER ssh $HOST "cat > $R/adapter/adapter_model.safetensors" < models/qlora_adapter_v2/adapter_model.safetensors
$CODER ssh $HOST "cd $R && wc -l docs.jsonl && ls -la adapter && HF_HOME=~/declassifai/hf setsid nohup ../venv/bin/python run_relabel.py --batch 16 > run.log 2>&1 < /dev/null & echo started"
echo "Remote shard running. Progress: $CODER ssh $HOST 'tail -2 $R/run.log'"
