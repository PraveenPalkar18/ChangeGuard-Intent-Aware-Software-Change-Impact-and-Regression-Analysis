"""Unified diff and patch parser."""
import re
from typing import List, Optional
from backend.app.preprocessing.models import (
    DiffHunk,
    DiffLine,
    DiffLineType,
    ParsedFileDiff,
)
from backend.app.github.models import PRFileChange

# Regex matching standard unified diff hunk header: @@ -old_start[,old_count] +new_start[,new_count] @@
HUNK_HEADER_PATTERN = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(?:[ \t]+(.*))?$"
)


def parse_patch(patch_text: Optional[str], filename: str = "") -> List[DiffHunk]:
    """Parse raw unified diff patch text into a list of structured DiffHunk objects.

    Args:
        patch_text: The unified diff patch string (from git diff or GitHub API).
        filename: Optional filename for logging or tracking.

    Returns:
        List of parsed DiffHunk objects with accurate old/new line numbers.
    """
    if not patch_text or not patch_text.strip():
        return []

    hunks: List[DiffHunk] = []
    lines = patch_text.splitlines()

    current_hunk: Optional[DiffHunk] = None
    curr_old_line = 0
    curr_new_line = 0
    hunk_idx = 0

    for line in lines:
        header_match = HUNK_HEADER_PATTERN.match(line)
        if header_match:
            # Finalize previous hunk if any
            if current_hunk is not None:
                hunks.append(current_hunk)

            old_start = int(header_match.group(1))
            old_count = int(header_match.group(2)) if header_match.group(2) else 1
            new_start = int(header_match.group(3))
            new_count = int(header_match.group(4)) if header_match.group(4) else 1

            curr_old_line = old_start
            curr_new_line = new_start

            current_hunk = DiffHunk(
                hunk_index=hunk_idx,
                header=line,
                old_start_line=old_start,
                old_line_count=old_count,
                new_start_line=new_start,
                new_line_count=new_count,
                lines=[],
            )
            hunk_idx += 1
            continue

        if current_hunk is None:
            # Lines before the first hunk header (e.g. diff headers) are ignored
            continue

        if line.startswith("+"):
            content = line[1:]
            current_hunk.lines.append(
                DiffLine(
                    line_type=DiffLineType.ADDED,
                    content=content,
                    old_line_number=None,
                    new_line_number=curr_new_line,
                )
            )
            curr_new_line += 1
        elif line.startswith("-"):
            content = line[1:]
            current_hunk.lines.append(
                DiffLine(
                    line_type=DiffLineType.DELETED,
                    content=content,
                    old_line_number=curr_old_line,
                    new_line_number=None,
                )
            )
            curr_old_line += 1
        elif line.startswith(" ") or line == "":
            content = line[1:] if line.startswith(" ") else ""
            current_hunk.lines.append(
                DiffLine(
                    line_type=DiffLineType.CONTEXT,
                    content=content,
                    old_line_number=curr_old_line,
                    new_line_number=curr_new_line,
                )
            )
            curr_old_line += 1
            curr_new_line += 1
        elif line.startswith("\\"):
            # E.g. "\\ No newline at end of file" - skip line counters
            continue

    if current_hunk is not None:
        hunks.append(current_hunk)

    return hunks


def parse_file_diff(file_change: PRFileChange) -> ParsedFileDiff:
    """Parse a PRFileChange into a ParsedFileDiff."""
    hunks = parse_patch(file_change.patch, filename=file_change.filename)
    return ParsedFileDiff(
        filename=file_change.filename,
        old_filename=file_change.previous_filename,
        status=file_change.status,
        hunks=hunks,
    )
