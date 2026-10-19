"""Abstract Intent Analyzer interface."""
from abc import ABC, abstractmethod
from typing import List
from backend.app.intent.models import (
    PRContext,
    HunkContext,
    HunkIntentResult,
    PRIntentReport,
)


class BaseIntentAnalyzer(ABC):
    """High-level abstraction for Intent Analysis operations."""

    @abstractmethod
    def analyze_hunk(
        self,
        pr_context: PRContext,
        hunk_context: HunkContext,
    ) -> HunkIntentResult:
        """Analyze a single diff hunk against the stated Pull Request intent.

        Args:
            pr_context: Stated PR title, description, and commit messages.
            hunk_context: Diff hunk, enclosing code entity, and file path.

        Returns:
            HunkIntentResult with classification, confidence, and explainable evidence.
        """
        pass

    @abstractmethod
    def analyze_pull_request(
        self,
        pr_context: PRContext,
        hunk_contexts: List[HunkContext],
        pr_number: int = 0,
    ) -> PRIntentReport:
        """Perform intent analysis across all hunks in a Pull Request.

        Args:
            pr_context: Stated PR intent.
            hunk_contexts: List of hunk contexts from all changed files.
            pr_number: Optional PR identifier.

        Returns:
            PRIntentReport summarizing hunk results and overall alignment.
        """
        pass
