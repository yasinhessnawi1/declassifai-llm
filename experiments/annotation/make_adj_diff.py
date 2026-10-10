"""Build an adjudication worksheet from two blind annotations of the same docs.
usage: make_adj_diff.py ann1.jsonl ann2.jsonl docs.jsonl out_prefix
Writes out_prefix_agreed.jsonl ({id, output} of exact (type,span) agreements) and
out_prefix_disputes.md (per doc: A-only / B-only spans, overlapping same-type pairs grouped)."""
import json, sys
a = {json.loads(l)["id"]: json.loads(l)["output"] for l in open(sys.argv[1]) if l.strip()}
b = {json.loads(l)["id"]: json.loads(l)["output"] for l in open(sys.argv[2]) if l.strip()}
docs = {json.loads(l)["id"]: json.loads(l)["text_input"] for l in open(sys.argv[3]) if l.strip()}
ids = [i for i in docs if i in a or i in b]
pre = sys.argv[4]
def pairs(o): return {(t, s) for t, v in o.items() for s in set(v)}
n_agree = n_disp = 0
with open(pre + "_agreed.jsonl", "w") as fa, open(pre + "_disputes.md", "w") as fd:
    for i in ids:
        A, B = pairs(a.get(i, {})), pairs(b.get(i, {}))
        agree = A & B; n_agree += len(agree)
        out = {}
        for t, s in sorted(agree): out.setdefault(t, []).append(s)
        fa.write(json.dumps({"id": i, "output": out}, ensure_ascii=False) + "\n")
        onlyA, onlyB = sorted(A - B), sorted(B - A)
        if not onlyA and not onlyB: continue
        fd.write(f"\n## {i}\n")
        used = set()
        for (t, s) in onlyA:
            partners = [(t2, s2) for (t2, s2) in onlyB if t2 == t and (s in s2 or s2 in s)]
            if partners:
                for p in partners: used.add(p)
                fd.write(f"- BOUNDARY {t}: A=\"{s}\" | B=" + " / ".join(f'"{p[1]}"' for p in partners) + "\n")
            else:
                fd.write(f"- A-only {t}: \"{s}\"\n")
            n_disp += 1
        for (t, s) in onlyB:
            if (t, s) not in used:
                fd.write(f"- B-only {t}: \"{s}\"\n"); n_disp += 1
print(f"{len(ids)} docs, {n_agree} agreed pairs, {n_disp} disputes -> {pre}_disputes.md")
