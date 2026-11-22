from pathlib import Path

import pytest
import requests
import yaml
from click.testing import CliRunner

from agent import cli
from agent.provider import (
    ModelInfo,
    detect_provider,
    fetch_model_info,
    resolve_provider,
)


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://openrouter.ai/api/v1", "openrouter"),
        ("https://eu.openrouter.ai/api/v1", "openrouter"),
        ("https://api.anthropic.com/v1/", "anthropic"),
        ("https://api.openai.com/v1", "openai"),
        ("http://localhost:8000/v1", "openai"),
        ("https://openrouter.ai.evil.com/api/v1", "openai"),
        ("https://evil.com/openrouter.ai", "openai"),
        (None, "openai"),
    ],
)
def test_detect_provider_uses_hostname(base_url, expected):
    assert detect_provider(base_url) == expected


def test_configured_provider_overrides_detection():
    assert resolve_provider("openai", "https://openrouter.ai/api/v1") == "openai"
    assert resolve_provider(None, "https://openrouter.ai/api/v1") == "openrouter"


def test_openrouter_lookup_reads_context_and_prices_per_million(monkeypatch):
    captured = {}

    def fake_get(url, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse(
            {
                "data": {
                    "context_length": 200_000,
                    "pricing": {"prompt": "0.000001", "completion": "0.000005"},
                }
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    info = fetch_model_info("openrouter", "anthropic/claude-haiku-5.5", "key")

    assert captured["url"] == (
        "https://openrouter.ai/api/v1/model/anthropic/claude-haiku-5.5"
    )
    assert captured["headers"] == {"Authorization": "Bearer key"}
    assert captured["timeout"] == 5
    assert info.context_window == 200_000
    assert info.input_price_per_1m == pytest.approx(1.0)
    assert info.output_price_per_1m == pytest.approx(5.0)


def test_anthropic_lookup_reads_max_input_tokens(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, headers, timeout: FakeResponse({"max_input_tokens": 1_000_000}),
    )

    info = fetch_model_info("anthropic", "claude-haiku-5-5", "key")

    assert info == ModelInfo(context_window=1_000_000)


@pytest.mark.parametrize(
    "payload",
    [{"max_input_tokens": 0}, {"max_input_tokens": None}, {}],
)
def test_anthropic_unknown_window_is_zero(monkeypatch, payload):
    monkeypatch.setattr(
        requests, "get", lambda url, headers, timeout: FakeResponse(payload)
    )

    assert fetch_model_info("anthropic", "m", "key") == ModelInfo()


def test_openrouter_null_context_and_pricing_are_zero(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, headers, timeout: FakeResponse(
            {"data": {"context_length": None, "pricing": None}}
        ),
    )

    assert fetch_model_info("openrouter", "m", "key") == ModelInfo()


@pytest.mark.parametrize("failure", ["timeout", "connection", "status", "bad-json"])
def test_lookup_failures_return_zeros(monkeypatch, failure):
    def fake_get(url, headers, timeout):
        if failure == "timeout":
            raise requests.Timeout("slow")
        if failure == "connection":
            raise requests.ConnectionError("down")
        if failure == "status":
            return FakeResponse(status=500)
        return FakeResponse({"unexpected": True})

    monkeypatch.setattr(requests, "get", fake_get)

    assert fetch_model_info("openrouter", "m", "key") == ModelInfo()


def test_openai_makes_no_request(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no lookup expected for openai")

    monkeypatch.setattr(requests, "get", fail)

    assert fetch_model_info("openai", "gpt-x", "key") == ModelInfo()


def test_config_dump_is_yaml_and_hides_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)
    monkeypatch.setattr(
        cli,
        "fetch_model_info",
        lambda provider, model, key: ModelInfo(
            context_window=200_000, input_price_per_1m=1.0, output_price_per_1m=5.0
        ),
    )
    monkeypatch.setattr(cli, "_run_repl", lambda *args: None)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0, result.output
    assert "super-secret-key" not in result.output
    # The YAML block starts at "settings:" and ends at the first blank line.
    dump = result.output.split("settings:\n", 1)[1].split("\n\n", 1)[0]
    parsed = yaml.safe_load("settings:\n" + dump)
    assert parsed["settings"]["openai_api_key"] == "**********"
    assert parsed["model"] == {
        "provider": "openrouter",
        "context_window": 200_000,
        "input_price_per_1m": 1.0,
        "output_price_per_1m": 5.0,
    }
