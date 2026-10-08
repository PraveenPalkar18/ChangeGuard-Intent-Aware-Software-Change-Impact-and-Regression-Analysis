"""Tests for GitHub importer, client error handling, and API endpoints."""
from unittest.mock import MagicMock, patch
import pytest
from github.GithubException import (
    BadCredentialsException,
    UnknownObjectException,
    RateLimitExceededException,
    GithubException,
)
from backend.app.core.exceptions import (
    GitHubAuthenticationException,
    GitHubResourceNotFoundException,
    GitHubRateLimitExceededException,
    GitHubAPIException,
)
from backend.app.github.client import GitHubClient
from backend.app.github.importer import GitHubPRImporter
from backend.app.github.models import PullRequestDetails
from backend.app.api.v1.github import get_importer, get_client


# ==============================================================================
# 1. UNIT TESTS: GitHubPRImporter
# ==============================================================================


def test_importer_success(mock_github_objects):
    """Test importing a PR successfully translates all fields accurately."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_pull_request.return_value = mock_github_objects["pr"]

    importer = GitHubPRImporter(client=mock_client)
    result = importer.import_pull_request(owner="testorg", repo="testrepo", pr_number=42)

    assert isinstance(result, PullRequestDetails)
    assert result.owner == "testorg"
    assert result.repo == "testrepo"
    assert result.pr_number == 42
    assert result.title == "Fix math bug in addition function"
    assert "critical bug" in result.description
    assert result.author == "alicedev"
    assert result.state == "open"
    assert result.base_branch == "main"
    assert result.head_branch == "bugfix/calc-repair"
    assert result.changed_files_count == 2
    assert result.commits_count == 1
    assert result.total_additions == 5
    assert result.total_deletions == 2

    # Verify files
    assert len(result.files) == 2
    assert result.files[0].filename == "app/calculator.py"
    assert result.files[0].status == "modified"
    assert result.files[0].patch is not None
    assert "def add" in result.files[0].patch
    assert result.files[1].filename == "assets/logo.png"
    assert result.files[1].patch is None

    # Verify commits
    assert len(result.commits) == 1
    assert result.commits[0].sha == "a1b2c3d4e5f67890123456789abcdef012345678"
    assert "fix: update calculation" in result.commits[0].message
    assert result.commits[0].author_name == "Alice Developer"


def test_importer_handles_null_optional_fields():
    """Verify importer handles null body, null author dates, etc. gracefully without error."""
    mock_pr = MagicMock()
    mock_pr.title = "Minimal PR"
    mock_pr.body = None
    mock_pr.user = None
    mock_pr.state = "closed"
    mock_pr.created_at = None
    mock_pr.updated_at = None
    mock_pr.merged_at = None
    mock_pr.base = None
    mock_pr.head = None
    mock_pr.commits = 0
    mock_pr.changed_files = 0
    mock_pr.additions = 0
    mock_pr.deletions = 0
    mock_pr.get_files.return_value = []
    mock_pr.get_commits.return_value = []

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_pull_request.return_value = mock_pr

    importer = GitHubPRImporter(client=mock_client)
    result = importer.import_pull_request("org", "repo", 1)

    assert result.title == "Minimal PR"
    assert result.description == ""
    assert result.author == "unknown"
    assert result.commits == []
    assert result.files == []


# ==============================================================================
# 2. UNIT TESTS: GitHubClient Exception Translation
# ==============================================================================


def test_client_bad_credentials_exception():
    """Verify BadCredentialsException translates to GitHubAuthenticationException."""
    client = GitHubClient(token="invalid_token")
    with patch.object(client._client, "get_repo") as mock_get_repo:
        mock_get_repo.side_effect = BadCredentialsException(401, {"message": "Bad credentials"}, {})
        with pytest.raises(GitHubAuthenticationException) as exc_info:
            client.get_pull_request("owner", "repo", 1)
        assert exc_info.value.status_code == 401


def test_client_unknown_object_exception():
    """Verify UnknownObjectException translates to GitHubResourceNotFoundException."""
    client = GitHubClient(token="mock_token")
    with patch.object(client._client, "get_repo") as mock_get_repo:
        mock_get_repo.side_effect = UnknownObjectException(404, {"message": "Not Found"}, {})
        with pytest.raises(GitHubResourceNotFoundException) as exc_info:
            client.get_pull_request("owner", "repo", 999)
        assert exc_info.value.status_code == 404


def test_client_rate_limit_exception():
    """Verify RateLimitExceededException translates to GitHubRateLimitExceededException."""
    client = GitHubClient(token="mock_token")
    with patch.object(client._client, "get_repo") as mock_get_repo:
        mock_get_repo.side_effect = RateLimitExceededException(403, {"message": "API rate limit exceeded"}, {})
        with pytest.raises(GitHubRateLimitExceededException) as exc_info:
            client.get_pull_request("owner", "repo", 1)
        assert exc_info.value.status_code == 429


def test_client_generic_github_exception():
    """Verify other GithubException statuses translate to GitHubAPIException."""
    client = GitHubClient(token="mock_token")
    with patch.object(client._client, "get_repo") as mock_get_repo:
        mock_get_repo.side_effect = GithubException(500, {"message": "Server Error"}, {})
        with pytest.raises(GitHubAPIException) as exc_info:
            client.get_pull_request("owner", "repo", 1)
        assert exc_info.value.status_code == 500


# ==============================================================================
# 3. API ENDPOINT TESTS (FastAPI TestClient)
# ==============================================================================


def test_health_check(test_client):
    """Test health check endpoints."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ChangeGuard"

    v1_response = test_client.get("/api/v1/health")
    assert v1_response.status_code == 200


