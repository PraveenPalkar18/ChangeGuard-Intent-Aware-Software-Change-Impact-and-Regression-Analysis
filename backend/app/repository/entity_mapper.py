"""Entity-Hunk Mapper associating diff modifications with AST code entities."""
from typing import List, Optional, Tuple
from backend.app.preprocessing.models import DiffHunk, ParsedFileDiff
from backend.app.repository.models import (
    CodeEntity,
    EntityHunkAssociation,
    ParseResult,
)


class EntityHunkMapper:
    """Associates diff hunks and modified line ranges with corresponding code entities."""

    @staticmethod
    def map_hunk_to_entities(
        hunk: DiffHunk,
        file_path: str,
        new_parse_result: Optional[ParseResult] = None,
        old_parse_result: Optional[ParseResult] = None,
    ) -> List[EntityHunkAssociation]:
        """Map added, modified, and deleted lines in a single hunk to AST entities.

        Distinguishes between new-file lines (mapped against new AST) and old-file lines
        (mapped against old AST).
        """
        associations: List[EntityHunkAssociation] = []

        added_nums = hunk.added_line_numbers
        deleted_nums = hunk.deleted_line_numbers

        # 1. Handle Added / Modified lines (New file context)
        if added_nums:
            new_min, new_max = min(added_nums), max(added_nums)
            change_type = "modified" if deleted_nums else "added"

            if new_parse_result and new_parse_result.entities:
                matched_entity, assoc_type = EntityHunkMapper._find_matching_entity(
                    entities=new_parse_result.entities,
                    start_line=new_min,
                    end_line=new_max,
                )
                if matched_entity:
                    associations.append(
                        EntityHunkAssociation(
                            hunk_index=hunk.hunk_index,
                            file_path=file_path,
                            change_type=change_type,
                            line_range=(new_min, new_max),
                            matched_entity_id=matched_entity.id,
                            matched_entity_name=matched_entity.name,
                            matched_entity_type=matched_entity.entity_type,
                            association_type=assoc_type,
                            details=f"Lines {new_min}-{new_max} {assoc_type} by {matched_entity.entity_type.value} '{matched_entity.name}'",
                        )
                    )
                else:
                    associations.append(
                        EntityHunkAssociation(
                            hunk_index=hunk.hunk_index,
                            file_path=file_path,
                            change_type=change_type,
                            line_range=(new_min, new_max),
                            matched_entity_id=None,
                            matched_entity_name=None,
                            matched_entity_type=None,
                            association_type="file_level",
                            details=f"Lines {new_min}-{new_max} at module/file level outside functions or classes",
                        )
                    )
            else:
                associations.append(
                    EntityHunkAssociation(
                        hunk_index=hunk.hunk_index,
                        file_path=file_path,
                        change_type=change_type,
                        line_range=(new_min, new_max),
                        matched_entity_id=None,
                        matched_entity_name=None,
                        matched_entity_type=None,
                        association_type="file_level",
                        details="No new source AST provided; recorded line range only",
                    )
                )

        # 2. Handle Pure Deletions (Old file context)
        # Note: If a hunk has both additions and deletions, it was captured as "modified" above.
        # But if it has deletions and old_parse_result is available, we explicitly map the deleted entity.
        if deleted_nums:
            old_min, old_max = min(deleted_nums), max(deleted_nums)

            # Check if this hunk is a pure deletion, or if we want to trace the deleted entity
            if not added_nums or old_parse_result:
                if old_parse_result and old_parse_result.entities:
                    matched_old, assoc_type = EntityHunkMapper._find_matching_entity(
                        entities=old_parse_result.entities,
                        start_line=old_min,
                        end_line=old_max,
                    )
                    if matched_old:
                        associations.append(
                            EntityHunkAssociation(
                                hunk_index=hunk.hunk_index,
                                file_path=file_path,
                                change_type="deleted",
                                line_range=(old_min, old_max),
                                matched_entity_id=matched_old.id,
                                matched_entity_name=matched_old.name,
                                matched_entity_type=matched_old.entity_type,
                                association_type=assoc_type,
                                details=f"Deleted lines {old_min}-{old_max} mapped to old {matched_old.entity_type.value} '{matched_old.name}'",
                            )
                        )
                elif not added_nums:
                    # Pure deletion without old AST
                    associations.append(
                        EntityHunkAssociation(
                            hunk_index=hunk.hunk_index,
                            file_path=file_path,
                            change_type="deleted",
                            line_range=(old_min, old_max),
                            matched_entity_id=None,
                            matched_entity_name=None,
                            matched_entity_type=None,
                            association_type="file_level",
                            details=f"Deleted lines {old_min}-{old_max} (old source AST not provided)",
                        )
                    )

        return associations

    @staticmethod
    def map_file_diff_to_entities(
        parsed_diff: ParsedFileDiff,
        new_parse_result: Optional[ParseResult] = None,
        old_parse_result: Optional[ParseResult] = None,
    ) -> List[EntityHunkAssociation]:
        """Map all hunks within a file diff to code entities."""
        all_associations: List[EntityHunkAssociation] = []
        for hunk in parsed_diff.hunks:
            assoc = EntityHunkMapper.map_hunk_to_entities(
                hunk=hunk,
                file_path=parsed_diff.filename,
                new_parse_result=new_parse_result,
                old_parse_result=old_parse_result,
            )
            all_associations.extend(assoc)
        return all_associations

    @staticmethod
    def _find_matching_entity(
        entities: List[CodeEntity],
        start_line: int,
        end_line: int,
    ) -> Tuple[Optional[CodeEntity], str]:
        """Find the innermost enclosing or overlapping entity for a given line range.

        Returns:
            (matched_entity, association_type) where association_type is 'enclosing' or 'overlapping'.
        """
        enclosing_candidates: List[CodeEntity] = []
        overlapping_candidates: List[CodeEntity] = []

        for entity in entities:
            # Enclosing: entity spans entire change
            if entity.start_line <= start_line and end_line <= entity.end_line:
                enclosing_candidates.append(entity)
            # Overlapping: change intersects entity span
            elif not (end_line < entity.start_line or start_line > entity.end_line):
                overlapping_candidates.append(entity)

        # 1. Prefer innermost enclosing entity (smallest line span)
        if enclosing_candidates:
            # Sort by span length ascending (innermost method beats class)
            enclosing_candidates.sort(key=lambda e: (e.end_line - e.start_line))
            return enclosing_candidates[0], "enclosing"

        # 2. Fall back to overlapping entity
        if overlapping_candidates:
            overlapping_candidates.sort(key=lambda e: (e.end_line - e.start_line))
            return overlapping_candidates[0], "overlapping"

        return None, "file_level"
