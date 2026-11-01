#!/usr/bin/env python3
"""Architect panel (2026-10-14; docs/architect_polisher.md).

A strong model writes K structurally different complete proofs of a row in ONE call (its only tool is `submit_proofs`); every proof is
compiled at $0 on the primary toolchain; the architect gets ONE repair call with the compile errors of its failing proofs (and the scores
of its compiling ones); the best compiling proof is also checked on every toolchain. The compiling proofs are skeletons for the cheap
polisher (probe/heldout/seed_from_ab.py --skeletons, run_e2_polish.sh).

Anti-anchoring: every model shown the incumbent's text kept its decomposition (Kimi K3, DeepSeek, the Opus and Sol depth sessions), so
the prompt shows the statement, the seed's reference proof, the score to beat and the incumbent's VOCABULARY (the lemma and definition
names it uses, sorted), never the incumbent's text. No file access and no other tools: nothing leaks from other lines.
    python3 harness/architect.py --problem NAME --model anthropic/claude-fable-5.1 [--k 4] [--effort high] --out FILE.json
Compiles go through the scorer (memgate): run in a memory-capped unit, never from an interactive shell.
"""
from __future__ import annotations

import argparse, json, os, pathlib, re, sys, time
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "harness"))
from harness.leantools import ROWS, HBS, comp, digest_error  # noqa: E402
from harness.pattern_cards import pattern_cards_for  # noqa: E402
from scorer.tokenize import split_declaration, count_tokens  # noqa: E402
from scorer.score import len_pct, hb_pct_local, compat_pct, problem_score  # noqa: E402
from scorer.compile import file_prefix  # noqa: E402
from probe.verify_candidates import newest_first  # noqa: E402
from llm.openai_compat import create  # noqa: E402

KEY = pathlib.Path("~/.config/vexorium/openrouter_api_key").expanduser()
SNAP = ROOT / "probe/autobrief/snapshot"
# provider routing per model (Kimi K3: the tools-capable FP4 providers of the kimi-k3-or preset)
# (2026-10-14: no Moonshot endpoint unless there is no other choice; Sail first: lowest output price, answered right at both
# efforts in the 2026-10-14 effort test, where Relace was right only at max and InferenceNet thought past 8k)
ROUTING = {"moonshotai/kimi-k3": {"provider": {"order": ["sail-research/fp4", "relace/fp4", "wafer", "inference-net/fp4"],
                                               "allow_fallbacks": False, "require_parameters": True}}}
SUBMIT = [{"name": "submit_proofs", "description": "Submit complete Lean 4 declarations (the exact statement followed by := and a proof).",
           "input_schema": {"type": "object", "properties": {"proofs": {"type": "array", "items": {"type": "object", "properties": {
               "label": {"type": "string", "description": "short unique name"},
               "strategy": {"type": "string", "description": "one line: the decomposition and why it can be shorter and cheaper"},
               "declaration": {"type": "string", "description": "the complete declaration: the exact statement, := and the proof"}},
               "required": ["label", "strategy", "declaration"]}}}, "required": ["proofs"]}}]
TECHNIQUES = (
    "GENERAL LEAN 4 GOLF TECHNIQUES (choose what fits; not all apply): `unhygienic` at the top of a tactic block makes auto-generated names "
    "accessible, so `intro`/`intros`/`introv` and `case` arms need no names (hypotheses become `a`, `a_1`, ..., induction hypotheses "
    "`a_ih`); consume facts as goals with `apply f` + `assumption` / `assumption'` instead of naming intermediate `have`/`let` results; "
    "move between goals with `rotate_left`, `case'`, `all_goals`, `any_goals`, `<;>`, `repeat`/`iterate n` instead of bullets and named "
    "structure; `repeat constructor` / `econstructor` for conjunctions and existentials; `‹_›` for an anonymous hypothesis; destructure an "
    "existential with an `obtain` pattern that substitutes by `rfl`, `induction e`, or the `.imp` combinators instead of `choose` / `choose_spec`; put side "
    "conditions inside one `simp only [...]` set (raise `maxDischargeDepth` if needed) instead of separate rewriting steps; `rewrite` "
    "instead of `rw` when no `rfl` is needed; term mode is not automatically cheaper in heartbeats; `grind`/`simp`/`omega` cost hundreds "
    "of heartbeats per call, explicit terms cost tokens.")
