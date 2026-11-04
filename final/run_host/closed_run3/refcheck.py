import json, sys, time
sys.path.insert(0, "/scratch/final3")
from scorer import compile as C
rows = {json.loads(l)["name"]: json.loads(l) for l in open("/workspace/final3-in/rows.jsonl") if l.strip()}
refs = {json.loads(l)["name"]: json.loads(l).get("heartbeat") for l in open("/workspace/final3-in/heartbeats.jsonl") if l.strip()}
for n in ("Lambda.denote_ext", "PauliMatrix.pauliContr_mul_pauliContrDown_mul_pauliContr"):
    r = rows[n]; pin = next(iter(r["version_info"][0])); t = time.time()
    res = C.compile_project(r, r["src"], pin, timeout=1200)
    print(n, "pin", pin, "ok", res.ok, "hb", res.heartbeats, "ref(run 2)", refs.get(n), "secs", round(time.time() - t, 1), flush=True)
