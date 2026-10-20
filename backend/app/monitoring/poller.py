"""Background Pull Request Polling Worker (Milestone 8)."""
import time
import asyncio
import logging
from threading import Thread, Event
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from backend.app.core.config import settings
from backend.app.github.client import GitHubClient
from backend.app.analysis.service import ChangeGuardAnalysisService
from backend.app.monitoring.models import (
    RepoConfig,
    PRStateRecord,
    PRProcessingStatus,
    MonitoringStatus,
)
from backend.app.monitoring.state_store import MonitoringStateStore

logger = logging.getLogger("changeguard.monitoring.worker")


class PRPollingWorker:
    """Background polling worker monitoring configured GitHub repositories for PR revisions."""

    def __init__(
        self,
        state_store: Optional[MonitoringStateStore] = None,
        github_client: Optional[GitHubClient] = None,
        analysis_service: Optional[ChangeGuardAnalysisService] = None,
        poll_interval_seconds: Optional[int] = None,
    ):
        self._state_store = state_store or MonitoringStateStore()
        self._github_client = github_client or GitHubClient()
        self._analysis_service = analysis_service or ChangeGuardAnalysisService(github_client=self._github_client)
        self._poll_interval = poll_interval_seconds or settings.MONITORING_POLL_INTERVAL_SECONDS
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._last_poll_time: Optional[str] = None
        self._last_successful_poll_time: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_poll_summary: Optional[Dict[str, Any]] = None
        self._is_polling = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def state_store(self) -> MonitoringStateStore:
        return self._state_store

    def start(self) -> bool:
        """Start background polling thread if not already active."""
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop_event.clear()
        self._thread = Thread(target=self._run_loop, name="ChangeGuardPRPoller", daemon=True)
        self._thread.start()
        logger.info(f"PR Polling Worker started (interval: {self._poll_interval}s)")
        return True

    def stop(self) -> bool:
        """Signal background polling thread to stop."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = None
            return False
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            logger.warning("PR Polling Worker thread did not terminate within timeout.")
            return False
        self._thread = None
        logger.info("PR Polling Worker stopped")
        return True

    def get_status(self) -> MonitoringStatus:
        """Return operational status and PR processing statistics."""
        repos = self._state_store.get_repo_configs()
        records = self._state_store.list_pr_records()

        pending = sum(1 for r in records if r.status == PRProcessingStatus.PENDING)
        running = sum(1 for r in records if r.status == PRProcessingStatus.RUNNING)
        completed = sum(1 for r in records if r.status == PRProcessingStatus.COMPLETED)
        failed = sum(1 for r in records if r.status == PRProcessingStatus.FAILED)

        return MonitoringStatus(
            is_running=self.is_running,
            is_polling=self._is_polling,
            poll_interval_seconds=self._poll_interval,
            monitored_repos=repos,
            last_poll_time=self._last_poll_time,
            last_successful_poll_time=self._last_successful_poll_time,
            last_error=self._last_error,
            last_poll_summary=self._last_poll_summary,
            total_prs_tracked=len(records),
            pending_count=pending,
            running_count=running,
            completed_count=completed,
            failed_count=failed,
        )

    # -------------------------------------------------------------------------
    # Core Polling Cycle
    # -------------------------------------------------------------------------

    def poll_once(self) -> Dict[str, Any]:
        """Execute a single polling cycle across all enabled repositories.

        Returns:
            Dictionary summarizing repositories checked, PRs analyzed, and errors.
        """
        self._is_polling = True
        cycle_start = datetime.now(timezone.utc).isoformat()
        self._last_poll_time = cycle_start
        summary: Dict[str, Any] = {
            "timestamp": cycle_start,
            "repos_checked": 0,
            "prs_discovered": 0,
            "prs_analyzed": 0,
            "prs_skipped": 0,
            "errors": [],
        }

        try:
            # Check rate limit quota before beginning
            rl_info = self._github_client.get_rate_limit_info()
            remaining = rl_info.get("remaining")
            if remaining is not None and remaining < 5:
                msg = f"GitHub API rate limit critical ({remaining} remaining). Skipping poll cycle until reset."
                logger.warning(msg)
                summary["errors"].append(msg)
                self._last_error = msg
                self._last_poll_summary = summary
                return summary

            repos = [r for r in self._state_store.get_repo_configs() if r.enabled]
            for repo_conf in repos:
                summary["repos_checked"] += 1
                try:
                    target_state = getattr(repo_conf, "pr_state", "open") or "open"
                    pull_requests = self._github_client.get_pull_requests(
                        owner=repo_conf.owner,
                        repo=repo_conf.repo,
                        state=target_state,
                    )
                    summary["prs_discovered"] += len(pull_requests)

                    for pr in pull_requests:
                        pr_num = pr.number
                        head_sha = getattr(getattr(pr, "head", None), "sha", None) or f"sha_{pr_num}"
                        title = pr.title or ""
                        author = getattr(getattr(pr, "user", None), "login", "") if hasattr(pr, "user") else ""

                        # Inspect existing record in state store
                        existing_record = self._state_store.get_pr_record(repo_conf.owner, repo_conf.repo, pr_num)

                        # Decision logic: Should this PR revision be analyzed?
                        should_analyze = False
                        if not existing_record:
                            # Newly discovered PR
                            should_analyze = True
                        elif existing_record.head_sha != head_sha:
                            # Updated PR revision (new commit pushed)
                            should_analyze = True
                        elif existing_record.status == PRProcessingStatus.PENDING:
                            should_analyze = True
                        elif existing_record.status == PRProcessingStatus.FAILED and existing_record.retry_count < settings.MAX_PROCESSING_RETRIES:
                            should_analyze = True
                        else:
                            # Existing unchanged PR with completed or exhausted status -> skip
                            summary["prs_skipped"] += 1

                        if should_analyze:
                            self._process_single_pr(
                                owner=repo_conf.owner,
                                repo=repo_conf.repo,
                                pr_number=pr_num,
                                head_sha=head_sha,
                                title=title,
                                author=author,
                                existing_record=existing_record,
                            )
                            summary["prs_analyzed"] += 1

                except Exception as exc:
                    err_msg = f"Error polling repository {repo_conf.key}: {str(exc)}"
                    logger.error(err_msg)
                    summary["errors"].append(err_msg)

            if summary["errors"]:
                self._last_error = "; ".join(summary["errors"])
            else:
                self._last_error = None
                self._last_successful_poll_time = cycle_start

            self._last_poll_summary = summary
            return summary
        finally:
            self._is_polling = False

    def _process_single_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        head_sha: str,
        title: str,
        author: str,
        existing_record: Optional[PRStateRecord],
    ) -> None:
        """Trigger analysis for a PR and persist state updates."""
        now_iso = datetime.now(timezone.utc).isoformat()
        retry_count = (existing_record.retry_count if existing_record else 0)

        # Mark as RUNNING
        running_rec = PRStateRecord(
            repo_key=f"{owner}/{repo}",
            pr_number=pr_number,
            head_sha=head_sha,
            title=title,
            author=author,
            status=PRProcessingStatus.RUNNING,
            retry_count=retry_count,
            created_at=existing_record.created_at if existing_record else now_iso,
            last_polled_at=now_iso,
            last_analyzed_at=existing_record.last_analyzed_at if existing_record else None,
            analysis_report=existing_record.analysis_report if existing_record else None,
        )
        self._state_store.save_pr_record(running_rec)

        try:
            logger.info(f"Triggering ChangeGuard analysis for {owner}/{repo} PR #{pr_number} (head: {head_sha[:7]})")
            report = self._analysis_service.analyze_pull_request(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                fetch_source_files=True,
            )

            # Mark as COMPLETED
            completed_rec = PRStateRecord(
                repo_key=f"{owner}/{repo}",
                pr_number=pr_number,
                head_sha=head_sha,
                title=title or report.title,
                author=author or report.author,
                status=PRProcessingStatus.COMPLETED,
                retry_count=0,
                created_at=running_rec.created_at,
                last_polled_at=now_iso,
                last_analyzed_at=now_iso,
                error_message=None,
                analysis_report=report,
            )
            self._state_store.save_pr_record(completed_rec)
            logger.info(f"Successfully analyzed {owner}/{repo} PR #{pr_number}")

        except Exception as exc:
            err_str = str(exc)
            logger.error(f"Analysis failed for {owner}/{repo} PR #{pr_number}: {err_str}")

            failed_rec = PRStateRecord(
                repo_key=f"{owner}/{repo}",
                pr_number=pr_number,
                head_sha=head_sha,
                title=title,
                author=author,
                status=PRProcessingStatus.FAILED,
                retry_count=retry_count + 1,
                created_at=running_rec.created_at,
                last_polled_at=now_iso,
                last_analyzed_at=running_rec.last_analyzed_at,
                error_message=err_str,
                analysis_report=None,
            )
            self._state_store.save_pr_record(failed_rec)

    def _run_loop(self) -> None:
        """Internal daemon polling loop."""
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                logger.error(f"Unhandled exception in polling loop: {exc}")

            # Sleep in small slices to respond promptly to stop_event
            sleep_chunks = max(1, self._poll_interval)
            for _ in range(sleep_chunks):
                if self._stop_event.is_set():
                    break
                time.sleep(1)


# Global worker instance singleton
_global_poller: Optional[PRPollingWorker] = None


def get_polling_worker() -> PRPollingWorker:
    """Obtain or instantiate global PRPollingWorker."""
    global _global_poller
    if _global_poller is None:
        _global_poller = PRPollingWorker()
    return _global_poller
