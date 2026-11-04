"""OpenAI-chat-compatible client path for harness/agent.py (self-hosted vLLM / SGLang, or OpenRouter's /chat/completions).

The agent keeps its conversation in the Anthropic Messages shape (content blocks: text / thinking / tool_use / tool_result).
This module converts that shape to OpenAI chat messages + function tools, makes one non-streaming request, and returns an
object that quacks like the subset of `anthropic.types.Message` the agent uses: `.content` (blocks with .type/.text/.name/
.input/.id/.thinking and .model_dump()), `.stop_reason` (end_turn | tool_use | max_tokens) and `.usage` (input/output tokens).

Reasoning: vLLM/SGLang with `--reasoning-parser glm45` return the model's thinking in `message.reasoning_content`
(OpenRouter: `message.reasoning`); it is kept as a `thinking` block and sent back inside the content as <think>...</think> so the chat template
renders the real reasoning for earlier turns instead of an empty <think></think>.
"""
from __future__ import annotations

import json
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import os, pathlib
import requests


@dataclass
class Block:
    type: str
    text: str | None = None
    thinking: str | None = None
    name: str | None = None
    input: dict | None = None
    id: str | None = None
    details: list | None = None   # OpenRouter reasoning_details, passed back verbatim (think_mode="details")
    extra: dict | None = None     # a tool call's extra_content (Vertex Gemini: {"google": {"thought_signature"}}), passed back verbatim

    def model_dump(self, exclude_none: bool = True) -> dict:
        d = {"type": self.type, "text": self.text, "thinking": self.thinking, "name": self.name, "input": self.input, "id": self.id,
             "details": self.details, "extra": self.extra}
        return {k: v for k, v in d.items() if v is not None} if exclude_none else d


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float | None = None   # provider-reported USD (OpenRouter usage.cost / gateway cost), None when not reported
    reasoning: int = 0          # 2026-10-20 audit: reasoning tokens as reported (already counted in output_tokens and priced as output)
    # b65 (2026-10-27: Sol metered at the higher of billed and list): False on an OpenRouter /generation record, which carries no
    # cache-write count (harness/agent.list_floor_usd then prices its uncached input at the cache-write price). A class attribute, not a field
    cw_reported = True


@dataclass
class Message:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
    provider: str | None = None
    raw_finish_reason: str | None = None
    usage_estimated: str | None = None   # why `usage` is an estimate, not the provider's count (e.g. "junk_cut"); None = provider-reported
    gen_id: str | None = None   # b64 L1 (c): the streamed generation's id (OpenRouter: GET /generation?id= has its billed record)


class OpenAIChatError(Exception):
    def __init__(self, status: int, body: str, headers=None, before_data: bool = False, gen_id: str | None = None):
        super().__init__(f"Error code: {status} - {body[:300]}")
        self.status_code = status
        self.body = body or ""
        self.retry_after_s = retry_after_s(headers, self.body) if status in (429, 503) else None
        # b64 F3 (harness/agent.maybe_billed, failed_attempt_charge): an error the server returned before any stream data (an HTTP error
        # status on a streamed request, or an SSE error chunk ahead of every data chunk: never generated, not billed), and the generation id
        # of a stream that had started (its OpenRouter /generation record is the attempt's real cost)
        self.before_data = before_data
        self.gen_id = gen_id


class PinUnservable(OpenAIChatError):
    """b65 (2026-10-27): OpenRouter serves no endpoint of a pinned preset under its provider.max_price (HTTP 404 "No endpoints found that
    satisfy the max price for this request", measured live 2026-10-27; or 503 "No allowed providers"): a configuration error, sent before any
    data (never billed), never retried (harness/agent.pin_unservable)."""


# 2026-10-20 (B34, Sol on Azure at 250k tokens/min, about two live sessions): a 429 is a rate limit or a capacity rejection, not a
# transport error. The agent and the reviewer wait for it on their own bounded budget (with_rate_limit_retry), honouring the server's
# retry-after: Azure sends retry-after-ms and retry-after headers and "retry after N seconds" in the body; Google sends RetryInfo.retryDelay
# in the body when it sends anything (the Vertex proxy forwards no headers). A spent quota (ClinePass weekly cap, OpenAI insufficient_quota,
# credits) is not waited for: no wait inside the budget fixes it.
RATE_LIMIT_BUDGET_S = float(os.environ.get("LRA_RATE_LIMIT_BUDGET_S", "1800"))
_PERMANENT_429 = ("insufficient_quota", "inference_cap_error", "weekly", "billing", "credits", "per day", "per_day", "per-day")


def retry_after_s(headers, body: str = "") -> float | None:
    """Seconds the server asks the client to wait, or None: retry-after-ms (Azure), retry-after (seconds or an HTTP date), then the body's
    RetryInfo retryDelay ("12s") or "retry after N second(s)" (Azure's message text)."""
    try:
        h = {str(k).lower(): v for k, v in (headers or {}).items()}
        if h.get("retry-after-ms") not in (None, ""):
            return max(0.0, float(h["retry-after-ms"]) / 1000)
        if h.get("retry-after") not in (None, ""):
            v = str(h["retry-after"]).strip()
            try:
                return max(0.0, float(v))
            except ValueError:
                from email.utils import parsedate_to_datetime
                return max(0.0, parsedate_to_datetime(v).timestamp() - time.time())
    except (TypeError, ValueError, OverflowError, AttributeError):
        pass
    m_ = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body or "") or re.search(r"retry after (\d+(?:\.\d+)?) seconds?", body or "", re.I)
    return float(m_.group(1)) if m_ else None


def is_rate_limit(e: BaseException) -> bool:
    """A 429 worth waiting for: a rate limit (Azure tokens/requests per minute) or a capacity rejection (Vertex RESOURCE_EXHAUSTED,
    an OpenRouter upstream 429); not a spent quota."""
    if not isinstance(e, OpenAIChatError) or e.status_code != 429:
        return False
    b = (e.body or str(e)).lower()
    return not any(k in b for k in _PERMANENT_429)


