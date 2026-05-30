"""Google Gemini REST provider for carousel planning."""

from __future__ import annotations

import requests

from app.llm.base import (
    LLMInvalidResponseError,
    LLMMissingKeyError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 90) -> None:
        if not api_key:
            raise LLMMissingKeyError("Missing GEMINI_API_KEY. Add it to auto_carousel/.env.")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

    def generate_json(self, prompt: str) -> str:
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "You are a precise content planning engine. "
                                "Return only valid JSON and never markdown.\n\n"
                                f"{prompt}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "response_mime_type": "application/json",
            },
        }
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                self.endpoint,
                params=params,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise LLMProviderError(
                "Gemini request failed before receiving a response."
            ) from exc

        if response.status_code == 429:
            raise LLMRateLimitError("Gemini rate limit hit: HTTP 429 Too Many Requests.")

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise LLMProviderError(f"Gemini HTTP error {response.status_code}: {response.text[:500]}") from exc

        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("Gemini returned an invalid response shape.") from exc

        if not text.strip():
            raise LLMInvalidResponseError("Gemini returned an empty response.")
        return text
