"""Application settings loaded from environment variables and an optional .env file."""

from pathlib import Path
from typing import Any, Literal

from dotenv import find_dotenv
from pydantic import Field, SecretStr, field_validator
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

    # Overrides the provider that would be detected from OPENAI_BASE_URL.
    provider: Literal["openai", "openrouter", "anthropic"] | None = None
    openai_api_key: SecretStr = Field(validation_alias="OPENAI_API_KEY")

    @field_validator("provider", mode="before")
    @classmethod
    def _lowercase_provider(cls, value: Any) -> Any:
        return value.lower() if isinstance(value, str) else value

    base_url: str | None = Field(None, validation_alias="OPENAI_BASE_URL")
    # models https://openrouter.ai/models?fmt=table&order=top-weekly
    model: str = "anthropic/claude-haiku-5.5"
    max_iterations: int = Field(42, gt=0)
    log_file: Path = Path(".agent-cache") / "agent.jsonl"
    sessions_dir: Path = SESSIONS_DIR
    working_dir: Path | None = None
    # Use this MCP config file instead of searching the default locations.
    mcp_config: Path | None = None
