#!/usr/bin/env python3
"""C2: class-namespace lemma variants + a compile-gated stack (b71 R2; docs/tail_signal_study.md sections 3 and 4.4;
2026-10-28). An end-stage FINAL family (harness/endstage.py FAMILIES "c2", tier 2): it
runs once, after every other tool family's passes, so it never changes what those families bank; it only adds banks on top.

Why: on the closed final's warm-up finals, swapping a lemma for its same-name variant in a type-class namespace (`f` -> `C.f` where `C`
is a class, i.e. the instance-field form of the generic lemma) saved heartbeats at unchanged tokens, and the compiled winners of one row
combined (stacked) near-additively (a few hundredths per row on the warm-up finals; less on held-out finals).

  query     (harness/endstage.py env_query: plain compiles on the meter's own path, no measurement) one Lean `#eval` placed after the row's
            file prefix, in the declaration's own namespace / `open` context, resolves every identifier of the proof (and its statement)
            to global constants (Lean.resolveGlobalName) and scans the row's environment for theorems whose last name component equals
            the last component `f` of a used theorem, or is `f_of_*` or `f'` (the variant shapes), each with Lean.isClass of its
            namespace. The primary pin first; the other pins only when the primary found a class variant; a variant is kept only when it
            is a theorem on EVERY pin that answered (a pin whose query fails filters nothing: the all-pin confirmation still gates).
  generate  signal C2: a variant whose namespace (Name.getPrefix) is a type class in the row's own environment; one candidate per (site,
            variant): one term occurrence of the used identifier in the proof body replaced by the variant's full name (op c2:swap).
            Deterministic order (the `f_of_*` / `f'` shapes first, then shorter names, earlier sites); at most MAX_CANDIDATES.
  search    (the t5 search contract, on the row's workbench, primary pin) every single read paired against the warm incumbent
            (famkit.Screen); winners = compiled with a positive paired estimate; their edit regions against the incumbent (difflib);
            the disjoint winners, greedily by estimate, applied at ONCE (op c2:stack) and read once; if that stack fails or does not beat
            the best single, a greedy incremental stack (one reading per added winner, kept when the estimate improves; at most
            STACK_READS readings). Survivors, best first: the stack(s) that beat the best single, then the winning singles (N_OUT in all).
  bank      every survivor goes through the end stage's own acceptance (endstage.attempt: the meter's primary reading, the incumbent
            re-read back to back, scorer.accept.decide (0.005 bar, HB_EPS), a fresh confirmation compile on every pin with the worse
            heartbeat reading counted, the statement prefix byte-identical, check_forbidden); a stack is ONE candidate, so a combination
            banks only on its own compiles (a combination of compiling singles can fail). After a stack banks, the singles it contains
            no longer rebase onto the new incumbent (stale, 0 compiles).
Budgets: the query is 1 compile per answering pin (charged to the tool phase and to the family cap); the workbench search is bounded by
SEARCH_SECONDS / MAX_CHECKS per row and the tool phase's deadline; the survivors' meter compiles by the config's caps.c2.
No harm: a query or search failure, a timeout or a budget stop leaves the incumbent as it is (the end stage's contract).
Generic: nothing here names a row, a lemma or a proof; the Lean query is a fixed text into which the proof's own identifiers are spliced
as Lean string literals, and every decision keys on facts read from the row's own environment (Lean.isClass, the constants' names)."""
from __future__ import annotations

import difflib, hashlib, re, time

OPS = ("c2:swap", "c2:stack")
MAX_CANDIDATES = 60    # singles screened per row (the study's cap)
SEARCH_SECONDS = 150.0  # workbench wall per row (all c2 searches)
MAX_CHECKS = 90        # workbench readings per row (the singles, the stacks, the paired incumbent readings excluded)
STACK_READS = 8        # stack readings per search (the one-pass stack + the greedy fallback)
N_OUT = 4              # survivors handed to the end stage's acceptance
PINS_UNSCREENED = 4    # without a search (no workbench): the first singles, unscreened (the end stage's batch screen then reads them)
QUERY_TIMEOUT = 300    # seconds per query compile
MIN_TIMEOUT_S = 10.0
TIMEOUT_MULT = 4.0

