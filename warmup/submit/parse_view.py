#!/usr/bin/env python3
"""Extract one submission's worker results from `submit/upload.py view` output.
  python3 submit/upload.py view > view.json; python3 submit/parse_view.py view.json "02:29 UTC" --out results.json
Prints the combined score; writes the per-problem rows [problem, result, score, length, L%, heartbeats, H%, zeroshot, notes]
in the format submit/ledger.py scored --results expects."""
import argparse, html, json, re, sys

ap = argparse.ArgumentParser(); ap.add_argument("view_json"); ap.add_argument("header", help='e.g. "02:29 UTC"'); ap.add_argument("--out")
a = ap.parse_args()
s = json.load(open(a.view_json))[0]
i = s.find(a.header)
if i < 0:
    sys.exit(f"header {a.header!r} not found")
nxt = re.search(r"\d\d:\d\d UTC", s[i + 20:]); seg = s[i: i + 20 + nxt.start()] if nxt else s[i:]
m = re.search(r"Combined\s*([\d.]+)%", html.unescape(re.sub(r"<[^>]+>", " ", seg)))
rows = []
for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S):
    cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td))).strip() for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
    if len(cells) == 9 and cells[0] != "Problem":
        rows.append(cells)
print(f"combined: {m.group(1) if m else 'n/a'} | rows: {len(rows)} | compiled: {sum(1 for r in rows if r[1] == 'Compiled')}")
if a.out:
    json.dump(rows, open(a.out, "w"), indent=0); print("wrote", a.out)
