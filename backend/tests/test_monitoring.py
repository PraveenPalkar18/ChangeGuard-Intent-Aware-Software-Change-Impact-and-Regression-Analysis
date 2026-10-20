"""Tests for ChangeGuard Milestone 8 (Automatic PR Monitoring) and Milestone 9 (Dashboard)."""
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.monitoring.models import (
    PRProcessingStatus,
    PRStateRecord,
    RepoConfig,
)
from backend.app.monitoring.state_store import MonitoringStateStore
from backend.app.monitoring.poller import PRPollingWorker
from backend.app.analysis.models import PRAnalysisReport
from backend.app.impact.models import PRRiskAssessment, RiskLevel


@pytest.fixture
def temp_state_file(tmp_path):
    """Provides a temporary json file path for state store testing."""
    return str(tmp_path / "test_monitoring_state.json")


@pytest.fixture
def sample_analysis_report():
    """Provides a valid PRAnalysisReport instance for testing."""
    return PRAnalysisReport(
        owner="test-owner",
        repo="test-repo",
        pr_number=42,
        title="Add feature",
        description="Feature explanation",
        author="alice",
        state="open",
        base_branch="main",
        head_branch="feature",
        ai_provider="tfidf",
        ai_model="tfidf-cosine",
        total_files_analyzed=1,
        total_hunks_analyzed=1,
        explained_count=1,
        unexplained_count=0,
        uncertain_count=0,
        overall_intent_summary="All hunks explained",
        files=[],
        risk_assessment=PRRiskAssessment(
            overall_risk_level=RiskLevel.LOW,
            overall_risk_score=0.15,
            summary="Low risk change with isolated logic.",
            high_risk_reasons=[],
            primary_impact_paths=[],
            file_risks=[],
            entity_risks=[],
            limitations=[],
        ),
        test_selection=None,
        processing_limitations=[],
    )


class TestMonitoringStateStore:
    """Tests for persistent state tracking."""
    __test__ = False

    def test_state_store_init_and_repo_management(self, temp_state_file):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        assert store.get_repo_configs() == []

        # Add repository
        store.set_repo_config(RepoConfig(owner="octocat", repo="Hello-World", enabled=True, poll_interval_seconds=60))
        repos = store.get_repo_configs()
        assert len(repos) == 1
        assert repos[0].owner == "octocat"
        assert repos[0].repo == "Hello-World"
        assert repos[0].enabled is True

        # Idempotent addition
        store.set_repo_config(RepoConfig(owner="octocat", repo="Hello-World", enabled=True, poll_interval_seconds=30))
        repos = store.get_repo_configs()
        assert len(repos) == 1
        assert repos[0].poll_interval_seconds == 30

        # Remove repository
        assert store.remove_repo_config("octocat", "Hello-World") is True
        assert len(store.get_repo_configs()) == 0
        assert store.remove_repo_config("octocat", "Hello-World") is False

    def test_pr_state_lifecycle_and_persistence(self, temp_state_file, sample_analysis_report):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()

        # Initial lookup
        assert store.get_pr_record("octocat", "Hello-World", 1) is None

        # Create record
        record = PRStateRecord(
            repo_key="octocat/Hello-World",
            pr_number=1,
            head_sha="sha-1",
            title="Add feature",
            author="alice",
            status=PRProcessingStatus.PENDING,
        )
        store.save_pr_record(record)

        loaded = store.get_pr_record("octocat", "Hello-World", 1)
        assert loaded is not None
        assert loaded.status == PRProcessingStatus.PENDING

        # Transition to completed
        loaded.status = PRProcessingStatus.COMPLETED
        loaded.analysis_report = sample_analysis_report
        store.save_pr_record(loaded)

        # Verify disk persistence across new store instance
        store_new = MonitoringStateStore(file_path=temp_state_file)
        reloaded = store_new.get_pr_record("octocat", "Hello-World", 1)
        assert reloaded is not None
        assert reloaded.head_sha == "sha-1"
        assert reloaded.status == PRProcessingStatus.COMPLETED
        assert reloaded.analysis_report is not None
        assert reloaded.analysis_report.pr_number == 42


