"""Integration tests for ChangeGuard End-to-End Analysis Service and API endpoints."""
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.github.models import (
    PullRequestDetails,
    PRFileChange,
    PRCommit,
)
from backend.app.github.client import GitHubClient
from backend.app.github.importer import GitHubPRImporter
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.intent.intent_analyzer import IntentAnalyzer
from backend.app.intent.providers.mock_provider import MockAIProvider
from backend.app.analysis.service import ChangeGuardAnalysisService
from backend.app.analysis.models import PRAnalysisReport
from backend.app.api.v1.analysis import get_analysis_service
from backend.app.core.exceptions import (
    GitHubResourceNotFoundException,
    GitHubRateLimitExceededException,
)


@pytest.fixture
def mock_pr_details():
    """Generates mock PullRequestDetails for end-to-end analysis."""
    return PullRequestDetails(
        owner="testowner",
        repo="testrepo",
        pr_number=50,
        title="Add discount rate validation in billing",
        description="This pull request adds rate validation to the calculate_discount method.",
        author="alice",
        state="open",
        created_at="2026-10-19T10:00:00Z",
        base_branch="main",
        head_branch="feature/discount-validation",
        base_sha="base12345",
        head_sha="head67890",
        commits_count=1,
        changed_files_count=3,
        total_additions=5,
        total_deletions=1,
        commits=[
            PRCommit(
                sha="head67890",
                message="feat: validate discount rate",
                author_name="Alice",
                timestamp="2026-10-19T10:00:00Z",
            )
        ],
        files=[
            # 1. Python file with patch and source
            PRFileChange(
                filename="app/billing.py",
                status="modified",
                additions=3,
                deletions=1,
                changes=4,
                patch="""@@ -3,3 +3,5 @@ class BillingService:
     def calculate_discount(self, price, rate):
-        return price * (1 - rate)
+        if rate < 0 or rate > 1:
+            raise ValueError("Invalid rate")
+        return price * (1 - rate)
""",
            ),
            # 2. File with missing patch (binary or unchanged)
            PRFileChange(
                filename="assets/badge.png",
                status="added",
                additions=0,
                deletions=0,
                changes=0,
                patch=None,
            ),
            # 3. Non-Python file with patch
            PRFileChange(
                filename="README.md",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                patch="""@@ -10,1 +10,2 @@
 Documentation
+Discount validation is now supported.
""",
            ),
        ],
    )


@pytest.fixture
def mock_source_code():
    return """class BillingService:
    def calculate_discount(self, price, rate):
        if rate < 0 or rate > 1:
            raise ValueError("Invalid rate")
        return price * (1 - rate)
"""


def test_analysis_service_end_to_end(mock_pr_details, mock_source_code):
    """Test full pipeline: ingestion -> diff parsing -> source AST -> entity mapping -> intent analysis."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    # Return source for billing.py, None for others
    def fake_get_file(owner, repo, path, ref=None):
        if path == "app/billing.py":
            return mock_source_code
        return None
    mock_client.get_file_content.side_effect = fake_get_file

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
        intent_analyzer=IntentAnalyzer(provider=MockAIProvider()),
    )

    report = service.analyze_pull_request(owner="testowner", repo="testrepo", pr_number=50)

    assert isinstance(report, PRAnalysisReport)
    assert report.owner == "testowner"
    assert report.repo == "testrepo"
    assert report.pr_number == 50
    assert report.total_files_analyzed == 3
    assert report.total_hunks_analyzed == 2  # 1 from billing.py, 1 from README.md

    # Check file 1 (app/billing.py)
    f1 = report.files[0]
    assert f1.filename == "app/billing.py"
    assert f1.patch_available is True
    assert f1.source_available is True
    assert f1.ast_entities_found > 0
    assert len(f1.hunks) == 1
    h1 = f1.hunks[0]
    assert h1.matched_entity_name == "calculate_discount"
    assert h1.classification.value == "EXPLAINED"
    assert h1.similarity_score > 0.0

    # Check file 2 (assets/badge.png - missing patch)
    f2 = report.files[1]
    assert f2.filename == "assets/badge.png"
    assert f2.patch_available is False
    assert len(f2.hunks) == 0
    assert any("no unified diff patch" in lim.lower() for lim in f2.limitations)

    # Check file 3 (README.md - non-Python file)
    f3 = report.files[2]
    assert f3.filename == "README.md"
    assert f3.patch_available is True
    assert f3.source_available is False
    assert any("non-python" in lim.lower() for lim in f3.limitations)


def test_analysis_service_source_unavailable_fallback(mock_pr_details):
    """Test graceful handling when source repository files cannot be retrieved."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    # Simulate network or API failure retrieving full source
    mock_client.get_file_content.return_value = None

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
        intent_analyzer=IntentAnalyzer(provider=MockAIProvider()),
    )

    report = service.analyze_pull_request(owner="testowner", repo="testrepo", pr_number=50, fetch_source_files=True)

    # Pipeline does NOT crash; reports source unavailable limitation
    assert report.total_hunks_analyzed == 2
    f1 = report.files[0]
    assert f1.source_available is False
    assert any("could not be retrieved" in lim.lower() for lim in f1.limitations)


