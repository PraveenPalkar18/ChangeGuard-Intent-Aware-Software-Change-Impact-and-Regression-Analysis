"""GitHub API client wrapper with standardized error handling."""
from typing import Optional
from github import Github, GithubException, Auth
from github.GithubException import (
    RateLimitExceededException,
    BadCredentialsException,
    UnknownObjectException,
)
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    GitHubAuthenticationException,
    GitHubRateLimitExceededException,
    GitHubResourceNotFoundException,
    GitHubAPIException,
)


class GitHubClient:
    """Wrapper around PyGithub providing standardized error translation and read-only access."""

    def __init__(self, token: Optional[str] = None):
        auth_token = token if token is not None else settings.GITHUB_TOKEN
        if auth_token and auth_token.strip():
            auth = Auth.Token(auth_token.strip())
            self._client = Github(auth=auth, timeout=settings.GITHUB_TIMEOUT_SECONDS)
        else:
            # Unauthenticated client - restricted to 60 req/hour
            self._client = Github(timeout=settings.GITHUB_TIMEOUT_SECONDS)

    @property
    def raw_client(self) -> Github:
        """Access underlying PyGithub client."""
        return self._client

    def get_pull_request(self, owner: str, repo: str, pr_number: int):
        """Fetch a specific Pull Request object by owner, repository name, and PR number.

        Raises:
            GitHubAuthenticationException: If credentials are bad (401).
            GitHubResourceNotFoundException: If repository or PR not found (404).
            GitHubRateLimitExceededException: If rate limits hit (403/429).
            GitHubAPIException: For other upstream GitHub errors.
        """
        full_repo_name = f"{owner}/{repo}"
        try:
            repository = self._client.get_repo(full_repo_name)
            pull_request = repository.get_pull(pr_number)
            return pull_request
        except BadCredentialsException as exc:
            raise GitHubAuthenticationException(
                message=f"GitHub authentication failed. Check your token.",
                details={"owner": owner, "repo": repo, "pr_number": pr_number, "error": str(exc)},
            ) from exc
        except UnknownObjectException as exc:
            raise GitHubResourceNotFoundException(
                message=f"Repository '{full_repo_name}' or PR #{pr_number} not found.",
                details={"owner": owner, "repo": repo, "pr_number": pr_number, "error": str(exc)},
            ) from exc
        except RateLimitExceededException as exc:
            raise GitHubRateLimitExceededException(
                message="GitHub API rate limit exceeded.",
                details={"owner": owner, "repo": repo, "pr_number": pr_number, "error": str(exc)},
            ) from exc
        except GithubException as exc:
            # Check status codes
            if exc.status == 401:
                raise GitHubAuthenticationException(
                    message="GitHub authentication failed.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            elif exc.status == 404:
                raise GitHubResourceNotFoundException(
                    message=f"Repository '{full_repo_name}' or PR #{pr_number} not found.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            elif exc.status in (403, 429) and "rate limit" in str(exc.data).lower():
                raise GitHubRateLimitExceededException(
                    message="GitHub API rate limit exceeded.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            raise GitHubAPIException(
                message=f"GitHub API error: {exc.data if hasattr(exc, 'data') else str(exc)}",
                status_code=exc.status or 502,
                details={"status": exc.status, "data": exc.data if hasattr(exc, "data") else str(exc)},
            ) from exc
        except Exception as exc:
            raise GitHubAPIException(
                message=f"Unexpected error communicating with GitHub: {str(exc)}",
                status_code=500,
                details={"error": str(exc)},
            ) from exc

    def get_rate_limit_info(self) -> dict:
        """Return remaining rate limit statistics."""
        try:
            rate_limit_obj = self._client.get_rate_limit()
            rate = getattr(rate_limit_obj, "rate", None) or getattr(rate_limit_obj, "core", None)
            if rate is None:
                return {"error": "Could not parse rate limit information"}
            return {
                "limit": rate.limit,
                "remaining": rate.remaining,
                "reset_time": rate.reset.isoformat() if rate.reset else None,
            }
        except Exception as exc:
            return {"error": str(exc)}

    def get_file_content(self, owner: str, repo: str, file_path: str, ref: Optional[str] = None) -> Optional[str]:
        """Fetch the decoded source content of a file from a repository at a specific commit or ref.

        Args:
            owner: GitHub repository owner.
            repo: GitHub repository name.
            file_path: Relative path to file in repo.
            ref: Git commit SHA or branch name.

        Returns:
            Decoded UTF-8 source string if file exists, or None if file not found / binary / deleted.
        """
        full_repo_name = f"{owner}/{repo}"
        try:
            repository = self._client.get_repo(full_repo_name)
            content_file = repository.get_contents(file_path, ref=ref) if ref else repository.get_contents(file_path)
            if content_file and hasattr(content_file, "decoded_content") and content_file.decoded_content:
                return content_file.decoded_content.decode("utf-8", errors="replace")
            return None
        except (UnknownObjectException, Exception):
            # Non-existent file at this ref (e.g. newly added file, deleted file) or network issue
            return None

    def get_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        sort: str = "updated",
        direction: str = "desc",
        max_results: int = 30,
    ):
        """Fetch list of pull requests for a repository with standardized error translation."""
        full_repo_name = f"{owner}/{repo}"
        try:
            repository = self._client.get_repo(full_repo_name)
            pulls_paginated = repository.get_pulls(state=state, sort=sort, direction=direction)
            results = []
            for p in pulls_paginated:
                results.append(p)
                if len(results) >= max_results:
                    break
            return results
        except BadCredentialsException as exc:
            raise GitHubAuthenticationException(
                message=f"GitHub authentication failed. Check your token.",
                details={"owner": owner, "repo": repo, "error": str(exc)},
            ) from exc
        except UnknownObjectException as exc:
            raise GitHubResourceNotFoundException(
                message=f"Repository '{full_repo_name}' not found.",
                details={"owner": owner, "repo": repo, "error": str(exc)},
            ) from exc
        except RateLimitExceededException as exc:
            raise GitHubRateLimitExceededException(
                message="GitHub API rate limit exceeded.",
                details={"owner": owner, "repo": repo, "error": str(exc)},
            ) from exc
        except GithubException as exc:
            if exc.status == 401:
                raise GitHubAuthenticationException(
                    message="GitHub authentication failed.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            elif exc.status == 404:
                raise GitHubResourceNotFoundException(
                    message=f"Repository '{full_repo_name}' not found.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            elif exc.status in (403, 429) and "rate limit" in str(exc.data).lower():
                raise GitHubRateLimitExceededException(
                    message="GitHub API rate limit exceeded.",
                    details={"status": exc.status, "data": exc.data},
                ) from exc
            raise GitHubAPIException(
                message=f"GitHub API error: {exc.data if hasattr(exc, 'data') else str(exc)}",
                status_code=exc.status or 502,
                details={"status": exc.status, "data": exc.data if hasattr(exc, "data") else str(exc)},
            ) from exc
        except Exception as exc:
            raise GitHubAPIException(
                message=f"Unexpected error communicating with GitHub: {str(exc)}",
                status_code=500,
                details={"error": str(exc)},
            ) from exc

    def post_pull_request_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment_body: str,
    ) -> bool:
        """Post a comment to a Pull Request if GitHub write reporting is enabled in settings."""
        if not settings.ENABLE_GITHUB_REPORTING:
            return False

        full_repo_name = f"{owner}/{repo}"
        try:
            repository = self._client.get_repo(full_repo_name)
            pr = repository.get_pull(pr_number)
            pr.create_issue_comment(comment_body)
            return True
        except Exception:
            return False