class TestPRPollingWorker:
    """Tests for local PR polling worker, duplicate suppression, and error handling."""
    __test__ = False

    def test_poll_once_discovers_and_analyzes_new_pr(self, temp_state_file, sample_analysis_report):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        store.set_repo_config(RepoConfig(owner="test-owner", repo="test-repo", enabled=True))

        mock_github = MagicMock()
        mock_github.get_rate_limit_info.return_value = {"remaining": 5000, "limit": 5000}

        # Mock PR item
        mock_pr = MagicMock()
        mock_pr.number = 42
        mock_pr.title = "Fix bug"
        mock_pr.user.login = "dev1"
        mock_pr.head.sha = "head-sha-1"
        mock_github.get_pull_requests.return_value = [mock_pr]

        mock_service = MagicMock()
        mock_service.analyze_pull_request.return_value = sample_analysis_report

        worker = PRPollingWorker(
            state_store=store,
            github_client=mock_github,
            analysis_service=mock_service,
        )

        # Execute single poll cycle
        summary = worker.poll_once()
        assert summary["prs_discovered"] == 1
        assert summary["prs_analyzed"] == 1

        mock_github.get_pull_requests.assert_called_once_with(
            owner="test-owner", repo="test-repo", state="open"
        )
        mock_service.analyze_pull_request.assert_called_once_with(
            owner="test-owner", repo="test-repo", pr_number=42, fetch_source_files=True
        )

        record = store.get_pr_record("test-owner", "test-repo", 42)
        assert record is not None
        assert record.status == PRProcessingStatus.COMPLETED
        assert record.head_sha == "head-sha-1"
        assert record.analysis_report is not None

    def test_duplicate_suppression_when_sha_unchanged(self, temp_state_file, sample_analysis_report):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        store.set_repo_config(RepoConfig(owner="test-owner", repo="test-repo", enabled=True))

        mock_github = MagicMock()
        mock_github.get_rate_limit_info.return_value = {"remaining": 5000, "limit": 5000}
        mock_pr = MagicMock()
        mock_pr.number = 42
        mock_pr.title = "Fix bug"
        mock_pr.user.login = "dev1"
        mock_pr.head.sha = "head-sha-1"
        mock_github.get_pull_requests.return_value = [mock_pr]

        mock_service = MagicMock()
        mock_service.analyze_pull_request.return_value = sample_analysis_report

        worker = PRPollingWorker(
            state_store=store,
            github_client=mock_github,
            analysis_service=mock_service,
        )

        # First run: analyzes PR
        summary1 = worker.poll_once()
        assert summary1["prs_analyzed"] == 1
        assert mock_service.analyze_pull_request.call_count == 1

        # Second run: same head_sha, must skip analysis
        summary2 = worker.poll_once()
        assert summary2["prs_skipped"] == 1
        assert summary2["prs_analyzed"] == 0
        assert mock_service.analyze_pull_request.call_count == 1  # Still 1!

    def test_reanalyze_when_head_sha_updates(self, temp_state_file, sample_analysis_report):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        store.set_repo_config(RepoConfig(owner="test-owner", repo="test-repo", enabled=True))

        mock_github = MagicMock()
        mock_github.get_rate_limit_info.return_value = {"remaining": 5000, "limit": 5000}
        mock_service = MagicMock()
        mock_service.analyze_pull_request.return_value = sample_analysis_report

        worker = PRPollingWorker(
            state_store=store,
            github_client=mock_github,
            analysis_service=mock_service,
        )

        # 1st commit
        mock_pr_v1 = MagicMock()
        mock_pr_v1.number = 42
        mock_pr_v1.title = "Fix bug"
        mock_pr_v1.user.login = "dev1"
        mock_pr_v1.head.sha = "commit-v1"
        mock_github.get_pull_requests.return_value = [mock_pr_v1]

        worker.poll_once()
        assert mock_service.analyze_pull_request.call_count == 1
        assert store.get_pr_record("test-owner", "test-repo", 42).head_sha == "commit-v1"

        # 2nd commit pushed
        mock_pr_v2 = MagicMock()
        mock_pr_v2.number = 42
        mock_pr_v2.title = "Fix bug"
        mock_pr_v2.user.login = "dev1"
        mock_pr_v2.head.sha = "commit-v2"
        mock_github.get_pull_requests.return_value = [mock_pr_v2]

        worker.poll_once()
        assert mock_service.analyze_pull_request.call_count == 2
        assert store.get_pr_record("test-owner", "test-repo", 42).head_sha == "commit-v2"

    def test_analysis_failure_retry_and_terminal_failed(self, temp_state_file):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        store.set_repo_config(RepoConfig(owner="test-owner", repo="test-repo", enabled=True))

        mock_github = MagicMock()
        mock_github.get_rate_limit_info.return_value = {"remaining": 5000, "limit": 5000}
        mock_pr = MagicMock()
        mock_pr.number = 99
        mock_pr.title = "Faulty PR"
        mock_pr.user.login = "baddev"
        mock_pr.head.sha = "sha-err"
        mock_github.get_pull_requests.return_value = [mock_pr]

        mock_service = MagicMock()
        mock_service.analyze_pull_request.side_effect = RuntimeError("Diff parsing timeout")

        worker = PRPollingWorker(
            state_store=store,
            github_client=mock_github,
            analysis_service=mock_service,
        )

        # Max retries is 3 (default)
        # Attempt 1: retry_count becomes 1, status is FAILED
        worker.poll_once()
        rec = store.get_pr_record("test-owner", "test-repo", 99)
        assert rec.status == PRProcessingStatus.FAILED
        assert rec.retry_count == 1

        # Attempt 2: retry_count becomes 2, status remains FAILED
        worker.poll_once()
        rec = store.get_pr_record("test-owner", "test-repo", 99)
        assert rec.status == PRProcessingStatus.FAILED
        assert rec.retry_count == 2

        # Attempt 3: retry_count becomes 3
        worker.poll_once()
        rec = store.get_pr_record("test-owner", "test-repo", 99)
        assert rec.status == PRProcessingStatus.FAILED
        assert rec.retry_count == 3
        assert "Diff parsing timeout" in rec.error_message

        # Attempt 4: retry_count == 3 is not < MAX_PROCESSING_RETRIES (3), so skipped!
        summary = worker.poll_once()
        assert summary["prs_skipped"] == 1
        assert summary["prs_analyzed"] == 0

    def test_rate_limit_warning_pauses_poll(self, temp_state_file):
        store = MonitoringStateStore(file_path=temp_state_file)
        store.clear()
        store.set_repo_config(RepoConfig(owner="test-owner", repo="test-repo", enabled=True))

        mock_github = MagicMock()
        mock_github.get_rate_limit_info.return_value = {"remaining": 2, "limit": 5000}  # < 5 critical
        mock_service = MagicMock()

        worker = PRPollingWorker(
            state_store=store,
            github_client=mock_github,
            analysis_service=mock_service,
        )

        summary = worker.poll_once()
        assert len(summary["errors"]) == 1
        assert "rate limit critical" in summary["errors"][0].lower()
        assert mock_github.get_pull_requests.call_count == 0


