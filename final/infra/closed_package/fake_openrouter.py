#!/usr/bin/env python3
"""b66 closed package (2026-10-27): the scripted OpenAI-compatible server of the $0 rehearsal (run_final.py --fake-model). No model, no key,
no network beyond the docker bridge: the shard units get LRA_SELFTEST_PRESET_URL=http://<this server>/v1, which agent.py (every session,
inside its container: hx_heldout DOCKER_PASS_NAMES) and harness/architect.endpoint_for (the review, in the router) use instead of the
preset's OpenRouter URL, reading and sending no key.

What it answers (POST .../chat/completions, streamed or not, the shapes of harness/selftest.py's Fake):
  review   (the request offers submit_edits, the review's tool, or submit_proofs): that tool with nothing in it, usage 3,000 in / 300 out
           ($0.0001 billed)
  session  (the request offers read_file, agent.py's tool): read_file original.lean lines 1-3 (no compile, no file change), usage --prompt-tokens in / 1,000 out
           ($0.0001 billed). The meter charges max(billed, list) (b65: Sol at $2.00 / $10.0 per 1M): 100k in = about $0.21 a turn, so a
           session spends its rung in a few turns and ends "budget reached", the way a real ladder fills its rungs
  repair   (b75: the request offers submit_repair, R6's repair turn, harness/review.py): a give-up, usage as a review call
The proofs therefore stay the seeds through the ladder; the router's $0 stages (cleanups, crossover, end stage) and the submission
writer still run for real on them.
b75 R6 rehearsal (opt-in, LRA_FAKE_R6=1 in the launcher's environment, --runner local; never in a real run, which starts no fake): the
review proposes, on the proof it is shown (generic text rules, no row text), a BROKEN edit (a unique tactic line + ` ]]`, a parse error),
an ASCRIPTION drop when a one-line `have h : T := e` exists (`have h := e`: fewer tokens when it compiles), up to three DELETIONS of
unique childless tactic lines (two when there is an ascription edit; some compile, some do not) and a COMMENT edit (compiles, no gain); a repair turn
answers the broken edit with its line plus a comment (compiles), and the failed deletions alternately with a give-up (booked as one call)
and an HTTP 400 refusal (never billed: the repairs of that round stop, nothing is booked for it); the same edit always gets the same
answer (retries included). So one rehearsal shows a repair sent, compiled and booked once, a give-up booked once, a refused repair that
books nothing, and the stack attempted on the compiling edits (verified and banked as review_stack when a deletion paid). Headers are never read or logged (no key is ever sent here; this is a guard against a future change).
b85 style_rw rehearsal (opt-in, LRA_FAKE_STYLE_RW=1): the style_rw step's rewrite calls (submit_proofs on a prompt that names the scoring
dialect; "style_rw" in the counts) get four declarations built from the proof shown (unchanged, `:= by unhygienic`, a broken line, the
statement re-typed) and a repair call gets the failing rewrite with its broken line removed; without the flag they get no proofs (one
billed call, nothing accepted), as the review's.
Counts per kind go to --stats (rewritten atomically after every request); b67: also per kind and model id ("models"). b70: --events F
appends one JSON line per request ({"t": UTC time with ms, "kind", "n": its number within the kind, "model", "gen": the generation id the
answer carries}; never a header or any message content), so a rehearsal can show WHEN each model was asked (the Terra tail after the
review) and match a session turn's recorded gen_id to its request.

    python3 infra/closed_package/fake_openrouter.py --host 172.17.0.1 --port-file F --stats S [--events E] [--prompt-tokens 100000]"""
from __future__ import annotations

import argparse, http.server, json, os, re, threading, time
from pathlib import Path

LOCK = threading.Lock()
STATS: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": 0, "review": 0, "repair": 0, "repair_refused": 0,
                "style_rw": 0, "other": 0}
CFG: dict = {"prompt_tokens": 100000, "stats": None, "events": None}


def _tools(body: dict) -> list[str]:
    out = []
    for t in body.get("tools") or []:
        if isinstance(t, dict):
            out.append(((t.get("function") or {}).get("name")) or t.get("name") or "")
    return out


