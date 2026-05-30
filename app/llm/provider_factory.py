"""Build configured LLM providers for planning."""

from __future__ import annotations

from collections.abc import Iterable

from app.config import AppConfig
from app.llm.base import LLMMissingKeyError, LLMProvider
from app.llm.cerebras_provider import CerebrasProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.groq_provider import GroqProvider
from app.llm.openrouter_provider import OpenRouterProvider


LLM_PROVIDER_ORDER = ("groq", "gemini", "openrouter", "cerebras")


def build_llm_providers(config: AppConfig, requested_provider: str) -> tuple[list[LLMProvider], list[str]]:
    """Create providers in the requested order, skipping missing keys for auto mode."""

    requested = (requested_provider or "auto").strip().lower()
    if requested not in (*LLM_PROVIDER_ORDER, "auto"):
        raise ValueError(
            "--llm-provider must be one of: auto, groq, gemini, openrouter, cerebras."
        )

    provider_names: Iterable[str] = LLM_PROVIDER_ORDER if requested == "auto" else (requested,)
    providers: list[LLMProvider] = []
    warnings: list[str] = []

    for name in provider_names:
        try:
            providers.append(_build_one_provider(config, name))
        except LLMMissingKeyError as exc:
            if requested == "auto":
                warnings.append(f"Skipping {name}: {exc}")
                continue
            raise

    if not providers:
        raise ValueError(
            "No LLM providers are available. Add at least one API key to .env, "
            "or choose a configured provider with --llm-provider."
        )

    return providers, warnings


def _build_one_provider(config: AppConfig, name: str) -> LLMProvider:
    if name == "groq":
        return GroqProvider(api_key=config.groq_api_key or "", model=config.groq_model)
    if name == "gemini":
        return GeminiProvider(api_key=config.gemini_api_key or "", model=config.gemini_model)
    if name == "openrouter":
        return OpenRouterProvider(
            api_key=config.openrouter_api_key or "",
            model=config.openrouter_model,
            http_referer=config.openrouter_http_referer,
            x_title=config.openrouter_x_title,
        )
    if name == "cerebras":
        return CerebrasProvider(api_key=config.cerebras_api_key or "", model=config.cerebras_model)
    raise ValueError(f"Unknown LLM provider: {name}")
