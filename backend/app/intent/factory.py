"""AI Model Provider Factory with fallback orchestration."""
import logging
from typing import Optional, Dict, Any
from backend.app.core.config import settings
from backend.app.intent.provider_interface import AIModelProvider
from backend.app.intent.providers.mock_provider import MockAIProvider
from backend.app.intent.providers.tfidf_provider import TFIDFSimilarityProvider
from backend.app.intent.providers.codebert_provider import (
    CodeBERTSimilarityProvider,
    ModelNotAvailableException,
)

logger = logging.getLogger("changeguard.intent.factory")


class FallbackModelProvider(AIModelProvider):
    """Wrapper provider that falls back to a secondary provider if the primary fails."""

    def __init__(self, primary: AIModelProvider, fallback: AIModelProvider):
        self._primary = primary
        self._fallback = fallback
        self._active_provider = primary
        # Eager availability check if primary has an initialization probe
        if hasattr(self._primary, "_ensure_initialized"):
            try:
                self._primary._ensure_initialized()
            except Exception as exc:
                logger.info(
                    f"Primary provider '{self._primary.provider_name}' unavailable ({exc}). "
                    f"Setting active provider to fallback '{self._fallback.provider_name}'."
                )
                self._active_provider = self._fallback

    @property
    def provider_name(self) -> str:
        if self._active_provider == self._fallback:
            return f"{self._fallback.provider_name} [fell back from {self._primary.provider_name}]"
        return self._primary.provider_name

    @property
    def model_name(self) -> str:
        return self._active_provider.model_name

    @property
    def is_fallback_active(self) -> bool:
        return self._active_provider == self._fallback

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        try:
            return self._active_provider.compute_similarity(text_a, text_b)
        except (ModelNotAvailableException, Exception) as exc:
            if self._active_provider != self._fallback:
                logger.warning(
                    f"Primary provider '{self._primary.provider_name}' failed ({exc}). "
                    f"Switching to fallback '{self._fallback.provider_name}'."
                )
                self._active_provider = self._fallback
                return self._fallback.compute_similarity(text_a, text_b)
            raise

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "is_fallback_active": self.is_fallback_active,
            "active_provider": self._active_provider.provider_name,
            "primary": self._primary.get_model_info(),
            "fallback": self._fallback.get_model_info(),
        }


def create_model_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
    fallback_provider_name: Optional[str] = "tfidf",
) -> AIModelProvider:
    """Factory creating an AIModelProvider according to configuration.

    Args:
        provider_name: 'tfidf', 'codebert', or 'mock'. Defaults to settings.AI_PROVIDER.
        model_name: Model identifier or checkpoint name.
        fallback_provider_name: Secondary provider to invoke if primary is unavailable.

    Returns:
        Configured AIModelProvider instance with fallback protection if specified.
    """
    prov_key = (provider_name or settings.AI_PROVIDER).strip().lower()
    if model_name:
        mod_key = model_name
    elif provider_name and provider_name.strip().lower() != settings.AI_PROVIDER.strip().lower():
        mod_key = None
    else:
        mod_key = settings.AI_MODEL

    # Instantiate primary provider
    primary = _instantiate_single_provider(prov_key, mod_key)

    # Wrap in FallbackModelProvider only for heavy/optional providers (e.g. codebert)
    # Never wrap mock or tfidf with a fallback
    if (
        fallback_provider_name
        and fallback_provider_name.strip().lower() != prov_key
        and prov_key not in ("mock", "tfidf")
    ):
        fallback = _instantiate_single_provider(fallback_provider_name.strip().lower(), None)
        return FallbackModelProvider(primary=primary, fallback=fallback)

    return primary


def _instantiate_single_provider(provider_key: str, model_name: Optional[str]) -> AIModelProvider:
    if provider_key == "tfidf":
        return TFIDFSimilarityProvider(model_name=model_name or "tfidf-baseline")
    elif provider_key in ("codebert", "unixcoder", "transformers"):
        return CodeBERTSimilarityProvider(model_name=model_name or "microsoft/codebert-base")
    elif provider_key == "mock":
        return MockAIProvider(model_name=model_name or "mock-jaccard")
    else:
        logger.warning(f"Unknown AI provider '{provider_key}'. Falling back to 'tfidf'.")
        return TFIDFSimilarityProvider(model_name="tfidf-fallback")

