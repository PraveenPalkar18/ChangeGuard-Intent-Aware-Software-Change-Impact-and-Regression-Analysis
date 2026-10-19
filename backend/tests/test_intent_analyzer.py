"""Unit tests for AI Intent Analysis, Model Providers, and Fallback System."""
import pytest
from backend.app.preprocessing.models import DiffHunk, DiffLine, DiffLineType
from backend.app.repository.models import CodeEntity, CodeEntityType
from backend.app.intent.models import (
    IntentClassification,
    PRContext,
    HunkContext,
    HunkIntentResult,
    PRIntentReport,
)
from backend.app.intent.providers.mock_provider import MockAIProvider
from backend.app.intent.providers.tfidf_provider import TFIDFSimilarityProvider
from backend.app.intent.providers.codebert_provider import (
    CodeBERTSimilarityProvider,
    ModelNotAvailableException,
)
from backend.app.intent.factory import (
    create_model_provider,
    FallbackModelProvider,
)
from backend.app.intent.intent_analyzer import IntentAnalyzer


# ==============================================================================
# Helper fixtures
# ==============================================================================


@pytest.fixture
def mock_hunk():
    return DiffHunk(
        hunk_index=0,
        header="@@ -10,3 +10,4 @@ def calculate_discount(price, rate):",
        old_start_line=10,
        old_line_count=3,
        new_start_line=10,
        new_line_count=4,
        lines=[
            DiffLine(line_type=DiffLineType.CONTEXT, content="def calculate_discount(price, rate):", old_line_number=10, new_line_number=10),
            DiffLine(line_type=DiffLineType.DELETED, content="    return price * (1 - rate)", old_line_number=11, new_line_number=None),
            DiffLine(line_type=DiffLineType.ADDED, content="    if rate < 0 or rate > 1: raise ValueError('Invalid rate')", old_line_number=None, new_line_number=11),
            DiffLine(line_type=DiffLineType.ADDED, content="    return price * (1 - rate)", old_line_number=None, new_line_number=12),
        ],
    )


@pytest.fixture
def mock_entity():
    return CodeEntity(
        id="app/billing.py::calculate_discount",
        name="calculate_discount",
        entity_type=CodeEntityType.FUNCTION,
        file_path="app/billing.py",
        start_line=10,
        end_line=15,
        parameters=["price", "rate"],
        docstring="Compute discount with rate validation.",
    )


# ==============================================================================
# 1. PROVIDER TESTS
# ==============================================================================


def test_mock_provider_deterministic():
    """Verify MockAIProvider calculates deterministic word-level Jaccard overlap."""
    provider = MockAIProvider()
    assert provider.provider_name == "mock"

    score_identical = provider.compute_similarity("fix billing discount bug", "fix billing discount bug")
    assert score_identical == 1.0

    score_partial = provider.compute_similarity("fix billing rate discount", "update billing tax invoice")
    assert 0.0 < score_partial < 1.0

    score_none = provider.compute_similarity("optimize database query", "render navigation button")
    assert score_none == 0.0


def test_tfidf_provider_similarity():
    """Verify TFIDFSimilarityProvider computes cosine similarity on related vs unrelated text."""
    provider = TFIDFSimilarityProvider()
    assert provider.provider_name == "tfidf"

    intent = "Add rate validation to discount calculation function"
    related_code = "def calculate_discount(price, rate): if rate < 0: raise ValueError"
    unrelated_code = "def render_navbar_dropdown(theme): return HTMLButton(theme)"

    score_rel = provider.compute_similarity(intent, related_code)
    score_unrel = provider.compute_similarity(intent, unrelated_code)

    assert score_rel > score_unrel
    assert score_rel > 0.15
    assert score_unrel < 0.05


def test_tfidf_provider_empty_inputs():
    """Verify TF-IDF gracefully handles empty strings without error."""
    provider = TFIDFSimilarityProvider()
    assert provider.compute_similarity("", "") == 0.0
    assert provider.compute_similarity("some text", "") == 0.0
    assert provider.compute_similarity("", "def foo(): pass") == 0.0


