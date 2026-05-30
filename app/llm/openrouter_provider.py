"""OpenRouter API provider for carousel planning."""

from __future__ import annotations

import requests

from app.llm.base import (
    LLMInvalidResponseError,
    LLMMissingKeyError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
)


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        http_referer: str | None = None,
        x_title: str | None = None,
        timeout_seconds: int = 90,
    ) -> None:
        if not api_key:
            raise LLMMissingKeyError("Missing OPENROUTER_API_KEY. Add it to auto_carousel/.env.")
        self.api_key = api_key
        self.model = model
        self.http_referer = http_referer
        self.x_title = x_title
        self.timeout_seconds = timeout_seconds
        self.endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def generate_json(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise content planning engine. "
                        "Return only valid JSON and never markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            headers["X-Title"] = self.x_title

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise LLMProviderError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code == 429:
            raise LLMRateLimitError("OpenRouter rate limit hit: HTTP 429 Too Many Requests.")

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise LLMProviderError(
                f"OpenRouter HTTP error {response.status_code}: {response.text[:500]}"
            ) from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("OpenRouter returned an invalid response shape.") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponseError("OpenRouter returned an empty response.")
        return content
