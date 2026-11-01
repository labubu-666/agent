"""Application settings loaded from environment variables and an optional .env file."""

from pathlib import Path

from dotenv import find_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .session import SESSIONS_DIR


class Settings(BaseSettings):
    """
    Reads `OPENAI_API_KEY` and `OPENAI_BASE_URL` as-is. Every other field uses the `AGENT_` prefix,
    e.g. `AGENT_MODEL` or `AGENT_MAX_ITERATIONS`.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=find_dotenv(usecwd=True) or None,
        env_file_encoding="utf-8",
        extra="ignore",
        validate_by_name=True,
    )

    openai_api_key: SecretStr = Field(validation_alias="OPENAI_API_KEY")
    base_url: str | None = Field(None, validation_alias="OPENAI_BASE_URL")
    # models https://openrouter.ai/models?fmt=table&order=top-weekly
    model: str = "anthropic/claude-haiku-5.5"
    max_iterations: int = Field(21, gt=0)
    log_file: Path = Path(".agent-cache") / "agent.jsonl"
    sessions_dir: Path = SESSIONS_DIR
    working_dir: Path | None = None