def with_rate_limit_retry(fn, *, budget_s: float = RATE_LIMIT_BUDGET_S, state: dict | None = None, log=None, sleep=time.sleep,
                          clock=time.monotonic, base_s: float = 15.0, max_wait_s: float = 120.0):
    """fn() until it does not raise a rate-limit 429 (is_rate_limit). Each wait is the server's retry-after x U(1.0, 1.2) + U(0, 2) s (the
    jitter keeps live sessions from retrying in step), else base_s doubling to max_wait_s. The budget is wall time from this call's first 429
    (Vertex can take 2 min to reject), shared through `state` ({"t0", "waited", "hits"}) by the caller's transport attempts of one call: a
    429 whose wait would end past it propagates with e.rate_limit_exhausted = True. Every other error propagates at once."""
    st = state if state is not None else {}
    st.setdefault("waited", 0.0); st.setdefault("hits", 0)
    while True:
        try:
            return fn()
        except OpenAIChatError as e:
            if not is_rate_limit(e):
                raise
            now = clock(); st.setdefault("t0", now); st["hits"] += 1
            used = now - st["t0"]
            ra = e.retry_after_s
            w = max(1.0, (ra * random.uniform(1.0, 1.2) + random.uniform(0, 2)) if ra is not None else
                    min(base_s * 2 ** min(st["hits"] - 1, 6), max_wait_s) * random.uniform(0.8, 1.2))   # jitter here too (Vertex sends no retry-after)
            if used + w > budget_s:
                e.rate_limit_exhausted = True
                if log:
                    log(f"429 rate limited: the 429 budget is used ({used:.0f} of {budget_s:.0f} s since the first rejection, {st['hits']} "
                        "rejections" + (f", server asks {ra:.0f} s" if ra is not None else "") + "); giving up on this call")
                raise
            if log:
                log(f"429 rate limited (retry-after {'none' if ra is None else f'{ra:.1f} s'}): waiting {w:.0f} s "
                    f"({used:.0f} of {budget_s:.0f} s of the 429 budget used, rejection {st['hits']})")
            sleep(w); st["waited"] += w


# b66 (retro A4; failure audit H3 / C8, no-harm rule 2026-10-27): an exception raised before the request reached the server - a DNS
# failure, a refused connection, a connect timeout, a failed TLS handshake - was charged as possibly billed (no status, no before_data:
# agent.maybe_billed True), so a few minutes of network trouble on the organizers' host turned each in-flight row's budget into charges
# that were never billed, and used up the turn's 6 transport attempts. Now such an error is flagged where requests.post raises it (_post:
# not_sent + before_data, so maybe_billed is False: $0), and with_connect_retry waits for the network on the wall clock without using up
# an attempt: LRA_CONNECT_BACKOFF_S (10 s) doubling to 120 s, jittered, within LRA_CONNECT_BUDGET_S (1800 s) of wall time from the first
# failure of the call (shared by the call's attempts through `state`); past it the error propagates with e.connect_exhausted (the agent then
# ends the turn, as after an exhausted 429 budget; still $0). Kept as before (possibly billed): a read timeout, a connection broken after
# the request was sent (urllib3 ProtocolError: reset, remote disconnect), a mid-stream error, a 5xx. The TLS case counts as not sent when
# urllib3 raised it inside its request cycle (MaxRetryError): the handshake is where a TLS error happens in practice; one that breaks the
# body later surfaces as a read error and stays possibly billed. Review 2026-10-27: urllib3 wraps an SSL error raised while the response
# headers were awaited (the whole request sent: a TLS alert or a bad record from the server or a proxy) exactly like a handshake failure
# (MaxRetryError(SSLError)), so connect_failure reads the frames: not sent only for a certificate failure or an error raised in ssl's
# do_handshake with no http.client getresponse in the chain; anything else stays possibly billed.
CONNECT_BUDGET_S = float(os.environ.get("LRA_CONNECT_BUDGET_S", "1800"))
CONNECT_BACKOFF_S = float(os.environ.get("LRA_CONNECT_BACKOFF_S", "10"))


def _exc_chain(e: BaseException) -> list:
    """e and what it wraps (args, urllib3's .reason / .original_error, __cause__; not __context__), at most 24 nodes."""
    seen: list = []
    todo = [e]
    while todo and len(seen) < 24:
        x = todo.pop(0)
        if not isinstance(x, BaseException) or any(x is y for y in seen):
            continue
        seen.append(x)
        todo += [a for a in getattr(x, "args", ()) or () if isinstance(a, BaseException)]
        todo += [getattr(x, "reason", None), getattr(x, "original_error", None), x.__cause__]
    return seen


def connect_failure(e: BaseException) -> bool:
    """b66 (A4): True when `e` was raised before the request reached the server (DNS failure, connection refused, connect timeout, TLS
    handshake failure): never billed. False for anything that may have reached it (a read timeout, a reset or remote disconnect after the
    request was sent, an HTTP status, a mid-stream error)."""
    if getattr(e, "not_sent", False):
        return True
    import socket
    from urllib3 import exceptions as U
    nodes = _exc_chain(e)
    if any(isinstance(x, (U.ProtocolError, U.ReadTimeoutError)) for x in nodes):
        return False   # the connection broke after the request went out
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return True
    if any(isinstance(x, (U.NewConnectionError, U.ConnectTimeoutError, socket.gaierror, ConnectionRefusedError)) for x in nodes):
        return True
    if not (any(isinstance(x, U.MaxRetryError) for x in nodes) and any(isinstance(x, U.SSLError) for x in nodes)):
        return False
    return _tls_handshake(nodes)


def _tls_handshake(nodes: list) -> bool:
    """Review 2026-10-27 (A4): an SSL error inside urllib3's request cycle was raised in the TLS handshake (never sent): a certificate
    failure, or ssl's do_handshake in its traceback with no http.client getresponse (the response awaited after the whole request went out:
    a TLS alert or bad record then may follow a billed request). No traceback (an exception built by hand): possibly billed."""
    import ssl
    import traceback
    if any(isinstance(x, ssl.CertificateError) for x in nodes):
        return True
    frames = {f.f_code.co_name for x in nodes for f, _ in traceback.walk_tb(x.__traceback__)}
    return "do_handshake" in frames and "getresponse" not in frames


def _post(url: str, **kw):
    """requests.post, with a connect failure (connect_failure) flagged on the exception: not_sent and before_data (agent.maybe_billed: $0)."""
    try:
        return requests.post(url, **kw)
    except requests.exceptions.RequestException as e:
        if connect_failure(e):
            e.not_sent, e.before_data = True, True
        raise


