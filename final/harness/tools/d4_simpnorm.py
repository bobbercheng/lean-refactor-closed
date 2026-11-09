#!/usr/bin/env python3
"""Bet D4N, "simpnorm" (docs/closed_run2.md, closed-bets-d4 2026-11-02: a research move distilled into a generic rule): an end-stage
family ("simpnorm", registered only by harness/end_d4.register() with the sub-switch D4N, never by default) with the
harness/sweep.candidates contract and an ENV QUERY (harness/endstage.py QUERY_FAMILIES; without an answer the family proposes nothing).

The rule: a simp-family call whose output a decide-family closer then decides (`decide` with `+flag` / `-flag` options, never `+native`)
hands the kernel whatever normal form its lemma list reaches. A few CORE ALGEBRAIC NORMALISATION lemmas appended to that list (GENERIC:
generic Mathlib vocabulary, the same for every row: `0 * a`, `a * 0`, `1 * a`, `a * 1`, `0 + a`, `a + 0`, `-a * b`, `a * -b`,
`ite` times / by a term, scalar multiplication as multiplication) can pre-normalise the goal so the closer's decision is cheaper. Which
ones, and in which direction, is the row's: Lean says which of them its simp set used.

  sites     the proof's decide-family closers (harness/tools/d4_closerprep.closer_sites: alone on their line, ending their tactic block)
            and, for each, the MAX_LISTS nearest simp-family lemma lists before it (d4_closerprep.simp_lists; heads with a search variant
            only: simp / simp_all / simpa / dsimp, and norm_num read through simp's own variant; never field_simp or a `!` head), at
            tactic position; a generic lemma already among its items is not appended again (either direction).
  query     three plain compiles after the row's file prefix (Meter.command, the primary pin), each charged to the tool phase and the
            family's cap:
              1. existence: one `#eval` that resolves every GENERIC name in the row's own scope, keeps those that are theorems (or, under
                 Lean's module system, imported theorems read as axioms) and passes the AXIOM GATE (harness/tools/d4_kit.axiom_ok; a real
                 `axiom` or a sorried theorem is reported, LRAD4NAX, and never written);
              2. usage (only with at least one name kept): per list and orientation ("fwd": every kept lemma as stated; "rev": the
                 REVERSIBLE ones reversed (`← l`), their forward forms and SMUL_FWD left out) one `example` with the row's statement whose
                 proof is the incumbent's text up to that call, the call's head replaced by its search variant (`simp?`; norm_num ->
                 `simp?`) and the kept lemmas appended to its list, cut right after the call; a marker message (LRAD4NPROBE, an `#eval`)
                 before each example. Lean's "Try this" message after a marker names the lemmas that simp set USED; the used generic lemmas of
                 that probe are its set U (GENERIC order). Unsolved goals after the cut are expected (only the message is read);
              3. measurement (some lemma used): the space below, read in one file (harness/tools/d4_measure.py: every variant
                 elaborated in one `#eval` between two heartbeat readings, ok = no sorryAx; the incumbent first as the control; at most
                 d4_measure.budget(ctx) variants): a probe's usage does not say which lemmas make the decision cheaper, a reading does.
  space     per list, U being the lemmas its probes found used (both orientations; a lemma never with its own reverse): each one
            alone, then every pair, then U itself when it holds three; the lists round robin. U whole is not in it: every lemma costs two
            tokens and the set a probe finds used is wider than the few that make the decision cheaper; a larger set is reached by the
            end stage's greedy passes (after a bank the next pass probes and measures the new incumbent, whose appended lemmas are no
            longer extras).
  generate  simpnorm:append   the measured subsets predicted to read higher than the control (d4_measure.predicted: heartbeats saved
                              minus tokens added times the row's exchange rate), best first, at most PROPOSE, appended to the list (the
                              call's own head kept).
The caller measures every candidate back to back with its incumbent (batch screen with the heartbeat bound, paired decide, all-pin
confirmation). No harm: no site, no answer, a timeout or a budget stop proposes nothing and never changes the final. Generic by
construction: the lemma names written are GENERIC's (the same for every row) and only those the row's environment holds and its simp set
used; nothing else is read but the proof, the statement and Lean's messages."""
from __future__ import annotations