def reply(body: dict) -> tuple[str, dict, dict]:
    """(kind, assistant message, usage) for one request; kind "repair_refused" (b75 R6 rehearsal) is answered with HTTP 400."""
    names = _tools(body)
    if "submit_repair" in names:   # b75: R6's repair turn (harness/review.py _repairs)
        kind, usage = "repair", {"prompt_tokens": 3000, "completion_tokens": 300, "cost": 0.0001}
        call = ("submit_repair", r6_repair(body) if CFG.get("r6") else {"give_up": True, "replace": ""})
        if call[1] is None:
            return "repair_refused", {}, {}
    elif "submit_proofs" in names and _is_style_rw(body):   # b85: the style_rw step's rewrite / repair call (harness/style_rw.py)
        kind, usage = "style_rw", {"prompt_tokens": 3000, "completion_tokens": 300, "cost": 0.0001}
        call = ("submit_proofs", {"proofs": style_rw_proofs(body) if CFG.get("style_rw") else []})
    elif "submit_edits" in names or "submit_proofs" in names:   # the review (harness/review.py) / the architect's proofs call
        kind, usage = "review", {"prompt_tokens": 3000, "completion_tokens": 300, "cost": 0.0001}
        call = ("submit_edits", {"edits": []}) if "submit_edits" in names else ("submit_proofs", {"proofs": []})
        if CFG.get("sorry_proofs") and "submit_edits" in names:   # b71 review: the review proposes a `stop` (sorry without the word)
            call = ("submit_edits", {"edits": [{"label": "stop", "find": ":= by", "replace": ":= by\n  stop", "why": "adversarial (R1)"}]})
        elif CFG.get("r6") and "submit_edits" in names:   # b75 R6 rehearsal: broken / deletions / comment (module notes)
            call = ("submit_edits", {"edits": r6_edits(body)})
    elif "read_file" in names:   # an agent.py session
        kind, usage = "session", {"prompt_tokens": int(CFG["prompt_tokens"]), "completion_tokens": 1000, "cost": 0.0001}
        call = ("read_file", {"path": "original.lean", "start": 1, "end": 3})
        if CFG.get("sorry_proofs"):   # b71 review (R1 adversarial rehearsal; off unless LRA_FAKE_SORRY_PROOFS=1)
            call = sorry_session_call(body) or call
    else:
        return "other", {"role": "assistant", "content": "ok"}, {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.0001}
    with LOCK:
        n = STATS[kind] + 1
    msg = {"role": "assistant", "content": None,
           "tool_calls": [{"id": f"call_{kind}_{n}", "type": "function", "function": {"name": call[0], "arguments": json.dumps(call[1])}}]}
    return kind, msg, usage


# ------------------------------------------------------------------------------------------- b75 R6 rehearsal (LRA_FAKE_R6=1, opt-in)
_BEST = re.compile(r"CURRENT BEST[^\n]*\n```lean\n(.*?)\n```", re.S)          # harness/review.prompt: the proof under review
_EDIT = re.compile(r"\nfind:\n```lean\n(.*?)\n```\nreplace:\n```lean\n(.*?)\n```", re.S)   # harness/review.repair_prompt
_OPENERS = ("case ", "| ", "next", ". ", "· ", "--", "theorem", "lemma", "induction", "cases", "rcases", "obtain", "match", "calc", "refine",
            "constructor", "by", "fun", "show", "focus", "all_goals", "any_goals", "on_goal")
_HAVE = re.compile(r"^(\s*)have (\S+) : (.+?) := (.+)$")
_LIKELY = ("rename_i", "skip", "clear", "try ", "have ", "intros", "dsimp", "norm_num", "unfold", "simp only")
R6_MEMO: dict = {}     # a deletion's find text -> its repair answer (the same edit always gets the same answer, retries included)
R6_CYCLE = [0]         # the next failed deletion's answer: even = a give-up, odd = an HTTP 400 refusal


def _user_text(body: dict) -> str:
    u = next((m.get("content") for m in reversed(body.get("messages") or []) if isinstance(m, dict) and m.get("role") == "user"), "") or ""
    return " ".join(str(x.get("text") or "") for x in u if isinstance(x, dict)) if isinstance(u, list) else str(u)