def with_connect_retry(fn, *, budget_s: float | None = None, state: dict | None = None, log=None, sleep=time.sleep, clock=time.monotonic,
                       base_s: float | None = None, max_wait_s: float = 120.0, pause=None, resume=None):
    """fn() until it does not raise a connect failure (connect_failure), waiting base_s doubling to max_wait_s (x U(1.0, 1.2)) between
    tries, within budget_s of wall time from the call's first connect failure (`state` {"t0", "waited", "hits"} shared by the caller's
    attempts of one call). Past the budget the failure propagates with e.connect_exhausted = True (and not_sent / before_data: $0). Every
    other error propagates at once. b66 (A4). pause() / resume(): called around each wait (agent.py takes its in-flight pre-charge off the
    ledger while nothing is in flight, so a session killed during a long outage leaves no worst case behind)."""
    budget_s = CONNECT_BUDGET_S if budget_s is None else budget_s
    base_s = CONNECT_BACKOFF_S if base_s is None else base_s
    st = state if state is not None else {}
    st.setdefault("waited", 0.0); st.setdefault("hits", 0)
    while True:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  (re-raised unless it is a connect failure within the budget)
            if not connect_failure(e):
                raise
            try:
                e.not_sent, e.before_data = True, True
            except AttributeError:
                pass
            now = clock(); st.setdefault("t0", now); st["hits"] += 1
            used = now - st["t0"]
            w = max(0.0, min(base_s * 2 ** min(st["hits"] - 1, 6), max_wait_s) * random.uniform(1.0, 1.2))
            if used + w > budget_s:
                try:
                    e.connect_exhausted = True
                except AttributeError:
                    pass
                if log:
                    log(f"connect failure ({type(e).__name__}): the connect budget is used ({used:.0f} of {budget_s:.0f} s since the first "
                        f"failure, {st['hits']} failures; never sent, $0); giving up on this call")
                raise
            if log:
                log(f"connect failure ({type(e).__name__}: {str(e)[:120]}): never sent ($0); waiting {w:.0f} s ({used:.0f} of {budget_s:.0f} s "
                    f"of the connect budget used, failure {st['hits']}; not a transport attempt)")
            if pause:
                pause()
            try:
                sleep(w); st["waited"] += w
            finally:
                if resume:
                    resume()


def tools_to_openai(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {"type": "object"})}} for t in tools]


def messages_to_openai(system: str, msgs: list[dict], think_mode: str = "glm", cache: bool = False) -> list[dict]:
    """think_mode: "glm" passes earlier thinking back as <think> text (GLM chat template); "details" passes OpenRouter
    reasoning_details back; "none" drops it. cache: Anthropic-style cache_control breakpoints on the system prompt and the
    two latest messages (Claude via OpenRouter caches only with explicit breakpoints; 2026-10-10 probe: 7.5x cheaper turn 2)."""
    out: list[dict] = [{"role": "system", "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if cache else system}]
    for m in msgs:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content}); continue
        if role == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            # Pass earlier thinking back as <think>...</think> inside the content: GLM's chat template splits it out as
            # reasoning_content, and renders an empty <think></think> when none is given — after a few such turns the
            # model stops thinking (A100 POC: 36% of turns with ~240 chars vs 65% / ~3.9k chars via the Anthropic path).
            think = "".join(b.get("thinking", "") for b in content if b.get("type") == "thinking")
            if think and think_mode == "glm":
                text = f"<think>{think}</think>" + text
            details = [d for b in content if b.get("type") == "thinking" for d in (b.get("details") or [])]
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)},
                      **({"extra_content": b["extra"]} if b.get("extra") else {})}   # 2026-10-15: Vertex Gemini rejects tool turns without their signature
                     for b in content if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            if details and think_mode == "details":
                msg["reasoning_details"] = details
            out.append(msg)
        else:  # user: tool results and/or plain text blocks
            for b in content:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c)
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": c if isinstance(c, str) else json.dumps(c)})
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b.get("text", "")})
    if cache:
        for m in [m for m in out[1:] if m["role"] in ("user", "tool") and isinstance(m.get("content"), str)][-2:]:
            m["content"] = [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]
    return out


_GLM_CALL = re.compile(r"<tool_call>\s*([^<\s]+)\s*(.*?)</tool_call>", re.S)
_GLM_ARG = re.compile(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.S)


def parse_glm_tool_calls(text: str) -> tuple[str, list[Block]]:
    """GLM-5.x tool-call markup (chat template): <tool_call>name<arg_key>k</arg_key><arg_value>v</arg_value>…</tool_call>; string values are
    raw, other types JSON. Used for budget-forced continuations, where vLLM's reasoning parser labels the whole output as reasoning (no
    </think> in the output) and its tool parser therefore never sees the calls (2026-10-08). Returns (text outside the calls, tool_use blocks)."""
    blocks: list[Block] = []
    for m in _GLM_CALL.finditer(text or ""):
        args: dict[str, Any] = {}
        for k, v in _GLM_ARG.findall(m.group(2)):
            v = v.strip("\n")
            if v[:1] in "[{" or v in ("true", "false", "null") or re.fullmatch(r"-?\d+(\.\d+)?", v or "x"):
                try:
                    args[k.strip()] = json.loads(v); continue
                except json.JSONDecodeError:
                    pass
            args[k.strip()] = v
        blocks.append(Block(type="tool_use", name=m.group(1).strip(), input=args, id=f"call_{uuid.uuid4().hex[:12]}"))
    return _GLM_CALL.sub("", text or "").strip(), blocks


def _is_azure(url: str) -> bool:
    return ".azure.com" in url or ".azure-api.net" in url


def _headers(url: str, api_key: str) -> dict:
    """Azure (2026-10-14, sponsor credit; all development on Azure AI): the `api-key` header; everyone else: Bearer."""
    return {"api-key": api_key, "Content-Type": "application/json"} if _is_azure(url) else {"Authorization": f"Bearer {api_key}",
                                                                                            "Content-Type": "application/json"}


def _azure_body(body: dict) -> dict:
    """OpenRouter-shaped request -> Azure OpenAI v1 chat completions: `max_completion_tokens` (reasoning models reject `max_tokens`), the
    top-level `reasoning_effort` instead of `reasoning: {effort}`, and no OpenRouter-only fields (`usage.include`, `provider`)."""
    b = dict(body)
    if "max_tokens" in b:
        b["max_completion_tokens"] = b.pop("max_tokens")
    b.pop("usage", None); b.pop("provider", None)
    r = b.pop("reasoning", None)
    if isinstance(r, dict) and r.get("effort") and "reasoning_effort" not in b:
        b["reasoning_effort"] = r["effort"]
    return b


def _is_vertex(url: str) -> bool:
    """Vertex AI's OpenAI-compatible endpoint, directly or through harness/vertex_proxy.py (which adds the OAuth token on the host)."""
    return "aiplatform.googleapis.com" in url or "/endpoints/openapi/" in url


