from types import SimpleNamespace

import pytest
from openai import NOT_GIVEN

from agent.agent import Agent
from agent.session import Session


def _fake_response(total_tokens: int | None):
    usage = None if total_tokens is None else SimpleNamespace(total_tokens=total_tokens)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"action": "finish", "final_answer": "done"}'
                )
            )
        ],
        usage=usage,
    )


def test_call_llm_records_context_tokens_from_usage(tmp_path, monkeypatch):
    agent = Agent(
        openai_api_key="test-key",
        model="model-a",
        session=Session.create(root=tmp_path),
    )
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(total_tokens=321),
    )

    agent._call_llm("system prompt")

    assert agent.context_tokens == 321


def test_call_llm_keeps_context_tokens_when_usage_is_missing(tmp_path, monkeypatch):
    agent = Agent(
        openai_api_key="test-key",
        model="model-a",
        session=Session.create(root=tmp_path),
    )
    agent.context_tokens = 50
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(total_tokens=None),
    )

    agent._call_llm("system prompt")

    assert agent.context_tokens == 50


def test_clear_context_resets_context_tokens_but_keeps_cost(tmp_path):
    agent = Agent(
        openai_api_key="test-key",
        model="model-a",
        session=Session.create(root=tmp_path),
    )
    agent.context_tokens = 900
    agent.cost = 0.5

    agent.clear_context()

    assert agent.context_tokens == 0
    assert agent.cost == 0.5


def test_call_llm_adds_reported_cost(tmp_path, monkeypatch):
    agent = Agent(
        openai_api_key="test-key",
        model="model-a",
        session=Session.create(root=tmp_path),
    )
    response = _fake_response(total_tokens=10)
    response.usage.cost = 0.25
    monkeypatch.setattr(
        agent.client.chat.completions, "create", lambda **kwargs: response
    )

    agent._call_llm("system prompt")
    agent._call_llm("system prompt")

    assert agent.cost == pytest.approx(0.5)


def test_anthropic_requests_omit_response_format(tmp_path, monkeypatch):
    agent = Agent(
        openai_api_key="test-key",
        model="claude-haiku-5-5",
        session=Session.create(root=tmp_path),
        provider="anthropic",
    )
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return _fake_response(total_tokens=1)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent._call_llm("system prompt")

    assert sent["response_format"] is NOT_GIVEN
