"""Claude on Vertex AI through harness/vertex_proxy.py (2026-10-15: Opus 5.5 via Vertex AI as the review
loop's reviewer; the GCP project comes from LRA_GCP_PROJECT). The official Anthropic SDK's AnthropicVertex client builds the rawPredict / streamRawPredict request; its base URL is the
proxy on the docker bridge, which adds the OAuth token on the host (no Google token in this process's environment). Returns the
llm/openai_compat Message shape (blocks with .type/.text/.thinking/.name/.input/.id, .stop_reason, .usage with .cost at list price), which
harness/architect.call and harness/review.py already read.

Opus 5.5: thinking is always on (no `thinking` field: a budget is rejected); depth is `output_config.effort` (low | medium | high | xhigh |
max). Streamed (long outputs) and read once complete with get_final_message(); tool inputs are therefore whole, and a call cut at max_tokens
is reported as stop_reason max_tokens for the caller to treat as incomplete.
"""
from __future__ import annotations
import os
from llm.openai_compat import Block, Message, Usage

PROXY_BASE = "http://172.17.0.1:18190/v1"


def create(*, model: str, max_tokens: int, system: str, tools: list[dict], messages: list[dict], effort: str | None,
           prices: tuple, region: str = "global", project: str = "", timeout: float = 3600) -> Message:
    from anthropic import AnthropicVertex
    cl = AnthropicVertex(region=region, project_id=project or os.environ.get("LRA_GCP_PROJECT", "your-gcp-project"), access_token="via-proxy", base_url=PROXY_BASE, timeout=timeout, max_retries=2)
    kw: dict = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
    if tools:
        kw["tools"] = tools
    if effort:
        kw["output_config"] = {"effort": effort}
    with cl.messages.stream(**kw) as s:
        m = s.get_final_message()
    blocks: list[Block] = []
    for b in m.content:
        if b.type == "thinking":
            blocks.append(Block(type="thinking", thinking=getattr(b, "thinking", "") or ""))
        elif b.type == "text":
            blocks.append(Block(type="text", text=b.text))
        elif b.type == "tool_use":
            blocks.append(Block(type="tool_use", name=b.name, input=b.input if isinstance(b.input, dict) else {"value": b.input}, id=b.id))
    u = m.usage
    cr, cw = int(getattr(u, "cache_read_input_tokens", 0) or 0), int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    pi, po, pr, pw = prices
    cost = round((u.input_tokens * pi + u.output_tokens * po + cr * pr + cw * pw) / 1e6, 6)
    stop = {"tool_use": "tool_use", "max_tokens": "max_tokens"}.get(m.stop_reason or "", "end_turn")
    return Message(content=blocks, stop_reason=stop, usage=Usage(int(u.input_tokens), int(u.output_tokens), cr, cw, cost),
                   provider="vertex", raw_finish_reason=m.stop_reason)
