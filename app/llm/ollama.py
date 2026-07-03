from __future__ import annotations

import httpx

from app.llm.base import LLMClient, LLMError


class OllamaClient(LLMClient):
    def __init__(self, *, base_url: str, model: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate_json(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError("Ollama request failed.") from exc

        payload = response.json()
        text = payload.get("response")
        if not isinstance(text, str) or text.strip() == "":
            raise LLMError("Ollama returned an empty response.")
        return text
