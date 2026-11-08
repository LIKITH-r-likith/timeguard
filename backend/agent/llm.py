"""LLM client interface and implementations.

LLMClient is a Protocol. Implementations:
  - GroqClient: calls the Groq API (reads GROQ_API_KEY and LLM_MODEL from env).
  - MockLLM:   scripted responses for tests.
  - ReplayLLM: record/replay from evals/replay/*.json, keyed by message hash.

Select via LLM_MODE env var: live | replay | mock.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    """Uniform response from any LLM backend."""

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@runtime_checkable
class LLMClient(Protocol):
    """Read-only LLM access.  Implementations must never write to timecards."""

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# GroqClient — live API calls (never used in tests)
# ---------------------------------------------------------------------------
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MAX_RETRIES = 2
_TIMEOUT_S = 30


class GroqClient:
    """Calls the Groq REST API with retries and back-off."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = _TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required for GroqClient")

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        if tools:
            body["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]
            body["tool_choice"] = "auto"

        data = json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err: Exception | None = None
        for attempt in range(1 + self.max_retries):
            if attempt > 0:
                time.sleep(2 ** attempt)  # exponential back-off
            t0 = time.monotonic()
            try:
                req = urllib.request.Request(_GROQ_URL, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    result = json.loads(resp.read())
                latency = int((time.monotonic() - t0) * 1000)
                return _parse_groq(result, latency)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                last_err = exc
        raise ConnectionError(f"Groq API failed after {1 + self.max_retries} attempts: {last_err}")


def _parse_groq(result: dict, latency_ms: int) -> LLMResponse:
    choice = result["choices"][0]["message"]
    text = choice.get("content") or ""
    tool_calls: list[dict] = []
    for tc in choice.get("tool_calls") or []:
        fn = tc.get("function", {})
        args_raw = fn.get("arguments", "{}")
        tool_calls.append({
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "arguments": json.loads(args_raw) if isinstance(args_raw, str) else args_raw,
        })
    usage = result.get("usage", {})
    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# MockLLM — scripted responses for unit tests
# ---------------------------------------------------------------------------
class MockLLM:
    """Pops pre-loaded responses in order.  Used exclusively by tests."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses: list[LLMResponse] = list(responses or [])
        self.calls: list[dict] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return LLMResponse(text="", tool_calls=[])
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# ReplayLLM — record/replay from evals/replay/*.json
# ---------------------------------------------------------------------------
REPLAY_DIR = Path(__file__).resolve().parents[2] / "evals" / "replay"


def _message_hash(messages: list[dict]) -> str:
    blob = json.dumps(messages, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class ReplayLLM:
    """Cache layer over a real LLM.

    LLM_MODE=replay  → read from cache, error on cache miss.
    LLM_MODE=live    → read from cache, fall through to real client on miss,
                        record the result for future replays.
    """

    def __init__(self, inner: LLMClient | None = None, replay_dir: Path | None = None) -> None:
        self.inner = inner
        self.dir = replay_dir or REPLAY_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        key = _message_hash(messages)
        cached = self._path(key)
        if cached.exists():
            data = json.loads(cached.read_text("utf-8"))
            return LLMResponse(**data)

        mode = os.environ.get("LLM_MODE", "replay")
        if mode == "replay":
            raise FileNotFoundError(f"Replay cache miss: {key} (set LLM_MODE=live to record)")

        if self.inner is None:
            raise ValueError("ReplayLLM in live mode needs an inner LLMClient")
        resp = self.inner.complete(messages, tools)
        data = {
            "text": resp.text,
            "tool_calls": resp.tool_calls,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "latency_ms": resp.latency_ms,
        }
        cached.write_text(json.dumps(data, indent=2), "utf-8")
        return resp


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_llm(mode: str | None = None) -> LLMClient:
    """Return an LLM client based on LLM_MODE env or explicit *mode*."""
    m = (mode or os.environ.get("LLM_MODE", "live")).lower()
    if m == "mock":
        return MockLLM()
    if m == "demo":
        from backend.agent.demo_script import ScriptedLLM
        return ScriptedLLM()
    if m == "replay":
        return ReplayLLM()
    # live mode
    inner = GroqClient()
    return ReplayLLM(inner=inner)
