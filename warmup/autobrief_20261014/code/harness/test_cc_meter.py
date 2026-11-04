#!/usr/bin/env python3
"""Unit tests of harness/cc_meter.py (driver v2 meter and gate, docs/cc_driver_v2.md §2), plain asserts, no pytest, no I/O beyond reading
recorded warm-up streams (probe/runs/ccline-opus55-p1, readable warm-up rows) for the replay test.
    python3 harness/test_cc_meter.py      # prints PASS/FAIL per test, exit 1 on any failure"""
from __future__ import annotations

import glob, gzip, json, pathlib, sys, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import cc_meter as cm  # noqa: E402

EPS = 1e-9


# ---- event builders (the CLI 2.1.296 shapes) ------------------------------------------------------------------------------------------
def u(inp=2, cc=0, e1h=None, cr=0, out=1, geo="global", speed=None):
    d = {"input_tokens": inp, "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr, "output_tokens": out, "inference_geo": geo,
         "cache_creation": {"ephemeral_5m_input_tokens": cc - (cc if e1h is None else min(e1h, cc)), "ephemeral_1h_input_tokens": cc if e1h is None else e1h}}
    if speed:
        d["speed"] = speed
    return d


def ms(mid, usage, parent=None):
    return {"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid, "usage": usage}}, "parent_tool_use_id": parent}


def text(s, kind="text_delta"):
    key = {"text_delta": "text", "input_json_delta": "partial_json", "thinking_delta": "thinking"}[kind]
    return {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": kind, key: s}}}


def md(out, stop=None, **extra):
    return {"type": "stream_event", "event": {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": out, **extra}}}


def think(delta, total=0):
    return {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": total, "estimated_tokens_delta": delta}


def asst(mid, usage):
    return {"type": "assistant", "message": {"id": mid, "usage": usage, "content": [{"type": "text", "text": "x"}]}}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}


def cin(inp=0, w5=0, w1=0, cr=0, g=1.0):
    return g * (4 * inp + 5 * w5 + 8 * w1 + 0.2 * cr) / 1e6


def feed_all(m, evs, t0=0.0, dt=0.1):
    t = t0; out = []
    for e in evs:
        r = m.feed(e, t); t += dt
        if r:
            out.append(r)
    return out


# ---- tests ---------------------------------------------------------------------------------------------------------------------------
def test_dedupe_repeated_assistant_ids():
    """Fallback stream (no partial messages): one call repeats its id per content block; it is counted once."""
    m = cm.Meter(None)
    us = u(inp=2, cc=1000, cr=5000, out=16)
    feed_all(m, [asst("m1", us), asst("m1", us), asst("m1", us), asst("m2", u(inp=3, cc=10, cr=6000, out=7))])
    assert len(m.calls) == 2 and len(m.points) == 2, m.calls
    t = m.totals()
    assert t["input_tokens"] == 5 and t["cache_creation_input_tokens"] == 1010 and t["cache_read_input_tokens"] == 11000, t
    assert abs(m.S - (cm.usage_cost(us) + cm.usage_cost(u(inp=3, cc=10, cr=6000, out=7)))) < EPS
    # with partial messages, the assistant events of an opened id are ignored (the stream_event usage is the meter)
    m2 = cm.Meter(None)
    feed_all(m2, [ms("a", u(inp=2, cc=100, cr=0, out=1)), asst("a", u(inp=2, cc=100, out=1)), md(50, "tool_use"), asst("a", u(inp=2, cc=100, out=1))])
    assert len(m2.points) == 1 and m2.calls["a"].out == 50 and "fallback" not in m2.flags
    assert abs(m2.S - (cin(2, 0, 100) + 20e-6 * 50)) < EPS


def test_cumulative_output_replace():
    m = cm.Meter(None)
    feed_all(m, [ms("a", u(inp=10, out=1)), md(100), md(300), md(450, "end_turn")])
    assert m.calls["a"].out == 450, m.calls["a"].out
    assert abs(m.S - (cin(10) + 20e-6 * 450)) < EPS
    # input/cache fields of a message_delta replace the message_start values when non-null
    m = cm.Meter(None)
    feed_all(m, [ms("b", u(inp=10, cc=0, cr=0, out=1)), md(20, "end_turn", input_tokens=12, cache_read_input_tokens=1000)])
    assert abs(m.S - (cin(12, cr=1000) + 20e-6 * 20)) < EPS


def test_5m_1h_split():
    assert cm.split(u(inp=1, cc=1000, e1h=600, cr=5)) == (1, 400, 600, 5)
    assert cm.split(u(inp=1, cc=1000, e1h=5000, cr=5)) == (1, 0, 1000, 5)   # 1 h never above the total creation
    assert cm.split({"input_tokens": 1, "cache_creation_input_tokens": 300}) == (1, 300, 0, 0)   # no split given: priced as 5 m writes
    assert abs(cm.input_cost(u(inp=0, cc=1000, e1h=600)) - (5 * 400 + 8 * 600) / 1e6) < EPS


def test_geo_multiplier():
    a, b = u(inp=1000, cc=2000, e1h=2000, cr=10000, out=500), u(inp=1000, cc=2000, e1h=2000, cr=10000, out=500, geo="us")
    assert abs(cm.usage_cost(b) - 1.1 * cm.usage_cost(a)) < EPS
    m = cm.Meter(None)
    feed_all(m, [ms("a", b), md(500, "end_turn")])
    assert abs(m.S - 1.1 * cm.usage_cost(a)) < EPS


def test_fallback_for_ids_without_message_start():
    m = cm.Meter(None)
    feed_all(m, [ms("a", u(inp=5, cc=100, out=1)), md(40, "tool_use"), asst("z", u(inp=7, cc=0, cr=900, out=33)), asst("z", u(inp=7, cr=900, out=33))])
    assert set(m.calls) == {"a", "z"} and m.calls["z"].fallback and "fallback" in m.flags
    assert abs(m.S - (cin(5, w1=100) + 20e-6 * 40 + cin(7, cr=900) + 20e-6 * 33)) < EPS


def test_kill_rule_a_in_flight():
    G = 0.30
    m = cm.Meter(G)
    evs = [ms("a", u(inp=2, cc=4000, cr=12000, out=1))] + [think(100, 100 * (k + 1)) for k in range(400)]
    t = 0.0; reason = None; k_at = None
    for k, e in enumerate(evs):
        before = m.exposure()
        reason = m.feed(e, t); t += 0.01
        if reason:
            k_at = k; break
    assert reason == "a", reason
    c = m.calls["a"]
    # fires at the first event where S + c_in + 20e-6·max(2·out_live, 2000) + M >= G (what a kill charges), and not one event earlier
    assert m.exposure() + cm.MARGIN >= G and before + cm.MARGIN < G, (before, m.exposure())
    assert abs(c.out_live - 1.5 * c.think) < EPS and k_at < 399
    # 2026-10-12 review: the charge of the killed session is the exposure the gate tested, so it stays below G (G - M + one event)
    assert m.charge() == m.exposure() and m.charge() <= G - cm.MARGIN + 20e-6 * 2 * 1.5 * 100 + EPS, m.charge()
    assert m.kill_detail["exposure"] >= m.kill_detail["estimate"]
    # streamed text/json chars count at 3 chars per token, x1.5
    m = cm.Meter(None)
    feed_all(m, [ms("b", u(inp=1, out=1)), text("x" * 300), text("y" * 150, "input_json_delta")])
    assert abs(m.calls["b"].out_live - 1.5 * 150) < EPS
    # thinking_delta chars are used only when larger than the thinking_tokens estimate (never both)
    m = cm.Meter(None)
    feed_all(m, [ms("c", u(inp=1, out=1)), think(100), text("t" * 600, "thinking_delta")])
    assert abs(m.calls["c"].out_live - 1.5 * 200) < EPS


def test_kill_rule_b_message_start():
    m = cm.Meter(0.20)
    feed_all(m, [ms("a", u(inp=2, cc=1000, cr=10000, out=1)), md(1000, "tool_use")])   # S = 0.008 + 0.002 + 0.02 = 0.030
    r = m.feed(ms("b", u(inp=2, cc=15000, e1h=15000, cr=11000, out=1)), 1.0)        # c_in = 0.122 -> 0.030 + 0.122 + 0.05 >= 0.20
    assert r == "b" and m.kill == "b", (r, m.S)
    m2 = cm.Meter(0.30)
    feed_all(m2, [ms("a", u(inp=2, cc=1000, cr=10000, out=1)), md(1000, "tool_use")])
    assert m2.feed(ms("b", u(inp=2, cc=15000, e1h=15000, cr=11000, out=1)), 1.0) is None   # 0.202 < 0.30


def test_kill_rule_c_tool_result_and_ttl_rewrite():
    # reserve = max(0.10, 1.25 · max c_in)
    m = cm.Meter(0.50)
    feed_all(m, [ms("a", u(inp=2, cc=20000, e1h=20000, cr=0, out=1)), md(10000, "tool_use")])   # c_in 0.160, S = 0.360
    assert abs(m.r_next(1.0) - 1.25 * 0.160008) < 1e-9
    assert m.feed(tool_result(), 1.0) == "c"                                                     # 0.36 + 0.20 + 0.05 >= 0.50
    m = cm.Meter(0.70)
    feed_all(m, [ms("a", u(inp=2, cc=20000, e1h=20000, cr=0, out=1)), md(10000, "tool_use")])
    assert m.feed(tool_result(), 1.0) is None                                                    # 0.61 < 0.70
    # TTL expiry, 5 m cache: after > 280 s the next call is priced as a full prefix rewrite at $5/MTok
    m = cm.Meter(0.80, ttl="5m")
    feed_all(m, [ms("a", u(inp=2, cc=1000, e1h=0, cr=60000, out=1)), md(2000, "tool_use")], t0=0.0)
    ctx = 2 + 1000 + 60000
    assert abs(m.r_next(100.0) - 0.10) < EPS                                                     # warm cache: the 0.10 floor
    assert abs(m.r_next(281.0) - 5e-6 * (ctx + 2000 + 2000)) < EPS                               # expired: rewrite
    S = m.S
    assert S + m.r_next(281.0) + 0.05 < 0.80 and m.feed(tool_result(), 281.0) is None
    m2 = cm.Meter(S + 5e-6 * (ctx + 4000) + 0.05 - 1e-6, ttl="5m")
    feed_all(m2, [ms("a", u(inp=2, cc=1000, e1h=0, cr=60000, out=1)), md(2000, "tool_use")], t0=0.0)
    assert m2.feed(tool_result(), 100.0) is None and m2.feed(tool_result(), 281.0) == "c"
    # 1 h cache: expiry only after 3580 s, priced at $8/MTok; a 5 m write seen in the stream (overage flip) switches to the 5 m TTL
    m = cm.Meter(5.0, ttl="1h")
    feed_all(m, [ms("a", u(inp=2, cc=1000, e1h=1000, cr=60000, out=1)), md(2000, "tool_use")])
    assert abs(m.r_next(3000.0) - 0.10) < EPS and abs(m.r_next(3581.0) - 8e-6 * (ctx + 4000)) < EPS
    feed_all(m, [ms("b", u(inp=2, cc=500, e1h=0, cr=63000, out=1)), md(10, "tool_use")], t0=4000.0)
    assert m.seen_5m and m.ttl_s() == 300.0 and abs(m.r_next(4000.0 + 281) - 5e-6 * (2 + 500 + 63000 + 10 + 2000)) < EPS


def test_charge_killed_and_no_result():
    m = cm.Meter(None)
    feed_all(m, [ms("a", u(inp=2, cc=1000, cr=0, out=1)), md(500, "tool_use"), ms("b", u(inp=2, cc=300, cr=1002, out=1)), think(1000)])
    S = cin(2, w1=1000) + 20e-6 * 500
    b_in = cin(2, w1=300, cr=1002)
    assert abs(m.charge() - (S + b_in + 20e-6 * max(2 * 1.5 * 1000, 2000))) < EPS
    m = cm.Meter(None)                                                                           # open call, nothing streamed yet: the 2000 floor
    feed_all(m, [ms("a", u(inp=2, cc=1000, out=1))])
    assert abs(m.charge() - (cin(2, w1=1000) + 20e-6 * 2000)) < EPS
    m = cm.Meter(None)                                                                           # no open call, no result: S
    feed_all(m, [ms("a", u(inp=2, cc=1000, out=1)), md(500, "end_turn")])
    assert abs(m.charge() - m.S) < EPS
    m.feed({"type": "result", "total_cost_usd": 0.123, "usage": {}, "modelUsage": {}}, 9.0)     # a result event wins
    assert m.charge() == 0.123
    m = cm.Meter(None)                                                                           # cut stream: a new call closes the old at its live estimate
    feed_all(m, [ms("a", u(inp=2, cc=1000, out=1)), think(400), ms("b", u(inp=2, cc=10, out=1))])
    assert m.calls["a"].closed and m.calls["a"].out == 600 and "abandoned-call" in m.flags


def test_rule_c_continuation_and_retry():
    """2026-10-12 review: requests that follow a continuation stop (max_tokens, pause_turn) or an api_retry wait are reserved like the
    request after a tool_result, with the TTL test at the time the request goes out."""
    def two_calls(G, t_close, stop):
        m = cm.Meter(G, ttl="5m")
        feed_all(m, [ms("a", u(inp=2, cc=2000, e1h=0, cr=100000, out=1)), md(20000, "tool_use")], t0=0.0, dt=0.0)   # c_in 0.030, S 0.430
        assert m.feed(tool_result(), 1.0) is None
        assert m.feed(ms("b", u(inp=2, cc=21000, e1h=0, cr=102000, out=1)), 10.0) is None                          # c_in 0.125
        assert m.feed(md(10000), 200.0) is None                                                                    # exposure 0.955 + M < 1.2
        return m, m.feed(md(10000, stop), t_close)
    m, r = two_calls(1.2, 400.0, "max_tokens")   # 390 s after its message_start: the 5 m cache expired, the continuation rewrites it
    rewrite = 5e-6 * (2 + 21000 + 102000 + 10000 + 2000)
    assert r == "c" and m.kill_detail["at"] == "stop:max_tokens" and abs(m.kill_detail["r_next"] - rewrite) < 1e-6, (r, m.kill_detail)
    m, r = two_calls(1.2, 100.0, "max_tokens")   # warm cache: reserve max(0.10, 1.25·0.125) fits
    assert r is None and m.kill is None
    m, r = two_calls(1.2, 400.0, "tool_use")     # a tool runs first (it may bank a best): the gate waits for its tool_result
    assert r is None and m.feed(tool_result(), 400.0) == "c" and m.kill_detail["at"] == "tool_result"
    m, r = two_calls(1.2, 400.0, "end_turn")
    assert r is None and m.kill is None
    # api_retry: the TTL is tested at now + retry_delay_ms
    retry = lambda ms_: {"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 10, "retry_delay_ms": ms_, "error_status": 529}
    for delay, want in ((10000, None), (200000, "c")):
        m = cm.Meter(1.0, ttl="5m")
        feed_all(m, [ms("a", u(inp=2, cc=2000, e1h=0, cr=100000, out=1)), md(20000, "tool_use")], t0=0.0, dt=0.0)
        assert m.feed(retry(delay), 100.0) == want, (delay, m.kill_detail)
    assert m.kill_detail["at"] == "api_retry" and abs(m.kill_detail["r_next"] - 5e-6 * (2 + 2000 + 100000 + 20000 + 2000)) < 1e-6


def test_r_next_incremental_write():
    """After a long output the next request writes it (and the tool result) to the cache: the reserve covers that write."""
    m = cm.Meter(5.0, ttl="1h")
    feed_all(m, [ms("a", u(inp=2, cc=1000, cr=60000, out=1)), md(32000, "tool_use")])
    inc = 8e-6 * (32000 + 2000) + 0.2e-6 * (2 + 1000 + 60000)
    assert abs(m.r_next(10.0) - inc) < EPS and inc > max(cm.R_MIN, cm.R_MULT * m.cin_max), (m.r_next(10.0), inc)


def test_rule_c_race_reserve_booked():
    """Round-2 review (2026-10-12): a rule (c) kill at a tool_result or a continuation stop may lose the race with the request the CLI sends
    at that moment, so the charge books R_next on top of the exposure (flag c-reserve-booked); an api_retry kill (its request waits) books
    nothing extra, and a result event still wins."""
    m = cm.Meter(0.50)
    feed_all(m, [ms("a", u(inp=2, cc=20000, e1h=20000, cr=0, out=1)), md(10000, "tool_use")])
    assert m.feed(tool_result(), 1.0) == "c" and "c-reserve-booked" in m.flags
    rn = m.kill_detail["r_next"]
    assert abs(rn - 1.25 * 0.160008) < 1e-6 and abs(m.race_reserve() - rn) < EPS and abs(m.charge() - (m.S + rn)) < EPS
    m.feed({"type": "result", "total_cost_usd": 0.42}, 2.0)
    assert m.charge() == 0.42
    m = cm.Meter(1.0, ttl="5m")
    feed_all(m, [ms("a", u(inp=2, cc=2000, e1h=0, cr=100000, out=1)), md(20000, "tool_use")], t0=0.0, dt=0.0)
    assert m.feed({"type": "system", "subtype": "api_retry", "retry_delay_ms": 200000}, 100.0) == "c"
    assert m.race_reserve() == 0.0 and abs(m.charge() - m.S) < EPS and "c-reserve-booked" not in m.flags
    m = cm.Meter(None)   # ungated: never a kill, never a reserve
    feed_all(m, [ms("a", u(inp=2, cc=20000, e1h=20000, cr=0, out=1)), md(10000, "tool_use"), tool_result()])
    assert m.kill is None and m.race_reserve() == 0.0


def test_unstreamed_call_flag():
    m = cm.Meter(2.85)   # partial messages on: an assistant id never opened is the CLI's non-streaming fallback
    feed_all(m, [ms("a", u(inp=2, cc=100, out=1)), md(10, "tool_use"), asst("z", u(inp=2, cr=200, out=5))])
    assert "unstreamed-call" in m.flags and "fallback" in m.flags
    m = cm.Meter(2.85)   # no partial messages at all (a recorded v1 stream): fallback only
    feed_all(m, [asst("z", u(inp=2, cr=200, out=5))])
    assert m.flags == ["fallback"]


def test_fast_mode_stops():
    m = cm.Meter(2.85)
    assert m.feed(ms("a", u(inp=2, cc=100, out=1, speed="fast")), 0.0) == "fast" and "fast-mode" in m.flags
    assert m.charge() == 2.85   # billed at the fast price, metered at standard: a result-less session books the whole gate
    m.feed({"type": "result", "total_cost_usd": 0.5}, 1.0)
    assert m.charge() == 0.5


def test_kill_reason_once():
    m = cm.Meter(0.10)
    assert m.feed(ms("a", u(inp=2, cc=20000, e1h=20000, out=1)), 0.0) == "b"
    assert m.feed(think(5000), 0.1) is None and m.kill == "b"


def test_replay_recorded_warmup_streams():
    """A recorded stream without partial messages: the deduped input side equals result.usage's input side, and the list price of
    result.usage equals total_cost_usd (the catalog tier above)."""
    files = sorted(glob.glob(str(ROOT / "probe/runs/ccline-opus55-p1/trajectories/*.jsonl.gz")))
    if not files:
        print("  SKIP replay: no recorded warm-up streams in this checkout"); return
    n = 0
    for f in files:
        m = cm.Meter(2.85)
        with gzip.open(f, "rt") as h:
            for i, line in enumerate(h):
                m.feed(line, float(i))
        if m.result is None:
            continue
        ru = m.result["usage"]; t = m.totals()
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            assert t[k] == int(ru.get(k) or 0), (f, k, t[k], ru.get(k))
        assert t["cache_creation_1h"] == int((ru.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0), f
        assert abs(cm.usage_cost(ru) - float(m.result["total_cost_usd"])) < 1e-6, (f, cm.usage_cost(ru), m.result["total_cost_usd"])
        mu = sum(float(v.get("costUSD") or 0) for v in (m.result.get("modelUsage") or {}).values())
        assert abs(mu - float(m.result["total_cost_usd"])) < 1e-6
        assert m.charge() == float(m.result["total_cost_usd"]) and "fallback" in m.flags
        n += 1
    assert n >= 1
    print(f"  replay: {n} recorded sessions, deduped input side == result.usage, list price == total_cost_usd")


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn(); print(f"PASS {k}")
        except Exception:  # noqa: BLE001
            bad += 1; print(f"FAIL {k}"); traceback.print_exc()
    print(f"{len(tests) - bad}/{len(tests)} passed")
    return 1 if bad else 0


def test_set_model_prices():
    """2026-10-12: Fable 5.1 is priced from its own catalog tier; unknown models refuse; Opus restores the default."""
    import cc_meter as m
    u = {"input_tokens": 1000, "cache_creation_input_tokens": 2000, "cache_creation": {"ephemeral_1h_input_tokens": 500},
         "cache_read_input_tokens": 10000, "output_tokens": 3000}
    m.set_model("claude-fable-5-1")
    assert abs(m.usage_cost(u) - (10 * 1000 + 12.5 * 1500 + 20 * 500 + 0.25 * 10000 + 50 * 3000) / 1e6) < 1e-12
    try:
        m.set_model("claude-fable-5"); raise AssertionError("unknown model accepted")
    except ValueError:
        pass
    m.set_model("claude-opus-5-5")
    assert abs(m.usage_cost(u) - (4 * 1000 + 5 * 1500 + 8 * 500 + 0.2 * 10000 + 20 * 3000) / 1e6) < 1e-12


if __name__ == "__main__":
    raise SystemExit(main())
