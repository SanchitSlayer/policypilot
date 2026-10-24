"""Provider factory: the only place that knows which class serves which provider name."""

from functools import lru_cache
from typing import Literal, get_args

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider, ProviderNotConfiguredError

ProviderName = Literal["openai", "anthropic", "gemini", "fake"]
PROVIDER_NAMES: tuple[str, ...] = get_args(ProviderName)


def _require(value: str | None, env_var: str, provider: str) -> str:
    if not value:
        raise ProviderNotConfiguredError(
            f"Provider '{provider}' is not configured: set {env_var} in the environment."
        )
    return value


def build_provider(name: str, settings: Settings) -> LLMProvider:
    common = {"max_tokens": settings.llm_max_output_tokens, "timeout": settings.llm_timeout_seconds}
    if name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=_require(settings.openai_api_key, "OPENAI_API_KEY", name),
            model=_require(settings.openai_chat_model, "OPENAI_CHAT_MODEL", name),
            **common,
        )
    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY", name),
            model=_require(settings.anthropic_chat_model, "ANTHROPIC_CHAT_MODEL", name),
            **common,
        )
    if name == "gemini":
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=_require(settings.gemini_api_key, "GEMINI_API_KEY", name),
            model=_require(settings.gemini_chat_model, "GEMINI_CHAT_MODEL", name),
            **common,
        )
    if name == "fake":
        from app.llm.fake_provider import FakeProvider

        return FakeProvider()
    raise ProviderNotConfiguredError(
        f"Unknown provider '{name}'. Choose one of: {', '.join(PROVIDER_NAMES)}."
    )


@lru_cache
def get_provider(name: str) -> LLMProvider:
    """Return a cached provider instance (SDK clients keep connection pools)."""
    return build_provider(name, get_settings())