# identifiers of the proof text: dotted names, Unicode letters, subscripts, primes (the study's lexer rule); never a keyword below
IDENT = re.compile(r"(?<![\w.'?!₀-₉])([A-Za-z_Ͱ-Ͽᴀ-ᶿ℀-⅏𝓐-𝔷][\w'₀-₉ₐ-ₜ!?]*(?:\.[A-Za-z_Ͱ-Ͽ℀-⅏][\w'₀-₉ₐ-ₜ!?]*)*)")
KW = frozenset({"by", "at", "only", "with", "using", "in", "from", "then", "else", "if", "do", "fun", "have", "show", "let", "this", "exact",
                "apply", "intro", "intros", "rintro", "simp", "rw", "cases", "induction", "obtain", "refine", "use", "constructor",
                "all_goals", "any_goals", "case", "next", "generalizing", "match", "calc", "suffices", "sorry", "Type", "Prop", "Sort"})
MAX_IDS = 400          # identifiers spliced into one query (a long proof: the first ones in text order)

QUERY = r'''theorem lraC2QueryDummy : True := trivial

set_option maxHeartbeats 0 in
#eval show Lean.Elab.Command.CommandElabM Unit from do
  let env ← Lean.getEnv
  let ids : List String := [IDS]
  let mut out : String := ""
  let mut lasts : List String := []
  for s in ids do
    let rs ← Lean.resolveGlobalName s.toName
    for (c, fs) in rs do
      if fs.isEmpty then
        let k := match env.find? c with
          | some (.thmInfo _) => "thm"
          | some (.defnInfo _) => "def"
          | some (.inductInfo _) => "ind"
          | some (.ctorInfo _) => "ctor"
          | some (.axiomInfo _) => "thm"
          | some _ => "other"
          | none => "none"
        out := out ++ s!"LRAC2USED\t{s}\t{c}\t{k}\n"
        if k == "thm" then
          match c with
          | .str _ l => if !(lasts.contains l) then lasts := l :: lasts
          | _ => pure ()
  let res := env.constants.fold (fun (acc : Array String) (n : Lean.Name) (ci : Lean.ConstantInfo) =>
      match n, ci with
      | .str _ s, .thmInfo _ =>
        if n.isInternal then acc else
        match lasts.find? (fun f => s == f || s.startsWith (f ++ "_of_") || s == f ++ "'") with
        | some f => acc.push s!"LRAC2VAR\t{n}\t{f}\t{Lean.isClass env n.getPrefix}"
        | none => acc
      | .str _ s, .axiomInfo _ =>
        if n.isInternal then acc else
        match lasts.find? (fun f => s == f || s.startsWith (f ++ "_of_") || s == f ++ "'") with
        | some f => acc.push s!"LRAC2VAR\t{n}\t{f}\t{Lean.isClass env n.getPrefix}"
        | none => acc
      | _, _ => acc) #[]
  for r in res do
    out := out ++ r ++ "\n"
  Lean.logInfo (Lean.toMessageData ("LRAC2BEGIN\n" ++ out ++ "LRAC2END"))
'''


def proof_key(proof: str) -> str:
    return hashlib.sha256(proof.strip().encode()).hexdigest()[:16]


def _body(proof: str, statement: str):
    from scorer.tokenize import split_declaration
    return split_declaration(proof, statement)


def lean_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def idents(text: str) -> list[str]:
    out = []
    for m in IDENT.finditer(text or ""):
        t = m.group(1)
        if t not in KW and len(t) >= 2 and t not in out:
            out.append(t)
    return out


def _ids(proof: str, statement: str) -> list[str] | None:
    b = _body(proof, statement)
    if b is None:
        return None
    ids = idents(b)
    ids += [i for i in idents(statement) if i not in ids]
    return ids[:MAX_IDS]


def n_ids(proof: str, statement: str) -> int:
    return len(_ids(proof, statement) or [])


