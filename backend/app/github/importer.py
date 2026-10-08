"""Pull Request Importer service for retrieving PR metadata, diffs, and commits."""
from typing import Optional, List
from backend.app.github.client import GitHubClient
from backend.app.github.models import (
    PullRequestDetails,
    PRFileChange,
    PRCommit,
)


class GitHubPRImporter:
    """Extracts and structures PR data from GitHub."""

    def __init__(self, client: Optional[GitHubClient] = None):
        self._client = client or GitHubClient()

    def import_pull_request(self, owner: str, repo: str, pr_number: int) -> PullRequestDetails:
        """Fetch and structure all PR data including title, description, commits, and diff hunks.

        Args:
            owner: GitHub repository owner or organisation.
            repo: GitHub repository name.
            pr_number: Pull request number.

        Returns:
            PullRequestDetails with full metadata, changed files, patches, and commit history.
        """
        pr = self._client.get_pull_request(owner=owner, repo=repo, pr_number=pr_number)

        # Extract file changes and diff patches
        files: List[PRFileChange] = []
        for file in pr.get_files():
            files.append(
                PRFileChange(
                    filename=file.filename,
                    status=file.status,
                    additions=getattr(file, "additions", 0),
                    deletions=getattr(file, "deletions", 0),
                    changes=getattr(file, "changes", 0),
                    patch=getattr(file, "patch", None),
                    raw_url=getattr(file, "raw_url", None),
                    previous_filename=getattr(file, "previous_filename", None),
                )
            )

        # Extract commits
        commits: List[PRCommit] = []
        for commit in pr.get_commits():
            author_name = None
            author_email = None
            commit_date = None

            if commit.commit and commit.commit.author:
                author_name = commit.commit.author.name
                author_email = commit.commit.author.email
                if commit.commit.author.date:
                    commit_date = commit.commit.author.date.isoformat()

            commits.append(
                PRCommit(
                    sha=commit.sha,
                    message=commit.commit.message if commit.commit else "",
                    author_name=author_name,
                    author_email=author_email,
                    timestamp=commit_date,
                )
            )

        return PullRequestDetails(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=pr.title or "",
            description=pr.body or "",
            author=pr.user.login if pr.user else "unknown",
            state=pr.state or "unknown",
            created_at=pr.created_at.isoformat() if pr.created_at else "",
            updated_at=pr.updated_at.isoformat() if pr.updated_at else None,
            merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
            base_branch=pr.base.ref if pr.base else "",
            head_branch=pr.head.ref if pr.head else "",
            commits_count=getattr(pr, "commits", len(commits)),
            changed_files_count=getattr(pr, "changed_files", len(files)),
            total_additions=getattr(pr, "additions", sum(f.additions for f in files)),
            total_deletions=getattr(pr, "deletions", sum(f.deletions for f in files)),
            commits=commits,
            files=files,
        )
