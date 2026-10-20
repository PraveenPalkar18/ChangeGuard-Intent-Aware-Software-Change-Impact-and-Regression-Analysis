"""Data models for GitHub PR Background Monitoring and State Tracking (Milestone 8)."""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.app.analysis.models import PRAnalysisReport


class PRProcessingStatus(str, Enum):
    """Lifecycle status of a Pull Request in the monitoring and analysis pipeline."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RepoConfig(BaseModel):
    """Configuration for a repository monitored by ChangeGuard."""
    owner: str = Field(..., description="Repository owner or organization")
    repo: str = Field(..., description="Repository name")
    enabled: bool = Field(default=True, description="Whether polling is active for this repository")
    poll_interval_seconds: int = Field(default=60, gt=5, description="Polling frequency in seconds")
    pr_state: str = Field(default="open", description="PR state filter: 'all', 'open', or 'closed'")

    @property
    def key(self) -> str:
        return f"{self.owner.strip().lower()}/{self.repo.strip().lower()}"


class PRStateRecord(BaseModel):
    """Persistent state record for a tracked Pull Request."""
    repo_key: str = Field(..., description="'owner/repo' key")
    pr_number: int = Field(..., gt=0, description="Pull Request number")
    head_sha: str = Field(..., description="Head commit SHA analyzed or pending")
    title: str = Field(default="", description="PR title")
    author: str = Field(default="", description="PR author username")
    status: PRProcessingStatus = Field(default=PRProcessingStatus.PENDING, description="Current processing state")
    retry_count: int = Field(default=0, ge=0, description="Number of failed analysis attempts")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of record creation")
    last_polled_at: Optional[str] = Field(default=None, description="ISO timestamp of last poll check")
    last_analyzed_at: Optional[str] = Field(default=None, description="ISO timestamp of last successful analysis")
    error_message: Optional[str] = Field(default=None, description="Error message if status is FAILED")
    analysis_report: Optional[PRAnalysisReport] = Field(default=None, description="Full analysis report if completed")


class MonitoringStatus(BaseModel):
    """Health and operational status of the background monitoring worker."""
    is_running: bool = Field(..., description="Whether background polling loop is active")
    is_polling: bool = Field(default=False, description="Whether a polling cycle is actively executing")
    poll_interval_seconds: int = Field(..., description="Active polling interval in seconds")
    monitored_repos: List[RepoConfig] = Field(default_factory=list, description="List of configured repositories")
    last_poll_time: Optional[str] = Field(default=None, description="ISO timestamp of most recent polling cycle")
    last_successful_poll_time: Optional[str] = Field(default=None, description="ISO timestamp of last error-free polling cycle")
    last_error: Optional[str] = Field(default=None, description="Most recent error message during polling")
    last_poll_summary: Optional[Dict[str, Any]] = Field(default=None, description="Summary details of most recent poll cycle")
    total_prs_tracked: int = Field(default=0, description="Total PR revisions recorded in local state store")
    pending_count: int = Field(default=0, description="PRs queued for analysis")
    running_count: int = Field(default=0, description="PRs currently being analyzed")
    completed_count: int = Field(default=0, description="PRs successfully analyzed")
    failed_count: int = Field(default=0, description="PRs that failed processing")


class MonitoredRepoRequest(BaseModel):
    """Payload to register or update a monitored repository."""
    owner: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=100)
    enabled: bool = Field(default=True)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    pr_state: Optional[str] = Field(default="all", description="PR state to monitor: 'all', 'open', or 'closed'")
