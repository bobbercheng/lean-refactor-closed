#!/usr/bin/env python3
"""Offline test of the junk guard (2026-10-14; llm/junk.py, llm/openai_compat.py stream guard, harness/agent.py history guard).
A local fake OpenAI-style SSE server streams (1) a normal turn: reasoning text, reasoning_details in pieces, a tool call in pieces; (2) a junk
turn: a tool call whose arguments degenerate into a whitespace run for 400 chunks; (3) the same junk with no usage record available.
Checks: (1) parses exactly; the guard does not fire on it; (2) the stream is cut within a few thousand characters (the server sees the
connection close long before its 400 chunks), the call comes back as {_raw_arguments, _junk}, stop max_tokens, finish junk_abort, and its
usage is the fake /generation record; (3) without a record the worst case is charged (full max_tokens). Plus detector checks on synthetic
junk and legitimate texts.    python3 harness/test_junk_guard.py      (a few seconds, no network, no Lean)"""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ["LRA_SELFTEST_GENERATION"] = "1"
from llm import openai_compat as oai  # noqa: E402
from llm.junk import junk_reason, StreamGuard  # noqa: E402

SENT = {"junk": 0, "closed_early": False}
GEN = {"gen-junk-1": {"native_tokens_prompt": 7000, "native_tokens_completion": 380, "native_tokens_cached": 6000, "total_cost": 0.0089}}