VERTEX_READ_S = int(os.environ.get("LRA_VERTEX_READ_S", "900"))   # 2026-10-15: a high-effort Gemini review thinks silently for longer
# 2026-10-20 price-trace audit (Sol on Azure priced as on OpenRouter): a Responses stream cut by the junk guard gets no
# usage, and Azure records no tokens for it, while the OpenRouter path meters the tokens generated until the cut (its generation record).
# Charging the full output cap over-metered the deployable warm-up ladder (wuclean-hx-solab1, OpenRouter) by about $0.48 per row: 61 cuts on
# 15 rows, OpenRouter-metered $0.05 per cut against about $0.16 at the cap. The estimate below charges what was streamed (text and call
# arguments) at 2 characters per token plus a reasoning allowance, never more than the cap; on those 61 cuts the generated tokens were the
# streamed characters / 3 within -2,055..+1,736, so it never under-counted. LRA_JUNK_CUT_WORST_CASE=1 restores the full-cap charge.
JUNK_CUT_REASONING_ALLOWANCE = 1750   # B34 adversarial review: generated tokens = streamed chars / 3 within -2,055..+1,736 on the 61 cuts
# 2026-10-20 B34 adversarial review: the prompt estimate leaves out the replayed encrypted_content blobs. Counted at 3 chars per token they
# inflated the estimate x1.73 on the same 61 cuts (median x1.32 on normal turns; the blobs are ~28% of the body's characters), which the
# OpenRouter path never charges (its generation record has the real prompt tokens). Without them: median x0.94 of the real prompt on 1,631
# normal turns. Priced against OpenRouter on those cuts: full cap +$0.56/row, P1 (chars//2 + 2000, blobs counted) +$0.22/row, this +$0.11/row,
# none under-counted.
def _cut_prompt_chars(body: dict) -> int:
    inp = [{k: v for k, v in it.items() if k != "encrypted_content"} if isinstance(it, dict) else it for it in (body.get("input") or [])]
    return len(body.get("instructions") or "") + len(json.dumps(inp, ensure_ascii=False))
JUNK_CUT_WORST_CASE = os.environ.get("LRA_JUNK_CUT_WORST_CASE") == "1"
# 2026-10-20 B34 patch review: the reasoning generated before the cut is billed too. Counted from the completed reasoning items' encrypted
# blobs (Azure calibration, 13 calls: blob = ~1,100-1,200 chars + 3-6 chars per reasoning token, so (chars - 1000) / 3 never fell below the
# reported reasoning tokens). Validated on all 166 OpenRouter Sol junk cuts with a generation record: streamed chars / 3 + reasoning + 1,750
# under-counted 0 (mean over-charge 2.6k tokens, $0.026 per cut); without the reasoning term the high-effort long-argument turns could
# under-count. The prompt is estimated at 2.5 chars per token with the tool schemas (chars / 3 was p10 x0.8 of the real prompt).
JUNK_CUT_PROMPT_CHARS_PER_TOKEN = 2.5


def _reasoning_seen(items) -> int:
    """Reasoning tokens a cut or usage-less Responses stream already generated, from its completed reasoning items' encrypted blobs."""
    return sum(max(0, len(it.get("encrypted_content") or "") - 1000) // 3 for it in items if isinstance(it, dict) and it.get("type") == "reasoning")


def _estimated_prompt(body: dict, key: str = "input") -> int:
    """A conservative prompt-token estimate for a request with no usage record (no cache discount, as OpenRouter bills a cut stream)."""
    if key == "input":
        chars = _cut_prompt_chars(body)
    else:
        chars = len(json.dumps(body.get(key), ensure_ascii=False))
    return int((chars + len(json.dumps(body.get("tools") or [], ensure_ascii=False))) / JUNK_CUT_PROMPT_CHARS_PER_TOKEN)


def _vertex_body(body: dict) -> dict:
    """OpenRouter-shaped request -> Vertex AI's OpenAI-compatible chat completions: the top-level `reasoning_effort` instead of
    `reasoning: {effort}`, and no OpenRouter-only fields (`usage.include`, `provider`)."""
    b = dict(body)
    b.pop("usage", None); b.pop("provider", None)
    r = b.pop("reasoning", None)
    if isinstance(r, dict) and r.get("effort") and "reasoning_effort" not in b:
        b["reasoning_effort"] = r["effort"]
    return b


def output_tokens(u: dict) -> int:
    """Billed output tokens of a usage record. Most providers count reasoning inside completion_tokens (total = prompt + completion);
    Vertex AI does not (2026-10-15 probe: completion 19, reasoning_tokens 933, total = prompt + 19 + 933), and its reasoning is billed as
    output: add it back whenever the total shows it was left out, so the cap meter never under-counts."""
    comp = int(u.get("completion_tokens") or 0)
    rt = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    tot, pr = u.get("total_tokens"), int(u.get("prompt_tokens") or 0)
    if rt and tot is not None and int(tot) >= pr + comp + rt:
        return comp + rt
    if tot is not None and int(tot) > pr + comp:
        # 2026-10-20 price-trace audit: a usage record whose total exceeds prompt + completion without a reasoning breakdown (a Vertex stream
        # chunk that drops completion_tokens_details) still billed the difference as output: count it, never under-meter
        return int(tot) - pr
    return comp


def reasoning_tokens(u: dict) -> int:
    """Reasoning tokens of a chat-completions usage record as reported (0 when not reported); output_tokens() already includes them."""
    return int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)