import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.normalize import _mask, _pairs, OPEN  # noqa: E402
from harness.tools import d4_kit as K  # noqa: E402
from harness.tools import d4_closerprep as CP  # noqa: E402
from harness.tools import d4_measure as MS  # noqa: E402
from harness.tools.d4_implied import example_decl  # noqa: E402
from harness.tools.d4_search import TRY_THIS, suggestions  # noqa: E402
from scorer.tokenize import split_declaration  # noqa: E402

FAMILY = "simpnorm"
OPS = ("simpnorm:append",)
ALL_OPS = OPS
OPT_IN_OPS: tuple = ()
DEFAULT_OPS = OPS
QUERY_OPS = OPS
TABLES: dict = {}
# generic Mathlib vocabulary (core algebraic normalisation; the same list for every row; checked in the row's environment):
GENERIC = ("zero_mul", "mul_zero", "one_mul", "mul_one", "zero_add", "add_zero", "neg_mul", "mul_neg", "ite_mul", "mul_ite",
           "smul_eq_mul", "zsmul_eq_mul", "nsmul_eq_mul")
REVERSIBLE = ("zsmul_eq_mul", "nsmul_eq_mul")   # also tried reversed (an integer / natural cast times a term -> a scalar product)
SMUL_FWD = ("smul_eq_mul",)                     # left out of the reversed probe (it would undo a reversed lemma's output)
MAX_PER_OP = 8
PROPOSE = 3            # proposals per incumbent (the best predicted)
MAX_LISTS = 2
QUERY_TIMEOUT = 300
PROBE_HEADS = {"simp": "simp?", "simp_all": "simp_all?", "simpa": "simpa?", "dsimp": "dsimp?", "norm_num": "simp?"}

EXIST_QUERY = r'''theorem lraD4NQueryDummy : True := trivial

set_option maxHeartbeats 2000000 in
#eval show Lean.Elab.Command.CommandElabM Unit from do
  let names : List String := [LRAD4NNAMES]
  let env ← Lean.getEnv
  let mut out : String := ""
  for h in names do
    let r ← Lean.Elab.Command.liftTermElabM do
      try
        let n ← Lean.resolveGlobalConstNoOverload (Lean.mkIdent h.toName)
        pure (some n)
      catch _ => pure none
    match r with
    | none => pure ()
    | some n =>
      let thm := match env.find? n with
        | some (.thmInfo _) => true
        | some (.axiomInfo _) => true
        | _ => false
      if thm then
        if (← Lean.collectAxioms n).all (fun a => LRAD4AXOK) then
          out := out ++ s!"LRAD4NOK\t{h}\t{n}\n"
        else
          out := out ++ s!"LRAD4NAX\t{h}\t{n}\n"
  Lean.logInfo (Lean.toMessageData ("LRAD4NBEGIN\n" ++ out ++ "LRAD4NEND"))
'''
PROBE_DUMMY = "theorem lraD4NProbeDummy : True := trivial\n"
MARK = "LRAD4NPROBE"


def _item_name(it: str) -> str:
    return re.sub(r"^(?:[↓↑]\s*)*(?:←\s*|<-\s*)?", "", it.strip()).strip()


def sites(body: str) -> list[dict]:
    """[{"L": a d4_closerprep.simp_lists list, "site": its closer, "present": the GENERIC names already among its items}] (module
    docstring, "sites"), the nearest list of the last closer first; each list once."""
    out, seen = [], set()
    for s in CP.closer_sites(body):
        for L in CP.simp_lists(body, before=s["line_start"], max_lists=MAX_LISTS, min_items=0):
            if L["lb"] in seen or L["head"] not in PROBE_HEADS or L["bang"]:
                continue
            seen.add(L["lb"])
            names = {_item_name(body[a:b]) for a, b in L["items"]}
            out.append({"L": L, "site": s, "present": sorted(names & set(GENERIC))})
    return out[:MAX_LISTS]


def _call_end(body: str, L: dict) -> int:
    """The end of the call whose list is L: the rest of the `]`'s line (` at h`, ` using e`) up to a top-level `;` / `<;>` or a comment."""
    mask = _mask(body)
    i = L["rb"] + 1
    while i < len(body) and body[i] != "\n" and not mask[i] and body[i] != ";" and not body.startswith("<;>", i):
        i += 1
    while i > L["rb"] + 1 and body[i - 1] in " \t":
        i -= 1
    return i


