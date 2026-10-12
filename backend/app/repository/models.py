"""Data models for code analysis, AST parsing, and entity extraction."""
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class Language(str, Enum):
    """Supported programming languages for code parsing."""
    PYTHON = "python"
    UNSUPPORTED = "unsupported"


class CodeEntityType(str, Enum):
    """Structural type of extracted code entity."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class CodeEntity(BaseModel):
    """Structured code entity representing a class, function, or method."""
    id: str = Field(..., description="Stable unique identifier (e.g. 'file.py::Class.method')")
    name: str = Field(..., description="Name of the entity (e.g. 'add')")
    entity_type: CodeEntityType = Field(..., description="Entity classification")
    file_path: str = Field(..., description="File path relative to repository root")
    start_line: int = Field(..., description="1-indexed starting line number")
    end_line: int = Field(..., description="1-indexed ending line number")
    parent_id: Optional[str] = Field(default=None, description="Identifier of enclosing class or function")
    docstring: Optional[str] = Field(default=None, description="Extracted docstring if present")
    parameters: List[str] = Field(default_factory=list, description="List of parameter names")
    decorators: List[str] = Field(default_factory=list, description="List of applied decorator names")
    is_async: bool = Field(default=False, description="True if asynchronous function or method")


class ImportEntity(BaseModel):
    """Extracted import statement."""
    module: str = Field(..., description="Module path being imported (e.g. 'os.path')")
    name: Optional[str] = Field(default=None, description="Specific symbol imported (e.g. 'join')")
    alias: Optional[str] = Field(default=None, description="Import alias if renamed with 'as'")
    line_number: int = Field(..., description="1-indexed line number of the import")
    is_from_import: bool = Field(default=False, description="True if 'from x import y' statement")


class CallSite(BaseModel):
    """Invocation of a function or method within source code."""
    caller_entity_id: Optional[str] = Field(default=None, description="ID of enclosing function/method if known")
    callee_name: str = Field(..., description="Invoked function or method name (e.g. 'math.sqrt')")
    line_number: int = Field(..., description="1-indexed line number of invocation")
    arguments_count: int = Field(default=0, description="Number of arguments passed")


class ParseErrorNode(BaseModel):
    """Information regarding a syntax or parsing error node within source."""
    start_line: int = Field(..., description="1-indexed start line of error node")
    end_line: int = Field(..., description="1-indexed end line of error node")
    error_text: str = Field(..., description="Code snippet containing the syntax error")


class ParseResult(BaseModel):
    """Complete structural outcome of parsing a source file."""
    file_path: str = Field(..., description="Relative file path of source")
    language: str = Field(..., description="Detected or requested language")
    is_success: bool = Field(..., description="True if parsed without fatal errors")
    has_syntax_errors: bool = Field(default=False, description="True if incomplete/malformed AST error nodes exist")
    entities: List[CodeEntity] = Field(default_factory=list, description="Extracted classes, functions, and methods")
    imports: List[ImportEntity] = Field(default_factory=list, description="Extracted import declarations")
    call_sites: List[CallSite] = Field(default_factory=list, description="Extracted invocation sites")
    error_nodes: List[ParseErrorNode] = Field(default_factory=list, description="Syntax error nodes recorded during parsing")
    raw_loc: int = Field(default=0, description="Total raw lines of code")
    error_message: Optional[str] = Field(default=None, description="Description of fatal parsing failure if any")


class EntityHunkAssociation(BaseModel):
    """Association connecting a diff hunk modification to a code entity."""
    hunk_index: int = Field(..., description="Index of associated diff hunk")
    file_path: str = Field(..., description="File path relative to repository root")
    change_type: str = Field(..., description="Type of change: 'added', 'modified', or 'deleted'")
    line_range: Tuple[int, int] = Field(..., description="(start_line, end_line) of the modification in context")
    matched_entity_id: Optional[str] = Field(default=None, description="ID of associated code entity, or None for file-level")
    matched_entity_name: Optional[str] = Field(default=None, description="Name of associated code entity")
    matched_entity_type: Optional[CodeEntityType] = Field(default=None, description="Type of entity")
    association_type: str = Field(default="enclosing", description="'enclosing', 'overlapping', or 'file_level'")
    details: Optional[str] = Field(default=None, description="Contextual explanation of association")
