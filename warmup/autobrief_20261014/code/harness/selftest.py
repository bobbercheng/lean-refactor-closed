"""Deterministic self-test of the agent harness with a scripted fake model (cycle 46, 2026-10-08).

Live smoke runs could not verify harness changes: a 3-turn z.ai run took the short-polish path and never wrote candidate.lean, and
turn-0 truncations ate the budget. This test starts a local OpenAI-compatible server that replays a fixed script of model responses,
runs harness/agent.py against it (--endpoint openai, scratch work root, model name `fake-selftest` so nothing is attributable to
GLM), records every request the harness sends, and asserts on what the model would have seen. No API calls, no bank writes: the
run directory is moved into the scratch root afterwards.

    python3 harness/selftest.py            # prints PASS/FAIL per check, exit 1 on any failure

Checks:
  opening_move     the first request ends with the OPENING MOVE line (runs longer than 10 turns)
  trunc_handback   a capped no-tool turn is answered with the tail of the cut reasoning (z.ai path: --no-budget-forcing)
  auto_check       writing candidate.lean returns an automatic lean_check result in the same tool result
  dup_note         writing it again unchanged returns the duplicate note, not a second compile
  finish_guard     an early finish is refused while a third of the budget remains
  noop_delete      a tactic left after the goal is closed (\"No goals\") is deleted by the auto-check and reported
  rw_repair        a failed rewrite (wrong rule direction) in a written candidate is repaired by the auto-check and reported
  text_end_guard   a turn that ends with text only (no tool call) is refused like an early finish while a third of the budget remains
  compat_why       a variant that compiles on the primary toolchain but not on an older one is reported with the errors there and
                   the names that do exist there (fixture: a real a4 candidate that fails on v4.26.0 and v4.25.0)
  closed_lessons   (--closed-lessons) the first message carries the three habits from the closed lines, and only with the flag
  normalize        (--normalize) after the session the lexer post-pass rewrites the best, compiles it on every toolchain and records it
  token_rules      (--token-rules) the system prompt of a run without --length-tools carries the TOKEN COUNTING lexer rules, only with the flag
  from_reference_guard  (--from-reference on a workspace with three flat runs at ~70, adaptive turns on) the run stays a restart:
                   no FRESH START, no structural brief or effort raise, the strategy brief kept, the --turns budget as given,
                   and the notes in the opening message (a warm restart)
  budget_gate      (--model-preset) the cap stops BEFORE a turn whose WORST CASE (context uncached + full output cap) could cross it,
                   a crossed spend milestone is recorded once (state + warning line), and a list_price preset
                   (DeepSeek) meters at the price table, not the provider-reported cost (ClinePass reports half)
  runaway_drop     a tool call cut at the output cap inside its arguments (unterminated JSON) is not re-sent: the next request carries a
                   stub and a tool result saying it was dropped; the output cap escalates only when the tail was not degenerate repetition
  degenerate_tail  the detector flags a whitespace run and a repeated short line, and never a real long proof (cut anywhere)
  lever_review     (--lever-review) a plateaued workspace (three flat runs at ~70) opens with the LEVER REVIEW checklist only with the flag
  variant_scores   (--variant-scores) a compiling variant that is not a new best shows its provisional score and vs_best, not null
  error_lines      (--relative-error-lines) a failing line is reported as `line k `<text>`` of the declaration, not the scratch file's line
  simp_prune       (--simp-prune) an unused lemma added to a `simp only [...]` list of the a4 best is dropped by the write's auto-check
  upstream_digest  a project problem's first message carries the precomputed upstream version of the theorem (CCS congr_choice:
                   simplified upstream), so the model need not search git history for it
  nothink_markup   (z.ai path) the retry's tool call arrives as GLM template markup in text: parsed and executed
  nothink_rescue   (z.ai path, Anthropic API) a capped thinking turn is re-asked once with thinking disabled and the cut reasoning
                   appended to the last user message; the rescued tool call is executed (auto-check result reaches the next request)
"""
from __future__ import annotations

import http.server, json, os, pathlib, shutil, socket, subprocess, sys, tempfile, threading, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBLEM = "putnam_1964_b2"
REASONING_TAIL = "PLANNED-EDIT-MARKER: V1 drops the have, V2 swaps the closer"


