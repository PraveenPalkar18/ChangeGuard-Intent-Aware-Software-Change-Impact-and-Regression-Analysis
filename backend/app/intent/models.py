"""Data models for AI Intent Analysis and Hunk Classification."""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.app.preprocessing.models import DiffHunk
from backend.app.repository.models import CodeEntity


class IntentClassification(str, Enum):
    """Classification of whether a change is explained by the PR intent."""
    EXPLAINED = "EXPLAINED"
    UNEXPLAINED = "UNEXPLAINED"
    UNCERTAIN = "UNCERTAIN"


class PRContext(BaseModel):
    """Contextual metadata describing the developer's stated intent."""
    pr_title: str = Field(default="", description="Pull Request title")
    pr_description: str = Field(default="", description="Pull Request markdown body")
    commit_messages: List[str] = Field(default_factory=list, description="Commit messages in the PR")

    @property
    def full_intent_text(self) -> str:
        """Combined intent text from title, description, and commit messages."""
        parts = []
        if self.pr_title.strip():
            parts.append(self.pr_title.strip())
        if self.pr_description.strip():
            parts.append(self.pr_description.strip())
        if self.commit_messages:
            parts.append(" ".join(m.strip() for m in self.commit_messages if m.strip()))
        return " ".join(parts).strip()


class HunkContext(BaseModel):
    """Contextual representation of a code hunk and its repository context."""
    file_path: str = Field(..., description="File path relative to repo root")
    hunk_index: int = Field(default=0, description="Hunk index within the file")
    hunk: DiffHunk = Field(..., description="Parsed diff hunk with line changes")
    enclosing_entity: Optional[CodeEntity] = Field(default=None, description="Enclosing AST entity from Tree-sitter")
    association_type: str = Field(default="file_level", description="'enclosing', 'overlapping', or 'file_level'")

    @property
    def code_representation(self) -> str:
        """Textual representation of code modification for similarity comparison."""
        parts = []
        # Include entity information if available
        if self.enclosing_entity:
            parts.append(f"{self.enclosing_entity.entity_type.value} {self.enclosing_entity.name}")
            if self.enclosing_entity.docstring:
                parts.append(self.enclosing_entity.docstring)
            if self.enclosing_entity.parameters:
                parts.append(" ".join(self.enclosing_entity.parameters))

        # Include added and deleted lines
        added = self.hunk.added_lines
        deleted = self.hunk.deleted_lines

        if added:
            parts.append(" ".join(added))
        if deleted:
            parts.append(" ".join(deleted))

        return " ".join(parts).strip()


class HunkIntentResult(BaseModel):
    """Final explainable intent analysis result for a single diff hunk."""
    hunk_index: int = Field(..., description="Index of analyzed hunk")
    file_path: str = Field(..., description="File path of analyzed hunk")
    classification: IntentClassification = Field(..., description="EXPLAINED, UNEXPLAINED, or UNCERTAIN")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Numerical confidence score")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Semantic or lexical similarity score")
    reason: str = Field(..., description="Concise explanation for the classification")
    evidence: List[str] = Field(default_factory=list, description="Supporting textual or code evidence")
    limitations: List[str] = Field(default_factory=list, description="Known limitations or caveats for this decision")
    model_used: str = Field(..., description="Model identifier used (e.g. 'tfidf-baseline', 'codebert-base')")
    provider_used: str = Field(..., description="Provider name (e.g. 'tfidf', 'transformers', 'mock')")
    raw_details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic provider-specific details")


class PRIntentReport(BaseModel):
    """Aggregate intent report for all hunks across a Pull Request."""
    pr_number: Optional[int] = None
    total_hunks: int = 0
    explained_count: int = 0
    unexplained_count: int = 0
    uncertain_count: int = 0
    hunk_results: List[HunkIntentResult] = Field(default_factory=list)
    summary: str = Field(default="", description="High-level evaluation of PR intent alignment")
