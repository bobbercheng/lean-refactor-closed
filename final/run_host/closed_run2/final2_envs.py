"""Env dirs closed run 2's rows compile in (every pin), relative to CO/envs. usage: python3 final2_envs.py CO ROWS"""
import json, sys
from pathlib import Path
co = Path(sys.argv[1]); sys.path.insert(0, str(co))
from scorer import compile as C
need = set()
for l in open(sys.argv[2]):
    if not l.strip():
        continue
    r = json.loads(l)
    for d in r.get("version_info") or []:
        pin = next(iter(d))
        p = C.env_dir(pin) if r["source"] == "putnambench" else C.project_env_dir(r["source"], pin)
        need.add(Path(p).relative_to(co / "envs").parts[0])
print("\n".join(sorted(need)))
