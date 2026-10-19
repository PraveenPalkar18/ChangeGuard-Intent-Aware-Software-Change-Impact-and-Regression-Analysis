"""Abstract AI Model Provider interface."""
from abc import ABC, abstractmethod
from typing import Dict, Any


class AIModelProvider(ABC):
    """Abstract interface for AI model providers calculating intent-to-code similarity."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier for the provider (e.g. 'tfidf', 'transformers', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name or checkpoint of the model (e.g. 'tfidf-baseline', 'codebert-base')."""
        pass

    @abstractmethod
    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Compute similarity between two text strings in range [0.0, 1.0].

        Args:
            text_a: Typically the PR intent text.
            text_b: Typically the code hunk representation.

        Returns:
            Normalized similarity score between 0.0 and 1.0.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return provider and model metadata, hardware requirements, and limits."""
        pass
