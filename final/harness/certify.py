#!/usr/bin/env python3
"""Certify: turn search tactics into the explicit form Lean itself reports (2026-10-18; docs/heartbeat_plan.md item 3).

A search tactic (`simp`, `simp_all`, `simpa`, `grind`, `aesop`) re-runs its search on every check; its `?` form prints
the explicit call it actually needed ("Try this: simp only [a, b]", "Try these: [apply] grind only [...]", an aesop
script). Replacing the tactic by that certificate removes the search: heartbeats drop, tokens may rise. Whether that
pays is the row's exchange rate - which the caller's score gate (harness/postpass.rule_search: primary compile, score
margin, then every listed toolchain with Z unchanged) already prices. This module only GENERATES candidates:

  certify_candidates(evaluate_fn, statement, max_probes=12, token_budget=None, log=None) -> candidate_fn(body)

For each search-tactic site in the body, one probe compile with the site's `?` form (memoised by probe text; at most
`max_probes` probes per row). The site's suggestions (one per goal when the tactic runs under `<;>` / `all_goals`) are
aggregated: identical -> used as is; differing simp / simp_all / grind `only` lists -> merged into one list (union, first
seen order). Suggestions carrying grind anchors (`#ab12`, version-specific) are skipped. Extra config candidates per
site: `gen := n` -> n-1 on grind, `maxDischargeDepth := k` -> k-1 on simp. A candidate whose token increase exceeds the
row's `token_budget` (heartbeat points left / points per token, probe/ceiling/floors.json) can never pay and is dropped
before compiling. Knows no problem or lemma names.

CLI over a finals JSON, measured with the scorer's Evaluator (memgate, every listed toolchain):
  python3 harness/certify.py --input FINALS.json --output OUT.json [--floors probe/ceiling/floors.json] [--max-compiles 60]
"""
from __future__ import annotations

import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.gap_rules import Rule  # noqa: E402
from harness.normalize import _mask, _pairs  # noqa: E402
from scorer.tokenize import count_tokens  # noqa: E402

# keyword -> its query form; longest first so `simp_all` is not read as `simp`
QUERY = {"simp_all": "simp_all?", "simpa": "simpa?", "simp": "simp?", "grind": "grind?", "aesop": "aesop?"}
KW_RE = re.compile(r"(?<![\w.'?])(simp_all|simpa|simp|grind|aesop)(?![\w'?!])")
ANCHOR_RE = re.compile(r"#[0-9a-f]{4}\b")
TRY_RE = re.compile(r"^Try th(?:is|ese):\s*", re.S)


def sites(body: str) -> list[dict]:
    """Search-tactic calls in the body: {start, end, kw, text}. The span runs from the keyword to the end of its line, or past
    the line while a bracket opened on it is unclosed; it stops before `<;>`, `;` or `·` on the same line."""
    mask = _mask(body)
    pairs = _pairs(body, mask)
    out = []
    for m in KW_RE.finditer(body):
        s = m.start()
        if mask[s]:
            continue
        i, e = m.end(), len(body)
        while i < len(body):
            ch = body[i]
            if mask[i]:
                i += 1
                continue
            if ch in "([{⟨" and i in pairs:
                i = pairs[i] + 1
                continue
            if ch == "\n" or body.startswith("<;>", i) or ch == ";" or ch == "·":
                e = i
                break
            i += 1
        else:
            e = len(body)
        text = body[s:e].rstrip()
        out.append({"start": s, "end": s + len(text), "kw": m.group(1), "text": text})
    return out


def _suggestions(messages) -> list[str]:
    """Every suggested tactic (one per goal) from the probe's messages, anchor-carrying options skipped."""
    out = []
    for msg in messages or []:
        d = str(msg.get("data", "") if isinstance(msg, dict) else msg)
        if not TRY_RE.match(d):
            continue
        rest = TRY_RE.sub("", d, count=1)
        opts = re.findall(r"\[apply\]\s*(.+?)(?=\n\s*\[apply\]|\Z)", rest, re.S) if "[apply]" in rest else [rest]
        opts = [o.strip() for o in opts if o.strip()]
        clean = [o for o in opts if not ANCHOR_RE.search(o)]
        if clean:
            out.append(clean[0])
    return out


