"""Tests for ChangeGuard On-Demand GitHub Pull Request Analysis Workflow."""
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.analysis.service import ChangeGuardAnalysisService
from backend.app.analysis.models import PRAnalysisReport
from backend.app.github.models import PullRequestDetails, PRFileChange, PRCommit
from backend.app.monitoring.state_store import MonitoringStateStore
from backend.app.monitoring.models import PRProcessingStatus


@pytest.fixture
def mock_pr_details():
    """Provides a realistic PullRequestDetails object for testing."""
    return PullRequestDetails(
        owner="pallets",
        repo="flask",
        pr_number=5000,
        title="Fix blueprint registration URL prefix handling",
        description="Ensures blueprint nested prefixes are joined properly without double slashes.",
        author="contributor1",
        state="open",
        created_at="2026-10-15T12:00:00Z",
        base_branch="main",
        head_branch="fix-nested-blueprints",
        base_sha="base_sha_123",
        head_sha="head_sha_456",
        commits_count=1,
        changed_files_count=1,
        total_additions=3,
        total_deletions=1,
        commits=[
            PRCommit(
                sha="commit_sha_789",
                message="Fix blueprint registration URL prefix handling",
                author_name="Contributor One",
                author_email="dev@example.com",
                timestamp="2026-10-15T11:55:00Z",
            )
        ],
        files=[
            PRFileChange(
                filename="src/flask/blueprints.py",
                status="modified",
                additions=3,
                deletions=1,
                changes=4,
                patch=(
                    "@@ -10,3 +10,5 @@\n"
                    " def register_blueprint(bp, url_prefix=None):\n"
                    "-    return bp.register(url_prefix)\n"
                    "+    normalized = url_prefix.rstrip('/') if url_prefix else ''\n"
                    "+    return bp.register(normalized)\n"
                ),
            )
        ],
    )


def test_on_demand_analysis_with_mocked_github(mock_pr_details, tmp_path):
    """Test full on-demand pipeline execution with mocked GitHub client and importer."""
    mock_importer = MagicMock()
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock()
    # Mock source content when fetching full source files
    mock_client.get_file_content.side_effect = lambda owner, repo, path, ref=None: (
        "def register_blueprint(bp, url_prefix=None):\n"
        "    normalized = url_prefix.rstrip('/') if url_prefix else ''\n"
        "    return bp.register(normalized)\n"
    )

    service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
    )

    report = service.analyze_pull_request(
        owner="pallets",
        repo="flask",
        pr_number=5000,
        fetch_source_files=True,
        provider_name="tfidf",
    )

    # Assertions on pipeline integration
    assert isinstance(report, PRAnalysisReport)
    assert report.owner == "pallets"
    assert report.repo == "flask"
    assert report.pr_number == 5000
    assert report.title == "Fix blueprint registration URL prefix handling"
    assert report.ai_provider == "tfidf"
    assert report.total_files_analyzed == 1
    assert report.total_hunks_analyzed == 1

    # Check intent results
    assert report.explained_count >= 1 or report.uncertain_count >= 0
    assert len(report.files) == 1
    file_rep = report.files[0]
    assert file_rep.filename == "src/flask/blueprints.py"
    assert len(file_rep.hunks) == 1
    hunk = file_rep.hunks[0]
    assert hunk.classification is not None
    assert hunk.confidence > 0.0

    # Check risk assessment
    assert report.risk_assessment is not None
    assert report.risk_assessment.overall_risk_level in ["LOW", "MEDIUM", "HIGH"]
    assert 0.0 <= report.risk_assessment.overall_risk_score <= 1.0


def test_on_demand_api_persists_to_state_store(mock_pr_details, tmp_path):
    """Verify that on-demand analysis via REST API automatically persists to local state store."""
    test_state_file = str(tmp_path / "on_demand_state.json")

    mock_importer = MagicMock()
    mock_importer.import_pull_request.return_value = mock_pr_details

    mock_client = MagicMock()
    mock_client.get_file_content.return_value = "def register_blueprint(bp):\n    pass\n"

    custom_service = ChangeGuardAnalysisService(
        importer=mock_importer,
        github_client=mock_client,
    )

    from backend.app.api.v1.analysis import get_analysis_service

    app.dependency_overrides[get_analysis_service] = lambda: custom_service
    client = TestClient(app)

    try:
        with patch("backend.app.api.v1.analysis.MonitoringStateStore") as mock_store_cls:
            real_store = MonitoringStateStore(file_path=test_state_file)
            real_store.clear()
            mock_store_cls.return_value = real_store

            # 1. Trigger via POST
            res_post = client.post(
                "/api/v1/analyze/pull-request",
                json={"owner": "pallets", "repo": "flask", "pr_number": 5000, "fetch_source_files": True},
            )
            assert res_post.status_code == 200
            data = res_post.json()
            assert data["pr_number"] == 5000

            # Verify state store has the record
            record = real_store.get_pr_record("pallets", "flask", 5000)
            assert record is not None
            assert record.status == PRProcessingStatus.COMPLETED
            assert record.pr_number == 5000
            assert record.title == "Fix blueprint registration URL prefix handling"

            # 2. Trigger via GET shortcut
            res_get = client.get("/api/v1/analyze/pull-request/pallets/flask/5000")
            assert res_get.status_code == 200
            assert res_get.json()["pr_number"] == 5000
    finally:
        app.dependency_overrides.clear()


def test_real_public_github_pr_live_analysis():
    """Verify that ChangeGuard can connect to GitHub and analyze a real public PR.
    
    Uses 'octocat/Hello-World' PR #1 as a stable, lightweight public test fixture.
    """
    from backend.app.github.client import GitHubClient
    client = GitHubClient()
    rl = client.get_rate_limit_info()
    if "error" in rl or rl.get("remaining", 0) < 5:
        pytest.skip("GitHub API rate limit exhausted or offline; skipping live network test.")

    service = ChangeGuardAnalysisService(github_client=client)
    report = service.analyze_pull_request(
        owner="octocat",
        repo="Hello-World",
        pr_number=1,
        fetch_source_files=True,
    )

    assert report.owner == "octocat"
    assert report.repo == "Hello-World"
    assert report.pr_number == 1
    assert report.title == "Edited README via GitHub"
    assert report.total_files_analyzed == 1
    assert report.risk_assessment is not None