# 2026-10-20: Chat Completions does not support function calling with GPT-6.1 Sol (OpenAI's model page: "Use
# the Responses API for tool calling"; 155 request variants on Azure all answered 400, and the "set reasoning_effort to 'none'" the error
# suggests is itself rejected: Sol accepts only low/medium/high/xhigh, plus max on Responses). Presets with think_mode "responses"
# therefore use the Responses API, stateless (store false), with the reasoning replayed between turns as its encrypted items (include
# reasoning.encrypted_content), the same information OpenRouter's Sol path passes back as reasoning_details. Probe: tools + effort medium
# accepted; replayed reasoning accepted; turn 2 read 3,994 of 4,549 input tokens from the prompt cache.
def messages_to_responses(msgs: list[dict]) -> list[dict]:
    """Anthropic-shape history -> Responses API input items. A thinking block carries its response's reasoning items in `details` (passed
    back verbatim); a reasoning item is sent only when an output item of the same turn follows it, because the API rejects a reasoning
    item without its following item (a turn cut at the cap while still thinking)."""
    out: list[dict] = []
    for m in msgs:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content}); continue
        if role == "assistant":
            pending: list[dict] = []
            for b in content:
                t = b.get("type")
                if t == "thinking":
                    pending += [d for d in (b.get("details") or []) if isinstance(d, dict) and d.get("type") == "reasoning" and d.get("encrypted_content")]
                    continue
                if t == "text" and b.get("text"):
                    item = {"role": "assistant", "content": b["text"]}
                elif t == "tool_use":
                    item = {"type": "function_call", "call_id": b["id"], "name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}
                else:
                    continue
                out += pending + [item]; pending = []
        else:  # user: tool results and/or plain text blocks
            for b in content:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c)
                    out.append({"type": "function_call_output", "call_id": b["tool_use_id"], "output": c if isinstance(c, str) else json.dumps(c)})
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b.get("text", "")})
    return out