def appended(body: str, L: dict, extra: list[str]) -> str:
    """The body with `extra` appended to list L (its own items kept as written; offsets before L's `]` unchanged)."""
    if not body[L["lb"] + 1:L["rb"]].strip():
        return body[:L["lb"] + 1] + ", ".join(extra) + body[L["rb"]:]
    j = L["rb"]
    while j > L["lb"] + 1 and body[j - 1] in " \t\n":
        j -= 1
    return body[:j] + ", " + ", ".join(extra) + body[j:]


def orientations(kept: list[str], present=()) -> list[tuple[str, list[str]]]:
    """[("fwd", lemmas), ("rev", lemmas)] for the kept GENERIC names not already in the list (module docstring, "query" 2); "rev" only
    when a REVERSIBLE one is among them."""
    avail = [g for g in GENERIC if g in kept and g not in set(present)]
    out = [("fwd", avail)] if avail else []
    if any(g in avail for g in REVERSIBLE):
        out.append(("rev", [("← " + g) if g in REVERSIBLE else g for g in avail if g not in SMUL_FWD]))
    return out


def probe_body(body: str, L: dict, extra: list[str]) -> str | None:
    """The incumbent's body up to L's call, its head replaced by the search variant and `extra` appended, cut after the call; None when
    the cut leaves a bracket open or the body is not a tactic block."""
    if not re.match(r"^\s*by(?![\w'])", body):
        return None
    nb = appended(body, L, extra)
    nb = nb[:_call_end(body, L) + len(nb) - len(body)]
    nb = nb[:L["h0"]] + PROBE_HEADS[L["head"]] + nb[L["h1"]:]
    m = _mask(nb)
    if len(_pairs(nb, m)) != sum(1 for i, ch in enumerate(nb) if ch in OPEN and not m[i]):
        return None
    return nb


def exist_text(names) -> str:
    return EXIST_QUERY.replace("[LRAD4NNAMES]", "[" + ", ".join(K.lean_str(n) for n in names) + "]").replace("LRAD4AXOK", K.axiom_ok("a"))


def probe_text(proof: str, statement: str, kept: list[str]) -> tuple[str | None, list[dict]]:
    """(the usage query's text, [{"k", "lb", "orient", "extra"}] per probe), or (None, []) without a probe."""
    body = split_declaration(proof, statement)
    ex = example_decl(statement)
    if body is None or ex is None:
        return None, []
    parts, probes = [PROBE_DUMMY], []
    for st in sites(body):
        L = st["L"]
        for orient, extra in orientations(kept, st["present"]):
            pb = probe_body(body, L, extra)
            if pb is None:
                continue
            k = len(probes)
            probes.append({"k": k, "lb": L["lb"], "orient": orient, "extra": list(extra)})
            parts.append(f'\n#eval show Lean.Elab.Command.CommandElabM Unit from Lean.logInfo "{MARK}\\t{k}"\n\n{ex.rstrip()} :={pb}\n')
    return ("".join(parts) if probes else None), probes


def parse_exist(messages) -> dict:
    out = {"answered": False, "kept": {}, "axioms": []}
    for m in messages or []:
        d = K.msg_text(m)
        if "LRAD4NBEGIN" not in d or "LRAD4NEND" not in d:
            continue
        out["answered"] = True
        for ln in d.split("\n"):
            p = ln.split("\t")
            if len(p) == 3 and p[1].strip() in GENERIC and K.IDENT_RE.match(p[2].strip()):
                if p[0] == "LRAD4NOK":
                    out["kept"][p[1].strip()] = p[2].strip()
                elif p[0] == "LRAD4NAX":
                    out["axioms"].append(p[2].strip())
        break
    return out


def _used(sug: str, lemma: str) -> bool:
    """`lemma` (`l` or `← l`) appears in the suggestion with that orientation."""
    rev = lemma.startswith("←")
    name = lemma.lstrip("← ").strip()
    for m in re.finditer(r"(?<![\w.'])%s(?![\w'.₀-₉])" % re.escape(name), sug):
        before = sug[:m.start()].rstrip()
        arrow = before.endswith("←") or before.endswith("<-")
        if arrow == rev:
            return True
    return False


