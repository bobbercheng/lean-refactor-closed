#!/usr/bin/env python3
"""M1 of docs/auto_brief_plan.md ($0, dev measurement only; the theorem-keyed briefs are an ANSWER KEY here, never shipped): how many of the
briefs' tested facts the auto-brief sweep rediscovers on the warm-up seeds.
Method: a brief fact line is a line with `[tested`, FAIL, fails, worse, "not better" or "->"; its identifiers are the backticked or
bare Lean-looking names in it (dotted names, snake_case with `_`, at least 4 chars). A fact is IN SCOPE when one of its identifiers occurs in
the seed (facts about other lines' later proofs are not reproducible from the seed). It is COVERED when the sweep tested an edit whose label
names one of those identifiers (a deletion of it, or a closer replacing the code that holds it). Agreement: the fact says it fails and the
edit failed, or the fact says it works / is better and the edit compiled.
    python3 probe/autobrief/m1_recall.py probe/autobrief/<tag>"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACT = re.compile(r"\[tested|FAIL|fails|worse|not better|->", re.I)
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_']*(?:\.[A-Za-z0-9_']+)+|[a-z][a-z0-9']*_[a-z0-9_']+")
NEG = re.compile(r"FAIL|fails|unsolved|error|does not|cannot|no progress|recursion", re.I)


def main() -> int:
    out_dir = Path(sys.argv[1])
    rows = {json.loads(l)["name"]: json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if l.strip()}
    tot = {"facts": 0, "in_scope": 0, "covered": 0, "agree": 0, "sweep_facts": 0}
    for name, row in rows.items():
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        bf, af = ROOT / "probe/oline-knowledge" / f"{safe}.md", out_dir / f"{safe}.json"
        if not bf.exists() or not af.exists():
            continue
        ab = json.loads(af.read_text()); edits = ab.get("edits") or []
        seed = row["src"]
        facts = [l for l in bf.read_text().splitlines() if FACT.search(l)]
        n = {"facts": len(facts), "in_scope": 0, "covered": 0, "agree": 0, "sweep_facts": len(edits)}
        for l in facts:
            ids = {i for i in IDENT.findall(l) if len(i) >= 4 and i in seed}
            if not ids:
                continue
            n["in_scope"] += 1
            hit = [e for e in edits if any(i in e["label"] for i in ids)]
            if not hit:
                continue
            n["covered"] += 1
            neg = bool(NEG.search(l))
            if any((not e.get("ok")) == neg for e in hit):
                n["agree"] += 1
        for k in tot:
            tot[k] += n[k]
        print(f"row#{list(rows).index(name):02d} facts {n['facts']:3d} in-scope {n['in_scope']:3d} covered {n['covered']:3d} agree {n['agree']:3d} | sweep edits {n['sweep_facts']}")
    if tot["in_scope"]:
        print(f"TOTAL brief facts {tot['facts']}, in scope {tot['in_scope']} ({100 * tot['in_scope'] / max(1, tot['facts']):.0f}%), covered "
              f"{tot['covered']} ({100 * tot['covered'] / tot['in_scope']:.0f}% of in-scope), agreeing {tot['agree']}; sweep edits measured {tot['sweep_facts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
