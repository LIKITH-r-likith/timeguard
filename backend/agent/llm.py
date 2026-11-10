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
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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
# Rate Limiting & Pacing
# ---------------------------------------------------------------------------
def parse_retry_delay(body: str, retry_after_header: str | None = None) -> float | None:
    """Parse delay in seconds from error body or Retry-After header."""
    if retry_after_header:
        try:
            return float(str(retry_after_header).strip())
        except (ValueError, TypeError):
            pass
    if not body:
        return None

    # Handle composite minutes and seconds, e.g. "try again in 1m20s"
    m_combo = re.search(
        r"try again in\s*(\d+)\s*m(?:in(?:ute)?s?)?\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:ond)?s?)?",
        body,
        re.IGNORECASE,
    )
    if m_combo:
        return float(m_combo.group(1)) * 60.0 + float(m_combo.group(2))

    # Match "try again in 2.34s", "try again in 450ms", "try again in 12 seconds", etc.
    m = re.search(
        r"try again in\s*([0-9.]+)\s*(ms|millisecond|milliseconds|s|sec|second|seconds|m|min|minute|minutes)?",
        body,
        re.IGNORECASE,
    )
    if m:
        val = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        if unit.startswith("ms") or "milli" in unit:
            return val / 1000.0
        elif unit.startswith("m") and not unit.startswith("ms"):
            return val * 60.0
        else:
            return val
    return None


class TokenPacer:
    """Sliding-window token rate limiter (tokens per minute)."""

    def __init__(
        self,
        tpm_limit: int | None = None,
        window_seconds: float = 60.0,
        time_fn: Any = None,
        sleep_fn: Any = None,
    ) -> None:
        self._tpm_override = tpm_limit
        self.window_seconds = window_seconds
        self.time_fn = time_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.history: list[tuple[float, int]] = []

    @property
    def tpm_limit(self) -> int:
        if self._tpm_override is not None:
            return self._tpm_override
        try:
            return int(os.environ.get("GROQ_TPM_LIMIT", "6000"))
        except ValueError:
            return 6000

    def pace(self, est_tokens: int) -> float:
        """Sleep if adding est_tokens would exceed tpm_limit in the last window_seconds.

        Returns total seconds slept.
        """
        limit = self.tpm_limit
        if limit <= 0:
            return 0.0

        total_slept = 0.0
        while True:
            now = self.time_fn()
            cutoff = now - self.window_seconds
            self.history = [(t, c) for t, c in self.history if t > cutoff]
            used = sum(c for _, c in self.history)

            if not self.history or (used + est_tokens <= limit):
                break

            oldest_ts, _ = self.history[0]
            wait = (oldest_ts + self.window_seconds) - now
            if wait <= 0:
                continue

            self.sleep_fn(wait)
            total_slept += wait

        return total_slept

    def record(self, tokens: int) -> None:
        """Record actual tokens consumed."""
        if tokens > 0:
            self.history.append((self.time_fn(), tokens))


def _unwrap_failed_generation(failed_gen: Any) -> str | None:
    """Unwrap failed_generation from Groq tool_use_failed error.

    Handles direct JSON strings or wrappers like {"name": "json", "arguments": {...}}.
    Returns unwrapped JSON text if valid, else None.
    """
    if not failed_gen:
        return None

    parsed: Any = None
    if isinstance(failed_gen, str):
        failed_gen = failed_gen.strip()
        try:
            parsed = json.loads(failed_gen)
        except Exception:
            return None
    elif isinstance(failed_gen, dict):
        parsed = failed_gen
    else:
        return None

    if isinstance(parsed, dict):
        # Check if wrapped in {"name": "...", "arguments": {...}}
        if "arguments" in parsed:
            args = parsed["arguments"]
            if isinstance(args, dict):
                return json.dumps(args)
            elif isinstance(args, str):
                try:
                    json.loads(args)
                    return args
                except Exception:
                    pass
        return json.dumps(parsed)

    return None


_shared_pacer = TokenPacer()


# ---------------------------------------------------------------------------
# GroqClient — live API calls (never used in tests)
# ---------------------------------------------------------------------------
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MAX_RETRIES = 8
_TIMEOUT_S = 30