def test_api_analyze_pr_post_endpoint(mock_pr_details, mock_source_code):
    """Test POST /api/v1/analyze/pull-request endpoint via TestClient."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_file_content.return_value = mock_source_code

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
        intent_analyzer=IntentAnalyzer(provider=MockAIProvider()),
    )

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/analyze/pull-request",
            json={"owner": "testowner", "repo": "testrepo", "pr_number": 50, "fetch_source_files": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["owner"] == "testowner"
        assert data["pr_number"] == 50
        assert data["total_files_analyzed"] == 3
        assert data["total_hunks_analyzed"] == 2
        assert len(data["files"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_api_analyze_pr_get_endpoint(mock_pr_details, mock_source_code):
    """Test GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number} endpoint."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_file_content.return_value = mock_source_code

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
        intent_analyzer=IntentAnalyzer(provider=MockAIProvider()),
    )

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        response = client.get("/api/v1/analyze/pull-request/testowner/testrepo/50")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Add discount rate validation in billing"
        assert "overall_intent_summary" in data
    finally:
        app.dependency_overrides.clear()


def test_api_analyze_pr_not_found():
    """Test 404 response when PR or repo is not found."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.side_effect = GitHubResourceNotFoundException("PR #999 not found")

    service = ChangeGuardAnalysisService(importer=mock_importer)

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        response = client.get("/api/v1/analyze/pull-request/testowner/testrepo/999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]["error"].lower()
    finally:
        app.dependency_overrides.clear()


def test_provider_selection_tfidf_real_inference():
    """Verify provider_name='tfidf' invokes TFIDFSimilarityProvider and computes real similarity."""
    from backend.app.intent.factory import create_model_provider
    from backend.app.intent.providers.tfidf_provider import TFIDFSimilarityProvider

    provider = create_model_provider(provider_name="tfidf")
    assert isinstance(provider, TFIDFSimilarityProvider)
    assert provider.provider_name == "tfidf"
    assert not isinstance(provider, MockAIProvider)

    # Actual inference computation check
    score = provider.compute_similarity(
        "def calculate_discount(price, rate): return price * (1 - rate)",
        "Add discount rate calculation and validation in billing module",
    )
    assert isinstance(score, float)
    assert score > 0.15  # Real cosine similarity with sub-word token expansion


def test_provider_selection_mock_attribution():
    """Verify provider_name='mock' cleanly returns deterministic MockAIProvider without fallback."""
    from backend.app.intent.factory import create_model_provider

    provider = create_model_provider(provider_name="mock")
    assert isinstance(provider, MockAIProvider)
    assert provider.provider_name == "mock"
    assert provider.model_name == "mock-jaccard"


def test_provider_selection_codebert_fallback_attribution():
    """Verify provider_name='codebert' cleanly reports fallback when torch is unavailable."""
    from backend.app.intent.factory import create_model_provider, FallbackModelProvider

    provider = create_model_provider(provider_name="codebert")
    assert isinstance(provider, FallbackModelProvider)
    assert provider.is_fallback_active
    assert "fell back from codebert" in provider.provider_name


def test_api_provider_override_via_post(mock_pr_details, mock_source_code):
    """Verify passing provider_name in POST payload routes to requested provider and attributions."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_file_content.return_value = mock_source_code

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
    )

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        # Request tfidf explicitly
        resp_tfidf = client.post(
            "/api/v1/analyze/pull-request",
            json={
                "owner": "testowner",
                "repo": "testrepo",
                "pr_number": 50,
                "provider_name": "tfidf",
            },
        )
        assert resp_tfidf.status_code == 200
        data_tfidf = resp_tfidf.json()
        assert data_tfidf["ai_provider"] == "tfidf"
        assert data_tfidf["files"][0]["hunks"][0]["provider_used"] == "tfidf"

        # Request mock explicitly
        resp_mock = client.post(
            "/api/v1/analyze/pull-request",
            json={
                "owner": "testowner",
                "repo": "testrepo",
                "pr_number": 50,
                "provider_name": "mock",
            },
        )
        assert resp_mock.status_code == 200
        data_mock = resp_mock.json()
        assert data_mock["ai_provider"] == "mock"
        assert data_mock["files"][0]["hunks"][0]["provider_used"] == "mock"
    finally:
        app.dependency_overrides.clear()


def test_api_provider_override_via_get(mock_pr_details, mock_source_code):
    """Verify provider query parameter in GET request routes properly."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_file_content.return_value = mock_source_code

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
    )

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        resp = client.get("/api/v1/analyze/pull-request/testowner/testrepo/50?provider=mock")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_provider"] == "mock"
        assert data["files"][0]["hunks"][0]["provider_used"] == "mock"
    finally:
        app.dependency_overrides.clear()


def test_api_analyze_pr_includes_change_graph(mock_pr_details, mock_source_code):
    """Verify change_graph is populated in PRAnalysisReport from API call without breaking existing schema."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_file_content.return_value = mock_source_code

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
    )

    client = TestClient(app)
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        resp = client.get("/api/v1/analyze/pull-request/testowner/testrepo/50")
        assert resp.status_code == 200
        data = resp.json()

        # Existing schema fields preserved
        assert data["owner"] == "testowner"
        assert data["total_files_analyzed"] == 3
        assert len(data["files"]) == 3

        # Milestone 5 change_graph populated
        assert "change_graph" in data
        cg = data["change_graph"]
        assert cg is not None
        assert cg["total_nodes"] >= 3
        assert cg["total_edges"] >= 2
        assert len(cg["changed_entities"]) >= 1
    finally:
        app.dependency_overrides.clear()


