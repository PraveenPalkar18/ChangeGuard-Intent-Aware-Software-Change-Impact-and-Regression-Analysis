"""Data models for Impact Analysis and Risk Ranking (Milestone 6)."""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.graph.models import ImpactPath


class RiskLevel(str, Enum):
    """Categorical risk ranking level."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RelationshipConfidence(str, Enum):
    """Classification of relationship verification."""
    CONFIRMED_STATIC = "CONFIRMED_STATIC"  # Directly confirmed AST relation (calls, imports, containment)
    POTENTIAL = "POTENTIAL"                # Indirect / transitive downstream propagation (distance >= 2)
    UNKNOWN = "UNKNOWN"                    # Unresolved imports, missing AST, or unparsed source blind spots


class RiskFactor(BaseModel):
    """Individual risk contributor with evidence breakdown."""
    name: str = Field(..., description="Factor name, e.g. 'Blast Radius', 'Change Volatility'")
    level: RiskLevel = Field(..., description="Risk tier for this specific factor")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score between 0.0 and 1.0")
    description: str = Field(..., description="Explanation of how this factor influences risk")
    evidence: List[str] = Field(default_factory=list, description="Concrete supporting evidence facts")


class EntityRiskDetail(BaseModel):
    """Detailed risk ranking and impact trace for a code entity or file."""
    node_id: str = Field(..., description="Graph node identifier")
    name: str = Field(..., description="Entity or file name")
    entity_type: str = Field(..., description="Node categorization ('function', 'method', 'class', 'file')")
    file_path: str = Field(..., description="File path relative to repo root")
    is_directly_changed: bool = Field(default=False, description="True if modified directly in diff hunk")
    risk_level: RiskLevel = Field(..., description="Assigned risk level: LOW, MEDIUM, or HIGH")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Composite risk score 0.0 to 1.0")
    relationship_type: RelationshipConfidence = Field(
        default=RelationshipConfidence.CONFIRMED_STATIC,
        description="Confidence category of the relationship"
    )
    min_distance: int = Field(default=0, description="0 for directly changed, >= 1 for downstream dependents")
    dependent_entities_count: int = Field(default=0, description="Total downstream entities that depend on this")
    dependent_files_count: int = Field(default=0, description="Total downstream files that depend on this")
    impact_paths: List[ImpactPath] = Field(default_factory=list, description="Explainable impact propagation paths")
    reasons: List[str] = Field(default_factory=list, description="Specific reasons for risk assignment")
    factors: List[RiskFactor] = Field(default_factory=list, description="Factor breakdown")


class FileRiskDetail(BaseModel):
    """File-level risk summary and contribution."""
    filename: str = Field(..., description="File path")
    risk_level: RiskLevel = Field(..., description="Assigned risk level: LOW, MEDIUM, or HIGH")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Composite file risk score 0.0 to 1.0")
    directly_changed_entities: int = Field(default=0, description="Number of modified entities in this file")
    impacted_entities_count: int = Field(default=0, description="Number of downstream impacted entities in this file")
    hunks_count: int = Field(default=0, description="Total diff hunks in this file")
    added_lines: int = Field(default=0, description="Total added lines")
    deleted_lines: int = Field(default=0, description="Total deleted lines")
    unexplained_hunks_count: int = Field(default=0, description="Count of UNEXPLAINED hunks")
    uncertain_hunks_count: int = Field(default=0, description="Count of UNCERTAIN hunks")
    reasons: List[str] = Field(default_factory=list, description="Specific risk reasons for this file")
    factors: List[RiskFactor] = Field(default_factory=list, description="Factor breakdown")


class PRRiskAssessment(BaseModel):
    """Overall Pull Request risk evaluation and impact ranking."""
    overall_risk_level: RiskLevel = Field(..., description="Overall PR risk level: LOW, MEDIUM, or HIGH")
    overall_risk_score: float = Field(..., ge=0.0, le=1.0, description="Composite PR risk score 0.0 to 1.0")
    summary: str = Field(..., description="Executive explainable summary of risk findings")
    high_risk_reasons: List[str] = Field(
        default_factory=list,
        description="Detailed reasons if overall PR or any entity is HIGH risk"
    )
    primary_impact_paths: List[ImpactPath] = Field(
        default_factory=list,
        description="Step-by-step impact paths supporting high-risk conclusions"
    )
    confirmed_relationships_count: int = Field(default=0, description="Confirmed direct static relationships")
    potential_relationships_count: int = Field(default=0, description="Indirect / potential downstream paths")
    unknown_relationships_count: int = Field(default=0, description="Unresolved imports or unparsed blind spots")
    risk_factors: List[RiskFactor] = Field(default_factory=list, description="PR-wide factor breakdown")
    entity_risks: List[EntityRiskDetail] = Field(
        default_factory=list,
        description="Ranked entity risk details (highest risk first)"
    )
    file_risks: List[FileRiskDetail] = Field(default_factory=list, description="Per-file risk evaluations")
    limitations: List[str] = Field(
        default_factory=list,
        description="Static analysis boundaries and unverified runtime assumptions"
    )
