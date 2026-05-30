"""Base interfaces for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot return usable text."""


class LLMMissingKeyError(LLMProviderError):
    """Raised when a provider is configured without its API key."""


class LLMRateLimitError(LLMProviderError):
    """Raised when a provider reports a rate limit."""


class LLMInvalidResponseError(LLMProviderError):
    """Raised when a provider response shape is not usable."""


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate_json(self, prompt: str) -> str:
        """Generate raw JSON text from a prompt."""

    def generate(self, prompt: str) -> str:
        """Backward-compatible alias for older planner code."""

        return self.generate_json(prompt)
