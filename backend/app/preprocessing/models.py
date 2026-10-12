"""Data models for unified git diff and hunk parsing."""
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class DiffLineType(str, Enum):
    """Classification of a single diff line."""
    CONTEXT = "context"
    ADDED = "added"
    DELETED = "deleted"


class DiffLine(BaseModel):
    """A single line within a diff hunk."""
    line_type: DiffLineType
    content: str
    old_line_number: Optional[int] = None
    new_line_number: Optional[int] = None


class DiffHunk(BaseModel):
    """A parsed hunk within a unified diff."""
    hunk_index: int = Field(default=0, description="0-indexed position of hunk within file patch")
    header: str = Field(..., description="Raw hunk header (e.g. @@ -10,4 +10,7 @@)")
    old_start_line: int = Field(..., description="Starting line in the old version of the file")
    old_line_count: int = Field(default=0, description="Total number of lines in old range")
    new_start_line: int = Field(..., description="Starting line in the new version of the file")
    new_line_count: int = Field(default=0, description="Total number of lines in new range")
    lines: List[DiffLine] = Field(default_factory=list, description="Ordered lines in hunk")

    @property
    def added_lines(self) -> List[str]:
        """Returns contents of added lines (+)."""
        return [line.content for line in self.lines if line.line_type == DiffLineType.ADDED]

    @property
    def deleted_lines(self) -> List[str]:
        """Returns contents of deleted lines (-)."""
        return [line.content for line in self.lines if line.line_type == DiffLineType.DELETED]

    @property
    def added_line_numbers(self) -> List[int]:
        """Returns 1-indexed line numbers of additions in the new file."""
        return [line.new_line_number for line in self.lines if line.line_type == DiffLineType.ADDED and line.new_line_number is not None]

    @property
    def deleted_line_numbers(self) -> List[int]:
        """Returns 1-indexed line numbers of deletions in the old file."""
        return [line.old_line_number for line in self.lines if line.line_type == DiffLineType.DELETED and line.old_line_number is not None]

    @property
    def new_line_range(self) -> Optional[Tuple[int, int]]:
        """Returns (start, end) line range for the new file if additions/modifications exist."""
        nums = [line.new_line_number for line in self.lines if line.new_line_number is not None]
        if nums:
            return (min(nums), max(nums))
        return None

    @property
    def old_line_range(self) -> Optional[Tuple[int, int]]:
        """Returns (start, end) line range for the old file if deletions exist."""
        nums = [line.old_line_number for line in self.lines if line.old_line_number is not None]
        if nums:
            return (min(nums), max(nums))
        return None


class ParsedFileDiff(BaseModel):
    """Complete parsed diff for a single changed file."""
    filename: str
    old_filename: Optional[str] = None
    status: str = "modified"
    hunks: List[DiffHunk] = Field(default_factory=list)