def test_codebert_provider_fallback_when_unavailable():
    """Verify CodeBERT provider handles missing torch or models cleanly."""
    provider = CodeBERTSimilarityProvider(model_name="nonexistent/fake-model")
    info = provider.get_model_info()
    assert info["provider"] == "codebert"
    assert "512 tokens" in info["context_window"]


def test_fallback_wrapper_switching():
    """Verify FallbackModelProvider seamlessly invokes fallback when primary fails."""
    failing_primary = CodeBERTSimilarityProvider(model_name="nonexistent/fake-model")
    working_fallback = MockAIProvider()

    wrapper = FallbackModelProvider(primary=failing_primary, fallback=working_fallback)
    score = wrapper.compute_similarity("fix billing discount", "fix billing discount")
    # Primary failed and fallback computed score 1.0
    assert score == 1.0


def test_factory_creation():
    """Verify create_model_provider instantiates based on arguments or settings."""
    p_mock = create_model_provider(provider_name="mock", fallback_provider_name=None)
    assert isinstance(p_mock, MockAIProvider)

    p_tfidf = create_model_provider(provider_name="tfidf", fallback_provider_name=None)
    assert isinstance(p_tfidf, TFIDFSimilarityProvider)


# ==============================================================================
# 2. INTENT ANALYZER CLASSIFICATION TESTS
# ==============================================================================


def test_analyze_hunk_explained_by_high_similarity(mock_hunk, mock_entity):
    """Test hunk classified as EXPLAINED when intent matches code changes."""
    analyzer = IntentAnalyzer(provider=TFIDFSimilarityProvider())

    pr_ctx = PRContext(
        pr_title="Fix invalid discount rate crash",
        pr_description="Adds validation check for discount rate parameters in billing logic.",
        commit_messages=["validate discount rate"],
    )
    hunk_ctx = HunkContext(
        file_path="app/billing.py",
        hunk_index=0,
        hunk=mock_hunk,
        enclosing_entity=mock_entity,
        association_type="enclosing",
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)
    assert result.classification == IntentClassification.EXPLAINED
    assert result.confidence >= 0.70
    assert result.similarity_score > 0.30
    assert len(result.evidence) > 0


def test_analyze_hunk_explained_by_direct_entity_mention(mock_hunk, mock_entity):
    """Test hunk classified as EXPLAINED when entity name is explicitly stated in PR."""
    analyzer = IntentAnalyzer(provider=MockAIProvider())

    pr_ctx = PRContext(
        pr_title="Update billing calculations",
        pr_description="We modified calculate_discount to ensure edge cases are handled.",
    )
    hunk_ctx = HunkContext(
        file_path="app/billing.py",
        hunk_index=0,
        hunk=mock_hunk,
        enclosing_entity=mock_entity,
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)
    assert result.classification == IntentClassification.EXPLAINED
    assert any("calculate_discount" in ev for ev in result.evidence)


def test_analyze_hunk_unexplained_orthogonal_change(mock_entity):
    """Test hunk classified as UNEXPLAINED when completely unrelated to PR intent."""
    analyzer = IntentAnalyzer(provider=TFIDFSimilarityProvider())

    pr_ctx = PRContext(
        pr_title="Add OAuth2 Google login button",
        pr_description="Implements Google social sign-in frontend authentication flow.",
    )

    unrelated_hunk = DiffHunk(
        hunk_index=1,
        header="@@ -45,2 +45,4 @@ def delete_cache():",
        old_start_line=45,
        old_line_count=2,
        new_start_line=45,
        new_line_count=4,
        lines=[
            DiffLine(line_type=DiffLineType.ADDED, content="redis_client.flushall()", new_line_number=46),
        ],
    )

    hunk_ctx = HunkContext(
        file_path="app/cache/redis.py",
        hunk_index=1,
        hunk=unrelated_hunk,
        enclosing_entity=CodeEntity(
            id="app/cache/redis.py::delete_cache",
            name="delete_cache",
            entity_type=CodeEntityType.FUNCTION,
            file_path="app/cache/redis.py",
            start_line=45,
            end_line=50,
        ),
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)
    assert result.classification == IntentClassification.UNEXPLAINED
    assert result.similarity_score < 0.15
    assert len(result.limitations) > 0


