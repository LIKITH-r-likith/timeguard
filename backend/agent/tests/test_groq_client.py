"""Unit tests for GroqClient and TokenPacer in backend.agent.llm.

Verifies request headers, HTTP 429 rate-limiting, 5xx retries, and token pacing with fake clocks.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from email.message import Message
from unittest.mock import MagicMock, patch

import pytest

from backend.agent.llm import GroqClient, TokenPacer, parse_retry_delay


class FakeClock:
    """Deterministic simulated clock for rate-limit and pacing tests."""

    def __init__(self, current_time: float = 100.0) -> None:
        self.current = current_time
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


def test_groq_client_headers_with_mocked_urlopen() -> None:
    """Verify GroqClient adds User-Agent: timeguard/1.0 and Accept: application/json."""
    client = GroqClient(api_key="test-api-key", max_retries=0)
    mock_payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action": "ADD_PUNCH", "confidence": 0.9, "rationale": "test"}',
                    "tool_calls": [],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    raw_response = json.dumps(mock_payload).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = raw_response
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    captured_requests: list[urllib.request.Request] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30.0):
        captured_requests.append(req)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        resp = client.complete(messages=[{"role": "user", "content": "Hello"}])

    assert resp.text.startswith('{"action"')
    assert len(captured_requests) == 1
    req = captured_requests[0]

    assert req.get_header("User-agent") == "timeguard/1.0"
    assert req.get_header("Accept") == "application/json"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Authorization") == "Bearer test-api-key"


def test_groq_client_includes_http_error_body_in_exception() -> None:
    """Verify HTTP error response body is included in the raised error message."""
    client = GroqClient(api_key="test-api-key", max_retries=0)
    error_body = b'{"error": {"message": "Invalid model parameter", "type": "invalid_request_error"}}'

    http_error = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/chat/completions",
        code=400,
        msg="Bad Request",
        hdrs=Message(),
        fp=io.BytesIO(error_body),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(ConnectionError) as exc_info:
            client.complete(messages=[{"role": "user", "content": "Hello"}])

    err_str = str(exc_info.value)
    assert "Invalid model parameter" in err_str
    assert "400" in err_str


def test_groq_client_429_retry_from_body_with_fake_clock() -> None:
    """On HTTP 429, parse delay from body, sleep delay + 1s, and succeed on retry."""
    clock = FakeClock(100.0)
    pacer = TokenPacer(tpm_limit=10000, time_fn=clock.time, sleep_fn=clock.sleep)
    client = GroqClient(api_key="test-key", max_retries=8, pacer=pacer)

    body_429 = b'{"error": {"message": "Rate limit reached. Please try again in 1.5s."}}'
    http_429 = urllib.error.HTTPError(
        url="https://api.groq.com",
        code=429,
        msg="Too Many Requests",
        hdrs=Message(),
        fp=io.BytesIO(body_429),
    )

    ok_payload = {
        "choices": [{"message": {"content": '{"action": "ADD_PUNCH"}'}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25},
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(ok_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    calls = 0

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30.0):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise http_429
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=clock.sleep):
            resp = client.complete(messages=[{"role": "user", "content": "Test"}])

    assert calls == 2
    assert resp.text == '{"action": "ADD_PUNCH"}'
    # 1.5s parsed from body + 1s extra = 2.5s slept
    assert 2.5 in clock.sleep_calls


def test_groq_client_429_retry_from_header_with_fake_clock() -> None:
    """On HTTP 429 with Retry-After header, sleep header + 1s."""
    clock = FakeClock(100.0)
    pacer = TokenPacer(tpm_limit=10000, time_fn=clock.time, sleep_fn=clock.sleep)
    client = GroqClient(api_key="test-key", max_retries=8, pacer=pacer)

    hdrs = Message()
    hdrs["Retry-After"] = "3"
    http_429 = urllib.error.HTTPError(
        url="https://api.groq.com",
        code=429,
        msg="Too Many Requests",
        hdrs=hdrs,
        fp=io.BytesIO(b'{"error": "Rate limit reached"}'),
    )

    ok_payload = {
        "choices": [{"message": {"content": '{"action": "RESOLVE"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(ok_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    calls = 0

    def fake_urlopen(req, timeout=30.0):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise http_429
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=clock.sleep):
            resp = client.complete(messages=[{"role": "user", "content": "Test"}])

    assert calls == 2
    assert resp.text == '{"action": "RESOLVE"}'
    # 3s from header + 1s = 4.0s slept
    assert 4.0 in clock.sleep_calls


def test_groq_client_5xx_retry() -> None:
    """Verify GroqClient retries on HTTP 503 and succeeds on subsequent attempt."""
    clock = FakeClock(100.0)
    pacer = TokenPacer(tpm_limit=10000, time_fn=clock.time, sleep_fn=clock.sleep)
    client = GroqClient(api_key="test-key", max_retries=8, pacer=pacer)

    http_503 = urllib.error.HTTPError(
        url="https://api.groq.com",
        code=503,
        msg="Service Unavailable",
        hdrs=Message(),
        fp=io.BytesIO(b"Service overloaded"),
    )

    ok_payload = {
        "choices": [{"message": {"content": '{"action": "ADD_PUNCH"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(ok_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    calls = 0

    def fake_urlopen(req, timeout=30.0):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise http_503
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=clock.sleep):
            resp = client.complete(messages=[{"role": "user", "content": "Test"}])

    assert calls == 2
    assert resp.text == '{"action": "ADD_PUNCH"}'


def test_token_pacer_sliding_window_with_fake_clock() -> None:
    """Verify TokenPacer sleeps before call when TPM limit would be exceeded."""
    clock = FakeClock(100.0)
    pacer = TokenPacer(tpm_limit=6000, window_seconds=60.0, time_fn=clock.time, sleep_fn=clock.sleep)

    # Call 1 at t=100: uses 4000 tokens. Est 500 -> 0 + 500 <= 6000, no sleep
    slept = pacer.pace(500)
    assert slept == 0.0
    pacer.record(4000)

    # Call 2 at t=115: wants 3000 tokens. 4000 + 3000 = 7000 > 6000.
    clock.current = 115.0
    slept = pacer.pace(3000)

    # Must sleep until call 1 expires at t = 100 + 60 = 160.
    # Sleep needed = 160 - 115 = 45.0s
    assert slept == 45.0
    assert clock.current == 160.0
    assert len(pacer.history) == 0  # old record expired and purged


def test_parse_retry_delay_formats() -> None:
    """Verify parse_retry_delay handles various units and formats."""
    assert parse_retry_delay("try again in 450ms") == 0.45
    assert parse_retry_delay("Please try again in 2.34s.") == 2.34
    assert parse_retry_delay("try again in 1m20s") == 80.0
    assert parse_retry_delay("try again in 2 minutes") == 120.0
    assert parse_retry_delay("limit reached", retry_after_header="5") == 5.0


def test_groq_client_unwraps_tool_use_failed_wrapper() -> None:
    """On HTTP 400 with code tool_use_failed, unwrap failed_generation wrapper."""
    client = GroqClient(api_key="test-key", max_retries=0)
    failed_payload = {
        "error": {
            "message": "Failed to call a function. See failed_generation.",
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "failed_generation": json.dumps({
                "name": "json",
                "arguments": {
                    "exception_id": "exc_1",
                    "action": "ADD_PUNCH",
                    "confidence": 0.95,
                    "rationale": "Unwrapped from wrapper",
                },
            }),
        }
    }
    http_400 = urllib.error.HTTPError(
        url="https://api.groq.com",
        code=400,
        msg="Bad Request",
        hdrs=Message(),
        fp=io.BytesIO(json.dumps(failed_payload).encode("utf-8")),
    )

    with patch("urllib.request.urlopen", side_effect=http_400):
        resp = client.complete(messages=[{"role": "user", "content": "Test"}])

    data = json.loads(resp.text)
    assert data["action"] == "ADD_PUNCH"
    assert data["rationale"] == "Unwrapped from wrapper"


def test_groq_client_unwraps_tool_use_failed_direct_json() -> None:
    """On HTTP 400 with code tool_use_failed, unwrap direct JSON string in failed_generation."""
    client = GroqClient(api_key="test-key", max_retries=0)
    failed_payload = {
        "error": {
            "message": "Tool use failed.",
            "code": "tool_use_failed",
            "failed_generation": json.dumps({
                "exception_id": "exc_2",
                "action": "FLAG_OVERTIME_FOR_APPROVAL",
                "confidence": 0.88,
            }),
        }
    }
    http_400 = urllib.error.HTTPError(
        url="https://api.groq.com",
        code=400,
        msg="Bad Request",
        hdrs=Message(),
        fp=io.BytesIO(json.dumps(failed_payload).encode("utf-8")),
    )

    with patch("urllib.request.urlopen", side_effect=http_400):
        resp = client.complete(messages=[{"role": "user", "content": "Test"}])

    data = json.loads(resp.text)
    assert data["action"] == "FLAG_OVERTIME_FOR_APPROVAL"
    assert data["confidence"] == 0.88