def query_text(proof: str, statement: str) -> str | None:
    """The Lean text of the env query for `proof` (placed after the row's file prefix; the dummy theorem takes the declaration's
    modifiers), or None when the body cannot be split off the statement or has no identifier."""
    ids = _ids(proof, statement)
    if not ids:
        return None
    return QUERY.replace("[IDS]", "[" + ", ".join(lean_str(i) for i in ids) + "]")


def parse_query(messages) -> dict:
    """{"used": [{"src", "name", "kind"}], "vars": [{"name", "f", "cls"}], "answered": bool} from the compile's Lean messages (the
    info message between the LRAC2BEGIN / LRAC2END markers; any other message is ignored)."""
    used, var, answered = [], [], False
    for m in messages or []:
        d = str((m or {}).get("data", "")) if isinstance(m, dict) else str(m)
        if "LRAC2BEGIN" not in d:
            continue
        answered = True
        for ln in d.split("\n"):
            p = ln.split("\t")
            if p[0] == "LRAC2USED" and len(p) == 4:
                used.append({"src": p[1], "name": p[2], "kind": p[3]})
            elif p[0] == "LRAC2VAR" and len(p) == 4:
                var.append({"name": p[1], "f": p[2], "cls": p[3].strip() == "true"})
    return {"used": used, "vars": var, "answered": answered}


def query(proof: str, statement: str, run, *, versions=None, ctx: dict | None = None, stats: dict | None = None, log=None) -> dict | None:
    """The env query (module docstring, "query"). run(text, version) -> a CompileResult-like (messages, ok, timed_out, errors), compiled
    plainly after the row's file prefix on that pin (the end stage charges it). Returns {"c2_query": {...}, "c2_query_for": key}; on a
    primary pin that does not answer, the query records an empty result (no candidates: the family proposes nothing for this proof)."""
    st = stats if stats is not None else {}
    log = log or (lambda *a: None)
    t0 = time.time()
    key = proof_key(proof)
    q = {"used": [], "vars": [], "pins": {}, "ids": 0}
    text = query_text(proof, statement)
    vs = list(versions or [None])
    if text is None:
        q["skip"] = "no identifier in the proof body"
        st["query"] = {k: q.get(k) for k in ("ids", "skip")}
        return {"c2_query": q, "c2_query_for": key}
    q["ids"] = n_ids(proof, statement)
    r = run(text, vs[0])
    prim = parse_query(getattr(r, "messages", None))
    q["pins"][str(vs[0])] = {"answered": prim["answered"], "timed_out": bool(getattr(r, "timed_out", False)),
                             "vars": len(prim["vars"]), "class_vars": sum(1 for v in prim["vars"] if v["cls"])}
    if not prim["answered"]:
        q["skip"] = "the primary pin did not answer: " + str((getattr(r, "errors", None) or ["?"])[0])[:160]
    else:
        q["used"], q["vars"] = prim["used"], prim["vars"]
        if any(v["cls"] for v in prim["vars"]):
            for v in vs[1:]:
                rv = run(text, v)
                pv = parse_query(getattr(rv, "messages", None))
                q["pins"][str(v)] = {"answered": pv["answered"], "timed_out": bool(getattr(rv, "timed_out", False)), "vars": len(pv["vars"])}
                if pv["answered"]:   # a variant must be a theorem on this pin too
                    names = {x["name"] for x in pv["vars"]}
                    q["vars"] = [x for x in q["vars"] if x["name"] in names]
    q["seconds"] = round(time.time() - t0, 2)
    st["query"] = {"ids": q["ids"], "used": len(q["used"]), "vars": len(q["vars"]), "class_vars": sum(1 for v in q["vars"] if v["cls"]),
                   "pins": q["pins"], "seconds": q["seconds"], **({"skip": q["skip"]} if q.get("skip") else {})}
    log(f"c2: env query {q['ids']} identifier(s): {len(q['used'])} resolved, {len(q['vars'])} variant(s), "
        f"{st['query']['class_vars']} in a class namespace, {len(q['pins'])} pin(s) asked ({q['seconds']} s)")
    return {"c2_query": q, "c2_query_for": key}