def script(candidate: str) -> list[dict]:
    return [
        {"length": True, "reasoning": "x " * 2000 + REASONING_TAIL},                              # turn 0: capped while thinking
        {"tool": "write_file", "args": {"path": "candidate.lean", "content": candidate}},          # turn 1: new candidate -> auto check
        {"tool": "write_file", "args": {"path": "candidate.lean", "content": candidate}},          # turn 2: same text -> duplicate note
        {"tool": "finish", "args": {}},                                                             # turn 3: early finish -> refused
    ]


class Fake(http.server.BaseHTTPRequestHandler):
    steps: list[dict] = []; seen: list[dict] = []

    def log_message(self, *a):   # quiet
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        step = Fake.steps[min(len(Fake.seen) - 1, len(Fake.steps) - 1)]
        if self.path.endswith("/messages"):
            return self.anthropic(body, step)
        msg: dict = {"role": "assistant", "content": None}
        if "text" in step:
            msg["content"] = step["text"]; fr = "stop"
        elif step.get("length"):
            msg["reasoning_content"] = step["reasoning"]; fr = "length"
        elif step.get("runaway"):   # a tool call cut at the output cap inside its arguments: unterminated JSON with a whitespace tail
            msg["tool_calls"] = [{"id": f"call_{len(Fake.seen)}", "type": "function",
                                  "function": {"name": step["tool"], "arguments": step["raw"]}}]; fr = "length"
        else:
            msg["tool_calls"] = [{"id": f"call_{len(Fake.seen)}", "type": "function",
                                  "function": {"name": step["tool"], "arguments": json.dumps(step["args"])}}]; fr = "tool_calls"
        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "cost": 0.0001}
        if body.get("stream"):   # streamed presets (DeepSeek via ClinePass): one delta chunk, then usage, then [DONE]
            delta = {k: v for k, v in msg.items() if k != "role" and v is not None}
            if "tool_calls" in delta:
                delta["tool_calls"] = [dict(tc, index=0) for tc in delta["tool_calls"]]
            chunks = [{"choices": [{"delta": delta, "finish_reason": fr}]}, {"choices": [], "usage": usage}]
            out = ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Content-Length", str(len(out)))
            self.end_headers(); self.wfile.write(out); return
        out = json.dumps({"choices": [{"message": msg, "finish_reason": fr}], "usage": usage}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

    def anthropic(self, body: dict, step: dict):
        """Anthropic Messages API (what the z.ai code path speaks): JSON for create(), SSE for stream()."""
        if step.get("length"):
            blocks = [{"type": "thinking", "thinking": step["reasoning"], "signature": ""}]; stop = "max_tokens"
        elif "text" in step:
            blocks = [{"type": "text", "text": step["text"]}]; stop = "end_turn"
        else:
            blocks = [{"type": "tool_use", "id": f"toolu_{len(Fake.seen)}", "name": step["tool"], "input": step["args"]}]; stop = "tool_use"
        msg = {"id": f"msg_{len(Fake.seen)}", "type": "message", "role": "assistant", "model": "fake", "content": blocks,
               "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 100}}
        if not body.get("stream"):
            out = json.dumps(msg).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
            self.end_headers(); self.wfile.write(out); return
        ev = [("message_start", {"type": "message_start", "message": {**msg, "content": [], "stop_reason": None,
                                                                         "usage": {"input_tokens": 1000, "output_tokens": 0}}})]
        for i, b in enumerate(blocks):
            if b["type"] == "text":
                ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}),
                       ("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": b["text"]}})]
            elif b["type"] == "thinking":
                ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
                       ("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "thinking_delta", "thinking": b["thinking"]}})]
            else:
                ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {**b, "input": {}}}),
                       ("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}})]
            ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
        ev += [("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 100}}),
               ("message_stop", {"type": "message_stop"})]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for name, data in ev:
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()); self.wfile.flush()


def text_of(m: dict) -> str:
    c = m.get("content")
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)


_run_seq = 0   # two runs in the same second must not share a run_id (shutil.move collision, cycle 88)