# Test function wrappers for pytest collection
def test_state_store_init_and_repo_management(temp_state_file):
    TestMonitoringStateStore().test_state_store_init_and_repo_management(temp_state_file)


def test_pr_state_lifecycle_and_persistence(temp_state_file, sample_analysis_report):
    TestMonitoringStateStore().test_pr_state_lifecycle_and_persistence(temp_state_file, sample_analysis_report)


def test_poll_once_discovers_and_analyzes_new_pr(temp_state_file, sample_analysis_report):
    TestPRPollingWorker().test_poll_once_discovers_and_analyzes_new_pr(temp_state_file, sample_analysis_report)


def test_duplicate_suppression_when_sha_unchanged(temp_state_file, sample_analysis_report):
    TestPRPollingWorker().test_duplicate_suppression_when_sha_unchanged(temp_state_file, sample_analysis_report)


def test_reanalyze_when_head_sha_updates(temp_state_file, sample_analysis_report):
    TestPRPollingWorker().test_reanalyze_when_head_sha_updates(temp_state_file, sample_analysis_report)


def test_analysis_failure_retry_and_terminal_failed(temp_state_file):
    TestPRPollingWorker().test_analysis_failure_retry_and_terminal_failed(temp_state_file)


def test_rate_limit_warning_pauses_poll(temp_state_file):
    TestPRPollingWorker().test_rate_limit_warning_pauses_poll(temp_state_file)