def _only_list(tac: str) -> tuple[str, list[str], str] | None:
    """Split `<prefix> only [a, b] <suffix>` into (prefix, items, suffix); None when there is no `only [...]`."""
    m = re.search(r"\bonly\s*\[", tac)
    if not m:
        return None
    start = m.end() - 1
    depth, j = 0, start
    while j < len(tac):
        if tac[j] in "([{⟨":
            depth += 1
        elif tac[j] in ")]}⟩":
            depth -= 1
            if depth == 0:
                break
        j += 1
    inner = tac[start + 1:j]
    items, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return tac[:start], items, tac[j + 1:]


def aggregate(kw: str, sugg: list[str]) -> str | None:
    """One replacement for a site from its per-goal suggestions."""
    if not sugg:
        return None
    flat = [re.sub(r"\s+", " ", s).strip() for s in sugg]
    if len(set(flat)) == 1:
        return sugg[0].strip() if kw == "aesop" else flat[0]
    if kw == "aesop":
        return None
    parts = [_only_list(s) for s in flat]
    if any(p is None for p in parts):
        return None
    pre, suf = parts[0][0], parts[0][2]
    if any(p[0] != pre or p[2] != suf for p in parts):
        return None
    seen, items = set(), []
    for _, its, _ in parts:
        for it in its:
            if it not in seen:
                seen.add(it); items.append(it)
    return f"{pre}[{', '.join(items)}]{suf}"


def _reindent(rep: str, body: str, start: int) -> str:
    """Indent the continuation lines of a multi-line replacement (aesop scripts) to the site's column."""
    if "\n" not in rep:
        return rep
    col = start - (body.rfind("\n", 0, start) + 1)
    lines = rep.split("\n")
    return "\n".join([lines[0]] + [" " * col + l.lstrip() for l in lines[1:]])


def config_variants(site: dict) -> list[str]:
    t, out = site["text"], []
    m = re.search(r"\(gen\s*:=\s*(\d+)\)", t)
    if site["kw"] == "grind" and m and int(m.group(1)) > 1:
        out.append(t[:m.start()] + f"(gen := {int(m.group(1)) - 1})" + t[m.end():])
    m = re.search(r"maxDischargeDepth\s*:=\s*(\d+)", t)
    if site["kw"] in ("simp", "simpa", "simp_all") and m and int(m.group(1)) > 1:
        out.append(t[:m.start()] + f"maxDischargeDepth := {int(m.group(1)) - 1}" + t[m.end():])
    return out


def certify_candidates(evaluate_fn, statement: str, max_probes: int = 12, token_budget: float | None = None, log=None):
    """A candidate function for harness.postpass.rule_search (see the module docstring)."""
    state = {"probes": 0, "memo": {}}

    def candidates(body: str) -> list[Rule]:
        out = []
        for st in sites(body):
            probe = body[:st["start"]] + QUERY[st["kw"]] + body[st["start"] + len(st["kw"]):]
            if probe in state["memo"]:
                rep = state["memo"][probe]
            elif state["probes"] >= max_probes:
                rep = None
            else:
                state["probes"] += 1
                try:
                    r = evaluate_fn(statement + " :=" + probe, False)
                except Exception as e:  # noqa: BLE001
                    r = {"error": f"{type(e).__name__}: {e}"}
                rep = aggregate(st["kw"], _suggestions(r.get("messages")))
                state["memo"][probe] = rep
                if log:
                    log(f"  certify probe {st['kw']} @{st['start']}: " + (rep[:70] if rep else (r.get("error") or "no suggestion")[:70]))
            reps = [("certify-" + st["kw"], rep)] if rep and re.sub(r"\s+", " ", rep) != re.sub(r"\s+", " ", st["text"]) else []
            reps += [("config-" + st["kw"], v) for v in config_variants(st)]
            for kind, rp in reps:
                rp = _reindent(rp, body, st["start"])
                delta = count_tokens(rp) - count_tokens(st["text"])
                if token_budget is not None and delta > token_budget:
                    continue
                out.append(Rule(kind, ((st["start"], st["end"] - st["start"], rp),), f"{st['text'][:40]} -> {rp[:50]}", -delta))
        out.sort(key=lambda r: -r.priority)
        return out
    candidates.state = state
    return candidates