def _ind(line: str) -> int:
    return len(line) - len(line.lstrip())


def r6_edits(body: dict) -> list:
    """Generic edits on the proof the review shows (no row text): BROKEN (the last unique tactic line + ` ]]`), up to three DELETIONS of
    unique childless one-line tactics (find = the line with its newline), and a COMMENT on another unique line."""
    m = _BEST.search(_user_text(body))
    proof = m.group(1) if m else ""
    lines = proof.split("\n")
    start = next((i for i, l in enumerate(lines) if ":= by" in l or l.rstrip().endswith(":=")), None)   # the body starts after it
    if not proof or start is None or len(lines) - start < 4:
        return []
    single, dels = [], []
    for i, l in enumerate(lines[start + 1:], start + 1):
        t = l.strip()
        if not t or "--" in l or ":= by" in l or l.rstrip().endswith(":=") or proof.count(l) != 1:   # (a trailing comment would swallow ` ]]`)
            continue
        single.append(l)
        nxt = next((x for x in lines[i + 1:] if x.strip()), "")
        prev = lines[i - 1].rstrip()
        if (not t.startswith(_OPENERS) and not t.endswith(("=>", "by", "with", "<;>", "do", "where", ",", "(", "[", "{")) and _ind(nxt) <= _ind(l)
                and not prev.endswith(("<;>", "by", "=>", ",")) and proof.count("\n" + l + "\n") == 1 and _ind(l) > 0):
            dels.append(l)
    if len(single) < 2:
        return []
    broken, comment = single[-1], single[-2]
    dels = [l for l in dels if l not in (broken, comment)]
    pick = [l for l in dels if l.strip().startswith(_LIKELY)][:2]   # two likely-redundant one-liners (keywords only) ...
    pick += [l for l in reversed(dels) if l not in pick][:3 - len(pick)]   # ... and the last ones (closing tactics: likely needed)
    dels = sorted(pick, key=lines.index)
    asc = next(((l, m) for l in single if l not in (broken, comment) and (m := _HAVE.match(l)) and not m.group(4).lstrip().startswith("by")
                and ":=" not in m.group(4) and l.count(" : ") == 1), None)
    if asc:   # a type ascription dropped (`have h : T := e` -> `have h := e`): fewer tokens, compiles when e's type is T as written
        dels = [l for l in dels if l != asc[0]][-2:]
    out = [{"label": "r6_broken", "find": broken, "replace": broken + " ]]", "why": "rehearsal: a parse error (repaired)"}]
    if asc:
        m = asc[1]
        out.append({"label": "r6_ascr", "find": asc[0], "replace": f"{m.group(1)}have {m.group(2)} := {m.group(4)}", "why": "rehearsal: drop an ascription"})
    out += [{"label": f"r6_del_{k}", "find": "\n" + l + "\n", "replace": "\n", "why": "rehearsal: a deletion"} for k, l in enumerate(dels, 1)]
    out.append({"label": "r6_comment", "find": comment, "replace": comment + "  -- r6 note", "why": "rehearsal: compiles, no gain"})
    return out


def r6_repair(body: dict):
    """submit_repair arguments for one repair turn, or None = refuse it (HTTP 400). The broken edit: its line plus a comment (compiles);
    a failed deletion: a give-up or a refusal, alternately (memoized per find text)."""
    m = _EDIT.search(_user_text(body))
    if not m:
        return {"give_up": True, "replace": ""}
    find, rep = m.group(1), m.group(2)
    if rep.endswith(" ]]"):
        return {"replace": find + "  -- r6 repaired"}
    with LOCK:
        if find not in R6_MEMO:
            R6_MEMO[find] = "give_up" if R6_CYCLE[0] % 2 == 0 else "refuse"
            R6_CYCLE[0] += 1
        ans = R6_MEMO[find]
    return {"give_up": True, "replace": ""} if ans == "give_up" else None


