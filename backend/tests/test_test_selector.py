"""Unit tests for Regression Test Selection (Milestone 7)."""
import pytest
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.graph.graph_builder import ChangeGraphBuilder
from backend.app.graph.models import ChangeGraphReport, ImpactedEntity, NodeType
from backend.app.impact.models import RelationshipConfidence
from backend.app.testing.models import (
    TestPriority,
    TestMatchType,
    SelectedTestCase,
    TestSelectionReport,
)
from backend.app.testing.selector import RegressionTestSelector


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


@pytest.fixture
def selector():
    return RegressionTestSelector()


def test_selector_direct_ast_call_critical(parser, selector):
    """Test function that directly invokes modified entity in AST is ranked P0_CRITICAL."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    test_src = """from app.billing import calculate_discount

def test_calculate_discount():
    assert calculate_discount(100, 0.1) == 90
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_test = parser.parse_source("tests/test_billing.py", test_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/billing.py": parse_billing,
        "tests/test_billing.py": parse_test,
    })

    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_billing.py": parse_test},
        graph=builder.graph,
    )

    assert selection.total_tests_discovered == 1
    assert selection.selected_tests_count == 1
    assert selection.critical_count == 1

    test_case = selection.recommended_tests[0]
    assert test_case.test_name == "test_calculate_discount"
    assert test_case.priority == TestPriority.P0_CRITICAL
    assert test_case.match_type == TestMatchType.STATIC_CALL
    assert test_case.relationship_confidence == RelationshipConfidence.CONFIRMED_STATIC
    assert test_case.score >= 0.90
    assert "calculate_discount" in test_case.suggested_command
    assert any("Direct AST invocation" in ev for ev in test_case.evidence)


def test_selector_impacted_entity_call_high(parser, selector):
    """Test function calling downstream impacted entity is ranked P1_HIGH with confirmed static linkage."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    checkout_src = """from app.billing import calculate_discount
def process_order(price, rate):
    return calculate_discount(price, rate)
"""
    test_src = """from app.checkout import process_order

def test_process_order():
    assert process_order(100, 0.2) == 80
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_checkout = parser.parse_source("app/checkout.py", checkout_src)
    parse_test = parser.parse_source("tests/test_checkout.py", test_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/billing.py": parse_billing,
        "app/checkout.py": parse_checkout,
        "tests/test_checkout.py": parse_test,
    })

    # Changed entity is calculate_discount in billing
    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_checkout.py": parse_test},
        graph=builder.graph,
    )

    assert selection.selected_tests_count == 1
    assert selection.high_count == 1

    test_case = selection.recommended_tests[0]
    assert test_case.test_name == "test_process_order"
    assert test_case.priority == TestPriority.P1_HIGH
    assert test_case.match_type == TestMatchType.STATIC_CALL
    assert test_case.relationship_confidence == RelationshipConfidence.CONFIRMED_STATIC
    assert test_case.score == 0.80
    assert any("downstream impacted entity" in ev for ev in test_case.evidence)


def test_selector_symbol_naming_heuristic(parser, selector):
    """Test symbol-level naming heuristic matches test targeting changed symbol even without direct call site."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    # Test does not call calculate_discount directly (e.g. asserts mock or indirect setup)
    test_src = """import app.billing

def test_calculate_discount():
    # Setup test without direct call expression
    pass
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_test = parser.parse_source("tests/test_billing.py", test_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/billing.py": parse_billing})
    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_billing.py": parse_test},
    )

    assert selection.selected_tests_count == 1
    test_case = selection.recommended_tests[0]
    assert test_case.match_type == TestMatchType.NAMING_HEURISTIC
    assert test_case.test_name == "test_calculate_discount"
    assert "calculate_discount" in test_case.evidence[0]


def test_selector_static_import_of_module(parser, selector):
    """Test module-level static import selects test cases at P1_HIGH priority."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    test_src = """import app.billing

def test_other_feature():
    pass
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_test = parser.parse_source("tests/test_other.py", test_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/billing.py": parse_billing})
    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_other.py": parse_test},
    )

    assert selection.selected_tests_count == 1
    test_case = selection.recommended_tests[0]
    assert test_case.priority == TestPriority.P1_HIGH
    assert test_case.match_type == TestMatchType.STATIC_IMPORT
    assert test_case.relationship_confidence == RelationshipConfidence.CONFIRMED_STATIC


def test_selector_file_naming_heuristic(parser, selector):
    """Test file-level naming convention (test_billing.py -> billing.py) selects tests at P2_MEDIUM."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    # No import of app.billing, but file is named test_billing.py
    test_src = """def test_something_generic():
    pass
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_test = parser.parse_source("tests/test_billing.py", test_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/billing.py": parse_billing})
    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_billing.py": parse_test},
    )

    assert selection.selected_tests_count == 1
    test_case = selection.recommended_tests[0]
    assert test_case.priority == TestPriority.P2_MEDIUM
    assert test_case.match_type == TestMatchType.NAMING_HEURISTIC
    assert test_case.relationship_confidence == RelationshipConfidence.POTENTIAL


def test_selector_no_tests_discovered(selector):
    """Test repository with no test files returns graceful summary without errors."""
    graph_report = ChangeGraphReport(
        total_nodes=2,
        total_edges=1,
        changed_entities=["app/billing.py::calculate_discount"],
        impacted_entities_count=0,
        impacted_files_count=0,
        impacted_entities=[],
        impacted_files=[],
    )

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={},
    )

    assert selection.total_tests_discovered == 0
    assert selection.selected_tests_count == 0
    assert len(selection.recommended_tests) == 0
    assert "No supported Python test suites" in selection.summary


def test_selector_missing_or_unparsed_source(selector):
    """Test unparsed test file is recorded in limitations without crashing."""
    graph_report = ChangeGraphReport(
        total_nodes=1,
        total_edges=0,
        changed_entities=["app/billing.py"],
        impacted_entities_count=0,
        impacted_files_count=0,
        impacted_entities=[],
        impacted_files=[],
    )

    selection = selector.select_tests(
        change_graph_report=graph_report,
        test_parse_results={"tests/test_missing.py": None},
    )

    assert any("Source code unavailable" in lim for lim in selection.limitations)
