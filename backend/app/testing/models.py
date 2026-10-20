"""Data models for Regression Test Selection (Milestone 7)."""
from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from backend.app.impact.models import RelationshipConfidence


class TestPriority(str, Enum):
    """Execution priority tier for recommended regression tests."""
    __test__ = False
    P0_CRITICAL = "P0_CRITICAL"  # Directly tests changed code via AST calls or direct symbol targeting
    P1_HIGH = "P1_HIGH"          # Tests direct downstream impacted entities (distance 1) or imports modified module
    P2_MEDIUM = "P2_MEDIUM"      # Transitive callers (distance >= 2) or strong naming heuristic matches
    P3_LOW = "P3_LOW"            # General module/directory-level correspondence


class TestMatchType(str, Enum):
    """Categorical technique used to map a test to changed/impacted code."""
    __test__ = False
    STATIC_CALL = "STATIC_CALL"              # Confirmed direct AST function/method invocation
    STATIC_IMPORT = "STATIC_IMPORT"          # Confirmed static import of modified file or entity
    TRANSITIVE_GRAPH = "TRANSITIVE_GRAPH"    # Multi-hop dependency path in AST graph
    NAMING_HEURISTIC = "NAMING_HEURISTIC"    # Symbol or file naming convention match


class SelectedTestCase(BaseModel):
    """Targeted test case recommended for regression verification."""
    __test__ = False
    test_id: str = Field(..., description="Unique test identifier, e.g. 'tests/test_billing.py::test_discount'")
    test_name: str = Field(..., description="Test function or class name")
    test_file: str = Field(..., description="Test file path relative to repo root")
    priority: TestPriority = Field(..., description="Recommended execution urgency")
    score: float = Field(..., ge=0.0, le=1.0, description="Deterministic recommendation score between 0.0 and 1.0")
    match_type: TestMatchType = Field(..., description="Method used to establish test-to-code mapping")
    relationship_confidence: RelationshipConfidence = Field(
        ...,
        description="Whether relationship is statically confirmed, potential, or heuristic"
    )
    linked_entities: List[str] = Field(default_factory=list, description="IDs of changed/impacted entities verified by this test")
    evidence: List[str] = Field(default_factory=list, description="Concrete evidence justifying test selection")
    suggested_command: str = Field(..., description="Suggested execution command (e.g. 'pytest tests/test_billing.py -k test_discount')")


class TestSelectionReport(BaseModel):
    """Aggregated regression test selection report for a Pull Request."""
    __test__ = False
    total_tests_discovered: int = Field(default=0, description="Total test functions/classes discovered in repo")
    selected_tests_count: int = Field(default=0, description="Number of targeted tests selected for regression")
    critical_count: int = Field(default=0, description="Count of P0_CRITICAL tests")
    high_count: int = Field(default=0, description="Count of P1_HIGH tests")
    medium_count: int = Field(default=0, description="Count of P2_MEDIUM tests")
    low_count: int = Field(default=0, description="Count of P3_LOW tests")
    summary: str = Field(..., description="Executive explainable summary of test selection findings")
    recommended_tests: List[SelectedTestCase] = Field(
        default_factory=list,
        description="Ranked list of recommended tests (highest priority first)"
    )
    selection_strategy: str = Field(
        default="AST Call Graph Traversal + Static Imports + Transparent Naming Heuristics",
        description="Explanation of selection methodology"
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Framework limitations, unparsed test files, or runtime gaps"
    )