def sites(body_text: str, tok: str) -> list[int]:
    """Term positions of `tok` in the body (a tactic-head position -- line start, after a bullet, `by`, `<;>`, `;` or `=>` -- is not a
    lemma site)."""
    pat = re.compile(r"(?<![\w.'?!₀-₉])" + re.escape(tok) + r"(?![\w'?!₀-₉])")
    out = []
    for m in pat.finditer(body_text):
        pre = body_text[body_text.rfind("\n", 0, m.start()) + 1:m.start()].rstrip()
        if pre.strip() in ("", "·") or pre.endswith(("<;>", ";", "=>", "·", " by", "(by", ":= by", "try", "first |", "|")):
            continue
        out.append(m.start())
    return out


def generate(proof: str, statement: str, q: dict | None, cap: int = MAX_CANDIDATES) -> list[dict]:
    """The C2 singles (module docstring, "generate"): [{"op": "c2:swap", "decl", "note", "src", "from", "to", "shape", "site"}]."""
    if not q:
        return []
    b = _body(proof, statement)
    if b is None:
        return []
    off = len(proof) - len(b) if proof.endswith(b) else proof.rfind(b)
    if off < 0:
        return []
    out, seen = [], set()
    for u in q.get("used") or []:
        if u.get("kind") != "thm":
            continue
        f = u["name"].split(".")[-1]
        poss = sites(b, u["src"])
        if not poss:
            continue
        for v in q.get("vars") or []:
            if not v.get("cls") or v.get("f") != f or v["name"] == u["name"] or v["name"] == u["src"]:
                continue
            shape = "same" if v["name"].split(".")[-1] == f else "variant"
            for p in poss:
                text = proof[:off + p] + v["name"] + proof[off + p + len(u["src"]):]
                if text in seen:
                    continue
                seen.add(text)
                out.append({"op": "c2:swap", "decl": text, "note": f"`{u['src']}` -> `{v['name']}` @ {p}", "src": u["src"], "from": u["name"],
                            "to": v["name"], "shape": shape, "site": p})
    out.sort(key=lambda c: (0 if c["shape"] == "variant" else 1, len(c["to"]), c["site"], c["to"]))
    return out[:max(0, int(cap))]


