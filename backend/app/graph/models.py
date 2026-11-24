"""Data models for Change and Dependency Graph analysis (Milestone 5)."""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of graph nodes."""
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    UNKNOWN = "unknown"


class EdgeType(str, Enum):
    """Types of graph dependency edges."""
    CONTAINS = "CONTAINS"      # Parent-child (e.g. File contains Function/Class, Class contains Method)
    IMPORTS = "IMPORTS"        # Module/File/Symbol import
    CALLS = "CALLS"            # Function/Method invocation
    INHERITS = "INHERITS"      # Class inheritance / subtyping
    REFERENCES = "REFERENCES"  # Attribute or symbol reference
    TESTS = "TESTS"            # Test case exercising function/class


class RelationshipCertainty(str, Enum):
    """Certainty level of a graph dependency relationship."""
    CONFIRMED = "CONFIRMED"  # Directly supported by resolved static AST evidence
    INFERRED = "INFERRED"    # Plausible but not fully resolved (e.g. naming heuristic or global symbol fallback)
    UNKNOWN = "UNKNOWN"      # Cannot be established reliably (e.g. unresolved import or dynamic invocation)


class GraphNode(BaseModel):
    """A node representing a file or code entity in the dependency graph."""
    id: str = Field(..., description="Unique node identifier, e.g. 'file:app/main.py' or 'entity:app/main.py::run'")
    name: str = Field(..., description="Short symbol or file name")
    node_type: NodeType = Field(..., description="Node categorization")
    file_path: str = Field(..., description="File path relative to repository root")
    start_line: Optional[int] = Field(default=None, description="Start line in source file if entity")
    end_line: Optional[int] = Field(default=None, description="End line in source file if entity")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structural attributes")


class GraphEdge(BaseModel):
    """A directed edge representing a structural or behavioral relationship."""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    edge_type: EdgeType = Field(..., description="Relationship type")
    source_file: Optional[str] = Field(default=None, description="Source file path")
    source_line: Optional[int] = Field(default=None, description="Source line number")
    target_file: Optional[str] = Field(default=None, description="Target file path")
    target_line: Optional[int] = Field(default=None, description="Target line number")
    detection_method: str = Field(default="ast", description="Detection method: ast, naming, fallback")
    certainty: RelationshipCertainty = Field(default=RelationshipCertainty.CONFIRMED, description="Certainty level")
    evidence: str = Field(default="", description="Human-readable reason or code evidence")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context details")


class ImpactPath(BaseModel):
    """Step-by-step explainable propagation path from a changed entity to a downstream entity."""
    target_id: str = Field(..., description="Impacted node ID")
    target_name: str = Field(..., description="Impacted entity name")
    target_type: NodeType = Field(..., description="Node type of impacted entity")
    target_file: str = Field(..., description="File containing the impacted entity")
    path_nodes: List[str] = Field(default_factory=list, description="Ordered node IDs along propagation path")
    path_description: str = Field(..., description="Human-readable explanation, e.g. 'changed func -> caller -> file'")
    distance: int = Field(default=1, description="Number of hops from changed entity")
    impact_reason: str = Field(default="", description="Why this entity is affected")
    certainty: RelationshipCertainty = Field(default=RelationshipCertainty.CONFIRMED, description="Certainty along this path")
    origin_changed_entity: str = Field(default="", description="Directly changed entity that initiated this path")


class ImpactedEntity(BaseModel):
    """Downstream entity impacted by one or more changed diff hunks."""
    node_id: str = Field(..., description="Unique identifier of impacted entity")
    name: str = Field(..., description="Symbol name")
    entity_type: NodeType = Field(..., description="Node type")
    file_path: str = Field(..., description="File path")
    min_distance: int = Field(default=1, description="Shortest hop distance from changed code")
    certainty: RelationshipCertainty = Field(default=RelationshipCertainty.CONFIRMED, description="Overall certainty")
    impact_paths: List[ImpactPath] = Field(default_factory=list, description="All explainable paths leading to impact")


class ChangeGraphReport(BaseModel):
    """Aggregated Change and Dependency Graph analysis result."""
    total_nodes: int = Field(default=0, description="Total nodes in repository graph")
    total_edges: int = Field(default=0, description="Total directed edges in graph")
    changed_entities: List[str] = Field(default_factory=list, description="Directly changed entity node IDs")
    impacted_entities_count: int = Field(default=0, description="Total downstream entities impacted")
    impacted_files_count: int = Field(default=0, description="Total downstream files impacted")
    direct_impacted_entities_count: int = Field(default=0, description="Downstream entities directly calling or importing (distance == 1)")
    transitive_impacted_entities_count: int = Field(default=0, description="Downstream entities impacted transitively (distance > 1)")
    direct_impacted_files_count: int = Field(default=0, description="Files containing directly impacted entities")
    transitive_impacted_files_count: int = Field(default=0, description="Files containing only transitively impacted entities")
    impacted_entities: List[ImpactedEntity] = Field(default_factory=list, description="Detailed downstream impacted entities")
    impacted_files: List[str] = Field(default_factory=list, description="List of all downstream impacted file paths")
    graph_limitations: List[str] = Field(default_factory=list, description="Limitations, unresolved imports, or unparsed files")
    edges: List[GraphEdge] = Field(default_factory=list, description="All graph edges with certainty and evidence")