def parse_probes(messages, probes: list[dict]) -> dict:
    """{probe k: [used lemmas, GENERIC order]} from the markers and the Try-this messages after them (position order)."""
    ms = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        pos = m.get("pos") or {}
        if not isinstance(pos.get("line"), int):
            continue
        ms.append((pos["line"], pos.get("column") if isinstance(pos.get("column"), int) else 0, K.msg_text(m), m.get("severity")))
    ms.sort(key=lambda x: (x[0], x[1]))
    cur, out = None, {}
    by_k = {p["k"]: p for p in probes}
    for _, _, d, sev in ms:
        mk = re.match(r"^%s\t(\d+)\s*$" % MARK, d.strip())
        if mk:
            cur = int(mk.group(1)) if int(mk.group(1)) in by_k else None
            continue
        if cur is None or sev not in ("information", "info") or not TRY_THIS.match(d) or cur in out:
            continue
        sug = " ".join(suggestions(d))
        out[cur] = [e for e in by_k[cur]["extra"] if _used(sug, e)]
    return out


def query(proof: str, statement: str, run, *, versions=None, ctx: dict | None = None, stats: dict | None = None, log=None) -> dict | None:
    """The env query (module docstring). Always returns {"simpnorm_query": {...}, "simpnorm_query_for": key}; no site: no compile."""
    st = stats if stats is not None else {}
    log = log or (lambda *a: None)
    t0 = time.time()
    key = K.proof_key(proof)
    body = split_declaration(proof, statement)
    q = {"answered": False, "kept": {}, "probes": [], "used": {}, "control": None, "variants": []}
    ss = sites(body) if body is not None else []
    if not ss or example_decl(statement) is None or not re.match(r"^\s*by(?![\w'])", body or ""):
        q["skip"] = "no simp-family list before a decide-family closer in a theorem's tactic proof"
        st["query"] = {"ids": 0, "used": 0, "vars": 0, "class_vars": 0, "skip": q["skip"]}
        return {"simpnorm_query": q, "simpnorm_query_for": key}
    vs = list(versions or [None])
    r = run(exist_text(GENERIC), vs[0])
    pe = parse_exist(getattr(r, "messages", None))
    q["kept"] = dict(pe["kept"])
    if not pe["answered"]:
        q["skip"] = "the existence check did not answer: " + str((getattr(r, "errors", None) or ["?"])[0])[:160]
    elif not pe["kept"]:
        q["skip"] = "no generic lemma in this environment"
    else:
        text, probes = probe_text(proof, statement, list(pe["kept"]))
        q["probes"] = probes
        if text is None:
            q["skip"] = "no probe could be cut"
        else:
            r2 = run(text, vs[0])
            used = parse_probes(getattr(r2, "messages", None), probes)
            q["used"] = {str(k): v for k, v in used.items()}
            if not any(used.values()):
                q["skip"] = "no probe printed a suggestion naming a generic lemma"
            else:   # 3. the subsets measured in one file (harness/tools/d4_measure.py), the incumbent first
                space = subset_space(body, q)[:MS.budget(ctx) - 1]
                mt = MS.text(statement, [body] + [x[1] for x in space])
                r3 = run(mt, vs[0]) if mt is not None else None
                rd = MS.parse(getattr(r3, "messages", None), len(space) + 1)
                q["control"] = rd.get(0) or {"ok": False}
                q["variants"] = [{"lemmas": lem, "body": nb, "note": note, **(rd.get(i) or {"ok": False, "hb": None})}
                                 for i, (lem, nb, note) in enumerate(space, 1)]
                q["answered"] = bool(q["control"].get("ok"))
                if not q["answered"]:
                    q["skip"] = "the control did not read in the measuring file"
    q["seconds"] = round(time.time() - t0, 2)
    nu = sum(len(v) for v in q["used"].values())
    st["query"] = {"ids": len(GENERIC), "used": len(q["kept"]), "vars": nu, "class_vars": 0, "seconds": q["seconds"],
                   **({"skip": q["skip"]} if q.get("skip") else {})}
    log(f"simpnorm: env query {len(ss)} list(s): {len(q['kept'])} generic lemma(s) kept, {len(q['probes'])} probe(s), "
        f"used {q['used']}; {len(q['variants'])} subset(s) measured, {sum(1 for v in q['variants'] if v.get('ok'))} read, control "
        f"{(q.get('control') or {}).get('hb')} in {q['seconds']} s" + (f" ({q['skip']})" if q.get("skip") else "")
        + (f"; dropped by the axiom gate: {pe['axioms']}" if pe.get("axioms") else ""))
    return {"simpnorm_query": q, "simpnorm_query_for": key}


