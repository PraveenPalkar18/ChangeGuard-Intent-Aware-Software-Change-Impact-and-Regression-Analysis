"""Unit and integration tests for Change and Dependency Graph (Milestone 5)."""
import pytest
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.graph.models import NodeType, EdgeType
from backend.app.graph.graph_builder import ChangeGraphBuilder


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


def test_graph_builder_nodes_and_containment(parser):
    """Test file and entity node creation with CONTAINS hierarchy."""
    source = """class BillingService:
    def calculate_discount(self, price, rate):
        return price * (1 - rate)
"""
    parse_result = parser.parse_source("app/billing.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/billing.py": parse_result})

    graph = builder.graph
    # Verify nodes
    assert graph.has_node("file:app/billing.py")
    assert graph.nodes["file:app/billing.py"]["node_type"] == NodeType.FILE

    class_node_id = "entity:app/billing.py::BillingService"
    assert graph.has_node(class_node_id)
    assert graph.nodes[class_node_id]["node_type"] == NodeType.CLASS

    method_node_id = "entity:app/billing.py::BillingService.calculate_discount"
    assert graph.has_node(method_node_id)
    assert graph.nodes[method_node_id]["node_type"] == NodeType.METHOD

    # Verify containment edges
    assert graph.has_edge("file:app/billing.py", class_node_id)
    assert graph.get_edge_data("file:app/billing.py", class_node_id)["edge_type"] == EdgeType.CONTAINS

    assert graph.has_edge(class_node_id, method_node_id)
    assert graph.get_edge_data(class_node_id, method_node_id)["edge_type"] == EdgeType.CONTAINS


def test_graph_builder_imports_and_calls(parser):
    """Test cross-file import and function call edges."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    checkout_src = """from app.billing import calculate_discount

def process_order(price, rate):
    discounted = calculate_discount(price, rate)
    return discounted
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_checkout = parser.parse_source("app/checkout.py", checkout_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/billing.py": parse_billing,
        "app/checkout.py": parse_checkout,
    })

    graph = builder.graph
    calc_node = "entity:app/billing.py::calculate_discount"
    process_node = "entity:app/checkout.py::process_order"

    assert graph.has_node(calc_node)
    assert graph.has_node(process_node)

    # Verify IMPORTS edge: checkout.py imports calculate_discount
    assert graph.has_edge("file:app/checkout.py", calc_node)
    assert graph.get_edge_data("file:app/checkout.py", calc_node)["edge_type"] == EdgeType.IMPORTS

    # Verify CALLS edge: process_order -> calculate_discount
    assert graph.has_edge(process_node, calc_node)
    assert graph.get_edge_data(process_node, calc_node)["edge_type"] == EdgeType.CALLS


def test_compute_impact_downstream_propagation(parser):
    """Test downstream traversal finding callers and dependent files with explainable paths."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    checkout_src = """from app.billing import calculate_discount

def process_order(price, rate):
    return calculate_discount(price, rate)
"""
    parse_billing = parser.parse_source("app/billing.py", billing_src)
    parse_checkout = parser.parse_source("app/checkout.py", checkout_src)

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/billing.py": parse_billing,
        "app/checkout.py": parse_checkout,
    })

    # Suppose calculate_discount in app/billing.py was changed in a PR diff hunk
    report = builder.compute_impact(["app/billing.py::calculate_discount"])

    assert report.total_nodes >= 4
    assert report.impacted_entities_count >= 1
    assert "app/checkout.py" in report.impacted_files

    # Find process_order in impacted entities
    impacted_names = [e.name for e in report.impacted_entities]
    assert "process_order" in impacted_names

    # Verify explainable path
    process_impact = next(e for e in report.impacted_entities if e.name == "process_order")
    assert len(process_impact.impact_paths) > 0
    path_desc = process_impact.impact_paths[0].path_description
    assert "calculate_discount" in path_desc
    assert "called by" in path_desc or "process_order" in path_desc


def test_compute_impact_cycle_safety(parser):
    """Test mutually recursive functions (cycles) do not cause infinite loops during BFS traversal."""
    source = """def ping(n):
    if n > 0:
        return pong(n - 1)
    return 0

def pong(n):
    if n > 0:
        return ping(n - 1)
    return 1
"""
    parse_res = parser.parse_source("app/recursion.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/recursion.py": parse_res})

    # Change ping
    report = builder.compute_impact(["app/recursion.py::ping"], max_depth=5)

    assert report.total_nodes >= 3
    # Traversal should finish safely and identify pong as impacted
    impacted_names = [e.name for e in report.impacted_entities]
    assert "pong" in impacted_names


def test_missing_source_and_unsupported_language_handling(parser):
    """Test graceful handling of unparsed/missing source and unsupported languages without crashes."""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "README.md": None,
        "assets/logo.png": None,
    })

    graph = builder.graph
    assert graph.has_node("file:README.md")
    assert graph.has_node("file:assets/logo.png")

    report = builder.compute_impact(["file:README.md"])
    assert report.total_nodes == 2
    assert len(report.graph_limitations) > 0
    assert any("Source code unavailable" in lim for lim in report.graph_limitations)


def test_unresolved_external_import_does_not_invent_edges(parser):
    """Test external libraries (e.g. sys, math) do not invent non-existent repository edges."""
    source = """import sys
import os.path

def get_platform():
    return sys.platform
"""
    parse_res = parser.parse_source("app/platform_check.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/platform_check.py": parse_res})

    graph = builder.graph
    # Verify no fake nodes created for sys or os.path
    assert not graph.has_node("file:sys.py")
    assert not graph.has_node("file:os.path.py")
