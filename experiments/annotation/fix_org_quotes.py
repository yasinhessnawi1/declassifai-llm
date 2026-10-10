"""Re-wrap ORGANIZATION spans in the quotes the document prints around them (B35 as corrected)."""
import json, sys, re
Q=[('"','"'),('«','»'),('“','”')]
def fix(text, spans):
    out=[]
    for s in spans:
        if s[:1] in '"«“': out.append(s); continue
        new=s
        for a,b in Q:
            if a+s+b in text: new=a+s+b; break
        out.append(new)
    return list(dict.fromkeys(out))
for path in sys.argv[1:]:
    rows=[json.loads(l) for l in open(path)]; n=0
    for r in rows:
        o=r["output"]
        if "ORGANIZATION" in o:
            f=fix(r["text_input"], o["ORGANIZATION"])
            n+=sum(1 for a,b in zip(o["ORGANIZATION"],f) if a!=b); o["ORGANIZATION"]=f
    with open(path,"w") as fh:
        for r in rows: fh.write(json.dumps(r,ensure_ascii=False)+"\n")
    print(path, "re-quoted", n)