def test_api_import_pr_payload_success(test_client, mock_github_objects):
    """Test POST /api/v1/github/pull-request/import with mock importer."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_pull_request.return_value = mock_github_objects["pr"]
    mock_importer = GitHubPRImporter(client=mock_client)

    test_client.app.dependency_overrides[get_importer] = lambda: mock_importer
    try:
        response = test_client.post(
            "/api/v1/github/pull-request/import",
            json={"owner": "testorg", "repo": "testrepo", "pr_number": 42},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["owner"] == "testorg"
        assert data["repo"] == "testrepo"
        assert data["pr_number"] == 42
        assert data["title"] == "Fix math bug in addition function"
        assert len(data["files"]) == 2
        assert len(data["commits"]) == 1
    finally:
        test_client.app.dependency_overrides.clear()


def test_api_import_pr_path_param_success(test_client, mock_github_objects):
    """Test GET /api/v1/github/pull-request/{owner}/{repo}/{pr_number}."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.get_pull_request.return_value = mock_github_objects["pr"]
    mock_importer = GitHubPRImporter(client=mock_client)

    test_client.app.dependency_overrides[get_importer] = lambda: mock_importer
    try:
        response = test_client.get("/api/v1/github/pull-request/testorg/testrepo/42")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Fix math bug in addition function"
    finally:
        test_client.app.dependency_overrides.clear()


def test_api_import_pr_not_found(test_client):
    """Test 404 response on non-existent PR or repository."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.side_effect = GitHubResourceNotFoundException("Not found")

    test_client.app.dependency_overrides[get_importer] = lambda: mock_importer
    try:
        response = test_client.post(
            "/api/v1/github/pull-request/import",
            json={"owner": "unknown", "repo": "unknown", "pr_number": 999},
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]["error"].lower()
    finally:
        test_client.app.dependency_overrides.clear()


def test_api_import_pr_rate_limited(test_client):
    """Test 429 response when GitHub rate limit is hit."""
    mock_importer = MagicMock(spec=GitHubPRImporter)
    mock_importer.import_pull_request.side_effect = GitHubRateLimitExceededException("Rate limit exceeded")

    test_client.app.dependency_overrides[get_importer] = lambda: mock_importer
    try:
        response = test_client.get("/api/v1/github/pull-request/owner/repo/1")
        assert response.status_code == 429
        data = response.json()
        assert "rate limit" in data["detail"]["error"].lower()
    finally:
        test_client.app.dependency_overrides.clear()


def test_api_invalid_request_payload(test_client):
    """Test 422 Unprocessable Entity when payload is invalid (negative PR number)."""
    response = test_client.post(
        "/api/v1/github/pull-request/import",
        json={"owner": "owner", "repo": "repo", "pr_number": -5},
    )
    assert response.status_code == 422
