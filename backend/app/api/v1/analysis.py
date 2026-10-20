"""FastAPI routes for End-to-End Pull Request Analysis."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from backend.app.core.exceptions import (
    GitHubAuthenticationException,
    GitHubResourceNotFoundException,
    GitHubRateLimitExceededException,
    GitHubAPIException,
)
from backend.app.analysis.models import (
    PRAnalysisRequest,
    PRAnalysisReport,
)
from backend.app.analysis.service import ChangeGuardAnalysisService

from datetime import datetime, timezone
from backend.app.monitoring.state_store import MonitoringStateStore
from backend.app.monitoring.models import PRStateRecord, PRProcessingStatus

router = APIRouter(prefix="/analyze", tags=["Analysis"])


def get_analysis_service() -> ChangeGuardAnalysisService:
    """Dependency provider for ChangeGuardAnalysisService."""
    return ChangeGuardAnalysisService()


def _save_to_state_store(owner: str, repo: str, pr_number: int, report: PRAnalysisReport) -> None:
    """Helper to save on-demand analysis results into the persistent local store."""
    try:
        store = MonitoringStateStore()
        now_iso = datetime.now(timezone.utc).isoformat()
        rec = PRStateRecord(
            repo_key=f"{owner}/{repo}",
            pr_number=pr_number,
            head_sha=report.head_branch or "HEAD",
            title=report.title or "",
            author=report.author or "",
            status=PRProcessingStatus.COMPLETED,
            retry_count=0,
            created_at=now_iso,
            last_polled_at=now_iso,
            last_analyzed_at=now_iso,
            error_message=None,
            analysis_report=report,
        )
        store.save_pr_record(rec)
    except Exception:
        # Non-fatal: if state persistence fails, analysis report is still returned
        pass


@router.post(
    "/pull-request",
    response_model=PRAnalysisReport,
    summary="Run End-to-End Intent & Impact Analysis on a GitHub Pull Request",
    description="Imports PR, parses diff hunks, runs AST entity extraction, and evaluates intent alignment per hunk.",
)
def analyze_pr_by_payload(
    payload: PRAnalysisRequest,
    service: ChangeGuardAnalysisService = Depends(get_analysis_service),
):
    try:
        report = service.analyze_pull_request(
            owner=payload.owner,
            repo=payload.repo,
            pr_number=payload.pr_number,
            fetch_source_files=payload.fetch_source_files,
            provider_name=payload.provider_name,
        )
        _save_to_state_store(payload.owner, payload.repo, payload.pr_number, report)
        return report
    except GitHubAuthenticationException as exc:
        raise HTTPException(status_code=401, detail={"error": exc.message, "details": exc.details})
    except GitHubResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail={"error": exc.message, "details": exc.details})
    except GitHubRateLimitExceededException as exc:
        raise HTTPException(status_code=429, detail={"error": exc.message, "details": exc.details})
    except GitHubAPIException as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.message, "details": exc.details})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"Analysis execution error: {str(exc)}"})


@router.get(
    "/pull-request/{owner}/{repo}/{pr_number}",
    response_model=PRAnalysisReport,
    summary="Run End-to-End Analysis on a GitHub PR (GET shortcut)",
    description="Convenience GET endpoint allowing instant browser or curl execution of PR analysis.",
)
def analyze_pr_by_path(
    owner: str,
    repo: str,
    pr_number: int,
    fetch_source: bool = True,
    provider: Optional[str] = None,
    service: ChangeGuardAnalysisService = Depends(get_analysis_service),
):
    try:
        report = service.analyze_pull_request(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            fetch_source_files=fetch_source,
            provider_name=provider,
        )
        _save_to_state_store(owner, repo, pr_number, report)
        return report
    except GitHubAuthenticationException as exc:
        raise HTTPException(status_code=401, detail={"error": exc.message, "details": exc.details})
    except GitHubResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail={"error": exc.message, "details": exc.details})
    except GitHubRateLimitExceededException as exc:
        raise HTTPException(status_code=429, detail={"error": exc.message, "details": exc.details})
    except GitHubAPIException as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.message, "details": exc.details})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"Analysis execution error: {str(exc)}"})