def test_monitoring_api_endpoints():
    """Integration test verifying monitoring management REST endpoints."""
    client = TestClient(app)

    # 1. Check monitoring status
    res = client.get("/api/v1/monitoring/status")
    assert res.status_code == 200
    status_data = res.json()
    assert "is_running" in status_data
    assert "poll_interval_seconds" in status_data
    assert "monitored_repos" in status_data

    # 2. Add repository
    res = client.post(
        "/api/v1/monitoring/repositories",
        json={"owner": "unit-test-org", "repo": "unit-test-repo", "enabled": True},
    )
    assert res.status_code == 200
    repo_data = res.json()
    assert repo_data["owner"] == "unit-test-org"
    assert repo_data["repo"] == "unit-test-repo"

    # 3. Check PR list
    res = client.get("/api/v1/monitoring/prs")
    assert res.status_code == 200
    prs_data = res.json()
    assert isinstance(prs_data, list)

    # 4. Remove repository
    res = client.delete("/api/v1/monitoring/repositories/unit-test-org/unit-test-repo")
    assert res.status_code == 200
    assert res.json()["status"] == "removed"


def test_github_reporting_permission_guard():
    """Verify that GitHub reporting safely rejects write operations when disabled."""
    client = TestClient(app)

    # Ensure ENABLE_GITHUB_REPORTING is False (safe read-only default)
    with patch.object(settings, "ENABLE_GITHUB_REPORTING", False):
        res = client.post(
            "/api/v1/monitoring/prs/test-owner/test-repo/1/comment",
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "disabled"
        assert "disabled by default" in data["message"].lower()


def test_dashboard_endpoint_serves_html():
    """Verify that /dashboard and / return HTML dashboard content."""
    client = TestClient(app)

    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    assert "text/html" in res_dash.headers.get("content-type", "")
    assert "ChangeGuard" in res_dash.text

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "ChangeGuard" in res_root.text


def test_github_client_get_pull_requests_safe_on_empty():
    """Verify that get_pull_requests safely handles empty pull request iterators without IndexError."""
    from backend.app.github.client import GitHubClient

    client = GitHubClient(token="mock_token")
    mock_repo = MagicMock()
    # Simulate PyGithub PaginatedList behavior when 0 PRs exist
    mock_repo.get_pulls.return_value = iter([])

    with patch.object(client.raw_client, "get_repo", return_value=mock_repo):
        prs = client.get_pull_requests("PraveenPalkar18", "ShopFlow", state="all")
        assert prs == []
        mock_repo.get_pulls.assert_called_once_with(state="all", sort="updated", direction="desc")


def test_worker_lifecycle_prevent_duplicate_threads(temp_state_file):
    """Verify that Start Poller and Stop Poller cleanly manage one worker without duplicate threads."""
    store = MonitoringStateStore(file_path=temp_state_file)
    store.clear()
    mock_gh = MagicMock()
    mock_analysis = MagicMock()

    worker = PRPollingWorker(
        state_store=store,
        github_client=mock_gh,
        analysis_service=mock_analysis,
        poll_interval_seconds=60,
    )

    try:
        # Start poller
        assert worker.start() is True
        assert worker.is_running is True

        # Second start attempt must be rejected to prevent duplicate workers
        assert worker.start() is False
        assert worker.is_running is True

        # Clean stop
        assert worker.stop() is True
        assert worker.is_running is False

        # Second stop attempt returns False (idempotent)
        assert worker.stop() is False
        assert worker.is_running is False
    finally:
        worker.stop()


def test_monitoring_button_endpoints_poll_and_worker_control():
    """Verify that /poll, /start, /stop API endpoints return actionable responses."""
    from backend.app.monitoring.poller import get_polling_worker

    mock_worker = MagicMock()
    mock_worker.poll_once.return_value = {
        "timestamp": "2026-10-20T12:00:00Z",
        "repos_checked": 1,
        "prs_discovered": 1,
        "prs_analyzed": 1,
        "prs_skipped": 0,
        "errors": [],
    }
    mock_worker.start.return_value = True
    mock_worker.stop.return_value = True
    mock_worker.is_running = True

    app.dependency_overrides[get_polling_worker] = lambda: mock_worker
    try:
        client = TestClient(app)

        # POST /poll
        poll_res = client.post("/api/v1/monitoring/poll")
        assert poll_res.status_code == 200
        poll_json = poll_res.json()
        assert poll_json["status"] == "poll_completed"
        assert poll_json["summary"]["repos_checked"] == 1
        assert poll_json["summary"]["prs_analyzed"] == 1
        assert poll_json["summary"]["errors"] == []

        # POST /start
        start_res = client.post("/api/v1/monitoring/start")
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "started"

        # POST /stop
        stop_res = client.post("/api/v1/monitoring/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "stopped"
    finally:
        app.dependency_overrides.pop(get_polling_worker, None)


def test_shopflow_pr_discovery_and_state_persistence(temp_state_file, sample_analysis_report):
    """Verify that PraveenPalkar18/ShopFlow is polled, discovered, analyzed, and persisted."""
    store = MonitoringStateStore(file_path=temp_state_file)
    store.clear()

    # Configure ShopFlow repository
    store.set_repo_config(RepoConfig(
        owner="PraveenPalkar18",
        repo="ShopFlow",
        enabled=True,
        poll_interval_seconds=60,
        pr_state="all",
    ))

    # Mock PR from ShopFlow
    mock_pr = MagicMock()
    mock_pr.number = 1
    mock_pr.title = "fix: normalize product names in input validation"
    mock_pr.head.sha = "bad48187dbfced5814f3b1ea5d565d7d9e980d3c"
    mock_pr.user.login = "PraveenPalkar18"

    mock_gh = MagicMock()
    mock_gh.get_rate_limit_info.return_value = {"remaining": 4900}
    mock_gh.get_pull_requests.return_value = [mock_pr]

    mock_analysis = MagicMock()
    mock_analysis.analyze_pull_request.return_value = sample_analysis_report

    worker = PRPollingWorker(
        state_store=store,
        github_client=mock_gh,
        analysis_service=mock_analysis,
    )

    summary = worker.poll_once()
    assert summary["repos_checked"] == 1
    assert summary["prs_discovered"] == 1
    assert summary["prs_analyzed"] == 1
    assert summary["errors"] == []

    # Verify state record persisted in store
    record = store.get_pr_record("PraveenPalkar18", "ShopFlow", 1)
    assert record is not None
    assert record.status == PRProcessingStatus.COMPLETED
    assert record.title == "fix: normalize product names in input validation"
    assert record.analysis_report is not None
    assert record.analysis_report.risk_assessment.overall_risk_level == RiskLevel.LOW

    # Status check confirms operational metrics
    status = worker.get_status()
    assert status.total_prs_tracked == 1
    assert status.completed_count == 1
    assert status.last_successful_poll_time is not None
    assert status.last_error is None


def test_worker_error_handling_reports_actionable_status(temp_state_file):
    """Verify that network or API errors during polling are captured in status rather than crashing."""
    store = MonitoringStateStore(file_path=temp_state_file)
    store.clear()
    store.set_repo_config(RepoConfig(owner="PraveenPalkar18", repo="ShopFlow", enabled=True))

    mock_gh = MagicMock()
    mock_gh.get_rate_limit_info.return_value = {"remaining": 5000}
    mock_gh.get_pull_requests.side_effect = RuntimeError("Simulated GitHub connection drop")

    worker = PRPollingWorker(
        state_store=store,
        github_client=mock_gh,
    )

    summary = worker.poll_once()
    assert summary["repos_checked"] == 1
    assert len(summary["errors"]) == 1
    assert "Simulated GitHub connection drop" in summary["errors"][0]

    status = worker.get_status()
    assert status.last_error is not None
    assert "Simulated GitHub connection drop" in status.last_error
    assert status.is_polling is False


def test_pr_table_repository_filtering(temp_state_file, sample_analysis_report):
    """Verify that list_pr_records correctly filters by repository, preventing cross-repo display."""
    store = MonitoringStateStore(file_path=temp_state_file)
    store.clear()

    rec_shopflow = PRStateRecord(
        repo_key="PraveenPalkar18/ShopFlow",
        pr_number=1,
        head_sha="sha1",
        title="ShopFlow PR",
        status=PRProcessingStatus.COMPLETED,
    )
    rec_other = PRStateRecord(
        repo_key="octocat/Hello-World",
        pr_number=1,
        head_sha="sha2",
        title="Octocat PR",
        status=PRProcessingStatus.COMPLETED,
    )

    store.save_pr_record(rec_shopflow)
    store.save_pr_record(rec_other)

    # Filter by ShopFlow only
    shopflow_prs = store.list_pr_records(owner="PraveenPalkar18", repo="ShopFlow")
    assert len(shopflow_prs) == 1
    assert shopflow_prs[0].repo_key == "PraveenPalkar18/ShopFlow"

    # All PRs
    all_prs = store.list_pr_records()
    assert len(all_prs) == 2