def run_agent(port: int, scratch: pathlib.Path, zai: bool, extra: tuple = ()) -> tuple[subprocess.CompletedProcess, float]:
    global _run_seq
    _run_seq += 1
    run_id = f"selftest-{'zai' if zai else 'oai'}-{time.strftime('%m%d-%H%M%S')}-{_run_seq:02d}"
    cmd = [sys.executable, "harness/agent.py", "--problems", PROBLEM, "--turns", "12", "--no-adaptive-turns", "--workers", "1",
           "--max-tokens", "4000", "--model", "fake-selftest", "--reasoning-effort", "low", "--max-api-retries", "1",
           "--run-id", run_id, "--work-root", str(scratch / f"work-{run_id}"), *extra]
    env = dict(os.environ)
    if zai:
        env["LRA_SELFTEST_ANTHROPIC_URL"] = f"http://127.0.0.1:{port}"
    else:
        cmd += ["--endpoint", "openai", "--base-url", f"http://127.0.0.1:{port}/v1", "--api-model", "fake", "--no-budget-forcing"]
    t0 = time.time()
    pr = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env)
    run_dir = ROOT / "probe/runs" / run_id
    if run_dir.exists():
        shutil.move(str(run_dir), str(scratch / run_id))   # keep fake records out of the bank import
    return pr, time.time() - t0


def last_user_text(req: dict) -> str:
    return text_of(req["messages"][-1]) if req.get("messages") else ""


