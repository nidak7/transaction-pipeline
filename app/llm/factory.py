from __future__ import annotations

import logging

from app.core.config import Settings
from app.llm.base import LLMClient, LLMError
from app.llm.gemini import GeminiClient
from app.llm.ollama import OllamaClient

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    def __init__(self, primary: LLMClient, fallback: LLMClient | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def generate_json(self, prompt: str) -> str:
        try:
            return self._primary.generate_json(prompt)
        except LLMError:
            if self._fallback is None:
                raise
            logger.warning("Primary LLM failed, trying fallback.", exc_info=True)
            return self._fallback.generate_json(prompt)


def create_llm_client(settings: Settings) -> LLMClient:
    primary = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.ollama_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    fallback = None
    if settings.gemini_api_key:
        fallback = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return FallbackLLMClient(primary=primary, fallback=fallback)
