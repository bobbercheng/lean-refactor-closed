"""List-price meter and hard per-session gate for Claude Code sessions (driver v2, docs/cc_driver_v2.md §2; 2026-10-12: the
subscription is the closed-final engine, metered at list price per call with a hard per-problem gate). Pure: the driver feeds every
stream-json line (or parsed event) with its wall-clock receipt time; no I/O, no processes, no clock reads.

Per call (Anthropic message id) with --include-partial-messages: open at `message_start` with the input-side cost
c_in = g·(4·in + 5·cw5 + 8·cw1h + 0.2·cr)/1e6 (cw1h = min(ephemeral_1h, cache_creation), cw5 = the rest); every `message_delta` REPLACES
the output count (cumulative) and any non-null input/cache field; a non-null stop_reason (or `message_stop`) closes the call at
c_in + g·20e-6·out. While open, out_live = 1.5·(thinking estimate since message_start + streamed text/json chars / 3). An assistant
message id never opened by message_start (a stream without partial messages) is taken once, deduped, from its own usage (its output
count is the stale message_start value: a fallback, not a meter). S = Σ closed calls.

Gate, G = min(rung, $2.85) − the problem's ledger spend before this session, M = $0.05 (feed() returns the first kill reason):
  (a) in flight:      exposure() + M >= G, exposure = S + Σ open calls' kill charge c_in + g·20e-6·max(2·out_live, 2000)
                      (2026-10-12 review: gating on 1×out_live while a kill charges 2×out_live booked killed rows up to ~$0.70 over G)
  (b) message_start:  S + c_in + M >= G
  (c) next request:   exposure() + R_next + M >= G, tested before every request the CLI sends without a new message_start in between: at
                      each tool_result, at a call that closes with a continuation stop (max_tokens, pause_turn, ...: no tool runs, the
                      CLI resumes at once) and at a system/api_retry event (TTL tested at now + retry_delay_ms; review 2026-10-12).
                      R_next = max(0.10, 1.25·max c_in seen, the incremental write g·(p_cw·(out_last + 2000) + 0.2e-6·ctx_last)), or at
                      least the full prefix rewrite g·p_cw·(ctx_last + out_last + 2000) once the time since the last message_start exceeds
                      TTL − 20 s (p_cw = 5|8e-6 by the TTL in effect)
  fast mode:          a call whose usage.speed is "fast" (priced differently; the driver sets CLAUDE_CODE_DISABLE_FAST_MODE) stops the
                      session, and a result-less charge is then at least the whole gate G
Session charge (charge()): the result event's total_cost_usd when present (= Σ modelUsage costUSD), otherwise (killed / no result)
S + Σ open calls' c_in + g·20e-6·max(2·out_live, 2000) (= exposure()), plus R_next after a rule (c) kill at a tool_result or a continuation
stop (round-2 review 2026-10-12: that kill can race the request it guards; flag c-reserve-booked). An assistant message never opened by message_start in a stream
that has partial messages is flagged "unstreamed-call" (the CLI's non-streaming fallback; the driver disables it when gated)."""
from __future__ import annotations

import json

# $ per token at LIST price: the CLI's catalog tier tier_4_20_cache_read_0_20 (CLI 2.1.296, Opus 5.5): input $4, cache write 5 m $5, cache
# write 1 h $8, cache read $0.20, output $20 per 1M tokens; x1.1 when usage.inference_geo == "us". total_cost_usd equals this price of
# result.usage on 76/76 recorded warm-up Opus sessions.
P_IN, P_CW5, P_CW1H, P_CR, P_OUT = 4e-6, 5e-6, 8e-6, 0.2e-6, 20e-6
# 2026-10-12 (Fable on set #3): per-model LIST prices from the same CLI 2.1.296 catalog, (input, cw5m, cw1h, cache read, output)
# per token. claude-fable-5-1 = tier_10_50_cache_read_0_25. Only verified tiers: a gated run with any other model is refused (set_model).
PRICES = {"claude-opus-5-5": (4e-6, 5e-6, 8e-6, 0.2e-6, 20e-6), "claude-fable-5-1": (10e-6, 12.5e-6, 20e-6, 0.25e-6, 50e-6)}
GEO = {"us": 1.1}
CAP = 2.85                 # per-problem gate ceiling (audit limit $3.00)
MARGIN = 0.05              # M
R_MIN, R_MULT = 0.10, 1.25   # next-call reserve at a tool_result
TTL_S = {"5m": 300.0, "1h": 3600.0}
TTL_SLACK = 20.0           # seconds before expiry from which the next call is priced as a full prefix rewrite
REWRITE_PAD = 2000         # tokens the next request appends to ctx_last + out_last (the tool result and its framing)
LIVE_MULT, CHARS_PER_TOKEN = 1.5, 3.0
KILL_OUT_MULT, KILL_OUT_MIN = 2.0, 2000   # an open call of a killed / result-less session: output charged at max(2·out_live, 2000)
NO_NEXT = ("tool_use", "end_turn", "stop_sequence", "refusal")   # stops after which no request follows at once (tool_use: at its tool_result)