_KW = set("by fun have let show from at with in do then else if match calc exact apply intro intros rintro obtain cases induction "
          "simp only rw rewrite refine use exists constructor assumption rfl this case all_goals any_goals first try repeat iterate "
          "generalizing using unfold dsimp simp_all omega grind linarith ring norm_num decide trivial sorry Type Prop by_cases conv_lhs "
          "conv_rhs rotate_left rotate_right rename_i apply_rfl exact_mod_cast push_cast field_simp specialize subst injection "
          "simp_rw nth_rewrite erw congr ext funext positivity gcongr nlinarith aesop solve_by_elim".split())


def vocabulary(proof: str, statement: str) -> list[str]:
    """Identifiers of the incumbent's proof that look like lemma or definition names (a dot, a capital, or an underscore between
    letters), minus those in the statement and tactic keywords: what it knows, not how it is arranged."""
    body = split_declaration(proof.rstrip(), statement) or proof
    ids = set(re.findall(r"[^\W\d][\w.'!?]*[\w'!?]", body))   # Unicode identifiers (ι_..., 𝓕...), dotted names
    st = set(re.findall(r"[^\W\d][\w.'!?]*", statement))
    keep = {i for i in ids if i not in _KW and i not in st and ("." in i or any(c.isupper() for c in i) or re.search(r"[a-z]_[a-z]", i))}
    return sorted(keep)


def incumbent(name: str) -> dict:
    ver = {r["name"]: r for r in json.load(open(SNAP / "autobrief-ab1-20261014.verify.json"))["rows"]}[name]
    proof = {json.loads(l)["name"]: json.loads(l)["proof"] for l in open(SNAP / "autobrief-ab1-20261014.jsonl")}[name]
    return {"proof": proof, "tokens": ver["tokens"], "heartbeats": ver["heartbeats"], "score": ver["score"]}


