"""Automated Test Suite for Groq Free-Tier AI API Intent Checking in ChangeGuard."""
import json
import pytest
from unittest.mock import MagicMock, patch

from backend.app.core.config import settings
from backend.app.intent.models import (
    PRContext,
    HunkContext,
    IntentClassification,
    UncertaintyLevel,
    SemanticHunkAssessment,
)
from backend.app.preprocessing.models import DiffHunk, DiffLine, DiffLineType
from backend.app.repository.models import CodeEntity, CodeEntityType
from backend.app.intent.semantic_engine import (
    GroqSemanticEngine,
    DeterministicSemanticEngine,
    create_semantic_engine,
    redact_sensitive_tokens,
    _global_semantic_cache,
)
from backend.app.intent.intent_analyzer import IntentAnalyzer


@pytest.fixture
def sample_pr_and_hunk():
    pr_ctx = PRContext(
        pr_title="fix: normalize product names in input validation",
        pr_description="Normalize product names by stripping whitespace and rejecting empty strings."
    )
    diff_lines = [
        DiffLine(line_type=DiffLineType.DELETED, content="return {'name': name}", old_line_number=5),
        DiffLine(line_type=DiffLineType.ADDED, content="cleaned = name.strip()", new_line_number=5),
        DiffLine(line_type=DiffLineType.ADDED, content="return {'name': cleaned}", new_line_number=6),
    ]
    hunk = DiffHunk(
        header="@@ -5,1 +5,2 @@",
        old_start_line=5,
        old_line_count=1,
        new_start_line=5,
        new_line_count=2,
        lines=diff_lines,
    )
    entity = CodeEntity(
        id="func:create_product",
        name="create_product",
        entity_type=CodeEntityType.FUNCTION,
        file_path="services/product_service.py",
        start_line=1,
        end_line=20,
    )
    hunk_ctx = HunkContext(
        file_path="services/product_service.py",
        hunk_index=0,
        hunk=hunk,
        enclosing_entity=entity,
    )
    return pr_ctx, hunk_ctx


# ==============================================================================
# 1. UNIT TESTS: Configuration & Redaction
# ==============================================================================

def test_groq_engine_configuration():
    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_fake_test_key_12345678901234567890",
        timeout_seconds=20,
        max_output_tokens=1024,
        fallback_enabled=True,
    )
    assert engine.provider_type == "groq"
    assert engine.model_name == "llama-3.3-70b-versatile"
    assert engine.is_configured is True
    assert engine._timeout_seconds == 20
    assert engine._max_output_tokens == 1024
    assert engine._fallback_enabled is True


def test_groq_engine_unconfigured_detection():
    engine = GroqSemanticEngine(api_key="")
    assert engine.is_configured is False


def test_redact_sensitive_tokens_with_groq_key():
    raw_text = (
        "Groq key: gsk_1234567890abcdefghijklmnopqrstuvwxyz and "
        "Google key: AIzaSyD1234567890123456789012345678901 and "
        "GitHub token: ghp_123456789012345678901234567890123456"
    )
    sanitized = redact_sensitive_tokens(raw_text)
    assert "gsk_" not in sanitized
    assert "AIza" not in sanitized
    assert "ghp_" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


# ==============================================================================
# 2. UNIT TESTS: Mocked Groq Responses & Classifications
# ==============================================================================

def test_groq_mock_successful_response_explained(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "classification": "EXPLAINED",
        "confidence": 0.95,
        "uncertainty_level": "LOW",
        "apparent_purpose": "Product name stripping",
        "reason": "Directly implements whitespace stripping mentioned in PR description.",
        "evidence": ["name.strip() added", "cleaned dict return"],
        "contradiction_signals": [],
        "missing_context": [],
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_fake_key_12345678901234567890",
        fallback_enabled=True,
    )
    engine._client = mock_client

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.45)

    assert assessment.classification == IntentClassification.EXPLAINED
    assert assessment.confidence == 0.95
    assert assessment.uncertainty_level == UncertaintyLevel.LOW
    assert "strip" in assessment.apparent_purpose.lower()
    assert assessment.provider_type == "groq (llama-3.3-70b-versatile)"
    assert len(assessment.evidence) == 2


