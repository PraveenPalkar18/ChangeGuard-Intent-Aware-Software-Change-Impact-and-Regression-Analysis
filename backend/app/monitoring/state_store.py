"""Thread-safe persistent local storage for monitoring configuration and PR states (Milestone 8)."""
import os
import json
import logging
from threading import Lock
from typing import Dict, List, Optional
from datetime import datetime, timezone

from backend.app.core.config import settings
from backend.app.monitoring.models import (
    RepoConfig,
    PRStateRecord,
    PRProcessingStatus,
)

logger = logging.getLogger("changeguard.monitoring.state")


class MonitoringStateStore:
    """Local JSON-backed persistent store for repository configs and analyzed PR state records."""

    def __init__(self, file_path: Optional[str] = None):
        self._file_path = file_path or settings.MONITORING_STATE_FILE
        self._lock = Lock()
        self._repos: Dict[str, RepoConfig] = {}
        self._records: Dict[str, PRStateRecord] = {}  # key: "owner/repo#pr_number"
        self._load_from_disk()

    @property
    def file_path(self) -> str:
        return self._file_path

    # -------------------------------------------------------------------------
    # Repository Configuration Operations
    # -------------------------------------------------------------------------

    def get_repo_configs(self) -> List[RepoConfig]:
        with self._lock:
            return list(self._repos.values())

    def get_repo_config(self, owner: str, repo: str) -> Optional[RepoConfig]:
        key = f"{owner.strip().lower()}/{repo.strip().lower()}"
        with self._lock:
            return self._repos.get(key)

    def set_repo_config(self, config: RepoConfig) -> None:
        key = config.key
        with self._lock:
            self._repos[key] = config
            self._save_to_disk_unlocked()

    def remove_repo_config(self, owner: str, repo: str) -> bool:
        key = f"{owner.strip().lower()}/{repo.strip().lower()}"
        with self._lock:
            if key in self._repos:
                del self._repos[key]
                self._save_to_disk_unlocked()
                return True
            return False

    # -------------------------------------------------------------------------
    # PR State Record Operations
    # -------------------------------------------------------------------------

    def get_pr_record(self, owner: str, repo: str, pr_number: int) -> Optional[PRStateRecord]:
        key = self._pr_record_key(owner, repo, pr_number)
        with self._lock:
            return self._records.get(key)

    def save_pr_record(self, record: PRStateRecord) -> None:
        key = f"{record.repo_key.lower()}#{record.pr_number}"
        with self._lock:
            self._records[key] = record
            self._save_to_disk_unlocked()

    def list_pr_records(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        status: Optional[PRProcessingStatus] = None,
    ) -> List[PRStateRecord]:
        with self._lock:
            results = list(self._records.values())

        if owner and repo:
            target_key = f"{owner.strip().lower()}/{repo.strip().lower()}"
            results = [r for r in results if r.repo_key.lower() == target_key]
        elif owner:
            owner_prefix = f"{owner.strip().lower()}/"
            results = [r for r in results if r.repo_key.lower().startswith(owner_prefix)]

        if status:
            results = [r for r in results if r.status == status]

        # Sort: newest analyzed/polled first
        results.sort(key=lambda r: (r.last_analyzed_at or r.last_polled_at or ""), reverse=True)
        return results

    def clear(self) -> None:
        """Clears all stored records and configurations (useful for test isolation)."""
        with self._lock:
            self._repos.clear()
            self._records.clear()
            self._save_to_disk_unlocked()

    # -------------------------------------------------------------------------
    # Disk I/O with Atomic Writes
    # -------------------------------------------------------------------------

    def _pr_record_key(self, owner: str, repo: str, pr_number: int) -> str:
        return f"{owner.strip().lower()}/{repo.strip().lower()}#{pr_number}"

    def _load_from_disk(self) -> None:
        """Read state from JSON file if present."""
        if not os.path.exists(self._file_path):
            # Seed initial repositories from MONITORED_REPOSITORIES config if specified
            if settings.MONITORED_REPOSITORIES:
                for entry in settings.MONITORED_REPOSITORIES.split(","):
                    entry = entry.strip()
                    if "/" in entry:
                        o, r = entry.split("/", 1)
                        conf = RepoConfig(
                            owner=o.strip(),
                            repo=r.strip(),
                            enabled=True,
                            poll_interval_seconds=settings.MONITORING_POLL_INTERVAL_SECONDS,
                        )
                        self._repos[conf.key] = conf
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            repos_raw = payload.get("repositories", {})
            records_raw = payload.get("records", {})

            for k, v in repos_raw.items():
                self._repos[k] = RepoConfig(**v)

            for k, v in records_raw.items():
                self._records[k] = PRStateRecord(**v)

            logger.info(f"Loaded {len(self._repos)} repos and {len(self._records)} PR records from {self._file_path}")
        except Exception as exc:
            logger.warning(f"Could not load state from {self._file_path} ({exc}). Initializing fresh store.")

    def _save_to_disk_unlocked(self) -> None:
        """Atomic write using temporary file and atomic rename."""
        try:
            target_dir = os.path.dirname(os.path.abspath(self._file_path))
            os.makedirs(target_dir, exist_ok=True)

            payload = {
                "version": "1.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "repositories": {k: v.model_dump() for k, v in self._repos.items()},
                "records": {k: v.model_dump() for k, v in self._records.items()},
            }

            temp_file = f"{self._file_path}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)

            # Atomic replace on Windows & POSIX
            os.replace(temp_file, self._file_path)
        except Exception as exc:
            logger.error(f"Failed to persist monitoring state to {self._file_path}: {exc}")
