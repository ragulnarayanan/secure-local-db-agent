"""Tests for the Ollama agent.

Unit tests mock the HTTP layer (fast, deterministic, no Ollama needed). One
integration test hits a real Ollama server and auto-skips when it's unreachable.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import src.agent as agent
from src.agent import DEFAULT_HOST, OllamaAgent, SQLResponse, build_user_prompt
from src.schema import introspect


class FakeResponse:
    """Stand-in for requests.Response covering only what generate_sql uses."""

    def __init__(self, payload: dict, ok: bool = True) -> None:
        self._payload = payload
        self._ok = ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise agent.requests.HTTPError("simulated HTTP error")

    def json(self) -> dict:
        return self._payload


def _chat_payload(content: str) -> dict:
    """Shape Ollama's /api/chat returns: the model's text lives in message.content."""
    return {"message": {"role": "assistant", "content": content}}


# ---- unit tests (mocked transport) ----------------------------------------


def test_build_user_prompt_orders_schema_then_question() -> None:
    prompt = build_user_prompt("Table t: id INTEGER PK", "how many rows?")
    assert prompt.index("Table t") < prompt.index("how many rows?")
    assert "Schema:" in prompt


def test_generate_sql_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    content = '{"sql": "SELECT COUNT(*) FROM Track", "reasoning": "count rows"}'
    monkeypatch.setattr(
        agent.requests, "post", lambda *a, **k: FakeResponse(_chat_payload(content))
    )

    resp = OllamaAgent(model="fake").generate_sql("schema", "how many tracks?")
    assert isinstance(resp, SQLResponse)
    assert resp.sql == "SELECT COUNT(*) FROM Track"
    assert resp.reasoning == "count rows"


def test_payload_has_json_format_and_zero_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_post(url: str, json: dict, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(_chat_payload('{"sql": "SELECT 1", "reasoning": "x"}'))

    monkeypatch.setattr(agent.requests, "post", fake_post)
    OllamaAgent(model="qwen2.5-coder:7b").generate_sql("MY_SCHEMA", "MY_QUESTION")

    assert captured["url"].endswith("/api/chat")
    body = captured["json"]
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["model"] == "qwen2.5-coder:7b"
    # schema and question both reach the model
    user_msg = body["messages"][-1]["content"]
    assert "MY_SCHEMA" in user_msg and "MY_QUESTION" in user_msg


def test_valid_json_but_wrong_shape_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Parseable JSON, but missing the required `sql` key -> Pydantic rejects it.
    # This is exactly what `format: "json"` alone cannot catch.
    content = '{"reasoning": "no sql field here"}'
    monkeypatch.setattr(
        agent.requests, "post", lambda *a, **k: FakeResponse(_chat_payload(content))
    )
    with pytest.raises(ValidationError):
        OllamaAgent(model="fake").generate_sql("schema", "q")


def test_http_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent.requests, "post", lambda *a, **k: FakeResponse({}, ok=False)
    )
    with pytest.raises(agent.requests.HTTPError):
        OllamaAgent(model="fake").generate_sql("schema", "q")


# ---- integration test (real Ollama, auto-skips) ---------------------------


@pytest.fixture
def ollama_available() -> None:
    try:
        agent.requests.get(f"{DEFAULT_HOST}/api/tags", timeout=2)
    except agent.requests.RequestException:
        pytest.skip("Ollama not reachable on localhost:11434")


@pytest.mark.integration
def test_real_model_returns_select(ollama_available: None) -> None:
    schema = introspect("data/chinook.db").to_prompt()
    resp = OllamaAgent(model="qwen2.5-coder:7b").generate_sql(
        schema, "How many tracks are in the database?"
    )
    assert isinstance(resp, SQLResponse)
    assert "select" in resp.sql.lower()