# ------------------------------------------------------------------------------------------- b85 style_rw rehearsal (LRA_FAKE_STYLE_RW=1, opt-in)
_RW_CUR = re.compile(r"(?:BEST SO FAR|CURRENT PROOF) \([^\n]*\n```lean\n(.*?)\n```", re.S)   # harness/style_rw.round_prompt: the proof to rewrite
_RW_FAIL = re.compile(r"FAILING REWRITE:\n```lean\n(.*?)\n```", re.S)                       # harness/style_rw.repair_prompt
RW_BROKEN = "exact rehearsal_no_such_lemma"


def _is_style_rw(body: dict) -> bool:
    t = _user_text(body)
    return "scoring dialect" in t.lower() and ("CURRENT PROOF (" in t or "FAILING REWRITE:" in t)


def style_rw_proofs(body: dict) -> list:
    """Generic answers on the proof the step shows (no row text). A round prompt: c0 the proof unchanged, c1 with `:= by unhygienic` (a
    dialect move that compiles on a tactic proof), c2 broken (an unknown lemma appended: exercises the repair call), c3 the statement
    re-typed with a doubled space (exercises the splice). A repair prompt: the failing rewrite with the broken line removed."""
    t = _user_text(body)
    m = _RW_FAIL.search(t)
    if m:
        d = m.group(1)
        return [{"label": "fix", "strategy": "drop the broken line", "declaration": "\n".join(l for l in d.split("\n") if RW_BROKEN not in l)}]
    m = _RW_CUR.search(t)
    if not m:
        return []
    base = m.group(1)
    hyg = re.sub(r":=\s*by\s*\n", ":= by unhygienic\n", base, count=1) if "unhygienic" not in base and ":= by" in base else base
    return [{"label": "c0", "strategy": "unchanged", "declaration": base},
            {"label": "c1", "strategy": "unhygienic", "declaration": hyg},
            {"label": "c2", "strategy": "broken", "declaration": base.rstrip() + "\n  " + RW_BROKEN},
            {"label": "c3", "strategy": "retyped statement", "declaration": base.replace(" :", "  :", 1)}]


SORRY_BODIES = (":= by\n  exfalso\n  impossible by simp\n", ":= by\n  stop\n  trivial\n")   # b71 review: sorryAx without the word sorry


def sorry_session_call(body: dict):
    """b71 review (R1 adversarial rehearsal, LRA_FAKE_SORRY_PROOFS=1 in the launcher's environment; never in a real run, which starts no
    fake): a session reads original.lean whole on its first turn, then writes candidate.lean with the statement (the text before its first
    `:= by`) and a body that depends on sorryAx without the word `sorry` (SORRY_BODIES, one per turn; write_file runs lean_check on it);
    later turns fall back to the plain read. None: no history to work from (the plain read)."""
    msgs = [m for m in body.get("messages") or [] if isinstance(m, dict)]
    turn = sum(1 for m in msgs if m.get("role") == "assistant")
    if turn == 0:
        return ("read_file", {"path": "original.lean", "start": 1, "end": 2000})
    if turn > len(SORRY_BODIES):
        return None
    for m in msgs:   # the first read of original.lean (agent.py numbers its lines "NNNNN| ")
        c = m.get("content")
        c = c if isinstance(c, str) else "".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
        if m.get("role") == "tool" and "| " in c:
            text = "\n".join(re.sub(r"^\s*\d+\| ?", "", l) for l in c.split("\n") if re.match(r"^\s*\d+\|", l))
            i = text.find(":= by")
            if i > 0:
                return ("write_file", {"path": "candidate.lean", "content": text[:i].rstrip() + " " + SORRY_BODIES[turn - 1]})
            return None
    return None