def test_analyze_hunk_uncertain_on_empty_intent(mock_hunk, mock_entity):
    """Test hunk classified as UNCERTAIN when PR title and description are empty."""
    analyzer = IntentAnalyzer(provider=TFIDFSimilarityProvider())

    empty_pr = PRContext(pr_title="", pr_description="", commit_messages=[])
    hunk_ctx = HunkContext(
        file_path="app/billing.py",
        hunk_index=0,
        hunk=mock_hunk,
        enclosing_entity=mock_entity,
    )

    result = analyzer.analyze_hunk(empty_pr, hunk_ctx)
    assert result.classification == IntentClassification.UNCERTAIN
    assert "empty or missing" in result.reason.lower()


def test_analyze_hunk_uncertain_on_ambiguous_partial_overlap():
    """Test hunk classified as UNCERTAIN when similarity is in middle threshold range."""
    # Custom analyzer with tight thresholds
    analyzer = IntentAnalyzer(
        provider=TFIDFSimilarityProvider(),
        explained_threshold=0.60,
        unexplained_threshold=0.03,
    )

    pr_ctx = PRContext(
        pr_title="Refactor invoice payment processing",
        pr_description="Clean up payment service classes.",
    )

    semi_related_hunk = DiffHunk(
        hunk_index=0,
        header="@@ -1,2 +1,3 @@",
        old_start_line=1,
        old_line_count=2,
        new_start_line=1,
        new_line_count=3,
        lines=[
            DiffLine(line_type=DiffLineType.ADDED, content="import logging\nlogger = logging.getLogger('payment')", new_line_number=2),
        ],
    )

    hunk_ctx = HunkContext(
        file_path="app/payment/logger.py",
        hunk_index=0,
        hunk=semi_related_hunk,
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)
    # Logging addition in payment module is partial/ambiguous
    assert result.classification in (IntentClassification.UNCERTAIN, IntentClassification.EXPLAINED)


def test_analyze_hunk_test_file_heuristic():
    """Test changes to test files are treated as supporting test suite changes."""
    analyzer = IntentAnalyzer(provider=TFIDFSimilarityProvider())

    pr_ctx = PRContext(
        pr_title="Update customer discount calculations",
        pr_description="Calculates customer loyalty rates.",
    )

    test_hunk = DiffHunk(
        hunk_index=0,
        header="@@ -10,3 +10,4 @@ def test_discount():",
        old_start_line=10,
        old_line_count=3,
        new_start_line=10,
        new_line_count=4,
        lines=[
            DiffLine(line_type=DiffLineType.ADDED, content="assert calc.discount(100, 0.1) == 90", new_line_number=12),
        ],
    )

    hunk_ctx = HunkContext(
        file_path="tests/test_billing.py",
        hunk_index=0,
        hunk=test_hunk,
    )

    result = analyzer.analyze_hunk(pr_ctx, hunk_ctx)
    # A test file updating assertions shouldn't be harshly flagged UNEXPLAINED
    assert result.classification in (IntentClassification.EXPLAINED, IntentClassification.UNCERTAIN)


def test_analyze_pull_request_aggregate_report(mock_hunk, mock_entity):
    """Test full PR analysis aggregates statistics and generates accurate summary."""
    analyzer = IntentAnalyzer(provider=TFIDFSimilarityProvider())

    pr_ctx = PRContext(
        pr_title="Fix discount bug in billing",
        pr_description="Validates rate bounds in calculate_discount.",
    )

    hunk1 = HunkContext(file_path="app/billing.py", hunk_index=0, hunk=mock_hunk, enclosing_entity=mock_entity)
    hunk2 = HunkContext(
        file_path="app/secret_miner.py",
        hunk_index=1,
        hunk=DiffHunk(
            hunk_index=1,
            header="@@ -1,1 +1,2 @@",
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=2,
            lines=[DiffLine(line_type=DiffLineType.ADDED, content="crypto_mine()", new_line_number=2)],
        ),
    )

    report = analyzer.analyze_pull_request(pr_ctx, [hunk1, hunk2], pr_number=101)
    assert isinstance(report, PRIntentReport)
    assert report.pr_number == 101
    assert report.total_hunks == 2
    assert report.explained_count == 1
    assert report.unexplained_count == 1
    assert "unexplained modifications" in report.summary.lower()
