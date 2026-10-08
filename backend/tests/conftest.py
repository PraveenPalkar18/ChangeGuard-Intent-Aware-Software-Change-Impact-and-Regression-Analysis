"""Test configuration and reusable mocks for GitHub testing."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.github.models import PullRequestDetails, PRFileChange, PRCommit


@pytest.fixture
def test_client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def mock_github_objects():
    """Generates mock PyGithub objects representing a typical Pull Request."""
    # Mock author
    mock_author = MagicMock()
    mock_author.name = "Alice Developer"
    mock_author.email = "alice@example.com"
    mock_author.date = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Mock commit payload
    mock_commit_data = MagicMock()
    mock_commit_data.message = "fix: update calculation logic and fix issue #42"
    mock_commit_data.author = mock_author

    # Mock commit object
    mock_commit = MagicMock()
    mock_commit.sha = "a1b2c3d4e5f67890123456789abcdef012345678"
    mock_commit.commit = mock_commit_data

    # Mock file object 1
    mock_file1 = MagicMock()
    mock_file1.filename = "app/calculator.py"
    mock_file1.status = "modified"
    mock_file1.additions = 5
    mock_file1.deletions = 2
    mock_file1.changes = 7
    mock_file1.patch = "@@ -10,4 +10,7 @@\n-def add(a, b):\n-    return a - b\n+def add(a, b):\n+    return a + b\n"
    mock_file1.raw_url = "https://raw.githubusercontent.com/test/repo/app/calculator.py"
    mock_file1.previous_filename = None

    # Mock file object 2 (without patch - e.g. binary or renamed without edit)
    mock_file2 = MagicMock()
    mock_file2.filename = "assets/logo.png"
    mock_file2.status = "added"
    mock_file2.additions = 0
    mock_file2.deletions = 0
    mock_file2.changes = 0
    mock_file2.patch = None
    mock_file2.raw_url = "https://raw.githubusercontent.com/test/repo/assets/logo.png"
    mock_file2.previous_filename = None

    # Mock user
    mock_user = MagicMock()
    mock_user.login = "alicedev"

    # Mock branch refs
    mock_base = MagicMock()
    mock_base.ref = "main"
    mock_head = MagicMock()
    mock_head.ref = "bugfix/calc-repair"

    # Mock PR
    mock_pr = MagicMock()
    mock_pr.title = "Fix math bug in addition function"
    mock_pr.body = "This PR fixes a critical bug where addition was subtracting."
    mock_pr.user = mock_user
    mock_pr.state = "open"
    mock_pr.created_at = datetime(2026, 4, 1, 12, 10, 0, tzinfo=timezone.utc)
    mock_pr.updated_at = datetime(2026, 4, 1, 12, 20, 0, tzinfo=timezone.utc)
    mock_pr.merged_at = None
    mock_pr.base = mock_base
    mock_head = mock_head
    mock_pr.head = mock_head
    mock_pr.commits = 1
    mock_pr.changed_files = 2
    mock_pr.additions = 5
    mock_pr.deletions = 2

    mock_pr.get_files.return_value = [mock_file1, mock_file2]
    mock_pr.get_commits.return_value = [mock_commit]

    return {
        "pr": mock_pr,
        "files": [mock_file1, mock_file2],
        "commits": [mock_commit],
    }
