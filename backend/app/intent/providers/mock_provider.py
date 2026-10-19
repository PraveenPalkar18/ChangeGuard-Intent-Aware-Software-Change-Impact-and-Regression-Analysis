"""Deterministic Mock AI Model Provider for offline and test environments."""
import re
from typing import Dict, Any, Set
from backend.app.intent.provider_interface import AIModelProvider


class MockAIProvider(AIModelProvider):
    """Deterministic token-overlap based mock provider for testing."""

    def __init__(self, model_name: str = "mock-jaccard-v1"):
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate normalized Jaccard word-level similarity."""
        tokens_a = self._tokenize(text_a)
        tokens_b = self._tokenize(text_b)

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)

        if not union:
            return 0.0

        return round(len(intersection) / len(union), 4)

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "type": "heuristic-jaccard",
            "hardware_requirements": "None (CPU minimal)",
            "approximate_cost": "0.00",
            "context_window": "unlimited",
            "limitations": [
                "Does not capture semantic synonyms",
                "Strict lexical token matching only",
            ],
        }

    def _tokenize(self, text: str) -> Set[str]:
        """Normalize and tokenize text into lowercase alphanumeric tokens."""
        if not text:
            return set()
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        # Filter single character tokens and common stop words
        stops = {"the", "a", "an", "and", "or", "in", "on", "of", "to", "for", "is", "it", "this", "that"}
        return {w for w in words if len(w) > 1 and w not in stops}