class Fake(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):   # quiet: never the request line or headers
        pass

    def _send(self, code: int, ctype: str, out: bytes) -> None:
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

    def do_GET(self):   # /models or /generation: nothing to report (the URL is not openrouter.ai, so no billing record is asked for)
        self._send(404, "application/json", b'{"error": {"code": 404}}')

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, "application/json", b'{"error": {"code": 400, "message": "bad json"}}')
        kind, msg, usage = reply(body)
        if kind == "repair_refused":   # b75 R6 rehearsal: a refused repair (HTTP 400 before any data: never billed)
            with LOCK:
                STATS[kind] += 1; n = STATS[kind]
                if CFG["stats"]:
                    tmp = Path(CFG["stats"]).with_suffix(".tmp"); tmp.write_text(json.dumps(STATS)); os.replace(tmp, CFG["stats"])
                if CFG["events"]:
                    t = time.time()
                    with open(CFG["events"], "a") as f:
                        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z",
                                            "kind": kind, "n": n, "model": str(body.get("model") or "?")[:80], "status": 400}) + "\n")
            return self._send(400, "application/json", b'{"error": {"code": 400, "message": "fake: repair refused (R6 rehearsal)"}}')
        with LOCK:
            STATS[kind] += 1; STATS["last"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            n = STATS[kind]
            # b67: per kind, the model id each request named (agent.py sends the preset's api_model): the rehearsal shows which preset
            # served the sessions (arm B: openai/gpt-6.1-sol below $1.25, openai/gpt-6.1-terra after) and the review (google/gemini-4-argon)
            mk = f"{kind}:{str(body.get('model') or '?')[:80]}"
            STATS.setdefault("models", {})[mk] = STATS.setdefault("models", {}).get(mk, 0) + 1
            if CFG["stats"]:
                tmp = Path(CFG["stats"]).with_suffix(".tmp"); tmp.write_text(json.dumps(STATS)); os.replace(tmp, CFG["stats"])
            gid = f"gen-fake-{kind}-{n}"
            if CFG["events"]:   # b70: when each model was asked (the time, the kind, the model id; never a header or message content)
                t = time.time()
                ev = {"t": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z", "kind": kind, "n": n,
                      "model": str(body.get("model") or "?")[:80], "gen": gid}
                with open(CFG["events"], "a") as f:
                    f.write(json.dumps(ev) + "\n")
        fr = "tool_calls" if msg.get("tool_calls") else "stop"
        if body.get("stream"):
            delta = {k: v for k, v in msg.items() if k != "role" and v is not None}
            if "tool_calls" in delta:
                delta["tool_calls"] = [dict(tc, index=0) for tc in delta["tool_calls"]]
            chunks = [{"id": gid, "choices": [{"index": 0, "delta": delta, "finish_reason": fr}]}, {"id": gid, "choices": [], "usage": usage}]
            out = ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            return self._send(200, "text/event-stream", out)
        self._send(200, "application/json", json.dumps({"id": gid, "choices": [{"index": 0, "message": msg, "finish_reason": fr}],
                                                        "usage": usage}).encode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--port-file"); ap.add_argument("--stats"); ap.add_argument("--prompt-tokens", type=int, default=100000)
    ap.add_argument("--events", help="b70: append one line per request (time, kind, number, model, generation id) to this file")
    a = ap.parse_args()
    CFG.update(prompt_tokens=a.prompt_tokens, stats=a.stats, events=a.events, sorry_proofs=os.environ.get("LRA_FAKE_SORRY_PROOFS") == "1",
               r6=os.environ.get("LRA_FAKE_R6") == "1", style_rw=os.environ.get("LRA_FAKE_STYLE_RW") == "1")
    if CFG["style_rw"]:
        print("STYLE_RW REHEARSAL: the style_rw step's calls get rewrites (unchanged / unhygienic / broken / re-typed) and repairs (b85)", flush=True)
    if CFG["r6"]:
        print("R6 REHEARSAL: the review proposes broken / deletion / comment edits; repairs: fixed, give-up, HTTP 400 (b75)", flush=True)
    if CFG["sorry_proofs"]:
        print("ADVERSARIAL: sessions write sorryAx proofs without the word sorry, the review proposes `stop` (b71 review)", flush=True)
    srv = http.server.ThreadingHTTPServer((a.host, a.port), Fake)
    srv.daemon_threads = True
    port = srv.server_address[1]
    if a.port_file:
        tmp = Path(a.port_file).with_suffix(".tmp"); tmp.write_text(f"{a.host}:{port}\n"); os.replace(tmp, a.port_file)
    print(f"fake OpenRouter on http://{a.host}:{port}/v1", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
