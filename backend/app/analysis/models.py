"""Data models for End-to-End Pull Request Intent and Impact Analysis."""
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.intent.models import IntentClassification
from backend.app.graph.models import ChangeGraphReport
from backend.app.impact.models import FileRiskDetail, PRRiskAssessment
from backend.app.testing.models import TestSelectionReport


class PRAnalysisRequest(BaseModel):
    """Payload to trigger end-to-end ChangeGuard analysis for a GitHub Pull Request."""
    owner: str = Field(..., min_length=1, max_length=100, description="GitHub repository owner or organization")
    repo: str = Field(..., min_length=1, max_length=100, description="GitHub repository name")
    pr_number: int = Field(..., gt=0, description="Pull Request number")
    fetch_source_files: bool = Field(default=True, description="Whether to fetch full repository source for Tree-sitter AST parsing")
    provider_name: Optional[str] = Field(default=None, description="Optional AI model provider ('tfidf', 'codebert', 'mock')")


class HunkAnalysisDetail(BaseModel):
    """Detailed intent analysis and code entity association for a single diff hunk."""
    hunk_index: int
    header: str
    old_start_line: int
    new_start_line: int
    change_type: str = Field(default="modified", description="'added', 'modified', or 'deleted'")
    matched_entity_id: Optional[str] = None
    matched_entity_name: Optional[str] = None
    matched_entity_type: Optional[str] = None
    association_type: str = Field(default="file_level", description="'enclosing', 'overlapping', or 'file_level'")
    classification: IntentClassification
    confidence: float
    similarity_score: float
    reason: str
    evidence: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    model_used: str
    provider_used: str


class FileAnalysisReport(BaseModel):
    """Per-file analysis summary including diff parsing, AST entity extraction, and hunk intent."""
    filename: str
    status: str
    patch_available: bool = True
    source_available: bool = False
    ast_entities_found: int = 0
    hunks_count: int = 0
    hunks: List[HunkAnalysisDetail] = Field(default_factory=list)
    risk: Optional[FileRiskDetail] = Field(default=None, description="File-level impact and risk ranking")
    limitations: List[str] = Field(default_factory=list)


class PRAnalysisReport(BaseModel):
    """Complete end-to-end ChangeGuard analysis report for a Pull Request."""
    owner: str
    repo: str
    pr_number: int
    title: str
    description: Optional[str] = None
    author: str
    state: str
    base_branch: str
    head_branch: str
    ai_provider: str
    ai_model: str
    total_files_analyzed: int = 0
    total_hunks_analyzed: int = 0
    explained_count: int = 0
    unexplained_count: int = 0
    uncertain_count: int = 0
    overall_intent_summary: str = ""
    files: List[FileAnalysisReport] = Field(default_factory=list)
    change_graph: Optional[ChangeGraphReport] = Field(default=None, description="Change and dependency graph with downstream impact propagation")
    risk_assessment: Optional[PRRiskAssessment] = Field(default=None, description="Overall and per-entity risk ranking and blast radius assessment")
    test_selection: Optional[TestSelectionReport] = Field(default=None, description="Targeted regression test recommendations")
    processing_limitations: List[str] = Field(default_factory=list)

