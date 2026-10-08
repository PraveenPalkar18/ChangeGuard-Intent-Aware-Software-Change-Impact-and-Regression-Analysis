"""GitHub Pull Request API routes."""
from fastapi import APIRouter, HTTPException, Depends
from backend.app.core.exceptions import (
    GitHubAuthenticationException,
    GitHubResourceNotFoundException,
    GitHubRateLimitExceededException,
    GitHubAPIException,
)
from backend.app.github.client import GitHubClient
from backend.app.github.importer import GitHubPRImporter
from backend.app.github.models import (
    PRImportRequest,
    PullRequestDetails,
)

router = APIRouter(prefix="/github", tags=["GitHub"])


def get_importer() -> GitHubPRImporter:
    """Dependency provider for GitHubPRImporter."""
    return GitHubPRImporter()


def get_client() -> GitHubClient:
    """Dependency provider for GitHubClient."""
    return GitHubClient()


@router.post(
    "/pull-request/import",
    response_model=PullRequestDetails,
    summary="Import GitHub Pull Request by payload",
    description="Fetches PR title, description, commits, changed files, and unified diff patches.",
)
def import_pr_by_payload(
    payload: PRImportRequest,
    importer: GitHubPRImporter = Depends(get_importer),
):
    try:
        return importer.import_pull_request(
            owner=payload.owner,
            repo=payload.repo,
            pr_number=payload.pr_number,
        )
    except GitHubAuthenticationException as exc:
        raise HTTPException(status_code=401, detail={"error": exc.message, "details": exc.details})
    except GitHubResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail={"error": exc.message, "details": exc.details})
    except GitHubRateLimitExceededException as exc:
        raise HTTPException(status_code=429, detail={"error": exc.message, "details": exc.details})
    except GitHubAPIException as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.message, "details": exc.details})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(exc)}"})


@router.get(
    "/pull-request/{owner}/{repo}/{pr_number}",
    response_model=PullRequestDetails,
    summary="Import GitHub Pull Request by path parameters",
    description="Convenience GET endpoint to inspect a Pull Request directly via URL parameters.",
)
def import_pr_by_path(
    owner: str,
    repo: str,
    pr_number: int,
    importer: GitHubPRImporter = Depends(get_importer),
):
    try:
        return importer.import_pull_request(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
        )
    except GitHubAuthenticationException as exc:
        raise HTTPException(status_code=401, detail={"error": exc.message, "details": exc.details})
    except GitHubResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail={"error": exc.message, "details": exc.details})
    except GitHubRateLimitExceededException as exc:
        raise HTTPException(status_code=429, detail={"error": exc.message, "details": exc.details})
    except GitHubAPIException as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.message, "details": exc.details})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(exc)}"})


@router.get(
    "/rate-limit",
    summary="Check GitHub API rate limit status",
    description="Returns current core rate limit quota, remaining requests, and reset timestamp.",
)
def check_rate_limit(client: GitHubClient = Depends(get_client)):
    return client.get_rate_limit_info()
