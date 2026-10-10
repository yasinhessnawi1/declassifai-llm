"""B1: keep a directly preceding 'innrømmet'/'erkjente' (+ 'å ha') at the start of CRIMINAL spans."""
import json, re, sys
PAT=re.compile(r"(?:innrømmet|innrømte|erkjente|erkjent)(?: (?:under inspeksjonen|også))?(?: å ha)? $")
for path in sys.argv[1:]:
    rows=[json.loads(l) for l in open(path)]; n=0
    for r in rows:
        t=r["text_input"]; cr=r["output"].get("CRIMINAL")
        if not cr: continue
        new=[]
        for s in cr:
            i=t.find(s); ext=s
            if i>0:
                m=PAT.search(t[max(0,i-60):i])
                if m: ext=t[i-len(m.group(0)):i]+s; n+=1
            new.append(ext)
        r["output"]["CRIMINAL"]=list(dict.fromkeys(new))
    with open(path,"w") as fh:
        for r in rows: fh.write(json.dumps(r,ensure_ascii=False)+"\n")
    print(path,"extended",n)
