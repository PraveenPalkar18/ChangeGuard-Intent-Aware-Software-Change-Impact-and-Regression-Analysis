"""Unit tests for unified diff and patch parsing."""
import pytest
from backend.app.preprocessing.models import DiffLineType, DiffHunk, ParsedFileDiff
from backend.app.preprocessing.diff_parser import parse_patch, parse_file_diff
from backend.app.github.models import PRFileChange


SAMPLE_PATCH = """@@ -10,5 +10,7 @@ def compute():
 context line 1
-old deleted line
+new added line 1
+new added line 2
 context line 2
\\ No newline at end of file
"""

MULTI_HUNK_PATCH = """@@ -1,3 +1,3 @@
-import old_module
+import new_module
 
@@ -20,4 +20,5 @@ class Service:
     def start(self):
+        self.validate()
         return True
"""


def test_parse_patch_basic():
    """Verify single-hunk patch extracts correct line counts and numbers."""
    hunks = parse_patch(SAMPLE_PATCH, filename="math.py")
    assert len(hunks) == 1
    hunk = hunks[0]

    assert hunk.old_start_line == 10
    assert hunk.old_line_count == 5
    assert hunk.new_start_line == 10
    assert hunk.new_line_count == 7
    assert len(hunk.added_lines) == 2
    assert "new added line 1" in hunk.added_lines
    assert len(hunk.deleted_lines) == 1
    assert "old deleted line" in hunk.deleted_lines

    # Check line numbers
    assert hunk.added_line_numbers == [11, 12]
    assert hunk.deleted_line_numbers == [11]
    assert hunk.new_line_range == (10, 13)


def test_parse_patch_multiple_hunks():
    """Verify multiple hunks are separated and tracked with correct indices."""
    hunks = parse_patch(MULTI_HUNK_PATCH, filename="service.py")
    assert len(hunks) == 2
    assert hunks[0].hunk_index == 0
    assert hunks[0].old_start_line == 1
    assert hunks[0].new_start_line == 1
    assert hunks[0].added_lines == ["import new_module"]
    assert hunks[0].deleted_lines == ["import old_module"]

    assert hunks[1].hunk_index == 1
    assert hunks[1].old_start_line == 20
    assert hunks[1].new_start_line == 20
    assert hunks[1].added_lines == ["        self.validate()"]
    assert hunks[1].added_line_numbers == [21]


def test_parse_patch_empty_or_none():
    """Verify empty or None patches produce empty hunk lists without error."""
    assert parse_patch(None) == []
    assert parse_patch("") == []
    assert parse_patch("   \n  ") == []


def test_parse_file_diff_integration():
    """Verify PRFileChange translates to ParsedFileDiff with hunks."""
    file_change = PRFileChange(
        filename="app/calc.py",
        status="modified",
        additions=2,
        deletions=1,
        changes=3,
        patch=SAMPLE_PATCH,
    )
    parsed = parse_file_diff(file_change)
    assert isinstance(parsed, ParsedFileDiff)
    assert parsed.filename == "app/calc.py"
    assert parsed.status == "modified"
    assert len(parsed.hunks) == 1
