"""LLM access with per-call token accounting.

The benchmark is as much about token cost as accuracy, so every call records
usage reported by the provider rather than an estimate.  All three pipelines
share this client so their costs are measured on the same basis.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from occam.eval.metrics import TokenUsage

_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


@dataclass
class LLMResponse:
    text: str
    usage: TokenUsage
    latency_s: float


class LLM:
    """Thin wrapper over Gemini that reports token usage on every call.

    ``offline=True`` makes the client raise instead of silently degrading, so a
    benchmark run can never quietly turn into a no-LLM run and report the
    resulting token count as a saving.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 temperature: float = 0.0):
        self.model = model or _DEFAULT_MODEL
        self.temperature = temperature
        self.calls: list[LLMResponse] = []
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set - copy .env.example to .env and fill it in")
        from occam.net import ensure_tls_trust
        ensure_tls_trust()
        from google import genai
        self._client = genai.Client(api_key=key)
        self._genai_types = __import__("google.genai.types", fromlist=["types"])

    def complete(self, prompt: str, *, system: str | None = None,
                 max_output_tokens: int = 1024, thinking: bool = False) -> LLMResponse:
        kwargs = dict(temperature=self.temperature,
                      max_output_tokens=max_output_tokens,
                      system_instruction=system)
        if not thinking:
            # Gemini 2.5 spends "thinking" tokens out of the same output budget,
            # which silently truncates short structured replies mid-JSON. These
            # calls emit a small fixed schema, so the budget is better spent on
            # the answer itself.
            try:
                kwargs["thinking_config"] = self._genai_types.ThinkingConfig(
                    thinking_budget=0)
            except AttributeError:
                pass
        cfg = self._genai_types.GenerateContentConfig(**kwargs)
        t0 = time.time()
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=cfg)
                break
            except Exception as exc:               # transient rate limits / 5xx
                last = exc
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        else:                                       # pragma: no cover
            raise last                              # type: ignore[misc]

        um = getattr(r, "usage_metadata", None)
        usage = TokenUsage(
            context=getattr(um, "prompt_token_count", 0) or 0,
            llm_input=getattr(um, "prompt_token_count", 0) or 0,
            llm_output=getattr(um, "candidates_token_count", 0) or 0,
        )
        resp = LLMResponse(r.text or "", usage, time.time() - t0)
        self.calls.append(resp)
        return resp

    @property
    def usage(self) -> TokenUsage:
        total = TokenUsage()
        for c in self.calls:
            total = total.add(c.usage)
        return total

    def reset(self) -> None:
        self.calls.clear()


_JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply.

    Models wrap JSON in prose or fences often enough that parsing the raw reply
    is unreliable; this tolerates both and raises with the offending text so a
    bad reply is diagnosable rather than silently empty.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"no JSON object in model reply: {text[:200]!r}")
    return json.loads(m.group(0))