def _responses_body(model: str, max_tokens: int, system: str, tools: list[dict], messages: list[dict], extra_body: dict | None) -> dict:
    """OpenRouter-shaped extra body -> Responses API request: `reasoning: {effort}` (or a top-level reasoning_effort) becomes
    `reasoning: {effort, summary: auto}` (the summary is the thinking text the trajectories keep); OpenRouter- and vLLM-only fields dropped."""
    eb = dict(extra_body or {})
    for k in ("usage", "provider", "continue_final_message", "add_generation_prompt"):
        eb.pop(k, None)
    r, e = eb.pop("reasoning", None), eb.pop("reasoning_effort", None)
    effort = (r.get("effort") if isinstance(r, dict) else None) or e
    body: dict[str, Any] = {"model": model, "instructions": system, "input": messages_to_responses(messages), "max_output_tokens": max_tokens,
                            "store": False, "include": ["reasoning.encrypted_content"], "reasoning": {"summary": "auto", **({"effort": effort} if effort else {})}}
    if tools:
        body.update(tools=[{"type": "function", "name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {"type": "object"})}
                           for t in tools], tool_choice="auto")
    body.update(eb)
    return body


def _responses_message(j: dict) -> Message:
    """A Responses API response (or the final object of its stream) -> Message, blocks in output order: reasoning -> thinking (its summary as
    text, the item itself in details for the replay), message -> text, function_call -> tool_use (id = call_id). Usage: input_tokens counts
    the cached and cache-written tokens, output_tokens counts the reasoning; Azure reports no cost (the preset's price table meters it)."""
    blocks: list[Block] = []
    for o in j.get("output") or []:
        t = o.get("type")
        if t == "reasoning":
            summ = "\n\n".join(s.get("text", "") for s in o.get("summary") or [] if isinstance(s, dict))
            blocks.append(Block(type="thinking", thinking=summ, details=[{k: v for k, v in o.items() if k != "status"}]))
        elif t == "message":
            txt = "".join(c.get("text") or c.get("refusal") or "" for c in o.get("content") or [] if isinstance(c, dict))
            if txt:
                blocks.append(Block(type="text", text=txt))
        elif t == "function_call":
            try:
                args = json.loads(o.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw_arguments": o.get("arguments")}
            blocks.append(Block(type="tool_use", name=o.get("name"), input=args if isinstance(args, dict) else {"value": args},
                                id=o.get("call_id") or f"call_{uuid.uuid4().hex[:12]}"))
    inc = (j.get("incomplete_details") or {}).get("reason")
    stop = "max_tokens" if inc == "max_output_tokens" else ("tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn")
    u = j.get("usage") or {}; d = u.get("input_tokens_details") or {}
    return Message(content=blocks, stop_reason=stop, usage=Usage(int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                                                                 int(d.get("cached_tokens") or 0), int(d.get("cache_write_tokens") or 0), None,
                                                                 reasoning=int((u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)),
                   raw_finish_reason=inc or j.get("status"))


def _create_responses_streamed(url: str, api_key: str, body: dict, timeout, guard: bool = False) -> Message:
    """Streamed Responses API call: the final response object (response.completed / response.incomplete) gives the Message. guard=True: text
    and function-call argument deltas feed llm/junk.StreamGuard; on junk the stream is closed at once, the call comes back as
    {"_raw_arguments", "_junk"} with stop max_tokens and finish junk_abort, and its usage is estimated from what was streamed (no generation
    record here; see JUNK_CUT_REASONING_ALLOWANCE), marked in Message.usage_estimated."""
    from llm.junk import StreamGuard
    body = dict(body, stream=True)
    sg = StreamGuard() if guard else None
    items: dict[int, dict] = {}; text: dict[int, str] = {}; args: dict[int, str] = {}; final, junk = None, None
    with _post(url, headers=_headers(url, api_key), json=body, timeout=timeout, stream=True) as r:   # b66 (A4): connect failures flagged
        if r.status_code != 200:
            raise OpenAIChatError(r.status_code, r.text, r.headers, before_data=True)   # b64 F3: a status, before any stream data
        for line in r.iter_lines():
            if not line or not line.startswith(b"data: ") or line == b"data: [DONE]":
                continue
            d = json.loads(line[6:]); t = d.get("type") or ""
            if t in ("error", "response.failed"):
                err = d.get("error") or (d.get("response") or {}).get("error") or d
                _code = str((err or {}).get("code") or "")
                raise OpenAIChatError(int(_code) if _code.isdigit() else 429 if "rate_limit" in _code else 500, json.dumps(err)[:300])
            if t in ("response.completed", "response.incomplete"):
                final = d.get("response") or {}; break
            i = int(d.get("output_index") or 0)
            if t in ("response.output_item.added", "response.output_item.done"):
                items[i] = d.get("item") or items.get(i) or {}
            elif t == "response.output_text.delta":
                text[i] = text.get(i, "") + (d.get("delta") or "")
                if sg and junk is None:
                    why = sg.feed("content", "".join(text[k] for k in sorted(text)))
                    junk = (i, why) if why else None
            elif t == "response.function_call_arguments.delta":
                args[i] = args.get(i, "") + (d.get("delta") or "")
                if sg and junk is None:
                    why = sg.feed(i, args[i])
                    junk = (i, why) if why else None
            if junk:
                break   # leaving the with-block closes the connection
    if final is not None and not junk:
        m = _responses_message(final)
        if not final.get("usage"):   # B34 patch review: a final object without usage was metered $0; estimate it like a cut instead
            outs = final.get("output") or []
            shown = sum(len(json.dumps(o.get("content") or o.get("arguments") or "", ensure_ascii=False)) for o in outs if o.get("type") != "reasoning")
            cap = int(body.get("max_output_tokens") or 0)
            m.usage = Usage(_estimated_prompt(body), min(cap, shown // 3 + _reasoning_seen(outs) + JUNK_CUT_REASONING_ALLOWANCE) if cap else 0, 0, 0, None)
            m.usage_estimated = "no_usage"
        return m
    if not junk:
        raise OpenAIChatError(502, "stream ended without a final response")
    out = []
    for i in sorted(items):
        it = dict(items[i])
        if it.get("type") == "function_call" and it.get("status") != "completed":
            it["arguments"] = args.get(i, "")
        elif it.get("type") == "message" and it.get("status") != "completed":
            it["content"] = [{"type": "output_text", "text": text.get(i, "")}]
        out.append(it)
    m = _responses_message({"output": out})
    ji = items.get(junk[0]) or {}
    for b in m.content:
        if b.type == "tool_use" and ji.get("type") == "function_call" and b.id == ji.get("call_id"):
            b.input = {"_raw_arguments": args.get(junk[0], ""), "_junk": junk[1]}
    m.stop_reason, m.raw_finish_reason = "max_tokens", "junk_abort"
    cap = int(body.get("max_output_tokens") or 0)
    seen = sum(len(v) for v in text.values()) + sum(len(v) for v in args.values())   # characters streamed before the cut
    out_est = cap if JUNK_CUT_WORST_CASE else min(cap, seen // 3 + _reasoning_seen(items.values()) + JUNK_CUT_REASONING_ALLOWANCE)
    in_est = (len(body.get("instructions") or "") + len(json.dumps(body.get("input"), ensure_ascii=False))) // 3 if JUNK_CUT_WORST_CASE \
        else _estimated_prompt(body)
    m.usage = Usage(in_est, out_est, 0, 0, None)
    m.usage_estimated = "junk_cut_worst_case" if JUNK_CUT_WORST_CASE else f"junk_cut ({seen} chars streamed)"
    return m


def create(*, base_url: str, api_key: str, model: str, max_tokens: int, system: str, tools: list[dict], messages: list[dict],
           extra_body: dict | None = None, timeout=(30, 3600), think_mode: str = "glm", cache: bool = False, stream: bool = False,
           guard: bool = False) -> Message:   # 2026-10-08: 900 s cut non-streamed high-effort answers on a saturated A100 (13-55% retried, biased to short outputs)   # (connect, read) — read = max silence while a generation is awaited; a 24k-token turn at ~44 tok/s is ~9 min
    if think_mode == "responses":
        url = base_url.rstrip("/") + "/responses"
        if _is_azure(url):   # the same stall bound as Azure chat completions
            timeout = (timeout[0], min(timeout[1], VERTEX_READ_S)) if isinstance(timeout, tuple) else min(timeout, VERTEX_READ_S)
        rb = _responses_body(model, max_tokens, system, tools, messages, extra_body)
        if stream or guard:
            return _create_responses_streamed(url, api_key, rb, timeout, guard=guard)
        r = _post(url, headers=_headers(url, api_key), json=rb, timeout=timeout)
        if r.status_code != 200:
            raise OpenAIChatError(r.status_code, r.text, r.headers)
        return _responses_message(r.json())
    body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages_to_openai(system, messages, think_mode, cache),
                            "stream": False}
    if tools:   # vLLM rejects an empty tools array with HTTP 400 (2026-10-07: the LR eval's tool-less calls all failed)
        body.update(tools=tools_to_openai(tools), tool_choice="auto")
    if extra_body:
        body.update(extra_body)
    url = base_url.rstrip("/") + "/chat/completions"
    if _is_azure(url):
        body = _azure_body(body)
        # 2026-10-15 babysit: an Azure Kimi review stream sent nothing for an hour (read timeout 3600 s); streams carry reasoning tokens
        # continuously (Kimi about 25 tok/s), so a silence past VERTEX_READ_S is a stall here too
        timeout = (timeout[0], min(timeout[1], VERTEX_READ_S)) if isinstance(timeout, tuple) else min(timeout, VERTEX_READ_S)
    if _is_vertex(url):
        body = _vertex_body(body)
        # 2026-10-15 babysit: one Argon stream sent nothing for an hour (the 3600 s read timeout, then a retry answered in 9.9 s); Vertex
        # turns take 3-30 s and send no bytes while thinking, so a silence past VERTEX_READ_S is a stall: give up and let the caller retry
        timeout = (timeout[0], min(timeout[1], VERTEX_READ_S)) if isinstance(timeout, tuple) else min(timeout, VERTEX_READ_S)
    if stream or guard:   # 2026-10-10: ClinePass turns a non-streamed all-reasoning turn into HTTP 500 "empty response content"
        # 2026-10-14 guard=True: streamed so junk can be cut mid-generation (llm/junk.py; a non-streamed request is billed in full)
        return _create_streamed(url, api_key, body, timeout, guard=guard)
    r = _post(url, headers=_headers(url, api_key), json=body, timeout=timeout)   # b66 (A4): a connect failure is flagged ($0)
    if r.status_code == 400 and "maximum context length" in r.text:
        # Window guard (A100 POC 2026-10-06: escalated 18-24k caps on 107k+ prompts overflowed a 131k window and the harness
        # retried the same 400 twenty times): shrink max_tokens to what fits and retry once, immediately.
        m_ = re.search(r"maximum context length is (\d+) tokens.*?contains at least (\d+) input tokens", r.text, re.S)
        if m_:
            fit = int(m_.group(1)) - int(m_.group(2)) - 256
            if fit >= 512:
                body["max_completion_tokens" if _is_azure(url) else "max_tokens"] = fit
                r = _post(url, headers=_headers(url, api_key), json=body, timeout=timeout)
    if r.status_code != 200:
        if os.environ.get("LRA_DUMP_FAILED_REQ"):   # debugging aid: keep the exact failing request body
            pathlib.Path(os.environ["LRA_DUMP_FAILED_REQ"]).write_text(json.dumps(body, ensure_ascii=False))
        raise OpenAIChatError(r.status_code, r.text, r.headers)
    j = r.json()
    if "choices" not in j and isinstance(j.get("data"), dict) and "choices" in j["data"]:
        j = j["data"]   # ClinePass wraps non-streaming responses in {"data": {...}}
    if "error" in j and not j.get("choices"):
        raise OpenAIChatError(int((j["error"] or {}).get("code") or 500), json.dumps(j["error"])[:300])
    ch = j["choices"][0]; msg = ch.get("message") or {}
    blocks: list[Block] = []
    think = msg.get("reasoning_content") or msg.get("reasoning")
    if think or msg.get("reasoning_details"):
        blocks.append(Block(type="thinking", thinking=think or "", details=msg.get("reasoning_details")))
    if msg.get("content"):
        blocks.append(Block(type="text", text=msg["content"]))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw_arguments": fn.get("arguments")}
        blocks.append(Block(type="tool_use", name=fn.get("name"), input=args if isinstance(args, dict) else {"value": args},
                            id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}", extra=tc.get("extra_content") or None))
    fr = ch.get("finish_reason")
    stop = "max_tokens" if fr == "length" else ("tool_use" if (fr == "tool_calls" or any(b.type == "tool_use" for b in blocks)) else "end_turn")
    u = j.get("usage") or {}
    pd = u.get("prompt_tokens_details") or {}
    gw = ((msg.get("provider_metadata") or {}).get("gateway") or {})
    cost = u.get("cost") if u.get("cost") is not None else (float(gw["cost"]) if gw.get("cost") else None)
    return Message(content=blocks, stop_reason=stop, usage=Usage(int(u.get("prompt_tokens") or 0), output_tokens(u),
                                                                 int(pd.get("cached_tokens") or 0), int(pd.get("cache_write_tokens") or 0), cost,
                                                                 reasoning=reasoning_tokens(u)),
                   provider=j.get("provider"), raw_finish_reason=fr)


def _merge_details(acc: dict, items: list) -> None:
    """Streamed OpenRouter reasoning_details arrive as pieces keyed by `index` and `type`: string fields (text, summary, data, signature)
    are concatenated per (index, type), other fields kept from the first piece that has them. 2026-10-14: keyed by type too, because
    Gemini 4 Argon streams a reasoning.text item and its reasoning.encrypted thought signature both at index 0 (keyed by index alone they
    fused into one malformed item); Sol streams summary at 0 and encrypted at 1, unchanged."""
    for it in items or []:
        if not isinstance(it, dict):
            continue
        cur = acc.setdefault((it.get("index", len(acc)), it.get("type")), {})
        for k, v in it.items():
            if isinstance(v, str) and k in ("text", "summary", "data", "signature") and isinstance(cur.get(k), str):
                cur[k] += v
            elif k not in cur or cur[k] in (None, ""):
                cur[k] = v


def generation_usage(base_url: str, api_key: str, gen_id: str, tries: int = 8, wait: float = 3.0) -> Usage | None:
    """OpenRouter's record of one generation (GET /generation?id=...): native token counts and cost, for a stream the guard cut (no usage
    chunk arrives after a cancel). None when not available after `tries` x `wait` seconds (bounded: 8 x 3 s)."""
    for _ in range(tries):
        try:
            r = requests.get(base_url.rstrip("/") + "/generation", params={"id": gen_id}, headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
            if r.status_code == 200:
                d = r.json().get("data") or {}
                pin = d.get("native_tokens_prompt") or d.get("tokens_prompt")
                pout = d.get("native_tokens_completion") or d.get("tokens_completion")
                if pin is not None and pout is not None:
                    u = Usage(int(pin), int(pout), int(d.get("native_tokens_cached") or 0), 0,
                              float(d["total_cost"]) if d.get("total_cost") is not None else None)
                    u.cw_reported = False   # b65: the record has no cache-write count (153 of 153 Sol junk-cut records read 0)
                    return u
        except (requests.RequestException, ValueError):
            pass
        time.sleep(wait)
    return None


def generation_provider(base_url: str, api_key: str, gen_id: str, timeout: float = 10.0) -> str | None:
    """b64 F4: the provider that served one OpenRouter generation (GET /generation's provider_name), or None. One request, no retry: the
    agent asks at most once per session, and only when the stream named no provider."""
    try:
        r = requests.get(base_url.rstrip("/") + "/generation", params={"id": gen_id}, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        return ((r.json().get("data") or {}).get("provider_name") or None) if r.status_code == 200 else None
    except (requests.RequestException, ValueError, AttributeError):
        return None


def _stream_lines(r, st: dict):
    """r.iter_lines(). b64 F3: a transport error raised mid-stream (a read timeout, a connection cut) leaves with e.gen_id and e.streamed
    from `st` (kept current by the caller), so the agent can price the attempt from its generation record instead of the worst case."""
    try:
        yield from r.iter_lines()
    except Exception as e:  # noqa: BLE001  (re-raised as is)
        try:
            e.gen_id, e.streamed = st.get("gen_id"), bool(st.get("data"))
        except AttributeError:
            pass
        raise


def _create_streamed(url: str, api_key: str, body: dict, timeout, guard: bool = False) -> Message:
    """Streamed /chat/completions assembled into the same Message shape (reasoning and reasoning_details, content, tool calls by index,
    usage). guard=True (2026-10-14): every chunk feeds llm/junk.StreamGuard; on junk the stream is closed at once (OpenRouter cancels the
    generation and its billing for supported providers, OpenAI among them), the junk call comes back as {"_raw_arguments", "_junk"} with
    stop_reason max_tokens and raw_finish_reason "junk_abort", and its usage is OpenRouter's generation record; if that is unavailable, the
    worst case is charged (the request's prompt at 3 chars per token and the full max_tokens), so a budget cap never under-counts."""
    from llm.junk import StreamGuard
    body = dict(body, stream=True, stream_options={"include_usage": True})
    reasoning, content, details, calls, fin, usage, gen_id, junk = [], [], {}, {}, None, {}, None, None
    prov, st = None, {"gen_id": None, "data": False}   # b64 F4: the provider the stream names; b64 F3: what had arrived before an error
    sg = StreamGuard() if guard else None
    with _post(url, headers=_headers(url, api_key), json=body, timeout=timeout, stream=True) as r:   # b66 (A4): connect failures flagged
        if r.status_code != 200:
            raise OpenAIChatError(r.status_code, r.text, r.headers, before_data=True)   # b64 F3: a status, before any stream data
        for line in _stream_lines(r, st):
            if not line or not line.startswith(b"data: ") or line == b"data: [DONE]":
                continue
            d = json.loads(line[6:])
            if d.get("error"):
                # b64 F3: an error chunk ahead of every data chunk (it2a: 22 OpenRouter 502 "Our servers are currently overloaded") was never
                # generated; a non-numeric code ("server_error") is a 500 (int() of it raised a ValueError the agent charged as a transport error)
                try:
                    _ec = int((d["error"] or {}).get("code") or 500)   # every numeric form as before ("502", 502, 502.0)
                except (TypeError, ValueError):
                    _ec = 500
                raise OpenAIChatError(_ec, json.dumps(d["error"])[:300], before_data=not st["data"], gen_id=d.get("id") or gen_id)
            gen_id = d.get("id") or gen_id
            prov = d.get("provider") or prov
            st.update(gen_id=gen_id, data=True)
            usage = d.get("usage") or usage
            for c in d.get("choices") or []:
                dl = c.get("delta") or {}
                if dl.get("reasoning") or dl.get("reasoning_content"):
                    reasoning.append(dl.get("reasoning") or dl.get("reasoning_content"))
                if dl.get("reasoning_details"):
                    _merge_details(details, dl["reasoning_details"])
                if dl.get("content"):
                    content.append(dl["content"])
                    if sg and junk is None:
                        why = sg.feed("content", "".join(content))
                        junk = ("content", why) if why else None
                for tc in dl.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": "", "extra": None})
                    slot["id"] = tc.get("id") or slot["id"]
                    slot["extra"] = tc.get("extra_content") or slot["extra"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""
                    if sg and junk is None:
                        why = sg.feed(tc.get("index", 0), slot["args"])
                        junk = (tc.get("index", 0), why) if why else None
                fin = c.get("finish_reason") or fin
            if junk:
                break   # leaving the with-block closes the connection: the generation is cancelled
    blocks: list[Block] = []
    if reasoning or details:
        blocks.append(Block(type="thinking", thinking="".join(reasoning), details=list(details.values()) or None))   # arrival order
    if content:
        blocks.append(Block(type="text", text="".join(content)))
    for i, s in sorted(calls.items()):
        if junk and junk[0] == i:
            args = {"_raw_arguments": s["args"], "_junk": junk[1]}
        else:
            try:
                args = json.loads(s["args"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw_arguments": s["args"]}
        blocks.append(Block(type="tool_use", name=s["name"], input=args if isinstance(args, dict) else {"value": args},
                            id=s["id"] or f"call_{uuid.uuid4().hex[:12]}", extra=s["extra"]))
    if junk:
        base = url.rsplit("/chat/completions", 1)[0]
        u = generation_usage(base, api_key, gen_id) if gen_id and ("openrouter.ai" in url or os.environ.get("LRA_SELFTEST_GENERATION")) else None
        worst = u is None
        if u is None:   # worst case: nothing was cancelled
            # Azure bodies carry the cap as max_completion_tokens (_azure_body renames it); reading only max_tokens charged 0 output tokens
            u = Usage(len(json.dumps(body.get("messages"), ensure_ascii=False)) // 3,
                      int(body.get("max_tokens") or body.get("max_completion_tokens") or 0), 0, 0, None)
        m = Message(content=blocks, stop_reason="max_tokens", usage=u, raw_finish_reason="junk_abort", gen_id=gen_id)
        if worst:   # b64 L1 (c): flagged like the Responses path; agent.py --junk-billing-reconcile looks the record up again later
            m.usage_estimated = "junk_cut_worst_case"
        return m
    if fin is None and not usage and _is_vertex(url):
        # 2026-10-20 price-trace audit: harness/vertex_proxy.py streams close-delimited (HTTP/1.0), so an upstream error mid-stream reaches us as a
        # clean end of stream: no finish reason, no usage. Returned as is it was a partial answer metered at $0; raise a retryable error instead
        # (as the Responses path does), so the caller retries and records the attempt
        raise OpenAIChatError(502, "stream ended without a finish reason or usage")
    stop = "max_tokens" if fin == "length" else ("tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn")
    paid = "openrouter.ai" in url or _is_azure(url) or _is_vertex(url) or "cline" in url
    if not usage and paid:
        # B34 patch review: a finished stream whose usage chunk never arrived (lost after the finish chunk, e.g. the close-delimited Vertex
        # proxy) was metered $0. OpenRouter: its generation record; otherwise an estimate, flagged (the answer is kept: retrying would bill twice)
        base = url.rsplit("/chat/completions", 1)[0]
        u = generation_usage(base, api_key, gen_id) if gen_id and "openrouter.ai" in url else None
        if u is None:
            cap = int(body.get("max_tokens") or body.get("max_completion_tokens") or 0)
            shown = len("".join(reasoning)) + len("".join(content)) + sum(len(s["args"]) for s in calls.values())
            u = Usage(_estimated_prompt(body, "messages"), min(cap, shown // 3 + JUNK_CUT_REASONING_ALLOWANCE) if cap else 0, 0, 0, None)
        m = Message(content=blocks, stop_reason=stop, usage=u, raw_finish_reason=fin, provider=prov, gen_id=gen_id)   # b64 F4: id, provider
        m.usage_estimated = "no_usage"
        return m
    pd = usage.get("prompt_tokens_details") or {}
    return Message(content=blocks, stop_reason=stop, usage=Usage(int(usage.get("prompt_tokens") or 0), output_tokens(usage),
                                                                 int(pd.get("cached_tokens") or 0), int(pd.get("cache_write_tokens") or 0),
                                                                 usage.get("cost"), reasoning=reasoning_tokens(usage)), raw_finish_reason=fin,
                   provider=prov, gen_id=gen_id)   # b64 F4: the generation id and the provider the stream named, for the trajectory


if __name__ == "__main__":  # smoke test against OpenRouter's OpenAI endpoint: python3 llm/openai_compat.py
    import os, pathlib
    key = pathlib.Path("~/.config/vexorium/openrouter_api_key").expanduser().read_text().strip()
    t0 = time.time()
    m = create(base_url="https://openrouter.ai/api/v1", api_key=key, model="z-ai/glm-5.3-flash", max_tokens=200, system="You are terse.",
               tools=[{"name": "echo", "description": "echo a string", "input_schema": {"type": "object", "properties": {"s": {"type": "string"}}, "required": ["s"]}}],
               messages=[{"role": "user", "content": "Call the echo tool with s='ready'."}],
               extra_body={"reasoning": {"effort": "low"}, "provider": {"quantizations": ["nvfp4"], "allow_fallbacks": False}})
    print(m.stop_reason, m.provider, m.usage, [b.model_dump() for b in m.content], f"{time.time()-t0:.1f}s")
