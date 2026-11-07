import pytest
from pydantic import ValidationError

from agent.settings import Settings

ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "AGENT_MODEL",
    "AGENT_MAX_ITERATIONS",
    "AGENT_LOG_FILE",
    "AGENT_SESSIONS_DIR",
    "AGENT_WORKING_DIR",
    "AGENT_OPENAI_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Removes agent-related variables so the host environment can't leak in."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_apply_when_only_api_key_is_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "test-key"
    assert settings.base_url is None
    assert settings.model == "anthropic/claude-haiku-5.5"
    assert settings.max_iterations == 42
    assert settings.log_file.as_posix() == ".agent-cache/agent.jsonl"
    assert settings.sessions_dir.as_posix() == ".agent-cache/sessions"


def test_agent_prefixed_variables_override_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("AGENT_MODEL", "model-x")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "5")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))

    settings = Settings(_env_file=None)

    assert settings.base_url == "http://localhost:8000/v1"
    assert settings.model == "model-x"
    assert settings.max_iterations == 5
    assert settings.log_file == tmp_path / "log.jsonl"
    assert settings.sessions_dir == tmp_path / "sessions"


def test_api_key_is_read_without_agent_prefix(monkeypatch):
    monkeypatch.setenv("AGENT_OPENAI_API_KEY", "ignored-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "test-key"


def test_missing_api_key_raises_validation_error():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_non_positive_max_iterations_is_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_values_load_from_dotenv_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=file-key\nAGENT_MODEL=model-from-file\n", encoding="utf-8"
    )

    settings = Settings(_env_file=env_file)

    assert settings.openai_api_key.get_secret_value() == "file-key"
    assert settings.model == "model-from-file"


def test_working_dir_defaults_to_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.working_dir is None


def test_working_dir_is_read_from_agent_prefixed_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_WORKING_DIR", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.working_dir == tmp_path


def test_api_key_is_hidden_in_repr(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")

    settings = Settings(_env_file=None)

    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)
