"""Data models for GitHub Pull Request import and inspection."""
from typing import List, Optional
from pydantic import BaseModel, Field


class PRFileChange(BaseModel):
    """Details of a single file altered in a Pull Request."""

    filename: str = Field(..., description="File path relative to repository root")
    status: str = Field(..., description="File change status (e.g. modified, added, removed, renamed)")
    additions: int = Field(default=0, description="Count of added lines in file")
    deletions: int = Field(default=0, description="Count of removed lines in file")
    changes: int = Field(default=0, description="Total count of line modifications")
    patch: Optional[str] = Field(default=None, description="Raw git unified diff patch hunk text")
    raw_url: Optional[str] = Field(default=None, description="URL to raw contents of the file")
    previous_filename: Optional[str] = Field(default=None, description="Original filename if renamed")


class PRCommit(BaseModel):
    """Commit summary associated with a Pull Request."""

    sha: str = Field(..., description="Commit SHA-1 hash")
    message: str = Field(..., description="Commit message")
    author_name: Optional[str] = Field(default=None, description="Author's git commit name")
    author_email: Optional[str] = Field(default=None, description="Author's git commit email")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp of commit commit date")


class PRImportRequest(BaseModel):
    """Request payload to import a GitHub Pull Request."""

    owner: str = Field(..., min_length=1, max_length=100, description="GitHub repository owner or organization")
    repo: str = Field(..., min_length=1, max_length=100, description="GitHub repository name")
    pr_number: int = Field(..., gt=0, description="Pull Request number (positive integer)")


class PullRequestDetails(BaseModel):
    """Complete structured metadata and diff contents of an imported Pull Request."""

    owner: str
    repo: str
    pr_number: int
    title: str
    description: Optional[str] = None
    author: str
    state: str
    created_at: str
    updated_at: Optional[str] = None
    merged_at: Optional[str] = None
    base_branch: str
    head_branch: str
    base_sha: Optional[str] = None
    head_sha: Optional[str] = None
    commits_count: int
    changed_files_count: int
    total_additions: int
    total_deletions: int
    commits: List[PRCommit] = Field(default_factory=list)
    files: List[PRFileChange] = Field(default_factory=list)
