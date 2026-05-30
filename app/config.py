"""Runtime configuration for the local carousel generator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_ROOT = PROJECT_ROOT / "outputs" / "posts"


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    outputs_root: Path
    groq_api_key: str | None
    groq_model: str
    gemini_api_key: str | None
    gemini_model: str
    openrouter_api_key: str | None
    openrouter_model: str
    openrouter_http_referer: str | None
    openrouter_x_title: str | None
    cerebras_api_key: str | None
    cerebras_model: str
    default_llm_provider: str
    pollinations_rate_limit_seconds: float
    warnings: list[str]


def _read_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def load_config() -> AppConfig:
    """Load configuration from .env and environment variables."""

    env_path = PROJECT_ROOT / ".env"
    warnings: list[str] = []
    if env_path.exists():
        load_dotenv(env_path)
    else:
        warnings.append("Missing .env file. Create one from .env.example before using LLM providers.")

    return AppConfig(
        project_root=PROJECT_ROOT,
        outputs_root=OUTPUTS_ROOT,
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        openrouter_http_referer=os.getenv("OPENROUTER_HTTP_REFERER"),
        openrouter_x_title=os.getenv("OPENROUTER_X_TITLE"),
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        cerebras_model=os.getenv("CEREBRAS_MODEL", "llama3.1-8b"),
        default_llm_provider=os.getenv("DEFAULT_LLM_PROVIDER", "auto").strip().lower() or "auto",
        pollinations_rate_limit_seconds=_read_float_env("POLLINATIONS_RATE_LIMIT_SECONDS", 15.0),
        warnings=warnings,
    )
