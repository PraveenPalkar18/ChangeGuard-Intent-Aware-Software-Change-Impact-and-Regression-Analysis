"""AI Intent Analysis package."""
from backend.app.intent.models import (
    IntentClassification,
    PRContext,
    HunkContext,
    HunkIntentResult,
    PRIntentReport,
)
from backend.app.intent.provider_interface import AIModelProvider
from backend.app.intent.analyzer_interface import BaseIntentAnalyzer
from backend.app.intent.intent_analyzer import IntentAnalyzer
from backend.app.intent.factory import create_model_provider, FallbackModelProvider
from backend.app.intent.providers.mock_provider import MockAIProvider
from backend.app.intent.providers.tfidf_provider import TFIDFSimilarityProvider
from backend.app.intent.providers.codebert_provider import (
    CodeBERTSimilarityProvider,
    ModelNotAvailableException,
)

__all__ = [
    "IntentClassification",
    "PRContext",
    "HunkContext",
    "HunkIntentResult",
    "PRIntentReport",
    "AIModelProvider",
    "BaseIntentAnalyzer",
    "IntentAnalyzer",
    "create_model_provider",
    "FallbackModelProvider",
    "MockAIProvider",
    "TFIDFSimilarityProvider",
    "CodeBERTSimilarityProvider",
    "ModelNotAvailableException",
]