def set_model(model: str) -> None:
    """Price every later call at `model`'s list prices (module-wide: one model per driver process). Unknown models raise."""
    global P_IN, P_CW5, P_CW1H, P_CR, P_OUT
    if model not in PRICES:
        raise ValueError(f"no verified list prices for {model!r} (known: {sorted(PRICES)})")
    P_IN, P_CW5, P_CW1H, P_CR, P_OUT = PRICES[model]


def geo(u: dict | None) -> float:
    return GEO.get(str((u or {}).get("inference_geo") or ""), 1.0)


def split(u: dict | None) -> tuple[int, int, int, int]:
    """(input, cache write 5 m, cache write 1 h, cache read) tokens of a usage block."""
    u = u or {}
    cc = int(u.get("cache_creation_input_tokens") or 0)
    cw1h = min(int((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0), cc)
    return int(u.get("input_tokens") or 0), cc - cw1h, cw1h, int(u.get("cache_read_input_tokens") or 0)


def input_cost(u: dict | None) -> float:
    i, w5, w1, r = split(u)
    return geo(u) * (P_IN * i + P_CW5 * w5 + P_CW1H * w1 + P_CR * r)


def usage_cost(u: dict | None) -> float:
    """List price of a whole usage block (a call's final usage, or result.usage for a whole session)."""
    return input_cost(u) + geo(u) * P_OUT * int((u or {}).get("output_tokens") or 0)


class Call:
    def __init__(self, mid: str, parent, usage: dict, t: float, fallback: bool = False):
        self.id, self.parent, self.t0, self.fallback = mid, parent, t, fallback
        self.usage = dict(usage or {}); self.out = int(self.usage.get("output_tokens") or 0) if fallback else 0
        self.think = 0; self.think_chars = 0; self.chars = 0; self.closed = False; self.cost = 0.0; self.t1 = None

    @property
    def g(self) -> float:
        return geo(self.usage)

    @property
    def c_in(self) -> float:
        return input_cost(self.usage)

    @property
    def ctx(self) -> int:
        i, w5, w1, r = split(self.usage)
        return i + w5 + w1 + r

    @property
    def out_live(self) -> float:
        """Live output estimate (spec: 1.5·(thinking estimate + streamed chars / 3)); never below the reported cumulative count. The thinking
        estimate is the system/thinking_tokens deltas, or the thinking_delta chars / 3 when larger (never both: no double count)."""
        return max(float(self.out), LIVE_MULT * (max(self.think, self.think_chars / CHARS_PER_TOKEN) + self.chars / CHARS_PER_TOKEN))

    def live_cost(self) -> float:
        return self.c_in + self.g * P_OUT * self.out_live

    def kill_charge(self) -> float:
        return self.c_in + self.g * P_OUT * max(KILL_OUT_MULT * self.out_live, KILL_OUT_MIN)


class Meter:
    def __init__(self, gate_usd: float | None, ttl: str = "1h", margin: float = MARGIN):
        self.G, self.ttl, self.M = gate_usd, ttl, margin
        self.calls: dict[str, Call] = {}; self.order: list[str] = []; self.cur: dict = {}   # parent_tool_use_id -> open call id
        self.S = 0.0; self.cin_max = 0.0; self.last_start: float | None = None; self.last: Call | None = None
        self.points: list[tuple[float, float, str]] = []   # (close time, call cost, id), one per closed call, for trajectory turn events
        self.kill: str | None = None; self.kill_detail: dict = {}; self.flags: list[str] = []
        self.result: dict | None = None; self.rate_limit: dict | None = None; self.seen_5m = False; self.events = 0; self.partial = False

    # ---- accounting -------------------------------------------------------------------------------------------------------------------
    def open_calls(self) -> list[Call]:
        return [self.calls[i] for i in self.cur.values() if i in self.calls and not self.calls[i].closed]

    def estimate(self) -> float:
        """S plus the live cost of every open call (the best live guess, for logs)."""
        return self.S + sum(c.live_cost() for c in self.open_calls())

    def exposure(self) -> float:
        """S plus what a kill now would charge for every open call: the quantity rules (a) and (c) test against G − M, so a killed
        session's charge never exceeds G by more than one event's increment (review 2026-10-12)."""
        return self.S + sum(c.kill_charge() for c in self.open_calls())

    def charge(self) -> float:
        if self.result is not None and self.result.get("total_cost_usd") is not None:
            return float(self.result["total_cost_usd"])
        if "fast-mode" in self.flags and self.G is not None:   # billed at the fast price, metered at standard: book the whole gate
            return max(self.exposure(), self.G)
        return self.exposure() + self.race_reserve()

    def race_reserve(self) -> float:
        """Round-2 review (2026-10-12): rule (c) fires on the event the CLI emits as it sends the next request (a tool_result, a continuation
        stop), so the kill can lose that race by milliseconds and the request's input side (<= R_next) is billed with no message_start seen.
        Such a kill books R_next on top of the exposure (flag c-reserve-booked) until the smoke (G0b) shows whether the raced request is
        billed. An api_retry kill lands before its delayed request: nothing extra."""
        d = self.kill_detail
        return float(d.get("r_next") or 0.0) if self.kill == "c" and d.get("at") != "api_retry" else 0.0

    def totals(self) -> dict:
        """Deduped token totals over every call seen (closed, open or fallback)."""
        t = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_creation_1h": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
        for c in self.calls.values():
            i, w5, w1, r = split(c.usage)
            t["input_tokens"] += i; t["cache_creation_input_tokens"] += w5 + w1; t["cache_creation_1h"] += w1; t["cache_read_input_tokens"] += r
            t["output_tokens"] += c.out
        return t

    def ttl_s(self) -> float:
        return TTL_S["5m"] if (self.ttl == "5m" or self.seen_5m) else TTL_S["1h"]

    def r_next(self, now: float) -> float:
        """Reserve for the next request: max(0.10, 1.25·max c_in, the incremental write of the last call's output plus the tool result
        (review 2026-10-12: a 32k-output call makes the next request write ~$0.18-0.27 that 1.25·max c_in did not cover) with the prefix read
        from cache), or (the strictest) the full prefix rewrite once the cache may have expired (time since the last message_start > TTL − 20 s;
        5 m TTL whenever a 5 m write was seen: the TTL flips on overage)."""
        r = max(R_MIN, R_MULT * self.cin_max)
        if self.last is not None:
            p = P_CW5 if self.ttl_s() <= TTL_S["5m"] else P_CW1H
            r = max(r, self.last.g * (p * (self.last.out + REWRITE_PAD) + P_CR * self.last.ctx))
            if self.last_start is not None and now - self.last_start > self.ttl_s() - TTL_SLACK:
                r = max(r, self.last.g * p * (self.last.ctx + self.last.out + REWRITE_PAD))
        return r

    def _close(self, c: Call, now: float, out: float | None = None) -> None:
        if c.closed:
            return
        if out is not None:
            c.out = int(out)
        c.closed = True; c.t1 = now; c.cost = c.c_in + c.g * P_OUT * c.out
        self.S += c.cost; self.points.append((now, c.cost, c.id)); self.last = c
        if self.cur.get(c.parent) == c.id:
            self.cur.pop(c.parent, None)

    def _kill(self, rule: str, now: float, **detail) -> str | None:
        if self.kill is None and self.G is not None:
            self.kill = rule; self.kill_detail = {"t": now, "S": round(self.S, 6), "G": self.G, **{k: round(v, 6) if isinstance(v, float) else v for k, v in detail.items()}}
            return rule
        return None

    def _gate_a(self, now: float) -> str | None:
        if self.G is not None and self.open_calls() and self.exposure() + self.M >= self.G:
            return self._kill("a", now, exposure=self.exposure(), estimate=self.estimate())
        return None

    def _gate_c(self, now: float, at: str, t_req: float | None = None) -> str | None:
        """Rule (c) before a request the CLI is about to send (`at`: what precedes it); t_req = when it goes out (a retry waits first)."""
        if self.G is None:
            return None
        r = self.r_next(now if t_req is None else t_req)
        if self.exposure() + r + self.M >= self.G:
            k = self._kill("c", now, r_next=r, at=at)
            if k and at != "api_retry" and "c-reserve-booked" not in self.flags:
                self.flags.append("c-reserve-booked")   # the kill may race the request it guards: charge() books R_next too
            return k
        return None

    # ---- events -------------------------------------------------------------------------------------------------------------------------
    def feed(self, line, now: float) -> str | None:
        """One stream-json line (str) or parsed event (dict). Returns a kill reason the first time the gate fires, else None."""
        if isinstance(line, str):
            line = line.strip()
            if not line.startswith("{"):
                return None
            try:
                d = json.loads(line)
            except ValueError:
                return None
        else:
            d = line
        if not isinstance(d, dict):
            return None
        self.events += 1
        t = d.get("type")
        if t == "stream_event":
            self.partial = True
            return self._stream(d.get("event") or {}, d.get("parent_tool_use_id"), now)
        if t == "system" and d.get("subtype") == "thinking_tokens":
            c = self._current(d.get("parent_tool_use_id"))
            if c is not None:
                delta = d.get("estimated_tokens_delta")
                c.think = c.think + int(delta) if delta is not None else max(c.think, int(d.get("estimated_tokens") or 0))
                return self._gate_a(now)
            return None
        if t == "system" and d.get("subtype") == "api_retry":   # the failed request is retried after retry_delay_ms: (c) at that time
            return self._gate_c(now, "api_retry", now + float(d.get("retry_delay_ms") or 0) / 1000.0)
        if t == "assistant":
            m = d.get("message") or {}
            mid = m.get("id")
            if mid and mid not in self.calls:   # never opened by message_start: take it once from its own usage (fallback)
                c = Call(mid, d.get("parent_tool_use_id"), m.get("usage") or {}, now, fallback=True)
                self.calls[mid] = c; self.order.append(mid); self.cin_max = max(self.cin_max, c.c_in); self.last_start = now
                self.seen_5m = self.seen_5m or split(c.usage)[1] > 0
                self._close(c, now)
                for fl in ("fallback", "unstreamed-call") if self.partial else ("fallback",):   # partial stream: the CLI's non-streaming fallback
                    if fl not in self.flags:
                        self.flags.append(fl)
            return None
        if t == "user":
            content = (d.get("message") or {}).get("content")
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                return self._gate_c(now, "tool_result")
            return None
        if t == "result":
            self.result = d
            return None
        if t == "rate_limit_event":
            self.rate_limit = d.get("rate_limit_info")
            return None
        return None

    def _current(self, parent) -> Call | None:
        mid = self.cur.get(parent)
        c = self.calls.get(mid) if mid else None
        return c if c is not None and not c.closed else None

    def _stream(self, ev: dict, parent, now: float) -> str | None:
        et = ev.get("type")
        if et == "message_start":
            m = ev.get("message") or {}
            mid = m.get("id") or f"anon-{len(self.order)}"
            prev = self._current(parent)
            if prev is not None:   # a new call while the previous one never closed (cut stream, retry): charge it at its live estimate
                self._close(prev, now, out=prev.out_live)
                if "abandoned-call" not in self.flags:
                    self.flags.append("abandoned-call")
            if mid in self.calls:   # a repeated message_start for a known id: keep the first
                return None
            c = Call(mid, parent, m.get("usage") or {}, now)
            self.calls[mid] = c; self.order.append(mid); self.cur[parent] = mid; self.last_start = now
            self.cin_max = max(self.cin_max, c.c_in); self.seen_5m = self.seen_5m or split(c.usage)[1] > 0
            if str((m.get("usage") or {}).get("speed") or "") == "fast":
                self.flags.append("fast-mode")
                return self._kill("fast", now, c_in=c.c_in)
            if self.G is not None and self.S + c.c_in + self.M >= self.G:
                return self._kill("b", now, c_in=c.c_in)
            return None
        c = self._current(parent)
        if c is None:
            return None
        if et == "content_block_delta":
            dl = ev.get("delta") or {}
            if dl.get("type") == "text_delta":
                c.chars += len(dl.get("text") or "")
            elif dl.get("type") == "input_json_delta":
                c.chars += len(dl.get("partial_json") or "")
            elif dl.get("type") == "thinking_delta":
                c.think_chars += len(dl.get("thinking") or "")
            return self._gate_a(now)
        if et == "message_delta":
            u = ev.get("usage") or {}
            if u.get("output_tokens") is not None:
                c.out = int(u["output_tokens"])   # cumulative: replace, never add
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cache_creation", "inference_geo"):
                if u.get(k) is not None:
                    c.usage[k] = u[k]
            self.seen_5m = self.seen_5m or split(c.usage)[1] > 0
            stop = (ev.get("delta") or {}).get("stop_reason")
            if stop is not None:
                self._close(c, now)
                # a continuation stop (max_tokens: up to 3 "Output token limit hit. Resume directly" calls; pause_turn) sends the next
                # request with no tool_result in between: rule (c) here, with the TTL test (review 2026-10-12: a 7-min 32k-thinking call
                # expired the 5 m cache, and its continuation's rewrite was billed before rule (b) could see it)
                return None if stop in NO_NEXT else self._gate_c(now, f"stop:{stop}")
            return self._gate_a(now)
        if et == "message_stop":
            self._close(c, now, out=c.out if c.out else c.out_live)
        return None
