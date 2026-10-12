"""Unit tests for EntityHunkMapper associating diff hunks to AST entities."""
import pytest
from backend.app.preprocessing.diff_parser import parse_patch
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.repository.entity_mapper import EntityHunkMapper
from backend.app.repository.models import CodeEntityType


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


def test_map_hunk_enclosed_in_method(parser):
    """Test modification lines that fall strictly inside an existing method."""
    new_source = '''
class Calculator:
    def add(self, a, b):
        # Modified line
        res = a + b
        return res
'''
    parse_res = parser.parse_source("calc.py", new_source)

    # Patch modifying lines inside add (e.g. lines 4-5)
    patch = """@@ -3,3 +3,4 @@ def add(self, a, b):
-        return a + b
+        # Modified line
+        res = a + b
+        return res
"""
    hunks = parse_patch(patch, "calc.py")
    assert len(hunks) == 1

    associations = EntityHunkMapper.map_hunk_to_entities(
        hunk=hunks[0],
        file_path="calc.py",
        new_parse_result=parse_res,
    )

    assert len(associations) == 1
    assoc = associations[0]
    assert assoc.matched_entity_name == "add"
    assert assoc.matched_entity_id == "calc.py::Calculator.add"
    assert assoc.matched_entity_type == CodeEntityType.METHOD
    assert assoc.association_type == "enclosing"
    assert assoc.change_type == "modified"


def test_map_hunk_new_function_addition(parser):
    """Test newly added function in source mapped accurately."""
    new_source = '''
def existing():
    pass

def newly_added(x):
    return x * 2
'''
    parse_res = parser.parse_source("module.py", new_source)

    patch = """@@ -3,0 +4,3 @@
+def newly_added(x):
+    return x * 2
"""
    hunks = parse_patch(patch, "module.py")
    associations = EntityHunkMapper.map_hunk_to_entities(
        hunk=hunks[0],
        file_path="module.py",
        new_parse_result=parse_res,
    )

    assert len(associations) == 1
    assoc = associations[0]
    assert assoc.matched_entity_name == "newly_added"
    assert assoc.matched_entity_id == "module.py::newly_added"
    assert assoc.matched_entity_type == CodeEntityType.FUNCTION
    assert assoc.change_type == "added"


def test_map_hunk_deletion_old_source_distinction(parser):
    """Test deleted entity mapped to old source AST without inferring in new AST."""
    old_source = '''
def legacy_helper():
    return "deprecated"

def keep():
    pass
'''
    new_source = '''
def keep():
    pass
'''
    old_parse = parser.parse_source("legacy.py", old_source)
    new_parse = parser.parse_source("legacy.py", new_source)

    # Patch deleting legacy_helper (lines 2-3 in old source)
    patch = """@@ -2,3 +1,1 @@
-def legacy_helper():
-    return "deprecated"
-
 def keep():
"""
    hunks = parse_patch(patch, "legacy.py")
    associations = EntityHunkMapper.map_hunk_to_entities(
        hunk=hunks[0],
        file_path="legacy.py",
        new_parse_result=new_parse,
        old_parse_result=old_parse,
    )

    # Should detect the deletion and map it to legacy_helper from old_parse
    deleted_assocs = [a for a in associations if a.change_type == "deleted"]
    assert len(deleted_assocs) == 1
    assoc = deleted_assocs[0]
    assert assoc.matched_entity_name == "legacy_helper"
    assert assoc.matched_entity_id == "legacy.py::legacy_helper"

    # Crucial check: verify legacy_helper is NOT in the new_parse result
    new_entity_names = [e.name for e in new_parse.entities]
    assert "legacy_helper" not in new_entity_names


def test_map_hunk_file_level_change(parser):
    """Test top-level variable or import modification mapped as file_level."""
    new_source = '''
VERSION = "2.0.0"

def get_version():
    return VERSION
'''
    parse_res = parser.parse_source("version.py", new_source)

    patch = """@@ -1,2 +1,2 @@
-VERSION = "1.0.0"
+VERSION = "2.0.0"
"""
    hunks = parse_patch(patch, "version.py")
    associations = EntityHunkMapper.map_hunk_to_entities(
        hunk=hunks[0],
        file_path="version.py",
        new_parse_result=parse_res,
    )

    assert len(associations) == 1
    assoc = associations[0]
    assert assoc.association_type == "file_level"
    assert assoc.matched_entity_id is None
