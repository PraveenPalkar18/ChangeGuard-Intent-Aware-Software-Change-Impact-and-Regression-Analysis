"""Unit tests for Tree-sitter Python code parser."""
import pytest
from backend.app.repository.models import (
    CodeEntityType,
    ParseResult,
)
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


def test_parse_simple_function_and_class(parser):
    """Test extracting standalone functions and classes."""
    source = '''
def add(a, b):
    """Add two numbers."""
    return a + b

class Greeter:
    """Greeter class."""
    def greet(self, name: str) -> str:
        return f"Hello, {name}"
'''
    res = parser.parse_source("app/math_util.py", source)
    assert res.is_success is True
    assert res.has_syntax_errors is False
    assert len(res.entities) == 3

    # Function 'add'
    fn = res.entities[0]
    assert fn.name == "add"
    assert fn.entity_type == CodeEntityType.FUNCTION
    assert fn.id == "app/math_util.py::add"
    assert fn.parameters == ["a", "b"]
    assert fn.docstring == "Add two numbers."
    assert fn.start_line == 2
    assert fn.end_line == 4

    # Class 'Greeter'
    cls_entity = res.entities[1]
    assert cls_entity.name == "Greeter"
    assert cls_entity.entity_type == CodeEntityType.CLASS
    assert cls_entity.id == "app/math_util.py::Greeter"
    assert cls_entity.docstring == "Greeter class."

    # Method 'greet'
    method = res.entities[2]
    assert method.name == "greet"
    assert method.entity_type == CodeEntityType.METHOD
    assert method.id == "app/math_util.py::Greeter.greet"
    assert method.parent_id == "app/math_util.py::Greeter"
    assert "name" in method.parameters


def test_parse_nested_functions(parser):
    """Test nested functions within outer functions."""
    source = '''
def outer_calculator(base):
    def multiplier(factor):
        return base * factor
    return multiplier
'''
    res = parser.parse_source("calc.py", source)
    assert res.is_success is True
    assert len(res.entities) == 2

    outer = res.entities[0]
    inner = res.entities[1]

    assert outer.name == "outer_calculator"
    assert outer.entity_type == CodeEntityType.FUNCTION
    assert inner.name == "multiplier"
    assert inner.entity_type == CodeEntityType.FUNCTION
    assert inner.parent_id == outer.id
    assert inner.id == "calc.py::outer_calculator.multiplier"


def test_parse_decorators_and_async(parser):
    """Test async functions and single/multiple decorators."""
    source = '''
@staticmethod
@register_route("/api/v1")
async def fetch_data(endpoint: str, timeout: int = 30):
    return await client.get(endpoint)
'''
    res = parser.parse_source("api.py", source)
    assert res.is_success is True
    assert len(res.entities) == 1

    fn = res.entities[0]
    assert fn.name == "fetch_data"
    assert fn.is_async is True
    assert fn.parameters == ["endpoint", "timeout"]
    assert len(fn.decorators) == 2
    assert "@staticmethod" in fn.decorators[0]
    assert "@register_route" in fn.decorators[1]
    # start_line includes decorators
    assert fn.start_line == 2


def test_parse_imports(parser):
    """Test extraction of diverse import styles."""
    source = '''
import os
import sys, math
import numpy as np
from os.path import join as pjoin, exists
from ..core import config
from . import local_mod
from typing import *
'''
    res = parser.parse_source("imports_test.py", source)
    assert res.is_success is True

    # Validate import entities
    modules = [(i.module, i.name, i.alias, i.is_from_import) for i in res.imports]
    assert ("os", None, None, False) in modules
    assert ("sys", None, None, False) in modules
    assert ("math", None, None, False) in modules
    assert ("numpy", None, "np", False) in modules
    assert ("os.path", "join", "pjoin", True) in modules
    assert ("os.path", "exists", None, True) in modules
    assert ("..core", "config", None, True) in modules
    assert (".", "local_mod", None, True) in modules
    assert ("typing", "*", None, True) in modules


def test_parse_call_sites(parser):
    """Test extraction of call sites and enclosing caller IDs."""
    source = '''
def process_data(items):
    print("starting")
    total = sum(items)
    result = helper.calculate(total, debug=True)
    return result

def uncalled():
    pass
'''
    res = parser.parse_source("caller.py", source)
    assert res.is_success is True

    calls = res.call_sites
    assert len(calls) >= 3

    callee_names = [c.callee_name for c in calls]
    assert "print" in callee_names
    assert "sum" in callee_names
    assert "helper.calculate" in callee_names

    # Check caller ID tracking
    for c in calls:
        assert c.caller_entity_id == "caller.py::process_data"


def test_empty_and_comment_files(parser):
    """Test that empty or comment-only files parse cleanly without error."""
    # Completely empty
    res_empty = parser.parse_source("empty.py", "")
    assert res_empty.is_success is True
    assert len(res_empty.entities) == 0

    # Whitespace and comments
    source_comments = '''
# Copyright 2026 ChangeGuard
# Author: Praveen

"""Module level docstring with no entities."""
'''
    res_comm = parser.parse_source("comments.py", source_comments)
    assert res_comm.is_success is True
    assert len(res_comm.entities) == 0
    assert len(res_comm.error_nodes) == 0


def test_syntax_errors_and_partial_recovery(parser):
    """Test that malformed code produces error nodes but preserves valid entities."""
    source = '''
def broken_syntax(:
    incomplete

def healthy_function():
    return 42
'''
    res = parser.parse_source("broken.py", source)
    assert res.is_success is True
    assert res.has_syntax_errors is True
    assert len(res.error_nodes) > 0

    # The parser still recovered and extracted the healthy function!
    healthy = [e for e in res.entities if e.name == "healthy_function"]
    assert len(healthy) == 1
    assert healthy[0].start_line == 5


def test_unsupported_language_rejection(parser):
    """Test that non-Python files are rejected with explicit failure."""
    res = parser.parse_source("Cargo.toml", "[package]\nname = 'test'")
    assert res.is_success is False
    assert res.language == "unsupported"
    assert "Unsupported language" in res.error_message