def token_budget_for(name: str, floors: dict) -> float | None:
    f = floors.get(name) or {}
    if not f.get("floor") or not f.get("ref_hb") or not f.get("ref_tok"):
        return None
    hb_now = f.get("hb_now")
    if hb_now is None:
        return None
    pts_left = (hb_now - f["floor"]) / f["ref_hb"] * 100 / 3
    return pts_left / (100 / 3 / f["ref_tok"])


def main(argv=None) -> int:
    from harness.hb_tool_eval import load_dataset, Evaluator
    from harness.postpass import rule_search
    from probe.verify_candidates import newest_first
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--output", required=True)
    ap.add_argument("--floors", default=str(ROOT / "probe/ceiling/floors.json"))
    ap.add_argument("--max-compiles", type=int, default=60); ap.add_argument("--max-probes", type=int, default=12)
    ap.add_argument("--min-gain", type=float, default=0.05); ap.add_argument("--problems", nargs="*")
    a = ap.parse_args(argv)
    rows, hbs = load_dataset(ROOT / "data/benchmark_warmup.jsonl", ROOT / "data/benchmark_heartbeats.jsonl")
    floors = json.loads(Path(a.floors).read_text()) if Path(a.floors).exists() else {}
    finals = json.loads(Path(a.input).read_text())
    out, report = {}, []
    for name, item in finals.items():
        if a.problems and name not in a.problems:
            out[name] = item; continue
        row = rows[name]
        versions = newest_first(row["version_info"])
        ev = Evaluator(rows, hbs, max_compiles=1 << 30).bound(name, versions)
        base = ev(item["proof"].strip(), True)
        if not base.get("ok"):
            out[name] = item; report.append({"problem": name, "status": "input does not compile"}); continue
        if floors.get(name) is not None:
            floors[name]["hb_now"] = base.get("heartbeats")
        budget = token_budget_for(name, floors)
        logf = lambda m, n=name: print(f"[{time.strftime('%H:%M:%S')}] {n[:36]}: {m}", flush=True)
        cfn = certify_candidates(ev, row["statement"], max_probes=a.max_probes, token_budget=budget, log=logf)
        r = rule_search(name, item["proof"].strip(), statement=row["statement"], versions=versions, evaluate_fn=ev, candidate_fn=cfn,
                        max_compiles=a.max_compiles, min_gain=a.min_gain, base=base, log=logf)
        after = r.get("after") or {}
        improved = r.get("status") == "improved" and after.get("score") is not None and after["score"] - base["score"] > a.min_gain
        out[name] = ({**item, "proof": r["proof"], "score": after["score"], "L": after.get("L"), "H": after.get("H"), "Z": after.get("Z"),
                      "tokens": after.get("tokens"), "heartbeats": after.get("heartbeats"), "src": "certify"} if improved else item)
        report.append({"problem": name, "status": r.get("status"), "before": base.get("score"), "after": after.get("score"),
                       "hb_before": base.get("heartbeats"), "hb_after": after.get("heartbeats"), "tok_before": base.get("tokens"),
                       "tok_after": after.get("tokens"), "probes": cfn.state["probes"], "compiles": r.get("compiles"), "budget": budget,
                       "applied": r.get("applied")})
        logf(f"{r.get('status')} {base.get('score')} -> {after.get('score')} (hb {base.get('heartbeats')} -> {after.get('heartbeats')}, "
             f"tokens {base.get('tokens')} -> {after.get('tokens')}, probes {cfn.state['probes']})")
        Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=1))
        Path(a.output).with_suffix(".report.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in report))
    n = len(finals)
    print(json.dumps({"rows": n, "improved": sum(1 for x in report if x.get("status") == "improved"),
                      "mean_before": round(sum(float(v["score"]) for v in finals.values()) / n, 3),
                      "mean_after": round(sum(float(v["score"]) for v in out.values()) / n, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