def region(base: str, cand: str):
    """(start, end, replacement) of `cand`'s edit of `base`: the span between the first and the last differing character."""
    sm = difflib.SequenceMatcher(None, base, cand, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    if not ops:
        return None
    i1, i2 = min(o[1] for o in ops), max(o[2] for o in ops)
    j1, j2 = min(o[3] for o in ops), max(o[4] for o in ops)
    return (i1, i2, cand[j1:j2])


def apply_all(base: str, regs) -> str:
    out = base
    for i1, i2, rep in sorted(regs, key=lambda r: -r[0]):
        out = out[:i1] + rep + out[i2:]
    return out


def pick_disjoint(items: list[dict], key: str = "reg") -> list[dict]:
    """Greedily (in the given order) the items whose regions neither overlap nor touch the ones chosen before."""
    chosen = []
    for it in items:
        a1, a2, _ = it[key]
        if all(a2 < c[key][0] - 1 or a1 > c[key][1] + 1 for c in chosen):
            chosen.append(it)
    return chosen


def _timeout(ctx: dict | None) -> float:
    cs = (ctx or {}).get("compile_s")
    return max(MIN_TIMEOUT_S, TIMEOUT_MULT * float(cs) + 4.0) if isinstance(cs, (int, float)) else MIN_TIMEOUT_S * 3


def _query_of(proof: str, ctx: dict | None):
    c = ctx or {}
    return c.get("c2_query") if c.get("c2_query_for") == proof_key(proof) and isinstance(c.get("c2_query"), dict) else None


def search_precheck(proof: str, statement: str, ctx: dict | None = None) -> str | None:
    """A reason the search stops before any workbench reading (no Lean), else None (harness/endstage._search_precheck)."""
    q = _query_of(proof, ctx)
    if ctx is not None and q is None:
        return "no env query for this proof"
    if q is not None and not generate(proof, statement, q, 1):
        return "no class-namespace variant at a term site"
    return None


def search(proof: str, statement: str, wb, *, meter_reading: dict | None = None, exchange=None, ctx: dict | None = None,
           stats: dict | None = None, log=None, deadline: float | None = None, max_checks: int = MAX_CHECKS, n_out: int = N_OUT,
           trace: list | None = None) -> dict:
    """The search (module docstring, "search"). Returns {"c2_found": [...], "c2_found_for": key} (an empty list: searched, nothing
    survived), or {} when there is no env query for this proof (the family then proposes nothing)."""
    from harness.tools import famkit as K
    t0 = time.time()
    st = stats if stats is not None else {}
    log = log or (lambda *a: None)
    for k_, v_ in (("sites", 0), ("variants", 0), ("readings", 0), ("compiled", 0), ("survivors", 0), ("skips", {}), ("errors", {}),
                   ("budget_out", False), ("searches", 0), ("winners", 0), ("stack", {"read": 0, "better": 0, "k": 0})):
        st.setdefault(k_, v_ if not isinstance(v_, dict) else dict(v_))
    st["searches"] += 1
    key = proof_key(proof)
    q = _query_of(proof, ctx)
    if q is None:
        st["skips"]["no env query"] = st["skips"].get("no env query", 0) + 1
        st["seconds"] = round(time.time() - t0, 2)
        return {}
    cands = generate(proof, statement, q, MAX_CANDIDATES)
    st["variants"] += len(cands)
    st["sites"] = max(st["sites"], len({(c["src"], c["site"]) for c in cands}))
    if not cands:
        st["skips"]["no class-namespace variant at a term site"] = st["skips"].get("no class-namespace variant at a term site", 0) + 1
        st["seconds"] = round(time.time() - t0, 2)
        return {"c2_found": [], "c2_found_for": key}
    dl = deadline if deadline is not None else time.time() + SEARCH_SECONDS
    scr = K.Screen(wb, proof, meter_reading=meter_reading, deadline=dl, max_checks=max_checks, timeout=_timeout(ctx), log=log)
    by = {c["decl"]: c for c in cands}
    rs = scr.read([c["decl"] for c in cands])
    wins = []
    for r in rs:
        c = by.get(r.get("decl"))
        if c is None:
            continue
        if trace is not None:
            trace.append({"op": c["op"], "src": c["note"], "status": r.get("status"), "d_score": r.get("d_score"),
                          "d_heartbeats": r.get("d_heartbeats")})
        est = r.get("d_score")
        if r.get("status") == "ok" and isinstance(est, (int, float)) and est > 0:
            reg = region(proof, c["decl"])
            if reg is not None:
                wins.append(dict(c, est=float(est), reg=reg, d_heartbeats=r.get("d_heartbeats"), tokens=r.get("tokens")))
    wins.sort(key=lambda w: (-w["est"], w["site"], w["to"]))
    st["winners"] += len(wins)
    stacks = []
    best_single = wins[0]["est"] if wins else None
    sel = pick_disjoint(wins)
    reads = [0]

    def read_stack(regs, note):
        if reads[0] >= STACK_READS or not scr.left():
            return None
        reads[0] += 1
        st["stack"]["read"] += 1
        text = apply_all(proof, regs)
        rr = scr.read([text])
        if not rr:
            return None
        r = rr[0]
        est = r.get("d_score")
        if trace is not None:
            trace.append({"op": "c2:stack", "src": note, "status": r.get("status"), "d_score": est, "d_heartbeats": r.get("d_heartbeats")})
        if r.get("status") == "ok" and isinstance(est, (int, float)):
            return {"decl": text, "est": float(est), "d_heartbeats": r.get("d_heartbeats"), "tokens": r.get("tokens")}
        return None
    one = None
    if len(sel) >= 2:   # ONE reading of every disjoint winner at once
        one = read_stack([w["reg"] for w in sel], f"{len(sel)} edits at once")
        if one is not None and one["est"] > best_single:
            stacks.append(dict(one, op="c2:stack", note=f"stack of {len(sel)} class-namespace swap(s) (one pass)", k=len(sel)))
    if len(sel) >= 2 and not stacks:   # greedy incremental fallback: add the next winner, keep it when the estimate improves
        cur, cur_est, last = [sel[0]], sel[0]["est"], None
        for w in sel[1:]:
            got = read_stack([x["reg"] for x in cur + [w]], f"{len(cur) + 1} edits (greedy)")
            if got is None:
                if reads[0] >= STACK_READS or not scr.left():
                    break
                continue
            if got["est"] > cur_est:
                cur, cur_est = cur + [w], got["est"]
                last = got
        if len(cur) >= 2 and last is not None and cur_est > best_single:
            stacks.append(dict(last, op="c2:stack", note=f"stack of {len(cur)} class-namespace swap(s) (greedy)", k=len(cur)))
    st["stack"]["better"] += len(stacks)
    st["stack"]["k"] = max(st["stack"]["k"], max((s["k"] for s in stacks), default=0))
    found = [{"op": s["op"], "decl": s["decl"], "note": s["note"] + f"; est {s['est']:+.4f}", "est": s["est"], "k": s["k"]} for s in stacks]
    found += [{"op": "c2:swap", "decl": w["decl"], "note": w["note"] + f"; hb {w.get('d_heartbeats')}; est {w['est']:+.4f}", "est": w["est"]}
              for w in wins]
    found = found[:max(0, int(n_out))]
    for k_ in ("readings", "compiled", "timeouts", "calls"):
        st[k_] = st.get(k_, 0) + scr.stats.get(k_, 0)
    st["budget_out"] = st["budget_out"] or scr.stats.get("budget_out", False)
    for k_, v_ in scr.stats.get("errors", {}).items():
        st["errors"][k_] = st["errors"].get(k_, 0) + v_
    st["survivors"] += len(found)
    st["best_est"] = max(st.get("best_est") or 0.0, max((f["est"] for f in found), default=0.0))
    st["wb_seconds"] = round(scr.stats.get("seconds", 0.0), 2)
    st["peak_rss_mb"] = getattr(wb, "peak_rss_mb", None)
    st["seconds"] = round(time.time() - t0, 2)
    log(f"c2: {len(found)} survivor(s) ({len(stacks)} stack(s)) of {len(cands)} single(s), {len(wins)} winning, {len(sel)} disjoint; "
        f"{scr.stats.get('readings', 0)} reading(s), {scr.stats.get('compiled', 0)} compiled ({st['seconds']} s)")
    return {"c2_found": found, "c2_found_for": key}


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int = N_OUT, ctx: dict | None = None) -> list[dict]:
    """The search's survivors for this proof (ctx "c2_found"); without a search but with the env query: the first PINS_UNSCREENED singles
    unscreened (the end stage's batch screen reads them); else nothing."""
    ctx = ctx or {}
    if ctx.get("c2_found_for") == proof_key(proof) and isinstance(ctx.get("c2_found"), list):
        return [{"op": c.get("op") or "c2:swap", "decl": c["decl"], "note": str(c.get("note") or "")[:300]}
                for c in ctx["c2_found"][:max(0, int(max_per_op))]
                if isinstance(c, dict) and isinstance(c.get("decl"), str) and c["decl"].strip() != proof.strip()]
    if ctx.get("c2_found_for") is not None:
        return []
    q = _query_of(proof, ctx)
    return [{"op": c["op"], "decl": c["decl"], "note": c["note"]} for c in generate(proof, statement, q, PINS_UNSCREENED)] if q else []


def explain(proof: str, statement: str, ctx: dict | None = None) -> dict:
    """Without Lean: the identifiers the query would resolve; with the env query in ctx, the singles it generates."""
    b = _body(proof, statement)
    q = _query_of(proof, ctx)
    out = {"ok": b is not None, "ids": len(idents(b or "")), "query": bool(q)}
    if q:
        g = generate(proof, statement, q, MAX_CANDIDATES)
        out.update(fire=bool(g), n_candidates=len(g), class_vars=sum(1 for v in q.get("vars") or [] if v.get("cls")))
    return out
