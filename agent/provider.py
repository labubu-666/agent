"""Works out which API provider the agent talks to and looks up what it knows about the model.

Context window and prices come from the provider at startup, not from settings.
Anything the provider can't tell us is 0.
"""

from typing import Literal
from urllib.parse import urlparse

import requests
import structlog
from pydantic import BaseModel

Provider = Literal["openai", "openrouter", "anthropic"]

logger = structlog.get_logger(__name__)

LOOKUP_TIMEOUT_SECONDS = 5
OPENROUTER_MODEL_URL = "https://openrouter.ai/api/v1/model/{model}"
ANTHROPIC_MODEL_URL = "https://api.anthropic.com/v1/models/{model}"
ANTHROPIC_VERSION = "2026-10-21"
PER_MILLION = 1_000_000


class ModelInfo(BaseModel):
    """What the provider reports about the model. 0 means unknown."""

    context_window: int = 0
    input_price_per_1m: float = 0
    output_price_per_1m: float = 0


def detect_provider(base_url: str | None) -> Provider:
    """Picks the provider from the hostname of the base URL. Anything unknown is openai."""
    host = (urlparse(base_url).hostname or "") if base_url else ""
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        return "openrouter"
    if host == "api.anthropic.com":
        return "anthropic"
    return "openai"


def resolve_provider(configured: Provider | None, base_url: str | None) -> Provider:
    """The configured provider wins. Otherwise it is detected from the base URL."""
    return configured or detect_provider(base_url)


def fetch_model_info(provider: Provider, model: str, api_key: str) -> ModelInfo:
    """Looks up the model's context window and prices. Any failure returns zeros."""
    if provider == "openai":
        return ModelInfo()
    try:
        if provider == "openrouter":
            return _openrouter_model_info(model, api_key)
        return _anthropic_model_info(model, api_key)
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logger.warning(
            "Model lookup failed", provider=provider, model=model, error=str(e)
        )
        return ModelInfo()


def _openrouter_model_info(model: str, api_key: str) -> ModelInfo:
    response = requests.get(
        OPENROUTER_MODEL_URL.format(model=model),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=LOOKUP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()["data"]
    pricing = data.get("pricing") or {}
    return ModelInfo(
        context_window=int(data.get("context_length") or 0),
        input_price_per_1m=float(pricing.get("prompt") or 0) * PER_MILLION,
        output_price_per_1m=float(pricing.get("completion") or 0) * PER_MILLION,
    )


def _anthropic_model_info(model: str, api_key: str) -> ModelInfo:
    response = requests.get(
        ANTHROPIC_MODEL_URL.format(model=model),
        headers={
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": ANTHROPIC_VERSION,
        },
        timeout=LOOKUP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    # The Anthropic docs example returns 0 here, so 0 and null both mean unknown.
    return ModelInfo(context_window=int(response.json().get("max_input_tokens") or 0))