@pytest.mark.parametrize("raw_class, expected_enum", [
    ("EXPLAINED", IntentClassification.EXPLAINED),
    ("ALIGNED", IntentClassification.EXPLAINED),
    ("UNEXPLAINED", IntentClassification.UNEXPLAINED),
    ("UNRELATED", IntentClassification.UNEXPLAINED),
    ("CONTRADICTORY", IntentClassification.CONTRADICTORY),
    ("UNCERTAIN", IntentClassification.UNCERTAIN),
    ("PARTIAL", IntentClassification.UNCERTAIN),
    ("UNKNOWN_GARBAGE", IntentClassification.UNCERTAIN),
])
def test_groq_mock_classification_mappings(sample_pr_and_hunk, raw_class, expected_enum):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "classification": raw_class,
        "confidence": 0.88,
        "uncertainty_level": "MEDIUM",
        "apparent_purpose": "Test modification",
        "reason": "Test evaluation",
        "evidence": ["Evidence 1"],
        "contradiction_signals": [],
        "missing_context": [],
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_fake_key_12345678901234567890",
        fallback_enabled=True,
    )
    engine._client = mock_client

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.30)
    assert assessment.classification == expected_enum


# ==============================================================================
# 3. UNIT TESTS: Error Handling & Deterministic Fallback
# ==============================================================================

def test_groq_unconfigured_fallback(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk
    engine = GroqSemanticEngine(api_key="", fallback_enabled=True)

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.35)

    assert assessment.provider_type == "groq_fallback (unconfigured)"
    assert any("not configured" in mc for mc in assessment.missing_context)
    assert assessment.classification in (IntentClassification.EXPLAINED, IntentClassification.UNEXPLAINED, IntentClassification.UNCERTAIN)


def test_groq_unconfigured_raises_when_fallback_disabled(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk
    engine = GroqSemanticEngine(api_key="", fallback_enabled=False)

    with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
        engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.35)


def test_groq_api_error_triggers_fallback(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized: Invalid API Key")

    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_invalid_test_key_1234567890",
        fallback_enabled=True,
    )
    engine._client = mock_client

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.35)

    assert assessment.provider_type == "groq_fallback (error)"
    assert any("Groq API invocation failed" in mc for mc in assessment.missing_context)
    # Ensure raw API key was not leaked into missing context
    for mc in assessment.missing_context:
        assert "gsk_invalid_test_key_1234567890" not in mc


def test_groq_rate_limit_error_triggers_fallback(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("429 Rate limit exceeded. Please wait.")

    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_fake_key_1234567890",
        fallback_enabled=True,
    )
    engine._client = mock_client

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.35)
    assert assessment.provider_type == "groq_fallback (error)"
    assert any("429" in mc for mc in assessment.missing_context)


def test_groq_malformed_json_fallback(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "I cannot evaluate this diff because I am an AI model and not outputting JSON."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_fake_key_1234567890",
        fallback_enabled=True,
    )
    engine._client = mock_client

    assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.35)
    assert assessment.provider_type == "groq_fallback (error)"


# ==============================================================================
# 4. INTEGRATION TESTS: Factory & IntentAnalyzer Pipeline
# ==============================================================================

def test_create_semantic_engine_factory():
    engine = create_semantic_engine(provider_name="groq", model_name="llama-3.3-70b-versatile")
    assert isinstance(engine, GroqSemanticEngine)
    assert engine.provider_type == "groq"
    assert engine.model_name == "llama-3.3-70b-versatile"


def test_intent_analyzer_with_groq_provider(sample_pr_and_hunk):
    pr_ctx, hunk_ctx = sample_pr_and_hunk

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "classification": "EXPLAINED",
        "confidence": 0.92,
        "uncertainty_level": "LOW",
        "apparent_purpose": "Whitespace normalization",
        "reason": "Matches PR title and intent.",
        "evidence": ["name.strip() added"],
        "contradiction_signals": [],
        "missing_context": [],
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    groq_engine = GroqSemanticEngine(
        model_name="llama-3.3-70b-versatile",
        api_key="gsk_test_key_1234567890",
        fallback_enabled=True,
    )
    groq_engine._client = mock_client

    analyzer = IntentAnalyzer(
        provider_name="tfidf",
        semantic_engine=groq_engine,
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)

    assert result.classification == IntentClassification.EXPLAINED
    assert result.confidence == 0.92
    assert "groq" in result.provider_used
    assert result.raw_details["semantic_model"] == "llama-3.3-70b-versatile"
    assert result.raw_details["semantic_provider"] == "groq"