def used_union(q: dict, lb: int) -> list[str]:
    """The lemmas the probes of list `lb` found used, both orientations merged: GENERIC order, a lemma's forward spelling before its
    reversed one."""
    got = set()
    for p in q.get("probes") or []:
        if p.get("lb") == lb:
            got |= {x for x in (q.get("used") or {}).get(str(p["k"])) or [] if x in p["extra"]}
    return [x for g in GENERIC for x in (g, "← " + g) if x in got]


def subsets(U: list[str]) -> list[list[str]]:
    """The small subsets of U to append (module docstring, "generate"): each lemma alone, then every pair (never a lemma with its own
    reverse), then U itself when it has three lemmas; U's order inside each."""
    base = lambda x: x.lstrip("← ").strip()   # noqa: E731
    out = [[x] for x in U]
    out += [[a, b] for i, a in enumerate(U) for b in U[i + 1:] if base(a) != base(b)]
    if len(U) == 3 and len({base(x) for x in U}) == 3:
        out.append(list(U))
    return out


def subset_space(body: str, q: dict) -> list[tuple[list[str], str, str]]:
    """[(lemmas, body with them appended, note)]: subsets() of each list's used lemmas, the lists round robin."""
    seqs = []
    for st in sites(body):
        L = st["L"]
        U = used_union(q, L["lb"])
        if U:
            seqs.append([(x, appended(body, L, x), f"{', '.join(x)} appended to `{L['head']}` @L{K.line_of(body, L['h0'])}")
                         for x in subsets(U)])
    return [seq[k] for k in range(max([len(x) for x in seqs] or [0])) for seq in seqs if k < len(seq)]


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int | None = None,
               ctx: dict | None = None) -> list[dict]:
    ctx = ctx or {}
    ops = K.ops_for(FAMILY, OPS, DEFAULT_OPS, OPT_IN_OPS, ctx)
    hb = K.head_body(proof, statement)
    if hb is None or "simpnorm:append" not in ops:
        return []
    head, body = hb
    q = ctx.get("simpnorm_query")
    if not (q and ctx.get("simpnorm_query_for") == K.proof_key(proof) and q.get("answered")):
        return []
    ex = exchange if exchange is not None else ctx.get("exchange")
    preds = []
    for v in q.get("variants") or []:
        pr = MS.predicted(q.get("control") or {}, body, v.get("body") or "", v, ex)
        if pr is not None and pr > 0:
            preds.append((pr, v))
    preds.sort(key=lambda x: -x[0])
    em = K.Emitter(proof, statement, head, body, int(max_per_op) if max_per_op else MAX_PER_OP)
    n = 0
    for pr, v in preds:
        if n >= PROPOSE:
            break
        if em.add("simpnorm:append", v["body"], f"{v['note']} (query: {v['hb']} hb, predicted +{pr:.0f})", save=False):
            n += 1
    return em.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="simpnorm: the sites of one declaration and its query texts (no compile)")
    ap.add_argument("--file", required=True); ap.add_argument("--statement-file", required=True)
    ap.add_argument("--query", action="store_true", help="print the usage probe text, every generic lemma assumed present")
    a = ap.parse_args(argv)
    proof = Path(a.file).read_text(); stmt = Path(a.statement_file).read_text().rstrip("\n")
    body = split_declaration(proof, stmt) or ""
    for s in sites(body):
        print(json.dumps({"head": s["L"]["head"], "items": len(s["L"]["items"]), "closer": s["site"]["closer"]}, ensure_ascii=False))
    if a.query:
        print(probe_text(proof, stmt, list(GENERIC))[0] or "(no probe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