def chunk(delta=None, fin=None, gid="gen-ok-1", usage=None):
    d = {"id": gid, "choices": [{"index": 0, "delta": delta or {}, "finish_reason": fin}]}
    if usage:
        d["usage"] = usage
    return b"data: " + json.dumps(d).encode() + b"\n\n"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):   # /generation?id=...
        gid = self.path.split("id=")[-1]
        body = json.dumps({"data": GEN[gid]}).encode() if gid in GEN else b'{"error": {"code": 404}}'
        self.send_response(200 if gid in GEN else 404); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode = req["messages"][-1]["content"]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        try:
            if mode == "normal":
                for c in (chunk({"reasoning": "plan: "}), chunk({"reasoning": "check it", "reasoning_details": [{"type": "reasoning.text", "index": 0, "text": "plan: "}]}),
                          chunk({"reasoning_details": [{"type": "reasoning.text", "index": 0, "text": "check it"}, {"type": "reasoning.encrypted", "index": 1, "data": "AAA"}]}),
                          chunk({"reasoning_details": [{"type": "reasoning.encrypted", "index": 1, "data": "BBB", "id": "rs_1", "format": "openai-responses-v1"}]}),
                          chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "write_file", "arguments": '{"path": "candidate.lean", '}}]}),
                          chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"content": "theorem t : True := by\\n  trivial\\n"}'}}]}),
                          chunk({}, fin="tool_calls"),
                          chunk(usage={"prompt_tokens": 900, "completion_tokens": 60, "prompt_tokens_details": {"cached_tokens": 800}, "cost": 0.001})):
                    self.wfile.write(c); self.wfile.flush()
            else:
                gid = "gen-junk-1" if mode == "junk" else "gen-junk-unknown"
                self.wfile.write(chunk({"tool_calls": [{"index": 0, "id": "call_j", "function": {"name": "lean_skeleton", "arguments": '{"content": "lemma x : True := by\\n'}}]}, gid=gid))
                for i in range(400):
                    self.wfile.write(chunk({"tool_calls": [{"index": 0, "function": {"arguments": "\\t\\t\\t \\n" * 8}}]}, gid=gid)); self.wfile.flush()
                    SENT["junk"] = i + 1
                    time.sleep(0.002)
                self.wfile.write(chunk({}, fin="tool_calls", gid=gid))
        except (BrokenPipeError, ConnectionResetError):
            SENT["closed_early"] = True


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    kw = dict(base_url=base, api_key="x", model="fake", max_tokens=12000, system="s", tools=[{"name": "write_file", "description": "w",
              "input_schema": {"type": "object", "properties": {}}}], think_mode="details", guard=True)
    ok = {}
    m = oai.create(messages=[{"role": "user", "content": "normal"}], **kw)
    tu = [b for b in m.content if b.type == "tool_use"]; th = [b for b in m.content if b.type == "thinking"]
    ok["normal: tool call parsed"] = len(tu) == 1 and tu[0].input == {"path": "candidate.lean", "content": "theorem t : True := by\n  trivial\n"}
    ok["normal: stop and usage"] = m.stop_reason == "tool_use" and m.usage.input_tokens == 900 and m.usage.output_tokens == 60 and m.raw_finish_reason == "tool_calls"
    ok["normal: reasoning_details merged by index"] = (th and th[0].details == [{"type": "reasoning.text", "index": 0, "text": "plan: check it"},
                                                                           {"type": "reasoning.encrypted", "index": 1, "data": "AAABBB", "id": "rs_1", "format": "openai-responses-v1"}])
    acc = {}
    oai._merge_details(acc, [{"type": "reasoning.text", "index": 0, "text": "a"}, {"type": "reasoning.text", "index": 0, "text": "b"},
                             {"type": "reasoning.encrypted", "index": 0, "data": "SIG", "format": "google-gemini-v1", "id": "x"}])
    ok["details: same index, different types stay apart (Gemini)"] = list(acc.values()) == [
        {"type": "reasoning.text", "index": 0, "text": "ab"}, {"type": "reasoning.encrypted", "index": 0, "data": "SIG", "format": "google-gemini-v1", "id": "x"}]
    t0 = time.time()
    m = oai.create(messages=[{"role": "user", "content": "junk"}], **kw)
    tu = [b for b in m.content if b.type == "tool_use"][0]
    time.sleep(0.5)
    ok["junk: cut early (server saw the close)"] = SENT["closed_early"] and SENT["junk"] < 120 and len(tu.input.get("_raw_arguments", "")) < 6000
    ok["junk: marked, stop max_tokens, junk_abort"] = "_junk" in tu.input and m.stop_reason == "max_tokens" and m.raw_finish_reason == "junk_abort"
    ok["junk: usage from the generation record"] = m.usage.output_tokens == 380 and m.usage.input_tokens == 7000 and m.usage.cache_read == 6000
    print(f"  junk stream: {SENT['junk']} of 400 chunks sent before the close, {len(tu.input['_raw_arguments'])} chars kept, {time.time() - t0:.1f}s")
    SENT.update(junk=0, closed_early=False)
    _gu = oai.generation_usage
    oai.generation_usage = lambda *a, **k: _gu(*a, tries=2, wait=0.1)
    m = oai.create(messages=[{"role": "user", "content": "junk-unknown"}], **kw)
    oai.generation_usage = _gu
    ok["junk without a record: worst case charged"] = m.usage.output_tokens == 12000 and m.raw_finish_reason == "junk_abort"
    # detector: synthetic junk shapes are flagged, legitimate shapes are not
    legit = ["theorem t : a = b := by\n" + "".join(f"  have h{i} : f {i} = g {i} := by simp [f, g, h{i - 1}]\n" for i in range(400)),
             "  · simp\n" * 30 + "  · omega\n",   # short legitimate repetition (under the window)
             "-- " + "=" * 120 + "\n" + "x" * 500]
    junk = ['{"content": "x"' + "\\t\\t\\t \\n" * 600, "\n  all_goals sorry" * 400, "'" * 60 + " vs" + ("'" * 97 + " vs") * 60, "a" * 70_000]
    ok["detector: junk flagged"] = all(junk_reason(j) for j in junk)
    ok["detector: legitimate not flagged"] = not any(junk_reason(t) for t in legit)
    g = StreamGuard(); fired = None
    for i in range(1, 400):
        fired = fired or g.feed(0, '{"c": "' + "  · simp\\n" * i)
    ok["stream guard: fires on a long single-line repeat"] = bool(fired)
    srv.shutdown()
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"{sum(ok.values())}/{len(ok)} checks passed")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