class GroqClient:
    """Calls the Groq REST API with pacing, retries, and back-off."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = _TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
        pacer: TokenPacer | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
        self.timeout = timeout
        self.max_retries = max_retries
        self.pacer = pacer or _shared_pacer
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
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters") or t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"

        data = json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "timeguard/1.0",
            "Accept": "application/json",
        }

        est_tokens = max(100, len(data) // 4 + 350)
        last_err: Exception | None = None

        for attempt in range(1 + self.max_retries):
            # Enforce pacing before initiating call
            self.pacer.pace(est_tokens)

            t0 = time.monotonic()
            try:
                req = urllib.request.Request(_GROQ_URL, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    result = json.loads(resp.read())
                latency = int((time.monotonic() - t0) * 1000)
                parsed = _parse_groq(result, latency)
                actual_tokens = parsed.input_tokens + parsed.output_tokens
                self.pacer.record(actual_tokens if actual_tokens > 0 else est_tokens)
                return parsed
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    raw = exc.read()
                    err_body = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                except Exception:
                    pass
                err_msg = f"{exc}: {err_body}" if err_body else str(exc)
                last_err = RuntimeError(err_msg)

                # HTTP 400 with code tool_use_failed: unwrap failed_generation if JSON
                if exc.code == 400 and err_body:
                    try:
                        err_data = json.loads(err_body)
                        error_obj = err_data.get("error", {})
                        if error_obj.get("code") == "tool_use_failed":
                            failed_gen = error_obj.get("failed_generation")
                            unwrapped = _unwrap_failed_generation(failed_gen)
                            if unwrapped is not None:
                                latency = int((time.monotonic() - t0) * 1000)
                                self.pacer.record(est_tokens)
                                return LLMResponse(
                                    text=unwrapped,
                                    input_tokens=est_tokens,
                                    output_tokens=max(1, len(unwrapped) // 4),
                                    latency_ms=latency,
                                )
                    except Exception:
                        pass

                # HTTP 429: Rate limit hit
                if exc.code == 429 and attempt < self.max_retries:
                    retry_header = None
                    if hasattr(exc, "headers") and exc.headers:
                        retry_header = exc.headers.get("Retry-After")
                    delay = parse_retry_delay(err_body, retry_header)
                    sleep_s = (delay if delay is not None else 1.0) + 1.0
                    time.sleep(sleep_s)
                    continue

                # HTTP 5xx: Server errors
                if 500 <= exc.code < 600 and attempt < self.max_retries:
                    backoff = min(60.0, (2 ** attempt) + 1.0)
                    time.sleep(backoff)
                    continue

                # Non-retryable 4xx or retries exhausted
                raise ConnectionError(f"Groq API failed after {attempt + 1} attempts: {last_err}") from exc

            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
                if attempt < self.max_retries:
                    time.sleep(min(60.0, (2 ** attempt) + 1.0))
                    continue
                raise ConnectionError(f"Groq API failed after {attempt + 1} attempts: {last_err}") from exc

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

    def __init__(self, responses: list[LLMResponse | Exception] | None = None) -> None:
        self.responses: list[LLMResponse | Exception] = list(responses or [])
        self.calls: list[dict] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return LLMResponse(text="", tool_calls=[])
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


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

    def __init__(
        self,
        inner: LLMClient | None = None,
        replay_dir: Path | None = None,
        allow_network: bool | None = None,
    ) -> None:
        self.inner = inner
        self.dir = replay_dir or REPLAY_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.last_cache_hit = False
        self.cache_hits = 0
        self.cache_misses = 0
        env_mode = os.environ.get("LLM_MODE", "replay").lower()
        if allow_network is not None:
            self.allow_network = allow_network
        else:
            self.allow_network = inner is not None and env_mode != "replay"

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        key = _message_hash(messages)
        cached = self._path(key)
        if cached.exists():
            self.last_cache_hit = True
            self.cache_hits += 1
            data = json.loads(cached.read_text("utf-8"))
            return LLMResponse(**data)

        self.last_cache_hit = False
        self.cache_misses += 1

        if not self.allow_network or self.inner is None:
            raise FileNotFoundError(f"Replay cache miss: {key} (replay mode cannot reach network)")

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
