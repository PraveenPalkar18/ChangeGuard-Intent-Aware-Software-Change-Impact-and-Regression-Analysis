"""FastAPI endpoints for GitHub PR Monitoring, State Inspection, and Reporting (Milestones 8 & 9)."""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query

from backend.app.core.config import settings
from backend.app.monitoring.models import (
    MonitoringStatus,
    RepoConfig,
    MonitoredRepoRequest,
    PRStateRecord,
    PRProcessingStatus,
)
from backend.app.monitoring.poller import PRPollingWorker, get_polling_worker

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Dashboard"])


@router.get("/status", response_model=MonitoringStatus, summary="Get background monitoring status")
def get_status(worker: PRPollingWorker = Depends(get_polling_worker)):
    return worker.get_status()


@router.post("/start", summary="Start background PR monitoring worker")
def start_worker(worker: PRPollingWorker = Depends(get_polling_worker)):
    started = worker.start()
    return {"status": "started" if started else "already_running", "is_running": worker.is_running}


@router.post("/stop", summary="Stop background PR monitoring worker")
def stop_worker(worker: PRPollingWorker = Depends(get_polling_worker)):
    stopped = worker.stop()
    return {"status": "stopped" if stopped else "already_stopped", "is_running": worker.is_running}


@router.post("/poll", summary="Trigger an immediate manual polling cycle")
def trigger_poll(worker: PRPollingWorker = Depends(get_polling_worker)):
    summary = worker.poll_once()
    return {"status": "poll_completed", "summary": summary}


@router.get("/repositories", response_model=List[RepoConfig], summary="List monitored repositories")
def list_repositories(worker: PRPollingWorker = Depends(get_polling_worker)):
    return worker.state_store.get_repo_configs()


@router.post("/repositories", response_model=RepoConfig, summary="Add or update monitored repository")
def add_repository(payload: MonitoredRepoRequest, worker: PRPollingWorker = Depends(get_polling_worker)):
    interval = payload.poll_interval_seconds or settings.MONITORING_POLL_INTERVAL_SECONDS
    config = RepoConfig(
        owner=payload.owner.strip(),
        repo=payload.repo.strip(),
        enabled=payload.enabled,
        poll_interval_seconds=interval,
        pr_state=payload.pr_state or "all",
    )
    worker.state_store.set_repo_config(config)
    return config


@router.delete("/repositories/{owner}/{repo}", summary="Remove repository from monitoring")
def delete_repository(owner: str, repo: str, worker: PRPollingWorker = Depends(get_polling_worker)):
    removed = worker.state_store.remove_repo_config(owner, repo)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Repository '{owner}/{repo}' not in monitoring list.")
    return {"status": "removed", "repository": f"{owner}/{repo}"}


@router.get("/prs", response_model=List[PRStateRecord], summary="List tracked PR state records")
def list_prs(
    owner: Optional[str] = Query(None, description="Filter by repository owner"),
    repo: Optional[str] = Query(None, description="Filter by repository name"),
    status: Optional[PRProcessingStatus] = Query(None, description="Filter by processing state"),
    worker: PRPollingWorker = Depends(get_polling_worker),
):
    return worker.state_store.list_pr_records(owner=owner, repo=repo, status=status)


@router.get("/prs/{owner}/{repo}/{pr_number}", response_model=PRStateRecord, summary="Get PR state and full analysis report")
def get_pr_record(owner: str, repo: str, pr_number: int, worker: PRPollingWorker = Depends(get_polling_worker)):
    record = worker.state_store.get_pr_record(owner, repo, pr_number)
    if not record:
        raise HTTPException(status_code=404, detail=f"PR #{pr_number} for '{owner}/{repo}' not found in state store.")
    return record


@router.post("/prs/{owner}/{repo}/{pr_number}/reanalyze", response_model=PRStateRecord, summary="Force immediate re-analysis of a PR")
def reanalyze_pr(owner: str, repo: str, pr_number: int, worker: PRPollingWorker = Depends(get_polling_worker)):
    record = worker.state_store.get_pr_record(owner, repo, pr_number)
    head_sha = record.head_sha if record else "HEAD"
    title = record.title if record else ""
    author = record.author if record else ""

    worker._process_single_pr(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        title=title,
        author=author,
        existing_record=record,
    )
    updated = worker.state_store.get_pr_record(owner, repo, pr_number)
    if not updated:
        raise HTTPException(status_code=500, detail="Re-analysis failed to produce state record.")
    return updated


@router.post("/prs/{owner}/{repo}/{pr_number}/comment", summary="Post analysis markdown report to GitHub PR (if reporting enabled)")
def post_github_comment(owner: str, repo: str, pr_number: int, worker: PRPollingWorker = Depends(get_polling_worker)):
    """Post markdown summary to GitHub PR issue comments if ENABLE_GITHUB_REPORTING is True."""
    if not settings.ENABLE_GITHUB_REPORTING:
        return {
            "status": "disabled",
            "message": "GitHub write reporting is disabled by default. Set ENABLE_GITHUB_REPORTING=True in .env to enable.",
        }

    record = worker.state_store.get_pr_record(owner, repo, pr_number)
    if not record or not record.analysis_report:
        raise HTTPException(status_code=404, detail="PR analysis report not found in local store.")

    rep = record.analysis_report
    risk = rep.risk_assessment.overall_risk_level if rep.risk_assessment else "UNKNOWN"
    score = rep.risk_assessment.overall_risk_score if rep.risk_assessment else 0.0

    markdown_comment = (
        f"### 🛡️ ChangeGuard Analysis Report\n\n"
        f"**Risk Level:** `{risk}` (Score: `{score:.2f}`)\n"
        f"**Intent Summary:** {rep.overall_intent_summary}\n\n"
        f"- **Files Analyzed:** {rep.total_files_analyzed}\n"
        f"- **Hunks Analyzed:** {rep.total_hunks_analyzed} ({rep.explained_count} explained, {rep.unexplained_count} unexplained, {rep.uncertain_count} uncertain)\n"
    )
    if rep.test_selection and rep.test_selection.recommended_tests:
        markdown_comment += f"- **Targeted Regression Tests Recommended:** {len(rep.test_selection.recommended_tests)}\n"

    success = worker._github_client.post_pull_request_comment(owner, repo, pr_number, markdown_comment)
    return {
        "status": "posted" if success else "failed",
        "repository": f"{owner}/{repo}",
        "pr_number": pr_number,
    }