def main() -> int:
    global PROBLEM
    best = (ROOT / f"harness/work/{PROBLEM}/best.lean")
    candidate = best.read_text().rstrip() + "\n\n"   # same proof, new bytes: a new sha, so it is compiled, not a duplicate
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="lra-selftest-"))

    # run 1: self-hosted (OpenAI) path without budget forcing
    Fake.steps = script(candidate); Fake.seen = []
    pr1, sec1 = run_agent(port, scratch, zai=False)
    reqs = Fake.seen
    first_user = next((text_of(m) for m in reqs[0]["messages"] if m["role"] == "user"), "") if reqs else ""
    last_new = lambda i: last_user_text(reqs[i]) if i < len(reqs) else ""
    checks = {
        "opening_move": "OPENING MOVE" in first_user,
        "trunc_handback": REASONING_TAIL in last_new(1) and "Do not rewrite the current best unchanged" in last_new(1),
        "auto_check": "auto lean_check of candidate.lean" in last_new(2),
        "dup_note": "byte-identical to an attempt already checked" in last_new(3) and "auto lean_check" not in last_new(3),
        "finish_guard": "finish rejected" in last_new(4),
    }
    oai_reqs = reqs

    # run 2: z.ai (Anthropic) path: capped thinking turn -> no-thinking rescue -> rescued write is executed
    Fake.steps = [{"length": True, "reasoning": "x " * 2000 + REASONING_TAIL},
                  {"tool": "write_file", "args": {"path": "candidate.lean", "content": candidate}},
                  {"tool": "finish", "args": {}}]
    Fake.seen = []
    OAI_ONLY = os.environ.get("LRA_SELFTEST_OAI_ONLY") == "1"   # 2026-10-09: replication without the Anthropic SDK runs only the OpenAI path
    pr2, sec2 = run_agent(port, scratch, zai=True) if not OAI_ONLY else (pr1, 0.0)
    z = Fake.seen

    # run 3: z.ai path, the no-thinking retry answers with GLM template markup in plain text instead of a tool_use block
    markup = ("<tool_call>write_file<arg_key>path</arg_key><arg_value>candidate.lean</arg_value>"
              f"<arg_key>content</arg_key><arg_value>{candidate}</arg_value></tool_call>")
    Fake.steps = [{"length": True, "reasoning": "x " * 2000 + REASONING_TAIL}, {"text": markup}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    if not OAI_ONLY:
        pr3, sec3 = run_agent(port, scratch, zai=True)
        z3 = Fake.seen
        checks["nothink_markup"] = len(z3) > 2 and "auto lean_check of candidate.lean" in last_user_text(z3[2])

    # run 4: OpenAI path, the model ends its first turn with plain text (gpt-oss in the second-model screen): the run must continue
    Fake.steps = [{"text": "I think the proof is already optimal."}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr4, sec4 = run_agent(port, scratch, zai=False)
    z4 = Fake.seen
    checks["text_end_guard"] = len(z4) > 1 and "You ended your turn without a tool call" in last_user_text(z4[1])

    # run 5: a candidate whose rewrite rule has the wrong direction (putnam_1964_a4 best with `← key (n - i)` reversed): the write's
    # auto-check must repair it (reversed rule / simp_rw / erw / simp only) and report it (cycle 53)
    a4 = (ROOT / "harness/work/putnam_1964_a4/best.lean").read_text()
    broken = a4.replace("← key (n - i)", "key (n - i)", 1)
    if broken != a4:
        PROBLEM, saved = "putnam_1964_a4", PROBLEM
        Fake.steps = [{"tool": "write_file", "args": {"path": "candidate.lean", "content": broken}}, {"tool": "finish", "args": {}}]
        Fake.seen = []
        pr5, sec5 = run_agent(port, scratch, zai=False)
        PROBLEM = saved
        z5 = Fake.seen
        checks["rw_repair"] = len(z5) > 1 and "failed rewrite repaired" in last_user_text(z5[1])
    else:
        checks["rw_repair"] = False
    # run 6: a superfluous tactic after the goal is closed ("No goals to be solved"): the auto-check must delete the no-op line (cycle 54)
    b2 = (ROOT / f"harness/work/{PROBLEM}/best.lean").read_text().rstrip()
    indent = next((l[:len(l) - len(l.lstrip())] for l in reversed(b2.split("\n")) if l.strip() and l.startswith(" ")), "  ")
    Fake.steps = [{"tool": "write_file", "args": {"path": "candidate.lean", "content": b2 + "\n" + indent + "rfl\n"}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6, sec6 = run_agent(port, scratch, zai=False)
    z6 = Fake.seen
    checks["noop_delete"] = len(z6) > 1 and "deleted no-op line" in last_user_text(z6[1])

    # run 6b (--relative-error-lines, cycle 76): a failing line inserted after `classical` in the b2 best. The write's auto-check must
    # report it as `line k `<text>`` of the declaration, not as the scratch file's line (head lines + k).
    _ls = b2.split("\n"); _k = next((i for i, l in enumerate(_ls) if l.strip() == "classical"), 0) + 2   # 1-based line of the insert
    _bad = "\n".join(_ls[:_k - 1] + [indent + "have hx : (1 : ℕ) = 2 := rfl"] + _ls[_k - 1:])
    Fake.steps = [{"tool": "write_file", "args": {"path": "candidate.lean", "content": _bad + "\n"}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6b, sec6b = run_agent(port, scratch, zai=False, extra=("--relative-error-lines",))
    z6b = Fake.seen
    sys.path.insert(0, str(ROOT))   # this script runs with harness/ as its import root
    from harness.leantools import head_line_count as _hlc6b, ROWS as _R6b
    from probe.verify_candidates import newest_first as _nf6b
    _raw6b = _hlc6b(_R6b[PROBLEM], _nf6b(_R6b[PROBLEM]["version_info"])[0]) + _k
    _t6b = last_user_text(z6b[1]) if len(z6b) > 1 else ""
    checks["error_lines"] = f"line {_k} `have hx" in _t6b and f"{_raw6b}:" not in _t6b

    # run 6d (--closed-lessons, cycle 80; DEFAULT ON since cycle 89, flagab-1010-1014 verdict +2.76, 7/10 better, new-file +4.19):
    # the first message carries the habits by default, and only --no-closed-lessons removes them
    Fake.steps = [{"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6d, sec6d = run_agent(port, scratch, zai=False, extra=())
    z6d = Fake.seen
    _f6d = next((text_of(m) for m in z6d[0]["messages"] if m["role"] == "user"), "") if z6d else ""
    checks["closed_lessons"] = ("HABITS OF THE STRONGEST PROVERS" in _f6d and "with_reducible apply Or.inl" in _f6d
                                and "HABITS OF THE STRONGEST" in first_user)
    Fake.steps = [{"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6d2, _ = run_agent(port, scratch, zai=False, extra=("--no-closed-lessons",))
    _f6d2 = next((text_of(m) for m in Fake.seen[0]["messages"] if m["role"] == "user"), "") if Fake.seen else ""
    checks["closed_lessons"] = checks["closed_lessons"] and "HABITS OF THE STRONGEST" not in _f6d2
    _s6d = next((text_of(m) for m in z6d[0]["messages"] if m["role"] == "system"), "") if z6d else ""   # a run without --token-rules

    # run 6f (--token-rules, cycle 83): the TOKEN COUNTING lexer rules reach a run without --length-tools only with the flag
    Fake.steps = [{"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6f, sec6f = run_agent(port, scratch, zai=False, extra=("--token-rules",))
    _s6f = next((text_of(m) for m in Fake.seen[0]["messages"] if m["role"] == "system"), "") if Fake.seen else ""
    # run 6g (--normalize, 2026-10-10): after the session the lexer post-pass rewrites the best (λx, $, ...), compiles it on every
    # toolchain and records the improvement with provenance.normalized (the fixture best normalizes 205 -> 189 tokens)
    Fake.steps = [{"tool": "write_file", "args": {"path": "candidate.lean", "content": candidate}}, {"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    _before6g = {q.name for q in scratch.iterdir()}
    pr6g, sec6g = run_agent(port, scratch, zai=False, extra=("--normalize",))
    _recs6g = [json.loads(l) for q in scratch.iterdir() if q.name not in _before6g and q.name.startswith("selftest-")
               for f in [q / "verified.jsonl"] if f.exists() for l in f.open() if l.strip()]
    checks["normalize"] = "normalized:" in pr6g.stdout and any((r.get("provenance") or {}).get("normalized") for r in _recs6g)

    checks["token_rules"] = ("TOKEN COUNTING" in _s6f and "`f $ g x` saves 1" in _s6f and "`λx => e` saves 1" in _s6f
                             and bool(_s6d) and "TOKEN COUNTING" not in _s6d)

    # run 6e (BFS deep dive, 2026-10-09): a --from-reference restart on a workspace with history (three flat runs at ~70, like the A100
    # copies harness/exp_variants.sh uses) must stay a restart: the adaptive rules must not turn it into a FRESH START or a 6-turn polish,
    # structural mode must not add its brief and effort raise, the strategy brief stays, and the budget is --turns as given.
    _w6e = scratch / "work-6e"; (_w6e / PROBLEM).mkdir(parents=True, exist_ok=True)
    _att6e = [{"run_id": f"st-r{i}", "ok": True, "score": s, "sha": f"s{i}", "t": f"2026-10-0{i + 1}T00:00:00"} for i, s in enumerate((69.8, 69.9, 70.0))]
    (_w6e / PROBLEM / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n- NOTES-6E-MARKER: lemma names from earlier runs\n")
    (_w6e / PROBLEM / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 70.0, "proof": None, "tokens": 1, "heartbeats": None},
                                                            "attempts": _att6e, "runs": [{"run_id": f"st-r{i}"} for i in range(3)]}))
    Fake.steps = [{"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6e, sec6e = run_agent(port, scratch, zai=False, extra=("--adaptive-turns", "--from-reference", "--brief", "restructure", "--work-root", str(_w6e)))
    _f6e = next((text_of(m) for m in Fake.seen[0]["messages"] if m["role"] == "user"), "") if Fake.seen else ""
    checks["from_reference_guard"] = ("scout brief: restructure" in pr6e.stdout and "FRESH START" not in pr6e.stdout and "structural mode" not in pr6e.stdout
                                      and "SCOUT RUN" in _f6e and "STRUCTURAL PASS" not in _f6e and "You have 12 tool turns" in _f6e
                                      and "NOTES-6E-MARKER" in _f6e    # warm: the notes reach the opening message
                                      and "BLIND TARGET: the stored best has 1 tokens" in _f6e)   # 2026-10-10: the blind target

    # run 6h (--lever-review, cycle 88): a workspace with three flat runs at ~70 (adaptive turns off, so no fresh start) opens with the
    # LEVER REVIEW only with the flag; the same workspace without the flag gets the structural brief alone
    def _plateau_ws(tag):
        w = scratch / f"work-6h-{tag}"; (w / PROBLEM).mkdir(parents=True, exist_ok=True)
        att = [{"run_id": f"lv-r{i}", "ok": True, "score": s, "sha": f"l{i}", "t": f"2026-10-0{i + 1}T00:00:00"} for i, s in enumerate((69.8, 69.9, 70.0))]
        (w / PROBLEM / "notes.md").write_text("# Notes (yours to keep; persisted across runs)\n")
        (w / PROBLEM / "state.json").write_text(json.dumps({"problem": PROBLEM, "best": {"score": 70.0, "proof": None, "tokens": 1, "heartbeats": None},
                                                         "attempts": att, "runs": [{"run_id": f"lv-r{i}"} for i in range(3)]}))
        return w
    _f6h = {}
    for _tag, _ex in (("on", ("--lever-review",)), ("off", ())):
        Fake.steps = [{"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
        Fake.seen = []
        _p6h, _ = run_agent(port, scratch, zai=False, extra=_ex + ("--no-adaptive-turns", "--work-root", str(_plateau_ws(_tag))))
        _f6h[_tag] = (_p6h.stdout, next((text_of(m) for m in Fake.seen[0]["messages"] if m["role"] == "user"), "") if Fake.seen else "")
    checks["lever_review"] = ("lever review first" in _f6h["on"][0] and "LEVER REVIEW FIRST" in _f6h["on"][1] and "`fun_induction f`" in _f6h["on"][1]
                              and "STRUCTURAL PASS" in _f6h["off"][1] and "LEVER REVIEW" not in _f6h["off"][1])

    # run 6i (budget gate, 2026-10-11; hard worst-case bound): DeepSeek preset against the fake server.
    # (a) cap $0.01: even turn 0's worst case (its 40k output cap x $1.20/1M alone is $0.048) does not fit, so NO request may be sent;
    # (b) cap $1.00: requests are sent and metered at the list price, $0.00042 each (1000 in x $0.30 + 100 out x $1.20 per 1M),
    #     not the $0.0001 the fake reports (ClinePass reports half the list price).
    _p6i = {}; _sp6i = {}; _n6i = {}
    # (b) also records the milestone $0.0004: the first request ($0.00042) crosses it -> state.json budget_milestones["0.0004"] + warning line
    for _tag, _cap in (("a", "0.01"), ("b", "1.00")):
        Fake.steps = [{"tool": "finish", "args": {}}] * 3
        Fake.seen = []
        _w6i = scratch / f"work-6i{_tag}"
        os.environ["LRA_SELFTEST_PRESET_URL"] = f"http://127.0.0.1:{port}/v1"
        try:
            _p6i[_tag], _ = run_agent(port, scratch, zai=False, extra=("--model-preset", "deepseek-v4.1-flash", "--budget-usd", _cap,
                                                                     "--budget-milestones", "0.0004", "--work-root", str(_w6i)))
        finally:
            os.environ.pop("LRA_SELFTEST_PRESET_URL", None)
        _n6i[_tag] = len(Fake.seen)
        try:
            _st6i = json.loads((_w6i / PROBLEM / "state.json").read_text())
            _sp6i[_tag] = float(_st6i.get("api_spend") or 0); _ms6i = _st6i.get("budget_milestones") or {}
        except Exception:  # noqa: BLE001
            _sp6i[_tag] = None; _ms6i = {}
    checks["budget_gate"] = (_n6i["a"] == 0 and "budget reached" in _p6i["a"].stdout and not _sp6i["a"]
                             and _n6i["b"] >= 1 and _sp6i["b"] is not None and abs(_sp6i["b"] - 0.00042 * _n6i["b"]) < 1e-6
                             and "budget milestone $0.0004 crossed" in _p6i["b"].stdout and abs(_ms6i.get("0.0004", {}).get("spend", 0) - 0.00042) < 1e-6)

    # run 6j (runaway tool calls, 2026-10-11): a tool call cut at the output cap inside its arguments (finish_reason length, unterminated
    # JSON) is never re-sent: the next request carries a short stub and a tool result saying so. (1) Sol's degenerate tail (tabs/blank
    # lines): the output cap is NOT escalated; (2) a legitimate long write cut mid-proof: it escalates as before (run 1's capped
    # thinking turn, the control, escalates too).
    _legit6j = next(json.loads(l) for l in (ROOT / "data/benchmark_warmup.jsonl").open() if '"putnam_1995_a3"' in l)["src"]
    _raw6j = json.dumps({"path": "candidate.lean", "content": "RUNAWAY-6J-MARKER lemma x :"})[:-2] + "\\t\\t\\t \\n" * 3000
    _cut6j = json.dumps({"path": "candidate.lean", "content": "LEGIT-6J-MARKER " + _legit6j}, ensure_ascii=False)
    _cut6j = _cut6j[: int(len(_cut6j) * 0.7)]
    Fake.steps = [{"runaway": True, "tool": "write_file", "raw": _raw6j}, {"runaway": True, "tool": "write_file", "raw": _cut6j},
                  {"tool": "finish", "args": {}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6j, sec6j = run_agent(port, scratch, zai=False)
    z6j = Fake.seen
    _m6j = [json.dumps(q["messages"], ensure_ascii=False) for q in z6j]
    _mx6j = [q.get("max_tokens", 0) for q in z6j]
    checks["runaway_drop"] = (len(z6j) > 2 and "RUNAWAY-6J-MARKER" not in _m6j[1] + _m6j[2] and "LEGIT-6J-MARKER" not in _m6j[2]
                              and "it was dropped and nothing was executed" in last_user_text(z6j[1])
                              and "repeated over and over" in last_user_text(z6j[1]) and "repeated over and over" not in last_user_text(z6j[2])
                              and _mx6j[1] == _mx6j[0] and _mx6j[2] > _mx6j[1]
                              and len(oai_reqs) > 1 and oai_reqs[1].get("max_tokens", 0) > oai_reqs[0].get("max_tokens", 0)
                              and pr6j.stdout.count("runaway write_file call cut at the output cap") == 2)
    # the detector itself on the run's two degenerate shapes (whitespace of varying length; a short line repeated) and a real long proof
    from harness.agent import degenerate_tail as _dt
    _ws6j = "".join("\\t" * (3 + i % 11) + " \\n " for i in range(400))
    _sorry6j = '{"content": "theorem t : p := by\\n  constructor' + "\\n  all_goals sorry" * 300
    _proof6j = json.dumps({"content": _legit6j}, ensure_ascii=False)
    checks["degenerate_tail"] = (_dt(_ws6j) and _dt(_sorry6j) and not any(_dt(_proof6j[: int(len(_proof6j) * f)]) for f in (0.3, 0.6, 0.9, 1.0))
                                 and _dt(_raw6j) and not _dt(_cut6j))

    # run 6c (--variant-scores, cycle 78): a batch of the b2 best (a new best in the scratch workspace) and the same proof with a second
    # `classical` (compiles, not above the new best). Row b must carry a numeric provisional score and a negative vs_best, not score null.
    _b2c = "\n".join(_ls[:_k - 1] + [indent + "classical"] + _ls[_k - 1:])
    Fake.steps = [{"tool": "lean_check_variants", "args": {"variants": [{"label": "a", "content": b2 + "\n"}, {"label": "b", "content": _b2c + "\n"}]}},
                  {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr6c, sec6c = run_agent(port, scratch, zai=False, extra=("--variant-scores",))
    z6c = Fake.seen
    try:
        _rows6c = {r_["label"]: r_ for r_ in json.loads(last_user_text(z6c[1]))["variants"]}
        checks["variant_scores"] = (isinstance(_rows6c["b"].get("score"), (int, float)) and _rows6c["b"].get("vs_best", 1) < 0
                                    and "provisional" in str(_rows6c["b"].get("score_kind")) and (_rows6c["a"].get("vs_best") or 0) > 0)
    except Exception:  # noqa: BLE001
        checks["variant_scores"] = False

    # run 7: a variant that compiles on the primary toolchain but not on the older ones (a real fresh-zai-p1 a4 candidate: `.not_finite`
    # does not resolve on v4.26.0/v4.25.0): the batch result must say why, per variant (cycle 56)
    fixture = (ROOT / "harness/selftest_fixtures/a4_fails_v426.lean").read_text()
    PROBLEM, saved = "putnam_1964_a4", PROBLEM
    Fake.steps = [{"tool": "lean_check_variants", "args": {"variants": [{"label": "V1", "content": fixture}]}}, {"tool": "finish", "args": {}}]
    Fake.seen = []
    pr7, sec7 = run_agent(port, scratch, zai=False)
    PROBLEM = saved
    z7 = Fake.seen
    r7 = last_user_text(z7[1]) if len(z7) > 1 else ""
    checks["compat_why"] = "compat_failures" in r7 and "v4.26.0" in r7 and "not_finite" in r7 and "did_you_mean_here" in r7

    # run 8: a project problem whose proof was later simplified upstream (CCS bisimilarity_congr_choice: 180 tokens at cslib HEAD vs 251):
    # the first message must carry the precomputed upstream version, so the model does not dig through git log for it (cycle 57)
    PROBLEM, saved = "Cslib.CCS.bisimilarity_congr_choice", PROBLEM
    Fake.steps = [{"tool": "finish", "args": {}}]
    Fake.seen = []
    pr8, sec8 = run_agent(port, scratch, zai=False)
    PROBLEM = saved
    z8 = Fake.seen
    f8 = next((text_of(m) for m in z8[0]["messages"] if m["role"] == "user"), "") if z8 else ""
    checks["upstream_digest"] = "UPSTREAM (precomputed" in f8 and "bisimilarity_congr_choice` at upstream HEAD" in f8 and "```lean" in f8.split("UPSTREAM (precomputed", 1)[-1]

    # run 9 (--simp-prune): the a4 best with an unused lemma added to its `simp only [...]` list: the write's auto-check must drop it (cycle 58)
    a4b = (ROOT / "harness/work/putnam_1964_a4/best.lean").read_text()
    padded = a4b.replace("simp only [Prod.mk.injEq]", "simp only [Prod.mk.injEq, List.length_nil]", 1)
    if padded != a4b:
        PROBLEM, saved = "putnam_1964_a4", PROBLEM
        Fake.steps = [{"tool": "write_file", "args": {"path": "candidate.lean", "content": padded}}, {"tool": "finish", "args": {}}]
        Fake.seen = []
        pr9, sec9 = run_agent(port, scratch, zai=False, extra=("--simp-prune",))
        PROBLEM = saved
        z9 = Fake.seen
        checks["simp_prune"] = len(z9) > 1 and "auto_pruned" in last_user_text(z9[1]) and "dropped 1 unused lemma" in last_user_text(z9[1])
    else:
        checks["simp_prune"] = False

    srv.shutdown(); srv.server_close()   # after the LAST run: a shut-down but still bound socket accepts connections and never answers
    rescue = z[1] if len(z) > 1 else {}
    if not OAI_ONLY:
      checks["nothink_rescue"] = (bool(z) and z[0].get("stream") is True and rescue.get("stream") in (None, False)
                                and rescue.get("thinking") == {"type": "disabled"} and REASONING_TAIL in last_user_text(rescue)
                                and len(z) > 2 and "auto lean_check of candidate.lean" in last_user_text(z[2]))

    for k, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {k}")
    print(f"oai: requests={len(oai_reqs)} rc={pr1.returncode} {sec1:.0f}s | zai: requests={len(z)} rc={pr2.returncode} {sec2:.0f}s | scratch={scratch}")
    if not all(checks.values()):
        for pr in (pr1, pr4, pr6, pr6b, pr6c, pr6d, pr6e, pr6f, pr6g, pr6j, pr7, pr8) + ((pr2, pr3) if not OAI_ONLY else ()) + ((pr5,) if 'pr5' in locals() else ()):
            print(pr.stdout[-1500:], pr.stderr[-1500:], sep="\n")
        for i in range(min(4, len(z))):
            print(f"--- zai request {i} stream={z[i].get('stream')} thinking={z[i].get('thinking')} last message:\n{last_user_text(z[i])[:400]}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