def context_excerpt(row: dict, version: str, max_chars: int = 14000) -> str:
    if row["source"] == "putnambench":
        return row["header"][-max_chars:]
    pre = file_prefix(row, version)
    head = "\n".join(l for l in pre.split("\n") if re.match(r"\s*(import|open|namespace|section|variable|universe|set_option)\b", l))
    tail = pre[-(max_chars - min(len(head), max_chars // 3)):]
    return head[: max_chars // 3] + "\n...\n" + tail


def prompt(name: str, k: int) -> str:
    row = ROWS[name]; versions = newest_first(row["version_info"]); inc = incumbent(name)
    ref_body = split_declaration(row["src"].rstrip(), row["statement"]) or row["src"]
    return (
        f"Rewrite the proof of this Lean 4 declaration (toolchains {', '.join(versions)}; the proof must compile on all of them).\n\n"
        "SCORE = mean of three percentages against the reference proof: token reduction (Lean tokens of the proof body), heartbeat "
        "reduction (elaboration heartbeats), and compatibility (toolchains where it compiles). Shorter AND cheaper wins.\n\n"
        f"STATEMENT (copy it exactly):\n```lean\n{row['statement']}\n```\n\n"
        f"REFERENCE PROOF ({count_tokens(ref_body)} tokens, {HBS.get(name, '?')} heartbeats; it compiles):\n```lean\n{row['src'].rstrip()}\n```\n\n"
        f"SCORE TO BEAT: {inc['score']:.2f} ({inc['tokens']} tokens, {inc['heartbeats']} heartbeats), held by a heavily polished proof "
        "whose decomposition is a local optimum: more polishing of it gains nothing. You do not see it on purpose.\n"
        f"Names it uses (lemmas and definitions known to exist and work here): {', '.join(vocabulary(inc['proof'], row['statement']))}\n\n"
        f"SURROUNDING FILE (excerpt):\n```lean\n{context_excerpt(row, versions[0])}\n```\n\n"
        f"{TECHNIQUES}\n\n{pattern_cards_for(row['statement'], row['src'])}\n\n"
        f"TASK: think deeply, then call submit_proofs ONCE with {k} complete declarations, each a DIFFERENT decomposition (a different "
        "case or induction structure, a different key lemma, a different main closer, term mode versus tactics), each aimed at fewer "
        "tokens AND fewer heartbeats than the score to beat. No sorry, admit, axioms, native_decide, auxiliary declarations, `open` or "
        "`set_option` outside the proof. You will get one chance to repair compile errors.")


def check(name: str, decl: str, versions: list[str], full: bool = False) -> dict:
    row = ROWS[name]; decl = decl.strip()
    body = split_declaration(decl, row["statement"])
    if body is None:   # tolerate a re-typed statement: splice the proof onto the exact one
        m = re.search(r":=\s*(by\b[\s\S]*|[\s\S]*)$", decl)
        if not m:
            return {"ok": False, "error": "no `:=` in the declaration"}
        decl = row["statement"] + " :=" + ("\n  " if not m.group(1).startswith("by") else " ") + m.group(1)
        body = split_declaration(decl, row["statement"])
    if re.search(r"\b(sorry|admit|native_decide)\b|^\s*axiom\b", body or "", re.M):
        return {"ok": False, "error": "forbidden: sorry/admit/native_decide/axiom", "decl": decl}
    r = comp(row, decl, versions[0])
    out = {"ok": r.ok, "tokens": count_tokens(body), "heartbeats": r.heartbeats, "decl": decl,
           "errors": [digest_error(e) for e in (r.errors or [])[:2]]}
    if r.ok:
        L = len_pct(row["proof_length"], out["tokens"]); H = hb_pct_local(name, r.heartbeats, HBS.get(name))
        compat = {versions[0]: True}
        if full:
            for v in versions[1:]:
                compat[v] = comp(row, decl, v, count=False).ok
        Z = compat_pct(compat) if full else 100.0
        out.update(L=round(L, 2), H=round(H, 2), Z=Z, compat=compat, score=round(problem_score(True, L, H, Z), 2))
    return out


def _reasoning(model: str, effort: str) -> dict:
    """2026-10-14 panel p1: OpenRouter turns an Anthropic effort into a thinking budget of about 80% of max_tokens at high, and Opus 5.5
    thought through the whole 24k cap on a dev row without submitting ($0.54). Anthropic models get an explicit thinking budget instead, so
    half the cap stays for the K proofs."""
    if model.startswith(("anthropic/", "google/", "qwen/")):   # Argon and Qwen3.8 Max Prime also thought through 24k on that row at high
        return {"max_tokens": {"high": 16000, "medium": 8000}.get(effort, 16000)}
    return {"effort": effort}


def endpoint_for(model: str) -> tuple:
    """(base_url, key, api model, extra body, think_mode, cache) for a model: an agent.py preset name (e.g. kimi-azure, an Azure deployment;
    2026-10-15: development runs on Azure) or an OpenRouter model id."""
    from harness.agent import MODEL_PRESETS
    if model in MODEL_PRESETS:
        p = MODEL_PRESETS[model]
        if os.environ.get("LRA_SELFTEST_PRESET_URL"):   # b66 (2026-10-27): the $0 rehearsal's fake server, as agent.main does: no key is read or sent
            return (os.environ["LRA_SELFTEST_PRESET_URL"], "selftest", p["api_model"], dict(p.get("extra_body") or {}),
                    p.get("think_mode", "none"), bool(p.get("cache")))
        return (p["base_url"], Path(p["key"]).expanduser().read_text().strip(), p["api_model"], dict(p.get("extra_body") or {}),
                p.get("think_mode", "none"), bool(p.get("cache")))
    return ("https://openrouter.ai/api/v1", KEY.read_text().strip(), model, {"usage": {"include": True}, **ROUTING.get(model, {})}, "details",
            model.startswith("anthropic/"))


def call(model: str, msgs: list, effort: str, max_tokens: int, tools: list | None = None, system: str | None = None) -> tuple:
    t0 = time.time()
    from harness.agent import MODEL_PRESETS
    system = system or ("You are an expert Lean 4 proof engineer: you design proofs that are short (few Lean tokens) and cheap to "
                        "elaborate (few heartbeats).")
    _p = MODEL_PRESETS.get(model) or {}
    if _p.get("anthropic_vertex"):   # 2026-10-15: Claude on Vertex (official SDK through harness/vertex_proxy.py); effort = output_config.effort
        from llm.anthropic_vertex import create as _vertex_claude
        m = _vertex_claude(model=_p["api_model"], max_tokens=max_tokens, system=system, tools=tools or SUBMIT, messages=msgs, effort=effort,
                           prices=_p["prices"], region=_p["anthropic_vertex"])
    else:
        base, key, api_model, eb, tm, cache = endpoint_for(model)
        m = create(base_url=base, api_key=key, model=api_model, max_tokens=max_tokens, system=system, tools=tools or SUBMIT, messages=msgs,
                   extra_body={**eb, "reasoning": _reasoning(model, effort)}, think_mode=tm, cache=cache, stream=True, guard=False)
    proofs = [b for b in m.content if b.type == "tool_use" and b.name == "submit_proofs"]
    sub = ((proofs[0].input or {}).get("proofs") or []) if proofs else []
    if not sub:   # proofs written as text instead of a tool call: take the ```lean blocks that hold a declaration
        text = "".join(b.text or "" for b in m.content if b.type == "text")
        decls = [d.strip() for c in re.findall(r"```(?:lean4?)?\s*\n(.*?)```", text, re.S)   # one block may hold several declarations
                 for d in re.split(r"(?m)^(?=(?:@\[[^\]]*\]\s*)?(?:theorem|lemma)\b)", c) if ":=" in d]
        sub = [{"label": f"text{i}", "strategy": "(from text)", "declaration": d} for i, d in enumerate(decls)]
    u = m.usage
    meta = {"seconds": round(time.time() - t0, 1), "input": u.input_tokens, "output": u.output_tokens, "cached": u.cache_read,
            "cost": u.cost, "stop": m.stop_reason,
            # where the output went (2026-10-14: Opus 5.5 used the whole cap twice on a dev row without submitting)
            "chars": {"thinking": sum(len(b.thinking or "") for b in m.content if b.type == "thinking"),
                      "text": sum(len(b.text or "") for b in m.content if b.type == "text"),
                      "tool_args": sum(len(json.dumps(b.input or {}, ensure_ascii=False)) for b in m.content if b.type == "tool_use")}}
    if not sub:   # keep the tail of what it wrote, to see why nothing was submitted
        meta["text_tail"] = "".join(b.text or "" for b in m.content if b.type == "text")[-1500:]
    return m, sub, meta


def run(name: str, model: str, k: int, effort: str, max_tokens: int, log=print, out: pathlib.Path | None = None,
        continue_on_length: int = 0) -> dict:
    row = ROWS[name]; versions = newest_first(row["version_info"]); inc = incumbent(name)
    msgs = [{"role": "user", "content": prompt(name, k)}]
    res = {"problem": name, "model": model, "effort": effort, "k": k, "incumbent": {x: inc[x] for x in ("tokens", "heartbeats", "score")},
           "calls": [], "variants": [], "submissions": []}

    def save():   # after every call and compile: a crash after an expensive call keeps its proofs
        if out:
            out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for rnd in (0, 1):
        m, sub, meta = call(model, msgs, effort, max_tokens); res["calls"].append(meta)
        log(f"{model} {name[:24]} round {rnd}: {len(sub)} proofs, {meta}")
        for _ in range(continue_on_length):   # the IMO-setup length guard: a call cut at the cap keeps its reasoning and continues
            if sub or meta.get("stop") != "max_tokens":
                break
            msgs += [{"role": "assistant", "content": [b.model_dump() for b in m.content]},
                     {"role": "user", "content": "Your output was cut by the length limit. Continue from where your reasoning stopped, "
                                                 "then call submit_proofs ONCE with your proofs."}]
            m, sub, meta = call(model, msgs, effort, max_tokens); meta["continued"] = True; res["calls"].append(meta)
            log(f"{model} {name[:24]} round {rnd} continued after the length cut: {len(sub)} proofs, {meta}")
        if not sub and rnd == 0 and not continue_on_length:   # 2026-10-14 smoke: DeepSeek reasoned through 24k; one fresh retry at medium
            m, sub, meta = call(model, msgs, "medium", max_tokens); meta["retry"] = "medium"; res["calls"].append(meta)
            log(f"{model} {name[:24]} round 0 retry at medium effort: {len(sub)} proofs, {meta}")
        res["submissions"].append({"round": rnd, "proofs": sub}); save()
        if not sub:
            break
        got = []
        for p in sub[: k + 2]:
            c = check(name, str(p.get("declaration") or ""), versions)
            v = {"round": rnd, "label": str(p.get("label"))[:60], "strategy": str(p.get("strategy"))[:300], **c}
            res["variants"].append(v); got.append(v); save()
            log(f"   {v['label'][:30]:30s} ok={c['ok']} tok={c.get('tokens')} hb={c.get('heartbeats')} score={c.get('score')}")
        if rnd == 1:
            break
        tool_ids = [b.id for b in m.content if b.type == "tool_use" and b.name == "submit_proofs"]
        lines = []
        for v in got:
            if v["ok"]:
                lines.append(f"- {v['label']}: COMPILES, {v['tokens']} tokens, {v['heartbeats']} heartbeats, score {v['score']}")
            else:
                lines.append(f"- {v['label']}: FAILS: " + " | ".join(v.get("errors") or [v.get("error") or "?"]))
        ask = ("Repair the failing proofs (same labels) and, if you see how, improve the compiling ones; the score to beat is "
               f"{inc['score']:.2f}. Call submit_proofs ONCE with the proofs to re-check.")
        msgs.append({"role": "assistant", "content": [b.model_dump() for b in m.content]})
        if tool_ids:
            msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_ids[0], "content": "\n".join(lines)},
                                                     {"type": "text", "text": ask}]})
        else:   # the proofs came as text: the results come back as text too
            msgs.append({"role": "user", "content": "Results of your proofs:\n" + "\n".join(lines) + "\n\n" + ask})
    ok = sorted([v for v in res["variants"] if v["ok"]], key=lambda v: -v["score"])
    if ok:
        best = ok[0]; full = check(name, best["decl"], versions, full=True)
        res["best"] = {"label": best["label"], "round": best["round"], **{x: full.get(x) for x in ("ok", "tokens", "heartbeats", "L", "H", "Z", "compat", "score")}}
    res["cost"] = round(sum(c.get("cost") or 0 for c in res["calls"]), 4); save()
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problem", required=True); ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=4); ap.add_argument("--effort", default="high"); ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--print-prompt", action="store_true", help="print the prompt and exit (no model call, no compile)")
    ap.add_argument("--continue-on-length", type=int, default=0, help="continuations of a call cut at the cap (its reasoning replayed), "
                    "in place of the fresh medium retry")
    a = ap.parse_args()
    if a.print_prompt:
        print(prompt(a.problem, a.k)); return 0
    r = run(a.problem, a.model, a.k, a.effort, a.max_tokens, out=pathlib.Path(a.out), continue_on_length=a.continue_on_length)
    print(json.dumps({x: r.get(x) for x in ("problem", "model", "cost", "best")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
